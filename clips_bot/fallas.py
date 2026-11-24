"""Resumen de los motivos de falla de la semana (Santi, 2026-11-24: "el viernes, un resumen de los motivos de falla de
la semana, para ver qué conviene mejorar").

Sale de `candidatos_descartados` (bitacora.py): cada historia o marca que se cayó antes de armar el video, con el paso
(fotos, guion, verificación, voz, render…), el motivo, lo que costó en Claude y, desde el 2026-11-24, qué se intentó para
arreglarla (`detalle.intentos`). Los que solo no llegaron al puntaje no cuentan como fallas (no se gastó nada en ellos).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, timedelta

ENVIADO = "fallas_semana_enviado"     # bot_estado: el viernes (AR) en que ya salió
DIA_SEMANA = 4                        # viernes
HORA = "10:00"
NO_ES_FALLA = ("puntaje",)


def tipo(motivo: str) -> str:
    """El motivo sin los números ni lo propio de cada historia, para agrupar: «solo 57 % del tiempo con fotos reales
    (mínimo 70 %)» y «solo 40 % …» son el mismo."""
    t = str(motivo or "").split(":")[0] if motivo.startswith(("El guion no pasó", "no verificada")) else str(motivo or "")
    t = re.sub(r"\d+([.,]\d+)?", "N", t)
    t = re.sub(r"«[^»]*»", "«…»", t)
    return " ".join(t.split())[:110]


def de_la_semana(conn, hasta: date) -> list[dict]:
    desde = (hasta - timedelta(days=6)).isoformat()
    filas = conn.execute(
        "SELECT dia, formato, candidato, paso, motivo, COALESCE(costo_usd, 0), COALESCE(detalle, '{}') "
        "FROM candidatos_descartados WHERE dia BETWEEN ? AND ? ORDER BY n", (desde, hasta.isoformat())).fetchall()
    out = []
    for dia, formato, cand, paso, motivo, costo, det in filas:
        if paso in NO_ES_FALLA:
            continue
        try:
            d = json.loads(det or "{}")
        except ValueError:
            d = {}
        out.append({"dia": dia, "formato": formato, "candidato": cand, "paso": paso, "motivo": motivo or "",
                    "costo": float(costo or 0), "intentos": d.get("intentos") or []})
    return out


def _usd(x: float) -> str:
    return f"US$ {x:.2f}".replace(".", ",")


def resumen(conn, hasta: date) -> str:
    """Las 3 primeras líneas van en el mensaje; el resto, detrás de 📋 Detalle (aviso_corto)."""
    fallas = de_la_semana(conn, hasta)
    desde = hasta - timedelta(days=6)
    cab = f"🔧 Claude Code: fallas del {desde:%d/%m} al {hasta:%d/%m}"
    if not fallas:
        return cab + ": ninguna historia se cayó después del puntaje."
    grupos: dict = defaultdict(lambda: {"n": 0, "costo": 0.0, "ej": [], "arreglados": 0})
    por_paso: dict = defaultdict(lambda: [0, 0.0])
    for f in fallas:
        g = grupos[(f["paso"], tipo(f["motivo"]))]
        g["n"] += 1
        g["costo"] += f["costo"]
        if len(g["ej"]) < 3:
            g["ej"].append(f["candidato"][:50])
        if len(f["intentos"]) > 1:
            g["arreglados"] += 1
        por_paso[f["paso"]][0] += 1
        por_paso[f["paso"]][1] += f["costo"]
    total = sum(f["costo"] for f in fallas)
    orden = sorted(grupos.items(), key=lambda kv: (-kv[1]["costo"], -kv[1]["n"]))
    (paso1, mot1), g1 = orden[0]
    lineas = [
        f"{cab}: {len(fallas)} historias caídas, {_usd(total)} de Claude perdidos.",
        f"Lo que más cuesta: {paso1} · «{mot1}» ({g1['n']} veces, {_usd(g1['costo'])}).",
        "Por paso: " + " · ".join(f"{p} {n} ({_usd(c)})" for p, (n, c) in
                                  sorted(por_paso.items(), key=lambda kv: -kv[1][1])) + ".",
        "",
        "Todos los motivos (veces · Claude · con arreglos intentados · ejemplos):",
    ]
    for (paso_, mot), g in orden[:12]:
        lineas.append(f"• {paso_} · {mot}: {g['n']} · {_usd(g['costo'])} · {g['arreglados']} con arreglos · "
                      + "; ".join(g["ej"]))
    con_intentos = [f for f in fallas if f["intentos"]][-5:]
    if con_intentos:
        lineas += ["", "Qué se intentó en las últimas:"]
        for f in con_intentos:
            lineas.append(f"• {f['candidato'][:60]}: " + " → ".join(str(x)[:120] for x in f["intentos"]))
    return "\n".join(lineas)


def toca(hoy: date, hm: str, enviado: str | None) -> bool:
    return hoy.weekday() == DIA_SEMANA and hm >= HORA and enviado != hoy.isoformat()
