"""Audio: la envolvente de la voz (para mover la boca), una voz de prueba sin TTS y Piper si está.

La boca se mueve por AMPLITUD, no por fonemas: es lo que se ve bien en un dibujo plano y no
necesita ningún modelo. La vocal (a/e/o) se elige por el nivel y un patrón fijo, así no se ve
siempre la misma forma."""
from __future__ import annotations

import os
import wave
from pathlib import Path

import numpy as np


def leer_wav(ruta: Path) -> tuple[np.ndarray, int]:
    """Mono float32 en [-1, 1] y la frecuencia de muestreo."""
    with wave.open(str(ruta)) as w:
        sr, canales, ancho = w.getframerate(), w.getnchannels(), w.getsampwidth()
        datos = w.readframes(w.getnframes())
    if ancho != 2:
        raise ValueError(f"Solo wav de 16 bits (este tiene {ancho * 8})")
    x = np.frombuffer(datos, dtype="<i2").astype(np.float32) / 32768.0
    if canales > 1:
        x = x.reshape(-1, canales).mean(axis=1)
    return x, sr


def duracion_wav(ruta: Path) -> float:
    with wave.open(str(ruta)) as w:
        return w.getnframes() / float(w.getframerate())


def envolvente(ruta: Path, fps: int) -> list[float]:
    """Un valor 0..1 por cuadro: RMS de la ventana del cuadro, normalizado al percentil 95,
    con compuerta de ruido y suavizado (abre rápido, cierra un poco más lento: así la boca no
    tiembla entre sílabas)."""
    x, sr = leer_wav(ruta)
    por_cuadro = sr / fps
    n = int(np.ceil(len(x) / por_cuadro))
    rms = np.zeros(n, dtype=np.float32)
    for i in range(n):
        a, b = int(i * por_cuadro), int((i + 1) * por_cuadro)
        seg = x[a:b]
        rms[i] = float(np.sqrt(np.mean(seg * seg))) if len(seg) else 0.0
    ref = float(np.percentile(rms[rms > 0], 95)) if np.any(rms > 0) else 1.0
    nivel = np.clip(rms / max(ref, 1e-6), 0, 1)
    nivel[nivel < 0.12] = 0.0           # compuerta: respiraciones y ruido no abren la boca
    out, prev = [], 0.0
    for v in nivel:
        prev = v if v > prev else prev * 0.55 + v * 0.45
        out.append(round(float(prev), 3))
    return out


def vocal(cuadro: int, apertura: float) -> str:
    """Forma de boca para un nivel: alto = a, medio = e/o alternando cada ~4 cuadros."""
    if apertura < 0.08:
        return "cerrada"
    if apertura > 0.62:
        return "a"
    return "e" if (cuadro // 4) % 3 != 1 else "o"


def voz_de_prueba(salida: Path, frases: list[tuple[float, float]], duracion: float,
                  sr: int = 48000) -> Path:
    """Un "bla bla" sintético (tono con sílabas a ~5 Hz) en los tramos (inicio, fin) dados y
    silencio en el resto. Para probar la boca y el audio sin TTS."""
    t = np.arange(int(duracion * sr), dtype=np.float32) / sr
    y = np.zeros_like(t)
    rng = np.random.default_rng(7)
    for ini, fin in frases:
        m = (t >= ini) & (t < fin)
        tt = t[m] - ini
        f0 = 150 + 25 * np.sin(2 * np.pi * 0.7 * tt)
        fase = 2 * np.pi * np.cumsum(f0) / sr
        voz = 0.6 * np.sin(fase) + 0.25 * np.sin(2 * fase) + 0.1 * np.sin(3 * fase)
        silabas = np.clip(np.sin(2 * np.pi * (4.5 + rng.uniform(-0.5, 0.5)) * tt), 0, 1) ** 0.6
        borde = np.clip(np.minimum(tt, (fin - ini) - tt) / 0.05, 0, 1)
        y[m] = 0.35 * voz * silabas * borde
    return _escribir(salida, y, sr)


def _escribir(salida: Path, y: np.ndarray, sr: int) -> Path:
    salida.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return salida


# ---- Piper (opcional) -----------------------------------------------------------

def modelo_piper() -> Path | None:
    """ANIM_VOZ, o la voz de Pequeña Historia del bot (~/clips/voces). None si no hay Piper."""
    try:
        import piper  # noqa: F401
    except Exception:
        return None
    candidatos = [os.getenv("ANIM_VOZ", ""),
                  str(Path.home() / "clips/voces/es_AR-daniela-high.onnx"),
                  str(Path.home() / "clips/voces/es_MX-claude-high.onnx")]
    for c in candidatos:
        if c and Path(c).is_file():
            return Path(c)
    return None


def piper_frases(frases: list[str], modelo: Path, salida: Path, pausa_s: float = 0.35,
                 inicio_s: float = 0.0) -> tuple[Path, list[tuple[float, float]]]:
    """Piper frase por frase (como `narrar.sintetizar_frases`, sin tocar ese módulo): un wav y
    el (inicio, fin) de cada frase, para que los subtítulos caigan donde se dicen."""
    from piper import PiperVoice

    voz = PiperVoice.load(str(modelo))
    sr = None
    partes = [np.zeros(0, dtype=np.float32)]
    tiempos, t = [], inicio_s
    for frase in frases:
        trozos = []
        for chunk in voz.synthesize(frase):
            sr = sr or chunk.sample_rate
            trozos.append(chunk.audio_float_array.astype(np.float32))
        a = np.concatenate(trozos) if trozos else np.zeros(0, dtype=np.float32)
        tiempos.append((t, t + len(a) / sr))
        partes.append(a)
        partes.append(np.zeros(int(sr * pausa_s), dtype=np.float32))
        t += len(a) / sr + pausa_s
    partes[0] = np.zeros(int((sr or 22050) * inicio_s), dtype=np.float32)
    return _escribir(salida, np.concatenate(partes), sr or 22050), tiempos
