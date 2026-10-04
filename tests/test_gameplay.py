"""Versión con gameplay abajo (gameplay.py, 2026-10-04): opcional, solo con el botón 🎮."""
import random

from clips_bot import gameplay
from clips_bot.telegram import PREFIJOS_BOTONES, teclado_voto

CHARLA = ("Just Chatting", "IRL")


def _meta(**kw):
    return {"streamer": "spreen", "categoria": "Just Chatting", "raw": "output/raw/x.mp4", **kw}


def test_el_boton_sale_solo_en_charla_con_gameplay(tmp_path):
    (tmp_path / "juego1.mp4").write_bytes(b"x")
    assert gameplay.disponible(_meta(), CHARLA, tmp_path)
    assert not gameplay.disponible(_meta(categoria="Minecraft"), CHARLA, tmp_path)
    assert not gameplay.disponible(_meta(efemeride={"x": 1}), CHARLA, tmp_path)
    assert not gameplay.disponible(_meta(raw=""), CHARLA, tmp_path)
    assert not gameplay.disponible(_meta(), CHARLA, tmp_path / "vacia")


def test_nunca_por_defecto_en_el_teclado():
    sin = teclado_voto("c1")["inline_keyboard"]
    con = teclado_voto("c1", gameplay=True)["inline_keyboard"]
    assert not any(b["callback_data"].startswith("gp:") for f in sin for b in f)
    assert any(b["callback_data"] == "gp:c1" for f in con for b in f)
    assert "gp" in PREFIJOS_BOTONES


def test_filtro_streamer_arriba_juego_abajo_sin_audio_del_juego():
    f = gameplay.filtro(1080, 1920, 1920, 1080, (0.4, 0.2, 0.6, 0.6), 30, True, True, 30)
    assert "[0:v]crop=" in f and "[1:v]scale=1080:960" in f and "vstack" in f
    assert "[1:a]" not in f and "ass=titulo.ass" in f
    # dos personas en las puntas: no entran en el recorte → el clip entero sobre el fondo difuminado
    f2 = gameplay.filtro(1080, 1920, 1920, 1080, (0.05, 0.2, 0.95, 0.6), 30, False, False, 30)
    assert "gblur" in f2 and "[0:v]crop=" not in f2


def test_tramo_al_azar_que_alcance(monkeypatch, tmp_path):
    class I:
        def __init__(self, d):
            self.duracion = d
    largos = {"a.mp4": 20.0, "b.mp4": 600.0}
    monkeypatch.setattr(gameplay, "probe", lambda p: I(largos[p.name]))
    p, inicio = gameplay.elegir_tramo([tmp_path / "a.mp4", tmp_path / "b.mp4"], 40, random.Random(1))
    assert p.name == "b.mp4" and 0 <= inicio <= 560
