"""Kick como segunda plataforma, política de permiso por experimento, exclusión por reclamo de
copyright y detección de marcador deportivo. Todo con respuestas simuladas."""

from datetime import datetime, timedelta, timezone

import pytest

from clips_bot import db
from clips_bot.candidates import buscar_kick, habilitados, Resultado
from clips_bot.config import Filtros, Seleccion, Streamer, load_streamers
from clips_bot.deportes import evaluar_region
from clips_bot.kick import KickClient, KickError, a_clip, url_clip
from clips_bot.seleccion import Opcion, seleccionar
from clips_bot.telegram import RECORDATORIO, comandos, mensaje_textos

AHORA = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
DAVOO = [Streamer("davoo", plataforma="kick", fuentes=("reciente",), grupo="kick_reciente", experimento=True)]


class Resp:
    def __init__(self, status, payload, texto=""):
        self.status_code = status
        self._p = payload
        self.text = texto or str(payload)

    def json(self):
        if self._p is None:
            raise ValueError("no es JSON")
        return self._p


class FakeSession:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.llamadas.append({"url": url, "params": params, "headers": headers})
        return self.respuestas.pop(0)


def clip_kick(id, views=100, horas=48.0, duration=30.0, titulo="un clip", categoria="Just Chatting",
              livestream="l1", offset=1000):
    return {
        "id": id, "title": titulo, "view_count": views, "duration": duration,
        "created_at": (AHORA - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
        "category": {"id": 15, "name": categoria}, "channel": {"slug": "davoo", "username": "DavooXeneize"},
        "livestream_id": livestream, "vod_starts_at": offset,
    }


def pagina(clips, cursor=None):
    return Resp(200, {"clips": clips, "nextCursor": cursor})


# ---- cliente de Kick ---------------------------------------------------------------


def test_kick_pagina_y_arma_el_clip():
    s = FakeSession([pagina([clip_kick("c1")], "cur2"), pagina([clip_kick("c2")])])
    clips = KickClient(session=s, sleep=lambda _: None).get_clips("davoo", max_clips=10)
    assert [c["id"] for c in clips] == ["c1", "c2"]
    assert s.llamadas[0]["url"] == "https://kick.com/api/v2/channels/davoo/clips"
    # sin sort=view vienen los últimos subidos: cientos de clips de la última hora con 2 o 3 vistas
    assert s.llamadas[0]["params"] == {"sort": "view", "time": "week"}
    assert s.llamadas[1]["params"] == {"sort": "view", "time": "week", "cursor": "cur2"}
    assert "Mozilla" in s.llamadas[0]["headers"]["User-Agent"]  # la API interna rechaza sin UA

    plano = a_clip(clip_kick("c1", views=7, offset=1234, livestream="l9"), "davoo")
    assert plano["url"] == url_clip("davoo", "c1") == "https://kick.com/davoo/clips/c1"
    assert (plano["view_count"], plano["vod_offset"], plano["video_id"]) == (7, 1234, "l9")
    assert plano["language"] == ""  # Kick no lo informa


def test_kick_html_de_cloudflare_es_error():
    s = FakeSession([Resp(200, None, "<html>captcha</html>"), Resp(403, None, "blocked"),
                     Resp(403, None, "blocked")])
    with pytest.raises(KickError):
        KickClient(session=s, sleep=lambda _: None).get_clips("davoo")


def test_buscar_kick_no_corta_la_corrida_si_la_api_falla():
    s = FakeSession([Resp(503, None, "boom")] * 3)
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), DAVOO, Filtros(), vistos=set(), ahora=AHORA)
    assert res.candidatos == []
    assert res.fallos and "kick/davoo" in res.fallos[0]


def test_twitch_no_pisa_los_candidatos_de_kick():
    """Bug de la primera corrida real: la búsqueda de Twitch reemplazaba res.candidatos y los de
    Kick desaparecían, así que el cupo kick_reciente quedaba vacío sin motivo visible."""
    from test_fuentes import fijos, vod
    from test_twitch_candidates import cliente as cliente_twitch

    from clips_bot.candidates import buscar_candidatos

    s = FakeSession([pagina([clip_kick("k1", views=300, horas=48)])])
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), DAVOO, Filtros(), vistos=set(), ahora=AHORA)
    assert [c.id for c in res.candidatos] == ["k1"]

    tw, _ = cliente_twitch(fijos({"/clips": Resp(200, {"data": [vod("t1", 500, horas=48, offset=1)]})}))
    uno = [Streamer("uno", fuentes=("reciente",), experimento=True)]
    res = buscar_candidatos(tw, uno, Filtros(), vistos=set(), ahora=AHORA, res=res)

    assert sorted(c.id for c in res.candidatos) == ["k1", "t1"]  # conviven las dos plataformas
    assert {c.plataforma for c in res.candidatos} == {"kick", "twitch"}


