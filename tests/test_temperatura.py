"""Calor de la Pi (Santi, 2026-11-14): el Fan SHIM con histéresis 55/48 °C y siempre prendido en los
renders, la pausa para enfriar entre renders y x264 con 3 hilos."""

import time

import pytest

from clips_bot import db, media, ventilador


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_ventilador_con_histeresis_y_siempre_en_render():
    d = ventilador.decidir
    assert d(False, 54.9, False) is False and d(False, 55.0, False) is True
    assert d(True, 50.0, False) is True                     # entre 48 y 55 se queda prendido
    assert d(True, 47.9, False) is False and d(False, 50.0, False) is False
    assert d(False, 30.0, True) is True                      # en un render, siempre prendido
    assert d(False, None, False) is True                     # sin sensor: prendido por las dudas


def test_el_bucle_cambia_el_pin_solo_cuando_cambia_el_estado(monkeypatch):
    llamados = []
    monkeypatch.setattr(ventilador, "temperatura", lambda: 60.0)
    monkeypatch.setattr(ventilador, "hay_render", lambda: False)
    monkeypatch.setattr(ventilador, "poner", lambda p: llamados.append(p))
    ventilador.bucle(una_vez=True)
    assert llamados == [True]


def test_pausa_para_enfriar_entre_renders(conn, monkeypatch):
    monkeypatch.setattr(db, "temperatura_cpu", lambda: 72.0)
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "a", maximo=1)        # sin render reciente: arranca
    db.soltar_turno(conn, db.RECURSO_PESADO, "a")
    assert not db.tomar_turno(conn, db.RECURSO_PESADO, "b", maximo=1)    # recién terminó y está caliente
    monkeypatch.setattr(db, "temperatura_cpu", lambda: 60.0)
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "b", maximo=1)        # ya enfrió
    db.soltar_turno(conn, db.RECURSO_PESADO, "b")
    monkeypatch.setattr(db, "temperatura_cpu", lambda: 72.0)
    db.set_valor(conn, db.FIN_PESADO, str(time.time() - db.PAUSA_MAX_S - 1))
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "c", maximo=1)        # nunca espera más de 10 min


def test_otros_turnos_no_esperan_a_que_enfrie(conn, monkeypatch):
    monkeypatch.setattr(db, "temperatura_cpu", lambda: 80.0)
    db.set_valor(conn, db.FIN_PESADO, str(time.time()))
    assert db.tomar_turno(conn, "busqueda", "x", maximo=2)


def test_x264_con_3_hilos_en_todos_los_encodes():
    assert media.X264 == ["-c:v", "libx264", "-threads", "3"]
    import pathlib
    raiz = pathlib.Path(media.__file__).parent
    sueltos = [str(p) for p in raiz.rglob("*.py")
               if '"-c:v", "libx264"' in p.read_text(encoding="utf-8") and p.name != "media.py"]
    assert sueltos == []
