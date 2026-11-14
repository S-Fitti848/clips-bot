"""Rots apagado (Santi, 2026-11-14: "que deje de buscar, armar y subir clips"; no se borra el código
ni el canal). Pequeña Historia no lo espera más."""

import argparse
from datetime import datetime

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_settings_tiene_rots_apagado():
    assert load_settings().publicacion.rots is False


def test_la_madrugada_no_lanza_rots_y_hace_la_de_tecnologia(conn):
    s = load_settings()
    lanzadas, efes = [], []
    m._madrugada_tick(conn, None, s, ahora=datetime(2026, 11, 14, 3, 40, tzinfo=m.AR),
                      lanzar=lambda: lanzadas.append(1), efemeride=lambda st: efes.append(1))
    assert lanzadas == [] and efes == []          # antes de efemerides.hora_propuesta (04:00)
    m._madrugada_tick(conn, None, s, ahora=datetime(2026, 11, 14, 4, 1, tzinfo=m.AR),
                      lanzar=lambda: lanzadas.append(1), efemeride=lambda st: efes.append(1))
    assert lanzadas == [] and efes == [1]         # no espera a Rots
    assert m._rots_listo(conn, datetime(2026, 11, 14, 4, 1, tzinfo=m.AR), s)


def test_el_timer_de_las_05_no_hace_nada(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(m, "_diario", lambda *a, **k: pytest.fail("no tenía que correr"))
    assert m.cmd_diario(argparse.Namespace(simular=False)) == 0
    assert "Rots está apagado" in capsys.readouterr().out


def test_pego_y_ya_no_corren(conn):
    s = load_settings()
    m._pego_tick(conn, s, ahora=datetime(2026, 11, 14, 2, 0, tzinfo=m.AR))
    assert db.get_valor(conn, m.PEGO_DIA) is None
    assert "apagado" in m._ya(conn, None, "1", s)
