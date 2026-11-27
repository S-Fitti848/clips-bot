"""Plan B (Santi, 2026-11-21): el 20 y el 21/11 no salió ni tecnología ni Latinoamérica porque "la frase 1 no tiene
ninguna foto posible" era un ValueError que cortaba toda la propuesta. Ahora la frase se reescribe para hablar de
algo con foto; si no se puede, es un NarrarError (el hecho siguiente y después el banco)."""
import json

import pytest

from clips_bot import efemerides as ef


def _g():
    return ef.Guion(titulo="t", descripcion="d", hashtags=[], frases=[
        "Un ingeniero cambió la forma de usar las computadoras.", "En 1985, Microsoft lanzó Windows.",
        "Tenía calculadora y Paint."], fotos=[], descartadas=[], mostrar=["a", "b", "c"])


def _pool():
    return [ef.Foto(archivo="File:Windows_1.0.png", url="", ancho=900, alto=700, licencia="CC0", autor="a",
                    epigrafe="Pantalla de Windows 1.0 (1985)", pagina="", articulo="Windows 1.0", anio=1985)]


class Cli:
    def __init__(self, frase):
        self.frase, self.n = frase, 0

    def json(self, sistema, prompt, schema, **k):
        if sistema == ef.SISTEMA_LECTOR:       # el control de comprensión (PH-27): se entiende
            return json.dumps({"entendi": "Microsoft lanzó Windows", "confuso": ""})
        if sistema == ef.SISTEMA_COINCIDE:
            return json.dumps({"coincide": True, "falta": ""})
        self.n += 1
        assert "FOTOS DISPONIBLES" in prompt and "Pantalla de Windows 1.0" in prompt
        return json.dumps({"frases": [{"n": 1, "frase": self.frase, "mostrar": "1985 Windows 1.0 screen",
                                       "foto": 1}]})


def test_reescribe_solo_la_frase_sin_foto():
    g = _g()
    g.ranking, g.del_hecho = [[], [0], [0]], [0]
    fuente = "Microsoft lanzó Windows 1.0 en 1985 con una pantalla de ventanas, calculadora y Paint."
    ok = ef.reescribir_frases_con_foto(Cli("La primera pantalla de ventanas de Microsoft traía calculadora y Paint."),
                                       ef.Evento("es", 1985, "Windows 1.0", ["Windows 1.0"]), fuente, g, [0], _pool(),
                                       avisar=lambda *_: None)
    assert ok and g.frases[0].startswith("La primera pantalla") and g.mostrar[0] == "1985 Windows 1.0 screen"
    assert g.frases[1] == "En 1985, Microsoft lanzó Windows."


def test_no_acepta_datos_que_no_estan_en_el_articulo():
    g = _g()
    g.ranking, g.del_hecho = [[], [0], [0]], [0]
    ok = ef.reescribir_frases_con_foto(Cli("Bill Gates vendió 40 millones de copias en Tokio."),
                                       ef.Evento("es", 1985, "Windows 1.0", ["Windows 1.0"]),
                                       "Microsoft lanzó Windows 1.0 en 1985.", g, [0], _pool(), avisar=lambda *_: None)
    assert not ok and g.frases[0].startswith("Un ingeniero")


def test_fotos_con_control_usa_el_plan_b_y_si_no_sigue_como_narrarerror(monkeypatch, tmp_path):
    llamadas = []

    def fpg(wiki, cliente, e, g, fotos, carpeta, avisar, **k):
        llamadas.append(k.get("pool"))
        if len(llamadas) == 1:
            raise ef.FraseSinFoto(_pool(), g, [0])
        return _pool(), g

    monkeypatch.setattr(ef, "fotos_para_guion", fpg)
    e = ef.Evento("es", 1985, "Windows 1.0", ["Windows 1.0"])
    pool, g = ef.fotos_con_control(object(), None, e, _g(), [], tmp_path, lambda *_: None,
                                   reescribir=lambda g_, idx, p_, forz=None: True)
    assert len(llamadas) == 2 and llamadas[1] is not None
    llamadas.clear()
    with pytest.raises(ef.NarrarError):           # sin plan B posible: el hecho siguiente (no un ValueError)
        ef.fotos_con_control(object(), None, e, _g(), [], tmp_path, lambda *_: None,
                             reescribir=lambda g_, idx, p_, forz=None: False)
