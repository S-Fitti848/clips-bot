"""/buscar y /streamers con botones (2026-09-29): período (7, 30, viejos, 🔥) y cantidad (1, 3, 5).
Si el comando ya trae todo, no se pregunta nada."""

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.menu import LIMITE_CALLBACK, teclado_cantidad, teclado_periodo, teclado_streamer
from clips_bot.telegram import que_falta_buscar, sacar_modo


@pytest.mark.parametrize("args,falta", [
    (["spreen"], (True, True)),
    (["spreen", "30"], (False, True)),
    (["spreen", "x5"], (True, False)),
    (["spreen", "30", "x5"], (False, False)),          # todo en el comando: no pregunta
    (["spreen", "viejos", "x3"], (False, False)),
    (["spreen", "pego"], (False, True)),
    (["davoo", "12", "de", "octubre"], (False, False)),  # con palabras, lo de siempre
    ([], (False, False)),
])
def test_que_falta(args, falta):
    assert que_falta_buscar(args) == falta


def test_sacar_modo():
    assert sacar_modo(["spreen", "viejos", "x3"]) == (["spreen", "x3"], "viejos")
    assert sacar_modo(["spreen", "🔥"]) == (["spreen"], "pego")
    assert sacar_modo(["spreen", "gol"]) == (["spreen", "gol"], None)


def test_los_botones_entran_en_64_bytes():
    for t in (teclado_periodo("abc123"), teclado_cantidad("abc123"), teclado_streamer(99, 99, 9)):
        for fila in t["inline_keyboard"]:
            for b in fila:
                assert len(b["callback_data"].encode()) <= LIMITE_CALLBACK
    textos = [b["text"] for f in teclado_periodo("t")["inline_keyboard"] for b in f]
    assert textos == ["Últimos 7 días", "Últimos 30 días", "Viejos (más de 30 días)",
                      "🔥 Lo que pegó en otros canales"]
    assert [b["text"] for b in teclado_cantidad("t")["inline_keyboard"][0]] == ["1", "3", "5"]


class TG:
    def __init__(self):
        self.mensajes, self.editados = [], []

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def edit_message(self, chat, msg, texto, teclado=None):
        self.editados.append((texto, teclado))

    def answer_callback(self, cid, texto=""):
        pass


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _cb(data):
    return {"data": data, "chat_id": "1", "message_id": 5, "callback_id": "q", "user_id": "7"}


def _datos(teclado):
    return [b["callback_data"] for f in teclado["inline_keyboard"] for b in f]


def test_buscar_a_secas_pregunta_periodo_y_despues_cantidad(conn, monkeypatch):
    encolados = []
    monkeypatch.setattr(m, "_encolar_busqueda", lambda conn, tg, chat, args, s, cola: encolados.append(args))
    monkeypatch.setattr(m, "_pesado", lambda *a, **k: pytest.fail("no tenía que arrancar todavía"))
    tg = TG()
    m._despachar(conn, tg, {"comando": "/buscar", "args": ["spreen"], "chat_id": "1", "usuario": "s",
                            "user_id": "7"}, None, [])
    texto, teclado = tg.mensajes[-1]
    assert "¿de cuándo?" in texto
    viejos = next(d for d in _datos(teclado) if d.endswith(":viejos"))
    m._buscar_callback(conn, tg, _cb(viejos), None, [])
    assert "¿cuántos videos?" in tg.editados[-1][0]
    cinco = next(d for d in _datos(tg.editados[-1][1]) if d.endswith(":5"))
    m._buscar_callback(conn, tg, _cb(cinco), None, [])
    assert encolados == [["spreen", "viejos", "x5"]]
    m._buscar_callback(conn, tg, _cb(cinco), None, [])   # el mismo botón otra vez: ya venció
    assert len(encolados) == 1


def test_buscar_completo_no_pregunta(conn, monkeypatch):
    corridas = []
    monkeypatch.setattr(m, "_pesado", lambda conn, tg, chat, comando, args, s, u="": corridas.append(args))
    tg = TG()
    m._despachar(conn, tg, {"comando": "/buscar", "args": ["spreen", "30", "x5"], "chat_id": "1",
                            "usuario": "s", "user_id": "7"}, None, [])
    assert corridas == [["spreen", "30", "x5"]] and not tg.mensajes


def test_en_streamers_el_periodo_lleva_a_la_cantidad(conn, monkeypatch):
    from clips_bot.config import Streamer

    monkeypatch.setattr(m, "load_streamers",
                        lambda: [Streamer("spreen", "kick", grupo="argentinos", experimento=True)])
    encolados = []
    monkeypatch.setattr(m, "_encolar_busqueda", lambda conn, tg, chat, args, s, cola: encolados.append(args))
    tg = TG()
    gi = list(m._carpetas_vista(conn)[0]).index("argentinos")
    m._menu_callback(conn, tg, _cb(f"st:b:{gi}:0:pego"), None, [])
    assert "¿cuántos videos?" in tg.editados[-1][0]
    tres = next(d for d in _datos(tg.editados[-1][1]) if d.endswith(":3"))
    m._buscar_callback(conn, tg, _cb(tres), None, [])
    assert encolados == [["spreen", "pego", "x3"]]


def test_modo_pego_usa_solo_lo_que_pego(conn, monkeypatch):
    from clips_bot.config import Streamer, load_settings

    st = Streamer("spreen", "kick", grupo="argentinos", experimento=True)
    llamados = []
    def pegados_para(s, sts, buscar_ahora, avisar=None, forzar=False, recuentos=None):
        llamados.append(forzar)
        rec = __import__("clips_bot.pego", fromlist=["x"]).Recuento("spreen", resultados=25, cortos=21)
        recuentos.append(rec)
        return []

    monkeypatch.setattr(m, "_pegados_para", pegados_para)
    monkeypatch.setattr(m, "_candidatos_viejos", lambda *a: pytest.fail("no es viejos"))
    tg = TG()
    r = m._buscar(conn, tg, "1", ["spreen", "pego", "x3"], load_settings(), [st], None)
    assert llamados == [True] and "en lo que pegó en otros canales" in r   # busca aunque esté apagado
    assert "paso por paso" in tg.mensajes[0][0] and "YouTube dio 25 Shorts" in tg.mensajes[0][0]
