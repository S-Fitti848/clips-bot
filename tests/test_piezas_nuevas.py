"""Así Nació único sin hacerlo todo desde cero (Santi, 2026-11-17): las piezas se reusan, la escena entera no se
repite; lo que falta (un lugar) se crea una vez y queda guardado; /costos muestra las piezas nuevas por video."""
import json

import pytest

from clips_bot import bitacora
from clips_bot.animacion import dibujos, escenas as esc, marcas as mk

SVG = '<rect x="0" y="0" width="1080" height="1920" fill="#88ccee"/><rect x="0" y="1380" width="1080" height="540" fill="#c9a66b"/>'


@pytest.fixture
def fondos(tmp_path, monkeypatch):
    monkeypatch.setattr(dibujos, "CARPETA_FONDOS", tmp_path / "fondos")
    monkeypatch.setattr(dibujos, "probar_fondo", lambda svg: None)
    return tmp_path / "fondos"


class Cli:
    def __init__(self):
        self.pedidos = 0

    def json(self, sistema, prompt, schema, temp, **k):
        self.pedidos += 1
        return json.dumps({"svg": SVG, "interior": True})


def test_un_lugar_que_falta_se_dibuja_una_vez_y_queda(fondos):
    cli = Cli()
    d = {"escenas": [{"frase": "a", "fondo": "campo"},
                     {"frase": "en la bolera", "fondo": "tienda", "lugar_nuevo": "bolera de los años 50 con pistas",
                      "anio_escena": 1955}]}
    hechos = mk.crear_lugares(cli, d, avisar=lambda *_: None)
    nombre = d["escenas"][1]["fondo"]
    assert nombre.startswith("lugar_") and "bolera" in nombre and hechos and cli.pedidos == 1
    assert (fondos / f"{nombre}.svg").exists() and dibujos.fondo_es_interior(nombre)
    assert esc.es_fondo(nombre) and "#88ccee" in esc.fondo(nombre, 19551)
    # el próximo video lo reusa sin dibujarlo
    d2 = {"escenas": [{"frase": "b", "fondo": "tienda", "lugar_nuevo": "bolera de los años 50 con pistas"}]}
    mk.crear_lugares(cli, d2, avisar=lambda *_: None)
    assert d2["escenas"][0]["fondo"] == nombre and cli.pedidos == 1
    assert nombre in mk._fondos_nuevos()


def test_si_no_se_puede_dibujar_queda_el_mas_parecido(fondos):
    class Mal:
        def json(self, *a, **k):
            return json.dumps({"svg": "<script/>", "interior": False})

    d = {"escenas": [{"frase": "x", "fondo": "tienda", "lugar_nuevo": "pista de patinaje"}]}
    mk.crear_lugares(Mal(), d, avisar=lambda *_: None)
    assert d["escenas"][0]["fondo"] == "tienda" and not d["escenas"][0]["lugar_nuevo"]


def test_la_escena_entera_no_se_repite():
    d = {"protagonista": {"prop": "pelota"},
         "escenas": [{"frase": "g"}, {"frase": "a", "accion_escena": "vender_tienda", "fondo": "tienda",
                                     "plano": "frente", "camara": "fija", "objetos": [{"prop": "pelota"}]}]}
    completa = mk.firma_completa(d["escenas"][1], "pelota")
    assert completa == "vender_tienda@tienda|frente|fija|{prota}"
    err = mk.errores_unicas(d, [], [[completa]])
    assert err and "IGUALES" in err[0]
    d["escenas"][1]["plano"] = "lejos"          # otro plano: ya es otra escena
    assert mk.errores_unicas(d, [], [[completa]]) == []


def test_costos_muestra_las_piezas_nuevas_por_video():
    filas = [{"canal": "asinacio", "titulo": "Frisbee", "costo_usd": 1.62,
              "detalle": {"claude": [{"paso": "dibujos", "usd": 0.04}, {"paso": "guion", "usd": 0.8}]}},
             {"canal": "pequena_historia", "titulo": "Colón", "costo_usd": 0.3, "detalle": {}}]
    t = bitacora.texto_piezas(filas)
    assert "Frisbee: US$ 1.62 · piezas US$ 0.04" in t and "pasó de US$ 1,50" in t and "Colón" not in t
