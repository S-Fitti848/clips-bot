"""Grupo evento (filtros, agrupación entre streamers) y Short multi-POV secuencial."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from test_twitch_candidates import helix_clip

from clips_bot.candidates import (MOTIVO_FUERA_EVENTO, Clip, Resultado, agrupar_evento,
                                  consolidar_evento, es_del_evento)
from clips_bot.config import Evento, Render, Subtitulos
from clips_bot.multipov import (Angulo, ass_carteles, credito_multiple, densidad_palabras,
                                filtro_concat, ordenar, palabras_de_srt, pico_reaccion)

AHORA = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
EVENTO = Evento(categorias=("Minecraft",), palabras=("dedsafio", "nights"), desde="2026-09-15",
                hasta="2026-09-30", ventana_entre_streamers_s=120)


def clip(id, login, views=100, horas=48.0, juego="Minecraft", titulo="un clip", grupo="evento"):
    d = {**helix_clip(id, views=views, created=(AHORA - timedelta(hours=horas)).strftime("%Y-%m-%dT%H:%M:%SZ")),
         "video_id": f"v_{login}", "vod_offset": 100}
    d["title"] = titulo
    return Clip.from_helix(d, login, juego, "", "reciente", "twitch", grupo)


# ---- filtros del evento ----------------------------------------------------------------


@pytest.mark.parametrize(
    "juego, titulo, horas, esperado",
    [
        ("Minecraft", "un clip", 48, True),
        ("Just Chatting", "DEDSAFIO día 3", 48, True),  # por título
        ("Just Chatting", "Nights con los pibes", 48, True),
        ("Just Chatting", "hablando de la vida", 48, False),  # ni categoría ni palabra
        ("Minecraft", "un clip", 24 * 20, False),  # anterior al período del evento
    ],
)
def test_es_del_evento(juego, titulo, horas, esperado):
    assert es_del_evento(clip("x", "uno", juego=juego, titulo=titulo, horas=horas), EVENTO) is esperado


def test_el_bonus_cuenta_creadores_distintos_no_clips():
    """Si el mismo usuario clipea tres veces la misma muerte, cuenta 1: la señal es cuánta gente
    distinta lo consideró clipeable."""
    from clips_bot.candidates import creadores_de

    def con_creador(id, creador):
        c = clip(id, "uno")
        return type(c)(**{**c.__dict__, "creator_id": creador})

    tres_del_mismo = [con_creador("a", "u1"), con_creador("b", "u1"), con_creador("c", "u1")]
    assert creadores_de(tres_del_mismo) == ("u1",)
    mezcla = [con_creador("a", "u1"), con_creador("b", "u2"), con_creador("c", "u1")]
    assert creadores_de(mezcla) == ("u1", "u2")
    # sin creator_id cada clip cuenta como propio, para no inflar ni desinflar el bonus
    assert len(creadores_de([clip("x", "uno"), clip("y", "uno")])) == 2


def test_el_evento_une_creadores_entre_canales():
    """Dos canales clipeados por el mismo usuario cuentan 1; tres usuarios distintos, 3."""
    res = Resultado()
    base = clip("a", "uno", views=50, horas=48.0)
    def con(id, login, creadores, views):
        c = clip(id, login, views=views, horas=48.0)
        return type(c)(**{**c.__dict__, "creadores": creadores})
    res.candidatos = [con("a", "uno", ("u1",), 50), con("b", "dos", ("u1",), 90),
                      con("c", "tres", ("u2", "u3"), 10)]
    res = consolidar_evento(res, EVENTO, peso_momento=0.5)
    elegido = [c for c in res.candidatos if c.grupo == "evento"][0]
    assert elegido.creadores == ("u1", "u2", "u3") and elegido.clips_mismo_momento == 3


def test_agrupar_evento_por_hora_real_entre_streamers():
    # la misma muerte clipeada por 3 canales con 1 min de diferencia
    a = clip("a", "uno", views=50, horas=48.0)
    b = clip("b", "dos", views=90, horas=48.0 - 1 / 60)
    c = clip("c", "tres", views=10, horas=48.0 + 1 / 60)
    lejos = clip("d", "cuatro", views=999, horas=40.0)
    grupos = [[x.id for x in g] for g in agrupar_evento([a, b, c, lejos], 120)]
    assert grupos == [["d"], ["b", "a", "c"]] or grupos == [["b", "a", "c"], ["d"]]


def test_consolidar_evento_suma_el_bonus_y_guarda_el_grupo_para_multipov():
    res = Resultado()
    res.candidatos = [
        clip("a", "uno", views=50, horas=48.0),
        clip("b", "dos", views=90, horas=48.0),
        clip("c", "tres", views=10, horas=48.0),
        clip("fuera", "cuatro", views=900, horas=48.0, juego="Just Chatting", titulo="charla"),
        clip("otro_grupo", "vegetta777", views=8000, horas=48.0, grupo="catalogo"),
    ]
    res = consolidar_evento(res, EVENTO, peso_momento=0.5)

    del_evento = [c for c in res.candidatos if c.grupo == "evento"]
    assert [(c.id, c.clips_mismo_momento) for c in del_evento] == [("b", 3)]  # el más visto, con el bonus
    assert res.descartes["fuera del evento (categoría, título o fecha)"] == 1
    assert res.descartes["mismo momento (entre streamers del evento)"] == 2
    assert [c.id for c in res.grupos_evento[0]] == ["b", "a", "c"]  # 3 canales → da para multi-POV
    assert any(c.grupo == "catalogo" for c in res.candidatos)  # el resto no se toca


def test_el_filtro_del_evento_corre_antes_del_corte_al_top_n():
    """Visto en la simulación del 2026-09-22: los clips de otra cosa del mismo streamer se comían
    los 8 lugares y el cupo del evento quedaba vacío, aunque más abajo había clips del evento."""
    from test_fuentes import fijos
    from test_twitch_candidates import Resp, cliente, helix_clip

    from clips_bot.candidates import buscar_candidatos
    from clips_bot.config import Filtros, Seleccion, Streamer

    def crudo(id, views, juego_id):
        return {**helix_clip(id, views=views, game_id=juego_id,
                             created=(AHORA - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")),
                "video_id": "", "vod_offset": None}

    c, _ = cliente(fijos({
        "/clips": Resp(200, {"data": [crudo("charla1", 900, "2"), crudo("charla2", 800, "2"),
                                      crudo("minecraft", 50, "1")]}),
        "/games": Resp(200, {"data": [{"id": "1", "name": "Minecraft"},
                                      {"id": "2", "name": "Just Chatting"}]}),
    }))
    uno = [Streamer("uno", fuentes=("reciente",), grupo="evento", experimento=True)]
    res = buscar_candidatos(c, uno, Filtros(n_candidatos=2), vistos=set(), ahora=AHORA,
                            seleccion=Seleccion(), evento=EVENTO)

    # los dos de Just Chatting tenían más vistas, pero no son del evento: no ocupan lugar
    assert [x.id for x in res.candidatos] == ["minecraft"]
    assert res.descartes[MOTIVO_FUERA_EVENTO] == 2


def test_el_evento_se_consolida_entero_antes_de_cortar():
    """Medido 2026-09-22: hubo 15 momentos con 3+ canales entre 479 clips del evento, y el multi-POV
    no se disparó nunca porque la agrupación corría sobre los 8 que sobrevivían al corte."""
    res = Resultado()
    # un momento con 3 canales, pero con pocas vistas: quedaría fuera de un top 2 hecho antes
    res.candidatos = [
        clip("pop1", "famoso", views=900, horas=48.0),
        clip("pop2", "famoso2", views=800, horas=47.0),
        clip("m1", "uno", views=10, horas=40.0),
        clip("m2", "dos", views=9, horas=40.0),
        clip("m3", "tres", views=8, horas=40.0),
    ]
    res = consolidar_evento(res, EVENTO, peso_momento=0.5, n_candidatos=2)

    assert len(res.candidatos) == 2  # el corte se aplica igual, pero al final
    assert [c.id for c in res.grupos_evento[0]] == ["m1", "m2", "m3"]  # el momento sobrevive


def test_grupo_de_dos_canales_no_va_a_multipov():
    res = Resultado()
    res.candidatos = [clip("a", "uno", horas=48.0), clip("b", "dos", horas=48.0)]
    res = consolidar_evento(res, EVENTO, 0.5)
    assert res.grupos_evento == []


# ---- multi-POV --------------------------------------------------------------------------


def ang(id, streamer, vistas, inicio=0.0, fin=8.0):
    return Angulo(id, streamer, Path(f"{id}.mp4"), vistas, inicio, fin)


def test_orden_de_menos_a_mas_visto_y_tope_de_3():
    angulos = [ang("a", "uno", 50), ang("b", "dos", 5000), ang("c", "tres", 300), ang("d", "cuatro", 10)]
    orden = ordenar(angulos)
    assert [a.streamer for a in orden] == ["uno", "tres", "dos"]  # el de 10 vistas queda afuera
    assert [a.vistas for a in orden] == [50, 300, 5000]  # el más fuerte queda al final
    assert len(orden) == 3


def test_pico_de_reaccion_usa_volumen_y_palabras():
    silencio, grito = [0.05] * 20, [0.9] * 4
    rms = silencio + grito + silencio  # el pico está a los ~10 s
    centro = pico_reaccion(rms, [], duracion=22, margen_s=4)
    assert 9.5 <= centro <= 12.5
    # con la misma señal de audio, las palabras mueven el centro hacia donde se habla
    palabras = [(2.0 + i * 0.1, 2.1 + i * 0.1) for i in range(30)]
    assert pico_reaccion([0.5] * 44, palabras, duracion=22, margen_s=4) < 6


def test_pico_respeta_los_bordes_del_clip():
    rms = [0.9] + [0.1] * 40  # el pico está al principio: la ventana no puede arrancar en negativo
    assert pico_reaccion(rms, [], duracion=20, margen_s=4) == 4.0
    rms = [0.1] * 40 + [0.9]  # y al final no puede pasarse
    assert pico_reaccion(rms, [], duracion=20, margen_s=4) == 16.0


def test_densidad_de_palabras_por_ventana():
    assert densidad_palabras([(0.1, 0.3), (0.2, 0.4), (1.2, 1.4)], 4) == [2.0, 0.0, 1.0, 0.0]


def test_palabras_de_srt(tmp_path: Path):
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nhola que tal\n\n"
                   "2\n00:00:05,000 --> 00:00:06,000\nchau\n", encoding="utf-8")
    palabras = palabras_de_srt(srt)
    assert len(palabras) == 4  # 3 + 1
    assert palabras[0][0] == 1.0 and palabras[-1][0] == 5.0
    assert palabras_de_srt(tmp_path / "no_existe.srt") == []


def test_filtro_concat_corta_cada_angulo_y_pega():
    angulos = [ang("a", "uno", 10, 2, 10), ang("b", "dos", 20, 0, 8)]
    f = filtro_concat(angulos, Render(), con_carteles=True)
    assert "trim=2.00:10.00" in f and "trim=0.00:8.00" in f
    assert "concat=n=2:v=1:a=1" in f
    assert f.endswith("[vcat]ass=carteles.ass[vout]")  # los carteles van al final, sobre el concat
    assert "hstack" not in f and "overlay" not in f  # nada de pantalla dividida


def test_carteles_duran_el_tramo_de_cada_streamer(tmp_path: Path):
    angulos = [ang("a", "uno", 10, 0, 8), ang("b", "dos", 20, 3, 11)]
    ass_carteles(angulos, tmp_path / "c.ass", Subtitulos(), Render())
    lineas = [l for l in (tmp_path / "c.ass").read_text(encoding="utf-8").splitlines()
              if l.startswith("Dialogue")]
    assert lineas[0].startswith("Dialogue: 0,0:00:00.00,0:00:08.00") and lineas[0].endswith("uno")
    assert lineas[1].startswith("Dialogue: 0,0:00:08.00,0:00:16.00") and lineas[1].endswith("dos")
    assert ",8," in (tmp_path / "c.ass").read_text(encoding="utf-8")  # alineación 8 = arriba al centro


def test_credito_lista_a_todos():
    c = credito_multiple([("Uno", "twitch.tv/uno"), ("Dos", "kick.com/dos"), ("Tres", "twitch.tv/tres")])
    assert c.count("·") == 3 and "kick.com/dos" in c and c.startswith("Clips de:")


# ---- panel con contenido (§3 7b) -------------------------------------------------


def test_panel_vacio_cuenta_frames_y_no_promedios():
    """PattyMeza 2026-09-23: 97-99 % negro los primeros 5 de 8 s y después se iluminaba. El brillo
    promedio daba 0,22 (nada raro); contando frames da 56 % vacíos."""
    from clips_bot.config import MultiPov
    from clips_bot.multipov import Contenido, panel_vacio

    cfg = MultiPov()
    assert panel_vacio(Contenido(vacios=0.56, brillo=0.221, frames=9), cfg.frames_vacios_max)
    # los dos peores clips reales ya renderizados: un corte a negro puntual no descalifica
    assert not panel_vacio(Contenido(vacios=0.22, frames=9), cfg.frames_vacios_max)
    assert not panel_vacio(Contenido(vacios=0.11, frames=9), cfg.frames_vacios_max)
    assert not panel_vacio(Contenido(vacios=0.0, frames=9), cfg.frames_vacios_max)
    # sin frames leídos no se decide nada (video ilegible): no se descarta por las dudas
    assert not panel_vacio(Contenido(vacios=1.0, frames=0), cfg.frames_vacios_max)


def _angulo(clip_id, vistas, tmp_path):
    from clips_bot.multipov import Angulo

    v = tmp_path / f"{clip_id}.mp4"
    v.write_bytes(b"x")
    return Angulo(clip_id, clip_id, v, vistas, inicio=0.0, fin=8.0)


def test_el_angulo_vacio_se_rescata_con_fit_blur(tmp_path, monkeypatch):
    from clips_bot import multipov
    from clips_bot.__main__ import _angulos_con_contenido
    from clips_bot.config import load_settings

    cfg = load_settings()
    a, b, c = (_angulo("a", 300, tmp_path), _angulo("b", 200, tmp_path), _angulo("c", 100, tmp_path))
    por_id = {x.clip_id: {"clip_id": x.clip_id, "layout": "split", "subtitulos_quemados": True}
              for x in (a, b, c)}

    # "b" está en negro en el split; con fit_blur (y0 = 0) se ve bien
    def medir(video, ini, fin, y0, y1, *args):
        vacio = video.stem.startswith("b") and y0 > 0
        return multipov.Contenido(vacios=0.9 if vacio else 0.0, frames=10)

    monkeypatch.setattr(multipov, "medir_panel", medir)
    monkeypatch.setattr("clips_bot.layout.detectar_caras", lambda *a, **k: (1920, 1080, [], []))
    hechos = []
    monkeypatch.setattr("clips_bot.render.renderizar",
                        lambda e, s, l, r, d: hechos.append((s.name, l.tipo)) or s.write_bytes(b"y"))

    elegidos = _angulos_con_contenido([a, b, c], por_id, cfg, 3, avisar=lambda *_: None)
    assert [x.clip_id for x in elegidos] == ["a", "b", "c"]
    assert hechos == [("fitblur_b.mp4", "fit_blur")]         # solo se rehizo el que hacía falta
    assert elegidos[1].video.name == "fitblur_b.mp4"         # y el tramo usa esa versión


def test_si_ni_con_fit_blur_hay_algo_se_reemplaza(tmp_path, monkeypatch):
    """Es el caso real: la pantalla de PattyMeza estaba en negro, no solo el panel de abajo."""
    from clips_bot import multipov
    from clips_bot.__main__ import _angulos_con_contenido
    from clips_bot.config import load_settings

    cfg = load_settings()
    a, b, c, d = (_angulo("a", 300, tmp_path), _angulo("b", 200, tmp_path),
                  _angulo("c", 100, tmp_path), _angulo("d", 50, tmp_path))
    por_id = {x.clip_id: {"clip_id": x.clip_id, "layout": "split", "subtitulos_quemados": True}
              for x in (a, b, c, d)}
    monkeypatch.setattr(multipov, "medir_panel",
                        lambda video, *args: multipov.Contenido(
                            vacios=0.9 if video.stem.endswith("b") else 0.0, frames=10))  # "b" y su fitblur_b
    monkeypatch.setattr("clips_bot.layout.detectar_caras", lambda *a, **k: (1920, 1080, [], []))
    monkeypatch.setattr("clips_bot.render.renderizar", lambda e, s, l, r, dd: s.write_bytes(b"y"))

    elegidos = _angulos_con_contenido([a, b, c, d], por_id, cfg, 3, avisar=lambda *_: None)
    assert [x.clip_id for x in elegidos] == ["a", "c", "d"]  # "b" sale, entra el siguiente del momento


def test_sin_reemplazo_no_se_arma_el_multipov(tmp_path, monkeypatch):
    from clips_bot import multipov
    from clips_bot.__main__ import _angulos_con_contenido
    from clips_bot.config import load_settings

    cfg = load_settings()
    a, b, c = (_angulo("a", 300, tmp_path), _angulo("b", 200, tmp_path), _angulo("c", 100, tmp_path))
    # todos con fit_blur: no hay panel que sacar, así que no hay rescate posible
    por_id = {x.clip_id: {"clip_id": x.clip_id, "layout": "fit_blur"} for x in (a, b, c)}
    monkeypatch.setattr(multipov, "medir_panel",
                        lambda video, *args: multipov.Contenido(
                            vacios=0.9 if video.stem == "c" else 0.0, frames=10))

    elegidos = _angulos_con_contenido([a, b, c], por_id, cfg, 3, avisar=lambda *_: None)
    assert [x.clip_id for x in elegidos] == ["a", "b"]
    assert len(elegidos) < cfg.multipov.min_angulos  # el que llama no arma nada


# ---- verificación de "mismo hecho" ------------------------------------------------


def test_superposicion_lexica():
    """Si varios cuentan el mismo hecho nombran las mismas cosas. Medido sobre los 5 grupos reales:
    el único que era de verdad el mismo momento dio 36 % y los otros cuatro 0, 2, 4 y 5 %."""
    from clips_bot.multipov import superposicion

    mismo = ["se murio el dragon no puedo creer que lo mataron entre todos",
             "mataron al dragon! el dragon esta muerto, lo lograron",
             "no puedo creer que el dragon se murio, lo mataron"]
    assert superposicion(mismo) > 0.5

    # el grupo que salió mal el 2026-09-24: menú de pausa, despedida y unos créditos
    distinto = ["Pondipedos. Tu me dices cuando regresamos, yo tambien ya fui por otro drink",
                "Ya me voy amigos, ya me voy, muchas gracias por todo de verdad",
                "Campfire Studios los constructores los builders. En memoria de Zelda"]
    assert superposicion(distinto) < 0.12

    # las muletillas no cuentan: dos clips de puro relleno no se parecen por eso
    assert superposicion(["bueno che dale vamos bien", "dale bueno vamos che muy bien"]) == 0.0
    assert superposicion(["algo"]) == 0.0          # con un solo ángulo no hay con qué comparar


def test_hacen_falta_las_dos_señales():
    """Superposición Y Gemini. La superposición se mide primero porque es gratis: si no llega, no se
    gasta una llamada."""
    from clips_bot.multipov import es_el_mismo_hecho

    class Gemini:
        def __init__(self, respuesta):
            self.respuesta, self.llamadas = respuesta, 0

        def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None):
            self.llamadas += 1
            return self.respuesta

    iguales = ["mataron al dragon entre todos", "el dragon muerto, lo mataron entre todos"]
    distintos = ["hola gente como andan", "verde azul amarillo violeta"]

    # 1) no pasa la superposición → ni se pregunta
    g = Gemini('{"mismo_hecho": true, "hecho": "x", "razon": "y"}')
    ok, det = es_el_mismo_hecho(g, ["a", "b"], distintos, 0.12)
    assert not ok and g.llamadas == 0 and "vocabulario" in det["razon"]

    # 2) pasa la superposición pero Gemini dice que no → no se arma
    g = Gemini('{"mismo_hecho": false, "hecho": "", "razon": "cada uno en la suya"}')
    ok, det = es_el_mismo_hecho(g, ["a", "b"], iguales, 0.12)
    assert not ok and g.llamadas == 1 and det["razon"] == "cada uno en la suya"

    # 3) las dos dicen que sí
    g = Gemini('{"mismo_hecho": true, "hecho": "mataron al dragon", "razon": "los dos lo cuentan"}')
    ok, det = es_el_mismo_hecho(g, ["a", "b"], iguales, 0.12)
    assert ok and det["hecho"] == "mataron al dragon"

    # 4) sin Gemini no se arma: una sola señal no alcanza
    ok, det = es_el_mismo_hecho(None, ["a", "b"], iguales, 0.12)
    assert not ok and "sin Gemini" in det["razon"]

    # 5) si Gemini contesta cualquier cosa, tampoco
    ok, _ = es_el_mismo_hecho(Gemini("no soy json"), ["a", "b"], iguales, 0.12)
    assert not ok
