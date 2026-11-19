"""El protagonista fiel al producto real (Santi, 2026-11-19, para TODOS los videos de Así Nació: la Wilson salía como
una pelota de espuma naranja genérica). Antes de dibujarlo, Haiku describe cómo es DE VERDAD (forma, colores, los
detalles que lo hacen reconocible); el dibujo sigue esa descripción; y Haiku mira el dibujo solo y contesta "¿alguien lo
reconoce sin leer el nombre?". Si no, se redibuja una vez con lo que faltaba. El dibujo queda en la biblioteca
(`data/animacion/dibujos/`) y la descripción en `data/animacion/fieles.json`: el próximo video de esa marca no paga nada.
"""
from __future__ import annotations

import io
import json
import logging
import re
import unicodedata

from ..config import DATA_DIR

log = logging.getLogger(__name__)

ARCHIVO = DATA_DIR / "animacion" / "fieles.json"
PREFIJO = "fiel_"

SISTEMA_DESCRIBIR = """Describís cómo es DE VERDAD un producto para que un dibujante lo dibuje simple (dibujo animado
plano) y cualquiera lo reconozca sin leer el nombre. Decí: la forma, los colores reales, y los 3 a 5 detalles que lo
hacen inconfundible (por ejemplo, la pelota de vóley de la película Náufrago: blanca, con paneles curvos y una cara
pintada a mano en rojo con la huella de una mano). Sin texto, letras, números ni logos en el dibujo: si el detalle es
un logo, describí su forma o su color, nunca las letras. Si el texto de la historia dice cómo era, eso manda. Corto:
como mucho 60 palabras en `descripcion`."""
SCHEMA_DESCRIBIR = {"type": "OBJECT", "properties": {
    "descripcion": {"type": "STRING"},
    "detalles": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["descripcion", "detalles"]}

SISTEMA_RECONOCE = """Te muestro UN dibujo de un objeto. Sin pensar en ningún nombre de marca: ¿qué objeto es? Después
decí si una persona común reconocería que es el objeto que te digo, solo mirándolo (sin leer nada). Sé exigente: un
círculo naranja no es "una pelota de vóley con una cara". En `falta`, lo que habría que agregar o cambiar para que se
reconozca (vacío si ya se reconoce)."""
SCHEMA_RECONOCE = {"type": "OBJECT", "properties": {
    "que_ves": {"type": "STRING"}, "reconocible": {"type": "BOOLEAN"}, "falta": {"type": "STRING"}},
    "required": ["que_ves", "reconocible", "falta"]}


def _slug(t: str, largo: int = 12) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:largo].strip("_")


def nombre_de(marca: str, que_es: str) -> str:
    return (PREFIJO + _slug(marca, 10) + "_" + _slug(que_es, 14))[:30].rstrip("_")


def _leer() -> dict:
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar(datos: dict) -> None:
    try:
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        log.warning("no pude guardar %s: %s", ARCHIVO, e)


def describir(cliente, marca: str, que_es: str, anio: int = 0, fuente: str = "") -> dict:
    """{"descripcion", "detalles"} del producto real (de la caché si ya se pidió)."""
    clave = f"{marca}|{que_es}|{anio // 10 if anio else 0}"
    datos = _leer()
    if clave in datos:
        return datos[clave]
    pedido = (f"PRODUCTO: {que_es} de la marca {marca}" + (f", como era en {anio}" if anio else "")
              + (f"\n\nTEXTO DE LA HISTORIA (lo que dice manda):\n{fuente[:4000]}" if fuente else ""))
    r = json.loads(cliente.json(SISTEMA_DESCRIBIR, pedido, SCHEMA_DESCRIBIR, 0.2))
    out = {"descripcion": str(r.get("descripcion") or "").strip(),
           "detalles": [str(x).strip() for x in r.get("detalles") or [] if str(x).strip()][:5]}
    if out["descripcion"]:
        datos[clave] = out
        _guardar(datos)
    return out


