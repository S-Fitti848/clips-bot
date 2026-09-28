"""Pasó Hoy: filtros de eventos y fotos, validación del guion contra el artículo, y el flujo.

Sin red: Wikipedia y Gemini son fakes. Los casos salen de la prueba real del 2026-09-27.
"""

import json
from datetime import date
from pathlib import Path

import pytest

import clips_bot.__main__ as m
from clips_bot import db, efemerides as ef

HOY = date(2026, 9, 27)


# ---- eventos --------------------------------------------------------------------------

@pytest.mark.parametrize("anio,texto,motivo", [
    (2014, "63 people are killed in an eruption of Mount Ontake in Japan.", "tema sensible"),
    (2020, "Second Nagorno-Karabakh War: Azerbaijan launches an offensive", "guerra reciente"),
    (1822, "Champollion anuncia que ha descifrado los jeroglíficos de la piedra de Rosetta", None),
    (1998, "en Estados Unidos empieza a funcionar en Internet el motor de búsqueda de Google.", None),
    (1200, "La catedral se construyó durante siglos", "sin fecha exacta"),
])
def test_motivo_evento(anio, texto, motivo):
    assert ef.motivo_evento(ef.Evento("es", anio, texto, ["X"]), HOY) == motivo


def test_las_guerras_viejas_no_se_filtran_por_palabra():
    """Solo las RECIENTES: una batalla de 1066 la decide Gemini, no el filtro de palabras."""
    assert ef.motivo_evento(ef.Evento("en", 1066, "Battle of Hastings begins", ["X"]), HOY) is None


class FakeGemini:
    def __init__(self, *respuestas):
        self.respuestas, self.prompts, self.imagenes = list(respuestas), [], []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
        self.prompts.append(prompt)
        self.imagenes.append(len(imagenes or []))
        return json.dumps(self.respuestas.pop(0))


def test_elegir_devuelve_el_articulo_del_hecho_y_no_el_pais():
    eventos = [ef.Evento("es", 2019, "cierra El Nuevo Diario", ["Nicaragua", "El_Nuevo_Diario_(Nicaragua)"]),
               ef.Evento("es", 1998, "arranca Google", ["Estados_Unidos", "Google"])]
    g = FakeGemini({"elegidos": [
        {"indice": 2, "articulo": "Google", "motivo": "x"},
        {"indice": 1, "articulo": "Managua", "motivo": "inventado: no está en la lista"},
        {"indice": 2, "articulo": "Google", "motivo": "repetido"},
        {"indice": 9, "articulo": "x", "motivo": "fuera de rango"}]})
    assert ef.elegir(g, eventos) == [(1, "Google"), (0, "El_Nuevo_Diario_(Nicaragua)")]


# ---- fotos ---------------------------------------------------------------------------

def _info(archivo="File:Foto.jpg", mime="image/jpeg", ancho=2000, lic="CC BY-SA 4.0", desc="",
          nonfree="", cats=""):
    return {"archivo": archivo, "mime": mime, "width": ancho, "height": 1200,
            "thumburl": "https://x/1280.jpg", "descriptionurl": "https://commons/x",
            "extmetadata": {"LicenseShortName": {"value": lic}, "ImageDescription": {"value": desc},
                            "NonFree": {"value": nonfree}, "Categories": {"value": cats},
                            "Artist": {"value": "<a href='x'>Ana Pérez</a>"}}}


@pytest.mark.parametrize("info,motivo", [
    (_info(), None),
    (_info(lic="Public domain"), None),
    (_info(mime="image/svg+xml"), "formato"),
    (_info(lic="Fair use"), "licencia no libre"),
    (_info(lic="CC BY-NC 2.0"), "licencia no libre"),
    (_info(nonfree="true"), "licencia no libre"),
    (_info(ancho=640), "menos de 800 px"),
    (_info(archivo="File:Flag of Japan.jpg"), "no es una foto"),
    (_info(desc="Mapa de la región"), "no es una foto"),
    (_info(cats="Coats of arms of Spain"), "no es una foto"),
    (_info(desc="An American soldier stands near a wagon loaded with corpses"), "no es una foto"),
])
def test_motivo_foto(info, motivo):
    m_ = ef.motivo_foto(info)
    assert (m_ is None) if motivo is None else m_.startswith(motivo)


