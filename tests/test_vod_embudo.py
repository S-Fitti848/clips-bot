"""El embudo para encontrar en el VOD el original de un Short que pegó (2026-10-29). Sin red."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np

from clips_bot import db, pego, vod as vd, vod_embudo as em
from clips_bot.config import Pego, Streamer

INICIO = datetime(2026, 10, 21, 23, 40, tzinfo=timezone.utc)


def _vod(id_="1", titulo="GOLEÓ EL MANCHESTER", horas=7.5, inicio=INICIO, categoria="Just Chatting"):
    return vd.Vod(id_, "kick", "u", f"https://kick.com/x/videos/{id_}", inicio, horas * 3600, titulo,
                  categoria=categoria)


def _pista(publicado, titulo="Las respuestas al tweet de Davo sobre la goleada"):
    return em.Pista("s", titulo, "", publicado, 30.0, None)


# ---- antes de buscar ----------------------------------------------------------------------------------

def test_compilados_y_otros_nombres_no_se_buscan():
    propios, otros = {"davooxeneize", "davo"}, ["Gastón Edul", "el Kun", "lacobraaa"]
    assert em.motivo_saltear("TOP 5 ENOJOS DE DAVO JUGANDO FIFA", propios, otros) == "compilado"
    assert em.motivo_saltear("Los mejores momentos de Davo", propios, otros) == "compilado"
    assert em.motivo_saltear("DAVO Y GASTON EDUL DEBATEN el DEBUT", propios, otros) == "nombra a Gastón Edul"
    assert em.motivo_saltear("LACOBRA, DAVO y el KUN AGUERO HABLAN", propios, otros) == "nombra a el Kun"
    # "TOP" en el medio no es un compilado; los hashtags no cuentan como nombrar a alguien
    assert em.motivo_saltear("DAVO DEBATE CRISTIANO RONALDO es TOP 6 del MU", propios, otros) == ""
    assert em.motivo_saltear("LO QUE JUEGA DAVO EH #lacobraaa", propios, otros) == ""


def test_los_salteados_salen_igual_en_el_resumen_con_el_motivo(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    davo = Streamer("davooxeneize", plataforma="kick", experimento=True, apodos=("Davo",))
    ahora = datetime.now(timezone.utc)
    pego.guardar(conn, pego.ShortAjeno("s0", "TOP 5 ENOJOS DE DAVO", "Otro", 900000, 30, ahora.isoformat()),
                 "davooxeneize", None, 40)
    assert pego.buscar_en_vod_del_dia(conn, [davo], Pego(), tmp_path, kick=object()) == 0
    t = pego.texto_sin_original(pego.sin_original(conn, [davo], ahora - timedelta(days=1)))
    assert "TOP 5 ENOJOS" in t and "No lo busqué en el VOD: compilado" in t


# ---- 1. el stream -----------------------------------------------------------------------------------------

def test_el_vod_en_vivo_a_la_hora_de_publicado_gana():
    pub = INICIO + timedelta(minutes=124)          # el caso real: momento min 107, publicado 17 min después
    vivo = _vod("1", "MANCHESTER UNITED FUE GOLEADO EN CHAMPIONS")
    viejo = _vod("2", "BOCA A LA FINAL", inicio=INICIO - timedelta(days=2))
    elegidos = em.elegir_vods(_pista(pub), [viejo, vivo], None, None, {"davo"})
    assert elegidos[0].vod.id == "1" and elegidos[0].vivo
    assert em.en_vivo(_vod(horas=0), INICIO + timedelta(hours=1))   # Kick todavía en vivo: duración 0


# ---- 2. el momento ---------------------------------------------------------------------------------------

def test_ventanas_por_la_hora_y_por_los_clips_se_juntan_si_se_pisan():
    pub = INICIO + timedelta(minutes=124)
    v = _vod()
    # Kick: vod_offset 0 → la posición sale de la hora de creación menos el inicio y lo que dura
    clip = SimpleNamespace(video_id="1", vod_offset=None, created_at=INICIO + timedelta(minutes=110),
                           duration=30, title="respuestas al tweet goleada", view_count=200)
    otro = SimpleNamespace(video_id="1", vod_offset=None, created_at=INICIO + timedelta(minutes=300),
                           duration=30, title="tweet goleada", view_count=10)
    lejos = SimpleNamespace(video_id="9", vod_offset=None, created_at=INICIO, duration=30,
                            title="goleada", view_count=999)
    vs = em.ventanas(v, _pista(pub), [clip, otro, lejos], {"davo"})
    assert "hora de publicación" in vs[0].motivo and "clip" in vs[0].motivo      # se pisaban: una sola
    assert vs[0].inicio <= 107 * 60 <= vs[0].fin
    assert any(abs((w.inicio + w.fin) / 2 - (300 * 60 - 30)) < 60 for w in vs)    # la del otro clip
    assert len(vs) <= em.MAX_VENTANAS


def test_sin_estar_en_vivo_no_hay_ventana_por_la_hora():
    v = _vod(inicio=INICIO - timedelta(days=2))
    assert em.ventanas(v, _pista(INICIO), [], set()) == []


# ---- 3. confirmar y el respaldo --------------------------------------------------------------------------

def test_confirma_solo_en_las_ventanas_y_da_el_segundo_del_vod(monkeypatch):
    pedidos = []
    monkeypatch.setattr(em, "huella_tramo", lambda v, i, d: pedidos.append((i, d)) or np.ones((10, 16)))
    monkeypatch.setattr(em.ah, "coincidencia_rapida", lambda corto, h: (0.97, 120.0))
    h = em.confirmar(np.ones((5, 16)), _vod(), [em.Ventana(3600, 4800, "hora")], 0.55)
    assert pedidos == [(3600, 1200)] and h.segundo == 3720 and h.valor == 0.97


def test_el_vod_entero_solo_si_sobra_tiempo(monkeypatch, tmp_path):
    monkeypatch.setattr(em.ah, "leer_audio", lambda p: np.ones(8000))
    monkeypatch.setattr(em.ah, "huella", lambda a: np.ones((5, 16)))
    monkeypatch.setattr(em, "confirmar", lambda *a, **k: None)
    llamados = []
    monkeypatch.setattr(vd, "buscar_en_vods", lambda *a, **k: llamados.append(1) or (_vod(), 60.0, 0.9))
    pub = INICIO + timedelta(minutes=124)
    sin_tiempo = em.buscar(_pista(pub), [_vod()], [], 0.55, tmp_path, set(), cache=tmp_path,
                           hasta=10.0, reloj=lambda: 20.0)
    assert sin_tiempo is None and llamados == []
    con_tiempo = em.buscar(_pista(pub), [_vod()], [], 0.55, tmp_path, set(), cache=tmp_path,
                           hasta=100.0, reloj=lambda: 20.0)
    assert con_tiempo.como == "VOD entero (respaldo)" and llamados == [1]


def test_la_pista_baja_video_y_audio_y_usa_el_archivo_unido(tmp_path, monkeypatch):
    """2026-10-30: el formato 18 ya no venía y bajaba solo el audio: sin cuadros para Gemini."""
    import sys
    import types

    pedidos = {}

    class YDL:
        def __init__(self, opts):
            pedidos.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=True):
            unido = tmp_path / "short_s.mp4"
            unido.write_bytes(b"x")
            return {"title": "t", "duration": 30, "vcodec": "avc1", "timestamp": 1761788000,
                    "requested_downloads": [{"filepath": str(unido)}]}

        def prepare_filename(self, info):
            return str(tmp_path / "short_s.webm")

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=YDL))
    monkeypatch.setattr(em.subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=1))
    p = em.bajar_pista("s", tmp_path)
    assert "bv*" in pedidos["format"] and "+ba" in pedidos["format"]
    assert p.audio.name == "short_s.mp4"
