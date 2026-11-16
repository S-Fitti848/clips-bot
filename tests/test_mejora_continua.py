"""Así Nació, mejora continua (Santi, 2026-11-16): lo más flojo de cada video con su cuadro, cruzado con las
estadísticas de 24 h, y los lunes y jueves las 5 mejoras al motor por impacto (al menos una del gancho)."""

import json
from datetime import datetime

from PIL import Image

from clips_bot import __main__ as m
from clips_bot import db
from clips_bot import stats_fb as sf
from clips_bot.config import load_settings


class _TG:
    def __init__(self):
        self.mensajes, self.fotos = [], []

    def send_message(self, chat, texto, *a, **k):
        self.mensajes.append(texto)

    def send_photo(self, chat, path, caption="", *a, **k):
        self.fotos.append((str(path), caption))


class _Cli:
    def __init__(self, *resps):
        self.resps, self.pedidos = list(resps), []

    def json(self, sistema, prompt, schema, temp=0.7, imagenes=None, **k):
        self.pedidos.append((prompt, len(imagenes or [])))
        return json.dumps(self.resps.pop(0))


def _mejora(cat, img=1):
    return {"mejora": f"mejorar {cat}", "por_que": "se van en el segundo 3", "imagen": img, "categoria": cat}


def test_lunes_y_jueves_las_5_mejoras_con_cuadro_y_una_del_gancho(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    png = tmp_path / "revision_1.png"
    Image.new("RGB", (40, 60), "red").save(png)
    db.set_valor(conn, m.ASINACIO_FLOJAS, json.dumps({"asinacio_20261116": {
        "fecha": "2026-11-16", "titulo": "Play-Doh", "flojas": [{"categoria": "accion", "que": "nadie amasa", "cuadro": str(png)}]}}))
    db.set_valor(conn, sf.CLAVE, json.dumps({"v": {"canal": "facebook_asinacio", "clip_id": "asinacio_20261116",
                                                    "vistas": 230, "pasa_3s": 80.0, "ret_10": 36.0}}))
    sin_gancho = {"mejoras": [_mejora("accion")] * 5}
    con_gancho = {"mejoras": [_mejora("gancho"), _mejora("accion"), _mejora("objeto", 9), _mejora("camara"), _mejora("texto")]}
    cli, tg = _Cli(sin_gancho, con_gancho), _TG()
    s = load_settings()
    m._mejoras_motor_tick(conn, tg, s, ahora=datetime(2026, 11, 17, 11, 0, tzinfo=m.AR), cliente=cli)   # martes
    assert not tg.mensajes and not cli.pedidos
    m._mejoras_motor_tick(conn, tg, s, ahora=datetime(2026, 11, 19, 9, 0, tzinfo=m.AR), cliente=cli)    # jueves, temprano
    assert not cli.pedidos
    m._mejoras_motor_tick(conn, tg, s, ahora=datetime(2026, 11, 19, 10, 5, tzinfo=m.AR), cliente=cli)
    assert len(cli.pedidos) == 2 and "gancho" in cli.pedidos[1][0]     # sin una del gancho, se vuelve a pedir
    assert "24 h en Facebook: 230 rep." in cli.pedidos[0][0] and cli.pedidos[0][1] == 1
    assert tg.mensajes[0].startswith("🔧 Claude Code:") and len(tg.fotos) == 4 and len(tg.mensajes) == 2
    assert tg.fotos[0][0] == str(png) and "mejorar gancho" in tg.fotos[0][1]
    m._mejoras_motor_tick(conn, tg, s, ahora=datetime(2026, 11, 19, 15, 0, tzinfo=m.AR), cliente=cli)  # una vez por día
    assert len(cli.pedidos) == 2
    assert json.loads(db.get_valor(conn, m.MEJORAS))[0]["mejoras"][0]["categoria"] == "gancho"


def test_el_resumen_de_24h_muestra_lo_mas_flojo():
    x = {"vistas": 200, "interaccion": 2, "reacciones": 2, "comentarios": 0, "compartidos": 0,
         "flojas": [{"categoria": "gancho", "que": "el producto no se reconoce"}]}
    assert "Lo más flojo según la revisión: gancho: el producto no se reconoce" in sf.texto("facebook_asinacio", x, [], True)
