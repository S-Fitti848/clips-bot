"""Santi, 2026-11-24: reintentos inteligentes (arreglar lo que falló antes de pasar a otra historia), 5 intentos por día
de la reserva dentro del tope de US$ 2,50, el banco de tecnología con marcas y videojuegos que tienen fotos libres
(sin Claude) y el resumen de fallas de los viernes."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

from clips_bot import banco, db, fallas, reserva_tec
from clips_bot import efemerides as ef


class WikiFalsa:
    def en_ingles(self, t):
        return {"Walkman": "Walkman"}.get(t, "Sony Walkman")


def test_consultas_de_una_frase_usan_el_nombre_en_ingles_y_el_anio_nunca_lo_generico_solo():
    e = ef.Evento("es", 1979, "Sony lanza el Walkman", ["Walkman_(Sony)"])
    g = SimpleNamespace(frases=["El primer TPS-L2 pesaba casi 400 gramos"], claves=["TPS-L2"],
                        mostrar=["1979 portable cassette player Japan"], objeto=["cassette player"])
    qs = ef.consultas_frase(WikiFalsa(), e, g, 0)
    assert "Sony Walkman TPS-L2" in qs and "Sony Walkman 1979" in qs and "Sony Walkman cassette player" in qs
    assert "Walkman TPS-L2" in qs                       # el título sin el paréntesis
    assert "cassette player" not in qs                  # una foto de banco no es ESE producto
    assert "portable cassette player Japan" in qs       # lo que muestra la frase, sin el año


def _g():
    return SimpleNamespace(descartadas=[], mostrar=["a"], tarjetas=[])


def test_primero_arregla_las_fotos_y_recien_despues_reescribe_y_anota_lo_intentado(monkeypatch):
    llamadas = []

    def fotos_para_guion(wiki, cliente, e, g, fotos, carpeta, avisar, **k):
        llamadas.append(k)
        if k.get("puntual") is not None:
            k["puntual"][2] = (["Sony Walkman 1979"], 3)
        raise ef.FotosInsuficientes([], _g(), 0.5 + 0.05 * len(llamadas))

    monkeypatch.setattr(ef, "fotos_para_guion", fotos_para_guion)
    monkeypatch.setattr(ef, "frases_flojas", lambda g, pool: [2])
    reescritas = []

    def reescribir(g, idxs, pool, forzadas):
        reescritas.append(idxs)
        return True

    with pytest.raises(ef.FotosInsuficientes) as err:
        ef.fotos_con_control(None, None, None, _g(), [], None, lambda *_: None, reescribir=reescribir)
    assert not llamadas[0].get("segunda")
    assert llamadas[1]["segunda"] and llamadas[1]["flojas"] == [2]      # la búsqueda puntual de la frase floja
    assert reescritas == [[2]] and len(llamadas) == 3                    # recién después, el plan B
    intentos = err.value.intentos
    assert intentos[0].startswith("1.ª búsqueda") and "Sony Walkman 1979" in intentos[1]
    assert "reescritas las frases [3]" in intentos[2] and "con las frases reescritas" in intentos[3]


def test_si_la_segunda_busqueda_alcanza_no_se_reescribe(monkeypatch):
    n = []

    def fotos_para_guion(*a, **k):
        n.append(k)
        if not k.get("segunda"):
            raise ef.FotosNoAlcanzan([], _g(), ["hay 5 fotos distintas"])
        return ["pool"], "guion"

    monkeypatch.setattr(ef, "fotos_para_guion", fotos_para_guion)
    monkeypatch.setattr(ef, "frases_flojas", lambda g, pool: [0])
    assert ef.fotos_con_control(None, None, None, _g(), [], None, lambda *_: None,
                                reescribir=lambda *a: pytest.fail("no hacía falta")) == (["pool"], "guion")


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table bot_estado (clave text primary key, valor text)")
    conn.execute("create table gemini_uso (dia text, funcion text, modelo text, clave text, entrada int, salida int, "
                 "origen text)")
    return conn


def test_reserva_hasta_5_intentos_y_dentro_del_tope_del_dia(monkeypatch):
    from clips_bot import claude

    monkeypatch.setattr(claude, "costo", lambda m, e, s: e / 1000)
    conn, hoy = _conn(), date(2026, 11, 24)
    for _ in range(4):
        reserva_tec.anotar_falla(conn, hoy)
    assert reserva_tec.hay_que_armar(conn, 3, hoy, "12:00")
    reserva_tec.anotar_falla(conn, hoy)
    assert not reserva_tec.hay_que_armar(conn, 3, hoy, "12:00")          # 5 intentos fallidos: hasta mañana
    conn2 = _conn()
    conn2.execute("insert into gemini_uso values ('2026-11-24','f','m','claude',2200,0,'produccion')")
    assert not reserva_tec.hay_que_armar(conn2, 3, hoy, "12:00")         # 2,20 + 0,35 > 2,50


def test_banco_solo_marcas_y_videojuegos_con_fotos_libres(monkeypatch):
    eventos = {"es": [ef.Evento("es", 1989, "Nintendo lanza la Game Boy en Japón", ["Game_Boy"]),
                      ef.Evento("es", 1979, "Sony presenta el walkman", ["Walkman"]),
                      ef.Evento("es", 1876, "Bell patenta un aparato nuevo", ["Alexander_Graham_Bell"])],
               "en": []}
    wiki = SimpleNamespace(eventos=lambda lang, dia: eventos[lang])
    vistos = []

    def elegir(cliente, cands, tema="", notas=None):
        vistos.extend(c.texto for c in cands)
        for i in range(len(cands)):
            notas[i] = {"puntaje": 9.0, **{k: 9 for k in ef.CRITERIOS_TEC}}
        return [(i, c.paginas[0]) for i, c in enumerate(cands)]

    monkeypatch.setattr(ef, "elegir", elegir)
    fotos = {"Game_Boy": 9, "Walkman": 3}
    out = banco.cosechar_tecnologia(wiki, None, date(2027, 3, 1), avisar=lambda *_: None,
                                    contar_fotos=lambda ev: fotos[ev.paginas[0]])
    assert "Bell patenta un aparato nuevo" not in vistos                 # ni se puntúa: no es marca ni videojuego
    assert [x["articulo"] for x in out] == ["Game_Boy"]                  # el Walkman, con 3 fotos libres, no entra
    assert out[0]["fotos_libres"] == 9 and out[0]["subtema"] == "videojuegos"


def test_fotos_libres_cuenta_otras_fuentes_solo_si_hace_falta(monkeypatch):
    monkeypatch.setattr(ef, "fotos_del_evento", lambda wiki, e: ([], {}))
    monkeypatch.setattr(ef, "fotos_previas", lambda wiki, e, f: 4)
    fuente = SimpleNamespace(
        openverse=lambda q: [{"archivo": f"o{i}", "url": "u", "licencia": "CC0", "epigrafe": "Game Boy"} for i in range(1)],
        flickr=lambda q: [{"archivo": "f1", "url": "u", "licencia": "CC BY 2.0", "epigrafe": "logo de Nintendo"},
                          {"archivo": "f2", "url": "u", "licencia": "CC BY 2.0", "epigrafe": "Game Boy 1989"}],
        archive=lambda q: pytest.fail("ya alcanzaba"))
    e = ef.Evento("en", 1989, "Game Boy", ["Game_Boy"])
    assert ef.fotos_libres(SimpleNamespace(), e, 6, fuentes=fuente) == 6     # el logo no cuenta
    monkeypatch.setattr(ef, "fotos_previas", lambda wiki, e, f: 7)
    assert ef.fotos_libres(SimpleNamespace(), e, 6, fuentes=None) == 7


def test_resumen_de_fallas_del_viernes():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table candidatos_descartados (n integer primary key, video_id text, bot text, canal text, "
                 "formato text, dia text, ts text, candidato text, paso text, motivo text, costo_usd real, "
                 "detalle text)")
    filas = [("2026-11-23", "AlphaGo", "fotos", "solo 40 % del tiempo con fotos reales (mínimo 70 %)", 0.09, "{}"),
             ("2026-11-24", "Bell", "fotos", "solo 57 % del tiempo con fotos reales (mínimo 70 %)", 0.12,
              json.dumps({"intentos": ["1.ª búsqueda: 50 %", "2.ª búsqueda: 57 %"]})),
             ("2026-11-24", "Motorola", "guion", "El guion no pasó la validación: la estructura no está en orden", 0.16, "{}"),
             ("2026-11-24", "Alibaba", "puntaje", "puntaje 5.75 < 8.5", 0.001, "{}"),
             ("2026-11-10", "Viejo", "fotos", "otra semana", 1.0, "{}")]
    conn.executemany("insert into candidatos_descartados (dia, formato, candidato, paso, motivo, costo_usd, detalle, "
                     "bot, canal, ts) values (?, 'tecnologia_reserva', ?, ?, ?, ?, ?, 'clips', 'pequena_historia', '')",
                     filas)
    t = fallas.resumen(conn, date(2026, 11, 27))
    primeras = t.splitlines()[:3]
    assert "3 historias caídas" in primeras[0] and "US$ 0,37" in primeras[0]
    assert "fotos" in primeras[1] and "2 veces" in primeras[1]          # los dos % se agrupan
    assert "Bell: 1.ª búsqueda: 50 % → 2.ª búsqueda: 57 %" in t
    assert "Alibaba" not in t and "Viejo" not in t
    assert fallas.toca(date(2026, 11, 27), "10:05", None) and not fallas.toca(date(2026, 11, 27), "10:05", "2026-11-27")
    assert not fallas.toca(date(2026, 11, 26), "10:05", None)


def test_banco_de_tecnologia_con_el_minimo_del_video_del_dia():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table bot_estado (clave text primary key, valor text)")
    assert banco.agregar(conn, "tecnologia", [{"id": "tec:a", "articulo": "a", "puntaje": 7.5},
                                              {"id": "tec:b", "articulo": "b", "puntaje": 7.25}]) == 1
    assert banco.agregar(conn, "latam", [{"id": "latam:a", "articulo": "a", "puntaje": 7.5}]) == 0


def test_reserva_acepta_60_a_69_por_ciento_solo_si_pasa_todo_lo_demas():
    falla = [{"id": "PH-05", "que": "x"}]
    assert reserva_tec.entrada(0.66, [], True) == (True, "⚠️ fotos 66 %")
    assert reserva_tec.entrada(0.66, [{"id": "PH-21"}], True) == (True, "⚠️ fotos 66 %")   # PH-21 es la de las fotos
    assert reserva_tec.entrada(0.66, falla, True) == (False, "")
    assert reserva_tec.entrada(0.66, [], False) == (False, "")      # sin revisión no se sabe si pasa lo demás
    assert reserva_tec.entrada(0.59, [], True) == (False, "")
    assert reserva_tec.entrada(0.80, falla, True) == (True, "")     # con 70 % o más, el estándar de siempre


def test_la_propuesta_de_la_reserva_no_baja_de_60():
    g = SimpleNamespace(umbral_fotos=0, fotos_reales=0)
    assert not ef.aceptar_relajado(ef.FotosInsuficientes([], g, 0.56), lambda *_: None, piso=0.60)
    assert ef.aceptar_relajado(ef.FotosInsuficientes([], g, 0.62), lambda *_: None, piso=0.60)
    assert g.umbral_fotos == 0.6
