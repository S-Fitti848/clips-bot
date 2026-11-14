"""Curvas de easing: f(0) = 0 y f(1) = 1, t ya recortado a [0, 1]."""
from __future__ import annotations

import math


def lineal(t: float) -> float:
    return t


def suave(t: float) -> float:          # ease-in-out (seno)
    return 0.5 - 0.5 * math.cos(math.pi * t)


def entrada(t: float) -> float:        # ease-in (cuadrática)
    return t * t


def salida(t: float) -> float:         # ease-out (cúbica)
    return 1 - (1 - t) ** 3


def rebote(t: float) -> float:         # ease-out-back: se pasa un poco y vuelve
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def elastico(t: float) -> float:       # ease-out-elastic
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def escalon(t: float) -> float:        # salta al final del tramo (cambio instantáneo)
    return 1.0 if t >= 1 else 0.0


CURVAS = {"lineal": lineal, "suave": suave, "entrada": entrada, "salida": salida,
          "rebote": rebote, "elastico": elastico, "escalon": escalon}


def curva(nombre: str | None):
    if not nombre:
        return suave
    if nombre not in CURVAS:
        raise ValueError(f"Easing desconocido: {nombre!r} (hay {', '.join(CURVAS)})")
    return CURVAS[nombre]


def recortar(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t
