"""El JUEGO FIJO de manos de Así Nació (Santi, 2026-11-20: "manos bien dibujadas, con anatomía correcta: palma, pulgar
del lado opuesto, dedos que envuelven el objeto; usalas siempre en vez de armar manos nuevas").

Cada pose está dibujada UNA vez acá y la usan los personajes, Tito y los primeros planos:

    abierta   la palma con los cuatro dedos y el pulgar separado (festejar, la mano en la cara)
    relajada  los dedos apenas doblados (los brazos al costado)
    puno      el puño: los dedos doblados con los nudillos marcados y el pulgar cruzado por delante del índice y el mayor
    senala    el índice bien estirado; los otros tres doblados contra la palma (se ven los nudillos) y el pulgar
              apoyado de costado sobre el mayor
    agarra    agarrar una botella o un vaso (y servir, inclinada): la palma detrás del objeto; los cuatro dedos lo
              envuelven por delante y el pulgar cruza por delante pasando sobre el índice (`encima`)
    pinza     sostener un papel: los dedos detrás del papel y el pulgar adelante (`encima`)
    lapiz     escribir: la lapicera (incluida) agarrada en pinza cerca de la punta entre las yemas del pulgar, el índice
              y el mayor, inclinada apoyando sobre el nudillo del índice; anular y meñique doblados apoyados en el papel

EL PULGAR (Santi, 2026-11-20): nace del costado de la palma, cerca de la muñeca; dos partes y uña en la punta; del lado
opuesto a los otros dedos. Su raíz se funde con la palma (sin contorno donde se unen): nunca un óvalo pegado encima.

Marco de cada mano: la muñeca en (0, 0), los dedos hacia +x, el pulgar hacia -y (arriba). `mano()` la ubica en la
muñeca, girada como el antebrazo. El contorno tiene SIEMPRE el mismo grosor en la pantalla (`TRAZO_PX`).
"""
from __future__ import annotations

import math

from . import paleta as P
from .svg import aclarar, g, n, oscurecer

FORMAS = ("abierta", "relajada", "puno", "senala", "agarra", "pinza", "lapiz")
TRAZO_PX = 4.0      # el contorno en píxeles de la pantalla
ANCHO = 10.0        # el ancho de un dedo en la base (marco de la mano)
PULGAR = 12.0
ESCALA_PERSONAJE = 1.45    # el tamaño de la mano en los personajes (plano medio): más grande que antes (1,15)
RAIZ_PULGAR = (7.0, -9.0)  # de dónde nace el pulgar: el costado de la palma, cerca de la muñeca


