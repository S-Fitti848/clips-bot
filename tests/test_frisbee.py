"""Lo que salió mal en el Frisbee del 17/11 (Santi): la escena de las manos vacías en un living que la revisión no vio,
la ventana flotando en la pared, y la regla nueva de escenas únicas en los lugares de la historia real."""
import json

from clips_bot.animacion import acciones as ac, escenas as esc, marcas as mk, reemplazo as rz


def _datos_con_viajes():
    """Como el Frisbee: gancho, 4 viajes en el tiempo, el mapa y 7 escenas de la historia."""
    esc_ = [{"duracion": 2.5, "frase": 0, "gancho_v3": True}]
    for k in range(1, 8):
        if k in (1, 3, 5, 7):
            esc_.append({"duracion": 1.35, "girar": True, "congela": True})
        if k == 1:
            esc_.append({"duracion": 1.4, "fondo": {"tipo": "mapa_geo"}})
        esc_.append({"duracion": 3.0, "frase": k})
    return {"escenas": esc_}


def test_la_revision_mira_cada_escena_de_la_historia():
    claves = mk.cuadros_clave(_datos_con_viajes())
    assert [q for _, _, q in claves] == ["gancho"] + [f"escena {k + 1}" for k in range(1, 8)]
    # antes: con 8 cuadros como tope, 4 eran el reloj del viaje y la escena 4 no la miraba nadie


def test_la_revision_rechaza_manos_vacias_y_el_lugar_equivocado():
    mk.REGLAS_V3, mk.USO_V4 = True, True
    try:
        texto = mk.sistema_revision_v3() + mk.REVISION_V4
    finally:
        mk.REGLAS_V3, mk.USO_V4 = False, False
    assert "MANOS LEVANTADAS, VACÍAS" in texto and "EL LUGAR NO ES EL DE LA HISTORIA" in texto
    assert "flotando en el medio de la pared" in texto


def test_un_uso_de_solo_agarrar_no_se_vuelve_escena_de_manos():
    d = {"protagonista": {"prop": "pelota"}, "uso": {"escena": 2, "pasos": ["agarrar"]},
         "escenas": [{"frase": "a"}, {"frase": "lanzaba una tapa de lata", "fondo": "playa"}]}
    mk.preparar_uso(None, d, avisar=lambda *_: None)
    assert d["escenas"][1].get("accion_escena") != "uso_manos"


def test_la_ventana_no_es_decorado():
    spec = {"frase": "lanzaba una tapa", "parte": "idea", "fondo": "casa", "actores": [],
            "objetos": [], "decorado": ["radio", "ventana", "cuadro"]}
    d, _ = ac.escena_accion(spec, 3.0, 3)
    nombres = [el.get("nombre") for el in d["elementos"]]
    assert "ventana" not in nombres and "cuadro" not in nombres


def test_playa_estadio_y_cocina_existen():
    for f in ("playa", "estadio", "cocina"):
        assert f in mk.FONDOS and len(esc.fondo(f, ac.semilla_fondo(1950, 0))) > 2000
    assert esc.fondo("cocina", ac.semilla_fondo(1950, 0)) != esc.fondo("cocina", ac.semilla_fondo(1990, 0))


def test_la_frase_que_dice_playa_va_en_la_playa():
    d = {"escenas": [{"frase": "gancho", "fondo": "campo"},
                     {"frase": "En la playa, le pagaron 25 centavos por un molde.", "fondo": "puerto"},
                     {"frase": "Mar del Plata, una ciudad de playa.", "fondo": "ciudad"}]}
    err = mk.errores_lugar(d)
    assert len(err) == 1 and "escena 2" in err[0] and "playa" in err[0] and "escena 3" not in err[0]
    d["escenas"][1]["fondo"] = "playa"
    assert mk.errores_lugar(d) == []


def _guion(firmas):
    escenas = [{"frase": "gancho", "fondo": "campo"}]
    for f in firmas:
        acc, fondo = f.split("@")
        escenas.append({"frase": "x", "accion_escena": acc, "fondo": fondo})
    return {"escenas": escenas}


def test_como_mucho_un_tercio_repetido_de_los_ultimos_10():
    previas = [["vender_tienda@tienda", "fabrica_produce@fabrica"], ["firmar@oficina"]]
    d = _guion(["vender_tienda@tienda", "fabrica_produce@fabrica", "firmar@oficina", "cargar_barco@puerto",
                "uso_manos@cocina", "contador_ventas@oficina"])
    err = mk.errores_unicas(d, previas)
    assert err and "[2, 3, 4]" in err[0] and "como mucho 2" in err[0]
    d["escenas"][3]["fondo"] = "playa"                         # la firma en la oficina pasa a la playa
    assert mk.errores_unicas(d, previas) == []
    # solo cuentan los últimos 10 videos
    assert mk.errores_unicas(_guion(["firmar@oficina"] * 3), [["firmar@oficina"]] + [["x@y"]] * 10) == []


def test_las_escenas_de_cada_video_quedan_anotadas(tmp_path):
    from clips_bot import db

    c = db.connect(tmp_path / "c.db")
    for n in range(12):
        mk.anotar_escenas(c, _guion([f"a{n}@tienda"]), f"v{n}", "M")
    prev = mk.escenas_recientes(c)
    assert len(prev) == 10 and prev[-1] == ["a11@tienda"] and ["a0@tienda"] not in prev


def test_el_reemplazo_ya_no_tiene_tope_de_repetidas(monkeypatch, tmp_path):
    """Santi, 2026-11-20: las escenas de la biblioteca se repiten todo lo que haga falta (sin el tope de un tercio)."""
    monkeypatch.setattr(esc, "es_prop", lambda n: True)
    d = _guion(["vender_tienda@tienda", "a@fabrica", "b@campo"])
    d["protagonista"] = {"prop": "pelota"}
    monkeypatch.setattr(mk, "ESCENAS_PREVIAS", [["firmar@fabrica", "vender_tienda@tienda"]])
    cand = {"video": "otro", "marca": "Otra", "k": 2, "parte": None, "accion_escena": "firmar", "plano": "",
            "frase": "x", "spec": {"accion_escena": "firmar", "objetos": [], "actores": []}}
    llamados = []
    rz.reemplazar(object(), d, {"escenas": []}, [], 2, [], lambda d_: llamados.append(1), "v", "M", tmp_path,
                  lib=[cand], avisar=lambda *_: None)
    assert llamados          # se armó aunque repite


def test_el_estandar_tiene_la_regla_nueva():
    from clips_bot import calidad

    ids = {r.id: r for r in calidad.reglas("asinacio")}
    assert "AN-25" in ids and "biblioteca base" in ids["AN-25"].texto
    assert "playa" in ids["AN-13"].texto and "vacías" in ids["AN-06"].texto
