"""Santi, 2026-11-25: el banco como fuente normal de tecnología (A), la verificación que reintenta lo técnico y solo
las 3 mejores (C) y el informe de las 09:00 con "% al primer intento" y "gastado en reintentos" (D)."""
from __future__ import annotations

import sqlite3

import pytest

from clips_bot import banco, db, fallas
from clips_bot import web_historias as wh


def test_el_banco_de_tecnologia_se_repone_debajo_de_20():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table bot_estado (clave text primary key, valor text)")
    banco.guardar(conn, "tecnologia", [{"id": f"tec:{i}"} for i in range(19)])
    assert banco.hay_que_reponer(conn, "tecnologia")
    banco.guardar(conn, "tecnologia", [{"id": f"tec:{i}"} for i in range(25)])
    assert not banco.hay_que_reponer(conn, "tecnologia")
    banco.guardar(conn, "latam", [{"id": f"l:{i}"} for i in range(12)])
    assert not banco.hay_que_reponer(conn, "latam")


class WebFalso:
    def __init__(self, fallas_):
        self.fallas, self.tokens = list(fallas_), []

    def pedir(self, sistema, prompt, busquedas, lecturas=0, max_tokens=16000):
        self.tokens.append(max_tokens)
        if self.fallas:
            raise wh.WebError(self.fallas.pop(0))
        return ('```json\n{"es_real": true, "resumen": "r", "datos": ['
                + ",".join('{"dato": "d%d", "fuentes": ["https://a.com/x", "https://b.org/y"]}' % i for i in range(3))
                + ']}\n```', [])


def test_la_verificacion_cortada_se_reintenta_una_vez_con_mas_lugar():
    w = WebFalso(["búsqueda web: la respuesta terminó con max_tokens"])
    assert wh.verificar(w, "t", 1907, "Nacozari", "México").ok and w.tokens == [16000, 32000]
    w = WebFalso(["búsqueda web: la respuesta terminó con max_tokens"] * 2)
    with pytest.raises(wh.WebError):
        wh.verificar(w, "t", 1907, "Nacozari", "México")
    w = WebFalso(["búsqueda web (haiku): 529 overloaded"])
    with pytest.raises(wh.WebError):                       # lo que no es técnico de la respuesta, no se reintenta
        wh.verificar(w, "t", 1907, "Nacozari", "México")
    assert w.tokens == [16000]


def test_lineas_del_informe(tmp_path):
    from clips_bot import bitacora

    conn = db.connect(tmp_path / "t.db")
    bitacora.asegurar_tabla(conn)
    conn.executemany("INSERT INTO videos_registro (id, bot, canal, formato, dia, inicio, estado, costo_usd) VALUES "
                     "(?, 'clips', 'pequena_historia', ?, '2026-11-24', '', ?, ?)",
                     [("a", "tecnologia", "retenido", 0.2), ("b", "latinoamerica", "retenido", 0.3),
                      ("c", "tecnologia_reserva", "descartado", 0.18), ("d", "tecnologia_reserva", "reserva", 0.4)])
    conn.executemany("INSERT INTO candidatos_descartados (dia, formato, candidato, paso, motivo, costo_usd, bot, canal, "
                     "ts) VALUES ('2026-11-24', ?, ?, ?, 'm', ?, 'clips', 'pequena_historia', '')",
                     [("latinoamerica", "Popeye", "fotos", 0.12), ("latinoamerica", "Popeye", "fotos", 0.10),
                      ("latinoamerica", "Avellaneda", "verificacion", 0.02), ("latinoamerica", "X", "puntaje", 0.0),
                      ("tecnologia_reserva", "Kaspárov", "otro", 0.0)])
    conn.commit()
    l1, l2 = fallas.lineas_informe(conn, "2026-11-24", 1.71)
    assert l1 == "Al primer intento: 50 % (tecnología 1/1 · Latinoamérica 1/3 · reserva 1/2)"
    assert l2 == "Gastado en reintentos: US$ 0,42 de US$ 1,71"
