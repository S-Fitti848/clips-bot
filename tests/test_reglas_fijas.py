"""Las tres reglas fijas para TODOS los videos (decisión de Santi, 2026-09-28). Si alguno de estos
tests falla, se rompió una regla que no se negocia:

1. Fotos que muestran lo que se dice: una búsqueda por frase, Gemini elige en UNA llamada, mínimo
   6 fotos distintas, ninguna más de 6 s seguidos, sin repetir salvo que no haya otra, y en la
   hoja cada foto con su frase al lado.
2. Guiones que se entienden: el cómo y el porqué para un chico de 15 años, en todos los prompts.
3. Audio limpio: fade in 0,1 s, fade out 0,5 s, termina exacto con el video, crossfade corto en las
   uniones y aviso si hay un pico arriba de −3 dB en el último segundo.

Sin red: Wikipedia, Commons, Gemini y ffmpeg son fakes (salvo PIL, que dibuja la hoja)."""

import json
from pathlib import Path

import pytest

import clips_bot.__main__ as m
from clips_bot import efemerides as ef, ilustrar, media, narrar, serie
from clips_bot.reglas import REGLAS_CLARIDAD


# ==== 1. fotos que muestran lo que se dice ======================================================

def test_asignar_no_repite_si_hay_otra():
    rankings = [[0, 1], [0, 2], [0, 1], [3], [3, 4], [5]]
    fotos = ilustrar.asignar(rankings, pool=[0, 1, 2, 3, 4, 5])
    assert fotos == [0, 2, 1, 3, 4, 5] and len(set(fotos)) == 6


def test_asignar_repite_solo_cuando_no_hay_otra_y_nunca_la_de_la_frase_anterior():
    fotos = ilustrar.asignar([[0, 1], [0, 1], [0, 1], [0, 1]], pool=[0, 1])
    assert fotos == [0, 1, 0, 1]


def test_una_frase_sin_fotos_propias_usa_una_del_pool_que_no_salio():
    assert ilustrar.asignar([[0], [], [1]], pool=[0, 7, 1]) == [0, 7, 1]


def test_completar_distintas_llega_a_seis_si_se_puede():
    fotos = ilustrar.completar_distintas([0, 1, 0, 1, 2, 3, 0], [[0]] * 7, pool=[0, 1, 2, 3, 4, 5])
    assert len(set(fotos)) == 6


def test_ninguna_foto_mas_de_6_segundos_seguidos():
    # frase 0 dura 10 s → se parte en dos de 5 s con otra foto de su lista
    plan = ilustrar.tramos([0, 1], [10.0, 3.0], [[0, 9], [1]], pool=[0, 1, 9])
    assert [(f, round(s, 1)) for _, f, s in plan] == [(0, 5.0), (9, 5.0), (1, 3.0)]
    # dos frases seguidas con la misma foto cuentan juntas: 4 + 4 > 6 → la segunda cambia
    plan = ilustrar.tramos([0, 0], [4.0, 4.0], [[0], [0, 5]], pool=[0, 5])
    assert [f for _, f, _ in plan] == [0, 5]
    assert ilustrar.errores_plan(plan, minimo=2) == []


def test_errores_plan_detecta_pocas_fotos_y_tramos_largos():
    assert "al menos 6" in ilustrar.errores_plan([(0, 0, 3.0), (1, 1, 3.0)])[0]
    largo = [(0, 0, 4.0), (1, 0, 4.0)] + [(i, i, 1.0) for i in range(1, 6)]
    assert any("seguidos" in e for e in ilustrar.errores_plan(largo))
    assert ilustrar.MIN_FOTOS_DISTINTAS == 6 and ilustrar.MAX_TRAMO_S == 6.0


def test_rankings_de_se_queda_con_las_candidatas_de_cada_frase():
    d = {"frases": [{"fotos": [1, 3, 9]}, {"fotos": [2, 2]}], "descartadas": [3]}
    rankings, malas = ef.rankings_de(d, [[0, 1, 2], [1]])
    assert rankings == [[0], [1]] and malas == {2}      # 9 no es candidata, 3 está descartada
    with pytest.raises(ValueError):
        ef.rankings_de({"frases": [{"fotos": [1]}], "descartadas": []}, [[0], [1]])


