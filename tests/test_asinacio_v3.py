"""Así Nació, reglas del 2026-11-16 (Santi; `animacion.reglas_v3`): gancho de 3 opciones con 2-3 cortes de ~1 s y
golpe en cada uno, texto grande arriba, rayos y efectos; ninguna toma de más de 3 s, 2 planos por frase (lejos →
cerca a las manos y el objeto), zoom siempre; decorado de contexto en interiores; rótulo con año y lugar; la
revisión elige el gancho y redibuja un protagonista que no se parece al real."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_animacion_marcas import guion  # noqa: E402

from clips_bot.animacion import gancho_v3 as gv  # noqa: E402
from clips_bot.animacion import marcas  # noqa: E402
from clips_bot.animacion.timeline import Video  # noqa: E402

OPS = [{"tipo": "gigante", "texto": "¿UN JUGUETE DE JABÓN?"}, {"tipo": "multiplica", "texto": "VENDIÓ MILLONES EN 1956"},
       {"tipo": "explota", "texto": "NADIE LO QUERÍA COMPRAR"}]


def _d():
    d = guion()
    d["ganchos"] = [dict(o) for o in OPS]
    for e in d["escenas"][1:]:
        e["decorado"] = ["botella", "radio", "jarron"]
    return d


def _armar(d, v3=True, visual=False):
    n = len(marcas.segmentos(d))
    inicios = [round(i * 3.4, 2) for i in range(n)]
    return marcas.linea_de_tiempo(d, inicios, round(n * 3.4, 2), [], None, v3=v3, visual=visual)


def _cortes(camara):
    return [float(k["t"]) for k in camara if k.get("easing") == "escalon"]


@pytest.mark.parametrize("j", [0, 1, 2])
def test_el_gancho_son_cortes_de_un_segundo_con_golpe_y_texto(j):
    d = _d()
    d["gancho_elegido"] = j
    datos, sfx = _armar(d)
    g = datos["escenas"][0]
    assert g["gancho_v3"] == OPS[j]["tipo"] and g["duracion"] <= 3.4
    cortes = _cortes(g["camara"])
    assert len(cortes) == 2 and all(0.8 <= b - a <= 1.3 for a, b in zip([0.0] + cortes, cortes + [g["duracion"]]))
    golpes = [t for t, s in sfx if s == "golpe" and t < g["duracion"]]
    assert len(golpes) == 3                                           # un golpe en cada corte
    texto = [el for el in g["elementos"] if el.get("tipo") == "gancho"]
    assert texto and texto[0]["texto"] == OPS[j]["texto"].upper() and texto[0]["tam"] >= 100
    nombres = {el.get("nombre") for el in g["elementos"]}
    assert {"rayos", "polvo", "destello"} <= nombres                  # colores fuertes y efectos
    Video.desde_dict({**datos, "audio": None})


def test_ninguna_toma_dura_mas_de_3_s_y_cada_frase_tiene_2_planos():
    datos, _ = _armar(_d())
    for esc in datos["escenas"][1:]:
        if esc.get("congela") or esc.get("girar") or float(esc["duracion"]) < 1.2:
            continue
        bordes = [0.0] + _cortes(esc["camara"]) + [float(esc["duracion"])]
        tomas = [b - a for a, b in zip(bordes, bordes[1:])]
        assert len(tomas) >= 2 and max(tomas) <= gv.TOMA_MAX_S + 0.05
        zooms = [k["zoom"] for k in esc["camara"] if "zoom" in k]
        assert len(set(zooms)) == len(zooms) or max(zooms) > min(zooms)   # nunca quieta


def test_sin_v3_nada_cambia():
    d = _d()
    datos, _ = _armar(d, v3=False)
    assert "gancho_v3" not in datos["escenas"][0]


def test_el_decorado_va_adentro_y_no_en_la_calle():
    d = _d()
    datos, _ = _armar(d)
    for esc in datos["escenas"]:
        deco = [el for el in esc.get("elementos") or [] if el.get("decorado")]
        if esc.get("fondo", {}).get("tipo") in ("ciudad", "campo", "puerto", "cielo"):
            assert not deco


def test_el_rotulo_lleva_anio_y_lugar():
    d = _d()
    d["visual"] = [{"rotulo": "Buenos Aires"} if i == 2 else ({"rotulo": "1956"} if i == 3 else {})
                   for i in range(len(d["escenas"]))]
    d["escenas"][2]["anio_escena"] = 1947
    datos, _ = _armar(d, visual=True)
    textos = [str(el.get("texto")) for esc in datos["escenas"] for el in esc.get("elementos") or []
              if "·" in str(el.get("texto") or "")]
    assert textos and all("·" in t for t in textos)
    assert "1947 · Buenos Aires" in textos and "1956 · Buenos Aires" in textos


def test_las_opciones_del_guion_se_validan():
    marcas.REGLAS_V3 = True
    try:
        d = _d()
        assert marcas.errores_v3(d) == []
        d["ganchos"][1]["tipo"] = "gigante"
        assert any("DISTINTOS" in e for e in marcas.errores_v3(d))
        d = _d()
        d["ganchos"][0]["texto"] = "UNO DOS"
        assert any("ganchos" in e for e in marcas.errores_v3(d))
        d = _d()
        for e in d["escenas"]:
            e.pop("decorado", None)
        assert any("decorado" in e for e in marcas.errores_v3(d))
        assert "REGLA 16" in marcas.sistema_guion()
    finally:
        marcas.REGLAS_V3 = False
    assert "REGLA 16" not in marcas.sistema_guion()


class _Elige:
    def __init__(self, mejor):
        self.mejor, self.imagenes = mejor, None

    def json(self, sistema, prompt, schema, temp=0.7, imagenes=None, **k):
        self.imagenes = imagenes
        return json.dumps({"mejor": self.mejor, "por_que": "frena el dedo"})


def test_la_revision_elige_el_gancho_mas_llamativo(tmp_path):
    d = _d()
    llamadas = []

    def capturar(datos, t, png):
        from PIL import Image
        Image.new("RGB", (60, 100), "red").save(png)
        llamadas.append(t)

    cli = _Elige(3)
    txt = marcas.elegir_gancho(cli, d, lambda d_: _armar(d_)[0], tmp_path, capturar=capturar)
    assert d["gancho_elegido"] == 2 and "opción 3" in txt and len(cli.imagenes) == 3
    assert len(llamadas) == 9 and (tmp_path / "gancho_opcion_1.jpg").exists()


def test_redibujar_el_protagonista(monkeypatch):
    from clips_bot.animacion import dibujos

    pedidos = []
    monkeypatch.setattr(dibujos, "dibujar", lambda cli, nombre, desc, ctx="": pedidos.append((nombre, desc)) or "<g/>")
    d = _d()
    d["protagonista"] = {"prop": "botella", "que_es": "un Tupper", "dibujo": ""}
    d["escenas"][0]["objetos"] = [{"prop": "botella", "efecto": "quieto", "donde": "centro", "soporte": "mesa"}]
    hecho = marcas.redibujar_protagonista(object(), d, "recipiente de plástico bajo con tapa hermética")
    assert pedidos and pedidos[0][0] == "un_tupper_real" and "tapa hermética" in pedidos[0][1]
    assert marcas.prop_real(d["protagonista"]) == "un_tupper_real" and "redibujé" in hecho
    assert marcas.prop_real(d["escenas"][0]["objetos"][0]) == "un_tupper_real"


class _Completa:
    def __init__(self, *resps):
        self.resps, self.prompts = list(resps), []

    def json(self, sistema, prompt, schema, temp=0.7, **k):
        self.prompts.append(prompt)
        return json.dumps(self.resps.pop(0))


def test_las_opciones_y_el_decorado_van_en_un_pedido_aparte():
    """El guion principal no cambia de schema (con los campos nuevos pasaba el tope de gramática de Claude)."""
    assert marcas.schema_guion() is marcas.SCHEMA_GUION
    d = guion()
    malo = {"ganchos": [dict(OPS[0]), dict(OPS[0]), dict(OPS[2])], "decorado": []}
    bueno = {"ganchos": [dict(o) for o in OPS], "decorado": [{"escena": 2, "objetos": ["radio", "botella"]},
                                                             {"escena": 99, "objetos": ["x"]}]}
    cli = _Completa(malo, bueno)
    assert marcas.completar_v3(cli, d)
    assert d["ganchos"] == OPS and d["escenas"][1]["decorado"] == ["radio", "botella"]
    assert "DISTINTOS" in cli.prompts[1]            # el segundo pedido lleva el error del primero
    assert not marcas.completar_v3(_Completa(malo, malo, malo), guion())
