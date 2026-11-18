"""Prueba de horarios de Así Nació (Santi, 2026-11-18): 12:30 y 18:00 del 19/11 al 02/12, y la comparación de los lunes."""
import dataclasses
import json
from datetime import date, datetime

import pytest

import clips_bot.__main__ as m
from clips_bot import aprendizaje, db, horarios_an as ha
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_horarios_de_la_prueba_solo_esas_dos_semanas():
    s = load_settings()
    assert m.horas_asinacio(s, date(2026, 11, 18)) == ["13:00", "20:00"]
    assert m.horas_asinacio(s, date(2026, 11, 19)) == ["12:30", "18:00"]
    assert m.horas_asinacio(s, date(2026, 12, 2)) == ["12:30", "18:00"]
    assert m.horas_asinacio(s, date(2026, 12, 3)) == ["13:00", "20:00"]
    sin = dataclasses.replace(s, animacion=dataclasses.replace(s.animacion, horas_prueba=()))
    assert m.horas_asinacio(sin, date(2026, 11, 20)) == ["13:00", "20:00"]


def test_el_meta_lleva_la_hora_de_la_prueba(tmp_path):
    r = type("R", (), {"descripcion": "d", "articulo": "a", "credito_musica": "", "video": "v.mp4", "duracion_s": 34,
                       "titulo": "t", "hashtags": [], "marca": "x", "angulo": "y"})()
    meta = m._animacion_meta(load_settings(), r, tmp_path, date(2026, 11, 20), 1)
    assert meta["hora"] == "18:00"


def test_turno_mas_cercano():
    assert ha.turno_de("13:19") == ("mediodía", "13:00")
    assert ha.turno_de("12:30") == ("mediodía", "12:30")
    assert ha.turno_de("18:05") == ("tarde", "18:00")
    assert ha.turno_de("20:00") == ("tarde", "20:00")


def test_compara_vistas_por_horario(conn):
    # 13:00 AR = 16:00Z, 12:30 = 15:30Z, 20:00 = 23:00Z, 18:00 = 21:00Z
    for i, (canal, vid, iso) in enumerate([
            ("animacion", "y1", "2026-11-17T16:00:00Z"), ("animacion", "y2", "2026-11-17T23:00:00Z"),
            ("animacion", "y3", "2026-11-20T15:30:00Z"), ("animacion", "y4", "2026-11-20T21:00:00Z"),
            ("facebook_asinacio", "f1", "2026-11-17T16:00:00Z"), ("facebook_asinacio", "f3", "2026-11-20T15:30:00Z")]):
        db.crear_subida(conn, f"asinacio_{i}", canal, "programada", video_id=vid, publish_at=iso)

    class Cli:
        pedidos = 0

        def _analytics(self, p):
            Cli.pedidos += 1
            return [[p["startDate"], {"y1": 100, "y2": 50, "y3": 300, "y4": 80}[p["filters"][7:]]], ["x", 10]]

    fb = {"f1": {"vistas": 200}, "f3": {"vistas": 400}}
    texto = ha.resumen(conn, Cli(), fb, datetime(2026, 11, 24, 10, 0, tzinfo=m.AR))
    assert "12:30 310/400 (1) contra 13:00 110/200 (1)" in texto
    assert "18:00 90/— (1) contra 20:00 60/— (1)" in texto
    assert Cli.pedidos == 4
    ha.resumen(conn, Cli(), fb, datetime(2026, 11, 24, 10, 0, tzinfo=m.AR))
    assert Cli.pedidos == 4                     # las ya pedidas salen de bot_estado
    assert json.loads(db.get_valor(conn, ha.YT_2DIAS))["y3"] == 310


def test_un_video_de_hace_menos_de_3_dias_no_se_mide(conn):
    db.crear_subida(conn, "asinacio_x", "animacion", "programada", video_id="y9", publish_at="2026-11-23T15:30:00Z")

    class Cli:
        def _analytics(self, p):
            raise AssertionError("no tenía que pedir")

    assert ha.resumen(conn, Cli(), {}, datetime(2026, 11, 24, 10, 0, tzinfo=m.AR)) == ""


def test_resumen_semanal_con_la_linea_de_horarios():
    txt = aprendizaje.resumen_semana({}, [], datetime(2026, 11, 23, 10, 0), "Horarios de Así Nació: x.")
    assert txt.splitlines()[-1] == "Horarios de Así Nació: x." and len(txt.splitlines()) <= 5
