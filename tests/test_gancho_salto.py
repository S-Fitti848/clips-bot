"""El gancho escrito hace salto de línea (2026-11-14): con WrapStyle 2 quedaba en una línea más ancha
que la pantalla, cortado a los costados (pasaba en los videos desde el 12/11)."""

import re

from clips_bot import graficos as gr

FRASE = "Una mujer joven espió a los españoles y por eso la fusilaron."


def _lineas(ev: str) -> list[str]:
    texto = ev.split(",,0,0,0,,", 1)[1]
    return [l.strip() for l in re.sub(r"\{[^}]*\}", "", texto).split(r"\N")]


def test_los_dos_estilos_entran_en_el_ancho():
    for ev in (gr.gancho_en_pantalla(FRASE, 3.0)[0], gr.gancho_animado(FRASE, 3.0)[0]):
        lineas = _lineas(ev)
        assert len(lineas) >= 3 and all(len(l) <= gr.GANCHO_CHARS for l in lineas), lineas
        assert " ".join(lineas) == FRASE


def test_el_animado_esta_entero_antes_de_la_portada():
    [ev] = gr.gancho_animado(FRASE, 3.0)
    tiempos = [int(x) for x in re.findall(r"\\t\((\d+),\d+,\\alpha&H00&", ev)]
    assert tiempos and tiempos[-1] + 230 <= 800


def test_la_misma_foto_de_commons_no_entra_dos_veces():
    from clips_bot import efemerides as ef

    assert ef.clave_archivo("Archivo:La Pola.jpg") == ef.clave_archivo("File:La_Pola.jpg")
    assert ef.clave_archivo("https://images.pexels.com/a.jpg") != ef.clave_archivo("https://images.pexels.com/b.jpg")


def test_el_montaje_usa_solo_las_fotos_del_gancho():
    from clips_bot import efemerides as ef

    g = ef.Guion(frases=["a", "b", "c"], fotos=[0, 1, 2], descartadas=[], titulo="t", descripcion="d",
                 hashtags=[], ranking=[[0], [1, 4], [2]], corto=True)
    plan, movs = ef.plan_rapido([(0, 0, 3.0), (1, 1, 3.0), (2, 2, 3.0)], g, montaje=True)
    # Santi, 2026-11-17 (Colón): cada foto muestra lo que dice SU frase: nada de adelantos de las siguientes
    assert [f for i, f, _ in plan if i == 0] == [0] and movs[0] == "golpe"
    g.ranking = [[0, 5, 6], [1, 4], [2]]
    plan, movs = ef.plan_rapido([(0, 0, 3.0), (1, 1, 3.0), (2, 2, 3.0)], g, montaje=True)
    assert [f for i, f, _ in plan if i == 0] == [0, 5, 6] and movs[:3] == ["golpe"] * 3


def test_el_mapa_llega_cuando_se_dice_el_lugar():
    from clips_bot import efemerides as ef
    from clips_bot.subtitles import Palabra

    ps = [Palabra(5.0, 5.3, "Fue"), Palabra(5.3, 5.5, "en"), Palabra(5.5, 6.0, "1817,"),
          Palabra(6.1, 6.2, "en"), Palabra(6.2, 6.8, "Bogotá,")]
    assert ef.momento_de_palabra(ps, "Bogotá") == 6.2
    assert ef.momento_de_palabra(ps, "Lima") is None
    plan = [(0, 0, 3.0), (1, 1, 2.5), (2, 2, 3.0)]
    nuevo, movs = ef.insertar_tramo(plan, ["a", "b", "c"], 4.4, 2.3, ef.MAPA, "mapa")
    assert abs(sum(s for *_, s in nuevo) - 8.5) < 0.01                 # el largo no cambia
    k = [x[1] for x in nuevo].index(ef.MAPA)
    assert abs(sum(s for *_, s in nuevo[:k]) - 4.4) < 0.01 and nuevo[k][2] == 2.3 and movs[k] == "mapa"
    assert all(s >= 0.4 for *_, s in nuevo)
