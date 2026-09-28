"""Estado en SQLite (data/clips.db)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
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
CREATE TABLE IF NOT EXISTS pedidos (
    token   TEXT PRIMARY KEY,
    tipo    TEXT NOT NULL,             -- buscar | ya | diario
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    criterio TEXT NOT NULL DEFAULT '{}',  -- json: logins, palabras, dias
    dados   TEXT NOT NULL DEFAULT '[]',   -- json: clip_ids ya entregados de este pedido
    creado  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    tipo    TEXT NOT NULL DEFAULT '',      -- private | group | supergroup
    nombre  TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',      -- si es privado, de quién es
    activo  INTEGER NOT NULL DEFAULT 0,    -- ¿recibe la entrega de las 05:00?
    visto   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS streamers_extra (
    login      TEXT PRIMARY KEY,
    accion     TEXT NOT NULL,            -- alta | baja
    plataforma TEXT NOT NULL DEFAULT 'twitch',
    grupo      TEXT NOT NULL DEFAULT 'argentinos',
    quien      TEXT NOT NULL,
    ts         TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS subidas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id    TEXT NOT NULL,
    canal      TEXT NOT NULL,            -- rots | pequena_historia (youtube.CANALES)
    video_id   TEXT,
    publish_at TEXT,                     -- ISO UTC
    estado     TEXT NOT NULL,            -- programada | cancelada | error
    error      TEXT,
    creada     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS carpetas (
    nombre   TEXT PRIMARY KEY,           -- el `grupo` de los streamers: argentinos, evento, catalogo…
    etiqueta TEXT NOT NULL DEFAULT '',   -- cómo se muestra: "Argentinos", "Dedsafío"
    en_vivo  INTEGER NOT NULL DEFAULT 0, -- ¿el modo en vivo vigila a los de esta carpeta?
    diarios  INTEGER NOT NULL DEFAULT 1, -- ¿entran en la corrida de las 05:00 (y /ya)?
    creada   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bot_estado (
    clave  TEXT PRIMARY KEY,
    valor  TEXT
);

CREATE TABLE IF NOT EXISTS envivo_alertas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer    TEXT NOT NULL,
    plataforma  TEXT NOT NULL,
    chat_id     TEXT NOT NULL,
    estado      TEXT NOT NULL,           -- ver ESTADOS_ALERTA
    motivo      TEXT,
    clip_id     TEXT,                    -- el elegido para procesar
    url         TEXT,
    clips       TEXT NOT NULL DEFAULT '[]',  -- json: todos los clip_id del momento
    creadores   INTEGER NOT NULL,
    -- Los cuatro tiempos, en ISO UTC, para ver dónde se pierde el tiempo:
    momento     TEXT NOT NULL,           -- el primer clip del momento (lo más cerca del hecho que se sabe)
    umbral      TEXT NOT NULL,           -- cuando clipeó el N-ésimo creador: desde ahí era detectable
    detectado   TEXT NOT NULL,           -- cuando lo vio el bot
    inicio      TEXT,                    -- cuando arrancó a procesarlo (después de esperar turno)
    entregado   TEXT,                    -- cuando salió el mensaje por Telegram
    tiempos     TEXT                     -- json: tiempos por etapa de procesar()
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


def borrar_valor(conn: sqlite3.Connection, clave: str) -> None:
    conn.execute("DELETE FROM bot_estado WHERE clave = ?", (clave,))
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


def votos_por_streamer(conn: sqlite3.Connection, user_ids) -> dict[str, tuple[int, int]]:
    """{streamer: (👍, 👎)} con los votos de esos usuarios. El streamer sale de la tabla clips
    (`broadcaster` es el login, en Twitch y en Kick); un multi-POV no está ahí y no cuenta."""
    ids = [str(u) for u in user_ids]
    if not ids:
        return {}
    filas = conn.execute(
        f"""SELECT c.broadcaster,
                   SUM(CASE WHEN v.voto > 0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN v.voto < 0 THEN 1 ELSE 0 END)
            FROM votos v JOIN clips c ON c.clip_id = v.clip_id
            WHERE v.user_id IN ({",".join("?" * len(ids))})
            GROUP BY c.broadcaster""", ids).fetchall()
    return {str(s).lower(): (int(a or 0), int(b or 0)) for s, a, b in filas}


def votos_por_puntaje(conn: sqlite3.Connection) -> list[tuple[int, int, int]]:
    """[(puntaje, 👍, 👎)] ordenado. Con esto se elige el corte: el puntaje desde el cual gana 👍."""
    filas = conn.execute(
        """SELECT puntaje,
                  SUM(CASE WHEN voto > 0 THEN 1 ELSE 0 END),
                  SUM(CASE WHEN voto < 0 THEN 1 ELSE 0 END)
           FROM votos WHERE puntaje > 0 GROUP BY puntaje ORDER BY puntaje"""
    ).fetchall()
    return [(int(p), int(a or 0), int(b or 0)) for p, a, b in filas]


# ---- prueba del multi-POV ----------------------------------------------------
# Se prendió el 2026-09-24 a prueba: si junta VOTOS_NEGATIVOS 👎 dentro del período, se apaga solo.
# El interruptor va en la DB y no en settings.yaml a propósito: el YAML está en git y lo editan las
# personas; esto lo decide el bot y tiene que poder apagarse sin un commit ni un deploy.

PREFIJO_MULTIPOV = "multipov_"
CLAVE_MP_DESDE = "multipov_prueba_desde"
CLAVE_MP_APAGADO = "multipov_apagado"


def arrancar_prueba_multipov(conn: sqlite3.Connection, cuando: str) -> None:
    """Marca desde cuándo se cuentan los 👎, y limpia un apagado anterior."""
    set_valor(conn, CLAVE_MP_DESDE, cuando)
    conn.execute("DELETE FROM bot_estado WHERE clave = ?", (CLAVE_MP_APAGADO,))
    conn.commit()


def multipov_apagado(conn: sqlite3.Connection) -> str | None:
    """El motivo por el que se apagó solo, o None si sigue andando."""
    return get_valor(conn, CLAVE_MP_APAGADO)


def apagar_multipov(conn: sqlite3.Connection, motivo: str) -> None:
    set_valor(conn, CLAVE_MP_APAGADO, motivo)


def _como_sqlite(iso: str) -> str:
    """ISO 8601 -> el formato que escribe datetime('now') de SQLite, que es con lo que se compara.

    Hace falta porque las dos formas se comparan como TEXTO: "2026-09-24 10:00:00" contra
    "2026-09-24T10:00:00+00:00" da False por el espacio contra la T, y el filtro se comía todo.
    """
    from datetime import timezone

    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def pulgares_abajo_multipov(conn: sqlite3.Connection, desde: str | None = None) -> list[str]:
    """Los multi-POV que recibieron 👎 desde `desde` (ISO). Uno por clip, no por voto."""
    sql = ("SELECT DISTINCT clip_id FROM votos WHERE voto < 0 AND clip_id LIKE ?"
           + (" AND ts >= ?" if desde else "") + " ORDER BY ts")
    args = [PREFIJO_MULTIPOV + "%"] + ([_como_sqlite(desde)] if desde else [])
    return [r[0] for r in conn.execute(sql, args)]


# ---- a qué chat se entregan los Shorts --------------------------------------
# Va en la DB y no solo en el .env porque el id de un grupo no se sabe de antemano: hay que estar
# adentro del grupo para verlo. Con `/aca` el bot lo anota solo, sin editar archivos ni pedir sudo.

CLAVE_CHAT = "chat_entrega"


def chat_entrega(conn: sqlite3.Connection) -> str | None:
    return get_valor(conn, CLAVE_CHAT)


def set_chat_entrega(conn: sqlite3.Connection, chat_id: str) -> None:
    set_valor(conn, CLAVE_CHAT, str(chat_id))


def borrar_chat_entrega(conn: sqlite3.Connection) -> None:
    borrar_valor(conn, CLAVE_CHAT)


# ---- destinos de la entrega diaria ------------------------------------------
# Un bot NO puede escribirle primero a nadie: la persona tiene que haberle mandado algo antes. Por
# eso los chats se van anotando solos cada vez que alguien escribe, y /destinos solo puede ofrecer
# los que ya existen. A un permitido que nunca escribió, /destinos le muestra que falta su /start.

def ver_chat(conn: sqlite3.Connection, chat_id: str, tipo: str = "", nombre: str = "",
             user_id: str = "") -> None:
    """Anota que este chat existe y que el bot puede escribirle. No toca `activo`."""
    if not chat_id:
        return
    conn.execute(
        """INSERT INTO chats (chat_id, tipo, nombre, user_id, activo, visto)
           VALUES (?, ?, ?, ?, 0, datetime('now'))
           ON CONFLICT(chat_id) DO UPDATE SET
               tipo = COALESCE(NULLIF(excluded.tipo, ''), chats.tipo),
               nombre = COALESCE(NULLIF(excluded.nombre, ''), chats.nombre),
               user_id = COALESCE(NULLIF(excluded.user_id, ''), chats.user_id),
               visto = excluded.visto""",
        (str(chat_id), tipo, nombre, str(user_id)),
    )
    conn.commit()


def chats_conocidos(conn: sqlite3.Connection) -> list[dict]:
    filas = conn.execute(
        "SELECT chat_id, tipo, nombre, user_id, activo FROM chats ORDER BY tipo, nombre").fetchall()
    return [{"chat_id": f[0], "tipo": f[1], "nombre": f[2], "user_id": f[3], "activo": bool(f[4])}
            for f in filas]


def destinos(conn: sqlite3.Connection) -> list[str]:
    """A dónde va la entrega de las 05:00. Vacío = a ninguno (lo dice el aviso de la corrida)."""
    return [f[0] for f in conn.execute("SELECT chat_id FROM chats WHERE activo = 1 ORDER BY tipo")]


def marcar_destino(conn: sqlite3.Connection, chat_id: str, activo: bool) -> None:
    conn.execute("UPDATE chats SET activo = ? WHERE chat_id = ?", (1 if activo else 0, str(chat_id)))
    conn.commit()


def alternar_destino(conn: sqlite3.Connection, chat_id: str) -> bool:
    """Prende o apaga. Devuelve cómo quedó."""
    fila = conn.execute("SELECT activo FROM chats WHERE chat_id = ?", (str(chat_id),)).fetchone()
    nuevo = not (fila and fila[0])
    marcar_destino(conn, chat_id, nuevo)
    return nuevo


# ---- cuántos clips por entrega, y los pedidos ---------------------------------
# El "pedido" es lo que permite que los botones "➕ 3 más" y "🔁 Reemplazar" sepan de dónde sacar el
# siguiente: guarda con qué criterio se armó la entrega y qué ya se mandó, para no repetir.

CANTIDAD_DEFAULT = 3
CANTIDAD_MAX = 6


def cantidad_diaria(conn: sqlite3.Connection) -> int:
    v = get_valor(conn, "cantidad_diaria")
    try:
        return max(1, min(CANTIDAD_MAX, int(v))) if v else CANTIDAD_DEFAULT
    except ValueError:
        return CANTIDAD_DEFAULT


def set_cantidad_diaria(conn: sqlite3.Connection, n: int) -> int:
    n = max(1, min(CANTIDAD_MAX, int(n)))
    set_valor(conn, "cantidad_diaria", str(n))
    return n


def crear_pedido(conn: sqlite3.Connection, token: str, tipo: str, chat_id: str, user_id: str,
                 criterio: dict) -> None:
    import json as _json

    conn.execute(
        """INSERT INTO pedidos (token, tipo, chat_id, user_id, criterio, dados, creado)
           VALUES (?, ?, ?, ?, ?, '[]', datetime('now'))
           ON CONFLICT(token) DO UPDATE SET criterio = excluded.criterio""",
        (token, tipo, str(chat_id), str(user_id), _json.dumps(criterio, ensure_ascii=False)),
    )
    conn.commit()


def pedido(conn: sqlite3.Connection, token: str) -> dict | None:
    import json as _json

    f = conn.execute(
        "SELECT token, tipo, chat_id, user_id, criterio, dados FROM pedidos WHERE token = ?",
        (token,)).fetchone()
    if not f:
        return None
    return {"token": f[0], "tipo": f[1], "chat_id": f[2], "user_id": f[3],
            "criterio": _json.loads(f[4] or "{}"), "dados": _json.loads(f[5] or "[]")}


def anotar_dado(conn: sqlite3.Connection, token: str, clip_id: str) -> None:
    """Deja constancia de que ese clip ya salió por este pedido: los botones no repiten."""
    import json as _json

    p = pedido(conn, token)
    if not p:
        return
    if clip_id not in p["dados"]:
        p["dados"].append(clip_id)
    conn.execute("UPDATE pedidos SET dados = ? WHERE token = ?",
                 (_json.dumps(p["dados"]), token))
    conn.commit()


# ---- modo en vivo -------------------------------------------------------------
# El interruptor va en la DB (como el del multi-POV): lo prende y lo apaga un comando de Telegram,
# no un commit. Guardar el chat que lo prendió ES el interruptor: sin chat, está apagado.

CLAVE_ENVIVO = "envivo_chat"
ESTADOS_ALERTA = ("pendiente", "procesando", "entregada", "descartada", "sin_clip", "tope", "vencida")
# Las que cuentan para el tope por hora: las que terminan (o pueden terminar) en un mensaje.
ESTADOS_CON_MENSAJE = ("pendiente", "procesando", "entregada")


def envivo_chat(conn: sqlite3.Connection) -> str | None:
    return get_valor(conn, CLAVE_ENVIVO)


def prender_envivo(conn: sqlite3.Connection, chat_id: str) -> None:
    set_valor(conn, CLAVE_ENVIVO, str(chat_id))


def apagar_envivo(conn: sqlite3.Connection) -> None:
    borrar_valor(conn, CLAVE_ENVIVO)


def _alerta(fila) -> dict:
    import json as _json

    claves = ("id", "streamer", "plataforma", "chat_id", "estado", "motivo", "clip_id", "url", "clips",
              "creadores", "momento", "umbral", "detectado", "inicio", "entregado", "tiempos")
    d = dict(zip(claves, fila))
    d["clips"] = _json.loads(d["clips"] or "[]")
    d["tiempos"] = _json.loads(d["tiempos"] or "{}")
    return d


_COLS_ALERTA = ("id, streamer, plataforma, chat_id, estado, motivo, clip_id, url, clips, creadores, "
                "momento, umbral, detectado, inicio, entregado, tiempos")


def crear_alerta(conn: sqlite3.Connection, *, streamer: str, plataforma: str, chat_id: str,
                 estado: str, clips: list[str], creadores: int, momento: str, umbral: str,
                 detectado: str, clip_id: str = "", url: str = "", motivo: str | None = None) -> int:
    import json as _json

    cur = conn.execute(
        """INSERT INTO envivo_alertas (streamer, plataforma, chat_id, estado, motivo, clip_id, url,
               clips, creadores, momento, umbral, detectado)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (streamer, plataforma, str(chat_id), estado, motivo, clip_id, url, _json.dumps(clips),
         creadores, momento, umbral, detectado))
    conn.commit()
    return int(cur.lastrowid)


