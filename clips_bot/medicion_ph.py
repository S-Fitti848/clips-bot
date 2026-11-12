"""Seguimiento de Pequeña Historia (Santi, 2026-11-12).

Desde el 2026-11-12: gancho primero en todo y el nicho nuevo (2 historias de Latinoamérica + 1 de
tecnología por día, formato corto). Para saber si sirvió, por cada video:
- Facebook: en qué SEGUNDO se va la mayoría (el primero en que la curva de retención,
  `post_video_retention_graph`, queda abajo del 50 %), reproducciones y tiempo medio visto.
- YouTube: el % que se queda, las vistas, si hubo un SEGUNDO EMPUJÓN (un día después del primero con
  al menos EMPUJON del primero) y el % de vistas de suscriptores.
  * "% que se queda": la API no da "Se quedaron para mirar" de Studio; lo más parecido es
    `engagedViews / views`, que da menos que Studio en los que rinden bien. Se CALIBRA con los
    valores que pasó Santi de Studio (CALIBRACION, recta por mínimos cuadrados).
  * "% de usuarios que vuelven": la API de Analytics no lo da (probado: `viewerType` no existe). Lo
    más parecido es el % de vistas de suscriptores (`subscribedStatus`); el dato exacto está en
    Studio (Audiencia → espectadores nuevos y recurrentes).
Se guarda en bot_estado (`CLAVE`), se actualiza una vez por día desde la escucha, y a las 2 semanas
(`DESDE` + `DIAS_INFORME`) le llega a Santi la comparación con los `ANTES_N` Shorts anteriores, y en
YouTube, tecnología contra Latinoamérica.
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timezone

import requests

from . import db

log = logging.getLogger(__name__)

CLAVE = "ph_medicion"                 # bot_estado: {"fb": {video_id: {...}}, "yt": {video_id: {...}}}
CLAVE_DIA = "ph_medicion_dia"         # bot_estado: el último día (AR) en que se midió
CLAVE_INFORME = "ph_medicion_informe"  # bot_estado: el informe ya se mandó
DESDE = date(2026, 11, 12)            # gancho primero y el nicho nuevo
DIAS_INFORME = 14                     # Santi: "en 2 semanas comparame contra los 10 Shorts anteriores"
ANTES_N = 10
HORA = "09:00"                        # la medición del día, después de la corrida de las 05:00
MITAD = 0.5
EMPUJON = 0.25                        # un día con ≥ 25 % de las vistas del primero = segundo empujón

# "Se quedaron para mirar" de Studio (Santi, 2026-11-12) contra engagedViews/views de la API, de los
# mismos Shorts: (API, Studio).
CALIBRACION = [(56.1, 63.9),    # Nacozari
               (50.3, 61.6),    # Beatles
               (28.2, 28.4)]    # Capilla Sixtina


def recta(puntos=None) -> tuple[float, float]:
    """(a, b) de Studio ≈ a + b · API, por mínimos cuadrados."""
    puntos = puntos or CALIBRACION
    xs, ys = [p[0] for p in puntos], [p[1] for p in puntos]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 1.0
    return my - b * mx, b


def calibrado(pct_api: float | None) -> float | None:
    if pct_api is None:
        return None
    a, b = recta()
    return round(max(0.0, min(100.0, a + b * pct_api)), 1)


def segundo_que_se_va(curva: dict) -> int | None:
    """El primer segundo en que queda menos de la mitad (la "mayoría se fue"). None si nunca."""
    puntos = sorted((int(k), float(v)) for k, v in (curva or {}).items() if str(k).isdigit())
    return next((s for s, v in puntos if v < MITAD), None)


def hubo_empujon(por_dia: list[int]) -> bool:
    """¿Algún día después del primero con al menos EMPUJON de las vistas del primero?"""
    if not por_dia or por_dia[0] <= 0:
        return False
    return any(v >= EMPUJON * por_dia[0] for v in por_dia[1:])


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
        out[vid] = {"clip_id": sub.get("clip_id"), "tipo": tipo_de(sub.get("clip_id")),
                    "publicado": (sub.get("publish_at") or sub.get("creada") or "")[:10],
                    "se_va_s": segundo_que_se_va(m.get("post_video_retention_graph") or {}),
                    "reproducciones": m.get("blue_reels_play_count") or m.get("fb_reels_total_plays"),
                    "medio_s": round((m.get("post_video_avg_time_watched") or 0) / 1000, 1)}
    return out


def tipo_de(clip_id: str | None) -> str:
    """latam (historia de Latinoamérica) | tecnologia (la efeméride desde el 2026-11-12) | efemeride."""
    c = str(clip_id or "")
    if c.startswith("historia_fb_"):
        return "latam"
    return "efemeride" if c.startswith("efemeride_") else ""


def medir_youtube(cliente, desde: datetime, clips: dict[str, str] | None = None) -> dict:
    """{video_id: {publicado, titulo, vistas, se_queda_api, se_queda_pct (calibrado), empujon,
    suscriptos_pct, tipo}} de los Shorts del canal. `clips`: {video_id: clip_id} (de `subidas`)."""
    from datetime import date as _date

    videos = cliente.mis_videos(desde)
    if not videos:
        return {}
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rango = {"startDate": desde.strftime("%Y-%m-%d"), "endDate": hoy}
    filas = cliente._analytics({**rango, "metrics": "views,engagedViews", "dimensions": "video",
                                "filters": "video==" + ",".join(v["id"] for v in videos[:200])})
    tot = {f[0]: (int(f[1]), int(f[2])) for f in filas}
    out = {}
    for v in videos:
        vistas, quedan = tot.get(v["id"], (0, 0))
        pub = v["publicado"][:10]
        api = round(100 * quedan / vistas, 1) if vistas else None
        x = {"publicado": pub, "titulo": v["titulo"], "vistas": vistas, "se_queda_api": api,
             "se_queda_pct": calibrado(api)}
        try:
            dias = cliente._analytics({**rango, "metrics": "views", "dimensions": "day",
                                       "filters": f"video=={v['id']}", "sort": "day"})
            x["empujon"] = hubo_empujon([int(r[1]) for r in dias if r[0] >= pub])
            subs = dict((r[0], int(r[1])) for r in cliente._analytics(
                {**rango, "metrics": "views", "dimensions": "subscribedStatus", "filters": f"video=={v['id']}"}))
            total = sum(subs.values())
            x["suscriptos_pct"] = round(100 * subs.get("SUBSCRIBED", 0) / total, 1) if total else None
        except Exception as e:      # una consulta que falla no tira la medición entera
            log.info("YouTube Analytics de %s: %s", v["id"], e)
        tipo = tipo_de((clips or {}).get(v["id"]))
        x["tipo"] = ("tecnologia" if tipo == "efemeride" and pub >= DESDE.isoformat() else tipo)
        out[v["id"]] = x
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
    return statistics.median(xs) if xs else None


def _f(x, suf=""):
    if x is None:
        return "-"
    t = f"{x:.1f}".replace(".", ",")
    return (t[:-2] if t.endswith(",0") else t) + suf


def _lados(xs: list[dict], desde: date, hasta: date, n_antes: int = ANTES_N) -> tuple[list, list]:
    """(los n_antes anteriores a `desde`, los de `desde` a `hasta`), por fecha de publicación."""
    con = sorted((x for x in xs if x.get("publicado")), key=lambda x: x["publicado"])
    antes = [x for x in con if x["publicado"] < desde.isoformat()][-n_antes:]
    despues = [x for x in con if desde.isoformat() <= x["publicado"] <= hasta.isoformat()]
    return antes, despues


def _pct(xs, k):
    vals = [bool(x.get(k)) for x in xs if x.get(k) is not None]
    return round(100 * sum(vals) / len(vals)) if vals else None


def informe(datos: dict, desde: date = DESDE, hasta: date | None = None) -> str:
    """Los ANTES_N anteriores contra los de desde `desde`, en medianas; y en YouTube, tecnología
    contra Latinoamérica."""
    hasta = hasta or date.today()
    fb_a, fb_d = _lados(list(datos["fb"].values()), desde, hasta)
    yt_a, yt_d = _lados(list(datos["yt"].values()), desde, hasta)
    L = [f"🔧 Claude Code: <b>Pequeña Historia: gancho primero y nicho nuevo</b> (desde el {desde:%d/%m}), "
         f"contra los {ANTES_N} anteriores. Medianas."]
    L.append(f"\n<b>YouTube</b> ({len(yt_a)} antes, {len(yt_d)} después)")
    L.append(f"• % que se queda (calibrado con Studio): {_f(_mediana([x.get('se_queda_pct') for x in yt_a]), ' %')}"
             f" → {_f(_mediana([x.get('se_queda_pct') for x in yt_d]), ' %')}")
    L.append(f"• vistas: {_f(_mediana([x.get('vistas') for x in yt_a]))} → {_f(_mediana([x.get('vistas') for x in yt_d]))}")
    L.append(f"• con segundo empujón: {_f(_pct(yt_a, 'empujon'), ' %')} → {_f(_pct(yt_d, 'empujon'), ' %')}")
    L.append(f"• vistas de suscriptores (lo más parecido a \"vuelven\" que da la API): "
             f"{_f(_mediana([x.get('suscriptos_pct') for x in yt_a]), ' %')} → "
             f"{_f(_mediana([x.get('suscriptos_pct') for x in yt_d]), ' %')}")
    for tipo, nombre in (("tecnologia", "Tecnología"), ("latam", "Latinoamérica")):
        xs = [x for x in yt_d if x.get("tipo") == tipo]
        L.append(f"• {nombre} ({len(xs)}): se queda {_f(_mediana([x.get('se_queda_pct') for x in xs]), ' %')}, "
                 f"vistas {_f(_mediana([x.get('vistas') for x in xs]))}, "
                 f"empujón {_f(_pct(xs, 'empujon'), ' %')}")
    L.append(f"\n<b>Facebook</b> ({len(fb_a)} antes, {len(fb_d)} después)")
    for k, titulo, suf in (("se_va_s", "segundo en que se va la mayoría", " s"),
                           ("reproducciones", "reproducciones", ""), ("medio_s", "tiempo medio visto", " s")):
        L.append(f"• {titulo}: {_f(_mediana([x.get(k) for x in fb_a]), suf)} → {_f(_mediana([x.get(k) for x in fb_d]), suf)}")
    L.append("\nOJO: el % que se queda es una estimación (la API no da el de Studio; calibrado con 3 videos, "
             "±3 puntos); el dato exacto de los que vuelven está en Studio; las vistas de los últimos 2 días "
             "no están completas; y con pocos videos por lado una diferencia chica puede ser ruido.")
    return "\n".join(L)


def por_video(datos: dict, desde: date = DESDE) -> str:
    """Una línea por video desde `desde`: lo que se registró de cada uno."""
    lineas = []
    for vid, x in sorted(datos["yt"].items(), key=lambda kv: kv[1].get("publicado") or ""):
        if (x.get("publicado") or "") >= desde.isoformat():
            lineas.append(f"YouTube {x['publicado']} · {x.get('tipo') or '?'} · {x.get('titulo', '')[:40]}: "
                          f"{x.get('vistas')} vistas, se queda {_f(x.get('se_queda_pct'), ' %')}"
                          + (", con segundo empujón" if x.get("empujon") else ""))
    for vid, x in sorted(datos["fb"].items(), key=lambda kv: kv[1].get("publicado") or ""):
        if (x.get("publicado") or "") >= desde.isoformat():
            lineas.append(f"Facebook {x['publicado']} · {vid}: se va la mayoría en el "
                          f"{_f(x.get('se_va_s'), ' s')}, {x.get('reproducciones')} reproducciones")
    return "\n".join(lineas)
