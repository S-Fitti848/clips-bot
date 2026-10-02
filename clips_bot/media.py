"""Helpers de ffmpeg/ffprobe: localizar binarios, leer metadata y medir silencio."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class MediaError(RuntimeError):
    pass


def find_bin(nombre: str) -> str:
    """Busca ffmpeg/ffprobe: variable FFMPEG_DIR → PATH → instalación de winget (Gyan.FFmpeg).

    El último caso cubre la consola que se abrió antes de instalar ffmpeg y todavía no ve el PATH nuevo.
    """
    exe = nombre + (".exe" if os.name == "nt" else "")
    if d := os.getenv("FFMPEG_DIR"):
        p = Path(d) / exe
        if p.exists():
            return str(p)
    if p := shutil.which(nombre):
        return p
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        for p in sorted(base.glob(f"Gyan.FFmpeg*/*/bin/{exe}"), reverse=True):
            return str(p)
    raise MediaError(f"No encuentro {nombre}. Instalalo o definí FFMPEG_DIR con la carpeta de los binarios.")


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise MediaError(f"{Path(args[0]).name} falló ({r.returncode}):\n{r.stderr[-1500:]}")
    return r


@dataclass(frozen=True)
class Info:
    ancho: int
    alto: int
    duracion: float
    fps: float
    tiene_audio: bool


def probe(path: Path) -> Info:
    r = run([find_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    d = json.loads(r.stdout)
    video = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise MediaError(f"{path} no tiene video")
    num, _, den = video.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0
    return Info(
        ancho=int(video["width"]),
        alto=int(video["height"]),
        duracion=float(d["format"].get("duration") or video.get("duration") or 0),
        fps=fps,
        tiene_audio=any(s["codec_type"] == "audio" for s in d["streams"]),
    )


def miniatura(video: Path, destino: Path, segundo: float = 1.0) -> Path:
    """JPEG de 180x320 (Telegram pide ≤ 320 px de lado y ≤ 200 kB) con la proporción del video."""
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(segundo), "-i", str(video),
         "-frames:v", "1", "-vf", "scale=-2:320", "-q:v", "5", str(destino)])
    return destino


_SIL_START = re.compile(r"silence_start: (-?[\d.]+)")
_SIL_END = re.compile(r"silence_end: ([\d.]+)")


def parse_silencio(stderr: str, duracion: float) -> float:
    """Segundos totales de silencio a partir de la salida de silencedetect."""
    total = 0.0
    inicio: float | None = None
    for linea in stderr.splitlines():
        if m := _SIL_START.search(linea):
            inicio = max(float(m.group(1)), 0.0)
        elif (m := _SIL_END.search(linea)) and inicio is not None:
            total += float(m.group(1)) - inicio
            inicio = None
    if inicio is not None:  # silencio hasta el final del archivo
        total += max(duracion - inicio, 0.0)
    return total


def fraccion_silencio(path: Path, duracion: float, umbral_db: float, min_s: float) -> float:
    if duracion <= 0:
        return 1.0
    r = run(
        [
            find_bin("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-vn",
            "-af", f"silencedetect=noise={umbral_db}dB:d={min_s}", "-f", "null", "-",
        ]
    )
    return min(parse_silencio(r.stderr, duracion) / duracion, 1.0)


def frames_jpeg(video: Path, n: int = 3, ancho: int = 384, calidad: int = 80) -> list[bytes]:
    """`n` frames repartidos entre el 10 % y el 90 % del clip, como JPEG chicos.

    Van a Gemini junto con la transcripción. A 512 px de ancho cada uno entra en un par de tiles de
    tokens; más grande no cambia el puntaje y cuesta el doble.
    """
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        log.warning("No puedo abrir %s para sacar frames", video)
        return []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out: list[bytes] = []
    try:
        for i in range(n):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (0.1 + 0.8 * i / max(n - 1, 1))))
            ok, img = cap.read()
            if not ok:
                continue
            alto = max(2, int(img.shape[0] * ancho / img.shape[1]))
            ok, buf = cv2.imencode(".jpg", cv2.resize(img, (ancho, alto)),
                                   [cv2.IMWRITE_JPEG_QUALITY, calidad])
            if ok:
                out.append(buf.tobytes())
    finally:
        cap.release()
    return out


# ---- audio limpio: regla fija para TODOS los videos (decisión 2026-09-28) ----------------------
# Efemérides, /narrar, /serie, /editar, los clips y el multi-POV terminan el audio por acá:
#   - fade in de FADE_IN_S y fade out de FADE_OUT_S en la mezcla final;
#   - el audio dura EXACTAMENTE lo que el video (apad + atrim), nunca cortado de golpe por -shortest;
#   - donde se pegan tramos de audio, crossfade corto (CROSSFADE_S) centrado en el corte;
#   - después del render, `chequear_audio` avisa si hay un pico por encima de PICO_MAX_DB en el
#     último segundo, o si el audio no termina con el video.

FADE_IN_S = 0.1
FADE_OUT_S = 0.5
CROSSFADE_S = 0.04
PICO_MAX_DB = -3.0
DESFASE_MAX_S = 0.05     # audio y video tienen que terminar juntos (1,5 frames a 30 fps)


def cola_audio(duracion: float) -> str:
    """Lo que va al final de la cadena de audio de CUALQUIER video: largo exacto y fundidos."""
    d = max(float(duracion), FADE_OUT_S + FADE_IN_S)
    return (f"apad,atrim=0:{d:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={FADE_IN_S},afade=t=out:st={d - FADE_OUT_S:.3f}:d={FADE_OUT_S}")


def audio_con_crossfade(tramos: list[tuple[str, float, float, float]], salida: str,
                        d: float = CROSSFADE_S) -> str:
    """Pega tramos de audio con un crossfade corto en cada unión, SIN correr la sincronía.

    `tramos`: (entrada, inicio, fin, largo de la fuente), ej. ("[0:a]", 3.0, 8.5, 60.0). Cada tramo
    se toma d/2 más largo de cada lado que toca otro tramo (sacado de la misma fuente), y acrossfade
    se come exactamente eso: el total queda igual a la suma de los tramos y cada unión cae en su
    corte, así que el video (que se pega con cortes secos) no se desfasa."""
    partes, etiquetas = [], []
    n = len(tramos)
    for i, (ent, a, b, largo) in enumerate(tramos):
        ini = max(0.0, a - d / 2) if i > 0 else a
        fin = min(largo, b + d / 2) if i < n - 1 else b
        partes.append(f"{ent}atrim={ini:.3f}:{fin:.3f},asetpts=PTS-STARTPTS[t{i}]")
        etiquetas.append(f"[t{i}]")
    actual = etiquetas[0]
    for i in range(1, n):
        siguiente = salida if i == n - 1 else f"[x{i}]"
        partes.append(f"{actual}{etiquetas[i]}acrossfade=d={d}:c1=tri:c2=tri{siguiente}")
        actual = siguiente
    if n == 1:
        partes[-1] = partes[-1].replace("[t0]", salida)
    return ";".join(partes)


def preparar_audio(entrada: Path, duracion: float, salida: Path) -> Path:
    """El audio final ya terminado (cola incluida) en un WAV de `duracion` exacta, en un paso
    aparte. Hace falta cuando el video entra por el demuxer concat: con esa entrada, ffmpeg 7.1
    cortó el audio del mismo filtro a 26,7 s en un video de 35,4 s (efeméride de Fleming,
    2026-09-28); el mismo filtro con cualquier otra entrada daba exacto."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(Path(entrada).resolve()),
         "-af", f"aresample=48000,{cola_audio(duracion)}", "-c:a", "pcm_s16le",
         str(salida.resolve())])
    return salida


