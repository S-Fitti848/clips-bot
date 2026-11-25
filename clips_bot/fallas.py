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


# ---- al primer intento (Santi, 2026-11-25: "que los videos salgan bien al primer intento"; el informe de las 09:00
# lleva "% al primer intento" y "gastado en reintentos") ----------------------------------------------------------
FORMATOS_PH = {"tecnologia": "tecnología", "latinoamerica": "Latinoamérica", "tecnologia_reserva": "reserva"}
LLEGARON = ("retenido", "programado", "entregado", "publicado", "reserva")


def primer_intento(conn, desde: str, hasta: str | None = None) -> dict:
    """{formato: {"videos", "caidas", "costo"}} de Pequeña Historia entre `desde` y `hasta` (AR, inclusive). Una
    historia caída = una que pasó el puntaje y no llegó a video (cada candidato una vez, aunque tenga varias filas);
    `costo`, lo que se gastó en Claude en las caídas."""
    hasta = hasta or desde
    out = {f: {"videos": 0, "caidas": 0, "costo": 0.0} for f in FORMATOS_PH}
    q = ",".join("?" * len(FORMATOS_PH))
    for formato, n in conn.execute(
            f"SELECT formato, COUNT(*) FROM videos_registro WHERE canal = 'pequena_historia' AND dia BETWEEN ? AND ? "
            f"AND formato IN ({q}) AND estado IN ({','.join('?' * len(LLEGARON))}) GROUP BY formato",
            (desde, hasta, *FORMATOS_PH, *LLEGARON)):
        out[formato]["videos"] = n
    for formato, n, costo in conn.execute(
            f"SELECT formato, COUNT(DISTINCT candidato), COALESCE(SUM(costo_usd), 0) FROM candidatos_descartados "
            f"WHERE dia BETWEEN ? AND ? AND formato IN ({q}) AND paso NOT IN ('puntaje') GROUP BY formato",
            (desde, hasta, *FORMATOS_PH)):
        out[formato]["caidas"] = n
        out[formato]["costo"] += float(costo or 0)
    # los de la reserva que se armaron enteros y no pasaron el estándar: su costo está en la bitácora del video
    for formato, costo in conn.execute(
            f"SELECT formato, COALESCE(SUM(costo_usd), 0) FROM videos_registro WHERE canal = 'pequena_historia' "
            f"AND dia BETWEEN ? AND ? AND formato IN ({q}) AND estado = 'descartado' GROUP BY formato",
            (desde, hasta, *FORMATOS_PH)):
        out[formato]["costo"] += float(costo or 0)
    return out


def lineas_informe(conn, dia: str, total_usd: float) -> list[str]:
    """Las dos líneas del informe de las 09:00."""
    d = primer_intento(conn, dia)
    v = sum(x["videos"] for x in d.values())
    c = sum(x["caidas"] for x in d.values())
    pct = f"{round(100 * v / (v + c))} %" if v + c else "sin historias"
    partes = " · ".join(f"{FORMATOS_PH[f]} {x['videos']}/{x['videos'] + x['caidas']}" for f, x in d.items()
                        if x["videos"] + x["caidas"])
    gastado = sum(x["costo"] for x in d.values())
    return [f"Al primer intento: {pct}" + (f" ({partes})" if partes else ""),
            f"Gastado en reintentos: {_usd(gastado)} de {_usd(total_usd)}"]