def actualizar_alerta(conn: sqlite3.Connection, alerta_id: int, **campos) -> None:
    import json as _json

    if not campos:
        return
    for k in ("clips", "tiempos"):
        if k in campos and not isinstance(campos[k], str):
            campos[k] = _json.dumps(campos[k], ensure_ascii=False)
    sets = ", ".join(f"{k} = ?" for k in campos)
    conn.execute(f"UPDATE envivo_alertas SET {sets} WHERE id = ?", (*campos.values(), alerta_id))
    conn.commit()


def alertas(conn: sqlite3.Connection, desde_iso: str | None = None, streamer: str | None = None,
            estados: tuple[str, ...] | None = None) -> list[dict]:
    """Alertas detectadas desde `desde_iso` (ISO UTC, se compara como texto: todas se escriben igual)."""
    sql, args = f"SELECT {_COLS_ALERTA} FROM envivo_alertas WHERE 1 = 1", []
    if desde_iso:
        sql += " AND detectado >= ?"
        args.append(desde_iso)
    if streamer:
        sql += " AND streamer = ?"
        args.append(streamer)
    if estados:
        sql += f" AND estado IN ({', '.join('?' for _ in estados)})"
        args.extend(estados)
    return [_alerta(f) for f in conn.execute(sql + " ORDER BY id", args)]


