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
    d = {"frases": [{"texto": "Un día como hoy, en 1998, Google estrenó su buscador en Internet.", "mostrar": "1998 Google search 1998", "presente": False},
                    {"texto": "Larry Page y Sergey Brin lo empezaron como un proyecto universitario.", "mostrar": "1998 Larry Page Sergey Brin", "presente": False},
                    {"texto": "Lo arrancaron en la Universidad de Stanford, con muy poco.", "mostrar": "1998 Stanford University", "presente": False},
                    {"texto": "¡Tenían un armario lleno de servidores y dos routers HP!", "mostrar": "1998 Google first server rack", "presente": False},
                    {"texto": "Al principio el buscador no se llamaba Google, se llamaba BackRub.", "mostrar": "1998 BackRub logo", "presente": False},
                    {"texto": "Con el tiempo superó a AltaVista, el más popular de la época.", "mostrar": "1998 AltaVista search", "presente": False},
                    {"texto": "Y el 27 de septiembre de 1998 el buscador salió a Internet para todos.", "mostrar": "1998 Google garage", "presente": False},
                    {"texto": "Desde ese día la forma de buscar cosas en la web cambió para siempre.", "mostrar": "1998 web search computer", "presente": False},
                    {"texto": "¿Te imaginás cómo buscarías cualquier cosa sin este buscador?", "mostrar": "1998 library card catalog", "presente": False}],
         "idea_clave": "Un buscador ordena la web para que encuentres lo que buscás.",
         "titulo": "El día que arrancó Google",
         "descripcion": "Así empezó el buscador.", "hashtags": ["#Shorts", "#Google", "#PequeñaHistoria"]}
    d.update(cambios)
    return d


def test_un_guion_bien_armado_pasa():
    assert ef.validar_guion(_guion_ok(), 1998, ARTICULO) == []


def test_el_gancho_la_pregunta_y_las_fotos():
    sin_gancho = _guion_ok()
    sin_gancho["frases"][0]["texto"] = "En 1998 Google estrenó su buscador en Internet para todo el mundo."
    assert any("Un día como hoy" in e for e in ef.validar_guion(sin_gancho, 1998, ARTICULO))
    sin_pregunta = _guion_ok()
    sin_pregunta["frases"][-1]["texto"] = "Y así fue como empezó todo, en un armario."
    assert any("gancho" in e for e in ef.validar_guion(sin_pregunta, 1998, ARTICULO))
    sin_exclamacion = _guion_ok()
    sin_exclamacion["frases"][3]["texto"] = "Tenían un armario lleno de servidores y dos routers HP."
    assert any("exclamación" in e for e in ef.validar_guion(sin_exclamacion, 1998, ARTICULO))
    cierre_exclamado = _guion_ok()
    cierre_exclamado["frases"][-1]["texto"] = "¡Y todo empezó en un armario de Stanford!"
    cierre_exclamado["frases"][4]["texto"] = "¿Sabés cómo se llamaba al principio el buscador? BackRub."
    assert ef.validar_guion(cierre_exclamado, 1998, ARTICULO) == []   # también es gancho
    larga = _guion_ok()
    larga["frases"][2]["texto"] = ("Lo arrancaron en la Universidad de Stanford con muy poco y sin "
                                   "saber todavía que iba a cambiar la forma de buscar en la web.")
    assert any("demasiado largas" in e for e in ef.validar_guion(larga, 1998, ARTICULO))
    sin_mostrar = _guion_ok()
    sin_mostrar["frases"][2]["mostrar"] = ""
    assert any("mostrar" in e for e in ef.validar_guion(sin_mostrar, 1998, ARTICULO))
    assert any("idea_clave" in e for e in ef.validar_guion(_guion_ok(idea_clave=""), 1998, ARTICULO))
    corto = _guion_ok(frases=_guion_ok()["frases"][:3] + [_guion_ok()["frases"][-1]])
    assert any("te faltan" in e and "porqué" in e for e in ef.validar_guion(corto, 1998, ARTICULO))


