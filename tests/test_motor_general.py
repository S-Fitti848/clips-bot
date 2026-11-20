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
    d, _ = ac.escena_accion({"fondo": "tienda:deportes", "actores": [
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


def test_en_el_estadio_se_pasan_la_pelota():
    d, sfx = ac.escena_accion({"fondo": "estadio", "actores": [
        {"rol": "joven", "accion": "asustarse", "desde": "izquierda", "cara": "sorprendido"},
        {"rol": "deportista", "accion": "quieto", "desde": "derecha"}]}, 3.2, 1, protagonista="pelota")
    personas = [el for el in d["elementos"] if el.get("tipo") == "personaje" and not el.get("multitud")]
    assert sorted(p_["pase"] for p_ in personas) == [0, 1]
    for p_ in personas:
        gestos = {g["gesto"] for g in p_["gestos"]}
        assert "lanzar" in gestos and "atrapar" in gestos            # tira y recibe
    pelota = next(el for el in d["elementos"] if el.get("tipo") == "prop" and el.get("pase"))
    xs = [k["x"] for k in pelota["keyframes"]]
    assert max(xs) - min(xs) > 300                                     # va de uno al otro
    assert not any(el.get("en_mano") for el in d["elementos"])        # una sola pelota, en juego
    # el festejo queda
    d2, _ = ac.escena_accion({"fondo": "estadio", "actores": [
        {"rol": "joven", "accion": "festejar", "desde": "izquierda"}]}, 2.0, 1, protagonista="pelota")
    assert not any(el.get("tipo") == "prop" and el.get("pase") for el in d2["elementos"])


def test_la_escena_de_manos_usa_el_protagonista_fiel(tmp_path, monkeypatch):
    from clips_bot.animacion import dibujos

    monkeypatch.setattr(fiel, "ARCHIVO", tmp_path / "fieles.json")
    monkeypatch.setattr(dibujos, "CARPETA", tmp_path / "dibujos")
    d = {"protagonista": {"prop": "pelota", "que_es": "pelota de vóley Wilson", "dibujo": ""},
         "escenas": [{"objetos": [{"prop": "pelota"}]},
                     {"accion_escena": "uso_manos", "uso": {"partes": {"cuerpo": "pelota", "tapa": "", "contenido": ""},
                                                            "pasos": ["girar"]}},
                     {"accion_escena": "inspiracion", "inspiracion": {"producto": "pelota", "fuente": "x"}}]}
    fiel.asegurar(_Haiku((True,)), d, "Wilson")
    nombre = d["protagonista"]["dibujo"]
    assert d["escenas"][1]["uso"]["partes"]["cuerpo"] == nombre
    assert d["escenas"][2]["inspiracion"]["producto"] == nombre


# ---- las fallas del Lego (Santi, 2026-11-19) ----------------------------------------------------------------------
class _HaikuAntes(_Haiku):
    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, **kw):
        if "antes" in schema["properties"]:
            self.pedidos.append(sistema[:20])
            return json.dumps({"descripcion": "ladrillo rojo de plástico con ocho botones", "detalles": ["8 botones"],
                               "anio_desde": 1949, "antes": "un patito de madera con ruedas"})
        return super().json(sistema, prompt, schema, temperatura, imagenes, **kw)


def test_antes_de_existir_va_lo_que_hacian(tmp_path, monkeypatch):
    from clips_bot.animacion import dibujos

    monkeypatch.setattr(fiel, "ARCHIVO", tmp_path / "fieles.json")
    monkeypatch.setattr(dibujos, "CARPETA", tmp_path / "dibujos")
    d = {"protagonista": {"prop": "caja", "que_es": "ladrillo de Lego", "dibujo": ""},
         "escenas": [{"anio_escena": 1932, "objetos": [{"prop": "caja"}]},
                     {"anio_escena": 1958, "objetos": [{"prop": "caja"}]}]}
    fiel.asegurar(_HaikuAntes((True,)), d, "Lego")
    prota = d["protagonista"]["dibujo"]
    antes = d["protagonista"]["antes"]
    assert antes["hasta"] == 1949 and antes["dibujo"].startswith("fiel_lego_antes")
    assert fiel.de_la_escena(d, 1932, prota) == antes["dibujo"]
    assert fiel.de_la_escena(d, 1958, prota) == prota
    e = fiel.epoca_de_escena({"objetos": [{"prop": prota}], "uso": {"partes": {"cuerpo": prota}}}, prota, antes["dibujo"])
    assert e["objetos"][0]["prop"] == antes["dibujo"] and e["uso"]["partes"]["cuerpo"] == antes["dibujo"]
    # el moderno ya no existe en 1932: el filtro de época lo saca de una escena de entonces
    from clips_bot.animacion import escenas as esc_

    assert not esc_.existe_en(prota, 1932) and esc_.existe_en(prota, 1960)


def test_el_guion_ya_tenia_lo_de_antes(tmp_path, monkeypatch):
    from clips_bot.animacion import dibujos

    monkeypatch.setattr(fiel, "ARCHIVO", tmp_path / "fieles.json")
    monkeypatch.setattr(dibujos, "CARPETA", tmp_path / "dibujos")
    dibujos.CARPETA.mkdir(parents=True)
    (dibujos.CARPETA / "juguete_de_madera.svg").write_text('<circle cx="0" cy="0" r="50" fill="#a0522d"/>', encoding="utf-8")
    d = {"protagonista": {"prop": "caja", "que_es": "ladrillo de Lego", "dibujo": ""},
         "escenas": [{"anio_escena": 1932, "objetos": [{"prop": "dibujo_nuevo", "dibujo": "juguete_de_madera"}]},
                     {"anio_escena": 1958, "objetos": [{"prop": "caja"}]}]}
    fiel.asegurar(_HaikuAntes((True,)), d, "Lego")
    assert d["protagonista"]["antes"]["dibujo"] == "juguete_de_madera"


def test_el_chequeo_del_fiel_acepta_lo_parecido():
    assert "SE PARECE" in fiel.SISTEMA_RECONOCE and "nunca agregues" in fiel.SISTEMA_RECONOCE


def test_manos_humanas_que_agarran():
    d, _ = ac.escena_accion({"fondo": "taller", "accion_escena": "armar_mesa", "plano": "arriba",
                             "objetos": [{"prop": "auto"}]}, 2.0, 1, anio=1932)
    manos = [el for el in d["elementos"] if el.get("nombre") == "mano"]
    assert len(manos) == 2 and all(m_.get("detalle") and m_.get("fase", 0) > 0 for m_ in manos)
    obj = next(el for el in d["elementos"] if el.get("nombre") == "auto")
    assert all(abs(k["rotacion"]) <= 6 for k in obj["keyframes"])        # apoyado, no dando vueltas en el aire


def test_la_fabrica_siempre_con_obreros_y_nunca_el_escenario():
    d, _ = ac.escena_accion({"fondo": "fabrica", "accion_escena": "inspiracion", "plano": "cerca",
                             "actores": [{"rol": "fundador", "accion": "probar"}], "objetos": [{"prop": "caja"}]},
                            3.0, 1, anio=1949, protagonista="caja")
    assert d["fondo"]["tipo"] != "escenario"
    roles = [el.get("rol") for el in d["elementos"] if el.get("tipo") == "personaje"]
    assert any(r in ("obrero", "obrera") for r in roles)


def test_los_graficos_siempre_con_gente():
    for objetos, gesto in (([{"prop": "grafico_baja"}], "preocupar"), ([{"prop": "grafico_sube"}], None)):
        d, _ = ac.escena_accion({"fondo": "oficina", "actores": [], "objetos": objetos}, 2.5, 1, anio=2004)
        gente = [el for el in d["elementos"] if el.get("tipo") == "personaje" and not el.get("multitud")]
        assert gente
        if gesto:
            assert any(g["gesto"].startswith(gesto) for p_ in gente for g in p_["gestos"])
    d, _ = ac.escena_accion({"fondo": "oficina", "accion_escena": "contador_ventas", "frase": "superó a Mattel",
                             "objetos": [{"prop": "grafico_sube"}, {"prop": "caja"}]}, 2.5, 1, anio=2015, protagonista="caja")
    assert d["fondo"]["tipo"] == "oficina"
    assert [el for el in d["elementos"] if el.get("tipo") == "personaje" and not el.get("multitud")]
    assert not [el for el in d["elementos"] if el.get("nombre") == "grafico_sube" and el.get("lib")]   # la pila no es de gráficos
