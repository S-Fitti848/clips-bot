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


def fondo_fabrica(semilla: int = 5) -> str:
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


def fondo_tienda(semilla: int = 6) -> str:
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
    p.append(g(prop_cartel("OFERTA", P.AMARILLO), 860, 150, escala=0.7))
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


def fondo_casa(semilla: int = 8) -> str:
    """El living de una casa: pared con papel, ventana, cuadro, sillón y alfombra (sin lámpara: la
    lámpara es un prop, así se puede romper)."""
    p = [rect(0, 0, W, H, "#f7d9b5", borde=False)]
    for x in range(0, W, 120):   # papel a rayas
        p.append(rect(x, 0, 60, H * 0.72, "#f1cda4", borde=False))
    p.append(rect(0, H * 0.72, W, H * 0.28, "#b98a5e", borde=False))
    p.append(f'<path d="M0 {n(H * 0.72)} L{W} {n(H * 0.72)}" {trazo()}/>')
    p.append(rect(0, H * 0.70, W, 30, P.BLANCO))                     # zócalo
    p.append(elipse(W / 2, H * 0.86, 420, 90, "#d9534f", ancho=P.TRAZO_FINO))   # alfombra
    p.append(elipse(W / 2, H * 0.86, 340, 62, "#f0ad4e", borde=False))
    p.append(rect(120, 300, 300, 230, P.BLANCO, r=6))                # cuadro
    p.append(camino("M150 500 L240 390 L300 450 L340 410 L390 500 Z", P.VERDE, ancho=P.TRAZO_FINO))
    # sillón
    p.append(rect(560, 1050, 460, 200, P.VIOLETA, r=40))
    p.append(rect(530, 1150, 520, 160, P.VIOLETA, r=40))
    p.append(rect(560, 1180, 460, 60, "#a78bfa", r=20, ancho=P.TRAZO_FINO))
    p.append(rect(560, 1300, 30, 60, P.MADERA) + rect(990, 1300, 30, 60, P.MADERA))
    return "".join(p)


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


FONDOS = {"casa": fondo_casa, "taller": fondo_taller, "cielo": fondo_cielo, "ciudad": fondo_ciudad, "oficina": fondo_oficina,
          "globo": fondo_globo, "mapa": fondo_globo, "fabrica": fondo_fabrica,
          "tienda": fondo_tienda, "escenario": fondo_escenario}


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


# ---- props genéricos del canal de marcas (2026-11-14) -----------------------------------------
# Productos SIN marca dibujada: la etiqueta lleva, como mucho, un texto en la fuente común del canal
# (nunca un logo ni la tipografía de la marca). El color lo pone quien llama (paleta del canal).

def _etiqueta(texto: str, y: float, ancho: float, tam: int = 40) -> str:
    if not texto:
        return ""
    tam = min(tam, int(ancho * 1.6 / max(1, len(texto))))
    return texto_con_borde(texto[:14], 0, y, max(18, tam), color=P.CONTORNO, borde=P.BLANCO,
                           ancho_borde=5)


def prop_botella(texto: str = "", color: str = P.ROJO, **_) -> str:
    return (camino("M-26 -230 L26 -230 L26 -170 Q80 -130 80 -60 L80 200 Q80 230 50 230 L-50 230 "
                   "Q-80 230 -80 200 L-80 -60 Q-80 -130 -26 -170 Z", color)
            + rect(-30, -262, 60, 36, P.GRIS_OSCURO, r=6)
            + rect(-80, -10, 160, 110, P.BLANCO, ancho=P.TRAZO_FINO)
            + _etiqueta(texto, 58, 150)
            + camino("M-50 -100 Q-58 -40 -54 40", borde=True, ancho=10, color="#ffffff"))


def prop_lata(texto: str = "", color: str = P.AZUL, **_) -> str:
    return (rect(-80, -150, 160, 300, color, r=18)
            + elipse(0, -150, 80, 18, P.GRIS)
            + elipse(0, -150, 22, 6, P.GRIS_OSCURO, borde=False)
            + rect(-80, -50, 160, 100, P.BLANCO, ancho=P.TRAZO_FINO)
            + _etiqueta(texto, 14, 150))


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


def icono_pausa() -> str:
    """El "⏸" de la pausa del locutor (dos barras), centrado en (0, 0)."""
    return (circulo(0, 0, 70, "#ffffff", ancho=P.TRAZO_FINO)
            + rect(-30, -36, 20, 72, P.CONTORNO, r=4, borde=False)
            + rect(10, -36, 20, 72, P.CONTORNO, r=4, borde=False))


PROPS = {"tele": prop_tele, "cuadro": prop_cuadro, "mesa": prop_mesa, "estante": prop_estante,
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
         "idea_fallida": prop_bombilla_rota}


def prop(nombre: str, **params) -> str:
    f = PROPS.get(nombre)
    if f is None:
        raise ValueError(f"Prop desconocido: {nombre!r} (hay {', '.join(sorted(PROPS))})")
    return f(**params)
