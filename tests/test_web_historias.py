"""Fuentes web para Latinoamérica (Santi, 2026-11-16, opción C): historias de diarios, museos y sitios de historia
con Haiku, cada dato verificado con 2 fuentes de sitios distintos antes del guion, el costo de las búsquedas en
/costos y la prueba de un día real que se apaga sola si se pasa."""

import json
from datetime import date, datetime
from types import SimpleNamespace as NS

import pytest

from clips_bot import __main__ as m
from clips_bot import claude, db, locales
from clips_bot import efemerides as ef
from clips_bot import web_historias as wh
from clips_bot.config import load_settings

HOY = date(2026, 11, 17)


def _resp(texto, busquedas=0, stop="end_turn", urls=()):
    contenido = [NS(type="web_search_tool_result", content=[NS(url=u) for u in urls]), NS(type="text", text=texto)]
    return NS(content=contenido, stop_reason=stop,
              usage=NS(input_tokens=1000, output_tokens=200, server_tool_use=NS(web_search_requests=busquedas)))


class _Anthropic:
    def __init__(self, respuestas):
        self.respuestas, self.pedidos = list(respuestas), []
        self.messages = self

    def create(self, **k):
        self.pedidos.append(k)
        return self.respuestas.pop(0)


def _cliente(respuestas):
    usos = []
    api = _Anthropic(respuestas)
    return wh.ClienteWeb(cliente=api, uso=lambda *a: usos.append(a)), api, usos


def test_las_busquedas_se_anotan_a_un_centavo(monkeypatch):
    c, api, usos = _cliente([_resp('```json\n{"historias": []}\n```', busquedas=3, urls=["https://a.com/x"])])
    texto, links = c.pedir("s", "p", busquedas=5, lecturas=2)
    tools = api.pedidos[0]["tools"]
    assert [t["type"] for t in tools] == [wh.HERRAMIENTA_BUSCAR, wh.HERRAMIENTA_LEER]
    assert tools[0]["max_uses"] == 5 and api.pedidos[0]["model"] == wh.HAIKU
    assert links == ["https://a.com/x"]
    (f1, mod1, _, e1, s1, _), (f2, mod2, _, e2, _, _) = usos
    assert mod1 == wh.HAIKU and (e1, s1) == (1000, 200)
    assert mod2 == wh.MODELO_BUSQUEDA and e2 == 3
    assert claude.costo(mod2, e2, 0) == pytest.approx(0.03)


def test_pause_turn_sigue_y_suma(monkeypatch):
    c, api, usos = _cliente([_resp("", busquedas=2, stop="pause_turn"), _resp("listo", busquedas=1)])
    texto, _ = c.pedir("s", "p", busquedas=5)
    assert texto == "listo" and len(api.pedidos) == 2
    assert usos[0][3] == 2000 and usos[1][3] == 3


def test_dominio_wikipedia_cuenta_una_sola_vez():
    assert wh.dominio("https://es.wikipedia.org/wiki/X") == wh.dominio("https://en.m.wikipedia.org/wiki/Y")
    assert wh.dominio("https://www.eltiempo.com/a") == "eltiempo.com"


VERIF_OK = {"datos": [
    {"dato": "Jesús García era maquinista.", "fuentes": ["https://es.wikipedia.org/a", "https://inah.gob.mx/b"]},
    {"dato": "Fue en 1907.", "fuentes": ["https://www.eluniversal.com.mx/c", "https://mexicodesconocido.com.mx/d"]},
    {"dato": "Pasó en Nacozari.", "fuentes": ["https://sonora.gob.mx/e", "https://es.wikipedia.org/f"]},
    {"dato": "Murió en la explosión.", "fuentes": ["https://es.wikipedia.org/g", "https://en.wikipedia.org/h"]}],
    "resumen": "En 1907, en Nacozari, el maquinista Jesús García…", "es_real": True, "problema": ""}


def test_verificar_pide_dos_sitios_distintos():
    c, _, _ = _cliente([_resp("```json\n" + json.dumps(VERIF_OK) + "\n```")])
    v = wh.verificar(c, "el maquinista", 1907, "Nacozari", "México")
    assert v.ok and len(v.datos) == 3                       # el de es+en Wikipedia no cuenta
    assert "Murió en la explosión" not in v.texto and "Fue en 1907." in v.texto
    pocos = dict(VERIF_OK, datos=VERIF_OK["datos"][:2])
    c, _, _ = _cliente([_resp(json.dumps(pocos))])
    v = wh.verificar(c, "x", 1907, "Nacozari", "México")
    assert not v.ok and "solo 2 datos" in v.motivo
    c, _, _ = _cliente([_resp(json.dumps(dict(VERIF_OK, es_real=False, problema="es una leyenda")))])
    assert not wh.verificar(c, "x", 1907, "N", "M").ok


