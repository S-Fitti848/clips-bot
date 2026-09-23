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


def videos(titulos=None):
    """Respuesta de /videos: {livestream_id: título del stream}. buscar_kick la pide después de
    los clips, así que va al final de la cola de la sesión falsa."""
    return Resp(200, [{"id": lid, "session_title": t} for lid, t in (titulos or {}).items()])


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


def test_programa_de_terceros_por_titulo_del_stream():
    """La Cobra, 2026-09-22: el clip se llamaba "El peor golpe en vivo" y el stream era
    "412 con LA COBRA... PROGRAMA". Ninguna palabra del programa estaba en el título del clip, así
    que solo el título del stream lo agarra. Kick no lo trae en el clip: sale de /videos."""
    cobra = [Streamer("cobra", plataforma="kick", fuentes=("reciente",), grupo="argentinos",
                      experimento=True, palabras_programa=("412", "ANALIZAMOS"))]
    s = FakeSession([
        pagina([clip_kick("prog", views=800, horas=48, titulo="El peor golpe en vivo", livestream="l1"),
                clip_kick("normal", views=700, horas=48, offset=9000, livestream="l2")]),
        videos({"l1": "412 con LA COBRA, DAVOOXENEIZE, AGUSNETA. PROGRAMA",
                "l2": "jugando un rato"}),
    ])
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), cobra, Filtros(),
                      vistos=set(), ahora=AHORA)
    assert [c.id for c in res.candidatos] == ["normal"]
    assert res.descartes["programa_terceros"] == 1


def test_el_programa_mira_el_stream_y_no_el_clip():
    from clips_bot.candidates import es_programa_de_terceros

    assert es_programa_de_terceros("412 con LA COBRA. PROGRAMA", ("412",))
    assert es_programa_de_terceros("hoy ANALIZAMOS la fecha", ("analizamos",))  # sin importar mayúsculas
    assert not es_programa_de_terceros("jugando al 4120", ("412",))  # palabra completa, no subcadena
    assert not es_programa_de_terceros("", ("412",))  # sin título de stream no se descarta nada


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

    s = FakeSession([pagina([clip_kick("k1", views=300, horas=48)]), videos()])
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
    ]), videos()])
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
    assert por_login["davooxeneize"].grupo_de("reciente") == "argentinos"
    assert por_login["vegetta777"].fuentes == ("catalogo",)
    # el grupo argentinos son los 8 de Kick resueltos el 2026-09-22
    argentinos = [s for s in por_login.values() if s.grupo == "argentinos"]
    assert len(argentinos) == 8 and all(s.plataforma == "kick" for s in argentinos)
    # la sección evento_* entra al grupo "evento"
    assert any(s.grupo == "evento" for s in por_login.values())


def test_el_filtro_de_deporte_no_toca_al_grupo_del_evento():
    """El evento es todo Minecraft y tiene mucho pasto: la señal de césped daría falsos positivos.
    Por eso la detección corre SOLO en los streamers marcados (hoy, davooxeneize)."""
    streamers = load_streamers()
    # los que hablan de fútbol, todos del grupo argentinos
    marcados = [s for s in streamers if s.detectar_marcador]
    assert sorted(s.login for s in marcados) == ["coker", "davooxeneize", "lacobraaa"]
    assert all(s.grupo == "argentinos" for s in marcados)
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
        {"update_id": 2, "message": {"chat": {"id": 9}, "from": {"id": 77, "first_name": "Santi",
                                                                 "username": "santi"},
                                     "text": "/reclamo@Clipsito_bot clip_1 strike"}},
    ]
    assert comandos(updates) == [{"update_id": 2, "chat_id": "9", "user_id": "77",
                                  "usuario": "Santi (@santi)", "comando": "/reclamo",
                                  "args": ["clip_1", "strike"]}]


def test_usuarios_permitidos_y_quien_escribio():
    """En un grupo el chat es uno solo: el permiso tiene que ser por usuario, no por chat."""
    from clips_bot.telegram import usuarios, usuarios_permitidos

    assert usuarios_permitidos(" 77, 88  99 ") == {"77", "88", "99"}
    assert usuarios_permitidos("") == set()  # sin lista no se obedece a nadie (falla cerrado)
    updates = [
        {"update_id": 3, "message": {"chat": {"id": -100123}, "from": {"id": 77, "first_name": "Santi"},
                                     "text": "/start"}},
        {"update_id": 4, "message": {"chat": {"id": -100123}, "from": {"id": 55, "first_name": "Otro"},
                                     "text": "/reclamo clip_1"}},
    ]
    assert [u["id"] for u in usuarios(updates)] == ["77", "55"]
    ajenos = [c for c in comandos(updates) if c["user_id"] not in usuarios_permitidos("77")]
    assert [c["user_id"] for c in ajenos] == ["55"]


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
        op("c2", "otro", 8000, "catalogo", "catalogo"),
        op("c3", "tercero", 7000, "catalogo", "catalogo"),
    ]
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["k1", "c1", "c2"]


