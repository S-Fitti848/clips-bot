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
