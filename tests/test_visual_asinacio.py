"""Mejoras visuales de Así Nació (Santi, 2026-11-15; regla para todos los videos, motor actual): volumen,
escenarios con textura y luz, color por escena, cámara con primer plano de la cara y efectos."""

import math

from clips_bot.animacion import acciones as ac, escenas as esc, paleta as P, personajes as per, svg


def test_volumen_degrade_y_contorno_variable():
    c = svg.circulo(0, 0, 50, "#3a86ff")
    assert "url(#v3a86ff)" in c and 'transform="translate(' in c     # degradé + copia corrida del contorno
    doc = svg.documento(c)
    assert '<radialGradient id="v3a86ff"' in doc
    assert "url(#v" not in svg.circulo(0, 0, 5, "#ffffff", borde=False)   # lo sin contorno queda plano
    assert P.VOLUMEN is True


def test_brazos_redondos_y_cara_expresiva():
    pj = per.personaje("nene")
    enojado = pj.svg(per.Estado(cejas="enojo"))
    contento = pj.svg(per.Estado(boca="sonrisa"))
    assert pj.svg(per.Estado()) != enojado != contento
    assert pj.IRIS in pj.svg(per.Estado())                          # iris de color
    assert svg.oscurecer(pj.ropa, 0.22) in pj.svg(per.Estado())     # franja de sombra en los brazos


def test_escenarios_con_textura_luz_y_sombra():
    casa = esc.fondo("casa", 19600)
    for cosa in ("pat_madera", "pat_empapelado", "amb_haz", "amb_zocalo", "amb_sombra_mueble"):
        assert cosa in casa
    assert "pat_ladrillo" in esc.fondo("taller", 19600)
    assert esc.grade("casa") != esc.grade("ciudad")                 # cada lugar con su luz


def _escena(spec, dur=3.0, i=0):
    d, sfx = ac.escena_accion(spec, dur, i)
    return d, sfx


def test_primer_plano_de_la_cara_en_el_momento_fuerte():
    spec = {"parte": "giro", "fondo": "casa", "actores": [{"rol": "nene", "accion": "quieto", "desde": "izquierda",
                                                           "cara": "sorprendido"}], "objetos": [], "camara": "fija"}
    d, sfx = _escena(spec, 3.0, 1)
    assert any(k.get("zoom", 1) >= 1.8 for k in d["camara"])
    tranquila = {**spec, "parte": "problema", "actores": [{**spec["actores"][0], "cara": "normal"}]}
    d2, _ = _escena(tranquila, 3.0, 1)
    assert not any(k.get("zoom", 1) >= 1.8 for k in d2["camara"])
    # destellos en el remate, nunca encima de la cara
    dest = [el for el in d["elementos"] if el.get("nombre") == "destello"]
    assert dest and any(s == "ding" for _, s in sfx)
    cara = next(el for el in d["elementos"] if el["tipo"] == "personaje")
    pp = ac.Escena(3.0)
    x, y = pp.cara_de(cara, 1.0)
    assert all(math.hypot(el["x"] - x, el["y"] - y) > 150 for el in dest)
    assert d["transicion"]["tipo"] == "iris"


def test_lineas_de_movimiento_y_polvo():
    spec = {"parte": "gancho", "fondo": "casa", "actores": [{"rol": "nene", "accion": "tirar", "desde": "izquierda"}],
            "objetos": [{"prop": "pelota", "efecto": "vuela", "donde": "izquierda", "soporte": "mano"},
                        {"prop": "tele", "efecto": "se_rompe", "donde": "centro", "soporte": "mesa"}], "camara": "sacudon"}
    d, _ = _escena(spec, 3.0, 0)
    nombres = [el.get("nombre") for el in d["elementos"]]
    assert "lineas_mov" in nombres and "polvo" in nombres and "pedazo" in nombres
    assert not ac.composicion(d)


def test_estela_mira_hacia_donde_va():
    el = ac.estela([{"t": 0, "x": 0, "y": 0}, {"t": 0.1, "x": 200, "y": 0}, {"t": 0.2, "x": 200, "y": 200}])
    assert el["keyframes"][0]["rotacion"] == 0 and el["keyframes"][1]["rotacion"] == 90


def test_transicion_iris_se_dibuja():
    from PIL import Image

    from clips_bot.animacion import render as rd

    a, b = Image.new("RGBA", (108, 192), (255, 0, 0, 255)), Image.new("RGBA", (108, 192), (0, 0, 255, 255))
    medio = rd._transicion(a, b, "iris", 0.5)
    assert medio.getpixel((54, 96))[:3] == (0, 0, 255) and medio.getpixel((1, 1))[:3] == (255, 0, 0)


def test_los_efectos_del_render_no_los_elige_el_guion():
    from clips_bot.animacion import marcas as mk

    assert not set(mk.EFECTOS_RENDER) & set(mk.PROPS)
