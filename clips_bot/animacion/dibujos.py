"""Dibujos que no están en la biblioteca (Santi, 2026-11-15: "si una escena necesita algo que no está — un
detective para Popeyes —, que Claude lo dibuje para ese video y lo guarde para reusarlo").

El guion pide un objeto nuevo (`dibujos_nuevos`: nombre corto + qué es). Sonnet lo dibuja como SVG en el
estilo del canal (contorno oscuro grueso, colores planos, centrado en (0, 0), ~200 px), se limpia (solo
formas: nada de texto, imágenes, scripts ni enlaces), se prueba que se rasterice, y se guarda en
`data/animacion/dibujos/<nombre>.svg` con su descripción: el próximo video ya lo tiene en la lista. Si no
se puede dibujar, quien llama reformula la frase o usa otro objeto (nunca queda un hueco)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from clips_bot.config import DATA_DIR

from . import paleta as P

log = logging.getLogger(__name__)

CARPETA = DATA_DIR / "animacion" / "dibujos"
ETIQUETAS = {"g", "path", "circle", "ellipse", "rect", "polygon", "polyline", "line"}
ATRIBUTOS = {"d", "cx", "cy", "r", "rx", "ry", "x", "y", "width", "height", "points", "x1", "y1", "x2", "y2",
             "fill", "stroke", "stroke-width", "stroke-linejoin", "stroke-linecap", "opacity", "fill-opacity",
             "stroke-opacity", "transform"}
MAX_BYTES = 12000
_NOMBRE = re.compile(r"^[a-z][a-z0-9_]{2,30}$")

SISTEMA = f"""Dibujás UN objeto o accesorio para un canal de videos animados (dibujos simples de dibujo animado).
Devolvé SOLO el contenido de un SVG (sin la etiqueta <svg>): formas <g>, <path>, <circle>, <ellipse>,
<rect>, <polygon>, <line>. Reglas:
- centrado en (0, 0), de unos 200 px de alto o de ancho (entre -110 y 110 en x e y);
- estilo del canal: contorno {P.CONTORNO} de {P.TRAZO} px (stroke-linejoin round), colores planos y saturados
  pero no chillones, 2 a 4 colores, un brillo blanco chico arriba a la izquierda;
