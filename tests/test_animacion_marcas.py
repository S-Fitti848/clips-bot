"""Canal de marcas animadas (2026-11-14): catálogo, rotación, puntaje, guion validado contra el
artículo, escenas → línea de tiempo y el tick de la escucha. Sin red, sin render y sin Claude."""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from clips_bot import db
from clips_bot.animacion import acciones as ac
from clips_bot.animacion import escenas as esc
from clips_bot.animacion import sfx as sfx_mod
from clips_bot.animacion import marcas as mk
from clips_bot.animacion.timeline import Video
from clips_bot.config import load_settings
from clips_bot.subtitles import Palabra

HOY = date(2026, 11, 20)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "clips.db")
    yield c
    c.close()


class ClienteFalso:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.pedidos = []

    def json(self, sistema, prompt, schema, temperatura=0.7, **kw):
        self.pedidos.append(prompt)
        r = self.respuestas.pop(0)
        return r if isinstance(r, str) else json.dumps(r)


def marca(nombre="Havanna", angulos=("origen", "nombre")):
    return mk.Marca(nombre, "Argentina", "golosinas", nombre, tuple(angulos))


# ---- catálogo -----------------------------------------------------------------------------

def test_catalogo_tiene_al_menos_300_marcas_validas():
    cat = mk.cargar_catalogo()
    assert len(cat) >= 300
    assert len({m.nombre for m in cat}) == len(cat)
    assert len({m.wiki_es for m in cat}) == len(cat)
    for m in cat:
        assert m.angulos and set(m.angulos) <= set(mk.ANGULOS), m
        assert m.wiki_es and m.pais and m.categoria
    nombres = {m.nombre for m in cat}
    for latina in ("Grupo Bimbo", "Inca Kola", "Havanna", "Arcor", "Quilmes", "Corona", "Bagley"):
        assert latina in nombres
    for global_ in ("Coca-Cola", "Nike", "Nintendo"):
        assert global_ in nombres


