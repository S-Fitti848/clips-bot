"""El JUEGO FIJO de manos de Así Nació (Santi, 2026-11-20: "manos bien dibujadas, con anatomía correcta: palma, pulgar
del lado opuesto, dedos que envuelven el objeto; usalas siempre en vez de armar manos nuevas").

Cada pose está dibujada UNA vez acá y la usan los personajes, Tito y los primeros planos:

    abierta   la palma con los cuatro dedos y el pulgar separado (festejar, la mano en la cara)
    relajada  los dedos apenas doblados (los brazos al costado)
    puno      el puño cerrado: los nudillos adelante y el pulgar cruzado encima
    senala    el índice estirado, los otros tres doblados y el pulgar encima del mayor
    agarra    agarrar una botella o un vaso (y servir: la misma, inclinada): la palma y el pulgar detrás del objeto y
              los cuatro dedos que lo ENVUELVEN por delante (`encima`, se dibuja después del objeto)
    pinza     sostener un papel: los dedos detrás del papel y el pulgar adelante (`encima`)
    lapiz     escribir: la lapicera entre el pulgar y el índice (`encima`), apoyada en el mayor

Marco de cada mano: la muñeca en (0, 0), los dedos hacia +x, el pulgar hacia -y (arriba). `mano()` la ubica en la
muñeca, girada como el antebrazo. El contorno tiene SIEMPRE el mismo grosor en la pantalla (`TRAZO_PX`, se divide por
la escala): en primer plano no se engorda. Los dedos se afinan hacia la punta, con uña y la arruga de la articulación.
"""
from __future__ import annotations

import math

from . import paleta as P
from .svg import aclarar, g, n, oscurecer

FORMAS = ("abierta", "relajada", "puno", "senala", "agarra", "pinza", "lapiz")
TRAZO_PX = 4.0      # el contorno en píxeles de la pantalla
ANCHO = 10.0        # el ancho de un dedo en la base (marco de la mano)
PULGAR = 11.5


class _Lapiz:
    """Junta las piezas de una mano: primero todos los contornos, después los rellenos y al final los detalles."""

    def __init__(self, piel: str, c: float):
        self.piel, self.c = piel, c
        self.cont, self.rell, self.det = [], [], []

    def palma(self, cerrada: bool) -> None:
        d = ("M-2 -12 C8 -17 22 -19 34 -18 C40 -17 42 -12 42 -4 L42 10 C42 16 38 19 32 19 C20 20 8 18 -2 13 Z"
             if not cerrada else
             "M-2 -12 C8 -17 22 -19 32 -18 C40 -16 44 -10 44 0 C44 10 40 17 32 18 C20 20 8 18 -2 13 Z")
        self.cont.append(f'<path d="{d}" fill="{P.CONTORNO}" stroke="{P.CONTORNO}" stroke-width="{n(2 * self.c)}" '
                         f'stroke-linejoin="round"/>')
        self.rell.append(f'<path d="{d}" fill="{self.piel}"/>')
        self.det.append(f'<path d="M2 9 C14 14 28 15 40 12 L40 17 C30 20 14 19 0 14 Z" '
                        f'fill="{oscurecer(self.piel, 0.16)}"/>')
        self.det.append("".join(f'<path d="M9 {y} Q22 {y * 1.05 - 1} 33 {y * 1.12}" fill="none" '
                                f'stroke="{oscurecer(self.piel, 0.2)}" stroke-width="1.3" stroke-linecap="round" '
                                f'opacity="0.55"/>' for y in (-8, -1, 6)))

    def dedo(self, pts, ancho: float = ANCHO, una: bool = True, arruga: bool = True) -> None:
        """Un dedo por sus articulaciones: cada falange un poco más angosta que la anterior; uña en la punta."""
        anchos = [ancho * (1 - 0.1 * k) for k in range(len(pts) - 1)]
        for (a, b), w in zip(zip(pts, pts[1:]), anchos):
            d = f"M{n(a[0])} {n(a[1])} L{n(b[0])} {n(b[1])}"
            self.cont.append(f'<path d="{d}" stroke="{P.CONTORNO}" stroke-width="{n(w + 2 * self.c)}" '
                             f'stroke-linecap="round"/>')
            self.rell.append(f'<path d="{d}" stroke="{self.piel}" stroke-width="{n(w)}" stroke-linecap="round"/>')
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        w = anchos[-1]
        if una:      # la uña: un rectángulo redondeado claro, justo antes de la punta
            self.det.append(g(f'<rect x="{n(-w * 0.62)}" y="{n(-w * 0.27)}" width="{n(w * 0.5)}" height="{n(w * 0.54)}" '
                              f'rx="{n(w * 0.2)}" fill="{aclarar(self.piel, 0.4)}" stroke="{oscurecer(self.piel, 0.28)}" '
                              f'stroke-width="{n(self.c * 0.35)}"/>', x2, y2, rot=ang))
        if arruga and len(pts) >= 3:
            mx, my = pts[-2]
            self.det.append(g(f'<path d="M0 {n(-w * 0.28)} Q{n(w * 0.12)} 0 0 {n(w * 0.28)}" fill="none" '
                              f'stroke="{oscurecer(self.piel, 0.3)}" stroke-width="{n(self.c * 0.4)}" '
                              f'stroke-linecap="round"/>', mx, my, rot=ang))

    def svg(self) -> str:
        return "".join(self.cont) + "".join(self.rell) + "".join(self.det)