class _Lapiz:
    """Junta piezas: primero todos los contornos, después los rellenos y al final los detalles (lo que va junto en un
    mismo _Lapiz queda unido, sin rayas adentro)."""

    def __init__(self, piel: str, c: float):
        self.piel, self.c = piel, c
        self.cont, self.rell, self.det = [], [], []

    def forma(self, d: str) -> None:
        self.cont.append(f'<path d="{d}" fill="{P.CONTORNO}" stroke="{P.CONTORNO}" stroke-width="{n(2 * self.c)}" '
                         f'stroke-linejoin="round"/>')
        self.rell.append(f'<path d="{d}" fill="{self.piel}"/>')

    def palma(self, cerrada: bool) -> None:
        self.forma("M-2 -12 C8 -17 22 -19 34 -18 C40 -17 42 -12 42 -4 L42 10 C42 16 38 19 32 19 C20 20 8 18 -2 13 Z"
                   if not cerrada else
                   "M-2 -12 C8 -17 22 -19 32 -18 C40 -16 44 -10 44 0 C44 10 40 17 32 18 C20 20 8 18 -2 13 Z")
        self.det.append(f'<path d="M2 9 C14 14 28 15 40 12 L40 17 C30 20 14 19 0 14 Z" '
                        f'fill="{oscurecer(self.piel, 0.16)}"/>')
        self.det.append("".join(f'<path d="M12 {y} Q24 {y * 1.05 - 1} 34 {y * 1.12}" fill="none" '
                                f'stroke="{oscurecer(self.piel, 0.2)}" stroke-width="1.3" stroke-linecap="round" '
                                f'opacity="0.5"/>' for y in (-2, 5)))

    def dedo(self, pts, ancho: float = ANCHO, una: bool = True, arruga: bool = True) -> None:
        """Un dedo por sus articulaciones: cada falange un poco más angosta; uña en la punta."""
        anchos = [ancho * (1 - 0.09 * k) for k in range(len(pts) - 1)]
        for (a, b), w in zip(zip(pts, pts[1:]), anchos):
            d = f"M{n(a[0])} {n(a[1])} L{n(b[0])} {n(b[1])}"
            self.cont.append(f'<path d="{d}" stroke="{P.CONTORNO}" stroke-width="{n(w + 2 * self.c)}" '
                             f'stroke-linecap="round"/>')
            self.rell.append(f'<path d="{d}" stroke="{self.piel}" stroke-width="{n(w)}" stroke-linecap="round"/>')
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        w = anchos[-1]
        if una:
            self.det.append(g(f'<rect x="{n(-w * 0.62)}" y="{n(-w * 0.27)}" width="{n(w * 0.5)}" height="{n(w * 0.54)}" '
                              f'rx="{n(w * 0.2)}" fill="{aclarar(self.piel, 0.4)}" stroke="{oscurecer(self.piel, 0.28)}" '
                              f'stroke-width="{n(self.c * 0.35)}"/>', x2, y2, rot=ang))
        if arruga and len(pts) >= 3:
            mx, my = pts[-2]
            self.det.append(g(f'<path d="M0 {n(-w * 0.28)} Q{n(w * 0.12)} 0 0 {n(w * 0.28)}" fill="none" '
                              f'stroke="{oscurecer(self.piel, 0.3)}" stroke-width="{n(self.c * 0.4)}" '
                              f'stroke-linecap="round"/>', mx, my, rot=ang))

    def nudillo(self, x: float, y: float) -> None:
        """Un nudillo de un dedo doblado (puño, señalar): el bulto redondo con su arruga."""
        self.det.append(f'<path d="M{n(x - 2)} {n(y - 3.5)} Q{n(x + 2.5)} {n(y)} {n(x - 2)} {n(y + 3.5)}" fill="none" '
                        f'stroke="{oscurecer(self.piel, 0.32)}" stroke-width="{n(self.c * 0.45)}" stroke-linecap="round"/>')

    def svg(self) -> str:
        return "".join(self.cont) + "".join(self.rell) + "".join(self.det)


def _pulgar(piel: str, c: float, medio, punta, raiz=RAIZ_PULGAR) -> str:
    """El pulgar ENCIMA de lo que cruza, pero nacido del costado de la palma: dos falanges con uña y, en la raíz, un
    parche del color de la piel que borra el contorno donde se une a la palma (no queda un óvalo pegado)."""
    lt = _Lapiz(piel, c)
    lt.dedo([raiz, medio, punta], PULGAR)
    parche = f'<circle cx="{n(raiz[0])}" cy="{n(raiz[1])}" r="{n(PULGAR * 0.62)}" fill="{piel}"/>'
    return lt.svg() + parche


