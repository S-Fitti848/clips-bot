"""Así Nació (Santi, 2026-11-16; `animacion.uso_manos`): el producto usado de verdad por dos manos paso a paso (Tupper:
agarrar, abrir la tapa, guardar comida, cerrar y apretar), manos con detalle y la inspiración animada (la tapa de la
lata de pintura encastra sobre el Tupper)."""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_animacion_marcas import guion  # noqa: E402

from clips_bot.animacion import escenas as esc  # noqa: E402
from clips_bot.animacion import escenas_lib as lib  # noqa: E402
from clips_bot.animacion import marcas  # noqa: E402
from clips_bot.animacion import uso_v3  # noqa: E402
from clips_bot.animacion.timeline import Video  # noqa: E402

PARTES = {"cuerpo": "lata", "tapa": "moneda", "contenido": "hamburguesa"}
TUPPER = ["agarrar", "abrir_tapa", "meter", "cerrar_tapa", "apretar"]


def _valor(el, campo, t):
    kfs = sorted((float(k["t"]), float(k[campo])) for k in el.get("keyframes") or [] if campo in k)
    if not kfs or t <= kfs[0][0]:
        return kfs[0][1] if kfs else float(el[campo])
    for (a, va), (b, vb) in zip(kfs, kfs[1:]):
        if a <= t <= b:
            return va + (vb - va) * (t - a) / max(1e-6, b - a)
    return kfs[-1][1]


def test_la_secuencia_del_tupper_paso_a_paso():
    h = uso_v3.escena_uso(5.0, "tupper", PARTES, TUPPER)
    nombres = [el["nombre"] for el in h["elementos"]]
    assert nombres[:3] == ["mesa", "lata", "moneda"] and "hamburguesa" in nombres
    manos = [el for el in h["elementos"] if el["nombre"] == "mano"]
    assert len(manos) == 2 and all(m["detalle"] for m in manos)
    sonidos = [s for _, s in h["sfx"]]
    assert "pop" in sonidos and sonidos.count("tac") >= 3 and "ding" in sonidos          # el clic del cierre
    tapa = next(el for el in h["elementos"] if el["nombre"] == "moneda")
    cuerpo = next(el for el in h["elementos"] if el["nombre"] == "lata")
    comida = next(el for el in h["elementos"] if el["nombre"] == "hamburguesa")
    tramo = 5.0 / 5
    # la tapa sube al abrir y vuelve a su lugar al cerrar
    assert _valor(tapa, "y", 1.5 * tramo) < _valor(tapa, "y", 0) - 100
    assert abs(_valor(tapa, "y", 4.0 * tramo) - _valor(tapa, "y", 0)) < 20
    # después de agarrar, las manos SIEMPRE tocan el objeto (a menos de 330 px del cuerpo, la tapa o la comida que meten)
    for t in [tramo + k * 0.25 for k in range(int(4 * tramo / 0.25))]:
        for m in manos:
            x, y = _valor(m, "x", t), _valor(m, "y", t)
            cerca = min(math.hypot(x - _valor(o, "x", t), y - _valor(o, "y", t)) for o in (tapa, cuerpo, comida))
            assert cerca < 330, (t, m["forma"], round(cerca))
    assert _valor(manos[0], "fase", tramo) == 1.0               # al agarrar, los dedos se cierran
    Video.desde_dict({"fps": 30, "escenas": [{"duracion": 5.0, "fondo": "casa", "elementos": h["elementos"],
                                              "camara": h["camara"]}]})


def test_sin_tapa_los_pasos_de_tapa_no_van():
    assert uso_v3.pasos_validos(TUPPER, {"cuerpo": "masa"}) == ["agarrar"] or \
        uso_v3.pasos_validos(TUPPER, {"cuerpo": "masa"}) == ["agarrar", "girar"]
    assert uso_v3.pasos_validos(["amasar", "moldear"], {}) == ["agarrar", "amasar", "moldear"]


