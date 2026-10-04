"""Modo /narrar: mirar el video, escribir un guion y ponerle voz.

Tres cosas que lo separan de /editar:

1. **Gemini VE el video.** Se le mandan frames y se le pide que describa paso a paso lo que pasa
   antes de escribir nada. Sin eso el guion sale de la transcripción, que en un clip de juego son
   gritos sueltos, y el resultado es una voz en off hablando de algo que no está en pantalla.
2. **El guion se aprueba antes de gastar nada.** Gemini puede inventar detalles: ya pasó con un
   Short titulado "Reconoce que no conoce a Zelda" donde Zelda era un perro muerto. Narrar algo
   inventado con voz de locutor es bastante peor que escribirlo. Por eso el guion llega primero.
3. **La voz es local.** Piper, por cuota más que por calidad: el free tier de Gemini son ~20
   requests/día y ya se agota con los textos. Ver la comparación medida en settings.yaml.
"""

from __future__ import annotations

import html as _html
import json
import logging
import math
import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from .media import audio_con_crossfade, cola_audio, find_bin, run
from .reglas import REGLAS_CLARIDAD

log = logging.getLogger(__name__)

# Palabras por segundo de la voz, para pedirle a Gemini un guion del largo correcto y avisar cuando
# se pasó. MEDIDO en la Pi el 2026-09-27 con es_AR-daniela-high y la pausa entre frases: 3,02 y
# 3,17 en dos guiones de 101 y 83 palabras. Antes decía 2,5 (estimado, nunca medido), y los guiones
# de /narrar y /serie salían ~20 % más cortos que el video.
PALABRAS_POR_SEGUNDO = 3.1

