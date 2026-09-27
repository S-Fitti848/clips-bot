"""/editar y /narrar: sin filtros de silencio ni de pocas palabras, `sin audio` y aviso de música.

Decisión 2026-09-27: esos filtros son para clips de streamers, no para videos de procesos. El
copyright del audio se resuelve con `sin audio` (el original se silencia y queda solo la voz), y si
el video tiene música, /narrar lo avisa ANTES de sintetizar y sugiere esa opción.
"""

import json
from pathlib import Path

import pytest

import clips_bot.__main__ as m
from clips_bot import db, narrar, process
from clips_bot.config import load_settings
from clips_bot.download import Descarga
from clips_bot.media import Info
from clips_bot.menu import parse_callback
from clips_bot.telegram import sacar_sin_audio


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


# ---- procesar: los filtros de audio no corren para un video propio -------------------

class _Pantalla:
    salteado, hay, caracteres, frames_leidos, hallazgos, motivo = "", False, 0, 8, [], ""

    def a_dict(self):
        return {}


@pytest.fixture
def pipeline_falso(monkeypatch, tmp_path):
    """Todo lo caro de procesar() reemplazado: video mudo de música, 95 % de 'silencio', 0 palabras."""
    for nombre in ("READY_DIR", "WORK_DIR", "DEBUG_DIR", "RAW_DIR"):
        monkeypatch.setattr(process, nombre, tmp_path / nombre.lower())
    monkeypatch.setattr(process, "probe", lambda p: Info(1920, 1080, 60.0, 30.0, True))
    monkeypatch.setattr(process.pant, "detectar_datos", lambda p, cfg: _Pantalla())
    monkeypatch.setattr(process, "fraccion_silencio", lambda *a: 0.95)
    monkeypatch.setattr(process.sub, "cargar_modelo", lambda cfg: object())
    monkeypatch.setattr(process.sub, "transcribir", lambda *a, **k: [])
    monkeypatch.setattr(process.lay, "detectar_caras", lambda p, n: (1920, 1080, [], []))
    def render(entrada, salida, *a):   # como el real: crea la carpeta
        Path(salida).parent.mkdir(parents=True, exist_ok=True)
        Path(salida).write_bytes(b"mp4")

    monkeypatch.setattr(process, "renderizar", render)
    monkeypatch.setattr(process, "_registrar", lambda *a: None)
    video = tmp_path / "aporte_x.mp4"
    video.write_bytes(b"x")
    return Descarga(path=video, clip_id="aporte_x", url="", titulo="", plataforma="aporte",
                    streamer="", canal="", duracion=60, vistas=0, creado=None, categoria="")


def test_un_video_propio_sin_habla_no_se_descarta(pipeline_falso):
    r = process.procesar("", load_settings(), [], descarga=pipeline_falso, avisar=lambda *_: None)
    assert r.descartado is None and r.salida
    assert r.silencio == 0.95 and r.palabras == 0      # se mide y se guarda igual


def test_un_clip_de_streamer_sin_habla_se_sigue_descartando(pipeline_falso, monkeypatch):
    from dataclasses import replace

    clip = replace(pipeline_falso, plataforma="twitch", streamer="alguien", clip_id="clipX")
    monkeypatch.setattr(process, "descargar", lambda url, d: clip)
    r = process.procesar("https://clips.twitch.tv/x", load_settings(), [], avisar=lambda *_: None)
    assert r.descartado and "silencio" in r.descartado


def test_transcripcion_lenta_en_un_video_propio_sigue_sin_subtitulos(pipeline_falso, monkeypatch):
    def lenta(*a, **k):
        raise process.sub.TranscripcionLenta("se pasó")

    monkeypatch.setattr(process.sub, "transcribir", lenta)
    r = process.procesar("", load_settings(), [], descarga=pipeline_falso, avisar=lambda *_: None)
    assert r.descartado is None and r.salida


# ---- sin audio --------------------------------------------------------------------

@pytest.mark.parametrize("args,resto,sin", [
    (["https://a", "sin", "audio"], ["https://a"], True),
    (["sin_audio", "https://a"], ["https://a"], True),
    (["https://a", "mudo"], ["https://a"], True),
    (["https://a", "sin", "vueltas"], ["https://a", "sin", "vueltas"], False),
])
def test_sacar_sin_audio(args, resto, sin):
    assert sacar_sin_audio(args) == (resto, sin)


def test_sin_audio_solo_queda_guardado_hasta_el_video(conn):
    m._editar(conn, None, "1", "7", ["sin", "audio", "cc:", "https://y"], None, "narrar")
    assert db.get_valor(conn, f"{m.ESPERA_SIN_AUDIO}:7") == "1"
    assert db.get_valor(conn, f"{m.ESPERA_CC}:7") == "https://y"


