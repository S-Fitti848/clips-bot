"""Medición del gancho de Pequeña Historia (Santi, 2026-11-12).

Desde el 2026-11-12 todo Pequeña Historia (YouTube y Facebook, efeméride e historia) arranca con el
gancho: lo más sorprendente en la primera frase, escrito en grande desde el primer cuadro, sin
"Un día como hoy". Para saber si sirvió, por cada video:
- Facebook: en qué SEGUNDO se va la mayoría (el primero en que la curva de retención,
  `post_video_retention_graph`, queda abajo del 50 %), reproducciones y tiempo medio visto.
- YouTube: el % que se queda (`engagedViews / views` de YouTube Analytics: lo más parecido que da
  la API a "vistos vs. deslizados" de Studio) y las vistas.
Se guarda en bot_estado (`CLAVE`), se actualiza una vez por día desde la escucha, y a la semana
(`DESDE` + `DIAS_INFORME`) le llega a Santi la comparación con los videos de antes.
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timedelta, timezone

import requests

from . import db

log = logging.getLogger(__name__)

CLAVE = "ph_medicion"                 # bot_estado: {"fb": {video_id: {...}}, "yt": {video_id: {...}}}
CLAVE_DIA = "ph_medicion_dia"         # bot_estado: el último día (AR) en que se midió
CLAVE_INFORME = "ph_medicion_informe"  # bot_estado: el informe ya se mandó
DESDE = date(2026, 11, 12)            # el primer día con el gancho primero
DIAS_INFORME = 7
HORA = "09:00"                        # la medición del día, después de la corrida de las 05:00
MITAD = 0.5


def segundo_que_se_va(curva: dict) -> int | None:
    """El primer segundo en que queda menos de la mitad (la "mayoría se fue"). None si nunca."""
    puntos = sorted((int(k), float(v)) for k, v in (curva or {}).items() if str(k).isdigit())
    return next((s for s, v in puntos if v < MITAD), None)


def medir_facebook(subidas: list[dict], token: str, version: str, session=None) -> dict:
    """{video_id: {publicado, se_va_s, reproducciones, medio_s, clip_id}} de los Reels de la página."""
    from .facebook import GRAPH

    s = session or requests.Session()
    base = GRAPH.format(version=version)
    out = {}
    for sub in subidas:
        vid = sub.get("video_id")
        if not vid:
            continue
        try:
            r = s.get(f"{base}/{vid}/video_insights", params={"access_token": token}, timeout=30)
            if r.status_code != 200:
                continue
            m = {x.get("name"): (x.get("values") or [{}])[0].get("value") for x in r.json().get("data", [])}
        except (requests.RequestException, ValueError) as e:
            log.info("insights de %s: %s", vid, e)
            continue
        out[vid] = {"clip_id": sub.get("clip_id"), "publicado": (sub.get("publish_at") or sub.get("creada") or "")[:10],
                    "se_va_s": segundo_que_se_va(m.get("post_video_retention_graph") or {}),
                    "reproducciones": m.get("blue_reels_play_count") or m.get("fb_reels_total_plays"),
                    "medio_s": round((m.get("post_video_avg_time_watched") or 0) / 1000, 1)}
    return out


def medir_youtube(cliente, desde: datetime) -> dict:
    """{video_id: {publicado, titulo, vistas, se_queda_pct}} de los Shorts del canal."""
    videos = cliente.mis_videos(desde)
    if not videos:
        return {}
    hoy = datetime.now(timezone.utc)
    filas = cliente._analytics({
        "startDate": desde.strftime("%Y-%m-%d"), "endDate": hoy.strftime("%Y-%m-%d"),
        "metrics": "views,engagedViews", "dimensions": "video",
        "filters": "video==" + ",".join(v["id"] for v in videos[:200])})
    tot = {f[0]: (int(f[1]), int(f[2])) for f in filas}
    out = {}
    for v in videos:
        vistas, quedan = tot.get(v["id"], (0, 0))
        out[v["id"]] = {"publicado": v["publicado"][:10], "titulo": v["titulo"], "vistas": vistas,
                        "se_queda_pct": round(100 * quedan / vistas, 1) if vistas else None}
    return out


def guardar(conn, fb: dict, yt: dict) -> dict:
    datos = cargar(conn)
    datos["fb"].update(fb)
    datos["yt"].update(yt)
    db.set_valor(conn, CLAVE, json.dumps(datos, ensure_ascii=False))
    return datos


def cargar(conn) -> dict:
    d = json.loads(db.get_valor(conn, CLAVE) or "{}")
    return {"fb": d.get("fb") or {}, "yt": d.get("yt") or {}}


def _mediana(xs):
    xs = [x for x in xs if x is not None]
    return (statistics.median(xs), len(xs)) if xs else (None, 0)


def _f(x, suf=""):
    return "-" if x is None else f"{x:.1f}".replace(".", ",").replace(",0", "") + suf


def informe(datos: dict, desde: date = DESDE, hasta: date | None = None) -> str:
    """Antes (publicados antes de `desde`) contra después (desde `desde`), en medianas."""
    hasta = hasta or date.today()

    def lado(xs, despues):
        return [x for x in xs if x.get("publicado") and
                ((desde.isoformat() <= x["publicado"] <= hasta.isoformat()) if despues
                 else x["publicado"] < desde.isoformat())]

    fb, yt = list(datos["fb"].values()), list(datos["yt"].values())
    lineas = [f"🔧 Claude Code: <b>Pequeña Historia, gancho primero</b> (desde el {desde:%d/%m}): "
              "antes contra después, en medianas."]
    for nombre, xs, campos in (
            ("Facebook", fb, (("se_va_s", "segundo en que se va la mayoría", " s"),
                              ("reproducciones", "reproducciones", ""), ("medio_s", "tiempo medio visto", " s"))),
            ("YouTube", yt, (("se_queda_pct", "% que se queda", " %"), ("vistas", "vistas", "")))):
        a, d = lado(xs, False), lado(xs, True)
        lineas.append(f"\n<b>{nombre}</b> ({len(a)} antes, {len(d)} después)")
        for k, titulo, suf in campos:
            (ma, na), (md, nd) = _mediana([x.get(k) for x in a]), _mediana([x.get(k) for x in d])
            lineas.append(f"• {titulo}: {_f(ma, suf)} → {_f(md, suf)}")
    lineas.append("\nOJO: las vistas de YouTube de los últimos 2 días todavía no están completas, y con "
                  "pocos videos por lado la diferencia puede ser ruido.")
    return "\n".join(lineas)


def por_video(datos: dict, desde: date = DESDE) -> str:
    """Una línea por video desde `desde`: lo que se registró de cada uno."""
    lineas = []
    for vid, x in sorted(datos["yt"].items(), key=lambda kv: kv[1].get("publicado") or ""):
        if (x.get("publicado") or "") >= desde.isoformat():
            lineas.append(f"YouTube {x['publicado']} · {x.get('titulo', '')[:40]}: {x.get('vistas')} vistas, "
                          f"se queda {_f(x.get('se_queda_pct'), ' %')}")
    for vid, x in sorted(datos["fb"].items(), key=lambda kv: kv[1].get("publicado") or ""):
        if (x.get("publicado") or "") >= desde.isoformat():
            lineas.append(f"Facebook {x['publicado']} · {vid}: se va la mayoría en el "
                          f"{_f(x.get('se_va_s'), ' s')}, {x.get('reproducciones')} reproducciones")
    return "\n".join(lineas)
