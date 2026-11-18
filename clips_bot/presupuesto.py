"""Control del saldo de Claude (Santi, 2026-11-18): quedan unos US$ 70 hasta el 14/12. Cada día se calcula el gasto
promedio y, si al ritmo actual no se llega al 14/12, Así Nació baja solo a 1 video por día hasta que alcance; vuelve a 2
cuando, con el video de más, igual alcanza. Cada cambio se avisa en una línea.

El gasto se cuenta desde la fila de gemini_uso en que se arrancó (`bot_estado.presupuesto_fila`), así lo gastado antes
de que Santi diera el saldo no cuenta dos veces.
"""
from __future__ import annotations

from datetime import date, datetime

SALDO = 70.0
DESDE = date(2026, 11, 18)
HASTA = date(2026, 12, 14)          # inclusive
COSTO_VIDEO_AN = 0.90               # lo que suma por día el segundo video de Así Nació (estimado, debajo del tope de 1,20)
FILA = "presupuesto_fila"
DIA = "presupuesto_dia"
UN_VIDEO = "asinacio_un_video"     # "1" = Así Nació a 1 por día por el presupuesto


def gasto_desde(conn, fila: int) -> tuple[float, dict[str, float]]:
    """(total, {día: US$}) de Claude (con las búsquedas web) después de la fila `fila`."""
    from . import claude

    por_dia: dict[str, float] = {}
    for dia, modelo, e, s in conn.execute(
            "SELECT dia, modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND rowid > ?", (fila,)):
        por_dia[dia] = por_dia.get(dia, 0.0) + claude.costo(modelo, e or 0, s or 0)
    return round(sum(por_dia.values()), 2), por_dia


def evaluar(gastado: float, por_dia: dict[str, float], hoy: date, reducido: bool) -> tuple[bool, float, float]:
    """(¿1 video por día?, promedio por día, proyección al 14/12). El promedio es el de los días completos desde el
    arranque (los últimos 7 como mucho); el primer día, lo de hoy."""
    completos = sorted(d for d in por_dia if d < hoy.isoformat())[-7:]
    if completos:
        promedio = sum(por_dia[d] for d in completos) / len(completos)
    else:
        promedio = por_dia.get(hoy.isoformat(), 0.0)
    hoy_ya = por_dia.get(hoy.isoformat(), 0.0)
    dias = max(0, (HASTA - hoy).days + 1)          # hoy incluido
    proyeccion = gastado - hoy_ya + promedio * dias
    if not reducido:
        return proyeccion > SALDO, round(promedio, 2), round(proyeccion, 2)
    # ya en 1 por día: vuelve a 2 solo si, sumando el segundo video, igual alcanza
    con_dos = gastado - hoy_ya + (promedio + COSTO_VIDEO_AN) * dias
    return con_dos > SALDO, round(promedio, 2), round(proyeccion, 2)


def tick(conn, avisar, ahora: datetime) -> None:
    """Una vez por día (desde las 06:30, antes de Así Nació): recalcula y, si cambia, avisa en una línea."""
    from . import db

    hoy = ahora.date()
    if hoy > HASTA or ahora.strftime("%H:%M") < "06:30" or db.get_valor(conn, DIA) == hoy.isoformat():
        return
    db.set_valor(conn, DIA, hoy.isoformat())
    arrancar(conn)
    fila = db.get_valor(conn, FILA)
    gastado, por_dia = gasto_desde(conn, int(fila))
    antes = db.get_valor(conn, UN_VIDEO) == "1"
    uno, promedio, proy = evaluar(gastado, por_dia, hoy, antes)
    queda = SALDO - gastado
    if uno != antes:
        db.set_valor(conn, UN_VIDEO, "1" if uno else "0")
        if uno:
            avisar(f"🔧 Claude Code: 💸 a US$ {_f(promedio)}/día no llegamos al 14/12 (quedan US$ {_f(queda)}): "
                   "Así Nació baja a 1 video por día.")
        else:
            avisar(f"🔧 Claude Code: 💸 ahora alcanza (quedan US$ {_f(queda)}, US$ {_f(promedio)}/día): Así Nació "
                   "vuelve a 2 por día.")


def _f(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def arrancar(conn) -> None:
    """Marca desde dónde se cuenta el saldo (la última fila de gemini_uso de ahora)."""
    from . import db

    if db.get_valor(conn, FILA) is None:
        n = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM gemini_uso").fetchone()[0]
        db.set_valor(conn, FILA, str(int(n)))