_MAX_VOL = re.compile(r"max_volume:\s*(-?[\d.]+|-inf) dB")


def duraciones_streams(video: Path) -> tuple[float, float | None]:
    """(duración del video, duración del audio o None si no tiene)."""
    r = run([find_bin("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", str(video)])
    dur = {"video": 0.0, "audio": None}
    for s in json.loads(r.stdout)["streams"]:
        if s["codec_type"] in dur and s.get("duration"):
            dur[s["codec_type"]] = float(s["duration"])
    return dur["video"], dur["audio"]


def pico_final_db(video: Path, segundos: float = 1.0) -> float | None:
    """El pico (dBFS) del último segundo de audio, o None si no hay audio."""
    r = run([find_bin("ffmpeg"), "-hide_banner", "-sseof", f"-{segundos}", "-i", str(video),
             "-vn", "-af", "volumedetect", "-f", "null", "-"])
    m = _MAX_VOL.search(r.stderr)
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


def avisos_audio(pico_db: float | None, dur_video: float, dur_audio: float | None) -> list[str]:
    """Lo que está mal en el final del audio, en castellano (vacío = está bien)."""
    avisos = []
    if dur_audio is not None and abs(dur_audio - dur_video) > DESFASE_MAX_S:
        avisos.append(f"el audio dura {dur_audio:.2f} s y el video {dur_video:.2f} s: no terminan juntos")
    if pico_db is not None and pico_db > PICO_MAX_DB:
        avisos.append(f"pico de {pico_db:.1f} dB en el último segundo (tope {PICO_MAX_DB:.0f} dB)")
    return avisos


def chequear_audio(video: Path) -> list[str]:
    """El chequeo de después del render. Nunca tira: si no puede medir, no avisa nada."""
    try:
        dur_v, dur_a = duraciones_streams(video)
        if dur_a is None:
            return []
        avisos = avisos_audio(pico_final_db(video), dur_v, dur_a)
    except (MediaError, OSError, ValueError, KeyError) as e:
        log.warning("no pude chequear el audio de %s: %s", video, e)
        return []
    for a in avisos:
        log.warning("audio de %s: %s", Path(video).name, a)
    return avisos
