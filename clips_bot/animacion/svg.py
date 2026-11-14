"""Ayudas mínimas para armar SVG como texto (sin dependencias) y la fuente del texto."""
from __future__ import annotations

import functools
import os
from pathlib import Path
from xml.sax.saxutils import escape

from . import paleta as P


def n(x: float) -> str:
    """Número corto: el SVG de cada cuadro se arma cientos de veces, menos texto = menos parseo."""
    r = round(float(x), 1)
    return str(int(r)) if r == int(r) else str(r)


def transform(x: float = 0, y: float = 0, escala: float = 1, rot: float = 0,
              escala_y: float | None = None) -> str:
    partes = []
    if x or y:
        partes.append(f"translate({n(x)} {n(y)})")
    if rot:
        partes.append(f"rotate({n(rot)})")
    ey = escala if escala_y is None else escala_y
    if escala != 1 or ey != 1:
        partes.append(f"scale({round(escala, 4)} {round(ey, 4)})" if ey != escala
                      else f"scale({round(escala, 4)})")
    return " ".join(partes)


def g(contenido: str, x: float = 0, y: float = 0, escala: float = 1, rot: float = 0,
      opacidad: float = 1, escala_y: float | None = None) -> str:
    t = transform(x, y, escala, rot, escala_y)
    attrs = f' transform="{t}"' if t else ""
    if opacidad < 1:
        attrs += f' opacity="{round(max(0.0, opacidad), 3)}"'
    return f"<g{attrs}>{contenido}</g>" if attrs else contenido


def trazo(color: str = P.CONTORNO, ancho: float = P.TRAZO) -> str:
    return (f'stroke="{color}" stroke-width="{n(ancho)}" stroke-linejoin="round" '
            f'stroke-linecap="round"')


def circulo(cx, cy, r, relleno, borde=True, ancho=P.TRAZO) -> str:
    b = trazo(ancho=ancho) if borde else 'stroke="none"'
    return f'<circle cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}" fill="{relleno}" {b}/>'


def elipse(cx, cy, rx, ry, relleno, borde=True, ancho=P.TRAZO) -> str:
    b = trazo(ancho=ancho) if borde else 'stroke="none"'
    return (f'<ellipse cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx)}" ry="{n(ry)}" fill="{relleno}" '
            f'{b}/>')


def rect(x, y, w, h, relleno, r=0, borde=True, ancho=P.TRAZO) -> str:
    b = trazo(ancho=ancho) if borde else 'stroke="none"'
    rr = f' rx="{n(r)}"' if r else ""
    return (f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}"{rr} fill="{relleno}" '
            f'{b}/>')


def camino(d: str, relleno: str = "none", borde=True, ancho=P.TRAZO, color=P.CONTORNO) -> str:
    b = trazo(color, ancho) if borde else 'stroke="none"'
    return f'<path d="{d}" fill="{relleno}" {b}/>'


def linea_gruesa(puntos: list[tuple[float, float]], color: str, ancho: float) -> str:
    """Una línea gruesa con contorno: primero el trazo oscuro más ancho, después el color.
    Así se dibujan los brazos (se doblan sin tener que calcular el contorno del polígono)."""
    d = "M" + " L".join(f"{n(x)} {n(y)}" for x, y in puntos)
    return (f'<path d="{d}" fill="none" {trazo(P.CONTORNO, ancho + 2 * P.TRAZO)}/>'
            f'<path d="{d}" fill="none" {trazo(color, ancho)}/>')


def documento(contenido: str, ancho: int = P.ANCHO, alto: int = P.ALTO,
              fondo: str | None = None) -> str:
    bg = f'<rect width="{ancho}" height="{alto}" fill="{fondo}"/>' if fondo else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
            f'viewBox="0 0 {ancho} {alto}">{bg}{contenido}</svg>')


# ---- fuente -----------------------------------------------------------------
# Una sola fuente gruesa para todo el texto. Se busca un archivo conocido (la Pi tiene DejaVu, Windows
# Arial Black / Arial Bold) y se le pasa EXPLÍCITA al rasterizador: resvg sin fuentes del sistema
# arranca mucho más rápido (no escanea /usr/share/fonts en cada cuadro) y el texto sale igual en
# cualquier máquina que tenga el mismo archivo. ANIM_FUENTE la pisa.
_CANDIDATAS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


@functools.lru_cache(maxsize=1)
def fuente() -> tuple[str | None, str]:
    """(archivo, familia). Sin archivo, (None, 'sans-serif') y el texto se mide aproximado."""
    for c in [os.getenv("ANIM_FUENTE", "")] + _CANDIDATAS:
        if c and Path(c).is_file():
            try:
                from PIL import ImageFont

                familia = ImageFont.truetype(c, 20).getname()[0]
            except Exception:
                familia = "sans-serif"
            return c, familia
    return None, "sans-serif"


@functools.lru_cache(maxsize=4096)
def ancho_texto(texto: str, tam: int) -> float:
    """Ancho en px del texto con la fuente del canal (PIL). Hace falta para centrar palabra por
    palabra: cada palabra de un subtítulo es un <text> aparte (color y salto propios)."""
    archivo, _ = fuente()
    if archivo:
        try:
            from PIL import ImageFont

            return float(_pil(archivo, tam).getlength(texto))
        except Exception:
            pass
    return 0.62 * tam * len(texto)


@functools.lru_cache(maxsize=64)
def _pil(archivo: str, tam: int):
    from PIL import ImageFont

    return ImageFont.truetype(archivo, tam)


def texto_con_borde(texto: str, x: float, y: float, tam: int, color: str = P.TEXTO,
                    borde: str = P.TEXTO_BORDE, ancho_borde: float | None = None,
                    ancla: str = "middle") -> str:
    """Texto grueso con borde, como dos <text>: el borde (stroke) abajo y el relleno arriba.
    No se usa paint-order porque cairosvg no lo respeta."""
    _, familia = fuente()
    ab = ancho_borde if ancho_borde is not None else max(4, tam * 0.16)
    t = escape(texto)
    base = (f'x="{n(x)}" y="{n(y)}" font-family="{familia}" font-size="{tam}" '
            f'font-weight="900" text-anchor="{ancla}"')
    return (f'<text {base} fill="{borde}" stroke="{borde}" stroke-width="{n(ab)}" '
            f'stroke-linejoin="round">{t}</text><text {base} fill="{color}">{t}</text>')