def marcar_si_nuevo(conn: sqlite3.Connection, clip_id: str, broadcaster: str, estado: str,
                    motivo: str, url: str = "") -> None:
    """Como registrar_clip, pero sin pisar un clip que ya estaba (ej. uno entregado)."""
    conn.execute("INSERT OR IGNORE INTO clips (clip_id, broadcaster, url, estado, motivo) "
                 "VALUES (?, ?, ?, ?, ?)", (clip_id, broadcaster, url, estado, motivo))
    conn.commit()


# ---- carpetas de streamers ------------------------------------------------------
# Una carpeta es un `grupo` de streamers.yaml (argentinos, evento, catalogo) o una creada por
# Telegram. Cada una tiene dos interruptores, en la DB y no en el YAML porque se tocan desde el
# teléfono: en_vivo (¿la vigila el modo en vivo?) y diarios (¿entra en la corrida de las 05:00?).
# Pedido 2026-09-28: Argentinos con en vivo; Dedsafío y Catálogo sin; diarios como estaban (todos).
# Revisado el mismo día (los Shorts de Minecraft y del Dedsafío no los mira nadie): Dedsafío sin
# diarios ni en vivo, y Famosos (Auron) con los dos.

CARPETAS_DEFAULT = {
    "argentinos": ("Argentinos", 1, 1),
    "famosos": ("Famosos", 1, 1),
    "evento": ("Dedsafío", 0, 0),
    "catalogo": ("Catálogo", 0, 1),
}


