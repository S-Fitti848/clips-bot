"""Mensajes cortos (Santi, 2026-11-20: "tienen demasiado texto y no los leo"): el video con título, hashtags y una
línea; el detalle detrás de 📋; los avisos en 3 líneas como mucho. Y el sepia del apretón del plano medio."""
from clips_bot import aviso_corto as ac
from clips_bot import db


def test_la_linea_de_resumen():
    assert ac.resumen(11, 13, 0.31, "11:00") == "✅ 11/13 · US$ 0,31 · sale 11:00"
    assert ac.resumen(12, 19, 0.5, "", retenido=True) == "⏸ 12/19 · US$ 0,50 · espera tu OK"


def test_el_caption_es_titulo_hashtags_y_una_linea():
    cap = ac.caption("La botica de Pepsi", ["#Shorts", "#Pepsi"], "✅ 18/19 · US$ 0,04 · sale 12:30")
    assert cap.split("\n") == ["La botica de Pepsi", "#Shorts #Pepsi", "✅ 18/19 · US$ 0,04 · sale 12:30"]


def test_el_motivo_es_una_sola_linea():
    m = ac.motivo_retenido("pequena_historia", [{"id": "PH-02", "que": "x " * 200}], True)
    assert m.startswith("Motivo: PH-02") and "\n" not in m and len(m) <= 150


def test_detalle_guardado_y_leido(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    ac.guardar(conn, "efemeride_1120_1985", "<b>todo</b>")
    assert ac.leer(conn, "efemeride_1120_1985") == "<b>todo</b>" and ac.leer(conn) == "<b>todo</b>"
    t = ac.con_detalle({"inline_keyboard": [[{"text": "❌", "callback_data": "sub:x:a"}]]}, "efemeride_1120_1985")
    assert t["inline_keyboard"][-1][0]["callback_data"] == "det:efemeride_1120_1985"


def test_un_aviso_largo_se_corta_en_3_lineas(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    mandados = []

    class Tg:
        def send_message(self, chat, texto, teclado=None):
            mandados.append((texto, teclado))

    ac.mandar_aviso(Tg(), "1", conn, "<b>uno</b>\ndos\ntres\ncuatro\ncinco")
    texto, teclado = mandados[0]
    assert texto.count("\n") == 2 and "cuatro" not in texto
    clave = teclado["inline_keyboard"][-1][0]["callback_data"].split(":", 1)[1]
    assert "cinco" in ac.leer(conn, clave)
    ac.mandar_aviso(Tg(), "1", conn, "corto")
    assert mandados[1] == ("corto", None)


def test_un_color_de_dibujo_no_queda_a_color_en_sepia():
    from clips_bot.animacion import timeline

    v = timeline.Video.desde_dict({"fps": 30, "escenas": [{"duracion": 1.0, "fondo": {"tipo": "color", "color": "#fff"},
                                                           "elementos": [
        {"tipo": "prop", "nombre": "dedos", "x": 540, "y": 900, "color": "#f2c29b"},
        {"tipo": "prop", "nombre": "botella", "x": 300, "y": 900, "color": True}]}]})
    capa = v._capa(v.escenas[0], 0.5, 15, separar=True)
    assert capa.color and "f2c29b" not in capa.color
