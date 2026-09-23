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
