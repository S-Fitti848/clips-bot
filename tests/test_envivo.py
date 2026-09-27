"""Modo en vivo: agrupar momentos, elegir clip, no repetir, tope por hora y los tiempos.

Sin red ni video: los clientes de Twitch/Kick y procesar() se reemplazan por fakes.
"""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import clips_bot.__main__ as m
from clips_bot import db, envivo
from clips_bot.candidates import Clip
from clips_bot.config import EnVivo, Filtros, Streamer, load_settings

T0 = datetime(2026, 9, 27, 20, 0, tzinfo=timezone.utc)
CFG = EnVivo()
FILTROS = Filtros(antiguedad_min_h=24, duracion_min_s=15, duracion_max_s=60)


def clip(i, seg=0, creador=None, login="spreen", dur=30, vistas=0, video="", offset=None,
         plataforma="kick", titulo="jaja", stream=""):
    return Clip(id=f"c{i}", url=f"https://kick.com/{login}/clips/c{i}", broadcaster_login=login,
                broadcaster_name=login, title=titulo, view_count=vistas, duration=dur, language="",
                created_at=T0 + timedelta(seconds=seg), game_id="", game_name="Just Chatting",
                vod_offset=offset, video_id=video, stream_title=stream, plataforma=plataforma,
                creator_id=creador or f"u{i}")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


# ---- agrupar ------------------------------------------------------------------

def test_tres_creadores_distintos_a_90_s_son_un_momento():
    ms = envivo.agrupar_en_vivo([clip(1, 0), clip(2, 40), clip(3, 80)], CFG)
    assert len(ms) == 1 and len(ms[0].creadores) == 3
    assert ms[0].momento == T0 and ms[0].umbral == T0 + timedelta(seconds=80)


def test_el_mismo_creador_tres_veces_cuenta_uno():
    ms = envivo.agrupar_en_vivo([clip(1, 0, "u1"), clip(2, 10, "u1"), clip(3, 20, "u1"),
                                 clip(4, 30, "u2")], CFG)
    assert ms == []


def test_fuera_de_la_ventana_no_se_juntan():
    assert envivo.agrupar_en_vivo([clip(1, 0), clip(2, 100), clip(3, 200)], CFG) == []


def test_canales_distintos_no_se_juntan():
    ms = envivo.agrupar_en_vivo([clip(1, 0, login="a"), clip(2, 5, login="b"),
                                 clip(3, 10, login="c")], CFG)
    assert ms == []


def test_twitch_con_vod_offset_usa_el_offset_y_no_la_hora():
    # Creados con 10 min de diferencia (se clipeó tarde desde el VOD) pero del mismo segundo del VOD.
    cs = [clip(i, seg=600 * i, video="v1", offset=1000 + i, plataforma="twitch") for i in range(3)]
    assert len(envivo.agrupar_en_vivo(cs, CFG)) == 1
    lejos = [clip(i, seg=0, video="v1", offset=1000 + 100 * i, plataforma="twitch") for i in range(3)]
    assert envivo.agrupar_en_vivo(lejos, CFG) == []


def test_el_momento_mas_clipeado_sale_primero():
    a = [clip(i, i) for i in range(3)]                    # 3 creadores
    b = [clip(10 + i, 1000 + i) for i in range(5)]        # 5 creadores
    ms = envivo.agrupar_en_vivo(a + b, CFG)
    assert [len(x.creadores) for x in ms] == [5, 3]


# ---- elegir -------------------------------------------------------------------

def test_elegir_saltea_la_espera_de_24_h_pero_no_los_filtros():
    m_ = envivo.agrupar_en_vivo([clip(1, 0, dur=120, vistas=9), clip(2, 5, vistas=3),
                                 clip(3, 10, vistas=1)], CFG)[0]
    elegido, desc = envivo.elegir(m_, FILTROS, set(), None)
    assert elegido.id == "c2"            # el más visto que pasa (c1 dura 120 s)
    assert desc["muy largo"] == 1


