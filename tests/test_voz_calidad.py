"""La voz de Pequeña Historia sin degradar (2026-10-04: la del 04/10 salió cortada a 9,8 kHz).
Nada de cambiar el tono, atempo como mucho ×1,1, si no entra se acorta el guion, y todo a 48 kHz."""
import json
import math
import struct
import wave
from pathlib import Path

from clips_bot import efemerides as ef, narrar
from clips_bot.config import load_settings

RAIZ = Path(__file__).resolve().parent.parent


def _wav(path: Path, sr: int, segundos: float, hz: float = 440.0) -> Path:
    n = int(sr * segundos)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * hz * i / sr))) for i in range(n)))
    return path


def test_ningun_cambio_de_tono_en_el_codigo():
    for archivo in ("narrar.py", "efemerides.py", "media.py", "musica.py", "graficos.py"):
        texto = (RAIZ / "clips_bot" / archivo).read_text(encoding="utf-8")
        assert "asetrate" not in texto and "rubberband" not in texto, archivo
    s = load_settings()
    assert not hasattr(s.voz, "semitonos") and not hasattr(s.efemerides, "piper_semitonos")


def test_atempo_como_mucho_1_1():
    assert load_settings().efemerides.tts_acelerar_max == 1.1


def test_la_voz_pasa_a_48k_sin_cambiar_la_duracion(tmp_path):
    w = _wav(tmp_path / "v.wav", 22050, 2.0)
    narrar.a_48k(w)
    with wave.open(str(w)) as r:
        assert r.getframerate() == 48000
        assert abs(r.getnframes() / 48000 - 2.0) < 0.01


def test_ajustar_duracion_no_pasa_de_1_1(tmp_path):
    w = _wav(tmp_path / "v.wav", 48000, 12.0)
    dur, factor = ef.ajustar_duracion(w, [6.0, 6.0], max_s=10.0, max_factor=1.1)
    assert factor == 1.1 and abs(narrar.duracion_wav(w) - 12.0 / 1.1) < 0.05
    assert abs(sum(dur) - 12.0 / 1.1) < 0.01
    with wave.open(str(w)) as r:
        assert r.getframerate() == 48000
    w2 = _wav(tmp_path / "c.wav", 48000, 9.0)
    assert ef.ajustar_duracion(w2, None, 10.0, 1.1) == (None, 1.0)


class _Cliente:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.prompts = []

    def json(self, sistema, prompt, schema, **kw):
        self.prompts.append(prompt)
        return json.dumps({"frases": self.respuestas.pop(0)})


def _guion(frases):
    return ef.Guion(frases=frases, fotos=[], descartadas=[], titulo="t", descripcion="d", hashtags=[],
                    claves=["cohete", "Sputnik"])


FUENTE = "El 4 de octubre de 1957 la Unión Soviética lanzó el Sputnik, el primer satélite, con un cohete."


def test_acortar_guion_mantiene_las_frases_y_valida_contra_el_articulo():
    g = _guion(["Un día como hoy, en 1957, la Unión Soviética lanzó al espacio el Sputnik, el primer satélite.",
                "Lo subió un cohete enorme que rugía con muchísima fuerza."])
    malo = ["Un día como hoy, en 1957, la NASA lanzó el Sputnik.", "Un cohete."]   # dato que no está y frase corta
    bueno = ["Un día como hoy, en 1957, la Unión Soviética lanzó el Sputnik.", "Lo subió un cohete enorme."]
    c = _Cliente([malo, bueno])
    corto = ef.acortar_guion(c, g, FUENTE, objetivo=18)
    assert corto is not None and corto.frases == bueno and len(c.prompts) == 2
    assert "errores" in c.prompts[1]
    assert corto.claves == ["cohete", "Sputnik"] or set(corto.claves) <= {"cohete", "Sputnik"}


def test_acortar_guion_que_no_sale_devuelve_none():
    g = _guion(["Un día como hoy, en 1957, la Unión Soviética lanzó el Sputnik.", "Lo subió un cohete."])
    c = _Cliente([["una sola frase larga de más"]] * 3)
    assert ef.acortar_guion(c, g, FUENTE, objetivo=10) is None


def test_palabras_objetivo():
    assert ef.palabras_objetivo(110, 60.0, 49.5) == int(110 * 49.5 / 60 * 0.95)
