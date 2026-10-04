"""Zooms en los picos de volumen sobre el fit_blur (zooms.py, 2026-10-04)."""

from clips_bot import zooms
from clips_bot.config import Render
from clips_bot.layout import Caja, Layout
from clips_bot.render import filtro


def _rms(n, picos=(), base=1.0, alto=5.0):
    v = [base] * n
    for i in picos:
        v[i] = alto
    return v


def test_pocos_picos_separados_y_lejos_de_los_bordes():
    # 40 s en ventanas de 0,5 s: picos en 10 s, 10,5 s (pegado) y 30 s; uno al principio (0,25 s)
    rms = _rms(80, picos=(0, 20, 21, 60))
    p = zooms.picos(rms, 0.5, 40.0, max_n=3)
    assert len(p) == 2                     # 40 s → como mucho 1 + 40 // 20 = 3, pero solo hay 2 fuertes
    assert all(abs(a - b) >= 8 for a, b in zip(p, p[1:]))
    assert p[0] > 1.0                      # el del principio no


def test_clip_parejo_no_lleva_zooms():
    assert zooms.picos([1.0] * 60, 0.5, 30.0) == []


def test_maximo_3_y_6_s_entre_uno_y_otro():
    rms = _rms(80, picos=(5, 15, 30, 50, 70))   # 40 s, picos en 2,75 / 7,75 / 15,25 / 25,25 / 35,25 s
    p = zooms.picos(rms, 0.5, 40.0, max_n=3)
    assert len(p) == 3 and all(b - a >= 6 for a, b in zip(p, p[1:]))


def test_punch_in_salta_rapido_y_vuelve():
    assert (zooms.SUBIDA_S, zooms.QUIETO_S, zooms.BAJADA_S) == (0.1, 0.8, 0.3)


def test_tramo_suave_alrededor_del_pico():
    (a, b), = zooms.tramos([10.0], 30.0)
    assert a < 10.0 < b and abs((b - a) - (zooms.SUBIDA_S + zooms.QUIETO_S + zooms.BAJADA_S)) < 0.01


def test_el_zoom_nunca_corta_las_caras():
    # cara grande que ocupa casi todo el alto: el zoom baja o no se hace
    frames = [[(800, 100, 300, 300)]] * 5
    z, cx, cy = zooms.encuadre(zooms.zona(frames, 1920, 1080), 1.12)
    zona = zooms.zona(frames, 1920, 1080)
    if z > 1.0:
        w, h = 1 / z, 1 / z
        x0 = min(max(cx - w / 2, 0), 1 - w)
        y0 = min(max(cy - h / 2, 0), 1 - h)
        assert x0 <= zona[0] and zona[2] <= x0 + w and y0 <= zona[1] and zona[3] <= y0 + h


def test_caras_que_no_entran_sin_zoom():
    frames = [[(100, 100, 200, 200)], [(1500, 600, 300, 300)]]   # dos personas en las puntas
    assert zooms.encuadre(zooms.zona(frames, 1920, 1080), 1.12)[0] == 1.0
    tr, z, _, _ = zooms.planear(_rms(60, picos=(20,)), 0.5, 30.0, frames, 1920, 1080, 1.12, 3)
    assert tr == [] and z == 1.0


def test_sin_caras_al_centro():
    assert zooms.encuadre(None, 1.12) == (1.12, 0.5, 0.5)


def test_caritas_de_ruido_no_cuentan():
    assert zooms.zona([[(10, 10, 20, 20)]], 1920, 1080) is None


def test_filtro_fit_blur_con_y_sin_zooms():
    r = Render()
    base = Layout("fit_blur", Caja(0, 0, 1920, 1080), None, 0.0, None)
    assert "zoompan" not in filtro(base, r, False)
    con = Layout("fit_blur", Caja(0, 0, 1920, 1080), None, 0.0, None,
                 zooms=((9.75, 11.65),), zoom=1.12, zoom_centro=(0.4, 0.3))
    f = filtro(con, r, False)
    assert "zoompan" in f and "s=1080x608" in f and "9.75" in f and "[frente]" in f


def test_formato_por_defecto_titulo_arriba_y_punch_in_prendido():
    from clips_bot.config import load_settings
    s = load_settings()
    assert s.render.titulo_arriba is True and s.camara.seguir_cara is False
    assert s.render.zoom_picos is True and s.render.zoom_max == 1.35 and s.render.zoom_max_n == 3


def test_titulo_solo_los_primeros_3_s_con_fundido(tmp_path):
    from clips_bot import subtitles as sub
    from clips_bot.config import load_settings
    s = load_settings()
    sub.escribir_titulo_ass(tmp_path / "t.ass", "Un título de prueba", "spreen", s.subtitulos, s.render)
    texto = (tmp_path / "t.ass").read_text(encoding="utf-8")
    dialogos = [l for l in texto.splitlines() if l.startswith("Dialogue")]
    assert len(dialogos) == 2
    assert all(",0:00:03.00," in l and r"\fad(0,300)" in l for l in dialogos)


def test_picos_en_la_linea_del_mensaje_sin_tocar_la_seleccion():
    from clips_bot.telegram import por_que
    base = {"vistas": 100, "mediana_vistas": 50, "puntaje": 7}
    assert por_que({**base, "picos_volumen": 2}).endswith("Gemini 7/10 · 2 picos")
    assert "1 pico" in por_que({**base, "picos_volumen": 1})
    assert "0 picos" in por_que({**base, "picos_volumen": 0})
    assert "pico" not in por_que(base)          # clips viejos, sin el dato
    import inspect
    from clips_bot import seleccion
    assert "picos_volumen" not in inspect.getsource(seleccion)
