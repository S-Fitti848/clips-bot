"""Los pedidos a YouTube tienen tope de tiempo TOTAL (2026-10-30: un comando quedó colgado horas)."""
import time

import pytest
import requests

from clips_bot import red, youtube


def test_un_pedido_que_no_termina_se_corta_en_el_tope(monkeypatch):
    def lento(self, method, url, *a, **k):
        time.sleep(5)

    monkeypatch.setattr(requests.Session, "request", lento)
    s = red.SesionConTope(tope_s=0.3)
    t0 = time.monotonic()
    with pytest.raises(red.TiempoAgotado):
        s.get("https://ejemplo.invalid/x")
    assert time.monotonic() - t0 < 2


def test_un_pedido_normal_pasa_y_lleva_timeout_por_defecto(monkeypatch):
    vistos = {}

    def rapido(self, method, url, *a, **k):
        vistos.update(k)
        return "ok"

    monkeypatch.setattr(requests.Session, "request", rapido)
    assert red.SesionConTope().get("https://ejemplo.invalid/x") == "ok"
    assert vistos["timeout"] == red.TIMEOUT_REQUESTS


def test_los_errores_se_relanzan_igual(monkeypatch):
    def roto(self, method, url, *a, **k):
        raise requests.ConnectionError("se cortó")

    monkeypatch.setattr(requests.Session, "request", roto)
    with pytest.raises(requests.ConnectionError):
        red.SesionConTope().get("https://ejemplo.invalid/x")


def test_el_cliente_de_youtube_usa_la_sesion_con_tope():
    c = youtube.Cliente("rots", token={"refresh_token": "x"})
    assert isinstance(c.session, red.SesionConTope)


def test_los_tests_no_pueden_salir_a_youtube_ni_facebook():
    """El conftest corta YouTube y Facebook en TODOS los tests, aunque la subida esté prendida."""
    from conftest import SalidaProhibida

    with pytest.raises(SalidaProhibida):
        requests.Session().get("https://www.googleapis.com/youtube/v3/videos")
    with pytest.raises(SalidaProhibida):
        requests.Session().post("https://graph.facebook.com/v23.0/me")
    with pytest.raises(youtube.YouTubeError, match="Falta"):
        youtube.Cliente("rots")                       # el token real de config/ no está al alcance
