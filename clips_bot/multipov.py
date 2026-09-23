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
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Render, Subtitulos
from .media import find_bin, run
from .subtitles import _escapar_ass, _t_ass

log = logging.getLogger(__name__)

MAX_ANGULOS = 3
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