def test_el_autor_se_busca_en_attribution_y_credit():
    """Dos fotos CC BY-SA de la piedra de Rosetta no traían `Artist` (prueba real del 27/09)."""
    assert ef.autor_de({"Attribution": {"value": "Carlos Delgado"},
                        "Credit": {"value": "Kadellar ( Own work )"}}) == "Carlos Delgado"
    assert ef.autor_de({"Credit": {"value": "Captmondo ( Own work )"}}) == "Captmondo"
    assert ef.autor_de({"Credit": {"value": "Captmondo ( Trabajo propio )"}}) == "Captmondo"
    assert ef.autor_de({"Credit": {"value": "Own work"}}) == ""
    # la nota de traslado de la foto de Figeac (27/09): el autor es el que la subió
    assert ef.autor_de({"Credit": {"value": "Transferido desde de.wikipedia a Commons por "
                                            "Thierry46 . . Original uploader was Bautsch at "
                                            "de.wikipedia"}}) == "Bautsch"


def test_cc_by_sin_autor_no_se_usa():
    info = _info()
    info["extmetadata"]["Artist"] = {"value": ""}
    info["extmetadata"]["AttributionRequired"] = {"value": "true"}
    assert ef.motivo_foto(info) == "sin autor para atribuir"
    info["extmetadata"]["LicenseShortName"] = {"value": "Public domain"}
    info["extmetadata"]["AttributionRequired"] = {"value": "false"}
    assert ef.motivo_foto(info) is None             # dominio público: no hace falta


def test_epigrafe_y_autor_sin_html():
    f = ef.a_foto(_info(desc="Wolfschanze &lt;abbr class=&quot;x&quot;&gt;BA&lt;/abbr&gt; Hitler"), "Art")
    assert f.epigrafe == "Wolfschanze BA Hitler" and f.autor == "Ana Pérez"


def test_creditos_autor_y_licencia_de_cada_foto():
    fotos = [ef.a_foto(_info(), "A"), ef.a_foto(_info(lic="Public domain"), "A")]
    c = ef.creditos(fotos)
    assert "1. Ana Pérez — CC BY-SA 4.0 — https://commons/x" in c and "2. Ana Pérez — Public domain" in c


# ---- el guion contra el artículo ---------------------------------------------------------

ARTICULO = ("Larry Page y Sergey Brin comenzaron Google como un proyecto universitario en la "
            "Universidad de Stanford. El nombre original era BackRub. Contaban con un armario lleno "
            "de servidores y dos routers HP. Superó a AltaVista, creado en 1995. Estrenó su buscador "
            "en Internet el 27 de septiembre de 1998.")


def test_lo_que_no_esta_en_el_articulo_no_pasa():
    """El caso real: "más de mil millones de búsquedas diarias" venía de la memoria de Gemini."""
    guion = "Hoy procesan más de mil millones de búsquedas diarias."
    assert ef.no_respaldados(guion, ARTICULO) == ["mil millones"]


@pytest.mark.parametrize("guion,faltan", [
    ("Larry Page y Sergey Brin lo crearon en Stanford.", []),
    ("Lo crearon Larry Page y Elon Musk.", ["Elon", "Musk"]),
    ("Contaban con dos routers HP.", []),
    ("Tenían 80 servidores y 3 routers.", ["3", "80"]),
    ("Arrancó en 1998 y superó a AltaVista, de 1995.", []),
    ("Estrenó en septiembre.", []),
    ("Estrenó en julio.", ["julio"]),
    ("Hoy tiene cien mil empleados.", ["cien mil"]),
])
def test_no_respaldados(guion, faltan):
    assert ef.no_respaldados(guion, ARTICULO) == faltan


