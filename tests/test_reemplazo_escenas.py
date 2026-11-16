"""Así Nació: la escena que sigue sin pasar el estándar se reemplaza por una aprobada de la biblioteca (Santi,
2026-11-16; clips_bot/animacion/reemplazo.py)."""
import json

import pytest

from clips_bot.animacion import reemplazo as rz


def _datos(acciones):
    """Una línea de tiempo de juguete: el gancho, el viaje, y una escena por frase."""
    escenas = [{"duracion": 2.0, "frase": 0, "gancho_v3": True, "elementos": ["g"]},
               {"duracion": 1.3, "girar": True, "elementos": ["viaje"]}]
    for k, a in enumerate(acciones, start=1):
        escenas.append({"duracion": 3.0, "frase": k, "elementos": [a], "transicion": {"tipo": "corte"}})
    return {"fps": 30, "escenas": escenas, "subtitulos": [{"palabras": [{"texto": "hola", "inicio": 0, "fin": 1}]}]}


def test_empalmar_cambia_solo_el_tramo_de_esa_frase():
    viejo, nuevo = _datos(["a1", "a2", "a3"]), _datos(["X1", "nueva", "X3"])
    nuevo["escenas"][3]["transicion"] = {"tipo": "iris"}
    nuevo["subtitulos"] = [{"palabras": []}]
    sfx_v = [(0.5, "pop"), (3.5, "tac"), (6.4, "golpe"), (8.0, "ding"), (9.4, "pop")]
    sfx_n = [(6.8, "caja_registradora"), (3.4, "otro")]
    datos, sfx = rz.empalmar(viejo, sfx_v, nuevo, sfx_n, 2)
    assert [e["elementos"] for e in datos["escenas"]] == [["g"], ["viaje"], ["a1"], ["nueva"], ["a3"]]
    assert datos["escenas"][3]["transicion"] == {"tipo": "corte"}        # el empalme con la de antes, como estaba
    assert datos["subtitulos"] == viejo["subtitulos"]                     # voz y subtítulos intactos
    assert [e["duracion"] for e in datos["escenas"]] == [e["duracion"] for e in viejo["escenas"]]
    # los efectos de afuera del tramo (6.3 a 9.3) quedan; los de adentro son los de la escena nueva
    assert sfx == [(0.5, "pop"), (3.5, "tac"), (6.8, "caja_registradora"), (9.4, "pop")]


def test_empalmar_no_acepta_otra_duracion():
    viejo, nuevo = _datos(["a1", "a2"]), _datos(["a1", "b2"])
    nuevo["escenas"][3]["duracion"] = 2.5
    assert rz.empalmar(viejo, [], nuevo, [], 2) is None
    nuevo = _datos(["a1", "b2"])
    nuevo["escenas"].insert(3, {"duracion": 0.0, "frase": 2, "elementos": []})
    assert rz.empalmar(viejo, [], nuevo, [], 2) is None


def _guion():
    return {"protagonista": {"prop": "cubo_rubik"},
            "escenas": [{"frase": "gancho", "parte": "gancho"},
                        {"frase": "vendió miles en una tienda de Budapest", "parte": "que_paso", "fondo": "tienda",
                         "anio_escena": 1980, "decorado": ["mostrador"], "accion_escena": "vender_tienda",
                         "actores": [{"rol": "inventor", "genero": "hombre", "edad": "adulto",
                                      "persona_real": "Ernő Rubik", "accion": "quieto"}],
                         "objetos": [{"prop": "cubo_rubik"}]},
                        {"frase": "lo probó", "parte": "idea", "actores": []}]}


def _aprobada(marca="Lego", accion="contar_billetes", parte="que_paso", **spec):
    base = {"frase": "contó la plata", "parte": parte, "fondo": "oficina", "anio_escena": 1958,
            "accion_escena": accion, "plano": "manos",
            "actores": [{"rol": "empresaria", "genero": "mujer", "edad": "adulto", "accion": "vender"},
                        {"rol": "vecina", "genero": "mujer", "edad": "mayor", "accion": "festejar"}],
            "objetos": [{"prop": rz.OBJETO}, {"prop": "billete"}, {"prop": "ladrillo_lego_raro"}]}
    base.update(spec)
    return {"video": f"2026-11-10/{marca}/x", "marca": marca, "fecha": "2026-11-10", "k": 3, "parte": parte,
            "accion_escena": accion, "plano": "manos", "frase": base["frase"], "spec": base}


def test_adaptar_mantiene_la_continuidad_y_los_personajes(monkeypatch):
    from clips_bot.animacion import escenas as esc

    monkeypatch.setattr(esc, "es_prop", lambda n: n in ("cubo_rubik", "billete"))
    nuevo = rz.adaptar(_aprobada(), _guion(), 1)
    assert nuevo["frase"] == "vendió miles en una tienda de Budapest"
    assert (nuevo["fondo"], nuevo["anio_escena"], nuevo["decorado"]) == ("tienda", 1980, ["mostrador"])
    assert nuevo["accion_escena"] == "contar_billetes"
    assert [o["prop"] for o in nuevo["objetos"]] == ["cubo_rubik", "billete"]       # sin dibujos nuevos
    assert len(nuevo["actores"]) == 1 and nuevo["actores"][0]["persona_real"] == "Ernő Rubik"
    assert nuevo["actores"][0]["accion"] == "vender"                                  # la acción aprobada
    # una escena sin personajes usa los de la vecina
    nuevo = rz.adaptar(_aprobada(), _guion(), 2)
    assert nuevo["actores"][0]["persona_real"] == "Ernő Rubik"
    monkeypatch.setattr(esc, "es_prop", lambda n: False)
    assert rz.adaptar(_aprobada(), _guion(), 1) is None


