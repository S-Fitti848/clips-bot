"""Santi, 2026-11-28: 1 video de 4. La verificación contra el artículo ya bajado (sin abrir links), el banco como red
(hasta BANCO_MAX historias) y videojuegos y marcas que se alternan en tecnología."""
import json

import pytest

from clips_bot import historias_usadas as hu
from clips_bot import locales
from clips_bot import web_historias as wh

ART = ("Ignacio Ugarte fue un marino peruano. En 1847 rescató a la tripulación de un barco hundido frente al Callao. "
       "Por esa hazaña recibió una medalla del gobierno del Perú. ") * 3


class Haiku:
    def __init__(self, datos, es_real=True):
        self.datos, self.es_real, self.prompts = datos, es_real, []

    def json(self, sistema, prompt, schema, temperatura=0.0, **k):
        self.prompts.append((sistema, prompt))
        return json.dumps({"datos": self.datos, "resumen": "r", "es_real": self.es_real, "problema": ""})


def test_verifica_con_citas_del_articulo_sin_web():
    h = Haiku([{"dato": "marino peruano", "cita": "Ignacio Ugarte fue un marino peruano"},
               {"dato": "1847", "cita": "En 1847 rescató a la tripulación"},
               {"dato": "medalla", "cita": "recibió una medalla del gobierno del Perú"}])
    v = wh.verificar_con_articulo(h, "Ugarte rescató marinos", 1847, "Callao", ART, "Ignacio Ugarte")
    assert v.ok and len(v.datos) == 3
    assert "NO busques" in h.prompts[0][0] and ART[:50] in h.prompts[0][1]


def test_una_cita_inventada_no_cuenta():
    h = Haiku([{"dato": "a", "cita": "Ignacio Ugarte fue un marino peruano"},
               {"dato": "b", "cita": "salvó a doscientas personas en Lima"},
               {"dato": "c", "cita": "recibió una medalla del gobierno del Perú"}])
    v = wh.verificar_con_articulo(h, "x", 1847, "Callao", ART)
    assert not v.ok and "1 sin cita" in v.motivo


def test_si_el_articulo_contradice_no_sirve():
    v = wh.verificar_con_articulo(Haiku([], es_real=False), "x", 1847, "Callao", ART)
    assert not v.ok


def test_sin_articulo_o_sin_respuesta_es_falla_tecnica():
    with pytest.raises(wh.WebError):
        wh.verificar_con_articulo(Haiku([]), "x", 1847, "Callao", "corto")

    class Caido:
        def json(self, *a, **k):
            raise ValueError("cortado")

    with pytest.raises(wh.WebError):
        wh.verificar_con_articulo(Caido(), "x", 1847, "Callao", ART)


def test_el_banco_se_prueba_hasta_ocho():
    assert locales.BANCO_MAX >= 8 > locales.MAX_VERIFICAR


def test_grupo_de_tecnologia():
    assert hu.grupo_tec("Nintendo lanzó el Super Mario Bros") == "videojuegos"
    assert hu.grupo_tec("Apple presentó el iPhone") == "marcas"
    assert hu.grupo_tec("x", "videojuegos") == "videojuegos"
    assert hu.ultimo_grupo_tec() == ""          # sin registro activo
