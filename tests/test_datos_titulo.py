"""Datos personales en textos escritos (2026-09-29): un clip real de Kick se titulaba
"si davo es +54 11 3396-6858". El OCR miraba la pantalla, no los títulos."""

import json

import pytest
from test_fuentes import AHORA, KICK
from test_kick_politica import FakeSession, clip_kick, pagina, videos

from clips_bot.candidates import buscar_kick
from clips_bot.config import Filtros, Textos
from clips_bot.kick import KickClient
from clips_bot.pantalla import MOTIVO_TITULO, datos_en_texto, tapar_datos
from clips_bot.textos import armar_prompt, parsear, validar


@pytest.mark.parametrize("texto,tipos", [
    ("si davo es +54 11 3396-6858", ["telefono"]),          # el caso real
    ("escribime a pepe@gmail.com", ["mail"]),
    ("whatsapp 1133966858", ["telefono"]),
    ("vivo en Av. Corrientes 1234", ["direccion"]),
    ("pasame tu código postal", ["direccion"]),
    ("67", []),
    ("top 10 2026", []),
    ("en la calle con los pibes", []),                      # "calle" suelta no es una dirección
    ("lo pisó feo", []),
    ("Vegetta tiene 17.764.293 de monedas", []),            # un número largo sin contexto
    ("Minecraft 1.20.4", []),
])
def test_datos_en_texto(texto, tipos):
    assert sorted({h.tipo for h in datos_en_texto(texto)}) == tipos


def test_tapar_datos_deja_el_resto():
    assert tapar_datos("si davo es +54 11 3396-6858 jaja") == "si davo es [dato personal] jaja"
    assert tapar_datos("top 10 2026") == "top 10 2026"


def test_un_clip_con_telefono_en_el_titulo_no_pasa():
    s = FakeSession([pagina([clip_kick("tel", views=900, horas=48, titulo="si davo es +54 11 3396-6858",
                                       livestream="l1"),
                             clip_kick("ok", views=800, horas=48, offset=9000, titulo="DAVO FANTASMA",
                                       livestream="l1")]),
                     videos({"l1": "stream normal"})])
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), KICK, Filtros(), vistos=set(), ahora=AHORA)
    assert [c.id for c in res.candidatos] == ["ok"]
    assert res.descartes[MOTIVO_TITULO] == 1


def test_el_titulo_del_stream_tambien_se_revisa():
    s = FakeSession([pagina([clip_kick("c", views=900, horas=48, titulo="risas", livestream="l1")]),
                     videos({"l1": "sorteo, mandá mail a sorteos@davo.com"})])
    res = buscar_kick(KickClient(session=s, sleep=lambda _: None), KICK, Filtros(), vistos=set(), ahora=AHORA)
    assert res.candidatos == [] and res.descartes[MOTIVO_TITULO] == 1


def test_a_gemini_le_llega_tapado():
    prompt = armar_prompt("Davo", "Just Chatting", "si davo es +54 11 3396-6858", 30,
                          "llamame al whatsapp 1133966858", Textos())
    assert "3396" not in prompt and "1133966858" not in prompt and "[dato personal]" in prompt


BASE = {"titulo": "Davo y la llamada", "descripcion": "Pasa algo.", "hashtags": ["#Shorts", "#a", "#b"],
        "gancho": "reaccion", "depende_de_fecha": False, "sensible": False, "puntaje": 7}


def test_lo_que_escribe_gemini_se_revisa():
    malo = {**BASE, "titulo": "Su número: +54 11 3396-6858"}
    assert any("titulo tiene datos personales (telefono)" in e for e in validar(malo, Textos()))
    malo = {**BASE, "descripcion": "Escribile a pepe@gmail.com"}
    assert any("descripcion tiene datos personales (mail)" in e for e in validar(malo, Textos()))
    assert validar(BASE, Textos()) == []


def test_parsear_ahora_si_chequea_los_nombres_contra_lo_que_se_dice():
    """Estaba roto desde v0.18: parsear no le pasaba el contexto a validar y el chequeo no corría."""
    texto = json.dumps({**BASE, "titulo": "Davo y Messi en la llamada"})
    t, errores = parsear(texto, Textos(), "Davo", "davooxeneize", contexto="davo habla por teléfono")
    assert t is None and any("Messi" in e for e in errores)
