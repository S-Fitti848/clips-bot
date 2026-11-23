"""El resumen de cada Reel de Facebook a las 24 h (Santi, 2026-11-16), de Pequeña Historia y de Así Nació: el
mismo resumen que el de los Shorts (vistas, cuántos pasan los 3 s, retención al segundo 10 y al final,
interacción y seguidores nuevos) contra la mediana de los otros Reels del canal, con el gancho (la primera frase).
Queda guardado en bot_estado (`fb_reels_24h`) para el informe del 26/11.

Lo que da Facebook por Reel (medido el 16/11 con un Reel de cada página): `blue_reels_play_count` (reproducciones),
`post_video_retention_graph` (la curva segundo a segundo: los segundos 0 a 3 vienen SIEMPRE en 100 %, así que
"pasa los 3 s" es el valor del segundo 4), `post_video_avg_time_watched` (ms), `post_video_followers` (seguidores
que trajo el Reel) y del post las reacciones, los comentarios y los compartidos; de la página,
`page_daily_follows_unique` (seguidores nuevos por día).
"""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import db

log = logging.getLogger(__name__)

CLAVE = "fb_reels_24h"           # bot_estado: {video_id: {canal, clip_id, publicado, medido, ...métricas}}
REVISADO = "fb_reels_24h_revisado"
CADA_S = 1800                    # se mira cada 30 min
DESDE_H, HASTA_H = 24, 48        # se mide entre las 24 y las 48 h de publicado (nada del pasado de golpe)
MIN_PARA_MEDIANA = 3             # con menos de 3 medidos a las 24 h, la mediana sale de los datos de hoy
NOMBRES = {"facebook": "Pequeña Historia", "facebook_asinacio": "Así Nació",
           "facebook_comunidad": "Pequeña Historia (publicación de comunidad)"}
CREDENCIALES = {"facebook": ("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN"),
                "facebook_comunidad": ("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN"),
                "facebook_asinacio": ("ASINACIO_FACEBOOK_PAGE_ID", "ASINACIO_FACEBOOK_PAGE_TOKEN")}


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def curva(graph: dict | None) -> list[tuple[int, float]]:
    return sorted((int(k), _num(v)) for k, v in (graph or {}).items() if str(k).isdigit())


def retencion_en(puntos: list[tuple[int, float]], segundo: int) -> float | None:
    """La fracción que sigue mirando en `segundo` (el último punto que no lo pasa)."""
    antes = [v for s, v in puntos if s <= segundo]
    return round(100 * antes[-1], 1) if antes else None


def metricas(vid: str, token: str, page_id: str, version: str, session=None,
             publicado: datetime | None = None) -> dict:
    """Las métricas de un Reel (las que da Facebook en este momento, acumuladas)."""
    from .facebook import GRAPH

    s = session or requests.Session()
    base = GRAPH.format(version=version)
    r = s.get(f"{base}/{vid}/video_insights", params={"access_token": token}, timeout=30)
    r.raise_for_status()
    m = {x.get("name"): (x.get("values") or [{}])[0].get("value") for x in r.json().get("data", [])}
    pts = curva(m.get("post_video_retention_graph"))
    out = {"vistas": int(_num(m.get("blue_reels_play_count") or m.get("fb_reels_total_plays"))),
           "pasa_3s": retencion_en(pts, 4), "ret_10": retencion_en(pts, 10),
           "ret_final": round(100 * pts[-1][1], 1) if pts else None, "dura_s": pts[-1][0] if pts else None,
           "medio_s": round(_num(m.get("post_video_avg_time_watched")) / 1000, 1),
           "seguidores_reel": int(_num(m.get("post_video_followers")))}
    v = s.get(f"{base}/{vid}", params={"access_token": token, "fields": "post_id,permalink_url"}, timeout=30)
    info = v.json() if v.status_code == 200 else {}
    out["link"] = ("https://www.facebook.com" + info["permalink_url"]) if str(info.get("permalink_url", "")).startswith("/") \
        else info.get("permalink_url", "")
    reacciones = comentarios = compartidos = 0
    if info.get("post_id"):
        p = s.get(f"{base}/{page_id}_{info['post_id']}", timeout=30,
                  params={"access_token": token,
                          "fields": "reactions.summary(true).limit(0),comments.summary(true).limit(0),shares"})
        if p.status_code == 200:
            pj = p.json()
            reacciones = int(_num(((pj.get("reactions") or {}).get("summary") or {}).get("total_count")))
            comentarios = int(_num(((pj.get("comments") or {}).get("summary") or {}).get("total_count")))
            compartidos = int(_num((pj.get("shares") or {}).get("count")))
    out.update(reacciones=reacciones, comentarios=comentarios, compartidos=compartidos,
               interaccion=reacciones + comentarios + compartidos)
    if publicado is not None:
        out["seguidores_pagina"] = seguidores_pagina(s, base, page_id, token, publicado)
    return out


