"""Fondos (1080x1920, estáticos: se cachean como imagen) y props sueltos.

Los fondos son deterministas (misma `semilla` = mismo dibujo), así el caché sirve entre cuadros y
entre corridas. Los props se dibujan centrados en (0, 0), de ~200 px, y se mueven con keyframes.
"""
from __future__ import annotations

import math
import random
import re

from . import paleta as P
from .svg import aclarar, camino, circulo, elipse, g, linea_gruesa, mezcla, n, oscurecer, rect, texto_con_borde, trazo

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


def _fondo_ciudad_base(semilla: int = 2) -> str:
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
    decada, _ = epoca_de(semilla)
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
    if decada and decada < 199:   # máquina de escribir y teléfono de disco
        p.append(rect(270, H * 0.62 - 90, 230, 90, "#3d4250", r=14))
        p.append(rect(300, H * 0.62 - 150, 170, 70, P.BLANCO, ancho=P.TRAZO_FINO))
        for k in range(5):
            p.append(circulo(300 + k * 40, H * 0.62 - 30, 12, "#cfd3da", ancho=3))
        p.append(rect(560, H * 0.62 - 60, 110, 60, "#2b2b33", r=14) + circulo(615, H * 0.62 - 34, 20, "#ddd", ancho=3))
    else:
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


def _fondo_fabrica_base(semilla: int = 5) -> str:
    """Una fábrica genérica por dentro: cinta transportadora con cajas, engranajes en la pared,
    caños y chimeneas en la ventana (canal de marcas, 2026-11-14)."""
    rnd = random.Random(semilla)
    p = [rect(0, 0, W, H, "#d9dde6", borde=False),
         rect(0, H * 0.7, W, H * 0.3, "#8a8f9c", borde=False),
         f'<path d="M0 {n(H * 0.7)} L{W} {n(H * 0.7)}" {trazo()}/>']
    # ventanal con chimeneas y humo
    p.append(rect(80, 200, 920, 420, "#ffcf9e", r=8))
    for i, x in enumerate((200, 420, 700)):
        alto = 220 + 60 * (i % 2)
        p.append(rect(x, 620 - alto, 70, alto, P.GRIS_OSCURO))
        p.append(g(nube(), x + 35 + rnd.uniform(-20, 20), 620 - alto - 70, escala=0.45))
    p.append(f'<path d="M80 410 L1000 410 M540 200 L540 620" {trazo()}/>')
    # caños y engranajes
    p.append(rect(-20, 700, W + 40, 34, P.ROJO))
    for x, r in ((170, 90), (330, 60), (880, 110)):
        p.append(g(prop_engranaje(color=P.GRIS), x, 900, escala=r / 100))
    # cinta transportadora con cajas
    y = H * 0.66
    p.append(rect(-20, y, W + 40, 60, P.GRIS_OSCURO, r=30))
    for x in range(30, W, 120):
        p.append(circulo(x, y + 30, 18, P.GRIS, ancho=P.TRAZO_FINO))
    for x in range(60, W, 300):
        p.append(rect(x, y - 130, 150, 130, P.MADERA, r=6))
        p.append(f'<path d="M{x} {n(y - 95)} L{x + 150} {n(y - 95)}" {trazo(ancho=P.TRAZO_FINO)}/>')
    return "".join(p)


def _fondo_tienda_base(semilla: int = 6) -> str:
    """Góndolas de un almacén/supermercado con productos genéricos de colores (sin marcas)."""
    rnd = random.Random(semilla)
    colores = [P.ROJO, P.AZUL, P.VERDE, P.AMARILLO, P.NARANJA, P.VIOLETA, P.ROSA, P.TURQUESA]
    p = [rect(0, 0, W, H, "#fff3dc", borde=False),
         rect(0, H * 0.74, W, H * 0.26, "#e9c9a0", borde=False),
         f'<path d="M0 {n(H * 0.74)} L{W} {n(H * 0.74)}" {trazo()}/>']
    # baldosas
    for x in range(0, W, 180):
        p.append(f'<path d="M{x} {n(H * 0.74)} L{x - 120} {H}" stroke="#c9a77c" stroke-width="5"/>')
    # dos estanterías con 4 estantes
    for x0 in (40, 560):
        p.append(rect(x0, 260, 480, 1130, "#b98a5e", r=10))
        for k in range(4):
            ye = 300 + k * 270
            p.append(rect(x0 + 20, ye + 200, 440, 26, P.MADERA, r=4))
            x = x0 + 34
            while x < x0 + 430:
                w, h = rnd.choice([(60, 150), (80, 110), (50, 180), (90, 90)])
                if x + w > x0 + 455:
                    break
                c = rnd.choice(colores)
                if h > 140:   # botella
                    p.append(camino(f"M{x + w * 0.35} {ye + 200 - h} L{x + w * 0.65} {ye + 200 - h} "
                                    f"L{x + w * 0.65} {ye + 230 - h} Q{x + w} {ye + 250 - h} {x + w} "
                                    f"{ye + 280 - h} L{x + w} {ye + 200} L{x} {ye + 200} L{x} {ye + 280 - h} "
                                    f"Q{x} {ye + 250 - h} {x + w * 0.35} {ye + 230 - h} Z", c,
                                    ancho=P.TRAZO_FINO))
                else:
                    p.append(rect(x, ye + 200 - h, w, h, c, r=6, ancho=P.TRAZO_FINO))
                    p.append(rect(x + 8, ye + 200 - h * 0.65, w - 16, h * 0.3, P.BLANCO, r=3,
                                  borde=False))
                x += w + 14
    # cartel de oferta genérico
    p.append(g(prop_cartel("", P.AMARILLO), 860, 150, escala=0.7))     # sin letras: en el espejado salían al revés
    return "".join(p)


# ---- decoración de época en la calle, la fábrica y la tienda (Santi, 2026-11-14) -------------------

def _rango(decada: int) -> str:
    """"antes" (antes de 1950), "medio" (50-70), "ochentas" (80-90) o "hoy"."""
    if not decada or decada >= 200:
        return "hoy"
    if decada < 195:
        return "antes"
    return "medio" if decada < 198 else "ochentas"


def auto_epoca(rango: str, color: str) -> str:
    """Un auto estacionado de la época, de costado, centrado en (0, 0) y apoyado en y = 60."""
    ruedas = circulo(-110, 40, 36, "#2b2b33") + circulo(-110, 40, 14, P.GRIS, ancho=4) + \
        circulo(110, 40, 36, "#2b2b33") + circulo(110, 40, 14, P.GRIS, ancho=4)
    if rango == "antes":     # alto y cuadrado, con estribos y guardabarros
        return (camino("M-170 30 L-170 -40 L-90 -40 L-80 -140 L80 -140 L90 -40 L170 -40 L170 30 Z", color)
                + rect(-60, -124, 50, 70, "#9fe3ff", ancho=4) + rect(10, -124, 50, 70, "#9fe3ff", ancho=4)
                + rect(-190, 20, 380, 14, "#2b2b33", r=6, ancho=3) + ruedas)
    if rango == "medio":     # redondeado con aletas atrás
        return (camino("M-200 30 Q-210 -30 -150 -40 L-90 -44 Q-60 -110 20 -110 Q90 -110 110 -44 L180 -40 "
                       "L210 -70 L210 30 Z", color)
                + camino("M-70 -46 Q-50 -96 0 -96 L0 -46 Z", "#9fe3ff", ancho=4)
                + camino("M10 -46 L10 -96 Q70 -96 92 -46 Z", "#9fe3ff", ancho=4)
                + rect(-200, 10, 410, 12, P.GRIS, r=6, ancho=3) + ruedas)
    if rango == "ochentas":  # cuadrado y bajo
        return (camino("M-200 30 L-200 -30 L-110 -40 L-70 -100 L90 -100 L130 -40 L200 -30 L200 30 Z", color)
                + rect(-60, -92, 70, 46, "#9fe3ff", ancho=4) + rect(20, -92, 90, 46, "#9fe3ff", ancho=4) + ruedas)
    return prop_auto(color=color)    # hoy


def farol(rango: str) -> str:
    """Un farol de la época, con la base en (0, 0)."""
    if rango == "antes":     # farol a gas, negro y labrado
        return (rect(-10, -520, 20, 520, "#2b2b33", ancho=4) + rect(-30, -40, 60, 40, "#2b2b33", r=6, ancho=4)
                + camino("M-40 -520 L40 -520 L28 -600 L-28 -600 Z", "#fff3b0", ancho=5)
                + camino("M-46 -600 L46 -600 L0 -640 Z", "#2b2b33", ancho=4))
    if rango in ("medio", "ochentas"):   # alumbrado curvo
        return (rect(-10, -600, 20, 600, P.GRIS_OSCURO, ancho=4)
                + camino("M0 -600 Q0 -660 80 -660 L120 -660", ancho=16) + elipse(120, -650, 40, 14, "#fff3b0", ancho=4))
    return (rect(-8, -620, 16, 620, P.GRIS, ancho=4) + rect(-8, -640, 120, 18, P.GRIS, r=6, ancho=4)
            + rect(60, -626, 50, 10, "#e6f7ff", borde=False))   # LED


def fondo_ciudad(semilla: int = 2) -> str:
    """La calle de la época: un auto estacionado, un farol y la vidriera de un negocio según la década
    (y los edificios de siempre atrás)."""
    decada, var = epoca_de(semilla)
    rango = _rango(decada)
    p = [_fondo_ciudad_base(semilla)]
    # vidriera de un negocio (toldo a rayas y vidrio), abajo a la izquierda, contra la vereda
    toldo = {"antes": "#8e2c2c", "medio": "#2a9d8f", "ochentas": "#ff99c8", "hoy": "#3a86ff"}[rango]
    p.append(rect(40, 1180, 380, 290, "#f5e6c8" if rango == "antes" else "#e9eef3", r=6))
    p.append(rect(70, 1240, 320, 200, "#bfe9ff", ancho=5))
    for k in range(6):
        p.append(camino(f"M{40 + k * 64} 1150 L{104 + k * 64} 1150 L{98 + k * 64} 1200 L{46 + k * 64} 1200 Z",
                        toldo if k % 2 == 0 else P.BLANCO, ancho=4))
    p.append(g(farol(rango), 980, 1520))
    colores = (P.ROJO, P.AZUL, P.VERDE, P.AMARILLO)
    p.append(g(auto_epoca(rango, colores[var % 4]), 640, 1500, escala=0.9))
    return "".join(p)


def fondo_fabrica(semilla: int = 5) -> str:
    """La fábrica de la época: caldera a vapor antes de 1950, reloj para fichar y palancas en los
    50-80, brazo robot y pantallas hoy."""
    decada, _ = epoca_de(semilla)
    rango = _rango(decada)
    p = [_fondo_fabrica_base(semilla)]
    if rango == "antes":
        p.append(rect(770, 760, 240, 380, "#8d6e63", r=60) + circulo(890, 860, 50, "#e9d8a6", ancho=5)
                 + f'<path d="M890 860 L920 830" {trazo(ancho=6)}/>' + rect(840, 1140, 100, 40, "#5d4037"))
    elif rango in ("medio", "ochentas"):
        p.append(rect(800, 780, 180, 240, P.GRIS, r=10) + circulo(890, 850, 50, P.BLANCO, ancho=5)
                 + f'<path d="M890 850 L890 815 M890 850 L915 860" {trazo(ancho=6)}/>' + rect(840, 930, 100, 60, "#e9d8a6", ancho=4))
        for k, c in enumerate((P.ROJO, P.VERDE, P.AMARILLO)):
            p.append(rect(800 + k * 60, 1060, 22, 90, P.GRIS_OSCURO, ancho=4) + circulo(811 + k * 60, 1060, 18, c, ancho=4))
    else:
        p.append(rect(780, 760, 240, 160, "#2b2b33", r=10) + rect(800, 780, 200, 120, "#3fd1a8", ancho=4)
                 + linea_gruesa([(900, 1180), (860, 1040), (960, 980)], P.NARANJA, 36)
                 + rect(840, 1160, 120, 40, P.GRIS_OSCURO, r=6))
    return "".join(p)


def fondo_tienda(semilla: int = 6) -> str:
    """La tienda de la época: caja registradora de bronce y frascos antes de 1950, registradora
    mecánica en los 50-80, pantalla y lector de código de barras hoy."""
    decada, _ = epoca_de(semilla)
    rango = _rango(decada)
    p = [_fondo_tienda_base(semilla)]
    p.append(rect(40, 1260, 300, 160, "#8a5a2b" if rango != "hoy" else "#cfd8dc", r=6))       # mostrador
    if rango == "antes":
        p.append(camino("M100 1260 L110 1170 L250 1170 L270 1260 Z", "#c9a24a")
                 + rect(130, 1150, 110, 30, "#e9d8a6", ancho=4))
        for k in range(3):
            p.append(rect(60 + k * 30, 1200, 24, 60, "#bfe9ff", r=6, ancho=4))
    elif rango in ("medio", "ochentas"):
        p.append(rect(110, 1170, 160, 90, P.GRIS, r=8) + rect(130, 1140, 120, 34, "#2b2b33", ancho=4)
                 + "".join(circulo(130 + k * 30, 1210, 9, P.BLANCO, ancho=3) for k in range(5)))
    else:
        p.append(rect(120, 1140, 140, 100, "#2b2b33", r=8) + rect(132, 1152, 116, 76, "#3fd1a8", ancho=4)
                 + rect(60, 1210, 50, 30, P.ROJO, r=6, ancho=4))
    return "".join(p)


