"""Control de calidad de las fotos (70 % reales) y calendario de fechas de Latinoamérica
(pedidos de Santi del 2026-11-11). Sin red: Wikipedia, Claude y Telegram son falsos."""

import json
from datetime import date, datetime

import pytest

from clips_bot import calendario, db
from clips_bot import efemerides as ef
from clips_bot import locales


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


def _foto(i, tarjeta=False):
    return ef.Foto(archivo=f"tarjeta:t{i}" if tarjeta else f"F{i}.jpg", url="", ancho=1000, alto=800,
                   licencia="CC0", autor="x", epigrafe="e", pagina="", articulo="tarjeta" if tarjeta else "A")


def _guion(**kw):
    base = dict(frases=["a"], fotos=[], descartadas=[], titulo="t", descripcion="d", hashtags=[])
    return ef.Guion(**{**base, **kw})


# ---- control de calidad -------------------------------------------------------------------------

def test_fraccion_real_cuenta_el_tiempo_sin_tarjetas():
    pool = [_foto(0), _foto(1, tarjeta=True)]
    assert ef.fraccion_real(pool, [(0, 0, 6.0), (1, 1, 4.0)]) == pytest.approx(0.6)
    assert ef.fraccion_real(pool, [(0, ef.VIDEO, 5.0), (1, 0, 5.0)]) == 1.0     # un video es real
    dicts = [{"articulo": "A", "archivo": "F.jpg"}, {"articulo": "tarjeta", "archivo": "tarjeta:x"}]
    assert ef.fraccion_real(dicts, [(0, 0, 3.0), (1, 1, 7.0)]) == pytest.approx(0.3)   # la Propuesta


def test_el_ejemplo_del_refrigerador_no_pasa():
    # 10/11: ~27 de 37 s con tarjetas «PATENTE»/«HELADERA»
    pool = [_foto(0), _foto(1, tarjeta=True)]
    g = _guion()
    with pytest.raises(ef.FotosInsuficientes) as err:
        ef.control_calidad(pool, g, [(0, 1, 27.0), (1, 0, 10.0)])
    assert "27 %" in str(err.value) and g.fotos_reales == pytest.approx(0.27, abs=0.01)
    assert ef.control_calidad(pool, _guion(), [(0, 0, 8.0), (1, 1, 2.0)]) == pytest.approx(0.8)


def test_la_segunda_busqueda_va_con_claude_y_sin_regla_de_epoca(monkeypatch):
    llamadas = []
    g = _guion()

    def fotos_para_guion(wiki, cliente, e, g_, fotos, carpeta, avisar, elector=None, segunda=False, **k):
        llamadas.append((elector, segunda, k.get("pool")))
        if not segunda:
            raise ef.FotosInsuficientes(["pool"], g_, 0.4)
        return ["pool", "nueva"], g_

    monkeypatch.setattr(ef, "fotos_para_guion", fotos_para_guion)
    pool, _ = ef.fotos_con_control(None, None, None, g, [], None, lambda *_: None,
                                   elector="gemini-o-nada", elector_reintento="claude")
    assert llamadas == [("gemini-o-nada", False, None), ("claude", True, ["pool"])]
    assert pool == ["pool", "nueva"]


def test_si_la_segunda_tampoco_llega_sigue_la_excepcion(monkeypatch):
    def nunca(*a, segunda=False, **k):
        raise ef.FotosInsuficientes([], _guion(), 0.5)

    monkeypatch.setattr(ef, "fotos_para_guion", nunca)
    with pytest.raises(ef.FotosInsuficientes):
        ef.fotos_con_control(None, None, None, _guion(), [], None, lambda *_: None)


def test_segunda_busqueda_sin_epoca_y_con_el_documento_del_hecho():
    g = _guion(frases=["El refrigerador.", "Hoy."], central=[True, False], imagen_frase=True)
    assert ef.sin_epoca(g) == [False, True]
    g.segunda_busqueda = True
    assert ef.sin_epoca(g) == [True, True]
    assert "documento" in ef.TIPOS_DEL_HECHO and "diagrama" in ef.TIPOS_DEL_HECHO


def test_el_respaldo_tambien_tiene_que_pasar_el_70(monkeypatch):
    pocas = ef.PocasFotos([_foto(0), _foto(1, tarjeta=True)], _guion(), 2)
    monkeypatch.setattr(ef, "plan_estimado", lambda g, n: [(0, 1, 8.0), (1, 0, 2.0)])
    assert not ef.respaldo_sirve(pocas)
    monkeypatch.setattr(ef, "plan_estimado", lambda g, n: [(0, 0, 8.0), (1, 1, 2.0)])
    assert ef.respaldo_sirve(pocas)


