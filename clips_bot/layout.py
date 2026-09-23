"""§3 paso 5: detectar la cámara del streamer y decidir los recortes del 9:16.

Tres layouts:
  split     cámara chica (overlay) → cámara arriba (ancho x alto_camara) + juego abajo
  fullcam   UNA cara grande y centrada → crop 9:16 centrado en la cara
  fit_blur  todo lo demás → el 16:9 entero sobre fondo borroso, sin recortar (ver render.py)

"Hay cámara" = una cara aparece en el mismo lugar en ≥ min_presencia de los frames muestreados.
Así se ignoran caras de personajes del juego, que cambian de lugar.

El recorte central sin cara (antes "sincam") se sacó el 2026-09-23: partía en dos a la gente
sentada en una mesa y cortaba el chat y el HUD en los clips de juego sin cámara.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median

from .config import Camara, Render

Deteccion = tuple[int, int, int, int]  # x, y, w, h en píxeles del video original

TOLERANCIA = 0.06  # distancia entre centros (fracción del frame) para considerar "misma cara"
FACTOR_CAMARA = 2.3  # alto del recorte de cámara / alto de la cara
RATIO_OVERLAY = 1.5  # ancho/alto típico de un overlay de webcam (entre 4:3 y 16:9; elxokas ≈ 510x340)


@dataclass(frozen=True)
class Caja:
    x: int
    y: int
    w: int
    h: int

    def ffmpeg_crop(self) -> str:
        return f"crop={self.w}:{self.h}:{self.x}:{self.y}"


@dataclass(frozen=True)
class Layout:
    tipo: str  # split | fullcam | fit_blur
    principal: Caja  # juego (split), el recorte (fullcam) o el frame entero (fit_blur)
    camara: Caja | None
    presencia: float  # fracción de frames con la cara estable
    cara: Deteccion | None


def _par(n: float) -> int:
    """Redondea hacia abajo a par (libx264 con yuv420p exige dimensiones pares)."""
    return max(0, int(n) // 2 * 2)


def recorte(W: int, H: int, ratio: float, cx: float, cy: float, alto: float) -> Caja:
    """Caja con relación ancho/alto = ratio, centrada en (cx, cy) y metida dentro del frame."""
    h = min(alto, H, W / ratio)
    w = max(_par(h * ratio), 2)
    h = max(_par(h), 2)
    x = min(max(cx - w / 2, 0), W - w)
    y = min(max(cy - h / 2, 0), H - h)
    return Caja(_par(x), _par(y), w, h)


def cara_estable(W: int, H: int, frames: list[list[Deteccion]]) -> tuple[Deteccion | None, float]:
    """La cara que aparece en más frames en el mismo lugar, como mediana de sus detecciones."""
    if not frames:
        return None, 0.0

    def centro(d: Deteccion) -> tuple[float, float]:
        return (d[0] + d[2] / 2) / W, (d[1] + d[3] / 2) / H

    mejor: list[Deteccion] = []
    for dets in frames:
        for ref in dets:
            rx, ry = centro(ref)
            apoyo: list[Deteccion] = []
            for otros in frames:
                cerca = [
                    d for d in otros
                    if abs(centro(d)[0] - rx) < TOLERANCIA and abs(centro(d)[1] - ry) < TOLERANCIA
                ]
                if cerca:
                    apoyo.append(min(cerca, key=lambda d: abs(centro(d)[0] - rx) + abs(centro(d)[1] - ry)))
            if len(apoyo) > len(mejor):
                mejor = apoyo
    if not mejor:
        return None, 0.0
    cara = tuple(int(median(d[i] for d in mejor)) for i in range(4))
    return cara, len(mejor) / len(frames)  # type: ignore[return-value]


def caras_estables(W: int, H: int, frames: list[list[Deteccion]], min_presencia: float,
                   max_caras: int = 3) -> list[tuple[Deteccion, float]]:
    """Todas las caras que se repiten en el mismo lugar, de la más presente a la menos.

    Se busca la mejor, se sacan las detecciones que la sostienen y se vuelve a buscar: así dos
    personas sentadas en una mesa salen como dos caras, no como una.
    """
    encontradas: list[tuple[Deteccion, float]] = []
    restantes = [list(f) for f in frames]
    for _ in range(max_caras):
        cara, presencia = cara_estable(W, H, restantes)
        if cara is None or presencia < min_presencia:
            break
        encontradas.append((cara, presencia))
        cx, cy = cara[0] + cara[2] / 2, cara[1] + cara[3] / 2
        restantes = [
            [d for d in dets
             if abs((d[0] + d[2] / 2) - cx) / W >= TOLERANCIA * 2
             or abs((d[1] + d[3] / 2) - cy) / H >= TOLERANCIA * 2]
            for dets in restantes
        ]
    return encontradas


def cortada_por(caja: Caja, cara: Deteccion) -> bool:
    """La cara queda partida por un borde del recorte: entra en parte y en parte queda afuera."""
    fx, fy, fw, fh = cara
    dentro_x = max(fx, caja.x) < min(fx + fw, caja.x + caja.w)
    dentro_y = max(fy, caja.y) < min(fy + fh, caja.y + caja.h)
    if not (dentro_x and dentro_y):
        return False  # la cara quedó entera afuera: no está "cortada"
    return fx < caja.x or fy < caja.y or fx + fw > caja.x + caja.w or fy + fh > caja.y + caja.h


def pegada_al_borde(caja: Caja, cara: Deteccion, margen: float = 0.15) -> bool:
    """La cara queda a menos de `margen` del ancho/alto del recorte de alguno de sus bordes."""
    fx, fy, fw, fh = cara
    mx, my = caja.w * margen, caja.h * margen
    return (fx - caja.x < mx or (caja.x + caja.w) - (fx + fw) < mx
            or fy - caja.y < my or (caja.y + caja.h) - (fy + fh) < my)


def layout_fit_blur(W: int, H: int, render: Render, presencia: float = 0.0,
                    cara: Deteccion | None = None) -> Layout:
    """El 16:9 entero sobre fondo borroso. `principal` es el frame completo: no se recorta nada."""
    return Layout("fit_blur", Caja(0, 0, _par(W), _par(H)), None, presencia, cara)


def decidir_layout(W: int, H: int, frames: list[list[Deteccion]], cam: Camara, render: Render) -> Layout:
    """Elige el layout (ver `fit_blur` en render.py para el porqué de cada regla).

    - facecam clara (una cara chica y estable) → split cámara/juego
    - sin cara estable, o 2+ caras separadas → fit_blur
    - una sola cara grande: recorte central solo si queda centrada; si toca un borde → fit_blur
    """
    ratio_total = render.ancho / render.alto
    caras = caras_estables(W, H, frames, cam.min_presencia)
    cara, presencia = (caras[0] if caras else (None, 0.0))
    if not caras:
        _, presencia = cara_estable(W, H, frames)  # para el informe, aunque no alcance el umbral

    if len(caras) >= 2 or cara is None:
        # dos personas separadas (cualquier recorte 9:16 corta a una o a las dos), o ningún rostro
        # estable (juego puro: el chat y el HUD viven en los bordes)
        return layout_fit_blur(W, H, render, presencia, cara)

    fx, fy, fw, fh = cara
    cx, cy = fx + fw / 2, fy + fh / 2

    if fw / W >= cam.cara_grande:
        central = recorte(W, H, ratio_total, cx, H / 2, H)
        if cortada_por(central, cara) or pegada_al_borde(central, cara, cam.margen_borde):
            return layout_fit_blur(W, H, render, presencia, cara)
        return Layout("fullcam", central, None, presencia, cara)

    # Cámara: en una webcam overlay la cara ocupa ~45 % del alto → 2.3 alturas de cara,
    # un poco corrida hacia abajo (hombros). El panel de arriba pierde `separador_px` para la línea negra.
    ratio_cam = render.ancho / (render.alto_camara - render.separador_px)
    centro_y = cy + 0.15 * fh
    camara = recorte(W, H, ratio_cam, cx, centro_y, fh * FACTOR_CAMARA)
    camara = recortar_abajo(camara, render.recorte_inferior_camara_px, ratio_cam)
    ratio_juego = render.ancho / (render.alto - render.alto_camara)
    # El juego se aleja del overlay real, no del recorte de cámara: el recorte depende de la proporción
    # del panel de salida (y del recorte de abajo), el overlay no. Se estima con proporción de webcam típica.
    overlay = recorte(W, H, RATIO_OVERLAY, cx, centro_y, fh * FACTOR_CAMARA)
    juego = _alejar_de(recorte(W, H, ratio_juego, W / 2, H / 2, H), overlay, W)
    return Layout("split", juego, camara, presencia, cara)


def recortar_abajo(caja: Caja, px: int, ratio: float) -> Caja:
    """Saca `px` (del video original) del pie de la caja, manteniendo el borde de arriba, el centro
    horizontal y la proporción. Es para no mostrar la UI del juego que queda debajo del overlay de la
    cámara. Nunca achica más del 30 %."""
    if px <= 0:
        return caja
    h = max(_par(caja.h - px), _par(caja.h * 0.7))
    w = _par(h * ratio)
    x = _par(caja.x + (caja.w - w) / 2)
    return Caja(x, caja.y, w, h)


def _alejar_de(juego: Caja, cam: Caja, W: int) -> Caja:
    """Si el overlay de la cámara se mete un poco en el recorte del juego, corre el juego para el
    otro lado para no mostrar la cámara dos veces. Si la cámara está en el medio, no se toca."""
    solape = min(juego.x + juego.w, cam.x + cam.w) - max(juego.x, cam.x)
    if solape <= 0 or solape > juego.w * 0.25:
        return juego
    if cam.x + cam.w / 2 < W / 2:
        x = min(cam.x + cam.w, W - juego.w)
    else:
        x = max(cam.x - juego.w, 0)
    return Caja(_par(x), juego.y, juego.w, juego.h)


# ---- OpenCV ------------------------------------------------------------------


def detectar_caras(video: Path, n_frames: int) -> tuple[int, int, list[list[Deteccion]], list]:
    """Muestrea n_frames entre el 5 % y el 95 % del clip y detecta caras frontales.

    Devuelve (ancho, alto, detecciones por frame, frames muestreados en BGR para el debug).
    """
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV no puede abrir {video}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    escala = min(1.0, 960 / W)  # detectar sobre ~960 px de ancho, mucho más rápido y alcanza
    min_lado = max(24, int(0.04 * H * escala))
    frames: list[list[Deteccion]] = []
    imagenes = []
    for i in range(n_frames):
        idx = int(total * (0.05 + 0.9 * i / max(n_frames - 1, 1)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, img = cap.read()
        if not ok:
            continue
        imagenes.append(img)
        gris = cv2.cvtColor(cv2.resize(img, None, fx=escala, fy=escala), cv2.COLOR_BGR2GRAY)
        caras = cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=6, minSize=(min_lado, min_lado))
        frames.append([tuple(int(v / escala) for v in c) for c in caras])
    cap.release()
    return W, H, frames, imagenes


def guardar_debug(imagen, layout: Layout, destino: Path) -> None:
    """Frame con la cara (amarillo), el recorte de cámara (verde) y el principal (rojo)."""
    import cv2

    img = imagen.copy()
    if layout.cara:
        x, y, w, h = layout.cara
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 255), 3)
    if layout.camara:
        c = layout.camara
        cv2.rectangle(img, (c.x, c.y), (c.x + c.w, c.y + c.h), (0, 255, 0), 4)
    p = layout.principal
    cv2.rectangle(img, (p.x, p.y), (p.x + p.w, p.y + p.h), (0, 0, 255), 4)
    texto = f"{layout.tipo}  presencia={layout.presencia:.0%}"
    cv2.putText(img, texto, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(destino), img)


def cara_cortada_en_render(video: Path, n_frames: int = 8, margen_px: int = 6) -> tuple[bool, str]:
    """Chequeo DESPUÉS del render: ¿hay alguna cara pegada a un borde del 9:16 final?

    Una cara que el recorte partió al medio queda con su caja tocando el borde. Es barato y atrapa
    los casos que la decisión previa no vio (ej. la persona se mueve a un costado a mitad del clip).
    Devuelve (hay_corte, detalle) para poder anotarlo en el json.
    """
    W, H, frames, _ = detectar_caras(video, n_frames)
    for dets in frames:
        for x, y, w, h in dets:
            if x <= margen_px or y <= margen_px or x + w >= W - margen_px or y + h >= H - margen_px:
                return True, f"cara pegada al borde en {x},{y} {w}x{h} (frame {W}x{H})"
    return False, ""