def fondo_escenario(semilla: int = 7) -> str:
    """Un escenario/estudio de TV: telón, reflectores y piso de tablas (para slogans y publicidades)."""
    p = [rect(0, 0, W, H, "#3b1f4a", borde=False)]
    for x in range(0, W, 90):   # telón con pliegues
        p.append(rect(x, 0, 90, H * 0.72, "#b3263a" if (x // 90) % 2 else "#c9384b", borde=False))
    p.append(camino(f"M0 0 L{W} 0 L{W} 120 Q{W * 0.75} 200 {W / 2} 140 Q{W * 0.25} 200 0 120 Z",
                    "#8e1b2c"))
    for x in (180, 900):   # haces de luz
        p.append(f'<path d="M{x} 0 L{x - 260} {n(H * 0.74)} L{x + 260} {n(H * 0.74)} Z" '
                 f'fill="#fff3b0" opacity="0.18"/>')
        p.append(circulo(x, 40, 50, P.GRIS_OSCURO))
    p.append(rect(-20, H * 0.72, W + 40, H * 0.28 + 20, "#a8714a"))
    for y in range(int(H * 0.76), H, 70):
        p.append(f'<path d="M0 {y} L{W} {y}" stroke="#8a5a38" stroke-width="5"/>')
    return "".join(p)


def epoca_de(semilla: int) -> tuple[int, int]:
    """(década, variante) de una semilla: década*100 + variante (19601 = los 60, variante 1); las
    semillas chicas de antes (1, 2, 8…) son el presente."""
    return (semilla // 100, semilla % 100) if semilla >= 1000 else (0, semilla)


def _libros(x: float, y: float, ancho: float, rnd) -> str:
    out, cx = [], x
    colores = [P.ROJO, P.AZUL, P.VERDE, P.AMARILLO, P.VIOLETA, P.NARANJA, P.TURQUESA]
    while cx < x + ancho - 18:
        w, h = rnd.choice([(18, 70), (22, 80), (16, 62), (26, 74)])
        out.append(rect(cx, y - h, w, h, rnd.choice(colores), r=2, ancho=4))
        cx += w + 2
    return "".join(out)


def _ventana_cortinas(x: float, y: float, w: float, h: float, cortina: str, rnd) -> str:
    out = [rect(x, y, w, h, "#bfe9ff", r=6), g(nube(), x + w * 0.35, y + h * 0.3, escala=0.4),
           f'<path d="M{n(x + w / 2)} {n(y)} L{n(x + w / 2)} {n(y + h)} M{n(x)} {n(y + h / 2)} '
           f'L{n(x + w)} {n(y + h / 2)}" {trazo(ancho=8)}/>',
           rect(x - 30, y - 30, w + 60, 18, P.MADERA, r=6, ancho=4)]
    for lado in (0, 1):   # cortinas recogidas a los costados, con pliegues
        cx = x - 26 if lado == 0 else x + w - 50
        out.append(camino(f"M{n(cx)} {n(y - 14)} L{n(cx + 76)} {n(y - 14)} Q{n(cx + 40)} {n(y + h * 0.5)} "
                          f"{n(cx + 70)} {n(y + h + 30)} L{n(cx + 6)} {n(y + h + 30)} Q{n(cx - 6)} {n(y + h * 0.5)} "
                          f"{n(cx)} {n(y - 14)} Z", cortina, ancho=P.TRAZO_FINO))
        for k in (18, 38, 58):
            out.append(f'<path d="M{n(cx + k)} {n(y)} Q{n(cx + k - 6)} {n(y + h * 0.5)} {n(cx + k + 4)} {n(y + h + 20)}" '
                       f'fill="none" stroke="{P.CONTORNO}" stroke-opacity="0.2" stroke-width="4"/>')
    return "".join(out)


ESTILOS_CASA = {
    # década: pared, dibujo de la pared, sillón, alfombra (afuera, adentro), cortina
    0: ("#eef1f4", "#e3e8ee", "#7b8fa6", ("#9aa5b1", "#d5dbe1"), "#c9d6e3"),
    190: ("#d8c9a3", "#c9b88d", "#8e2c2c", ("#8e2c2c", "#d9a441"), "#7a1f2b"),
    195: ("#f7d9a0", "#e8b96a", "#2a9d8f", ("#e76f51", "#f4a261"), "#e76f51"),
    196: ("#f2b25c", "#c9762e", "#e9c46a", ("#bc6c25", "#dda15e"), "#bc4749"),
    197: ("#c99a5b", "#8a5a2b", "#a3542b", ("#6b4226", "#d4a373"), "#606c38"),
    198: ("#f6d6e6", "#9fd8d0", "#7fc8f8", ("#ff99c8", "#fcf6bd"), "#a9def9"),
    199: ("#e4ecd5", "#c3d7a4", "#5e8c61", ("#8fa38a", "#dfe8cc"), "#5e8c61"),
}


def _estilo_casa(decada: int):
    if not decada or decada >= 200:
        return ESTILOS_CASA[0]
    if decada < 195:
        return ESTILOS_CASA[190]
    return ESTILOS_CASA.get(decada, ESTILOS_CASA[196])


def fondo_casa(semilla: int = 8) -> str:
    """El living de una casa, con la DÉCADA de la escena (2026-11-14, "la casa es muy genérica"): papel
    de pared, sillón, alfombra, cortinas y objetos de la época (radio y teléfono de disco en los 60,
    gramófono antes de 1950, equipo de música en los 80, plantas y estantes en el presente), biblioteca
    con libros y juguetes. La variante cambia la decoración (y en las impares, `fondo` la espeja). Sin
    lámpara ni tele: son props, así se pueden romper."""
    import random as _random

    decada, var = epoca_de(semilla)
    rnd = _random.Random(semilla)
    pared, dibujo, sillon, (alf1, alf2), cortina = _estilo_casa(decada)
    p = [rect(0, 0, W, H, pared, borde=False)]
    if decada and decada < 195:          # papel de flores chiquitas + boiserie de madera abajo
        for y in range(40, int(H * 0.5), 110):
            for x in range(40 + (y // 110 % 2) * 55, W, 110):
                p.append(circulo(x, y, 9, dibujo, borde=False))
        p.append(rect(0, H * 0.5, W, H * 0.22, "#8a6a45", borde=False))
        for x in range(30, W, 170):
            p.append(rect(x, H * 0.52, 130, H * 0.17, "#9c7b52", r=6, ancho=4))
    elif decada and decada < 198:        # años 50-70: círculos grandes y rombos de época
        for y in range(70, int(H * 0.7), 170):
            for x in range(60 + (y // 170 % 2) * 85, W, 170):
                p.append(circulo(x, y, 34, dibujo, borde=False) + circulo(x, y, 16, pared, borde=False))
    elif decada and decada < 200:        # 80-90: zigzag pastel
        for y in range(80, int(H * 0.7), 140):
            d = "M0 {y} ".format(y=y) + " ".join(f"L{x} {y + (28 if (x // 60) % 2 else 0)}" for x in range(0, W + 60, 60))
            p.append(f'<path d="{d}" fill="none" stroke="{dibujo}" stroke-width="12"/>')
    else:                                 # presente: pared lisa con una guarda suave
        p.append(rect(0, H * 0.36, W, 14, dibujo, borde=False))
    p.append(rect(0, H * 0.72, W, H * 0.28, "#b98a5e" if decada else "#c8a27a", borde=False))
    for x in range(-200, W + 200, 160):   # tablas del piso en perspectiva
        p.append(f'<path d="M{x} {n(H * 0.72)} L{x - 140} {H}" stroke="#a4774c" stroke-width="5"/>')
    p.append(f'<path d="M0 {n(H * 0.72)} L{W} {n(H * 0.72)}" {trazo()}/>')
    p.append(rect(0, H * 0.70, W, 30, P.BLANCO))                      # zócalo
    # ventana con cortinas (arriba, del lado del sillón)
    p.append(_ventana_cortinas(640, 250, 300, 330, cortina, rnd))
    # biblioteca con libros y un objeto de la época arriba
    p.append(rect(30, 330, 200, 1050, P.MADERA, r=6))
    for k, y in enumerate((520, 760, 1000, 1240)):
        p.append(rect(42, y, 176, 16, "#7a4b2a", ancho=4))
        p.append(_libros(48, y, 166, _random.Random(semilla * 7 + k)))
    p.append(_objeto_epoca(decada, 130, 330))
    # cuadro de la época arriba de la biblioteca
    if not decada or decada >= 200:
        p.append(rect(300, 330, 220, 160, P.BLANCO, r=4) + rect(318, 348, 184, 124, "#7fb7e8", ancho=4)
                 + circulo(380, 410, 30, P.AMARILLO, ancho=4) + rect(420, 380, 60, 70, P.ROJO, ancho=4))
    else:
        p.append(elipse(410, 410, 90, 110, "#c9a24a") + elipse(410, 410, 70, 88, "#efe2c1", ancho=4)
                 + circulo(410, 390, 28, "#6b4a2e", ancho=4) + elipse(410, 470, 44, 30, "#6b4a2e", ancho=4))
    # alfombra
    p.append(elipse(W / 2, H * 0.86, 420, 90, alf1, ancho=P.TRAZO_FINO))
    p.append(elipse(W / 2, H * 0.86, 340, 62, alf2, borde=False))
    if decada and decada < 200:
        p.append(elipse(W / 2, H * 0.86, 220, 36, alf1, borde=False))
    # sillón de la época (con patitas en los 50-70)
    p.append(rect(560, 1050, 460, 200, sillon, r=40))
    p.append(rect(530, 1150, 520, 160, sillon, r=40))
    p.append(rect(560, 1180, 460, 60, sillon, r=20, ancho=P.TRAZO_FINO))
    if decada and 195 <= decada < 198:
        for x in (580, 1000):
            p.append(camino(f"M{x} 1305 L{x + 14} 1305 L{x + 6} 1380 L{x + 2} 1380 Z", P.MADERA, ancho=4))
    else:
        p.append(rect(560, 1300, 30, 60, P.MADERA) + rect(990, 1300, 30, 60, P.MADERA))
    p.append(rect(600, 1090, 110, 80, cortina, r=24, ancho=P.TRAZO_FINO))    # almohadón
    # juguetes en el piso (algunas variantes): cubos con letras
    if var % 3 != 2:
        for k, (x, c) in enumerate(((820, P.ROJO), (880, P.AZUL), (850, P.AMARILLO))):
            y = 1440 if k < 2 else 1390
            p.append(rect(x, y, 56, 56, c, r=6, ancho=5))
    if not decada or decada >= 200:      # una planta en el presente
        p.append(rect(965, 1290, 90, 100, P.NARANJA, r=10))
        for ang in (-35, -10, 15, 40):
            p.append(g(camino("M0 0 Q-24 -80 0 -150 Q24 -80 0 0 Z", P.VERDE, ancho=P.TRAZO_FINO), 1010, 1290, rot=ang))
    return "".join(p)


def _objeto_epoca(decada: int, x: float, y: float) -> str:
    """Un objeto que cuenta la época, apoyado arriba de la biblioteca (su base en `y`)."""
    if decada and decada < 195:     # gramófono
        return (rect(x - 50, y - 50, 100, 50, P.MADERA, r=6)
                + camino(f"M{x} {y - 50} L{x + 10} {y - 110} Q{x + 70} {y - 190} {x + 90} {y - 120} "
                         f"Q{x + 40} {y - 110} {x + 20} {y - 60} Z", "#c9a24a"))
    if decada and decada < 198:     # radio de válvulas y teléfono de disco
        return (rect(x - 80, y - 90, 120, 90, "#a0522d", r=18) + circulo(x - 50, y - 45, 26, "#e9d8a6", ancho=4)
                + rect(x - 18, y - 70, 44, 50, "#e9d8a6", r=4, ancho=4)
                + rect(x + 50, y - 40, 70, 40, "#2b2b33", r=10)
                + circulo(x + 85, y - 30, 16, "#ddd", ancho=3))
    if decada and decada < 200:     # equipo de música con casetera
        return (rect(x - 90, y - 70, 180, 70, "#5b6170", r=8) + circulo(x - 55, y - 35, 22, "#2b2b33", ancho=4)
                + circulo(x + 55, y - 35, 22, "#2b2b33", ancho=4) + rect(x - 22, y - 55, 44, 28, "#9fe3ff", ancho=3))
    return rect(x - 30, y - 70, 60, 70, P.TURQUESA, r=10) + circulo(x, y - 90, 30, P.VERDE)   # maceta moderna


def fondo_taller(semilla: int = 9) -> str:
    """Un taller de inventor: banco de trabajo, herramientas colgadas, planos en la pared."""
    p = [rect(0, 0, W, H, "#cfd8dc", borde=False),
         rect(0, H * 0.72, W, H * 0.28, "#8d6e63", borde=False),
         f'<path d="M0 {n(H * 0.72)} L{W} {n(H * 0.72)}" {trazo()}/>']
    p.append(rect(80, 220, 920, 460, "#a1887f", r=8))                # panel de herramientas
    for x in range(120, 1000, 60):
        for y in range(260, 660, 60):
            p.append(circulo(x, y, 6, "#6d4c41", borde=False))
    p.append(g(prop_martillo(), 260, 420, escala=0.7, rot=-30))
    p.append(g(prop_engranaje(), 520, 400, escala=0.6))
    p.append(rect(700, 300, 240, 300, "#bbdefb", r=6))                # plano
    p.append(f'<path d="M730 360 L900 360 M730 420 L860 420 M730 480 L900 480" {trazo(ancho=6)}/>')
    p.append(circulo(820, 540, 40, "none", ancho=6))
    p.append(rect(60, H * 0.62, 960, 50, P.MADERA, r=8))              # banco
    p.append(rect(100, H * 0.62 + 44, 50, 300, P.MADERA) + rect(930, H * 0.62 + 44, 50, 300, P.MADERA))
    p.append(rect(200, H * 0.62 - 70, 140, 70, P.ROJO, r=8))          # caja de herramientas
    return "".join(p)


def fondo_laboratorio(semilla: int = 10) -> str:
    """Un laboratorio: mesadas con frascos de colores, un microscopio, pizarrón con fórmulas, estantes."""
    decada, _ = epoca_de(semilla)
    p = [rect(0, 0, W, H, "#dfe9ee", borde=False), rect(0, H * 0.72, W, H * 0.28, "#b8c4cc", borde=False),
         f'<path d="M0 {n(H * 0.72)} L{W} {n(H * 0.72)}" {trazo()}/>']
    p.append(rect(100, 260, 560, 380, "#2f4f4f" if decada and decada < 197 else "#f4f7f8", r=8))   # pizarrón
    tiza = "#e8f0e8" if decada and decada < 197 else "#3a86ff"
    for k, y in enumerate((330, 410, 490, 570)):
        p.append(f'<path d="M150 {y} Q{260 + k * 30} {y - 25} {360 + k * 40} {y} T{580 - k * 20} {y}" '
                 f'fill="none" stroke="{tiza}" stroke-width="7" stroke-linecap="round"/>')
    p.append(rect(730, 300, 270, 22, P.MADERA, ancho=5) + rect(730, 480, 270, 22, P.MADERA, ancho=5))
    colores = (P.VERDE, P.ROJO, P.AZUL, P.AMARILLO, P.VIOLETA, P.TURQUESA)
    for k in range(5):
        for fila, yb in enumerate((300, 480)):
            c = colores[(k + fila * 2) % len(colores)]
            x = 750 + k * 50
            p.append(camino(f"M{x} {yb - 70} L{x + 30} {yb - 70} L{x + 30} {yb - 40} L{x + 40} {yb} L{x - 10} {yb} "
                            f"L{x} {yb - 40} Z", "#e8f6ff", ancho=4) +
                     camino(f"M{x - 6} {yb - 14} L{x + 36} {yb - 14} L{x + 40} {yb} L{x - 10} {yb} Z", c,
                            borde=False))
    p.append(rect(40, H * 0.6, 1000, 60, "#8a9aa5", r=8))                       # mesada
    p.append(rect(80, H * 0.6 + 56, 940, 300, "#c9d3d9", r=6, ancho=6))
    p.append(rect(330, H * 0.6 - 200, 40, 200, P.GRIS_OSCURO, r=10) + circulo(350, H * 0.6 - 210, 34, P.GRIS_OSCURO)
             + rect(300, H * 0.6 - 30, 130, 30, P.GRIS_OSCURO, r=8))           # microscopio
    p.append(circulo(700, H * 0.6 - 60, 60, "#e8f6ff", ancho=5) + rect(685, H * 0.6 - 170, 30, 60, "#e8f6ff", ancho=5)
             + circulo(700, H * 0.6 - 45, 40, P.VERDE, borde=False))           # balón con líquido
    return "".join(p)


def fondo_hospital(semilla: int = 11) -> str:
    """Un hospital: cama con sábanas, cortina, cruz en la pared, ventana, carrito con frascos."""
    p = [rect(0, 0, W, H, "#e9f3f1", borde=False), rect(0, H * 0.72, W, H * 0.28, "#cfd8d6", borde=False),
         f'<path d="M0 {n(H * 0.72)} L{W} {n(H * 0.72)}" {trazo()}/>']
    p.append(rect(0, 820, W, 30, "#9fd8d0", borde=False))
    p.append(rect(120, 300, 180, 180, P.BLANCO, r=10) + rect(185, 325, 50, 130, P.ROJO, borde=False)
             + rect(145, 365, 130, 50, P.ROJO, borde=False))                    # cruz
    p.append(rect(560, 260, 380, 360, "#bfe9ff", r=8) +
             f'<path d="M750 260 L750 620 M560 440 L940 440" {trazo()}/>')
    p.append(rect(470, 220, 70, 620, "#7fc8b8", r=10, ancho=5))                # cortina
    for x in (490, 515):
        p.append(f'<path d="M{x} 240 L{x} 830" stroke="#000" stroke-opacity="0.12" stroke-width="5"/>')
    p.append(rect(560, 1150, 440, 70, P.BLANCO, r=20) + rect(560, 1100, 120, 70, P.BLANCO, r=24, ancho=6)
             + rect(560, 1215, 440, 30, P.GRIS, r=6) + rect(580, 1240, 20, 140, P.GRIS) + rect(960, 1240, 20, 140, P.GRIS)
             + rect(700, 1140, 300, 50, "#9fd8d0", r=14, ancho=5))              # cama
    p.append(rect(100, 1150, 200, 20, P.GRIS, ancho=5) + rect(100, 1270, 200, 20, P.GRIS, ancho=5)
             + rect(110, 1170, 12, 230, P.GRIS, borde=False) + rect(278, 1170, 12, 230, P.GRIS, borde=False)
             + rect(130, 1100, 36, 50, "#e8f6ff", r=6, ancho=4) + rect(190, 1110, 36, 40, "#ffd6e0", r=6, ancho=4))
    return "".join(p)


def fondo_campo(semilla: int = 12) -> str:
    """El campo: cielo, sol, sierras, surcos de cultivo, un granero y una cerca."""
    rnd = random.Random(semilla)
    p = [rect(0, 0, W, H, P.CIELO, borde=False), rect(0, H * 0.5, W, H * 0.5, P.CIELO_BAJO, borde=False),
         circulo(820, 300, 100, P.AMARILLO)]
    for i in range(3):
        p.append(g(nube(), rnd.uniform(100, W - 100), 200 + i * 170, escala=rnd.uniform(0.6, 1.0)))
    p.append(_colinas(H * 0.62, "#a7c4a0", 140, semilla + 1))
    p.append(rect(-20, H * 0.66, W + 40, H * 0.34 + 20, "#c9a66b", borde=False))
    for k in range(9):        # surcos en perspectiva
        x = -400 + k * 240
        p.append(f'<path d="M540 {n(H * 0.66)} L{x} {H}" stroke="#a5824e" stroke-width="10"/>')
    for k in range(14):       # plantitas
        y = H * 0.7 + (k // 7) * 120
        x = 60 + (k % 7) * 160 + (k // 7) * 60
        p.append(g(camino("M0 0 Q-20 -50 0 -80 Q20 -50 0 0 Z", P.VERDE, ancho=4), x, y))
    p.append(rect(700, H * 0.5, 280, 230, "#b5442c", r=4) + camino(f"M680 {n(H * 0.5)} L840 {n(H * 0.5 - 130)} "
             f"L1000 {n(H * 0.5)} Z", "#8e3322") + rect(800, H * 0.5 + 110, 80, 120, "#7a2a1c", ancho=6))   # granero
    for x in range(0, W, 120):  # cerca
        p.append(rect(x, H * 0.64 - 80, 18, 100, "#e9d8a6", ancho=4))
    p.append(rect(0, H * 0.64 - 60, W, 14, "#e9d8a6", ancho=4))
    return "".join(p)


def fondo_puerto(semilla: int = 13) -> str:
    """Un puerto: mar, un barco de la época en el muelle, grúa, cajones y gaviotas."""
    decada, _ = epoca_de(semilla)
    p = [rect(0, 0, W, H, "#ffd9a8", borde=False), rect(0, 0, W, H * 0.35, "#ffbf91", borde=False),
         circulo(300, 420, 110, "#ffe08a", borde=False), rect(0, H * 0.45, W, H * 0.3, P.OCEANO, borde=False)]
    for k in range(6):
        y = H * 0.48 + k * 70
        p.append(f'<path d="M0 {n(y)} Q135 {n(y - 18)} 270 {n(y)} T540 {n(y)} T810 {n(y)} T1080 {n(y)}" '
                 f'fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="6"/>')
    # el barco: a vapor con chimenea antes de 1960; de contenedores después
    if decada and decada < 196:
        p.append(camino(f"M180 {n(H * 0.5)} L900 {n(H * 0.5)} L840 {n(H * 0.58)} L240 {n(H * 0.58)} Z", "#2b2b33")
                 + rect(320, H * 0.5 - 120, 380, 120, P.BLANCO, r=8) + rect(480, H * 0.5 - 260, 70, 150, P.ROJO)
                 + rect(480, H * 0.5 - 270, 70, 30, "#2b2b33"))
        for x in range(360, 680, 70):
            p.append(circulo(x, H * 0.5 - 60, 16, "#bfe9ff", ancho=4))
    else:
        p.append(camino(f"M120 {n(H * 0.5)} L960 {n(H * 0.5)} L900 {n(H * 0.58)} L180 {n(H * 0.58)} Z", "#2b4a7a"))
        for k, c in enumerate((P.ROJO, P.AZUL, P.AMARILLO, P.VERDE, P.NARANJA, P.TURQUESA)):
            p.append(rect(220 + k * 110, H * 0.5 - 90, 100, 90, c, r=4, ancho=5))
    p.append(rect(-20, H * 0.72, W + 40, H * 0.28 + 20, "#8d6e63"))                 # muelle de tablas
    for y in range(int(H * 0.75), H, 60):
        p.append(f'<path d="M0 {y} L{W} {y}" stroke="#6d4c41" stroke-width="5"/>')
    p.append(linea_gruesa([(960, H * 0.72), (960, 380), (700, 330)], P.AMARILLO, 30))  # grúa
    p.append(f'<path d="M760 340 L760 600" {trazo(ancho=5)}/>' + rect(730, 600, 60, 50, P.MADERA, ancho=5))
    for x, y in ((150, 260), (240, 320), (620, 220)):  # gaviotas
        p.append(f'<path d="M{x - 30} {y} Q{x - 15} {y - 18} {x} {y} Q{x + 15} {y - 18} {x + 30} {y}" '
                 f'fill="none" {trazo(ancho=6)}/>')
    return "".join(p)


FONDOS = {"mapa_geo": None, "laboratorio": fondo_laboratorio, "hospital": fondo_hospital, "campo": fondo_campo,
          "puerto": fondo_puerto, "casa": fondo_casa, "taller": fondo_taller, "cielo": fondo_cielo, "ciudad": fondo_ciudad, "oficina": fondo_oficina,
          "globo": fondo_globo, "mapa": fondo_globo, "fabrica": fondo_fabrica,
          "tienda": fondo_tienda, "escenario": fondo_escenario}


# ---- ambiente de los fondos (Santi, 2026-11-15: "escenarios ricos: profundidad, texturas simples (madera,
# ladrillo, empapelado), luz de ventana, sombras en el piso") --------------------------------------------
# Encima de cada fondo, en el MISMO dibujo cacheado (no cuesta nada por cuadro): la textura de la pared y
# del piso, la luz que entra por la ventana y cae al piso, la sombra donde la pared toca el piso y debajo
# de los muebles, y una bruma suave arriba (lo lejano, más claro). La línea del piso y la ventana de cada
# lugar están acá; si un fondo cambia de lugar la ventana, se cambia esta tabla.
PISO_Y = {"casa": 0.72, "oficina": 0.72, "taller": 0.72, "fabrica": 0.70, "tienda": 0.74, "escenario": 0.72,
          "laboratorio": 0.72, "hospital": 0.72}
VENTANA = {"casa": (640, 250, 300, 330), "oficina": (560, 260, 400, 480), "fabrica": (80, 200, 920, 420),
           "hospital": (560, 260, 380, 360)}
PARED_TEXTURA = {"casa": "empapelado", "oficina": "empapelado", "taller": "ladrillo", "fabrica": "ladrillo",
                 "tienda": "azulejo", "laboratorio": "azulejo", "hospital": "azulejo"}
MUEBLES_SOMBRA = {"casa": [(790, 1385, 270, 26), (130, 1385, 110, 18)], "oficina": [(390, 1520, 330, 30),
                  (920, 1408, 80, 16)], "taller": [(540, 1540, 470, 30)], "fabrica": [(540, 1330, 560, 26)],
                  "tienda": [(190, 1425, 160, 22)]}


def _patrones() -> str:
    return (
        '<defs>'
        '<pattern id="pat_madera" width="240" height="60" patternUnits="userSpaceOnUse">'
        '<path d="M0 59 L240 59" stroke="#000000" stroke-opacity="0.16" stroke-width="3"/>'
        '<path d="M150 0 L150 60" stroke="#000000" stroke-opacity="0.1" stroke-width="3"/>'
        '<path d="M14 20 Q60 14 110 22 M170 36 Q200 30 232 38 M30 44 Q48 41 70 45" fill="none" '
        'stroke="#000000" stroke-opacity="0.08" stroke-width="2.5"/></pattern>'
        '<pattern id="pat_ladrillo" width="140" height="70" patternUnits="userSpaceOnUse">'
        '<path d="M0 0.5 L140 0.5 M0 35 L140 35 M35 0 L35 35 M105 35 L105 70" stroke="#000000" '
        'stroke-opacity="0.13" stroke-width="4"/>'
        '<rect x="40" y="6" width="58" height="24" fill="#ffffff" opacity="0.05"/></pattern>'
        '<pattern id="pat_empapelado" width="90" height="120" patternUnits="userSpaceOnUse">'
        '<path d="M45 0 L45 120" stroke="#000000" stroke-opacity="0.045" stroke-width="16"/>'
        '<path d="M45 52 L53 60 L45 68 L37 60 Z" fill="#ffffff" opacity="0.18"/></pattern>'
        '<pattern id="pat_azulejo" width="80" height="80" patternUnits="userSpaceOnUse">'
        '<path d="M0 0.5 L80 0.5 M0.5 0 L0.5 80" stroke="#000000" stroke-opacity="0.07" stroke-width="3"/></pattern>'
        '<linearGradient id="amb_zocalo" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{P.SOMBRA_TINTE}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{P.SOMBRA_TINTE}" stop-opacity="0.32"/></linearGradient>'
        '<linearGradient id="amb_piso" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{P.SOMBRA_TINTE}" stop-opacity="0.38"/>'
        f'<stop offset="1" stop-color="{P.SOMBRA_TINTE}" stop-opacity="0"/></linearGradient>'
        '<linearGradient id="amb_haz" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{P.LUZ}" stop-opacity="0.42"/>'
        f'<stop offset="1" stop-color="{P.LUZ}" stop-opacity="0"/></linearGradient>'
        '<linearGradient id="amb_bruma" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#fff6e6" stop-opacity="0.28"/>'
        '<stop offset="1" stop-color="#fff6e6" stop-opacity="0"/></linearGradient>'
        '<radialGradient id="amb_sombra_mueble"><stop offset="0" stop-color="#2a1838" stop-opacity="0.42"/>'
        '<stop offset="1" stop-color="#2a1838" stop-opacity="0"/></radialGradient>'
        '</defs>')


def ambiente(tipo: str) -> str:
    """Lo que le da profundidad y luz a un fondo (ver arriba). Vacío para los que no lo llevan."""
    out = []
    if tipo in PISO_Y:
        py = H * PISO_Y[tipo]
        tex = PARED_TEXTURA.get(tipo)
        if tex:
            out.append(f'<rect x="0" y="0" width="{W}" height="{n(py)}" fill="url(#pat_{tex})"/>')
        # el piso: tablas de madera (o el patrón de cada lugar) y la sombra donde toca la pared
        out.append(f'<rect x="0" y="{n(py)}" width="{W}" height="{n(H - py)}" fill="url(#pat_madera)" '
                   f'opacity="{0.55 if tipo in ("fabrica", "tienda") else 1}"/>')
        out.append(f'<rect x="0" y="{n(py - 150)}" width="{W}" height="150" fill="url(#amb_zocalo)"/>')
        out.append(f'<rect x="0" y="{n(py)}" width="{W}" height="140" fill="url(#amb_piso)"/>')
        for cx, cy, rx, ry in MUEBLES_SOMBRA.get(tipo, []):
            out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="url(#amb_sombra_mueble)"/>')
        v = VENTANA.get(tipo)
        if v:   # el haz de luz: de la ventana baja en diagonal hasta el piso
            x, y, w, h = v
            caida = py + 260
            corre = -0.55 * (caida - (y + h))
            out.append(f'<path d="M{x} {y + h} L{x + w} {y + h} L{n(x + w + corre)} {n(caida)} '
                       f'L{n(x + corre - 60)} {n(caida)} Z" fill="url(#amb_haz)"/>')
            out.append(f'<path d="M{n(x + corre - 60)} {n(caida)} L{n(x + w + corre)} {n(caida)} '
                       f'L{n(x + w + corre - 50)} {n(caida - 120)} L{n(x + corre - 10)} {n(caida - 120)} Z" '
                       f'fill="{P.LUZ}" opacity="0.18"/>')
        out.append(f'<rect x="0" y="0" width="{W}" height="{n(py * 0.55)}" fill="url(#amb_bruma)"/>')
    elif tipo == "ciudad":
        out.append(f'<rect x="0" y="0" width="{W}" height="{n(H * 0.6)}" fill="url(#amb_bruma)"/>')
        out.append(f'<rect x="0" y="{n(H * 0.8)}" width="{W}" height="120" fill="url(#amb_piso)"/>')
    elif tipo in ("cielo", "campo", "puerto"):
        out.append(f'<rect x="0" y="0" width="{W}" height="{n(H * 0.5)}" fill="url(#amb_bruma)"/>')
    return (_patrones() + "".join(out)) if out else ""


# ---- color por escena (Santi, 2026-11-15: "paleta más linda: cálidos y armónicos por escena") -----------
# Encima de TODO (personajes incluidos) y debajo de los subtítulos: un tinte suave del color de la luz de
# ese lugar y una viñeta que oscurece los bordes (el ojo va al centro). Así cada lugar tiene su paleta y
# los personajes "están" en esa luz. Cuesta un rectángulo con degradé por cuadro.
TINTE = {"laboratorio": ("#bfe3ff", 0.05), "hospital": ("#d8fff4", 0.05), "campo": ("#ffcf6b", 0.08),
         "puerto": ("#ff9f6b", 0.08), "casa": ("#ffb36b", 0.07), "oficina": ("#ffd59a", 0.06), "taller": ("#ffad5c", 0.07),
         "fabrica": ("#ff9a5c", 0.06), "tienda": ("#ffd28a", 0.05), "ciudad": ("#ff8f5c", 0.08),
         "cielo": ("#ffd08a", 0.05), "escenario": ("#ff6b8a", 0.06), "globo": ("#7c6bff", 0.05),
         "mapa": ("#7c6bff", 0.05)}
VINETA = 0.34


# La luz según el momento (Santi, 2026-11-15): encima del tinte del lugar.
MOMENTO_LUZ = {"atardecer": ("#ff7a3d", 0.17), "noche": ("#0d1a40", 0.36), "interior": ("#ffcf8a", 0.05)}


def grade(tipo: str, momento: str = "") -> str:
    """El tinte y la viñeta de ese lugar, y la luz del momento (SVG en coordenadas de pantalla)."""
    luz = ""
    if momento in MOMENTO_LUZ:
        c_, op_ = MOMENTO_LUZ[momento]
        luz = f'<rect width="{W}" height="{H}" fill="{c_}" opacity="{op_}"/>'
    return _grade_base(tipo) + luz


def _grade_base(tipo: str) -> str:
    color, op = TINTE.get(tipo, ("#ffc08a", 0.05))
    borde = mezcla(oscurecer(color, 0.75), P.SOMBRA_TINTE, 0.5)
    return (f'<defs><radialGradient id="vineta" cx="0.5" cy="0.48" r="0.75">'
            f'<stop offset="0.55" stop-color="{borde}" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="{borde}" stop-opacity="{VINETA}"/></radialGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="{color}" opacity="{op}"/>'
            f'<rect width="{W}" height="{H}" fill="url(#vineta)"/>')


# ---- primer plano (profundidad): algo cerca de la cámara en una esquina de abajo, oscuro y grande -------
def primer_plano(tipo: str, lado: int = 1, variante: int = 0) -> str:
    """Un objeto MUY cerca de la cámara, recortado por el borde de abajo (una planta, el respaldo de una
    silla, una caja, un poste): más oscuro (fuera de la luz). Coordenadas de pantalla: la esquina de abajo
    del `lado` (-1 izquierda, 1 derecha). Ocupa solo el borde (≤ 120 px adentro, de y 1640 para abajo)."""
    oscuro = lambda c: oscurecer(c, 0.55)   # noqa: E731
    if tipo in ("casa", "oficina", "cielo") and variante % 2 == 0:     # hojas de una planta
        hojas = "".join(g(camino("M0 0 Q-55 -140 0 -300 Q55 -140 0 0 Z", oscuro(P.VERDE), ancho=P.TRAZO_FINO),
                          0, 0, rot=a) for a in (-30, -8, 16))
        cosa = g(hojas, -10, 2000) + elipse(-10, 1965, 130, 55, oscuro(P.NARANJA))
    elif tipo in ("casa", "oficina", "tienda"):                          # respaldo de una silla
        cosa = (rect(-60, 1700, 170, 320, oscuro(P.MADERA), r=24)
                + rect(-30, 1740, 110, 240, oscuro(mezcla(P.MADERA, P.ROJO, 0.4)), r=16, ancho=P.TRAZO_FINO))
    elif tipo in ("taller", "fabrica"):                                  # cajón de madera
        cosa = (rect(-80, 1690, 200, 300, oscuro("#a8714a"), r=8)
                + f'<path d="M-80 1760 L120 1760 M-80 1850 L120 1850" {trazo(ancho=P.TRAZO_FINO)}/>')
    elif tipo == "ciudad":                                               # un poste con un cartel
        cosa = rect(30, 1500, 50, 500, oscuro(P.GRIS_OSCURO)) + rect(-40, 1560, 160, 90, oscuro(P.AMARILLO), r=10)
    else:                                                                # cualquier otro lugar: la planta
        return primer_plano("casa", lado, 0)
    return cosa if lado < 0 else f'<g transform="translate({W} 0) scale(-1 1)">{cosa}</g>'


def fondo(tipo: str, semilla: int | None = None) -> str:
    """El fondo. Con la semilla nueva (década*100 + variante) las variantes impares salen ESPEJADAS
    (otro "ángulo" del mismo lugar: dos escenas seguidas en la casa no se ven idénticas). Encima va el
    ambiente (texturas, luz, sombras), espejado junto con el lugar."""
    if tipo == "mapa_geo":     # el mapa con el pin (visuales.py): nunca espejado
        from . import visuales

        return visuales.svg_mapa(int(semilla or 0))
    f = FONDOS.get(tipo)
    if f is None:
        raise ValueError(f"Fondo desconocido: {tipo!r} (hay {', '.join(sorted(FONDOS))})")
    if semilla is None:
        return f() + (ambiente(tipo) if P.VOLUMEN else "")
    svg_ = f(semilla) + (ambiente(tipo) if P.VOLUMEN else "")
    if semilla >= 1000 and (semilla % 100) % 2 == 1:
        return f'<g transform="translate({W} 0) scale(-1 1)">{svg_}</g>'
    return svg_


def espejado(semilla: int) -> bool:
    return semilla >= 1000 and (semilla % 100) % 2 == 1


# ---- props --------------------------------------------------------------------

def prop_cartel(texto: str = "", color: str = P.AMARILLO, **_) -> str:
    """Un cartel. Sin texto (Santi, 2026-11-16: "ningún objeto con etiquetas de texto salvo que la historia lo pida"; y en
    un fondo espejado el texto salía al revés), una estrella de oferta dibujada."""
    base = rect(-14, 0, 28, 230, P.MADERA) + rect(-190, -140, 380, 170, color, r=14)
    if not texto:
        pts = " ".join(f"{(60 if k % 2 == 0 else 26) * math.cos(math.radians(-90 + k * 36)):.0f},"
                       f"{-55 + (60 if k % 2 == 0 else 26) * math.sin(math.radians(-90 + k * 36)):.0f}" for k in range(10))
        return base + f'<polygon points="{pts}" fill="{P.ROJO}" stroke="{P.CONTORNO}" stroke-width="6" stroke-linejoin="round"/>'
    tam = 64 if len(texto) <= 8 else 48
    return base + texto_con_borde(texto, 0, -36, tam, color=P.CONTORNO, borde=P.BLANCO, ancho_borde=6)


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


# ---- props genéricos del canal de marcas (2026-11-14) -----------------------------------------
# Productos SIN marca dibujada: la etiqueta lleva, como mucho, un texto en la fuente común del canal
# (nunca un logo ni la tipografía de la marca). El color lo pone quien llama (paleta del canal).

def _etiqueta(texto: str, y: float, ancho: float, tam: int = 40) -> str:
    if not texto:
        return ""
    tam = min(tam, int(ancho * 1.6 / max(1, len(texto))))
    return texto_con_borde(texto[:14], 0, y, max(18, tam), color=P.CONTORNO, borde=P.BLANCO,
                           ancho_borde=5)


def _etiqueta_dibujada(x: float, y: float, w: float, h: float, color: str) -> str:
    """Una etiqueta con dibujo (Santi, 2026-11-16: "nada de etiquetas en blanco"): fondo claro, dos franjas del color del
    objeto y un sello redondo, sin letras."""
    claro = aclarar(color, 0.62)
    return (rect(x, y, w, h, claro, ancho=P.TRAZO_FINO)
            + rect(x, y + h * 0.16, w, h * 0.14, aclarar(color, 0.2), borde=False)
            + rect(x, y + h * 0.70, w, h * 0.14, aclarar(color, 0.2), borde=False)
            + circulo(x + w / 2, y + h / 2, min(w, h) * 0.2, oscurecer(color, 0.1), ancho=P.TRAZO_FINO)
            + circulo(x + w / 2, y + h / 2, min(w, h) * 0.09, P.AMARILLO, borde=False))


def prop_botella(texto: str = "", color: str = P.ROJO, **_) -> str:
    return (camino("M-26 -230 L26 -230 L26 -170 Q80 -130 80 -60 L80 200 Q80 230 50 230 L-50 230 "
                   "Q-80 230 -80 200 L-80 -60 Q-80 -130 -26 -170 Z", color)
            + rect(-30, -262, 60, 36, P.GRIS_OSCURO, r=6)
            + (rect(-80, -10, 160, 110, P.BLANCO, ancho=P.TRAZO_FINO) + _etiqueta(texto, 58, 150) if texto
               else _etiqueta_dibujada(-80, -10, 160, 110, color))
            + camino("M-50 -100 Q-58 -40 -54 40", borde=True, ancho=10, color="#ffffff"))


def prop_lata(texto: str = "", color: str = P.AZUL, **_) -> str:
    return (rect(-80, -150, 160, 300, color, r=18)
            + elipse(0, -150, 80, 18, P.GRIS)
            + elipse(0, -150, 22, 6, P.GRIS_OSCURO, borde=False)
            + (rect(-80, -50, 160, 100, P.BLANCO, ancho=P.TRAZO_FINO) + _etiqueta(texto, 14, 150) if texto
               else _etiqueta_dibujada(-80, -50, 160, 100, color))
            + camino("M-58 -120 L-58 120", borde=True, ancho=9, color="#ffffff"))


def prop_caja_registradora(fase: float = 0.0, **_) -> str:
    """La caja registradora de antes (la plata con una acción real, 2026-11-16): `fase` 0..1 = el cajón que se abre con
    los billetes adentro."""
    abre = max(0.0, min(1.0, float(fase or 0.0)))
    cajon_y = 90 + 70 * abre
    billetes = "".join(rect(-70 + k * 48, cajon_y - 8, 40, 22, P.VERDE, r=3, ancho=3) for k in range(3)) if abre > 0.2 else ""
    return (rect(-150, 90, 300, 40, "#7a5530", r=6)                                   # base
            + rect(-130, cajon_y, 260, 50, "#9c6a3d", r=6) + billetes                  # cajón
            + camino("M-140 90 L-110 -40 L110 -40 L140 90 Z", "#c0392b")             # cuerpo
            + rect(-90, -120, 180, 80, "#2c3e50", r=10) + rect(-70, -105, 140, 50, "#a8e6a1", r=6, ancho=3)  # visor
            + "".join(circulo(-80 + (k % 4) * 54, 10 + (k // 4) * 40, 14, "#f4f1ea", ancho=3) for k in range(8)))


def prop_papel_firma(fase: float = 0.0, forma: int = 0, **_) -> str:
    """Un contrato o un cheque con la firma que se va escribiendo (`fase` 0..1). `forma` 1 = apoyado sobre una mesa,
    visto un poco desde arriba (un trapecio chato: el contrato sobre la mesa del apretón, Santi 2026-11-16)."""
    f = max(0.0, min(1.0, float(fase or 0.0)))
    if int(forma or 0) == 1:
        hoja = camino("M-118 -62 L118 -62 L150 0 L-150 0 Z", "#fbf7ec", ancho=5)
        sombra = camino("M-150 0 L150 0 L146 8 L-146 8 Z", "#d9d2c0", borde=False)
        renglones = "".join(f'<path d="M{-112 + k * 6} {-50 + k * 11} L{(96 if k % 2 else 70) + k * 6} {-50 + k * 11}" '
                            f'stroke="#9aa0ab" stroke-width="4" stroke-linecap="round"/>' for k in range(3))
        firma = (f'<path d="M20 -12 C35 -30 45 -2 62 -16 S90 -26 110 -10" fill="none" stroke="#1d3a8a" stroke-width="5" '
                 f'stroke-linecap="round"/><path d="M-60 -8 L10 -8" stroke="#5a6070" stroke-width="3"/>')
        return sombra + hoja + renglones + firma
    renglones = "".join(f'<path d="M-120 {-110 + k * 34} L{120 - (k % 3) * 30} {-110 + k * 34}" stroke="#9aa0ab" '
                        f'stroke-width="6" stroke-linecap="round"/>' for k in range(5))
    largo = 420 * f
    firma = (f'<path d="M-110 120 C-80 70 -60 150 -30 100 S20 70 40 120 S90 90 120 100" fill="none" stroke="#1d3a8a" '
             f'stroke-width="7" stroke-linecap="round" stroke-dasharray="{largo:.0f} 999"/>') if f > 0 else ""
    return (rect(-150, -170, 300, 340, "#fbf7ec", r=6) + renglones
            + f'<path d="M-120 140 L120 140" stroke="#5a6070" stroke-width="4"/>' + firma)


def prop_lapicera(**_) -> str:
    """Una lapicera de las de antes, la punta abajo a la izquierda."""
    return g(rect(-14, -130, 28, 210, "#1f2d4d", r=12) + rect(-16, -130, 32, 40, "#c9a227", r=6, ancho=4)
             + camino("M-14 80 L0 130 L14 80 Z", "#c9a227", ancho=4), 0, 0, rot=35)


def prop_caja(texto: str = "", color: str = P.AMARILLO, **_) -> str:
    """Un paquete (galletitas, cereal, alfajores) con una ventana y el texto al frente."""
    return (camino("M-110 -150 L110 -150 L140 -180 L-80 -180 Z", color)
            + camino("M110 -150 L140 -180 L140 140 L110 170 Z", color)
            + rect(-110, -150, 220, 320, color)
            + rect(-80, -110, 160, 90, P.BLANCO, r=10, ancho=P.TRAZO_FINO)
            + _etiqueta(texto, -50, 150)
            + circulo(-40, 80, 34, P.MADERA, ancho=P.TRAZO_FINO)
            + circulo(40, 80, 34, P.MADERA, ancho=P.TRAZO_FINO))


def prop_zapatilla(color: str = P.ROJO, **_) -> str:
    return (camino("M-170 60 L-170 -40 Q-160 -90 -110 -90 L-40 -90 Q-20 -40 40 -30 L140 -10 "
                   "Q190 0 190 50 L190 60 Z", color)
            + rect(-180, 60, 380, 44, P.BLANCO, r=20)
            + f'<path d="M-60 -70 L-20 -40 M-80 -50 L-40 -24 M-100 -30 L-60 -6" '
              f'{trazo(ancho=P.TRAZO_FINO)} fill="none"/>')


def prop_billete(texto: str = "$", color: str = P.VERDE, **_) -> str:
    return (rect(-170, -85, 340, 170, color, r=12)
            + rect(-140, -60, 280, 120, "#a8e6a1", r=8, ancho=P.TRAZO_FINO)
            + circulo(0, 0, 46, color, ancho=P.TRAZO_FINO)
            + texto_con_borde(texto if 0 < len(texto) <= 3 else "$", 0, 22, 64, color=P.BLANCO, borde=P.CONTORNO,
                              ancho_borde=8))


def prop_bolsa_plata(color: str = "#d6a45a", **_) -> str:
    return (camino("M-40 -120 Q-60 -150 -30 -160 L30 -160 Q60 -150 40 -120 Q150 -40 140 80 "
                   "Q130 160 0 160 Q-130 160 -140 80 Q-150 -40 -40 -120 Z", color)
            + f'<path d="M-50 -118 L50 -118" {trazo(ancho=12)}/>'
            + texto_con_borde("$", 0, 70, 150, color=P.VERDE, ancho_borde=12))


def _grafico(sube: bool, color: str) -> str:
    pts = [(-150, 80), (-80, 30), (-20, 60), (50, -20), (130, -110)] if sube else \
          [(-150, -110), (-80, -40), (-20, -70), (50, 20), (130, 90)]
    d = "M" + " L".join(f"{x} {y}" for x, y in pts)
    x1, y1 = pts[-1]
    punta = (camino(f"M{x1 - 34} {y1 + 4} L{x1 + 16} {y1 - 16} L{x1 - 4} {y1 + 34} Z", color)
             if sube else camino(f"M{x1 - 34} {y1 - 4} L{x1 + 16} {y1 + 16} L{x1 - 4} {y1 - 34} Z", color))
    return (rect(-190, -170, 380, 320, P.BLANCO, r=14)
            + f'<path d="M-160 130 L170 130 M-160 130 L-160 -150" {trazo(ancho=P.TRAZO_FINO)}/>'
            + f'<path d="{d}" fill="none" {trazo(P.CONTORNO, 30)}/>'
            + f'<path d="{d}" fill="none" {trazo(color, 16)}/>' + punta)


def prop_grafico_sube(color: str = P.VERDE, **_) -> str:
    return _grafico(True, color)


def prop_grafico_baja(color: str = P.ROJO, **_) -> str:
    return _grafico(False, color)


def prop_trofeo(color: str = P.AMARILLO, **_) -> str:
    return (camino("M-100 -150 L100 -150 Q100 0 0 40 Q-100 0 -100 -150 Z", color)
            + camino("M-100 -120 Q-170 -120 -160 -60 Q-150 -10 -80 -10", ancho=14)
            + camino("M100 -120 Q170 -120 160 -60 Q150 -10 80 -10", ancho=14)
            + rect(-22, 36, 44, 70, color)
            + rect(-80, 100, 160, 50, P.MADERA, r=8))


def prop_megafono(color: str = P.ROJO, **_) -> str:
    return (camino("M-120 -40 L60 -130 L60 130 L-120 40 Z", color)
            + rect(-170, -46, 60, 92, P.GRIS_OSCURO, r=10)
            + rect(-120, 30, 40, 100, P.GRIS_OSCURO, r=8)
            + "".join(f'<path d="M{90 + i * 34} {-60 + i * 0} Q{120 + i * 34} 0 {90 + i * 34} 60" '
                      f'fill="none" {trazo(ancho=10)}/>' for i in range(3)))


def prop_calendario(texto: str = "", color: str = P.ROJO, **_) -> str:
    return (rect(-130, -130, 260, 260, P.BLANCO, r=16)
            + rect(-130, -130, 260, 70, color, r=16)
            + "".join(circulo(x, -130, 14, P.GRIS) for x in (-70, 70))
            + texto_con_borde(texto[:8], 0, 60, max(34, min(96, int(400 / max(1, len(texto[:8]))))),
                              color=P.CONTORNO, borde=P.BLANCO, ancho_borde=6))


def prop_control(color: str = P.GRIS_OSCURO, **_) -> str:
    """Un control de consola genérico (no copia el de ninguna marca)."""
    return (camino("M-170 -50 Q-170 -110 -110 -110 L110 -110 Q170 -110 170 -50 L190 70 "
                   "Q200 130 140 130 Q100 130 80 80 L-80 80 Q-100 130 -140 130 Q-200 130 -190 70 Z",
                   color)
            + rect(-130, -50, 70, 22, P.BLANCO, borde=False) + rect(-106, -74, 22, 70, P.BLANCO, borde=False)
            + circulo(90, -60, 18, P.ROJO, ancho=P.TRAZO_FINO)
            + circulo(130, -24, 18, P.AMARILLO, ancho=P.TRAZO_FINO)
            + circulo(50, -24, 18, P.AZUL, ancho=P.TRAZO_FINO)
            + circulo(90, 12, 18, P.VERDE, ancho=P.TRAZO_FINO))


def prop_engranaje(color: str = P.GRIS, **_) -> str:
    dientes = "".join(g(rect(-22, -120, 44, 50, color, r=6), rot=a) for a in range(0, 360, 45))
    return dientes + circulo(0, 0, 90, color) + circulo(0, 0, 30, P.BLANCO)


def prop_camion(color: str = P.AZUL, texto: str = "", **_) -> str:
    return (rect(-200, -110, 260, 150, color, r=10)
            + g(_etiqueta(texto, -20, 220, 44), -70, 0)
            + camino("M60 -70 L140 -70 L190 -10 L190 40 L60 40 Z", P.AMARILLO)
            + rect(110, -60, 50, 40, "#9fe3ff", r=4, ancho=P.TRAZO_FINO)
            + circulo(-130, 50, 36, P.GRIS_OSCURO) + circulo(120, 50, 36, P.GRIS_OSCURO))


def prop_celular(color: str = P.GRIS_OSCURO, texto: str = "", **_) -> str:
    return (rect(-95, -180, 190, 360, color, r=28)
            + rect(-78, -150, 156, 290, "#9fe3ff", r=10, ancho=P.TRAZO_FINO)
            + _etiqueta(texto, 4, 140, 40)
            + circulo(0, 160, 10, P.GRIS, borde=False))


def prop_corona(color: str = P.AMARILLO, **_) -> str:
    return (camino("M-150 80 L-150 -60 L-80 10 L0 -110 L80 10 L150 -60 L150 80 Z", color)
            + rect(-150, 80, 300, 50, color)
            + "".join(circulo(x, 105, 14, P.ROJO, ancho=P.TRAZO_FINO) for x in (-80, 0, 80)))


def prop_cohete(color: str = P.BLANCO, **_) -> str:
    return (camino("M0 -200 Q70 -120 70 40 L-70 40 Q-70 -120 0 -200 Z", color)
            + camino("M-70 -10 L-120 80 L-70 60 Z", P.ROJO) + camino("M70 -10 L120 80 L70 60 Z", P.ROJO)
            + circulo(0, -80, 30, "#9fe3ff", ancho=P.TRAZO_FINO)
            + camino("M-40 40 Q0 150 40 40 Z", P.NARANJA))


def prop_bombilla_rota(**_) -> str:
    """Una idea que no anduvo (producto fracasado): la lamparita apagada con una rajadura."""
    return (prop_lamparita(encendida=False)
            + f'<path d="M-30 -110 L-6 -70 L-30 -40 L4 -6" fill="none" {trazo(ancho=7)}/>')


def prop_pelota(color: str = P.NARANJA, **_) -> str:
    """Una pelota de espuma (sin costuras de ninguna marca)."""
    return (circulo(0, 0, 70, color)
            + "".join(circulo(x, y, 9, "#c96f1c", borde=False)
                      for x, y in ((-30, -20), (10, -35), (25, 15), (-15, 25), (40, -5), (-40, 10)))
            + elipse(-24, -30, 20, 12, "#ffffff", borde=False))


def prop_lampara(color: str = P.AMARILLO, **_) -> str:
    """Lámpara de mesa: pantalla, pie y base. El punto (0, 0) es el centro."""
    return (rect(-12, -10, 24, 170, P.GRIS_OSCURO)
            + elipse(0, 165, 80, 22, P.GRIS_OSCURO)
            + camino("M-70 -10 L70 -10 L110 -150 L-110 -150 Z", color))


def prop_ventana(rota: bool = False, **_) -> str:
    """Una ventana con su marco; `rota` = el vidrio astillado (rajaduras desde un punto)."""
    out = rect(-170, -200, 340, 400, "#9fe3ff", r=6) +         f'<path d="M0 -200 L0 200 M-170 0 L170 0" {trazo(ancho=14)}/>'
    if rota:
        cx, cy = 60, -70
        rayos = "".join(f"M{cx} {cy} L{cx + int(150 * math.cos(math.radians(a)))} "
                        f"{cy + int(150 * math.sin(math.radians(a)))} " for a in range(0, 360, 40))
        out += (circulo(cx, cy, 36, "#e3f6ff", ancho=P.TRAZO_FINO)
                + f'<path d="{rayos}" fill="none" {trazo(ancho=5)}/>')
    else:
        out += camino("M-140 -170 L-90 -170 L-140 -120 Z", "#ffffff", borde=False)
    return out


def prop_pedazo(color: str = "#9fe3ff", forma: int = 0, **_) -> str:
    """Un pedazo de algo roto (vidrio, cerámica): un triángulo irregular, ~50 px."""
    formas = ("M-30 -20 L30 -26 L6 30 Z", "M-24 -30 L26 -6 L-12 28 Z", "M-28 10 L0 -32 L30 20 Z",
              "M-20 -24 L32 0 L-6 22 L-26 6 Z")
    return camino(formas[int(forma) % len(formas)], color, ancho=P.TRAZO_FINO)


def prop_martillo(**_) -> str:
    return (rect(-12, -40, 24, 200, P.MADERA, r=8)
            + rect(-70, -90, 140, 60, P.GRIS_OSCURO, r=10))


def prop_jarron(color: str = P.TURQUESA, **_) -> str:
    return camino("M-40 -120 L40 -120 L30 -90 Q100 -40 80 60 Q60 120 0 120 Q-60 120 -80 60 "
                  "Q-100 -40 -30 -90 Z", color) +         f'<path d="M-60 0 Q0 30 60 0" fill="none" {trazo(ancho=8, color=P.BLANCO)}/>'


def prop_microfono(**_) -> str:
    return (rect(-10, 0, 20, 150, P.GRIS_OSCURO, r=6)
            + rect(-44, -110, 88, 120, "#3d4250", r=44)
            + "".join(f'<path d="M-36 {y} L36 {y}" stroke="#7d8597" stroke-width="5"/>'
                      for y in (-80, -55, -30)))


def prop_tele(rota: bool = False, **_) -> str:
    """Un televisor de tubo genérico (sin marca), centrado; `rota` = la pantalla astillada."""
    out = (rect(-150, -120, 300, 230, "#8d6e63", r=22)
           + rect(-125, -98, 210, 180, "#5b6b7a" if not rota else "#3a4450", r=26, ancho=P.TRAZO_FINO)
           + circulo(112, -50, 12, P.GRIS_OSCURO, ancho=4) + circulo(112, -10, 12, P.GRIS_OSCURO, ancho=4)
           + rect(-90, 110, 24, 20, P.GRIS_OSCURO, borde=False) + rect(66, 110, 24, 20, P.GRIS_OSCURO, borde=False)
           + f'<path d="M-40 -120 L-80 -190 M40 -120 L80 -190" {trazo(ancho=6)}/>')
    if rota:
        out += f'<path d="M-20 -20 L-110 -80 M-20 -20 L60 -90 M-20 -20 L-90 60 M-20 -20 L70 60 M-20 -20 L-60 -90" fill="none" {trazo(ancho=5, color="#e3f6ff")}/>'
    else:
        out += camino("M-110 -80 L-70 -80 L-110 -40 Z", "#8fa3b5", borde=False)
    return out


def prop_cuadro(color: str = P.VERDE, **_) -> str:
    """Un cuadro colgado (paisaje genérico)."""
    return (f'<path d="M-40 -110 L0 -150 L40 -110" fill="none" {trazo(ancho=5)}/>'
            + rect(-130, -110, 260, 200, P.MADERA, r=6)
            + rect(-108, -88, 216, 156, "#bfe3ff", ancho=P.TRAZO_FINO)
            + camino("M-108 68 L-40 -10 L10 40 L50 0 L108 68 Z", color, ancho=P.TRAZO_FINO)
            + circulo(60, -50, 18, P.AMARILLO, ancho=4))


def prop_mesa(**_) -> str:
    """Una mesita (el origen es el medio de la tapa: las cosas se apoyan arriba)."""
    return (rect(-150, 0, 300, 30, P.MADERA, r=6)
            + rect(-130, 26, 22, 200, P.MADERA) + rect(108, 26, 22, 200, P.MADERA))


def prop_estante(**_) -> str:
    """Un estante de pared (el origen es el medio de la tabla)."""
    return (rect(-140, 0, 280, 24, P.MADERA, r=4)
            + camino("M-110 24 L-110 70 L-70 24 Z", P.MADERA, ancho=P.TRAZO_FINO)
            + camino("M110 24 L110 70 L70 24 Z", P.MADERA, ancho=P.TRAZO_FINO))


def prop_reloj_bolsillo(**_) -> str:
    from .tito import reloj

    return reloj(40.0, 90)


def prop_pelota_espuma(color: str = P.NARANJA, **_) -> str:
    """La pelota de ESPUMA (Nerf): colores vivos, una franja, poros de distintos tamaños y un brillo:
    se tiene que ver blandita. Sin logo."""
    import random as _random

    rnd = _random.Random(7)
    poros = []
    while len(poros) < 34:
        x, y = rnd.uniform(-62, 62), rnd.uniform(-62, 62)
        if x * x + y * y < 60 * 60:
            poros.append(elipse(x, y, rnd.uniform(4, 9), rnd.uniform(3, 7), "#c4561a", borde=False))
    return (circulo(0, 0, 78, color)
            + camino("M-72 30 Q0 70 72 30 Q60 60 0 74 Q-60 60 -72 30 Z", "#d9661f", borde=False)   # sombra
            + rect(-74, -16, 148, 32, P.AMARILLO, borde=False)                                  # franja
            + "".join(poros)
            + circulo(0, 0, 78, "none")
            + elipse(-30, -40, 24, 14, "#ffe3c4", borde=False))


def prop_juego_mesa(**_) -> str:
    """Un juego de mesa abierto: tablero con casillas de colores alrededor, dados y fichas."""
    out = [camino("M-170 0 L0 -90 L170 0 L0 90 Z", "#e8f3d6")]
    colores = [P.ROJO, P.AZUL, P.VERDE, P.AMARILLO, P.VIOLETA, P.NARANJA]
    for k in range(6):   # casillas en el borde (en perspectiva)
        u0, u1 = k / 6, (k + 1) / 6
        for (ax, ay), (bx, by) in (((-170, 0), (0, -90)), ((0, 90), (170, 0))):
            x0, y0 = ax + (bx - ax) * u0, ay + (by - ay) * u0
            x1, y1 = ax + (bx - ax) * u1, ay + (by - ay) * u1
            out.append(camino(f"M{n(x0)} {n(y0)} L{n(x1)} {n(y1)} L{n(x1 * 0.8)} {n(y1 * 0.8)} "
                              f"L{n(x0 * 0.8)} {n(y0 * 0.8)} Z", colores[(k + (1 if ax else 0)) % 6], ancho=3))
    out.append(rect(-30, -24, 40, 40, P.BLANCO, r=6, ancho=4) + circulo(-20, -14, 4, P.CONTORNO, borde=False)
               + circulo(0, 6, 4, P.CONTORNO, borde=False))
    out.append(rect(30, -10, 36, 36, P.BLANCO, r=6, ancho=4) + circulo(48, 8, 4, P.CONTORNO, borde=False))
    for x, c in ((-80, P.ROJO), (90, P.AZUL)):   # fichas
        out.append(camino(f"M{x - 12} 30 L{x} -10 L{x + 12} 30 Z", c, ancho=4) + circulo(x, -12, 9, c, ancho=4))
    out.append(rect(-14, 34, 28, 22, P.VERDE, ancho=3) + camino("M-18 34 L0 20 L18 34 Z", P.ROJO, ancho=3))
    return "".join(out)


def prop_hamburguesa(**_) -> str:
    return (camino("M-120 30 Q-120 -90 0 -90 Q120 -90 120 30 Z", "#e0a050")
            + "".join(elipse(x, y, 7, 4, "#fff6dc", borde=False) for x, y in ((-50, -50), (0, -66), (45, -48), (-20, -30), (30, -24)))
            + camino("M-130 30 Q-110 50 -90 30 Q-70 50 -50 30 Q-30 50 -10 30 Q10 50 30 30 Q50 50 70 30 Q90 50 110 30 Q125 45 130 30 L130 44 L-130 44 Z", P.VERDE, ancho=4)
            + camino("M-110 44 L110 44 L60 74 L-60 74 Z", P.AMARILLO, ancho=4)
            + rect(-118, 56, 236, 40, "#7a4b2a", r=18)
            + camino("M-110 96 L110 96 Q110 130 0 130 Q-110 130 -110 96 Z", "#e0a050"))


def prop_chocolate(**_) -> str:
    out = [rect(-150, -70, 300, 140, "#6b3b1f", r=10)]
    for x in range(-150, 150, 60):
        for y in (-70, 0):
            out.append(rect(x + 6, y + 6, 48, 58, "#7d4826", r=6, ancho=4))
    out.append(camino("M30 -78 L160 -78 L160 78 L30 78 Q60 40 40 0 Q60 -40 30 -78 Z", P.ROJO))
    out.append(rect(70, -20, 70, 40, P.AMARILLO, r=6, ancho=4))
    return "".join(out)


def prop_galletitas(**_) -> str:
    out = []
    for k, y in enumerate((40, 0, -40)):
        out.append(elipse(0, y + 14, 100, 26, "#3d2314") + elipse(0, y, 100, 26, "#f4ead5", ancho=4)
                   + elipse(0, y - 12, 100, 26, "#3d2314"))
        for x in (-50, 0, 50):
            out.append(circulo(x, y - 14, 5, "#2a170d", borde=False))
    return "".join(out)


def prop_auto(color: str = P.ROJO, **_) -> str:
    return (camino("M-180 30 L-180 -20 Q-170 -40 -120 -44 L-70 -100 L80 -100 L130 -44 Q175 -40 180 -10 L180 30 Z", color)
            + camino("M-60 -90 L-20 -90 L-20 -46 L-100 -46 Z", "#9fe3ff", ancho=5)
            + camino("M0 -90 L70 -90 L110 -46 L0 -46 Z", "#9fe3ff", ancho=5)
            + circulo(-110, 34, 38, "#2b2b33") + circulo(-110, 34, 16, P.GRIS, ancho=4)
            + circulo(110, 34, 38, "#2b2b33") + circulo(110, 34, 16, P.GRIS, ancho=4)
            + rect(160, -20, 20, 16, P.AMARILLO, r=4, ancho=3))


def prop_telefono_disco(**_) -> str:
    return (camino("M-110 60 L-90 -30 L90 -30 L110 60 Z", "#2b2b33")
            + circulo(0, 18, 48, "#e8e3d8", ancho=4)
            + "".join(circulo(30 * math.cos(math.radians(a)), 18 + 30 * math.sin(math.radians(a)), 7, "#2b2b33", borde=False)
                      for a in range(-60, 240, 30))
            + camino("M-120 -40 Q-130 -90 -80 -90 L80 -90 Q130 -90 120 -40 L90 -50 L-90 -50 Z", "#2b2b33"))


def prop_radio(**_) -> str:
    return (rect(-130, -90, 260, 180, "#a0522d", r=40)
            + rect(-100, -60, 120, 120, "#e9d8a6", r=16, ancho=4)
            + "".join(f'<path d="M-90 {y} L10 {y}" stroke="#a0522d" stroke-width="6"/>' for y in range(-40, 50, 16))
            + circulo(70, -20, 26, "#e9d8a6", ancho=4) + circulo(70, 45, 18, "#e9d8a6", ancho=4)
            + f'<path d="M70 -20 L84 -34" {trazo(ancho=5)}/>')


def prop_consola(**_) -> str:
    return (rect(-150, -40, 300, 80, "#3d4250", r=14) + rect(-120, -24, 120, 14, "#2b2b33", r=4, borde=False)
            + circulo(100, 0, 12, P.ROJO, ancho=3)
            + f'<path d="M-60 40 Q-60 110 40 110" fill="none" {trazo(ancho=6)}/>'
            + g(prop_control(), 120, 130, escala=0.6))


def prop_primer_plano(texto: str = "casa", forma: int = 1, **_) -> str:
    """El primer plano como prop (lo agrega acciones.py; `texto` = el lugar, `forma` = el lado)."""
    return primer_plano(texto, -1 if forma < 0 else 1, abs(forma) // 2)


def prop_polvo(color: str = "#d9c7a8", **_) -> str:
    """Una nube de polvo (partícula de los golpes y las roturas): 3 bolas suaves, sin contorno."""
    return (circulo(-26, 6, 34, color, borde=False) + circulo(18, -8, 40, color, borde=False)
            + circulo(36, 18, 26, aclarar(color, 0.3), borde=False))


def prop_lineas_mov(color: str = "#ffffff", **_) -> str:
    """Líneas de movimiento DETRÁS de algo que vuela (mirando a +x): la rotación las alinea con la
    dirección. Blancas con borde, como en los dibujos animados."""
    out = []
    for dy, largo in ((-34, 150), (0, 210), (34, 140)):
        d = f"M-60 {dy} L{-60 - largo} {dy}"
        out.append(f'<path d="{d}" stroke="{P.CONTORNO}" stroke-width="15" stroke-linecap="round" opacity="0.55"/>'
                   f'<path d="{d}" stroke="{color}" stroke-width="8" stroke-linecap="round"/>')
    return "".join(out)


def prop_rayos(color: str = P.AMARILLO, **_) -> str:
    """Rayos de cómic (el gancho, 2026-11-16: "colores fuertes y mucho movimiento"): 16 rayos de dos colores
    fuertes alrededor del centro, detrás del objeto; girando se ven en movimiento."""
    out = []
    otro = P.NARANJA if color != P.NARANJA else P.ROJO
    for k in range(16):
        a0, a1 = math.radians(k * 22.5 - 9), math.radians(k * 22.5 + 9)
        r = 1400
        d = f"M0 0 L{r * math.cos(a0):.0f} {r * math.sin(a0):.0f} L{r * math.cos(a1):.0f} {r * math.sin(a1):.0f} Z"
        out.append(f'<path d="{d}" fill="{color if k % 2 else otro}"/>')
    return "".join(out) + circulo(0, 0, 230, aclarar(color, 0.55), borde=False)


def prop_destello(color: str = P.AMARILLO, **_) -> str:
    """Un destello de 4 puntas (el remate brilla)."""
    d = "M0 -90 Q10 -10 90 0 Q10 10 0 90 Q-10 10 -90 0 Q-10 -10 0 -90 Z"
    return (f'<path d="{d}" fill="{color}" stroke="{P.CONTORNO}" stroke-width="6" stroke-linejoin="round"/>'
            f'<path d="M0 -50 Q5 -5 50 0 Q5 5 0 50 Q-5 5 -50 0 Q-5 -5 0 -50 Z" fill="#ffffff"/>')


def _partes(texto: str) -> tuple[str, str]:
    a, _, b = str(texto or "").partition("|")
    return a.strip(), b.strip()


ANCHO_TEXTOS = 940   # Santi, 2026-11-15: ningún texto se sale de la pantalla (1080 menos los márgenes)


def tam_que_entra(texto: str, tam: float, ancho_max: float, minimo: float = 34) -> float:
    """El tamaño de letra más grande (hasta `tam`) con el que `texto` entra en `ancho_max` (medido con la
    fuente del canal y un 8 % de aire por el contorno)."""
    from .svg import ancho_texto

    while tam > minimo and ancho_texto(texto, int(tam)) * 1.08 > ancho_max:
        tam *= 0.94
    return max(minimo, tam)


def partir_en_dos(texto: str) -> tuple[str, str]:
    """El texto en dos líneas lo más parejas posible (por palabras)."""
    pal = texto.split()
    if len(pal) < 2:
        return texto, ""
    mejor = min(range(1, len(pal)), key=lambda k: abs(len(" ".join(pal[:k])) - len(" ".join(pal[k:]))))
    return " ".join(pal[:mejor]), " ".join(pal[mejor:])


def prop_rotulo(texto: str = "1974 · Budapest", **_) -> str:
    """Rótulo tipo noticiero (año · lugar), arriba a la izquierda (coordenadas de pantalla: va fijo)."""
    anio, _, lugar = str(texto).partition(" · ")
    if not lugar and not anio.strip().isdigit():
        anio, lugar = "", anio
    from .svg import ancho_texto

    w_a = 40 + ancho_texto(anio, 56) if anio else 0
    w_l = 50 + ancho_texto(lugar.upper(), 46) if lugar else 0
    out = ""
    if anio:
        out += rect(0, 0, w_a, 76, P.ROJO, r=6, ancho=5) + texto_con_borde(anio, w_a / 2, 54, 56, ancho_borde=6)
    if lugar:
        out += (rect(w_a, 0, w_l, 76, "#1d3557", r=6, ancho=5)
                + texto_con_borde(lugar.upper(), w_a + w_l / 2, 52, 46, ancho_borde=6))
    total = w_a + w_l
    if total > ANCHO_TEXTOS + 60:   # va desde x = 40: que no pase de 1040
        return g(out, 0, 0, escala=(ANCHO_TEXTOS + 60) / total)
    return out


def prop_dato(texto: str = "4 MILLONES|cubos vendidos", **_) -> str:
    """Un número gigante con qué es abajo, en una placa (fijo, arriba al centro)."""
    from .svg import ancho_texto

    num, que = _partes(texto)
    interior = ANCHO_TEXTOS - 80
    tam = tam_que_entra(num, 170, interior, minimo=90)
    lineas = [num]
    if ancho_texto(num, int(tam)) * 1.08 > interior:      # ni a 90 px entra: dos líneas
        lineas = [x for x in partir_en_dos(num) if x]
        tam = min(tam_que_entra(x, 150, interior, minimo=60) for x in lineas)
    tam_q = tam_que_entra(que.upper(), 48, interior, minimo=28) if que else 0
    w = min(ANCHO_TEXTOS, max(560, max(ancho_texto(x, int(tam)) for x in lineas) * 1.08 + 80))
    alto_num = tam * 1.05 * len(lineas)
    out = rect(-w / 2, -tam * 0.95, w, alto_num + tam * 0.55 + (60 if que else 0), "#fff6dc", r=28)
    for k, linea in enumerate(lineas):
        out += texto_con_borde(linea, 0, tam * 0.35 + k * tam * 1.05, int(tam), color=P.AMARILLO,
                               ancho_borde=tam * 0.12)
    if que:
        out += texto_con_borde(que.upper(), 0, tam * 0.35 + (len(lineas) - 1) * tam * 1.05 + 78, int(tam_q),
                               color=P.BLANCO, ancho_borde=8)
    return out


def prop_cita(texto: str = "«La cita»|Nombre, cargo", **_) -> str:
    """Tarjeta de cita: el texto en 2-4 líneas y abajo nombre y cargo (fijo, arriba al centro)."""
    cita, quien = _partes(texto)
    palabras, lineas, actual = cita.split(), [], ""
    for p_ in palabras:
        if len(actual) + len(p_) + 1 > 24 and actual:
            lineas.append(actual)
            actual = p_
        else:
            actual = (actual + " " + p_).strip()
    if actual:
        lineas.append(actual)
    lineas = lineas[:4]
    alto = 90 + 62 * len(lineas) + (70 if quien else 0)
    out = rect(-470, 0, 940, alto, "#fffdf6", r=26) + rect(-470, 0, 22, alto, P.ROJO, borde=False)
    tam_c = min([tam_que_entra(l, 50, 860, minimo=30) for l in lineas] or [50])
    for k, l in enumerate(lineas):
        out += texto_con_borde(l, 0, 86 + 62 * k, int(tam_c), color="#1f1a24", borde="#fffdf6", ancho_borde=2)
    if quien:
        out += texto_con_borde("— " + quien.upper(), 0, 86 + 62 * len(lineas) + 30,
                               int(tam_que_entra("— " + quien.upper(), 34, 860, minimo=22)), color=P.ROJO,
                               borde="#fffdf6", ancho_borde=2)
    return out


def prop_cartel_comic(texto: str = "¡BOOM!", **_) -> str:
    """Estallido tipo cómic con una palabra (en el golpe)."""
    import math as _m

    puntas = []
    for k in range(24):
        r_ = 230 if k % 2 == 0 else 160
        a = _m.radians(k * 15)
        puntas.append(f"{n(_m.cos(a) * r_ * 1.25)} {n(_m.sin(a) * r_ * 0.8)}")
    tam = int(tam_que_entra(texto, 92, 360, minimo=40))
    return (f'<path d="M{" L".join(puntas)} Z" fill="{P.AMARILLO}" stroke="{P.CONTORNO}" stroke-width="10" '
            f'stroke-linejoin="round"/>' + texto_con_borde(texto, 0, tam * 0.35, tam, color=P.ROJO, ancho_borde=12))


def prop_tito_reaccion(forma: int = 0, **_) -> str:
    """Tito en una ventanita redonda reaccionando (0 sorprendido, 1 riéndose, 2 señalando)."""
    from . import tito as _tito

    cara = _tito.tito_cara_svg()
    icono = (texto_con_borde("!", 108, -60, 110, color=P.AMARILLO, ancho_borde=12) if forma == 0 else
             texto_con_borde("JA", 112, -70, 64, color=P.AMARILLO, ancho_borde=10) if forma == 1 else
             f'<path d="M80 40 L170 40 L150 15 M170 40 L150 65" fill="none" {trazo(ancho=14)}/>')
    return circulo(0, 0, 118, "#7cc6ee", ancho=10) + g(cara, 0, 26, escala=0.62) + icono


def _dedo(largo: float, ancho: float, piel: str, nudillos: int = 2) -> str:
    """Un dedo visto desde arriba, apuntando hacia arriba desde (0, 0): falange redondeada, uña y los pliegues
    de los nudillos."""
    r = ancho / 2
    d = (f"M{n(-r)} 0 L{n(-r)} {n(-largo + r)} A{n(r)} {n(r)} 0 0 1 {n(r)} {n(-largo + r)} "
         f"L{n(r)} 0 Z")
    out = camino(d, piel, ancho=5)
    uña = rect(-r * 0.62, -largo + r * 0.35, r * 1.24, largo * 0.26, aclarar(piel, 0.45), r=r * 0.55, ancho=3)
    pliegues = ""
    for k in range(1, nudillos + 1):
        y = -largo * (0.30 * k)
        pliegues += (f'<path d="M{n(-r * 0.55)} {n(y)} Q0 {n(y - 5)} {n(r * 0.55)} {n(y)}" fill="none" '
                     f'stroke="{oscurecer(piel, 0.28)}" stroke-width="3.5" stroke-linecap="round"/>')
    return out + uña + pliegues


def _mano_de_antes(forma: int = 1, color: str = "") -> str:
    """La mano de antes (hasta el OK de Santi a la nueva: animacion.uso_manos)."""
    s_ = 1 if int(forma or 1) < 0 else -1
    piel, manga = P.PIEL[0], color if isinstance(color, str) and color.startswith("#") else P.AZUL
    sombra = oscurecer(piel, 0.18)
    dedos = ""
    for dx, largo, ang in ((22, 74, 4), (0, 84, 0), (-22, 78, -4), (-42, 60, -10)):
        dedos += g(_dedo(largo, 21 if largo > 62 else 18, piel), s_ * dx, -118, rot=s_ * ang)
    palma = camino("M-56 -36 C-62 -80 -58 -118 -40 -126 L40 -126 C58 -118 62 -80 56 -36 Z", piel, ancho=5)
    nudillos = "".join(elipse(s_ * dx, -122, 9, 5, sombra, borde=False) for dx in (22, 0, -22, -42))
    tendones = "".join(f'<path d="M{s_ * dx} -50 L{s_ * dx * 1.05} -110" stroke="{sombra}" stroke-width="3" '
                       f'stroke-linecap="round" opacity="0.6"/>' for dx in (18, 0, -18))
    pulgar = g(_dedo(66, 24, piel, nudillos=1), s_ * 36, -52, rot=s_ * 42)
    manga_svg = (rect(-60, -40, 120, 230, manga, r=26) + rect(-64, -44, 128, 28, aclarar(manga, 0.3), r=10, ancho=5)
                 + f'<path d="M-30 -10 L-26 180 M30 -10 L26 180" stroke="{oscurecer(manga, 0.2)}" stroke-width="4"/>')
    return manga_svg + pulgar + palma + tendones + nudillos + dedos


def prop_mano(forma: int = 1, color: str = "", fase: float = 0.0, manga: str = "", detalle: bool = False, **_) -> str:
    if not detalle:
        return _mano_de_antes(forma, color)
    return _mano_detalle(forma, color, fase, manga)


def _mano_detalle(forma: int = 1, color: str = "", fase: float = 0.0, manga: str = "") -> str:
    """Una mano vista desde arriba con la manga (plano de manos de la biblioteca de escenas): entra desde abajo;
    `forma` -1 = la izquierda, 1 = la derecha. Santi, 2026-11-16 ("manos con más detalle: sombras, arrugas en los
    dedos, puño de la camisa o manga de la época; no las de madera gigantes"): la palma con su lado en sombra, tres
    arrugas en cada nudillo, uñas con su lúnula, el puño blanco de la camisa con su botón y la manga del color de la
    ropa (`color`). `fase` 0..1 = cuánto agarra (los dedos se doblan sobre el objeto)."""
    s_ = 1 if int(forma or 1) < 0 else -1
    agarre = max(0.0, min(1.0, float(fase or 0.0)))
    piel, manga = P.PIEL[0], manga or (color if isinstance(color, str) and color.startswith("#") else "") or "#3d4f7a"
    sombra, profunda = oscurecer(piel, 0.16), oscurecer(piel, 0.32)
    dedos = ""
    for dx, largo, ang in ((22, 74, 4), (0, 84, 0), (-22, 78, -4), (-42, 60, -10)):
        l_ = largo * (1 - 0.42 * agarre)          # al agarrar, el dedo se dobla: se ve más corto desde arriba
        dedo = _dedo(l_, 21 if largo > 62 else 18, piel)
        arrugas = "".join(f'<path d="M{n(-6 + k * 3)} {n(-l_ * 0.62 - k * 3)} q 6 -2 12 0" fill="none" '
                          f'stroke="{profunda}" stroke-width="2" stroke-linecap="round" opacity="0.55"/>' for k in range(3))
        dedos += g(dedo + arrugas, s_ * dx, -118, rot=s_ * ang * (1 - agarre))
    palma = camino("M-56 -36 C-62 -80 -58 -118 -40 -126 L40 -126 C58 -118 62 -80 56 -36 Z", piel, ancho=5)
    lado_sombra = camino(f"M{s_ * -56} -36 C{s_ * -62} -80 {s_ * -58} -118 {s_ * -40} -126 L{s_ * -22} -126 "
                         f"C{s_ * -36} -100 {s_ * -38} -70 {s_ * -30} -36 Z", sombra, borde=False)
    nudillos = "".join(elipse(s_ * dx, -122, 9, 5, sombra, borde=False) for dx in (22, 0, -22, -42))
    tendones = "".join(f'<path d="M{s_ * dx} -50 L{s_ * dx * 1.05} -110" stroke="{sombra}" stroke-width="3" '
                       f'stroke-linecap="round" opacity="0.6"/>' for dx in (18, 0, -18))
    pulgar = g(_dedo(66, 24, piel, nudillos=1), s_ * 36, -52, rot=s_ * (42 + 30 * agarre))
    puño = (rect(-62, -46, 124, 40, "#f4f1ea", r=12, ancho=5) + circulo(s_ * -38, -26, 6, "#d8d2c4", ancho=3)
            + f'<path d="M-58 -14 L58 -14" stroke="{oscurecer("#f4f1ea", 0.15)}" stroke-width="3"/>')
    manga_svg = (rect(-66, -18, 132, 230, manga, r=26)
                 + camino(f"M{s_ * 66} -10 L{s_ * 66} 210 L{s_ * 30} 210 L{s_ * 40} -10 Z", oscurecer(manga, 0.22),
                          borde=False)
                 + f'<path d="M-30 10 L-26 190 M30 10 L26 190" stroke="{oscurecer(manga, 0.3)}" stroke-width="4"/>')
    return manga_svg + puño + pulgar + palma + lado_sombra + tendones + nudillos + dedos


def prop_apreton(manga: str = "", color: str = "", forma: int = 1, **_) -> str:
    """Dos manos que se dan un apretón, vistas DE COSTADO (Santi, 2026-11-16: "puño contra puño no; la palma de una
    contra la palma de la otra, los dedos envolviendo la mano del otro y los pulgares cruzados arriba"). La de la
    izquierda (manga `manga`) muestra el dorso con sus cuatro dedos doblados sobre la mano de la derecha (manga
    `color`); los dedos de la derecha la envuelven por atrás y se asoman abajo; los dos pulgares se cruzan arriba.
    El centro (0, 0) es donde se juntan las palmas. `forma` 0 = mangas cortas (para el plano medio, sobre los brazos
    de los personajes)."""
    m_izq = manga if isinstance(manga, str) and manga.startswith("#") else "#3d4f7a"
    m_der = color if isinstance(color, str) and color.startswith("#") else "#5a3d2b"
    largo = 420 if int(forma if forma is not None else 1) else 110
    p1, p2 = P.PIEL[0], P.PIEL[1]
    s1, s2 = oscurecer(p1, 0.16), oscurecer(p2, 0.16)
    blanco = "#f4f1ea"

    def manga_(x0: float, y0: float, alto: float, c: str, lado: int) -> str:
        x = x0 if lado > 0 else x0 - largo
        return (rect(x, y0, largo, alto, c, r=22)
                + camino(f"M{n(x + 6)} {n(y0 + alto * 0.68)} L{n(x + largo - 6)} {n(y0 + alto * 0.68)} "
                         f"L{n(x + largo - 6)} {n(y0 + alto - 6)} L{n(x + 6)} {n(y0 + alto - 6)} Z",
                         oscurecer(c, 0.22), borde=False)
                + f'<path d="M{n(x + 20)} {n(y0 + alto * 0.3)} L{n(x + largo - 20)} {n(y0 + alto * 0.3)}" '
                  f'stroke="{oscurecer(c, 0.3)}" stroke-width="4" opacity="0.6"/>')

    def puno(x: float, y0: float, alto: float, lado: int) -> str:
        return (rect(x - 26, y0, 52, alto, blanco, r=12, ancho=5)
                + circulo(x + lado * 4, y0 + alto * 0.62, 6, "#d8d2c4", ancho=3))

    out = []
    # la de la DERECHA, atrás: manga, puño, la mano (su palma contra la otra) y la punta de sus dedos asomando abajo
    out.append(manga_(170, -72, 150, m_der, 1))
    out.append(puno(160, -64, 136, 1))
    out.append(camino("M150 -60 C90 -70 30 -64 -6 -50 C-14 -10 -14 30 -6 64 C40 74 100 74 150 66 Z", p2, ancho=5))
    out.append(camino("M150 30 C100 40 40 44 -6 40 L-6 64 C40 74 100 74 150 66 Z", s2, borde=False))
    for cx, cy, rot in ((-92, 60, 20), (-62, 70, 10), (-32, 74, 0)):
        out.append(g(elipse(0, 0, 17, 13, p2, ancho=4), cx, cy, rot=rot))
    # la de la IZQUIERDA, adelante: manga, puño y el dorso de la mano
    out.append(manga_(-170, -68, 144, m_izq, -1))
    out.append(puno(-160, -60, 128, -1))
    # el dorso: angosto en la muñeca, ancho y abombado en los nudillos (no una tabla)
    out.append(camino("M-150 -46 C-96 -52 -36 -72 26 -64 C62 -58 78 -30 78 0 C78 30 62 56 28 62 "
                      "C-34 68 -94 56 -150 50 Z", p1, ancho=5))
    out.append(camino("M-150 24 C-94 32 -30 42 40 40 C66 38 76 22 78 6 C78 30 62 56 28 62 C-34 68 -94 56 -150 50 Z",
                      s1, borde=False))
    out.append(f'<path d="M-128 -42 C-80 -50 -24 -66 30 -56" fill="none" stroke="{aclarar(p1, 0.45)}" '
               f'stroke-width="8" stroke-linecap="round" opacity="0.8"/>')
    out.append("".join(f'<path d="M-118 {n(y * 0.4)} Q-40 {n(y * 0.7)} 40 {y}" fill="none" stroke="{s1}" '
                       f'stroke-width="3.5" stroke-linecap="round" opacity="0.5"/>' for y in (-30, -6, 18)))
    out.append(f'<path d="M-140 -10 q 6 10 0 22" fill="none" stroke="{s1}" stroke-width="3" opacity="0.6"/>')
    # sus cuatro dedos doblados por encima de la mano de la derecha (se ven el dorso y las uñas)
    for (x, y, largo_d, ancho_d, rot) in ((54, -36, 74, 24, 104), (62, -12, 82, 24, 100), (62, 12, 78, 23, 97),
                                          (54, 36, 62, 20, 94)):
        out.append(g(_dedo(largo_d, ancho_d, p1), x, y, rot=rot))
    for y in (-36, -12, 12, 36):          # los nudillos
        out.append(elipse(54 if abs(y) > 20 else 60, y, 10, 11, s1, borde=False))
    # los pulgares cruzados arriba: el de la izquierda va hacia la derecha y el de la derecha, por encima, hacia la izq.
    out.append(g(_dedo(112, 28, p1, nudillos=1), -14, -40, rot=60))
    out.append(g(_dedo(116, 28, p2, nudillos=1), 110, -36, rot=-58))
    return "".join(out)


def prop_mostrador(**_) -> str:
    """El mostrador de la tienda (el vendedor queda detrás)."""
    return (rect(-200, -120, 400, 240, "#8a5a2b", r=10) + rect(-215, -140, 430, 34, "#a8714a", r=8)
            + rect(-150, -70, 300, 120, "#9c6a3d", r=6, ancho=4))


def prop_fuego(**_) -> str:
    """Llamas del despegue (debajo del objeto que sube)."""
    return (camino("M-70 -20 Q-90 90 0 220 Q90 90 70 -20 Q40 40 0 -10 Q-40 40 -70 -20 Z", P.NARANJA)
            + camino("M-40 -10 Q-50 70 0 150 Q50 70 40 -10 Q20 30 0 0 Q-20 30 -40 -10 Z", P.AMARILLO, ancho=5))


def prop_reloj_gigante(fase: float = 0.0, forma: int = -1, **_) -> str:
    """El reloj gigante del viaje en el tiempo (marca del canal, Santi 2026-11-15): esfera antigua con números
    romanos y las agujas girando a toda velocidad, hacia ATRÁS (`forma` -1, al pasado) o hacia adelante (1).
    `fase` 0..1 = cuánto avanzó el viaje."""
    sentido = -1 if int(forma or -1) < 0 else 1
    out = [circulo(0, 0, 400, "#3a2a1c", ancho=14), circulo(0, 0, 370, "#f3e6c4", ancho=8),
           circulo(0, 0, 330, "none", ancho=3)]
    romanos = ("XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI")
    for k in range(60):
        ang = math.radians(k * 6)
        r0 = 345 if k % 5 else 315
        out.append(f'<path d="M{n(math.sin(ang) * r0)} {n(-math.cos(ang) * r0)} L{n(math.sin(ang) * 362)} '
                   f'{n(-math.cos(ang) * 362)}" stroke="{P.CONTORNO}" stroke-width="{8 if k % 5 == 0 else 4}"/>')
    for k, rom in enumerate(romanos):
        ang = math.radians(k * 30)
        out.append(texto_con_borde(rom, math.sin(ang) * 262, -math.cos(ang) * 262 + 22, 64, color="#3a2a1c",
                                   borde="#f3e6c4", ancho_borde=2))
    vueltas = float(fase or 0) * 7.0      # la grande da 7 vueltas; la chica, una
    minutero = sentido * vueltas * 360 + 0
    horario = sentido * vueltas * 30 + 300
    for ang, largo, ancho in ((horario, 190, 26), (minutero, 300, 16)):
        rad = math.radians(ang)
        out.append(f'<path d="M0 0 L{n(math.sin(rad) * largo)} {n(-math.cos(rad) * largo)}" stroke="{P.CONTORNO}" '
                   f'stroke-width="{ancho}" stroke-linecap="round"/>')
    # estela de la aguja grande (se ve que gira rapidísimo)
    for k in range(1, 5):
        rad = math.radians(minutero - sentido * k * 9)
        out.append(f'<path d="M0 0 L{n(math.sin(rad) * 290)} {n(-math.cos(rad) * 290)}" stroke="{P.CONTORNO}" '
                   f'stroke-width="{16 - 3 * k}" stroke-linecap="round" opacity="{round(0.35 - 0.07 * k, 2)}"/>')
    out.append(circulo(0, 0, 30, P.AMARILLO, ancho=8))
    return "".join(out)


def odometro(valor: float, tam: int = 200) -> str:
    """El año como cuentakilómetros (viaje en el tiempo): una cajita por dígito; el último rueda."""
    v = max(0.0, float(valor))
    entero = int(math.floor(v))
    frac = v - entero
    txt = str(entero)
    bw, bh = tam * 0.66, tam * 1.0
    total = bw * len(txt) + 10 * (len(txt) - 1)
    x0 = -total / 2
    out = [rect(x0 - 24, -bh / 2 - 24, total + 48, bh + 48, "#2a2420", r=22, ancho=10)]
    for k, ch in enumerate(txt):
        x = x0 + k * (bw + 10)
        out.append(rect(x, -bh / 2, bw, bh, "#111014", r=10, ancho=5))
        cx = x + bw / 2
        if k == len(txt) - 1 and frac > 0.02:   # el último dígito rodando hacia el siguiente
            sig = str((int(ch) + 1) % 10)
            cid = f"odo{entero}_{int(frac * 100)}"
            out.append(f'<clipPath id="{cid}"><rect x="{n(x)}" y="{n(-bh / 2)}" width="{n(bw)}" height="{n(bh)}"/>'
                       f'</clipPath><g clip-path="url(#{cid})">'
                       + texto_con_borde(ch, cx, tam * 0.36 + frac * bh, tam, color="#ffffff", ancho_borde=0)
                       + texto_con_borde(sig, cx, tam * 0.36 + (frac - 1) * bh, tam, color="#ffffff", ancho_borde=0)
                       + "</g>")
        else:
            out.append(texto_con_borde(ch, cx, tam * 0.36, tam, color="#ffffff", ancho_borde=0))
    out.append(f'<rect x="{n(x0 - 10)}" y="-4" width="{n(total + 20)}" height="8" fill="#000000" opacity="0.35"/>')
    return "".join(out)


COLORES_CUBO = ("#ffffff", "#ffd23f", "#e63946", "#f59a3a", "#3a86ff", "#2a9d48")


def prop_cubo_rubik(fase: float = 1.0, **_) -> str:
    """El cubo de Rubik en perspectiva (3 caras de 3×3). `fase` 0 = mezclado, 1 = resuelto: cada cuadradito
    pasa a su color a medida que sube la fase (se resuelve solo)."""
    import random as _r

    rnd = _r.Random(7)
    fase = max(0.0, min(1.0, float(fase or 0)))
    out = []
    caras = [((-86, -50), (86, -50), (86, 50), 0),       # arriba: origen, eje u, eje v, color resuelto
             ((-86, -50), (86, 50), (0, 100), 2),        # izquierda
             ((0, 0), (86, -50), (0, 100), 4)]           # derecha
    for (ox, oy), (ux, uy), (vx, vy), resuelto in caras:
        for a in range(3):
            for b in range(3):
                mezcla = rnd.choice([c for c in range(6) if c != resuelto])
                umbral = rnd.random()
                color = COLORES_CUBO[resuelto if fase >= umbral else mezcla]
                x0, y0 = ox + ux * a / 3 + vx * b / 3, oy + uy * a / 3 + vy * b / 3
                pts = [(x0, y0), (x0 + ux / 3, y0 + uy / 3), (x0 + ux / 3 + vx / 3, y0 + uy / 3 + vy / 3),
                       (x0 + vx / 3, y0 + vy / 3)]
                d = "M" + " L".join(f"{n(x)} {n(y)}" for x, y in pts) + " Z"
                out.append(f'<path d="{d}" fill="{color}" stroke="{P.CONTORNO}" stroke-width="7" stroke-linejoin="round"/>')
    return "".join(out)


def fondo_mesa_arriba(semilla: int = 14) -> str:
    """Una mesa de madera vista desde arriba que llena el cuadro (plano cenital de las manos trabajando)."""
    p = [rect(0, 0, W, H, "#b07a4a", borde=False)]
    for k in range(0, W, 180):
        p.append(f'<path d="M{k} 0 L{k} {H}" stroke="#8a5a32" stroke-width="6"/>')
    rnd = random.Random(semilla)
    for _ in range(40):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        p.append(f'<path d="M{n(x)} {n(y)} q 30 -8 60 0" fill="none" stroke="#7a4e2a" stroke-opacity="0.35" stroke-width="3"/>')
    for x, y, r_ in ((150, 520, 18), (930, 1500, 14), (870, 420, 10)):     # piezas sueltas y un tornillo
        p.append(circulo(x, y, r_, P.GRIS, ancho=4))
    p.append(rect(80, 1650, 260, 180, "#f4ecd6", r=8, ancho=5) + f'<path d="M110 1700 L300 1700 M110 1740 L280 1740 M110 1780 '
             f'L250 1780" stroke="#9aa0ab" stroke-width="5"/>')     # un papel con notas
    return "".join(p)


FONDOS["mesa_arriba"] = fondo_mesa_arriba


def icono_pausa() -> str:
    """El "⏸" de la pausa del locutor (dos barras), centrado en (0, 0)."""
    return (circulo(0, 0, 70, "#ffffff", ancho=P.TRAZO_FINO)
            + rect(-30, -36, 20, 72, P.CONTORNO, r=4, borde=False)
            + rect(10, -36, 20, 72, P.CONTORNO, r=4, borde=False))


PROPS = {"reloj_gigante": prop_reloj_gigante, "mano": prop_mano, "mostrador": prop_mostrador, "fuego": prop_fuego, "cubo_rubik": prop_cubo_rubik,
         "rotulo": prop_rotulo, "dato": prop_dato, "cita": prop_cita, "cartel_comic": prop_cartel_comic,
         "tito_reaccion": prop_tito_reaccion, "primer_plano": prop_primer_plano, "polvo": prop_polvo, "lineas_mov": prop_lineas_mov,
         "destello": prop_destello, "pelota_espuma": prop_pelota_espuma, "juego_mesa": prop_juego_mesa, "hamburguesa": prop_hamburguesa,
         "chocolate": prop_chocolate, "galletitas": prop_galletitas, "auto": prop_auto,
         "telefono_disco": prop_telefono_disco, "radio": prop_radio, "consola": prop_consola,
         "tele": prop_tele, "cuadro": prop_cuadro, "mesa": prop_mesa, "estante": prop_estante,
         "reloj_bolsillo": prop_reloj_bolsillo, "pelota": prop_pelota, "lampara": prop_lampara, "ventana": prop_ventana,
         "pedazo": prop_pedazo, "martillo": prop_martillo, "jarron": prop_jarron,
         "microfono": prop_microfono, "cartel": prop_cartel, "flecha": prop_flecha, "pregunta": prop_pregunta,
         "exclamacion": prop_exclamacion, "moneda": prop_moneda, "lamparita": prop_lamparita,
         "nube": prop_nube, "botella": prop_botella, "lata": prop_lata, "caja": prop_caja,
         "zapatilla": prop_zapatilla, "billete": prop_billete, "bolsa_plata": prop_bolsa_plata,
         "grafico_sube": prop_grafico_sube, "grafico_baja": prop_grafico_baja,
         "trofeo": prop_trofeo, "megafono": prop_megafono, "calendario": prop_calendario,
         "control": prop_control, "engranaje": prop_engranaje, "camion": prop_camion,
         "celular": prop_celular, "corona": prop_corona, "cohete": prop_cohete,
         "idea_fallida": prop_bombilla_rota, "rayos": prop_rayos,
         "caja_registradora": prop_caja_registradora, "papel_firma": prop_papel_firma, "lapicera": prop_lapicera,
         "apreton": prop_apreton}


def _palabras(t: str) -> set[str]:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return {w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 3}


def parecido(nombre: str, opciones, descripcion: str = "", descripciones: dict | None = None,
             defecto: str | None = None) -> str:
    """La opción más parecida a `nombre` (Santi, 2026-11-16: "un objeto que no está nunca puede frenar el
    video"): primero las palabras en común (del nombre y de qué es), después el parecido de las letras."""
    import difflib

    opciones = [o for o in opciones if o]
    if not opciones:
        return defecto or ""
    buscado = _palabras(nombre.replace("_", " ") + " " + descripcion)
    descripciones = descripciones or {}

    def puntaje(o):
        suyas = _palabras(o.replace("_", " ") + " " + str(descripciones.get(o) or ""))
        comunes = len(buscado & suyas) + sum(1 for b in buscado for s in suyas if b != s and len(b) >= 4
                                              and (b.startswith(s[:4]) or s.startswith(b[:4])))
        return comunes, difflib.SequenceMatcher(None, nombre, o).ratio()

    mejor = max(opciones, key=puntaje)
    if puntaje(mejor) == (0, 0.0) or (puntaje(mejor)[0] == 0 and puntaje(mejor)[1] < 0.6 and defecto):
        return defecto if defecto in opciones else mejor
    return mejor


# Lo que el código puede poner solo (efectos del render y piezas de las escenas): no reemplazan a un objeto.
NO_REEMPLAZO = ("polvo", "lineas_mov", "destello", "primer_plano", "rayos", "pedazo", "microfono", "rotulo", "cita", "dato",
                "cartel_comic", "tito_reaccion", "reloj_gigante",
                # regla de Así Nació: martillo y engranajes solo si la frase habla de un taller o una máquina
                "martillo", "engranaje")


def prop_parecido(nombre: str, descripcion: str = "") -> str:
    """El objeto existente (biblioteca de siempre o dibujo guardado) más parecido; si no se parece a nada, una caja."""
    from . import dibujos

    guardados = dibujos.biblioteca()
    opciones = [p for p in PROPS if p not in NO_REEMPLAZO] + list(guardados)
    return parecido(nombre, opciones, descripcion, guardados, defecto="caja")


# Desde qué año existe cada objeto de la biblioteca (Santi, 2026-11-16: "hay monitores de computadora en escenas de
# 1938 y 1958"): nunca aparece en una escena anterior. Los que no están (botella, caja, mesa, moneda…) existen siempre.
ANIO_DESDE = {
    "auto": 1886, "camion": 1896, "celular": 1983, "consola": 1972, "control": 1956, "cohete": 1926,
    "cubo_rubik": 1974, "hamburguesa": 1900, "lamparita": 1879, "idea_fallida": 1879, "megafono": 1878,
    "microfono": 1876, "radio": 1920, "tele": 1936, "telefono_disco": 1919, "zapatilla": 1916,
    "pelota_espuma": 1969, "lata": 1810, "grafico_sube": 1786, "grafico_baja": 1786, "chocolate": 1847,
    "galletitas": 1850, "juego_mesa": 1850, "calendario": 1582, "billete": 1661, "bolsa_plata": 1600,
    "reloj_bolsillo": 1600, "cartel": 1800, "trofeo": 1850,
}


def existe_en(nombre: str, anio: int) -> bool:
    """¿El objeto ya existía en `anio`? (0 = hoy). Un dibujo guardado con su `anio_desde` también cuenta."""
    if not anio:
        return True
    desde = ANIO_DESDE.get(nombre)
    if desde is None:
        from . import dibujos

        desde = dibujos.anio_desde(nombre)
    return not desde or anio >= desde


def es_prop(nombre: str) -> bool:
    """De la biblioteca de siempre o un dibujo guardado (dibujos.py, 2026-11-15)."""
    from . import dibujos

    return nombre in PROPS or dibujos.svg_de(nombre) is not None


def prop(nombre: str, **params) -> str:
    from . import dibujos

    if nombre in dibujos.reemplazos():    # un dibujo de código redibujado con detalle (Santi, 2026-11-16)
        svg_ = dibujos.svg_de(nombre)
        if svg_ is not None:
            return svg_
    f = PROPS.get(nombre)
    if f is None:
        from . import dibujos

        svg_ = dibujos.svg_de(nombre)
        if svg_ is not None:
            return svg_
        raise ValueError(f"Prop desconocido: {nombre!r} (hay {', '.join(sorted(PROPS))})")
    return f(**params)
