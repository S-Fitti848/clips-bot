"""Canal de marcas animadas (2026-11-14): catálogo, rotación, puntaje, guion validado contra el
artículo, escenas → línea de tiempo y el tick de la escucha. Sin red, sin render y sin Claude."""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from clips_bot import db
from clips_bot.animacion import escenas as esc
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
    with pytest.raises(mk.SinCandidato, match="8"):
        mk.proponer(conn, cliente, Wiki(), HOY, [marca()], n=1)


# ---- guion -----------------------------------------------------------------------------------

FUENTE = ("Havanna es una empresa argentina de alfajores fundada en 1947 en Mar del Plata. El nombre "
          "viene del Havanna Bar, un bar de los socios que después cerró. Los alfajores se volvieron "
          "famosos en toda la costa y la gente los llevaba de regalo después de las vacaciones.")

FRASES = [
    "Esta marca de alfajores se llama como un bar que ya no existía.",
    "Todo arranca en Mar del Plata, una ciudad de playa.",
    "Ahí unos socios tenían un bar llamado Havanna Bar.",
    "En 1947 fundaron la empresa y empezaron a vender alfajores.",
    "¿Y el bar? Cerró, obvio, porque así es la vida.",
    "Los alfajores, en cambio, se volvieron famosos en toda la costa.",
    "La gente los llevaba de regalo después de las vacaciones.",
    "Hoy la marca es más conocida que el bar que le dio el nombre.",
    "O sea: un bar cerrado bautizó a un alfajor eterno.",
]


def guion(**cambios):
    escenas = [{"frase": f, "fondo": "tienda" if i % 2 else "ciudad", "personaje": "fundador" if i % 3 == 0
                else "ninguno", "gesto": "explicar", "gesto_personaje": "sorpresa",
                "prop": "caja" if i % 2 else "ninguno", "texto_prop": "HAVANNA" if i % 2 else "",
                "texto_pantalla": "1947" if i == 3 else ("MAR DEL PLATA" if i == 1 else ""),
                "transicion": "zoom"} for i, f in enumerate(FRASES)]
    d = {"titulo": "Havanna: el alfajor que se llama como un bar", "descripcion": "La historia del nombre.",
         "tono": "curioso", "pregunta_gancho": "¿Por qué se llama así?", "gancho_pantalla": "Un bar que no existe",
         "frase_giro": 5, "frase_pago": 9, "escenas": escenas}
    d.update(cambios)
    return d


def test_un_guion_bueno_valida():
    assert mk.validar_guion(guion(), marca(), FUENTE) == []


def test_datos_que_no_estan_en_el_articulo():
    d = guion()
    d["escenas"][3]["frase"] = "En 1952 Pedro fundó la empresa y empezaron a vender alfajores."
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "1952" in err and "Pedro" in err


def test_el_texto_en_pantalla_tambien_se_valida():
    d = guion()
    d["escenas"][2]["texto_pantalla"] = "1999"
    assert "1999" in " ".join(mk.validar_guion(d, marca(), FUENTE))


def test_texto_de_pantalla_en_mayusculas_no_son_nombres():
    """Visto en la Pi con Nerf: "NA, MENTIRA" y "TIRARON" daban "Mentira" y "Tiraron" como nombres
    que no estaban en el artículo."""
    d = guion()
    d["escenas"][4]["texto_pantalla"] = "NA, MENTIRA"
    d["escenas"][5]["texto_pantalla"] = "LOS TIRARON"
    assert mk.validar_guion(d, marca(), FUENTE) == []
    assert mk._sin_mayusculas("NA, MENTIRA") == "Na, mentira"


