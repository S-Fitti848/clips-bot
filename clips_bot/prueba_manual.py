"""Prueba manual vs API (pedido de Santi, 2026-11-10): ¿el problema de Rots es subir por la API?

Durante `publicacion.prueba_manual_dias` días desde `prueba_manual_desde`, de la entrega diaria UN
clip por día va marcado "📱 SUBILO VOS": Santi lo sube a mano desde la app del celular, y el bot no
lo sube (no tiene 📤). Para no sesgar la prueba, el clip manual no es siempre el #1 de la entrega:
rota según el día (así cae en los tres horarios y no siempre en el mejor puntaje).

El video que sube Santi se encuentra solo por título (metricas.emparejar, en la corrida de las
05:00). Al terminar, `comparar` pide a YouTube Analytics de dónde vinieron las vistas de cada video
(insightTrafficSourceType) y compara el % que vino del feed de Shorts (SHORTS): manuales contra los
subidos por la API en los mismos días. El informe sale solo por Telegram el día siguiente al último.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from statistics import median

from . import db

REGISTRO = "prueba_manual"            # bot_estado: [{clip_id, dia, streamer, horario, orden}]
INFORME = "prueba_manual_informe"     # bot_estado: fecha en que ya se mandó el informe


def dias(desde: str, n: int) -> list[date]:
    inicio = date.fromisoformat(desde)
    return [inicio + timedelta(days=i) for i in range(n)]


def activa(hoy: date, desde: str, n: int) -> bool:
    return bool(desde) and n > 0 and hoy in dias(desde, n)


def indice_del_dia(hoy: date, desde: str, cuantos: int) -> int:
    """Qué posición de la entrega va a mano: rota con el día (0, 1, 2, 0, …)."""
    if cuantos <= 0:
        return 0
    return (hoy - date.fromisoformat(desde)).days % cuantos


def registro(conn: sqlite3.Connection) -> list[dict]:
    try:
        return json.loads(db.get_valor(conn, REGISTRO) or "[]")
    except ValueError:
        return []


def es_manual(conn: sqlite3.Connection, clip_id: str) -> bool:
    return any(r.get("clip_id") == clip_id for r in registro(conn))


def ya_hay_hoy(conn: sqlite3.Connection, hoy: date) -> bool:
    return any(r.get("dia") == hoy.isoformat() for r in registro(conn))


def anotar(conn: sqlite3.Connection, clip_id: str, hoy: date, streamer: str, horario: str | None,
           orden: int) -> None:
    filas = [r for r in registro(conn) if r.get("clip_id") != clip_id]
    filas.append({"clip_id": clip_id, "dia": hoy.isoformat(), "streamer": streamer,
                  "horario": horario, "orden": orden})
    db.set_valor(conn, REGISTRO, json.dumps(filas, ensure_ascii=False))


def descripcion_para_pegar(textos: dict) -> str:
    """En la era manual (los Shorts que rendían) los hashtags iban en la descripción: acá van juntos,
    en un solo bloque para copiar y pegar en la app."""
    desc = (textos.get("descripcion") or "").strip()
    tags = " ".join(textos.get("hashtags") or [])
    return f"{desc}\n\n{tags}".strip() if tags else desc


ENCABEZADO = ("📱 <b>SUBILO VOS DESDE EL CELU</b> (prueba manual vs API, día {n} de {total}). "
              "El bot NO lo sube. Subilo en el horario sugerido, PÚBLICO, con el título y la "
              "descripción de abajo tal cual (el bot lo encuentra por el título).")


def grupos(conn: sqlite3.Connection, desde: str, n: int) -> tuple[dict[str, dict], dict[str, dict],
                                                                   list[dict]]:
    """({video_id: fila} manuales, {video_id: fila} por la API, manuales sin video encontrado)."""
    primero = date.fromisoformat(desde)
    ultimo = primero + timedelta(days=n)       # exclusivo
    reg = registro(conn)
    manual_ids = {r["clip_id"] for r in reg}
    pares = dict(conn.execute("SELECT clip_id, video_id FROM metricas").fetchall())
    manuales, sin_video = {}, []
    for r in reg:
        vid = pares.get(r["clip_id"])
        if vid:
            manuales[vid] = {**r, "video_id": vid}
        else:
            sin_video.append(r)
    api = {}
    for s in db.subidas(conn, ("programada", "publicada")):
        if s["canal"] != "rots" or not s["video_id"] or s["clip_id"] in manual_ids:
            continue
        cuando = (s["publish_at"] or s["creada"] or "")[:10]
        try:
            d = date.fromisoformat(cuando)
        except ValueError:
            continue
        if primero <= d < ultimo:
            api[s["video_id"]] = {"clip_id": s["clip_id"], "dia": d.isoformat()}
    return manuales, api, sin_video


def fuentes(cliente, video_ids: list[str], desde: date, hasta: date) -> dict[str, dict[str, int]]:
    """{video_id: {fuente: vistas}} de YouTube Analytics (una consulta por video)."""
    out: dict[str, dict[str, int]] = {}
    for vid in video_ids:
        filas = cliente._analytics({
            "startDate": desde.isoformat(), "endDate": hasta.isoformat(), "metrics": "views",
            "dimensions": "insightTrafficSourceType", "filters": f"video=={vid}"})
        out[vid] = {f[0]: int(f[1]) for f in filas}
    return out


def resumen(por_video: dict[str, dict[str, int]]) -> dict:
    """Vistas totales, % del feed de Shorts sobre el total del grupo y la mediana por video."""
    total = sum(sum(f.values()) for f in por_video.values())
    feed = sum(f.get("SHORTS", 0) for f in por_video.values())
    pcts = [100 * f.get("SHORTS", 0) / sum(f.values()) for f in por_video.values() if sum(f.values())]
    vistas = [sum(f.values()) for f in por_video.values()]
    return {"videos": len(por_video), "vistas": total, "feed": feed,
            "pct_feed": round(100 * feed / total, 1) if total else None,
            "pct_feed_mediana": round(median(pcts), 1) if pcts else None,
            "vistas_mediana": median(vistas) if vistas else None}


def comparar(conn: sqlite3.Connection, cliente, desde: str, n: int,
             hoy: date | None = None) -> str:
    """El informe en HTML para Telegram (y para la consola)."""
    hoy = hoy or datetime.now(timezone.utc).date()
    manuales, api, sin_video = grupos(conn, desde, n)
    inicio = date.fromisoformat(desde)
    datos = fuentes(cliente, list(manuales) + list(api), inicio, hoy)
    m = resumen({v: datos.get(v, {}) for v in manuales})
    a = resumen({v: datos.get(v, {}) for v in api})

    def num(x) -> str:
        return f"{x:,.0f}".replace(",", ".")

    def linea(nombre: str, r: dict) -> str:
        if not r["videos"]:
            return f"{nombre}: sin videos"
        return (f"{nombre}: {r['videos']} videos, {num(r['vistas'])} vistas, "
                f"<b>{r['pct_feed']} % del feed de Shorts</b> (mediana por video "
                f"{r['pct_feed_mediana']} %; vistas por video, mediana {num(r['vistas_mediana'])})")

    partes = [f"📱 <b>Prueba manual vs API</b> ({inicio:%d/%m} → "
              f"{inicio + timedelta(days=n - 1):%d/%m}, datos hasta {hoy:%d/%m})",
              linea("📱 A mano", m), linea("🤖 Por la API", a)]
    if sin_video:
        partes.append("No encontré el video de: " + ", ".join(
            f"{r['dia'][5:]} {r['streamer']}" for r in sin_video)
            + " (¿no se subió, o se cambió el título?)")
    if m["pct_feed"] is not None and a["pct_feed"] is not None:
        if m["pct_feed"] >= a["pct_feed"] + 20:
            partes.append("→ Los subidos a mano entran mucho más al feed: la subida por la API "
                          "parece ser parte del problema.")
        elif abs(m["pct_feed"] - a["pct_feed"]) < 20:
            partes.append("→ Diferencia chica: la API no parece ser la causa; mirar lo demás "
                          "(hashtags, categoría, streamers, duración).")
        else:
            partes.append("→ Los de la API entran más al feed que los manuales.")
    partes.append("Por video (fuente principal de vistas):")
    for nombre, grupo in (("📱", manuales), ("🤖", api)):
        for vid, info in sorted(grupo.items(), key=lambda kv: kv[1]["dia"]):
            f = datos.get(vid, {})
            tot = sum(f.values())
            pct = f"{100 * f.get('SHORTS', 0) / tot:.0f} %" if tot else "-"
            partes.append(f"{nombre} {info['dia'][5:]} youtu.be/{vid}: {tot} vistas, feed {pct}")
    return "\n".join(partes)


def toca_informe(conn: sqlite3.Connection, hoy: date, desde: str, n: int) -> bool:
    """El día siguiente al último de la prueba (o después, si ese día falló), una sola vez."""
    if not desde or n <= 0:
        return False
    fin = date.fromisoformat(desde) + timedelta(days=n)
    return hoy >= fin and not db.get_valor(conn, INFORME)
