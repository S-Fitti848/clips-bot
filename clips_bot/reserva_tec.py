"""Colchón de tecnología (Santi, 2026-11-23: "tené siempre 3 videos de tecnología ya armados, revisados y listos").

Tecnología es lo que mejor anda en YouTube (~10.000 vistas por video) y pasa a ser la prioridad número uno: 2 videos por
día (`efemerides.por_dia`). La reserva son videos YA ARMADOS de historias que no dependen de la fecha (las del banco de
tecnología, con el guion que no dice "hoy"), con la revisión del video terminado hecha. Si el del día falla, o para el
segundo del día, sale uno de la reserva; cuando baja de `efemerides.reserva` (3), se arma otro solo, de a uno, fuera de
la madrugada y con el turno pesado libre.

Estado en bot_estado:
- `reserva_tec`: [{"token", "clip_id", "titulo", "subtema", "fallas", "corregidas", "revisado", "motor", "relajado",
  "local", "costo", "armado"}], el más viejo primero. La propuesta (`efe:<token>`) y el meta (ready/) quedan guardados.
- `tec_entregados:<día>`: cuántos de tecnología se mandaron ese día (del día y de la reserva).
- `reserva_tec_fallas:<día>`: cuántas veces falló armar uno ese día (tope, para no gastar de más).
"""
from __future__ import annotations

import json
from datetime import date

from . import db

CLAVE = "reserva_tec"
ENTREGADOS = "tec_entregados:{}"
FALLAS = "reserva_tec_fallas:{}"
MAX_FALLAS_DIA = 3          # armar uno que no pasa el estándar cuesta ~US$ 0,30: como mucho 3 intentos fallidos por día
DESDE, HASTA = "06:30", "22:00"   # nunca en la madrugada (03:30-06:30 es de los videos del día)


def leer(conn) -> list[dict]:
    try:
        return json.loads(db.get_valor(conn, CLAVE) or "[]")
    except ValueError:
        return []


def guardar(conn, items: list[dict]) -> None:
    db.set_valor(conn, CLAVE, json.dumps(items, ensure_ascii=False))


def agregar(conn, item: dict) -> None:
    guardar(conn, leer(conn) + [item])


def sacar_primero(conn) -> dict | None:
    """El más viejo de la reserva (sale de la lista)."""
    items = leer(conn)
    if not items:
        return None
    guardar(conn, items[1:])
    return items[0]


def entregados(conn, dia: date) -> int:
    return int(db.get_valor(conn, ENTREGADOS.format(dia.isoformat())) or 0)


def contar_entregado(conn, dia: date, n: int = 1) -> None:
    db.set_valor(conn, ENTREGADOS.format(dia.isoformat()), str(entregados(conn, dia) + n))


def faltan_hoy(conn, dia: date, por_dia: int) -> int:
    return max(0, int(por_dia) - entregados(conn, dia))


def fallas_hoy(conn, dia: date) -> int:
    return int(db.get_valor(conn, FALLAS.format(dia.isoformat())) or 0)


def anotar_falla(conn, dia: date) -> None:
    db.set_valor(conn, FALLAS.format(dia.isoformat()), str(fallas_hoy(conn, dia) + 1))


def hay_que_armar(conn, objetivo: int, dia: date, hm: str) -> bool:
    return (DESDE <= hm < HASTA and len(leer(conn)) < int(objetivo)
            and fallas_hoy(conn, dia) < MAX_FALLAS_DIA)
