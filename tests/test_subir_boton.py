"""La subida separada del voto (2026-09-30): 👍/👎 solo votan; "📤 Subir" / "🚫 No subir" aparte."""

import json
from dataclasses import replace

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import load_settings
from clips_bot.telegram import fila_subida, teclado_voto

SLUG = "AstuteSneakyGerbilPeteZaroll-pLMSrT0PRz0zgzuv"


def test_los_botones_entran_en_64_bytes_y_cambian_con_el_estado():
    for estado in ("", "no", "18:00"):
        for fila in fila_subida(SLUG, estado):
            for b in fila:
                assert len(b["callback_data"].encode()) <= 64
    assert [b["text"] for b in fila_subida(SLUG, "")[0]] == ["📤 Subir", "🚫 No subir"]
    assert [b["text"] for b in fila_subida(SLUG, "18:00")[0]] == ["📤 Programado para las 18:00", "❌ Cancelar"]
    assert fila_subida(SLUG, None) == []
    t = teclado_voto(SLUG, 1, subida="")
    assert t["inline_keyboard"][0][0]["text"] == "👍 ✓" and t["inline_keyboard"][-1][0]["text"] == "📤 Subir"


def test_canal_y_estado(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert m._canal_de(SLUG, {"plataforma": "twitch"}) == "rots"
    assert m._canal_de("efemeride_1004_1957", {}) == "pequena_historia"
    assert m._canal_de("propio_x", {"plataforma": "aporte"}) is None
    assert m._estado_subida(conn, SLUG, {"plataforma": "twitch"}) == ""
    db.crear_subida(conn, SLUG, "rots", "programada", video_id="v", publish_at="2026-10-01T21:00:00Z")
    assert m._estado_subida(conn, SLUG, {"plataforma": "twitch"}) == "18:00"      # hora AR


class TG:
    def __init__(self):
        self.respuestas, self.teclados, self.mensajes = [], [], []

    def answer_callback(self, cid, texto="", alerta=False):
        self.respuestas.append((texto, alerta))

    def edit_reply_markup(self, chat, msg, teclado):
        self.teclados.append(teclado)

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append(texto)


def _cb(data):
    return {"data": data, "chat_id": "1", "message_id": 5, "callback_id": "q", "user_id": "7"}


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(m, "_meta_de", lambda cid: {"clip_id": cid, "plataforma": "twitch",
                                                   "entregado": {"horario": "18:00"}, "textos": {}})
    return conn


def test_con_la_subida_apagada_el_boton_lo_dice(entorno):
    tg = TG()
    s = replace(load_settings(), youtube_upload_enabled=False)
    m._subidas_callback(entorno, tg, _cb(f"sub:u:{SLUG}"), s)
    assert tg.respuestas == [(m.APAGADA, True)]


def test_subir_programa_y_el_boton_pasa_a_programado_y_se_cancela(entorno, monkeypatch):
    tg = TG()
    s = replace(load_settings(), youtube_upload_enabled=True)

    def programar(conn, settings, meta, canal, hora):
        assert (canal, hora) == ("rots", "18:00")
        db.crear_subida(conn, meta["clip_id"], canal, "programada", video_id="v1",
                        publish_at="2026-10-01T21:00:00Z")
        return "📤 Programado"

    monkeypatch.setattr(m, "_programar_subida", programar)
    m._subidas_callback(entorno, tg, _cb(f"sub:u:{SLUG}"), s)
    assert tg.teclados[-1]["inline_keyboard"][-1][0]["text"] == "📤 Programado para las 18:00"
    cancelados = []
    import clips_bot.youtube as yt

    class Cliente:
        def __init__(self, canal):
            pass

        def cancelar(self, vid):
            cancelados.append(vid)

    monkeypatch.setattr(yt, "Cliente", Cliente)
    m._subidas_callback(entorno, tg, _cb(f"sub:x:{SLUG}"), s)
    assert cancelados == ["v1"] and tg.teclados[-1]["inline_keyboard"][-1][0]["text"] == "📤 Subir"


def test_no_subir_queda_marcado_y_se_puede_volver(entorno):
    tg = TG()
    s = load_settings()
    m._subidas_callback(entorno, tg, _cb(f"sub:n:{SLUG}"), s)
    assert tg.teclados[-1]["inline_keyboard"][-1][0]["text"] == "🚫 No se sube"
    m._subidas_callback(entorno, tg, _cb(f"sub:r:{SLUG}"), s)
    assert tg.teclados[-1]["inline_keyboard"][-1][0]["text"] == "📤 Subir"


def test_el_voto_ya_no_sube_nada():
    import inspect

    fuente = inspect.getsource(m._votos) if hasattr(m, "_votos") else inspect.getsource(m)
    assert "_programar_subida(conn, ajustes, meta, \"rots\"" not in fuente
