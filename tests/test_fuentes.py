"""Fuentes reciente y catálogo, score de velocidad, mismo momento, mezcla por cupos y
depende_de_fecha. Todo con respuestas simuladas de Twitch y Gemini (no hay credenciales)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from test_twitch_candidates import Resp, cliente, helix_clip

from clips_bot import db
from clips_bot.candidates import Clip, agrupar_momentos, buscar_candidatos, buscar_catalogo
from clips_bot.config import Catalogo, Filtros, Seleccion, Settings, Streamer, Textos
from clips_bot.process import fuente_por_antiguedad
from clips_bot.seleccion import Opcion, score_reciente, seleccionar
from clips_bot.textos import armar_prompt, parsear, validar

AHORA = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
UNO = [Streamer("uno", fuentes=("reciente",), cita="clipeen tranqui", fuente="panel")]
UNO_CAT = [Streamer("uno", fuentes=("catalogo",), cita="clipeen tranqui", fuente="panel")]
KICK = [Streamer("davoo", plataforma="kick", fuentes=("reciente",), grupo="kick_reciente", experimento=True)]


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def hace(horas: float) -> str:
    return iso(AHORA - timedelta(hours=horas))


def vod(id, views, horas=48.0, video="v1", offset=None, duration=30.0):
    return {**helix_clip(id, views=views, created=hace(horas), duration=duration),
            "video_id": video, "vod_offset": offset}


def fijos(extra: dict | None = None) -> dict:
    """Respuestas de Helix que no cambian entre tests (usuario, juegos, VODs)."""
    return {
        "/users": Resp(200, {"data": [{"login": "uno", "id": "1"}]}),
        "/games": Resp(200, {"data": [{"id": "1", "name": "Minecraft"}]}),
        "/videos": Resp(200, {"data": [{"id": "v1", "title": "stream normal"}]}),
        **(extra or {}),
    }


# ---- velocidad y mismo momento --------------------------------------------------------


def test_score_reciente_achata_las_vistas_y_pondera_duplicados():
    # 0 vistas y 3 personas que clipearon (2,0) compite con 500 vistas sin duplicados (3,7)
    assert score_reciente(0, 1, 0.5) == 1.0
    assert score_reciente(0, 3, 0.5) == 2.0
    assert score_reciente(500, 1, 0.5) == pytest.approx(3.70, abs=0.01)
    assert score_reciente(50_000, 1, 0.5) == pytest.approx(5.70, abs=0.01)
    # duplicar las vistas suma poco; un duplicado más suma bastante
    assert score_reciente(20, 1, 0.5) < score_reciente(10, 2, 0.5)
    assert score_reciente(0, 1, 0.5) > 0  # un clip sin vistas nunca queda en cero


def test_agrupar_momentos_ventana_alrededor_del_mas_visto():
    def c(id, views, video, offset):
        return Clip.from_helix(vod(id, views, video=video, offset=offset), "uno")

    clips = [
        c("a", 100, "v1", 1000),
        c("b", 50, "v1", 1040),  # a 40 s de "a" → mismo momento
        c("c", 30, "v1", 1100),  # a 100 s de "a" (aunque a 60 de "b") → otro momento
        c("d", 20, "v2", 1000),  # otro VOD
        c("e", 10, "", None),  # sin VOD: solo
    ]
    grupos = [[x.id for x in g] for g in agrupar_momentos(clips, 60)]
    assert grupos == [["a", "b"], ["c"], ["d"], ["e"]]


def test_reciente_un_clip_por_momento_y_los_duplicados_pesan():
    c, _ = cliente(fijos({"/clips": Resp(200, {"data": [
        vod("m1", 4, offset=500),
        vod("m2", 2, offset=520),
        vod("m3", 1, offset=470, duration=5),  # no pasa (muy corto) pero cuenta para el momento
        vod("solo", 20, offset=3000),
        vod("sin_vistas", 0, offset=9000),
    ]})}))
    res = buscar_candidatos(c, UNO, Filtros(), vistos=set(), ahora=AHORA, seleccion=Seleccion(peso_momento=0.5))

    # m1: 2.0 × 1.70 = 3.40  >  solo: 1 × 2.32  >  sin_vistas: 1 × 1.0 (igual compite)
    assert [(x.id, x.clips_mismo_momento) for x in res.candidatos] == [("m1", 3), ("solo", 1), ("sin_vistas", 1)]
    assert res.descartes["mismo momento"] == 1  # m2 (m3 ya estaba descartado por corto)
    assert res.descartes["muy corto"] == 1


def test_reciente_descarta_los_de_menos_de_24_h_sin_marcarlos():
    c, _ = cliente(fijos({"/clips": Resp(200, {"data": [
        vod("maduro", 5, horas=25, offset=100),
        vod("bebe", 500, horas=10, offset=5000),  # muchas vistas, pero todavía no cumplió 24 h
    ]})}))
    res = buscar_candidatos(c, UNO, Filtros(antiguedad_min_h=24), vistos=set(), ahora=AHORA,
                            seleccion=Seleccion())
    assert [x.id for x in res.candidatos] == ["maduro"]
    assert res.descartes["muy nuevo (no llegó a antiguedad_min_h; se reevalúa mañana)"] == 1
    assert [x.id for x in res.costream] == []  # no se marca en la DB: vuelve mañana


def test_ventana_reciente_de_7_dias():
    c, s = cliente(fijos({"/clips": Resp(200, {"data": [vod("a", 10, horas=100, offset=1)]})}))
    buscar_candidatos(c, UNO, Filtros(ventana_horas=168), vistos=set(), ahora=AHORA, seleccion=Seleccion())
    p = dict([x for x in s.calls if x[0] == "/clips"][0][1])
    assert p["started_at"] == iso(AHORA - timedelta(hours=168))


# ---- catálogo con cursor en la DB -------------------------------------------------------

CAT = Catalogo(antiguedad_min_dias=7, antiguedad_max_dias=1095, min_vistas=500, n_candidatos=2,
               por_pagina=3, max_paginas=3)


def pagina(clips, cursor=None):
    return Resp(200, {"data": clips, "pagination": {"cursor": cursor} if cursor else {}})


def viejo(id, views, dias=200):
    return {**helix_clip(id, views=views, created=iso(AHORA - timedelta(days=dias))), "video_id": ""}


def params(llamada) -> dict:
    return dict(llamada[1])


def llamadas_clips(s):
    return [params(x) for x in s.calls if x[0] == "/clips"]


def test_catalogo_guarda_cursor_y_la_ventana_y_sigue_donde_quedo(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    c, s = cliente(fijos({"/clips": [
        pagina([viejo("a", 9000), viejo("b", 8000)], cursor="c1"),  # corrida 1: 2 que pasan → corta
        pagina([viejo("c", 7000), viejo("d", 6000)], cursor="c2"),  # corrida 2
    ]}))

    res = buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos=set(), ahora=AHORA)
    assert [x.id for x in res.catalogo] == ["a", "b"]
    assert all(x.fuente == "catalogo" for x in res.catalogo)
    p1 = llamadas_clips(s)[0]
    assert "after" not in p1
    assert p1["started_at"] == iso(AHORA - timedelta(days=1095))
    assert p1["ended_at"] == iso(AHORA - timedelta(days=7))
    cursor, desde, hasta = db.get_cursor(conn, "uno")
    assert cursor == "c1"

    # Al otro día: usa el cursor y la MISMA ventana (el cursor solo vale para la misma consulta).
    res = buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos={"a", "b"}, ahora=AHORA + timedelta(days=1))
    p2 = llamadas_clips(s)[1]
    assert p2["after"] == "c1"
    assert (p2["started_at"], p2["ended_at"]) == (p1["started_at"], p1["ended_at"])
    assert [x.id for x in res.catalogo] == ["c", "d"]
    assert db.get_cursor(conn, "uno")[0] == "c2"


def test_catalogo_pagina_hasta_juntar_y_filtra_min_vistas_y_vistos(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    c, s = cliente(fijos({"/clips": [
        pagina([viejo("ya", 9000), viejo("poco", 100), viejo("ok1", 5000)], cursor="p2"),
        pagina([viejo("ok2", 4000), viejo("ok3", 3000)], cursor="p3"),
    ]}))
    res = buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos={"ya"}, ahora=AHORA)
    assert [x.id for x in res.catalogo] == ["ok1", "ok2"]  # top 2 por vistas absolutas
    assert res.descartes_catalogo["ya visto"] == 1
    assert res.descartes_catalogo["pocas vistas"] == 1  # 100 < min_vistas 500 del catálogo
    assert res.descartes_catalogo["fuera del top N"] == 1
    assert len(llamadas_clips(s)) == 2  # paró al juntar n_candidatos
    assert db.get_cursor(conn, "uno")[0] == "p3"


def test_catalogo_ciclo_agotado_borra_cursor_y_el_siguiente_usa_ventana_nueva(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    db.set_cursor(conn, "uno", "ultimo", iso(AHORA - timedelta(days=1100)), iso(AHORA - timedelta(days=9)))
    c, s = cliente(fijos({"/clips": [pagina([viejo("z", 900)]), pagina([viejo("y", 800)])]}))

    res = buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos=set(), ahora=AHORA)
    assert res.descartes_catalogo["ciclo agotado"] == 1
    assert db.get_cursor(conn, "uno") is None

    buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos={"z"}, ahora=AHORA + timedelta(days=2))
    p = llamadas_clips(s)[1]
    assert "after" not in p
    assert p["ended_at"] == iso(AHORA + timedelta(days=2) - timedelta(days=7))


def test_catalogo_cursor_rechazado_reinicia_el_ciclo(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    db.set_cursor(conn, "uno", "vencido", iso(AHORA - timedelta(days=1100)), iso(AHORA - timedelta(days=9)))
    c, s = cliente(fijos({"/clips": [
        Resp(400, {"message": "invalid cursor"}),
        pagina([viejo("a", 9000), viejo("b", 8000)], cursor="nuevo"),
    ]}))
    res = buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos=set(), ahora=AHORA)
    assert res.descartes_catalogo["cursor reiniciado"] == 1
    p = llamadas_clips(s)
    assert p[0]["after"] == "vencido" and "after" not in p[1]
    assert p[1]["ended_at"] == iso(AHORA - timedelta(days=7))  # ventana de hoy, no la vieja
    assert [x.id for x in res.catalogo] == ["a", "b"]
    assert db.get_cursor(conn, "uno")[0] == "nuevo"


def test_listar_no_mueve_el_cursor(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    c, _ = cliente(fijos({"/clips": [pagina([viejo("a", 9000), viejo("b", 8000)], cursor="c1")] * 2}))
    buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos=set(), ahora=AHORA, guardar_cursor=False)
    assert db.get_cursor(conn, "uno") is None  # listar no quema la página
    buscar_catalogo(c, UNO_CAT, Filtros(), CAT, conn, vistos=set(), ahora=AHORA)
    assert db.get_cursor(conn, "uno")[0] == "c1"


def test_catalogo_sin_cursor_y_error_de_twitch_se_propaga(tmp_path):
    from clips_bot.twitch import TwitchError

    c, _ = cliente(fijos({"/clips": Resp(400, {"message": "bad"})}))
    with pytest.raises(TwitchError):
        buscar_catalogo(c, UNO_CAT, Filtros(), CAT, db.connect(tmp_path / "c.db"), vistos=set(), ahora=AHORA)


# ---- mezcla por cupos ---------------------------------------------------------------------


def op(id, streamer, vistas, horas, fuente="reciente", momento=1):
    return Opcion(id, streamer, vistas, AHORA - timedelta(hours=horas), titulo=id, fuente=fuente,
                  clips_mismo_momento=momento)


MEZCLA = Seleccion(mezcla={"reciente": 1, "catalogo": 2}, peso_momento=0.5,
                   max_por_streamer=2, empate_pct={"reciente": 0.0, "catalogo": 0.0})


def test_mezcla_1_reciente_y_2_catalogo_cada_uno_en_su_cupo():
    opciones = [
        op("cat_1", "a", 500_000, 24 * 400, "catalogo"),
        op("cat_2", "b", 300_000, 24 * 200, "catalogo"),
        op("cat_3", "g", 200_000, 24 * 100, "catalogo"),
        op("r1", "c", 1000, 30),  # el mejor reciente se lleva el único cupo reciente
        op("r2", "d", 400, 30),
    ]
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["r1", "cat_1", "cat_2"]


def test_mismo_momento_gana_el_cupo_reciente():
    opciones = [op("r_visto", "c", 1000, 30), op("r_dup", "d", 400, 30, momento=4)]
    # r_dup: 2.5 × (1 + log10(401)) = 9.0  >  r_visto: 1 × (1 + log10(1001)) = 4.0
    # (sin catálogo, los 2 cupos de catálogo vuelven a recientes: entran los dos, r_dup primero)
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["r_dup", "r_visto"]


def test_fallback_en_los_dos_sentidos():
    # sin recientes: el cupo pasa al catálogo
    solo_cat = [op(f"cat_{i}", str(i), 90_000 - i, 24 * 60, "catalogo") for i in range(4)]
    assert [o.clip_id for o in seleccionar(solo_cat, MEZCLA, AHORA)] == ["cat_0", "cat_1", "cat_2"]
    # sin catálogo: los cupos de catálogo pasan a recientes
    solo_rec = [op(f"r{i}", str(i), 100 - i, 30) for i in range(4)]
    assert [o.clip_id for o in seleccionar(solo_rec, MEZCLA, AHORA)] == ["r0", "r1", "r2"]
    # catálogo con un solo clip: el cupo que sobra vuelve a recientes
    mixto = [op("cat", "a", 90_000, 24 * 60, "catalogo"), op("r1", "b", 100, 30), op("r2", "c", 90, 30)]
    assert [o.clip_id for o in seleccionar(mixto, MEZCLA, AHORA)] == ["r1", "r2", "cat"]


def test_empate_pct_es_por_fuente():
    llamados = []

    def invertir(grupo):
        llamados.append(grupo[0].fuente)
        return list(reversed(grupo))

    cfg = Seleccion(mezcla={"reciente": 1, "catalogo": 1}, empate_pct={"reciente": 0.03, "catalogo": 0.10})
    opciones = [
        # recientes: scores 3.30 y 3.26 (diferencia 1,2 % < 3 %) → empate
        op("r1", "a", 199, 30), op("r2", "b", 180, 30),
        # catálogo: 100.000 y 80.000 (20 % > 10 %) → no hay empate
        op("c1", "c", 100_000, 24 * 60, "catalogo"), op("c2", "d", 80_000, 24 * 60, "catalogo"),
    ]
    elegidos = [o.clip_id for o in seleccionar(opciones, cfg, AHORA, invertir)]
    assert llamados == ["reciente"]  # solo desempató la fuente reciente
    assert elegidos == ["r2", "c1"]


def test_tope_por_streamer_cuenta_entre_las_dos_fuentes():
    opciones = [op("r1", "a", 1000, 30), op("r2", "a", 900, 30),
                op("cat_a", "a", 90_000, 24 * 60, "catalogo"), op("cat_b", "b", 1_000, 24 * 60, "catalogo"),
                op("cat_c", "h", 900, 24 * 60, "catalogo")]
    # "a" ya puso r1 (cupo reciente) + cat_a; el tercero de "a" no entra
    assert [o.clip_id for o in seleccionar(opciones, MEZCLA, AHORA)] == ["r1", "cat_a", "cat_b"]


def test_config_de_mezcla_se_valida(tmp_path):
    from clips_bot.config import ConfigError, load_settings

    ok = tmp_path / "ok.yaml"
    ok.write_text("seleccion:\n  mezcla:\n    reciente: 3\n", encoding="utf-8")
    s = load_settings(ok)
    assert s.seleccion.mezcla == {"reciente": 3} and s.seleccion.n == 3
    # los nombres de grupo son libres (salen de streamers.yaml); los cupos sí tienen que ser enteros ≥ 0
    libre = tmp_path / "libre.yaml"
    libre.write_text("seleccion:\n  mezcla:\n    kick_reciente: 1\n    evento: 2\n", encoding="utf-8")
    assert load_settings(libre).seleccion.mezcla == {"kick_reciente": 1, "evento": 2}
    malo = tmp_path / "malo.yaml"
    malo.write_text("seleccion:\n  mezcla:\n    evento: -1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(malo)


def test_fuente_por_antiguedad_para_urls_manuales():
    cfg = Settings(filtros=Filtros())
    assert fuente_por_antiguedad(AHORA - timedelta(days=8), cfg, AHORA) == "catalogo"
    assert fuente_por_antiguedad(AHORA - timedelta(days=2), cfg, AHORA) == "reciente"
    assert fuente_por_antiguedad(None, cfg, AHORA) == "reciente"


# ---- depende_de_fecha -----------------------------------------------------------------------

BASE = {"titulo": "No puede creer lo que pasó", "descripcion": "Pasa algo.", "hashtags": ["#Shorts", "#a", "#b"],
        "gancho": "reaccion"}


def test_depende_de_fecha_es_obligatorio_y_booleano():
    cfg = Textos()
    assert any("depende_de_fecha" in e for e in validar(BASE, cfg))  # falta
    assert any("true o false" in e for e in validar({**BASE, "depende_de_fecha": "true"}, cfg))
    assert validar({**BASE, "depende_de_fecha": True}, cfg) == []
    t, _ = parsear(json.dumps({**BASE, "depende_de_fecha": True}), cfg, "x", "x")
    assert t.depende_de_fecha is True


def test_prompt_lleva_la_fecha_del_clip():
    p = armar_prompt("X", "Just Chatting", "t", 30, "hola", Textos(), "2026-09-20")
    assert "Fecha del clip: 2026-09-20" in p and "depende_de_fecha" in p


class FakeGemini:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)

    def json(self, sistema, prompt, schema, temperatura=0.7):
        return self.respuestas.pop(0)


def meta(clip_id, textos=None):
    return {"clip_id": clip_id, "streamer": "uno", "canal": "Uno", "categoria": "Just Chatting",
            "titulo_twitch": "t", "duracion_s": 30, "transcripcion": "hola", "creado": "2026-09-20T10:00:00+00:00",
            "textos": textos}


def test_seleccionar_completa_textos_y_descarta_los_que_dependen_de_la_fecha(tmp_path):
    from clips_bot.__main__ import completar_textos

    viejos = {"titulo": "t", "descripcion": "d", "hashtags": ["#Shorts"], "gancho": "reaccion", "credito": "c"}
    opciones = [
        Opcion("fecha", "uno", 10, AHORA, meta=meta("fecha")),  # Gemini dice que depende de la fecha
        Opcion("ok", "uno", 10, AHORA, meta=meta("ok")),  # Gemini dice que no
        Opcion("ya", "uno", 10, AHORA, meta=meta("ya", {**viejos, "depende_de_fecha": False})),  # no se llama
        Opcion("legado", "uno", 10, AHORA, meta=meta("legado", viejos)),  # textos de antes de v0.4: se regenera
    ]
    gemini = FakeGemini([json.dumps({**BASE, "depende_de_fecha": True}),
                         json.dumps({**BASE, "depende_de_fecha": False}),
                         json.dumps({**BASE, "depende_de_fecha": True})])
    descartados = []
    listas = completar_textos(opciones, gemini, Settings(filtros=Filtros()), tmp_path,
                              lambda cid, motivo: descartados.append((cid, motivo)))

    assert [o.clip_id for o in listas] == ["ok", "ya"]
    assert descartados == [("fecha", "depende_de_fecha"), ("legado", "depende_de_fecha")]
    assert json.loads((tmp_path / "ok.json").read_text(encoding="utf-8"))["textos"]["depende_de_fecha"] is False
    assert gemini.respuestas == []

    sin_gemini = completar_textos([Opcion("x", "uno", 1, AHORA, meta=meta("x"))], None,
                                  Settings(filtros=Filtros()), tmp_path, lambda *a: None)
    assert sin_gemini == []
