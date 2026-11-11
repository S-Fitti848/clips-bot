"""El video de Pequeña Historia para Facebook (locales.py, claude.py; pedido de Santi el 2026-11-09):
historias humanas de un lugar concreto de Latinoamérica, texto con Claude, voz por la segunda clave,
subida solo a Facebook a historias_fb.hora_publicacion. Nada sale a la red."""

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from clips_bot import claude, db, locales
from clips_bot import efemerides as ef

WIKITEXTO = """== Acontecimientos ==
* [[1813]]: se produce la [[Batalla de Tierrita Blanca]] en [[Venezuela]].
* 1985: se inunda, bajo las aguas del [[Laguna Epecuén|lago Epecuén]], el centro turístico bonaerense [[Villa Epecuén]], a 7{{esd}}km de [[Carhué]] ([[Argentina]]).<ref>{{cita web|url=x}}</ref>
* 1990: en [[España]] se inaugura un puente.
* 2001: en [[Lima]] (Perú) un atentado con bomba destruye un edificio.
== Nacimientos ==
* [[1795]]: [[Policarpa Salavarrieta]], heroína colombiana (f. 1817).
* [[1834]]: [[Fulano de Tal]], escritor argentino.
== Celebraciones ==
* {{bandera|Colombia}} [[Colombia]]: Día de la Mujer Colombiana, en homenaje a [[Policarpa Salavarrieta]].
"""


class WikiFalsa:
    def __init__(self):
        self.pedidos = []

    def _get(self, url, params=None):
        self.pedidos.append(params)
        return {"parse": {"wikitext": WIKITEXTO}}


def test_leer_dia_y_filtrar():
    w = WikiFalsa()
    todos, conm, homen = locales.leer_dia(w, date(2026, 11, 10))
    assert w.pedidos[0]["page"] == "10 de noviembre"
    assert any("Mujer Colombiana" in c for c in conm)
    assert "Policarpa Salavarrieta" in homen
    epe = next(c for c in todos if c.anio == 1985)
    assert "Villa Epecuén" in epe.texto and "{{" not in epe.texto and "<ref" not in epe.texto
    assert epe.paginas[:3] == ["Laguna Epecuén", "Villa Epecuén", "Carhué"]
    ok, motivos = locales.filtrar(todos, date(2026, 11, 10), homen)
    anios = sorted(c.anio for c in ok)
    # Epecuén y Tierrita Blanca (lugar de Latinoamérica), La Pola (se la conmemora ese día).
    # Afuera: España (sin lugar), el atentado (duro) y el escritor (nadie lo conmemora).
    assert anios == [1795, 1813, 1985]
    assert motivos["tema sensible"] == 1


class Falso:
    """Un cliente con la forma de GeminiClient/ClaudeClient: devuelve lo que se le diga por schema."""

    def __init__(self, respuestas):
        self.respuestas = respuestas
        self.llamadas = []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, **k):
        self.llamadas.append((sistema, prompt))
        return json.dumps(self.respuestas.pop(0))


def _cands():
    return [locales.Candidato("acontecimientos", 1985, "se inunda Villa Epecuén", ["Laguna Epecuén", "Villa Epecuén"]),
            locales.Candidato("acontecimientos", 1913, "se funda el Deportivo Independiente Medellín",
                              ["Medellín", "Deportivo Independiente Medellín"]),
            locales.Candidato("acontecimientos", 1985, "erupción y miles de muertos en Armero", ["Armero"])]


def test_clasificar_y_buenos():
    haiku = Falso([{"hechos": [
        {"n": 1, "humana": True, "lugar": "Villa Epecuén", "region": "Buenos Aires", "pais": "Argentina",
         "tipo": "momento_emotivo", "tragedia_sola": False, "conmemora": "", "interes": 8},
        {"n": 2, "humana": False, "lugar": "Medellín", "region": "", "pais": "Colombia", "tipo": "otro",
         "tragedia_sola": False, "conmemora": "", "interes": 3},
        {"n": 3, "humana": True, "lugar": "Armero", "region": "Tolima", "pais": "Colombia",
         "tipo": "momento_emotivo", "tragedia_sola": True, "conmemora": "", "interes": 9}]}])
    cands = locales.clasificar(haiku, _cands(), ["Día de la Tradición"])
    assert "Día de la Tradición" in haiku.llamadas[0][1]
    b = locales.buenos(cands)
    assert [c.clasif["lugar"] for c in b] == ["Villa Epecuén"]   # ni el club ni la tragedia sola


