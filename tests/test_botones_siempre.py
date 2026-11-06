"""2026-11-05: el video de Pequeña Historia ("La increíble historia del nacimiento de Android")
llegó SIN botones: el mensaje pasaba de 4096 caracteres (Telegram: "message is too long") porque el
autor de una foto de Commons traía el CSS de Wikipedia. Ahora: el mensaje largo se parte, los
botones van en el último pedazo, se verifica que hayan quedado, y los créditos salen sin CSS."""
import re

from clips_bot import efemerides as ef
from clips_bot.telegram import MAX_MENSAJE, TelegramError, mandar_con_botones, partir_html

TECLADO = {"inline_keyboard": [[{"text": "📤 Subir", "callback_data": "sub:u:x"}]]}


class TG:
    """Telegram falso: rechaza lo que pasa de 4096 como el de verdad, y puede 'perder' los botones."""

    def __init__(self, pierde_botones=False, falla_edicion=False):
        self.enviados, self.editados = [], []
        self.pierde, self.falla_edicion = pierde_botones, falla_edicion

    def send_message(self, chat, texto, teclado=None):
        if len(texto) > 4096:
            raise TelegramError("sendMessage: 400 Bad Request: message is too long")
        self.enviados.append((texto, teclado))
        r = {"message_id": len(self.enviados)}
        if teclado and not self.pierde:
            r["reply_markup"] = teclado
        return r

    def edit_reply_markup(self, chat, mid, teclado):
        if self.falla_edicion:
            raise TelegramError("editMessageReplyMarkup: 400")
        self.editados.append((mid, teclado))


def _largo():
    creditos = "\n".join(f"{i}. Autor {i} — CC BY-SA 4.0 — https://commons.wikimedia.org/wiki/File:Foto_{i}.jpg"
                         for i in range(80))
    return f"<b>#1 · Pequeña Historia</b>\n\n<b>Descripción:</b>\n<pre>Android.\n\n{creditos}</pre>\n\n⚠️ <b>Subir en PRIVADO</b>"


def test_un_mensaje_largo_se_parte_con_el_html_bien_cerrado():
    pedazos = partir_html(_largo())
    assert len(pedazos) > 1 and all(len(p) <= MAX_MENSAJE for p in pedazos)
    for p in pedazos:
        for tag in ("pre", "b"):
            assert len(re.findall(f"<{tag}>", p)) == len(re.findall(f"</{tag}>", p)), p[:80]
    assert "".join(pedazos).count("Foto_79") == 1


def test_los_botones_van_en_el_ultimo_pedazo_aunque_sea_largo():
    tg = TG()
    mandar_con_botones(tg, "1", _largo(), TECLADO, "#1 · Android")
    assert len(tg.enviados) > 1
    assert [t is not None for _, t in tg.enviados] == [False] * (len(tg.enviados) - 1) + [True]


def test_si_quedo_sin_botones_se_los_pone_y_si_no_puede_van_aparte():
    tg = TG(pierde_botones=True)
    mandar_con_botones(tg, "1", "hola", TECLADO, "#1 · Android")
    assert tg.editados == [(1, TECLADO)]
    tg = TG(pierde_botones=True, falla_edicion=True)
    mandar_con_botones(tg, "1", "hola", TECLADO, "#1 · Android")
    assert tg.enviados[-1] == ("🔘 Botones de #1 · Android", TECLADO)


def test_si_el_mensaje_no_sale_van_los_botones_solos():
    class Roto(TG):
        def send_message(self, chat, texto, teclado=None):
            if texto.startswith("🔘"):
                return super().send_message(chat, texto, teclado)
            raise TelegramError("sendMessage: 400 Bad Request: can't parse entities")

    tg = Roto()
    mandar_con_botones(tg, "1", "<b>roto", TECLADO, "#1 · Android")
    assert tg.enviados == [("🔘 Botones de #1 · Android", TECLADO)]


def test_el_autor_de_commons_sale_sin_el_css_de_wikipedia():
    crudo = ('&lt;style data-mw-deduplicate="TemplateStyles:r1"&gt;.mw-parser-output .hlist dl,'
             '.mw-parser-output .hlist ol{margin:0;padding:0}.mw-parser-output .hlist li:after'
             '{content:")"}&lt;/style&gt;Original: Evan-Amos Obra derivada: Alhadis')
    assert ef.sin_html(crudo) == "Original: Evan-Amos Obra derivada: Alhadis"
    assert ef.autor_de({"Artist": {"value": crudo}}) == "Original: Evan-Amos Obra derivada: Alhadis"
