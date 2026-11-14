"""La letra de los subtítulos de "Así Nació": Montserrat Black (SIL Open Font License 1.1, Google Fonts;
el .ttf y el OFL.txt están en assets/fuentes/) dibujada como CAMINOS SVG.

Por qué caminos y no <text>: así el subtítulo sale igual en cairosvg, en resvg y en el Chrome de Remotion,
en la compu y en la Pi, sin instalar ninguna fuente en el sistema. Los contornos de cada letra se sacan una
vez del .ttf (`generar`, con fontTools, que solo hace falta en la compu) y quedan en
`montserrat_black.json`; en la corrida diaria solo se lee ese JSON.

    python -m clips_bot.animacion.letra          # regenera montserrat_black.json desde el .ttf
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TTF = RAIZ / "assets" / "fuentes" / "Montserrat-Black.ttf"
GLIFOS = Path(__file__).with_name("montserrat_black.json")
CARACTERES = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
              "ÁÉÍÓÚÜÑáéíóúüñÀÈÌÒÙàèìòùÇç¿?¡!.,;:'\"-–—…%$&()/+#@*=“”‘’«» ")


def generar(ttf: Path = TTF, destino: Path = GLIFOS) -> int:
    """Contornos (en unidades de la fuente, y hacia abajo) y avances de cada carácter → JSON."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    f = TTFont(str(ttf))
    cmap = f.getBestCmap()
    gs = f.getGlyphSet()
    hmtx = f["hmtx"]
    out = {}
    for ch in CARACTERES:
        nombre = cmap.get(ord(ch))
        if not nombre:
            continue
        pen = SVGPathPen(gs, ntos=lambda v: str(round(v)))
        gs[nombre].draw(TransformPen(pen, (1, 0, 0, -1, 0, 0)))
        out[ch] = {"d": pen.getCommands(), "a": hmtx[nombre][0]}
    kern = {}
    datos = {"upm": f["head"].unitsPerEm, "asc": f["hhea"].ascent, "desc": f["hhea"].descent,
             "alto_mayus": getattr(f["OS/2"], "sCapHeight", 700), "glifos": out, "kern": kern,
             "fuente": "Montserrat Black (SIL OFL 1.1)"}
    destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(out)


@functools.lru_cache(maxsize=1)
def glifos() -> dict:
    return json.loads(GLIFOS.read_text(encoding="utf-8"))


def ancho(texto: str, tam: float) -> float:
    """Ancho en px del texto a `tam` px (lo que no está en la fuente cuenta como una "M" angosta)."""
    g = glifos()
    k = tam / g["upm"]
    return sum(g["glifos"].get(c, {"a": 600})["a"] for c in texto) * k


def camino(texto: str, tam: float) -> str:
    """Un solo `d` con todo el texto, el origen en la línea de base al principio (x = 0)."""
    g = glifos()
    k = tam / g["upm"]
    partes, x = [], 0.0
    for c in texto:
        gl = g["glifos"].get(c)
        if gl is None:
            x += 600
            continue
        if gl["d"]:
            partes.append(_mover(gl["d"], x))
        x += gl["a"]
    d = " ".join(partes)
    return _escalar(d, k) if d else ""


def _numeros(d: str):
    import re

    return re.split(r"([A-Za-z])", d)


def _mover(d: str, dx: float) -> str:
    """Corre un camino absoluto (solo M/L/Q/C/Z, como los escribe SVGPathPen) en x."""
    out, cmd = [], ""
    for tok in _numeros(d):
        if not tok:
            continue
        if tok.isalpha():
            cmd = tok
            out.append(tok)
            continue
        nums = tok.replace(",", " ").split()
        if cmd in "HV":       # SVGPathPen no los usa en contornos de TrueType, pero por las dudas
            nums = [str(float(n) + (dx if cmd == "H" else 0)) for n in nums]
        else:
            nums = [str(round(float(n) + (dx if i % 2 == 0 else 0), 1)) for i, n in enumerate(nums)]
        out.append(" ".join(nums))
    return "".join(out)


def _escalar(d: str, k: float) -> str:
    out = []
    for tok in _numeros(d):
        if not tok:
            continue
        if tok.isalpha():
            out.append(tok)
        else:
            out.append(" ".join(str(round(float(n) * k, 1)) for n in tok.replace(",", " ").split()))
    return "".join(out)


if __name__ == "__main__":
    print(f"{generar()} caracteres -> {GLIFOS}")
