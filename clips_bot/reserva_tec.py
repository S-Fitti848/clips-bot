"""Colchón de tecnología (Santi, 2026-11-23: "tené siempre 3 videos de tecnología ya armados, revisados y listos").

Tecnología es lo que mejor anda en YouTube (~10.000 vistas por video) y pasa a ser la prioridad número uno: 2 videos por
día (`efemerides.por_dia`). La reserva son videos YA ARMADOS de historias que no dependen de la fecha (las del banco de
tecnología, con el guion que no dice "hoy"), con la revisión del video terminado hecha. Si el del día falla, o para el
segundo del día, sale uno de la reserva; cuando baja de `efemerides.reserva` (3), se arma otro solo, de a uno, fuera de
la madrugada y con el turno pesado libre.

Estado en bot_estado:
- `reserva_tec`: [{"token", "clip_id", "titulo", "subtema", "fallas", "corregidas", "revisado", "motor", "relajado",
  "local", "costo", "armado"}], el más viejo primero. La propuesta (`efe:<token>`) y el meta (ready/) quedan guardados.
- `tec_entregados:<día>`: cuántos de tecnología se mandaron ese día (del día y de la reserva).
- `reserva_tec_fallas:<día>`: cuántas veces falló armar uno ese día (tope, para no gastar de más).
"""
from __future__ import annotations

import json
from datetime import date

from . import db

CLAVE = "reserva_tec"
ENTREGADOS = "tec_entregados:{}"
FALLAS = "reserva_tec_fallas:{}"
# Santi, 2026-11-24: "que reintente con equilibrio: máximo 5 intentos por día y nunca pasar el tope de US$ 2,50".
# Cada intento es UNA historia (con todos sus arreglos de fotos adentro); una que falla no se vuelve a intentar.
MAX_FALLAS_DIA = 5
COSTO_INTENTO = 0.35        # lo que puede costar un intento (guion + 2 búsquedas + plan B): no arranca si no entra
DESDE, HASTA = "06:30", "22:00"   # nunca en la madrugada (03:30-06:30 es de los videos del día)


def leer(conn) -> list[dict]:
    try:
        return json.loads(db.get_valor(conn, CLAVE) or "[]")
    except ValueError:
        return []


def guardar(conn, items: list[dict]) -> None:
    db.set_valor(conn, CLAVE, json.dumps(items, ensure_ascii=False))


def agregar(conn, item: dict) -> None:
    guardar(conn, leer(conn) + [item])


def sacar_primero(conn) -> dict | None:
    """El más viejo de la reserva (sale de la lista)."""
    items = leer(conn)
    if not items:
        return None
    guardar(conn, items[1:])
    return items[0]


def entregados(conn, dia: date) -> int:
    return int(db.get_valor(conn, ENTREGADOS.format(dia.isoformat())) or 0)


def contar_entregado(conn, dia: date, n: int = 1) -> None:
    db.set_valor(conn, ENTREGADOS.format(dia.isoformat()), str(entregados(conn, dia) + n))


def faltan_hoy(conn, dia: date, por_dia: int) -> int:
    return max(0, int(por_dia) - entregados(conn, dia))


def fallas_hoy(conn, dia: date) -> int:
    return int(db.get_valor(conn, FALLAS.format(dia.isoformat())) or 0)


def anotar_falla(conn, dia: date) -> None:
    db.set_valor(conn, FALLAS.format(dia.isoformat()), str(fallas_hoy(conn, dia) + 1))


PAUSA = "reserva_tec_pausa"   # bot_estado: "1" = no se arma nada (Santi, 2026-11-23: "pausá la reserva hasta el deploy")


def pausada(conn) -> bool:
    return (db.get_valor(conn, PAUSA) or "") == "1"


def entra_en_tope(conn, dia: date) -> bool:
    """¿Un intento más entra en el tope diario de producción (presupuesto.TOPE_DIA)?"""
    from . import presupuesto

    try:
        return presupuesto.gasto_hoy(conn, dia.isoformat()) + COSTO_INTENTO <= presupuesto.TOPE_DIA
    except Exception:  # noqa: BLE001 — sin gemini_uso (tests): no frena
        return True


def hay_que_armar(conn, objetivo: int, dia: date, hm: str) -> bool:
    return (not pausada(conn) and DESDE <= hm < HASTA and len(leer(conn)) < int(objetivo)
            and fallas_hoy(conn, dia) < MAX_FALLAS_DIA and entra_en_tope(conn, dia))


# ---- informe del día siguiente al cambio (Santi, 2026-11-23: "avisame cuánto mejora el % de fotos reales y cuánto
# gastó la reserva al día siguiente") -------------------------------------------------------------------------------
INFORME = "informe_fotos_pedido"     # bot_estado: el día (AR) a informar, apenas termina (22:05)
ANTES_PCT_REAL = 70                  # 17-23/11: 5 videos de tecnología, 30 % del tiempo con tarjetas (medido en la Pi)
ANTES_RESERVA_USD = 2.50             # 23/11: 6 intentos de la reserva, 3 entraron


def pct_real(cortes: list[dict]) -> float | None:
    total = sum(float(c.get("dur") or 0) for c in cortes)
    if total <= 0:
        return None
    tarjetas = sum(float(c.get("dur") or 0) for c in cortes if str(c.get("archivo") or "").startswith("tarjeta"))
    return 100 * (1 - tarjetas / total)


def informe(conn, dia: date, raiz_output) -> str:
    from pathlib import Path

    filas = conn.execute("select estado, coalesce(costo_usd, 0) from videos_registro where dia = ? and formato = "
                         "'tecnologia_reserva'", (dia.isoformat(),)).fetchall()
    gasto = sum(c for _, c in filas)
    entraron = sum(1 for e, _ in filas if e == "reserva")
    pcts = []
    for p in Path(raiz_output, "efemerides").glob(f"*/efemeride_{dia:%m%d}_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8")).get("efemeride") or {}
        except (OSError, ValueError):
            continue
        x = pct_real(d.get("cortes") or [])
        if x is not None:
            pcts.append(x)
    medio = f"{sum(pcts) / len(pcts):.0f} %" if pcts else "sin videos armados"

    def usd(x: float) -> str:
        return f"US$ {x:.2f}".replace(".", ",")

    return "\n".join([
        f"🔧 Claude Code: fotos y reserva de tecnología, {dia:%d/%m} (primer día con el chequeo previo y el plan B).",
        f"Fotos reales: {medio} del tiempo en {len(pcts)} videos (antes {ANTES_PCT_REAL} %).",
        f"Reserva: {len(filas)} intentos, {entraron} entraron, {usd(gasto)} (el 23/11: {usd(ANTES_RESERVA_USD)})."])
