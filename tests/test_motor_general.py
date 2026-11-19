"""El motor de Así Nació, para TODOS los videos (Santi, 2026-11-19, después del Wilson 8/19): fondos por rubro, el
protagonista fiel al producto real, poses de acción reusables (nadie parado) y física (nada flotando)."""
import json

from clips_bot.animacion import acciones as ac
from clips_bot.animacion import escenas as esc
from clips_bot.animacion import fiel


def test_la_tienda_vende_lo_del_rubro():
    assert esc.rubro_de("deportes") == "deportes"
    assert esc.rubro_de("juguetes") == "jugueteria"
    assert esc.rubro_de("higiene") == "farmacia"
    assert esc.rubro_de("autos") == "concesionaria"
    assert esc.rubro_de("bebidas", "la vendían en una farmacia") == "farmacia"    # la frase manda
    assert esc.rubro_de("", "") == "almacen"
    for r in esc.RUBROS:
        assert esc.es_fondo(f"tienda:{r}")
        assert len(esc.fondo(f"tienda:{r}", 1003)) > 1000
    assert not esc.es_fondo("tienda:inventado")
    # la de deportes no tiene las botellas del almacén
    assert esc.fondo("tienda:deportes", 6) != esc.fondo("tienda:almacen", 6)


def test_nada_flota_salvo_que_se_mueva():
    assert ac.apoyar("zapatilla", "aire") == "piso"
    assert ac.apoyar("botella", "aire") == "mesa"
    assert ac.apoyar("pregunta", "aire") == "aire"            # un ícono sí
    assert ac.apoyar("pelota", "aire", "vuela") == "aire"      # la frase lo pide
    assert ac.apoyar("botella", "mesa", fondo="playa") == "piso"   # afuera no hay mesas


def test_nadie_parado_segun_su_rol():
    d, _ = ac.escena_accion({"fondo": "estadio", "actores": [
        {"rol": "deportista", "accion": "quieto", "desde": "izquierda"},
        {"rol": "cliente", "accion": "senalar", "desde": "derecha"}]}, 3.0, 1, protagonista="pelota")
    personas = [el for el in d["elementos"] if el.get("tipo") == "personaje" and not el.get("multitud")]
    gestos = {g["gesto"] for p in personas for g in p["gestos"]}
    assert "lanzar" in gestos and "pagar" in gestos
    assert any(el.get("en_mano") for el in d["elementos"])      # algo en las manos


class _Haiku:
    def __init__(self, reconoce=(False, True)):
        self.reconoce = list(reconoce)
        self.pedidos = []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, **kw):
        self.pedidos.append(sistema[:20])
        if "svg" in schema["properties"]:
            return json.dumps({"svg": '<circle cx="0" cy="0" r="90" fill="#ffffff" stroke="#2b2233" stroke-width="8"/>'
                                      '<circle cx="-30" cy="-20" r="12" fill="#d9452f"/>',
                               "anio_desde": 0})
        if "reconocible" in schema["properties"]:
            ok = self.reconoce.pop(0)
            return json.dumps({"que_ves": "una pelota", "reconocible": ok, "falta": "" if ok else "la cara roja"})
        return json.dumps({"descripcion": "pelota de vóley blanca con una cara roja pintada a mano",
                           "detalles": ["paneles curvos", "cara roja"]})


def test_protagonista_fiel(tmp_path, monkeypatch):
    from clips_bot.animacion import dibujos

    monkeypatch.setattr(fiel, "ARCHIVO", tmp_path / "fieles.json")
    monkeypatch.setattr(dibujos, "CARPETA", tmp_path / "dibujos")
    d = {"protagonista": {"prop": "pelota", "que_es": "pelota de vóley Wilson", "dibujo": ""},
         "escenas": [{"objetos": [{"prop": "pelota"}]}, {"objetos": [{"prop": "pelota"}, {"prop": "caja"}]}]}
    c = _Haiku((False, True))
    hechos = fiel.asegurar(c, d, "Wilson")
    nombre = d["protagonista"]["dibujo"]
    assert nombre.startswith("fiel_wilson") and nombre.endswith("_v2")      # el primero no se reconocía
    assert all(o["dibujo"] == nombre for e in d["escenas"] for o in e["objetos"] if o["prop"] == "dibujo_nuevo")
    assert d["escenas"][1]["objetos"][1]["prop"] == "caja"                   # lo demás, igual
    assert hechos
    # la segunda vez, la descripción sale de la caché y el dibujo de la biblioteca
    c2 = _Haiku((True,))
    d2 = {"protagonista": {"prop": "pelota", "que_es": "pelota de vóley Wilson", "dibujo": ""}, "escenas": []}
    fiel.asegurar(c2, d2, "Wilson")
    assert not any(p.startswith("Describís") for p in c2.pedidos)
