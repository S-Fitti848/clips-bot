"""Nunca un día sin video (Santi, 2026-11-15): piso absoluto de 6, bancos de reserva (20, se reponen bajo
10), el mínimo de fotos reales que baja de a 5 puntos del 70 al 50 %, avisos y el chequeo de las 20:00.
Sin red ni Claude."""
import json
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

import pytest

from clips_bot import __main__ as m
from clips_bot import banco, db, locales
from clips_bot import efemerides as ef
from clips_bot.animacion import marcas as mk
from clips_bot.config import load_settings

HOY = date(2026, 11, 20)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "clips.db")
    yield c
    c.close()


# ---- fotos: 70 % → 50 % -----------------------------------------------------------------------

def test_el_minimo_baja_de_a_5_puntos_hasta_50():
    assert ef.umbral_relajado(0.72) == 0.70
    assert ef.umbral_relajado(0.68) == 0.65
    assert ef.umbral_relajado(0.61) == 0.60
    assert ef.umbral_relajado(0.50) == 0.50
    assert ef.umbral_relajado(0.49) is None


def test_con_la_voz_real_debajo_de_50_no_se_arma_y_entre_50_y_70_avisa():
    g = ef.Guion(frases=["a"], fotos=[0], descartadas=[], titulo="t", descripcion="d", hashtags=[])
    ef._control_real(g, 0.80)
    assert not g.umbral_fotos and ef.aviso_fotos(g) == ""
    ef._control_real(g, 0.57)
    assert g.umbral_fotos == 0.55 and "57 %" in ef.aviso_fotos(g) and "55 %" in ef.aviso_fotos(g)
    with pytest.raises(ef.SinFotosReales):
        ef._control_real(g, 0.45)


def test_aceptar_relajado_marca_el_guion():
    g = ef.Guion(frases=["a"], fotos=[0], descartadas=[], titulo="t", descripcion="d", hashtags=[])
    err = ef.FotosInsuficientes([], g, 0.63)
    assert ef.aceptar_relajado(err, lambda *_: None)
    assert g.umbral_fotos == 0.60 and g.fotos_reales == 0.63
    assert not ef.aceptar_relajado(ef.FotosInsuficientes([], g, 0.30), lambda *_: None)


def test_la_segunda_busqueda_va_en_dos_idiomas_con_la_epoca_y_los_archivos():
    class W:
        def en_espanol(self, t):
            return "Cohete Saturno V"

    qs = ef.consultas_segunda(W(), ef.Evento("en", 1967, "x", ["Saturn_V", "Wernher_von_Braun"]))
    assert "Saturn V" in qs and "Saturn V 1960s" in qs and "Cohete Saturno V" in qs
    assert any("incategory:" in q and "Archivo General de la Nación Argentina" in q for q in qs)


# ---- bancos ---------------------------------------------------------------------------------

def _item(i, p=8.5):
    return {"id": f"latam:Art_{i}", "texto": f"historia {i}", "anio": 1900 + i, "paginas": [f"Art_{i}"],
            "articulo": f"Art_{i}", "articulo_lugar": "", "puntaje": p,
            "clasif": {"lugar": "Cusco", "pais": "Perú", "tipo": "lugar_curioso"}}


def test_el_banco_solo_guarda_de_8_o_mas_sin_repetir_y_saca_lo_usado(conn):
    assert banco.agregar(conn, "latam", [_item(1), _item(1), _item(2, 7.9), _item(3)]) == 2
    assert [x["id"] for x in banco.leer(conn, "latam")] == ["latam:Art_1", "latam:Art_3"]
    banco.sacar(conn, "latam", "latam:Art_1")
    assert [x["id"] for x in banco.leer(conn, "latam")] == ["latam:Art_3"]


def test_se_repone_debajo_de_10_y_llena_hasta_20(conn):
    assert banco.hay_que_reponer(conn, "latam")            # vacío: arranca
    banco.agregar(conn, "latam", [_item(i) for i in range(12)])
    assert banco.hay_que_reponer(conn, "latam")            # 12: sigue hasta 20
    banco.agregar(conn, "latam", [_item(i) for i in range(12, 20)])
    assert not banco.hay_que_reponer(conn, "latam")        # 20: para
    banco.guardar(conn, "latam", banco.leer(conn, "latam")[:11])
    assert not banco.hay_que_reponer(conn, "latam")        # 11: todavía no
    banco.guardar(conn, "latam", banco.leer(conn, "latam")[:9])
    assert banco.hay_que_reponer(conn, "latam")            # 9: vuelve a llenar


