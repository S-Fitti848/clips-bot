"""Santi, 2026-11-24: la Pi se colgó por calor (freno a 80 °C y pausa más larga entre renders) y el tope de US$ 2,50 por
día de producción con los recortes en orden (comunidad y web primero, después Latinoamérica a 1; tecnología nunca)."""
from __future__ import annotations

import sqlite3
import time

from clips_bot import db, freno_calor, presupuesto


def test_freno_congela_desde_80_y_suelta_debajo_de_72():
    assert freno_calor.decidir(False, 79.9) is False
    assert freno_calor.decidir(False, 80.0) is True
    assert freno_calor.decidir(True, 75.0) is True          # histéresis: sigue frenado
    assert freno_calor.decidir(True, 72.0) is False
    assert freno_calor.decidir(True, None) is False         # sin lectura no frena a ciegas


def test_anota_y_rota(tmp_path):
    r = tmp_path / "t.log"
    freno_calor.anotar("x", r)
    assert r.read_text(encoding="utf-8") == "x\n"


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table bot_estado (clave text primary key, valor text)")
    conn.execute("create table gemini_uso (dia text, funcion text, modelo text, clave text, entrada int, salida int, "
                 "origen text)")
    return conn


def test_pausa_minima_entre_renders_aunque_este_fria(monkeypatch):
    conn = _conn()
    conn.execute("create table if not exists turnos (x int)")
    monkeypatch.setattr(db, "temperatura_cpu", lambda: 45.0)
    db.set_valor(conn, db.FIN_PESADO, str(time.time() - 60))
    assert not db.tomar_turno(conn, db.RECURSO_PESADO, "a")
    db.set_valor(conn, db.FIN_PESADO, str(time.time() - db.PAUSA_MIN_S - 1))
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "a")


def test_caliente_espera_hasta_30_min(monkeypatch):
    conn = _conn()
    monkeypatch.setattr(db, "temperatura_cpu", lambda: 70.0)
    db.set_valor(conn, db.FIN_PESADO, str(time.time() - 20 * 60))
    assert not db.tomar_turno(conn, db.RECURSO_PESADO, "a")
    db.set_valor(conn, db.FIN_PESADO, str(time.time() - 31 * 60))
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "a")


def test_nivel_del_dia():
    assert presupuesto.nivel_dia(1.00) == 0
    assert presupuesto.nivel_dia(2.20) == 2                 # no entra comunidad + web
    assert presupuesto.nivel_dia(2.50) == 3                 # Latinoamérica a 1
    assert presupuesto.nivel_dia(9.99) == 3                 # nunca 4: la primera de Latinoamérica y tecnología siguen


def test_tope_cuenta_produccion_y_a_mano_pero_no_pruebas(monkeypatch):
    from clips_bot import claude

    monkeypatch.setattr(claude, "costo", lambda m, e, s: e / 1000)
    conn = _conn()
    conn.executemany("insert into gemini_uso values ('2026-11-24','f','m','claude',?,0,?)",
                     [(1500, "produccion"), (1100, "a_mano"), (5000, "prueba")])
    assert presupuesto.gasto_hoy(conn, "2026-11-24") == 2.6
    assert presupuesto.nivel_hoy(conn, "2026-11-24") == 3
    t = presupuesto.aviso_tope(conn, "2026-11-24")
    assert t and "Latinoamérica a 1" in t and "comunidad" in t and len(t.splitlines()) == 1
    assert presupuesto.aviso_tope(conn, "2026-11-24") is None   # una vez por día y nivel
