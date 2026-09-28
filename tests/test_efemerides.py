"""Pequeña Historia: filtros de eventos y fotos, validación del guion contra el artículo, y el flujo.

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
                    {"texto": "Y el 27 de septiembre de 1998 el buscador salió a Internet para todos.", "foto": 4},
                    {"texto": "Desde ese día la forma de buscar cosas en la web cambió para siempre.", "foto": 1},
                    {"texto": "¿Te imaginás cómo buscarías cualquier cosa sin este buscador?", "foto": 2}],
         "fotos_descartadas": [5], "titulo": "El día que arrancó Google",
         "descripcion": "Así empezó el buscador.", "hashtags": ["#Shorts", "#Google", "#PequeñaHistoria"]}
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


# ---- la voz: Gemini TTS con respaldo de Piper, y la alineación al guion --------------------

def test_alinear_usa_el_texto_del_guion_y_los_tiempos_de_whisper():
    from clips_bot.narrar import alinear_a_guion
    from clips_bot.subtitles import Palabra

    frases = ["Un día como hoy, Jean-François hizo un anuncio.", "¡Lo logró!"]
    whisper = [Palabra(0.1, 0.3, "Un"), Palabra(0.3, 0.5, "día"), Palabra(0.5, 0.7, "como"),
               Palabra(0.7, 0.9, "hoy,"), Palabra(1.0, 1.3, "Jean"), Palabra(1.3, 1.7, "-François"),
               Palabra(1.7, 2.0, "hizo"), Palabra(2.0, 2.1, "un"), Palabra(2.1, 2.6, "anuncia."),
               Palabra(3.0, 3.2, "Lo"), Palabra(3.2, 3.6, "logró.")]
    palabras, inicios = alinear_a_guion(whisper, frases, 4.0)
    assert [p.texto for p in palabras] == ["Un", "día", "como", "hoy,", "Jean-François", "hizo", "un",
                                           "anuncio.", "¡Lo", "logró!"]
    assert inicios == [0.0, 3.0]


def test_alinear_sin_nada_de_whisper_reparte_parejo():
    from clips_bot.narrar import alinear_a_guion

    palabras, inicios = alinear_a_guion([], ["uno dos", "tres cuatro"], 4.0)
    assert [round(p.inicio, 2) for p in palabras] == [0.0, 1.0, 2.0, 3.0] and inicios == [0.0, 2.0]


def _cfg_voz(tmp_path, motor="gemini"):
    from dataclasses import replace

    from clips_bot.config import load_settings

    s = load_settings()
    return replace(s, efemerides=replace(s.efemerides, voz_motor=motor))


def test_voz_con_gemini_no_devuelve_duraciones_y_acelera_si_se_pasa(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    acelerados = []
    monkeypatch.setattr(ef, "acelerar", lambda wav, f: acelerados.append(round(f, 3)) or wav)
    pcm = b"\x00\x00" * 24000 * 50                     # 50 s a 24 kHz
    wav, dur, motor = ef.voz_efemeride(["hola"], _cfg_voz(tmp_path), tmp_path,
                                       tts=lambda *a, **k: (pcm, 24000))
    assert dur is None and motor == "gemini:Laomedeia" and acelerados == [round(50 / 45, 3)]


def test_sin_cuota_de_gemini_va_piper_ajustado(tmp_path, monkeypatch):
    from clips_bot import narrar
    from clips_bot.gemini import GeminiError

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    usados = []

    def piper(frases, modelo, salida, pausa_s=0.3, ajustes=None):
        usados.append(ajustes)
        return salida, [1.0] * len(frases)

    def sin_cuota(*a, **k):
        raise GeminiError("429 quota")

    monkeypatch.setattr(narrar, "sintetizar_frases", piper)
    s = _cfg_voz(tmp_path)
    from dataclasses import replace
    modelo = tmp_path / "v.onnx"
    modelo.write_bytes(b"")
    s = replace(s, voz=replace(s.voz, modelo=str(modelo)))
    wav, dur, motor = ef.voz_efemeride(["a", "b"], s, tmp_path, tts=sin_cuota)
    assert motor.startswith("piper:") and dur == [1.0, 1.0]
    aj = usados[0]
    assert (aj.length_scale, aj.noise_w_scale, aj.semitonos) == (0.88, 1.0, 1.5)


def test_si_la_voz_lee_algo_antes_del_guion_se_recorta(tmp_path, monkeypatch):
    """Gemini TTS leía la instrucción de tono en voz alta (10 s antes del guion, 28/09)."""
    from clips_bot import narrar
    from clips_bot.subtitles import Palabra

    cortes = []
    monkeypatch.setattr(narrar, "run", lambda args: cortes.append(args[args.index("-ss") + 1]))
    wav = tmp_path / "voz.wav"
    wav.with_name("voz.recorte.wav").write_bytes(b"x")
    oidas = [Palabra(0.0, 0.5, "Leé"), Palabra(0.5, 0.7, "esto"), Palabra(10.4, 10.7, "Un"),
             Palabra(10.7, 10.9, "día"), Palabra(10.9, 11.1, "como"), Palabra(11.1, 11.4, "hoy,")]
    palabras, corte = narrar.recortar_inicio(wav, oidas, ["Un día como hoy, en 1822, pasó algo."])
    assert round(corte, 2) == 10.28 and cortes == ["10.280"]
    assert palabras[0].texto == "Un" and round(palabras[0].inicio, 2) == 0.12


def test_si_arranca_bien_no_se_toca(tmp_path, monkeypatch):
    from clips_bot import narrar
    from clips_bot.subtitles import Palabra

    monkeypatch.setattr(narrar, "run", lambda args: pytest.fail("no había nada que recortar"))
    oidas = [Palabra(0.05, 0.3, "Un"), Palabra(0.3, 0.5, "día"), Palabra(0.5, 0.7, "como")]
    assert narrar.recortar_inicio(tmp_path / "v.wav", oidas, ["Un día como hoy"])[1] == 0.0
