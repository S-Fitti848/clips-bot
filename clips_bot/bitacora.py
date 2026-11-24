"""Bitácora de cada video que arma el bot (Santi, 2026-11-15: "un registro detallado de cada video, para
después mejorar costos y tiempos"). Mismo formato en todos los bots (ver docs/registro-videos.md): una fila
por video en la tabla `videos_registro`, con canal y formato, costo de Claude por paso (modelo e intentos),
voces de Gemini, tiempo de cada etapa, temperatura máxima de la Pi y si se frenó por calor en el render, y la
falla (paso y motivo) si la hubo. El estado final (publicado, cancelado) sale de la tabla `subidas`.

Uso (un video a la vez: el turno pesado ya lo garantiza):
    bitacora.abrir(conn, "asinacio_20261116", "asinacio", "marcas")
    bitacora.paso("guion")      # cierra la etapa anterior y arranca esta (los tiempos se suman por nombre)
    ...
    bitacora.fallo("render", "ffmpeg falló")       # si algo falla
    bitacora.cerrar(conn, "programado")
Un video aprobado más tarde (Pequeña Historia con ✅) se `retomar` y se cierra otra vez: suma su tramo.

Claude y las voces salen de `gemini_uso` (todas las llamadas ya se anotan ahí) por rango de filas: las del
tramo del video. Nunca tumba nada: si algo de esto falla, se anota en el log y el video sigue."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

BOT = "clips"
TABLA = """CREATE TABLE IF NOT EXISTS videos_registro (
    id           TEXT PRIMARY KEY,   -- el id del video en ese bot (clip_id o el token de la propuesta)
    bot          TEXT NOT NULL,      -- clips | lo_encontre
    canal        TEXT NOT NULL,      -- asinacio | pequena_historia | lo_encontre …
    formato      TEXT NOT NULL,      -- marcas | tecnologia | latinoamerica | producto | 3_cosas | caro_barato | carrusel …
    titulo       TEXT DEFAULT '',
    clip_id      TEXT DEFAULT '',    -- para cruzar con las subidas (publicado / cancelado)
    dia          TEXT NOT NULL,      -- AR, AAAA-MM-DD (cuando arrancó)
    inicio       TEXT NOT NULL,      -- UTC ISO
    fin          TEXT DEFAULT '',
    total_s      REAL DEFAULT 0,     -- suma de las etapas (sin las esperas entre tramos)
    estado       TEXT DEFAULT '',    -- armando | propuesto | entregado | programado | publicado | cancelado | fallido
    fallo_paso   TEXT DEFAULT '',
    fallo_motivo TEXT DEFAULT '',
    temp_max     REAL,               -- °C, máxima de todo el video
    frenado      INTEGER DEFAULT 0,  -- 1 si la Pi se frenó por calor durante el render
    costo_usd    REAL DEFAULT 0,     -- Claude, todos los pasos
    detalle      TEXT DEFAULT '{}'   -- JSON: etapas, claude por paso, voces, tramos
)"""

# Candidatos descartados antes de armar el video (Santi, 2026-11-15): cada historia o marca que se cae, con
# el paso (puntaje, fotos, guion, voz, render, otro), el motivo concreto, lo que costó en Claude hasta ahí y,
# si fue por fotos, qué se buscó y qué se encontró.
TABLA_DESCARTES = """CREATE TABLE IF NOT EXISTS candidatos_descartados (
    n          INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT DEFAULT '',     -- la fila de videos_registro de esa corrida
    bot        TEXT NOT NULL,
    canal      TEXT NOT NULL,
    formato    TEXT NOT NULL,
    dia        TEXT NOT NULL,       -- AR
    ts         TEXT NOT NULL,       -- UTC ISO
    candidato  TEXT NOT NULL,       -- la marca/ángulo o el hecho
    paso       TEXT NOT NULL,       -- puntaje | fotos | guion | voz | render | otro
    motivo     TEXT DEFAULT '',
    costo_usd  REAL DEFAULT 0,      -- Claude gastado en ESE candidato hasta que se cayó
    detalle    TEXT DEFAULT '{}'    -- JSON: en fotos, {"buscado": [...], "encontrado": "..."}
)"""
PASOS_DESCARTE = ("puntaje", "verificacion", "fotos", "guion", "voz", "render", "otro")
ETAPA_A_PASO = {"busqueda": "puntaje", "verificacion": "verificacion", "guion": "guion", "fotos": "fotos", "dibujos": "otro", "voz": "voz",
                "whisper": "voz", "revision": "render", "render": "render", "subida": "otro"}

# Paso de cada función que llama a un modelo (el resto cuenta como "otros").
PASOS = (
    ("web", ("web_historias.",)),
    ("correccion", ("correcciones.",)),
    ("final", ("final_que_paga",)),
    ("fotos", ("efemerides.pedir", "elegir_fotos", "describir_fotos", "prefiltrar_fotos")),
    ("revision_visual", ("revisar_visual", "chequear_calidad", "marcar_claves")),
    ("dibujos", ("dibujos.",)),
    ("guion", ("escribir_guion", "acortar_guion", "textos.generar")),
    ("elegir", ("elegir", "clasificar", "candidatos")),
)
# Bits de vcgencmd get_throttled que dicen que AHORA está frenada (frecuencia capada, throttling o el límite
# blando de temperatura).
FRENADA_BITS = 0x2 | 0x4 | 0x8

_ACTIVA: "Bitacora | None" = None
_LOCK = threading.Lock()


def paso_de(funcion: str) -> str:
    for nombre, claves in PASOS:
        if any(k in funcion for k in claves):
            return nombre
    return "otros"


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def asegurar_tabla(conn) -> None:
    conn.execute(TABLA)
    conn.execute(TABLA_DESCARTES)
    conn.commit()


def _ultima_fila(conn) -> int:
    try:
        return int(conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM gemini_uso").fetchone()[0])
    except Exception:  # noqa: BLE001
        return 0


class _Muestreo(threading.Thread):
    """Temperatura y estado de frenado cada `cada_s`, con la etapa en curso."""

    def __init__(self, bit: "Bitacora", cada_s: float = 5.0):
        super().__init__(daemon=True)
        self.bit, self.cada_s, self._fin = bit, cada_s, threading.Event()

    def run(self):
        from .animacion import render as rd

        while not self._fin.is_set():
            t = rd.temperatura()
            if t is not None:
                self.bit.temp_max = max(self.bit.temp_max or 0.0, t)
                if self.bit.etapa == "render":
                    th = rd.throttled()
                    try:
                        if th and int(th, 16) & FRENADA_BITS:
                            self.bit.frenado = True
                    except ValueError:
                        pass
            self._fin.wait(self.cada_s)

    def parar(self):
        self._fin.set()


class Bitacora:
    def __init__(self, vid: str, canal: str, formato: str, fila0: int, previo: dict | None = None):
        previo = previo or {}
        det = json.loads(previo.get("detalle") or "{}") if previo else {}
        self.id, self.canal, self.formato = vid, canal, formato
        self.titulo = previo.get("titulo", "")
        self.clip_id = previo.get("clip_id", "")
        self.inicio = previo.get("inicio") or ahora_utc().isoformat(timespec="seconds")
        self.dia = previo.get("dia") or (ahora_utc() - timedelta(hours=3)).date().isoformat()
        self.etapas: dict[str, float] = dict(det.get("etapas") or {})
        self.tramos: list[list[int]] = list(det.get("tramos") or [])
        self.fila0 = fila0
        self.etapa: str | None = None
        self._t_etapa = time.monotonic()
        self.temp_max: float | None = previo.get("temp_max")
        self.frenado = bool(previo.get("frenado"))
        self.fallo_paso = previo.get("fallo_paso", "")
        self.fallo_motivo = previo.get("fallo_motivo", "")
        self.extra: dict = dict(det.get("extra") or {})
        self.conn = None                 # la base del tramo (para anotar los descartes al momento)
        self._muestreo = _Muestreo(self)
        self._muestreo.start()

    def marcar(self, nombre: str | None) -> None:
        ahora = time.monotonic()
        if self.etapa:
            self.etapas[self.etapa] = round(self.etapas.get(self.etapa, 0.0) + ahora - self._t_etapa, 1)
        self.etapa, self._t_etapa = nombre, ahora


# ---- la API ------------------------------------------------------------------------------------------

def abrir(conn, vid: str, canal: str, formato: str, titulo: str = "") -> None:
    """Empieza la bitácora de un video (si había una abierta, la cierra sin estado)."""
    global _ACTIVA
    try:
        asegurar_tabla(conn)
        if _ACTIVA is not None:
            cerrar(conn, "")
        _ACTIVA = Bitacora(vid, canal, formato, _ultima_fila(conn))
        _ACTIVA.conn = conn
        _ACTIVA.titulo = titulo
        _guardar(conn, _ACTIVA, "armando")
    except Exception as err:  # noqa: BLE001 — la bitácora nunca frena un video
        log.warning("bitácora: no pude abrir %s: %s", vid, err)


def retomar(conn, vid: str) -> bool:
    """Sigue la bitácora de un video ya registrado (un tramo nuevo: el ✅ que llega más tarde)."""
    global _ACTIVA
    try:
        asegurar_tabla(conn)
        cur = conn.execute("SELECT * FROM videos_registro WHERE id = ?", (vid,))
        fila = cur.fetchone()
        if not fila:
            return False
        previo = dict(zip([c[0] for c in cur.description], fila))
        if _ACTIVA is not None:
            cerrar(conn, "")
        _ACTIVA = Bitacora(vid, previo["canal"], previo["formato"], _ultima_fila(conn), previo)
        _ACTIVA.conn = conn
        return True
    except Exception as err:  # noqa: BLE001
        log.warning("bitácora: no pude retomar %s: %s", vid, err)
        return False


def paso(nombre: str | None) -> None:
    """Cierra la etapa en curso y arranca `nombre` (busqueda, guion, fotos, voz, whisper, render, subida…)."""
    if _ACTIVA is not None:
        with _LOCK:
            _ACTIVA.marcar(nombre)


def dato(**kw) -> None:
    """titulo=, clip_id=, o cualquier dato extra (va a detalle.extra)."""
    if _ACTIVA is None:
        return
    for k, v in kw.items():
        if k in ("titulo", "clip_id"):
            setattr(_ACTIVA, k, str(v or ""))
        else:
            _ACTIVA.extra[k] = v


def fallo(paso_: str, motivo: str) -> None:
    if _ACTIVA is not None:
        _ACTIVA.fallo_paso = paso_ or (_ACTIVA.etapa or "")
        _ACTIVA.fallo_motivo = str(motivo)[:500]
        # el video ya elegido que se cae en la voz, el render u otro paso también es un candidato descartado
        if _ACTIVA.fallo_paso not in ("busqueda", "guion", "fotos"):
            descarte(_ACTIVA.titulo or _ACTIVA.id, motivo, paso_=ETAPA_A_PASO.get(_ACTIVA.fallo_paso, "otro"),
                     desde_fila=_ACTIVA.fila0)


def fila_actual() -> int:
    """La última fila de gemini_uso (para medir lo que gasta un candidato desde acá)."""
    if _ACTIVA is None or _ACTIVA.conn is None:
        return 0
    return _ultima_fila(_ACTIVA.conn)


def costo_entre_activa(desde: int) -> float:
    """Lo gastado en Claude desde la fila `desde` hasta ahora, en la base de la bitácora activa (0 sin bitácora)."""
    if _ACTIVA is None or _ACTIVA.conn is None or not desde:
        return 0.0
    return costo_entre(_ACTIVA.conn, desde, _ultima_fila(_ACTIVA.conn))


def costo_activo() -> float:
    """Lo gastado en Claude por el video en curso: sus tramos anteriores más el actual (0 sin bitácora)."""
    if _ACTIVA is None or _ACTIVA.conn is None:
        return 0.0
    try:
        tramos = list(_ACTIVA.tramos) + [[_ACTIVA.fila0, _ultima_fila(_ACTIVA.conn)]]
        return round(sum(costo_entre(_ACTIVA.conn, a, b) for a, b in tramos if b > a), 4)
    except Exception:  # noqa: BLE001
        return 0.0


def costo_entre(conn, desde: int, hasta: int) -> float:
    from . import claude

    return round(sum(claude.costo(m, e or 0, s_ or 0) for m, e, s_ in conn.execute(
        "SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND rowid > ? AND rowid <= ?",
        (desde, hasta))), 4)


def descarte(candidato: str, motivo: str, paso_: str | None = None, desde_fila: int | None = None,
             costo: float | None = None, buscado: list | None = None, encontrado: str = "",
             intentos: list | None = None) -> None:
    """Un candidato que se cae antes de armar el video. `paso_`: si no viene, sale de la etapa en curso.
    `intentos` (Santi, 2026-11-24): qué se intentó para arreglarlo antes de dejarlo, en orden.
    El costo: `costo` (una parte de un pedido compartido) o lo gastado desde `desde_fila` hasta ahora."""
    bit = _ACTIVA
    if bit is None or bit.conn is None:
        return
    try:
        conn = bit.conn
        paso_ = paso_ if paso_ in PASOS_DESCARTE else ETAPA_A_PASO.get(bit.etapa or "", "otro")
        if costo is None:
            costo = costo_entre(conn, desde_fila, _ultima_fila(conn)) if desde_fila is not None else 0.0
        det = {}
        if buscado is not None or encontrado:
            det = {"buscado": [str(x) for x in (buscado or [])][:15], "encontrado": str(encontrado)[:300]}
        if intentos:
            det["intentos"] = [str(x)[:300] for x in intentos][:10]
        conn.execute("INSERT INTO candidatos_descartados (video_id, bot, canal, formato, dia, ts, candidato, paso, "
                     "motivo, costo_usd, detalle) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (bit.id, BOT, bit.canal, bit.formato, (ahora_utc() - timedelta(hours=3)).date().isoformat(),
                      ahora_utc().isoformat(timespec="seconds"), str(candidato)[:200], paso_, str(motivo)[:400],
                      round(float(costo or 0), 4), json.dumps(det, ensure_ascii=False)))
        conn.commit()
    except Exception as err:  # noqa: BLE001 — anotar nunca frena el video
        log.warning("bitácora: no pude anotar el descarte de %s: %s", candidato, err)


def activa() -> str | None:
    return _ACTIVA.id if _ACTIVA is not None else None


def cerrar(conn, estado: str) -> None:
    """Termina el tramo: tiempos, Claude y voces del rango de filas, temperatura; guarda la fila."""
    global _ACTIVA
    bit = _ACTIVA
    if bit is None:
        return
    _ACTIVA = None
    try:
        bit.marcar(None)
        bit._muestreo.parar()
        bit.tramos.append([bit.fila0, _ultima_fila(conn)])
        _guardar(conn, bit, estado or ("fallido" if bit.fallo_paso else "entregado"), fin=True)
    except Exception as err:  # noqa: BLE001
        log.warning("bitácora: no pude cerrar %s: %s", bit.id, err)


def _modelos(conn, tramos: list[list[int]]) -> tuple[list[dict], dict, float]:
    """(claude por paso, voces, costo total) de las filas de gemini_uso de los tramos."""
    from . import claude

    por: dict[tuple[str, str], dict] = {}
    voces = {"n": 0, "reintentos": 0, "claves": {}}
    total = 0.0
    for a, b in tramos:
        for funcion, modelo, clave, entrada, salida, cache in conn.execute(
                "SELECT funcion, modelo, clave, entrada, salida, cache FROM gemini_uso WHERE rowid > ? AND rowid <= ?",
                (a, b)):
            if "tts" in str(modelo).lower():
                voces["n"] += 1
                voces["claves"][clave or "?"] = voces["claves"].get(clave or "?", 0) + 1
                continue
            p_ = paso_de(str(funcion))
            k = (p_, str(modelo))
            x = por.setdefault(k, {"paso": p_, "modelo": str(modelo), "intentos": 0, "entrada": 0, "salida": 0,
                                   "usd": 0.0, "cache": 0})
            x["intentos"] += 1
            x["entrada"] += int(entrada or 0)
            x["salida"] += int(salida or 0)
            x["cache"] += int(cache or 0)
            if clave == "claude":
                usd = claude.costo(modelo, entrada or 0, salida or 0)
                x["usd"] = round(x["usd"] + usd, 4)
                total += usd
    # una voz por video: lo que pase de 1 son reintentos (otra clave, o la voz rehecha por largo)
    voces["reintentos"] = max(0, voces["n"] - 1)
    return sorted(por.values(), key=lambda x: -x["usd"]), voces, round(total, 4)


def _guardar(conn, bit: Bitacora, estado: str, fin: bool = False) -> None:
    claude_, voces, costo = _modelos(conn, bit.tramos) if bit.tramos else ([], {"n": 0, "reintentos": 0}, 0.0)
    detalle = {"etapas": bit.etapas, "claude": claude_, "voces": voces, "tramos": bit.tramos, "extra": bit.extra}
    conn.execute(
        "INSERT INTO videos_registro (id, bot, canal, formato, titulo, clip_id, dia, inicio, fin, total_s, estado, "
        "fallo_paso, fallo_motivo, temp_max, frenado, costo_usd, detalle) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET canal=excluded.canal, formato=excluded.formato, titulo=excluded.titulo, "
        "clip_id=excluded.clip_id, fin=excluded.fin, total_s=excluded.total_s, estado=excluded.estado, "
        "fallo_paso=excluded.fallo_paso, fallo_motivo=excluded.fallo_motivo, temp_max=excluded.temp_max, "
        "frenado=excluded.frenado, costo_usd=excluded.costo_usd, detalle=excluded.detalle",
        (bit.id, BOT, bit.canal, bit.formato, bit.titulo, bit.clip_id, bit.dia, bit.inicio,
         ahora_utc().isoformat(timespec="seconds") if fin else "", round(sum(bit.etapas.values()), 1), estado,
         bit.fallo_paso, bit.fallo_motivo, bit.temp_max, int(bit.frenado), costo,
         json.dumps(detalle, ensure_ascii=False)))
    conn.commit()


# ---- lectura: /costos y el resumen de los lunes ----------------------------------------------------------

NOMBRES_CANAL = {"asinacio": "Así Nació", "pequena_historia": "Pequeña Historia", "lo_encontre": "Lo Encontré"}


def leer(conn, desde: str, otras_db: list | None = None) -> list[dict]:
    """Las filas desde el día `desde` (AR) de esta base y de las otras (Lo Encontré, mismo formato), con el
    estado final según las subidas (publicado / cancelado)."""
    import sqlite3
    from pathlib import Path

    filas = []
    bases = [(conn, False)]
    for ruta in otras_db or []:
        if ruta and Path(ruta).exists():
            try:
                bases.append((sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=10), True))
            except sqlite3.Error:
                continue
    for c, ajena in bases:
        try:
            cur = c.execute("SELECT * FROM videos_registro WHERE dia >= ? ORDER BY inicio", (desde,))
            cols = [x[0] for x in cur.description]
            for f in cur.fetchall():
                d = dict(zip(cols, f))
                d["detalle"] = json.loads(d.get("detalle") or "{}")
                filas.append(d)
        except Exception:  # noqa: BLE001 — una base sin la tabla todavía
            pass
        finally:
            if ajena:
                c.close()
    # el estado final: lo que dice la tabla subidas de este bot
    try:
        for d in filas:
            if d.get("bot") != BOT or not d.get("clip_id"):
                continue
            est = {r[0] for r in conn.execute("SELECT estado FROM subidas WHERE clip_id = ?", (d["clip_id"],))}
            if "cancelada" in est:
                d["estado"] = "cancelado"
            elif "publicada" in est:
                d["estado"] = "publicado"
            elif "programada" in est and d.get("estado") in ("", "entregado", "programado"):
                d["estado"] = "programado"
    except Exception:  # noqa: BLE001
        pass
    return filas


def leer_descartes(conn, desde: str, otras_db: list | None = None) -> list[dict]:
    """Los candidatos descartados desde `desde` (AR), de esta base y de las otras (mismo formato)."""
    import sqlite3
    from pathlib import Path

    out = []
    bases = [(conn, False)] + [(sqlite3.connect(f"file:{r}?mode=ro", uri=True, timeout=10), True)
                               for r in otras_db or [] if r and Path(r).exists()]
    for c, ajena in bases:
        try:
            cur = c.execute("SELECT * FROM candidatos_descartados WHERE dia >= ? ORDER BY ts", (desde,))
            cols = [x[0] for x in cur.description]
            for f in cur.fetchall():
                d = dict(zip(cols, f))
                d["detalle"] = json.loads(d.get("detalle") or "{}")
                out.append(d)
        except Exception:  # noqa: BLE001 — base sin la tabla
            pass
        finally:
            if ajena:
                c.close()
    return out


def texto_descartes(desc: list[dict]) -> str:
    """Cuántos se cayeron en cada paso, lo que costaron, los motivos más repetidos y un ejemplo de fotos."""
    if not desc:
        return ""
    por: dict[str, list] = {}
    for d in desc:
        por.setdefault(d["paso"], []).append(d)
    total = sum(d.get("costo_usd") or 0 for d in desc)
    lineas = ["", f"<b>Candidatos descartados</b>: {len(desc)} (Claude gastado en ellos: US$ {total:.2f})"]
    for paso_, lista in sorted(por.items(), key=lambda kv: -sum(x.get("costo_usd") or 0 for x in kv[1])):
        usd = sum(x.get("costo_usd") or 0 for x in lista)
        motivos: dict[str, int] = {}
        for x in lista:
            m = (x.get("motivo") or "").split(":")[0][:70]
            motivos[m] = motivos.get(m, 0) + 1
        top = "; ".join(f"{m} ({n})" for m, n in sorted(motivos.items(), key=lambda kv: -kv[1])[:2])
        lineas.append(f"• {paso_}: {len(lista)} · US$ {usd:.2f} — {top}")
    fotos = [d for d in desc if d["paso"] == "fotos" and (d.get("detalle") or {}).get("buscado")]
    if fotos:
        f = fotos[-1]
        lineas.append(f"  ej. fotos: «{f['candidato'][:60]}» buscó {', '.join(f['detalle']['buscado'][:3])}… "
                      f"→ {f['detalle'].get('encontrado') or '?'}")
    return "\n".join(lineas)


def resumen(filas: list[dict]) -> dict:
    """Por canal/formato: videos, costo y tiempo promedio; las etapas más caras y más lentas; fallas."""
    grupos: dict[str, dict] = {}
    pasos_usd: dict[str, list] = {}
    etapas_s: dict[str, list] = {}
    for d in filas:
        clave = f"{NOMBRES_CANAL.get(d['canal'], d['canal'])} · {d['formato']}"
        g = grupos.setdefault(clave, {"n": 0, "usd": 0.0, "s": 0.0, "fallidos": 0, "frenados": 0, "temp_max": 0.0,
                                      "publicados": 0, "cancelados": 0})
        g["n"] += 1
        g["usd"] += d.get("costo_usd") or 0
        g["s"] += d.get("total_s") or 0
        g["fallidos"] += d.get("estado") == "fallido"
        g["frenados"] += bool(d.get("frenado"))
        g["publicados"] += d.get("estado") in ("publicado", "programado")
        g["cancelados"] += d.get("estado") == "cancelado"
        g["temp_max"] = max(g["temp_max"], d.get("temp_max") or 0)
        det = d.get("detalle") or {}
        for x in det.get("claude") or []:
            pasos_usd.setdefault(x["paso"], []).append((x.get("usd") or 0, x.get("intentos") or 0))
        for k, v in (det.get("etapas") or {}).items():
            etapas_s.setdefault(k, []).append(v)
    n_total = max(1, len(filas))
    caras = sorted(((k, sum(u for u, _ in v), sum(i for _, i in v)) for k, v in pasos_usd.items()), key=lambda x: -x[1])
    lentas = sorted(((k, sum(v) / len(v), len(v)) for k, v in etapas_s.items()), key=lambda x: -x[1])
    return {"grupos": grupos, "caras": caras, "lentas": lentas, "n": len(filas),
            "usd": round(sum(d.get("costo_usd") or 0 for d in filas), 2), "videos_con_datos": n_total,
            "fallas": [(d.get("canal"), d.get("formato"), d.get("fallo_paso"), d.get("fallo_motivo"))
                       for d in filas if d.get("estado") == "fallido"]}


AVISO_VIDEO_USD = 1.50     # Santi, 2026-11-17: un video de Así Nació que pase de esto, se avisa


def piezas_usd(fila: dict) -> float:
    """Lo que se gastó en piezas nuevas (dibujos de objetos y lugares) en ese video."""
    return round(sum(x.get("usd") or 0 for x in ((fila.get("detalle") or {}).get("claude") or [])
                     if x.get("paso") == "dibujos"), 3)


def texto_piezas(filas: list[dict], n: int = 10) -> str:
    """Así Nació, video por video (Santi, 2026-11-17): el total y cuánto fue en piezas nuevas."""
    an = [d for d in filas if d.get("canal") == "asinacio"][-n:]
    if not an:
        return ""
    lineas = ["<b>Así Nació por video</b> (total · piezas nuevas):"]
    for d in an:
        total = d.get("costo_usd") or 0
        lineas.append(f"• {(d.get('titulo') or d.get('clip_id') or '?')[:45]}: US$ {total:.2f} · piezas "
                      f"US$ {piezas_usd(d):.2f}" + (" ⚠️ pasó de US$ 1,50" if total > AVISO_VIDEO_USD else ""))
    return "\n".join(lineas)


def _mmss(s: float) -> str:
    s = int(round(s or 0))
    return f"{s // 60}:{s % 60:02d}"


def texto(filas: list[dict], dias: int = 7, descartes: list[dict] | None = None) -> str:
    r = resumen(filas)
    if not r["n"]:
        return (f"🔧 Claude Code: <b>Costos de los últimos {dias} días</b>: todavía no hay videos registrados."
                + texto_descartes(descartes or []))
    lineas = [f"🔧 Claude Code: <b>Costos y tiempos, últimos {dias} días</b> — {r['n']} videos, Claude US$ {r['usd']:.2f}",
              ""]
    for clave, g in sorted(r["grupos"].items()):
        n = max(1, g["n"])
        lineas.append(f"<b>{clave}</b>: {g['n']} videos · US$ {g['usd'] / n:.2f} y {_mmss(g['s'] / n)} por video"
                      + (f" · {g['fallidos']} fallaron" if g["fallidos"] else "")
                      + (f" · {g['cancelados']} cancelados" if g["cancelados"] else "")
                      + (f" · frenó por calor en {g['frenados']}" if g["frenados"] else "")
                      + (f" · máx {g['temp_max']:.0f} °C" if g["temp_max"] else ""))
    por_video = texto_piezas(filas)
    if por_video:
        lineas += ["", por_video]
    lineas += ["", "<b>Las 3 etapas más caras</b> (Claude, total de la semana):"]
    lineas += [f"• {k}: US$ {usd:.2f} ({intentos} pedidos)" for k, usd, intentos in r["caras"][:3]]
    lineas += ["", "<b>Las 3 más lentas</b> (promedio por video):"]
    lineas += [f"• {k}: {_mmss(s)} ({n} videos)" for k, s, n in r["lentas"][:3]]
    if r["fallas"]:
        lineas += ["", "<b>Fallas</b>:"]
        lineas += [f"• {NOMBRES_CANAL.get(c, c)} · {f}: en {p or '?'} — {(m or '')[:90]}" for c, f, p, m in r["fallas"][:5]]
    return "\n".join(lineas) + texto_descartes(descartes or [])


def ideas(filas: list[dict]) -> list[str]:
    """2 o 3 ideas concretas para bajar costo o tiempo, sacadas de los números (sin gastar un modelo)."""
    r = resumen(filas)
    out: list[tuple[float, str]] = []
    total = max(0.01, r["usd"])
    for k, usd, intentos in r["caras"][:3]:
        if k == "guion" and intentos > 3 * max(1, r["n"]):
            out.append((usd, f"El guion se pidió {intentos} veces para {r['n']} videos (US$ {usd:.2f}): mirar qué "
                             "regla de la validación rechaza más y aflojarla o explicarla mejor en el prompt."))
        elif k == "fotos" and usd / total > 0.3:
            out.append((usd, f"Las fotos son el {usd / total:.0%} del costo (US$ {usd:.2f}): bajar de 5 a 3 las "
                             "fotos por frase que mira Sonnet (PREFILTRO_POR_FRASE) o de 3 a 2 los videos."))
        elif k == "correccion" and intentos > 2 * max(1, r["n"]):
            out.append((usd, f"Las correcciones puntuales son {intentos} pedidos (US$ {usd:.2f}): sumar al prompt "
                             "del guion la regla que más se corrige, para que salga bien de entrada."))
        elif k == "elegir" and usd / total > 0.2:
            out.append((usd, f"Puntuar candidatos cuesta US$ {usd:.2f} ({usd / total:.0%}): menos candidatos por tanda."))
    frenados = sum(1 for d in filas if d.get("frenado"))
    con_render = [d for d in filas if (d.get("detalle") or {}).get("etapas", {}).get("render")]
    if con_render and frenados / len(con_render) > 0.5:
        render = sum(d["detalle"]["etapas"]["render"] for d in con_render) / len(con_render)
        out.append((frenados * 60.0 / 100, f"La Pi se frenó por calor en {frenados} de {len(con_render)} renders (render "
                                            f"promedio {_mmss(render)}): disipadores en el chip o arm_boost=0 bajarían el "
                                            "tiempo sin tocar la calidad."))
    for k, s, n in r["lentas"][:2]:
        if k == "voz" and s > 120:
            out.append((s / 100, f"La voz tarda {_mmss(s)} por video: ver cuántas veces se rehace por largo (reintentos de voz)."))
        if k in ("fotos", "busqueda") and s > 300:
            out.append((s / 100, f"La etapa {k} tarda {_mmss(s)} por video: bajar el tope de búsqueda de fotos y videos "
                                 "(efemerides.tope_fotos_min) o las fuentes que más fallan."))
    voces_rei = sum((d.get("detalle") or {}).get("voces", {}).get("reintentos", 0) for d in filas)
    if voces_rei > r["n"] * 0.5:
        out.append((voces_rei / 10, f"Hubo {voces_rei} voces de más en {r['n']} videos: el guion sale largo y se rehace la "
                                    "voz; pedirle al guion las palabras justas evita gastar voces."))
    out.sort(key=lambda x: -x[0])
    vistas, lista = set(), []
    for _, t in out:
        if t not in vistas:
            vistas.add(t)
            lista.append(t)
    return lista[:3] or ["Sin nada que destaque esta semana: los costos y los tiempos están parejos."]
