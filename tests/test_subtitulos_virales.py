"""Subtítulos virales de Así Nació (Santi, 2026-11-14): 1-3 palabras, Montserrat Black como caminos, pop al
empezar cada palabra, claves en color, temblor en el impacto, emoji (máx. uno cada 4,5 s) y todo en la franja."""
import json
import re
import xml.dom.minidom

from clips_bot.animacion import acciones as ac
from clips_bot.animacion import letra
from clips_bot.animacion import marcas as mk
from clips_bot.animacion import subtitulos_virales as sv
from clips_bot.animacion import texto as tx
from clips_bot.animacion.timeline import Video


def _svg(s: str) -> None:
    xml.dom.minidom.parseString(f'<svg xmlns="http://www.w3.org/2000/svg">{s}</svg>')


def _palabras(texto: str, t0: float = 0.0, paso: float = 0.3):
    return [tx.Palabra(w, t0 + i * paso, t0 + (i + 1) * paso) for i, w in enumerate(texto.split())]


def test_fuente_montserrat_black_con_licencia():
    assert letra.TTF.is_file() and (letra.TTF.parent / "OFL.txt").is_file()
    assert "SIL Open Font License" in (letra.TTF.parent / "OFL.txt").read_text(encoding="utf-8")
    g = letra.glifos()
    assert "Montserrat Black" in g["fuente"]
    assert all(c in g["glifos"] for c in "ÁÉÍÓÚÑ¿?¡!0123456789")
    assert letra.ancho("MM", 100) > letra.ancho("II", 100) > 0
    d = letra.camino("HOLA", 80)
    assert d.startswith("M") and "<" not in d


def test_grupos_de_1_a_3_palabras():
    ps = _palabras("En mil novecientos sesenta y nueve un inventor de Minnesota tuvo una idea genial.")
    ps[3].clave = True
    grupos = sv.agrupar(ps)
    assert all(1 <= len(g) <= 3 for g in grupos)
    assert sum(len(g) for g in grupos) == len(ps)
    assert all(sum(len(p.texto) for p in g) + len(g) - 1 <= sv.MAX_LETRAS or len(g) == 1 for g in grupos)


def test_pop_arranca_justo_con_la_voz():
    ps = _palabras("Nerf nació así", t0=1.0)
    grupos = sv.agrupar(ps)
    assert sv.subtitulo(grupos, 0.9) == ""                       # antes de que la voz arranque, nada
    s0 = sv.subtitulo(grupos, 1.01)
    s1 = sv.subtitulo(grupos, 1.05)
    s2 = sv.subtitulo(grupos, 1.32)                              # la segunda palabra recién entra
    _svg(s0)
    _svg(s2)
    esc = [float(x) for x in re.findall(r"scale\(([0-9.]+)\)", s1)]
    assert esc and 0 < esc[0] < 1.12                             # creciendo (pop)
    assert s0.count("<g transform") == 1 and s2.count("<g transform") == 2
    assert sv.pop(0.55) > 1.0 and sv.pop(1.0) == 1.0             # se pasa apenas y vuelve


def test_claves_en_color_y_temblor_en_el_impacto():
    ps = _palabras("rompió la tele")
    ps[0].clave, ps[0].impacto = True, True
    ps[2].clave = True
    g = sv.agrupar(ps)
    s = sv.subtitulo(g, 0.35)
    assert sv.ROJO in s and sv.BLANCO in s and sv.AMARILLO in sv.subtitulo(g, 0.7)
    a, b = sv.subtitulo(g, 0.10), sv.subtitulo(g, 0.12)
    rot = [re.search(r"rotate\(([-0-9.]+)\)", x).group(1) for x in (a, b)]
    assert rot[0] != rot[1]                                     # tiembla
    assert "rotate(0.00)" in sv.subtitulo(g, 0.55)              # y se calma


def test_marcar_claves_emoji_y_topes():
    ps = _palabras("La pelota rompió la tele y en 1969 vendieron millones de pelotas carísimas", paso=0.5)
    segs = [{"texto": "La pelota rompió la tele", "claves": ["rompió", "tele", "pelota"], "emoji": "explosion",
             "remate": False},
            {"texto": "y en 1969 vendieron millones de pelotas carísimas", "claves": ["millones", "inexistente"],
             "emoji": "plata", "remate": True}]
    sv.marcar(ps, segs, golpes=[1.1])
    claves = [p.texto for p in ps if p.clave]
    assert claves == ["pelota", "rompió", "1969", "millones"]           # 2 por segmento; los números cuentan
    assert "inexistente" not in claves
    assert next(p for p in ps if p.texto == "rompió").impacto            # cerca del golpe
    assert next(p for p in ps if p.texto == "millones").impacto          # el remate
    emojis = [(p.texto, p.emoji) for p in ps if p.emoji]
    assert emojis == [("pelota", "explosion")]       # el segundo cae a menos de 4,5 s del primero: no va
    ps2 = _palabras("a b c d e f g h i j k l m n o p", paso=0.4)
    sv.marcar(ps2, [{"texto": "a b c d e f g h", "claves": ["b"], "emoji": "risa"},
                    {"texto": "i j k l m n o p", "claves": ["p"], "emoji": "susto"}], [])
    assert [p.emoji for p in ps2 if p.emoji] == ["risa", "susto"]       # 6 s de distancia: van los dos
    assert all(p.clave for p in ps2 if p.emoji)                         # el emoji, siempre al lado de una clave


