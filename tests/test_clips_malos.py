"""Clips malos (2026-09-29): vistas relativas al streamer (30 % superior), puntaje mínimo 6 y la
línea de "por qué" en cada clip que llega."""

from datetime import timedelta

from test_fuentes import AHORA, CAT, UNO, UNO_CAT, fijos, iso, llamadas_clips, pagina, viejo, vod
from test_twitch_candidates import Resp, cliente, helix_clip

from clips_bot import db
from clips_bot.candidates import (MOTIVO_VISTAS_RELATIVAS, Clip, buscar_candidatos, buscar_catalogo,
                                  umbral_historico, umbrales_vistas)
from clips_bot.config import Filtros, Seleccion, load_settings
from clips_bot.telegram import mensaje_textos, por_que

TOP = Filtros(vistas_top=0.30)


def test_umbral_es_la_vista_mas_baja_del_30_por_ciento_superior_de_cada_streamer():
    clips = [Clip.from_helix(helix_clip(f"a{i}", views=v), "grande") for i, v in
             enumerate([1000, 900, 800, 700, 600, 500, 400, 300, 200, 100])]
    clips += [Clip.from_helix(helix_clip(f"b{i}", views=v), "chico") for i, v in enumerate([40, 30, 5])]
    u = umbrales_vistas(clips, 0.30)
    assert u["grande"] == (800, 550)       # top 3 de 10; mediana 550
    assert u["chico"] == (40, 30)          # top 1 de 3 (se redondea para arriba)


def test_recientes_solo_pasan_el_30_por_ciento_superior_y_llevan_la_mediana():
    datos = [vod(f"c{i}", v, offset=1000 * i) for i, v in enumerate([500, 400, 300, 200, 100, 50, 10])]
    c, _ = cliente(fijos({"/clips": Resp(200, {"data": datos})}))
    res = buscar_candidatos(c, UNO, TOP, vistos=set(), ahora=AHORA, seleccion=Seleccion())
    assert [x.id for x in res.candidatos] == ["c0", "c1", "c2"]          # 3 de 7 (30 % → 3)
    assert res.descartes[MOTIVO_VISTAS_RELATIVAS] == 4
    assert all(x.mediana_vistas == 200 for x in res.candidatos)


def test_buscar_con_palabras_no_filtra_por_vistas():
    datos = [vod(f"c{i}", v, offset=1000 * i) for i, v in enumerate([500, 400, 300, 10])]
    c, _ = cliente(fijos({"/clips": Resp(200, {"data": datos})}))
    res = buscar_candidatos(c, UNO, TOP, vistos=set(), ahora=AHORA, seleccion=Seleccion(),
                            palabras_titulo=("stream",))           # está en el título del stream
    assert len(res.candidatos) == 4 and res.descartes[MOTIVO_VISTAS_RELATIVAS] == 0


def test_catalogo_usa_el_umbral_historico_y_lo_guarda_una_semana(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    historico = pagina([viejo(f"h{i}", v) for i, v in enumerate([9000, 5000, 3000, 1000, 800, 600, 550,
                                                                  520, 510, 505])])
    c, s = cliente(fijos({"/clips": [historico,
                                     pagina([viejo("bueno", 5000), viejo("flojo", 600)])]}))
    res = buscar_catalogo(c, UNO_CAT, TOP, CAT, conn, vistos=set(), ahora=AHORA)
    assert [x.id for x in res.catalogo] == ["bueno"]                     # umbral histórico 3000
    assert res.descartes_catalogo[MOTIVO_VISTAS_RELATIVAS] == 1
    assert res.catalogo[0].mediana_vistas == 700
    llamadas = len(llamadas_clips(s))
    assert umbral_historico(c, conn, "uno", "1", AHORA, AHORA, 0.3, ahora=AHORA + timedelta(days=3)) \
        == (3000, 700)
    assert len(llamadas_clips(s)) == llamadas                             # guardado: no pagina de nuevo


def test_la_config_real_tiene_las_reglas_nuevas():
    s = load_settings()
    assert s.filtros.vistas_top == 0.30 and s.textos.puntaje_min == 6


def test_por_que_en_una_linea():
    meta = {"vistas": 1240, "mediana_vistas": 400, "clips_mismo_momento": 3, "puntaje": 7}
    assert por_que(meta) == "📊 1.240 vistas (×3,1 su mediana) · 3 creadores distintos · Gemini 7/10"
    assert por_que({"vistas": 80, "clips_mismo_momento": 1}) == "📊 80 vistas · 1 creador"
    assert por_que({"streamer": "Pequeña Historia"}) == ""                 # efemérides, /editar
    texto = mensaje_textos(1, "spreen", "x", "13:00", {"titulo": "t", "descripcion": "d",
                                                       "hashtags": ["#Shorts"], "credito": "c"},
                           por_que=por_que(meta))
    assert "<i>📊 1.240 vistas" in texto.split("Título")[0]               # arriba, antes de los textos


def test_el_umbral_no_cuenta_los_clips_del_programa_de_terceros():
    """Davo (2026-09-29): 23 de 51 clips eran del "412" y los más vistos; con ellos adentro la vara
    subía de 25 a 36 vistas."""
    from clips_bot.candidates import MOTIVO_PROGRAMA, aplicar_vistas_relativas

    clips = [Clip.from_helix(helix_clip(f"p{i}", views=v), "davo") for i, v in enumerate([900, 800, 700])]
    clips += [Clip.from_helix(helix_clip(f"s{i}", views=v), "davo") for i, v in enumerate([50, 40, 30, 20])]
    motivos = {c.id: (MOTIVO_PROGRAMA if c.id.startswith("p") else None) for c in clips}
    umbrales = aplicar_vistas_relativas(clips, motivos, 0.30)
    assert umbrales["davo"] == (40, 35)                         # top 2 de sus 4 propios
    assert [c.id for c in clips if motivos[c.id] is None] == ["s0", "s1"]
