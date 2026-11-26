"""Santi, 2026-11-26, después de la prueba de fotos primero: (1) un dato que no está en el artículo se corrige
reescribiendo solo esa frase (Goycochea se cayó porque "Nápoles", el lugar que la regla exige nombrar, no estaba en
el artículo: se sacaba y se volvía a pedir hasta el tope); (2) antes de 1970 alcanzan 6 fotos buenas."""

import json

import pytest

from clips_bot import efemerides as ef
from clips_bot import fotos_primero as fp


def test_el_dato_sin_respaldo_dice_en_que_frase_esta():
    d = {"frases": [{"texto": "Atajó dos penales."}, {"texto": "Fue en 1990, en Nápoles, contra Italia."}]}
    errores = []
    faltan = ef.no_respaldados(" ".join(f["texto"] for f in d["frases"]), "Atajó dos penales contra Italia en 1990.",
                               1990)
    assert faltan == ["Nápoles"]
    # el mensaje completo de validar_guion
    errores = ef.validar_guion({"frases": d["frases"], "titulo": "t", "descripcion": "d", "hashtags": [],
                                "idea_clave": "x"}, 1990, "Atajó dos penales contra Italia en 1990.")
    msg = next(e for e in errores if "NO está en el artículo" in e)
    assert "Nápoles (frase 2)" in msg and "solo esas frases" in msg


def test_el_lugar_de_la_historia_cuenta_como_respaldo(monkeypatch):
    vistos = []

    def validar(d, anio, fuente, **k):
        vistos.append(fuente)
        return ["otro error"]

    monkeypatch.setattr(ef, "validar_guion", validar)

    class _C:
        def json(self, *a, **k):
            return json.dumps({"frases": [{"texto": "x"}]})

    e = ef.Evento(lang="es", anio=1990, texto="Goycochea ataja", paginas=["Sergio Goycochea"])
    with pytest.raises(ef.NarrarError):
        ef.escribir_guion(_C(), e, "artículo", reintentos=0, respaldo="Lugar: Nápoles (Campania, Italia).",
                          revisar_final=False)
    assert vistos and all("Nápoles" in f for f in vistos)
    assert ef.no_respaldados("Fue en Nápoles.", "artículo\nLugar: Nápoles (Campania, Italia).", 1990) == []


def test_antes_de_1970_alcanzan_6_fotos():
    assert fp.minimo_para(1911) == 6
    assert fp.minimo_para(1969) == 6
    assert fp.minimo_para(1970) == fp.MINIMO == 8
    assert fp.minimo_para(None) == 8
    assert "mínimo 6" in str(fp.FotosPrevias(5, {"borrosa": 3}, minimo=6))