def test_emoji_dibujado_al_lado_de_la_clave():
    for nombre in sv.EMOJIS:
        _svg(sv.emoji_svg(nombre))
        assert "<text" not in sv.emoji_svg(nombre)                       # no depende de fuentes de emoji
    ps = _palabras("se rompió todo")
    ps[1].clave, ps[1].emoji = True, "explosion"
    s = sv.subtitulo(sv.agrupar(ps), 0.45)
    assert "#ff4b3e" in s and s.index("translate") >= 0


def test_nada_se_sale_de_la_franja_ni_del_ancho():
    largas = _palabras("Desoxirribonucleico Otorrinolaringólogo Electroencefalografista")
    for p in largas:
        p.clave = True
    largas[0].emoji = "susto"
    grupos = sv.agrupar(largas)
    x0, x1, y0, y1 = sv.limites(grupos)
    assert x0 >= 0 and x1 <= 1080
    assert y1 < ac.BANDA_SUBTITULOS and y0 > 150


def test_linea_de_tiempo_viral_y_marcar_con_haiku():
    d = {"escenas": [
        {"frase": "Una pelota rompió la tele.", "parte": "gancho", "fondo": "casa", "actores": [],
         "objetos": [], "cadena": [], "camara": "fija", "texto_pantalla": "", "transicion": "corte",
         "viaje_a_anio": 0, "vuelve_al_presente": False},
        {"frase": "Y vendieron millones.", "parte": "giro", "fondo": "tienda", "actores": [], "objetos": [],
         "cadena": [], "camara": "fija", "texto_pantalla": "", "transicion": "corte", "viaje_a_anio": 0,
         "vuelve_al_presente": False}],
        "locutor": [{"despues_de_frase": 1, "texto": "Pobre tele."}]}
    assert not mk.tiene_claves(d)

    class Haiku:
        llamadas = 0

        def json(self, sistema, pedido, schema, temp):
            Haiku.llamadas += 1
            assert "[0] Una pelota rompió la tele." in pedido and "[1] Pobre tele." in pedido
            return json.dumps({"textos": [{"indice": 0, "claves": ["rompió"], "emoji": "explosion"},
                                          {"indice": 1, "claves": ["tele."], "emoji": "risa"},
                                          {"indice": 2, "claves": ["millones."], "emoji": "plata"}]})

    mk.marcar_claves(Haiku(), d)
    assert Haiku.llamadas == 1 and mk.tiene_claves(d)
    assert d["escenas"][0]["claves"] == ["rompió"] and d["locutor"][0]["emoji"] == "risa"
    assert [s["remate"] for s in mk.segmentos_subtitulos(d)] == [False, True, True]
    palabras = [tx.Palabra(w, i * 0.4, i * 0.4 + 0.35) for i, w in
                enumerate("Una pelota rompió la tele. Pobre tele. Y vendieron millones.".split())]
    datos, _ = mk.linea_de_tiempo(d, [0.0, 2.0, 2.8], 4.5, palabras, None, presente=2026)
    assert datos["subtitulos_estilo"] == "viral"
    marcadas = {p["texto"]: p for p in datos["subtitulos"][0]["palabras"]}
    assert marcadas["rompió"]["clave"] and marcadas["rompió"]["emoji"] == "explosion"
    v = Video.desde_dict(datos)
    assert v.sub_estilo == "viral" and all(1 <= len(g) <= 3 for g in v.subtitulos)
    _svg(v.encima(0.85))


def test_schema_del_guion_pide_claves_y_emoji():
    props = mk.SCHEMA_GUION["properties"]["escenas"]["items"]
    assert {"claves", "emoji"} <= set(props["required"])
    loc = mk.SCHEMA_GUION["properties"]["locutor"]["items"]
    assert {"claves", "emoji"} <= set(loc["required"])
    assert "REGLA 9" in mk.SISTEMA_GUION


def test_clave_de_varias_palabras_no_marca_el_relleno():
    ps = _palabras("Era una pelota de espuma")
    sv.marcar(ps, [{"texto": "Era una pelota de espuma", "claves": ["pelota de espuma"], "emoji": ""}], [])
    assert [p.texto for p in ps if p.clave] == ["pelota", "espuma"]