def _forma(forma: str, piel: str, c: float) -> str:
    """La mano entera en su marco (muñeca en 0,0; dedos hacia +x; pulgar arriba)."""
    lp = _Lapiz(piel, c)
    cerrada = forma in ("puno", "senala", "agarra", "pinza", "lapiz")
    lp.palma(cerrada)
    pulgar = None
    if forma == "abierta":
        lp.dedo([(38, -13), (52, -16), (64, -18)])
        lp.dedo([(39, -4.5), (55, -5.5), (69, -6.5)])
        lp.dedo([(39, 4.5), (54, 5), (67, 5.5)])
        lp.dedo([(37, 13), (49, 15.5), (59, 18)], ANCHO * 0.88)
        pulgar = [(8, -13), (17, -26), (27, -34)]
    elif forma == "relajada":
        for y in (-13, -4.5, 4.5, 13):
            lp.dedo([(38, y), (50, y * 1.05 + 2), (55, y * 1.05 + 10)], ANCHO * (0.9 if y > 10 else 1))
        pulgar = [(8, -13), (20, -22), (30, -22)]
    elif forma == "senala":
        for y in (-3, 6, 14):
            lp.dedo([(40, y), (48, y + 1), (46, y + 8)], una=False)
        lp.dedo([(38, -12), (58, -12.5), (80, -12)])
        pulgar = [(10, -12), (26, -6), (40, -3)]
    elif forma == "puno":
        # los cuatro dedos enrollados hacia la palma: se ve cada uno doblado (nudillo, falange y la punta que vuelve)
        for y in (-13, -4.5, 4.5, 13):
            lp.dedo([(38, y - 1), (49, y), (51, y + 6), (44, y + 8)], ANCHO * (0.9 if y > 10 else 1), una=False)
        lp.det.append("".join(f'<circle cx="42" cy="{y}" r="2" fill="{oscurecer(piel, 0.25)}"/>'
                              for y in (-13, -4.5, 4.5, 13)))
        pulgar = [(10, -12), (28, -8), (40, -6)]
    elif forma == "agarra":
        pulgar = [(10, -13), (26, -22), (40, -24)]      # lo de ATRÁS del objeto: los dedos van en `encima`
    elif forma == "pinza":
        for y in (-13, -4.5, 4.5, 13):
            lp.dedo([(38, y), (52, y), (62, y + 2)], ANCHO * (0.9 if y > 10 else 1))
    elif forma == "lapiz":
        for y in (6, 14):
            lp.dedo([(40, y), (47, y + 1), (44, y + 7)], una=False)
        lp.dedo([(40, -3), (52, 0), (60, 6)])
    else:
        return _forma("relajada", piel, c)
    out = lp.svg()
    if pulgar:          # el pulgar encima de todo, del lado opuesto a los dedos
        lt = _Lapiz(piel, c)
        lt.dedo(pulgar, PULGAR)
        out += lt.svg()
    return out


