"""Carpetas de streamers: los dos interruptores (en vivo, diarios), mover, crear, borrar, y que el
modo en vivo y la corrida diaria los respeten."""

import json

import pytest

import clips_bot.__main__ as m
from clips_bot import db, registro
from clips_bot.config import Streamer
from clips_bot.menu import teclado_streamers, parse_callback


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


YAML = [Streamer("spreen", "kick", grupo="argentinos", experimento=True),
        Streamer("rivers_gg", "twitch", grupo="evento", experimento=True),
        Streamer("vegetta777", "twitch", fuentes=("catalogo",), grupo="catalogo", experimento=True)]


@pytest.fixture
def lista(monkeypatch):
    monkeypatch.setattr(m, "load_streamers", lambda: list(YAML))


def test_valores_de_fabrica(conn):
    c = db.carpetas(conn)
    assert (c["argentinos"]["en_vivo"], c["argentinos"]["diarios"]) == (True, True)
    assert (c["famosos"]["en_vivo"], c["famosos"]["diarios"]) == (True, True)
    assert (c["evento"]["en_vivo"], c["evento"]["diarios"]) == (False, False)   # desde el 2026-09-28
    assert (c["catalogo"]["en_vivo"], c["catalogo"]["diarios"]) == (False, True)
    assert c["evento"]["etiqueta"] == "Dedsafío" and c["famosos"]["etiqueta"] == "Famosos"


def test_el_modo_en_vivo_solo_vigila_carpetas_con_en_vivo(conn):
    assert [s.login for s in registro.filtrar(YAML, conn, "en_vivo")] == ["spreen"]
    db.set_interruptor(conn, "evento", "en_vivo", True)
    assert [s.login for s in registro.filtrar(YAML, conn, "en_vivo")] == ["spreen", "rivers_gg"]


def test_la_corrida_diaria_saltea_carpetas_sin_diarios(conn):
    assert [s.login for s in registro.filtrar(YAML, conn, "diarios")] == ["spreen", "vegetta777"]
    db.set_interruptor(conn, "catalogo", "diarios", False)
    db.set_interruptor(conn, "evento", "diarios", True)
    assert [s.login for s in registro.filtrar(YAML, conn, "diarios")] == ["spreen", "rivers_gg"]


def test_mover_uno_del_yaml_y_despues_quitarlo_lo_saca(conn, lista):
    """Con un ALTA, /quitar solo borraba la anotación: el del YAML volvía a su carpeta."""
    s = YAML[1]
    registro.mover(conn, s, "argentinos", "7")
    assert {x.login: x.grupo for x in m._streamers(conn)}["rivers_gg"] == "argentinos"
    m._quitar(conn, ["rivers_gg"], "7")
    assert "rivers_gg" not in {x.login for x in m._streamers(conn)}


def test_mover_uno_agregado_por_telegram_sigue_siendo_alta(conn, lista):
    registro.guardar(conn, "coscu", registro.ALTA, "7", plataforma="kick", grupo="argentinos")
    coscu = next(x for x in m._streamers(conn) if x.login == "coscu")
    registro.mover(conn, coscu, "catalogo", "7")
    assert registro.anotados(conn)["coscu"]["accion"] == registro.ALTA
    assert next(x for x in m._streamers(conn) if x.login == "coscu").grupo == "catalogo"


def test_crear_carpeta_sin_tildes_ni_repetidas(conn):
    assert db.crear_carpeta(conn, "Fútbol y más") == "futbol_y_mas"
    assert db.crear_carpeta(conn, "Fútbol y más") == "futbol_y_mas_2"
    c = db.carpetas(conn)["futbol_y_mas"]
    assert c["etiqueta"] == "Fútbol y más" and not c["en_vivo"] and c["diarios"]


def test_el_menu_muestra_los_interruptores_y_borrar_solo_si_esta_vacia(conn):
    c = db.carpeta(conn, "argentinos")
    t = teclado_streamers(0, [YAML[0]], 0, {}, c)
    primera = [b["text"] for b in t["inline_keyboard"][0]]
    assert primera == ["🔴 En vivo: sí", "📅 Diarios: sí"]
    assert not any("Borrar" in b["text"] for f in t["inline_keyboard"] for b in f)
    vacia = teclado_streamers(3, [], 0, {}, db.carpeta(conn, "nueva"))
    assert any(b["callback_data"] == "st:del:3" for f in vacia["inline_keyboard"] for b in f)


