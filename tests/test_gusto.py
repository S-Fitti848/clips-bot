"""El gusto de Santi como ejemplo en la llamada del puntaje (pedido 2026-09-29)."""

import json

from clips_bot import db
from clips_bot.config import Textos, load_settings
from clips_bot.textos import armar_prompt, ejemplos_de_gusto, texto_gusto

SANTI = "8668060171"


def _ready(tmp_path, clip_id, titulo, trans):
    (tmp_path / f"{clip_id}.json").write_text(json.dumps(
        {"clip_id": clip_id, "textos": {"titulo": titulo}, "transcripcion": trans}), encoding="utf-8")


def test_toma_los_ultimos_de_cada_lado_solo_de_santi(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for i in range(5):
        _ready(tmp_path, f"b{i}", f"Bueno {i}", f"esto dice el bueno {i} llamame al +54 11 3396-6858")
        db.votar(conn, f"b{i}", 1, SANTI)
    _ready(tmp_path, "m0", "Malo", "aburrido")
    db.votar(conn, "m0", -1, SANTI)
    _ready(tmp_path, "t0", "De Tommy", "x")
    db.votar(conn, "t0", -1, "8824893712")
    g = ejemplos_de_gusto(conn, tmp_path, [SANTI], 3)
    assert len(g["bien"]) == 3 and [e["titulo"] for e in g["mal"]] == ["Malo"]
    assert all("3396" not in e["dice"] for e in g["bien"])         # lo que se dice va tapado
    assert ejemplos_de_gusto(conn, tmp_path, [SANTI], 0) == {"bien": [], "mal": []}


def test_el_prompt_lleva_los_ejemplos():
    g = {"bien": [{"titulo": "Spreen y el balde", "dice": "no puede ser"}], "mal": [{"titulo": "Saludo", "dice": ""}]}
    p = armar_prompt("Spreen", "Just Chatting", "t", 30, "hola", Textos(), gusto=g)
    assert "CÓMO JUZGA SANTI" in p and "«Spreen y el balde»" in p and "NO le gustaron" in p
    assert "(sin habla)" in p
    assert texto_gusto(None) == "" and "CÓMO JUZGA" not in armar_prompt("S", "", "t", 30, "h", Textos())


def test_la_config_real_lleva_3_ejemplos_por_lado():
    assert load_settings().textos.ejemplos_gusto == 3   # decidido por Santi el 2026-09-29
