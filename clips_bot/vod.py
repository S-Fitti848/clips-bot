"""¿El Short que pegó salió del VOD y no de un clip? (pedido 2026-09-30, APAGADO: `pego.vod`)

Los canales de clips muchas veces cortan del VOD, no de un clip: por eso "pegó" no encuentra el
original entre los clips. Para los 2 Shorts sin original con más vistas del día, se busca su
audio dentro de los VODs del streamer de los días anteriores a que se publicara.

Cómo, sin bajar video: el VOD de Kick es un HLS de Amazon IVS con variantes 1080p…160p (sin
variante de solo audio: da 403); se lee la de 160p (230 kbps) con ffmpeg y se saca SOLO el audio a
8 kHz mono. Medido 2026-09-30: un VOD de Davo dura 7-9 h, ~725 MB de 160p. La huella del VOD se
guarda (float16) y la búsqueda del Short en todas las posiciones va por FFT
(`audio_huella.coincidencia_rapida`: 7 h en ~1 s en Windows).

Si coincide, el momento queda anotado con el link del VOD y el segundo exacto: el clip no existe,
así que no se procesa solo; se avisa en el resumen de "🔥 Pegó en otros canales" para cortarlo a mano.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import audio_huella as ah
from .media import find_bin

log = logging.getLogger(__name__)

API_VIDEOS = "https://kick.com/api/v2/channels/{slug}/videos"
VARIANTE = "160p30"
BLOQUE_S = 600       # la huella del VOD se arma de a 10 min (7 h de audio crudo son 400 MB)


@dataclass
class Vod:
    id: str
    plataforma: str
    url: str             # lo que lee ffmpeg (la playlist de la variante chica)
    pagina: str          # para mirarlo a mano
    inicio: datetime
    duracion_s: float
    titulo: str = ""


def vods_kick(kick, slug: str, desde: datetime, hasta: datetime) -> list[Vod]:
    out = []
    for v in kick._get(API_VIDEOS.format(slug=slug)) or []:
        try:
            inicio = datetime.strptime(v["start_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        dur = float(v.get("duration") or 0) / 1000
        if not v.get("source") or inicio > hasta or inicio + timedelta(seconds=dur) < desde:
            continue
        base = str(v["source"]).rsplit("/", 1)[0]
        uuid = (v.get("video") or {}).get("uuid") or v.get("id")
        out.append(Vod(str(v.get("id")), "kick", f"{base}/{VARIANTE}/playlist.m3u8",
                       f"https://kick.com/{slug}/videos/{uuid}", inicio, dur,
                       str(v.get("session_title") or "")))
    return sorted(out, key=lambda x: x.inicio, reverse=True)


def huella_vod(v: Vod, cache: Path, reloj=time.monotonic, hasta: float | None = None) -> np.ndarray:
    """La huella del audio del VOD (se guarda: el mismo VOD sirve para varios Shorts y días).
    ffmpeg saca solo el audio; se procesa de a BLOQUE_S para no tener horas de audio en memoria."""
    cache.mkdir(parents=True, exist_ok=True)
    archivo = cache / f"vod_{v.plataforma}_{v.id}.npy"
    if archivo.exists():
        return np.load(archivo).astype(np.float32)
    p = subprocess.Popen([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error",
                          "-rw_timeout", "30000000", "-i", v.url, "-vn", "-ac", "1", "-ar", str(ah.SR),
                          "-f", "s16le", "-"], stdout=subprocess.PIPE)
    por_bloque = BLOQUE_S * ah.SR
    partes, resto = [], np.zeros(0, dtype=np.float32)
    try:
        while True:
            if hasta is not None and reloj() >= hasta:
                raise TimeoutError("se terminó el tiempo bajando el audio del VOD")
            datos = p.stdout.read(por_bloque * 2)
            if not datos:
                break
            audio = np.concatenate([resto, np.frombuffer(datos, dtype=np.int16).astype(np.float32) / 32768])
            n = (len(audio) - ah.VENTANA) // ah.SALTO + 1
            if n <= 0:
                resto = audio
                continue
            partes.append(ah.huella(audio[:(n - 1) * ah.SALTO + ah.VENTANA]))
            resto = audio[n * ah.SALTO:]
    finally:
        p.kill()
        p.wait()
    h = np.concatenate(partes) if partes else np.zeros((0, ah.BANDAS), dtype=np.float32)
    np.save(archivo, h.astype(np.float16))
    return h


def buscar_en_vods(short_audio: Path, vods: list[Vod], cache: Path, umbral: float,
                   avisar=log.info, hasta: float | None = None, reloj=time.monotonic):
    """(vod, segundo, coincidencia) del mejor lugar que pase el umbral, o None."""
    corto = ah.huella(ah.leer_audio(short_audio))
    mejor = None
    for v in vods:
        t0 = reloj()
        h = huella_vod(v, cache, reloj, hasta)
        valor, seg = ah.coincidencia_rapida(corto, h)
        avisar(f"    VOD {v.id} ({v.duracion_s / 3600:.1f} h, «{v.titulo[:40]}»): {valor:.2f} en "
               f"{seg / 60:.1f} min ({reloj() - t0:.0f} s)")
        if valor >= umbral and (mejor is None or valor > mejor[2]):
            mejor = (v, seg, valor)
    return mejor
