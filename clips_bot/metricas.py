"""Métricas de los Shorts de Santi (§4b, pedido 2026-09-29): vistas, duración media vista y % que
lo mira entero, por clip, una vez por día; y con eso, un peso por streamer y por tipo de clip
(duración, layout, con o sin cámara) para la selección.

Cómo se sabe qué Short es qué clip: la subida es manual, así que no hay un id que los una. El
título del Short es el que generó el bot (Santi lo copia del mensaje), así que se empareja por
título normalizado (y el Short tiene que ser posterior a la entrega del clip).

REGLA de §4b: los pesos se mueven suave y SOLO con n ≥ `metricas.min_n` Shorts por grupo; con menos
el bot mide y guarda, pero no cambia nada. La métrica que manda es la mediana de vistas.
"""

from __future__ import annotations

import difflib
import json
import logging
import math
import re
import sqlite3
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SIMILITUD_MIN = 0.85   # título del Short vs título que generó el bot (Santi a veces le toca algo)
# Regla de los 30 días de las Políticas para Desarrolladores de YouTube (2026-10-04, Santi: "no
# quiero que se borren; cumplí actualizando"): los datos de cada video se vuelven a pedir antes de
# que pasen 30 días desde la última vez. Los de los últimos RECIENTES_DIAS, todos los días.
REFRESCO_DIAS = 25
RECIENTES_DIAS = 60
DESDE_SIEMPRE = datetime(2005, 1, 1, tzinfo=timezone.utc)
CONCLUSIONES = "metricas_conclusiones"   # bot_estado: lo que se calculó de las métricas (se guarda siempre)