def test_candidatas_de_otros_videos():
    lib = [_aprobada("Rubik"), _aprobada("Lego", "uso_manos"), _aprobada("Lego", "vender_tienda"),
           _aprobada("Lego"), _aprobada("Lego"), _aprobada("Nerf", "firmar", parte="idea")]
    lib[2]["plano"] = ""
    actual = _guion()["escenas"][1]
    c = rz.candidatas(lib, actual, "2026-11-17/Rubik/x", "Rubik")
    assert [(x["marca"], x["accion_escena"]) for x in c] == [("Lego", "contar_billetes"), ("Nerf", "firmar")]


def test_guardar_las_que_pasaron(tmp_path):
    ruta = tmp_path / "lib.json"
    datos = _datos(["a1", "a2"])
    claves = [(1.0, 0, "gancho"), (5.0, 2, "escena 2"), (8.0, 3, "escena 3")]
    ok = rz.escenas_que_pasaron(datos, claves, [{"cuadro": 3, "que": "parado"}])
    assert ok == {1}
    g = _guion()
    n = rz.guardar_aprobadas(g, ok, "2026-11-17/Rubik/x", "Rubik", ruta)
    lib = json.loads(ruta.read_text(encoding="utf-8"))
    assert n == 1 and lib[0]["spec"]["objetos"][0]["prop"] == rz.OBJETO and lib[0]["marca"] == "Rubik"
    rz.guardar_aprobadas(g, ok, "2026-11-17/Rubik/x", "Rubik", ruta)      # el mismo video no se duplica
    assert len(json.loads(ruta.read_text(encoding="utf-8"))) == 1


def test_reemplazar_prueba_candidatas_hasta_que_una_pasa(monkeypatch, tmp_path):
    from clips_bot.animacion import escenas as esc

    monkeypatch.setattr(esc, "es_prop", lambda n: True)
    d = _guion()
    viejo = _datos(["a1", "a2"])

    def armar(d_):
        acc = d_["escenas"][1].get("accion_escena")
        return _datos([acc, "a2"]), [(4.0, "tac")]

    vistas = []
    monkeypatch.setattr(rz, "chequear", lambda haiku, datos, k, frase, ids, carpeta, n, capturar=None: (
        vistas.append(datos["escenas"][2]["elementos"][0]) or (n == 2, "ok" if n == 2 else "parado")))
    lib = [_aprobada("Lego", "contar_billetes"), _aprobada("Nerf", "firmar")]
    r = rz.reemplazar(object(), d, viejo, [], 1, ["AN-05"], armar, "v", "Rubik", tmp_path, lib=lib)
    assert vistas == ["contar_billetes", "firmar"]
    datos, sfx, d2, texto = r
    assert datos["escenas"][2]["elementos"] == ["firmar"] and datos["escenas"][3]["elementos"] == ["a2"]
    assert d2["escenas"][1]["accion_escena"] == "firmar" and "Nerf" in texto
    # el tope de costo frena antes de probar
    d = _guion()
    assert rz.reemplazar(object(), d, viejo, [], 1, [], armar, "v", "Rubik", tmp_path, sigue=lambda: False,
                         lib=lib) is None
    assert d["escenas"][1]["accion_escena"] == "vender_tienda"


def test_lo_que_no_se_arregla_va_primero_en_las_mejoras(tmp_path):
    from clips_bot import db
    from clips_bot.animacion import marcas

    c = db.connect(tmp_path / "c.db")
    marcas._anotar_mejoras_primero(c, "2026-11-17/Tupper/x", [{"frase": 4, "reglas": ["AN-06"], "que": "manos"}])
    lista = json.loads(db.get_valor(c, marcas.MEJORAS_PRIMERO))
    assert lista[0]["reglas"] == ["AN-06"] and lista[0]["enviada"] is False


def test_el_mensaje_dice_lo_reemplazado_y_el_tope():
    from clips_bot.animacion import marcas

    r = marcas.Resultado("Tupper", "x", {c: 8 for c in marcas.CRITERIOS}, 8.0, "t", "d", [], [], "v.mp4", 35.0, "eleven",
                         estandar={"revisado": True, "fallas": [], "corregidas": [], "reemplazos": ["escena 4: reemplazada"],
                                   "sin_arreglo": [{"frase": 6, "reglas": ["AN-06"], "que": ""}], "frenado_usd": 0.53})
    t = marcas.texto_mensaje(r)
    assert "🔁 escena 4: reemplazada" in t and "escena 6: ninguna" in t and "0,53" not in t and "0.53" in t
    assert "tope US$ 0.50" in t
