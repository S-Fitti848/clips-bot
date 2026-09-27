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

import json
import logging
import math
import re
import wave
from dataclasses import dataclass
from pathlib import Path

from .media import find_bin, run

log = logging.getLogger(__name__)

# Una voz en español ronda las 2,5 palabras por segundo a ritmo de narración. Sirve para pedirle a
# Gemini un guion del largo correcto y para avisar cuando se pasó.
PALABRAS_POR_SEGUNDO = 2.5

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

Respondé solo con el JSON pedido."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "que_pasa": {"type": "ARRAY", "items": {"type": "STRING"}},
        "guion": {"type": "STRING"},
        "sensible": {"type": "BOOLEAN"},
        "confianza": {"type": "INTEGER"},
    },
    "required": ["que_pasa", "guion", "sensible", "confianza"],
}


@dataclass
class Guion:
    texto: str
    que_pasa: tuple[str, ...] = ()
    sensible: bool = False
    confianza: int = 0          # 1 a 10: cuánto entendió de lo que vio
    palabras: int = 0
    segundos_estimados: float = 0.0

    def a_dict(self) -> dict:
        return {"texto": self.texto, "que_pasa": list(self.que_pasa), "sensible": self.sensible,
                "confianza": self.confianza, "palabras": self.palabras,
                "segundos_estimados": round(self.segundos_estimados, 1)}

    @classmethod
    def de_dict(cls, d: dict) -> "Guion":
        return cls(d["texto"], tuple(d.get("que_pasa") or ()), bool(d.get("sensible")),
                   int(d.get("confianza") or 0), int(d.get("palabras") or 0),
                   float(d.get("segundos_estimados") or 0))


def _medir(texto: str) -> tuple[int, float]:
    n = len(re.findall(r"[^\s]+", texto))
    return n, n / PALABRAS_POR_SEGUNDO


def escribir(cliente, duracion: float, transcripcion: str, imagenes: list[bytes],
             correccion: str = "") -> Guion:
    """Le pide a Gemini el guion. `correccion` es lo que pediste cambiar en el intento anterior."""
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
    crudo = cliente.json(SISTEMA, prompt, SCHEMA, temperatura=0.6, imagenes=imagenes)
    d = json.loads(crudo)
    texto = str(d.get("guion") or "").strip()
    palabras, segundos = _medir(texto)
    return Guion(texto=texto, que_pasa=tuple(d.get("que_pasa") or ()),
                 sensible=bool(d.get("sensible")), confianza=int(d.get("confianza") or 0),
                 palabras=palabras, segundos_estimados=segundos)


def sintetizar(texto: str, modelo: Path, salida: Path) -> Path:
    """Piper: texto → wav. Corre local, sin red y sin cuota."""
    from piper import PiperVoice

    salida.parent.mkdir(parents=True, exist_ok=True)
    voz = PiperVoice.load(str(modelo))
    with wave.open(str(salida), "wb") as w:
        voz.synthesize_wav(texto, w)
    return salida


def duracion_wav(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def mezclar(video: Path, voz: Path, salida: Path, volumen_original: float = 0.15) -> Path:
    """Voz encima, audio del video de fondo. Si el video no tiene audio, va solo la voz.

    El video NO se re-encodea: se copia el stream de imagen y solo se rearma el audio. En la Pi el
    render es la etapa más cara, y volver a pasarlo por x264 acá lo duplicaría al pedo.
    """
    salida.parent.mkdir(parents=True, exist_ok=True)
    tiene_audio = _tiene_audio(video)
    if tiene_audio:
        filtro = (f"[0:a]volume={volumen_original}[fondo];"
                  f"[1:a]aresample=48000[voz];"
                  f"[fondo][voz]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        mapeo = ["-map", "0:v", "-map", "[a]"]
    else:
        filtro = "[1:a]aresample=48000[a]"
        mapeo = ["-map", "0:v", "-map", "[a]"]
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video.resolve()), "-i", str(voz.resolve()),
         "-filter_complex", filtro, *mapeo,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
         str(salida.resolve())])
    return salida


def _tiene_audio(video: Path) -> bool:
    from .media import probe

    try:
        return probe(video).tiene_audio
    except Exception:
        return False


def subtitular_voz(wav: Path, cfg_subs, texto_guion: str = "") -> list:
    """Subtítulos de LA VOZ, no del audio original: se transcribe el wav sintetizado.

    Se pasa Whisper por encima de la propia voz en vez de repartir el guion a ojo por la duración.
    Suena al revés (ya sabemos qué dice), pero es lo que da los tiempos REALES de cada palabra, que
    es lo único que hace que el subtítulo caiga cuando se escucha. Repartir el texto de forma
    pareja se desfasa apenas hay una pausa.
    """
    from . import subtitles as sub

    modelo = sub.cargar_modelo(cfg_subs)
    try:
        palabras = sub.transcribir(modelo, wav, cfg_subs, duracion_wav(wav))
    finally:
        del modelo
    return sub.armar_subtitulos(palabras, cfg_subs)


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
        if audio:
            partes.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]")
            entradas += f"[a{i}]"
    partes.append(f"{entradas}concat=n={len(tramos)}:v=1:a={1 if audio else 0}"
                  + ("[v][a]" if audio else "[v]"))
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
