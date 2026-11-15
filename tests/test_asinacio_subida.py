"""Así Nació prendido (Santi, 2026-11-14): el video llega al privado ya programado en YouTube a las 19:00 AR
con ❌ Cancelar; el Reel de Facebook queda preparado para cuando se conecte la página."""

import json
from dataclasses import replace
from datetime import date

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


class R:
    marca, angulo, promedio, titulo = "Nerf", "origen", 8.5, "La pelota que no rompía nada"
    descripcion, hashtags, articulo = "Un juguete nacido de un problema.", ["#Shorts", "#Nerf"], "Nerf"
    credito_musica, duracion_s, video, total_s, costo_usd = "Tema X (CC BY)", 34.0, "v.mp4", 400, 0.2


def test_prendido_y_a_las_19():
    s = load_settings().animacion
    assert s.activo and s.subir and s.hora_publicacion == "19:00" and s.facebook
    assert s.chat in ("", m.DUENO)


def test_programa_youtube_y_guarda_el_meta(conn, tmp_path, monkeypatch):
    s = load_settings()
    s = replace(s, animacion=replace(s.animacion, facebook=False))
    vistos = []
    monkeypatch.setattr(m, "_programar_subida", lambda c, st, meta, canal, hora: (
        vistos.append((meta, canal, hora)), "📤 Programado en <b>Así Nació</b> para el 15/11 a las 19:00 (AR).")[1])
    avisos = m._animacion_subir(conn, s, R(), tmp_path, date(2026, 11, 15))
    meta, canal, hora = vistos[0]
    assert canal == "animacion" and hora == "19:00" and meta["clip_id"] == "asinacio_20261115"
    assert "Música: Tema X (CC BY)" in meta["textos"]["descripcion"]       # el crédito de la licencia
    assert json.loads((tmp_path / "asinacio_20261115.json").read_text(encoding="utf-8"))["salida"] == "v.mp4"
    assert avisos and avisos[0].startswith("📤")
    assert m._canal_de("asinacio_20261115", {}) == "animacion"


def test_llega_con_el_boton_de_cancelar(conn, tmp_path, monkeypatch):
    s = load_settings()
    enviados, mensajes = [], []
    from clips_bot.animacion import marcas

    monkeypatch.setattr(marcas, "armar_video", lambda *a, **k: R())
    monkeypatch.setattr(marcas, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(marcas, "enviar", lambda tg, chats, r, encabezado="", subida=False:
                        enviados.append((encabezado, subida)))
    monkeypatch.setattr(m, "_animacion_subir", lambda *a: ["📤 Programado para el 15/11 a las 19:00 (AR)."])
    monkeypatch.setattr(m, "DATA_DIR", tmp_path / "data")

    class TG:
        def send_message(self, chat, texto, teclado=None):
            mensajes.append((chat, teclado))

    m._animacion_armar(conn, TG(), [m.DUENO], s, date(2026, 11, 15))
    assert enviados[0][1] is True and "Se publica sola" in enviados[0][0]
    chat, teclado = mensajes[0]
    assert chat == m.DUENO and teclado["inline_keyboard"][0][0]["callback_data"] == "sub:x:asinacio_20261115"


def test_sin_la_pagina_de_facebook_avisa_y_no_rompe(conn, monkeypatch):
    s = load_settings()
    s = replace(s, animacion=replace(s.animacion, facebook=True))
    monkeypatch.setattr(m, "env", lambda k, requerido=True: "")
    aviso = m._subir_facebook_asinacio(conn, s, {"clip_id": "asinacio_1", "salida": "v.mp4",
                                                 "textos": {"titulo": "t", "descripcion": "d", "hashtags": []}})
    assert "ASINACIO_FACEBOOK_PAGE_ID" in aviso


def test_con_facebook_prendido_tambien_va_el_reel(conn, tmp_path, monkeypatch):
    s = load_settings()
    monkeypatch.setattr(m, "_programar_subida", lambda *a: "📤 Programado en YouTube.")
    monkeypatch.setattr(m, "_subir_facebook_asinacio", lambda c, st, meta: "📘 Programado en Facebook.")
    avisos = m._animacion_subir(conn, s, R(), tmp_path, date(2026, 11, 15))
    assert avisos == ["📤 Programado en YouTube.", "📘 Programado en Facebook."]


def test_subtitulos_virales_prendidos():
    assert load_settings().animacion.subtitulos_virales is True     # aprobados por Santi el 2026-11-14
    import inspect
    from clips_bot.animacion import marcas

    assert 'subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico"' in inspect.getsource(marcas.armar_video)
