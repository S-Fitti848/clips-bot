"""Lo que pega en otros canales → el clip original (pego.py) y el comparador de audio."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from clips_bot import audio_huella as ah, db, pego
from clips_bot.candidates import Clip
from clips_bot.config import Pego, Streamer
from clips_bot.telegram import por_que

AHORA = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
SPREEN = Streamer("spreen", plataforma="kick", fuentes=("reciente",), grupo="argentinos", experimento=True)


def _short(id, titulo="Spreen se cae", canal="Otro", vistas=50000, dur=40):
    return pego.ShortAjeno(id, titulo, canal, vistas, dur, AHORA.isoformat())


def test_relevantes_nombran_al_streamer_pegaron_y_no_son_propios():
    shorts = [_short("a", vistas=90000), _short("b", titulo="Otro streamer", vistas=900000),
              _short("c", vistas=500), _short("d", canal="Rots"), _short("e", dur=120),
              _short("f", titulo="clip", canal="SpreenClips", vistas=60000), _short("g", vistas=20000)]
    elegidos = pego.relevantes(shorts, SPREEN, 10000, 2, ("Rots",))
    assert [x.id for x in elegidos] == ["a", "f"]            # los 2 más vistos que califican


def test_buscar_api_pide_shorts_por_vistas():
    class R:
        def __init__(self, d):
            self.status_code, self._d, self.text = 200, d, ""

        def json(self):
            return self._d

    pedidos = []

    class S:
        def get(self, url, params=None, timeout=None):
            pedidos.append((url, params))
            if url.endswith("/search"):
                return R({"items": [{"id": {"videoId": "v1"}}]})
            return R({"items": [{"id": "v1", "snippet": {"title": "Spreen", "channelTitle": "X",
                                                          "publishedAt": "2026-09-28T10:00:00Z"},
                                 "statistics": {"viewCount": "123456"},
                                 "contentDetails": {"duration": "PT45S"}}]})

    r = pego.buscar_api("spreen", AHORA - timedelta(days=7), "KEY", session=S())
    assert r[0].vistas == 123456 and r[0].duracion == 45.0 and r[0].publicado.startswith("2026-09-28")
    p = pedidos[0][1]
    assert p["order"] == "viewCount" and p["videoDuration"] == "short" and p["type"] == "video"


def _clip(id, vistas=100):
    return Clip(id=id, url=f"https://kick.com/spreen/clips/{id}", broadcaster_login="spreen",
                broadcaster_name="spreen", title="t", view_count=vistas, duration=30, language="",
                created_at=AHORA - timedelta(days=2), game_id="", game_name="", vod_offset=None,
                plataforma="kick")


def test_de_punta_a_punta_encuentra_guarda_y_devuelve_el_original(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(pego, "bajar_audio_short", lambda short, d: (d / "a.m4a", AHORA))
    monkeypatch.setattr(pego, "originales", lambda s, cuando, dias, maximo, tw, k: [_clip("c1"), _clip("c2")])
    monkeypatch.setattr(pego, "encontrar",
                        lambda audio, clips, d, umbral: (clips[1], 0.81) if "a" in str(audio) else None)
    buscar = lambda consulta, desde: [_short("s1", vistas=80000), _short("s2", vistas=30000)]
    n = pego.buscar_pegados(conn, [SPREEN], Pego(), tmp_path, buscar=buscar, ahora=AHORA)
    assert n == 2
    cands = pego.como_candidatos(conn, [SPREEN], vistos=set())
    assert [c.id for c in cands] == ["c2"]                          # dos Shorts, el mismo clip
    assert cands[0].pego_vistas == 80000 and cands[0].grupo == "argentinos"
    assert pego.como_candidatos(conn, [SPREEN], vistos={"c2"}) == []
    # el mismo Short no se vuelve a comparar
    llamadas = []
    monkeypatch.setattr(pego, "encontrar", lambda *a: llamadas.append(1))
    pego.buscar_pegados(conn, [SPREEN], Pego(), tmp_path, buscar=buscar, ahora=AHORA)
    assert llamadas == []


def test_el_tope_de_busquedas_por_dia(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    hechas = []
    buscar = lambda consulta, desde: hechas.append(consulta) or []
    otros = [Streamer(f"s{i}", plataforma="kick", experimento=True) for i in range(5)]
    pego.buscar_pegados(conn, otros, Pego(busquedas_por_dia=3), tmp_path, buscar=buscar, ahora=AHORA)
    assert hechas == ["s0", "s1", "s2"]
    pego.buscar_pegados(conn, otros, Pego(busquedas_por_dia=3), tmp_path, buscar=buscar, ahora=AHORA)
    assert len(hechas) == 3                                           # hoy ya no busca más


def test_la_linea_dice_que_pego():
    meta = {"vistas": 300, "mediana_vistas": 100, "clips_mismo_momento": 1, "puntaje": 7,
            "pego": {"vistas": 85000, "canal": "SpreenClips"}}
    assert por_que(meta).startswith("🔥 Pegó en otro canal: 85.000 vistas (SpreenClips) · 📊 300 vistas")


# ---- el comparador de audio, con señales sintéticas (sin ffmpeg) -------------------------------

def _voz(segundos, semilla):
    """Ruido con envolvente y timbre cambiante: se parece más a una voz que el ruido blanco."""
    rng = np.random.default_rng(semilla)
    n = int(segundos * ah.SR)
    env = np.repeat(rng.random(int(segundos * 8)) ** 2, ah.SR // 8)[:n]
    ruido = rng.standard_normal(n)
    tono = np.sin(2 * np.pi * np.cumsum(rng.uniform(100, 900, n)) / ah.SR)
    return ((ruido * 0.3 + tono) * env).astype(np.float32)


def test_un_pedazo_con_ruido_coincide_con_su_original_y_no_con_otro():
    original = _voz(40, 1)
    otro = _voz(40, 2)
    pedazo = original[5 * ah.SR:25 * ah.SR] + 0.2 * np.random.default_rng(3).standard_normal(20 * ah.SR).astype(np.float32)
    propio, desfase = ah.coincidencia(ah.huella(pedazo), ah.huella(original))
    ajeno, _ = ah.coincidencia(ah.huella(pedazo), ah.huella(otro))
    assert propio >= Pego().umbral > ajeno
    assert desfase == pytest.approx(5.0, abs=0.1)


def test_muy_corto_no_compara():
    assert ah.coincidencia(ah.huella(_voz(2, 1)), ah.huella(_voz(30, 1)))[0] == 0.0
