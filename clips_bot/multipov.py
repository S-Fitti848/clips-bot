"""Short multi-POV secuencial: el mismo momento visto por varios streamers, uno atrás del otro.

Cuando un grupo de "mismo momento entre streamers" tiene 3 o más clips, además del Short individual
se arma uno que encadena hasta 3 ángulos. De cada ángulo se toma una ventana de ±4 s alrededor del
pico de reacción (volumen + palabras de Whisper), con el nombre del streamer en un cartel arriba
durante su tramo. Orden: del menos al más visto, para que el final sea el ángulo más fuerte.
NO hay pantalla dividida: es secuencial.

Se parte de los mp4 verticales ya renderizados (output/ready/), así el layout y los subtítulos de
cada ángulo se reusan tal cual.
"""

from __future__ import annotations

import logging
import unicodedata
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Render, Subtitulos
from .media import find_bin, run
from .subtitles import _escapar_ass, _t_ass

log = logging.getLogger(__name__)

MAX_ANGULOS = 3
MIN_ANGULOS = 3  # la política (§3 7b) es armarlo cuando 3+ canales clipearon el mismo momento
SR = 8000  # audio a 8 kHz mono alcanza para medir volumen
VENTANA_RMS_S = 0.5
PESO_VOLUMEN = 0.6  # el resto lo aporta la densidad de palabras


@dataclass(frozen=True)
class Angulo:
    clip_id: str
    streamer: str
    video: Path
    vistas: int
    inicio: float = 0.0
    fin: float = 0.0

    @property
    def duracion(self) -> float:
        return max(self.fin - self.inicio, 0.0)


def envolvente_rms(video: Path, duracion: float) -> list[float]:
    """RMS por ventana de VENTANA_RMS_S, leyendo el audio crudo (sin dependencias extra)."""
    import numpy as np

    r = subprocess.run(
        [find_bin("ffmpeg"), "-v", "error", "-i", str(video), "-ac", "1", "-ar", str(SR),
         "-f", "s16le", "-"],
        capture_output=True,
    )
    if r.returncode != 0 or not r.stdout:
        return []
    muestras = np.frombuffer(r.stdout, dtype="<i2").astype("float32")
    n = int(SR * VENTANA_RMS_S)
    if len(muestras) < n:
        return []
    bloques = muestras[: len(muestras) // n * n].reshape(-1, n)
    return [float(x) for x in np.sqrt((bloques ** 2).mean(axis=1))]


def densidad_palabras(palabras: list[tuple[float, float]], n_ventanas: int) -> list[float]:
    """Cuántas palabras caen en cada ventana (palabras = [(inicio, fin), ...])."""
    cuenta = [0.0] * n_ventanas
    for inicio, _fin in palabras:
        i = int(inicio / VENTANA_RMS_S)
        if 0 <= i < n_ventanas:
            cuenta[i] += 1
    return cuenta


def palabras_de_srt(path: Path) -> list[tuple[float, float]]:
    """(inicio, fin) por palabra, a partir del .srt del clip (una entrada por palabra del bloque)."""
    import re

    if not path.exists():
        return []
    palabras: list[tuple[float, float]] = []
    tiempos = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)")
    bloques = path.read_text(encoding="utf-8").split("\n\n")
    for b in bloques:
        m = tiempos.search(b)
        if not m:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
        inicio = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        fin = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        texto = " ".join(b.split("\n")[2:])
        n = max(len(texto.split()), 1)
        paso = (fin - inicio) / n
        palabras += [(inicio + i * paso, inicio + (i + 1) * paso) for i in range(n)]
    return palabras


