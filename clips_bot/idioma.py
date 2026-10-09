"""Idioma de los mensajes del bot (pedido de Santi, 2026-10-08, para la demo de la auditoría de
YouTube): `/lang en` pone en inglés los mensajes que se ven al grabar la pantalla (aprobación,
subida, /subidas, cancelar, /metricas, búsqueda pública y /demo), `/lang es` vuelve.

Se guarda en la DB (`bot_estado.idioma`) y la escucha lo relee en cada vuelta, igual que los
accesos: cambia sin reiniciar nada. Lo que no está traducido sigue en castellano.
"""

from __future__ import annotations

import sqlite3

CLAVE = "idioma"
IDIOMAS = ("es", "en")
_estado = {"lang": "es"}


def actual() -> str:
    return _estado["lang"]


def L(es: str, en: str) -> str:
    """El texto en el idioma actual."""
    return en if _estado["lang"] == "en" else es


def poner(lang: str) -> None:
    _estado["lang"] = lang if lang in IDIOMAS else "es"


def cargar(conn: sqlite3.Connection) -> str:
    from . import db

    poner(db.get_valor(conn, CLAVE) or "es")
    return actual()


def guardar(conn: sqlite3.Connection, lang: str) -> str:
    from . import db

    poner(lang)
    db.set_valor(conn, CLAVE, actual())
    return actual()
