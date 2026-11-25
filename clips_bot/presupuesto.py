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
# Tecnología va primero (Santi, 2026-11-23): si el saldo no alcanza, se recorta TODO lo demás antes, en este orden, y
# tecnología (los 2 por día y su reserva) nunca. Cada nivel incluye los anteriores; el ahorro es por día, estimado.
NIVEL = "presupuesto_nivel"        # bot_estado: 0 = nada recortado
RECORTES = ((1, "Así Nació a 1 video por día", 0.90),
            (2, "sin publicación de comunidad ni búsqueda web de Latinoamérica", 0.35),
            (3, "Latinoamérica a 1 por día", 0.40),
            (4, "sin Latinoamérica", 0.40))


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


def _ahorro(hasta: int, activos: dict | None = None) -> float:
    return sum(a for n, _, a in RECORTES if n <= hasta and (activos or {}).get(n, True))


# El ritmo (Santi, 2026-11-25: "recortaste Latinoamérica entero por un ritmo de US$ 2,93/día, pero ayer gastaste ~US$ 1"):
# los últimos 3 días completos de PRODUCCIÓN (sin pruebas) y sin los días de reintentos que ya se arreglaron. Se recorta
# de a un escalón por día y, si el ritmo baja, se devuelve lo recortado.
DIAS_RITMO = 3
DIAS_NO_CUENTAN = {"2026-11-23"}   # la reserva reintentó 30 veces las mismas historias (arreglado en v1.52.0/v1.54.0)
NIVELES_DIA = "presupuesto_niveles"    # bot_estado: {día: nivel con el que corrió}, para sumarle lo que se ahorró


def gasto_produccion(conn, desde_dia: str) -> dict[str, float]:
    """{día: US$} de Claude sin las pruebas (producción y lo que se arma a mano con un ✅)."""
    from . import claude

    por: dict[str, float] = {}
    for dia, modelo, e, s in conn.execute(
            "SELECT dia, modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND dia >= ? "
            "AND COALESCE(origen, '') != 'prueba'", (desde_dia,)):
        por[dia] = por.get(dia, 0.0) + claude.costo(modelo, e or 0, s or 0)
    return por


def dias_ritmo(por_dia: dict[str, float], hoy: date) -> list[str]:
    return [d for d in sorted(por_dia) if d < hoy.isoformat() and d not in DIAS_NO_CUENTAN][-DIAS_RITMO:]


def nivel_necesario(gastado: float, por_dia: dict[str, float], hoy: date, actual: int,
                    activos: dict | None = None, niveles: dict | None = None) -> tuple[int, float]:
    """(nivel de recorte que hace falta para llegar al 14/12, ritmo por día). El ritmo sale de `dias_ritmo`; a cada día
    se le suma lo que ahorró el recorte con el que corrió (`niveles` {día: nivel}; sin el dato, `actual`), así recortar
    y volver no oscila. `activos` {nivel: bool}: un recorte de algo que ya está apagado (Así Nació pausado) no ahorra."""
    dias = dias_ritmo(por_dia, hoy)
    if dias:
        sin_recorte = sum(por_dia[d] + _ahorro((niveles or {}).get(d, 0), activos) for d in dias) / len(dias)
    else:
        sin_recorte = por_dia.get(hoy.isoformat(), 0.0) + _ahorro(actual, activos)
    hoy_ya = por_dia.get(hoy.isoformat(), 0.0)
    restan = max(0, (HASTA - hoy).days + 1)
    for n in range(0, len(RECORTES) + 1):
        if gastado - hoy_ya + max(0.0, sin_recorte - _ahorro(n, activos)) * restan <= SALDO:
            return n, round(sin_recorte - _ahorro(actual, activos), 2)
    return len(RECORTES), round(sin_recorte - _ahorro(actual, activos), 2)


def un_escalon(antes: int, objetivo: int, activos: dict | None = None) -> int:
    """Subir de a un escalón (saltando los que no ahorran nada porque eso ya está apagado); bajar, directo."""
    if objetivo <= antes:
        return objetivo
    for n in range(antes + 1, len(RECORTES) + 1):
        if (activos or {}).get(n, True) or n == objetivo:
            return n
    return objetivo


# Tope diario (Santi, 2026-11-24: "el 23/11 Claude gastó US$ 4,52; me quedan ~US$ 2,50 por día"): lo que se gasta HOY en
# producción (todo menos las pruebas: lo que el bot hace solo y lo que arma un ✅) no pasa de US$ 2,50. Al acercarse se
# recorta en el orden de RECORTES (comunidad y búsqueda web primero, después Latinoamérica a 1); tecnología nunca.
TOPE_DIA = 2.50
TOPE_AVISADO = "presupuesto_tope_dia"   # bot_estado: el día en que ya se avisó