def test_las_miniaturas_de_thumb_wikimedia_tambien_esperan_entre_descargas(tmp_path):
    class R:
        status_code, content, headers, text = 200, b"x", {}, ""

    class S:
        def get(self, *a, **k):
            return R()

    esperas = []
    w = ef.Wiki(session=S(), sleep=esperas.append, cache=None)
    w.bajar("https://thumb.wikimedia.org/wikipedia/commons/thumb/7/74/A.jpg/1280px-A.jpg",
            tmp_path / "a.jpg")
    assert esperas == [ef.Wiki.PAUSA_FOTOS_S]


def test_la_reserva_nunca_usa_fotos_que_gemini_no_eligio_para_nada():
    """Prueba del 28/09: la postal de Hamburgo entró por la reserva sin que nadie la eligiera."""
    g = _guion(3)
    g.ranking, g.descartadas = [[2], [5], []], [0]
    assert ef.de_reserva(g, 8) == [2, 5]
    g.ranking = [[], [], []]
    assert ef.de_reserva(g, 3) == [1, 2]            # sin nada elegido, lo que queda (sin descartes)


def test_cada_frase_puede_elegir_cualquier_foto_empezando_por_las_de_su_busqueda(tmp_path):
    prompts = []

    class Gem(GeminiFotos):
        def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
            prompts.append(prompt)
            return super().json(sistema, prompt, schema, temperatura, imagenes, audio)

    wiki = WikiFalsa()
    e = ef.Evento("es", 1928, "x", ["Penicilina"])
    art, _ = ef.fotos_del_evento(wiki, e)
    pool, _ = ef.fotos_para_guion(wiki, Gem(), e, _guion(), art, tmp_path)
    frase5 = prompts[0].split("frase 5:")[1].split("frase 6:")[0]
    cands = frase5.split("candidatas:")[1].split("\n")[0]
    assert len(cands.split(",")) == len(pool)                     # todo el pool
    assert "de su búsqueda:" in frase5 and "se_ve" in ef.SCHEMA_FOTOS["properties"]["frases"]["items"]["required"]


def test_el_guion_pide_busquedas_concretas():
    for mal in ("microscope view", "medical research", "historical laboratory"):
        assert mal in ef.SISTEMA_GUION                              # como ejemplo de lo que NO
    assert "COSA\n  PUNTUAL" in ef.SISTEMA_GUION or "COSA PUNTUAL" in ef.SISTEMA_GUION


def test_el_guion_pide_que_mostrar_en_cada_frase():
    frase = ef.SCHEMA_GUION["properties"]["frases"]["items"]
    assert "mostrar" in frase["required"] and "foto" not in frase["properties"]
    assert "INGLÉS" in ef.SISTEMA_GUION


# -- de punta a punta, sin red --

def _jpg(ruta: Path, color=(120, 80, 40)) -> Path:
    from PIL import Image

    ruta.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), color).save(ruta)
    return ruta


def _info(archivo, ancho=2000):
    return {"archivo": archivo, "mime": "image/jpeg", "width": ancho, "height": 1200,
            "thumburl": f"https://upload.wikimedia.org/x/thumb/{archivo}/1280px-a.jpg",
            "descriptionurl": "https://commons/x",
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "ImageDescription": {"value": archivo}, "Artist": {"value": "Ana"}}}


class WikiFalsa:
    """Dos fotos en el artículo y dos por búsqueda de Commons (distintas para cada frase)."""

    def __init__(self):
        self.busquedas = []

    def archivos(self, lang, titulo):
        return ["File:art0.jpg", "File:art1.jpg"]

    def info(self, lang, archivos, ancho=1280):
        return [_info(a) for a in archivos]

    def buscar_commons(self, terminos, cuantas=6):
        self.busquedas.append(terminos)
        k = len(self.busquedas)
        return [_info(f"File:q{k}_a.jpg"), _info(f"File:q{k}_b.jpg")]

    def bajar(self, url, destino):
        return _jpg(destino)


class GeminiFotos:
    """Para cada frase elige la primera candidata que vino de SU búsqueda."""

    def __init__(self):
        self.llamadas = []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
        self.llamadas.append(len(imagenes or []))
        frases = []
        for bloque in prompt.split("frase ")[1:]:
            cands = [int(x) for x in bloque.split("candidatas:")[1].split("\n")[0].split(",")]
            frases.append({"fotos": cands[:2]})
        return json.dumps({"frases": frases, "descartadas": []})