def test_elegir_aplica_programa_de_terceros_con_el_titulo_del_stream():
    st = Streamer("spreen", "kick", experimento=True, palabras_programa=("412",))
    cs = [clip(i, i, stream="412 con amigos") for i in range(3)]
    elegido, desc = envivo.elegir(envivo.agrupar_en_vivo(cs, CFG)[0], FILTROS, set(), st)
    assert elegido is None and desc["programa_terceros"] == 3


# ---- detectar (fakes de las APIs) -------------------------------------------------

class FakeKick:
    def __init__(self, vivos, clips):
        self.vivos, self.clips, self.llamadas = vivos, clips, []

    def get_livestream(self, slug):
        self.llamadas.append(slug)
        return self.vivos.get(slug)

    def get_clips_desde(self, slug, desde, max_paginas=5):
        return [c for c in self.clips.get(slug, [])]


class FakeTwitch:
    def __init__(self, vivos, clips):
        self.vivos, self.clips = vivos, clips

    def get_streams(self, logins):
        return {l: v for l, v in self.vivos.items() if l in logins}

    def get_clips(self, bid, desde, hasta, maximo):
        return self.clips.get(bid, [])


def _kick_crudo(i, seg, ls="L1"):
    return {"id": f"k{i}", "title": "uh", "view_count": 0, "duration": 30,
            "created_at": (T0 + timedelta(seconds=seg)).isoformat().replace("+00:00", "Z"),
            "category": {"name": "Just Chatting"}, "channel": {"slug": "spreen"},
            "livestream_id": ls, "vod_starts_at": 0, "creator": {"id": f"u{i}"}}


def test_detectar_solo_mira_a_los_permitidos_y_no_excluidos():
    sts = [Streamer("spreen", "kick", experimento=True), Streamer("coscu", "kick", experimento=True),
           Streamer("sinpermiso", "kick")]
    k = FakeKick({"spreen": {"id": "L1", "titulo": "t", "juego": "", "inicio": "", "espectadores": 1}},
                 {"spreen": [_kick_crudo(i, i * 10) for i in range(3)]})
    v = envivo.detectar(sts, CFG, {"coscu": "reclamo"}, kick=k, ahora=T0 + timedelta(minutes=1))
    assert k.llamadas == ["spreen"]
    assert v.vivos == {"spreen": "kick"} and len(v.momentos) == 1
    assert v.momentos[0].clips[0].stream_title == "t"   # el título del stream llega a los filtros


