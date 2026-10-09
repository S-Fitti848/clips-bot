"""La demo para la auditoría de YouTube (2026-10-08): /lang en|es, /demo (subida de prueba aunque la
subida esté apagada, programada para mañana), /subidas y ❌ con videos.update, /metricas y la
búsqueda pública en inglés."""
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

import clips_bot.__main__ as m
from clips_bot import db, idioma, pego
from clips_bot.config import load_settings
from clips_bot.telegram import fila_subida, mensaje_textos


@pytest.fixture(autouse=True)
def castellano():
    idioma.poner("es")
    yield
    idioma.poner("es")


class TG:
    def __init__(self):
        self.mensajes, self.respuestas, self.teclados, self.videos = [], [], [], []

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def send_video(self, chat, path, caption="", **kw):
        self.videos.append((path, caption))
        return {"video": {"file_id": "F"}}

    def send_document(self, *a, **k):
        pass

    def answer_callback(self, cid, texto="", alerta=False):
        self.respuestas.append(texto)

    def edit_reply_markup(self, chat, msg, teclado):
        self.teclados.append(teclado)

    def edit_message(self, chat, msg, texto, teclado=None):
        self.mensajes.append((texto, teclado))


def test_lang_cambia_y_queda_en_la_db(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert "English" in m._lang(conn, ["en"]) and idioma.actual() == "en"
    idioma.poner("es")
    assert idioma.cargar(conn) == "en"           # la escucha lo relee en cada vuelta
    assert "castellano" in m._lang(conn, ["es"]) and idioma.cargar(conn) == "es"
    assert "/lang en" in m._lang(conn, [])


def test_mensajes_en_ingles():
    idioma.poner("en")
    t = mensaje_textos(1, "Clips Bot", "demo_1", "13:00", {"titulo": "T", "descripcion": "D",
                                                          "hashtags": ["#Shorts"], "credito": ""})
    assert "Title:" in t and "Description:" in t and "Upload as PRIVATE" in t and "Título" not in t
    assert [b["text"] for b in fila_subida("demo_1", "")[0]] == ["📤 Upload to YouTube", "🚫 Don't upload"]
    assert [b["text"] for b in fila_subida("demo_1", "13:00")[0]] == ["📤 Scheduled for 13:00", "❌ Cancel"]
    idioma.poner("es")
    assert [b["text"] for b in fila_subida("demo_1", "")[0]] == ["📤 Subir", "🚫 No subir"]


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    from clips_bot import process

    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(process, "READY_DIR", tmp_path)
    monkeypatch.setattr(m, "video_demo", lambda salida, render, segundos=12.0: salida.write_bytes(b"x") or salida)
    monkeypatch.setattr(m, "probe", lambda p: type("I", (), {"ancho": 1080, "alto": 1920, "duracion": 12.0})())
    monkeypatch.setattr(m, "miniatura", lambda v, d: None)
    monkeypatch.setattr(m, "chequear_audio", lambda v: [])
    monkeypatch.setattr(m, "_meta_de", lambda cid: __import__("json").loads((tmp_path / f"{cid}.json").read_text(encoding="utf-8")))
    subidos, cancelados = [], []
    import clips_bot.youtube as yt

    class Cliente:
        def __init__(self, canal):
            self.canal = canal

        def subir(self, video, titulo, descripcion, tags, publicar, categoria="24"):
            subidos.append((self.canal, titulo, publicar))
            return "VID123"

        def cancelar(self, vid):
            cancelados.append(vid)

    monkeypatch.setattr(yt, "Cliente", Cliente)
    return conn, subidos, cancelados


def test_demo_sube_aunque_este_apagada_programada_para_manana_y_se_cancela(entorno):
    conn, subidos, cancelados = entorno
    idioma.poner("en")
    tg = TG()
    s = replace(load_settings(), youtube_upload_enabled=False)
    m._demo(conn, tg, "1", s)
    clip_id = next(c for c in db.estados(conn) if c.startswith(m.PREFIJO_DEMO))
    assert tg.videos and any("Upload to YouTube" in str(t) for _, t in tg.mensajes)
    assert db.estados(conn)[clip_id] == "entregado"       # nunca queda "procesado": no entra a las 05:00
    cb = {"data": f"sub:u:{clip_id}", "chat_id": "1", "message_id": 5, "callback_id": "q", "user_id": "7"}
    m._subidas_callback(conn, tg, cb, s)
    assert subidos and subidos[0][0] == "rots"
    manana = (datetime.now(m.AR) + timedelta(days=1)).date()
    assert subidos[0][2].astimezone(m.AR).date() == manana
    assert "videos.insert" in tg.mensajes[-1][0] and "VID123" in tg.mensajes[-1][0]
    assert tg.teclados[-1]["inline_keyboard"][-1][0]["text"].startswith("📤 Scheduled for")
    texto, teclado = m._subidas_texto(conn, s)
    assert "Scheduled YouTube uploads" in texto and "VID123" in texto
    sid = teclado["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
    m._subidas_callback(conn, tg, dict(cb, data=f"sub:c:{sid}"), s)
    assert cancelados == ["VID123"] and any("videos.update" in t for t, _ in tg.mensajes[-2:])
    assert not db.subidas(conn, ("programada",))


def test_un_clip_comun_sigue_sin_subirse_con_la_subida_apagada(entorno):
    conn, subidos, _ = entorno
    assert m._programar_subida(conn, replace(load_settings(), youtube_upload_enabled=False),
                               {"clip_id": "x", "textos": {}}, "rots", "13:00") == ""
    assert subidos == []


def test_busqueda_publica_lista_los_shorts_con_vistas_en_ingles():
    idioma.poner("en")
    rec = pego.Recuento("davooxeneize", "davooxeneize|Davo")
    from clips_bot.config import Streamer
    s = Streamer("davooxeneize", plataforma="kick", experimento=True, apodos=("Davo",))
    shorts = [pego.ShortAjeno("a1", "DAVO se enoja", "ClipsAR", 120000, 30),
              pego.ShortAjeno("a2", "otra cosa", "X", 90000, 30)]
    pego.filtrar(shorts, s, 5000, rec=rec)
    t = pego.texto_publicos([rec])
    assert "Public Shorts found on YouTube" in t and "120,000 views" in t and "shorts/a1" in t
    assert "a2" not in t                                  # no lo nombra
    assert "YouTube search returned 2 videos" in rec.texto(5000)


def test_metricas_en_ingles(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("""INSERT INTO metricas (clip_id, video_id, publicado, actualizado, vistas,
                    duracion_media_s, pct_visto_medio, pct_entero, streamer)
                    VALUES ('c1', 'v1', '2026-10-01', '2026-10-08T08:00', 1033, 33, 77, 25, 'davo')""")
    conn.commit()
    idioma.poner("en")
    t = m._texto_metricas(conn)
    assert "YouTube Analytics" in t and "1,033 views" in t and "77% viewed" in t


def test_demo_y_lang_en_la_ayuda():
    nombres = [c[0].split()[0] for c in m.COMANDOS]
    assert "/demo" in nombres and "/lang" in nombres


def test_el_video_de_demo_se_arma(tmp_path):
    from clips_bot.media import probe
    v = m.video_demo(tmp_path / "demo.mp4", load_settings().render, segundos=2.0)
    i = probe(v)
    assert (i.ancho, i.alto) == (1080, 1920) and i.tiene_audio and abs(i.duracion - 2.0) < 0.2


def test_publicos_contesta_con_la_lista_sin_bajar_nada(tmp_path, monkeypatch):
    from clips_bot.config import Streamer
    conn = db.connect(tmp_path / "t.db")
    davo = Streamer("davooxeneize", plataforma="kick", experimento=True, apodos=("Davo",))
    monkeypatch.setattr(m, "_streamers", lambda c=None: [davo])
    monkeypatch.setattr(pego, "bajar_audio_short", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no baja")))
    pedidos = []

    def buscar(consulta, desde):
        pedidos.append(consulta)
        return [pego.ShortAjeno("a1", "DAVO se enoja", "ClipsAR", 1200, 30),
                pego.ShortAjeno("a2", "Davo y el chat", "Otro", 50, 25),
                pego.ShortAjeno("a3", "nada que ver", "X", 90000, 30)]

    idioma.poner("en")
    t = m._publicos(conn, ["davo"], load_settings(), buscar=buscar)
    assert pedidos == ["davooxeneize|Davo"]
    assert "Public YouTube search" in t and "1,200 views" in t and "50 views" in t and "a3" not in t
    assert t.index("a1") < t.index("a2")                      # más vistos primero
    idioma.poner("es")
    assert "No tengo a" in m._publicos(conn, ["nadie"], load_settings(), buscar=buscar)
    assert "falló" in m._publicos(conn, ["davooxeneize"], load_settings(),
                                  buscar=lambda *a: (_ for _ in ()).throw(RuntimeError("403")))
