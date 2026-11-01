"""Prueba 2026-11-01 ("la voz todavía suena a IA"): guion para ser dicho, redondeos que se validan,
pausas variables entre frases y EQ de locutor. Sin red."""
import wave
from datetime import date

import numpy as np

from clips_bot import efemerides as ef
from clips_bot.subtitles import Palabra

FUENTE = "En 1928 Alexander Fleming descubrió la penicilina. El hongo mató a 2.300 colonias."


def test_redondeos_con_casi_pasan_y_sin_casi_no():
    hoy = date(2026, 11, 1)
    # 98 años desde 1928: "casi cien años" está bien
    assert ef.no_respaldados("Hace casi cien años, Fleming vio algo raro.", FUENTE, 1928, hoy) == []
    # redondeo de un número del artículo (2.300 -> "más de dos mil")
    assert ef.no_respaldados("Mató a más de dos mil colonias.", FUENTE, 1928, hoy) == []
    assert ef.no_respaldados("Mató a casi 2500 colonias.", FUENTE, 1928, hoy) == []
    # sin "casi"/"más de", el número tiene que estar tal cual
    assert ef.no_respaldados("Hace cien años, Fleming vio algo raro.", FUENTE, 1928, hoy) == ["cien"]
    # redondeo de algo que NO sale del artículo: afuera
    assert ef.no_respaldados("Mató a casi cinco mil colonias.", FUENTE, 1928, hoy) == ["cinco mil"]


def test_valor_en_letras():
    assert ef.valor_en_letras("dos mil quinientos") == 2500
    assert ef.valor_en_letras("cien") == 100
    assert ef.valor_en_letras("noventa y ocho") == 98
    assert ef.valor_en_letras("tres millones") == 3_000_000
    assert ef.valor_en_letras("miles") is None


def test_el_prompt_hablado_cambio_las_reglas_de_frases_y_numeros():
    s = ef.SISTEMA_GUION_HABLADO
    assert s != ef.SISTEMA_GUION
    assert "LARGO VARIADO" in s and "COMO SE DICEN" in s and "puntos suspensivos" in s
    assert "ninguna de más de 14 palabras" not in s and "escritos igual" not in s
    assert "REGLA DE ORO" in s                      # lo de no inventar sigue igual


def _wav(ruta, segundos, sr=48000):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.ones(int(segundos * sr)) * 1000).astype(np.int16).tobytes())


def _dur(ruta):
    with wave.open(str(ruta)) as w:
        return w.getnframes() / w.getframerate()


def test_pausas_variables_corren_los_tiempos_y_no_se_repiten(tmp_path):
    frases = ["Un día como hoy, pasó algo.", "¿Sabés qué?", "Y adentro había…", "nada."]
    palabras, t = [], 0.0
    inicios = []
    for f in frases:
        inicios.append(t)
        for w in f.split():
            palabras.append(Palabra(t, t + 0.3, w))
            t += 0.35
        t += 0.1                                     # Gemini deja huecos chicos y todos iguales
    wav = tmp_path / "voz.wav"
    _wav(wav, t)
    nuevas, nuevos, extra = ef.pausas_variables(wav, palabras, inicios, frases)
    assert abs(_dur(wav) - (t + extra)) < 0.01
    huecos = [nuevos[i + 1] - nuevas[sum(len(f.split()) for f in frases[:i + 1]) - 1].fin
              for i in range(len(frases) - 1)]
    assert all(0.29 <= h <= 0.86 for h in huecos)
    assert len({round(h, 2) for h in huecos}) == len(huecos)          # no todas iguales
    assert huecos[2] >= ef.PAUSA_SUSPENSO[0] - 0.01                    # después de "…", la más larga
    assert [p.texto for p in nuevas] == [p.texto for p in palabras]
    # Mismo guion, mismas pausas
    _wav(wav, t)
    assert ef.pausas_variables(wav, palabras, inicios, frases)[2] == extra


def test_pausas_respetan_el_tope(tmp_path):
    frases = ["Uno.", "Dos.", "Tres."]
    palabras = [Palabra(i * 0.5, i * 0.5 + 0.4, f) for i, f in enumerate(frases)]
    wav = tmp_path / "voz.wav"
    _wav(wav, 1.5)
    _, _, extra = ef.pausas_variables(wav, palabras, [0.0, 0.5, 1.0], frases, maximo_extra_s=0.2)
    assert extra <= 0.2 + 1e-3


def test_ecualizado_no_cambia_el_largo(tmp_path):
    wav = tmp_path / "voz.wav"
    _wav(wav, 2.0)
    ef.ecualizar_locutor(wav)
    assert abs(_dur(wav) - 2.0) < 0.01
    with wave.open(str(wav)) as w:
        assert w.getframerate() == 48000


def test_interruptores_apagados_de_fabrica():
    from clips_bot.config import load_settings
    s = load_settings()
    assert s.efemerides.guion_hablado is False and s.efemerides.voz_natural is False