def imagen(nombre: str, lado: int = 384) -> bytes:
    """El dibujo solo, sobre blanco, en JPEG (lo que mira Haiku)."""
    from PIL import Image

    from . import escenas as esc
    from . import render as rd
    from .svg import documento

    cuerpo = f'<g transform="translate({lado / 2} {lado / 2}) scale({lado / 300})">{esc.prop(nombre)}</g>'
    img = rd.crear("auto").rgba(documento(cuerpo, lado, lado, fondo="#ffffff"), lado, lado)
    fondo = Image.new("RGB", img.size, "white")
    fondo.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
    buf = io.BytesIO()
    fondo.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def reconoce(cliente, nombre: str, que_es: str) -> tuple[bool, str, str]:
    """(se reconoce, qué falta, qué vio) mirando el dibujo."""
    r = json.loads(cliente.json(SISTEMA_RECONOCE, f"El objeto que tiene que ser: {que_es}", SCHEMA_RECONOCE, 0.1,
                                imagenes=[imagen(nombre)]))
    return bool(r.get("reconocible")), str(r.get("falta") or ""), str(r.get("que_ves") or "")


def asegurar(cliente, d: dict, marca: str, fuente: str = "", avisar=log.info) -> list[str]:
    """El protagonista dibujado como el real y reconocible, en todas las escenas. Devuelve lo que hizo. Nunca frena el
    video: si algo falla, queda el dibujo de antes."""
    from . import dibujos
    from . import marcas as mk

    pr = d.get("protagonista") or {}
    viejo = mk.prop_real(pr)
    que_es = str(pr.get("que_es") or viejo or "").strip()
    if not que_es or cliente is None:
        return []
    anios = [int(x.get("anio_escena") or 0) for x in d.get("escenas") or [] if x.get("anio_escena")]
    hechos: list[str] = []
    try:
        desc = describir(cliente, marca, que_es, max(anios) if anios else 0, fuente)
        texto = desc["descripcion"] + (". Detalles: " + "; ".join(desc["detalles"]) if desc.get("detalles") else "")
        nombre = viejo if viejo.startswith(PREFIJO) else nombre_de(marca, que_es)
        if dibujos.svg_de(nombre) is None:
            dibujos.dibujar(cliente, nombre, texto, f"{marca}: el protagonista de la historia")
            hechos.append(f"dibujé {nombre} como el real")
        ok, falta, vio = reconoce(cliente, nombre, que_es)
        if not ok:
            otro = (nombre[:27] + "_v2")[:30]
            if dibujos.svg_de(otro) is None:
                dibujos.dibujar(cliente, otro, f"{texto}. Lo que faltaba para reconocerlo: {falta}",
                                f"{marca}: el protagonista (segunda versión)")
            ok2, falta2, vio2 = reconoce(cliente, otro, que_es)
            hechos.append(f"{nombre} no se reconocía ({vio[:60]}): {otro} " + ("sí" if ok2 else f"tampoco ({falta2[:60]})"))
            if ok2:
                dibujos.reemplazar(nombre, otro)
                nombre = otro
        else:
            hechos.append(f"{nombre} se reconoce ({vio[:60]})")
    except Exception as err:  # noqa: BLE001 — nunca frena el video
        avisar(f"protagonista fiel: {str(err)[:150]}; queda {viejo}")
        return hechos
    if nombre != viejo:
        for e_ in d.get("escenas") or []:
            for o in e_.get("objetos") or []:
                if mk.prop_real(o) == viejo:
                    o["prop"], o["dibujo"] = mk.DIBUJO_NUEVO, nombre
        pr["prop"], pr["dibujo"] = mk.DIBUJO_NUEVO, nombre
        d["protagonista"] = pr
        # las escenas de uso con las manos y de inspiración ya tenían el producto viejo (la pelota naranja en la escena
        # de manos del Wilson, 2026-11-19): pasan al fiel
        for e_ in d.get("escenas") or []:
            for clave, campos in (("uso", ("partes",)), ("inspiracion", ())):
                bloque = e_.get(clave)
                if not isinstance(bloque, dict):
                    continue
                for dic in [bloque] + [bloque[c] for c in campos if isinstance(bloque.get(c), dict)]:
                    for k_, v in list(dic.items()):
                        if v == viejo:
                            dic[k_] = nombre
    if hechos:
        avisar("protagonista fiel: " + "; ".join(hechos))
    return hechos
