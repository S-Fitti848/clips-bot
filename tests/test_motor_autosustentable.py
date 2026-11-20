"""Motor de Así Nació que se autosustenta (Santi, 2026-11-20): manos con dedos, acciones completas, expresiones según el
momento, menos gente, el lugar según el oficio, videos de 25-30 s, reemplazo por escena base y revisión calibrada."""

from clips_bot import calidad
from clips_bot.animacion import acciones as ac
from clips_bot.animacion import emociones as emo
from clips_bot.animacion import manos as M
from clips_bot.animacion import marcas as mk
from clips_bot.animacion import personajes as per
from clips_bot.animacion import plantillas as pl
from clips_bot.animacion import reemplazo as rz
from clips_bot.animacion import tito as ti


def _armar(accion, fondo="oficina", anio=1950, prota="botella", **extra):
    ac.MANOS_V3 = True
    try:
        return ac.escena_accion({"accion_escena": accion, "fondo": fondo, "frase": "x", **extra}, 4.5, 2, anio=anio,
                                protagonista=prota)[0]
    finally:
        ac.MANOS_V3 = False


def test_manos_con_dedos_en_personajes_y_tito():
    for forma in M.FORMAS:
        assert M.mano(0, 0, 30, forma).count("<path") >= 8          # palma + dedos y pulgar, contorno y relleno
    assert per.manos_de_gesto("senalar") == ("relajada", "senala")
    assert per.manos_de_gesto("p_sostener_a") == ("agarra", "agarra")
    assert per.manos_de_gesto("punos")[1] == "puno"
    # Tito señala con el índice: ya no es un palito pegado a una bola
    assert "M342 -612 L392 -634" not in ti.tito_svg("senala")


def test_las_manos_en_la_cara_van_delante_de_la_cabeza():
    pj = per.personaje("narrador")
    e = per.estado_de_gesto("cara_manos")
    hy = -150 - 270 + 38
    assert pj._a_la_cara(1, hy, e.brazo_der) and not pj._a_la_cara(1, hy, per.estado_de_gesto("reposo").brazo_der)
    # los puños cerrados quedan adelante del pecho, con los codos para afuera (no cruzados)
    izq, der = pj.brazos(per.estado_de_gesto("punos"))
    assert der[-1][0] > 0 > izq[-1][0] and der[1][0] > der[-1][0]


def test_tomar_es_el_movimiento_completo():
    d = _armar("producto_en_uso", fondo="cocina", _categoria="bebidas")
    p0 = next(el for el in d["elementos"] if el.get("tipo") == "personaje")
    gestos = [g["gesto"] for g in p0["gestos"]]
    assert gestos.count("p_tomar_alto") >= 2                       # sube, baja y vuelve a subir en 4,5 s
    assert per.extra_de_gesto("p_tomar_alto")["cabeza"] < 0        # la cabeza va para atrás
    botella = next(el for el in d["elementos"] if el.get("a_la_boca"))
    ys = [k["y"] for k in botella["keyframes"]]
    assert max(ys) - min(ys) > 100                                 # la botella viaja del pecho a la boca
    # una comida se come
    d = _armar("producto_en_uso", fondo="cocina", _categoria="golosinas", prota="chocolate")
    p0 = next(el for el in d["elementos"] if el.get("tipo") == "personaje")
    assert "p_comer_a" in [g["gesto"] for g in p0["gestos"]]


def test_los_dedos_cierran_sobre_lo_que_se_agarra():
    d = _armar("fabrica_produce", fondo="fabrica")
    els = d["elementos"]
    agarrados = [k for k, el in enumerate(els) if el.get("agarre")]
    assert agarrados and all(els[k + 1]["nombre"] == "dedos" for k in agarrados)