def test_catalogo_rechaza_angulos_desconocidos(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text('marcas:\n  - {nombre: "X", pais: "Y", categoria: "z", wiki_es: "X", angulos: [origen, rumor]}\n',
                 encoding="utf-8")
    with pytest.raises(ValueError, match="rumor"):
        mk.cargar_catalogo(p)


# ---- rotación -------------------------------------------------------------------------------

def test_un_angulo_no_se_repite_nunca(conn):
    cat = [marca()]
    mk.registrar(conn, "Havanna", "origen", HOY)
    for dias in (0, 7, 30, 400):
        pares = [(m.nombre, a) for m, a in mk.disponibles(conn, cat, HOY + timedelta(days=dias))]
        assert ("Havanna", "origen") not in pares


def test_la_marca_no_vuelve_en_7_dias(conn):
    cat = [marca(), marca("Arcor", ("origen",))]
    mk.registrar(conn, "Havanna", "origen", HOY)
    for dias in range(7):   # el mismo día y los 6 siguientes: ni con otro ángulo
        nombres = {m.nombre for m, _ in mk.disponibles(conn, cat, HOY + timedelta(days=dias))}
        assert nombres == {"Arcor"}, dias
    pares = [(m.nombre, a) for m, a in mk.disponibles(conn, cat, HOY + timedelta(days=7))]
    assert ("Havanna", "nombre") in pares and ("Havanna", "origen") not in pares


def test_candidatos_de_marcas_distintas_y_que_pasan_la_rotacion(conn):
    cat = mk.cargar_catalogo()
    mk.registrar(conn, "Coca-Cola", "logo", HOY - timedelta(days=1))
    cands = mk.candidatos(conn, cat, HOY, n=40)
    assert len(cands) == 40
    assert len({m.nombre for m, _ in cands}) == 40
    assert all(a in m.angulos for m, a in cands)
    assert "Coca-Cola" not in {m.nombre for m, _ in cands}
    # determinista por día (mismo día = mismos candidatos)
    assert [(m.nombre, a) for m, a in mk.candidatos(conn, cat, HOY, n=40)] == [(m.nombre, a) for m, a in cands]


def test_sin_nada_disponible_no_hay_candidato(conn):
    mk.registrar(conn, "Havanna", "origen", HOY - timedelta(days=30))
    mk.registrar(conn, "Havanna", "nombre", HOY - timedelta(days=20))
    assert mk.candidatos(conn, [marca()], HOY) == []
    with pytest.raises(mk.SinCandidato):
        mk.proponer(conn, ClienteFalso(), None, HOY, [marca()])


# ---- puntaje ---------------------------------------------------------------------------------

def _nota(i, n, sensible=False, dato="dato"):
    return {"indice": i, "dato": dato, "marca_conocida": n, "dato_sorprendente": n, "giro": n,
            "humor": n, "sensible": sensible}


def test_elegir_deja_solo_8_o_mas_sin_sensibles_de_mejor_a_peor():
    cands = [(marca("A"), "origen", "t"), (marca("B"), "nombre", "t"), (marca("C"), "origen", "t"),
             (marca("D"), "origen", "t")]
    cliente = ClienteFalso({"candidatos": [_nota(0, 7), _nota(1, 8), _nota(2, 10, sensible=True),
                                           _nota(3, 9), _nota(9, 10)]})
    out = mk.elegir(cliente, cands)
    assert [(e.marca.nombre, e.promedio) for e in out] == [("D", 9.0), ("B", 8.0)]
    assert set(out[0].notas) == set(mk.CRITERIOS)


def test_el_promedio_es_de_los_cuatro_criterios():
    e = mk.Elegido(marca(), "origen", {"marca_conocida": 10, "dato_sorprendente": 8, "giro": 7, "humor": 8})
    assert e.promedio == 8.25


def test_ninguno_llega_a_8_no_sale(conn):
    class Wiki:
        def texto(self, lang, titulo):
            return "texto"

    cliente = ClienteFalso({"candidatos": [_nota(0, 7)]})
    # 2026-11-15: no es "no sale": esas marcas quedan afuera hoy y se reintenta con otras en 1 h
    with pytest.raises(mk.GuionesFallidos, match="8"):
        mk.proponer(conn, cliente, Wiki(), HOY, [marca()], n=1)
    assert marca().nombre in mk.fallidos_de(conn, HOY)
    with pytest.raises(mk.SinCandidato):                      # ya no queda ninguna: ahí sí, no sale
        mk.proponer(conn, cliente, Wiki(), HOY, [marca()], n=1)


# ---- guion -----------------------------------------------------------------------------------
# Reglas de Santi (2026-11-14, después de Nerf y Monopoly): mostrar no contar, la mascota-locutor,
# toda empresa o persona presentada, problema → idea → qué pasó → final, y movimiento.

FUENTE = ("Havanna es una empresa argentina de alfajores fundada en 1947 en Mar del Plata, una ciudad de "
          "playa. El nombre viene del Havanna Bar, un bar de los socios que después cerró. Los alfajores "
          "se volvieron famosos en toda la costa y la gente los llevaba de regalo después de las vacaciones.")


def _a(rol, accion, desde="centro", hacia="ninguno", cara="normal"):
    return {"rol": rol, "accion": accion, "desde": desde, "hacia": hacia, "cara": cara}


def _o(prop, efecto, donde="centro", texto="", soporte=None):
    return {"prop": prop, "efecto": efecto, "donde": donde, "texto": texto,
            "soporte": soporte or ac.soporte_de(prop, None)}


def _c(prop, soporte, donde):
    return {"prop": prop, "soporte": soporte, "donde": donde}


ESCENAS = [
    ("¡Otra caja de alfajores voló por el aire!", "gancho", "casa",
     [_a("joven", "tirar", "izquierda")], [_o("galletitas", "vuela"), _o("jarron", "se_rompe", "derecha")]),
    ("Unos socios tenían un bar en Mar del Plata, una ciudad de playa.", "problema", "ciudad",
     [_a("empresario", "caminar", "izquierda", "centro")], []),
    ("El bar se llamaba Havanna Bar, pero vendía poco.", "problema", "tienda",
     [_a("vendedor", "asustarse", "derecha")], [_o("grafico_baja", "aparece", "izquierda")]),
    ("Entonces pensaron vender alfajores con el mismo nombre.", "idea", "oficina",
     [_a("empresario", "pensar", "izquierda"), _a("fundador", "senalar", "derecha")], []),
    ("En 1947 fundaron la empresa y empezaron a fabricar alfajores.", "que_paso", "fabrica",
     [_a("fundador", "martillar", "izquierda")], [_o("galletitas", "quieto", "derecha")]),
    ("Los alfajores se volvieron famosos.", "que_paso", "ciudad",
     [_a("cliente", "correr", "izquierda", "derecha")], [_o("billete", "llueve")]),
    ("¿Y el bar? Cerró, y el alfajor se quedó con el nombre.", "final", "escenario",
     [_a("fundador", "festejar", "centro")], [_o("corona", "crece", "derecha")]),
]


ACCIONES_ESC = ["libre", "libre", "vender_tienda", "reunion", "fabrica_produce", "contador_ventas", "objeto_gira"]


def guion(**cambios):
    escenas = [{"frase": f, "parte": p, "fondo": fo, "actores": a, "objetos": o, "camara": "fija",
                "texto_pantalla": "1947" if i == 4 else "", "transicion": "barrido",
                "cadena": [_c("tele", "mesa", "izquierda"), _c("lampara", "piso", "centro")] if i == 0 else [],
                "viaje_a_anio": 1947 if i == 1 else 0, "vuelve_al_presente": i == 6,
                # biblioteca de escenas (2026-11-15): la acción de cada frase; "libre" como mucho 4 de 10
                "accion_escena": ACCIONES_ESC[i] if i < len(ACCIONES_ESC) else "libre", "plano": "lejos"}
               for i, (f, p, fo, a, o) in enumerate(ESCENAS)]
    d = {"titulo": "Havanna: el alfajor que se llama como un bar", "descripcion": "La historia del nombre.",
         "tono": "curioso", "pregunta_gancho": "¿Por qué se llama así?", "escenas": escenas,
         "locutor": [{"despues_de_frase": 3, "texto": "Spoiler: el bar no la pasó nada bien."}],
         "protagonista": {"prop": "galletitas", "que_es": "los alfajores Havanna"},
         "entidades": [{"nombre": "Mar del Plata", "presentacion": "una ciudad de playa", "frase": 2},
                       {"nombre": "Havanna Bar", "presentacion": "el bar se llamaba", "frase": 3}]}
    d.update(cambios)
    return d


def test_un_guion_bueno_valida():
    assert mk.validar_guion(guion(), marca(), FUENTE) == []


def test_datos_que_no_estan_en_el_articulo():
    d = guion()
    d["escenas"][4]["frase"] = "En 1952 Pedro fundó la empresa y empezaron a fabricar alfajores."
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "1952" in err and "Pedro" in err


def test_el_texto_en_pantalla_y_el_locutor_tambien_se_validan():
    d = guion()
    d["escenas"][2]["texto_pantalla"] = "1999"
    d["locutor"][0]["texto"] = "Spoiler: en 1980 el bar no la pasó nada bien."
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "1999" in err and "1980" in err


def test_texto_de_pantalla_en_mayusculas_no_son_nombres():
    """Visto en la Pi con Nerf: "NA, MENTIRA" daba "Mentira" como un nombre que no estaba."""
    d = guion()
    d["escenas"][5]["texto_pantalla"] = "NA, MENTIRA"
    assert mk.validar_guion(d, marca(), FUENTE) == []
    assert mk._sin_mayusculas("NA, MENTIRA") == "Na, mentira"


def test_gancho_corto_y_de_accion():
    d = guion()
    d["escenas"][0]["frase"] = "¡Otra caja de alfajores voló por el aire de la casa!"
    assert any("menos de 3 segundos" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][0]["actores"] = [_a("joven", "quieto")]
    d["escenas"][0]["objetos"] = [_o("caja", "quieto")]
    d["escenas"][0]["cadena"] = []
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "ACCIÓN" in err and "estáticas" in err


def test_escenas_con_sentido():
    """Santi: la vasija cayendo del cielo no tiene sentido; la lámpara de pie al lado del sillón."""
    d = guion()
    d["escenas"][2]["objetos"] = [_o("jarron", "cae_y_se_rompe", soporte="aire")]
    d["escenas"][3]["objetos"] = [_o("botella", "aparece")]
    d["escenas"][5]["objetos"] = [_o("caja", "llueve")]
    d["escenas"][6]["objetos"] = [_o("lampara", "quieto", soporte="estante")]
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "¿de dónde?" in err and "de la nada" in err and "solo llueven" in err and "lampara va en" in err


def test_la_cadena_es_opcional_y_si_va_se_entiende():
    # Santi, 2026-11-15: la destrucción en cadena era SOLO para Nerf; cada marca, su propio gancho.
    d = guion()
    d["escenas"][0]["cadena"] = []
    assert not any("cadena" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d["escenas"][1]["cadena"] = [_c("tele", "mesa", "izquierda")] * 2
    assert any("solo en el gancho" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][0]["cadena"] = [_c("tele", "mesa", "izquierda")] * 2
    assert any("mismo lugar" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d["escenas"][0]["cadena"] = [_c("cuadro", "mesa", "izquierda"), _c("tele", "mesa", "derecha")]
    assert any("cuadro va en pared" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_viaje_al_pasado_cuando_cambia_la_epoca():
    d = guion()
    d["escenas"][1]["viaje_a_anio"] = 0                  # 1947 en la frase 5 sin viaje
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "habla de 1947" in err and "sin haber viajado" in err
    d = guion()
    d["escenas"][0]["viaje_a_anio"] = 1947
    assert any("gancho es en el presente" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][6]["vuelve_al_presente"] = False
    d["escenas"][6]["frase"] = "Hoy el bar ya no existe, y el alfajor se quedó con el nombre."
    assert any("habla de hoy" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][1]["viaje_a_anio"] = 1932                # el año del viaje también va contra el artículo
    assert any("1932" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_ninguna_escena_estatica():
    """"Dos personajes hablando no engancha": una escena sin movimiento no pasa."""
    d = guion()
    d["escenas"][3]["actores"] = [_a("empresario", "senalar"), _a("fundador", "quieto")]
    d["escenas"][3]["accion_escena"] = "libre"          # las de la biblioteca ya traen su acción
    assert any("estáticas (solo personajes parados): 4" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_problema_idea_que_paso_final_en_orden():
    d = guion()
    d["escenas"][3]["parte"] = "final"
    assert any("orden" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    for e in d["escenas"][1:-1]:
        e["parte"] = "que_paso"
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "`problema`" in err and "`idea`" in err


def test_el_locutor_interrumpe_como_mucho_una_vez():
    """Santi (2026-11-20): en 25-30 s Tito interrumpe 0 o 1 vez."""
    assert not any("interrumpe" in e for e in mk.validar_guion(guion(locutor=[]), marca(), FUENTE))
    dos = [{"despues_de_frase": 2, "texto": "Spoiler: el bar no la pasó nada bien."},
           {"despues_de_frase": 3, "texto": "Y sí, el bar cerró."}]
    assert any("interrumpe" in e for e in mk.validar_guion(guion(locutor=dos), marca(), FUENTE))
    ultima = [{"despues_de_frase": 8, "texto": "Spoiler: el bar no la pasó nada bien."}]
    assert any("entre la 1 y la 6" in e for e in mk.validar_guion(guion(locutor=ultima), marca(), FUENTE))


def test_toda_empresa_o_persona_se_presenta():
    """Monopoly: Santi no sabía qué era Parker Brothers."""
    err = " ".join(mk.validar_guion(guion(entidades=[]), marca(), FUENTE))
    assert "entidades" in err and "Bar" in err and "Plata" not in err   # Mar del Plata es un lugar
    mal = [{"nombre": "Mar del Plata", "presentacion": "la capital mundial del turismo", "frase": 2},
           {"nombre": "Havanna Bar", "presentacion": "el bar se llamaba", "frase": 3}]
    assert any("Mar del Plata: presentalo" in e for e in mk.validar_guion(guion(entidades=mal), marca(), FUENTE))


def test_los_lugares_no_hace_falta_presentarlos_y_el_giro_puede_ir_en_el_medio():
    """Visto en la Pi con el Nerf: "un inventor de Minnesota" y "en Estados Unidos" pedían presentación,
    y gancho → … → que_paso → giro → que_paso → final no pasaba."""
    assert mk.es_lugar("Un inventor de Minnesota armó la pelota.", "Minnesota")
    assert mk.es_lugar("Se vendió en Estados Unidos.", "Unidos")
    assert not mk.es_lugar("Parker Brothers compró la idea.", "Parker")
    d = guion()
    d["escenas"][3]["frase"] = "Entonces en Rosario pensaron vender alfajores con el mismo nombre."
    assert not any("entidades" in e for e in mk.validar_guion(d, marca(), FUENTE + " Rosario"))
    d = guion()
    d["escenas"][5]["parte"] = "giro"
    assert not any("orden" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_nada_de_temas_sensibles():
    d = guion()
    d["escenas"][6]["frase"] = "¿Y el bar? Cerró después de un accidente, obvio."
    assert any("sensibles" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_props_y_fondos_tienen_que_existir():
    d = guion()
    d["escenas"][1]["objetos"] = [_o("logo_de_la_marca", "vuela")]
    d["escenas"][2]["fondo"] = "luna"          # la playa, el estadio y la cocina existen desde el 17/11
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "logo_de_la_marca" in err and "luna" in err


def test_escribir_guion_reintenta_con_los_errores():
    malo = guion(locutor=[{"despues_de_frase": 2, "texto": "Spoiler: el bar no la pasó nada bien."},
                          {"despues_de_frase": 3, "texto": "Y sí, el bar cerró."}])
    cliente = ClienteFalso(malo, guion())
    e = mk.Elegido(marca(), "nombre", {c: 9 for c in mk.CRITERIOS})
    assert mk.escribir_guion(cliente, e, FUENTE, avisar=lambda *_: None)["locutor"]
    # 2026-11-15: el segundo pedido es una CORRECCIÓN PUNTUAL (el guion como contexto y los errores)
    assert "ERRORES:" in cliente.pedidos[1] and "el locutor interrumpe" in cliente.pedidos[1]
    # Santi, 2026-11-16: una regla de ESTILO que nunca se cumple no frena el video: sale con aviso
    d = mk.escribir_guion(ClienteFalso(malo, malo, malo, malo, malo), e, FUENTE, reintentos=5, avisar=lambda *_: None)
    assert any("locutor" in x for x in d["_estilo_pendiente"]) and "⚠️" in mk.aviso_estilo(d)


def test_el_chequeo_de_haiku_tambien_hace_reintentar():
    e = mk.Elegido(marca(), "nombre", {c: 9 for c in mk.CRITERIOS})
    haiku = ClienteFalso({"sin_presentar": ["Havanna Bar: no se dice qué es"], "confuso": [], "no_muestra": [],
                          "sin_sentido": [], "rotulo": []},
                         {"sin_presentar": [], "confuso": [], "no_muestra": [], "sin_sentido": [], "rotulo": []})
    cliente = ClienteFalso(guion(), guion())
    mk.escribir_guion(cliente, e, FUENTE, avisar=lambda *_: None, revisor=haiku)
    assert len(cliente.pedidos) == 2 and "presentá" in cliente.pedidos[1]
    assert "SE VE" in haiku.pedidos[0]


def test_si_haiku_no_responde_sigue():
    class Roto:
        def json(self, *a, **k):
            raise RuntimeError("caído")

    assert mk.chequear_calidad(Roto(), guion(), marca()) == []


# ---- escenas de acción, pausa del locutor y SFX ---------------------------------------------

def test_props_y_fondos_nuevos_se_dibujan():
    for nombre in mk.FONDOS:
        assert esc.fondo(nombre, 3).startswith("<")
    for nombre in esc.PROPS:
        assert "<" in esc.prop(nombre, texto="HAVANNA", color="#123456")
    assert "<path" in esc.prop("ventana", rota=True) and esc.prop("ventana", rota=True) != esc.prop("ventana")
    for nuevo in ("pelota", "lampara", "ventana", "pedazo", "martillo", "jarron", "microfono", "botella"):
        assert nuevo in esc.PROPS
    assert {"casa", "taller"} <= set(esc.FONDOS)


@pytest.mark.parametrize("accion", ac.ACCIONES)
def test_cada_accion_arma_una_escena_valida(accion):
    d, sfx = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", accion, "izquierda", "derecha")],
                               "objetos": [], "camara": "fija"}, 3.0, 0)
    v = Video.desde_dict({"escenas": [d]})
    v.cuadro(45)
    assert all(s in ac.SFX for _, s in sfx)


@pytest.mark.parametrize("efecto", ac.EFECTOS)
def test_cada_efecto_arma_una_escena_valida(efecto):
    d, _ = ac.escena_accion({"fondo": "taller", "actores": [], "objetos": [_o("pelota", efecto)],
                             "camara": "paneo"}, 3.0, 2)
    Video.desde_dict({"escenas": [d]}).cuadro(60)


def test_lo_que_vuela_rompe_la_lampara_y_suena_en_el_impacto():
    d, sfx = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "tirar", "izquierda")],
                               "objetos": [_o("pelota", "vuela"), _o("lampara", "se_rompe")],
                               "camara": "fija"}, 3.0, 0)
    pelota = next(e for e in d["elementos"] if e.get("nombre") == "pelota")
    pedazos = [e for e in d["elementos"] if e.get("nombre") == "pedazo"]
    lampara = next(e for e in d["elementos"] if e.get("nombre") == "lampara")
    impacto = pelota["keyframes"][-1]["t"]
    # la lámpara recibe el golpe, se cae de costado y se rompe contra el piso
    assert lampara["hasta"] == pytest.approx(impacto, abs=0.02)
    rotura = pedazos[0]["desde"]
    assert len(pedazos) == 8 and impacto < rotura < impacto + 0.5
    assert any(s == "vidrio" and t == pytest.approx(rotura, abs=0.02) for t, s in sfx)
    assert ("whoosh" in [s for _, s in sfx])
    # el sacudón de cámara en el golpe
    assert any(k.get("x") for k in d["camara"] if abs(k["t"] - impacto) < 0.45)


def test_la_pelota_rebota_con_boing():
    _, sfx = ac.escena_accion({"fondo": "casa", "actores": [], "objetos": [_o("pelota", "rebota")]}, 3.5, 0)
    assert sum(s == "boing" for _, s in sfx) >= 2


def test_la_cadena_rompe_cada_cosa_en_orden_con_su_sonido():
    d, sfx = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "tirar", "izquierda")], "objetos": [],
                               "cadena": [_c("tele", "mesa", "izquierda"), _c("lampara", "piso", "centro"),
                                          _c("cuadro", "pared", "derecha")]}, 3.0, 0, primera=True)
    pelota = next(e for e in d["elementos"] if e.get("nombre") == "pelota")
    tele = [e for e in d["elementos"] if e.get("nombre") == "tele"]
    assert len(tele) == 2 and tele[1].get("rota")                 # la tele queda con la pantalla rota
    assert any(e.get("nombre") == "mesa" for e in d["elementos"])   # y está sobre una mesa
    golpes = [t for t, s in sfx if s in ("vidrio", "golpe")]
    assert len(golpes) >= 3 and golpes == sorted(golpes)
    assert pelota["keyframes"][0]["t"] < tele[1]["desde"] < 3.0
    lampara = [e for e in d["elementos"] if e.get("nombre") == "lampara"]
    assert lampara[0]["x"] == 470                                  # la lámpara, al lado del sillón
    Video.desde_dict({"escenas": [d]}).cuadro(50)


