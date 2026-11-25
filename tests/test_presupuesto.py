"""Saldo de Claude hasta el 14/12 (Santi, 2026-11-18): si al ritmo actual no alcanza, Así Nació baja a 1 por día."""
from datetime import date, datetime

import clips_bot.__main__ as m
from clips_bot import db, presupuesto as pr


def test_al_ritmo_actual_no_alcanza():
    hoy = date(2026, 11, 20)
    por = {"2026-11-18": 3.5, "2026-11-19": 3.5}
    uno, prom, proy = pr.evaluar(7.0, por, hoy, False)
    assert uno and prom == 3.5 and proy > pr.SALDO
    uno, *_ = pr.evaluar(4.0, {"2026-11-18": 2.0, "2026-11-19": 2.0}, hoy, False)
    assert not uno                                   # 2/día × 25 días = 54 < 70


def test_vuelve_a_dos_solo_si_con_el_segundo_alcanza():
    hoy = date(2026, 11, 25)
    por = {f"2026-11-{d}": 2.2 for d in range(18, 25)}
    assert pr.evaluar(15.4, por, hoy, True)[0]       # 2,2 + 0,9 por 20 días no entra
    por = {f"2026-11-{d}": 1.5 for d in range(18, 25)}
    assert not pr.evaluar(10.5, por, hoy, True)[0]   # 1,5 + 0,9 por 20 días = 48 + 10,5 < 70


def test_el_tick_avisa_una_linea_y_baja_a_uno(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.set_valor(c, pr.FILA, "0")
    for dia in ("2026-11-18", "2026-11-19"):
        c.execute("INSERT INTO gemini_uso (ts, dia, funcion, modelo, clave, entrada, salida) VALUES "
                  "(?, ?, 'x', 'claude-sonnet-5-5', 'claude', 600000, 250000)", (dia + "T10:00", dia))
    c.commit()
    avisos = []
    pr.tick(c, avisos.append, datetime(2026, 11, 20, 7, 0))
    assert len(avisos) == 1 and "\n" not in avisos[0] and "1 video por día" in avisos[0]
    assert db.get_valor(c, pr.UN_VIDEO) == "1"
    pr.tick(c, avisos.append, datetime(2026, 11, 20, 9, 0))      # una vez por día
    assert len(avisos) == 1


def _uso(c, dia, entrada, origen="produccion"):
    c.execute("INSERT INTO gemini_uso (ts, dia, funcion, modelo, clave, entrada, salida, origen) VALUES "
              "(?, ?, 'x', 'm', 'claude', ?, 0, ?)", (dia + "T10:00", dia, entrada, origen))
    c.commit()


def test_ritmo_de_3_dias_sin_pruebas_ni_el_23(tmp_path, monkeypatch):
    """Santi, 2026-11-25: el ritmo con los últimos 3 días, sin pruebas ni el 23/11 (reintentos ya arreglados)."""
    from clips_bot import claude

    monkeypatch.setattr(claude, "costo", lambda m, e, s: e / 1000)
    c = db.connect(tmp_path / "t.db")
    db.set_valor(c, pr.FILA, "0")
    db.set_valor(c, pr.NIVEL, "4")
    for dia, usd in (("2026-11-19", 4700), ("2026-11-20", 1300), ("2026-11-21", 2100), ("2026-11-22", 1200),
                     ("2026-11-23", 4500), ("2026-11-24", 1700)):
        _uso(c, dia, usd)
    _uso(c, "2026-11-20", 2700, "prueba")
    por = pr.gasto_produccion(c, "2026-11-18")
    assert pr.dias_ritmo(por, date(2026, 11, 25)) == ["2026-11-21", "2026-11-22", "2026-11-24"]
    avisos = []
    activos = {1: False, 2: True, 3: True, 4: True}
    pr.tick(c, avisos.append, datetime(2026, 11, 25, 7, 0), activos)
    assert pr.nivel(c) == 0 and "se deshace" in avisos[0] and "Latinoamérica" in avisos[0]


def test_recorta_de_a_un_escalon_y_saltea_lo_apagado():
    activos = {1: False}
    assert pr.un_escalon(0, 4, activos) == 2       # Así Nació ya está pausado: el primero es comunidad y web
    assert pr.un_escalon(2, 4, activos) == 3
    assert pr.un_escalon(3, 4, activos) == 4
    assert pr.un_escalon(4, 1, activos) == 1       # devolver, directo
    assert pr.un_escalon(0, 3) == 1
