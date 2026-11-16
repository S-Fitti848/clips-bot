"""Santi, 2026-11-16: el gancho de Pequeña Historia y de Así Nació dice el dato concreto más fuerte de la historia;
las fórmulas genéricas de intriga no pasan la validación."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from clips_bot import efemerides as ef  # noqa: E402
from clips_bot import locales  # noqa: E402
from clips_bot.animacion import marcas  # noqa: E402
from clips_bot.reglas import REGLA_GANCHO_CONCRETO, gancho_generico  # noqa: E402


@pytest.mark.parametrize("texto", [
    "Fusilaron a una joven por espía, y pasó algo que no esperaban.",
    "Nadie lo podía creer.",
    "Lo que pasó después te va a sorprender.",
    "No vas a creer lo que pasó en Medellín.",
    "Nadie se lo esperaba.",
    "Un pueblo vivió algo increíble.",
])
def test_las_formulas_genericas_se_detectan(texto):
    assert gancho_generico(texto)


@pytest.mark.parametrize("texto", [
    "La fusilaron a los 22 y antes gritó una frase que todavía se recuerda.",
    "Una banda terminó una canción 45 años después.",
    "¡Un limpiador de hollín se volvió juguete!",
    "Un maquinista sacó un tren con dinamita encendida del pueblo.",
])
def test_los_ganchos_concretos_pasan(texto):
    assert gancho_generico(texto) is None


def test_pequena_historia_rechaza_el_gancho_generico():
    from test_efemerides import ARTICULO, _guion_ok

    d = _guion_ok()
    d["frases"][0]["texto"] = "Un buscador nació en un armario y pasó algo que nadie esperaba."
    assert any("genérica" in e for e in ef.validar_guion(d, 1998, ARTICULO))
    assert ef.validar_guion(_guion_ok(), 1998, ARTICULO) == []
    for sistema in (ef.SISTEMA_GUION, ef.SISTEMA_GUION_CORTO, locales.SISTEMA_GUION_LOCAL, locales.SISTEMA_GUION_CORTO):
        assert REGLA_GANCHO_CONCRETO in sistema
    assert "Nadie lo esperaba" not in ef.SISTEMA_GUION


def test_asinacio_rechaza_el_gancho_generico():
    from test_animacion_marcas import guion

    d = guion()
    d["escenas"][0]["frase"] = "¡Pasó algo que nadie esperaba!"
    assert any("genérica" in e for e in marcas.validar_guion(d, marcas.cargar_catalogo()[0], ""))
    d = guion()
    d["ganchos"] = [{"tipo": "gigante", "texto": "ALGO QUE NADIE ESPERABA"},
                    {"tipo": "vuela", "texto": "VENDIÓ UN MILLÓN EN 1949"},
                    {"tipo": "explota", "texto": "¿UN JUGUETE DE JABÓN?"}]
    for e in d["escenas"][1:]:
        e["decorado"] = ["radio"]
    assert any("genéricos" in e for e in marcas.errores_v3(d))
    assert "fórmulas" in marcas.SISTEMA_GUION and "fórmulas" in marcas.SISTEMA_V3
