"""Fotos con parallax 3D para Pequeña Historia (pedido 2026-09-30).

Sin modelos que bajar: la figura se separa del fondo con GrabCut (OpenCV), empezando por la cara
más grande o por el centro; el hueco que deja en el fondo se rellena (inpaint); y en cada cuadro
las dos capas se mueven y se agrandan a distinta velocidad (el frente más): eso da la sensación de
profundidad. Si GrabCut no encuentra una figura razonable (menos del 8 % o más del 70 % de la
foto), va sin capas: el mismo movimiento, parejo.

Encuadre (pedido 2026-09-30, "que no queden chiquitas con mucho fondo borroso"): la foto ocupa al
menos `ALTO_MIN` del alto de la pantalla; si es horizontal se recortan los costados, hacia la cara
o el centro de la acción (`efemerides.foco`). El resto de la pantalla, el mismo fondo borroso.

Los cuadros se generan con numpy/cv2 y van por un pipe a ffmpeg (rgb24).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np

from .media import find_bin

log = logging.getLogger(__name__)

ALTO_MIN = 0.72          # la foto (o el video) ocupa al menos esto del alto de la pantalla
AMPLITUD = 0.022         # cuánto se corre el frente (fracción del ancho): con 0,035 se veía el relleno
ZOOM_FONDO, ZOOM_FRENTE = 1.03, 1.09
FIGURA_MIN, FIGURA_MAX = 0.08, 0.70


def caja(ancho: int, alto: int, W: int, H: int, alto_min: float = ALTO_MIN) -> tuple[float, int, int]:
    """(escala, ancho visible, alto visible) de la foto en la pantalla: de ancho completo si así ya
    llega a `alto_min`; si no (horizontal), la escala del alto mínimo y se recortan los costados."""
    s = W / ancho
    if alto * s < alto_min * H:
        s = alto_min * H / alto
    return s, min(W, int(round(ancho * s))), min(H, int(round(alto * s)))


# Caras SIEMPRE enteras (2026-10-02): el recorte y el zoom contienen todas las caras con este
# margen (en alturas o anchos de cara): bastante arriba de la cabeza (pelo, sombrero), algo a los
# costados y abajo (mentón, cuello).
MARGEN_CABEZA, MARGEN_LADO, MARGEN_ABAJO = 0.9, 0.4, 0.35


def caras(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Las caras (x, y, w, h) en píxeles de `img`, detectadas en chico (Haar)."""
    import cv2

    h, w = img.shape[:2]
    k = min(1.0, 900 / max(h, w))
    gris = cv2.cvtColor(cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k)))), cv2.COLOR_BGR2GRAY)
    cascada = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    lado = max(20, int(min(gris.shape) / 25))
    halladas = cascada.detectMultiScale(gris, 1.1, 5, minSize=(lado, lado))
    return [tuple(int(v / k) for v in c) for c in halladas]


def zona_caras(cs: list, ancho: int, alto: int) -> tuple[int, int, int, int] | None:
    """El rectángulo (x0, y0, x1, y1) que tiene que quedar a la vista: todas las caras con margen."""
    if not cs:
        return None
    x0 = min(x - MARGEN_LADO * w for x, y, w, h in cs)
    y0 = min(y - MARGEN_CABEZA * h for x, y, w, h in cs)
    x1 = max(x + w + MARGEN_LADO * w for x, y, w, h in cs)
    y1 = max(y + h + MARGEN_ABAJO * h for x, y, w, h in cs)
    return int(max(0, x0)), int(max(0, y0)), int(min(ancho, x1)), int(min(alto, y1))