def _guion(n=8):
    return ef.Guion(frases=[f"Frase número {i} del guion." for i in range(n)], fotos=[],
                    descartadas=[], titulo="t", descripcion="d", hashtags=["#Shorts"],
                    mostrar=[f"cosa {i}" for i in range(n)], idea_clave="x")


def test_fotos_para_guion_busca_por_frase_y_elige_en_una_sola_llamada(tmp_path):
    wiki, gem = WikiFalsa(), GeminiFotos()
    e = ef.Evento("es", 1928, "Fleming descubre la penicilina", ["Penicilina"])
    art, _ = ef.fotos_del_evento(wiki, e)
    pool, g = ef.fotos_para_guion(wiki, gem, e, _guion(), art, tmp_path)
    assert wiki.busquedas == [f"cosa {i}" for i in range(8)]       # una búsqueda por frase
    assert gem.llamadas == [len(pool)]                              # UNA llamada, con todas las fotos
    assert len(set(g.fotos)) >= 6 and len(g.ranking) == 8
    assert not ilustrar.errores_plan(ef.plan_estimado(g, len(pool)))
    # cada frase usa una foto de SU búsqueda (no la misma del artículo para todas)
    assert all(pool[f].articulo.startswith("Commons: cosa") for f in g.fotos)


def test_la_hoja_pone_cada_foto_al_lado_de_su_frase(tmp_path):
    from PIL import Image

    fotos = [ef.a_foto(_info(f"File:{i}.jpg"), "X") for i in range(3)]
    for i, f in enumerate(fotos):
        f.ruta = str(_jpg(tmp_path / f"{i}.jpg", (40 * i, 90, 90)))
    plan = [(0, 0, 5.0), (0, 2, 5.0), (1, 1, 3.0)]
    filas = ef.filas_de_hoja(plan, ["Una frase larga que se parte.", "Otra frase."])
    assert filas == [([0, 2], "Una frase larga que se parte."), ([1], "Otra frase.")]
    hoja = ef.hoja_de_guion(fotos, filas, tmp_path / "hoja.jpg")
    with Image.open(hoja) as im:
        assert im.width == 1000 and im.height >= 2 * 165           # una fila por frase
    g = ef.Guion(frases=[t for _, t in filas], fotos=[0, 1], descartadas=[], titulo="t",
                 descripcion="d", hashtags=[], idea_clave="el moho mata bacterias")
    texto = ef.texto_aprobacion(ef.Evento("es", 1928, "x", ["X"]), g, fotos, ef.date(2026, 9, 28), plan)
    assert "[1→3] Una frase larga" in texto and "Tiene que quedar claro" in texto


def test_el_video_usa_el_plan_con_los_tiempos_reales(tmp_path):
    g = _guion(2)
    g.fotos, g.ranking = [0, 1], [[0, 2], [1]]
    p = ef.Propuesta(fecha="2026-09-28", evento={"lang": "es", "anio": 1928, "texto": "x",
                                                 "paginas": ["X"]},
                     fotos=[ef.a_foto(_info(f"File:{i}.jpg"), "X").a_dict() for i in range(3)],
                     reserva=[], guion=g.a_dict())
    plan = ef.plan_de(p, [9.0, 2.0])
    assert max(s for _, _, s in plan) <= 6.0 and [f for _, f, _ in plan] == [0, 2, 1]


# ==== 2. guiones que se entienden ================================================================

@pytest.mark.parametrize("prompt", [ef.SISTEMA_GUION, narrar.SISTEMA, serie.SISTEMA_GUIONES],
                         ids=["efemerides", "narrar", "serie"])
def test_todos_los_guiones_llevan_las_reglas_de_claridad(prompt):
    assert REGLAS_CLARIDAD in prompt


def test_las_reglas_de_claridad_dicen_lo_que_se_pidio():
    for frase in ("15 años", "CÓMO", "PORQUÉ", "paso a paso", "técnic", "Menos datos",
                  "MATABA a las bacterias", "POR ESO sirve como remedio"):
        assert frase in REGLAS_CLARIDAD


def test_la_efemeride_pide_la_idea_clave():
    assert "idea_clave" in ef.SCHEMA_GUION["required"]


def test_menos_datos_no_es_un_guion_mas_corto():
    """Prueba del 28/09: con "menos datos", flash-lite escribió 75 palabras tres veces."""
    assert "NO es un guion más corto" in ef.SISTEMA_GUION
    assert ef.SISTEMA_GUION.index(REGLAS_CLARIDAD) < ef.SISTEMA_GUION.index("NO es un guion más corto")