def mano(x: float, y: float, ang: float, forma: str = "relajada", piel: str = "#f2c29b", escala: float = 1.0,
         espejo: bool = False) -> str:
    """La mano en la muñeca (x, y) apuntando a `ang` grados (la dirección del antebrazo). El pulgar queda del lado de
    arriba de la pantalla (o del de abajo, con `espejo`)."""
    forma = forma if forma in FORMAS else "relajada"
    abajo = math.cos(math.radians(ang)) < 0
    flip = -1 if (abajo != espejo) else 1
    return g(g(_forma(forma, piel, TRAZO_PX / max(0.2, escala)), escala=escala, escala_y=escala * flip), x, y, rot=ang)


def encima(tipo: str = "agarra", piel: str = "#f2c29b", lado: int = 1, escala: float = 1.0) -> str:
    """Lo que va DELANTE del objeto agarrado, centrado en el objeto: los cuatro dedos que lo envuelven (agarra: se ve
    el dorso de cada dedo con su nudillo, la punta se pierde detrás), el pulgar sobre el papel (pinza) o el pulgar y
    el índice sobre la lapicera (lapiz). `lado` -1 = mirando a la izquierda (se espeja). `escala`: la que se le va a
    aplicar afuera (para que el contorno quede del mismo grosor)."""
    c = TRAZO_PX / max(0.2, escala)
    lp = _Lapiz(piel, c)
    if tipo == "pinza":
        lp.dedo([(-14, 6), (-2, 0), (8, -4)], PULGAR)
    elif tipo == "lapiz":
        lp.dedo([(-18, -6), (-4, -6), (8, -2)])
        lp.dedo([(-16, 8), (-4, 4), (6, 2)], PULGAR)
    else:
        for y, largo in ((-15, 25), (-5, 27), (5, 25), (14.5, 20)):
            x0 = -largo / 2
            lp.dedo([(x0, y), (x0 + largo * 0.55, y - 0.5), (x0 + largo, y + 2.5)],
                    ANCHO * (0.88 if y > 10 else 1), una=False)
        for y in (-15, -5, 5, 14.5):       # los nudillos
            lp.det.append(f'<path d="M-6 {n(y - 3)} Q-4 {n(y)} -6 {n(y + 3)}" fill="none" '
                          f'stroke="{oscurecer(piel, 0.3)}" stroke-width="{n(c * 0.45)}" stroke-linecap="round"/>')
    cuerpo = lp.svg()
    return cuerpo if lado >= 0 else g(cuerpo, escala=-1, escala_y=1)


def dedos_encima(piel: str = "#f2c29b", lado: int = 1, tipo: str = "agarra") -> str:
    """Compatibilidad: los dedos que cierran sobre lo agarrado (prop `dedos`)."""
    return encima(tipo, piel, lado)


def brazo_desde_borde(x: float, y: float, ang: float, manga: str, largo: float = 1400, ancho: float = 46) -> str:
    """El antebrazo de una mano de primer plano que entra DESDE EL BORDE de la pantalla (Santi, 2026-11-20: "nunca una
    mano flotando en el medio"): sale de la muñeca (x, y) hacia atrás, en la dirección contraria a `ang`, lo bastante
    largo para llegar siempre al borde; con el puño de la camisa en la muñeca."""
    rad = math.radians(ang + 180)
    x2, y2 = x + math.cos(rad) * largo, y + math.sin(rad) * largo
    d = f"M{n(x)} {n(y)} L{n(x2)} {n(y2)}"
    px, py = x + math.cos(rad) * ancho * 0.25, y + math.sin(rad) * ancho * 0.25
    return (f'<path d="{d}" stroke="{P.CONTORNO}" stroke-width="{n(ancho + 2 * TRAZO_PX)}" stroke-linecap="butt"/>'
            f'<path d="{d}" stroke="{manga}" stroke-width="{n(ancho)}" stroke-linecap="butt"/>'
            f'<path d="{d}" stroke="{oscurecer(manga, 0.22)}" stroke-width="{n(ancho * 0.3)}" stroke-linecap="butt" '
            f'transform="translate(0 {n(ancho * 0.3)})" opacity="0.5"/>'
            + g(f'<rect x="{n(-ancho * 0.3)}" y="{n(-ancho * 0.58)}" width="{n(ancho * 0.6)}" height="{n(ancho * 1.16)}" '
                f'rx="{n(ancho * 0.14)}" fill="#f4f1ea" stroke="{P.CONTORNO}" stroke-width="{n(TRAZO_PX)}"/>', px, py,
                rot=ang))
