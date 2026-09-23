from datetime import datetime, timezone

import pytest

from clips_bot.candidates import Clip, buscar_candidatos, motivo_descarte
from clips_bot.config import Filtros, Streamer
from clips_bot.twitch import TwitchClient, TwitchError

AHORA = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def helix_clip(id, views=500, duration=30.0, language="es", game_id="1", created="2026-09-21T02:00:00Z"):
    return {
        "id": id,
        "url": f"https://clips.twitch.tv/{id}",
        "broadcaster_id": "b1",
        "broadcaster_name": "Streamer",
        "title": f"titulo {id}",
        "view_count": views,
        "duration": duration,
        "language": language,
        "game_id": game_id,
        "created_at": created,
        "vod_offset": None,
    }


class Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """Responde según el path; `gets` puede traer listas para respuestas secuenciales."""

    def __init__(self, gets):
        self.gets = {k: list(v) if isinstance(v, list) else v for k, v in gets.items()}
        self.calls = []
        self.tokens = 0

    def post(self, url, data, timeout):
        self.tokens += 1
        return Resp(200, {"access_token": f"tok{self.tokens}"})

    def get(self, url, params, headers, timeout):
        path = url.split("/helix")[1]
        self.calls.append((path, params, headers))
        r = self.gets[path]
        return r.pop(0) if isinstance(r, list) else r


def cliente(gets):
    s = FakeSession(gets)
    return TwitchClient("cid", "secret", session=s, sleep=lambda _: None), s


# ---- filtros -------------------------------------------------------------


def test_motivo_descarte():
    f = Filtros(min_vistas=100)
    base = dict(login="x", game_name="Minecraft")
    ok = Clip.from_helix(helix_clip("a"), **base)
    assert motivo_descarte(ok, f, set()) is None
    assert motivo_descarte(ok, f, {"a"}) == "ya visto"
    assert motivo_descarte(Clip.from_helix(helix_clip("b", duration=10), **base), f, set()) == "muy corto"
    assert motivo_descarte(Clip.from_helix(helix_clip("c", duration=61), **base), f, set()) == "muy largo"
    assert motivo_descarte(Clip.from_helix(helix_clip("c2", duration=60), **base), f, set()) is None  # 60 entra
    assert motivo_descarte(Clip.from_helix(helix_clip("d", language="en"), **base), f, set()) == "idioma != es"
    assert motivo_descarte(Clip.from_helix(helix_clip("e", views=99), **base), f, set()) == "pocas vistas"
    musica = Clip.from_helix(helix_clip("g"), login="x", game_name="Music")
    assert motivo_descarte(musica, f, set()).startswith("categoría excluida")


# ---- cliente -------------------------------------------------------------


def test_paginacion_clips():
    c, s = cliente(
        {
            "/clips": [
                Resp(200, {"data": [helix_clip("a"), helix_clip("b")], "pagination": {"cursor": "p2"}}),
                Resp(200, {"data": [helix_clip("c")], "pagination": {}}),
            ]
        }
    )
    clips = c.get_clips("b1", AHORA, AHORA, max_clips=100)
    assert [x["id"] for x in clips] == ["a", "b", "c"]
    assert ("after", "p2") in s.calls[1][1]
    assert s.calls[0][2]["Client-Id"] == "cid"


def test_401_renueva_token_una_vez():
    c, s = cliente({"/users": [Resp(401), Resp(200, {"data": [{"login": "Foo", "id": "9"}]})]})
    assert c.get_user_ids(["foo"]) == {"foo": "9"}
    assert s.tokens == 2
    assert s.calls[1][2]["Authorization"] == "Bearer tok2"


def test_5xx_agota_reintentos():
    c, _ = cliente({"/users": Resp(503)})
    with pytest.raises(TwitchError):
        c.get_user_ids(["foo"])


def test_4xx_no_reintenta():
    c, s = cliente({"/users": Resp(400, {"message": "bad"})})
    with pytest.raises(TwitchError):
        c.get_user_ids(["foo"])
    assert len(s.calls) == 1


# ---- flujo completo ------------------------------------------------------


def test_buscar_candidatos_respeta_permiso_y_ordena():
    c, s = cliente(
        {
            "/users": Resp(200, {"data": [{"login": "uno", "id": "1"}]}),
            "/clips": Resp(
                200,
                {
                    "data": [
                        helix_clip("a", views=300),
                        helix_clip("b", views=900),
                        helix_clip("m", views=5000, game_id="music"),
                        helix_clip("en", views=5000, language="en"),
                        {**helix_clip("lec", views=9000), "video_id": "v1"},  # título del stream: LEC
                    ]
                },
            ),
            "/games": Resp(200, {"data": [{"id": "1", "name": "Minecraft"}, {"id": "music", "name": "Music"}]}),
            "/videos": Resp(200, {"data": [{"id": "v1", "title": "COSTREAM LEC semana 5"}]}),
        }
    )
    streamers = [Streamer("uno", cita="clipeen tranqui", fuente="panel"), Streamer("dos")]
    filtros = Filtros(n_candidatos=1, palabras_costream=("LEC",), antiguedad_min_h=0, min_vistas=100)
    res = buscar_candidatos(c, streamers, filtros, vistos=set(), ahora=AHORA)

    assert [x.id for x in res.candidatos] == ["b"]
    assert [x.id for x in res.costream] == ["lec"]
    assert res.descartes["costream"] == 1
    assert res.sin_permiso == ["dos"]
    # "dos" no tiene permiso: ni siquiera se consulta a Twitch
    assert ("login", "dos") not in s.calls[0][1]
    assert res.descartes["fuera del top N"] == 1
    assert res.descartes["categoría excluida (Music)"] == 1
    assert res.descartes["idioma != es"] == 1


def test_db_registrar_clip_guarda_motivo_y_actualiza(tmp_path):
    from clips_bot import db

    conn = db.connect(tmp_path / "t.db")
    db.registrar_clip(conn, "c1", "uno", "descartado", "costream", title="LEC", view_count=10)
    db.registrar_clip(conn, "c1", "uno", "descartado", "costream", view_count=None)
    fila = conn.execute("SELECT estado, motivo, view_count, title FROM clips WHERE clip_id='c1'").fetchone()
    assert fila == ("descartado", "costream", 10, "LEC")
    assert db.ids_vistos(conn) == {"c1"}
    db.set_estado(conn, "c1", "entregado")
    assert db.estados(conn) == {"c1": "entregado"}