def test_buscar_filtra_lo_que_no_tiene_link_ni_anio():
    hist = {"historias": [
        {"texto": "Un invento", "anio": 1950, "fecha": "17/11", "lugar": "Medellín", "pais": "Colombia",
         "tipo": "invento", "fuentes": ["https://eltiempo.com/x"], "interes": 8},
        {"texto": "Sin link", "anio": 1950, "lugar": "Lima", "pais": "Perú", "fuentes": []},
        {"texto": "Sin año", "anio": "?", "lugar": "Lima", "pais": "Perú", "fuentes": ["https://a.pe"]}]}
    c, api, _ = _cliente([_resp(json.dumps(hist))])
    out = wh.buscar(c, HOY, evitar=["ya salió"])
    assert [h["texto"] for h in out] == ["Un invento"] and wh.es_del_dia(out[0], HOY)
    assert "17 de noviembre" in api.pedidos[0]["messages"][0]["content"]
    assert "ya salió" in api.pedidos[0]["messages"][0]["content"]


# ---- en la propuesta -----------------------------------------------------------------------------------

class _Puntuador:
    def __init__(self, nota):
        self.nota = nota

    def json(self, sistema, prompt, schema, **k):
        return json.dumps({"elegidos": [{"n": 1, "articulo": "", "articulo_lugar": "", "motivo": "",
                                         "persona": self.nota, "peligro": self.nota, "giro": self.nota,
                                         "emocion": self.nota, "sorpresa": 0}]})


@pytest.fixture
def sin_red(monkeypatch):
    usados = []
    monkeypatch.setattr(locales, "leer_todo", lambda wiki, dia, avisar: ([], [], set()))
    monkeypatch.setattr(ef, "fotos_del_evento", lambda wiki, e: ([], {}))
    monkeypatch.setattr(ef, "texto_fuente", lambda wiki, e: "TEXTO DEL ARTÍCULO")

    def guion(cliente, e, fuente, *a, contexto="", **k):
        usados.append((e.texto, fuente, contexto))
        return ef.Guion(frases=["a"], fotos=[0], descartadas=[], titulo="t", descripcion="d", hashtags=[])

    monkeypatch.setattr(ef, "escribir_guion", guion)
    monkeypatch.setattr(ef, "fotos_con_control", lambda wiki, cl, e, g, *a, **k: ([], g))
    return usados


def _web(monkeypatch, del_dia=True, verificada=True):
    h = {"texto": "El cartero de Mompox", "anio": 1932, "fecha": "17/11" if del_dia else "", "lugar": "Mompox",
         "pais": "Colombia", "tipo": "gente_comun", "fuentes": ["https://eltiempo.com/x"], "interes": 9}
    monkeypatch.setattr(wh, "buscar", lambda cliente, dia, evitar=None: [h])
    verif = wh.Verificacion(True, [{"dato": "d", "fuentes": ["https://a.com", "https://b.com"]}],
                            "SOLO LO VERIFICADO") if verificada else wh.Verificacion(False, motivo="sin fuentes")
    llamados = []
    monkeypatch.setattr(wh, "verificar", lambda c, texto, *a, **k: llamados.append(texto) or verif)
    return llamados


def test_una_historia_de_la_web_sale_solo_con_lo_verificado(monkeypatch, sin_red, tmp_path):
    _web(monkeypatch, del_dia=False)
    p = locales.proponer(None, None, None, None, HOY, tmp_path, puntuador=_Puntuador(9), web=object())
    texto, fuente, contexto = sin_red[-1]
    assert texto == "El cartero de Mompox" and fuente == "SOLO LO VERIFICADO"
    assert ef.NO_ES_DE_HOY in contexto                        # no es de esta fecha: no dice "hoy"
    assert p.local["origen"] == "web" and p.local["verificados"][0]["fuentes"] == ["https://a.com", "https://b.com"]
    assert p.local["fuentes_web"] == ["https://eltiempo.com/x"]


def test_la_del_banco_tambien_se_verifica_y_si_no_pasa_no_sale(monkeypatch, sin_red, tmp_path):
    from tests.test_nunca_sin_video import _item

    llamados = _web(monkeypatch, verificada=False)
    with pytest.raises(ef.SinFotosReales):
        locales.proponer(None, None, None, None, HOY, tmp_path, puntuador=_Puntuador(9), web=object(),
                         banco=[_item(1, 8.7)], piso_alternativo=6.0)
    assert llamados == ["El cartero de Mompox", "historia 1"] and not sin_red   # ningún guion sin verificar
    # la del día no se verifica, la del banco sí: sale la del banco (nunca vacía)
    ok = wh.Verificacion(True, [{"dato": "d", "fuentes": ["https://a.com", "https://b.com"]}], "BANCO VERIFICADO")
    monkeypatch.setattr(wh, "verificar", lambda c, texto, *a, **k:
                        ok if texto == "historia 1" else wh.Verificacion(False, motivo="no"))
    p = locales.proponer(None, None, None, None, HOY, tmp_path, puntuador=_Puntuador(9), web=object(),
                         banco=[_item(1, 8.7)], piso_alternativo=6.0)
    assert p.local["origen"] == "banco" and "banco" in p.local["aviso"] and sin_red[-1][1] == "BANCO VERIFICADO"


