"""Nunca dos videos de la misma historia (Santi, 2026-11-27, después de los dos de la fundación de Apple: el banco la
tenía dos veces, con el artículo "Apple" y con "Apple_Inc.", y la reserva armó una el 26/11 y la del día otra el 27/11).

Regla: una historia no se usa dos veces en `DIAS` (7) días, sumando producción, reserva, banco y pruebas. Una historia
que entra en una propuesta (también la de una prueba) queda reservada en ese momento: nadie más la puede tomar.

Cómo se usa: quien propone abre `activo(conn, dia, origen)`; adentro, `efemerides.proponer` y `locales.proponer`
saltean lo que `bloqueada()` dice y cada Propuesta que se crea se anota sola (`al_crear`, desde Propuesta). Sin un
registro activo no se mira ni se anota nada (los tests de siempre no cambian).

La misma historia = el mismo artículo, sin tildes, guiones bajos, paréntesis ni sufijos de empresa ("Apple_Inc." =
"Apple" = "Apple Computer, Inc."), o del mismo año y con las palabras de uno dentro de las del otro."""

from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
from contextlib import contextmanager
from datetime import date, timedelta

from . import db

log = logging.getLogger(__name__)

CLAVE = "historias_usadas"     # bot_estado: [{"nucleo", "articulo", "anio", "dia", "origen", "texto"}]
DIAS = 7                       # ni el mismo día ni en la misma semana
GUARDAR_DIAS = 30
_SUFIJOS = {"inc", "corp", "corporation", "computer", "computers", "company", "co", "ltd", "llc", "sa", "s", "a",
            "plc", "gmbh", "ag", "holdings", "group"}
_LOCAL = threading.local()