def test_estructura_largo_y_gancho():
    d = guion(frase_pago=5)
    assert any("paga" in e for e in mk.validar_guion(d, marca(), FUENTE))
    d = guion()
    d["escenas"][0]["frase"] = "¿Sabías que en 1947 nació esta marca de alfajores tan famosa?"
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "año" in err and "fórmula" in err
    d = guion(escenas=guion()["escenas"][:5])
    assert any("palabras" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_nada_de_temas_sensibles():
    d = guion()
    d["escenas"][4]["frase"] = "¿Y el bar? Cerró después de un accidente, obvio."
    assert any("sensibles" in e for e in mk.validar_guion(d, marca(), FUENTE))


def test_props_y_fondos_tienen_que_existir():
    d = guion()
    d["escenas"][1]["prop"] = "logo_de_la_marca"
    d["escenas"][2]["fondo"] = "playa"
    err = " ".join(mk.validar_guion(d, marca(), FUENTE))
    assert "logo_de_la_marca" in err and "playa" in err


def test_escribir_guion_reintenta_con_los_errores():
    malo = guion(frase_pago=4)
    cliente = ClienteFalso(malo, guion())
    e = mk.Elegido(marca(), "nombre", {c: 9 for c in mk.CRITERIOS})
    assert mk.escribir_guion(cliente, e, FUENTE, avisar=lambda *_: None)["frase_pago"] == 9
    assert "NO SIRVIÓ" in cliente.pedidos[1]
    with pytest.raises(mk.GuionInvalido):
        mk.escribir_guion(ClienteFalso(malo, malo), e, FUENTE, reintentos=2, avisar=lambda *_: None)


# ---- escenas → línea de tiempo ---------------------------------------------------------------

def test_props_y_fondos_nuevos_se_dibujan():
    for nombre in mk.FONDOS:
        assert esc.fondo(nombre, 3).startswith("<")
    for nombre in mk.PROPS:
        if nombre != "ninguno":
            assert "<" in esc.prop(nombre, texto="HAVANNA", color="#123456")
    for nuevo in ("botella", "lata", "caja", "billete", "grafico_baja", "megafono", "control"):
        assert nuevo in esc.PROPS


def test_linea_de_tiempo_arma_un_video_valido():
    inicios = [i * 3.5 for i in range(len(FRASES))]
    fin = inicios[-1] + 3.0
    palabras = [Palabra(0.0, 0.4, "Esta"), Palabra(0.4, 0.8, "marca")]
    datos = mk.linea_de_tiempo(guion(), inicios, fin, palabras, None)
    v = Video.desde_dict(datos)
    assert len(v.escenas) == len(FRASES)
    assert v.duracion == pytest.approx(fin + 0.8, abs=0.01)
    primera = datos["escenas"][0]["elementos"]
    assert primera[0]["habla"] is True and any(e["tipo"] == "gancho" for e in primera)
    assert all(e["elementos"][0]["nombre"] == "narrador" for e in datos["escenas"])
    assert v.subtitulos and v.cuadro(5).encima   # el subtítulo de la base se dibuja
    # el secundario "fundador" es el abuelo del elenco
    assert any(e.get("nombre") == "abuelo" for e in datos["escenas"][0]["elementos"])


def test_cortes_siguen_la_voz():
    assert mk.cortes([0.0, 2.0, 5.0], 8.0) == [1.88, 3.0, 3.92]


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

    llamadas = []
    m._animacion_tick(conn, TgFalso(), load_settings(), _ahora("08:00"),
                      armar=lambda *a: llamadas.append(a))
    assert not llamadas and load_settings().animacion.activo is False


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

    def armar(c, tg, chats, settings, hoy):
        llamadas.append((chats, hoy))
        assert db.hay_trabajo_pesado(c, m.VENCIMIENTO_PESADO_S)   # con el turno tomado

    m._animacion_tick(conn, TgFalso(), _settings(), _ahora("06:30"), armar=armar)   # antes de la hora
    assert not llamadas
    m._animacion_tick(conn, TgFalso(), _settings(), _ahora("07:10"), armar=armar)
    m._animacion_tick(conn, TgFalso(), _settings(), _ahora("09:00"), armar=armar)
    assert llamadas == [([m.DUENO], date(2026, 11, 20))]
    assert not db.hay_trabajo_pesado(conn, m.VENCIMIENTO_PESADO_S)   # lo soltó


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
                     frases=FRASES, video="x.mp4", duracion_s=38.2, motor_voz="gemini:Laomedeia",
                     render_s=150, costo_usd=0.08)
    t = mk.texto_mensaje(r, "🔧 Claude Code: ejemplo")
    assert "Havanna" in t and "casi quiebra" in t and "Puntaje 9" in t and "humor 9" in t
    assert "#Havanna" in t and "No se sube" in t