def metricas_post(post_id: str, token: str, page_id: str, version: str, session=None,
                  publicado: datetime | None = None) -> dict:
    """Una publicación de comunidad (foto + pregunta): cuántos la vieron, comentarios, compartidos y reacciones."""
    from .facebook import GRAPH

    s = session or requests.Session()
    base = GRAPH.format(version=version)
    # La subida de una foto devuelve el id de la FOTO; la publicación es <página>_<foto> (con el id solo, Facebook
    # contesta 400 "nonexisting field (permalink_url)": pasaba cada 30 min con la comunidad del 21/11).
    if "_" not in str(post_id) and page_id:
        post_id = f"{page_id}_{post_id}"
    p = s.get(f"{base}/{post_id}", timeout=30, params={
        "access_token": token, "fields": "permalink_url,reactions.summary(true).limit(0),comments.summary(true).limit(0),shares"})
    p.raise_for_status()
    pj = p.json()
    vistas = None
    i = s.get(f"{base}/{post_id}/insights", timeout=30,
              params={"access_token": token, "metric": "post_impressions_unique"})
    if i.status_code == 200:
        datos = i.json().get("data") or []
        vistas = int(_num(((datos[0].get("values") or [{}])[0] if datos else {}).get("value")))
    out = {"vistas": vistas, "reacciones": int(_num(((pj.get("reactions") or {}).get("summary") or {}).get("total_count"))),
           "comentarios": int(_num(((pj.get("comments") or {}).get("summary") or {}).get("total_count"))),
           "compartidos": int(_num((pj.get("shares") or {}).get("count"))), "link": pj.get("permalink_url", "")}
    out["interaccion"] = out["reacciones"] + out["comentarios"] + out["compartidos"]
    if publicado is not None:
        out["seguidores_pagina"] = seguidores_pagina(s, base, page_id, token, publicado)
    return out


def seguidores_pagina(s, base: str, page_id: str, token: str, publicado: datetime) -> int | None:
    """Seguidores nuevos de la página en las 24 h desde la publicación (los días que la tocan)."""
    try:
        r = s.get(f"{base}/{page_id}/insights/page_daily_follows_unique", timeout=30,
                  params={"access_token": token, "period": "day",
                          "since": int((publicado - timedelta(days=1)).timestamp()),
                          "until": int((publicado + timedelta(days=2)).timestamp())})
        valores = ((r.json().get("data") or [{}])[0].get("values") or []) if r.status_code == 200 else []
    except (requests.RequestException, ValueError, IndexError):
        return None
    total = 0
    for x in valores:
        fin = datetime.fromisoformat(str(x.get("end_time")).replace("+0000", "+00:00"))
        if publicado < fin <= publicado + timedelta(hours=32):
            total += int(_num(x.get("value")))
    return total


def gancho_y_titulo(clip_id: str, root: Path) -> tuple[str, str]:
    """La primera frase del video y el título, de lo que quedó guardado al armarlo."""
    try:
        if str(clip_id).startswith("asinacio_"):
            dia = clip_id.split("_", 1)[1]
            g = json.loads((root / "output" / "animacion" / dia / "guion.json").read_text("utf-8"))["guion"]
            from .animacion import marcas

            segs = marcas.segmentos(g)
            return (segs[0][2] if segs else ""), str(g.get("titulo") or "")
        meta = json.loads((root / "output" / "ready" / f"{clip_id}.json").read_text("utf-8"))
        guion = (meta.get("efemeride") or {}).get("guion") or []
        primera = guion[0] if guion and isinstance(guion[0], str) else ((guion[0] or {}).get("texto", "") if guion else "")
        return primera, str((meta.get("textos") or {}).get("titulo") or "")
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return "", ""


