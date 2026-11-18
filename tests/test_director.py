"""Así Nació: escenas con sentido (Santi, 2026-11-18): el director escribe qué ve el espectador y se corrigen solo las
escenas que no se entienden sin la voz."""
import json

from clips_bot.animacion import director, marcas as mk


def _guion():
    return {"protagonista": {"prop": "celular", "que_es": "Twitter"},
            "escenas": [{"frase": "Jack Dorsey creó Twitter en 2006.", "fondo": "oficina", "anio_escena": 2006,
                         "actores": [{"rol": "inventor", "accion": "fabricar"}],
                         "objetos": [{"prop": "celular", "soporte": "mano", "efecto": "quieto"}]},
                        {"frase": "Las ventas bajaron.", "fondo": "oficina", "anio_escena": 2008,
                         "actores": [{"rol": "empresario", "accion": "senalar"}], "objetos": []}]}


class Director:
    def __init__(self):
        self.prompts = []

    def json(self, sistema, prompt, schema, temp=0.3, **k):
        self.prompts.append((sistema, prompt))
        return json.dumps({"escenas": [
            {"frase": 1, "que_ve": "Jack en una computadora de tubo de 2006, zoom a la primera página de Twitter",
             "se_entiende": False, "problema": "manos sobre un celular: no se entiende que crea un sitio",
             "cambio": "computadora de la época con zoom a la pantalla"},
            {"frase": 2, "que_ve": "un empresario agarrándose la cabeza frente al papel de ventas, lámpara de mesa",
             "se_entiende": True, "problema": "", "cambio": ""}]})


def test_el_director_deja_la_nota_y_marca_las_que_no_se_entienden():
    d = _guion()
    c = Director()
    malas = director.dirigir(c, d, mk.describir, "Twitter", 2006)
    assert [m["frase"] for m in malas] == [0]
    assert "computadora de tubo" in d["escenas"][0]["que_ve"] and "lámpara" in d["escenas"][1]["que_ve"]
    sistema, _ = c.prompts[0]
    assert "NO unas manos sobre un celular" in sistema and "smartphone con botón en 2006" in sistema
    assert "NO SE ENTIENDE SIN LA VOZ" in director.errores_para_corregir(malas)[0]


def test_la_regla_va_en_el_prompt_del_guion():
    assert "REGLA 18" in mk.sistema_guion() and "lámpara de mesa" in mk.sistema_guion()


def test_la_ficha_lleva_lo_que_tiene_que_verse():
    d = _guion()
    d["escenas"][0]["que_ve"] = "Jack en una computadora de 2006"
    t = mk.texto_ficha(mk.ficha_escena(d["escenas"][0], d))
    assert "TIENE QUE VERSE (director): Jack en una computadora de 2006" in t
    assert "TIENE QUE VERSE" in mk.REVISION_FICHA


def test_se_corrige_solo_si_valida(monkeypatch):
    from clips_bot import correcciones

    d = _guion()
    e = mk.Elegido(marca=mk.Marca("Twitter", "EE.UU.", "internet", "Twitter", ()), angulo=list(mk.ANGULOS)[0], notas={})
    nuevo = json.loads(json.dumps(d))
    nuevo["escenas"][0]["objetos"] = [{"prop": "computadora", "soporte": "mesa", "efecto": "quieto"}]
    monkeypatch.setattr(correcciones, "corregir", lambda *a, **k: json.loads(json.dumps(nuevo)))
    monkeypatch.setattr(mk, "validar_guion", lambda *a, **k: [])
    r = mk.dirigir_escenas(Director(), d, e, "texto")
    assert r["escenas"][0]["objetos"][0]["prop"] == "computadora" and "computadora de tubo" in r["escenas"][0]["que_ve"]
    # si la corrección trae un error que bloquea, queda como estaba
    monkeypatch.setattr(mk, "validar_guion", lambda g, *a, **k: ["dato que no está en el artículo: 1999"]
                        if g["escenas"][0]["objetos"][0]["prop"] == "computadora" else [])
    monkeypatch.setattr(mk, "bloquea", lambda x: "dato" in x)
    r = mk.dirigir_escenas(Director(), _guion(), e, "texto")
    assert r["escenas"][0]["objetos"][0]["prop"] == "celular"
