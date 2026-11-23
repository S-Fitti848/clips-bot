"""Ninguna marca en Pequeña Historia (tecnología) y en Así Nació en la misma semana (Santi, 2026-11-23).

Así Nació anota sus marcas en `animacion_videos`; los videos de tecnología de Pequeña Historia, al mandarse, dejan el
texto del hecho y el título en `bot_estado.tec_marcas_semana`. Una marca del catálogo de Así Nació que aparece en ese
texto (palabra entera, sin tildes ni mayúsculas) cuenta como usada por Pequeña Historia esos 7 días.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, timedelta

from . import db

REGISTRO = "tec_marcas_semana"
DIAS = 7


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def menciona(texto: str, nombres) -> list[str]:
    """Los nombres (marcas) que aparecen en el texto como palabras enteras."""
    t = f" {_norm(texto)} "
    return [n for n in nombres if _norm(n) and len(_norm(n)) >= 2 and f" {_norm(n)} " in t]


def anotar_ph(conn, dia: date, texto: str) -> None:
    try:
        items = json.loads(db.get_valor(conn, REGISTRO) or "[]")
    except ValueError:
        items = []
    desde = (dia - timedelta(days=30)).isoformat()
    items = [x for x in items if str(x.get("dia")) >= desde] + [{"dia": dia.isoformat(), "texto": texto[:2000]}]
    db.set_valor(conn, REGISTRO, json.dumps(items, ensure_ascii=False))


def textos_ph(conn, hoy: date, dias: int = DIAS) -> list[str]:
    try:
        items = json.loads(db.get_valor(conn, REGISTRO) or "[]")
    except ValueError:
        return []
    desde = (hoy - timedelta(days=dias - 1)).isoformat()
    return [str(x.get("texto") or "") for x in items if str(x.get("dia")) >= desde]


def usadas_ph(conn, hoy: date, nombres) -> set[str]:
    """Las marcas del catálogo que salieron en un video de tecnología de Pequeña Historia esta semana."""
    out: set[str] = set()
    for t in textos_ph(conn, hoy):
        out.update(menciona(t, nombres))
    return out


def usadas_an(conn, hoy: date) -> set[str]:
    """Las marcas de Así Nació de esta semana (las que Pequeña Historia no usa)."""
    from .animacion import marcas

    try:
        return set(marcas.marcas_recientes(conn, hoy, DIAS))
    except Exception:       # noqa: BLE001 — sin la tabla todavía
        return set()