def test_sin_fotos_reales_no_se_reintenta_solo():
    import clips_bot.__main__ as m
    from clips_bot.config import load_settings

    s = load_settings()
    assert m._con_reintento_pasajero(["07:00", "10:00"], m.ErrorDefinitivo("x"), s, datetime.now(m.AR)) == []
    assert m._con_reintento_pasajero(["07:00"], "otro error", s, datetime.now(m.AR)) == ["07:00"]


def test_el_reintento_va_con_claude_aunque_la_regla_este_apagada(monkeypatch):
    import clips_bot.__main__ as m
    from dataclasses import replace

    from clips_bot import claude
    from clips_bot.config import load_settings

    s = load_settings()
    s = replace(s, efemerides=replace(s.efemerides, imagen_frase=False))
    monkeypatch.setattr(claude, "cliente", lambda modelo, **k: f"claude:{modelo}")
    assert m._elector_fotos(s) is None
    assert m._elector_fotos(s, reintento=True) == f"claude:{s.historias_fb.modelo_texto}"


def test_la_tarjeta_entra_en_el_ancho(tmp_path):
    from PIL import Image

    base = tmp_path / "b.jpg"
    Image.new("RGB", (800, 600), (40, 90, 160)).save(base)
    f = _foto(0)
    f.ruta = str(base)
    t = ef.tarjeta(f, "HELADERA", tmp_path / "t.jpg")
    img = Image.open(t.ruta).convert("L")
    # Las columnas de los bordes (70 px) no tienen texto blanco: la palabra entra con margen.
    bordes = [img.getpixel((x, y)) for x in (5, 60, 1020, 1075) for y in range(0, 1920, 20)]
    assert max(bordes) < 200


# ---- Facebook: el día exacto ---------------------------------------------------------------------