def test_buscar_kick_filtra_ventana_y_no_filtra_idioma():
    s = FakeSession([pagina([
        clip_kick("viejo", horas=24 * 10),  # fuera de la ventana de 7 días
        clip_kick("nuevo", horas=5, offset=5000),  # no llegó a las 24 h
        clip_kick("ok", views=50, horas=48, offset=1000),
        clip_kick("mismo", views=20, horas=48, offset=1030),  # mismo momento que "ok"
        clip_kick("gol", views=999, horas=48, offset=8000, titulo="GOL de Boca"),
    ])])
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), DAVOO,
                      Filtros(palabras_costream=("Boca", "gol")), vistos=set(), ahora=AHORA)
    assert [(c.id, c.clips_mismo_momento, c.plataforma, c.grupo) for c in res.candidatos] == [
        ("ok", 2, "kick", "kick_reciente")]
    assert res.descartes["fuera de la ventana"] == 1
    assert res.descartes["costream"] == 1  # el de fútbol
    assert res.descartes["mismo momento"] == 1
    assert "muy nuevo (no llegó a antiguedad_min_h; se reevalúa mañana)" in res.descartes


# ---- política de permiso y exclusión -------------------------------------------------


def test_permiso_por_experimento_y_por_cita():
    con_cita = Streamer("a", cita="clipeen", fuente="panel")
    experimento = Streamer("b", experimento=True)
    sin_nada = Streamer("c")
    assert (con_cita.permitido, con_cita.como_entra) == (True, "cita")
    assert (experimento.permitido, experimento.como_entra) == (True, "experimento")
    assert sin_nada.permitido is False


def test_streamers_yaml_del_repo_carga_los_grupos():
    por_login = {s.login: s for s in load_streamers()}
    assert por_login["davooxeneize"].plataforma == "kick"
    assert por_login["davooxeneize"].detectar_marcador is True
    assert por_login["vegetta777"].fuentes == ("catalogo",)
    assert por_login["davooxeneize"].grupo_de("reciente") == "kick_reciente"
    # la sección evento_* entra al grupo "evento"
    assert any(s.grupo == "evento" for s in por_login.values())


def test_el_filtro_de_deporte_no_toca_al_grupo_del_evento():
    """El evento es todo Minecraft y tiene mucho pasto: la señal de césped daría falsos positivos.
    Por eso la detección corre SOLO en los streamers marcados (hoy, davooxeneize)."""
    streamers = load_streamers()
    assert [s.login for s in streamers if s.detectar_marcador] == ["davooxeneize"]
    evento = [s for s in streamers if s.grupo == "evento"]
    assert len(evento) > 10 and not any(s.detectar_marcador for s in evento)


def test_excluido_no_se_consulta_mas():
    res = Resultado()
    activos = habilitados(DAVOO, "kick", "reciente", res, False, {"davoo": "reclamo de copyright"})
    assert activos == [] and res.excluidos == ["davoo"]
    assert habilitados(DAVOO, "kick", "reciente", Resultado(), False, {}) == DAVOO


def test_reclamo_excluye_al_streamer_y_es_idempotente(tmp_path):
    from clips_bot.__main__ import _reclamo

    conn = db.connect(tmp_path / "t.db")
    db.registrar_clip(conn, "clip_1", "davoo", "entregado", None, url="https://kick.com/davoo/clips/clip_1")

    assert "no tengo" in _reclamo(conn, ["otro"]).lower()
    assert "Uso:" in _reclamo(conn, [])

    r = _reclamo(conn, ["clip_1"])
    assert "EXCLUIDO" in r and "davoo" in r
    assert db.excluidos(conn)["davoo"].startswith("reclamo de copyright")
    assert conn.execute("SELECT motivo FROM clips WHERE clip_id='clip_1'").fetchone()[0] == "reclamo"
    assert "ya estaba excluido" in _reclamo(conn, ["clip_1"])


def test_mensaje_de_telegram_lleva_el_recordatorio_y_el_comando():
    m = mensaje_textos(1, "davoo", "clip_1", "13:00", {"titulo": "T", "descripcion": "D",
                                                      "hashtags": ["#Shorts"], "credito": "C"})
    assert RECORDATORIO in m
    assert "PRIVADO" in m and "Chequeos de copyright" in m
    assert "/reclamo clip_1" in m