def preparar(metas: list[dict], ready: Path, margen_s: float = 4.0) -> list[Angulo]:
    """De cada clip ya procesado: ventana de ±margen_s alrededor de su pico de reacción."""
    angulos = []
    for meta in metas:
        video = Path(meta["salida"])
        duracion = float(meta.get("duracion_s") or 0)
        rms = envolvente_rms(video, duracion)
        palabras = palabras_de_srt(ready / f"{meta['clip_id']}.srt")
        centro = pico_reaccion(rms, palabras, duracion, margen_s)
        angulos.append(Angulo(meta["clip_id"], meta.get("canal") or meta["streamer"], video,
                              int(meta.get("vistas") or 0),
                              inicio=round(max(centro - margen_s, 0.0), 2),
                              fin=round(min(centro + margen_s, duracion), 2)))
    return angulos


@dataclass(frozen=True)
class Contenido:
    """Qué tan "vivo" está el panel de un ángulo durante su tramo."""
    vacios: float = 0.0    # fracción de frames del tramo cuyo panel es casi todo negro
    brillo: float = 0.0    # luma media 0-1 (informativo)
    detalle: float = 0.0   # desvío de la luma dentro del frame (informativo)
    frames: int = 0

    def a_dict(self) -> dict:
        return {"vacios": round(self.vacios, 3), "brillo": round(self.brillo, 3),
                "detalle": round(self.detalle, 3), "frames": self.frames}


def medir_panel(video: Path, inicio: float, fin: float, y0: int, y1: int,
                n_frames: int = 10, luma_negro: float = 0.08,
                pixeles_negros_min: float = 0.90) -> Contenido:
    """Cuánto del tramo de un ángulo es un rectángulo negro (filas y0..y1 del 9:16 renderizado).

    PattyMeza, 2026-09-23: su pantalla estaba en negro, así que el 60 % de abajo del Short era un
    rectángulo negro — y encima era el ángulo final, el que más pesa. Un panel sin nada no aporta
    ningún POV: o se muestra el 16:9 entero (fit_blur) o el ángulo no va.

    Se cuenta FRAME POR FRAME y no con el promedio del tramo: en ese caso el panel estaba 97-99 %
    negro durante los primeros 5 de los 8 s y después se iluminaba, y el promedio daba un brillo
    de 0,22 que no parecía nada raro.
    """
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        log.warning("No puedo abrir %s para medir el panel", video)
        return Contenido()
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    brillos, detalles, vacios = [], [], 0
    try:
        for i in range(n_frames):
            t = inicio + (fin - inicio) * (i / max(n_frames - 1, 1))
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, img = cap.read()
            if not ok:
                continue
            panel = cv2.cvtColor(img[y0:y1], cv2.COLOR_BGR2GRAY).astype("float32") / 255.0
            brillos.append(float(panel.mean()))
            detalles.append(float(panel.std()))
            if float((panel < luma_negro).mean()) >= pixeles_negros_min:
                vacios += 1
    finally:
        cap.release()
    if not brillos:
        return Contenido()
    return Contenido(vacios=vacios / len(brillos), brillo=sum(brillos) / len(brillos),
                     detalle=sum(detalles) / len(detalles), frames=len(brillos))


def panel_vacio(c: Contenido, frames_vacios_max: float) -> bool:
    """True si buena parte del tramo es un rectángulo negro.

    Calibrado 2026-09-23: el tramo de PattyMeza daba 56 % de frames vacíos; de los 13 clips split
    de ready/ medidos enteros, 11 dan 0 % y los dos peores 22 % y 11 % (un corte a negro puntual).
    """
    return c.frames > 0 and c.vacios > frames_vacios_max


# Palabras que aparecen en cualquier clip y no dicen nada sobre de qué se habla.
_VACIAS = frozenset("""
que de la el en y a los las un una con por para se me te lo le su es no si al del esto eso esta ese
pero como cuando donde porque bien bueno ahora vamos vamo dale nada todo algo hay muy mas menos
gente chicos amigos wey boludo che tipo cosa cosas hacer hace voy vas va ver mira mire aca alla
""".split())


