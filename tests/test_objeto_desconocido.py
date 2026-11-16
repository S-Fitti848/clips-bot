"""Santi, 2026-11-16: un objeto que no está en la biblioteca nunca puede frenar el video de Así Nació (el 16/11 a
las 07:13 el guion reescrito por duración trajo 'masa_gris' y la línea de tiempo lo rechazó, después de pagar la
voz). Se dibuja con Claude (queda guardado) y, si eso falla, va el más parecido. Lo mismo con fondos, gestos y
poses de Tito: nunca frenan."""

from types import SimpleNamespace as NS

import pytest

from clips_bot.animacion import dibujos
from clips_bot.animacion import escenas as esc
from clips_bot.animacion import marcas, timeline


@pytest.fixture
def carpeta(monkeypatch, tmp_path):
    monkeypatch.setattr(dibujos, "CARPETA", tmp_path / "dibujos")
    return tmp_path / "dibujos"


def _guion(prop="masa_gris"):
    return {"escenas": [{"objetos": [{"prop": prop, "que_es": "masa gris de modelar"}],
                         "cadena": [{"prop": "jarron"}]}],
            "protagonista": {"prop": "dibujo_nuevo", "dibujo": "masa_gris"}, "dibujos_nuevos": []}


E = NS(marca=NS(nombre="Play-Doh"), angulo="origen")


def test_un_objeto_que_falta_se_dibuja_y_queda_guardado(monkeypatch, carpeta):
    pedidos = []

    def dibujar(cliente, nombre, descripcion, contexto=""):
        pedidos.append(nombre)
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / f"{nombre}.svg").write_text("<g/>", encoding="utf-8")
        (carpeta / f"{nombre}.json").write_text('{"descripcion": "x"}', encoding="utf-8")
        return "<g/>"

    monkeypatch.setattr(dibujos, "dibujar", dibujar)
    d = _guion()
    assert marcas.resolver_objetos(object(), d, E) == []
    assert pedidos == ["masa_gris"]                          # una sola vez aunque aparezca dos
    assert esc.es_prop("masa_gris") and d["escenas"][0]["objetos"][0]["prop"] == "masa_gris"
    assert marcas.prop_real(d["protagonista"]) == "masa_gris"


def test_si_no_se_puede_dibujar_va_el_mas_parecido(monkeypatch, carpeta):
    carpeta.mkdir(parents=True)
    (carpeta / "masa_modelar.svg").write_text("<g/>", encoding="utf-8")
    (carpeta / "masa_modelar.json").write_text('{"descripcion": "bolita de masa blanda de modelar"}', encoding="utf-8")
    monkeypatch.setattr(dibujos, "dibujar", lambda *a, **k: (_ for _ in ()).throw(ValueError("no salió")))
    d = _guion()
    cambios = marcas.resolver_objetos(object(), d, E)
    assert cambios == ["masa_gris → masa_modelar"]
    assert d["escenas"][0]["objetos"][0]["prop"] == "masa_modelar"
    assert d["protagonista"]["prop"] == "masa_modelar" and "dibujo" not in d["protagonista"]
    assert d["escenas"][0]["cadena"][0]["prop"] == "jarron"   # lo que existe no se toca


def test_sin_cliente_tambien_resuelve(carpeta):
    d = _guion("pelota_futbol")
    marcas.resolver_objetos(None, d, E)
    assert d["escenas"][0]["objetos"][0]["prop"] == "pelota"


def test_el_reemplazo_nunca_es_martillo_ni_un_efecto(carpeta):
    for raro in ("masa_gris", "martillo_neumatico", "xyzw", "polvo_magico"):
        assert esc.prop_parecido(raro) not in esc.NO_REEMPLAZO
    assert esc.prop_parecido("xyzw") == "caja"


def test_la_linea_de_tiempo_nunca_frena(carpeta):
    el = timeline.Elemento.desde_dict({"tipo": "prop", "nombre": "masa_gris"}, "elemento 3", 3.0)
    assert esc.es_prop(el.datos["nombre"])
    p = timeline.Elemento.desde_dict({"tipo": "personaje", "nombre": "joven",
                                      "gestos": [{"t": 0.5, "gesto": "bailar_tango"}]}, "e", 3.0)
    from clips_bot.animacion import personajes as per
    assert p.datos["gestos"][0]["gesto"] in per.GESTOS


def test_el_video_del_16_11_ya_no_se_frena_en_la_reescritura():
    """La reescritura por duración y la revisión visual pasan por resolver_objetos antes de la línea de tiempo."""
    src = open(marcas.__file__, encoding="utf-8").read()
    i = src.index("def armar_video")
    cuerpo = src[i:]
    assert cuerpo.count("resolver_objetos(cliente, d, e, avisar)") >= 4
    reescritura = cuerpo.index("no pude acortar el guion")
    assert cuerpo.index("resolver_objetos", reescritura) < cuerpo.index("tiempos[\"voz_s\"]")