def _guion_ok(**cambios):
    d = {"frases": [{"texto": "Un día como hoy, en 1998, Google estrenó su buscador en Internet.", "foto": 1},
                    {"texto": "Larry Page y Sergey Brin lo empezaron como un proyecto universitario.", "foto": 2},
                    {"texto": "Lo arrancaron en la Universidad de Stanford, con muy poco.", "foto": 3},
                    {"texto": "¡Tenían un armario lleno de servidores y dos routers HP!", "foto": 4},
                    {"texto": "Al principio el buscador no se llamaba Google, se llamaba BackRub.", "foto": 1},
                    {"texto": "Con el tiempo superó a AltaVista, el más popular de la época.", "foto": 2},
                    {"texto": "Todo eso empezó con un proyecto de dos estudiantes y un armario.", "foto": 3},
                    {"texto": "Y el 27 de septiembre de 1998 el buscador salió a Internet para todos.", "foto": 4},
                    {"texto": "Desde ese día la forma de buscar cosas en la web cambió para siempre.", "foto": 1},
                    {"texto": "¿Te imaginás cómo buscarías cualquier cosa sin este buscador?", "foto": 2}],
         "fotos_descartadas": [5], "titulo": "El día que arrancó Google",
         "descripcion": "Así empezó el buscador.", "hashtags": ["#Shorts", "#Google", "#PasoHoy"]}
    d.update(cambios)
    return d


def test_un_guion_bien_armado_pasa():
    assert ef.validar_guion(_guion_ok(), 1998, 5, ARTICULO) == []


def test_el_gancho_la_pregunta_y_las_fotos():
    sin_gancho = _guion_ok()
    sin_gancho["frases"][0]["texto"] = "En 1998 Google estrenó su buscador en Internet para todo el mundo."
    assert any("Un día como hoy" in e for e in ef.validar_guion(sin_gancho, 1998, 5, ARTICULO))
    sin_pregunta = _guion_ok()
    sin_pregunta["frases"][-1]["texto"] = "Y así fue como empezó todo, en un armario."
    assert any("gancho" in e for e in ef.validar_guion(sin_pregunta, 1998, 5, ARTICULO))
    sin_exclamacion = _guion_ok()
    sin_exclamacion["frases"][3]["texto"] = "Tenían un armario lleno de servidores y dos routers HP."
    assert any("exclamación" in e for e in ef.validar_guion(sin_exclamacion, 1998, 5, ARTICULO))
    cierre_exclamado = _guion_ok()
    cierre_exclamado["frases"][-1]["texto"] = "¡Y todo empezó en un armario de Stanford!"
    cierre_exclamado["frases"][4]["texto"] = "¿Sabés cómo se llamaba al principio el buscador? BackRub."
    assert ef.validar_guion(cierre_exclamado, 1998, 5, ARTICULO) == []   # también es gancho
    larga = _guion_ok()
    larga["frases"][2]["texto"] = ("Lo arrancaron en la Universidad de Stanford con muy poco y sin "
                                   "saber todavía que iba a cambiar la forma de buscar en la web.")
    assert any("demasiado largas" in e for e in ef.validar_guion(larga, 1998, 5, ARTICULO))
    con_descartada = _guion_ok(fotos_descartadas=[1])
    assert any("descartaste" in e for e in ef.validar_guion(con_descartada, 1998, 5, ARTICULO))
    corto = _guion_ok(frases=_guion_ok()["frases"][:3] + [_guion_ok()["frases"][-1]])
    assert any("palabras" in e for e in ef.validar_guion(corto, 1998, 5, ARTICULO))


def test_escribir_guion_reintenta_con_los_errores():
    malo = _guion_ok()
    malo["frases"][4]["texto"] = "Hoy procesan más de mil millones de búsquedas diarias en el mundo."
    g = FakeGemini(malo, _guion_ok())
    e = ef.Evento("es", 1998, "arranca Google", ["Google"])
    fotos = [ef.a_foto(_info(), "Google") for _ in range(5)]
    guion = ef.escribir_guion(g, e, ARTICULO, fotos, [b"x"] * 5)
    assert "mil millones" in g.prompts[1] and g.imagenes[0] == 5
    assert guion.fotos[:4] == [0, 1, 2, 3] and guion.descartadas == [4]


