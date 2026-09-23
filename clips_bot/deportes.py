"""Detección de transmisión deportiva en pantalla (marcador de TV).

Señal elegida: en las transmisiones de fútbol hay un marcador fijo en una esquina de arriba. O sea,
una región que casi no cambia entre frames (mientras el resto del video sí cambia) y que tiene mucho
borde (texto y líneas del gráfico). Es una heurística, no un detector: da falsos positivos con
HUDs de juegos y marcas de agua fijas, por eso se activa por streamer (`detectar_marcador: true`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Marcador:
    hay: bool
    esquina: str = ""
    quietud: float = 0.0  # 1 = la región no cambió nada entre frames
    bordes: float = 0.0  # fracción de píxeles que son borde


def evaluar_region(quietud: float, bordes: float, quietud_min: float, bordes_min: float) -> bool:
    return quietud >= quietud_min and bordes >= bordes_min


def detectar(video: Path, n_frames: int, quietud_min: float, bordes_min: float,
             ancho_region: float = 0.30, alto_region: float = 0.18) -> Marcador:
    """Mira las dos esquinas de arriba en n_frames repartidos por el clip."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV no puede abrir {video}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    rw, rh = int(W * ancho_region), int(H * alto_region)

    grises = []
    for i in range(n_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (0.1 + 0.8 * i / max(n_frames - 1, 1))))
        ok, img = cap.read()
        if ok:
            grises.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    cap.release()
    if len(grises) < 2:
        return Marcador(False)

    # Se guarda siempre la mejor medición, dispare o no: sin eso no hay con qué calibrar.
    mejor = Marcador(False)
    for nombre, x0 in (("arriba-izq", 0), ("arriba-der", W - rw)):
        regiones = [g[0:rh, x0:x0 + rw] for g in grises]
        # Cuánto cambia la región entre frames, comparado con cuánto cambia el frame entero:
        # así un clip entero quieto (pantalla de carga) no dispara.
        cambio_region = float(np.mean([np.mean(np.abs(a.astype("int16") - b.astype("int16")))
                                       for a, b in zip(regiones, regiones[1:])]))
        cambio_frame = float(np.mean([np.mean(np.abs(a.astype("int16") - b.astype("int16")))
                                      for a, b in zip(grises, grises[1:])])) or 1.0
        quietud = max(0.0, 1.0 - cambio_region / cambio_frame)
        bordes = float((cv2.Canny(regiones[len(regiones) // 2], 80, 200) > 0).mean())
        log.debug("marcador %s: quietud %.2f bordes %.3f", nombre, quietud, bordes)
        dispara = evaluar_region(quietud, bordes, quietud_min, bordes_min)
        if (dispara and not mejor.hay) or (dispara == mejor.hay and quietud > mejor.quietud):
            mejor = Marcador(dispara, nombre, round(quietud, 2), round(bordes, 3))
    return mejor
