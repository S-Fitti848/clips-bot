"""Dos claves de Gemini (2026-09-29): siempre la principal; la segunda solo ante un 429 de cuota del
día, y recién después el modelo de respaldo. Una segunda inválida se ignora y se avisa una vez."""

import json
import logging

import pytest

from clips_bot import db, gemini
from clips_bot.gemini import GeminiClient, GeminiError, hablar_con_claves

OK = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
CUOTA = {"error": {"code": 429, "message": "You exceeded your current quota", "status": "RESOURCE_EXHAUSTED"}}
INVALIDA = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                      "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}


class Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._p = status, payload or {}
        self.text = json.dumps(self._p)

    def json(self):
        return self._p


class Sesion:
    def __init__(self, *respuestas):
        self.respuestas, self.pedidos = list(respuestas), []

    def post(self, url, headers=None, json=None, timeout=None):
        self.pedidos.append((url.split("/models/")[1].split(":")[0], headers["x-goog-api-key"]))
        return self.respuestas.pop(0)


CLAVES = [("principal", "K1"), ("segunda", "K2")]


def _cliente(s, avisos):
    return GeminiClient(CLAVES, "flash", session=s, sleep=lambda _: None, modelo_fallback="lite",
                        aviso=lambda *a: avisos.append(a[:2]))


def test_con_cuota_usa_siempre_la_principal(caplog):
    avisos = []
    s = Sesion(Resp(200, OK), Resp(200, OK))
    c = _cliente(s, avisos)
    with caplog.at_level(logging.INFO, logger="clips_bot.gemini"):
        c.json("s", "p", {})
        c.json("s", "p", {})
    assert s.pedidos == [("flash", "K1")] * 2 and avisos == []
    assert "Gemini flash con la clave principal" in caplog.text


def test_sin_cuota_la_principal_pasa_a_la_segunda_antes_que_al_respaldo(caplog):
    avisos = []
    s = Sesion(Resp(429, CUOTA), Resp(200, OK), Resp(200, OK))
    c = _cliente(s, avisos)
    with caplog.at_level(logging.INFO, logger="clips_bot.gemini"):
        c.json("s", "p", {})
        c.json("s", "p", {})                     # la principal ya se sabe sin cuota hoy: ni se prueba
    assert s.pedidos == [("flash", "K1"), ("flash", "K2"), ("flash", "K2")]
    assert avisos == [("segunda", "segunda")] * 2        # el "una vez por día" lo hace el aviso
    assert "con la clave segunda" in caplog.text


def test_las_dos_sin_cuota_recien_ahi_el_modelo_de_respaldo():
    s = Sesion(Resp(429, CUOTA), Resp(429, CUOTA), Resp(200, OK))
    _cliente(s, []).json("s", "p", {})
    assert s.pedidos == [("flash", "K1"), ("flash", "K2"), ("lite", "K1")]


def test_un_429_que_no_es_de_cuota_no_cambia_de_clave():
    s = Sesion(Resp(429, {"error": {"message": "rate limit"}}), Resp(200, OK))
    _cliente(s, []).json("s", "p", {})
    assert s.pedidos == [("flash", "K1"), ("flash", "K1")]


def test_la_segunda_invalida_se_ignora_y_avisa():
    avisos = []
    s = Sesion(Resp(429, CUOTA), Resp(400, INVALIDA), Resp(200, OK), Resp(200, OK))
    c = _cliente(s, avisos)
    c.json("s", "p", {})
    assert s.pedidos == [("flash", "K1"), ("flash", "K2"), ("lite", "K1")]
    assert avisos == [("invalida", "segunda")]
    c.json("s", "p", {})
    assert s.pedidos[-1] == ("lite", "K1") and len(avisos) == 1


def test_la_principal_invalida_sigue_siendo_un_error():
    s = Sesion(Resp(400, INVALIDA))
    with pytest.raises(GeminiError):
        _cliente(s, []).json("s", "p", {})


def test_claves_saca_la_segunda_ya_marcada_invalida(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "K1")
    monkeypatch.setenv("GEMINI_API_KEY_2", "K2")
    monkeypatch.setattr("clips_bot.config.load_dotenv", lambda *a, **k: None)
    conn = db.connect(tmp_path / "t.db")
    assert gemini.claves(conn) == CLAVES
    db.set_valor(conn, gemini.CLAVE_INVALIDA, json.dumps({"segunda": gemini.huella("K2")}))
    assert gemini.claves(conn) == [("principal", "K1")]
    monkeypatch.setenv("GEMINI_API_KEY_2", "K3")                  # la cambió: se vuelve a probar
    assert gemini.claves(conn) == [("principal", "K1"), ("segunda", "K3")]


def test_el_aviso_de_la_segunda_sale_una_vez_por_dia(tmp_path, monkeypatch):
    import clips_bot.config as config
    import clips_bot.telegram as telegram

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "env", lambda n, requerido=True: {"TELEGRAM_CHAT_ID": "8668060171"}.get(n, "T"))
    mandados = []

    class TG:
        def __init__(self, token):
            pass

        def send_message(self, chat, texto):
            mandados.append((chat, texto))

    monkeypatch.setattr(telegram, "TelegramClient", TG)
    gemini.aviso_por_telegram("segunda", "segunda", "K2")
    gemini.aviso_por_telegram("segunda", "segunda", "K2")
    assert len(mandados) == 1 and "sin la cuota de hoy" in mandados[0][1]
    gemini.aviso_por_telegram("invalida", "segunda", "K2", "400 API key not valid")
    assert "inválida" in mandados[-1][1] and "K2" not in mandados[-1][1]   # la clave no se muestra
    conn = db.connect(tmp_path / "t.db")
    assert json.loads(db.get_valor(conn, gemini.CLAVE_INVALIDA)) == {"segunda": gemini.huella("K2")}


def test_la_voz_tambien_pasa_a_la_segunda_sin_cuota(monkeypatch):
    usadas, avisos = [], []

    def hablar(clave, texto, **kw):
        usadas.append(clave)
        if clave == "K1":
            raise GeminiError('Gemini TTS (tts): 429 {"error": "quota exceeded"}')
        return b"pcm", 24000

    monkeypatch.setattr(gemini, "hablar", hablar)
    assert hablar_con_claves(CLAVES, "hola", aviso=lambda *a: avisos.append(a[0])) == (b"pcm", 24000)
    assert usadas == ["K1", "K2"] and avisos == ["segunda"]
