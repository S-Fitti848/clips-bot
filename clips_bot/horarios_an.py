"""Prueba de horarios de Así Nació (Santi, 2026-11-18): 12:30 y 18:00 del 19/11 al 02/12 contra los de antes (13:00 y
20:00). Cada lunes, una línea en el resumen semanal con la mediana de vistas por horario:

- YouTube: las vistas de los 2 primeros días (el día de publicado y el siguiente, YouTube Analytics por día), así un
  video viejo no le gana a uno nuevo por tiempo. Se guardan en `bot_estado.asinacio_yt_2dias` (se piden una vez).
- Facebook: las reproducciones a las 24 h que ya mide `stats_fb` (`fb_reels_24h`).

El horario de cada video sale de su `publish_at` (los que salieron más tarde por un reintento cuentan en el turno más
cercano: 13:19 → 13:00).
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone

from . import db
from .youtube import AR

log = logging.getLogger(__name__)

YT_2DIAS = "asinacio_yt_2dias"     # bot_estado: {video_id: vistas de los 2 primeros días}
TURNOS = {"mediodía": ("12:30", "13:00"), "tarde": ("18:00", "20:00")}   # (prueba, antes)


def _min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def turno_de(hora_ar: str) -> tuple[str, str]:
    """('mediodía' | 'tarde', el horario de los cuatro más cercano)."""
    hs = [(t, h) for t, par in TURNOS.items() for h in par]
    return min(hs, key=lambda th: abs(_min(th[1]) - _min(hora_ar)))


def _hora_ar(iso: str) -> tuple[str, str] | None:
    try:
        t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    t = t.astimezone(AR)
    return t.date().isoformat(), t.strftime("%H:%M")


def vistas_youtube(conn, cliente, ahora: datetime) -> dict[str, int]:
    """Las vistas de los 2 primeros días de cada Así Nació de YouTube publicado hace más de 2 días (las ya pedidas
    salen de bot_estado)."""
    guardadas = json.loads(db.get_valor(conn, YT_2DIAS) or "{}")
    nuevas = False
    for s in db.subidas(conn, ("programada", "publicada")):
        if s["canal"] != "animacion" or not s["video_id"] or s["video_id"] in guardadas:
            continue
        try:
            t = datetime.strptime(s["publish_at"] or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if ahora.astimezone(timezone.utc) - t < timedelta(days=3):     # que el segundo día esté completo
            continue
        dia = t.astimezone(timezone(timedelta(hours=-8)))           # YouTube Analytics cuenta los días en el Pacífico
        try:
            filas = cliente._analytics({"startDate": dia.strftime("%Y-%m-%d"),
                                        "endDate": (dia + timedelta(days=1)).strftime("%Y-%m-%d"),
                                        "metrics": "views", "dimensions": "day",
                                        "filters": f"video=={s['video_id']}"})
        except Exception as e:      # noqa: BLE001 — una consulta que falla no tira el resumen
            log.info("vistas de %s: %s", s["video_id"], e)
            continue
        guardadas[s["video_id"]] = sum(int(f[1]) for f in filas)
        nuevas = True
    if nuevas:
        db.set_valor(conn, YT_2DIAS, json.dumps(guardadas))
    return guardadas


def por_horario(conn, yt: dict[str, int], fb: dict) -> dict:
    """{(turno, hora): {"yt": [vistas], "fb": [vistas]}} de todos los Así Nació medidos."""
    out: dict = {}
    for s in db.subidas(conn, ("programada", "publicada")):
        dh = _hora_ar(s["publish_at"] or "")
        if not dh or not s["video_id"]:
            continue
        if s["canal"] == "animacion" and s["video_id"] in yt:
            out.setdefault(turno_de(dh[1]), {"yt": [], "fb": []})["yt"].append(yt[s["video_id"]])
        elif s["canal"] == "facebook_asinacio" and (fb.get(s["video_id"]) or {}).get("vistas") is not None:
            out.setdefault(turno_de(dh[1]), {"yt": [], "fb": []})["fb"].append(int(fb[s["video_id"]]["vistas"]))
    return out


def _m(xs: list[int]) -> str:
    return f"{round(statistics.median(xs)):,}".replace(",", ".") if xs else "—"


def linea(datos: dict) -> str:
    """Una línea: 12:30 contra 13:00 y 18:00 contra 20:00, mediana de YouTube (2 días) / Facebook (24 h) y cuántos."""
    if not any(v["yt"] or v["fb"] for v in datos.values()):
        return ""
    partes = []
    for turno, (prueba, antes) in TURNOS.items():
        a, b = datos.get((turno, prueba), {"yt": [], "fb": []}), datos.get((turno, antes), {"yt": [], "fb": []})
        partes.append(f"{prueba} {_m(a['yt'])}/{_m(a['fb'])} ({len(a['yt'])}) contra {antes} "
                      f"{_m(b['yt'])}/{_m(b['fb'])} ({len(b['yt'])})")
    return "Horarios de Así Nació (mediana YouTube 2 días/Facebook 24 h, videos): " + " · ".join(partes) + "."


def resumen(conn, cliente, fb: dict, ahora: datetime) -> str:
    try:
        yt = vistas_youtube(conn, cliente, ahora) if cliente is not None else {}
    except Exception as e:      # noqa: BLE001
        log.warning("horarios de Así Nació: %s", e)
        yt = {}
    return linea(por_horario(conn, yt, fb))