def test_cosecha_dias_lejos_de_hoy_y_de_a_uno(conn):
    d1 = banco.proximo_dia(conn, "latam", HOY)
    d2 = banco.proximo_dia(conn, "latam", HOY)
    assert d1 == HOY + timedelta(days=banco.LEJOS_DIAS) and d2 == d1 + timedelta(days=1)


def test_de_banco_saca_lo_ya_usado_y_ordena_por_puntaje():
    out = locales.de_banco([_item(1, 8.2), _item(2, 9.1), _item(3, 8.5)], excluir={"historia 3"})
    assert [c.texto for c, _, _ in out] == ["historia 2", "historia 1"]
    c, art, _ = out[0]
    assert c.clasif["banco_id"] == "latam:Art_2" and art == "Art_2"
    assert locales.local_de(c, "📦 del banco")["banco_id"] == "latam:Art_2"


# ---- Latinoamérica: la primera del día sale siempre -------------------------------------------

def test_la_primera_del_dia_tiene_piso_6_y_banco_la_segunda_no(conn):
    banco.agregar(conn, "latam", [_item(1)])
    p = m._piso_latam(conn, HOY)
    assert p["piso_alternativo"] == 6.0 and len(p["banco"]) == 1
    db.set_valor(conn, f"{m.PH_LATAM}:{HOY.isoformat()}", json.dumps([{"texto": "x", "puntaje": 8.5}]))
    assert m._piso_latam(conn, HOY) == {"piso_alternativo": locales.PISO_UNA_POR_DIA}
    db.set_valor(conn, f"{m.PH_LATAM}:{HOY.isoformat()}", json.dumps([{"texto": "x", "puntaje": 6.2}]))
    assert m._piso_latam(conn, HOY) == {"piso_alternativo": None}
    assert m._piso_latam(conn, HOY, hecho="Epecuén") == {}


# ---- Así Nació ------------------------------------------------------------------------------

class Wiki:
    def texto(self, lang, titulo):
        return "texto del artículo"


class Cliente:
    def __init__(self, nota):
        self.nota = nota

    def json(self, sistema, prompt, schema, temperatura=0.7, **kw):
        n = self.nota
        return json.dumps({"candidatos": [{"indice": 0, "dato": "d", "marca_conocida": n, "dato_sorprendente": n,
                                            "giro": n, "humor": n, "sensible": False}]})


def _marca(nombre="Havanna"):
    return mk.Marca(nombre, "Argentina", "golosinas", nombre, ("origen", "nombre"))


@pytest.fixture
def sin_guion(monkeypatch):
    monkeypatch.setattr(mk, "escribir_guion", lambda *a, **k: {"titulo": "ok"})


def test_asinacio_en_el_ultimo_intento_sale_la_mejor_si_tiene_6(conn, sin_guion):
    e, d, _ = mk.proponer(conn, Cliente(6), Wiki(), HOY, [_marca()], n=1, ultimo=True)
    assert e.marca.nombre == "Havanna" and "6,0" in e.aviso and "mínimo 8" in e.aviso
    # antes del último intento, no: se reintenta con otras
    with pytest.raises(mk.GuionesFallidos):
        mk.proponer(conn, Cliente(6), Wiki(), HOY, [_marca("Arcor")], n=1)


def test_asinacio_debajo_de_6_usa_el_banco(conn, sin_guion):
    cat = [_marca("Havanna"), _marca("Arcor")]
    item = {"id": "Arcor/origen", "marca": "Arcor", "angulo": "origen", "puntaje": 8.5,
            "notas": {"marca_conocida": 9, "dato_sorprendente": 8, "giro": 8, "humor": 9}}
    e, _, _ = mk.proponer(conn, Cliente(5), Wiki(), HOY, cat, n=1, ultimo=True, banco=[item])
    assert e.marca.nombre == "Arcor" and e.banco_id == "Arcor/origen" and "banco" in e.aviso


