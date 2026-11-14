"""ElevenLabs preparado (2026-11-14): sin clave o sin voz elegida, sigue la voz de siempre."""

import pytest

from clips_bot import efemerides as ef
from clips_bot import elevenlabs
from clips_bot.config import load_settings


class _Resp:
    def __init__(self, status, content=b"", js=None):
        self.status_code, self.content, self.text, self._js = status, content, "error", js

    def json(self):
        return self._js


class _Sesion:
    def __init__(self, resp):
        self.resp, self.pedidos = resp, []

    def post(self, url, **k):
        self.pedidos.append((url, k))
        return self.resp

    def get(self, url, **k):
        self.pedidos.append((url, k))
        return self.resp


def test_preparado_pero_sin_usar(monkeypatch):
    monkeypatch.setattr(elevenlabs, "clave", lambda: "")
    assert not elevenlabs.lista(load_settings().efemerides)
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    assert not elevenlabs.lista(load_settings().efemerides)      # falta la voz en settings


def test_hablar_pide_pcm_en_castellano():
    s = _Sesion(_Resp(200, b"\x00\x01" * 24000))
    pcm, sr = elevenlabs.hablar("Hola", "voz1", "eleven_multilingual_v2", api_key="k", sesion=s)
    url, k = s.pedidos[0]
    assert url.endswith("/text-to-speech/voz1") and k["params"]["output_format"] == "pcm_24000"
    assert k["headers"]["xi-api-key"] == "k" and k["json"]["language_code"] == "es"
    assert sr == 24000 and len(pcm) == 48000


def test_un_error_es_elevenlabserror():
    with pytest.raises(elevenlabs.ElevenLabsError):
        elevenlabs.hablar("Hola", "voz1", "m", api_key="k", sesion=_Sesion(_Resp(401)))
    with pytest.raises(elevenlabs.ElevenLabsError):
        elevenlabs.hablar("Hola", "voz1", "m", api_key="")


def test_voces():
    js = {"voices": [{"voice_id": "a", "name": "Lucía", "labels": {"accent": "argentine"}}]}
    assert elevenlabs.voces(api_key="k", sesion=_Sesion(_Resp(200, js=js))) == \
        [{"id": "a", "nombre": "Lucía", "idioma": "argentine", "descripcion": ""}]


def test_si_falla_sigue_la_voz_de_siempre(monkeypatch, tmp_path):
    from dataclasses import replace

    from clips_bot import narrar

    modelo = tmp_path / "voz.onnx"
    modelo.write_bytes(b"x")
    s = load_settings()
    s = replace(s, efemerides=replace(s.efemerides, elevenlabs_voz="voz1", voz_motor="piper"),
                voz=replace(s.voz, modelo=str(modelo)))
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    monkeypatch.setattr(elevenlabs, "hablar", lambda *a, **k: (_ for _ in ()).throw(
        elevenlabs.ElevenLabsError("caída")))
    monkeypatch.setattr(narrar, "sintetizar_frases", lambda frases, m, out, ajustes=None: (out, [1.0]))
    avisos = []
    _, _, motor = ef.voz_efemeride(["Hola."], s, tmp_path, avisar=avisos.append)
    assert motor.startswith("piper:") and any("ElevenLabs no anduvo" in a for a in avisos)
    assert ef.texto_voz("elevenlabs:Lucía") == "Voz: Lucía (ElevenLabs)"
