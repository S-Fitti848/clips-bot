"""Efectos de sonido de Así Nació.

BIBLIOTECA (Santi, 2026-11-15): los efectos se generan UNA vez con ElevenLabs (licencia comercial del plan
pago), se guardan como wav de 48 kHz y se reusan en todos los videos; uno nuevo se genera solo cuando no está
en la biblioteca. `assets/sfx/` (en git, generados una vez en la compu) y `data/animacion/sfx/` (los que se
generan después en la Pi), con sus descripciones en `biblioteca.json`. Si un nombre no tiene archivo ni se
puede generar (sin clave, sin créditos, en los tests), va el SINTETIZADO de siempre (numpy, determinista) o,
si no hay, nada. `mezclar` los suma a la mezcla de voz + música en el segundo exacto de cada acción, con un
limitador suave para que nada clipee."""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SR = 48000
_RAIZ = Path(__file__).resolve().parent.parent.parent
BIBLIOTECA = _RAIZ / "assets" / "sfx"                     # en git: los que ya se generaron
NUEVOS = _RAIZ / "data" / "animacion" / "sfx"             # generados en la Pi después (fuera de git)

# nombre → (descripción para ElevenLabs, duración en s, influencia del texto). Cortos y secos donde marcan
# un golpe (el sonido tiene que caer en el cuadro de la acción); el del viaje, la marca del canal.
CATALOGO = {
    "viaje": ("Powerful cinematic time-travel whoosh: a huge swirling rewind sweep with fast backwards "
              "clock ticking, rising pitch and a deep sub boom at the end, cartoon style", 1.4, 0.6),
    "whoosh": ("Fast cartoon swoosh of an object flying past the camera", 0.6, 0.6),
    "golpe": ("Comedic cartoon bonk, a solid punchy hit on an object, short and dry", 0.5, 0.6),
    "vidrio": ("Short cartoon glass crash, a vase shattering, no reverb tail", 0.8, 0.6),
    "boing": ("Cartoon spring boing, bouncy and funny", 0.6, 0.6),
    "pop": ("Tiny bubbly cartoon pop, short UI-like", 0.5, 0.7),
    "tac": ("Single short wooden tick click", 0.5, 0.7),
    "ding": ("Bright magical sparkle ding chime, cheerful", 1.0, 0.6),
    "aplausos": ("Enthusiastic small crowd applause with a few cheers and whistles", 2.5, 0.5),
    "caja_registradora": ("Old mechanical cash register ka-ching with drawer opening and bell", 1.2, 0.6),
    "explosion": ("Cartoon comic explosion, a funny poof with debris, not scary", 1.2, 0.5),
    "cohete": ("Cartoon rocket launch: ignition whoosh and rumble taking off upwards", 2.0, 0.5),
    "maquina": ("Retro factory machine clanking and whirring in a steady rhythm, cartoon", 2.0, 0.5),
    "asombro": ("Small crowd going 'ooooh' in amazement", 1.5, 0.5),
}


def _ruta(nombre: str) -> Path | None:
    for carpeta in (BIBLIOTECA, NUEVOS):
        p = carpeta / f"{nombre}.wav"
        if p.exists():
            return p
    return None