def _contenido(texto: str) -> set[str]:
    """Palabras con contenido: sin tildes, de 4 letras para arriba, sin muletillas."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z]{4,}", sin_tildes.lower()) if w not in _VACIAS}


def superposicion(transcripciones: list[str]) -> float:
    """Cuánto vocabulario comparten los ángulos, de 0 a 1 (Jaccard sobre el par más parecido).

    Si tres personas cuentan el MISMO hecho, aunque sea desde ángulos distintos, nombran las mismas
    cosas. Si no lo comparten, casi seguro no están hablando de lo mismo. Se toma el mejor par y no
    el promedio para no castigar al ángulo que se queda callado.
    """
    vocab = [_contenido(t) for t in transcripciones]
    mejor = 0.0
    for i in range(len(vocab)):
        for j in range(i + 1, len(vocab)):
            union = vocab[i] | vocab[j]
            if union:
                mejor = max(mejor, len(vocab[i] & vocab[j]) / len(union))
    return mejor


SISTEMA_MISMO_HECHO = """Te paso lo que se dice en varios clips de streamers distintos, grabados a la
misma hora en el mismo evento. Decidí si están todos reaccionando AL MISMO HECHO concreto (la misma
muerte, la misma jugada, el mismo anuncio, la misma pelea) o si cada uno está en la suya.

Estar en el mismo juego, en el mismo evento o de buen humor NO alcanza: tiene que ser el mismo hecho
puntual. Ante la duda, false: un Short que junta momentos que no tienen nada que ver es peor que no
publicar nada.