def test_lo_que_cae_cae_de_su_lugar():
    d, _ = ac.escena_accion({"fondo": "casa", "actores": [],
                             "objetos": [_o("jarron", "cae_y_se_rompe", "derecha", soporte="estante")]}, 3.0, 0)
    jarron = next(e for e in d["elementos"] if e.get("nombre") == "jarron")
    assert jarron["keyframes"][0]["y"] == jarron["y"] < ac.Y_ESTANTE       # arranca en el estante
    assert any(e.get("nombre") == "estante" for e in d["elementos"])


def test_tito_es_el_locutor():
    from clips_bot.animacion import tito

    for pose in tito.POSES:
        assert "<" in tito.tito_svg(pose, apertura=0.5, aguja=90)
    assert "<" in tito.tito_cara_svg()
    p, _ = ac.escena_locutor(2.0)
    assert p["elementos"][0]["tipo"] == "tito"
    v = Video.desde_dict({"escenas": [ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "correr")]}, 1.0, 0)[0], p]})
    assert ORO_EN(v.cuadro(45).a.fijo)                             # el reloj dorado de Tito, en la pausa


def ORO_EN(svg: str) -> bool:
    from clips_bot.animacion import tito

    return tito.ORO in svg


def test_viaje_en_el_tiempo_gira_cuenta_y_pasa_a_sepia():
    a, _ = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "correr")]}, 1.0, 0)
    v_, sfx = ac.escena_viaje(1.2, 2026, 1969)
    v = Video.desde_dict({"escenas": [a, v_]})
    medio = v.cuadro(30 + 18)
    assert medio.tono > 0.2 and medio.a.camara[3] != 0             # gira y se va poniendo sepia
    fin = v.cuadro(30 + 35)
    # el año llegó a 1969 en el cuentakilómetros (una cajita por dígito), con el reloj gigante y el remolino
    assert fin.tono > 0.95 and all(f">{c}<" in fin.a.fijo for c in "1969") and fin.remolino > 0.9
    assert "XII" in fin.a.fijo and medio.remolino < fin.remolino
    assert sfx == [(0.0, "viaje")]
    assert 1.0 <= ac.VIAJE_S <= 1.5
    vuelta, _ = ac.escena_viaje(1.2, 1969, 2026)
    assert vuelta["tono"] == [1.0, 0.0]