def _forma(forma: str, piel: str, c: float) -> str:
    """La mano entera en su marco (muñeca en 0,0; dedos hacia +x; pulgar arriba)."""
    lp = _Lapiz(piel, c)
    cerrada = forma in ("puno", "senala", "agarra", "pinza", "lapiz")
    lp.palma(cerrada)
    pulgar = ""
    if forma == "abierta":
        lp.dedo([(38, -13), (52, -16), (64, -18)])
        lp.dedo([(39, -4.5), (55, -5.5), (69, -6.5)])
        lp.dedo([(39, 4.5), (54, 5), (67, 5.5)])
        lp.dedo([(37, 13), (49, 15.5), (59, 18)], ANCHO * 0.88)
        lp.dedo([RAIZ_PULGAR, (14, -24), (24, -34)], PULGAR)          # el pulgar separado, en el mismo trazo
    elif forma == "relajada":
        for y in (-13, -4.5, 4.5, 13):
            lp.dedo([(38, y), (50, y * 1.05 + 2), (55, y * 1.05 + 10)], ANCHO * (0.9 if y > 10 else 1))
        lp.dedo([RAIZ_PULGAR, (18, -20), (28, -22)], PULGAR)
    elif forma == "senala":
        # los tres doblados contra la palma: solo asoman sus nudillos
        for y in (-3.5, 5, 13):
            lp.dedo([(38, y), (45, y + 1.5)], ANCHO * (0.9 if y > 10 else 1), una=False, arruga=False)
            lp.nudillo(47, y + 1.5)
        lp.dedo([(38, -12.5), (62, -13), (90, -13)])                     # el índice, largo y recto
        pulgar = _pulgar(piel, c, (22, -6), (38, 2))                      # de costado, sobre el mayor
    elif forma == "puno":
        # los cuatro dedos enrollados, apilados de frente (como al agarrar, pero sin nada adentro): cada uno con su
        # nudillo marcado donde dobla y la punta que vuelve hacia la palma
        ld = _Lapiz(piel, c)       # su propia capa encima de la palma: se ve cada dedo con su contorno
        for y in (-13.5, -4.5, 4.5, 13.5):
            ld.dedo([(24, y), (44, y), (50, y + 3), (48, y + 6)], ANCHO * (0.92 if y > 10 else 1.02), una=False,
                    arruga=False)
            ld.nudillo(26, y)            # el nudillo donde el dedo dobla
            ld.nudillo(45, y + 1)        # y la segunda articulación, adelante
        pulgar = ld.svg() + _pulgar(piel, c, (20, -18), (40, -10))        # cruzado delante del índice y el mayor
    elif forma == "agarra":
        pass       # detrás del objeto, solo la palma: los dedos y el pulgar van por delante (`encima`)
    elif forma == "pinza":
        # sostener un papel: lo de ATRÁS del papel son los dedos; la palma y el pulgar van adelante (`encima`, en el
        # marco de la mano, en la muñeca)
        lp = _Lapiz(piel, c)
        for y in (-13, -4.5, 4.5, 13):
            lp.dedo([(36, y), (52, y), (62, y + 2)], ANCHO * (0.9 if y > 10 else 1))
    elif forma == "lapiz":
        return _escribiendo(piel, c)
    else:
        return _forma("relajada", piel, c)
    return lp.svg() + pulgar


def _escribiendo(piel: str, c: float) -> str:
    """La mano que escribe (marco de la mano: los dedos hacia +x; la mano va inclinada hacia el papel). La lapicera va
    INCLUIDA: agarrada cerca de la punta en pinza (yemas del pulgar, el índice y el mayor), inclinada y apoyada sobre
    el nudillo del índice; el anular y el meñique doblados abajo, apoyados en el papel."""
    lp = _Lapiz(piel, c)
    lp.palma(True)
    for x0, y0 in ((40, 6), (37, 13)):                         # anular y meñique doblados, hacia el papel
        lp.dedo([(x0, y0), (x0 + 7, y0 + 5), (x0 + 3, y0 + 12)], ANCHO * 0.9, una=False)
    lp.dedo([(40, -3), (51, 2), (58, 9)])                       # el mayor: la lapicera apoya en su yema
    atras = lp.svg()
    lt = _Lapiz(piel, c)                                        # el pulgar, del otro lado de la lapicera
    lt.dedo([RAIZ_PULGAR, (26, -6), (52, 6)], PULGAR)
    pulgar = lt.svg()
    # la lapicera: de arriba atrás (pasa sobre el nudillo del índice) a la punta, cerca de las yemas
    a, b = (14, -30), (72, 15)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    largo = math.hypot(b[0] - a[0], b[1] - a[1])
    lapicera = g(f'<rect x="0" y="-4" width="{n(largo - 9)}" height="8" rx="3" fill="#1f2a44" stroke="{P.CONTORNO}" '
                 f'stroke-width="{n(c * 0.7)}"/><path d="M{n(largo - 9)} -4 L{n(largo)} 0 L{n(largo - 9)} 4 Z" '
                 f'fill="#d9b34a" stroke="{P.CONTORNO}" stroke-width="{n(c * 0.6)}" stroke-linejoin="round"/>'
                 f'<rect x="2" y="-4" width="10" height="8" fill="#c9a43a"/>', a[0], a[1], rot=ang)
    li = _Lapiz(piel, c)                                        # el índice por encima, con la yema sobre la lapicera
    li.dedo([(38, -13), (50, -5), (60, 4)])
    return atras + pulgar + lapicera + li.svg()


