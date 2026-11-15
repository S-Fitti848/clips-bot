"""Ayudas mínimas para armar SVG como texto (sin dependencias) y la fuente del texto."""
from __future__ import annotations

import functools
import os
import re
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


# ---- volumen (Santi, 2026-11-15: "dibujos con volumen: sombras y luces suaves, contornos con grosor
# variable") -------------------------------------------------------------------------------------------
# Toda forma CON contorno (personajes, muebles, objetos) se pinta con un degradé radial de su color: más
# clara arriba a la izquierda (de donde viene la luz de la ventana), el color en el medio y más oscura y
# un poco violeta abajo a la derecha. Abajo de la forma va una copia del contorno corrida hacia abajo a la
# derecha: el borde sale fino del lado de la luz y grueso del de la sombra. Las formas SIN contorno
# (brillos, sombras, cachetes) quedan planas. Todo en este archivo: con P.VOLUMEN = False vuelve lo plano.
_HEX6 = re.compile(r"#[0-9a-fA-F]{6}$")
_URL_VOL = re.compile(r"url\(#v([0-9a-f]{6})\)")


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def mezcla(a: str, b: str, t: float) -> str:
    """El color `a` corrido una fracción `t` hacia `b` (los dos #rrggbb)."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{max(0, min(255, round(x + (y - x) * t))):02x}" for x, y in zip(ra, rb))


def aclarar(c: str, t: float = 0.3) -> str:
    return mezcla(c, P.LUZ, t)


def oscurecer(c: str, t: float = 0.3) -> str:
    return mezcla(mezcla(c, "#000000", t), P.SOMBRA_TINTE, 0.18)


def _vol(relleno: str) -> str:
    if P.VOLUMEN and isinstance(relleno, str) and _HEX6.match(relleno) and relleno.lower() != P.CONTORNO:
        return f"url(#v{relleno[1:].lower()})"
    return relleno


def _base(etiqueta: str, attrs: str, relleno: str, borde: bool, ancho: float) -> str:
    """La forma (con contorno: con volumen y el contorno variable abajo)."""
    if not borde:
        return f'<{etiqueta} {attrs} fill="{relleno}" stroke="none"/>'
    forma = f'<{etiqueta} {attrs} fill="{_vol(relleno)}" {trazo(ancho=ancho)}/>'
    if not P.VOLUMEN or relleno == "none":
        return forma
    dx, dy = n(ancho * P.CONTORNO_CORRIDO[0]), n(ancho * P.CONTORNO_CORRIDO[1])
    return (f'<{etiqueta} {attrs} fill="{P.CONTORNO}" {trazo(ancho=ancho)} '
            f'transform="translate({dx} {dy})"/>' + forma)


def circulo(cx, cy, r, relleno, borde=True, ancho=P.TRAZO) -> str:
    return _base("circle", f'cx="{n(cx)}" cy="{n(cy)}" r="{n(r)}"', relleno, borde, ancho)


def elipse(cx, cy, rx, ry, relleno, borde=True, ancho=P.TRAZO) -> str:
    return _base("ellipse", f'cx="{n(cx)}" cy="{n(cy)}" rx="{n(rx)}" ry="{n(ry)}"', relleno, borde, ancho)


def rect(x, y, w, h, relleno, r=0, borde=True, ancho=P.TRAZO) -> str:
    rr = f' rx="{n(r)}"' if r else ""
    return _base("rect", f'x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{n(h)}"{rr}', relleno, borde, ancho)


def camino(d: str, relleno: str = "none", borde=True, ancho=P.TRAZO, color=P.CONTORNO) -> str:
    if not borde:
        return f'<path d="{d}" fill="{relleno}" stroke="none"/>'
    if color != P.CONTORNO:     # un trazo de color (no es un contorno): plano
        return f'<path d="{d}" fill="{relleno}" {trazo(color, ancho)}/>'
    return _base("path", f'd="{d}"', relleno, borde, ancho)


def linea_gruesa(puntos: list[tuple[float, float]], color: str, ancho: float) -> str:
    """Una línea gruesa con contorno: primero el trazo oscuro más ancho, después el color.
    Así se dibujan los brazos (se doblan sin tener que calcular el contorno del polígono).
    Con volumen: el contorno corrido abajo a la derecha, y adentro una franja de sombra de un lado y
    un brillo del otro (el brazo se ve redondo)."""
    d = "M" + " L".join(f"{n(x)} {n(y)}" for x, y in puntos)
    base = (f'<path d="{d}" fill="none" {trazo(P.CONTORNO, ancho + 2 * P.TRAZO)}/>'
            f'<path d="{d}" fill="none" {trazo(color, ancho)}/>')
    if not P.VOLUMEN or not _HEX6.match(str(color)):
        return base
    k = P.TRAZO
    sombra = (f'<path d="{d}" fill="none" {trazo(P.CONTORNO, ancho + 2 * k)} '
              f'transform="translate({n(k * P.CONTORNO_CORRIDO[0])} {n(k * P.CONTORNO_CORRIDO[1])})"/>')
    franjas = (f'<path d="{d}" fill="none" {trazo(oscurecer(color, 0.22), ancho * 0.42)} '
               f'transform="translate({n(ancho * 0.2)} {n(ancho * 0.12)})"/>'
               f'<path d="{d}" fill="none" {trazo(aclarar(color, 0.35), ancho * 0.2)} '
               f'transform="translate({n(-ancho * 0.22)} {n(-ancho * 0.1)})"/>')
    return sombra + base + franjas


def defs_volumen(contenido: str) -> str:
    """Los degradés de las formas con volumen que usa `contenido` (uno por color)."""
    usados = sorted(set(_URL_VOL.findall(contenido)))
    if not usados:
        return ""
    partes = []
    for h in usados:
        c = "#" + h
        partes.append(
            f'<radialGradient id="v{h}" cx="0.36" cy="0.3" r="0.82" fx="0.3" fy="0.22">'
            f'<stop offset="0" stop-color="{aclarar(c, 0.32)}"/>'
            f'<stop offset="0.5" stop-color="{c}"/>'
            f'<stop offset="1" stop-color="{oscurecer(c, 0.24)}"/></radialGradient>')
    return "<defs>" + "".join(partes) + "</defs>"


def documento(contenido: str, ancho: int = P.ANCHO, alto: int = P.ALTO,
              fondo: str | None = None) -> str:
    bg = f'<rect width="{ancho}" height="{alto}" fill="{fondo}"/>' if fondo else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
            f'viewBox="0 0 {ancho} {alto}">{defs_volumen(contenido)}{bg}{contenido}</svg>')


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