def test_sin_busqueda_web_todo_sigue_como_antes(monkeypatch, sin_red, tmp_path):
    from tests.test_nunca_sin_video import _item

    monkeypatch.setattr(wh, "buscar", lambda *a, **k: pytest.fail("buscó en la web"))
    p = locales.proponer(None, None, None, None, HOY, tmp_path, banco=[_item(1, 8.7)], piso_alternativo=6.0)
    assert p.local["origen"] == "banco" and sin_red[-1][1] == "TEXTO DEL ARTÍCULO"


def test_si_la_verificacion_se_cae_la_de_wikipedia_sale_con_aviso(monkeypatch, sin_red, tmp_path):
    from tests.test_nunca_sin_video import _item

    monkeypatch.setattr(wh, "buscar", lambda *a, **k: [])
    monkeypatch.setattr(wh, "verificar", lambda *a, **k: (_ for _ in ()).throw(wh.WebError("caída")))
    p = locales.proponer(None, None, None, None, HOY, tmp_path, web=object(), banco=[_item(1, 8.7)],
                         piso_alternativo=6.0)
    assert "sin verificar" in p.local["aviso"] and sin_red[-1][1] == "TEXTO DEL ARTÍCULO"


# ---- la prueba de un día real ----------------------------------------------------------------------------

class _TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, *a, **k):
        self.mensajes.append(texto)


def _uso(conn, dia, modelo, entrada, salida=0):
    db.anotar_gemini(conn, "web_historias.buscar", modelo, "claude", entrada, salida, False, origen="produccion")
    conn.execute("UPDATE gemini_uso SET dia = ? WHERE rowid = (SELECT MAX(rowid) FROM gemini_uso)", (dia,))
    conn.commit()


@pytest.mark.parametrize("busquedas,queda", [(20, True), (60, False)])
def test_la_prueba_mide_el_dia_y_se_apaga_sola_si_se_pasa(tmp_path, busquedas, queda):
    conn = db.connect(tmp_path / "c.db")
    s = load_settings()
    assert s.historias_fb.web and s.historias_fb.web_tope_usd == 0.45
    _uso(conn, "2026-11-17", wh.HAIKU, 300_000, 20_000)        # US$ 0,04
    _uso(conn, "2026-11-17", wh.MODELO_BUSQUEDA, busquedas)
    tg = _TG()
    m._web_latam_tick(conn, tg, s, ahora=datetime(2026, 11, 17, 23, 0, tzinfo=m.AR))
    assert tg.mensajes == []                                   # el día todavía no terminó
    m._web_latam_tick(conn, tg, s, ahora=datetime(2026, 11, 18, 0, 5, tzinfo=m.AR))
    m._web_latam_tick(conn, tg, s, ahora=datetime(2026, 11, 18, 0, 10, tzinfo=m.AR))
    assert len(tg.mensajes) == 1 and tg.mensajes[0].startswith("🔧 Claude Code:")
    assert f"{busquedas} búsquedas" in tg.mensajes[0]
    assert ("queda andando" in tg.mensajes[0]) == queda
    assert (db.get_valor(conn, m.WEB_APAGADO) is None) == queda
    assert (m._web_latam(conn, s) is None) or queda


def test_costos_del_dia_incluyen_la_busqueda(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    _uso(conn, "2026-11-17", wh.MODELO_BUSQUEDA, 10)
    total, filas = claude.resumen_costo(conn, "2026-11-17")
    assert total == pytest.approx(0.10) and filas[0][0] == "Latinoamérica: buscar en la web (Haiku)"


def test_si_la_respuesta_no_trae_el_json_se_pide_el_formato():
    """Santi, 2026-11-18: 2 de 5 verificaciones se cayeron por "la respuesta no trajo el JSON pedido"."""
    from types import SimpleNamespace

    from clips_bot import web_historias as wh

    class Msgs:
        def create(self, **k):
            assert "tools" not in k
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                                   content=[SimpleNamespace(type="text", text='```json\n{"datos": [], "es_real": true}\n```')])

    cliente = SimpleNamespace(_c=SimpleNamespace(messages=Msgs()), modelo="haiku", uso=None)
    assert wh.json_de(cliente, "verifiqué todo y está bien", wh.SISTEMA_VERIFICAR) == {"datos": [], "es_real": True}
    assert wh.json_de(cliente, '{"a": 1}', wh.SISTEMA_VERIFICAR) == {"a": 1}


def test_sin_acceso_web_es_falla_tecnica():
    """Santi, 2026-11-28: la verificación dijo "no tengo acceso web en esta conversación" y la historia quedó como "no
    verificada": eso es técnico (se reintenta y, si sigue, cuenta como búsqueda caída)."""
    from clips_bot import web_historias as wh
    d = {"problema": "No pude abrir ni leer las URLs citadas porque no tengo acceso web en esta conversación",
         "es_real": False}
    assert wh.sin_acceso(d)
    assert not wh.sin_acceso({"problema": "las fuentes se contradicen en el año", "es_real": False})
    assert wh.es_tecnica(wh.WebError("SIN ACCESO: x"))
