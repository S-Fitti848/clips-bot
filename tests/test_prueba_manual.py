"""Prueba manual vs API (2026-11-10): un clip por día lo sube Santi a mano; el bot no lo sube, y a la
semana compara el % de vistas del feed de Shorts entre los dos grupos."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot import prueba_manual as pm
from clips_bot.config import load_settings
from clips_bot.telegram import fila_subida, mensaje_textos


def _settings(desde="2026-11-11", dias=7):
    s = load_settings()
    return replace(s, publicacion=replace(s.publicacion, prueba_manual_desde=desde,
                                          prueba_manual_dias=dias))


def _op(clip_id, streamer, **meta):
    return SimpleNamespace(clip_id=clip_id, streamer=streamer, meta=meta)


def test_ventana_y_rotacion():
    assert not pm.activa(date(2026, 11, 10), "2026-11-11", 7)
    assert pm.activa(date(2026, 11, 11), "2026-11-11", 7)
    assert pm.activa(date(2026, 11, 17), "2026-11-11", 7)
    assert not pm.activa(date(2026, 11, 18), "2026-11-11", 7)
    assert not pm.activa(date(2026, 11, 11), "", 7)
    idx = [pm.indice_del_dia(date(2026, 11, d), "2026-11-11", 3) for d in range(11, 18)]
    assert idx == [0, 1, 2, 0, 1, 2, 0]      # cae en los tres horarios, no siempre en el #1


def test_descripcion_lleva_los_hashtags():
    t = {"descripcion": "Davo se ríe.\n\nClip de Davo — kick.com/davooxeneize",
         "hashtags": ["#Davo", "#Shorts"]}
    assert pm.descripcion_para_pegar(t) == ("Davo se ríe.\n\nClip de Davo — kick.com/davooxeneize"
                                            "\n\n#Davo #Shorts")


def test_un_manual_por_dia_rotando_y_sin_partido(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    s = _settings()
    elegidos = [_op("a", "davo"), _op("b", "coker", partido_en_pantalla=True), _op("c", "auron")]

    class Ahora:
        @staticmethod
        def now(tz=None):
            from datetime import datetime
            return datetime(2026, 11, 12, 5, 30, tzinfo=tz)

    monkeypatch.setattr(m, "datetime", type("D", (m.datetime,), {"now": Ahora.now}))
    # 12/11 = día 2 → posición 1, que es un partido: pasa a la siguiente
    assert m._manual_del_dia(conn, s, elegidos, ("13:00", "18:00", "21:30")) == "c"
    assert pm.es_manual(conn, "c") and not pm.es_manual(conn, "a")
    reg = pm.registro(conn)
    assert reg == [{"clip_id": "c", "dia": "2026-11-12", "streamer": "auron", "horario": "21:30",
                    "orden": 3}]
    # el mismo día no marca otro (un /ya o un reintento)
    assert m._manual_del_dia(conn, s, elegidos, ("13:00", "18:00", "21:30")) is None


def test_fuera_de_la_prueba_no_marca(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    s = _settings(desde="2020-01-01")
    assert m._manual_del_dia(conn, s, [_op("a", "davo")], ("13:00",)) is None
    assert pm.registro(conn) == []


def test_el_manual_no_tiene_boton_de_subir(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    pm.anotar(conn, "clipM", date(2026, 11, 11), "davo", "13:00", 1)
    meta = {"clip_id": "clipM", "plataforma": "kick", "textos": {"titulo": "t"}}
    assert m._estado_subida(conn, "clipM", meta) == "manual"
    fila = fila_subida("clipM", "manual")
    textos = [b["text"] for f in fila for b in f]
    assert textos == ["📱 Lo subís vos (prueba manual)"]
    assert all("sub:u" not in b["callback_data"] for f in fila for b in f)


def test_el_callback_de_subir_no_sube_un_manual(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    pm.anotar(conn, "clipM", date(2026, 11, 11), "davo", "13:00", 1)
    monkeypatch.setattr(m, "_meta_de", lambda cid: {"clip_id": cid, "plataforma": "kick",
                                                     "salida": "x.mp4", "textos": {"titulo": "t"}})
    subio = []
    monkeypatch.setattr(m, "_subir", lambda *a, **k: subio.append(1) or [])
    respuestas = []
    tg = SimpleNamespace(answer_callback=lambda cid, texto="", alerta=False: respuestas.append(texto),
                         edit_reply_markup=lambda *a, **k: None, send_message=lambda *a, **k: None)
    cb = {"callback_id": "1", "chat_id": "1", "message_id": 1, "user_id": "8668060171",
          "data": "sub:u:clipM"}
    m._subir_callback(conn, tg, cb, _settings(), {"menu": "sub", "accion": "u", "crudos": ["clipM"]})
    assert not subio and "lo subís vos" in respuestas[0]


def test_mensaje_para_copiar_sin_bloque_de_hashtags():
    t = {"titulo": "Davo se ríe", "descripcion": pm.descripcion_para_pegar(
        {"descripcion": "d", "hashtags": ["#Davo", "#Shorts"]}), "hashtags": [], "credito": ""}
    texto = mensaje_textos(1, "davo", "clipM", "13:00", t)
    assert "#Davo #Shorts" in texto and "<b>Hashtags:</b>" not in texto


class Cliente:
    def __init__(self, fuentes):
        self.f = fuentes

    def _analytics(self, params):
        vid = params["filters"].split("==")[1]
        return [[k, v] for k, v in self.f.get(vid, {}).items()]


def test_comparar_feed_a_mano_contra_api(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    pm.anotar(conn, "m1", date(2026, 11, 11), "davo", "13:00", 1)
    pm.anotar(conn, "m2", date(2026, 11, 12), "coker", "18:00", 2)    # no lo encontró
    conn.execute("INSERT INTO metricas (clip_id, video_id, publicado, actualizado) "
                 "VALUES ('m1', 'VM1', '2026-11-11T16:00:00+00:00', '2026-11-18')")
    conn.commit()
    db.crear_subida(conn, "a1", "rots", "programada", video_id="VA1", publish_at="2026-11-11T21:00:00Z")
    db.crear_subida(conn, "a2", "rots", "programada", video_id="VA2", publish_at="2026-11-13T16:00:00Z")
    db.crear_subida(conn, "viejo", "rots", "programada", video_id="VX", publish_at="2026-11-01T16:00:00Z")
    db.crear_subida(conn, "efe", "pequena_historia", "programada", video_id="VE",
                    publish_at="2026-11-11T15:00:00Z")
    manuales, api, sin = pm.grupos(conn, "2026-11-11", 7)
    assert set(manuales) == {"VM1"} and set(api) == {"VA1", "VA2"}
    assert [r["clip_id"] for r in sin] == ["m2"]
    cli = Cliente({"VM1": {"SHORTS": 800, "SUBSCRIBER": 200},
                   "VA1": {"SHORTS": 3, "YT_CHANNEL": 27}, "VA2": {"YT_CHANNEL": 10}})
    texto = pm.comparar(conn, cli, "2026-11-11", 7, hoy=date(2026, 11, 18))
    assert "A mano: 1 videos, 1.000 vistas, <b>80.0 % del feed" in texto
    assert "Por la API: 2 videos, 40 vistas, <b>7.5 % del feed" in texto
    assert "11-12 coker" in texto and "la API parece ser parte del problema" in texto


def test_comparar_antes_de_arrancar_no_pide_un_rango_al_reves(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.crear_subida(conn, "a1", "rots", "programada", video_id="VA1", publish_at="2026-11-11T21:00:00Z")
    pedidos = []

    class C:
        def _analytics(self, params):
            pedidos.append((params["startDate"], params["endDate"]))
            return []

    pm.comparar(conn, C(), "2026-11-11", 7, hoy=date(2026, 11, 10))
    assert pedidos == [("2026-11-11", "2026-11-11")]


def test_informe_una_sola_vez_desde_el_dia_8(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert not pm.toca_informe(conn, date(2026, 11, 17), "2026-11-11", 7)
    assert pm.toca_informe(conn, date(2026, 11, 18), "2026-11-11", 7)
    db.set_valor(conn, pm.INFORME, "2026-11-18")
    assert not pm.toca_informe(conn, date(2026, 11, 19), "2026-11-11", 7)


def test_settings_tiene_la_prueba():
    cfg = load_settings().publicacion
    assert cfg.prueba_manual_desde == "2026-11-11" and cfg.prueba_manual_dias == 7
