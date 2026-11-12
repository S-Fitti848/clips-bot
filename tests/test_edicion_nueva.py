"""Edición nueva (propuesta aprobada por Santi el 2026-11-10), todo APAGADO hasta que apruebe los
ejemplos: Rots sin silencios con texto de contexto, karaoke y pregunta; Pequeña Historia con la
imagen = lo que se dice; la historia de Facebook en formato corto."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

import clips_bot.__main__ as m
from clips_bot import edicion as ed
from clips_bot import efemerides as ef
from clips_bot import locales
from clips_bot import subtitles as sub
from clips_bot import textos as tx
from clips_bot.config import load_settings
from clips_bot.layout import layout_fit_blur
from clips_bot.render import filtro

P = sub.Palabra


def _habla(desde: float, n: int, paso: float = 0.4, texto: str = "bla") -> list[P]:
    return [P(round(desde + k * paso, 2), round(desde + k * paso + 0.3, 2), texto) for k in range(n)]


def test_interruptores_en_los_timers():
    s = load_settings()
    assert s.render.edicion_rots is True          # Rots: aprobado por Santi el 2026-11-10
    assert s.efemerides.imagen_frase is True       # prendidos por Santi el 2026-11-12
    assert s.historias_fb.formato_corto is True


# ---- Rots: recorte -------------------------------------------------------------------------

def test_saca_principio_final_y_pausas_largas():
    palabras = _habla(3.0, 20) + _habla(14.0, 20) + _habla(25.0, 15)   # pausas de ~3 s
    tr = ed.tramos_a_dejar(palabras, 40.0, [1.0] * 80, 0.5)
    assert len(tr) == 3
    assert tr[0][0] == pytest.approx(2.85)            # el principio muerto, afuera
    assert tr[-1][1] < 40.0                            # el final muerto, afuera
    assert ed.MIN_S <= sum(b - a for a, b in tr) <= ed.MAX_S


def test_una_pausa_con_ruido_fuerte_no_se_corta():
    palabras = _habla(0.5, 20) + _habla(11.0, 20)      # pausa de 8,5 a 11 s
    rms = [1.0] * 60
    for k in range(18, 21):                            # una risa sin palabras en la pausa
        rms[k] = 5.0
    tr = ed.tramos_a_dejar(palabras, 30.0, rms, 0.5)
    assert len(tr) == 1


def test_si_sacando_pausas_queda_corto_solo_recorta_las_puntas():
    palabras = _habla(2.0, 10) + _habla(12.0, 10) + _habla(20.0, 5)
    tr = ed.tramos_a_dejar(palabras, 26.0, [1.0] * 60, 0.5)
    assert len(tr) == 1 and tr[0][1] - tr[0][0] >= ed.MIN_S


def test_mas_largo_que_el_tope_se_queda_con_el_remate():
    palabras = _habla(0.0, 30) + _habla(14.0, 30) + _habla(28.0, 30) + _habla(42.0, 30)
    rms = [1.0] * 120
    rms[100] = 9.0                                      # el pico, en el último bloque (50 s)
    tr = ed.tramos_a_dejar(palabras, 58.0, rms, 0.5)
    total = sum(b - a for a, b in tr)
    assert total <= ed.MAX_S and tr[0][0] <= 50.25 <= tr[-1][1]


def test_mapear_pasa_las_palabras_al_video_cortado():
    palabras = [P(1.0, 1.3, "uno"), P(5.0, 5.3, "dos"), P(9.0, 9.3, "tres")]
    tr = [(0.85, 1.45), (4.85, 5.45)]
    out = ed.mapear(palabras, tr)
    assert [w.texto for w in out] == ["uno", "dos"]
    assert out[1].inicio == pytest.approx(0.6 + 0.15)


def test_risas():
    palabras = [P(1, 1.2, "jajaja"), P(2, 2.2, "hola"), P(3, 3.2, "JSJS"), P(4, 4.2, "jamás")]
    assert ed.risas(palabras) == [1.1, 3.1]


# ---- Rots: textos ----------------------------------------------------------------------------

BASE = {"titulo": "Auron pierde todo", "descripcion": "Auron juega.", "hashtags": ["#Shorts", "#auron", "#mc"],
        "gancho": "reaccion", "depende_de_fecha": False, "sensible": False, "momento": "se cae al vacío y grita",
        "puntaje": 8}


def test_frase_inicio_y_pregunta_se_validan():
    cfg = load_settings().textos
    assert tx.validar({**BASE, "frase_inicio": "Auron no esperaba esto", "pregunta": "¿Vos qué hacías?"},
                      cfg) == []
    errores = tx.validar({**BASE, "frase_inicio": "esto es una frase de muchas palabras de más",
                          "pregunta": "Vos qué hacías"}, cfg)
    assert any("frase_inicio" in e for e in errores) and any("pregunta" in e for e in errores)
    assert tx.validar(BASE, cfg) == []        # respuestas viejas, sin los campos nuevos


def test_la_pregunta_va_en_la_descripcion_solo_con_la_edicion():
    meta = {"streamer": "auronplay", "plataforma": "twitch", "categoria": "Minecraft",
            "textos": {"descripcion": "Auron juega.\n\nClip de Auron — twitch.tv/auronplay",
                       "credito": "Clip de Auron — twitch.tv/auronplay", "pregunta": "¿Vos qué hacías?"}}
    assert "¿Vos" not in tx.descripcion_youtube(meta)
    d = tx.descripcion_youtube({**meta, "edicion": True})
    assert d.startswith("¿Vos qué hacías?\n\nAuron juega.") and d.endswith("twitch.tv/auronplay")
    assert "#Shorts #auronplay #twitch #minecraft" in d


def test_karaoke_resalta_la_palabra_que_suena():
    w = [P(0.0, 0.3, "Hola"), P(0.35, 0.6, "che,"), P(0.7, 1.0, "mirá")]
    ev = sub.eventos_karaoke(w, sub.KARAOKE_ROTS)
    assert len(ev) == 3
    assert "{\\c&H0000E5FF&\\fscx112\\fscy112}HOLA{\\r} CHE," in ev[0]
    assert "HOLA {\\c&H0000E5FF&" in ev[1]
    assert "MIRÁ" in ev[2] and "HOLA" not in ev[2]           # "che," cierra el grupo


def test_render_congela_el_final_para_la_pregunta():
    s = load_settings()
    lay = layout_fit_blur(1920, 1080, s.render)
    assert "tpad=stop_mode=clone:stop_duration=2.00" in filtro(lay, s.render, True, True, 2.0)
    assert "tpad" not in filtro(lay, s.render, True, True)


def test_un_momento_que_otro_subio_baja_con_la_edicion():
    s = load_settings()
    sin = replace(s, render=replace(s.render, edicion_rots=False))
    assert m._factor_pego(sin) == s.pego.peso
    con = replace(s, render=replace(s.render, edicion_rots=True))
    assert m._factor_pego(con) == s.pego.peso_copiado < 1


# ---- Pequeña Historia ------------------------------------------------------------------------

def _guion(**kw):
    base = dict(frases=["a"], fotos=[], descartadas=[], titulo="t", descripcion="d", hashtags=[])
    return ef.Guion(**{**base, **kw})


def test_plan_rapido_corta_cada_2_5_a_4_s_con_las_fotos_de_la_frase():
    g = _guion(frases=["uno", "dos"], ranking=[[0, 3], [1]])
    plan, movs = ef.plan_rapido([(0, 0, 6.0), (1, 1, 3.0), (1, 2, 1.2)], g)
    assert ef.CORTE_MIN_S == 2.5 and ef.CORTE_MAX_S == 4.0
    assert all(s <= ef.CORTE_MAX_S for *_, s in plan)
    assert all(s >= ef.CORTE_MIN_S for i, f, s in plan if i == 0)
    assert [f for i, f, _ in plan if i == 0] == [0, 3]             # alterna entre SUS fotos
    assert sum(s for *_, s in plan) == pytest.approx(10.2)
    for (a, b), (ma, mb) in zip(zip(plan, plan[1:]), zip(movs, movs[1:])):
        assert not (a[1] == b[1] and ma == mb)                      # misma foto, otro movimiento


def test_plan_rapido_ninguna_foto_mas_de_2_veces():
    # una frase larga con dos fotos: A B A B A… pasaría los 2 cortes por foto (Santi, 2026-11-11:
    # cada corte cuenta, aunque sea la misma foto con otro movimiento) → tarjetas.
    g = _guion(frases=["uno"], ranking=[[0, 1]])
    hechas = iter(range(10, 20))
    plan, movs = ef.plan_rapido([(0, 0, 18.0)], g, nueva_tarjeta=lambda i: next(hechas))
    veces = {}
    for _, f, _s in plan:
        veces[f] = veces.get(f, 0) + 1
    assert max(veces.values()) <= 2
    assert len(plan) >= 5 and sum(s for *_, s in plan) == pytest.approx(18.0)
    faltas = []
    ef.plan_rapido([(0, 0, 18.0)], g, faltas=faltas)     # sin tarjetas: queda anotado
    assert faltas


def test_sin_tarjeta_con_un_texto_que_no_tiene_que_ver():
    g = _guion(frases=["Ese año salió Pokémon Escarlata.", "Y vendió millones."], claves=["Pokémon"])
    assert ef.texto_tarjeta(g, 0, 2022, solo_clave=True) == "POKÉMON"
    assert ef.texto_tarjeta(g, 1, 2022, solo_clave=True) is None      # nada de "2022" suelto
    assert ef.texto_tarjeta(g, 1, 2022) == "2022"                      # sin la regla, como antes


def test_central_y_al_pasar():
    g = _guion(frases=["El pueblo se inundó.", "Como un muro de agua.", "Hoy es un museo."],
               central=[True, False, True], presente=[False, False, True], imagen_frase=True)
    assert [ef.es_central(g, i) for i in range(3)] == [True, False, True]
    assert ef.sin_epoca(g) == [False, True, True]       # al pasar: sin regla de época
    assert ef.sin_epoca(replace(g, imagen_frase=False)) == [False, False, True]
    viejo = _guion(frases=["a"])                        # guiones sin el dato: central
    assert ef.es_central(viejo, 0)


def _d(frases):
    return {"frases": [{"texto": t, "mostrar": "1907 Nacozari Sonora train", "presente": False}
                       for t in frases],
            "idea_clave": "x", "titulo": "Nacozari", "descripcion": "d",
            "hashtags": ["#Shorts", "#Nacozari", "#Mexico"]}


def test_guion_corto_gancho_primero_y_fecha_en_la_segunda():
    fuente = "En 1907 en Nacozari un maquinista llevó un tren con dinamita lejos del pueblo"
    bien = _d(["¡Un maquinista llevó un tren en llamas lejos de su pueblo!",
               "En 1907, en Nacozari, un tren cargaba dinamita."] + ["Y el pueblo se salvó?"] * 6)
    errores = ef.validar_guion(bien, 1907, fuente, corto=True)
    assert not any("primera" in e or "segunda" in e for e in errores)
    viejo = _d(["Un día como hoy, en 1907, en Nacozari, un tren cargaba dinamita."] * 8)
    errores = ef.validar_guion(viejo, 1907, fuente, corto=True)
    assert any("GANCHO" in e for e in errores) and any("segunda" in e for e in errores)
    assert not any("palabras" in e for e in ef.validar_guion(bien, 1907, fuente, corto=True)
                   if "mínimo" in e and "70" in e)


def test_el_lugar_en_la_segunda_frase_del_corto():
    v = locales.validar_lugar("Nacozari", corto=True)
    d = _d(["¡Un tren en llamas!", "En 1907, en Nacozari, pasó esto."])
    assert not any("lugar" in e for e in v(d))
    assert "20 a 30 segundos" in locales.SISTEMA_GUION_CORTO


class _Gemini:
    modelo = None

    def __init__(self, respuesta):
        self.r = respuesta

    def json(self, *a, **k):
        return json.dumps(self.r)


def _foto(tmp_path: Path, n: int, articulo: str) -> ef.Foto:
    from PIL import Image

    ruta = tmp_path / f"f{n}.jpg"
    Image.new("RGB", (64, 48), (n * 40, 90, 120)).save(ruta)
    return ef.Foto(archivo=f"File:{n}.jpg", url="", ancho=1280, alto=960, licencia="CC0", autor="x",
                   epigrafe=f"foto {n}", pagina="", articulo=articulo, ruta=str(ruta))


def test_pexels_en_el_pasado_solo_si_gemini_confirma_que_no_hay_nada_fuera_de_epoca(tmp_path):
    pool = [_foto(tmp_path, 0, "Commons: 1907 Nacozari"), _foto(tmp_path, 1, "pexels: steam train"),
            _foto(tmp_path, 2, "pexels: old station")]
    g = _guion(frases=["El tren salió."], mostrar=["1907 train"], presente=[False], imagen_frase=True)
    tipos = [{"foto": 1, "tipo": "foto", "otro_idioma": False, "anacronismo": False},
             {"foto": 2, "tipo": "foto", "otro_idioma": False, "anacronismo": True},
             {"foto": 3, "tipo": "foto", "otro_idioma": False, "anacronismo": False}]
    r = {"frases": [{"se_ve": "tren", "fotos": [2, 3, 1], "de_epoca": True, "seguro": True,
                     "contradice": False}], "descartadas": [], "tipos": tipos}
    rankings, _ = ef.elegir_fotos(_Gemini(r), g, pool, [[0, 1, 2]], avisar=lambda *_: None, anio=1907)
    assert rankings == [[2, 0]]          # el de Pexels con algo moderno, afuera; el otro queda
    hoy = _guion(frases=["Hoy el tren está en un museo."], mostrar=["train museum"], presente=[True],
                 imagen_frase=True)
    rankings, _ = ef.elegir_fotos(_Gemini(r), hoy, pool, [[0, 1, 2]], avisar=lambda *_: None, anio=1907)
    assert rankings[0][0] == 1           # en una frase de hoy, el stock moderno sirve


def test_el_orden_de_preferencia_va_en_el_pedido_solo_con_la_regla(tmp_path):
    pool = [_foto(tmp_path, 0, "Commons (objeto): train"), _foto(tmp_path, 1, "pexels: train")]
    pedidos = []

    class G(_Gemini):
        def json(self, sistema, prompt, *a, **k):
            pedidos.append(prompt)
            return super().json()

    r = {"frases": [{"se_ve": "tren", "fotos": [1], "de_epoca": True, "seguro": True, "contradice": False}],
         "descartadas": [], "tipos": []}
    g = _guion(frases=["El tren."], mostrar=["1907 train"], presente=[False], imagen_frase=True)
    ef.elegir_fotos(G(r), g, pool, [[0, 1]], avisar=lambda *_: None, anio=1907)
    ef.elegir_fotos(G(r), replace(g, imagen_frase=False), pool, [[0, 1]], avisar=lambda *_: None, anio=1907)
    assert "REGLAS DE SANTI" in pedidos[0] and "foto de stock del objeto" in pedidos[0]
    assert "foto del objeto" in pedidos[0] and "(CENTRAL" in pedidos[0]
    assert "REGLAS DE SANTI" not in pedidos[1]


def test_al_pasar_el_prompt_dice_que_sirve_una_generica(tmp_path):
    pool = [_foto(tmp_path, 0, "pexels: pikachu")]
    pedidos = []

    class G(_Gemini):
        def json(self, sistema, prompt, *a, **k):
            pedidos.append(prompt)
            return super().json()

    r = {"frases": [{"se_ve": "Pikachu", "fotos": [1], "de_epoca": False, "seguro": True, "contradice": False}],
         "descartadas": [], "tipos": [{"foto": 1, "tipo": "foto", "otro_idioma": False, "anacronismo": True}]}
    g = _guion(frases=["Ese año salió Pokémon."], mostrar=["2022 Pokemon game"], presente=[False],
               central=[False], objeto=["Pikachu toy"], imagen_frase=True)
    rankings, _ = ef.elegir_fotos(G(r), g, pool, [[0]], avisar=lambda *_: None, anio=1950)
    assert "AL PASAR" in pedidos[0] and "Pikachu toy" in pedidos[0]
    assert rankings == [[0]]       # al pasar: ni la época ni el anacronismo la sacan


def test_claude_elige_y_gemini_queda_de_respaldo(tmp_path):
    from clips_bot.claude import ClaudeError

    pool = [_foto(tmp_path, 0, "Commons: 1907 train")]
    r = {"frases": [{"se_ve": "tren", "fotos": [1], "de_epoca": True, "seguro": True, "contradice": False}],
         "descartadas": [], "tipos": []}
    usados = []

    class Claude:
        def __init__(self, falla):
            self.falla = falla

        def json(self, sistema, prompt, schema, imagenes=None, **k):
            usados.append(("claude", len(imagenes or [])))
            if self.falla:
                raise ClaudeError("caído", pasajero=True)
            return json.dumps(r)

    class G(_Gemini):
        def json(self, *a, **k):
            usados.append(("gemini", len(k.get("imagenes") or [])))
            return super().json()

    g = _guion(frases=["El tren."], mostrar=["1907 train"], presente=[False], imagen_frase=True)
    ef.elegir_fotos(G(r), g, pool, [[0]], avisar=lambda *_: None, anio=1907, elector=Claude(False))
    assert usados == [("claude", 1)]
    usados.clear()
    ef.elegir_fotos(G(r), g, pool, [[0]], avisar=lambda *_: None, anio=1907, elector=Claude(True))
    assert usados == [("claude", 1), ("gemini", 1)]


def test_claude_recibe_las_imagenes_antes_del_texto():
    from types import SimpleNamespace

    from clips_bot.claude import ClaudeClient

    pedidos = []

    class Mensajes:
        def create(self, **k):
            pedidos.append(k)
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5), model=k["model"],
                                   stop_reason="end_turn", content=[SimpleNamespace(type="text", text="{}")])

    falso = SimpleNamespace(messages=Mensajes(), beta=SimpleNamespace(messages=Mensajes()))
    c = ClaudeClient("x", cliente=falso)
    c.json("sis", "elegí", {"type": "OBJECT", "properties": {}}, imagenes=[b"\xff\xd8a", b"\xff\xd8b"])
    contenido = pedidos[0]["messages"][0]["content"]
    assert [b["type"] for b in contenido] == ["image", "image", "text"]
    assert contenido[0]["source"]["media_type"] == "image/jpeg"


def test_el_elector_va_solo_con_la_regla_prendida():
    s = load_settings()
    assert m._elector_fotos(replace(s, efemerides=replace(s.efemerides, imagen_frase=False))) is None
