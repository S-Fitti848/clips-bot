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
