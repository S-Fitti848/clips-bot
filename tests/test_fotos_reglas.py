"""Imágenes de Pequeña Historia (2026-10-02): relevancia dura, sin capturas de páginas, cada frase
busca otra cosa y ninguna imagen más de 2 veces."""

from clips_bot import efemerides as ef, ilustrar


def test_ninguna_foto_aparece_mas_de_2_veces_si_hay_otra():
    # 8 frases de 3 s, solo 2 fotos rankeadas para todas y un pool de 4
    rankings = [[0, 1]] * 8
    fotos = ilustrar.asignar(rankings, [0, 1, 2, 3])
    plan = ilustrar.tramos(fotos, [3.0] * 8, rankings, [0, 1, 2, 3])
    assert max(ilustrar.apariciones(plan).values()) <= 2
    assert not [e for e in ilustrar.errores_plan(plan, 4) if "aparecen" in e]


def test_si_no_alcanzan_lo_dice():
    plan = [(0, 0, 3.0), (1, 1, 3.0), (2, 0, 3.0), (3, 1, 3.0), (4, 0, 3.0)]
    assert ilustrar.apariciones(plan) == {0: 3, 1: 2}
    assert any("la 1 (3)" in e for e in ilustrar.errores_plan(plan, 2))
    seguidas = [(0, 0, 3.0), (1, 0, 2.0), (2, 1, 3.0)]          # la misma foto seguida = 1 aparición
    assert ilustrar.apariciones(seguidas) == {0: 1, 1: 1}


def test_si_gemini_no_esta_seguro_la_foto_sale():
    d = {"frases": [{"se_ve": "x", "fotos": [1, 2], "de_epoca": True, "seguro": False},
                    {"se_ve": "y", "fotos": [2], "de_epoca": True, "seguro": True}], "descartadas": []}
    rankings, _ = ef.rankings_de(d, [[0, 1], [0, 1]])
    assert rankings == [[1], [1]]


def test_dos_frases_con_el_mismo_mostrar_no_pasan():
    base = {"texto": "Un día como hoy, en 1924, pasó algo con Onzari.", "mostrar": "1924 Cesáreo Onzari Argentina",
            "presente": False}
    d = {"frases": [base, {**base, "texto": "¡Fue un gol olímpico!", "mostrar": "1924 Onzari Argentina Cesareo"}],
         "idea_clave": "x", "titulo": "t", "descripcion": "d", "hashtags": ["#Shorts", "#a", "#b"]}
    errores = ef.validar_guion(d, 1924, "Onzari 1924 gol olímpico Argentina Cesáreo")
    assert any("buscan lo mismo" in e and "1 y 2" in e for e in errores)


def test_las_capturas_de_paginas_solo_para_frases_que_hablan_de_una_pagina():
    assert ef._CAPTURA.search("File:4chan screenshot.png") and ef._CAPTURA.search("Página de Facebook del ejército")
    assert not ef._CAPTURA.search("File:Cesareo Onzari 1924.jpg")
    assert ef._HABLA_DE_WEB.search("En 2003 nació el foro 4chan") and not ef._HABLA_DE_WEB.search("Hizo un gol olímpico")
