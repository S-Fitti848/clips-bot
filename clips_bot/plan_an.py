"""Así Nació: cómo vamos con el plan hasta el 15/12, los lunes desde las 10:00, en 5 líneas (Santi, 2026-11-23: "que
lo mande el bot desde la Pi, no la tarea de mi compu").

Sin Claude ni renders: lee el plan de PENDIENTES.md, los resultado.json de las pruebas de la semana
(output/animacion/**/resultado.json: ok/19, fallas y costo) y el gasto de pruebas por día (gemini_uso).
"""
from __future__ import annotations

import json
import re
import statistics
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ENVIADO = "plan_an_lunes"       # bot_estado: el lunes (AR) en que ya salió
HORA = (10, 0)
MINIMO_OK, TOPE_USD = 15, 0.60  # la meta del 10/12: 8 de 10 marcas con 15/19 o más y menos de US$ 0,60


def semanas(pendientes: str, anio: int) -> list[dict]:
    """Las filas del plan: {desde, hasta, meta, estado}."""
    out = []
    for linea in pendientes.splitlines():
        m = re.match(r"\|\s*\**(\d{1,2})/(\d{1,2})(?:\s*[–-]\s*(\d{1,2})/(\d{1,2}))?\**\s*\|([^|]*)\|([^|]*)\|", linea)
        if not m:
            continue
        d1, m1 = int(m.group(1)), int(m.group(2))
        d2, m2 = (int(m.group(3)), int(m.group(4))) if m.group(3) else (d1, m1)
        out.append({"desde": date(anio, m1, d1), "hasta": date(anio, m2, d2),
                    "meta": m.group(5).strip().strip("*").strip(), "estado": m.group(6).strip()})
    return out


def semana_de(filas: list[dict], hoy: date) -> dict | None:
    for f in filas:
        if f["desde"] <= hoy <= f["hasta"]:
            return f
    futuras = [f for f in filas if f["desde"] > hoy]
    return futuras[0] if futuras else None


def resultados(raiz: Path, desde_ts: float) -> list[dict]:
    out = []
    for p in raiz.glob("**/resultado.json"):
        try:
            if p.stat().st_mtime < desde_ts:
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d["_marca"] = p.parent.parent.name if p.parent.parent != raiz else p.parent.name
        out.append(d)
    return out


def _usd(x: float) -> str:
    return f"US$ {x:.2f}".replace(".", ",")


def texto(hoy: date, pendientes: str, res: list[dict], gasto_dias: dict[str, float]) -> str:
    filas = semanas(pendientes, hoy.year)
    sem = semana_de(filas, hoy)
    l1 = (f"🔧 Claude Code: Así Nació, semana {sem['desde']:%d/%m}–{sem['hasta']:%d/%m}: {sem['meta']}."
          if sem else "🔧 Claude Code: Así Nació: el plan hasta el 15/12 ya terminó.")
    previa = semana_de(filas, hoy - timedelta(days=7))
    hecho = (previa or {}).get("estado") or ""
    l2 = ("La semana pasada: " + (hecho[:160] + ("…" if len(hecho) > 160 else ""))) if hecho \
        else "La semana pasada: sin nada anotado en el plan."
    if res:
        mejor = max(res, key=lambda r: (r.get("ok") or 0) / max(1, r.get("total") or 19))
        costos = [float(r["costo"]) for r in res if r.get("costo") is not None]
        l3 = (f"Pruebas de la semana: {len(res)}; la mejor {mejor.get('ok')}/{mejor.get('total')} ({mejor['_marca']}), "
              f"costo mediano {_usd(statistics.median(costos)) if costos else 'sin medir'} por video; "
              f"gasto de pruebas {_usd(sum(gasto_dias.values()))}.")
        fallas = Counter(f.get("id") for r in res for f in r.get("fallas") or [] if f.get("id"))
        l4 = ("Lo más flojo: " + ", ".join(f"{k} ({n})" for k, n in fallas.most_common(3))) if fallas \
            else "Lo más flojo: ninguna regla falló en las pruebas."
        pasan = {r["_marca"] for r in res if (r.get("ok") or 0) >= MINIMO_OK and float(r.get("costo") or 9) < TOPE_USD}
        marcas = {r["_marca"] for r in res}
        l5 = (f"Para el 10/12: {len(pasan)} de {len(marcas)} marcas probadas pasan {MINIMO_OK}/19 con menos de "
              f"{_usd(TOPE_USD)} (hace falta 8 de 10).")
    else:
        l3 = f"Pruebas de la semana: ninguna (gasto de pruebas {_usd(sum(gasto_dias.values()))})."
        l4 = "Lo más flojo: sin pruebas nuevas, no hay datos."
        l5 = "Para el 10/12: sin pruebas esta semana no se puede decir; hace falta 8 de 10 marcas con 15/19."
    return "\n".join([l1, l2, l3, l4, l5])


def gasto_pruebas(conn, desde: date, hasta: date) -> dict[str, float]:
    from . import claude

    out = {}
    d = desde
    while d <= hasta:
        out[d.isoformat()] = claude.gasto_pruebas_hoy(conn, d.isoformat())
        d += timedelta(days=1)
    return out


def tick(conn, avisar, raiz_repo: Path, ahora: datetime) -> bool:
    from . import db

    lunes = ahora.date().isoformat()
    if ahora.weekday() != 0 or (ahora.hour, ahora.minute) < HORA or db.get_valor(conn, ENVIADO) == lunes:
        return False
    db.set_valor(conn, ENVIADO, lunes)
    try:
        pend = (raiz_repo / "PENDIENTES.md").read_text(encoding="utf-8")
    except OSError:
        pend = ""
    hoy = ahora.date()
    res = resultados(raiz_repo / "output" / "animacion", time.time() - 7 * 86400)
    avisar(texto(hoy, pend, res, gasto_pruebas(conn, hoy - timedelta(days=7), hoy - timedelta(days=1))))
    return True
