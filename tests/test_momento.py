"""Clips aburridos (2026-11-01): sin un momento concreto el puntaje no pasa de 5; corte en 7; los
ejemplos del puntaje suman lo que mejor rindió en el canal; más peso a lo que clipearon varios."""
import json

from clips_bot import db, textos as tx
from clips_bot.config import load_settings
from clips_bot.seleccion import factor_momento

CFG = load_settings().textos
BASE = {"titulo": "Le explota el horno en vivo", "descripcion": "Cocina y pasa algo.",
        "hashtags": ["#Shorts", "#a", "#b"], "gancho": "reaccion", "depende_de_fecha": False,
        "sensible": False, "puntaje": 9}


def _parsear(**cambios):
    t, errores = tx.parsear(json.dumps({**BASE, **cambios}), CFG, "x", "x")
    assert errores == []
    return t


def test_sin_momento_no_pasa_de_5():
    assert _parsear(momento="").puntaje == 5
    assert _parsear(momento="nada").puntaje == 5                    # menos de 3 palabras = no hay
    t = _parsear(momento="le explota el horno y grita")
    assert t.puntaje == 9 and t.momento == "le explota el horno y grita"
    assert _parsear(momento="", puntaje=3).puntaje == 3              # el tope solo baja


def test_momento_es_obligatorio_y_el_prompt_lo_exige():
    _, errores = tx.parsear(json.dumps(BASE), CFG, "x", "x")
    assert any("momento" in e for e in errores)
    assert "momento" in tx.SCHEMA["required"]
    assert "SIN momento concreto, el puntaje es 5 como mucho" in tx.SISTEMA


def test_config_corte_7_y_mas_peso_al_mismo_momento():
    s = load_settings()
    assert s.textos.puntaje_min == 7
    assert s.seleccion.peso_momento == 1.0
    assert factor_momento(3, s.seleccion.peso_momento) == 3.0      # 3 personas → ×3 (antes ×2)


def test_ejemplos_con_lo_que_mejor_rindio_en_el_canal(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    ready = tmp_path / "ready"
    ready.mkdir()
    for cid, vistas, pct in (("a", 50000, 20.0), ("b", 300, 80.0), ("c", 100, 5.0)):
        (ready / f"{cid}.json").write_text(json.dumps({"textos": {"titulo": f"titulo {cid}"},
                                                       "transcripcion": f"dice {cid}"}), encoding="utf-8")
        conn.execute("INSERT INTO metricas (clip_id, video_id, actualizado, vistas, pct_entero) "
                     "VALUES (?, ?, '2026-11-01', ?, ?)", (cid, f"v{cid}", vistas, pct))
    conn.commit()
    g = tx.ejemplos_de_gusto(conn, ready, ["1"], 1)
    assert [e["titulo"] for e in g["canal"]] == ["titulo a", "titulo b"]      # más vistas y más retención
    texto = tx.texto_gusto(g)
    assert "MEJOR RINDIERON" in texto and "50.000 vistas" in texto and "80 % lo vio entero" in texto
