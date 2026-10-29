"""Un corte de conexión con Telegram se reintenta 2 veces antes de darlo por fallido (2026-10-29)."""
import io

import pytest
import requests

from clips_bot.telegram import TelegramClient, TelegramError


class Resp:
    def __init__(self, cuerpo):
        self._c = cuerpo

    def json(self):
        return self._c


class Sesion:
    def __init__(self, *resultados):
        self.resultados, self.llamadas, self.leidos = list(resultados), 0, []

    def post(self, url, data=None, files=None, timeout=None):
        self.llamadas += 1
        for valor in (files or {}).values():
            self.leidos.append(valor[1].read())
        r = self.resultados.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _cliente(sesion, esperas):
    return TelegramClient("x", session=sesion, sleep=esperas.append)


def test_un_corte_se_reintenta_y_si_vuelve_no_avisa_nada():
    esperas = []
    s = Sesion(requests.ConnectionError("('Connection aborted.', RemoteDisconnected('Remote end closed'))"),
               requests.ReadTimeout("read timed out"), Resp({"ok": True, "result": {"message_id": 1}}))
    _cliente(s, esperas).send_message("1", "hola")
    assert s.llamadas == 3 and esperas == [3, 6]


def test_si_fallan_los_tres_intentos_recien_ahi_es_error():
    esperas = []
    s = Sesion(*[requests.ConnectionError("Connection aborted")] * 3)
    with pytest.raises(TelegramError, match="3 intentos"):
        _cliente(s, esperas).send_message("1", "hola")
    assert s.llamadas == 3


def test_un_error_que_contesta_telegram_no_se_reintenta():
    esperas = []
    s = Sesion(Resp({"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities"}))
    with pytest.raises(TelegramError, match="400"):
        _cliente(s, esperas).send_message("1", "<b>")
    assert s.llamadas == 1 and esperas == []


def test_el_archivo_se_vuelve_a_mandar_entero(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"video-entero")
    s = Sesion(requests.ConnectionError("RemoteDisconnected"), Resp({"ok": True, "result": {}}))
    _cliente(s, []).send_video("1", video, "c", width=1080, height=1920)
    assert s.leidos == [b"video-entero", b"video-entero"]
