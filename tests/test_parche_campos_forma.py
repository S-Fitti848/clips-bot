"""2026-11-19, 07:05: la corrección puntual del guion de Toys "R" Us trajo `dibujos_nuevos` como lista de textos y
`errores_protagonista` se cayó con "'str' object has no attribute 'get'": Así Nació no salió."""
import json

from clips_bot import correcciones
from clips_bot.animacion import marcas


def _guion():
    return {"escenas": [{"texto": "Hoy abre hasta en aeropuertos"}],
            "dibujos_nuevos": [{"nombre": "avion", "descripcion": "un avión de línea"}],
            "entidades": [{"nombre": "Macy's", "presentacion": "una cadena de tiendas"}]}


def test_campo_con_textos_no_rompe_el_guion():
    parche = {"cambios": [], "sacar": [],
              "campos": [{"campo": "dibujos_nuevos", "valor": json.dumps(["aeropuerto", "avion"])},
                         {"campo": "entidades", "valor": json.dumps(["Macy's"])}]}
    d = correcciones.aplicar(_guion(), parche, "escenas", marcas.schema_guion())
    assert all(isinstance(x, dict) for x in d["dibujos_nuevos"])
    assert all(isinstance(x, dict) for x in d["entidades"])
    marcas.errores_protagonista(d)          # antes: AttributeError


def test_con_forma():
    lista_obj = {"type": "ARRAY", "items": {"type": "OBJECT"}}
    assert correcciones.con_forma(["a", {"nombre": "b"}], lista_obj) == [{"nombre": "b"}]
    assert correcciones.con_forma({"nombre": "b"}, lista_obj) == [{"nombre": "b"}]
    assert correcciones.con_forma("texto", lista_obj) is None
    assert correcciones.con_forma("x", {"type": "STRING"}) == "x"


def test_lectores_ignoran_textos_sueltos():
    d = {"escenas": [], "dibujos_nuevos": ["aeropuerto"], "entidades": ["Macy's"]}
    marcas.errores_protagonista(d)