def test_linea_de_tiempo_con_viaje_y_sepia():
    d = guion()
    segs = mk.segmentos(d)
    inicios = [i * 3.0 for i in range(len(segs))]
    datos, sfx = mk.linea_de_tiempo(d, inicios, inicios[-1] + 3.0, [], None, presente=2026)
    tipos = [("viaje" if e.get("girar") else "pausa" if e.get("congela") else "accion", e.get("tono"))
             for e in datos["escenas"]]
    assert tipos[1][0] == "viaje" and tipos[1][1] == [0.0, 1.0]     # va a 1947 en la frase 2
    assert tipos[2] == ("accion", 1.0)                              # la escena del pasado, en sepia
    assert ("viaje", [1.0, 0.0]) in tipos                            # y vuelve al presente al final
    assert tipos[-1] == ("accion", 0.0)
    assert sum(1 for t, s in sfx if s == "viaje") == 2
    v = Video.desde_dict(datos)
    assert v.duracion == pytest.approx(inicios[-1] + 3.8, abs=0.01)


def test_un_salto_chico_no_es_otro_viaje():
    """Visto en la Pi con el Nerf: 1969 → 1970 hacía otro remolino de 1,25 s y pasaba por color."""
    d = guion()
    d["escenas"][4]["viaje_a_anio"] = 1950
    segs = mk.segmentos(d)
    inicios = [i * 3.0 for i in range(len(segs))]
    datos, _ = mk.linea_de_tiempo(d, inicios, inicios[-1] + 3.0, [], None, presente=2026)
    assert sum(1 for e in datos["escenas"] if e.get("girar")) == 2           # ida y vuelta, nada más
    v, _ = ac.escena_viaje(1.2, 1947, 1890, presente=2026)
    assert v["tono"] == [1.0, 1.0]                                           # de pasado a pasado: sepia


# ---- movimiento, lugares, escenarios y objetos (Santi, 2026-11-14, después del Nerf con Tito) -----

def _personaje(escena_d):
    return next(e for e in escena_d["elementos"] if e.get("tipo") == "personaje")


def test_caminar_con_ciclo_rodillas_brazos_en_contrafase_y_rebote():
    from clips_bot.animacion.timeline import Elemento

    d, _ = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "caminar", "izquierda", "derecha")]}, 3.0, 0)
    pj = _personaje(d)
    assert pj["ciclos"][0]["tipo"] == "caminar"
    el = Elemento.desde_dict(pj, "x", 3.0)
    t0 = pj["ciclos"][0]["t0"]
    vistos = set()
    for k in range(12):
        t = t0 + 0.2 + k * 0.07
        e, dy = el._estado(t, 0.0, int(t * 30), 0.0)
        assert not (e.pierna_izq > 0.05 and e.pierna_der > 0.05)          # una pierna por vez
        if e.pierna_izq > 0.3:
            vistos.add("izq")
            assert e.brazo_izq[0] > e.brazo_der[0]                       # brazos en contrafase
        if e.pierna_der > 0.3:
            vistos.add("der")
        assert dy <= 0                                                    # el cuerpo sube con el paso
    assert vistos == {"izq", "der"}
    assert "<path" in el.svg(t0 + 0.3, 0.0, 10)


def test_saltar_con_anticipacion_y_squash():
    d, _ = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "saltar")]}, 2.0, 0)
    est = [k["estirar"] for k in _personaje(d)["keyframes"] if "estirar" in k]
    assert min(est) < 0.9 and max(est) > 1.05                             # se agacha, se estira, se aplasta
    assert any(c["cara"] == "risa" for c in _personaje(d)["caras"])
    Video.desde_dict({"escenas": [d]}).cuadro(20)


def test_la_cara_cambia_con_la_accion():
    from clips_bot.animacion.timeline import Elemento

    d, _ = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "caerse")]}, 2.5, 0)
    el = Elemento.desde_dict(_personaje(d), "x", 2.5)
    antes, _ = el._estado(0.3, 0.0, 9, 0.0)
    despues, _ = el._estado(2.2, 0.0, 66, 0.0)
    assert antes.boca == "o" and despues.cejas == "triste"


@pytest.mark.parametrize("semilla", range(60))
def test_nunca_un_personaje_encima_de_otro(semilla):
    import random

    rnd = random.Random(semilla)
    actores = [_a(rnd.choice(list(ac.ROLES)), rnd.choice(ac.ACCIONES), rnd.choice(ac.LADOS),
                  rnd.choice(list(ac.POS) + ["ninguno"])) for _ in range(rnd.randint(2, 3))]
    reservar = rnd.choice([None, "izquierda", "derecha"])
    d, _ = ac.escena_accion({"fondo": "casa", "actores": actores}, rnd.uniform(1.5, 4.0), semilla,
                            reservar=reservar)
    assert ac.superposiciones(d) == []
    if reservar:      # el costado de Tito queda libre al final (la escena congelada)
        for x, hw in ac.posiciones_finales(d):
            assert abs(x - ac.X_TITO[reservar]) >= ac.ANCHO_MEDIO_TITO + hw


def test_tito_no_tapa_a_nadie_en_la_pausa():
    d = guion()
    segs = mk.segmentos(d)
    inicios = [i * 3.0 for i in range(len(segs))]
    datos, _ = mk.linea_de_tiempo(d, inicios, inicios[-1] + 3.0, [], None, presente=2026)
    for i, e in enumerate(datos["escenas"]):
        assert ac.superposiciones(e) == [], i
        if e.get("congela") and not e.get("girar"):           # la pausa: Tito contra la escena congelada
            tito = e["elementos"][0]
            previa = next(x for x in reversed(datos["escenas"][:i]) if not x.get("congela"))
            for x, hw in ac.posiciones_finales(previa):
                assert abs(x - tito["x"]) >= ac.ANCHO_MEDIO_TITO + hw


