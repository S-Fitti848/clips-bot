"""Santi, 2026-11-27 (los dos videos de la fundación de Apple: la reserva la armó el 26/11 con el artículo "Apple" y la
del día el 27/11 con "Apple_Inc."): nunca dos videos de la misma historia, ni el mismo día ni en la misma semana,
sumando producción, reserva, banco y pruebas; una historia que se usa en una prueba queda reservada."""

import json
from datetime import date, timedelta

import clips_bot.__main__ as m
from clips_bot import banco, db
from clips_bot import efemerides as ef
from clips_bot import historias_usadas as hu

HOY = date(2026, 11, 27)


def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def _prop(art, anio, texto="x"):
    return ef.Propuesta(fecha=HOY.isoformat(), evento={"lang": "es", "anio": anio, "texto": texto, "paginas": [art]},
                        fotos=[], reserva=[], guion={})


def test_apple_y_apple_inc_son_la_misma_historia():
    assert hu.nucleo("Apple_Inc.") == hu.nucleo("Apple") == hu.nucleo("Apple Computer, Inc.") == "apple"
    assert hu.nucleo("Super_Mario_Bros.") == hu.nucleo("Super Mario Bros. (videojuego)")
    assert hu.misma(hu.entrada("Apple", 1976), hu.entrada("Apple_Inc.", 1976))
    assert not hu.misma(hu.entrada("Apple", 1976), hu.entrada("IPod", 2001), marca=False)
    assert not hu.misma(hu.entrada("IMac", 1998), hu.entrada("Apple", 1976), marca=False)


def test_la_misma_marca_tampoco_en_la_semana(tmp_path):
    """Santi, 2026-11-28: el 27/11 la fundación de Apple, el 28/11 el iPhone y la reserva probaba el iPod."""
    assert "Apple" in hu.marcas_de("IPhone")
    assert "Apple" in hu.marcas_de("se estrena el reproductor de audio iPod, de la empresa Apple")
    assert hu.misma(hu.entrada("Apple_Inc.", 1976), hu.entrada("IPhone", 2007, "Apple presenta el iPhone"))
    assert not hu.misma(hu.entrada("Walkman", 1979), hu.entrada("IPhone", 2007))
    c = _conn(tmp_path)
    with hu.activo(c, HOY, "produccion"):
        _prop("Apple_Inc.", 1976, "se funda Apple")
    with hu.activo(c, HOY + timedelta(days=1), "reserva"):
        assert hu.bloqueada(ef.Evento("es", 2001, "se estrena el iPod, de Apple", ["IPod"]), "IPod")
        assert hu.bloqueada(ef.Evento("es", 1979, "Sony presenta el Walkman", ["Walkman"]), "Walkman") == ""


def test_reservada_toda_la_semana_por_cualquier_origen(tmp_path):
    c = _conn(tmp_path)
    with hu.activo(c, HOY - timedelta(days=1), "reserva"):
        _prop("Apple", 1976)                                    # la reserva del 26/11
    ev = ef.Evento("en", 1976, "Steve Jobs and Steve Wozniak found Apple Computer, Inc.", ["Apple_Inc."])
    with hu.activo(c, HOY, "produccion"):
        assert "ya se usó" in hu.bloqueada(ev, "Apple_Inc.")    # la del día del 27/11 ya no puede
    with hu.activo(c, HOY + timedelta(days=5), "produccion"):
        assert hu.bloqueada(ev, "Apple_Inc.")
    with hu.activo(c, HOY + timedelta(days=6), "produccion"):
        assert hu.bloqueada(ev, "Apple_Inc.") == ""             # pasada la semana, sí
    assert hu.bloqueada(ev, "Apple_Inc.") == ""                 # sin registro activo no se mira


def test_una_prueba_reserva_la_historia_para_la_produccion(tmp_path):
    c = _conn(tmp_path)
    with hu.activo(c, HOY, "prueba"):
        _prop("Sixto_Rodríguez", 2023)
    with hu.activo(c, HOY, "produccion"):
        assert "prueba" in hu.bloqueada(ef.Evento("es", 2023, "Sixto", ["Sixto Rodríguez"]), "Sixto Rodríguez")


def test_usarla_saca_a_sus_mellizas_del_banco(tmp_path):
    c = _conn(tmp_path)
    banco.guardar(c, "tecnologia", [
        {"id": "a", "anio": 1976, "articulo": "Apple", "texto": "se funda Apple", "paginas": ["Apple"]},
        {"id": "b", "anio": 2001, "articulo": "IPod", "texto": "iPod", "paginas": ["IPod"]}])   # otra historia: se queda
    with hu.activo(c, HOY, "produccion"):
        _prop("Apple_Inc.", 1976)
    assert [x["id"] for x in banco.leer(c, "tecnologia")] == ["b"]


def test_siembra_lo_de_antes_de_la_regla(tmp_path):
    c = _conn(tmp_path)
    estado = {"propuesta": {"fecha": "2026-11-26", "evento": {"anio": 1976, "texto": "Apple", "paginas": ["Apple"]}}}
    db.set_valor(c, "efe:abc", json.dumps(estado))
    db.set_valor(c, "ph_latam:2026-11-25", json.dumps([{"texto": "Elián", "articulo": "Elián González"}]))
    with hu.activo(c, HOY, "produccion"):
        assert hu.bloqueada(ef.Evento("en", 1976, "Apple", ["Apple_Inc."]), "Apple_Inc.")
        assert hu.bloqueada(ef.Evento("es", 1999, "Elián", ["Elián González"]), "Elián González")


def test_todas_las_propuestas_pasan_por_el_registro():
    """Producción, reserva, Latinoamérica, los comandos a mano y el script de pruebas."""
    from pathlib import Path

    fuente = Path(m.__file__).read_text(encoding="utf-8")
    assert fuente.count("_registrado(") >= 6
    for linea in fuente.splitlines():
        if ".proponer(ef.Wiki()" in linea:
            assert "_registrado(" in linea, linea
    script = (Path(m.__file__).parents[1] / "scripts" / "prueba_fotos_primero.py").read_text(encoding="utf-8")
    assert "proponer(ef.Wiki()" not in script.replace("m._registrado(conn, locales.proponer)(ef.Wiki()", "") \
        .replace("m._registrado(conn, ef.proponer)(ef.Wiki()", "")