def test_comandos_ignora_lo_que_no_es_comando():
    updates = [
        {"update_id": 1, "message": {"chat": {"id": 9}, "text": "hola"}},
        {"update_id": 2, "message": {"chat": {"id": 9}, "text": "/reclamo@Clipsito_bot clip_1 strike"}},
    ]
    assert comandos(updates) == [{"update_id": 2, "chat_id": "9", "comando": "/reclamo",
                                  "args": ["clip_1", "strike"]}]


# ---- mezcla por grupo ----------------------------------------------------------------


def op(id, streamer, vistas, grupo, fuente="reciente"):
    return Opcion(id, streamer, vistas, AHORA - timedelta(days=2), titulo=id, fuente=fuente, grupo=grupo)


MEZCLA = Seleccion(mezcla={"kick_reciente": 1, "evento": 1, "catalogo": 1},
                   empate_pct={"reciente": 0.0, "catalogo": 0.0})


def test_mezcla_por_grupo_1_kick_1_evento_1_catalogo():
    opciones = [
        op("k1", "davoo", 500, "kick_reciente"), op("k2", "davoo", 400, "kick_reciente"),
        op("e1", "parti", 300, "evento"), op("e2", "parti", 200, "evento"),
        op("c1", "vegetta777", 9000, "catalogo", "catalogo"),
        op("c2", "vegetta777", 8000, "catalogo", "catalogo"),
    ]
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["k1", "e1", "c1"]


def test_sin_evento_el_cupo_va_al_catalogo():
    opciones = [
        op("k1", "davoo", 500, "kick_reciente"),
        op("c1", "vegetta777", 9000, "catalogo", "catalogo"),
        op("c2", "vegetta777", 8000, "catalogo", "catalogo"),
        op("c3", "otro", 7000, "catalogo", "catalogo"),
    ]
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["k1", "c1", "c2"]


def test_sin_catalogo_los_cupos_vuelven_a_los_otros_grupos():
    opciones = [op("k1", "davoo", 500, "kick_reciente"), op("k2", "davoo", 400, "kick_reciente"),
                op("e1", "parti", 300, "evento")]
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["k1", "k2", "e1"]


# ---- marcador deportivo ----------------------------------------------------------------


@pytest.mark.parametrize(
    "quietud, bordes, esperado",
    [
        (0.90, 0.09, True),  # marcador de TV: región quieta y llena de texto
        (0.90, 0.01, False),  # quieta pero lisa (cielo, pared): no es marcador
        (0.20, 0.09, False),  # llena de bordes pero se mueve: es el juego
        (0.74, 0.09, False),  # justo abajo del umbral
    ],
)
def test_evaluar_region_del_marcador(quietud, bordes, esperado):
    assert evaluar_region(quietud, bordes, 0.75, 0.05) is esperado


def test_fraccion_cesped_separa_cancha_de_minecraft():
    import numpy as np
    from clips_bot.deportes import fraccion_cesped

    def lleno(bgr):
        return np.full((60, 80, 3), bgr, dtype=np.uint8)

    cancha = lleno((60, 140, 60))  # verde césped
    assert fraccion_cesped(cancha) > 0.95
    assert fraccion_cesped(lleno((30, 30, 30))) == 0.0  # gris oscuro
    assert fraccion_cesped(lleno((200, 120, 60))) == 0.0  # azul
    # medido con clips reales (2026-09-22): fútbol llega a 68 %, Minecraft no pasa de 26 %
    mitad = np.concatenate([lleno((60, 140, 60))[:30], lleno((30, 30, 30))[:30]])
    assert 0.45 < fraccion_cesped(mitad) < 0.55


def test_deporte_dispara_por_cesped_aunque_no_haya_marcador():
    from clips_bot.deportes import Deporte, Marcador

    # el caso real: cámara sobre la tribuna, sin marcador en pantalla
    sin_nada = Deporte("", Marcador(False), 0.26, 0)
    con_cancha = Deporte("cancha en pantalla (2/12 frames con ≥ 45% de césped)", Marcador(False), 0.68, 2)
    assert sin_nada.hay is False
    assert con_cancha.hay is True
    assert con_cancha.a_dict()["cesped_max"] == 0.68  # la medición se guarda siempre, para calibrar
    assert sin_nada.a_dict()["frames_con_cesped"] == 0
