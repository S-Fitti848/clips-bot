"""Reels de Pequeña Historia a Facebook (2026-09-30). Sin red: la sesión es falsa."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import clips_bot.__main__ as m
from clips_bot import db, facebook
from clips_bot.config import load_settings

AHORA = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


class R:
    def __init__(self, d, status=200):
        self.status_code, self._d, self.text = status, d, json.dumps(d)

    def json(self):
        return self._d


class S:
    def __init__(self, *respuestas):
        self.r, self.pedidos = list(respuestas), []

    def post(self, url, data=None, headers=None, timeout=None):
        self.pedidos.append((url, data if isinstance(data, dict) else f"<{len(data)} bytes>", headers))
        return self.r.pop(0)

    def delete(self, url, params=None, timeout=None):
        self.pedidos.append(("DELETE " + url, params, None))
        return self.r.pop(0)


def test_los_tres_pasos_y_programado_a_la_hora(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    s = S(R({"video_id": "V1", "upload_url": "u"}), R({"success": True}), R({"success": True}))
    vid = facebook.subir_reel(video, "Título\n\nDesc", AHORA + timedelta(hours=3), "v23.0", "PAGE", "TOK",
                              session=s, ahora=AHORA)
    assert vid == "V1"
    (u1, d1, _), (u2, d2, h2), (u3, d3, _) = s.pedidos
    assert u1.endswith("/v23.0/PAGE/video_reels") and d1["upload_phase"] == "start"
    assert u2 == "https://rupload.facebook.com/video-upload/v23.0/V1" and d2 == "<1000 bytes>"
    assert h2["Authorization"] == "OAuth TOK" and h2["file_size"] == "1000"
    assert d3["upload_phase"] == "finish" and d3["video_state"] == "SCHEDULED"
    assert int(d3["scheduled_publish_time"]) == int((AHORA + timedelta(hours=3)).timestamp())


def test_si_la_hora_ya_paso_se_publica_ya_y_un_error_se_explica(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    s = S(R({"video_id": "V1"}), R({"success": True}), R({"success": True}))
    facebook.subir_reel(video, "t", AHORA + timedelta(minutes=5), "v23.0", "P", "T", session=s, ahora=AHORA)
    assert s.pedidos[-1][1]["video_state"] == "PUBLISHED"
    s = S(R({"error": {"message": "Invalid OAuth access token"}}, 400))
    with pytest.raises(facebook.FacebookError, match="Invalid OAuth"):
        facebook.subir_reel(video, "t", None, "v23.0", "P", "T", session=s)


def test_sin_credenciales_lo_dice(monkeypatch):
    monkeypatch.setattr(facebook, "env", lambda n, requerido=True: "")
    with pytest.raises(facebook.FacebookError, match="docs/facebook.md"):
        facebook.credenciales()


def test_prendido():
    assert load_settings().facebook.activo is True   # prendido 2026-10-04, Reel de prueba OK


def test_subir_de_una_efemeride_va_a_facebook_aunque_youtube_este_apagado(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    s = load_settings()
    s = replace(s, youtube_upload_enabled=False, facebook=replace(s.facebook, activo=True))
    subidos = []
    monkeypatch.setattr(facebook, "subir_reel", lambda v, t, c, ver: subidos.append((t, c)) or "FB1")
    meta = {"clip_id": "efemeride_1004_1957", "salida": str(tmp_path / "v.mp4"), "efemeride": {},
            "textos": {"titulo": "El Sputnik", "descripcion": "d", "hashtags": ["#Shorts"]}}
    avisos = m._subir(conn, s, meta, "pequena_historia")
    assert subidos and subidos[0][0].startswith("El Sputnik")
    assert any("Facebook" in a for a in avisos) and any("esperando la auditoría" in a for a in avisos)
    assert m._subir(conn, s, meta, "pequena_historia") == [] or len(subidos) == 1   # no dos veces
    assert m._subir(conn, s, {**meta, "clip_id": "x", "plataforma": "twitch"}, "rots") == []  # clips: no