SISTEMA = """Escribís la voz en off de un video vertical corto, en español rioplatense (vos, no tú).

Te paso frames del video en orden y, si hay, lo que se escucha. Primero DESCRIBÍS lo que pasa paso
a paso, mirando las imágenes; después escribís el guion.

Reglas del guion:
- Arranca con un gancho de una frase que haga quedarse: una pregunta, algo raro que se ve, o el
  final adelantado. Nada de "en este video vamos a ver".
- Contá SOLO lo que se ve. Si no estás seguro de qué es algo, no lo nombres: decilo de forma
  general. Es preferible un guion vago a uno que inventa.
- Nada de nombres propios (juegos, personas, lugares, marcas) que no aparezcan en lo que se
  escucha o no se lean claramente en pantalla.
- Hablado, no escrito: frases cortas, como se lo contarías a un amigo.
- Sin emojis, sin hashtags, sin "suscribite".
""" + REGLAS_CLARIDAD + """
Si te paso el audio, decí también si tiene música: "ninguna", "de_fondo" (música sin letra o que
no reconocés) o "cancion" (una canción con letra, o un tema que reconocés). Si reconocés cuál es,
ponela en `cancion` ("Artista – Tema"); si no, dejalo vacío. No adivines el nombre.

Respondé solo con el JSON pedido."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "que_pasa": {"type": "ARRAY", "items": {"type": "STRING"}},
        "guion": {"type": "STRING"},
        "sensible": {"type": "BOOLEAN"},
        "confianza": {"type": "INTEGER"},
        "musica": {"type": "STRING", "enum": ["ninguna", "de_fondo", "cancion"]},
        "cancion": {"type": "STRING"},
    },
    "required": ["que_pasa", "guion", "sensible", "confianza"],
}

MUSICAS = ("ninguna", "de_fondo", "cancion")


@dataclass
class Guion:
    texto: str
    que_pasa: tuple[str, ...] = ()
    sensible: bool = False
    confianza: int = 0          # 1 a 10: cuánto entendió de lo que vio
    palabras: int = 0
    segundos_estimados: float = 0.0
    musica: str = ""            # ninguna | de_fondo | cancion; vacío = no se le pasó el audio
    cancion: str = ""           # "Artista – Tema" si la reconoció

    def a_dict(self) -> dict:
        return {"texto": self.texto, "que_pasa": list(self.que_pasa), "sensible": self.sensible,
                "confianza": self.confianza, "palabras": self.palabras,
                "segundos_estimados": round(self.segundos_estimados, 1),
                "musica": self.musica, "cancion": self.cancion}

    @classmethod
    def de_dict(cls, d: dict) -> "Guion":
        return cls(d["texto"], tuple(d.get("que_pasa") or ()), bool(d.get("sensible")),
                   int(d.get("confianza") or 0), int(d.get("palabras") or 0),
                   float(d.get("segundos_estimados") or 0), str(d.get("musica") or ""),
                   str(d.get("cancion") or ""))


def _medir(texto: str) -> tuple[int, float]:
    n = len(re.findall(r"[^\s]+", texto))
    return n, n / PALABRAS_POR_SEGUNDO


def escribir(cliente, duracion: float, transcripcion: str, imagenes: list[bytes],
             correccion: str = "", audio: bytes | None = None) -> Guion:
    """Le pide a Gemini el guion. `correccion` es lo que pediste cambiar en el intento anterior.

    `audio`: el del video, para que diga si hay música. Va en la MISMA llamada que el guion: la
    cuota de Gemini (~20 por día) no da para una llamada aparte."""
    objetivo = max(4, int(duracion * PALABRAS_POR_SEGUNDO))
    prompt = (f"El video dura {duracion:.0f} segundos, así que el guion tiene que tener alrededor "
              f"de {objetivo} palabras (ni la mitad ni el doble).\n"
              f"Te mando {len(imagenes)} frames en orden.\n")
    if transcripcion.strip():
        prompt += f"Lo que se escucha: {transcripcion[:1500]}\n"
    else:
        prompt += "No se escucha nada claro: guiate por las imágenes.\n"
    prompt += ("\nconfianza: del 1 al 10, cuánto entendiste REALMENTE de lo que pasa mirando los "
               "frames. Si es bajo, escribí un guion más general en vez de inventar.")
    if correccion:
        prompt += f"\n\nEl guion anterior no sirvió. Lo que hay que cambiar: {correccion}"
    if audio:
        prompt += " También te paso el audio del video: decí si tiene música (campo `musica`)."
    crudo = cliente.json(SISTEMA, prompt, SCHEMA, temperatura=0.6, imagenes=imagenes, audio=audio)
    d = json.loads(crudo)
    texto = str(d.get("guion") or "").strip()
    palabras, segundos = _medir(texto)
    musica = str(d.get("musica") or "") if audio else ""
    return Guion(texto=texto, que_pasa=tuple(d.get("que_pasa") or ()),
                 sensible=bool(d.get("sensible")), confianza=int(d.get("confianza") or 0),
                 palabras=palabras, segundos_estimados=segundos,
                 musica=musica if musica in MUSICAS else "",
                 cancion=str(d.get("cancion") or "").strip() if musica == "cancion" else "")


def audio_para_gemini(video: Path, max_s: float = 60.0) -> bytes | None:
    """El audio del video como MP3 mono chico (32 kbps, 16 kHz): ~240 KB por minuto. None si el
    video no tiene audio (no hay nada que preguntar)."""
    if not _tiene_audio(video):
        return None
    r = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i",
                        str(video.resolve()), "-t", str(max_s), "-vn", "-ac", "1", "-ar", "16000",
                        "-b:a", "32k", "-f", "mp3", "-"], capture_output=True)
    return r.stdout if r.returncode == 0 and r.stdout else None


def aviso_musica(g: Guion) -> str:
    """Si hay música, avisar ANTES de sintetizar: al 15 % debajo de la voz, Content ID la encuentra
    igual. La salida es `sin audio`: el original se silencia y queda solo la voz."""
    if g.musica == "cancion":
        cual = f" (me suena a <b>{_html.escape(g.cancion)}</b>)" if g.cancion else ""
        return (f"🎵 El video tiene una canción{cual}. Aunque quede al 15 % debajo de la voz, "
                "Content ID la puede reclamar: te sugiero <b>✅ Aprobar sin audio</b>, que silencia "
                "el original y deja solo la voz.")
    if g.musica == "de_fondo":
        return ("🎵 El video tiene música de fondo. Si no sabés de dónde es, mejor "
                "<b>✅ Aprobar sin audio</b>: silencia el original y deja solo la voz.")
    return ""


def _config_piper(ajustes):
    """`ajustes` es la sección `voz` de settings (o None = lo que trae el modelo)."""
    if ajustes is None:
        return None
    from piper import SynthesisConfig

    return SynthesisConfig(length_scale=ajustes.length_scale, noise_scale=ajustes.noise_scale,
                           noise_w_scale=ajustes.noise_w_scale)


VOZ_SR = 48000   # la voz se procesa SIEMPRE a 48 kHz (Santi, 2026-10-04)


def a_48k(wav: Path) -> Path:
    """La voz a 48 kHz, UNA vez y con el mejor re-muestreo (soxr, 28 bits), en el mismo archivo.
    Nada de cambiar el tono (2026-10-04: el +1,5 semitonos sobre los 22 kHz de Piper dejaba la voz
    cortada a 9,8 kHz y sonaba horrible): de acá en más ningún paso baja la calidad. Ojo: arriba de
    lo que da el motor no aparece nada (Piper llega a ~11 kHz, Gemini TTS a ~12 kHz)."""
    import wave as _wave

    with _wave.open(str(wav)) as w:
        if w.getframerate() == VOZ_SR:
            return wav
    tmp = wav.with_name(wav.stem + ".48k.wav")
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav.resolve()),
         "-af", f"aresample={VOZ_SR}:resampler=soxr:precision=28", "-c:a", "pcm_s16le",
         str(tmp.resolve())])
    tmp.replace(wav)
    return wav


def sintetizar(texto: str, modelo: Path, salida: Path, ajustes=None) -> Path:
    """Piper: texto → wav. Corre local, sin red y sin cuota."""
    from piper import PiperVoice

    salida.parent.mkdir(parents=True, exist_ok=True)
    voz = PiperVoice.load(str(modelo))
    with wave.open(str(salida), "wb") as w:
        voz.synthesize_wav(texto, w, syn_config=_config_piper(ajustes))
    return a_48k(salida)


def sintetizar_frases(frases: list[str], modelo: Path, salida: Path,
                      pausa_s: float = 0.3, ajustes=None) -> tuple[Path, list[float]]:
    """Piper frase por frase, pegadas con una pausa: un solo wav y lo que dura cada frase (con su
    pausa). Las efemérides cambian de foto en cada frase, y así los cortes caen justo donde
    termina lo que se dice, sin adivinar tiempos. La voz se carga una sola vez."""
    import io

    from piper import PiperVoice

    salida.parent.mkdir(parents=True, exist_ok=True)
    voz = PiperVoice.load(str(modelo))
    partes, duraciones, formato = [], [], None
    for frase in frases:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            voz.synthesize_wav(frase, w, syn_config=_config_piper(ajustes))
        buf.seek(0)
        with wave.open(buf) as r:
            formato = formato or (r.getnchannels(), r.getsampwidth(), r.getframerate())
            datos = r.readframes(r.getnframes())
        silencio = b"\x00" * (int(formato[2] * pausa_s) * formato[0] * formato[1])
        partes.append(datos + silencio)
        duraciones.append(len(datos + silencio) / (formato[0] * formato[1] * formato[2]))
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(formato[0])
        w.setsampwidth(formato[1])
        w.setframerate(formato[2])
        w.writeframes(b"".join(partes))
    a_48k(salida)
    return salida, duraciones


def duracion_wav(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def mezclar(video: Path, voz: Path, salida: Path, volumen_original: float = 0.15,
            sin_original: bool = False) -> Path:
    """Voz encima, audio del video de fondo. Si el video no tiene audio, va solo la voz.

    `sin_original` (la opción `sin audio`): el original se descarta entero, no se baja a 0. Con
    volumen 0 el stream seguiría en la mezcla, y lo que se quiere es que no haya nada que reclamar.

    El video NO se re-encodea: se copia el stream de imagen y solo se rearma el audio. En la Pi el
    render es la etapa más cara, y volver a pasarlo por x264 acá lo duplicaría al pedo.
    """
    salida.parent.mkdir(parents=True, exist_ok=True)
    tiene_audio = _tiene_audio(video) and not sin_original
    # La cola (media.cola_audio) deja el audio del largo EXACTO del video, con los fundidos. Antes
    # era `-shortest` + apad: sin apad, -shortest cortaba el VIDEO al largo de la voz (medido: un
    # video de 40 s con una voz de 30 salía de 30 s); con la cola ni hace falta -shortest.
    cola = cola_audio(_duracion_video(video))
    if tiene_audio:
        filtro = (f"[0:a]volume={volumen_original}[fondo];"
                  f"[1:a]aresample=48000[voz];"
                  f"[fondo][voz]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                  f"{cola}[a]")
    else:
        filtro = f"[1:a]aresample=48000,{cola}[a]"
    mapeo = ["-map", "0:v", "-map", "[a]"]
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video.resolve()), "-i", str(voz.resolve()),
         "-filter_complex", filtro, *mapeo,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         str(salida.resolve())])
    return salida


def _duracion_video(video: Path) -> float:
    from .media import probe

    try:
        return probe(video).duracion
    except Exception:
        return 0.0


def _tiene_audio(video: Path) -> bool:
    from .media import probe

    try:
        return probe(video).tiene_audio
    except Exception:
        return False


def subtitular_voz(wav: Path, cfg_subs, texto_guion: str = "",
                   palabra_por_palabra: bool = False) -> list:
    """Subtítulos de LA VOZ, no del audio original: se transcribe el wav sintetizado.

    Se pasa Whisper por encima de la propia voz en vez de repartir el guion a ojo por la duración.
    Suena al revés (ya sabemos qué dice), pero es lo que da los tiempos REALES de cada palabra, que
    es lo único que hace que el subtítulo caiga cuando se escucha. Repartir el texto de forma
    pareja se desfasa apenas hay una pausa.
    """
    from . import subtitles as sub

    palabras = palabras_de_voz(wav, cfg_subs)
    if texto_guion.strip():
        palabras, _ = alinear_a_guion(palabras, [texto_guion], duracion_wav(wav))
    if palabra_por_palabra:
        return sub.palabra_por_palabra(palabras, cfg_subs)
    return sub.armar_subtitulos(palabras, cfg_subs)


def palabras_de_voz(wav: Path, cfg_subs) -> list:
    """Whisper sobre la voz sintetizada: los tiempos reales de cada palabra."""
    from . import subtitles as sub

    modelo = sub.cargar_modelo(cfg_subs)
    try:
        return sub.transcribir(modelo, wav, cfg_subs, duracion_wav(wav))
    finally:
        del modelo


def recortar_inicio(wav: Path, palabras: list, frases: list[str],
                    margen_s: float = 0.12) -> tuple[list, float]:
    """Si la voz dice algo ANTES del guion (Gemini TTS leyó en voz alta la instrucción de tono,
    visto el 2026-09-28), se corta el audio hasta donde arranca el guion. Devuelve las palabras
    corridas al nuevo cero y cuántos segundos se sacaron (0 si arrancaba bien).

    El arranque se reconoce por las 3 primeras palabras del guion seguidas en lo que oyó Whisper."""
    guion = [_clave(t) for f in frases for t in f.split()][:3]
    oidas = [_clave(p.texto) for p in palabras]
    if len(guion) < 3:
        return palabras, 0.0
    for i in range(len(oidas) - 2):
        if oidas[i:i + 3] == guion:
            corte = max(palabras[i].inicio - margen_s, 0.0)
            if corte < 0.4:
                return palabras, 0.0
            tmp = wav.with_name(wav.stem + ".recorte.wav")
            run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss",
                 f"{corte:.3f}", "-i", str(wav.resolve()), str(tmp.resolve())])
            tmp.replace(wav)
            from .subtitles import Palabra

            return [Palabra(p.inicio - corte, p.fin - corte, p.texto) for p in palabras[i:]], corte
    return palabras, 0.0


def _clave(t: str) -> str:
    sin = "".join(c for c in __import__("unicodedata").normalize("NFKD", t)
                  if not __import__("unicodedata").combining(c))
    return re.sub(r"[^a-z0-9]", "", sin.lower())


def alinear_a_guion(palabras: list, frases: list[str], fin_audio: float) -> tuple[list, list[float]]:
    """Los tiempos de Whisper con el TEXTO del guion, y cuándo arranca cada frase.

    Whisper escucha la voz y a veces escribe otra cosa: "propia" por "propio", "Jean" y
    "-François" en dos (visto el 2026-09-27). El guion es lo que se aprobó, así que los subtítulos
    llevan sus palabras y de Whisper se toman solo los tiempos: se emparejan las dos secuencias
    (difflib) y lo que no empareja se reparte entre los vecinos que sí.

    Devuelve (palabras del guion con su tiempo, inicio de cada frase en segundos). Lo segundo es lo
    que permite cambiar de foto por frase cuando la voz viene en un solo audio (Gemini TTS)."""
    import difflib

    from .subtitles import Palabra

    tokens = [(i, t) for i, f in enumerate(frases) for t in f.split()]
    if not tokens:
        return [], [0.0] * len(frases)
    a, b = [_clave(t) for _, t in tokens], [_clave(p.texto) for p in palabras]
    tiempos: list = [None] * len(tokens)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            p = palabras[blk.b + k]
            tiempos[blk.a + k] = (p.inicio, p.fin)
    # Lo que no emparejó: se reparte parejo entre el último tiempo conocido y el siguiente.
    i = 0
    while i < len(tokens):
        if tiempos[i] is not None:
            i += 1
            continue
        j = i
        while j < len(tokens) and tiempos[j] is None:
            j += 1
        desde = tiempos[i - 1][1] if i > 0 else 0.0
        hasta = tiempos[j][0] if j < len(tokens) else fin_audio
        paso = max(hasta - desde, 0.0) / (j - i)
        for k in range(i, j):
            tiempos[k] = (desde + paso * (k - i), desde + paso * (k - i + 1))
        i = j
    alineadas = [Palabra(ini, max(fin, ini + 0.05), tok) for (_, tok), (ini, fin) in zip(tokens, tiempos)]
    inicios, visto = [0.0] * len(frases), set()
    for (f, _), (ini, _) in zip(tokens, tiempos):
        if f not in visto:
            inicios[f] = ini
            visto.add(f)
    inicios[0] = 0.0
    return alineadas, inicios


def aviso_largo(guion: Guion, duracion: float) -> str:
    """Si el guion no entra en el video, hay que decirlo ANTES de sintetizar."""
    if duracion <= 0:
        return ""
    ratio = guion.segundos_estimados / duracion
    if ratio > 1.25:
        sobra = guion.segundos_estimados - duracion
        return (f"⚠️ El guion son ~{guion.segundos_estimados:.0f}s hablados y el video dura "
                f"{duracion:.0f}s: sobran ~{sobra:.0f}s. Pedime que lo acorte con ✏️.")
    if ratio < 0.5:
        return (f"⚠️ El guion son ~{guion.segundos_estimados:.0f}s y el video dura "
                f"{duracion:.0f}s: va a quedar mucho silencio.")
    return ""


# ---- videos largos: resumir por escenas antes de narrar -----------------------------
# Un video de más de LARGO_MAX_S (un proceso: una receta, una construcción, una restauración) no
# entra en un Short. Antes del guion se arma un resumen: cambios de escena con ffmpeg → un frame por
# escena → Gemini elige 8-10 pasos en orden (inicio, intermedios, resultado) → 4-5 s de cada uno →
# un video de 40-55 s. Los pasos se aprueban ANTES de cortar, igual que el guion antes de la voz.

LARGO_MAX_S = 90
PASOS_MIN, PASOS_MAX = 8, 10
SEG_MIN, SEG_MAX = 4.0, 5.0
RESUMEN_OBJETIVO_S = 48.0      # 8 pasos → 40 s, 9 → 45 s, 10 → 48 s: siempre entre 40 y 55
ESCENAS_MAX = 40               # frames que van a Gemini: más no cambia la elección y gasta tokens
ESCENAS_MIN = 12               # un plano secuencia sin cortes igual tiene que dar de dónde elegir
ESCENA_MIN_S = 1.0


class NarrarError(RuntimeError):
    pass


def cortes_de_escena(video: Path, umbral: float = 0.3) -> list[float]:
    """Segundos donde ffmpeg ve un cambio de escena (`select=gt(scene,U)` + showinfo).

    Se achica a 320 px antes de medir: decodificar es inevitable, pero comparar frames chicos es
    mucho más barato en la Pi y el puntaje de escena casi no cambia."""
    r = run([find_bin("ffmpeg"), "-hide_banner", "-nostats", "-i", str(video.resolve()),
             "-vf", f"scale=320:-2,select='gt(scene,{umbral})',showinfo", "-an", "-f", "null", "-"])
    return [float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


def escenas(cortes: list[float], duracion: float, minimo: int = ESCENAS_MIN,
            maximo: int = ESCENAS_MAX, min_s: float = ESCENA_MIN_S) -> list[tuple[float, float]]:
    """Cortes → [(inicio, fin)] contiguos, sin escenas de menos de `min_s`, entre `minimo` y `maximo`.

    Muy cortas o demasiadas (un video muy editado): se funde la más corta con su vecina.
    Muy pocas (un plano secuencia): se parte al medio la más larga, hasta llegar al mínimo.
    """
    puntos = [0.0] + sorted(c for c in cortes if 0 < c < duracion) + [duracion]
    out = [[a, b] for a, b in zip(puntos, puntos[1:]) if b > a]

    def largo(k: int) -> float:
        return out[k][1] - out[k][0]

    def fundir(i: int) -> None:
        """La escena i se une con la vecina más corta."""
        if i == 0:
            j = 1
        elif i == len(out) - 1:
            j = i - 1
        else:
            j = i - 1 if largo(i - 1) <= largo(i + 1) else i + 1
        a, b = sorted((i, j))
        out[a:b + 1] = [[out[a][0], out[b][1]]]

    while len(out) > 1 and min(largo(k) for k in range(len(out))) < min_s:
        fundir(min(range(len(out)), key=largo))
    while len(out) > maximo:
        fundir(min(range(len(out)), key=largo))
    while len(out) < minimo:
        i = max(range(len(out)), key=largo)
        if largo(i) < 2 * min_s:
            break
        a, b = out[i]
        out[i:i + 1] = [[a, (a + b) / 2], [(a + b) / 2, b]]
    return [(round(a, 2), round(b, 2)) for a, b in out]


def frames_en(video: Path, tiempos: list[float], ancho: int = 384, calidad: int = 75) -> list[bytes]:
    """Un JPEG chico por cada segundo pedido (el medio de cada escena)."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise NarrarError(f"No puedo abrir {video.name}")
    out = []
    try:
        for t in tiempos:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                raise NarrarError(f"No pude leer el frame del segundo {t:.1f}")
            h, w = frame.shape[:2]
            frame = cv2.resize(frame, (ancho, int(h * ancho / w)))
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, calidad])
            out.append(buf.tobytes())
    finally:
        cap.release()
    return out


