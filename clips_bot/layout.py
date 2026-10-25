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

import logging
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from .config import Camara, Render

log = logging.getLogger(__name__)

Deteccion = tuple[int, int, int, int]  # x, y, w, h en píxeles del video original

TOLERANCIA = 0.06  # distancia entre centros (fracción del frame) para considerar "misma cara"
# Y de tamaño parecido: 2026-10-25, en un clip de Auron la cara de él a pantalla completa (12 % del
# ancho) y la de un chico en una foto (2,7 %) caían en el mismo lugar y contaban como UNA cara
# estable al 90 %; el split puso la foto arriba como si fuera la cámara.
TAMANO_MAX = 1.6   # el ancho de dos detecciones de la misma cara no difiere en más que esto
FACTOR_CAMARA = 2.3  # alto del recorte de cámara / alto de la cara
RATIO_OVERLAY = 1.5  # ancho/alto típico de un overlay de webcam (entre 4:3 y 16:9; elxokas ≈ 510x340)
Fraccion = tuple[float, float, float, float]   # x, y, ancho, alto como fracción del cuadro


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
    tipo: str  # split | fullcam | fit_blur | sigue
    principal: Caja  # juego (split), el recorte (fullcam, sigue) o el frame entero (fit_blur)
    camara: Caja | None
    presencia: float  # fracción de frames con la cara estable
    cara: Deteccion | None
    # "sigue": el recorte se mueve con la cara. ((t, x, y) de la esquina del recorte, en segundos).
    camino: tuple = ()
    # fit_blur con zooms en los picos de volumen (zooms.py): ((inicio, fin), ...), cuánto y hacia dónde.
    zooms: tuple = ()
    zoom: float = 1.0
    zoom_centro: tuple = (0.5, 0.5)

    def ffmpeg_crop_movil(self) -> str:
        """crop con x e y que cambian con el tiempo: interpolación lineal entre los puntos."""
        c = self.principal
        return f"crop={c.w}:{c.h}:x='{_expr(self.camino, 1)}':y='{_expr(self.camino, 2)}'"


def _expr(puntos: tuple, k: int) -> str:
    """Una expresión de ffmpeg que va de punto a punto (lineal) según t."""
    if not puntos:
        return "0"
    if len(puntos) == 1:
        return str(puntos[0][k])
    expr = str(puntos[-1][k])
    for (t0, *a), (t1, *b) in reversed(list(zip(puntos, puntos[1:]))):
        v0, v1 = (a[k - 1], b[k - 1])
        tramo = f"{v0}+({v1}-{v0})*(t-{t0:.2f})/{max(t1 - t0, 0.01):.2f}"
        expr = f"if(lt(t,{t1:.2f}),{tramo},{expr})"
    return f"if(lt(t,{puntos[0][0]:.2f}),{puntos[0][k]},{expr})"   # entre comillas simples: sin escapar comas


# ---- "sigue": charla o IRL, zoom siguiendo la cara (pedido 2026-09-30) -----------------------------

ALTO_PERSONA = 3.3        # la persona visible (cabeza a pecho) ≈ 3,3 alturas de cara
ALTO_MIN_RECORTE = 0.45   # nunca más chico que esto del alto del frame (se vería muy pixelado)
CARA_Y = 0.36             # la cara a esta altura del recorte (deja lugar al cuerpo y al título)