class FakeTG:
    def __init__(self):
        self.editados, self.mensajes, self.respuestas = [], [], []

    def edit_message(self, chat, msg, texto, teclado=None):
        self.editados.append((texto, teclado))

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def answer_callback(self, cid, texto=""):
        self.respuestas.append(texto)


def _cb(data):
    return {"data": data, "chat_id": "1", "message_id": 5, "callback_id": "q", "user_id": "7"}


def _gi(conn, carpeta):
    grupos, _ = m._carpetas_vista(conn)
    return list(grupos).index(carpeta)


def test_tocar_los_interruptores_desde_el_menu(conn, lista):
    gi = _gi(conn, "evento")
    tg = FakeTG()
    m._menu_callback(conn, tg, _cb(f"st:v:{gi}"), None, [])
    assert db.carpeta(conn, "evento")["en_vivo"] and tg.respuestas[-1] == "🔴 En vivo: sí"
    m._menu_callback(conn, tg, _cb(f"st:d:{gi}"), None, [])
    assert db.carpeta(conn, "evento")["diarios"]          # de fábrica está apagado
    assert "📅 Diarios: sí" in tg.editados[-1][0]


def test_mover_desde_el_menu(conn, lista):
    gi, ci = _gi(conn, "evento"), _gi(conn, "argentinos")
    m._menu_callback(conn, FakeTG(), _cb(f"st:mv:{gi}:0:{ci}"), None, [])
    assert {x.login: x.grupo for x in m._streamers(conn)}["rivers_gg"] == "argentinos"


def test_carpeta_vacia_se_borra_y_una_con_gente_no(conn, lista):
    db.crear_carpeta(conn, "Vacía")
    tg = FakeTG()
    m._menu_callback(conn, tg, _cb(f"st:del:{_gi(conn, 'argentinos')}"), None, [])
    assert "vacía" in tg.respuestas[-1] and "argentinos" in db.carpetas(conn)
    m._menu_callback(conn, tg, _cb(f"st:del:{_gi(conn, 'vacia')}"), None, [])
    assert "vacia" not in db.carpetas(conn)


def test_agregar_pregunta_la_carpeta_y_acepta_una_nueva(conn, lista):
    db.set_valor(conn, "alta:0a1b2c", json.dumps({
        "grupo": None, "pedido": "coscu",
        "elegido": {"login": "coscu", "plataforma": "kick", "nombre": "Coscu", "seguidores": 1,
                    "clips_7d": 30, "extra": ""}}))
    tg = FakeTG()
    m._alta_callback(conn, tg, _cb("add:y:0a1b2c"), None)          # ✅ sin carpeta → pregunta
    texto, teclado = tg.editados[-1]
    datos = [b["callback_data"] for f in teclado["inline_keyboard"] for b in f]
    assert "¿En qué carpeta" in texto and "add:cn:0a1b2c" in datos and "add:c:0a1b2c:0" in datos
    m._alta_callback(conn, tg, _cb("add:cn:0a1b2c"), None)         # ➕ Carpeta nueva
    espera = json.loads(db.get_valor(conn, f"{m.ESPERA_CARPETA}:7"))
    m._carpeta_nueva(conn, tg, {"chat_id": "1", "user_id": "7", "texto": "Fútbol"}, espera)
    assert next(x for x in m._streamers(conn) if x.login == "coscu").grupo == "futbol"
    assert "agregado a la carpeta <b>Fútbol</b>" in tg.mensajes[-1][0]


def test_las_carpetas_nuevas_compiten_en_el_fallback():
    from datetime import datetime, timezone

    from clips_bot.config import Seleccion
    from clips_bot.seleccion import Opcion, seleccionar

    ahora = datetime.now(timezone.utc)
    ops = [Opcion("x1", "a", 100, ahora, "t", "", {}, fuente="reciente", grupo="futbol")]
    elegidos = seleccionar(ops, Seleccion(mezcla={"argentinos": 1, "catalogo": 0}), ahora)
    assert [o.clip_id for o in elegidos] == ["x1"]
