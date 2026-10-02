"""/permitir y /sacar_acceso (2026-10-02): solo Santi, sin tocar el .env."""

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.telegram import comandos

SANTI, TOMMY, NUEVO = "8668060171", "8824893712", "8988378175"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", f"{SANTI},{TOMMY}")
    monkeypatch.setattr("clips_bot.config.load_dotenv", lambda *a, **k: None)
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _cmd(texto, de=SANTI, responde_a=None):
    msg = {"text": texto, "chat": {"id": -5453399767, "type": "group", "title": "Rots clips"},
           "from": {"id": int(de), "first_name": "X"}}
    if responde_a:
        msg["reply_to_message"] = {"from": {"id": int(responde_a), "first_name": "Micheal",
                                            "last_name": "Lanlin"}}
    return comandos([{"update_id": 1, "message": msg}])[0]


def test_el_comando_trae_a_quien_le_respondio():
    c = _cmd("/permitir", responde_a=NUEVO)
    assert c["responde_a"] == {"id": NUEVO, "nombre": "Micheal Lanlin"}
    assert _cmd("/permitir")["responde_a"] is None


def test_permitir_respondiendo_y_sacar(conn):
    assert NUEVO not in m._permitidos(conn)
    r = m._permitir(conn, _cmd("/permitir", responde_a=NUEVO))
    assert "Micheal Lanlin" in r and NUEVO in m._permitidos(conn)
    texto, teclado = m._sacar_acceso(conn, _cmd("/sacar_acceso"))
    botones = [b["callback_data"] for f in teclado["inline_keyboard"] for b in f]
    assert f"acc:x:{NUEVO}" in botones and f"acc:x:{SANTI}" not in botones
    m._sacar_acceso(conn, _cmd("/sacar_acceso", responde_a=NUEVO))
    assert NUEVO not in m._permitidos(conn)
    m._sacar_acceso(conn, _cmd(f"/sacar_acceso {TOMMY}"))          # también los del .env
    assert TOMMY not in m._permitidos(conn) and SANTI in m._permitidos(conn)
    m._permitir(conn, _cmd(f"/permitir {TOMMY}"))
    assert TOMMY in m._permitidos(conn)


def test_solo_santi(conn):
    assert "Solo Santi" in m._permitir(conn, _cmd("/permitir", de=TOMMY, responde_a=NUEVO))
    assert NUEVO not in m._permitidos(conn)
    assert "Solo Santi" in m._sacar_acceso(conn, _cmd("/sacar_acceso", de=TOMMY, responde_a=SANTI))[0]
    assert "no te puedo sacar" in m._sacar(conn, SANTI)
    assert SANTI in m._permitidos(conn)
