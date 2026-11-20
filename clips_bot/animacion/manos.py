"""Manos con dedos para todos los personajes y Tito (Santi, 2026-11-20: "manos con todos los dedos: señalar con el
índice estirado y los demás doblados; agarrar con los dedos cerrando sobre el objeto").

La mano sale de la muñeca (x, y) en la dirección del antebrazo (`ang`, grados en la pantalla: 0 = a la derecha, 90 =
hacia abajo). Formas:

    abierta   la palma con los 4 dedos estirados y el pulgar (festejar, explicar, la mano en la cara)
    relajada  los dedos un poco doblados (los brazos al costado)
    puno      el puño cerrado con los nudillos (determinado, golpear la mesa)
    senala    el puño con el índice estirado y el pulgar encima
    agarra    los dedos cerrados en C: lo que agarra se dibuja encima y `dedos_encima` cierra los dedos sobre el
              objeto (se dibujan DESPUÉS del objeto)

Todo se dibuja en dos pasadas (primero los contornos, después el relleno) para que palma y dedos queden unidos sin
rayas adentro.
"""
from __future__ import annotations

import math

from . import paleta as P
from .svg import g, n

FORMAS = ("abierta", "relajada", "puno", "senala", "agarra")
_CONTORNO = 6.0


def _dedos(forma: str) -> list[tuple[list[tuple[float, float]], float]]:
    """Las poligonales de los dedos (y el pulgar) con su ancho, en el marco de la mano: la muñeca en (0, 0), los dedos
    hacia +x, el pulgar hacia -y."""
    if forma == "abierta":
        return [([(30, y0), (52, y0 * 1.25), (66, y0 * 1.45)], 11) for y0 in (-13, -4.5, 4.5, 13)] + \
               [([(10, -16), (22, -30), (34, -38)], 12)]
    if forma == "relajada":
        return [([(30, y0), (46, y0 * 1.1), (52, y0 * 1.1 + 9)], 11) for y0 in (-12, -4, 4, 12)] + \
               [([(10, -16), (24, -26), (32, -24)], 12)]
    if forma == "senala":
        return [([(32, -11), (56, -12), (80, -12)], 11)] + \
               [([(36, y0), (44, y0 + 4), (38, y0 + 10)], 11) for y0 in (-2, 7)] + \
               [([(12, -16), (26, -22), (36, -18)], 12)]
    if forma == "agarra":     # en C: los dedos van hacia adelante y se cierran (la punta vuelve hacia la palma)
        return [([(30, y0), (44, y0 + 2), (46, y0 + 12)], 11) for y0 in (-12, -4, 4)] + \
               [([(10, -16), (26, -26), (40, -24)], 12)]
    # puño: los nudillos son bultos cortos al frente
    return [([(34, y0), (40, y0 + 3), (36, y0 + 8)], 11) for y0 in (-13, -5, 3, 10)] + \
           [([(12, -14), (28, -16), (36, -10)], 12)]


def _palma(forma: str) -> tuple[float, float, float, float]:
    """(cx, cy, rx, ry) de la palma."""
    if forma in ("puno", "senala"):
        return 20.0, 0.0, 22.0, 19.0
    return 18.0, 0.0, 20.0, 19.0


def mano(x: float, y: float, ang: float, forma: str = "relajada", piel: str = "#f2c29b", escala: float = 1.0,
         espejo: bool = False) -> str:
    """La mano en la muñeca (x, y) apuntando a `ang` grados. `espejo` da vuelta el pulgar (para la mano izquierda de
    frente). El pulgar queda siempre del lado de arriba de la pantalla, salvo con `espejo`."""
    forma = forma if forma in FORMAS else "relajada"
    rad = math.radians(ang)
    abajo = math.cos(rad) < 0      # apuntando a la izquierda: sin esto el pulgar quedaría para abajo
    flip = -1 if (abajo != espejo) else 1
    dedos = _dedos(forma)
    cx, cy, rx, ry = _palma(forma)
    contornos, rellenos = [], []
    for pts, ancho in dedos:
        d = "M" + " L".join(f"{n(px)} {n(py)}" for px, py in pts)
        contornos.append(f'<path d="{d}" fill="none" stroke="{P.CONTORNO}" stroke-width="{n(ancho + 2 * _CONTORNO)}" '
                         f'stroke-linecap="round" stroke-linejoin="round"/>')
        rellenos.append(f'<path d="{d}" fill="none" stroke="{piel}" stroke-width="{n(ancho)}" stroke-linecap="round" '
                        f'stroke-linejoin="round"/>')
    contornos.insert(0, f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx + _CONTORNO)}" ry="{n(ry + _CONTORNO)}" '
                        f'fill="{P.CONTORNO}"/>')
    rellenos.insert(0, f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx)}" ry="{n(ry)}" fill="{piel}"/>')
    detalle = ""
    if forma in ("puno", "senala", "agarra"):   # las rayitas de los dedos doblados
        detalle = "".join(f'<path d="M{n(cx + 8)} {n(yy)} L{n(cx + 16)} {n(yy)}" stroke="{P.CONTORNO}" '
                          f'stroke-width="2.5" stroke-linecap="round" opacity="0.55"/>' for yy in (-6, 2, 9))
    cuerpo = "".join(contornos) + "".join(rellenos) + detalle
    return g(g(cuerpo, escala=escala, escala_y=escala * flip), x, y, rot=ang)


def dedos_encima(piel: str = "#f2c29b", lado: int = 1) -> str:
    """Los 4 dedos cerrados SOBRE lo que se agarra (el origen es la mano): bandas cortas apiladas que cruzan el frente
    del objeto, más el pulgar del otro lado. Se dibuja después del objeto para que se lea "lo tiene agarrado"."""
    p_c, p_r = [], []
    for k, yy in enumerate((-21, -7, 7, 21)):
        largo = 24 - abs(k - 1.5) * 3
        d = f"M{n(-largo * lado)} {n(yy)} Q{n(0)} {n(yy - 4)} {n(largo * lado)} {n(yy + 1)}"
        p_c.append(f'<path d="{d}" fill="none" stroke="{P.CONTORNO}" stroke-width="{n(13 + 2 * _CONTORNO)}" '
                   f'stroke-linecap="round"/>')
        p_r.append(f'<path d="{d}" fill="none" stroke="{piel}" stroke-width="13" stroke-linecap="round"/>')
    for yy in (-14, 0, 14):   # la separación entre los dedos
        p_r.append(f'<path d="M{n(-18 * lado)} {n(yy)} L{n(18 * lado)} {n(yy)}" stroke="{P.CONTORNO}" '
                   f'stroke-width="2.5" opacity="0.4"/>')
    return "".join(p_c) + "".join(p_r)