def test_escenarios_con_epoca_y_variantes():
    casa_60 = esc.fondo("casa", ac.semilla_fondo(1969, 0))
    casa_hoy = esc.fondo("casa", ac.semilla_fondo(2026, 0))
    casa_40 = esc.fondo("casa", ac.semilla_fondo(1940, 0))
    assert len({casa_60, casa_hoy, casa_40}) == 3
    assert "scale(-1 1)" in esc.fondo("casa", ac.semilla_fondo(1969, 1))     # otra toma: espejada
    assert "scale(-1 1)" not in casa_60
    for f in ("oficina", "taller", "fabrica", "tienda", "ciudad"):
        esc.fondo(f, ac.semilla_fondo(1969, 1))
    assert esc.fondo("oficina", ac.semilla_fondo(1965, 0)) != esc.fondo("oficina", ac.semilla_fondo(2026, 0))
    # dos escenas seguidas en la casa no son idénticas
    d = guion()
    for e in d["escenas"]:
        e["fondo"] = "casa"
    segs = mk.segmentos(d)
    datos, _ = mk.linea_de_tiempo(d, [i * 3.0 for i in range(len(segs))], len(segs) * 3.0, [], None, presente=2026)
    accion = [e["fondo"]["semilla"] for e in datos["escenas"] if not e.get("congela")]
    assert all(a != b for a, b in zip(accion, accion[1:]))
    assert any(s_ // 100 == 194 for s_ in accion) and any(s_ // 100 == 202 for s_ in accion)   # 1947 y hoy


def test_objetos_llamativos():
    for nombre in ("pelota_espuma", "juego_mesa", "hamburguesa", "chocolate", "galletitas", "auto",
                   "telefono_disco", "radio", "consola"):
        assert esc.prop(nombre).count("<") >= 8, nombre                   # con detalle, no un rótulo
    d = guion()
    d["escenas"][4]["objetos"] = [_o("caja", "quieto", texto="Juego")]
    assert any("rótulo" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion(protagonista={"prop": "caja", "que_es": "un juego"})
    assert any("protagonista" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion(protagonista={"prop": "radio", "que_es": "una radio"})
    assert any("aparece en 0" in e for e in mk.validar_guion(d, marca(), FUENTE))
    # en la cadena se tira el protagonista si se puede tirar
    d = guion(protagonista={"prop": "pelota_espuma", "que_es": "la pelota de espuma"})
    d["escenas"][0]["objetos"] = [_o("jarron", "quieto", "derecha")]
    segs = mk.segmentos(d)
    datos, _ = mk.linea_de_tiempo(d, [i * 3.0 for i in range(len(segs))], len(segs) * 3.0, [], None, presente=2026)
    assert any(e.get("nombre") == "pelota_espuma" for e in datos["escenas"][0]["elementos"])


# ---- ritmo, subtítulos arriba, composición, revisión visual, perfil, época y audio (2026-11-14) ----

def _wav(ruta, tramos, sr=48000):
    import wave

    import numpy as np

    partes = []
    for tipo, seg in tramos:
        t = np.arange(int(seg * sr)) / sr
        partes.append(0.4 * np.sin(2 * np.pi * 220 * t) if tipo == "voz" else np.zeros(len(t)))
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.concatenate(partes) * 32767).astype("<i2").tobytes())
    return ruta


def test_pausas_entre_frases_a_022(tmp_path):
    from clips_bot.narrar import duracion_wav

    w = _wav(tmp_path / "v.wav", [("voz", 1.0), ("sil", 0.9), ("voz", 1.0), ("sil", 0.15), ("voz", 0.5)])
    sacado = mk.acortar_pausas(w)
    assert sacado == pytest.approx(0.9 - mk.PAUSA_MAX_S, abs=0.03)        # la pausa corta no se toca
    assert duracion_wav(w) == pytest.approx(3.55 - sacado, abs=0.02)


def test_niveles_de_audio(tmp_path):
    w = _wav(tmp_path / "v.wav", [("voz", 1.0)])
    n = mk.niveles(w)
    assert -14 < n["medio"] < -8 and n["pico"] < 0


def test_ritmo_25_a_30_s():
    """Santi (2026-11-14): ×1,13 quedó un pelín rápido → ×1,065; (2026-11-20) videos de 25 a 30 s con 6-7 escenas."""
    assert (mk.MIN_S, mk.MAX_S) == (25.0, 30.0) and mk.VELOCIDAD_VOZ == 1.065
    assert (mk.FRASES_MIN, mk.FRASES_MAX) == (6, 7)
    assert "25 a 30 segundos" in mk.SISTEMA_GUION


def _dos_cerca(gesto_a="senalar"):
    """Dos personajes pegados, uno señalando hacia el otro (el brazo le cruza la cara)."""
    return {"duracion": 1.0, "fondo": {"tipo": "casa", "semilla": 20200}, "elementos": [
        {"tipo": "personaje", "nombre": "narrador", "x": 400, "y": ac.PISO, "escala": 0.74,
         "gestos": [{"t": 0, "gesto": gesto_a}]},
        {"tipo": "personaje", "nombre": "abuelo", "x": 560, "y": ac.PISO, "escala": 0.74,
         "gestos": [{"t": 0, "gesto": "reposo"}]}]}


def test_composicion_brazo_que_atraviesa_una_cara():
    d = _dos_cerca()
    malos = ac.composicion(d)
    assert any(q == "brazo_en_cara" for _, q, _, _ in malos)
    assert ac.arreglar_composicion(d) == []
    assert all(g["gesto"] not in ac.GESTOS_QUE_ALCANZAN for g in d["elementos"][0]["gestos"])


def test_composicion_objeto_sobre_la_cabeza_mueble_en_medio_y_franja():
    d = _dos_cerca("reposo")
    d["elementos"] = d["elementos"][1:] + [
        {"tipo": "prop", "nombre": "pelota_espuma", "x": 560, "y": ac.PISO - 640},       # sobre la cabeza
        {"tipo": "prop", "nombre": "mesa", "x": 540, "y": ac.Y_MESA, "mueble": True},     # en el medio
        {"tipo": "prop", "nombre": "cuadro", "x": 200, "y": 200}]                         # en la franja
    assert ac.composicion(d)[0][1] == "mueble_en_medio"
    assert ac.arreglar_composicion(d) == []


@pytest.mark.parametrize("semilla", range(40))
def test_ninguna_escena_queda_mal_compuesta(semilla):
    import random

    rnd = random.Random(1000 + semilla)
    props = ["pelota_espuma", "tele", "lampara", "jarron", "radio", "juego_mesa", "botella", "cuadro", "trofeo"]
    actores = [_a(rnd.choice(list(ac.ROLES)), rnd.choice(ac.ACCIONES), rnd.choice(ac.LADOS),
                  rnd.choice(list(ac.POS) + ["ninguno"])) for _ in range(rnd.randint(1, 3))]
    objetos = [_o(rnd.choice(props), rnd.choice(["quieto", "se_rompe", "cae_y_se_rompe", "gira"]), rnd.choice(ac.LADOS),
                  soporte=rnd.choice(["mesa", "estante", "piso", "mano", "pared"])) for _ in range(rnd.randint(0, 3))]
    d, _ = ac.escena_accion({"fondo": rnd.choice(["casa", "taller", "tienda"]), "actores": actores,
                             "objetos": objetos, "camara": rnd.choice(ac.CAMARAS),
                             "cadena": [_c("tele", "mesa", "izquierda"), _c("lampara", "piso", "centro")]
                             if semilla % 3 == 0 else []}, rnd.uniform(1.5, 4.0), semilla,
                            reservar=rnd.choice([None, "izquierda", "derecha"]))
    assert ac.composicion(d) == [] and ac.superposiciones(d) == []
    assert all(not (el.get("mueble") and 330 < el["x"] < 750) for el in d["elementos"])


def test_de_perfil_al_caminar_de_costado():
    from clips_bot.animacion.timeline import Elemento

    d, _ = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "caminar", "izquierda", "derecha")]}, 3.0, 0)
    pj = _personaje(d)
    el = Elemento.desde_dict(pj, "x", 3.0)
    t0 = pj["ciclos"][0]["t0"]
    caminando, _ = el._estado(t0 + 0.5, 0.0, 15, 1.0)
    quieto, _ = el._estado(2.9, 0.0, 87, 0.0)
    assert caminando.perfil == 1 and quieto.perfil == 0
    assert el._pj.svg(caminando) != el._pj.svg(quieto)
    from clips_bot.animacion import personajes as per

    izq = el._pj.svg(per.Estado(perfil=-1))
    assert "scale(-1" in izq                                          # mirando a la izquierda: espejado


