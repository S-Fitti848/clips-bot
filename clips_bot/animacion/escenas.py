"""Fondos (1080x1920, estáticos: se cachean como imagen) y props sueltos.

Los fondos son deterministas (misma `semilla` = mismo dibujo), así el caché sirve entre cuadros y
entre corridas. Los props se dibujan centrados en (0, 0), de ~200 px, y se mueven con keyframes.
"""
from __future__ import annotations

import math
import random

from . import paleta as P
from .svg import camino, circulo, elipse, g, n, rect, texto_con_borde, trazo

W, H = P.ANCHO, P.ALTO


# ---- piezas -------------------------------------------------------------------

def nube(escala: float = 1.0) -> str:
    """Nube centrada en (0, 0), ~260 px de ancho a escala 1."""
    d = ("M-120 40 Q-150 40 -150 10 Q-150 -24 -112 -26 Q-104 -78 -48 -74 Q-20 -112 30 -90 "
         "Q78 -102 92 -52 Q146 -54 148 -6 Q150 40 110 40 Z")
    return g(camino(d, P.NUBE, ancho=P.TRAZO_FINO + 2), escala=escala)


def _colinas(y: float, color: str, amp: float, semilla: int) -> str:
    rnd = random.Random(semilla)
    pts = [(x, y - rnd.uniform(0, amp)) for x in range(-100, W + 200, 220)]
    d = f"M-100 {H + 20} L{pts[0][0]} {n(pts[0][1])} "
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d += f"Q{n((x0 + x1) / 2)} {n(min(y0, y1) - amp * 0.6)} {x1} {n(y1)} "
    d += f"L{W + 200} {H + 20} Z"
    return camino(d, color)


# ---- fondos -------------------------------------------------------------------

def fondo_cielo(semilla: int = 1) -> str:
    rnd = random.Random(semilla)
    p = [rect(0, 0, W, H, P.CIELO, borde=False),
         rect(0, H * 0.55, W, H * 0.45, P.CIELO_BAJO, borde=False),
         circulo(840, 300, 110, P.AMARILLO)]
    for i in range(5):
        p.append(g(nube(), rnd.uniform(80, W - 80), 180 + i * 230 + rnd.uniform(-40, 40),
                   escala=rnd.uniform(0.7, 1.3)))
    p.append(_colinas(H * 0.74, "#9ad97f", 120, semilla + 1))
    p.append(_colinas(H * 0.84, P.VERDE, 90, semilla + 2))
    return "".join(p)


def fondo_ciudad(semilla: int = 2) -> str:
    rnd = random.Random(semilla)
    p = [rect(0, 0, W, H, "#ffd9a8", borde=False),
         rect(0, 0, W, H * 0.4, "#ffb98a", borde=False),
         circulo(270, 520, 130, "#ffe08a", borde=False)]
    # dos filas de edificios: los de atrás más claros y sin ventanas detalladas
    for fila, (color, base, alto_min, alto_max) in enumerate(
            [(P.CIUDAD_LEJOS, H * 0.72, 380, 820), (P.CIUDAD_CERCA, H * 0.8, 300, 700)]):
        x = -40
        while x < W + 40:
            w = rnd.uniform(140, 230)
            h = rnd.uniform(alto_min, alto_max)
            p.append(rect(x, base - h, w, h + 40, color, r=6))
            if fila == 1:
                for vy in range(int(base - h + 40), int(base - 60), 80):
                    for vx in range(int(x + 24), int(x + w - 40), 56):
                        if rnd.random() < 0.7:
                            p.append(rect(vx, vy, 30, 42, P.VENTANA, r=4, ancho=P.TRAZO_FINO))
            x += w + rnd.uniform(-10, 18)
    p.append(rect(-20, H * 0.8, W + 40, H * 0.2 + 20, GRIS_CALLE))
    for x in range(40, W, 220):
        p.append(rect(x, H * 0.9, 120, 18, P.BLANCO, borde=False))
    return "".join(p)


GRIS_CALLE = "#5d6270"


def fondo_oficina(semilla: int = 3) -> str:
    p = [rect(0, 0, W, H, P.PARED, borde=False),
         rect(0, H * 0.72, W, H * 0.28, P.PISO, borde=False),
         f'<path d="M0 {n(H * 0.72)} L{W} {n(H * 0.72)}" {trazo()}/>']
    # ventana con cielo
    p.append(rect(560, 260, 400, 480, P.CIELO, r=8))
    p.append(g(nube(), 700, 400, escala=0.6))
    p.append(f'<path d="M760 260 L760 740 M560 500 L960 500" {trazo()}/>')
    # cuadro en la pared
    p.append(rect(120, 330, 280, 210, P.BLANCO, r=6))
    p.append(camino("M150 510 L230 400 L290 470 L330 430 L380 510 Z", P.VERDE,
                    ancho=P.TRAZO_FINO))
    p.append(circulo(330, 380, 22, P.AMARILLO, ancho=P.TRAZO_FINO))
    # escritorio
    p.append(rect(80, H * 0.62, 620, 46, P.MADERA, r=8))
    p.append(rect(110, H * 0.62 + 40, 40, 280, P.MADERA))
    p.append(rect(630, H * 0.62 + 40, 40, 280, P.MADERA))
    p.append(rect(260, H * 0.62 - 190, 250, 170, P.GRIS_OSCURO, r=10))   # monitor
    p.append(rect(278, H * 0.62 - 172, 214, 134, "#9fe3ff", r=4, ancho=P.TRAZO_FINO))
    p.append(rect(365, H * 0.62 - 22, 40, 24, P.GRIS_OSCURO))
    # planta
    p.append(rect(860, H * 0.66, 120, 130, P.NARANJA, r=10))
    for ang in (-40, -15, 10, 35):
        p.append(g(camino("M0 0 Q-30 -90 0 -170 Q30 -90 0 0 Z", P.VERDE, ancho=P.TRAZO_FINO),
                   920, H * 0.66, rot=ang))
    return "".join(p)