def test_buenos_pone_primero_lo_que_se_conmemora():
    a, b = _cands()[:2]
    a.clasif = {"humana": True, "lugar": "X", "interes": 9, "conmemora": ""}
    b.clasif = {"humana": True, "lugar": "Y", "interes": 5, "conmemora": "Día del pueblo"}
    assert [c.clasif["lugar"] for c in locales.buenos([a, b])] == ["Y", "X"]


def test_elegir_valida_los_articulos():
    c = _cands()[0]
    c.clasif = {"lugar": "Villa Epecuén"}
    sonnet = Falso([{"elegidos": [{"n": 1, "articulo": "Inventado", "articulo_lugar": "Villa Epecuén",
                                   "motivo": "x"}, {"n": 7, "articulo": "", "articulo_lugar": "", "motivo": ""}]}])
    [(cand, art, lug)] = locales.elegir(sonnet, [c])
    assert art == "Laguna Epecuén"          # no está en la lista: el primero del hecho
    assert lug == "Villa Epecuén"


def _guion(primera="Un día como hoy, en 1985, en Villa Epecuén, el agua tapó todo.",
           titulo="Villa Epecuén: el pueblo bajo el agua", tags=("#Shorts", "#VillaEpecuen", "#Argentina")):
    return {"frases": [{"texto": primera}], "titulo": titulo, "hashtags": list(tags)}


def test_validar_lugar():
    v = locales.validar_lugar("Villa Epecuén")
    assert v(_guion()) == []
    errores = v(_guion(primera="Un día como hoy, en 1985, el agua tapó todo.", titulo="El pueblo bajo el agua",
                       tags=("#Shorts", "#Argentina")))
    assert len(errores) == 3


def test_el_prompt_del_guion_pide_el_lugar():
    assert "en <lugar>," in locales.SISTEMA_GUION_LOCAL
    assert "#VillaEpecuen" in locales.SISTEMA_GUION_LOCAL
    assert ef.REGLAS_CLARIDAD in locales.SISTEMA_GUION_LOCAL    # regla fija 2


# ---- claude.py -----------------------------------------------------------------------------

def test_schema_de_gemini_a_json_schema():
    s = claude.a_json_schema(ef.SCHEMA_GUION)
    assert s["type"] == "object" and s["additionalProperties"] is False
    frase = s["properties"]["frases"]["items"]
    assert frase["properties"]["presente"] == {"type": "boolean"}
    assert frase["additionalProperties"] is False
    assert s["properties"]["tono"]["enum"][0] == "alegre"


class _Resp:
    def __init__(self, texto="{}", stop="end_turn"):
        self.content = [SimpleNamespace(type="text", text=texto)]
        self.stop_reason = stop
        self.usage = SimpleNamespace(input_tokens=1000, output_tokens=200)
        self.model = "m"


class _SDK:
    def __init__(self, resp):
        self.pedidos = []
        resp_ = resp

        class _M:
            def create(_, **k):
                self.pedidos.append(("std", k))
                return resp_

        class _B:
            messages = None

        class _BM:
            def create(_, **k):
                self.pedidos.append(("beta", k))
                return resp_

        self.messages = _M()
        self.beta = _B()
        self.beta.messages = _BM()


def test_sonnet_con_respaldo_y_haiku_sin():
    sdk = _SDK(_Resp('{"a": 1}'))
    usos = []
    c = claude.ClaudeClient("k", claude.SONNET, cliente=sdk, uso=lambda *a: usos.append(a))
    assert json.loads(c.json("sis", "hola", {"type": "OBJECT", "properties": {"a": {"type": "INTEGER"}},
                                             "required": ["a"]})) == {"a": 1}
    tipo, k = sdk.pedidos[0]
    assert tipo == "beta" and k["fallbacks"] == "default" and "temperature" not in k
    assert k["output_config"]["format"]["schema"]["properties"]["a"] == {"type": "integer"}
    assert usos[0][2] == "claude" and usos[0][3:5] == (1000, 200)
    h = claude.ClaudeClient("k", claude.HAIKU, cliente=sdk, esfuerzo="low")
    h.json("sis", "hola", {"type": "OBJECT", "properties": {}})
    tipo, k = sdk.pedidos[1]
    assert tipo == "std" and "fallbacks" not in k and k["output_config"]["effort"] == "low"