# ---- cambiar una foto -----------------------------------------------------------------------

def _propuesta(n_fotos=6, reserva=0):
    fotos = [{**ef.a_foto(_info(archivo=f"File:{i}.jpg"), "Google").a_dict(), "ruta": f"{i}.jpg"}
             for i in range(n_fotos)]
    g = ef.Guion(frases=["a", "b", "c", "d"], fotos=[0, 1, 2, 3], descartadas=[4], titulo="t",
                 descripcion="d", hashtags=["#Shorts"])
    return ef.Propuesta(fecha="2026-09-27", evento={"lang": "es", "anio": 1998, "texto": "x",
                                                    "paginas": ["Google"]},
                        fotos=fotos, reserva=[ef.a_foto(_info(), "Google").a_dict()] * reserva,
                        guion=g.a_dict())


class FakeWiki:
    def bajar(self, url, destino):
        return destino


def test_cambiar_foto_usa_primero_una_que_gemini_ya_vio(tmp_path):
    p = _propuesta()                                  # la 5 (índice 4) fue descartada; la 6 está libre
    nueva = ef.cambiar_foto(p, 2, FakeWiki(), tmp_path)
    g = ef.Guion.de_dict(p.guion)
    assert nueva.archivo == "File:5.jpg" and g.fotos == [0, 5, 2, 3] and 1 in g.descartadas


def test_cambiar_foto_despues_va_a_la_reserva_y_si_no_hay_avisa(tmp_path):
    p = _propuesta(n_fotos=5, reserva=1)
    assert ef.cambiar_foto(p, 1, FakeWiki(), tmp_path) is not None and len(p.fotos) == 6
    assert ef.cambiar_foto(p, 3, FakeWiki(), tmp_path) is None     # no queda nada


def test_el_video_tiene_los_creditos_en_el_orden_en_que_aparecen():
    p = _propuesta()
    p.guion = {**p.guion, "fotos": [3, 0, 3, 1]}
    assert [f.archivo for f in ef.usadas_en_orden(p)] == ["File:3.jpg", "File:0.jpg", "File:1.jpg"]
    assert ef.numeros_usados(p) == [1, 2, 4]


# ---- el zoom -----------------------------------------------------------------------------

def test_el_zoom_se_hace_sobre_la_foto_agrandada_4x_y_no_pasa_del_110():
    f = ef.filtro_tramo(2000, 1200, 1080, 1920, 90, 0.3, 0.4, 30)
    assert "scale=4320:2592" in f                     # 1080x648 × 4
    assert "zoompan=z='min(1+0.100*on/89,1.1)'" in f and ":s=1080x648:" in f
    assert "0.3*iw-iw/zoom/2" in f and "0.4*ih-ih/zoom/2" in f


def test_una_foto_vertical_manda_el_alto():
    f = ef.filtro_tramo(1000, 3000, 1080, 1920, 30, 0.5, 0.5, 30)
    assert ":s=640x1920:" in f


# ---- el flujo en el bot ------------------------------------------------------------------