def test_un_solo_clip_por_streamer_en_todo_el_envio():
    """Tope 1 por streamer (2026-09-22): si no, un día entero podía salir del mismo canal."""
    opciones = [
        op("k1", "davoo", 500, "kick_reciente"), op("k2", "davoo", 450, "kick_reciente"),
        op("c1", "vegetta777", 9000, "catalogo", "catalogo"),
        op("c2", "vegetta777", 8000, "catalogo", "catalogo"),
    ]
    elegidos = seleccionar(opciones, MEZCLA, AHORA)
    assert [o.clip_id for o in elegidos] == ["k1", "c1"]
    assert len({o.streamer for o in elegidos}) == len(elegidos)


def test_sin_catalogo_los_cupos_vuelven_a_los_otros_grupos():
    opciones = [op("k1", "davoo", 500, "kick_reciente"), op("k2", "spreen", 400, "kick_reciente"),
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


# ---- /buscar -------------------------------------------------------------------


def test_parse_buscar():
    from clips_bot.telegram import parse_buscar

    assert parse_buscar(["davoo", "gol", "3"]) == ("davoo", ("gol",), 3)
    assert parse_buscar(["davoo"]) == ("davoo", (), 7)
    assert parse_buscar(["@DavooXeneize", "gol"]) == ("davooxeneize", ("gol",), 7)
    # un número que NO es el último es parte de lo que se busca, no los días
    assert parse_buscar(["davoo", "12", "de", "octubre"]) == ("davoo", ("12", "de", "octubre"), 7)
    for malo in ([], ["davoo", "gol", "999"], ["davoo", "gol", "0"]):
        with pytest.raises(ValueError):
            parse_buscar(malo)


def test_las_palabras_se_filtran_antes_del_corte_al_top_n():
    """Mismo bug de orden que ya pasó dos veces (evento y Kick): si el filtro de palabras corre
    después del corte al top N, los clips sin las palabras se comen los lugares."""
    s = FakeSession([pagina([
        clip_kick(f"ruido{i}", views=900 - i, horas=48, offset=1000 * i, titulo="jugando")
        for i in range(10)
    ] + [clip_kick("elbueno", views=5, horas=48, offset=99000, titulo="GOLAZO de Boca")]), videos()])
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), DAVOO,
                      Filtros(n_candidatos=3), vistos=set(), ahora=AHORA,
                      palabras_titulo=("golazo",))
    assert [c.id for c in res.candidatos] == ["elbueno"]  # el único con la palabra, aunque tenga 5 vistas
    assert res.descartes["sin las palabras buscadas"] == 10


def test_tiene_palabras_mira_los_dos_titulos():
    from clips_bot.candidates import Clip, tiene_palabras

    def clip(titulo, stream=""):
        return Clip.from_helix({"id": "x", "url": "u", "title": titulo,
                                "created_at": "2026-09-20T00:00:00Z"},
                               "davoo", "", stream, "reciente", "kick", "argentinos")

    assert tiene_palabras(clip("GOLAZO"), ("gol",)) is False          # palabra completa, no prefijo
    assert tiene_palabras(clip("un GOL tremendo"), ("gol",)) is True
    assert tiene_palabras(clip("nada", "NOCHE de GOLES"), ("goles",)) is True  # título del stream
    assert tiene_palabras(clip("Ñandú ácido"), ("nandu",)) is True    # sin tildes
    assert tiene_palabras(clip("cualquier cosa"), ()) is True         # sin palabras pedidas, pasan todos


def test_turnos_de_busqueda_topea_en_dos(tmp_path):
    """Dos búsquedas a la vez como máximo: cada una procesa hasta 3 clips (Whisper + OCR + render),
    y eso calienta la Pi y gasta cuota de Gemini. El turno va en la DB porque puede haber dos
    procesos (el timer y un `atender-telegram` a mano)."""
    conn = db.connect(tmp_path / "x.db")
    assert db.tomar_turno_busqueda(conn, "a", maximo=2)
    assert db.tomar_turno_busqueda(conn, "b", maximo=2)
    assert not db.tomar_turno_busqueda(conn, "c", maximo=2)
    db.soltar_turno_busqueda(conn, "a")
    assert db.tomar_turno_busqueda(conn, "c", maximo=2)
    # un turno colgado (el proceso murió) se suelta solo al vencer
    assert not db.tomar_turno_busqueda(conn, "d", maximo=2)
    assert db.tomar_turno_busqueda(conn, "d", maximo=2, vencimiento_s=0)
    conn.close()


def test_resumen_de_descartes():
    from clips_bot.__main__ import _resumen_descartes
    from clips_bot.candidates import Resultado

    res = Resultado()
    res.descartes["sin las palabras buscadas"] = 40
    res.descartes["muy corto"] = 2
    texto = _resumen_descartes(res)
    assert "Descartes (42)" in texto
    assert texto.index("sin las palabras") < texto.index("muy corto")  # de mayor a menor
    assert _resumen_descartes(Resultado()) == ""