def test_un_rechazo_es_error_y_las_imagenes_no_van():
    c = claude.ClaudeClient("k", claude.SONNET, cliente=_SDK(_Resp("", "refusal")))
    with pytest.raises(claude.ClaudeError):
        c.json("s", "p", {"type": "OBJECT"})
    with pytest.raises(claude.ClaudeError):
        c.json("s", "p", {"type": "OBJECT"}, imagenes=[b"x"])


def test_costo():
    assert claude.costo(claude.SONNET, 1_000_000, 100_000) == pytest.approx(3.0)
    assert claude.costo(claude.HAIKU, 1_000_000, 0) == pytest.approx(0.10)


# ---- voz por la segunda clave ----------------------------------------------------------------

def test_la_voz_de_facebook_va_por_la_segunda(monkeypatch, tmp_path):
    from clips_bot import gemini, narrar
    from clips_bot.config import load_settings

    monkeypatch.setenv("GEMINI_API_KEY", "A")
    monkeypatch.setattr(gemini, "claves_activas", lambda: [("principal", "A"), ("segunda", "B")])
    monkeypatch.setattr(narrar, "a_48k", lambda p: p)
    usadas = []

    def tts(clave, texto, **k):
        usadas.append(clave)
        return b"\0\0" * 2400, 24000

    settings = load_settings()
    ef.voz_efemeride(["Hola."], settings, tmp_path, tts=tts, segunda_primero=True)
    ef.voz_efemeride(["Hola."], settings, tmp_path, tts=tts)
    assert usadas == ["B", "A"]


# ---- la escucha a las 06:30 y la subida solo a Facebook -------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


class TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, **k):
        self.mensajes.append((chat, texto))


