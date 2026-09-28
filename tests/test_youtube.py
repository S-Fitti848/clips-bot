"""Subida a YouTube (apagada hasta la auditoría): metadatos, horarios, el upload reanudable con una
sesión falsa, cancelar, y que con `youtube_upload_enabled: false` no se haga nada."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import clips_bot.__main__ as m
from clips_bot import db, youtube as yt
from clips_bot.config import load_settings

AR = yt.AR


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_metadatos_privado_con_publishat_y_limites():
    cuando = datetime(2026, 9, 28, 13, 0, tzinfo=AR)
    d = yt.metadatos("x" * 150, "d" * 6000, ["#Shorts", "#Historia", "#" + "a" * 600], cuando, "27")
    assert d["status"] == {"privacyStatus": "private", "publishAt": "2026-09-28T16:00:00Z",
                           "selfDeclaredMadeForKids": False}
    assert len(d["snippet"]["title"]) == 100 and len(d["snippet"]["description"]) == 5000
    assert d["snippet"]["tags"] == ["Shorts", "Historia"]      # sin #, y el que no entra afuera
    assert d["snippet"]["categoryId"] == "27"


def test_proximo_horario():
    ahora = datetime(2026, 9, 28, 12, 50, tzinfo=AR)
    horas = ["13:00", "18:00", "21:30"]
    # 13:00 está a 10 min (menos del margen de 20): pasa al siguiente horario
    assert yt.proximo_horario("13:00", ahora, horarios=horas).strftime("%d %H:%M") == "28 18:00"
    ocupado = {datetime(2026, 9, 28, 18, 0, tzinfo=AR).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert yt.proximo_horario("18:00", ahora, ocupados=ocupado, horarios=horas).strftime("%H:%M") == "21:30"
    assert yt.proximo_horario("12:00", ahora).strftime("%d %H:%M") == "29 12:00"


class Resp:
    def __init__(self, status=200, datos=None, headers=None):
        self.status_code, self._datos, self.headers, self.text = status, datos or {}, headers or {}, ""

    def json(self):
        return self._datos


class Sesion:
    def __init__(self):
        self.llamadas = []

    def post(self, url, **k):
        self.llamadas.append(("POST", url, k))
        if url == yt.TOKEN_URL:
            return Resp(datos={"access_token": "A", "expires_in": 3600})
        return Resp(headers={"Location": "https://upload/sesion/1"})

    def put(self, url, **k):
        self.llamadas.append(("PUT", url, k))
        return Resp(datos={"id": "VIDEO123"})

    def get(self, url, **k):
        return Resp(datos={"items": [{"id": "UC1", "snippet": {"title": "Rots"}}]})


def _cliente(sesion):
    return yt.Cliente("rots", session=sesion, token={"refresh_token": "R"},
                      secreto={"client_id": "C", "client_secret": "S"})


def test_subir_es_reanudable_en_dos_pasos(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    s = Sesion()
    vid = _cliente(s).subir(video, "Título", "Desc", ["#Shorts"], datetime(2026, 9, 28, 13, tzinfo=AR))
    assert vid == "VIDEO123"
    inicio = next(k for met, u, k in s.llamadas if u == yt.UPLOAD)
    assert inicio["params"] == {"uploadType": "resumable", "part": "snippet,status"}
    assert inicio["headers"]["X-Upload-Content-Length"] == "1000"
    assert json.loads(inicio["data"])["status"]["publishAt"] == "2026-09-28T16:00:00Z"
    assert any(met == "PUT" and u == "https://upload/sesion/1" for met, u, _ in s.llamadas)


def test_cancelar_lo_deja_privado_sin_fecha():
    s = Sesion()
    _cliente(s).cancelar("VIDEO123")
    met, url, k = s.llamadas[-1]
    assert (met, url) == ("PUT", f"{yt.API}/videos")
    assert json.loads(k["data"])["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}


def test_sin_token_avisa_como_conseguirlo(tmp_path, monkeypatch):
    monkeypatch.setattr(yt, "CONFIG_DIR", tmp_path)
    with pytest.raises(yt.YouTubeError, match="youtube-auth"):
        yt.Cliente("rots")


# ---- desde el bot -------------------------------------------------------------------------------

META = {"clip_id": "c1", "salida": "x.mp4",
        "textos": {"titulo": "T", "descripcion": "D", "hashtags": ["#Shorts"]}}


def test_apagada_no_hace_nada(conn, monkeypatch):
    monkeypatch.setattr(yt, "Cliente", lambda *a, **k: pytest.fail("está apagada"))
    assert m._programar_subida(conn, load_settings(), META, "rots", "13:00") == ""
    assert db.subidas(conn) == []


class ClienteFalso:
    subidos = []

    def __init__(self, canal):
        self.canal = canal

    def subir(self, video, titulo, desc, tags, cuando, categoria):
        ClienteFalso.subidos.append((self.canal, titulo, cuando, categoria))
        return "VID"

    def cancelar(self, video_id):
        ClienteFalso.subidos.append(("cancelado", video_id))


@pytest.fixture
def prendida(monkeypatch):
    ClienteFalso.subidos = []
    monkeypatch.setattr(yt, "Cliente", ClienteFalso)
    return replace(load_settings(), youtube_upload_enabled=True)


def test_prendida_programa_una_sola_vez(conn, prendida):
    r = m._programar_subida(conn, prendida, META, "rots", "18:00")
    assert "Programado" in r and "Rots" in r
    assert m._programar_subida(conn, prendida, META, "rots", "18:00") == ""    # ya estaba
    (s,) = db.subidas(conn)
    assert (s["estado"], s["video_id"], s["canal"]) == ("programada", "VID", "rots")
    assert ClienteFalso.subidos[0][3] == "20"


@pytest.mark.parametrize("hora_aprobacion,esperado", [
    ((9, 0), (12, 0)),        # antes de las 12: a las 12
    ((15, 10), (15, 40)),     # pasadas las 12: en 30 min, el mismo día
    ((23, 32), (23, 55)),     # tarde: nunca después de las 23:55 (antes caía a las 00:02 de mañana)
])
def test_la_efemeride_sale_el_mismo_dia(conn, prendida, hora_aprobacion, esperado):
    """"Un día como hoy" no puede salir mañana. Encontrado corriendo el test en la Pi a las 23:32."""
    ahora = datetime(2026, 9, 28, *hora_aprobacion, tzinfo=AR)
    m._programar_subida(conn, prendida, {**META, "clip_id": f"efe_{hora_aprobacion}"},
                        "pequena_historia", "12:00", ahora=ahora)
    canal, _, cuando, cat = ClienteFalso.subidos[-1]
    assert canal == "pequena_historia" and cat == "27"
    assert cuando.date() == ahora.date() and (cuando.hour, cuando.minute) == esperado


def test_subidas_lista_y_cancela(conn, prendida):
    m._programar_subida(conn, prendida, META, "rots", "18:00")
    texto, teclado = m._subidas_texto(conn, prendida)
    sid = db.subidas(conn)[0]["id"]
    assert "c1" in texto and teclado["inline_keyboard"][0][0]["callback_data"] == f"sub:c:{sid}"

    class TG:
        def answer_callback(self, *a):
            pass

        def edit_message(self, *a):
            pass

    m._subidas_callback(conn, TG(), {"data": f"sub:c:{sid}", "chat_id": "1", "message_id": 2,
                                     "callback_id": "q"}, prendida)
    assert db.subidas(conn)[0]["estado"] == "cancelada" and ("cancelado", "VID") in ClienteFalso.subidos


def test_con_la_subida_apagada_subidas_lo_dice(conn):
    texto, teclado = m._subidas_texto(conn, load_settings())
    assert "apagada" in texto and teclado is None