def test_la_inspiracion_encastra_en_el_producto():
    h = uso_v3.escena_inspiracion(3.0, "lata", "moneda", "tupper")
    pieza = next(el for el in h["elementos"] if el["nombre"] == "moneda")
    producto = next(el for el in h["elementos"] if el["nombre"] == "tupper")
    t_llega = 3.0 * 0.68
    assert abs(_valor(pieza, "x", t_llega) - producto["x"]) < 5 and _valor(pieza, "rotacion", t_llega) == 180
    flecha = next(el for el in h["elementos"] if el["nombre"] == "flecha")
    assert flecha["desde"] >= t_llega - 0.01
    assert any(s == "ding" for _, s in h["sfx"]) and any(el["nombre"] == "destello" for el in h["elementos"])


def test_la_mano_con_detalle_solo_donde_se_pide():
    nueva = esc.prop("mano", forma=1, detalle=True, fase=1.0, manga="#6b4a2b")
    vieja = esc.prop("mano", forma=1)
    assert "f4f1ea" in nueva and "6b4a2b" in nueva                  # el puño de la camisa y la manga de la época
    assert "f4f1ea" not in vieja                                     # sin el OK, la de siempre


def test_la_biblioteca_arma_las_escenas_nuevas():
    h = lib.construir("uso_manos", "manos", {"uso": {"partes": PARTES, "pasos": TUPPER}, "objetos": []}, 4.0, 2, "lata")
    assert any(el["nombre"] == "mano" for el in h["elementos"])
    h = lib.construir("inspiracion", "cerca", {"inspiracion": {"fuente": "lata", "pieza": "moneda", "producto": "lata"},
                                               "objetos": []}, 3.0, 2, "lata")
    assert any(el["nombre"] == "flecha" for el in h["elementos"])
    h = lib.construir("inspiracion", "cerca", {"objetos": []}, 3.0, 2, "lata")     # sin datos: objeto_gira
    assert h is not None


def test_preparar_uso_dibuja_las_partes_y_marca_las_escenas(monkeypatch, tmp_path):
    from clips_bot.animacion import dibujos

    monkeypatch.setattr(dibujos, "CARPETA", tmp_path)

    def dibujar(cli, nombre, desc, ctx=""):
        (tmp_path / f"{nombre}.svg").write_text("<g/>", encoding="utf-8")
        (tmp_path / f"{nombre}.json").write_text(json.dumps({"descripcion": desc}), encoding="utf-8")
        return "<g/>"

    monkeypatch.setattr(dibujos, "dibujar", dibujar)
    d = guion(protagonista={"prop": "jarron", "que_es": "un recipiente de plástico", "dibujo": ""})
    d["uso"] = {"escena": 3, "pasos": TUPPER, "cuerpo": "tazón celeste de plástico", "tapa": "tapa blanca redonda",
                "contenido": "porción de ensalada con tomate"}
    d["inspiracion"] = {"escena": 5, "fuente": "lata de pintura metálica", "pieza": "tapa redonda de la lata de pintura"}
    hechos = marcas.preparar_uso(object(), d)
    e3, e5 = d["escenas"][2], d["escenas"][4]
    assert e3["accion_escena"] == "uso_manos" and e3["uso"]["partes"]["cuerpo"] == "jarron_cuerpo"
    assert e3["uso"]["partes"]["tapa"] == "jarron_tapa" and e3["uso"]["partes"]["contenido"].startswith("porcion")
    assert e5["accion_escena"] == "inspiracion" and e5["inspiracion"]["pieza"].endswith("_pieza")
    assert len(hechos) == 2


def test_apagado_no_cambia_las_escenas():
    d = guion()
    resp = {"ganchos": [{"tipo": "gigante", "texto": "¿UN JUGUETE DE JABÓN?"},
                        {"tipo": "vuela", "texto": "VENDIÓ UN MILLÓN EN 1949"},
                        {"tipo": "explota", "texto": "NADIE LO QUERÍA COMPRAR"}],
            "decorado": [], "uso": {"escena": 3, "pasos": TUPPER, "cuerpo": "", "tapa": "", "contenido": ""},
            "inspiracion": {"escena": 0, "fuente": "", "pieza": ""}}

    class Cli:
        def json(self, *a, **k):
            return json.dumps(resp)

    antes = d["escenas"][2].get("accion_escena")
    assert marcas.USO_V4 is False and marcas.completar_v3(Cli(), d)
    assert d["escenas"][2].get("accion_escena") == antes
