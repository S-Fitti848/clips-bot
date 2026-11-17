"""Así Nació, calidad para todos los videos (Santi, 2026-11-17: "que no tenga que corregir más escenas a mano"):
personajes según quién es y su rol, todos haciendo algo de su rol, la línea de producción con gente y producto, época
y lugar en el fondo, la ficha de cada escena y la ventanita de Tito que no tapa a nadie."""
import pytest

from clips_bot.animacion import acciones as ac, escenas as esc, marcas as mk, personajes as per


def test_ropa_segun_rol_y_epoca():
    assert ac.vestir("obrero", 1883, "hombre")["vestuario"] == "delantal"
    assert ac.vestir("obrero", 1883, "hombre")["sombrero"] == "boina"
    assert ac.vestir("obrero", 1965, "hombre")["vestuario"] == "mameluco"
    obrera = ac.vestir("obrera", 1883, "mujer")
    assert "falda_larga" in obrera["vestuario"] and obrera["sombrero"] == "cofia"
    assert ac.vestir("cajero", 1950, "hombre")["vestuario"] == "uniforme"
    assert ac.vestir("cliente", 1882, "hombre")["sombrero"] == "bombin"
    assert ac.vestir("cliente", 1882, "mujer")["vestuario"] == "falda_larga"
    emp = ac.vestir("empresario", 1883, "hombre")
    assert emp["vestuario"] == "traje" and emp["sombrero"] == "galera" and emp["bigote"]
    assert ac.vestir("cientifica", 2000, "mujer")["vestuario"] == "guardapolvo"
    assert "bigote" not in ac.vestir("empresario", 1883, "mujer")


def test_las_piezas_se_dibujan():
    base = per.personaje("narrador").svg()
    dibujos = {v: per.personaje("narrador", vestuario=v, color_vestuario="#3d6fb6").svg()
               for v in ("delantal", "mameluco", "uniforme", "traje", "guardapolvo", "calle")}
    assert all(len(x) > len(base) for x in dibujos.values()) and len(set(dibujos.values())) == 6
    assert len(per.personaje("mama", vestuario="falda_larga").svg()) > len(per.personaje("mama").svg())
    for s in ("bombin", "boina", "cofia"):
        assert per.personaje("narrador", sombrero=s).svg() != per.personaje("narrador").svg()


def _escena(actores, fondo="fabrica", anio=1883, prota="chocolate"):
    spec = {"fondo": fondo, "actores": actores, "objetos": []}
    d, _ = ac.escena_accion(spec, 3.0, 1, anio=anio, protagonista=prota)
    return d


@pytest.mark.parametrize("v3", [False, True])
def test_nadie_queda_quieto_con_las_manos_vacias(monkeypatch, v3):
    monkeypatch.setattr(ac, "MANOS_V3", v3)
    d = _escena([{"rol": "obrero", "accion": "quieto"}, {"rol": "obrera", "accion": "quieto"}])
    gente = [el for el in d["elementos"] if el.get("tipo") == "personaje"]
    assert all(el.get("objeto_rol") and el.get("lleva") for el in gente)
    en_mano = [el["nombre"] for el in d["elementos"] if el.get("en_mano")]
    assert sorted(en_mano) == ["caja", "chocolate"]
    assert all(el["cambios"].get("vestuario") for el in gente)       # con la ropa de su rol


def test_linea_de_produccion_con_producto_que_avanza():
    d = _escena([{"rol": "obrero", "accion": "quieto"}])
    linea = [el for el in d["elementos"] if el.get("linea")]
    assert linea[0]["nombre"] == "cinta_frente" and linea[0]["forma"] == 1        # de madera en 1883
    prods = [el for el in linea[1:] if el["nombre"] == "chocolate"]
    assert len(prods) >= 5 and all(el["keyframes"][-1]["x"] > 1000 for el in prods)
    # sin obreros, no hay cinta
    assert not [el for el in _escena([{"rol": "empresario", "accion": "senalar"}])["elementos"] if el.get("linea")]


def test_quieto_sin_rol_de_trabajo_no_valida():
    d = {"escenas": [{"fondo": "oficina", "actores": [{"rol": "empresario", "accion": "quieto"},
                                                      {"rol": "cajero", "accion": "quieto"}], "objetos": []}]}
    errores = mk.errores_quietos(d)
    assert len(errores) == 1 and "empresario" in errores[0]


def test_fondos_de_epoca():
    fab = esc.fondo("fabrica", 18831)
    assert "7a3f17" in fab and "5d4037" in fab                       # ollas de cobre y vigas de madera
    assert "#a8613f" in fab                                             # ladrillo
    assert "7a3f17" not in esc.fondo("fabrica", 19801)                 # en 1980, la fábrica de siempre
    ciudad = esc.fondo("ciudad", 18821)
    assert "7b4a2d" in ciudad                                          # el caballo del carro
    assert "8d8275" in ciudad                                          # adoquines
    assert "7b4a2d" not in esc.fondo("ciudad", 19601)                  # en 1960, autos


def test_ficha_de_cada_escena():
    d = {"protagonista": {"prop": "chocolate", "que_es": "una barra"},
         "escenas": [{"fondo": "fabrica", "anio_escena": 1883, "plano": "lejos", "objetos": [{"prop": "caja"}],
                      "actores": [{"rol": "fundador", "accion": "senalar", "genero": "hombre", "edad": "joven",
                                   "persona_real": "Milton Hershey"},
                                  {"rol": "obrera", "accion": "quieto", "genero": "mujer", "edad": "adulto"}]}]}
    f = mk.ficha_escena(d["escenas"][0], d)
    assert f["anio"] == 1883 and f["lugar"] == "fabrica"
    hershey, obrera = f["gente"]
    assert hershey["quien"] == "Milton Hershey" and "traje" in hershey["ropa"] and hershey["hace"] == "senalar"
    assert "falda_larga" in obrera["ropa"] and obrera["hace"] == "empaca el producto" and obrera["en_las_manos"] == "chocolate"
    t = mk.texto_ficha(f)
    assert "Milton Hershey" in t and "año 1883" in t


def test_tito_no_tapa_a_nadie():
    # alguien parado justo debajo de la primera esquina, y un objeto en la otra: Tito va a un lugar libre
    e = {"duracion": 4.0, "fondo": {"tipo": "fabrica", "semilla": 18831}, "camara": None,
         "elementos": [{"tipo": "prop", "nombre": "caja", "x": 150, "y": 640, "escala": 0.5},
                       {"tipo": "personaje", "nombre": "narrador", "x": 930, "y": 1500, "escala": 0.74}]}
    x, y = mk.lugar_tito(e, 1.0, 0)
    assert (x, y) not in ((150, 640), (930, 640)) and x is not None
    for c in mk.cajas_en_pantalla(e, 1.0, 2.6):
        hw, hh = mk.CAJA_TITO
        assert not (x - hw < c[2] and c[0] < x + hw and y - hh < c[3] and c[1] < y + hh)
    lleno = {**e, "elementos": [{"tipo": "prop", "nombre": "caja", "x": x_, "y": y_, "escala": 1.0}
                                for x_, y_ in mk.LUGARES_TITO]}
    assert mk.lugar_tito(lleno, 1.0, 0) == (None, None)
