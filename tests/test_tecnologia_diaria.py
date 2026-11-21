"""Tecnología sale todos los días (Santi, 2026-11-20): el Windows 1.0 del 20/11 salió con 51 % de fotos reales y
quedó retenido porque la revisión final marcó como "foto borrosa" la tarjeta «MELAZA» (clave de OTRA frase)."""
import inspect
from datetime import datetime

from clips_bot import __main__ as m
from clips_bot import calidad
from clips_bot import efemerides as ef


def test_banco_antes_que_bajar_el_minimo_de_fotos():
    src = inspect.getsource(ef.proponer)
    assert src.index('usar_banco("los de hoy no llegaron a las fotos")') < src.index("aceptar_relajado(insuf[0]")


def test_la_tarjeta_de_la_revision_solo_usa_la_clave_de_su_frase(tmp_path):
    from PIL import Image

    base = tmp_path / "b.jpg"
    Image.new("RGB", (1200, 900), (90, 90, 90)).save(base)
    pool = [ef.Foto(archivo="b.jpg", url="", ancho=1200, alto=900, licencia="CC0", autor="a", epigrafe="b",
                    pagina="", articulo="", ruta=str(base))]
    g = ef.Guion(titulo="t", descripcion="d", hashtags=[], frases=["la llamaron melaza", "traía Paint"],
                 fotos=[0, 0], descartadas=[])
    g.claves = ["melaza"]
    nueva = ef.fabrica_tarjetas(g, 1985, tmp_path, lambda k: pool[k], lambda f: (pool.append(f), len(pool) - 1)[1])
    k = nueva(1, propia=True)
    assert pool[k].epigrafe == "tarjeta: 1985"          # nunca MELAZA, que es de la frase 1


def test_una_tarjeta_no_se_juzga_como_foto(tmp_path, monkeypatch):
    g = ef.Guion(titulo="t", descripcion="d", hashtags=[], frases=["a", "b"], fotos=[0, 1], descartadas=[])
    g.ranking = [[0], [1]]
    plan = [(0, 0, 3.0), (1, 1, 3.0)]
    vueltas = []

    def revisar(cliente, meta, avisar=None):
        vueltas.append(1)
        return [{"id": "PH-12", "cuadro": 1 if len(vueltas) > 1 else 2, "que": "borrosa"}], True

    monkeypatch.setattr(calidad, "revisar_video_ph", revisar)
    out = calidad.revisar_y_reemplazar(object(), tmp_path / "v.mp4", plan, g,
                                       [{"frase": 0, "inicio": 0, "dur": 3}, {"frase": 1, "inicio": 3, "dur": 3}],
                                       ef.Evento("es", 1985, "Windows", ["Windows 1.0"]), {},
                                       lambda r: tmp_path / "v.mp4", lambda i: 9)
    assert plan[1][1] == 9 and out["fallas"] == []
    assert not calidad.retener("pequena_historia", out["fallas"], True)


def test_los_reintentos_de_tecnologia_no_pasan_de_las_16_30(monkeypatch):
    horas = m._antes_del_tope_efe(["07:00", "10:00", "16:30", "17:10", "21:00"])
    assert horas == ["07:00", "10:00", "16:30"]


def test_las_pruebas_frenan_al_llegar_a_1_dolar(tmp_path, monkeypatch):
    import pytest

    from clips_bot import claude, db, gemini

    conn = db.connect(tmp_path / "c.db")
    conn.execute("INSERT INTO gemini_uso (ts, dia, funcion, modelo, clave, entrada, salida, origen) "
                 "VALUES ('t', '2026-11-20', 'x', 'claude-sonnet-5-5', 'claude', 200000, 80000, 'prueba')")
    conn.commit()
    assert claude._gasto_original(conn, "2026-11-20") >= claude.TOPE_PRUEBAS_DIA
    monkeypatch.setattr(gemini, "ORIGEN", gemini.PRUEBA)
    monkeypatch.setenv("CLIPS_CLAUDE_REAL", "1")
    monkeypatch.setattr(claude, "gasto_pruebas_hoy", lambda *a, **k: 1.02)
    avisos = []
    monkeypatch.setattr(claude, "_avisar_tope_pruebas", avisos.append)
    with pytest.raises(claude.TopePruebas):
        claude.prueba_sin_claude()
    assert avisos == [1.02]
    monkeypatch.setattr(claude, "gasto_pruebas_hoy", lambda *a, **k: 0.4)
    claude.prueba_sin_claude()