def _fila_carpeta(f) -> dict:
    return {"nombre": f[0], "etiqueta": f[1], "en_vivo": bool(f[2]), "diarios": bool(f[3])}


def carpetas(conn: sqlite3.Connection) -> dict[str, dict]:
    """Todas, con las de siempre creadas la primera vez (con sus valores de fábrica)."""
    for nombre, (etiqueta, en_vivo, diarios) in CARPETAS_DEFAULT.items():
        conn.execute("INSERT OR IGNORE INTO carpetas (nombre, etiqueta, en_vivo, diarios) "
                     "VALUES (?, ?, ?, ?)", (nombre, etiqueta, en_vivo, diarios))
    conn.commit()
    filas = conn.execute("SELECT nombre, etiqueta, en_vivo, diarios FROM carpetas ORDER BY creada, nombre")
    return {f[0]: _fila_carpeta(f) for f in filas}


def carpeta(conn: sqlite3.Connection, nombre: str) -> dict:
    """La carpeta de ese grupo. Si es un grupo del YAML que todavía no estaba (ej. kick_reciente),
    se crea sin en vivo y con diarios, que es como se comportaba antes de las carpetas."""
    todas = carpetas(conn)
    if nombre not in todas:
        conn.execute("INSERT OR IGNORE INTO carpetas (nombre, etiqueta) VALUES (?, ?)",
                     (nombre, nombre.replace("_", " ").capitalize()))
        conn.commit()
        return carpetas(conn)[nombre]
    return todas[nombre]


