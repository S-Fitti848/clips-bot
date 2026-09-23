"""Capa de datos en pantalla (OCR). Sin tesseract ni video: se testea el matcheo sobre texto."""

from clips_bot.config import PantallaCfg
from clips_bot.pantalla import MOTIVO, Pantalla, buscar, detectar_datos

PAGO = ("checkout", "subtotal", "tarjeta", "CVV", "discount code")
DIR = ("direccion de envio", "shipping", "codigo postal", "calle")
CTX = ("tel", "telefono", "phone", "contact")


def _tipos(texto, **kw):
    return sorted({h.tipo for h in buscar(texto, PAGO, DIR, **kw)})


def test_el_checkout_de_hasvik():
    """El caso real (2026-09-23): categoría Minecraft, pero en pantalla había un checkout con el
    nombre, el mail y la dirección de un tercero."""
    texto = ("YOUTOOZ  Cart > Information > Shipping > Payment\n"
             "Contact  ilanalatriste123@gmail.com\n"
             "Ship to  Universidad anahuac, house, 77560 ciudad de mexico\n"
             "Subtotal $29.99   Discount code")
    assert _tipos(texto, palabras_contexto=CTX) == ["direccion", "mail", "pago"]


def test_los_numeros_solos_no_alcanzan():
    """Medido sobre 26 clips: el regex de teléfono sin contexto daba 3 falsos positivos (el contador
    de dinero de Vegetta, un id de Minecraft, un timer) y ningún acierto."""
    hud = "Dinero: 17.764.293.15  Usuarios: 4545485445  00:00:00"
    assert _tipos(hud, palabras_contexto=CTX) == []
    assert _tipos("Telefono de contacto: +54 11 4545-4854", palabras_contexto=CTX) == ["telefono"]
    # y sin palabras de contexto cargadas, ningún número cuenta
    assert _tipos("Telefono: +54 11 4545-4854", palabras_contexto=()) == []


def test_el_mail_vale_solo():
    assert _tipos("escribime a hola@ejemplo.com", palabras_contexto=()) == ["mail"]
    assert _tipos("vamos a jugar un rato", palabras_contexto=CTX) == []


def test_sin_tildes_ni_mayusculas():
    assert _tipos("DIRECCIÓN DE ENVÍO", palabras_contexto=()) == ["direccion"]
    assert _tipos("poné el CVV de la Tarjeta", palabras_contexto=()) == ["pago"]


def test_la_capa_apagada_no_descarta_nada():
    r = detectar_datos(None, PantallaCfg(activo=False))
    assert not r.hay and r.salteado and r.a_dict()["motivo"] == ""


def test_sin_tesseract_no_corta_la_corrida(tmp_path, monkeypatch):
    """Si falta el binario, la capa se saltea: es un filtro menos, no un error."""
    from clips_bot import pantalla

    def explota(*a, **k):
        raise pantalla.OcrNoDisponible("No encuentro tesseract")

    monkeypatch.setattr(pantalla, "leer_frames", explota)
    r = pantalla.detectar_datos(tmp_path / "x.mp4", PantallaCfg())
    assert not r.hay and "tesseract" in r.salteado
    assert MOTIVO == "datos_en_pantalla"


def test_pantalla_a_dict_es_serializable():
    import json

    r = Pantalla(motivo="mail en pantalla", hallazgos=(), frames_leidos=8, caracteres=120)
    assert json.loads(json.dumps(r.a_dict()))["frames_leidos"] == 8