def trayectoria(video: Path, n: int = 24) -> tuple[float, list[tuple[float, Deteccion | None]]]:
    """(duración, [(t, cara más grande de ese cuadro o None)]) en n cuadros parejos."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    escala = min(1.0, 960 / max(W, 1))
    out = []
    for i in range(n):
        idx = int(total * (0.02 + 0.96 * i / max(n - 1, 1)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, img = cap.read()
        if not ok:
            continue
        gris = cv2.cvtColor(cv2.resize(img, None, fx=escala, fy=escala), cv2.COLOR_BGR2GRAY)
        caras = cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=6,
                                         minSize=(max(24, int(0.04 * gris.shape[0])),) * 2)
        mejor = max(caras, key=lambda c: c[2] * c[3]) if len(caras) else None
        out.append((idx / fps, tuple(int(v / escala) for v in mejor) if mejor is not None else None))
    cap.release()
    return total / fps, out


def layout_sigue(W: int, H: int, render: Render, puntos: list, cara: Deteccion, presencia: float,
                 persona_min: float = 0.6) -> Layout | None:
    """Un recorte 9:16 que acompaña a la cara, del alto justo para que la persona ocupe al menos
    `persona_min` de la pantalla. None si no hay suficientes cuadros con cara para seguirla."""
    con = [(t, c) for t, c in puntos if c is not None]
    if len(con) < max(3, len(puntos) // 3):
        return None
    fh = sorted(c[3] for _, c in con)[len(con) // 2]
    ratio = render.ancho / render.alto
    alto = min(H, W / ratio, max(ALTO_PERSONA * fh / persona_min, ALTO_MIN_RECORTE * H))
    w, h = max(_par(alto * ratio), 2), max(_par(alto), 2)
    # Centro de la cara en cada cuadro (los que no tienen cara, interpolados), suavizado.
    ts = [t for t, _ in puntos]
    import numpy as np

    cx = np.interp(ts, [t for t, _ in con], [c[0] + c[2] / 2 for _, c in con])
    cy = np.interp(ts, [t for t, _ in con], [c[1] + c[3] / 2 for _, c in con])
    k = np.ones(3) / 3
    cx = np.convolve(np.pad(cx, 1, mode="edge"), k, mode="valid")
    cy = np.convolve(np.pad(cy, 1, mode="edge"), k, mode="valid")
    camino = []
    for t, x, y in zip(ts, cx, cy):
        x0 = _par(min(max(x - w / 2, 0), W - w))
        y0 = _par(min(max(y - CARA_Y * h, 0), H - h))
        camino.append((round(t, 2), x0, y0))
    return Layout("sigue", Caja(camino[0][1], camino[0][2], w, h), None, presencia, cara, tuple(camino))


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
                    and max(d[2], ref[2]) <= TAMANO_MAX * max(1, min(d[2], ref[2]))
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


def caras_en_caja(W: int, H: int, frames: list[list[Deteccion]], caja: Caja,
                  excepto: Deteccion | None = None, min_ancho: float = 0.065) -> float:
    """Fracción de frames con alguna cara DETECTADA dentro de la caja, sin contar la de la cámara.

    Mira las detecciones crudas y no `caras_estables` a propósito: al segundo de una charla lo
    agarra Haar de a ratos (se mueve, se ríe, gira), nunca con presencia suficiente para contar como
    cara estable, y esa es justo la que el split parte al medio.

    `min_ancho` (fracción del ancho del frame) saca las caras chicas. Hace falta: Haar ve "caras" en
    los skins de Minecraft y en la gente de una transmisión de fútbol. Medido 2026-09-23 sobre 9
    clips reales: las personas de los podcasts de coker miden 6,7–8,8 % del ancho y los skins de
    Vegetta 4,8–6,2 %. Solo con la presencia no alcanzaba (25 % contra 20 %: sin margen).
    """
    if not frames:
        return 0.0
    ex = (excepto[0] + excepto[2] / 2, excepto[1] + excepto[3] / 2) if excepto else None
    con_cara = 0
    for dets in frames:
        for x, y, w, h in dets:
            if w / W < min_ancho:
                continue
            cx, cy = x + w / 2, y + h / 2
            if ex and abs(cx - ex[0]) / W < TOLERANCIA and abs(cy - ex[1]) / H < TOLERANCIA:
                continue  # es la cámara del streamer, no una segunda persona
            if caja.x <= cx <= caja.x + caja.w and caja.y <= cy <= caja.y + caja.h:
                con_cara += 1
                break
    return con_cara / len(frames)


# ---- la webcam: un recuadro fijo con la cara del streamer en TODO el clip (2026-10-25) --------------
#
# Lo que distingue la webcam de cualquier otra cara (una foto en pantalla, un personaje, alguien en
# una llamada) es que vive en un recuadro que no se mueve y está todo el clip. Dos maneras de saber
# dónde está: la guardada por streamer (streamers.yaml → facecam, editable en /streamers) o, si no
# hay, los bordes que no se mueven alrededor de la cara (el marco del overlay).

FIJO_MIN = 0.8        # un píxel es "borde fijo" si es borde en al menos esta fracción de los cuadros
LADO_CUBIERTO = 0.7   # un lado del recuadro tiene que tener borde fijo en al menos esto de su largo
ESCALA_BORDES = 0.5   # los bordes se buscan a la mitad de tamaño (alcanza y es 4× más rápido)
CARA_CON_MARCO = 0.3  # con el marco de la webcam en su lugar, alcanza con ver la cara en esto de los
                      # cuadros (Haar la pierde cuando mira el chat o el juego)


def caja_de(f: Fraccion, W: int, H: int) -> Caja:
    """Una posición guardada como fracción del cuadro, en píxeles de este video."""
    x, y, w, h = f
    return Caja(_par(x * W), _par(y * H), max(_par(w * W), 2), max(_par(h * H), 2))


def bordes_fijos(imagenes: list, escala: float = ESCALA_BORDES):
    """Por píxel, en qué fracción de los cuadros hay un borde (Canny). El marco de un overlay da ~1;
    lo que se mueve (la persona, el juego), mucho menos. Con un cambio de escena a mitad del clip el
    marco no llega a FIJO_MIN, y está bien: entonces la webcam no está en todo el clip."""
    import cv2
    import numpy as np

    acum = None
    for img in imagenes:
        gris = cv2.cvtColor(cv2.resize(img, None, fx=escala, fy=escala), cv2.COLOR_BGR2GRAY)
        borde = cv2.dilate(cv2.Canny(gris, 60, 150), np.ones((3, 3), np.uint8)) > 0
        acum = borde.astype(np.float32) if acum is None else acum + borde
    return acum / max(len(imagenes), 1) if acum is not None else None


def recuadro_fijo(imagenes: list, cara: Deteccion, W: int, H: int) -> Caja | None:
    """El recuadro de bordes fijos que encierra a la cara (el marco de la webcam), o None.

    Por cada lado, los candidatos son las columnas (o filas) con borde fijo a lo largo de la cara; se
    queda con el rectángulo más chico cuyos cuatro lados están cubiertos de borde fijo en al menos
    LADO_CUBIERTO de su largo. El borde del cuadro cuenta como lado (webcams pegadas a un costado).
    """
    import numpy as np

    fijo = bordes_fijos(imagenes)
    if fijo is None:
        return None
    m = fijo >= FIJO_MIN
    h, w = m.shape
    e = w / W
    fx, fy, fw, fh = (int(v * e) for v in cara)
    if fw < 4 or fh < 4:
        return None
    alto_y = slice(max(fy, 0), min(fy + fh, h))
    ancho_x = slice(max(fx, 0), min(fx + fw, w))
    col = m[alto_y, :].mean(axis=0)     # cuánto de la altura de la cara cubre cada columna
    fila = m[:, ancho_x].mean(axis=1)

    def candidatos(perfil, desde, hasta, paso, borde_lim):
        out = [i for i in range(desde, hasta, paso) if 0 <= i < len(perfil) and perfil[i] >= 0.6][:6]
        return out + [borde_lim]          # el borde del cuadro también puede ser un lado

    izq = candidatos(col, fx - 1, max(fx - 3 * fw, -1), -1, 0)
    der = candidatos(col, fx + fw, min(fx + 4 * fw, w), 1, w - 1)
    arr = candidatos(fila, fy - 1, max(fy - 3 * fh, -1), -1, 0)
    aba = candidatos(fila, fy + fh, min(fy + 4 * fh, h), 1, h - 1)

    def cubierto(segmento) -> bool:
        return segmento.size > 0 and float(segmento.mean()) >= LADO_CUBIERTO

    mejor = None
    for x0 in izq:
        for x1 in der:
            for y0 in arr:
                for y1 in aba:
                    if x1 - x0 < 1.4 * fw or y1 - y0 < 1.4 * fh:
                        continue
                    if (x1 - x0) > 0.5 * w or (y1 - y0) > 0.7 * h:
                        continue
                    lados = [(x0 == 0 or cubierto(m[y0:y1 + 1, x0])),
                             (x1 == w - 1 or cubierto(m[y0:y1 + 1, x1])),
                             (y0 == 0 or cubierto(m[y0, x0:x1 + 1])),
                             (y1 == h - 1 or cubierto(m[y1, x0:x1 + 1]))]
                    # Al menos dos lados de verdad: con todos en el borde del cuadro sería el cuadro.
                    reales = sum(1 for v, lim in ((x0, 0), (x1, w - 1), (y0, 0), (y1, h - 1)) if v != lim)
                    if all(lados) and reales >= 2:
                        area = (x1 - x0) * (y1 - y0)
                        if mejor is None or area < mejor[0]:
                            mejor = (area, x0, y0, x1, y1)
    if mejor is None:
        return None
    _, x0, y0, x1, y1 = mejor
    # Adentro del marco (el borde dilatado ocupa ~2 px a esta escala).
    return Caja(_par((x0 + 2) / e), _par((y0 + 2) / e), _par((x1 - x0 - 3) / e), _par((y1 - y0 - 3) / e))


def caras_en_recuadro(imagenes: list, caja: Caja) -> tuple[float, Deteccion | None]:
    """(fracción de cuadros con una cara adentro de la caja, la cara mediana en píxeles del video).

    La caja se recorta y se agranda antes de buscar: Haar sobre el cuadro entero casi no ve la cara
    de una webcam chica (en el clip de Auron del 2026-10-25, 2 de 20 cuadros)."""
    import cv2

    if not imagenes:
        return 0.0, None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    perfil = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    halladas: list[Deteccion] = []
    con = 0
    for img in imagenes:
        H, W = img.shape[:2]
        x0, y0 = max(caja.x, 0), max(caja.y, 0)
        x1, y1 = min(caja.x + caja.w, W), min(caja.y + caja.h, H)
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        recorte_img = img[y0:y1, x0:x1]
        k = 360 / (y1 - y0)
        gris = cv2.cvtColor(cv2.resize(recorte_img, None, fx=k, fy=k), cv2.COLOR_BGR2GRAY)
        caras = list(cascade.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)))
        if not caras:   # de costado (mira el chat, el juego): el detector de perfil, y espejado
            caras = list(perfil.detectMultiScale(gris, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)))
            espejo = perfil.detectMultiScale(cv2.flip(gris, 1), scaleFactor=1.1, minNeighbors=5,
                                             minSize=(48, 48))
            caras += [(gris.shape[1] - x - w, y, w, h) for x, y, w, h in espejo]
        if len(caras):
            con += 1
            cx, cy, cw, ch = max(caras, key=lambda c: c[2] * c[3])
            halladas.append((int(x0 + cx / k), int(y0 + cy / k), int(cw / k), int(ch / k)))
    if not halladas:
        return 0.0, None
    cara = tuple(int(median(d[i] for d in halladas)) for i in range(4))
    return con / len(imagenes), cara   # type: ignore[return-value]


def marco_presente(fijo, caja: Caja, W: int, holgura: int = 5) -> int:
    """Cuántos lados de la caja tienen borde fijo (el marco del overlay) a lo largo de al menos
    LADO_CUBIERTO de su largo, buscando hasta `holgura` px (a la escala de los bordes) para cada lado:
    la posición guardada es aproximada. Un lado pegado al borde del cuadro cuenta como presente."""
    if fijo is None:
        return 0
    m = fijo >= FIJO_MIN
    h, w = m.shape
    e = w / W
    x0, y0 = int(caja.x * e), int(caja.y * e)
    x1, y1 = int((caja.x + caja.w) * e), int((caja.y + caja.h) * e)
    lados = 0
    for vertical, pos, a, b, lim in ((True, x0, y0, y1, 0), (True, x1, y0, y1, w - 1),
                                      (False, y0, x0, x1, 0), (False, y1, x0, x1, h - 1)):
        if abs(pos - lim) <= holgura:
            lados += 1
            continue
        mejor = 0.0
        for d in range(-holgura, holgura + 1):
            p = pos + d
            if vertical and 0 <= p < w:
                seg = m[max(a, 0):min(b, h), p]
            elif not vertical and 0 <= p < h:
                seg = m[p, max(a, 0):min(b, w)]
            else:
                continue
            if seg.size:
                mejor = max(mejor, float(seg.mean()))
        lados += mejor >= LADO_CUBIERTO
    return lados


def camara_desde_recuadro(caja: Caja, ratio: float, cara: Deteccion | None) -> Caja:
    """El recorte más grande con la proporción del panel de arriba que entra en el recuadro de la
    webcam, centrado en la cara (o en el recuadro si no hay cara)."""
    cx = cara[0] + cara[2] / 2 if cara else caja.x + caja.w / 2
    cy = cara[1] + cara[3] / 2 if cara else caja.y + caja.h / 2
    if caja.w / caja.h > ratio:          # recuadro más ancho que el panel: se recortan los costados
        h = caja.h
        w = h * ratio
    else:                                # más alto: se recorta arriba y abajo
        w = caja.w
        h = w / ratio
    x = min(max(cx - w / 2, caja.x), caja.x + caja.w - w)
    y = min(max(cy - h / 2, caja.y), caja.y + caja.h - h)
    return Caja(_par(x), _par(y), max(_par(w), 2), max(_par(h), 2))


def layout_split_recuadro(W: int, H: int, render: Render, caja: Caja, presencia: float,
                          cara: Deteccion | None) -> Layout:
    """Split con la webcam sacada de su recuadro. Abajo va el cuadro ENTERO (render.py), así que el
    `principal` es el cuadro completo."""
    ratio_cam = render.ancho / (render.alto_camara - render.separador_px)
    return Layout("split", Caja(0, 0, _par(W), _par(H)), camara_desde_recuadro(caja, ratio_cam, cara),
                  presencia, cara)


def layout_fit_blur(W: int, H: int, render: Render, presencia: float = 0.0,
                    cara: Deteccion | None = None) -> Layout:
    """El 16:9 entero sobre fondo borroso. `principal` es el frame completo: no se recorta nada."""
    return Layout("fit_blur", Caja(0, 0, _par(W), _par(H)), None, presencia, cara)


def decidir_layout(W: int, H: int, frames: list[list[Deteccion]], cam: Camara, render: Render,
                   forzado: str = "", charla: bool = False, puntos: list | None = None,
                   imagenes: list | None = None, facecams: tuple = ()) -> Layout:
    """Elige el layout (ver `fit_blur` en render.py para el porqué de cada regla).

    - la webcam guardada del streamer (`facecams`, fracciones del cuadro) con su cara en al menos
      `cam.presencia_facecam` de los cuadros → split con ese recuadro
    - facecam clara (una cara chica, del mismo tamaño y en el mismo lugar en casi todo el clip) →
      split, con el recuadro de bordes fijos si lo hay; salvo que abajo, en la zona del "juego",
      también haya caras: ahí no hay juego (podcast, llamada, estudio) → fit_blur
    - sin cara estable, o 2+ caras separadas sin una webcam clara → fit_blur
    - una sola cara grande: recorte central solo si queda centrada; si toca un borde → fit_blur

    `forzado` (streamers.yaml: layout_forzado) saltea todo esto. Un split o un fullcam forzados
    igual necesitan una cara; sin ella se cae a fit_blur, que es el único que no depende de nada.
    """
    ratio_total = render.ancho / render.alto
    caras = caras_estables(W, H, frames, cam.min_presencia)
    cara, presencia = (caras[0] if caras else (None, 0.0))
    if not caras:
        _, presencia = cara_estable(W, H, frames)  # para el informe, aunque no alcance el umbral

    if forzado == "fit_blur":
        return layout_fit_blur(W, H, render, presencia, cara)

    # La webcam guardada del streamer: la PRIMERA de sus posiciones (el orden es la prioridad) que está
    # en todo el clip: su marco fijo en el lugar (bordes que no se mueven) con una persona adentro, o
    # la cara en casi todos los cuadros. Medido 2026-10-25 en los Minecraft de Auron: arriba a la
    # derecha está la webcam de la invitada, con cara en 90 %; por eso gana el orden y no la presencia.
    if facecams and imagenes and forzado != "fullcam":
        fijo = bordes_fijos(imagenes)
        for i, f in enumerate(facecams):
            caja = caja_de(f, W, H)
            pres, cara_cam = caras_en_recuadro(imagenes, caja)
            lados = marco_presente(fijo, caja, W)
            log.info("Webcam guardada %d: marco %d/4 lados, cara en %.0f%% de los cuadros", i + 1, lados,
                     pres * 100)
            if (lados >= 3 and pres >= CARA_CON_MARCO) or pres >= cam.presencia_facecam:
                return layout_split_recuadro(W, H, render, caja, pres, cara_cam)

    if forzado in ("split", "fullcam") and cara is None:
        log.warning("layout_forzado=%s pero no hay cara estable: va fit_blur", forzado)
        return layout_fit_blur(W, H, render, presencia, cara)

    # Una webcam con marco fijo: la que está en todo el clip, aunque haya otras caras (una invitada,
    # una foto en pantalla). Abajo va el cuadro entero, así que esas otras caras no se cortan.
    if imagenes and not forzado:
        for c, p in caras:
            if p < cam.presencia_facecam or c[2] / W >= cam.cara_grande:
                continue
            caja = recuadro_fijo(imagenes, c, W, H)
            if caja is not None:
                log.info("Webcam en un recuadro fijo (%s), cara en %.0f%% de los cuadros: split", caja, p * 100)
                return layout_split_recuadro(W, H, render, caja, p, c)

    if forzado != "split" and (len(caras) >= 2 or cara is None):
        # dos personas separadas (cualquier recorte 9:16 corta a una o a las dos), o ningún rostro
        # estable (juego puro: el chat y el HUD viven en los bordes)
        return layout_fit_blur(W, H, render, presencia, cara)

    fx, fy, fw, fh = cara
    cx, cy = fx + fw / 2, fy + fh / 2

    # Charla o IRL con UNA persona (o una cara grande): zoom siguiendo la cara, que la persona ocupe
    # al menos `persona_min` del alto. fit_blur queda para cuando hace falta ver todo el cuadro.
    if cam.seguir_cara and not forzado and len(caras) == 1 and puntos \
            and (charla or fw / W >= cam.cara_grande):
        sigue = layout_sigue(W, H, render, puntos, cara, presencia, cam.persona_min)
        if sigue is not None:
            return sigue

    if forzado == "fullcam" or (not forzado and fw / W >= cam.cara_grande):
        central = recorte(W, H, ratio_total, cx, H / 2, H)
        if not forzado and (cortada_por(central, cara) or pegada_al_borde(central, cara, cam.margen_borde)):
            return layout_fit_blur(W, H, render, presencia, cara)
        return Layout("fullcam", central, None, presencia, cara)

    # El split es para una webcam, y una webcam está TODO el clip. Una cara que aparece y desaparece
    # (contenido en pantalla, un cambio de escena) no es la cámara del streamer.
    if not forzado and presencia < cam.presencia_facecam:
        log.info("Cara chica en %.0f%% de los cuadros (< %.0f%%): no es una webcam fija, va fit_blur",
                 presencia * 100, cam.presencia_facecam * 100)
        return layout_fit_blur(W, H, render, presencia, cara)

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
    # El split da por sentado que abajo hay un juego. Con contenido multicámara (podcast, llamada,
    # estudio con dos personas) no lo hay: el panel de abajo repite la escena y corta a alguien
    # (visto 2026-09-23 en dos clips de coker). Si hay caras ahí, no se recorta nada.
    en_juego = caras_en_caja(W, H, frames, juego, cara, cam.cara_juego_min)
    if not forzado and en_juego > cam.presencia_juego_max:
        log.info("Caras en la zona del juego en %.0f%% de los frames: no hay juego, va fit_blur", en_juego * 100)
        return layout_fit_blur(W, H, render, presencia, cara)
    # Abajo va el cuadro ENTERO (2026-10-25: el recorte del juego cortó la izquierda de la pantalla
    # de Auron). `juego` queda solo para la cuenta de caras de arriba.
    return Layout("split", Caja(0, 0, _par(W), _par(H)), camara, presencia, cara)


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