SISTEMA_PASOS = """Resumís un video largo de un PROCESO (una receta, una construcción, una
restauración, un armado) en un video corto que se entienda solo.

Te paso un frame por escena, en orden. Elegís las escenas que cuentan el proceso de punta a punta:
la primera muestra CÓMO ARRANCA, las del medio los pasos que cambian algo visible, y la última el
RESULTADO FINAL. Nada de escenas repetidas, de gente hablando a cámara sin hacer nada, ni de
pantallas de título.

Cada paso lleva una línea corta de lo que SE VE en ese frame. Si no estás seguro de qué es algo,
describilo de forma general: no inventes materiales, herramientas ni nombres.
Respondé solo con el JSON pedido."""

SCHEMA_PASOS = {
    "type": "OBJECT",
    "properties": {
        "pasos": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"escena": {"type": "INTEGER"}, "descripcion": {"type": "STRING"}},
            "required": ["escena", "descripcion"]}},
        "sensible": {"type": "BOOLEAN"},
    },
    "required": ["pasos", "sensible"],
}


@dataclass
class Paso:
    escena: int            # índice en la lista de escenas (desde 0)
    descripcion: str

    def a_dict(self) -> dict:
        return {"escena": self.escena, "descripcion": self.descripcion}


def validar_pasos(d: dict, n_escenas: int) -> list[str]:
    pasos = d.get("pasos") if isinstance(d, dict) else None
    if not isinstance(pasos, list) or not all(isinstance(p, dict) for p in pasos):
        return ["falta la lista de pasos"]
    errores = []
    minimo, maximo = min(PASOS_MIN, n_escenas), min(PASOS_MAX, n_escenas)
    if not minimo <= len(pasos) <= maximo:
        errores.append(f"tienen que ser entre {minimo} y {maximo} pasos, no {len(pasos)}")
    nums = [p.get("escena") for p in pasos]
    if any(not isinstance(x, int) or not 1 <= x <= n_escenas for x in nums):
        errores.append(f"las escenas van del 1 al {n_escenas}")
    elif nums != sorted(set(nums)):
        errores.append("las escenas tienen que ir en orden y sin repetir")
    if any(not str(p.get("descripcion") or "").strip() for p in pasos):
        errores.append("cada paso necesita su descripción")
    return errores


