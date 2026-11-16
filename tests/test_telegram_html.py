"""Santi, 2026-11-16: el informe de costo de las 09:00 no salió ("can't parse entities: Unsupported start tag
'module'"): un nombre de función "__main__.<module>" en el texto. Todo mensaje se escapa antes de mandarse y,
si Telegram igual no lo puede leer, se reenvía como texto plano."""

from clips_bot.telegram import TelegramClient, html_a_texto, html_seguro


class _Resp:
    def __init__(self, js):
        self._js = js

    def json(self):
        return self._js


class _Sesion:
    def __init__(self, respuestas):
        self.respuestas, self.pedidos = list(respuestas), []

    def post(self, url, data=None, files=None, timeout=None):
        self.pedidos.append(dict(data or {}))
        return _Resp(self.respuestas.pop(0))


OK = {"ok": True, "result": {"message_id": 1}}
MAL = {"ok": False, "error_code": 400, "description": "Bad Request: can't parse entities: Unsupported start tag"}


def test_escapa_lo_que_no_es_etiqueta_y_deja_las_de_telegram():
    t = html_seguro('• __main__.<module>: <b>US$ 1</b> a&b &amp; 3 < 5 <a href="u">x</a> <pre>a &lt; b</pre>')
    assert "&lt;module&gt;" in t and "<b>US$ 1</b>" in t and "a&amp;b &amp; 3 &lt; 5" in t
    assert '<a href="u">x</a>' in t and "<pre>a &lt; b</pre>" in t


def test_el_informe_con_module_sale():
    s = _Sesion([OK])
    TelegramClient("t", session=s).send_message("1", "<b>Costo</b>\n• __main__.<module>: US$ 0,10")
    assert "&lt;module&gt;" in s.pedidos[0]["text"] and s.pedidos[0]["parse_mode"] == "HTML"


def test_si_igual_no_parsea_va_como_texto_plano():
    s = _Sesion([MAL, OK])
    TelegramClient("t", session=s).send_message("1", "<b>hola</b> <i>sin cerrar")
    assert len(s.pedidos) == 2 and "parse_mode" not in s.pedidos[1]
    assert s.pedidos[1]["text"] == "hola sin cerrar"


def test_editar_tambien_escapa():
    s = _Sesion([OK])
    TelegramClient("t", session=s).edit_message("1", 5, "paso <render>")
    assert s.pedidos[0]["text"] == "paso &lt;render&gt;"


def test_a_texto():
    assert html_a_texto("<b>a</b> &lt;module&gt;") == "a <module>"
