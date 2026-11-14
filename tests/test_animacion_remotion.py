"""Prototipo de Así Nació con Remotion: el exportador (timeline → datos por cuadro) sin Node ni red."""
import json
from datetime import datetime

from clips_bot.animacion_remotion import exportar as ex
from clips_bot.animacion_remotion import prueba


def test_exporta_un_cuadro_por_cuadro_del_motor_actual(tmp_path):
    v = prueba.video_sintetico(12.0)
    r = ex.exportar(v, tmp_path / "d.json")
    d = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
    assert r["cuadros"] == v.total_cuadros == len(d["cuadros"])
    tipos = {it["k"] for c in d["cuadros"] for it in c["a"]["fr"] + c["a"]["fi"] + c["a"]["en"]}
    assert {"p", "o"} <= tipos          # personajes y objetos van como datos (los dibuja Remotion)
    assert d["personajes"] and all("piel" in p for p in d["personajes"])


def test_mismo_esqueleto_que_el_motor_actual(tmp_path):
    """Posición, escala y pose de un personaje salen de la MISMA línea de tiempo (los chequeos de
    composición del motor actual siguen valiendo)."""
    v = prueba.video_sintetico(12.0)
    e = ex.Exportador(v)
    c = e.cuadro(15)
    pj = next(it for it in c["a"]["fr"] if it["k"] == "p")
    assert set(ex.CAMPOS_ESTADO) == set(pj["e"])
    assert pj["piso"] >= pj["y"] - 1


def test_pausa_y_viaje_en_el_tiempo():
    v = prueba.video_sintetico(35.0)
    e = ex.Exportador(v)
    cuadros = [e.cuadro(i) for i in range(0, v.total_cuadros, 3)]
    assert any(c["a"]["pausa"] is not None and any(it["k"] == "t" for it in c["a"]["en"]) for c in cuadros)
    assert any(c["a"]["giro"] for c in cuadros)
    assert any(c["tono"] > 0.9 for c in cuadros)      # el pasado en sepia


def test_franjas_prohibidas():
    assert prueba.franja_prohibida(datetime(2026, 11, 15, 4, 0))
    assert prueba.franja_prohibida(datetime(2026, 11, 15, 7, 0))
    assert not prueba.franja_prohibida(datetime(2026, 11, 15, 19, 0))
