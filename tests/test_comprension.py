"""Santi, 2026-11-27 (el de Sixto Rodríguez, confuso): que se entienda a la primera, una idea por frase y en orden, solo
la parte más fuerte si es enredada, y un control: Haiku lee el guion sin saber nada y dice qué entendió (PH-27)."""

import json

import pytest

from clips_bot import calidad
from clips_bot import efemerides as ef
from clips_bot.reglas import REGLAS_CLARIDAD


class Lector:
    """Haiku falso: primero dice qué entendió, después si coincide."""

    def __init__(self, coincide):
        self.coincide = list(coincide)
        self.pedidos = []

    def json(self, sistema, prompt, schema, temperatura=0.0, **k):
        self.pedidos.append((sistema, prompt))
        if sistema == ef.SISTEMA_LECTOR:
            return json.dumps({"entendi": "un cantante tocaba en escenarios", "confuso": "frase 2"})
        return json.dumps({"coincide": self.coincide.pop(0), "falta": "no se sabe por qué es famoso en Sudáfrica"})


def test_la_regla_esta_por_encima_del_estilo():
    for frase in ("POR ENCIMA DE TODAS LAS DE", "QUIÉN es", "EN ORDEN", "la parte más fuerte"):
        assert frase in REGLAS_CLARIDAD
    assert REGLAS_CLARIDAD.index("A LA PRIMERA") < REGLAS_CLARIDAD.index("chico de 15")


def test_el_lector_no_ve_la_idea_clave():
    lector = Lector([True])
    sirve, entendi, _ = ef.comprension(lector, ["a", "b"], "IDEA SECRETA")
    assert sirve and entendi
    assert "IDEA SECRETA" not in lector.pedidos[0][1]       # lee como alguien que no sabe nada
    assert "IDEA SECRETA" in lector.pedidos[1][1]


def test_si_no_se_entiende_se_reescribe(monkeypatch):
    monkeypatch.setattr(ef, "validar_guion", lambda *a, **k: [])
    pedidos = []

    class Escritor:
        def json(self, sistema, prompt, schema, **k):
            pedidos.append(prompt)
            return json.dumps({"frases": [{"texto": "f", "mostrar": "x"}], "titulo": "t", "descripcion": "d",
                               "hashtags": [], "idea_clave": "idea"})

    from clips_bot import correcciones
    monkeypatch.setattr(correcciones, "corregir",
                        lambda cliente, base, prompt, d, errores, *a: (pedidos.append(errores[0]), d)[1])
    e = ef.Evento("es", 2023, "Sixto", ["Sixto Rodríguez"])
    g = ef.escribir_guion(Escritor(), e, "art", revisar_final=False, lector=Lector([False, True]))
    assert g.frases == ["f"]
    assert any("NO SE ENTIENDE A LA PRIMERA" in p and "Sudáfrica" in p for p in pedidos)


def test_una_sola_reescritura_por_comprension(monkeypatch):
    """2026-11-28: el control tiró 5 guiones que se entendían y se comió las 4 correcciones de cada uno. Ahora se
    reescribe una vez; si la segunda versión tampoco convence, sale igual (no se pierde la historia)."""
    monkeypatch.setattr(ef, "validar_guion", lambda *a, **k: [])
    pedidos = []

    class Escritor:
        def json(self, *a, **k):
            pedidos.append(1)
            return json.dumps({"frases": [{"texto": "f", "mostrar": "x"}], "titulo": "t", "descripcion": "d",
                               "hashtags": [], "idea_clave": "idea"})

    from clips_bot import correcciones
    monkeypatch.setattr(correcciones, "corregir", lambda cliente, base, prompt, d, errores, *a: (pedidos.append(2), d)[1])
    lector = Lector([False] * 20)
    g = ef.escribir_guion(Escritor(), ef.Evento("es", 2023, "x", ["X"]), "art", revisar_final=False,
                          reintentos=1, lector=lector)
    assert g.frases == ["f"] and pedidos == [1, 2]
    assert len(lector.pedidos) == 4          # dos lecturas, nada más


def test_el_comparador_no_pide_responder_la_pregunta_final():
    for frase in ("pregunta al público", "SOLO si se equivocó", "aunque le falten"):
        assert frase in ef.SISTEMA_COINCIDE


def test_sin_lector_o_sin_respuesta_no_frena():
    assert ef.comprension(None, ["a"], "x")[0]

    class Caido:
        def json(self, *a, **k):
            raise ValueError("sin JSON")

    assert ef.comprension(Caido(), ["a"], "x")[0]


def test_el_plan_b_no_deja_un_guion_confuso():
    g = ef.Guion(frases=["Vendió más que Elvis en Sudáfrica.", "frase sin foto", "fin"], fotos=[], descartadas=[],
                 titulo="t", descripcion="d", hashtags=[], idea_clave="idea")
    g.ranking, g.del_hecho = [[0], [], [0]], [0]
    pool = [ef.Foto(archivo="File:a.jpg", url="u", ancho=1200, alto=800, licencia="CC0", autor="x",
                    epigrafe="Rodriguez on stage", pagina="p", articulo="Sixto Rodríguez")]

    class Haiku(Lector):
        def json(self, sistema, prompt, schema, temperatura=0.0, **k):
            if sistema == ef.SISTEMA_FRASE_CON_FOTO:
                return json.dumps({"frases": [{"n": 2, "frase": "Y él seguía tocando en escenarios.", "foto": 1}]})
            return super().json(sistema, prompt, schema, temperatura)

    e = ef.Evento("es", 2023, "Sixto", ["Sixto Rodríguez"])
    assert ef.reescribir_frases_con_foto(Haiku([False]), e, "seguía tocando en escenarios", g, [1], pool) is False
    assert g.frases[1] == "frase sin foto"


def test_esta_en_el_estandar():
    ids = {r.id for r in calidad.reglas("pequena_historia")}
    assert {"PH-07", "PH-27"} <= ids


def test_el_anio_de_la_historia_puede_ser_otro_del_articulo():
    """Sixto: la fecha del día era su muerte (2023) y la historia es de 1970; vale cualquier año del artículo."""
    def errores(tercera):
        d = {"frases": [{"texto": "Vendió más que Elvis en Sudáfrica y no lo sabía."},
                        {"texto": "Y en su ciudad casi nadie compraba sus discos."},
                        {"texto": tercera}, {"texto": "¡Así que dejó la música!"}, {"texto": "¿Lo sabías?"}]}
        return [e for e in ef.validar_guion(d, 2023, "Grabó Cold Fact en 1970 en Detroit.") if "el año" in e]
    assert errores("Fue en 1970, en Detroit, con su primer disco.") == []
    assert errores("Fue en 2023.") == []
    assert errores("Fue en 1985, en Detroit.") and errores("Fue en Detroit.")
