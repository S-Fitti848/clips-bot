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


@dataclass(frozen=True)
class Deporte:
    """Resultado de las dos señales. `motivo` vacío = no dispara ninguna."""
    motivo: str = ""
    marcador: Marcador = Marcador(False)
    cesped_max: float = 0.0  # mayor fracción de césped vista en un frame
    frames_con_cesped: int = 0

    @property
    def hay(self) -> bool:
        return bool(self.motivo)

    def a_dict(self) -> dict:
        return {"motivo": self.motivo, "esquina": self.marcador.esquina,
                "quietud": self.marcador.quietud, "bordes": self.marcador.bordes,
                "cesped_max": round(self.cesped_max, 3), "frames_con_cesped": self.frames_con_cesped}


def evaluar_region(quietud: float, bordes: float, quietud_min: float, bordes_min: float) -> bool:
    return quietud >= quietud_min and bordes >= bordes_min


def fraccion_cesped(img_bgr) -> float:
    """Fracción de píxeles verde-césped: una cancha de fútbol llena la pantalla de verde uniforme.

    Verde en HSV (OpenCV: H 0–179), con saturación y brillo medios para no contar verdes oscuros de
    sombra ni grises. Minecraft también tiene verde, pero mucho menos uniforme y casi nunca tan
    dominante como una cancha en cámara abierta.
    """
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mascara = cv2.inRange(hsv, np.array([30, 60, 40]), np.array([90, 255, 235]))
    return float((mascara > 0).mean())


def detectar_deporte(video: Path, n_frames: int, quietud_min: float, bordes_min: float,
                     cesped_min: float, cesped_frames_min: int) -> Deporte:
    """Dos señales, baratas las dos. Si cualquiera dispara, el clip es transmisión deportiva.

    1. Marcador de TV: esquina de arriba quieta y con mucho borde (ver `detectar`).
    2. Césped: fracción de verde-césped alta en varios frames (una cancha llena la pantalla).
    La 2 cubre el caso que la 1 no ve: cámara sobre la tribuna o el juego sin el gráfico en pantalla.
    """
    marcador, cespedes = detectar(video, n_frames, quietud_min, bordes_min, con_cesped=True)
    con_cesped = sum(1 for c in cespedes if c >= cesped_min)
    motivo = ""
    if marcador.hay:
        motivo = (f"marcador de TV ({marcador.esquina}, quietud {marcador.quietud}, "
                  f"bordes {marcador.bordes})")
    elif con_cesped >= cesped_frames_min:
        motivo = f"cancha en pantalla ({con_cesped}/{len(cespedes)} frames con ≥ {cesped_min:.0%} de césped)"
    return Deporte(motivo, marcador, max(cespedes, default=0.0), con_cesped)


def detectar(video: Path, n_frames: int, quietud_min: float, bordes_min: float,
             ancho_region: float = 0.30, alto_region: float = 0.18,
             con_cesped: bool = False) -> Marcador | tuple[Marcador, list[float]]:
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

    grises, cespedes = [], []
    # Se muestrea casi todo el clip (3 %–97 %): en el clip de fútbol de Davoo la cancha aparecía
    # recién al final, y con el rango 10 %–90 % se veía en un solo frame.
    for i in range(n_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (0.03 + 0.94 * i / max(n_frames - 1, 1))))
        ok, img = cap.read()
        if ok:
            grises.append(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            if con_cesped:
                cespedes.append(fraccion_cesped(img))
    cap.release()
    if len(grises) < 2:
        return (Marcador(False), cespedes) if con_cesped else Marcador(False)

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
    return (mejor, cespedes) if con_cesped else mejor
