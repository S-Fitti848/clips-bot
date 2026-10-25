"""El título quemado arriba del video no lleva lo que Arial no dibuja (2026-10-25: el 📸 del clip de
Auron salía como un cuadradito vacío); el título del json (YouTube/Telegram) queda igual."""

import json

from clips_bot import subtitles as sub
from clips_bot.config import load_settings

S = load_settings()
AURON = "«¡Que todo el mundo vea la selfie que me enviaste!» 📸"


def _sin_glifo(texto: str) -> list[str]:
    return [c for c in texto if any(a <= ord(c) <= b for a, b in sub._SIN_GLIFO)]


def test_titulo_ass_sin_emojis_y_el_json_con_emojis(tmp_path):
    textos = {"titulo": AURON}
    sub.escribir_titulo_ass(tmp_path / "titulo.ass", textos["titulo"], "auronplay 👑", S.subtitulos, S.render)
    ass = (tmp_path / "titulo.ass").read_text(encoding="utf-8")
    assert _sin_glifo(ass) == []
    assert "«" not in ass and "»" not in ass                     # la cita entera, sin comillas
    assert "¡Que todo el mundo vea la" in ass and "enviaste!" in ass and "auronplay" in ass
    (tmp_path / "clip.json").write_text(json.dumps({"textos": textos}, ensure_ascii=False), encoding="utf-8")
    assert json.loads((tmp_path / "clip.json").read_text(encoding="utf-8"))["textos"]["titulo"] == AURON


def test_titulo_quemable():
    assert sub.titulo_quemable(AURON) == "¡Que todo el mundo vea la selfie que me enviaste!"
    assert sub.titulo_quemable("Spreen ❤️‍🔥 explota 👍🏽 🇦🇷") == "Spreen explota"
    assert sub.titulo_quemable('Dice "hola" y se va') == 'Dice "hola" y se va'      # comillas internas, sí
    assert sub.titulo_quemable("«Uno» y «otro»") == "«Uno» y «otro»"
    assert sub.titulo_quemable("Ganó 10° a 3° ¿Cómo? Ñandú") == "Ganó 10° a 3° ¿Cómo? Ñandú"
