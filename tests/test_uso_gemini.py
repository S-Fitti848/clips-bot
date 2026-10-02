"""Cuota de Gemini (2026-10-02): medir llamadas y tokens por función, imágenes de 384 px como
máximo, y caché de respuestas a pedidos idénticos."""

import io
import json

from PIL import Image

import clips_bot.__main__ as m
from clips_bot import db, gemini
from clips_bot.gemini import GeminiClient

OK = {"candidates": [{"content": {"parts": [{"text": "{\"ok\": 1}"}]}}],
      "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 40}}


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._p


class Sesion:
    def __init__(self):
        self.cuerpos = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.cuerpos.append(json)
        return Resp(200, OK)


def _jpeg(lado):
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado // 2), (200, 30, 30)).save(buf, "JPEG")
    return buf.getvalue()


def puntuar(cliente):          # el nombre de la función es lo que se anota
    return cliente.json("s", "p", {}, imagenes=[_jpeg(1280), _jpeg(300)])


def test_achica_las_imagenes_y_anota_funcion_y_tokens(tmp_path):
    usos, s = [], Sesion()
    c = GeminiClient("K", "flash", session=s, sleep=lambda _: None, uso=lambda *a: usos.append(a))
    puntuar(c)
    partes = s.cuerpos[0]["contents"][0]["parts"]
    tamanos = [Image.open(io.BytesIO(__import__("base64").b64decode(p["inlineData"]["data"]))).size
               for p in partes[1:]]
    assert tamanos == [(384, 192), (300, 150)]
    assert usos == [("test_uso_gemini.puntuar", "flash", "principal", 1200, 40, False)]


def test_un_pedido_identico_sale_de_la_cache(tmp_path):
    usos, s = [], Sesion()
    c = GeminiClient("K", "flash", session=s, sleep=lambda _: None, uso=lambda *a: usos.append(a),
                     cache_dir=tmp_path / "cache")
    assert c.json("s", "p", {}) == c.json("s", "p", {}) == '{"ok": 1}'
    assert len(s.cuerpos) == 1 and usos[-1][2:] == ("", 0, 0, True)
    c.json("s", "otro prompt", {})
    assert len(s.cuerpos) == 2                       # distinto pedido: llama
    sin_cache = GeminiClient("K", "flash", session=s, sleep=lambda _: None)
    sin_cache.json("s", "p", {})
    assert len(s.cuerpos) == 3                       # sin cache_dir no guarda nada


def test_el_resumen_por_dia_y_funcion(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.anotar_gemini(conn, "textos.generar", "flash", "principal", 3000, 200)
    db.anotar_gemini(conn, "textos.generar", "flash", "segunda", 2800, 180)
    db.anotar_gemini(conn, "efemerides.elegir_fotos", "flash", "principal", 9000, 500)
    db.anotar_gemini(conn, "textos.generar", "cache", "", 0, 0, True)
    filas = db.uso_gemini(conn, 3)
    assert [(f[1], f[2], f[3], f[5]) for f in filas] == [("efemerides.elegir_fotos", 1, 9000, 0),
                                                       ("textos.generar", 2, 5800, 1)]
    t = m._texto_uso_gemini(conn)
    assert "3 llamadas" in t and "textos.generar: 2 · 5.800/380 · 1 de caché" in t


def test_los_clips_mandan_3_imagenes_chicas():
    from clips_bot.config import load_settings
    from clips_bot.media import frames_jpeg
    import inspect

    assert load_settings().textos.frames_para_puntaje == 3
    assert inspect.signature(frames_jpeg).parameters["ancho"].default <= gemini.IMAGEN_MAX_PX