def gasto_hoy(conn, dia: str) -> float:
    from . import claude

    filas = conn.execute("SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND dia = ? "
                         "AND COALESCE(origen, '') != 'prueba'", (dia,)).fetchall()
    return round(sum(claude.costo(m, e or 0, s or 0) for m, e, s in filas), 4)


def nivel_dia(gastado_hoy: float) -> int:
    """El recorte que pide el tope del día: con lo que queda no entra la comunidad + la búsqueda web → 2; llegado el
    tope → 3 (Latinoamérica a 1 por día: si ya salió una, no sale otra). Nunca 4: tecnología y la primera de
    Latinoamérica del día no se tocan."""
    if gastado_hoy >= TOPE_DIA:
        return 3
    if gastado_hoy + RECORTES[1][2] > TOPE_DIA:
        return 2
    return 0


def nivel_hoy(conn, dia: str) -> int:
    """El recorte vigente hoy: el mayor entre el del saldo hasta el 14/12 y el del tope diario."""
    try:
        d = nivel_dia(gasto_hoy(conn, dia))
    except Exception:          # sin gemini_uso (tests): solo el del saldo
        d = 0
    return max(nivel(conn), d)


def aviso_tope(conn, dia: str) -> str | None:
    """Una línea, una vez por día, cuando el tope diario empieza a recortar algo."""
    from . import db

    g = gasto_hoy(conn, dia)
    n = nivel_dia(g)
    if n == 0 or db.get_valor(conn, TOPE_AVISADO) == f"{dia}:{n}":
        return None
    db.set_valor(conn, TOPE_AVISADO, f"{dia}:{n}")
    que = "; ".join(t for k, t, _ in RECORTES if 2 <= k <= n)
    return (f"🔧 Claude Code: 💸 hoy van US$ {_f(g)} de US$ {_f(TOPE_DIA)}: {que} hasta mañana. "
            "Tecnología sigue igual.")


def nivel(conn) -> int:
    """El recorte vigente (0 = nada)."""
    from . import db

    try:
        return int(db.get_valor(conn, NIVEL) or 0)
    except ValueError:
        return 0


def tick(conn, avisar, ahora: datetime, activos: dict | None = None, forzar: bool = False) -> None:
    """Una vez por día (desde las 06:30, antes de Así Nació): recalcula y, si cambia, avisa en una línea."""
    import json

    from . import db

    hoy = ahora.date()
    if hoy > HASTA or (not forzar and (ahora.strftime("%H:%M") < "06:30"
                                       or db.get_valor(conn, DIA) == hoy.isoformat())):
        return
    db.set_valor(conn, DIA, hoy.isoformat())
    arrancar(conn)
    fila = db.get_valor(conn, FILA)
    gastado, _ = gasto_desde(conn, int(fila))      # el saldo: todo lo gastado, pruebas incluidas (es plata de verdad)
    por_dia = gasto_produccion(conn, DESDE.isoformat())
    antes = nivel(conn)
    if antes == 0 and db.get_valor(conn, UN_VIDEO) == "1" and (activos or {}).get(1, True):
        antes = 1                                   # el estado de antes del 23/11
    try:
        niveles = json.loads(db.get_valor(conn, NIVELES_DIA) or "{}")
    except ValueError:
        niveles = {}
    objetivo, promedio = nivel_necesario(gastado, por_dia, hoy, antes, activos, niveles)
    nuevo = un_escalon(antes, objetivo, activos)
    niveles[hoy.isoformat()] = nuevo
    db.set_valor(conn, NIVELES_DIA, json.dumps(dict(sorted(niveles.items())[-30:])))
    queda = SALDO - gastado
    db.set_valor(conn, UN_VIDEO, "1" if nuevo >= 1 else "0")
    if nuevo == antes:
        return
    db.set_valor(conn, NIVEL, str(nuevo))
    if nuevo > antes:
        recorte = "; ".join(t for n, t, _ in RECORTES if antes < n <= nuevo and (activos or {}).get(n, True))
        avisar(f"🔧 Claude Code: 💸 a US$ {_f(promedio)}/día no llegamos al 14/12 (quedan US$ {_f(queda)}): {recorte}. "
               "Tecnología sigue igual.")
    else:
        vuelve = "; ".join(t for n, t, _ in RECORTES if nuevo < n <= antes and (activos or {}).get(n, True))
        avisar(f"🔧 Claude Code: 💸 ahora alcanza (quedan US$ {_f(queda)}, US$ {_f(promedio)}/día): se deshace "
               f"«{vuelve}».")


def _f(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def arrancar(conn) -> None:
    """Marca desde dónde se cuenta el saldo (la última fila de gemini_uso de ahora)."""
    from . import db

    if db.get_valor(conn, FILA) is None:
        n = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM gemini_uso").fetchone()[0]
        db.set_valor(conn, FILA, str(int(n)))