def encuadre(ancho: int, alto: int, W: int, H: int, zona, foco: tuple[float, float],
             alto_min: float = ALTO_MIN, zoom: float = ZOOM_FRENTE) -> tuple[float, int, int, int, int]:
    """(escala, ancho visible, alto visible, x0, y0 del recorte en la foto escalada). Como `caja`,
    pero si las caras (con margen y con el zoom que viene) no entran, la foto se achica hasta que
    entren: antes una foto más chica que una cara cortada."""
    s, vis_w, vis_h = caja(ancho, alto, W, H, alto_min)
    if zona:
        zw, zh = (zona[2] - zona[0]) * zoom, (zona[3] - zona[1]) * zoom
        s = min(s, W / max(zw, 1), H / max(zh, 1))
        vis_w, vis_h = min(W, int(round(ancho * s))), min(H, int(round(alto * s)))
    bw, bh = int(round(ancho * s)), int(round(alto * s))
    cx, cy = (((zona[0] + zona[2]) / 2) / ancho, ((zona[1] + zona[3]) / 2) / alto) if zona else foco
    x0 = cx * bw - vis_w / 2
    y0 = cy * bh - vis_h / 2
    if zona:     # que la zona quede adentro aunque el centro empuje para un lado
        x0 = min(max(x0, zona[2] * s - vis_w), zona[0] * s)
        y0 = min(max(y0, zona[3] * s - vis_h), zona[1] * s)
    x0 = int(min(max(x0, 0), bw - vis_w))
    y0 = int(min(max(y0, 0), bh - vis_h))
    return s, vis_w, vis_h, x0, y0