def _norm(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def entregados(ready: Path, desde: datetime) -> list[dict]:
    """Los clips de streamers entregados desde `desde` (el json de output/ready/)."""
    out = []
    for p in ready.glob("*.json"):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ent = (meta.get("entregado") or {}).get("fecha")
        if not ent or meta.get("efemeride") or not (meta.get("textos") or {}).get("titulo"):
            continue
        if datetime.fromisoformat(ent) >= desde:
            out.append(meta)
    return out


def emparejar(videos: list[dict], clips: list[dict]) -> dict[str, dict]:
    """{clip_id: video} por título: el más parecido, si pasa SIMILITUD_MIN y se publicó después de
    la entrega. Cada video se usa una sola vez."""
    usados, out = set(), {}
    for meta in clips:
        titulo = _norm(meta["textos"]["titulo"])
        entregado = datetime.fromisoformat(meta["entregado"]["fecha"])
        mejor, puntaje = None, 0.0
        for v in videos:
            if v["id"] in usados or datetime.fromisoformat(v["publicado"]) < entregado - timedelta(hours=1):
                continue
            s = difflib.SequenceMatcher(None, titulo, _norm(v["titulo"])).ratio()
            if s > puntaje:
                mejor, puntaje = v, s
        if mejor and puntaje >= SIMILITUD_MIN:
            usados.add(mejor["id"])
            out[meta["clip_id"]] = mejor
    return out


def actualizar(conn: sqlite3.Connection, cliente, ready: Path, dias: int = RECIENTES_DIAS,
               ahora: datetime | None = None) -> dict:
    """Una vez por día. (1) La lista COMPLETA de videos del canal: los datos de un video que ya no
    está se borran (es la única razón, junto con revocar el acceso, para borrar algo). (2) Los
    Shorts nuevos se emparejan con los clips entregados. (3) Se vuelven a pedir las estadísticas de
    los nuevos, de los de los últimos `dias` y de TODOS los que no se actualizan hace REFRESCO_DIAS
    (así ninguno pasa 30 días sin actualizar), con las vistas de toda la vida del video. (4) Se
    guardan las conclusiones. `cliente`: youtube.Cliente del canal de clips (rots).
    Devuelve {"nuevos", "actualizados", "borrados"}."""
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(days=dias)
    todos = cliente.mis_videos(DESDE_SIEMPRE, maximo=10000)
    en_canal = {v["id"]: v for v in todos}
    borrados = 0
    if en_canal:     # con la lista vacía (un error raro de la API) no se borra nada
        for clip_id, video_id in conn.execute("SELECT clip_id, video_id FROM metricas").fetchall():
            if video_id not in en_canal:
                conn.execute("DELETE FROM metricas WHERE clip_id = ?", (clip_id,))
                borrados += 1
    clips = entregados(ready, desde)
    ya = {r[0] for r in conn.execute("SELECT clip_id FROM metricas")}
    recientes = [v for v in todos if datetime.fromisoformat(v["publicado"]) >= desde]
    pares = emparejar(recientes, [m for m in clips if m["clip_id"] not in ya])
    por_id = {m["clip_id"]: m for m in clips}
    a_pedir: dict[str, tuple[str, str]] = {cid: (v["id"], v["publicado"]) for cid, v in pares.items()}
    vencen = (ahora - timedelta(days=REFRESCO_DIAS)).isoformat()
    for clip_id, video_id, publicado, actualizado in conn.execute(
            "SELECT clip_id, video_id, publicado, actualizado FROM metricas").fetchall():
        if (publicado or "") >= desde.isoformat() or (actualizado or "") <= vencen:
            a_pedir.setdefault(clip_id, (video_id, publicado))
    if a_pedir:
        inicio = min((datetime.fromisoformat(p) for _, p in a_pedir.values() if p), default=DESDE_SIEMPRE)
        datos = cliente.metricas([v for v, _ in a_pedir.values()], inicio, ahora)
        for clip_id, (video_id, publicado) in a_pedir.items():
            d = datos.get(video_id, {})
            nace = datetime.fromisoformat(publicado) if publicado else inicio
            try:
                entero = cliente.pct_entero(video_id, nace, ahora)
            except Exception as e:     # la curva de retención es un extra: sin ella se guarda el resto
                log.warning("retención de %s: %s", video_id, e)
                entero = None
            meta = por_id.get(clip_id, {})
            conn.execute(
                """INSERT INTO metricas (clip_id, video_id, publicado, actualizado, vistas,
                       duracion_media_s, pct_visto_medio, pct_entero, streamer, duracion_s, layout, camara)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(clip_id) DO UPDATE SET actualizado = excluded.actualizado,
                       vistas = excluded.vistas, duracion_media_s = excluded.duracion_media_s,
                       pct_visto_medio = excluded.pct_visto_medio, pct_entero = excluded.pct_entero""",
                (clip_id, video_id, publicado, ahora.isoformat(), d.get("vistas", 0),
                 d.get("duracion_media_s"), d.get("pct_visto_medio"), entero, meta.get("streamer"),
                 meta.get("duracion_s"), meta.get("layout"), 1 if tiene_camara(meta) else 0))
    conn.commit()
    guardar_conclusiones(conn, ahora)
    return {"nuevos": len(pares), "actualizados": len(a_pedir) - len(pares), "borrados": borrados}


def borrar_por_revocacion(conn: sqlite3.Connection, canal: str) -> int:
    """Revocaron el acceso de la app a la cuenta de Google: se borran los datos de los videos que
    vinieron de la API (métricas e ids de subida de ese canal). Las CONCLUSIONES quedan."""
    n = 0
    if canal == "rots":
        n += conn.execute("DELETE FROM metricas").rowcount
    n += conn.execute("DELETE FROM subidas WHERE canal = ?", (canal,)).rowcount
    conn.commit()
    return n


# ---- los pesos ------------------------------------------------------------------------------

def tiene_camara(meta: dict) -> bool:
    return (meta.get("layout") or "") in ("split", "fullcam")


def tramo_duracion(segundos: float | None) -> str:
    s = float(segundos or 0)
    return "corto" if s < 30 else "medio" if s < 45 else "largo"


def claves_de(meta: dict) -> dict[str, str]:
    """A qué grupo pertenece un clip en cada dimensión."""
    return {"streamer": (meta.get("streamer") or "").lower(),
            "duracion": tramo_duracion(meta.get("duracion_s")),
            "layout": meta.get("layout") or "",
            "camara": "con_camara" if tiene_camara(meta) else "sin_camara"}


def conclusiones(conn: sqlite3.Connection) -> dict:
    """Lo que se concluye de las métricas, por dimensión y grupo: {dim: {grupo: {n, mediana, log2}}}
    (log2 = mediana del grupo / mediana general). Es lo que se guarda para siempre."""
    filas = conn.execute("SELECT vistas, streamer, duracion_s, layout, camara FROM metricas").fetchall()
    if not filas:
        return {}
    general = statistics.median(f[0] for f in filas) or 1
    grupos: dict[str, dict[str, list[int]]] = {}
    for vistas, streamer, dur, layout, camara in filas:
        meta = {"streamer": streamer, "duracion_s": dur, "layout": layout}
        claves = claves_de(meta)
        claves["camara"] = "con_camara" if camara else "sin_camara"
        for dim, grupo in claves.items():
            grupos.setdefault(dim, {}).setdefault(grupo, []).append(vistas)
    return {dim: {grupo: {"n": len(v), "mediana": statistics.median(v),
                          "log2": math.log2(max(statistics.median(v), 1) / general)}
                  for grupo, v in por_grupo.items()}
            for dim, por_grupo in grupos.items()}


def guardar_conclusiones(conn: sqlite3.Connection, ahora: datetime | None = None) -> None:
    from . import db

    c = conclusiones(conn)
    if c:     # sin métricas (revocado, o todavía nada) se queda lo último que se calculó
        db.set_valor(conn, CONCLUSIONES, json.dumps(
            {"fecha": (ahora or datetime.now(timezone.utc)).isoformat(), "grupos": c}, ensure_ascii=False))


def factores(conn: sqlite3.Connection, peso: float, min_n: int) -> dict[str, dict[str, float]]:
    """{dimensión: {grupo: factor}}. factor = 1 + peso × log2(mediana del grupo / mediana general),
    acotado a ±1 en el log (entre ×(1 − peso) y ×(1 + peso)). Solo grupos con n ≥ min_n. Sale de
    las métricas guardadas o, si no hay (revocado), de las conclusiones guardadas: se usan siempre."""
    from . import db

    if not peso:
        return {}
    c = conclusiones(conn)
    if not c:
        c = (json.loads(db.get_valor(conn, CONCLUSIONES) or "{}") or {}).get("grupos") or {}
    out: dict[str, dict[str, float]] = {}
    for dim, por_grupo in c.items():
        for grupo, d in por_grupo.items():
            if d["n"] < min_n:
                continue
            out.setdefault(dim, {})[grupo] = 1 + peso * max(-1.0, min(1.0, d["log2"]))
    return out


def factor_de(meta: dict, tabla: dict[str, dict[str, float]]) -> float:
    """El multiplicador de un clip: el producto de los factores de sus grupos (1 si no hay datos)."""
    f = 1.0
    for dim, grupo in claves_de(meta).items():
        f *= tabla.get(dim, {}).get(grupo, 1.0)
    return f