def crear_carpeta(conn: sqlite3.Connection, etiqueta: str) -> str:
    """Una carpeta nueva desde Telegram. Devuelve su nombre interno (sin tildes ni espacios)."""
    import re
    import unicodedata

    etiqueta = etiqueta.strip()[:40]
    base = "".join(c for c in unicodedata.normalize("NFKD", etiqueta) if not unicodedata.combining(c))
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")[:24] or "carpeta"
    nombre, n = base, 2
    existentes = carpetas(conn)
    while nombre in existentes:
        nombre, n = f"{base}_{n}", n + 1
    conn.execute("INSERT INTO carpetas (nombre, etiqueta) VALUES (?, ?)", (nombre, etiqueta))
    conn.commit()
    return nombre


def set_interruptor(conn: sqlite3.Connection, nombre: str, campo: str, valor: bool) -> None:
    if campo not in ("en_vivo", "diarios"):
        raise ValueError(campo)
    carpeta(conn, nombre)
    conn.execute(f"UPDATE carpetas SET {campo} = ? WHERE nombre = ?", (1 if valor else 0, nombre))
    conn.commit()


def borrar_carpeta(conn: sqlite3.Connection, nombre: str) -> None:
    conn.execute("DELETE FROM carpetas WHERE nombre = ?", (nombre,))
    conn.commit()


# ---- subidas a YouTube (preparadas; apagadas hasta la auditoría) ----------------------------

def _fila_subida(f) -> dict:
    return dict(zip(("id", "clip_id", "canal", "video_id", "publish_at", "estado", "error", "creada"), f))


def crear_subida(conn: sqlite3.Connection, clip_id: str, canal: str, estado: str,
                 video_id: str = "", publish_at: str = "", error: str = "") -> int:
    cur = conn.execute("INSERT INTO subidas (clip_id, canal, video_id, publish_at, estado, error) "
                       "VALUES (?, ?, ?, ?, ?, ?)", (clip_id, canal, video_id, publish_at, estado, error))
    conn.commit()
    return int(cur.lastrowid)


def subidas(conn: sqlite3.Connection, estados: tuple[str, ...] | None = None,
            clip_id: str | None = None) -> list[dict]:
    sql, args = "SELECT id, clip_id, canal, video_id, publish_at, estado, error, creada FROM subidas WHERE 1=1", []
    if estados:
        sql += f" AND estado IN ({', '.join('?' for _ in estados)})"
        args += list(estados)
    if clip_id:
        sql += " AND clip_id = ?"
        args.append(clip_id)
    return [_fila_subida(f) for f in conn.execute(sql + " ORDER BY publish_at, id", args)]


def marcar_subida(conn: sqlite3.Connection, subida_id: int, estado: str, error: str = "") -> None:
    conn.execute("UPDATE subidas SET estado = ?, error = ? WHERE id = ?", (estado, error, subida_id))
    conn.commit()