def _a_wav(mp3: bytes, salida: Path) -> None:
    """mp3 → wav mono 48 kHz, sin el silencio del principio (el golpe tiene que caer en su cuadro), con el
    pico normalizado."""
    from ..media import find_bin

    with tempfile.TemporaryDirectory() as tmp:
        ent = Path(tmp) / "e.mp3"
        ent.write_bytes(mp3)
        sal = Path(tmp) / "s.wav"
        subprocess.run([find_bin("ffmpeg"), "-v", "error", "-y", "-i", str(ent), "-ac", "1", "-ar", str(SR),
                        "-af", "silenceremove=start_periods=1:start_threshold=-45dB", "-c:a", "pcm_s16le",
                        str(sal)], check=True, capture_output=True, timeout=60)
        x, _ = _leer(sal)
    pico = float(np.max(np.abs(x))) if len(x) else 0.0
    if pico < 1e-4:
        raise ValueError("efecto en silencio")
    x = x / pico * 0.98
    n_fin = min(len(x), int(0.02 * SR))               # sin clic al final
    x[len(x) - n_fin:] *= np.linspace(1, 0, n_fin)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def generar(nombre: str, carpeta: Path | None = None, forzar: bool = False) -> Path | None:
    """El efecto `nombre` del CATALOGO en la biblioteca: si ya está, no hace nada (no se paga dos veces); si
    no, lo genera con ElevenLabs y lo guarda. None si no se pudo (y queda el sintetizado)."""
    from .. import elevenlabs

    ya = _ruta(nombre)
    if ya and not forzar:
        return ya
    if nombre not in CATALOGO or not elevenlabs.clave():
        return None
    texto, dur, influencia = CATALOGO[nombre]
    carpeta = carpeta or NUEVOS
    try:
        mp3 = elevenlabs.efecto(texto, dur, influencia, nombre=nombre)
        salida = carpeta / f"{nombre}.wav"
        _a_wav(mp3, salida)
    except Exception as e:     # noqa: BLE001 — un efecto que no sale no frena el video
        log.warning("efecto %s: no pude generarlo con ElevenLabs (%s): va el sintetizado", nombre, str(e)[:150])
        return None
    indice = carpeta / "biblioteca.json"
    try:
        datos = json.loads(indice.read_text(encoding="utf-8")) if indice.exists() else {}
    except ValueError:
        datos = {}
    datos[nombre] = {"descripcion": texto, "duracion": dur, "influencia": influencia, "motor": "elevenlabs",
                     "modelo": elevenlabs.MODELO_EFECTOS,
                     "fecha": datetime.now(timezone.utc).date().isoformat()}
    indice.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("efecto %s generado con ElevenLabs y guardado en la biblioteca", nombre)
    return salida


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR), dtype=np.float32) / SR


def _ruido(n: int, semilla: int) -> np.ndarray:
    return np.random.default_rng(semilla).standard_normal(n).astype(np.float32)


