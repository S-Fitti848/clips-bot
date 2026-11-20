"""La biblioteca base de Así Nació (Santi, 2026-11-20: reusar escenas cuando sirven, crear nuevas solo si hace falta)."""

from clips_bot.animacion import acciones as ac
from clips_bot.animacion import escenas_lib as lib
from clips_bot.animacion import marcas as mk
from clips_bot.animacion import personajes as per
from clips_bot.animacion import plantillas as pl


def _armar(accion, fondo="oficina", anio=1950, prota="botella", **extra):
    ac.MANOS_V3 = True
    try:
        return ac.escena_accion({"accion_escena": accion, "fondo": fondo, "frase": "x", **extra}, 3.0, 2, anio=anio,
                                protagonista=prota)[0]
    finally:
        ac.MANOS_V3 = False


def test_las_diez_de_la_base_existen_y_se_ofrecen_al_guion_primero():
    assert len(pl.BASE) == 10 and pl.BASE[0] == "gancho" and pl.BASE[-1] == "cierre_tito"
    for k in pl.BASE[1:]:
        assert k in lib.ACCIONES, k
    texto = mk.sistema_guion()
    assert "★ taller_inventor" in texto and "POR\nDEFECTO" in texto


def test_cada_escena_tiene_gente_haciendo_algo_y_el_producto():
    for accion in pl.CONSTRUCTORES:
        d = _armar(accion)
        gente = [el for el in d["elementos"] if el.get("tipo") in ("personaje", "tito") and not el.get("multitud")]
        assert gente, accion
        assert any(el.get("nombre") == "botella" for el in d["elementos"]), accion
        for el in gente:
            if el.get("tipo") == "personaje":
                assert any(g["gesto"] != "reposo" for g in el.get("gestos") or []), (accion, "parado")


def test_traen_su_camara_y_no_la_pisa_gancho_v3():
    assert pl.CON_CAMARA <= lib.CON_CAMARA
    cam = lib.construir("crisis", "", {"frase": "x"}, 3.0, 1, "botella")["camara"]
    assert cam[0]["zoom"] >= 1.5          # plano medio: la gente grande, no el cuadro entero


def test_de_perfil_el_producto_queda_en_la_mano_de_adelante():
    d = _armar("taller_inventor")
    inv = next(el for el in d["elementos"] if el.get("tipo") == "personaje")
    prod = next(el for el in d["elementos"] if el.get("nombre") == "botella" and el.get("en_mano"))
    lx, ly = per.personaje(inv["nombre"], **inv.get("cambios", {})).mano_perfil(*per.GESTOS["p_sostener_a"]["der"])
    assert inv["perfil"] == 1
    assert abs(inv["x"] + lx * inv["escala"] - prod["x"]) < 5 and abs(ac.PISO + ly * inv["escala"] - 10 - prod["y"]) < 5


def test_la_crisis_va_de_noche_y_el_cierre_con_tito_sin_nadie_de_mas():
    assert _armar("crisis")["fondo"].get("momento") == "noche"
    d = _armar("cierre_tito", fondo="taller")
    assert any(el.get("tipo") == "tito" for el in d["elementos"])
    assert not [el for el in d["elementos"] if el.get("tipo") == "personaje" and not el.get("multitud")]


def test_en_uso_una_bebida_se_lleva_a_la_boca():
    d = _armar("producto_en_uso", fondo="cocina", _categoria="bebidas")
    p0 = next(el for el in d["elementos"] if el.get("tipo") == "personaje")
    assert p0["gestos"][0]["gesto"] == "p_tomar_a"
    d = _armar("producto_en_uso", fondo="cocina", _categoria="juguetes", prota="pelota")
    p0 = next(el for el in d["elementos"] if el.get("tipo") == "personaje")
    assert p0["gestos"][0]["gesto"] == "p_sostener_a"


def test_un_dibujo_guardado_mide_como_uno_de_codigo():
    assert pl.esc_de("fiel_cualquiera", 150) > pl.esc_de("botella", 150)
    assert abs(ac.factor_tam("botella") * (230 + 262) - ac.factor_tam("fiel_x") * 300) < 1


def test_un_cartel_generico_no_se_redibuja_para_todos():
    class Cli:
        def json(self, *a, **k):
            raise AssertionError("no tenía que dibujar")
    assert mk.redibujar_objeto(Cli(), "cartel", "un cartel de LEY SECA") == ""
    assert mk.redibujar_objeto(Cli(), "mesa", "otra mesa") == ""


def test_se_pueden_repetir_escenas_de_otros_videos(monkeypatch):
    monkeypatch.setattr(mk, "ESCENAS_PREVIAS", [["vender_tienda@tienda", "fabrica_produce@fabrica"]] * 10)
    d = {"escenas": [{"accion_escena": "vender_tienda", "fondo": "tienda", "frase": "lo vendían"},
                     {"accion_escena": "fabrica_produce", "fondo": "fabrica", "frase": "lo fabricaban"}] * 3}
    assert not [x for x in mk.errores_lugar(d) if "único" in x]
    assert "un tercio" not in mk.sistema_guion()