def test_fb_tick_una_vez_por_dia_desde_las_0630(conn, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot.config import load_settings

    settings = load_settings()
    monkeypatch.setattr(db, "destinos", lambda c: ["-100"])
    llamados = []

    def proponer(conn_, tg, chats, dia, settings_, hecho=""):
        llamados.append((chats, dia, hecho))
        return None

    tg = TG()
    m._fb_tick(conn, tg, settings, ahora=datetime(2026, 11, 10, 6, 10, tzinfo=m.AR), proponer=proponer)
    assert llamados == []
    db.set_valor(conn, m.FB_FECHA_FIJA, json.dumps({"dia": "2026-11-10", "hecho": "Epecuén"}))
    m._fb_tick(conn, tg, settings, ahora=datetime(2026, 11, 10, 6, 31, tzinfo=m.AR), proponer=proponer)
    m._fb_tick(conn, tg, settings, ahora=datetime(2026, 11, 10, 9, 0, tzinfo=m.AR), proponer=proponer)
    assert llamados == [(["-100"], date(2026, 11, 10), "Epecuén")]
    assert db.hay_trabajo_pesado(conn) is None      # el turno se soltó
    m._fb_tick(conn, tg, settings, ahora=datetime(2026, 11, 11, 6, 40, tzinfo=m.AR),
               proponer=lambda *a, **k: "No salió la historia de Facebook: x")
    assert "hoy no hay propuesta" in tg.mensajes[-1][1]


def test_la_historia_sube_solo_a_facebook_a_su_hora(conn, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot.config import load_settings

    settings = load_settings()
    meta = {"clip_id": "historia_fb_1110_1985", "salida": "x.mp4",
            "textos": {"titulo": "Villa Epecuén", "descripcion": "d", "hashtags": ["#Shorts"]},
            "efemeride": {"fecha": "2026-11-10", "anio": 1985, "destino": "facebook",
                          "local": {"lugar": "Villa Epecuén", "pais": "Argentina", "tipo": "momento_emotivo"}}}
    monkeypatch.setattr(m, "_programar_subida", lambda *a, **k: pytest.fail("no va a YouTube"))
    horas = []

    def subir_fb(conn_, settings_, meta_, ahora=None, hora=None):
        horas.append(hora)
        m._registrar_historia_fb(conn_, meta_, "123", "2026-11-10T22:00:00Z")
        return "📘 Programado en Facebook para las 19:00."

    monkeypatch.setattr(m, "_subir_facebook", subir_fb)
    avisos = m._subir(conn, settings, meta, "pequena_historia")
    assert avisos == ["📘 Programado en Facebook para las 19:00."]
    assert horas == [m.hora_historia_fb(settings, "Argentina", datetime.now(m.AR).date())]  # su país
    [r] = json.loads(db.get_valor(conn, m.HISTORIAS_FB_REGISTRO))
    assert r["tipo"] == "momento_emotivo" and r["lugar"] == "Villa Epecuén" and r["video_id"] == "123"


def test_una_efemeride_comun_sigue_igual(conn, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot.config import load_settings

    settings = load_settings()
    meta = {"clip_id": "efemeride_1110_1985", "efemeride": {"fecha": "2026-11-10"}}
    assert not m._solo_facebook(meta)
    llamado = []
    monkeypatch.setattr(m, "_programar_subida", lambda *a, **k: llamado.append("yt") or "")
    monkeypatch.setattr(m, "_subir_facebook", lambda *a, **k: llamado.append(k.get("hora")) or "")
    m._subir(conn, settings, meta, "pequena_historia")
    assert llamado[:1] == (["yt"] if settings.youtube_upload_enabled else [None])


def test_historia_en_la_ayuda():
    import clips_bot.__main__ as m

    assert any(c[0].startswith("/historia") for c in m.COMANDOS)


def test_un_hecho_elegido_a_mano_no_lo_descarta_haiku(tmp_path, monkeypatch):
    """/historia 10/11 Epecuén: aunque Haiku diga que no es una historia humana, se usa (lo eligió
    una persona). Haiku clasifica el día entero, no solo ese hecho."""
    haiku = Falso([{"hechos": [
        {"n": 1, "humana": True, "lugar": "Tierrita Blanca", "region": "", "pais": "Venezuela",
         "tipo": "otro", "tragedia_sola": False, "conmemora": "", "interes": 3},
        {"n": 2, "humana": False, "lugar": "", "region": "", "pais": "Argentina", "tipo": "otro",
         "tragedia_sola": False, "conmemora": "", "interes": 2},
        {"n": 3, "humana": True, "lugar": "Bogotá", "region": "", "pais": "Colombia", "tipo": "otro",
         "tragedia_sola": False, "conmemora": "", "interes": 5}]}])
    vistos = []

    def elegir(sonnet, lista, cuantos=8):
        vistos.extend(lista)
        raise ef.NarrarError("corto acá")

    monkeypatch.setattr(locales, "elegir", elegir)
    monkeypatch.setattr(locales.ef, "MAX_GUIONES", 0)
    with pytest.raises(ef.NarrarError):
        locales.proponer(WikiFalsa(), None, haiku, None, date(2026, 11, 10), tmp_path, hecho="Epecuén")
    assert len(haiku.llamadas) == 1 and "Tierrita" in haiku.llamadas[0][1]   # el día entero
    assert [c.anio for c in vistos] == [1985]
    assert vistos[0].clasif["lugar"] == "Laguna Epecuén"     # sin lugar: el primer artículo


def test_sor_juana_entra_aunque_el_enlace_sea_otra_redireccion():
    """12/11: el nacimiento enlaza "Juana Inés de la Cruz" y el Día Nacional del Libro, la
    redirección "Sor Juana Inés de la Cruz". Antes no coincidían y Sor Juana no era candidata."""
    c = locales.Candidato("nacimientos", 1651, "sor Juana Inés de la Cruz, poetisa mexicana (f. 1695).",
                          ["Juana Inés de la Cruz"])
    assert locales.motivo_local(c, date(2026, 11, 12), {"Sor Juana Inés de la Cruz"}) is None
    assert locales.motivo_local(c, date(2026, 11, 12), {"Juana de Arco"}) == \
        "nacimiento o muerte sin conmemoración"
    assert locales.homenajeado("Policarpa Salavarrieta", {"Policarpa Salavarrieta"})
    assert not locales.homenajeado("Juana", {"Juana Azurduy"})


def test_fb_tick_con_un_hecho_fijado_para_un_dia(conn, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot.config import load_settings

    monkeypatch.setattr(db, "destinos", lambda c: ["-100"])
    db.set_valor(conn, m.FB_FECHA_FIJA, json.dumps({"dia": "2026-11-10", "hecho": "Epecuén"}))
    db.set_valor(conn, f"{m.FB_FECHA_FIJA}:2026-11-12", "Juana Inés")
    hechos = []
    proponer = lambda conn_, tg, chats, dia, s, hecho="": hechos.append((dia.day, hecho))
    for dia in (10, 11, 12):
        m._fb_tick(conn, TG(), load_settings(), ahora=datetime(2026, 11, dia, 6, 35, tzinfo=m.AR),
                   proponer=proponer)
    assert hechos == [(10, "Epecuén"), (11, ""), (12, "Juana Inés")]