class FakeTG:
    def __init__(self):
        self.mensajes, self.fotos, self.respuestas = [], [], []

    def send_message(self, chat_id, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def send_photo(self, chat_id, path, caption="", teclado=None):
        self.fotos.append(path)

    def answer_callback(self, cid, texto=""):
        self.respuestas.append(texto)

    def edit_message(self, *a, **k):
        pass


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_la_aprobacion_trae_un_boton_por_foto_del_guion(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(ef, "hoja_de_fotos", lambda fotos, salida, numeros=None: salida)
    tg = FakeTG()
    m._efe_mostrar(conn, tg, "1", "0a1b2c", {"propuesta": _propuesta().__dict__,
                                            "carpeta": str(tmp_path), "chat_id": "1"})
    texto, teclado = tg.mensajes[-1]
    datos = [b["callback_data"] for fila in teclado["inline_keyboard"] for b in fila]
    assert datos[:2] == ["efe:ok:0a1b2c", "efe:gno:0a1b2c"]
    assert datos[2:] == [f"efe:f:0a1b2c:{n}" for n in (1, 2, 3, 4)]
    assert "Créditos" in texto and len(tg.fotos) == 1


def test_aprobar_con_algo_pesado_andando_va_a_la_cola(conn, tmp_path):
    db.set_valor(conn, "efe:0a1b2c", json.dumps({"propuesta": _propuesta().__dict__,
                                                 "carpeta": str(tmp_path), "chat_id": "1"}))
    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1)
    tg, cola = FakeTG(), []
    m._efe_callback(conn, tg, {"data": "efe:ok:0a1b2c", "chat_id": "1", "message_id": 3,
                               "callback_id": "q", "user_id": "7"}, None, cola)
    assert cola == [{"chat_id": "1", "comando": "efe:video", "args": ["0a1b2c"], "user_id": "7"}]


def test_sin_aprobar_no_se_sintetiza(conn, monkeypatch, tmp_path):
    """✏️ y 🔁 nunca llegan a la voz."""
    monkeypatch.setattr(ef, "hacer_video", lambda *a, **k: pytest.fail("no se aprobó"))
    monkeypatch.setattr(ef, "hoja_de_fotos", lambda fotos, salida, numeros=None: salida)
    monkeypatch.setattr(ef, "Wiki", FakeWiki)
    db.set_valor(conn, "efe:0a1b2c", json.dumps({"propuesta": _propuesta().__dict__,
                                                 "carpeta": str(tmp_path), "chat_id": "1"}))
    for data in ("efe:gno:0a1b2c", "efe:f:0a1b2c:2"):
        m._efe_callback(conn, FakeTG(), {"data": data, "chat_id": "1", "message_id": 3,
                                         "callback_id": "q", "user_id": "7"}, None, [])
    assert db.get_valor(conn, f"{m.ESPERA_EFE}:7") == "0a1b2c"
    guardado = ef.Guion.de_dict(m._efe_estado(conn, "0a1b2c")["propuesta"]["guion"])
    assert guardado.fotos == [0, 5, 2, 3]            # el 🔁 2 quedó guardado


@pytest.mark.parametrize("texto,esperado", [("27/09", (9, 27)), ("09-27", (9, 27)), ("1/2", (2, 1))])
def test_fecha(texto, esperado):
    d = m._fecha_efemeride(texto)
    assert (d.month, d.day) == esperado


# ---- música de fondo -------------------------------------------------------------------

def test_sin_musica_en_la_carpeta_no_hay_musica(tmp_path):
    assert ef.elegir_musica(tmp_path / "no_existe") is None
    (tmp_path / "README.md").write_text("x")
    assert ef.elegir_musica(tmp_path) is None


def test_elige_una_pista_al_azar_y_su_credito(tmp_path):
    import random

    for n in ("a.mp3", "b.ogg", "c.m4a"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "creditos.json").write_text(json.dumps({"b.ogg": "Tema – Autor – CC BY 4.0 – link"}),
                                            encoding="utf-8")
    elegidas = {ef.elegir_musica(tmp_path, random.Random(s)).name for s in range(30)}
    assert elegidas == {"a.mp3", "b.ogg", "c.m4a"}
    assert ef.credito_musica(tmp_path / "b.ogg") == "Música: Tema – Autor – CC BY 4.0 – link"
    assert ef.credito_musica(tmp_path / "a.mp3") == ""


def test_la_musica_baja_cuando_habla_y_se_apaga_al_final():
    f = ef.filtro_musica(0.12, 42.0)
    assert "volume=0.12" in f and "afade=t=out:st=40.50:d=1.5" in f
    assert "[mus][disparo]sidechaincompress" in f      # la voz dispara el ducking
    assert "amix=inputs=2:duration=first" in f         # dura lo que la voz
