"""🔥 SUBIR YA (2026-11-01): un clip de una alerta del modo en vivo se sube PÚBLICO al instante, sin
programarlo; con partido en pantalla sigue yendo privado a revisar."""
from dataclasses import replace

import clips_bot.__main__ as m
from clips_bot import db, youtube
from clips_bot.config import load_settings
from clips_bot.telegram import fila_subida


class Cliente:
    respuesta_subida = {"status": {"privacyStatus": "public"}}
    subidas: list = []

    def __init__(self, canal):
        pass

    def subir(self, video, titulo, desc, tags, publicar, categoria, publico=False):
        Cliente.subidas.append((publicar, publico))
        return "vidYA"


def _alerta(conn, clip_id="clipA", estado="entregada"):
    db.crear_alerta(conn, streamer="davooxeneize", plataforma="kick", chat_id="1", estado=estado,
                    clips=[clip_id], creadores=5, momento="2026-11-01T20:00:00Z",
                    umbral="2026-11-01T20:01:00Z", detectado="2026-11-01T20:02:00Z", clip_id=clip_id)


def _meta(tmp_path, **extra):
    return {"clip_id": "clipA", "salida": str(tmp_path / "c.mp4"), "plataforma": "kick",
            "textos": {"titulo": "t", "descripcion": "d", "hashtags": ["#Shorts"]}, **extra}


def test_metadatos_publico_sin_fecha():
    st = youtube.metadatos("t", "d", [], None, publico=True)["status"]
    assert st["privacyStatus"] == "public" and "publishAt" not in st


def test_alerta_en_vivo_se_publica_ya(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    _alerta(conn)
    Cliente.subidas = []
    monkeypatch.setattr(youtube, "Cliente", Cliente)
    settings = replace(load_settings(), youtube_upload_enabled=True)
    aviso = m._programar_subida(conn, settings, _meta(tmp_path), "rots", "13:00")
    assert Cliente.subidas == [(None, True)]
    assert "Publicado YA" in aviso and "vidYA" in aviso
    assert db.subidas(conn, ("publicada",), clip_id="clipA")
    assert m._estado_subida(conn, "clipA", {"plataforma": "kick"}) == "publicado"
    assert fila_subida("clipA", "publicado")[0][0]["text"] == "✅ Publicado"
    assert m._programar_subida(conn, settings, _meta(tmp_path), "rots", "13:00") == ""   # una sola vez


def test_alerta_con_partido_queda_privada(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    _alerta(conn)
    Cliente.subidas = []
    monkeypatch.setattr(youtube, "Cliente", Cliente)
    settings = replace(load_settings(), youtube_upload_enabled=True)
    aviso = m._programar_subida(conn, settings, _meta(tmp_path, partido_en_pantalla=True), "rots", "13:00")
    assert Cliente.subidas == [(None, False)] and "PRIVADO" in aviso


def test_un_clip_comun_se_sigue_programando(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    _alerta(conn, clip_id="otro")                      # una alerta de OTRO clip no cuenta
    _alerta(conn, clip_id="clipA", estado="descartada")  # ni una alerta que no se entregó
    Cliente.subidas = []
    monkeypatch.setattr(youtube, "Cliente", Cliente)
    settings = replace(load_settings(), youtube_upload_enabled=True)
    aviso = m._programar_subida(conn, settings, _meta(tmp_path), "rots", "13:00")
    publicar, publico = Cliente.subidas[0]
    assert publicar is not None and publico is False and "Programado" in aviso
