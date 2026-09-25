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
CREATE TABLE IF NOT EXISTS votos (
    clip_id    TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    voto       INTEGER NOT NULL,          -- 1 o -1
    puntaje    INTEGER NOT NULL DEFAULT 0, -- el que le puso Gemini, para calibrar el corte
    relleno    INTEGER NOT NULL DEFAULT 0,
    ts         TEXT NOT NULL,
    PRIMARY KEY (clip_id, user_id)
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


# ---- turnos: trabajo pesado y búsquedas -------------------------------------
# Procesar un clip es descarga + Whisper + OCR + render: en la Pi son minutos y calienta. No puede
# haber dos de esas cosas a la vez, y la corrida diaria no puede pisarse con un /buscar.
#
# El control va en la DB y no en memoria porque son PROCESOS distintos: el timer de systemd
# (clips-bot.service), el modo escucha (clips-bot-telegram.service) y cualquier comando a mano.
# Cada turno vence solo, por si el proceso que lo tomó murió a la mitad.

RECURSO_PESADO = "pesado"      # lo toman `diario` y cada /buscar: uno solo a la vez
RECURSO_BUSQUEDAS = "busquedas"  # cuántos /buscar puede haber esperando, ver MAX_BUSQUEDAS


def _clave_turno(recurso: str) -> str:
    return f"turnos_{recurso}"


def turnos_activos(conn: sqlite3.Connection, recurso: str,
                   vencimiento_s: float = 3600) -> list[tuple[str, float]]:
    import json
    import time

    crudo = get_valor(conn, _clave_turno(recurso))
    ahora = time.time()
    try:
        activos = json.loads(crudo) if crudo else []
    except ValueError:
        activos = []
    return [(str(t), float(ts)) for t, ts in activos if ahora - float(ts) < vencimiento_s]


def tomar_turno(conn: sqlite3.Connection, recurso: str, token: str, maximo: int = 1,
                vencimiento_s: float = 3600) -> bool:
    """Reserva un lugar. False si ya hay `maximo` tomados (los vencidos no cuentan)."""
    import json
    import time

    activos = turnos_activos(conn, recurso, vencimiento_s)
    if len(activos) >= maximo:
        set_valor(conn, _clave_turno(recurso), json.dumps(activos))  # deja limpios los vencidos
        return False
    activos.append((token, time.time()))
    set_valor(conn, _clave_turno(recurso), json.dumps(activos))
    return True


def soltar_turno(conn: sqlite3.Connection, recurso: str, token: str,
                 vencimiento_s: float = 3600) -> None:
    import json

    activos = [(t, ts) for t, ts in turnos_activos(conn, recurso, vencimiento_s) if t != token]
    set_valor(conn, _clave_turno(recurso), json.dumps(activos))


def hay_trabajo_pesado(conn: sqlite3.Connection, vencimiento_s: float = 3600) -> str | None:
    """Qué está corriendo ahora mismo (el token dice quién), o None si está libre."""
    activos = turnos_activos(conn, RECURSO_PESADO, vencimiento_s)
    return activos[0][0] if activos else None


# ---- votos 👍/👎 -------------------------------------------------------------
# Para qué: el corte de calidad (textos.puntaje_min) hoy es un número puesto a ojo. Con dos semanas
# de votos, el corte se elige con datos: el puntaje a partir del cual Santi vota más 👍 que 👎.

def votar(conn: sqlite3.Connection, clip_id: str, voto: int, user_id: str, puntaje: int = 0,
          relleno: bool = False) -> None:
    """voto: 1 (pulgar arriba) o -1. Un voto por clip y por persona; el último pisa al anterior."""
    conn.execute(
        """INSERT INTO votos (clip_id, user_id, voto, puntaje, relleno, ts)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(clip_id, user_id) DO UPDATE SET
               voto = excluded.voto, puntaje = excluded.puntaje,
               relleno = excluded.relleno, ts = excluded.ts""",
        (clip_id, str(user_id), int(voto), int(puntaje), 1 if relleno else 0),
    )
    conn.commit()


def voto_de(conn: sqlite3.Connection, clip_id: str, user_id: str) -> int | None:
    fila = conn.execute("SELECT voto FROM votos WHERE clip_id = ? AND user_id = ?",
                        (clip_id, str(user_id))).fetchone()
    return fila[0] if fila else None


def votos_por_puntaje(conn: sqlite3.Connection) -> list[tuple[int, int, int]]:
    """[(puntaje, 👍, 👎)] ordenado. Con esto se elige el corte: el puntaje desde el cual gana 👍."""
    filas = conn.execute(
        """SELECT puntaje,
                  SUM(CASE WHEN voto > 0 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN voto < 0 THEN 1 ELSE 0 END)
           FROM votos WHERE puntaje > 0 GROUP BY puntaje ORDER BY puntaje"""
    ).fetchall()
    return [(int(p), int(a or 0), int(b or 0)) for p, a, b in filas]