- que se reconozca SIN leer: nada de texto, letras ni números; nada de logos ni marcas reales;
- simple: 4 a 25 formas, menos de 8.000 caracteres.
Además `anio_desde`: el año desde el que existe ese objeto tal como lo dibujaste (un celular, 1983; un táper de
plástico, 1946; una hoja de papel, 0 si existe desde siempre): nunca aparece en una escena anterior."""

SCHEMA = {"type": "OBJECT", "properties": {"svg": {"type": "STRING"}, "anio_desde": {"type": "INTEGER"}},
          "required": ["svg", "anio_desde"]}


def nombre_valido(nombre: str) -> bool:
    return bool(_NOMBRE.match(str(nombre or "")))


REEMPLAZOS = "reemplazos.json"     # {viejo: nuevo}: una versión nueva de un objeto reemplaza a la vieja (2026-11-16)


def biblioteca() -> dict[str, str]:
    """{nombre: descripción} de los dibujos guardados (sin los reemplazados)."""
    out = {}
    for f in sorted(CARPETA.glob("*.json")):
        if f.name == REEMPLAZOS:
            continue
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8")).get("descripcion", "")
        except (OSError, ValueError):
            continue
    return out


_CACHE_REEMP: dict = {}


def reemplazos() -> dict[str, str]:
    """{viejo: nuevo}. Se lee una vez por cambio del archivo (se consulta en cada cuadro)."""
    f = CARPETA / REEMPLAZOS
    try:
        clave = (str(f), f.stat().st_mtime)
    except OSError:
        return {}
    if _CACHE_REEMP.get("clave") != clave:
        try:
            _CACHE_REEMP.update(clave=clave, datos=json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}
    return _CACHE_REEMP.get("datos") or {}


def actual(nombre: str) -> str:
    """El nombre vigente de un dibujo: si se dibujó una versión nueva, la nueva (siguiendo la cadena)."""
    r, vistos = reemplazos(), set()
    while nombre in r and nombre not in vistos:
        vistos.add(nombre)
        nombre = r[nombre]
    return nombre


def reemplazar(viejo: str, nuevo: str) -> None:
    """Santi, 2026-11-16 ("en la escena de manos volvió el Tupper con forma de olla"): la versión nueva reemplaza a la
    vieja en todas las escenas y la vieja sale de la biblioteca (se mueve a retirados/, no se pierde)."""
    if viejo == nuevo or not nombre_valido(viejo) or not nombre_valido(nuevo):
        return
    r = reemplazos()
    r[viejo] = nuevo
    CARPETA.mkdir(parents=True, exist_ok=True)
    (CARPETA / REEMPLAZOS).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    retirados = CARPETA / "retirados"
    for ext in (".svg", ".json"):
        f = CARPETA / f"{viejo}{ext}"
        if f.exists():
            retirados.mkdir(exist_ok=True)
            f.replace(retirados / f.name)
    log.info("dibujo %s reemplazado por %s", viejo, nuevo)


_VACIAS = {"sin", "texto", "logos", "logo", "con", "color", "colores", "una", "uno", "del", "las", "los", "que", "muy",
           "forma", "arriba", "abajo", "chico", "chica", "grande", "simple"}


def _clave(t: str) -> set[str]:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return {w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 4 and w not in _VACIAS}


def mismo_objeto(desc_a: str, desc_b: str) -> bool:
    """¿Dos descripciones son del mismo objeto? (la mitad o más de las palabras de la más corta, al menos 3)."""
    a, b = _clave(desc_a), _clave(desc_b)
    comunes = a & b
    return len(comunes) >= 3 and len(comunes) * 2 >= min(len(a), len(b))


def anio_desde(nombre: str) -> int:
    """Desde qué año existe el objeto de un dibujo guardado (0 = no se sabe: se usa en cualquier época)."""
    try:
        d = json.loads((CARPETA / f"{actual(nombre)}.json").read_text(encoding="utf-8"))
        return int(d.get("anio_desde") or 0)
    except (OSError, ValueError, TypeError):
        return 0


def svg_de(nombre: str) -> str | None:
    nombre = actual(str(nombre or ""))
    f = CARPETA / f"{nombre}.svg"
    try:
        return f.read_text(encoding="utf-8") if nombre_valido(nombre) else None
    except OSError:
        return None


def limpiar(contenido: str) -> str:
    """Solo formas y atributos de dibujo. ValueError si no queda nada o si no es SVG válido."""
    contenido = re.sub(r"</?svg[^>]*>", "", str(contenido or "")).strip()
    if not contenido or len(contenido) > MAX_BYTES:
        raise ValueError("vacío o demasiado grande")
    raiz = ET.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{contenido}</g>')
    formas = 0

    def nodo(el) -> str:
        nonlocal formas
        tag = el.tag.split("}")[-1]
        if tag not in ETIQUETAS:
            return ""
        attrs = " ".join(f'{k}="{v}"' for k, v in el.attrib.items()
                         if k in ATRIBUTOS and "url(" not in v and "javascript" not in v.lower())
        hijos = "".join(nodo(h) for h in el)
        formas += tag != "g"
        return f"<{tag} {attrs}>{hijos}</{tag}>" if hijos else f"<{tag} {attrs}/>"

    limpio = "".join(nodo(h) for h in raiz)
    if formas < 2:
        raise ValueError("menos de 2 formas")
    return limpio


def probar(svg: str) -> None:
    """Que se rasterice (si cairosvg o resvg revientan, el dibujo no sirve)."""
    from . import render as rd
    from .svg import documento

    r = rd.crear("auto")
    r.rgba(documento(f'<g transform="translate(150 150)">{svg}</g>', 300, 300), 300, 300)


def dibujar(cliente, nombre: str, descripcion: str, contexto: str = "") -> str:
    """Dibuja y guarda. Devuelve el SVG; ValueError si no se pudo."""
    if not nombre_valido(nombre):
        raise ValueError(f"nombre inválido: {nombre!r}")
    ya = svg_de(nombre)
    if ya:
        return ya
    pedido = f"Dibujá: {nombre} — {descripcion}." + (f"\nPara: {contexto}" if contexto else "")
    ultimo = ""
    for _ in range(2):
        try:
            r = json.loads(cliente.json(SISTEMA, pedido + ultimo, SCHEMA, 0.6))
            svg = limpiar(r.get("svg"))
            anio = int(r.get("anio_desde") or 0) if str(r.get("anio_desde") or "0").lstrip("-").isdigit() else 0
            probar(svg)
        except Exception as err:  # noqa: BLE001 — se reintenta una vez con el error
            ultimo = f"\n\nTu dibujo anterior no sirvió: {str(err)[:200]}. Hacelo más simple."
            continue
        CARPETA.mkdir(parents=True, exist_ok=True)
        (CARPETA / f"{nombre}.svg").write_text(svg, encoding="utf-8")
        (CARPETA / f"{nombre}.json").write_text(json.dumps({"descripcion": descripcion, "anio_desde": max(0, anio)},
                                                           ensure_ascii=False),
                                               encoding="utf-8")
        log.info("dibujo nuevo guardado: %s (%s)", nombre, descripcion)
        return svg
    raise ValueError(f"no pude dibujar {nombre}{ultimo[:150]}")
