"""¿Es el mismo momento? Compara el audio de un Short de otro canal con el de un clip original.

Sin librerías de huellas (chromaprint no está en la Pi): el audio a 8 kHz mono, un espectro cada
32 ms reducido a 16 bandas en escala logarítmica, y se busca el desfase en el que las dos series
se parecen más (correlación de Pearson sobre la parte que se superpone). Un Short de otro canal
suele ser un pedazo del clip, con subtítulos, a veces con música encima y recomprimido: las
bandas de la voz siguen ahí. No aguanta cambios de velocidad (un Short acelerado no matchea).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .media import MediaError, find_bin

SR = 8000
VENTANA = 512      # 64 ms
SALTO = 256        # 32 ms entre frames
BANDAS = 16
SUPERPOSICION_MIN_S = 5.0


def leer_audio(ruta: Path, max_s: float = 180.0) -> np.ndarray:
    """El audio como float32 mono a 8 kHz (los primeros `max_s`)."""
    r = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", str(ruta),
                        "-t", str(max_s), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise MediaError(f"ffmpeg no pudo leer el audio de {ruta}: {r.stderr[-300:]!r}")
    return np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def huella(audio: np.ndarray) -> np.ndarray:
    """Matriz frames × BANDAS: log-energía por banda, sin la media de cada banda."""
    if len(audio) < VENTANA * 4:
        return np.zeros((0, BANDAS), dtype=np.float32)
    n = 1 + (len(audio) - VENTANA) // SALTO
    idx = np.arange(VENTANA)[None, :] + SALTO * np.arange(n)[:, None]
    espectro = np.abs(np.fft.rfft(audio[idx] * np.hanning(VENTANA), axis=1)) ** 2
    frec = np.fft.rfftfreq(VENTANA, 1 / SR)
    bordes = np.geomspace(100, 3800, BANDAS + 1)
    bandas = np.stack([espectro[:, (frec >= a) & (frec < b)].sum(axis=1)
                       for a, b in zip(bordes[:-1], bordes[1:])], axis=1)
    h = np.log(bandas + 1e-9)
    return (h - h.mean(axis=0)).astype(np.float32)


def coincidencia(a: np.ndarray, b: np.ndarray, paso: int = 2) -> tuple[float, float]:
    """(correlación máxima, desfase en segundos de `a` dentro de `b`). Se desliza la más corta
    sobre la más larga; cuenta solo si se superponen al menos SUPERPOSICION_MIN_S."""
    if len(a) == 0 or len(b) == 0:
        return 0.0, 0.0
    corta, larga, invertido = (a, b, False) if len(a) <= len(b) else (b, a, True)
    minimo = int(SUPERPOSICION_MIN_S * SR / SALTO)
    if len(corta) < minimo:
        return 0.0, 0.0
    mejor, donde = -1.0, 0
    for lag in range(0, len(larga) - len(corta) + 1, paso):
        x = corta.ravel()
        y = larga[lag:lag + len(corta)].ravel()
        x0, y0 = x - x.mean(), y - y.mean()
        den = float(np.sqrt((x0 * x0).sum() * (y0 * y0).sum()))
        c = float((x0 * y0).sum() / den) if den else 0.0
        if c > mejor:
            mejor, donde = c, lag
    desfase = donde * SALTO / SR
    return round(mejor, 3), round(-desfase if invertido else desfase, 2)


def comparar(short: Path, clip: Path) -> tuple[float, float]:
    return coincidencia(huella(leer_audio(short)), huella(leer_audio(clip)))


def coincidencia_rapida(corta: np.ndarray, larga: np.ndarray) -> tuple[float, float]:
    """Lo mismo que `coincidencia` (Pearson sobre la parte que se superpone, desfase de `corta`
    dentro de `larga`), pero en TODOS los desfases a la vez con FFT: para buscar un Short de 30 s
    dentro de un VOD de 7 horas (~790.000 cuadros), donde el recorrido de a uno tarda demasiado."""
    n, bandas = corta.shape
    if n == 0 or len(larga) < n or n < int(SUPERPOSICION_MIN_S * SR / SALTO):
        return 0.0, 0.0
    a = corta.astype(np.float64)
    a0 = a - a.mean()
    saa = float((a0 * a0).sum())
    if saa == 0:
        return 0.0, 0.0
    b = larga.astype(np.float64)
    L = len(b)
    tam = 1 << int(np.ceil(np.log2(L + n)))
    # sum(a0 * ventana de b) para cada desfase, sumado por banda.
    prod = np.zeros(L - n + 1)
    for k in range(bandas):
        fa = np.fft.rfft(a0[::-1, k], tam)
        fb = np.fft.rfft(b[:, k], tam)
        prod += np.fft.irfft(fa * fb, tam)[n - 1:L]
    # sum y sum² de cada ventana de b (todas las bandas juntas), con sumas acumuladas.
    fila, fila2 = b.sum(axis=1), (b * b).sum(axis=1)
    c1 = np.concatenate([[0.0], np.cumsum(fila)])
    c2 = np.concatenate([[0.0], np.cumsum(fila2)])
    s1 = c1[n:] - c1[:-n]
    s2 = c2[n:] - c2[:-n]
    sbb = s2 - s1 * s1 / (n * bandas)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(sbb > 1e-9, prod / np.sqrt(saa * sbb), 0.0)
    lag = int(np.argmax(corr))
    return round(float(corr[lag]), 3), round(lag * SALTO / SR, 2)
