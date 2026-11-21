"""Un video con el estándar muy bajo no se publica solo (Santi, 2026-11-17): debajo de 12/14 (Así Nació) o 7/9
(Pequeña Historia) después de las correcciones, llega con ✅ Publicar igual / ❌ Cancelar y, sin respuesta, no sale."""
import json
from datetime import date

import pytest

import clips_bot.__main__ as m
from clips_bot import calidad, db
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _fallas(ids):
    return [{"id": i, "cuadro": 1, "que": "x"} for i in ids]


def test_umbrales():
    an = [r.id for r in calidad.de_revision("asinacio")]
    ph = [r.id for r in calidad.de_revision("pequena_historia")]
    assert len(an) == 19 and len(ph) == 13                               # PH-10 a PH-13 (Colón, 17/11)
    # Así Nació 15/19 (Santi, 2026-11-20): como mucho 4 sin cumplir
    assert calidad.minimo("asinacio") == 15 and calidad.minimo("pequena_historia") == 11
    assert calidad.retener("asinacio", _fallas(an[:5]), True)            # 5 sin cumplir: 14/19, se retiene
    assert not calidad.retener("asinacio", _fallas(an[:4]), True)        # 4 sin cumplir: 15/19, sale con aviso
    assert not calidad.retener("asinacio", _fallas(an[:6]), False)       # la revisión no respondió: no se puntuó
    assert calidad.retener("pequena_historia", _fallas(["PH-07", "PH-08", "PH-09"]), True)    # 10/13
    assert not calidad.retener("pequena_historia", _fallas(["PH-07", "PH-08"]), True)
    assert calidad.retener("pequena_historia", _fallas(["PH-02"]), True)           # una que frena
    assert "14/19" in calidad.texto_retenido("asinacio", _fallas(an[:5]))


class R:
    marca, angulo, promedio, titulo = "Frisbee", "nombre", 8.5, "Frisbee: el nombre"
    descripcion, hashtags, articulo = "d", ["#Shorts"], "Frisbee"
    credito_musica, duracion_s, video, total_s, costo_usd = "", 34.0, "v.mp4", 400, 0.2
    estandar = {"revisado": True, "fallas": _fallas(["AN-01", "AN-02", "AN-03", "AN-04", "AN-05"])}


def test_asi_nacio_bajo_no_se_programa(conn, tmp_path, monkeypatch):
    from clips_bot.animacion import marcas

    s = load_settings()
    enviados, mensajes, programados = [], [], []
    monkeypatch.setattr(marcas, "armar_video", lambda *a, **k: R())
    monkeypatch.setattr(marcas, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(marcas, "enviar", lambda tg, chats, r, caption="", teclado=None, **k:
                        enviados.append((caption, teclado)))
    monkeypatch.setattr(m, "_programar_subida", lambda *a: programados.append(a) or "📤 x")
    monkeypatch.setattr(m, "_subir_facebook_asinacio", lambda *a: programados.append(a) or "📘 x")
    monkeypatch.setattr(m, "DATA_DIR", tmp_path / "data")

    class TG:
        def send_message(self, chat, texto, teclado=None):
            mensajes.append((texto, teclado))

    m._animacion_armar(conn, TG(), [m.DUENO], s, date(2026, 11, 17))
    assert not programados                                         # nada a YouTube ni a Facebook
    caption, teclado = enviados[0]
    assert "⏸ 14/19" in caption and "Motivo:" in caption
    from clips_bot import aviso_corto
    assert "NO se publica sola" in aviso_corto.leer(conn, "asinacio_20261117")
    botones = [b["callback_data"] for b in teclado["inline_keyboard"][0]]
    assert botones == ["sub:pub:asinacio_20261117", "sub:no:asinacio_20261117"]
    meta = tmp_path / "output" / "animacion" / "20261117" / "asinacio_20261117.json"
    assert json.loads(meta.read_text(encoding="utf-8"))["clip_id"] == "asinacio_20261117"


class TG2:
    def __init__(self):
        self.respuestas, self.mensajes, self.teclados = [], [], []

    def answer_callback(self, cid, texto="", alerta=False):
        self.respuestas.append(texto)

    def edit_reply_markup(self, chat, mid, teclado):
        self.teclados.append(teclado)

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append(texto)


def _cb(accion, clip="asinacio_20261117"):
    return {"callback_id": "1", "chat_id": m.DUENO, "message_id": 5, "user_id": m.DUENO,
            "data": f"sub:{accion}:{clip}"}


def test_publicar_igual_lo_programa(conn, monkeypatch):
    s = load_settings()
    monkeypatch.setattr(m, "_meta_de", lambda c: {"clip_id": c, "hora": "13:00"})
    llamados = []
    monkeypatch.setattr(m, "_animacion_programar", lambda c, st, meta: llamados.append(meta) or ["📤 Programado."])
    tg = TG2()
    m._subidas_callback(conn, tg, _cb("pub"), s)
    assert llamados and tg.mensajes == ["📤 Programado."]
    assert tg.teclados[-1]["inline_keyboard"][0][0]["callback_data"] == "sub:x:asinacio_20261117"


def test_cancelar_no_lo_publica(conn, monkeypatch):
    s = load_settings()
    monkeypatch.setattr(m, "_meta_de", lambda c: {"clip_id": c})
    monkeypatch.setattr(m, "_animacion_programar", lambda *a: pytest.fail("no se programa"))
    tg = TG2()
    m._subidas_callback(conn, tg, _cb("no"), s)
    assert db.get_valor(conn, f"{m.NO_SUBIR}:asinacio_20261117") == "1" and "no se publica" in tg.mensajes[0]


def test_pequena_historia_publicar_igual_usa_la_subida_de_siempre(conn, monkeypatch):
    s = load_settings()
    monkeypatch.setattr(m, "_meta_de", lambda c: {"clip_id": c})
    llamados = []
    monkeypatch.setattr(m, "_subir", lambda c, st, meta, canal: llamados.append(canal) or ["📤 ok"])
    m._subidas_callback(conn, TG2(), _cb("pub", "historia_fb_1117_1937"), s)
    assert llamados == ["pequena_historia"]


def test_aviso_si_el_video_pasa_de_1_50(conn, tmp_path, monkeypatch):
    from clips_bot.animacion import marcas

    class Caro(R):
        costo_usd, piezas_usd = 1.72, 0.06
        estandar = {"revisado": True, "fallas": []}

    s = load_settings()
    mensajes = []
    monkeypatch.setattr(marcas, "armar_video", lambda *a, **k: Caro())
    monkeypatch.setattr(marcas, "registrar", lambda *a, **k: None)
    monkeypatch.setattr(marcas, "enviar", lambda *a, **k: None)
    monkeypatch.setattr(m, "_animacion_subir", lambda *a: [])
    monkeypatch.setattr(m, "DATA_DIR", tmp_path / "data")

    class TG:
        def send_message(self, chat, texto, teclado=None):
            mensajes.append(texto)

    m._animacion_armar(conn, TG(), [m.DUENO], s, date(2026, 11, 17))
    assert any("1.72" in t and "piezas nuevas US$ 0.06" in t for t in mensajes)