def test_escribir_guion_reintenta_con_los_errores():
    malo = _guion_ok()
    malo["frases"][4]["texto"] = "Hoy procesan más de mil millones de búsquedas diarias en el mundo."
    g = FakeGemini(malo, _guion_ok())
    e = ef.Evento("es", 1998, "arranca Google", ["Google"])
    guion = ef.escribir_guion(g, e, ARTICULO)
    assert "mil millones" in g.prompts[1] and g.imagenes == [0, 0]   # el guion va sin fotos
    assert guion.mostrar[2] == "1998 Stanford University" and guion.idea_clave and guion.fotos == []


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
    monkeypatch.setattr(ef, "hoja_de_guion", lambda fotos, filas, salida, videos=None: salida)
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
    monkeypatch.setattr(ef, "hoja_de_guion", lambda fotos, filas, salida, videos=None: salida)
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


# ---- la corrida de las 05:00 -----------------------------------------------------------------

@pytest.fixture
def diaria(monkeypatch, tmp_path):
    """efemeride_del_dia con todo lo externo reemplazado. Devuelve lo que se mandó y a quién."""
    from dataclasses import replace

    from clips_bot import musica
    from clips_bot.config import load_settings

    dbp = tmp_path / "t.db"
    monkeypatch.setattr(m, "DB_PATH", dbp)
    c = db.connect(dbp)
    db.ver_chat(c, "-100", "group", "Rots clips")
    db.marcar_destino(c, "-100", True)
    c.close()
    enviados = {"propuestas": [], "mensajes": []}

    class TG:
        def __init__(self, token):
            pass

        def send_message(self, chat, texto, teclado=None):
            enviados["mensajes"].append((chat, texto))

    monkeypatch.setattr(m, "TelegramClient", TG)
    monkeypatch.setattr(m, "env", lambda *a, **k: "x")
    monkeypatch.setattr(m, "_gemini", lambda s: object())
    monkeypatch.setattr(musica, "llenar", lambda *a, **k: 0)
    monkeypatch.setattr(m, "_efe_proponer",
                        lambda conn, tg, chats, dia, s, g: enviados["propuestas"].append(chats))
    s = load_settings()
    return enviados, lambda **cambios: replace(s, efemerides=replace(s.efemerides, **cambios))


def test_la_corrida_diaria_propone_a_los_destinos(diaria):
    enviados, cfg = diaria
    m.efemeride_del_dia(cfg())
    assert enviados["propuestas"] == [["-100"]]


def test_con_chat_configurado_va_ahi(diaria):
    enviados, cfg = diaria
    m.efemeride_del_dia(cfg(chat="8668060171, 123"))
    assert enviados["propuestas"] == [["8668060171", "123"]]


def test_si_no_sale_avisa_por_que(diaria, monkeypatch):
    enviados, cfg = diaria
    monkeypatch.setattr(m, "_efe_proponer", lambda *a: "No salió la efeméride: ninguno tuvo 4 fotos")
    m.efemeride_del_dia(cfg(reintentos=()))      # sin reintentos: avisa ya
    chat, texto = enviados["mensajes"][-1]
    assert chat == "-100" and "hoy no hay propuesta" in texto and "4 fotos" in texto


def test_simular_y_apagada_no_mandan_nada(diaria):
    enviados, cfg = diaria
    m.efemeride_del_dia(cfg(), simular=True)
    m.efemeride_del_dia(cfg(diaria=False))
    assert enviados == {"propuestas": [], "mensajes": []}


