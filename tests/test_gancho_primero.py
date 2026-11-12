"""Gancho primero en todo Pequeña Historia y la medición (Santi, 2026-11-12). Sin red."""

import json
import wave
from datetime import date, datetime

import numpy as np
import pytest

from clips_bot import db, locales, medicion_ph
from clips_bot import efemerides as ef
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_los_cuatro_guiones_arrancan_con_el_gancho():
    for sistema in (ef.SISTEMA_GUION, ef.SISTEMA_GUION_HABLADO, locales.SISTEMA_GUION_LOCAL,
                    locales.SISTEMA_GUION_CORTO):
        assert "La PRIMERA frase es el GANCHO" in sistema
        assert 'arranca EXACTAMENTE con "Un día como hoy' not in sistema
    assert 'La SEGUNDA frase arranca EXACTAMENTE con "En <año>, en <lugar>,"' in locales.SISTEMA_GUION_LOCAL
    assert 'La SEGUNDA frase arranca EXACTAMENTE con "En <año>, en <lugar>,"' in locales.SISTEMA_GUION_CORTO


def test_el_lugar_va_en_la_segunda_frase_tambien_en_el_formato_largo():
    v = locales.validar_lugar("Nacozari")
    d = {"frases": [{"texto": "Un maquinista alejó un tren en llamas de su pueblo."},
                    {"texto": "En 1907, en Nacozari, Jesús García lo hizo."}],
         "titulo": "El héroe de Nacozari", "hashtags": ["#Nacozari", "#Mexico", "#Shorts"]}
    assert v(d) == []


def test_interruptores_prendidos():
    s = load_settings()
    assert s.efemerides.imagen_frase is True and s.historias_fb.formato_corto is True


def _wav(ruta, x, sr=48000):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def test_la_voz_arranca_en_el_primer_cuadro(tmp_path):
    from clips_bot import narrar

    sr = 48000
    voz = 0.3 * np.sin(np.linspace(0, 3000, sr * 2))
    ruta = tmp_path / "v.wav"
    _wav(ruta, np.concatenate([np.zeros(int(sr * 0.4)), voz]))
    assert narrar.sacar_silencio_inicial(ruta) == pytest.approx(0.38, abs=0.02)
    assert narrar.duracion_wav(ruta) == pytest.approx(2.02, abs=0.02)
    assert narrar.sacar_silencio_inicial(ruta) == 0.0          # ya arranca con voz: no toca


def test_la_primera_foto_es_la_mas_impactante():
    g = ef.Guion(frases=["El gancho.", "En 1907, en el pueblo."], fotos=[], descartadas=[],
                 titulo="t", descripcion="d", hashtags=[])
    pool = [ef.Foto(archivo=f"F{i}.jpg", url="", ancho=1000, alto=800, licencia="CC0", autor="x",
                    epigrafe="e", pagina="", articulo="A", ruta="") for i in range(3)]

    class Elector:
        def json(self, *a, **k):
            return json.dumps({"frases": [{"se_ve": "x", "fotos": [1], "de_epoca": True, "seguro": True,
                                           "contradice": False},
                                          {"se_ve": "y", "fotos": [3, 2], "de_epoca": True, "seguro": True,
                                           "contradice": False}],
                               "descartadas": [], "impactantes": [3, 1], "tipos": []})

    import clips_bot.efemerides as m
    original = m._jpeg_chico
    m._jpeg_chico = lambda *a, **k: b""
    try:
        rankings, _ = ef.elegir_fotos(None, g, pool, [[0, 1, 2], [0, 1, 2]], elector=Elector(),
                                      avisar=lambda *_: None)
    finally:
        m._jpeg_chico = original
    assert rankings[0][0] == 2 and 0 in rankings[0]


def test_segundo_en_que_se_va_la_mayoria():
    curva = {"0": 1, "1": 1, "2": 1, "3": 0.97, "4": 0.86, "5": 0.76, "6": 0.60, "7": 0.51, "8": 0.48}
    assert medicion_ph.segundo_que_se_va(curva) == 8
    assert medicion_ph.segundo_que_se_va({"0": 1, "1": 0.9}) is None


def test_informe_antes_y_despues():
    datos = {"fb": {"a": {"publicado": "2026-11-08", "se_va_s": 4, "reproducciones": 200, "medio_s": 5.5},
                    "b": {"publicado": "2026-11-13", "se_va_s": 9, "reproducciones": 600, "medio_s": 9.0}},
             "yt": {"x": {"publicado": "2026-11-07", "titulo": "Nacozari", "vistas": 1343, "se_queda_pct": 56.0},
                    "y": {"publicado": "2026-11-14", "titulo": "Otro", "vistas": 2500, "se_queda_pct": 64.0}}}
    texto = medicion_ph.informe(datos, hasta=date(2026, 11, 19))
    assert "segundo en que se va la mayoría: 4 s → 9 s" in texto
    assert "% que se queda: 56 % → 64 %" in texto
    assert "Otro" in medicion_ph.por_video(datos) and "Nacozari" not in medicion_ph.por_video(datos)


def test_la_medicion_corre_una_vez_por_dia_y_el_informe_a_la_semana(conn):
    import clips_bot.__main__ as m

    class TG:
        def __init__(self):
            self.mensajes = []

        def send_message(self, chat, texto, **k):
            self.mensajes.append((chat, texto))

    tg, veces = TG(), []

    def medir(c, s):
        veces.append(1)
        return medicion_ph.guardar(c, {}, {})

    s = load_settings()
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 13, 8, 0, tzinfo=m.AR), medir=medir)
    assert veces == []                                    # antes de la hora
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 13, 9, 30, tzinfo=m.AR), medir=medir)
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 13, 11, 0, tzinfo=m.AR), medir=medir)
    assert veces == [1] and tg.mensajes == []             # una vez por día, sin informe todavía
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 19, 9, 5, tzinfo=m.AR), medir=medir)
    assert len(tg.mensajes) == 1 and tg.mensajes[0][0] == m.DUENO
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 20, 9, 5, tzinfo=m.AR), medir=medir)
    assert len(tg.mensajes) == 1                          # el informe va una sola vez
