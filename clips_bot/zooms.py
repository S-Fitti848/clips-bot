"""Zooms en los momentos fuertes de un clip (pedido de Santi, 2026-10-04): sobre el formato de
siempre (fit_blur: el video entero y atrás el mismo video difuminado), unos pocos acercamientos
suaves cuando el volumen pega un pico (un grito, una risa, el remate). Nunca todo el tiempo y nunca
cortando una cara: la zona de TODAS las caras detectadas (con margen) tiene que entrar en el cuadro
con el zoom puesto; si no entra ni con un zoom mínimo, ese clip va sin zooms.
"""

from __future__ import annotations

import statistics

SUBIDA_S = 0.3     # cuánto tarda en acercarse
QUIETO_S = 1.0     # cuánto se queda cerca
BAJADA_S = 0.6     # cuánto tarda en volver
ANTES_S = 0.25     # arranca un poco antes del pico, así el acercamiento llega con el grito
ZOOM_MIN = 1.06    # menos que esto no se nota: mejor no hacer nada
CARA_MIN = 0.04    # caras más angostas que esto (fracción del ancho) son ruido del detector


def picos(rms: list[float], ventana_s: float, duracion: float, max_n: int = 3,
          separacion_s: float = 8.0, cada_s: float = 20.0) -> list[float]:
    """Segundos de los picos de volumen más fuertes: como mucho 1 cada `cada_s` del clip (y
    `max_n`), separados `separacion_s`, lejos del principio y del final. Un pico tiene que pasar
    1,6 veces la mediana y el percentil 90: un clip parejo no tiene momentos fuertes y no lleva."""
    if len(rms) < 4:
        return []
    med = statistics.median(rms) or 1e-9
    umbral = max(1.6 * med, sorted(rms)[int(0.9 * (len(rms) - 1))])
    n = min(max_n, 1 + int(duracion // cada_s))
    candidatos = sorted(range(len(rms)), key=lambda i: rms[i], reverse=True)
    out: list[float] = []
    for i in candidatos:
        if len(out) >= n or rms[i] < umbral:
            break
        t = (i + 0.5) * ventana_s
        if t < 1.0 or t > duracion - 1.5 or any(abs(t - o) < separacion_s for o in out):
            continue
        out.append(t)
    return sorted(out)


def tramos(segundos: list[float], duracion: float) -> list[tuple[float, float]]:
    """(inicio, fin) de cada zoom alrededor de su pico."""
    out = []
    for t in segundos:
        a = max(0.0, t - ANTES_S)
        b = min(duracion, a + SUBIDA_S + QUIETO_S + BAJADA_S)
        out.append((round(a, 2), round(b, 2)))
    return out


def zona(frames: list[list[tuple[int, int, int, int]]], W: int, H: int) -> tuple[float, float, float, float] | None:
    """La zona de todas las caras de todos los cuadros muestreados (con el margen de las fotos de
    Pequeña Historia: cabeza, costados y mentón), en fracciones del cuadro. None si no hay caras."""
    from .parallax import zona_caras

    cs = [c for f in frames for c in f if c[2] >= CARA_MIN * W]
    z = zona_caras(cs, W, H)
    if not z:
        return None
    return z[0] / W, z[1] / H, z[2] / W, z[3] / H


def encuadre(z: tuple[float, float, float, float] | None, zoom: float) -> tuple[float, float, float]:
    """(zoom, centro x, centro y) en fracciones: hacia las caras, y el zoom bajado hasta que todas
    entren. Sin caras, al centro. zoom 1.0 = no se puede sin cortar una cara."""
    if z is None:
        return zoom, 0.5, 0.5
    zw, zh = max(z[2] - z[0], 1e-6), max(z[3] - z[1], 1e-6)
    zoom = min(zoom, 1 / zw, 1 / zh)
    if zoom < ZOOM_MIN:
        return 1.0, 0.5, 0.5
    return round(zoom, 3), (z[0] + z[2]) / 2, (z[1] + z[3]) / 2


def expr_zoom(tr: list[tuple[float, float]], zoom: float) -> str:
    """Expresión de ffmpeg del zoom en función del tiempo de entrada (`it` de zoompan): 1 fuera de
    los tramos, `zoom` en el medio, con subida y bajada suaves (coseno)."""
    partes = []
    for a, b in tr:
        e = f"min(clip((it-{a})/{SUBIDA_S},0,1),clip(({b}-it)/{BAJADA_S},0,1))"
        partes.append(f"(0.5-0.5*cos(PI*{e}))")
    return f"1+{zoom - 1:.3f}*({'+'.join(partes) or '0'})"


def filtro_frente(W: int, h: int, fps: int, tr: list[tuple[float, float]], zoom: float,
                  cx: float, cy: float) -> str:
    """El frente del fit_blur con los zooms: se agranda al doble antes de zoompan (a tamaño normal
    redondea a píxel entero y tiembla) y la ventana se centra en las caras sin salirse del cuadro."""
    x = f"clip(iw*{cx:.4f}-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip(ih*{cy:.4f}-ih/zoom/2,0,ih-ih/zoom)"
    return (f"fps={fps},scale={2 * W}:{2 * h}:flags=lanczos,setsar=1,"
            f"zoompan=z='{expr_zoom(tr, zoom)}':x='{x}':y='{y}':d=1:s={W}x{h}:fps={fps}")


def planear(rms: list[float], ventana_s: float, duracion: float, frames, W: int, H: int,
            zoom: float, max_n: int) -> tuple[list[tuple[float, float]], float, float, float]:
    """Todo junto: (tramos, zoom, cx, cy). Sin tramos si no hay picos o si las caras no entran."""
    z, cx, cy = encuadre(zona(frames, W, H), zoom)
    if z <= 1.0:
        return [], 1.0, 0.5, 0.5
    tr = tramos(picos(rms, ventana_s, duracion, max_n), duracion)
    return tr, z, cx, cy

