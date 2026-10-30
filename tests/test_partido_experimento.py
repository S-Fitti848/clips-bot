"""Partido en pantalla como experimento (2026-10-29): no se descarta, avisa, nunca se publica solo, y
un /reclamo sobre uno vuelve a descartar todos. También: el crédito de Kick dice kick.com."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import clips_bot.__main__ as m
from clips_bot import db, process, registro, youtube
from clips_bot.config import Streamer, load_settings
from clips_bot.download import Descarga
from clips_bot.media import Info
from clips_bot.subtitles import Palabra


class _Pantalla:
    salteado, hay, caracteres, frames_leidos, hallazgos, motivo = "", False, 0, 8, [], ""

    def a_dict(self):
        return {}


class _Partido:
    hay, motivo, cesped_max, frames_con_cesped = True, "marcador de TV (arriba-der)", 0.6, 4
    marcador = SimpleNamespace(hay=True)

    def a_dict(self):
        return {"hay": True}


@pytest.fixture
def clip_con_partido(monkeypatch, tmp_path):
    for nombre in ("READY_DIR", "WORK_DIR", "DEBUG_DIR", "RAW_DIR"):
        monkeypatch.setattr(process, nombre, tmp_path / nombre.lower())
    monkeypatch.setattr(process, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(process, "probe", lambda p: Info(1920, 1080, 30.0, 30.0, True))
    monkeypatch.setattr(process.pant, "detectar_datos", lambda p, cfg: _Pantalla())
    monkeypatch.setattr(process.pant, "subtitulos_en_video", lambda *a, **k: (False, 0))
    monkeypatch.setattr(process.deportes, "detectar_deporte", lambda *a: _Partido())
    monkeypatch.setattr(process, "fraccion_silencio", lambda *a: 0.1)
    monkeypatch.setattr(process.sub, "cargar_modelo", lambda cfg: object())
    monkeypatch.setattr(process.sub, "transcribir",
                        lambda *a, **k: [Palabra(i * 0.5, i * 0.5 + 0.4, "gol") for i in range(60)])
    monkeypatch.setattr(process.lay, "detectar_caras", lambda p, n: (1920, 1080, [], []))
    monkeypatch.setattr(process, "_rms", lambda *a: [])

    def render(entrada, salida, *a):
        Path(salida).parent.mkdir(parents=True, exist_ok=True)
        Path(salida).write_bytes(b"mp4")

    monkeypatch.setattr(process, "renderizar", render)
    monkeypatch.setattr(process, "_registrar", lambda *a: None)
    video = tmp_path / "c.mp4"
    video.write_bytes(b"x")
    d = Descarga(path=video, clip_id="clipP", url="u", titulo="BOCA RIVER", plataforma="kick",
                 streamer="davooxeneize", canal="davooxeneize", duracion=30, vistas=10, creado=None,
                 categoria="Just Chatting")
    monkeypatch.setattr(process, "descargar", lambda url, dest: d)
    davo = Streamer("davooxeneize", plataforma="kick", experimento=True, detectar_marcador=True)
    return davo, tmp_path / "t.db"


def test_un_partido_no_se_descarta_y_avisa(clip_con_partido):
    davo, _ = clip_con_partido
    r = process.procesar("u", load_settings(), [davo], avisar=lambda *_: None)
    assert r.descartado is None and r.partido_en_pantalla
    assert process.AVISO_PARTIDO in r.aviso


def test_con_los_partidos_re_excluidos_se_vuelve_a_descartar(clip_con_partido):
    davo, dbp = clip_con_partido
    c = db.connect(dbp)
    registro.excluir_partidos(c, "clipViejo")
    c.close()
    r = process.procesar("u", load_settings(), [davo], avisar=lambda *_: None)
    assert r.descartado and "transmisión deportiva" in r.descartado


# ---- la subida: nunca se publica solo ---------------------------------------------------------

def test_youtube_sin_fecha_queda_privado_sin_publishat():
    st = youtube.metadatos("t", "d", ["#Shorts"], None)["status"]
    assert st["privacyStatus"] == "private" and "publishAt" not in st


def test_con_partido_se_sube_privado_sin_fecha_y_avisa(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    subidos = []

    class Cliente:
        respuesta_subida = {"status": {"privacyStatus": "private"}}

        def __init__(self, canal):
            pass

        def subir(self, video, titulo, desc, tags, publicar, categoria):
            subidos.append(publicar)
            return "vid123"

    monkeypatch.setattr(youtube, "Cliente", Cliente)
    settings = replace(load_settings(), youtube_upload_enabled=True)
    meta = {"clip_id": "clipP", "salida": str(tmp_path / "c.mp4"), "partido_en_pantalla": True,
            "textos": {"titulo": "t", "descripcion": "d", "hashtags": ["#Shorts"]}}
    aviso = m._programar_subida(conn, settings, meta, "rots", "13:00")
    assert subidos == [None]                                      # sin publishAt: no sale solo
    assert "PRIVADO" in aviso and "Verificaciones" in aviso and "vid123" in aviso
    assert db.subidas(conn, ("privada",), clip_id="clipP")
    assert m._estado_subida(conn, "clipP", {"plataforma": "kick"}) == "privado"
    from clips_bot.telegram import fila_subida
    assert "privado" in fila_subida("clipP", "privado")[0][0]["text"].lower()
    assert m._programar_subida(conn, settings, meta, "rots", "13:00") == ""   # no se sube dos veces


# ---- /reclamo ----------------------------------------------------------------------------------

def test_un_reclamo_sobre_un_partido_los_vuelve_a_excluir_y_no_al_streamer(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    ready = tmp_path / "ready"
    ready.mkdir()
    monkeypatch.setattr(process, "READY_DIR", ready)
    (ready / "clipP.json").write_text(json.dumps({"partido_en_pantalla": True, "aviso": "x"}),
                                      encoding="utf-8")
    db.registrar_clip(conn, "clipP", "davooxeneize", "entregado", None)
    texto = m._reclamo(conn, ["clipP"])
    assert "vuelven a quedar EXCLUIDOS" in texto and registro.partidos_excluidos(conn)
    assert "davooxeneize" not in db.excluidos(conn)


# ---- el crédito con la plataforma real ------------------------------------------------------------

def test_el_credito_de_kick_dice_kick():
    from clips_bot.textos import armar_prompt, credito

    assert credito("davooxeneize", "davooxeneize", "kick") == "Clip de davooxeneize — kick.com/davooxeneize"
    assert credito("auronplay", "auronplay", "twitch").endswith("twitch.tv/auronplay")
    assert "Plataforma donde transmite: Kick" in armar_prompt("d", "x", "t", 30, "hola",
                                                              load_settings().textos, plataforma="kick")
