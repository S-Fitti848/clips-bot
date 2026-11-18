"""Tope duro de costo de Así Nació (Santi, 2026-11-18: el Atari costó US$ 3,43): US$ 1,50 por video contando todo."""
import json
import sqlite3
from datetime import date

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.animacion import marcas as mk
from test_animacion_marcas import TgFalso, _ahora, _settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _uso(c, entrada, salida, n=1):
    for _ in range(n):
        c.execute("INSERT INTO gemini_uso (ts, dia, funcion, modelo, clave, entrada, salida) VALUES "
                  "('2026-11-18T10:00', '2026-11-18', 'x', 'claude-sonnet-5-5', 'claude', ?, ?)", (entrada, salida))
    c.commit()


def test_tope_de_1_20():
    assert mk.TOPE_USD_VIDEO == 1.20


def test_pasado_el_tope_se_frena(conn):
    _uso(conn, 1000, 1000)
    mk._PRESUPUESTO.update(conn=conn, fila=mk.ultima_fila_uso(conn))
    assert not mk.pasado_tope()
    _uso(conn, 100_000, 100_000, n=2)            # ~US$ 2,40 de Sonnet
    assert mk.gastado() > 1.5 and mk.pasado_tope()


def test_el_guion_no_prueba_mas_pasado_el_tope(conn, monkeypatch):
    mk._PRESUPUESTO.update(conn=conn, fila=0)
    monkeypatch.setattr(mk, "pasado_tope", lambda: True)
    pedidos = []

    class C:
        def json(self, *a, **k):
            pedidos.append(1)
            return json.dumps({"frases": []})

    monkeypatch.setattr(mk, "validar_guion", lambda *a, **k: ["algo"])
    e = mk.Elegido(marca=mk.Marca("Atari", "EE.UU.", "juguetes", "Atari", ()), angulo=list(mk.ANGULOS)[0],
                   notas={})
    mk.escribir_guion(C(), e, "texto", reintentos=8)      # sale el mejor que hubo, con el estilo pendiente
    assert len(pedidos) == 1


def test_al_tope_y_debajo_del_estandar_hoy_no_sale_con_una_linea(conn):
    tg = TgFalso()
    llamadas = []

    def armar(c, tg_, chats, settings, hoy, k=0, **kw):
        llamadas.append(k)
        if k == 0:
            raise mk.TopeCosto("llegó al tope de US$ 1.50 (US$ 1.62) con el estándar 14/19: hoy no sale")

    m._animacion_tick(conn, tg, _settings(), _ahora("07:00"), armar=armar)
    texto = tg.mensajes[-1][1]
    assert texto.startswith("💸 Así Nació") and "hoy no sale" in texto and "\n" not in texto
    m._animacion_tick(conn, tg, _settings(), _ahora("08:30"), armar=armar)      # sin reintento del primero
    assert llamadas == [0, 1]