def _mediana(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


CAMPOS = (("vistas", "Reproducciones", ""), ("pasa_3s", "Pasan los 3 s", " %"), ("ret_10", "Siguen en el segundo 10", " %"),
          ("ret_final", "Llegan al final", " %"), ("medio_s", "Tiempo medio visto", " s"),
          ("interaccion", "Interacción (reacciones + comentarios + compartidos)", ""),
          ("seguidores_reel", "Seguidores que trajo el Reel", ""))


def _f(x, suf=""):
    if x is None:
        return "–"
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return (f"{x:,}".replace(",", ".") if isinstance(x, int) else str(x).replace(".", ",")) + suf


CAMPOS_POST = (("vistas", "Personas que la vieron", ""), ("comentarios", "Comentarios", ""),
               ("compartidos", "Compartidos", ""), ("reacciones", "Reacciones", ""))


def texto(canal: str, x: dict, otros: list[dict], de_hoy: bool) -> str:
    nombre = NOMBRES.get(canal, canal)
    que = "Publicación" if canal == "facebook_comunidad" else "Reel"
    lineas = [f"🔧 Claude Code: 📊 <b>{que} de {nombre} a las 24 h</b>" + (f": {html.escape(x['titulo'])}" if x.get("titulo") else ""),
              f"Gancho: «{html.escape(x.get('gancho') or '(no lo encontré)')}»",
              f"Mediana de las otras {len(otros)} del canal entre paréntesis"
              + (" (todavía sin 3 medidos a las 24 h: los datos de hoy, acumulados)" if de_hoy else " (a las 24 h)") + ":"]
    for k, nombre_k, suf in (CAMPOS_POST if canal == "facebook_comunidad" else CAMPOS):
        lineas.append(f"• {nombre_k}: {_f(x.get(k), suf)} ({_f(_mediana([o.get(k) for o in otros]), suf)})")
    if x.get("vistas"):
        lineas.append(f"• Cada 1.000 reproducciones: {_f(round(1000 * x['interaccion'] / x['vistas'], 1))} interacciones "
                      f"({x['reacciones']} reacciones, {x['comentarios']} comentarios, {x['compartidos']} compartidos)")
    if x.get("seguidores_pagina") is not None:
        lineas.append(f"• La página sumó {x['seguidores_pagina']} seguidores en esas 24 h")
    if x.get("flojas"):     # Así Nació: lo más flojo según la revisión, al lado de los números (2026-11-16)
        lineas.append("Lo más flojo según la revisión: " + " · ".join(
            f"{html.escape(f['categoria'])}: {html.escape(f['que'][:90])}" for f in x["flojas"]))
    if x.get("link"):
        lineas.append(x["link"])
    return "\n".join(lineas)


def cargar(conn) -> dict:
    try:
        return json.loads(db.get_valor(conn, CLAVE) or "{}")
    except ValueError:
        return {}


def pendientes(subidas: list[dict], medidos: dict, ahora: datetime) -> list[dict]:
    out = []
    for s in subidas:
        if s.get("canal") not in NOMBRES or not s.get("video_id") or s["video_id"] in medidos:
            continue
        try:
            pub = datetime.fromisoformat(str(s.get("publish_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub + timedelta(hours=DESDE_H) <= ahora <= pub + timedelta(hours=HASTA_H):
            out.append({**s, "_pub": pub})
    return out


def resumen_informe(conn) -> str:
    """Para el informe del 26/11: por canal, las medianas a las 24 h y los 3 mejores ganchos por retención al 10."""
    datos = cargar(conn)
    lineas = ["<b>Reels de Facebook a las 24 h</b>"]
    for canal, nombre in NOMBRES.items():
        xs = [x for x in datos.values() if x.get("canal") == canal]
        if not xs:
            continue
        lineas.append(f"{nombre}: {len(xs)} Reels · mediana: " + " · ".join(
            f"{n.split(' (')[0].lower()} {_f(_mediana([x.get(k) for x in xs]), suf)}" for k, n, suf in CAMPOS[:4]))
        for x in sorted(xs, key=lambda x: -(x.get("ret_10") or 0))[:3]:
            lineas.append(f"  · {_f(x.get('ret_10'), ' %')} en el seg. 10, {_f(x.get('vistas'))} rep.: "
                          f"«{html.escape((x.get('gancho') or '')[:90])}»")
    return "\n".join(lineas) if len(lineas) > 1 else ""