def elegir_pasos(cliente, escenas_: list[tuple[float, float]], imagenes: list[bytes],
                 transcripcion: str = "", correccion: str = "",
                 anteriores: list[Paso] | None = None, reintentos: int = 1) -> tuple[list[Paso], bool]:
    """Gemini elige los pasos. Devuelve (pasos, sensible). Reintenta una vez si no valida."""
    lista = "\n".join(f"escena {i}: {a:.0f}-{b:.0f} s" for i, (a, b) in enumerate(escenas_, 1))
    prompt = (f"Son {len(escenas_)} escenas; la imagen k es la escena k.\n{lista}\n\n"
              f"Elegí entre {min(PASOS_MIN, len(escenas_))} y {min(PASOS_MAX, len(escenas_))}, "
              "en orden. `escena` es el número de la lista (desde 1). `descripcion`: una línea de "
              "hasta 80 caracteres.")
    if transcripcion.strip():
        prompt += f"\n\nLo que se escucha (puede ayudar a ubicar los pasos): {transcripcion[:1200]}"
    if correccion:
        antes = ", ".join(str(p.escena + 1) for p in anteriores or [])
        prompt += (f"\n\nLa elección anterior fue: escenas {antes}. No sirvió. "
                   f"Lo que hay que cambiar: {correccion}")
    errores: list[str] = []
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        d = json.loads(cliente.json(SISTEMA_PASOS, prompt + extra, SCHEMA_PASOS, temperatura=0.3,
                                    imagenes=imagenes))
        errores = validar_pasos(d, len(escenas_))
        if not errores:
            pasos = [Paso(int(p["escena"]) - 1, str(p["descripcion"]).strip()[:90])
                     for p in d["pasos"]]
            return pasos, bool(d.get("sensible"))
    raise NarrarError("Gemini no eligió pasos válidos: " + "; ".join(errores))