def test_cuadros_clave_y_revision_visual(tmp_path):
    d = guion()
    segs = mk.segmentos(d)
    inicios = [i * 3.0 for i in range(len(segs))]
    datos, _ = mk.linea_de_tiempo(d, inicios, inicios[-1] + 3.0, [], None, presente=2026)
    claves = mk.cuadros_clave(datos)
    # una por escena de la historia (gancho incluido); el reloj del viaje no se mira (Frisbee, 17/11)
    frases = {e.get("frase") for e in datos["escenas"] if isinstance(e.get("frase"), int)}
    assert len(claves) == len(frases)
    assert claves[0][2] == "gancho" and not any(q == "viaje en el tiempo" for _, _, q in claves)

    def capturar(_datos, _t, png):
        from PIL import Image

        Image.new("RGB", (540, 960), "white").save(png)

    n_escena = next(n for n, (_t, _i, q) in enumerate(claves) if q.startswith("escena 7")) + 1
    cliente = ClienteFalso({"problemas": [{"cuadro": n_escena, "que": "la caja flota", "arreglo": "cambiar_soporte",
                                           "objeto": "galletitas"}]})
    problemas, cl = mk.revisar_visual(cliente, d, datos, tmp_path, capturar=capturar)
    assert problemas and cl == claves
    hechos = mk.aplicar_revision(d, problemas, claves, datos)
    assert hechos and d["escenas"][6]["objetos"][0]["soporte"] == "estante"


def test_epoca_en_la_calle_la_fabrica_y_la_tienda():
    for f in ("ciudad", "fabrica", "tienda"):
        versiones = {esc.fondo(f, ac.semilla_fondo(a, 0)) for a in (1930, 1965, 1985, 2026)}
        assert len(versiones) == 4, f


def test_sepia():
    import numpy as np

    from clips_bot.animacion import render as rd

    img = np.zeros((2, 2, 3), dtype=np.uint8)
    img[..., 2] = 255                                              # azul puro
    out = rd.sepia(img.copy(), 1.0)
    assert out[0, 0, 0] > out[0, 0, 2]                              # pasa a marrón: más rojo que azul
    assert (rd.sepia(img.copy(), 0.0) == img).all()
    bgra = np.zeros((2, 2, 4), dtype=np.uint8)
    bgra[..., 0] = 255                                             # azul puro en BGRA (cairo)
    out = rd.sepia(bgra.copy(), 1.0, bgr=True)
    assert out[0, 0, 2] > out[0, 0, 0]                              # R > B


def test_pausa_del_locutor_congela_y_pone_gris():
    a, _ = ac.escena_accion({"fondo": "casa", "actores": [_a("nene", "correr", "izquierda", "derecha")],
                             "objetos": []}, 2.0, 0)
    p, sfx = ac.escena_locutor(2.0)
    v = Video.desde_dict({"escenas": [a, p]})
    c = v.cuadro(90)                                    # 1 s adentro de la pausa
    assert 'fill="#4a4f5c"' in c.a.fijo                 # la escena de atrás, en gris
    assert c.a.frente == v._capa(v.escenas[0], 2.0 - 1e-3, 90, apertura=0.0).frente   # congelada
    assert ("tac" in [s for _, s in sfx])
    with pytest.raises(Exception):
        Video.desde_dict({"escenas": [p]})              # una pausa necesita algo antes


def test_linea_de_tiempo_con_locutor_y_sfx():
    d = guion()
    segs = mk.segmentos(d)
    assert [t for t, _, _ in segs].count("locutor") == 1 and segs[3][0] == "locutor"
    inicios = [i * 3.0 for i in range(len(segs))]
    fin = inicios[-1] + 3.0
    palabras = [Palabra(0.0, 0.4, "Otra"), Palabra(0.4, 0.8, "caja")]
    datos, sfx = mk.linea_de_tiempo(d, inicios, fin, palabras, None)
    v = Video.desde_dict(datos)
    assert len(v.escenas) == len(segs) + 2                          # + ida y vuelta del viaje en el tiempo
    assert sum(1 for e in v.escenas if e.congela and not e.girar) == 1   # la pausa de Tito
    assert v.duracion == pytest.approx(fin + 0.8, abs=0.01)
    assert v.subtitulos and v.cuadro(5).encima
    assert v.sub_y == mk.SUBTITULOS_Y and v.sub_estilo == "viral" and v.sub_tam == mk.SUBTITULOS_TAM
    # los subtítulos (estilo viral) están arriba, antes de donde puede subir la escena
    from clips_bot.animacion import subtitulos_virales as sv

    x0, x1, y0, y1 = sv.limites(v.subtitulos, v.sub_y)
    assert y1 < ac.BANDA_SUBTITULOS and y0 > 150 and x0 > 0 and x1 < 1080
    assert sfx and all(0 <= t < v.duracion for t, _ in sfx) and sfx == sorted(sfx)


def test_cortes_siguen_la_voz():
    assert mk.cortes([0.0, 2.0, 5.0], 8.0) == [1.88, 3.0, 3.92]


