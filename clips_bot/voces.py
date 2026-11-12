"""Cuántas voces de Gemini se gastaron hoy (Santi, 2026-11-12: "avisame por Telegram si las voces se
acercan al límite").

El plan gratis tiene un tope de pedidos de TTS por día y por PROYECTO de Google (no se publica: se
ve en AI Studio; Lo Encontré asume 10), y se reinicia a la medianoche de California. La clave
principal la usan Pequeña Historia y Lo Encontré (~/bot-videos, la misma GEMINI_API_KEY: comparado
por huella el 2026-11-12); la segunda es de otro proyecto. Lo de Pequeña Historia sale de
gemini_uso (clips.db); lo de Lo Encontré, de su base (estado `tts_uso:<día de California>`).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import db

CLAVE_AVISO = "voces_aviso"   # bot_estado: "<día>:<clave>" ya avisado


def _pacifico():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/Los_Angeles")
    except Exception:
        return timezone(timedelta(hours=-8))


def dia_cuota(ahora: datetime | None = None) -> tuple[str, datetime]:
    """(día de la cuota en California, desde cuándo cuenta, en UTC)."""
    ahora = ahora or datetime.now(timezone.utc)
    local = ahora.astimezone(_pacifico())
    inicio = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return local.strftime("%Y-%m-%d"), inicio


def uso_hoy(conn, lo_encontre_db: str | Path | None, ahora: datetime | None = None) -> dict:
    """{"principal": n, "segunda": n, "lo_encontre": n} de hoy (día de California). Lo Encontré
    gasta de la principal. Sin su base (en la compu), 0."""
    dia, desde = dia_cuota(ahora)
    out = {"principal": 0, "segunda": 0, "lo_encontre": 0, "dia": dia}
    for clave, n in conn.execute(
            "SELECT clave, COUNT(*) FROM gemini_uso WHERE modelo LIKE '%tts%' AND cache = 0 AND ts >= ? "
            "GROUP BY clave", (desde.isoformat(),)):
        if clave in out:
            out[clave] = int(n)
    if lo_encontre_db and Path(lo_encontre_db).exists():
        try:
            with sqlite3.connect(f"file:{lo_encontre_db}?mode=ro", uri=True, timeout=5) as c:
                fila = c.execute("SELECT valor FROM estado WHERE clave = ?", (f"tts_uso:{dia}",)).fetchone()
            out["lo_encontre"] = int(str(fila[0]).strip() or 0) if fila else 0
        except (sqlite3.Error, ValueError):
            pass
    return out


def avisos(conn, uso: dict, tope: int, aviso: int) -> list[str]:
    """Los avisos que corresponden (una vez por día y clave): la principal cuenta lo de Lo Encontré."""
    textos = []
    cuentas = {"principal": uso["principal"] + uso["lo_encontre"], "segunda": uso["segunda"]}
    for clave, n in cuentas.items():
        marca = f"{uso['dia']}:{clave}"
        if n < aviso or marca in (db.get_valor(conn, CLAVE_AVISO) or "").split(","):
            continue
        db.set_valor(conn, CLAVE_AVISO, ",".join(filter(None, [db.get_valor(conn, CLAVE_AVISO), marca]))[-500:])
        detalle = (f" ({uso['principal']} de Pequeña Historia + {uso['lo_encontre']} de Lo Encontré)"
                   if clave == "principal" else "")
        textos.append(f"🔧 Claude Code: ⚠️ <b>Voces de Gemini</b>: la clave {clave} lleva {n} de ~{tope} "
                      f"hoy{detalle}. Se renueva a las 5 de la mañana; si se acaba, Pequeña Historia "
                      "sale con Piper y Lo Encontré sale muda.")
    return textos
