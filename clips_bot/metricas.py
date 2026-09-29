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


def actualizar(conn: sqlite3.Connection, cliente, ready: Path, dias: int = 60,
               ahora: datetime | None = None) -> int:
    """Lee las métricas de los Shorts de los últimos `dias` y las guarda por clip. Devuelve cuántos
    clips tienen métrica. `cliente`: youtube.Cliente del canal de clips (rots)."""
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(days=dias)
    clips = entregados(ready, desde)
    pares = emparejar(cliente.mis_videos(desde), clips)
    if not pares:
        return 0
    datos = cliente.metricas([v["id"] for v in pares.values()], desde, ahora)
    por_id = {m["clip_id"]: m for m in clips}
    for clip_id, v in pares.items():
        meta, d = por_id[clip_id], datos.get(v["id"], {})
        try:
            entero = cliente.pct_entero(v["id"], desde, ahora)
        except Exception as e:     # la curva de retención es un extra: sin ella se guarda el resto
            log.warning("retención de %s: %s", v["id"], e)
            entero = None
        conn.execute(
            """INSERT INTO metricas (clip_id, video_id, publicado, actualizado, vistas,
                   duracion_media_s, pct_visto_medio, pct_entero, streamer, duracion_s, layout, camara)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(clip_id) DO UPDATE SET actualizado = excluded.actualizado,
                   vistas = excluded.vistas, duracion_media_s = excluded.duracion_media_s,
                   pct_visto_medio = excluded.pct_visto_medio, pct_entero = excluded.pct_entero""",
            (clip_id, v["id"], v["publicado"], ahora.isoformat(), d.get("vistas", 0),
             d.get("duracion_media_s"), d.get("pct_visto_medio"), entero, meta.get("streamer"),
             meta.get("duracion_s"), meta.get("layout"), 1 if tiene_camara(meta) else 0))
    conn.commit()
    return len(pares)


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


def factores(conn: sqlite3.Connection, peso: float, min_n: int) -> dict[str, dict[str, float]]:
    """{dimensión: {grupo: factor}}. factor = 1 + peso × log2(mediana del grupo / mediana general),
    acotado a ±1 en el log (entre ×(1 − peso) y ×(1 + peso)). Solo grupos con n ≥ min_n."""
    filas = conn.execute("SELECT vistas, streamer, duracion_s, layout, camara FROM metricas").fetchall()
    if not filas or not peso:
        return {}
    general = statistics.median(f[0] for f in filas) or 1
    grupos: dict[str, dict[str, list[int]]] = {}
    for vistas, streamer, dur, layout, camara in filas:
        meta = {"streamer": streamer, "duracion_s": dur, "layout": layout}
        claves = claves_de(meta)
        claves["camara"] = "con_camara" if camara else "sin_camara"
        for dim, grupo in claves.items():
            grupos.setdefault(dim, {}).setdefault(grupo, []).append(vistas)
    out: dict[str, dict[str, float]] = {}
    for dim, por_grupo in grupos.items():
        for grupo, vistas in por_grupo.items():
            if len(vistas) < min_n:
                continue
            ratio = max(statistics.median(vistas), 1) / general
            out.setdefault(dim, {})[grupo] = 1 + peso * max(-1.0, min(1.0, math.log2(ratio)))
    return out


def factor_de(meta: dict, tabla: dict[str, dict[str, float]]) -> float:
    """El multiplicador de un clip: el producto de los factores de sus grupos (1 si no hay datos)."""
    f = 1.0
    for dim, grupo in claves_de(meta).items():
        f *= tabla.get(dim, {}).get(grupo, 1.0)
    return f