def capas(img: np.ndarray, foco: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    """(máscara del frente 0-1 suavizada, fondo con el hueco rellenado). Trabaja en chico."""
    import cv2

    h, w = img.shape[:2]
    k = 512 / max(h, w)
    chica = cv2.resize(img, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA)
    hc, wc = chica.shape[:2]
    fx, fy = foco
    if (fx, fy) != (0.5, 0.5):     # hay cara: la figura va de la cara para abajo
        x0, x1 = max(1, int((fx - 0.25) * wc)), min(wc - 2, int((fx + 0.25) * wc))
        y0, y1 = max(1, int((fy - 0.2) * hc)), hc - 2
    else:
        x0, x1, y0, y1 = int(0.2 * wc), int(0.8 * wc), int(0.15 * hc), hc - 2
    mascara = np.zeros((hc, wc), np.uint8)
    try:
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(chica, mascara, (x0, y0, max(2, x1 - x0), max(2, y1 - y0)), bgd, fgd, 4,
                    cv2.GC_INIT_WITH_RECT)
        frente = np.where((mascara == cv2.GC_FGD) | (mascara == cv2.GC_PR_FGD), 1, 0).astype(np.uint8)
    except cv2.error:
        frente = np.zeros((hc, wc), np.uint8)
    fraccion = float(frente.mean())
    if not FIGURA_MIN <= fraccion <= FIGURA_MAX:
        return np.zeros((h, w), np.float32), img
    # La figura LLENA: GrabCut deja agujeros (en la primera prueba, la boca de un retrato quedaba
    # como fondo y al moverse se veía el paisaje adentro de la cara). Se queda el contorno exterior
    # de las partes grandes, relleno.
    frente = cv2.morphologyEx(frente, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contornos, _ = cv2.findContours(frente, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lleno = np.zeros_like(frente)
    grandes = [c for c in contornos if cv2.contourArea(c) >= 0.02 * hc * wc]
    cv2.drawContours(lleno, grandes, -1, 1, thickness=cv2.FILLED)
    frente = lleno
    if not FIGURA_MIN <= float(frente.mean()) <= FIGURA_MAX:
        return np.zeros((h, w), np.float32), img
    hueco = cv2.dilate(frente, np.ones((15, 15), np.uint8)) * 255
    fondo_chico = cv2.inpaint(chica, hueco, 12, cv2.INPAINT_TELEA)
    fondo = cv2.resize(fondo_chico, (w, h), interpolation=cv2.INTER_CUBIC)
    # El fondo rellenado solo donde estaba la figura: el resto, la foto original nítida.
    m_hueco = cv2.resize(hueco, (w, h)).astype(np.float32)[..., None] / 255
    fondo = (fondo * m_hueco + img * (1 - m_hueco)).astype(np.uint8)
    alfa = cv2.GaussianBlur(cv2.resize(frente.astype(np.float32), (w, h)), (0, 0), max(2, w / 300))
    return np.clip(alfa, 0, 1), fondo


def _mover(capa: np.ndarray, escala: float, dx: float, cx: float, cy: float) -> np.ndarray:
    """La capa agrandada `escala` alrededor de (cx, cy) y corrida dx píxeles, del mismo tamaño."""
    import cv2

    h, w = capa.shape[:2]
    M = np.float32([[escala, 0, (1 - escala) * cx + dx], [0, escala, (1 - escala) * cy]])
    return cv2.warpAffine(capa, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def renderizar(foto: Path, dur: float, salida: Path, W: int, H: int, blur: float, foco: tuple[float, float],
               fps: int = 30, preset: str = "veryfast", crf: int = 18, con_capas: bool = True) -> Path:
    """Un tramo de parallax de `dur` segundos, 1080x1920 (W×H), directo a mp4."""
    import cv2

    img = cv2.imread(str(foto))
    if img is None:
        raise RuntimeError(f"no pude leer {foto}")
    zona = zona_caras(caras(img), img.shape[1], img.shape[0])
    s, vis_w, vis_h, x0, y0 = encuadre(img.shape[1], img.shape[0], W, H, zona, foco)
    base = cv2.resize(img, (int(round(img.shape[1] * s)), int(round(img.shape[0] * s))),
                      interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    fx, fy = foco
    recorte = np.ascontiguousarray(base[y0:y0 + vis_h, x0:x0 + vis_w])
    alfa, fondo = capas(recorte, ((fx * base.shape[1] - x0) / vis_w, (fy * base.shape[0] - y0) / vis_h)) \
        if con_capas else (np.zeros(recorte.shape[:2], np.float32), recorte)
    hay_figura = bool(alfa.max() > 0)
    # El fondo de toda la pantalla: la foto agrandada y muy borrosa (quieta).
    ks = max(W / img.shape[1], H / img.shape[0])
    lleno = cv2.resize(img, (int(img.shape[1] * ks) + 2, int(img.shape[0] * ks) + 2))
    oy, ox = (lleno.shape[0] - H) // 2, (lleno.shape[1] - W) // 2
    borroso = cv2.GaussianBlur(np.ascontiguousarray(lleno[oy:oy + H, ox:ox + W]), (0, 0), blur)
    px, py = (W - vis_w) // 2, (H - vis_h) // 2
    frames = max(1, int(round(dur * fps)))
    # El zoom se hace alrededor de las caras: así no se van del cuadro al acercarse.
    if zona:
        cx = min(max((zona[0] + zona[2]) / 2 * s - x0, 0), vis_w)
        cy = min(max((zona[1] + zona[3]) / 2 * s - y0, 0), vis_h)
    else:
        cx, cy = vis_w * 0.5, vis_h * 0.5
    salida.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps),
                          "-i", "-", "-frames:v", str(frames), "-c:v", "libx264", "-preset", preset,
                          "-crf", str(crf), "-pix_fmt", "yuv420p", str(salida)], stdin=subprocess.PIPE)
    try:
        for n in range(frames):
            t = n / max(frames - 1, 1)
            t = t * t * (3 - 2 * t)          # arranca y termina suave
            atras = _mover(fondo, 1 + (ZOOM_FONDO - 1) * t, -AMPLITUD * vis_w * 0.35 * t, cx, cy)
            if hay_figura:
                adelante = _mover(recorte, 1 + (ZOOM_FRENTE - 1) * t, AMPLITUD * vis_w * t, cx, cy)
                m = _mover(alfa, 1 + (ZOOM_FRENTE - 1) * t, AMPLITUD * vis_w * t, cx, cy)
                cuadro_foto = cv2.blendLinear(adelante, atras, m, 1 - m)   # 6× más rápido que en float
            else:
                cuadro_foto = _mover(recorte, 1 + (ZOOM_FRENTE - 1) * t, AMPLITUD * vis_w * 0.5 * t, cx, cy)
            cuadro = borroso.copy()
            cuadro[py:py + vis_h, px:px + vis_w] = cuadro_foto
            p.stdin.write(cuadro.tobytes())
    finally:
        p.stdin.close()
        p.wait()
    if p.returncode != 0 or not salida.exists():
        raise RuntimeError(f"ffmpeg no pudo armar el parallax de {foto.name}")
    return salida
