"""2026-11-01: Brunenger seguía saliendo en los diarios después de moverlo a una carpeta sin diarios
(los clips YA procesados se elegían igual). Y "📅 En diarios: sí/no" por streamer, aparte de la carpeta."""
import json
from types import SimpleNamespace

import clips_bot.__main__ as m
from clips_bot import db, registro
from clips_bot.config import Streamer
from clips_bot.menu import teclado_streamer

BRUNE = Streamer("brunenger", plataforma="kick", experimento=True, grupo="extra")
DAVO = Streamer("davooxeneize", plataforma="kick", experimento=True, grupo="argentinos")


def _conn(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT OR REPLACE INTO carpetas (nombre, etiqueta, en_vivo, diarios) VALUES ('extra', 'Extra', 0, 0)")
    conn.execute("INSERT OR REPLACE INTO carpetas (nombre, etiqueta, en_vivo, diarios) VALUES ('argentinos', 'Argentinos', 1, 1)")
    conn.commit()
    return conn


def test_el_interruptor_del_streamer_le_gana_a_la_carpeta(tmp_path):
    conn = _conn(tmp_path)
    assert [s.login for s in registro.filtrar([BRUNE, DAVO], conn, "diarios")] == ["davooxeneize"]
    registro.poner_diarios(conn, "brunenger", True)        # carpeta sin diarios, pero él sí
    registro.poner_diarios(conn, "DavooXeneize", False)    # carpeta con diarios, pero él no
    assert [s.login for s in registro.filtrar([BRUNE, DAVO], conn, "diarios")] == ["brunenger"]
    # en vivo no cambia: sigue siendo de la carpeta
    assert [s.login for s in registro.filtrar([BRUNE, DAVO], conn, "en_vivo")] == ["davooxeneize"]


def test_los_ya_procesados_de_alguien_fuera_de_diarios_no_se_eligen(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(m, "_streamers", lambda c=None: [BRUNE, DAVO])
    ops = [SimpleNamespace(streamer="brunenger"), SimpleNamespace(streamer="davooxeneize"),
           SimpleNamespace(streamer="Pequeña Historia")]          # uno que no es streamer: se queda
    assert [o.streamer for o in m._fuera_de_diarios(conn, ops)] == ["davooxeneize", "Pequeña Historia"]
    registro.poner_diarios(conn, "brunenger", True)
    assert len(m._fuera_de_diarios(conn, ops)) == 3


def test_boton_en_diarios_en_el_menu_del_streamer():
    filas = teclado_streamer(0, 1, 0, diarios=False)["inline_keyboard"]
    boton = next(b for f in filas for b in f if b["text"].startswith("📅"))
    assert boton["text"] == "📅 En diarios: no" and ":dd:" in boton["callback_data"]
    assert any(b["text"] == "📅 En diarios: sí" for f in teclado_streamer(0, 1, 0)["inline_keyboard"] for b in f)


def test_tocar_el_boton_lo_cambia(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(m, "_streamers", lambda c=None: [BRUNE, DAVO])
    editados = []

    class TG:
        def answer_callback(self, cid, texto=""):
            pass

        def edit_message(self, chat, msg, texto, teclado):
            editados.append(teclado)

    grupos, _ = m._carpetas_vista(conn)
    gi = list(grupos).index("extra")
    cb = {"callback_id": "c", "chat_id": "1", "message_id": 5, "user_id": "8668060171",
          "data": f"st:dd:{gi}:0"}
    m._menu_callback(conn, TG(), cb, None, [])
    assert registro.en_diarios(conn, BRUNE) is True
    textos = [b["text"] for f in editados[-1]["inline_keyboard"] for b in f]
    assert "📅 En diarios: sí" in textos
