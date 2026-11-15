"""Bitácora de cada video (Santi, 2026-11-15): costo de Claude por paso, voces, tiempos, calor, fallas;
/costos y el resumen de los lunes. Mismo formato que Lo Encontré."""

import json
import sqlite3
import time
from datetime import datetime

import pytest

from clips_bot import bitacora, claude, db
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _uso(conn, funcion, modelo, entrada, salida, clave="claude"):
    db.anotar_gemini(conn, funcion, modelo, clave, entrada, salida, origen="produccion")


def test_un_video_queda_registrado_con_sus_pasos(conn, monkeypatch):
    monkeypatch.setattr(bitacora._Muestreo, "run", lambda self: None)
    _uso(conn, "marcas.elegir", claude.HAIKU, 10000, 1000)            # de otro video: no cuenta
    bitacora.abrir(conn, "asinacio_20261116", "asinacio", "marcas")
    bitacora.paso("busqueda")
    _uso(conn, "marcas.elegir", claude.HAIKU, 20000, 2000)
    bitacora.paso("guion")
    _uso(conn, "marcas.escribir_guion", claude.SONNET, 9000, 12000)
    _uso(conn, "correcciones.corregir", claude.SONNET, 15000, 3000)
    _uso(conn, "correcciones.corregir", claude.SONNET, 15000, 3000)
    time.sleep(0.02)
    bitacora.paso("voz")
    _uso(conn, "efemerides.voz_efemeride", "gemini-2.5-flash-preview-tts", 1000, 0, clave="principal")
    _uso(conn, "efemerides.voz_efemeride", "gemini-2.5-flash-preview-tts", 1000, 0, clave="principal")
    bitacora.paso("render")
    bitacora.dato(clip_id="asinacio_20261116", titulo="Así nació el cubo")
    bitacora.cerrar(conn, "programado")
    d = bitacora.leer(conn, "2000-01-01")[0]
    pasos = {(x["paso"], x["modelo"]): x for x in d["detalle"]["claude"]}
    assert pasos[("correccion", claude.SONNET)]["intentos"] == 2
    assert pasos[("elegir", claude.HAIKU)]["intentos"] == 1               # solo la de ESTE video
    assert d["detalle"]["voces"] == {"n": 2, "reintentos": 1, "claves": {"principal": 2}}
    assert set(d["detalle"]["etapas"]) == {"busqueda", "guion", "voz", "render"}
    assert d["estado"] == "programado" and d["costo_usd"] > 0 and d["titulo"] == "Así nació el cubo"


def test_falla_y_estado_final_desde_las_subidas(conn, monkeypatch):
    monkeypatch.setattr(bitacora._Muestreo, "run", lambda self: None)
    bitacora.abrir(conn, "tok1", "pequena_historia", "tecnologia")
    bitacora.paso("fotos")
    bitacora.fallo("", "no hay fotos reales")
    bitacora.cerrar(conn, "fallido")
    bitacora.abrir(conn, "tok2", "pequena_historia", "latinoamerica")
    bitacora.dato(clip_id="efemeride_x")
    bitacora.cerrar(conn, "programado")
    db.crear_subida(conn, "efemeride_x", "pequena_historia", "cancelada")
    filas = {f["id"]: f for f in bitacora.leer(conn, "2000-01-01")}
    assert filas["tok1"]["fallo_paso"] == "fotos" and filas["tok1"]["estado"] == "fallido"
    assert filas["tok2"]["estado"] == "cancelado"


def test_retomar_suma_el_tramo_del_ok(conn, monkeypatch):
    monkeypatch.setattr(bitacora._Muestreo, "run", lambda self: None)
    bitacora.abrir(conn, "tok", "pequena_historia", "tecnologia")
    _uso(conn, "efemerides.escribir_guion", claude.SONNET, 8000, 4000)
    bitacora.cerrar(conn, "propuesto")
    _uso(conn, "otra.cosa", claude.SONNET, 99999, 99999)                # entre tramos: no cuenta
    assert bitacora.retomar(conn, "tok")
    _uso(conn, "efemerides.acortar_guion", claude.SONNET, 3000, 1000)
    bitacora.cerrar(conn, "entregado")
    d = bitacora.leer(conn, "2000-01-01")[0]
    assert sum(x["intentos"] for x in d["detalle"]["claude"]) == 2 and len(d["detalle"]["tramos"]) == 2


def test_costos_lee_lo_encontre_con_el_mismo_formato(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(bitacora._Muestreo, "run", lambda self: None)
    bitacora.abrir(conn, "a1", "asinacio", "marcas")
    _uso(conn, "marcas.escribir_guion", claude.SONNET, 9000, 12000)
    bitacora.paso("render")
    bitacora.cerrar(conn, "programado")
    otra = tmp_path / "bot2.db"
    c2 = sqlite3.connect(otra)
    c2.execute(bitacora.TABLA)
    c2.execute("INSERT INTO videos_registro (id, bot, canal, formato, dia, inicio, total_s, estado, costo_usd, detalle) "
               "VALUES ('v9', 'lo_encontre', 'lo_encontre', 'producto', ?, 'x', 300, 'publicado', 0.2, ?)",
               (conn.execute("SELECT dia FROM videos_registro").fetchone()[0],
                json.dumps({"etapas": {"render": 250, "guion": 40}, "claude": [{"paso": "guion", "modelo": "s",
                                                                              "intentos": 1, "usd": 0.2}]})))
    c2.commit()
    c2.close()
    filas = bitacora.leer(conn, "2000-01-01", [str(otra)])
    texto = bitacora.texto(filas)
    assert "Así Nació · marcas" in texto and "Lo Encontré · producto" in texto and "más caras" in texto
    assert bitacora.ideas(filas)


def test_resumen_de_los_lunes_una_vez(conn, monkeypatch):
    import clips_bot.__main__ as m

    monkeypatch.setattr(bitacora._Muestreo, "run", lambda self: None)
    bitacora.abrir(conn, "a1", "asinacio", "marcas")
    bitacora.cerrar(conn, "programado")
    conn.execute("UPDATE videos_registro SET dia = '2026-11-18'")
    conn.commit()

    class TG:
        m = []

        def send_message(self, chat, texto, **k):
            self.m.append(texto)

    tg, s = TG(), load_settings()
    m._costos_semana_tick(conn, tg, s, ahora=datetime(2026, 11, 22, 10, 0, tzinfo=m.AR))   # domingo
    m._costos_semana_tick(conn, tg, s, ahora=datetime(2026, 11, 23, 8, 0, tzinfo=m.AR))    # lunes temprano
    assert tg.m == []
    m._costos_semana_tick(conn, tg, s, ahora=datetime(2026, 11, 23, 9, 30, tzinfo=m.AR))
    m._costos_semana_tick(conn, tg, s, ahora=datetime(2026, 11, 23, 11, 0, tzinfo=m.AR))
    assert len(tg.m) == 1 and "Resumen de la semana" in tg.m[0] and "Ideas" in tg.m[0]


def test_paso_de_cada_funcion():
    assert bitacora.paso_de("correcciones.corregir") == "correccion"
    assert bitacora.paso_de("marcas.escribir_guion") == "guion"
    assert bitacora.paso_de("efemerides.pedir") == "fotos"
    assert bitacora.paso_de("locales.clasificar") == "elegir"
    assert bitacora.paso_de("marcas.revisar_visual") == "revision_visual"
    assert bitacora.paso_de("efemerides.final_que_paga") == "final"