def ventanas(escenas_: list[tuple[float, float]], pasos: list[Paso],
             duracion: float) -> list[tuple[float, float]]:
    """4-5 s de cada paso, centrados en su escena, sin pisarse y dentro del video.

    El largo por paso sale del total buscado (48 s): 8 pasos → 5 s c/u (40 s), 10 → 4,8 s (48 s)."""
    seg = max(SEG_MIN, min(SEG_MAX, RESUMEN_OBJETIVO_S / max(len(pasos), 1)))
    out: list[tuple[float, float]] = []
    for p in pasos:
        a, b = escenas_[p.escena]
        ini = max(0.0, min((a + b) / 2 - seg / 2, duracion - seg))
        if out and ini < out[-1][1]:
            ini = out[-1][1]
        fin = min(duracion, ini + seg)
        if fin - ini >= 1.0:
            out.append((round(ini, 2), round(fin, 2)))
    return out


def armar_resumen(video: Path, tramos: list[tuple[float, float]], salida: Path) -> Path:
    """Corta los tramos y los pega en orden, en una sola pasada de ffmpeg. Re-encodea a propósito:
    los cortes no caen en keyframes y con `-c copy` cada tramo arrancaría con frames congelados."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    audio = _tiene_audio(video)
    partes, entradas = [], ""
    for i, (a, b) in enumerate(tramos):
        partes.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]")
        entradas += f"[v{i}]"
    partes.append(f"{entradas}concat=n={len(tramos)}:v=1:a=0[v]")
    if audio:   # el audio se pega con crossfade corto en cada unión (media.audio_con_crossfade)
        largo = _duracion_video(video) or max(b for _, b in tramos)
        partes.append(audio_con_crossfade([("[0:a]", a, b, largo) for a, b in tramos], "[ac]"))
        partes.append(f"[ac]{cola_audio(sum(b - a for a, b in tramos))}[a]")
    mapeo = ["-map", "[v]"] + (["-map", "[a]", "-c:a", "aac", "-b:a", "160k"] if audio else [])
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video.resolve()),
         "-filter_complex", ";".join(partes), *mapeo,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         str(salida.resolve())])
    return salida


def hoja_de_pasos(imagenes: list[bytes], salida: Path, columnas: int = 2, ancho: int = 360) -> Path:
    """Una sola imagen con las miniaturas numeradas. Va con la lista de pasos en el caption y los
    botones ✅/✏️ abajo: un álbum de Telegram no admite botones."""
    import cv2
    import numpy as np

    tiles = []
    for n, img in enumerate(imagenes, 1):
        f = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_COLOR)
        h, w = f.shape[:2]
        f = cv2.resize(f, (ancho, int(h * ancho / w)))
        cv2.rectangle(f, (0, 0), (54 if n < 10 else 78, 44), (0, 0, 0), -1)
        cv2.putText(f, str(n), (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2,
                    cv2.LINE_AA)
        tiles.append(f)
    alto = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, alto - t.shape[0], 0, 0, cv2.BORDER_CONSTANT) for t in tiles]
    filas = [tiles[i:i + columnas] for i in range(0, len(tiles), columnas)]
    filas[-1] += [np.zeros_like(tiles[0])] * (columnas - len(filas[-1]))
    salida.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(salida), np.vstack([np.hstack(f) for f in filas]),
                [cv2.IMWRITE_JPEG_QUALITY, 82])
    return salida


def texto_pasos(pasos: list[Paso], tramos: list[tuple[float, float]], duracion: float) -> str:
    """Una línea por paso, con el minuto del original, para leer debajo de la hoja."""
    import html as _html

    total = sum(b - a for a, b in tramos)
    lineas = [f"<b>Resumen en {len(pasos)} pasos</b> (video de {duracion / 60:.1f} min → "
              f"{total:.0f} s)"]
    for n, (p, (a, _)) in enumerate(zip(pasos, tramos), 1):
        lineas.append(f"{n}. <i>{int(a // 60)}:{int(a % 60):02d}</i> {_html.escape(p.descripcion)}")
    return "\n".join(lineas)