def test_asinacio_sin_candidatos_usa_el_banco(conn, sin_guion):
    for a in ("origen", "nombre"):
        mk.registrar(conn, "Havanna", a, HOY - timedelta(days=30))
    cat = [_marca("Havanna"), _marca("Arcor")]
    mk.registrar(conn, "Arcor", "nombre", HOY - timedelta(days=30))
    mk.registrar(conn, "Arcor", "origen", HOY - timedelta(days=1))   # Arcor tampoco: salió ayer
    item = {"id": "Arcor/origen", "marca": "Arcor", "angulo": "origen", "puntaje": 8.5, "notas": {}}
    with pytest.raises(mk.SinCandidato):          # el del banco ya no está libre en la rotación
        mk.proponer(conn, Cliente(9), Wiki(), HOY, cat, n=1, banco=[item])


# ---- el aviso de las 20:00 y la reposición ---------------------------------------------------

class Tg:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, *a, **k):
        self.mensajes.append((chat, texto))


def _ahora(hhmm, dia=HOY):
    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(dia.year, dia.month, dia.day, h, mi, tzinfo=m.AR)


def test_a_las_2000_avisa_los_canales_sin_video_una_vez(conn):
    s = load_settings()
    tg = Tg()
    cuando = _ahora("13:00").astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.crear_subida(conn, "efemeride_x", "pequena_historia", "programada", video_id="v", publish_at=cuando)
    m._sin_video_tick(conn, tg, s, _ahora("19:59"))
    assert not tg.mensajes
    m._sin_video_tick(conn, tg, s, _ahora("20:00"))
    assert len(tg.mensajes) == 1
    texto = tg.mensajes[0][1]
    assert "Pequeña Historia (YouTube)" not in texto and "Así Nació (YouTube)" in texto
    m._sin_video_tick(conn, tg, s, _ahora("21:00"))
    assert len(tg.mensajes) == 1


def test_sin_faltantes_no_avisa(conn):
    s = load_settings()
    tg = Tg()
    cuando = _ahora("13:00").astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for canal in m.canales_del_dia(s):
        db.crear_subida(conn, "x", canal, "programada", video_id="v", publish_at=cuando)
    m._sin_video_tick(conn, tg, s, _ahora("20:05"))
    assert not tg.mensajes


def test_la_reposicion_va_al_banco_mas_vacio_en_su_horario(conn, monkeypatch):
    s = load_settings()
    corridos = []
    monkeypatch.setattr(banco, "paso", lambda c, canal, *a, **k: corridos.append(canal))
    monkeypatch.setattr(m, "_claude_textos", lambda st: (object(), object()))
    monkeypatch.setattr(m, "_puntuador", lambda st: object())
    monkeypatch.setattr(m, "DB_PATH", Path(conn.execute("PRAGMA database_list").fetchone()[2]))
    banco.agregar(conn, "latam", [_item(i) for i in range(5)])
    banco.agregar(conn, "tecnologia", [dict(_item(i), id=f"tec:{i}") for i in range(3)])
    m._bancos_tick(conn, Tg(), s, _ahora("05:00"), correr=lambda f: f())
    assert corridos == []                                    # de madrugada, no
    m._bancos_tick(conn, Tg(), s, _ahora("10:00"), correr=lambda f: f())
    assert corridos == ["asinacio"]                          # el más vacío (0)


# ---- tecnología -----------------------------------------------------------------------------

class WikiTec:
    def eventos(self, lang, dia):
        return [ef.Evento("es", 1990, "Se lanza un producto de tecnología", ["Producto_X"])] if lang == "es" else []


@pytest.fixture
def tec_sin_red(monkeypatch, tmp_path):
    usados = []
    monkeypatch.setattr(ef, "fotos_del_evento", lambda wiki, e: ([], {}))
    monkeypatch.setattr(ef, "texto_fuente", lambda wiki, e: "texto")

    def guion(cliente, e, fuente, *a, contexto="", **k):
        usados.append((e.paginas[0], contexto))
        return ef.Guion(frases=["a"], fotos=[0], descartadas=[], titulo="t", descripcion="d", hashtags=[])

    monkeypatch.setattr(ef, "escribir_guion", guion)
    monkeypatch.setattr(ef, "fotos_con_control", lambda wiki, cl, e, g, *a, **k: ([], g))
    return usados