def test_emociones_cara_y_cuerpo():
    assert emo.de_escena({"frase": "Casi quiebran por las deudas"}) == "perdida"
    assert emo.de_escena({"frase": "Vendió millones en un año"}) == "exito"
    assert emo.de_escena({"frase": "Todos se burlaron de su idea"}) == "burla"
    assert emo.de_escena({"frase": "x", "accion_escena": "crisis"}) == "perdida"
    assert emo.de_escena({"frase": "x", "emocion": "determinado"}) == "determinado"
    # de frente con las manos libres: el cuerpo también (éxito = brazos arriba y salta)
    prota = {"tipo": "personaje", "nombre": "narrador", "x": 300, "y": ac.PISO}
    otro = {"tipo": "personaje", "nombre": "narrador", "x": 700, "y": ac.PISO}
    emo.aplicar([prota, otro], "exito", 3.0)
    assert prota["cara"] == "euforico" and prota["gestos"][0]["gesto"] == "festejar"
    assert any("y" in k for k in prota["keyframes"]) and otro["cara"] == "feliz"
    # burla: los demás se ríen; el protagonista frustrado
    prota, otro = dict(prota, keyframes=[]), dict(otro)
    emo.aplicar([prota, otro], "burla", 3.0)
    assert prota["cara"] == "frustrado" and otro["cara"] == "risa"
    # de perfil trabajando con el producto: cambia solo la cara
    p = {"tipo": "personaje", "nombre": "narrador", "perfil": 1, "lleva": "_", "gestos": [{"t": 0, "gesto": "p_cinta_a"}]}
    emo.aplicar([p], "perdida", 3.0)
    assert p["cara"] == "devastado" and p["gestos"][0]["gesto"] == "p_cinta_a"


def test_menos_gente_y_el_lugar_segun_el_oficio():
    d = _armar("exito_multitud", fondo="ciudad")
    assert not [el for el in d["elementos"] if el.get("multitud")]
    assert d["fondo"]["tipo"] == "tienda:vacia"
    assert any(el.get("nombre") == "grafico_sube" for el in d["elementos"])
    assert pl.lugar_de_oficio({"_oficio": "farmacéutico"}) == "laboratorio"
    assert pl.lugar_de_oficio({"_oficio": "empresario textil"}) == "oficina"
    assert pl.lugar_de_oficio({"actores": [{"rol": "inventor"}]}) == "taller"
    lab = _armar("taller_inventor", fondo="taller", _oficio="químico")
    assert lab["fondo"]["tipo"] == "laboratorio" and any(el.get("nombre") == "frasco" for el in lab["elementos"])
    libre = ac.escena_accion({"frase": "x", "fondo": "casa", "actores": [{"rol": "joven", "accion": "usar"}] * 3},
                             3.0, 2)[0]
    assert len([el for el in libre["elementos"] if el.get("tipo") == "personaje" and not el.get("multitud")]) <= 2


def test_videos_de_25_a_30_s_con_emocion_en_el_guion():
    assert (mk.MIN_S, mk.MAX_S, mk.FRASES_MIN, mk.FRASES_MAX) == (25.0, 30.0, 6, 7)
    props = mk.SCHEMA_GUION["properties"]
    assert "emocion" in props["escenas"]["items"]["properties"] and "oficio" in props["protagonista"]["properties"]
    assert "REGLA 17" in mk.SISTEMA_GUION and "REGLA 18" in mk.SISTEMA_GUION


def test_reemplazo_por_escena_base_sin_claude():
    assert rz.base_para_frase("Pero las ventas cayeron") == "crisis"
    assert rz.base_para_frase("Las ventas cayeron", fallo="crisis") != "crisis"
    assert rz.base_para_frase("Y así nació", parte="final") == "cierre_tito"
    d = {"escenas": [{"frase": "a"}, {"frase": "La fábrica producía miles", "accion_escena": "libre",
                                      "fondo": "fabrica", "anio_escena": 1920, "objetos": [{"prop": "dibujo_nuevo"}],
                                      "actores": [{"rol": "obrero"}]}]}
    nuevo = rz.spec_base(d, 1)
    assert nuevo["accion_escena"] == "fabrica_produce" and nuevo["anio_escena"] == 1920
    assert nuevo["objetos"] == [] and nuevo["actores"] == [{"rol": "obrero"}]
    assert mk.VUELTAS_REVISION == 0 and not mk.RESCATE and mk.TOPE_USD_VIDEO == 0.60


def test_revision_calibrada_y_minimo_15():
    assert "1 SEGUNDO" in mk.REVISION_CALIBRADA and "NO marques detalles del fondo" in mk.REVISION_CALIBRADA
    assert "menos de 3 detalles" not in mk.REVISION_FICHA
    assert calidad.minimo("asinacio") == 15
    ficha = mk.ficha_escena({"frase": "Casi quiebran", "fondo": "oficina"}, {})
    assert ficha["emocion"] == "perdida" and "EMOCIÓN" in mk.texto_ficha(ficha)