# ==== 3. audio limpio ============================================================================

def test_cola_de_audio():
    c = media.cola_audio(40.0)
    assert c.startswith("apad,atrim=0:40.000")               # largo exacto: ni cortado ni de más
    assert "afade=t=in:st=0:d=0.1" in c and "afade=t=out:st=39.500:d=0.5" in c
    assert media.FADE_IN_S == 0.1 and media.FADE_OUT_S == 0.5 and media.PICO_MAX_DB == -3.0


def test_crossfade_en_las_uniones_sin_correr_la_sincronia():
    f = media.audio_con_crossfade([("[0:a]", 1.0, 4.5, 60.0), ("[0:a]", 8.0, 11.0, 60.0),
                                   ("[0:a]", 15.0, 19.2, 60.0)], "[a]")
    # cada tramo se estira d/2 del lado de la unión, y acrossfade se come d: el total no cambia
    assert "atrim=1.000:4.520" in f and "atrim=7.980:11.020" in f and "atrim=14.980:19.200" in f
    assert f.count("acrossfade=d=0.04") == 2 and f.endswith("[a]")
    assert media.audio_con_crossfade([("[0:a]", 2.0, 5.0, 9.0)], "[a]") == \
        "[0:a]atrim=2.000:5.000,asetpts=PTS-STARTPTS[a]"


@pytest.mark.parametrize("pico,dv,da,aviso", [
    (-6.0, 40.0, 40.0, None), (-1.5, 40.0, 40.0, "pico"), (-8.0, 40.0, 38.9, "no terminan juntos"),
    (None, 40.0, None, None)])
def test_avisos_de_audio(pico, dv, da, aviso):
    avisos = media.avisos_audio(pico, dv, da)
    assert (not avisos) if aviso is None else any(aviso in a for a in avisos)


def _capturar(monkeypatch, modulo):
    comandos = []
    monkeypatch.setattr(modulo, "run", lambda args, cwd=None: comandos.append(" ".join(map(str, args))))
    return comandos


def test_clips_y_editar_terminan_con_la_cola(monkeypatch, tmp_path):
    from clips_bot import render
    from clips_bot.config import Render
    from clips_bot.layout import layout_fit_blur

    comandos = _capturar(monkeypatch, render)
    monkeypatch.setattr(render, "probe", lambda p: media.Info(1920, 1080, 30.0, 30, True))
    lay = layout_fit_blur(1920, 1080, Render())
    render.renderizar(tmp_path / "a.mp4", tmp_path / "b.mp4", lay, Render(), None)
    assert "[0:a]apad,atrim=0:30.000" in comandos[0] and "afade=t=out:st=29.500" in comandos[0]
    assert "0:a?" not in comandos[0]                         # el audio crudo ya no se copia


def test_narrar_y_serie_terminan_con_la_cola_sin_shortest(monkeypatch, tmp_path):
    comandos = _capturar(monkeypatch, narrar)
    monkeypatch.setattr(narrar, "_tiene_audio", lambda v: True)
    monkeypatch.setattr(narrar, "_duracion_video", lambda v: 45.0)
    narrar.mezclar(tmp_path / "v.mp4", tmp_path / "voz.wav", tmp_path / "s.mp4", 0.15)
    narrar.mezclar(tmp_path / "v.mp4", tmp_path / "voz.wav", tmp_path / "s.mp4", 0.15, sin_original=True)
    for c in comandos:
        assert "atrim=0:45.000" in c and "afade=t=in" in c and "-shortest" not in c


def test_el_resumen_pega_el_audio_con_crossfade(monkeypatch, tmp_path):
    comandos = _capturar(monkeypatch, narrar)
    monkeypatch.setattr(narrar, "_tiene_audio", lambda v: True)
    monkeypatch.setattr(narrar, "_duracion_video", lambda v: 120.0)
    narrar.armar_resumen(tmp_path / "v.mp4", [(0.0, 5.0), (10.0, 15.0)], tmp_path / "r.mp4")
    assert "acrossfade" in comandos[0] and "atrim=0:10.000" in comandos[0]


