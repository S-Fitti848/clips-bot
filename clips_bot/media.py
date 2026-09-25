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


def frames_jpeg(video: Path, n: int = 4, ancho: int = 512, calidad: int = 80) -> list[bytes]:
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