def test_si_la_musica_falla_la_efemeride_sale_igual(diaria, monkeypatch):
    from clips_bot import musica

    enviados, cfg = diaria

    def roto(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(musica, "llenar", roto)
    m.efemeride_del_dia(cfg())
    assert enviados["propuestas"] == [["-100"]]


# ---- Wikimedia: User-Agent, miniaturas, caché, 429 (lo del 2026-09-28) -----------------------

class Resp:
    def __init__(self, status=200, contenido=b"jpg", headers=None, datos=None):
        self.status_code, self.content, self.headers = status, contenido, headers or {}
        self.text, self._datos = contenido.decode(errors="ignore"), datos

    def json(self):
        return self._datos


class Sesion:
    """requests.Session falsa: devuelve las respuestas en orden y anota qué se pidió."""

    def __init__(self, *respuestas):
        self.respuestas, self.pedidos = list(respuestas), []

    def get(self, url, params=None, timeout=None, headers=None):
        self.pedidos.append((url, params, headers))
        return self.respuestas.pop(0)


THUMB = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/A.jpg/1280px-A.jpg"
ORIGINAL = "https://upload.wikimedia.org/wikipedia/commons/c/c1/A.jpg"


def _wiki(sesion, tmp_path, esperas=None):
    return ef.Wiki(session=sesion, sleep=(esperas.append if esperas is not None else lambda s: None),
                   cache=tmp_path / "cache")


def test_user_agent_con_contacto_segun_la_politica_de_wikimedia(monkeypatch):
    from clips_bot.config import user_agent

    monkeypatch.setenv("WIKIMEDIA_CONTACTO", "bot@ejemplo.com")
    ua = user_agent()
    assert ua.startswith("PequenaHistoriaBot/") and "bot@ejemplo.com" in ua
    assert "github.com/S-Fitti848/clips-bot" in ua and "python-requests/" in ua
    assert ua.isascii()      # Openverse da 403 con tildes


def test_todos_los_pedidos_llevan_el_user_agent(tmp_path):
    s = Sesion(Resp(datos={"events": []}), Resp())
    w = _wiki(s, tmp_path)
    w.eventos("es", HOY)
    w.bajar(THUMB, tmp_path / "f.jpg")
    assert all(h["User-Agent"] == w.ua for _, _, h in s.pedidos)


def test_429_respeta_retry_after_y_despues_baja(tmp_path):
    esperas = []
    s = Sesion(Resp(429, b"Too many", {"Retry-After": "37"}), Resp(contenido=b"foto"))
    _wiki(s, tmp_path, esperas).bajar(THUMB, tmp_path / "f.jpg")
    assert 37 in esperas and (tmp_path / "f.jpg").read_bytes() == b"foto"
    assert ef.Wiki.PAUSA_FOTOS_S in esperas          # pausa entre descargas


def test_solo_baja_miniaturas(tmp_path):
    s = Sesion()
    with pytest.raises(ef.WikiError, match="miniatura"):
        _wiki(s, tmp_path).bajar(ORIGINAL, tmp_path / "f.jpg")
    assert s.pedidos == []


def test_la_cache_no_repite_pedidos(tmp_path):
    s = Sesion(Resp(datos={"events": [{"year": 1928, "text": "penicilina", "pages": []}]}),
               Resp(contenido=b"foto"))
    w = _wiki(s, tmp_path)
    assert w.eventos("es", HOY) == w.eventos("es", HOY)
    w.bajar(THUMB, tmp_path / "a.jpg")
    w.bajar(THUMB, tmp_path / "b.jpg")               # otra propuesta, la misma foto
    assert len(s.pedidos) == 2 and (tmp_path / "b.jpg").read_bytes() == b"foto"
    # otro proceso (otra corrida) también la encuentra
    assert _wiki(Sesion(), tmp_path).eventos("es", HOY)[0].anio == 1928


class WikiFotos:
    """archivos/info falsos: la miniatura existe solo si el original es más ancho que lo pedido."""

    def __init__(self, anchos):
        self.anchos, self.pedidos = anchos, []

    def archivos(self, lang, titulo):
        return list(self.anchos)

    def info(self, lang, archivos, ancho=1280):
        self.pedidos.append((archivos, ancho))
        out = []
        for a in archivos:
            i = _info(archivo=a, ancho=self.anchos[a])
            i["thumburl"] = (f"https://upload.wikimedia.org/x/thumb/{a}/{ancho}px-{a}"
                             if self.anchos[a] > ancho else f"https://upload.wikimedia.org/x/{a}")
            out.append(i)
        return out


def test_si_la_api_da_el_original_pide_la_miniatura_de_960_y_si_no_hay_la_saltea():
    w = WikiFotos({"File:grande.jpg": 3000, "File:media.jpg": 1100, "File:justa.jpg": 900})
    fotos, desc = ef.fotos_del_evento(w, ef.Evento("es", 1928, "x", ["Penicilina"]))
    assert [f.archivo for f in fotos] == ["File:grande.jpg", "File:media.jpg"]
    assert all(ef.es_miniatura(f.url) for f in fotos) and "960px" in fotos[1].url
    assert desc == {"sin miniatura": 1}
    assert w.pedidos[1] == (["File:media.jpg"], 960)     # solo las que pueden tener una de 960


class WikiBajar:
    def __init__(self, fallan=(), status=429):
        self.fallan, self.status = set(fallan), status

    def bajar(self, url, destino):
        if url in self.fallan:
            raise ef.WikiError(f"{self.status} x", self.status)
        return destino


def _fotos(n):
    return [ef.a_foto({**_info(archivo=f"File:{i}.jpg"), "thumburl": f"https://u/thumb/{i}"}, "X")
            for i in range(n)]


def test_una_foto_que_falla_se_saltea_y_sigue_con_las_otras(tmp_path):
    fotos = _fotos(8)
    bajadas, reserva = ef.bajar_fotos(WikiBajar({"https://u/thumb/1"}), fotos, tmp_path, "1928", 5)
    assert [f.archivo for f in bajadas] == ["File:0.jpg", "File:2.jpg", "File:3.jpg", "File:4.jpg",
                                            "File:5.jpg"]
    assert [f.archivo for f in reserva] == ["File:6.jpg", "File:7.jpg"]


def test_tres_429_seguidos_cortan_en_vez_de_insistir(tmp_path):
    w = WikiBajar({f"https://u/thumb/{i}" for i in (1, 2, 3)})
    with pytest.raises(ef.WikiError) as e:
        ef.bajar_fotos(w, _fotos(8), tmp_path, "1928", 12)
    assert e.value.status == 429


def test_cambiar_foto_saltea_la_reserva_que_no_baja(tmp_path):
    p = _propuesta(n_fotos=5, reserva=0)
    p.reserva = [f.a_dict() for f in _fotos(2)]
    nueva = ef.cambiar_foto(p, 1, WikiBajar({"https://u/thumb/0"}), tmp_path)
    assert nueva.archivo == "File:1.jpg" and p.reserva == []


# ---- reintentos de las 07:00 y 10:00 --------------------------------------------------------

def test_horas_que_faltan():
    from datetime import datetime

    assert m._efe_horas_que_faltan(["10:00", "7:00"], datetime(2026, 9, 28, 5, 29)) == ["07:00", "10:00"]
    assert m._efe_horas_que_faltan(["07:00", "10:00"], datetime(2026, 9, 28, 8, 0)) == ["10:00"]
    assert m._efe_horas_que_faltan(["07:00", "10:00"], datetime(2026, 9, 28, 11, 0)) == []


def _a_las(h, mi=0):
    from datetime import datetime

    hoy = datetime.now(m.AR).date()
    return datetime(hoy.year, hoy.month, hoy.day, h, mi, tzinfo=m.AR)


def test_si_falla_a_las_5_no_avisa_y_reintenta_a_las_7_y_a_las_10(diaria, monkeypatch):
    enviados, cfg = diaria
    resultados = ["No salió la efeméride: 429", "No salió la efeméride: 429 otra vez",
                  "No salió la efeméride: 429 de nuevo"]
    llamadas = []

    def proponer(conn, tg, chats, dia, s, g):
        llamadas.append((chats, dia))
        return resultados.pop(0)

    monkeypatch.setattr(m, "_efe_proponer", proponer)
    monkeypatch.setattr(m, "_efe_horas_que_faltan", lambda horas, ahora: ["07:00", "10:00"])
    m.efemeride_del_dia(cfg())
    assert enviados["mensajes"] == [] and len(llamadas) == 1        # a las 05:00 no avisa

    conn = db.connect(m.DB_PATH)
    tg = m.TelegramClient("x")
    m._efe_reintento_tick(conn, tg, cfg(), ahora=_a_las(6, 59))
    assert len(llamadas) == 1                                       # todavía no es la hora
    m._efe_reintento_tick(conn, tg, cfg(), ahora=_a_las(7, 0))
    m._efe_reintento_tick(conn, tg, cfg(), ahora=_a_las(7, 1))
    assert len(llamadas) == 2 and enviados["mensajes"] == []        # uno solo a las 7
    m._efe_reintento_tick(conn, tg, cfg(), ahora=_a_las(10, 0))
    assert len(llamadas) == 3 and llamadas[-1] == (["-100"], _a_las(10).date())
    chat, texto = enviados["mensajes"][-1]
    assert chat == "-100" and "hoy no hay propuesta" in texto and "05:00, 07:00, 10:00" in texto
    assert db.get_valor(conn, m.EFE_REINTENTO) is None
    m._efe_reintento_tick(conn, tg, cfg(), ahora=_a_las(11, 0))
    assert len(llamadas) == 3                                       # no queda nada pendiente


def test_si_sale_en_el_reintento_no_avisa_nada(diaria, monkeypatch):
    enviados, cfg = diaria
    resultados = ["No salió la efeméride: 429", None]
    monkeypatch.setattr(m, "_efe_proponer", lambda *a: resultados.pop(0))
    monkeypatch.setattr(m, "_efe_horas_que_faltan", lambda horas, ahora: ["07:00", "10:00"])
    m.efemeride_del_dia(cfg())
    conn = db.connect(m.DB_PATH)
    m._efe_reintento_tick(conn, m.TelegramClient("x"), cfg(), ahora=_a_las(7, 0))
    assert enviados["mensajes"] == [] and db.get_valor(conn, m.EFE_REINTENTO) is None


def test_el_reintento_espera_si_hay_algo_pesado_andando(diaria, monkeypatch):
    enviados, cfg = diaria
    llamadas = []
    monkeypatch.setattr(m, "_efe_proponer", lambda *a: llamadas.append(1) or "No salió")
    monkeypatch.setattr(m, "_efe_horas_que_faltan", lambda horas, ahora: ["07:00"])
    m.efemeride_del_dia(cfg())
    conn = db.connect(m.DB_PATH)
    db.tomar_turno(conn, db.RECURSO_PESADO, "diario", maximo=1, vencimiento_s=3600)
    m._efe_reintento_tick(conn, m.TelegramClient("x"), cfg(), ahora=_a_las(7, 0))
    assert len(llamadas) == 1 and db.get_valor(conn, m.EFE_REINTENTO)   # sigue pendiente


# ---- 2026-09-28: mínimo 70, "…Volvió" no es un nombre, /efemeride con tema -------------------------

def test_un_guion_de_70_a_84_palabras_ya_no_falla_por_corto():
    d = _guion_ok()
    while len(" ".join(f["texto"] for f in d["frases"]).split()) > 84:
        d["frases"].pop(-2)               # se saca del medio: el cierre con gancho queda
    n = len(" ".join(f["texto"] for f in d["frases"]).split())
    assert ef.PALABRAS_MIN == 70 and 70 <= n <= 84
    assert not any("palabras" in e for e in ef.validar_guion(d, 1998, ARTICULO))


@pytest.mark.parametrize("frase,marcados", [
    ("…Volvió de sus vacaciones.", []),
    ("(Volvió de sus vacaciones.)", []),
    ("«Volvió de sus vacaciones», contó.", []),
    ("Y entonces Volvió al laboratorio.", ["Volvió"]),     # en el medio de la oración sí cuenta
])
def test_mayuscula_al_principio_de_una_oracion_no_es_un_nombre(frase, marcados):
    assert ef.no_respaldados(frase, ARTICULO) == marcados


@pytest.mark.parametrize("args,fecha,tema", [
    ([], None, ""),
    (["penicilina"], None, "penicilina"),
    (["28/09", "penicilina"], "28/09", "penicilina"),
    (["penicilina", "28/09"], "28/09", "penicilina"),
    (["20/07"], "20/07", ""),
    (["piedra", "de", "Rosetta"], None, "piedra de Rosetta"),
])
def test_args_de_efemeride(args, fecha, tema):
    assert m._args_efemeride(args) == (fecha, tema)


def test_efemeride_con_tema_pasa_el_tema_a_la_propuesta(conn, monkeypatch):
    pedidos = []
    monkeypatch.setattr(m, "_gemini", lambda s: object())
    monkeypatch.setattr(m, "_efe_proponer",
                        lambda conn, tg, chats, dia, s, g, hecho="": pedidos.append((dia, hecho)))
    tg = FakeTG()
    m._efemeride(conn, tg, "1", ["28/09", "penicilina"], None)
    assert pedidos and pedidos[0][0].day == 28 and pedidos[0][1] == "penicilina"
    assert "sobre «penicilina»" in tg.mensajes[0][0]