def mano(x: float, y: float, ang: float, forma: str = "relajada", piel: str = "#f2c29b", escala: float = 1.0,
         espejo: bool = False) -> str:
    """La mano en la muñeca (x, y) apuntando a `ang` grados (la dirección del antebrazo). El pulgar queda del lado de
    arriba de la pantalla (o del de abajo, con `espejo`)."""
    forma = forma if forma in FORMAS else "relajada"
    abajo = math.cos(math.radians(ang)) < 0
    flip = -1 if (abajo != espejo) else 1
    return g(g(_forma(forma, piel, TRAZO_PX / max(0.2, escala)), escala=escala, escala_y=escala * flip), x, y, rot=ang)


def encima(tipo: str = "agarra", piel: str = "#f2c29b", lado: int = 1, escala: float = 1.0) -> str:
    """Lo que va DELANTE del objeto agarrado, centrado en el objeto. agarra: los cuatro dedos que lo envuelven (se ve
    el dorso de cada uno con su nudillo) y el pulgar que cruza por delante pasando sobre el índice; pinza: el pulgar
    sobre el papel. `lado` -1 = mirando a la izquierda. `escala`: la que se le aplica afuera (el contorno no cambia)."""
    c = TRAZO_PX / max(0.2, escala)
    lp = _Lapiz(piel, c)
    if tipo == "pinza":
        # en el marco de la MANO (va en la muñeca, girada como el antebrazo): la palma y el pulgar que aprieta el papel
        lp.palma(True)
        cuerpo = lp.svg() + _pulgar(piel, c, (24, -14), (46, -9))
    else:
        for y, largo in ((-15, 25), (-5, 27), (5, 25), (14.5, 20)):
            x0 = -largo / 2
            lp.dedo([(x0, y), (x0 + largo * 0.55, y - 0.5), (x0 + largo, y + 2.5)],
                    ANCHO * (0.88 if y > 10 else 1), una=False)
        for y in (-15, -5, 5, 14.5):
            lp.nudillo(-4, y)
        lt = _Lapiz(piel, c)       # el pulgar: viene de atrás (de la palma) y cruza por delante sobre el índice
        lt.dedo([(-20, -24), (-6, -21), (8, -17)], PULGAR)
        cuerpo = lp.svg() + lt.svg()
    return cuerpo if lado >= 0 else g(cuerpo, escala=-1, escala_y=1)


def dedos_encima(piel: str = "#f2c29b", lado: int = 1, tipo: str = "agarra") -> str:
    """Compatibilidad: lo que la mano pone delante de lo agarrado (prop `dedos`)."""
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
            + g(f'<rect x="{n(-ancho * 0.3)}" y="{n(-ancho * 0.58)}" width="{n(ancho * 0.6)}" height="{n(ancho * 1.16)}" '
                f'rx="{n(ancho * 0.14)}" fill="#f4f1ea" stroke="{P.CONTORNO}" stroke-width="{n(TRAZO_PX)}"/>', px, py,
                rot=ang))