def test_mezclar_sin_original_deja_solo_la_voz(monkeypatch, tmp_path):
    comandos = []
    monkeypatch.setattr(narrar, "_tiene_audio", lambda v: True)
    monkeypatch.setattr(narrar, "run", lambda args: comandos.append(args))
    narrar.mezclar(tmp_path / "v.mp4", tmp_path / "voz.wav", tmp_path / "s.mp4", 0.15)
    narrar.mezclar(tmp_path / "v.mp4", tmp_path / "voz.wav", tmp_path / "s.mp4", 0.15,
                   sin_original=True)
    con, sin = (" ".join(c) for c in comandos)
    assert "[0:a]volume=0.15" in con and "amix" in con
    assert "[0:a]" not in sin and "amix" not in sin    # el original no entra a la mezcla


# ---- aviso de música, antes de sintetizar --------------------------------------------

class FakeGemini:
    def __init__(self, respuesta):
        self.respuesta, self.audios = respuesta, []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
        self.audios.append(audio)
        return json.dumps(self.respuesta)


GUION = {"que_pasa": ["lija una tabla"], "guion": "Mirá lo que pasa con esta madera vieja.",
         "sensible": False, "confianza": 8}


def test_escribir_con_audio_devuelve_la_musica():
    g = narrar.escribir(FakeGemini({**GUION, "musica": "cancion", "cancion": "Artista – Tema"}),
                        20, "", [], audio=b"mp3")
    assert g.musica == "cancion" and g.cancion == "Artista – Tema"
    assert "Artista – Tema" in narrar.aviso_musica(g) and "sin audio" in narrar.aviso_musica(g)


def test_sin_audio_no_se_inventa_la_musica():
    g = narrar.escribir(FakeGemini({**GUION, "musica": "cancion"}), 20, "", [], audio=None)
    assert g.musica == "" and narrar.aviso_musica(g) == ""


class FakeTG:
    def __init__(self):
        self.mensajes, self.respuestas = [], []

    def send_message(self, chat_id, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def answer_callback(self, cid, texto=""):
        self.respuestas.append(texto)

    def edit_message(self, *a, **k):
        pass


def _guion(conn, monkeypatch, tmp_path, meta_extra, respuesta):
    g = FakeGemini(respuesta)
    monkeypatch.setattr(m, "_gemini", lambda s: g)
    monkeypatch.setattr(narrar, "audio_para_gemini", lambda v: b"mp3")
    import clips_bot.media as media
    monkeypatch.setattr(media, "frames_jpeg", lambda v, n: [])
    tg = FakeTG()
    meta = {"clip_id": "c1", "salida": str(tmp_path / "c1.mp4"), "duracion_s": 20,
            "transcripcion": "", **meta_extra}
    m._narrar_guion(conn, tg, "1", "7", meta, load_settings())
    return tg, g


def _botones(teclado):
    return [b["callback_data"].split(":")[1] for fila in teclado["inline_keyboard"] for b in fila]


def test_con_musica_avisa_y_ofrece_aprobar_sin_audio(conn, monkeypatch, tmp_path):
    tg, g = _guion(conn, monkeypatch, tmp_path, {}, {**GUION, "musica": "de_fondo"})
    texto, teclado = tg.mensajes[-1]
    assert "música de fondo" in texto and g.audios == [b"mp3"]
    assert _botones(teclado) == ["ok", "no", "okm"]


def test_sin_musica_no_hay_tercer_boton(conn, monkeypatch, tmp_path):
    tg, _ = _guion(conn, monkeypatch, tmp_path, {}, {**GUION, "musica": "ninguna"})
    assert _botones(tg.mensajes[-1][1]) == ["ok", "no"]


def test_si_ya_pidio_sin_audio_no_manda_el_audio_ni_avisa(conn, monkeypatch, tmp_path):
    tg, g = _guion(conn, monkeypatch, tmp_path, {"sin_audio": True}, {**GUION, "musica": "cancion"})
    texto, teclado = tg.mensajes[-1]
    assert g.audios == [None] and "🎵" not in texto and "sin audio" in texto
    assert _botones(teclado) == ["ok", "no"]


def test_aprobar_sin_audio_llega_a_la_voz(conn, monkeypatch):
    db.set_valor(conn, "guion:012345", json.dumps({"clip_id": "c1", "guion": {"texto": "x"},
                                                   "chat_id": "1", "sin_audio": False}))
    llamados = []
    monkeypatch.setattr(m, "_narrar_voz", lambda c, tg, chat, guardado, s: llamados.append(guardado))
    m._guion_callback(conn, FakeTG(), {"data": "gui:okm:012345", "chat_id": "1", "message_id": 3,
                                       "callback_id": "q", "user_id": "7"}, None)
    assert llamados and llamados[0]["sin_audio"] is True


def test_los_tokens_con_cero_adelante_no_se_rompen():
    """"012345" como número es 12345: el botón buscaba otro pedido. Los handlers leen `crudos`."""
    d = parse_callback("gui:ok:012345")
    assert d["crudos"] == ["012345"] and d["args"] == [12345]