def _nota_tec(n):
    class C:
        def json(self, *a, **k):
            return json.dumps({"elegidos": [{"indice": 1, "articulo": "Producto_X", "marca": n, "sorpresa": n,
                                             "consecuencia": n, "final": n}]})
    return C()


ITEM_TEC = {"id": "tec:Netscape", "lang": "es", "anio": 1997, "texto": "Netscape", "paginas": ["Netscape"],
            "articulo": "Netscape", "puntaje": 9.0, "notas": {"marca": 9}}


def test_tecnologia_con_6_sale_con_aviso(tec_sin_red, tmp_path):
    p = ef.proponer(WikiTec(), _nota_tec(6), HOY, tmp_path, tema="tecnologia", piso=6.0, banco=[ITEM_TEC])
    assert p.evento["paginas"][0] == "Producto_X" and "6,0" in p.local["aviso"]


def test_tecnologia_debajo_de_6_va_al_banco_sin_decir_hoy(tec_sin_red, tmp_path):
    p = ef.proponer(WikiTec(), _nota_tec(5), HOY, tmp_path, tema="tecnologia", piso=6.0, banco=[ITEM_TEC])
    assert p.local["banco_id"] == "tec:Netscape" and "banco" in p.local["aviso"]
    assert tec_sin_red[-1] == ("Netscape", ef.NO_ES_DE_HOY)


def test_tecnologia_sin_banco_no_sale(tec_sin_red, tmp_path):
    with pytest.raises(ef.SinTema):
        ef.proponer(WikiTec(), _nota_tec(5), HOY, tmp_path, tema="tecnologia", piso=6.0, banco=[])


def test_latam_sin_candidatas_usa_el_banco(monkeypatch, tmp_path, tec_sin_red):
    monkeypatch.setattr(locales, "leer_todo", lambda wiki, dia, avisar: ([], [], set()))
    p = locales.proponer(None, None, None, None, HOY, tmp_path, banco=[_item(1, 8.7)], piso_alternativo=6.0)
    assert p.local["banco_id"] == "latam:Art_1" and "banco" in p.local["aviso"]
    assert ef.NO_ES_DE_HOY in tec_sin_red[-1][1]
    with pytest.raises(ef.NarrarError):
        locales.proponer(None, None, None, None, HOY, tmp_path, banco=[], piso_alternativo=6.0)


# ---- voz falsa en las pruebas (Santi, 2026-11-15) ---------------------------------------------

def test_en_una_prueba_la_voz_es_falsa_y_en_produccion_real(monkeypatch):
    from clips_bot import gemini as gm

    monkeypatch.delenv("CLIPS_VOZ_REAL", raising=False)
    assert gm.ORIGEN == gm.PRUEBA and ef.voz_falsa()
    with gm.origen(gm.PRODUCCION):
        assert not ef.voz_falsa()
    with gm.origen(gm.A_MANO):          # ✅ en Telegram arma el video que se publica
        assert not ef.voz_falsa()
    monkeypatch.setenv("CLIPS_VOZ_REAL", "1")
    assert not ef.voz_falsa()


def test_la_voz_de_prueba_no_llama_a_gemini(monkeypatch, tmp_path):
    import wave
    from dataclasses import replace

    monkeypatch.delenv("CLIPS_VOZ_REAL", raising=False)
    s = load_settings()
    s = replace(s, voz=replace(s.voz, modelo=str(tmp_path / "no_existe.onnx")))

    def tts(*a, **k):
        raise AssertionError("una prueba no puede gastar una voz de Gemini")

    wav, dur, motor = ef.voz_efemeride(["Una frase de cinco palabras.", "Otra más."], s, tmp_path, tts=tts)
    assert motor == "falsa:silencio" and len(dur) == 2 and "PRUEBA" in ef.texto_voz(motor)
    with wave.open(str(wav)) as w:
        assert abs(w.getnframes() / w.getframerate() - sum(dur)) < 0.01