def test_sfx_sintetizados_y_mezclados(tmp_path):
    import wave

    import numpy as np

    for nombre in sfx_mod.SONIDOS:
        x = sfx_mod.sonido(nombre)
        assert 0.02 < len(x) / sfx_mod.SR < 1.5 and np.max(np.abs(x)) == pytest.approx(1.0)
    base = tmp_path / "voz.wav"
    with wave.open(str(base), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes((np.ones(48000) * 30000).astype("<i2").tobytes())   # casi al tope: el limitador actúa
    out = sfx_mod.mezclar(base, [(0.2, "vidrio"), (0.5, "golpe"), (5.0, "pop")], tmp_path / "f.wav", 2.0)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 48000 and w.getnframes() == 96000
        y = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert np.max(np.abs(y)) <= 32767 * 0.96


# ---- la escucha ------------------------------------------------------------------------------

class TgFalso:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((chat, texto))


def _settings(**cambios):
    s = load_settings()
    return replace(s, animacion=replace(s.animacion, activo=True, **cambios))


AR_ = None


def _ahora(hhmm: str) -> datetime:
    import clips_bot.__main__ as m

    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(2026, 11, 20, h, mi, tzinfo=m.AR)


def test_tick_apagado_no_hace_nada(conn):
    import clips_bot.__main__ as m

    from dataclasses import replace

    llamadas = []
    s = load_settings()
    s = replace(s, animacion=replace(s.animacion, activo=False))   # prendido desde el 2026-11-14
    m._animacion_tick(conn, TgFalso(), s, _ahora("08:00"), armar=lambda *a: llamadas.append(a))
    assert not llamadas


def test_tick_nunca_en_la_franja_de_pequena_historia(conn):
    import clips_bot.__main__ as m

    llamadas = []
    for hhmm in ("03:45", "04:30", "05:59"):
        m._animacion_tick(conn, TgFalso(), _settings(hora="00:00"), _ahora(hhmm),
                          armar=lambda *a: llamadas.append(a))
    assert not llamadas


def test_tick_una_vez_por_dia_con_el_turno(conn):
    import clips_bot.__main__ as m

    llamadas = []

    def armar(c, tg, chats, settings, hoy, k=0):
        llamadas.append((chats, hoy, k))
        assert db.hay_trabajo_pesado(c, m.VENCIMIENTO_PESADO_S)   # con el turno tomado

    m._animacion_tick(conn, TgFalso(), _settings(), _ahora("06:30"), armar=armar)   # antes de la hora
    assert not llamadas
    for hhmm in ("07:10", "07:30", "09:00", "10:00"):
        m._animacion_tick(conn, TgFalso(), _settings(), _ahora(hhmm), armar=armar)
    # 2 por día (13:00 y 20:00, 2026-11-15): uno detrás del otro, y nada más
    assert llamadas == [([m.DUENO], date(2026, 11, 20), 0), ([m.DUENO], date(2026, 11, 20), 1)]
    assert not db.hay_trabajo_pesado(conn, m.VENCIMIENTO_PESADO_S)   # lo soltó


def test_tick_si_falla_reintenta_en_una_hora(conn):
    import clips_bot.__main__ as m

    from clips_bot.claude import ClaudeError

    llamadas, tg = [], TgFalso()

    def armar(c, tg_, chats, settings, hoy, k=0):
        llamadas.append(k)
        if len(llamadas) == 1:
            raise ClaudeError("Claude (claude-sonnet-5-5): la respuesta se cortó (max_tokens)")

    m._animacion_tick(conn, tg, _settings(), _ahora("07:00"), armar=armar)
    assert "Reintento a las 08:00" in tg.mensajes[-1][1]
    m._animacion_tick(conn, tg, _settings(), _ahora("07:30"), armar=armar)      # todavía no
    assert llamadas == [0]
    m._animacion_tick(conn, tg, _settings(), _ahora("08:01"), armar=armar)
    m._animacion_tick(conn, tg, _settings(), _ahora("08:20"), armar=armar)
    assert llamadas == [0, 0, 1]


def test_tick_no_reintenta_despues_de_las_22(conn):
    import clips_bot.__main__ as m

    tg = TgFalso()

    def armar(*a, **k):
        raise RuntimeError("Gemini caído")

    m._animacion_tick(conn, tg, _settings(), _ahora("21:30"), armar=armar)
    assert "hoy no sale" in tg.mensajes[-1][1]


def test_tick_espera_si_el_turno_esta_ocupado(conn):
    import clips_bot.__main__ as m

    db.tomar_turno(conn, db.RECURSO_PESADO, "otro", maximo=1, vencimiento_s=m.VENCIMIENTO_PESADO_S)
    llamadas = []
    m._animacion_tick(conn, TgFalso(), _settings(), _ahora("08:00"), armar=lambda *a: llamadas.append(a))
    assert not llamadas and db.get_valor(conn, m.ANIM_DIA) is None


def test_tick_sin_candidato_avisa(conn):
    import clips_bot.__main__ as m

    def armar(*a):
        raise mk.SinCandidato("ninguno de los 8 candidatos de hoy llegó a 8 de promedio")

    tg = TgFalso()
    m._animacion_tick(conn, tg, _settings(chat="123"), _ahora("08:00"), armar=armar)
    assert tg.mensajes and tg.mensajes[0][0] == "123" and "hoy no sale" in tg.mensajes[0][1]
    assert not db.hay_trabajo_pesado(conn, m.VENCIMIENTO_PESADO_S)


def test_no_sube_a_ningun_lado():
    """El canal de YouTube todavía no existe: el nombre está preparado y el módulo no sube nada."""
    import inspect

    from clips_bot import youtube

    assert "animacion" in youtube.CANALES
    fuente = inspect.getsource(mk)
    for prohibido in ("import youtube", "youtube.", "import facebook", "facebook.", "subir("):
        assert prohibido not in fuente, prohibido


def test_mensaje_con_marca_angulo_y_puntaje():
    r = mk.Resultado(marca="Havanna", angulo="casi_quiebra", notas={c: 9 for c in mk.CRITERIOS},
                     promedio=9.0, titulo="T", descripcion="D", hashtags=mk.hashtags(marca()),
                     frases=mk.frases_de(guion()), video="x.mp4", duracion_s=38.2, motor_voz="gemini:Laomedeia",
                     render_s=150, costo_usd=0.08)
    t = mk.texto_mensaje(r, "🔧 Claude Code: ejemplo")
    assert "Havanna" in t and "casi quiebra" in t and "Puntaje 9" in t and "humor 9" in t
    assert "#Havanna" in t and "No quedó programado" in t


def test_el_gancho_no_repite_el_de_otro_video():
    d = guion()
    previos = mk.ganchos_recientes(None)          # siempre está el de Nerf
    assert any("destrucción en cadena de Nerf" in e for e in mk.validar_guion(d, marca(), FUENTE, previos))
    d["escenas"][0]["cadena"] = []
    otro = dict(mk.firma_gancho(d, "Otra"), cadena=False)
    assert any("se parece al de Otra" in e for e in mk.validar_guion(d, marca(), FUENTE, [otro]))


def test_lugares_dialogos_y_personajes():
    d = guion()
    for e in d["escenas"]:
        e["fondo"] = "casa"
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "lugares distintos" in err and "seguidas en casa" in err and "como mucho 2" in err
    d = guion()
    for e in d["escenas"]:
        e["actores"] = [{"rol": "nene", "accion": "quieto", "desde": "izquierda", "hacia": "ninguno", "cara": "normal"}]
        e["objetos"], e["cadena"] = [], []
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "personajes distintos" in err and "chicos" in err and "gente hablando" in err


def test_lugares_nuevos_y_multitud():
    from clips_bot.animacion import acciones as ac, escenas as esc

    for f in ("laboratorio", "hospital", "campo", "puerto"):
        assert f in mk.FONDOS and esc.fondo(f, 19600).startswith("<")
    spec = {"parte": "que_paso", "fondo": "fabrica", "multitud": True, "actores": [
        {"rol": "obrero", "accion": "fabricar", "desde": "izquierda"}, {"rol": "vendedor", "accion": "vender",
                                                                         "desde": "derecha"}], "objetos": []}
    d, _ = ac.escena_accion(spec, 3.0, 2)
    # menos gente (Santi, 2026-11-20): la multitud de relleno ya no se dibuja
    assert not [el for el in d["elementos"] if el.get("multitud")]
    ac.SIN_RELLENO = False
    try:
        d, _ = ac.escena_accion(spec, 3.0, 2)
    finally:
        ac.SIN_RELLENO = True
    gente = [el for el in d["elementos"] if el.get("multitud")]
    assert len(gente) >= 5 and ac.es_dinamica(spec) and not ac.superposiciones(d)


def test_marca_con_guion_fallido_queda_afuera_ese_dia(conn):
    from datetime import date as _d

    cat = mk.cargar_catalogo()
    hoy = _d(2026, 11, 15)
    antes = {m.nombre for m, _ in mk.candidatos(conn, cat, hoy, 20)}
    una = sorted(antes)[0]
    mk.anotar_fallidos(conn, hoy, [una])
    despues = {m.nombre for m, _ in mk.candidatos(conn, cat, hoy, 20, excluir=mk.fallidos_de(conn, hoy))}
    assert una not in despues and despues != antes
    assert not issubclass(mk.GuionesFallidos, mk.SinCandidato)     # se reintenta en 1 h



def test_correccion_puntual_toca_solo_lo_que_falla():
    from clips_bot import correcciones as co

    d = {"titulo": "t", "escenas": [{"frase": "uno"}, {"frase": "dos"}, {"frase": "tres"}]}
    out = co.aplicar(d, {"cambios": [{"indice": 2, "item": {"frase": "DOS"}}], "agregar": [{"despues_de": 3,
                         "item": {"frase": "cuatro"}}], "sacar": [1], "campos": {"titulo": "nuevo"}}, "escenas")
    assert [x["frase"] for x in out["escenas"]] == ["DOS", "tres", "cuatro"] and out["titulo"] == "nuevo"
    assert d["escenas"][1]["frase"] == "dos"                       # el original no se toca
    sch = co.schema_parche(mk.SCHEMA_GUION, "escenas")
    campos = sch["properties"]["campos"]["items"]["properties"]["campo"]["enum"]
    assert "titulo" in campos and "escenas" not in campos
    assert "agregar" not in sch["properties"]                     # el item una sola vez (tope de gramática)
    out2 = co.aplicar(d, {"cambios": [{"indice": 2, "nuevo": False, "item": {"frase": "DOS"}},
                                      {"indice": 3, "nuevo": True, "item": {"frase": "cuatro"}}],
                          "sacar": [1], "campos": [{"campo": "titulo", "valor": '"nuevo"'}]}, "escenas")
    assert [x["frase"] for x in out2["escenas"]] == ["DOS", "tres", "cuatro"] and out2["titulo"] == "nuevo"



def test_lo_que_se_ve_es_lo_que_dice_la_voz():
    d = guion()
    for k in range(6):
        d["escenas"][k]["accion_escena"] = "libre"
    assert any("demasiadas escenas `libre`" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][1]["actores"] = [_a("empresario", "festejar", "izquierda")]     # libre, sin éxito en la frase
    assert any("escena 2: festejan" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][1]["actores"] = [_a("empresario", "martillar", "izquierda")]
    assert any("escena 2: martillo" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_biblioteca_arma_cada_accion_con_sus_planos():
    from clips_bot.animacion import acciones as ac, escenas_lib as lib

    for accion, (_, planos, _) in lib.ACCIONES.items():
        for plano in planos:
            spec = {"frase": "vendió 1000 cubos", "parte": "que_paso", "fondo": "oficina", "accion_escena": accion,
                    "plano": plano, "actores": [_a("inventor", "quieto")], "objetos": [_o("cubo_rubik", "quieto")]}
            d, _ = ac.escena_accion(spec, 3.0, 2, protagonista="cubo_rubik")
            nombres = [el.get("nombre") for el in d["elementos"]]
            if accion in ("contar_billetes", "abrir_caja", "apreton_manos"):   # la plata, con acciones reales
                assert ("apreton" if accion == "apreton_manos" else "mano") in nombres, (accion, plano)
                continue
            if accion == "firmar":      # una persona firmando en su escritorio (nada de manos sueltas, 2026-11-20)
                assert "papel_firma" in nombres and any(el.get("tipo") == "personaje" for el in d["elementos"])
                continue
            assert "cubo_rubik" in nombres or any(el.get("tipo") == "contador" for el in d["elementos"]), (accion, plano)
    arriba, _ = ac.escena_accion({"frase": "armó el cubo", "parte": "idea", "fondo": "taller", "accion_escena": "armar_mesa",
                                  "plano": "arriba", "actores": [], "objetos": []}, 3.0, 1, protagonista="cubo_rubik")
    assert arriba["fondo"]["tipo"] == "mesa_arriba" and sum(el.get("nombre") == "mano" for el in arriba["elementos"]) == 2


def test_receta_nueva_queda_guardada(tmp_path, monkeypatch):
    from clips_bot.animacion import escenas_lib as lib

    monkeypatch.setattr(lib, "RECETAS", tmp_path / "lib.json")
    d = guion()
    d["escenas"][6]["accion_escena"] = "nueva"
    d["escenas"][6]["accion_nueva"] = "regalar_cajas"
    # antes de la revisión se arma como libre y no se guarda (Santi, 2026-11-20: solo si pasa el estándar)
    mk.guardar_acciones_nuevas(d)
    assert "regalar_cajas" not in lib.recetas() and d["escenas"][6]["accion_escena"] == lib.LIBRE
    mk.guardar_acciones_nuevas(d, aprobadas={1, 2})          # no pasó: sigue afuera
    assert "regalar_cajas" not in lib.recetas()
    mk.guardar_acciones_nuevas(d, aprobadas={6})             # pasó el estándar: entra a la biblioteca
    assert "regalar_cajas" in lib.recetas() and "regalar_cajas" in lib.todas_las_acciones()


def test_el_contador_usa_el_numero_de_la_frase_y_nunca_inventa():
    from clips_bot.animacion import escenas_lib as lib

    assert lib.numero_de_ventas("vendió 100.000 cubos en 1980") == 100000
    assert lib.numero_de_ventas("más de 350 millones de cubos") == 350_000_000
    assert lib.numero_de_ventas("En 1974 lo inventó") is None          # un año no es una venta
    hecha = lib.construir("contador_ventas", "frente", {"frase": "lo inventó en 1974"}, 2.0, 3, "cubo_rubik")
    assert not any(el.get("tipo") == "contador" for el in hecha["elementos"])


def test_objeto_gira_como_mucho_en_dos_escenas():
    d = guion()
    for e in d["escenas"][:4]:
        e["accion_escena"] = "objeto_gira"
    assert any("objeto_gira" in x and "como mucho 2" in x for x in mk.errores_accion(d))


def test_el_cubo_cierra_sus_tres_caras():
    from clips_bot.animacion import escenas as esc_

    svg = esc_.prop_cubo_rubik(fase=1.0)
    # la cara de arriba comparte la esquina del medio (0, 0) con las dos de los costados
    assert svg.count("M-86 -50") >= 2 and "M0 0" in svg


# ---- 2026-11-15 (tarde): gancho, nadie parado, viaje, sepia con el protagonista en color, manos, textos ----

def test_el_gancho_con_accion_y_nadie_parado():
    d = guion()
    d["escenas"][0]["accion_escena"] = "objeto_gira"
    assert any("gancho (escena 1)" in x for x in mk.errores_accion(d))
    d = guion()
    d["escenas"][2]["accion_escena"] = "libre"
    d["escenas"][2]["actores"] = [{"rol": "inventor", "accion": "pensar", "desde": "izquierda", "hacia": "ninguno",
                                   "cara": "feliz", "genero": "hombre", "edad": "adulto", "persona_real": ""}]
    assert any("parado sin hacer nada" in x for x in mk.errores_accion(d))


def test_la_revision_rehace_el_gancho_repetido(monkeypatch):
    from clips_bot import correcciones

    d = guion()
    segs = mk.segmentos(d)
    inicios = [i * 3.0 for i in range(len(segs))]
    datos, _ = mk.linea_de_tiempo(d, inicios, inicios[-1] + 3.0, [], None, presente=2026)
    claves = mk.cuadros_clave(datos)
    pedidos = []

    def corregir(cliente, sistema, fuente, d_, errores, *a, **k):
        pedidos.append(errores)
        return d_

    monkeypatch.setattr(correcciones, "corregir", corregir)
    monkeypatch.setattr(mk, "validar_guion", lambda *a, **k: [])
    e = mk.Elegido(mk.Marca("Havanna", "Argentina", "golosinas", "Havanna", ("origen",)), "origen", {})
    d2, hecho = mk.corregir_acciones(object(), d, e, "texto", [(0, "repite el escenario de antes")], claves, datos,
                                     ganchos="- Nerf: living")
    assert pedidos and "GANCHO" in pedidos[0][0] and "Nerf" in pedidos[0][0] and hecho.startswith("rehice")


def test_en_el_pasado_el_protagonista_queda_a_color():
    a, _ = ac.escena_accion({"fondo": "taller", "accion_escena": "armar_mesa", "plano": "lejos",
                             "actores": [{"rol": "inventor", "accion": "fabricar", "genero": "hombre", "edad": "adulto"}],
                             "objetos": []}, 2.0, 3, tono=1.0, protagonista="cubo_rubik", anio=1974)
    v = Video.desde_dict({"escenas": [a]})
    c = v.cuadro(30)
    assert c.tono > 0.9 and c.a.color.strip()                              # el cubo va aparte, a color
    sin, _ = ac.escena_accion({"fondo": "taller", "accion_escena": "armar_mesa", "plano": "lejos",
                               "actores": [], "objetos": []}, 2.0, 3, protagonista="cubo_rubik")
    assert not Video.desde_dict({"escenas": [sin]}).cuadro(30).a.color      # en color, todo junto como siempre


def test_las_manos_tienen_dedos_y_unas():
    svg = esc.prop_mano(forma=1)
    assert svg.count("A") >= 5 and "stroke-linecap" in svg       # 4 dedos + pulgar redondeados, pliegues


def test_los_textos_nunca_se_salen():
    from clips_bot.animacion import subtitulos_virales as sv
    from clips_bot.animacion.texto import Palabra as PalabraV

    largo = [PalabraV("VENDIÓ", 1.0, 1.4), PalabraV("CUATROCIENTOS", 1.0, 1.4, clave=True, impacto=True, emoji="plata")]
    x0, x1, y0, y1 = sv.limites([largo])
    assert x0 >= 0 and x1 <= 1080 and y1 < ac.BANDA_SUBTITULOS and y0 > 150
    assert len(sv.lineas_de(largo)) == 2
    assert esc.tam_que_entra("2.76 SEGUNDOS", 170, 860) < 170
