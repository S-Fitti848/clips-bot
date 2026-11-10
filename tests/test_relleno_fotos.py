"""Regla del relleno de fotos (Santi, 2026-11-09): una frase sin foto propia nunca usa la foto que
Gemini eligió para OTRA frase puntual; usa una del tema general del video o alarga la anterior.

El caso que la originó: Android (05/11). "inversores" no tenía foto y el relleno repitió los billetes
de rupias de Pexels que Gemini había elegido para "10.000 dólares en efectivo"."""

from clips_bot import efemerides, ilustrar

# Fotos: 0-2 del artículo del hecho (generales), 3 = Andy Rubin, 4 = un HTC Dream,
# 5 = billetes de rupias (Pexels, elegida SOLO para la frase de los 10.000 dólares).
BILLETES = 5
RANKINGS = [
    [3],          # 0 Andy Rubin crea Android
    [4],          # 1 el primer teléfono
    [BILLETES],   # 2 "10.000 dólares en efectivo"
    [3],          # 3 Rubin se queda sin plata
    [],           # 4 "inversores": sin foto propia
    [4],          # 5 cierre
]
DEL_HECHO = [0, 1, 2]
RESERVA = list(dict.fromkeys(DEL_HECHO + [3, 4, BILLETES]))


def test_billetes_sin_generales_libres_alarga_la_anterior():
    # Las del artículo ya salieron todas: "inversores" alarga la de la frase anterior, no los billetes.
    rk = [[0], [1], [BILLETES], [2], [], [3]]
    fotos = ilustrar.asignar(rk, RESERVA, generales=DEL_HECHO)
    assert fotos[4] == fotos[3] == 2
    assert fotos.count(BILLETES) == 1


def test_billetes_usa_una_general():
    fotos = ilustrar.asignar(RANKINGS, RESERVA, generales=DEL_HECHO)
    assert fotos[4] in DEL_HECHO
    assert fotos.count(BILLETES) == 1


def test_completar_distintas_no_mete_la_de_otra_frase():
    rk = [[0], [1], [BILLETES], [2], [], [3]]
    fotos = ilustrar.asignar(rk, RESERVA, generales=DEL_HECHO)
    fotos = ilustrar.completar_distintas(fotos, rk, RESERVA, minimo=8, generales=DEL_HECHO)
    assert fotos[4] != BILLETES
    assert fotos.count(BILLETES) == 1


def test_tramos_de_una_frase_sin_foto_larga_no_usan_la_de_otra_frase():
    rk = [[0], [1], [BILLETES], [2], [], [3]]
    fotos = ilustrar.asignar(rk, RESERVA, generales=DEL_HECHO)
    plan = ilustrar.tramos(fotos, [3, 3, 3, 3, 9, 3], rk, RESERVA, generales=DEL_HECHO)
    de_inversores = [f for i, f, _ in plan if i == 4]
    assert BILLETES not in de_inversores
    assert all(f in DEL_HECHO for f in de_inversores)
    assert not ilustrar.errores_plan(plan, minimo=4)


def test_generales_son_las_del_articulo_sin_descartadas_ni_modernas():
    g = efemerides.Guion(frases=["a"] * 6, fotos=[0] * 6, descartadas=[1], titulo="t",
                         descripcion="d", hashtags=[], ranking=RANKINGS, del_hecho=[0, 1, 2, 7],
                         modernas=[7])
    assert efemerides.generales(g) == [0, 2]


def test_plan_de_la_propuesta_respeta_la_regla():
    g = efemerides.Guion(frases=["una frase de prueba con varias palabras"] * 6,
                         fotos=ilustrar.asignar(RANKINGS, RESERVA, generales=DEL_HECHO),
                         descartadas=[], titulo="t", descripcion="d", hashtags=[],
                         ranking=RANKINGS, del_hecho=DEL_HECHO)
    plan = efemerides.plan_estimado(g, 6)
    assert BILLETES not in [f for i, f, _ in plan if i == 4]