def test_facebook_no_sube_una_historia_de_ayer(conn, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot import facebook
    from clips_bot.config import load_settings

    monkeypatch.setattr(facebook, "subir_reel", lambda *a, **k: pytest.fail("no se sube un día después"))
    meta = {"clip_id": "historia_fb_1110_1907", "salida": "x.mp4",
            "textos": {"titulo": "t", "descripcion": "d", "hashtags": []},
            "efemeride": {"fecha": "2026-11-10", "destino": "facebook"}}
    aviso = m._subir_facebook(conn, load_settings(), meta, ahora=datetime(2026, 11, 11, 9, 0, tzinfo=m.AR),
                              hora="19:00")
    assert "nunca después" in aviso and "10/11" in aviso


# ---- calendario ---------------------------------------------------------------------------------

WIKITEXTO = """== Acontecimientos ==
* [[1907]]: algo.
== Celebraciones ==
* {{MEX}}
** [[Día del Ferrocarrilero]], en homenaje a [[Jesús García Corona]].
* {{USA}}
** Día de algo de afuera.
* {{COL}}
** [[Día del Psicólogo]].
** Por provincias:
=== Santoral católico ===
* San [[Serapión]].
"""


def _fuentes_falsas(monkeypatch, fundaciones=()):
    monkeypatch.setattr(locales, "_wikitexto_dia", lambda wiki, dia: WIKITEXTO)
    monkeypatch.setattr(locales, "leer_anexos",
                        lambda wiki, dia: (["Venezuela: natalicio de Fulano"], set()))
    monkeypatch.setattr(locales, "buscar_fundaciones", lambda wiki, dia: list(fundaciones))


def test_entradas_del_dia_solo_latinoamerica_con_fuente_y_prioridad(monkeypatch):
    fund = locales.Candidato("fundacion", 1541, "Fundación de Santiago: ... ciudad de Chile", ["Santiago de Chile"])
    _fuentes_falsas(monkeypatch, [fund])
    e = calendario.entradas_del_dia(None, date(2026, 11, 7))
    assert [x["pais"] for x in e] == ["México", "Colombia", "Chile", "Venezuela"]
    assert e[0]["fuente"] == "https://es.wikipedia.org/wiki/7_de_noviembre"
    assert "Ferrocarrilero" in e[0]["texto"] and "Jesús García Corona" in e[0]["articulos"]
    assert e[2]["tipo"] == "fundacion" and e[2]["anio"] == 1541
    assert e[2]["fuente"].endswith("Santiago_de_Chile")
    assert not any("afuera" in x["texto"] for x in e)
    assert not any("Serapión" in x["texto"] or x["texto"].endswith(":") for x in e)


def test_una_fundacion_reciente_es_un_barrio_no_va(monkeypatch):
    barrio = locales.Candidato("fundacion", 2009, "Fundación de Paseos del Lago II: México", ["Paseos del Lago II"])
    _fuentes_falsas(monkeypatch, [barrio])
    assert not any(x["tipo"] == "fundacion" for x in calendario.entradas_del_dia(None, date(2026, 11, 15)))


def test_actualizar_de_a_pocos_y_la_semana(conn, monkeypatch):
    _fuentes_falsas(monkeypatch)
    hoy = date(2026, 11, 9)       # lunes
    assert calendario.actualizar(conn, None, hoy, dias=10, max_nuevos=3) == 3
    assert calendario.falta(conn, hoy, 7)
    assert calendario.actualizar(conn, None, hoy, dias=10) == 7
    assert not calendario.falta(conn, hoy, 10)
    assert calendario.actualizar(conn, None, hoy, dias=10) == 0      # ya está todo
    texto = calendario.texto_semana(conn, hoy)
    assert "Lunes 09/11" in texto and "Domingo 15/11" in texto and "🇲🇽 México" in texto
    assert "https://es.wikipedia.org/wiki/9_de_noviembre" in texto


def test_calendario_tick_manda_la_semana_los_lunes_una_vez(conn, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot.config import load_settings

    _fuentes_falsas(monkeypatch)
    monkeypatch.setattr(calendario, "DIAS", 7)
    calendario.actualizar(conn, None, date(2026, 11, 16), dias=7)
    tg = TG()
    s = load_settings()
    m._calendario_tick(conn, tg, s, ahora=datetime(2026, 11, 16, 7, 0, tzinfo=m.AR), wiki=object())
    assert tg.mensajes == []                                    # antes de las 08:00
    m._calendario_tick(conn, tg, s, ahora=datetime(2026, 11, 16, 8, 5, tzinfo=m.AR), wiki=object())
    m._calendario_tick(conn, tg, s, ahora=datetime(2026, 11, 16, 9, 0, tzinfo=m.AR), wiki=object())
    assert len(tg.mensajes) == 1 and tg.mensajes[0][0] == m.DUENO
    assert "Calendario de la semana" in tg.mensajes[0][1]
    m._calendario_tick(conn, tg, s, ahora=datetime(2026, 11, 17, 9, 0, tzinfo=m.AR), wiki=object())
    assert len(tg.mensajes) == 1                                # martes: nada


# ---- historia de Facebook: el calendario primero ---------------------------------------------

def _c(seccion, pais, interes, humana=True, conmemora=""):
    c = locales.Candidato(seccion, 1900, f"{pais} {interes}", [f"A{interes}"])
    c.clasif = {"humana": humana, "lugar": "Pueblo", "pais": pais, "tragedia_sola": False,
                "conmemora": conmemora, "interes": interes}
    return c


def test_el_calendario_va_primero_y_entre_esos_los_paises_con_mas_publico():
    comun = _c("acontecimientos", "Uruguay", 10)
    cal_ar = _c("celebracion", "Argentina", 3)
    cal_mx = _c("acontecimientos", "México", 2, conmemora="Día del Ferrocarrilero")
    fund = _c("fundacion", "Perú", 9, humana=False)      # Haiku: "no es humana"; el calendario manda
    trag = _c("fundacion", "Chile", 9)
    trag.clasif["tragedia_sola"] = True
    assert locales.buenos([comun, cal_ar, cal_mx, fund, trag]) == [cal_mx, cal_ar, fund, comun]


def test_sonnet_no_puede_saltear_el_calendario():
    comun = _c("acontecimientos", "Uruguay", 10)
    cal = _c("celebracion", "México", 3)

    class Sonnet:
        def json(self, sistema, prompt, schema, **k):
            assert "★ CALENDARIO" in prompt and "SIEMPRE primero" in sistema
            return json.dumps({"elegidos": [{"n": 1, "articulo": "A10", "articulo_lugar": "", "motivo": ""},
                                            {"n": 2, "articulo": "A3", "articulo_lugar": "", "motivo": ""}]})

    assert [c for c, *_ in locales.elegir(Sonnet(), [comun, cal])] == [cal, comun]