Respondé solo con el JSON pedido."""

SCHEMA_MISMO_HECHO = {
    "type": "OBJECT",
    "properties": {
        "mismo_hecho": {"type": "BOOLEAN"},
        "hecho": {"type": "STRING"},
        "razon": {"type": "STRING"},
    },
    "required": ["mismo_hecho", "hecho", "razon"],
}


def pregunta_mismo_hecho(cliente, streamers: list[str], transcripciones: list[str]) -> dict:
    """La segunda mitad de la verificación: se lo preguntamos a Gemini."""
    import json as _json

    partes = [f"--- {s}\n{t[:900]}" for s, t in zip(streamers, transcripciones)]
    crudo = cliente.json(SISTEMA_MISMO_HECHO, "\n\n".join(partes), SCHEMA_MISMO_HECHO,
                         temperatura=0.1)
    try:
        d = _json.loads(crudo)
    except ValueError:
        return {"mismo_hecho": False, "hecho": "", "razon": "Gemini no devolvió JSON válido"}
    return {"mismo_hecho": bool(d.get("mismo_hecho")), "hecho": str(d.get("hecho") or ""),
            "razon": str(d.get("razon") or "")}


def es_el_mismo_hecho(cliente, streamers: list[str], transcripciones: list[str],
                      minimo: float) -> tuple[bool, dict]:
    """Las DOS tienen que pasar: superposición léxica y la pregunta a Gemini.

    Se mide primero la superposición porque es gratis: si no llega, no se gasta una llamada.
    """
    sup = superposicion(transcripciones)
    detalle = {"superposicion": round(sup, 3), "minimo": minimo}
    if sup < minimo:
        detalle["razon"] = f"comparten {sup:.0%} del vocabulario (hace falta {minimo:.0%})"
        return False, detalle
    if cliente is None:
        detalle["razon"] = "sin Gemini no se puede confirmar el hecho"
        return False, detalle
    respuesta = pregunta_mismo_hecho(cliente, streamers, transcripciones)
    detalle.update(respuesta)
    return bool(respuesta["mismo_hecho"]), detalle


def _normalizar(valores: list[float]) -> list[float]:
    if not valores:
        return []
    maximo = max(valores)
    return [v / maximo for v in valores] if maximo > 0 else [0.0] * len(valores)


def pico_reaccion(rms: list[float], palabras: list[tuple[float, float]], duracion: float,
                  margen_s: float = 4.0) -> float:
    """Centro (en segundos) de la ventana de ±margen_s con más reacción.

    Reacción = volumen + palabras. El centro se corre para que la ventana entre en el clip.
    """
    if not rms:
        return duracion / 2
    v = _normalizar(rms)
    p = _normalizar(densidad_palabras(palabras, len(rms)))
    puntaje = [PESO_VOLUMEN * a + (1 - PESO_VOLUMEN) * b for a, b in zip(v, p)]
    mejor = max(range(len(puntaje)), key=lambda i: puntaje[i])
    centro = (mejor + 0.5) * VENTANA_RMS_S
    return min(max(centro, margen_s), max(duracion - margen_s, margen_s))


def ordenar(angulos: list[Angulo], max_angulos: int = MAX_ANGULOS) -> list[Angulo]:
    """Los `max_angulos` más vistos, ordenados de menos a más visto: el final es el más fuerte."""
    mejores = sorted(angulos, key=lambda a: a.vistas, reverse=True)[:max_angulos]
    return sorted(mejores, key=lambda a: a.vistas)


def ass_carteles(angulos: list[Angulo], path: Path, cfg: Subtitulos, render: Render) -> None:
    """Cartel con el nombre del streamer arriba, durante su tramo del video final."""
    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {render.ancho}
PlayResY: {render.alto}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cartel,{cfg.fuente},{int(cfg.tamano * 0.9)},&H00FFFFFF,&H000000FF,&H60000000,&H60000000,-1,0,0,0,100,100,0,0,3,14,0,8,40,40,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos, t = [], 0.0
    for a in angulos:
        eventos.append(f"Dialogue: 0,{_t_ass(t)},{_t_ass(t + a.duracion)},Cartel,,0,0,0,,"
                       f"{_escapar_ass(a.streamer)}")
        t += a.duracion
    path.write_text(cabecera + "\n".join(eventos) + "\n", encoding="utf-8")


def filtro_concat(angulos: list[Angulo], render: Render, con_carteles: bool) -> str:
    """Corta cada ángulo en su ventana y los pega uno atrás del otro (video y audio)."""
    partes = []
    for i, a in enumerate(angulos):
        partes.append(
            f"[{i}:v]trim={a.inicio:.2f}:{a.fin:.2f},setpts=PTS-STARTPTS,"
            f"scale={render.ancho}:{render.alto}:flags=lanczos,setsar=1,fps={render.fps}[v{i}];"
            f"[{i}:a]atrim={a.inicio:.2f}:{a.fin:.2f},asetpts=PTS-STARTPTS[a{i}];"
        )
    entradas = "".join(f"[v{i}][a{i}]" for i in range(len(angulos)))
    salida = "[vcat][aout]" if not con_carteles else "[vcat][aout];[vcat]ass=carteles.ass[vout]"
    return "".join(partes) + f"{entradas}concat=n={len(angulos)}:v=1:a=1{salida}"


def armar(angulos: list[Angulo], salida: Path, work: Path, render: Render, cfg_subs: Subtitulos) -> Path:
    """Genera el mp4 multi-POV. `angulos` ya viene ordenado y con sus ventanas."""
    if len(angulos) < 2:
        raise ValueError("un multi-POV necesita al menos 2 ángulos")
    work.mkdir(parents=True, exist_ok=True)
    ass_carteles(angulos, work / "carteles.ass", cfg_subs, render)
    salida.parent.mkdir(parents=True, exist_ok=True)

    args = [find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    for a in angulos:
        args += ["-i", str(a.video.resolve())]
    args += [
        "-filter_complex", filtro_concat(angulos, render, con_carteles=True),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", render.x264_preset, "-crf", str(render.crf), "-pix_fmt", "yuv420p",
        "-maxrate", f"{render.maxrate_kbps}k", "-bufsize", f"{2 * render.maxrate_kbps}k",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
        str(salida.resolve()),
    ]
    run(args, cwd=work)  # cwd=work: el filtro ass usa el nombre relativo, sin pelear con las rutas
    return salida


def credito_multiple(streamers: list[tuple[str, str]]) -> str:
    """streamers = [(nombre visible, url del canal)] → una línea de crédito por ángulo."""
    return "Clips de:\n" + "\n".join(f"· {nombre} — {url}" for nombre, url in streamers)