def nucleo(articulo: str) -> str:
    t = unicodedata.normalize("NFKD", str(articulo or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\(.*?\)", " ", t.replace("_", " "))
    palabras = re.findall(r"[a-z0-9]+", t)
    sin = [w for w in palabras if w not in _SUFIJOS]
    return " ".join(sin or palabras)


def misma(a: dict, b: dict) -> bool:
    """¿Dos entradas ({nucleo, anio}) son la misma historia?"""
    na, nb = a.get("nucleo") or "", b.get("nucleo") or ""
    if not na or not nb:
        return False
    if na == nb:
        return True
    if a.get("anio") and a.get("anio") == b.get("anio"):
        sa, sb = set(na.split()), set(nb.split())
        return sa <= sb or sb <= sa
    return False


def leer(conn) -> list[dict]:
    try:
        return json.loads(db.get_valor(conn, CLAVE) or "[]")
    except ValueError:
        return []


def _guardar(conn, items: list[dict], hoy: date) -> None:
    desde = (hoy - timedelta(days=GUARDAR_DIAS)).isoformat()
    db.set_valor(conn, CLAVE, json.dumps([x for x in items if x.get("dia", "") >= desde], ensure_ascii=False))


def entrada(articulo: str, anio=None, texto: str = "") -> dict:
    try:
        anio = int(anio) if anio not in (None, "") else None
    except (TypeError, ValueError):
        anio = None
    return {"nucleo": nucleo(articulo), "articulo": str(articulo or ""), "anio": anio, "texto": str(texto or "")[:120]}


def usada(conn, hoy: date, articulo: str, anio=None) -> dict | None:
    """La entrada que la bloquea (usada hace menos de DIAS días), o None."""
    e = entrada(articulo, anio)
    desde = (hoy - timedelta(days=DIAS - 1)).isoformat()
    hasta = (hoy + timedelta(days=DIAS - 1)).isoformat()
    for x in leer(conn):
        if desde <= x.get("dia", "") <= hasta and misma(e, x):
            return x
    return None


def anotar(conn, hoy: date, articulo: str, anio=None, origen: str = "", texto: str = "") -> bool:
    """Reserva la historia. Devuelve False si ya estaba anotada hoy (no la duplica). Saca del banco sus mellizas (la
    misma historia con otro artículo)."""
    e = entrada(articulo, anio, texto)
    if not e["nucleo"]:
        return False
    items = leer(conn)
    if any(x.get("dia") == hoy.isoformat() and misma(e, x) for x in items):
        return False
    items.append(dict(e, dia=hoy.isoformat(), origen=origen))
    _guardar(conn, items, hoy)
    log.info("historia reservada (%s): %s %s", origen or "?", e["anio"] or "", e["articulo"])
    _sacar_del_banco(conn, e)
    return True


def _sacar_del_banco(conn, e: dict) -> None:
    from . import banco

    for canal in ("tecnologia", "latam"):
        items = banco.leer(conn, canal)
        quedan = [x for x in items if not misma(
            e, entrada(x.get("articulo") or (x.get("paginas") or [""])[0], x.get("anio")))]
        if len(quedan) < len(items):
            banco.guardar(conn, canal, quedan)
            log.info("banco %s: saqué %d con la misma historia (%s)", canal, len(items) - len(quedan), e["articulo"])


# --- el registro activo de quien propone (por hilo) ---

@contextmanager
def activo(conn, hoy: date, origen: str):
    previo = getattr(_LOCAL, "reg", None)
    sembrar(conn, hoy)
    _LOCAL.reg = (conn, hoy, origen)
    try:
        yield
    finally:
        _LOCAL.reg = previo


def bloqueada(evento, articulo: str = "") -> str:
    """Con un registro activo: el motivo si la historia de `evento` (con su artículo elegido) ya se usó esta semana."""
    reg = getattr(_LOCAL, "reg", None)
    if reg is None:
        return ""
    conn, hoy, _ = reg
    paginas = list(getattr(evento, "paginas", None) or [])
    for art in [a for a in [articulo] + paginas[:1] if a]:
        x = usada(conn, hoy, art, getattr(evento, "anio", None))
        if x:
            return (f"ya se usó esta historia ({x.get('articulo')}, {x.get('dia')}, {x.get('origen') or '?'}): "
                    "nunca dos videos de la misma en la semana")
    return ""


def al_crear(propuesta) -> None:
    """Desde Propuesta.__post_init__: con un registro activo, la historia queda reservada."""
    reg = getattr(_LOCAL, "reg", None)
    if reg is None:
        return
    conn, hoy, origen = reg
    ev = getattr(propuesta, "evento", None) or {}
    paginas = ev.get("paginas") or []
    if paginas:
        try:
            anotar(conn, hoy, paginas[0], ev.get("anio"), origen, ev.get("texto") or "")
        except Exception:      # anotar nunca frena una propuesta
            log.exception("no pude anotar la historia usada")


# --- lo de antes de esta regla ---

SEMBRADO = "historias_usadas_sembrado"


def sembrar(conn, hoy: date) -> None:
    """Una vez: las propuestas guardadas (efe:*), las historias de Latinoamérica de la semana (ph_latam:*) y la
    reserva de tecnología entran al registro."""
    if db.get_valor(conn, SEMBRADO):
        return
    n = 0
    for clave, valor in conn.execute("SELECT clave, valor FROM bot_estado WHERE clave LIKE 'efe:%'").fetchall():
        try:
            p = (json.loads(valor) or {}).get("propuesta") or {}
            ev = p.get("evento") or {}
            dia = date.fromisoformat(str(p.get("fecha"))[:10])
        except (ValueError, TypeError, AttributeError):
            continue
        if (ev.get("paginas") or []) and dia >= hoy - timedelta(days=DIAS):
            n += anotar(conn, min(dia, hoy), ev["paginas"][0], ev.get("anio"), "antes", ev.get("texto") or "")
    for k in range(DIAS):
        d = hoy - timedelta(days=k)
        try:
            ya = json.loads(db.get_valor(conn, f"ph_latam:{d.isoformat()}") or "[]")
        except ValueError:
            ya = []
        for x in ya:
            if x.get("articulo"):
                n += anotar(conn, d, x["articulo"], None, "antes", x.get("texto") or "")
    db.set_valor(conn, SEMBRADO, hoy.isoformat())
    log.info("historias usadas: %d de antes de la regla", n)
