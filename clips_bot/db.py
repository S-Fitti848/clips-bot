"""Estado en SQLite (data/clips.db)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    clip_id          TEXT PRIMARY KEY,
    broadcaster      TEXT NOT NULL,
    title            TEXT,
    game_name        TEXT,
    duration_s       REAL,
    view_count       INTEGER,
    created_at       TEXT,          -- ISO UTC, fecha de creación del clip en Twitch
    url              TEXT,
    estado           TEXT NOT NULL, -- candidato | descartado | procesado | entregado
    motivo           TEXT,          -- por qué se descartó, si aplica
    first_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id     TEXT NOT NULL REFERENCES clips(clip_id),
    plataforma  TEXT NOT NULL,      -- youtube | tiktok | instagram | facebook
    url         TEXT,
    video_id    TEXT,
    fecha       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    publish_at  TEXT,
    UNIQUE (clip_id, plataforma)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.executescript(SCHEMA_CURSOR)
    conn.executescript(SCHEMA_ESTADO)
    return conn


def ids_vistos(conn: sqlite3.Connection) -> set[str]:
    """Clips que ya pasaron por el pipeline (cualquier estado) y no se reconsideran."""
    return {row[0] for row in conn.execute("SELECT clip_id FROM clips")}


def registrar_clip(
    conn: sqlite3.Connection,
    clip_id: str,
    broadcaster: str,
    estado: str,
    motivo: str | None = None,
    *,
    title: str = "",
    game_name: str = "",
    duration_s: float | None = None,
    view_count: int | None = None,
    created_at: str | None = None,
    url: str = "",
) -> None:
    """Inserta el clip o actualiza estado/motivo/vistas si ya estaba (conserva first_seen_at)."""
    conn.execute(
        """
        INSERT INTO clips (clip_id, broadcaster, title, game_name, duration_s, view_count,
                           created_at, url, estado, motivo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(clip_id) DO UPDATE SET
            estado = excluded.estado,
            motivo = excluded.motivo,
            view_count = COALESCE(excluded.view_count, clips.view_count)
        """,
        (clip_id, broadcaster, title, game_name, duration_s, view_count, created_at, url, estado, motivo),
    )
    conn.commit()


def estados(conn: sqlite3.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT clip_id, estado FROM clips"))


def set_estado(conn: sqlite3.Connection, clip_id: str, estado: str) -> None:
    conn.execute("UPDATE clips SET estado = ? WHERE clip_id = ?", (estado, clip_id))
    conn.commit()


# ---- cursor del catálogo por streamer ----------------------------------------------
# El cursor de Helix solo sirve para la misma consulta, así que se guarda junto con la ventana de
# fechas con la que se generó. Mientras el ciclo dure, la ventana queda fija.

SCHEMA_CURSOR = """
CREATE TABLE IF NOT EXISTS catalogo_cursor (
    streamer     TEXT PRIMARY KEY,
    cursor       TEXT,              -- NULL = arrancar desde la primera página
    desde        TEXT NOT NULL,     -- ISO UTC
    hasta        TEXT NOT NULL,     -- ISO UTC
    actualizado  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""


def get_cursor(conn: sqlite3.Connection, streamer: str) -> tuple[str | None, str, str] | None:
    fila = conn.execute("SELECT cursor, desde, hasta FROM catalogo_cursor WHERE streamer = ?", (streamer,)).fetchone()
    return tuple(fila) if fila else None  # type: ignore[return-value]


def set_cursor(conn: sqlite3.Connection, streamer: str, cursor: str | None, desde: str, hasta: str) -> None:
    conn.execute(
        """
        INSERT INTO catalogo_cursor (streamer, cursor, desde, hasta) VALUES (?, ?, ?, ?)
        ON CONFLICT(streamer) DO UPDATE SET cursor = excluded.cursor, desde = excluded.desde,
            hasta = excluded.hasta, actualizado = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (streamer, cursor, desde, hasta),
    )
    conn.commit()


def borrar_cursor(conn: sqlite3.Connection, streamer: str) -> None:
    """Ciclo terminado: la próxima corrida arranca con ventana nueva desde la primera página."""
    conn.execute("DELETE FROM catalogo_cursor WHERE streamer = ?", (streamer,))
    conn.commit()


# ---- estado de streamers (exclusión por reclamo de copyright) -----------------------

SCHEMA_ESTADO = """
CREATE TABLE IF NOT EXISTS streamer_estado (
    streamer  TEXT PRIMARY KEY,
    estado    TEXT NOT NULL,          -- excluido
    motivo    TEXT,
    clip_id   TEXT,
    fecha     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS bot_estado (
    clave  TEXT PRIMARY KEY,
    valor  TEXT
);
"""


def excluir_streamer(conn: sqlite3.Connection, streamer: str, motivo: str, clip_id: str | None = None) -> bool:
    """Excluye al streamer (reclamo o strike). Devuelve False si ya estaba excluido."""
    if conn.execute("SELECT 1 FROM streamer_estado WHERE streamer = ?", (streamer,)).fetchone():
        return False
    conn.execute("INSERT INTO streamer_estado (streamer, estado, motivo, clip_id) VALUES (?, 'excluido', ?, ?)",
                 (streamer, motivo, clip_id))
    conn.commit()
    return True


def excluidos(conn: sqlite3.Connection) -> dict[str, str]:
    """streamer → motivo."""
    return {s: m or "" for s, m in conn.execute("SELECT streamer, motivo FROM streamer_estado")}


def readmitir_streamer(conn: sqlite3.Connection, streamer: str) -> None:
    conn.execute("DELETE FROM streamer_estado WHERE streamer = ?", (streamer,))
    conn.commit()


def get_valor(conn: sqlite3.Connection, clave: str) -> str | None:
    fila = conn.execute("SELECT valor FROM bot_estado WHERE clave = ?", (clave,)).fetchone()
    return fila[0] if fila else None


def set_valor(conn: sqlite3.Connection, clave: str, valor: str) -> None:
    conn.execute("INSERT INTO bot_estado (clave, valor) VALUES (?, ?) "
                 "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor", (clave, valor))
    conn.commit()


def clip_de(conn: sqlite3.Connection, clip_id: str) -> tuple[str, str] | None:
    """(streamer, url) del clip, o None si no está en la DB."""
    fila = conn.execute("SELECT broadcaster, url FROM clips WHERE clip_id = ?", (clip_id,)).fetchone()
    return (fila[0], fila[1]) if fila else None