def test_la_efemeride_termina_con_la_cola_del_largo_de_las_fotos(monkeypatch, tmp_path):
    from clips_bot.config import Render

    comandos = _capturar(monkeypatch, ef)
    audio = _capturar(monkeypatch, media)
    monkeypatch.setattr(ef, "foco", lambda ruta: (0.5, 0.5))
    fotos = [_jpg(tmp_path / f"{i}.jpg") for i in range(2)]
    ef.armar_video([(fotos[0], 4.0), (fotos[1], 5.5)], tmp_path / "voz.wav", tmp_path,
                   tmp_path / "v.mp4", Render())
    # el audio se termina en un paso aparte (con la entrada concat, ffmpeg lo cortaba a 26,7 s)
    assert "aresample=48000,apad,atrim=0:9.500" in audio[0] and "afade=t=out:st=9.000" in audio[0]
    final = comandos[-1]
    assert "audio_final.wav" in final and "-map 1:a" in final
    assert "-shortest" not in final and "[1:a]" not in final


def test_la_entrega_avisa_si_el_audio_esta_mal(monkeypatch, tmp_path):
    class TG:
        def __init__(self):
            self.mensajes = []

        def send_video(self, *a, **k):
            return {"video": {"file_id": "f"}}

        def send_message(self, chat, texto, teclado=None):
            self.mensajes.append(texto)

    from clips_bot import db

    monkeypatch.setattr(m, "probe", lambda v: media.Info(1080, 1920, 30.0, 30, True))
    monkeypatch.setattr(m, "miniatura", lambda v, d: d)
    monkeypatch.setattr(m, "chequear_audio", lambda v: ["pico de -1.0 dB en el último segundo"])
    monkeypatch.setattr("clips_bot.process.READY_DIR", tmp_path)
    tg = TG()
    meta = {"salida": str(tmp_path / "x.mp4"), "streamer": "coker",
            "textos": {"titulo": "t", "descripcion": "d", "hashtags": ["#Shorts"], "credito": "c"}}
    m.enviar_clip(tg, "1", db.connect(tmp_path / "t.db"), "x", meta, 1, "13:00")
    assert "⚠️ <b>Audio</b>: pico de -1.0 dB" in tg.mensajes[0]


# ==== 1b. fotos de época (2026-09-29: un avión de 2008 en una historia de 1940) =================

@pytest.mark.parametrize("fecha,anio", [
    ("2008-08-17", 2008), ("Tomada el 20 de septiembre de 2010, 17:5", 2010),
    ("circa WW1, pre-1923", 1923), ("1940s", 1940), ("", None), ("desconocida", None)])
def test_anio_de_la_foto(fecha, anio):
    assert ef.anio_de(fecha) == anio


def test_el_mostrar_de_una_frase_del_pasado_lleva_la_epoca():
    from test_efemerides import ARTICULO, _guion_ok

    d = _guion_ok()
    d["frases"][2]["mostrar"] = "Stanford University"           # sin año
    errores = ef.validar_guion(d, 1998, ARTICULO)
    assert any("le falta la época" in e and "[3]" in e for e in errores)
    d["frases"][2]["presente"] = True                            # habla de hoy: no hace falta
    assert not any("época" in e for e in ef.validar_guion(d, 1998, ARTICULO))
    assert "ÉPOCA Y LUGAR" in ef.SISTEMA_GUION and "1940 German fighter aircraft grounded" in ef.SISTEMA_GUION
    assert "presente" in ef.SCHEMA_GUION["properties"]["frases"]["items"]["required"]


def _info_anio(archivo, anio):
    i = _info(archivo)
    if anio:
        i["extmetadata"]["DateTimeOriginal"] = {"value": str(anio)}
    return i


class WikiEpoca(WikiFalsa):
    """El artículo trae 2 fotos de 1940; cada búsqueda trae una de 2008 y una de 1940."""

    def archivos(self, lang, titulo):
        return ["File:art0.jpg", "File:art1.jpg"]

    def info(self, lang, archivos, ancho=1280):
        return [_info_anio(a, 1940) for a in archivos]

    def buscar_commons(self, terminos, cuantas=6):
        self.busquedas.append(terminos)
        k = len(self.busquedas)
        return [_info_anio(f"File:q{k}_moderna.jpg", 2008), _info_anio(f"File:q{k}_vieja.jpg", 1941)]


class GeminiQueVe:
    """Guarda el prompt; en cada frase pone primero lo primero de sus candidatas."""

    def __init__(self, de_epoca=True):
        self.prompts, self.de_epoca = [], de_epoca

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
        self.prompts.append(prompt)
        frases = []
        for bloque in prompt.split("\nfrase ")[1:]:
            cands = [int(x) for x in bloque.split("candidatas:")[1].split("\n")[0].split(",")]
            frases.append({"se_ve": "x", "fotos": cands[:2], "de_epoca": self.de_epoca})
        return json.dumps({"frases": frases, "descartadas": []})


