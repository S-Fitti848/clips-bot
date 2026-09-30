"""Qué voz salió en la efeméride y el botón para rehacerla con Laomedeia (2026-09-30)."""

import json

import clips_bot.__main__ as m
from clips_bot import db, efemerides as ef


def test_la_etiqueta_de_la_voz():
    assert ef.texto_voz("gemini:Laomedeia") == "Voz: Laomedeia"
    assert ef.texto_voz("piper:es_AR-daniela-high|sin cuota") == "Voz: Piper (respaldo, sin cuota)"
    assert ef.texto_voz("piper:es_AR-daniela-high|Gemini no respondió") == \
        "Voz: Piper (respaldo, Gemini no respondió)"
    assert ef.es_piper("piper:x") and not ef.es_piper("gemini:Laomedeia")


def test_el_motivo_de_piper_viaja_en_el_motor(tmp_path, monkeypatch):
    from dataclasses import replace

    from clips_bot import narrar
    from clips_bot.config import load_settings
    from clips_bot.gemini import GeminiError

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(narrar, "sintetizar_frases", lambda f, mo, sal, pausa_s=0.3, ajustes=None: (sal, [1.0]))
    s = load_settings()
    modelo = tmp_path / "v.onnx"
    modelo.write_bytes(b"")
    s = replace(s, voz=replace(s.voz, modelo=str(modelo)), efemerides=replace(s.efemerides, voz_motor="gemini"))

    def sin_cuota(*a, **k):
        raise GeminiError('Gemini TTS (x): 429 {"error": "quota"}')

    def caido(*a, **k):
        raise GeminiError("Gemini TTS (x): Read timed out", pasajero=True)

    assert ef.voz_efemeride(["a"], s, tmp_path, tts=sin_cuota)[2].endswith("|sin cuota")
    assert ef.voz_efemeride(["a"], s, tmp_path, tts=caido)[2].endswith("|Gemini no respondió")


class TG:
    def __init__(self):
        self.mensajes, self.videos = [], []

    def send_video(self, chat, video, caption, **k):
        self.videos.append(caption)
        return {"video": {"file_id": "F"}}

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def answer_callback(self, *a, **k):
        pass

    def edit_message(self, *a, **k):
        pass

    def edit_reply_markup(self, *a, **k):
        pass


def _meta(tmp_path, motor):
    return {"clip_id": "efemeride_1004_1957", "streamer": "Pequeña Historia", "salida": str(tmp_path / "v.mp4"),
            "textos": {"titulo": "t", "descripcion": "d", "hashtags": ["#Shorts"], "credito": "c"},
            "efemeride": {"voz": motor}}


def _entregar(tmp_path, monkeypatch, motor):
    conn = db.connect(tmp_path / "t.db")
    db.set_valor(conn, "efe:tok", json.dumps({"propuesta": {}, "carpeta": str(tmp_path)}))
    monkeypatch.setattr(m, "_efe_estado", lambda c, t: {"propuesta": {}, "carpeta": str(tmp_path)})
    monkeypatch.setattr(ef, "Propuesta", lambda **k: None)
    monkeypatch.setattr(ef, "hacer_video", lambda *a, **k: _meta(tmp_path, motor))
    monkeypatch.setattr(m, "probe", lambda v: type("I", (), {"ancho": 1080, "alto": 1920, "duracion": 40})())
    monkeypatch.setattr(m, "miniatura", lambda v, s: None)
    monkeypatch.setattr(m, "chequear_audio", lambda v: [])
    monkeypatch.setattr(m, "_programar_subida", lambda *a, **k: None)
    import clips_bot.process as proc
    monkeypatch.setattr(proc, "guardar_meta", lambda *a: None)
    tg = TG()
    from clips_bot.config import load_settings
    m._efe_video(conn, tg, "1", "tok", load_settings())
    return conn, tg


def test_con_laomedeia_dice_la_voz_y_no_hay_boton(tmp_path, monkeypatch):
    conn, tg = _entregar(tmp_path, monkeypatch, "gemini:Laomedeia")
    texto, teclado = tg.mensajes[-1]
    assert "Voz: Laomedeia" in texto
    assert not any("Rehacer" in b["text"] for f in teclado["inline_keyboard"] for b in f)
    assert db.get_valor(conn, "efe:tok") is None


def test_con_piper_boton_para_rehacer_y_la_propuesta_se_guarda(tmp_path, monkeypatch):
    conn, tg = _entregar(tmp_path, monkeypatch, "piper:es_AR-daniela-high|sin cuota")
    texto, teclado = tg.mensajes[-1]
    assert "Voz: Piper (respaldo, sin cuota)" in texto
    botones = [b for f in teclado["inline_keyboard"] for b in f]
    assert {"text": "🔁 Rehacer con Laomedeia", "callback_data": "efe:voz:tok"} in botones
    assert db.get_valor(conn, "efe:tok") is not None


def test_el_boton_rehacer_vuelve_a_armar_el_video(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(m, "_efe_estado", lambda c, t: {"propuesta": {}, "carpeta": str(tmp_path)})
    corridas = []
    monkeypatch.setattr(m, "_pesado", lambda conn, tg, chat, comando, args, s, u="": corridas.append((comando, args)))
    m._efe_callback(conn, TG(), {"data": "efe:voz:tok", "chat_id": "1", "message_id": 5,
                                 "callback_id": "q", "user_id": "7"}, None, [])
    assert corridas == [("efe:video", ["tok"])]