def test_detectar_twitch_en_lote():
    sts = [Streamer("rivers_gg", "twitch", experimento=True, grupo="evento")]
    crudos = [{"id": f"t{i}", "url": f"https://clips.twitch.tv/t{i}", "title": "x", "view_count": 1,
               "duration": 30, "language": "es", "game_id": "1", "video_id": "", "vod_offset": None,
               "creator_id": f"u{i}",
               "created_at": (T0 + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")}
              for i in range(4)]
    tw = FakeTwitch({"rivers_gg": {"user_id": "99", "titulo": "Minecraft!", "juego": "Minecraft",
                                   "inicio": "", "espectadores": 5}}, {"99": crudos})
    v = envivo.detectar(sts, CFG, {}, twitch=tw, ahora=T0 + timedelta(minutes=2))
    assert len(v.momentos) == 1 and len(v.momentos[0].creadores) == 4
    assert v.momentos[0].clips[0].grupo == "evento"


# ---- registrar: no repetir, tope, sin_clip ------------------------------------------

def _vuelta(*momentos):
    return envivo.Vuelta(momentos=list(momentos))


def _momento(base, n=3, login="spreen", **kw):
    return envivo.agrupar_en_vivo([clip(base + i, base + i, login=login, **kw) for i in range(n)],
                                  CFG)[0]


def test_nunca_dos_del_mismo_momento(conn):
    m1 = _momento(0)
    envivo.registrar(conn, _vuelta(m1), CFG, FILTROS, [], "chat", ahora=T0)
    # la vuelta siguiente ve el mismo momento, ahora con un clip más
    m1b = _momento(0, n=4)
    assert envivo.registrar(conn, _vuelta(m1b), CFG, FILTROS, [], "chat",
                            ahora=T0 + timedelta(minutes=2)) == []
    assert len(db.alertas(conn)) == 1


def test_tope_por_hora_se_anota_como_tope(conn):
    cfg = replace(CFG, alertas_por_hora=2)
    for i in range(3):
        envivo.registrar(conn, _vuelta(_momento(1000 * i)), cfg, FILTROS, [], "chat",
                         ahora=T0 + timedelta(minutes=i))
    assert [a["estado"] for a in db.alertas(conn)] == ["pendiente", "pendiente", "tope"]
    # pasada la hora, vuelve a haber lugar
    envivo.registrar(conn, _vuelta(_momento(9000)), cfg, FILTROS, [], "chat",
                     ahora=T0 + timedelta(minutes=70))
    assert db.alertas(conn)[-1]["estado"] == "pendiente"


def test_sin_clip_se_reevalua_cuando_aparece_uno_que_pasa(conn):
    largo = _momento(0, dur=120)
    envivo.registrar(conn, _vuelta(largo), CFG, FILTROS, [], "chat", ahora=T0)
    a = db.alertas(conn)[0]
    assert a["estado"] == "sin_clip" and "muy largo" in a["motivo"]
    # en la vuelta siguiente alguien hizo uno de 30 s del mismo momento
    nuevo = envivo.agrupar_en_vivo([clip(i, i, dur=120) for i in range(3)] + [clip(7, 5, dur=30)],
                                   CFG)[0]
    envivo.registrar(conn, _vuelta(nuevo), CFG, FILTROS, [], "chat", ahora=T0 + timedelta(minutes=2))
    a = db.alertas(conn)
    assert len(a) == 1 and a[0]["estado"] == "pendiente" and a[0]["clip_id"] == "c7"


def test_las_pendientes_viejas_se_vencen(conn):
    envivo.registrar(conn, _vuelta(_momento(0)), CFG, FILTROS, [], "chat", ahora=T0)
    assert envivo.vencer(conn, CFG, ahora=T0 + timedelta(minutes=CFG.vencimiento_min + 1)) == 1
    assert db.alertas(conn)[0]["estado"] == "vencida" and envivo.siguiente(conn) is None


def test_resumen_mide_cada_tramo():
    a = {"estado": "entregada", "motivo": None, "momento": "2026-09-27T20:00:00Z",
         "umbral": "2026-09-27T20:01:00Z", "detectado": "2026-09-27T20:04:00Z",
         "inicio": "2026-09-27T20:05:00Z", "entregado": "2026-09-27T20:09:00Z"}
    txt = envivo.resumen([a])
    assert "entregada 1" in txt
    for tramo, minutos in [("momento → umbral", "1.0"), ("umbral → detectado", "3.0"),
                           ("detectado → inicio", "1.0"), ("inicio → entregado", "4.0"),
                           ("momento → entregado", "9.0")]:
        linea = next(l for l in txt.splitlines() if tramo in l)
        assert minutos in linea


# ---- el comando y la vuelta de la escucha ---------------------------------------------

def test_envivo_on_off_y_estado(conn):
    cfg = load_settings()
    assert "prendido" in m._envivo(conn, "-100", ["on"], cfg)
    assert db.envivo_chat(conn) == "-100"
    assert "prendido" in m._envivo(conn, "-100", [], cfg)
    assert "apagado" in m._envivo(conn, "-100", ["off"], cfg)
    assert db.envivo_chat(conn) is None


def test_apagado_no_consulta_nada(conn, monkeypatch):
    monkeypatch.setattr(m, "_envivo_detectar", lambda *a: pytest.fail("no debería detectar"))
    m._envivo_tick(conn, None, load_settings(), {})


def test_cada_plataforma_con_su_intervalo(conn, monkeypatch):
    llamadas = []
    monkeypatch.setattr(m, "_envivo_detectar", lambda c, s, chat, p: llamadas.append(tuple(p)))
    monkeypatch.setattr(m, "_envivo_procesar", lambda *a: None)
    db.prender_envivo(conn, "1")
    cfg, reloj = load_settings(), {}
    for t in (0, 60, 130, 250, 310):
        m._envivo_tick(conn, None, cfg, reloj, ahora=lambda t=t: 1_000_000 + t)
    assert llamadas == [("twitch", "kick"), ("kick",), ("kick",), ("twitch",)]


class FakeTG:
    def __init__(self):
        self.mensajes = []


def _pendiente(conn, **kw):
    envivo.registrar(conn, _vuelta(_momento(0)), CFG, FILTROS, [], "chat",
                     ahora=datetime.now(timezone.utc))
    return db.alertas(conn)[0]


def test_la_alerta_se_procesa_con_prioridad_y_llega_con_subir_ya(conn, monkeypatch, tmp_path):
    from clips_bot import process

    monkeypatch.setattr(process, "READY_DIR", tmp_path)
    alerta = _pendiente(conn)
    llamado = {}

    elegido = alerta["clip_id"]

    def falso_procesar(url, settings, streamers, **kw):
        llamado.update(kw, url=url)
        (tmp_path / f"{elegido}.json").write_text(
            json.dumps({"clip_id": elegido, "textos": {"titulo": "x"}}))
        return process.Resultado(clip_id=elegido, tiempos={"render": 40.0, "total": 90.0})

    enviados = []
    monkeypatch.setattr(process, "procesar", falso_procesar)
    monkeypatch.setattr(m, "_streamers", lambda conn=None: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)
    monkeypatch.setattr(m, "enviar_clip",
                        lambda tg, chat, conn_, cid, meta, n, h, encabezado="": enviados.append(
                            (chat, cid, encabezado)) or 1)
    m._envivo_procesar(conn, FakeTG(), load_settings())

    assert llamado["url"] == alerta["url"] and llamado["permitir_fecha"] is True
    assert enviados and enviados[0][0] == "chat" and "SUBIR YA" in enviados[0][2]
    a = db.alertas(conn)[0]
    assert a["estado"] == "entregada" and a["inicio"] and a["entregado"]
    assert a["tiempos"]["render"] == 40.0
    # los otros clips del momento quedan vistos: mañana no salen en la corrida diaria
    assert {"c0", "c1", "c2"} - {elegido} <= db.ids_vistos(conn)
    assert db.hay_trabajo_pesado(conn) is None      # soltó el turno


def test_con_el_turno_ocupado_espera_y_no_procesa(conn, monkeypatch):
    _pendiente(conn)
    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1)
    monkeypatch.setattr(m, "_procesar_alerta", lambda *a: pytest.fail("no debería procesar"))
    m._envivo_procesar(conn, FakeTG(), load_settings())
    assert db.alertas(conn)[0]["estado"] == "pendiente"


def test_sin_textos_no_se_manda_porque_no_paso_el_filtro_de_tono(conn, monkeypatch, tmp_path):
    from clips_bot import process

    monkeypatch.setattr(process, "READY_DIR", tmp_path)
    _pendiente(conn)

    def falso_procesar(url, settings, streamers, **kw):
        (tmp_path / "cx.json").write_text(json.dumps({"clip_id": "cx", "textos": None}))
        return process.Resultado(clip_id="cx")

    monkeypatch.setattr(process, "procesar", falso_procesar)
    monkeypatch.setattr(m, "_streamers", lambda conn=None: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)
    monkeypatch.setattr(m, "enviar_clip", lambda *a, **k: pytest.fail("no debería mandar"))
    m._envivo_procesar(conn, FakeTG(), load_settings())
    a = db.alertas(conn)[0]
    assert a["estado"] == "descartada" and "tono" in a["motivo"]