def _paso_bajo(x: np.ndarray, a: float) -> np.ndarray:
    """Filtro de un polo (a cerca de 1 = más grave)."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc = a * acc + (1 - a) * v
        y[i] = acc
    return y


def golpe() -> np.ndarray:
    t = _t(0.35)
    f = 110 * np.exp(-t * 9) + 45
    cuerpo = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 11)
    chasquido = _paso_bajo(_ruido(len(t), 1), 0.7) * np.exp(-t * 40)
    return 0.9 * cuerpo + 0.5 * chasquido


def vidrio() -> np.ndarray:
    t = _t(0.9)
    ruido = _ruido(len(t), 2)
    agudo = ruido - _paso_bajo(ruido, 0.6)            # paso alto: el "crash"
    out = agudo * np.exp(-t * 7) * 0.7
    rng = np.random.default_rng(3)
    for k in range(9):                                  # tintineos de los pedazos
        t0 = rng.uniform(0.03, 0.6)
        f = rng.uniform(2500, 6000)
        m = t >= t0
        tt = t[m] - t0
        out[m] += 0.18 * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 25)
    return out


def whoosh() -> np.ndarray:
    t = _t(0.45)
    ruido = _ruido(len(t), 4)
    # barrido: el filtro se abre y se cierra (paso bajo variable a mano, por tramos)
    out = np.zeros_like(ruido)
    acc = 0.0
    for i, v in enumerate(ruido):
        u = i / len(ruido)
        a = 0.97 - 0.5 * np.sin(np.pi * u)
        acc = a * acc + (1 - a) * v
        out[i] = acc
    return out * np.sin(np.pi * t / 0.45) ** 2 * 1.4


def boing() -> np.ndarray:
    t = _t(0.5)
    f = 180 + 120 * np.sin(2 * np.pi * 9 * t) * np.exp(-t * 5) + 140 * t
    return 0.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6)


def pop() -> np.ndarray:
    t = _t(0.12)
    f = 900 * np.exp(-t * 30) + 300
    return 0.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 35)


def tac() -> np.ndarray:
    t = _t(0.1)
    return 0.6 * (_paso_bajo(_ruido(len(t), 5), 0.4) + 0.5 * np.sin(2 * np.pi * 1200 * t)) * np.exp(-t * 60)


def ding() -> np.ndarray:
    t = _t(0.8)
    return 0.4 * (np.sin(2 * np.pi * 1320 * t) + 0.4 * np.sin(2 * np.pi * 2640 * t)) * np.exp(-t * 5)


def viaje() -> np.ndarray:
    """El viaje en el tiempo: un barrido que sube (de 200 a 1600 Hz) con trémolo, tic-tacs rápidos
    y un whoosh abajo."""
    t = _t(1.2)
    f = 200 * (8 ** (t / 1.2))
    tono = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.6 + 0.4 * np.sin(2 * np.pi * 18 * t))
    env = np.minimum(1.0, t / 0.15) * np.minimum(1.0, (1.2 - t) / 0.3)
    out = 0.45 * tono * env
    for k in range(10):                          # tic-tac acelerando
        t0 = 1.0 * (1 - (1 - k / 10) ** 1.6)
        m = (t >= t0) & (t < t0 + 0.03)
        out[m] += 0.5 * np.sin(2 * np.pi * 2200 * (t[m] - t0)) * np.exp(-(t[m] - t0) * 120)
    # el whoosh FUERTE (Santi, 2026-11-15): un barrido de ruido de todo el viaje que sube y se corta, con
    # un rugido grave abajo
    ruido = _ruido(len(t), 11)
    barrido = np.zeros_like(ruido)
    acc = 0.0
    for i, v in enumerate(ruido):
        u = i / len(ruido)
        a = 0.985 - 0.75 * u ** 1.5
        acc = a * acc + (1 - a) * v
        barrido[i] = acc
    env_w = np.minimum(1.0, t / 0.08) * np.clip((1.2 - t) / 0.12, 0, 1) * (0.5 + 0.5 * t / 1.2)
    out += 2.6 * barrido * env_w
    out += 0.35 * np.sin(2 * np.pi * np.cumsum(55 + 40 * t) / SR) * env
    w = whoosh()
    out[:len(w)] += 0.5 * w[:len(out)]
    return out


SONIDOS = {"viaje": viaje, "golpe": golpe, "vidrio": vidrio, "whoosh": whoosh, "boing": boing, "pop": pop,
           "tac": tac, "ding": ding}
_CACHE: dict[str, np.ndarray] = {}
GENERAR = True     # los tests lo apagan (conftest): nunca se llama a ElevenLabs desde una prueba


def conocido(nombre: str) -> bool:
    return nombre in SONIDOS or nombre in CATALOGO


def sonido(nombre: str) -> np.ndarray:
    """La biblioteca primero (ElevenLabs); si falta, se genera una vez; si no se puede, el sintetizado; si
    tampoco hay, nada (un arreglo vacío)."""
    if nombre not in _CACHE:
        ruta = _ruta(nombre) or (generar(nombre) if GENERAR else None)
        if ruta:
            x, sr = _leer(ruta)
            if sr != SR:
                raise ValueError(f"{ruta} no está a {SR} Hz")
        elif nombre in SONIDOS:
            x = SONIDOS[nombre]().astype(np.float32)
        else:
            x = np.zeros(0, dtype=np.float32)
        if len(x):
            x = x / max(1e-6, float(np.max(np.abs(x))))
        _CACHE[nombre] = x.astype(np.float32)
    return _CACHE[nombre]


def pista(eventos: list[tuple[float, str]], duracion: float, volumen: float = 0.35) -> np.ndarray:
    """Todos los SFX en una pista mono de `duracion` s (los que se superponen se suman)."""
    out = np.zeros(int(duracion * SR) + 1, dtype=np.float32)
    for t, nombre in eventos:
        if not conocido(nombre) or t < 0 or t >= duracion:
            continue
        x = sonido(nombre) * volumen
        a = int(t * SR)
        b = min(len(out), a + len(x))
        out[a:b] += x[:b - a]
    return out


def _leer(ruta: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(ruta)) as w:
        sr, ch, ancho = w.getframerate(), w.getnchannels(), w.getsampwidth()
        datos = w.readframes(w.getnframes())
    if ancho != 2:
        raise ValueError("solo wav de 16 bits")
    x = np.frombuffer(datos, dtype="<i2").astype(np.float32) / 32768.0
    return (x.reshape(-1, ch).mean(axis=1) if ch > 1 else x), sr


def mezclar(audio: Path, eventos: list[tuple[float, str]], salida: Path, duracion: float | None = None,
            volumen: float = 0.35) -> Path:
    """`audio` (voz + música, mono 48 kHz) + los SFX → `salida`, del largo `duracion` (o el del audio)."""
    x, sr = _leer(audio)
    if sr != SR:
        raise ValueError(f"el audio tiene que estar a {SR} Hz (tiene {sr})")
    dur = duracion if duracion is not None else len(x) / SR
    n = int(dur * SR)
    base = np.zeros(n, dtype=np.float32)
    base[:min(n, len(x))] = x[:n]
    fx = pista(eventos, dur, volumen)[:n]
    y = base + fx
    pico = float(np.max(np.abs(y))) if len(y) else 0.0
    if pico > 0.95:                     # limitador suave: nada de clipeo
        y = np.tanh(y * 1.2) / np.tanh(1.2 * pico) * 0.95
    salida.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return salida