def _guion_epoca(n=8, presente=None):
    g = _guion(n)
    g.presente = presente or [False] * n
    return g


def test_las_fotos_modernas_no_son_candidatas_de_las_frases_del_pasado(tmp_path):
    wiki, gem = WikiEpoca(), GeminiQueVe()
    e = ef.Evento("es", 1940, "Two Avro Ansons collide", ["Brocklesby"])
    art, _ = ef.fotos_del_evento(wiki, e)
    g = _guion_epoca(presente=[False] * 7 + [True])
    pool, g = ef.fotos_para_guion(wiki, gem, e, g, art, tmp_path)
    modernas = {i for i, f in enumerate(pool) if f.anio == 2008}
    assert modernas and set(g.modernas) == modernas
    prompt = gem.prompts[0]
    assert "EL HECHO ES DE 1940" in prompt and "(2008)" in prompt       # Gemini ve los años
    for bloque in prompt.split("\nfrase ")[1:8]:                        # frases del pasado
        cands = {int(x) - 1 for x in bloque.split("candidatas:")[1].split("\n")[0].split(",")}
        assert not cands & modernas
    ultima = prompt.split("\nfrase ")[8]                                # la que habla de hoy
    assert "(habla de hoy)" in ultima
    assert all(pool[f].anio != 2008 for i, f in enumerate(g.fotos) if not g.presente[i])


def test_si_gemini_dice_que_no_es_de_la_epoca_esa_foto_sale():
    d = {"frases": [{"fotos": [1, 2], "de_epoca": False}, {"fotos": [1, 2], "de_epoca": False}],
         "descartadas": []}
    rankings, _ = ef.rankings_de(d, [[0, 1], [0, 1]], presente=[False, True])
    assert rankings == [[1], [0, 1]]                  # en la de hoy, una actual sirve


def test_sin_fotos_de_epoca_se_repite_una_del_articulo_antes_que_una_moderna(tmp_path):
    class SoloModernas(WikiEpoca):
        def buscar_commons(self, terminos, cuantas=6):
            self.busquedas.append(terminos)
            return [_info_anio(f"File:m{len(self.busquedas)}.jpg", 2010)]

    wiki = SoloModernas()
    e = ef.Evento("es", 1940, "x", ["Brocklesby"])
    art, _ = ef.fotos_del_evento(wiki, e)
    wiki_art = [f for f in art]
    wiki_art.append(ef.a_foto(_info_anio("File:art2.jpg", 1940), "Brocklesby"))
    pool, g = ef.fotos_para_guion(wiki, GeminiQueVe(), e, _guion_epoca(), wiki_art, tmp_path)
    usadas = {f for _, f, _ in ef.plan_estimado(g, len(pool))}
    assert all(pool[f].anio == 1940 for f in usadas)                    # ninguna de 2010
    assert g.minimo_fotos == 3                                          # la época le gana a la cantidad
    texto = ef.texto_aprobacion(e, g, [], ef.date(2026, 9, 29), ef.plan_estimado(g, len(pool)), pool)
    assert "Solo hay 3 fotos de la época" in texto and "(1940)" in texto


def test_con_menos_de_tres_fotos_de_epoca_pasa_al_hecho_siguiente(tmp_path):
    class Nada(WikiEpoca):
        def archivos(self, lang, titulo):
            return ["File:art0.jpg"]

        def buscar_commons(self, terminos, cuantas=6):
            return [_info_anio("File:moderna.jpg", 2015)]

    wiki = Nada()
    e = ef.Evento("es", 1940, "x", ["X"])
    art, _ = ef.fotos_del_evento(wiki, e)
    with pytest.raises(ef.NarrarError, match="fotos de época"):
        ef.fotos_para_guion(wiki, GeminiQueVe(), e, _guion_epoca(), art, tmp_path)


def test_la_eleccion_pide_confirmar_la_epoca():
    assert "de_epoca" in ef.SCHEMA_FOTOS["properties"]["frases"]["items"]["required"]
    assert "ÉPOCA Y LUGAR" in ef.SISTEMA_FOTOS and ef.MARGEN_EPOCA == 10