def fondo_globo(semilla: int = 4) -> str:
    rnd = random.Random(semilla)
    p = [rect(0, 0, W, H, P.NOCHE, borde=False)]
    for _ in range(90):
        p.append(circulo(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(2, 5), P.BLANCO,
                         borde=False))
    cx, cy, r = W / 2, H * 0.42, 400
    p.append(circulo(cx, cy, r + 28, "#2b3a80", borde=False))   # halo
    p.append(f'<clipPath id="globo"><circle cx="{n(cx)}" cy="{n(cy)}" r="{r}"/></clipPath>')
    tierra = [circulo(cx, cy, r, P.OCEANO, borde=False)]
    for _ in range(6):   # continentes: manchas con forma de blob
        bx, by = cx + rnd.uniform(-r, r), cy + rnd.uniform(-r, r)
        pts = []
        for i in range(9):
            a = 2 * math.pi * i / 9
            rr = rnd.uniform(60, 150)
            pts.append((bx + math.cos(a) * rr, by + math.sin(a) * rr))
        d = f"M{n(pts[0][0])} {n(pts[0][1])} "
        for i in range(len(pts)):
            p0, p1 = pts[i], pts[(i + 1) % len(pts)]
            d += f"Q{n(p0[0])} {n(p0[1])} {n((p0[0] + p1[0]) / 2)} {n((p0[1] + p1[1]) / 2)} "
        tierra.append(camino(d + "Z", P.TIERRA, ancho=P.TRAZO_FINO))
    for k in (-0.6, -0.2, 0.2, 0.6):   # meridianos y paralelos
        tierra.append(f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(abs(k) * r)}" ry="{r}" '
                      f'fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="4"/>')
        tierra.append(f'<path d="M{n(cx - r)} {n(cy + k * r)} L{n(cx + r)} {n(cy + k * r)}" '
                      f'stroke="#ffffff" stroke-opacity="0.35" stroke-width="4"/>')
    p.append(f'<g clip-path="url(#globo)">{"".join(tierra)}</g>')
    p.append(circulo(cx, cy, r, "none", ancho=P.TRAZO + 3))
    return "".join(p)


FONDOS = {"cielo": fondo_cielo, "ciudad": fondo_ciudad, "oficina": fondo_oficina,
          "globo": fondo_globo, "mapa": fondo_globo}


def fondo(tipo: str, semilla: int | None = None) -> str:
    f = FONDOS.get(tipo)
    if f is None:
        raise ValueError(f"Fondo desconocido: {tipo!r} (hay {', '.join(sorted(FONDOS))})")
    return f() if semilla is None else f(semilla)


# ---- props --------------------------------------------------------------------

def prop_cartel(texto: str = "¡OJO!", color: str = P.AMARILLO, **_) -> str:
    tam = 64 if len(texto) <= 8 else 48
    return (rect(-14, 0, 28, 230, P.MADERA)
            + rect(-190, -140, 380, 170, color, r=14)
            + texto_con_borde(texto, 0, -36, tam, color=P.CONTORNO, borde=P.BLANCO,
                              ancho_borde=6))


def prop_flecha(color: str = P.ROJO, **_) -> str:
    return camino("M-150 -36 L40 -36 L40 -90 L160 0 L40 90 L40 36 L-150 36 Z", color)


def prop_pregunta(color: str = P.AMARILLO, **_) -> str:
    return texto_con_borde("?", 0, 90, 260, color=color, ancho_borde=22)


def prop_exclamacion(color: str = P.ROJO, **_) -> str:
    return texto_con_borde("!", 0, 90, 260, color=color, ancho_borde=22)


def prop_moneda(color: str = P.AMARILLO, **_) -> str:
    return (circulo(0, 0, 110, "#e8a920")
            + circulo(0, 0, 84, color, ancho=P.TRAZO_FINO)
            + texto_con_borde("$", 0, 44, 120, color="#e8a920", borde=P.CONTORNO,
                              ancho_borde=10))


def prop_lamparita(color: str = P.AMARILLO, encendida: bool = True, **_) -> str:
    rayos = ""
    if encendida:
        rayos = "".join(g(f'<path d="M0 -150 L0 -200" {trazo(ancho=12)}/>', 0, -20, rot=a)
                        for a in (-70, -35, 0, 35, 70))
    return (rayos
            + camino("M-80 -20 Q-80 -130 0 -130 Q80 -130 80 -20 Q80 30 40 60 L40 90 L-40 90 "
                     "L-40 60 Q-80 30 -80 -20 Z", color if encendida else P.BLANCO)
            + rect(-44, 90, 88, 50, P.GRIS, r=8)
            + f'<path d="M-44 108 L44 108 M-44 124 L44 124" {trazo(ancho=P.TRAZO_FINO)}/>')


def prop_nube(**_) -> str:
    return nube()


PROPS = {"cartel": prop_cartel, "flecha": prop_flecha, "pregunta": prop_pregunta,
         "exclamacion": prop_exclamacion, "moneda": prop_moneda, "lamparita": prop_lamparita,
         "nube": prop_nube}


def prop(nombre: str, **params) -> str:
    f = PROPS.get(nombre)
    if f is None:
        raise ValueError(f"Prop desconocido: {nombre!r} (hay {', '.join(sorted(PROPS))})")
    return f(**params)
