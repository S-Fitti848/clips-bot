"""Pequeña Historia sin aprobar (efemerides.sin_aprobar, Santi 2026-11-14): el video se arma y se
programa solo; llega a Telegram con ❌ Cancelar horas antes de publicarse."""

import json

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot import efemerides as ef
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _estado(tmp_path, destino=""):
    p = ef.Propuesta(fecha="2026-11-14", evento={"texto": "x"}, fotos=[], reserva=[], guion={},
                     destino=destino, local={"lugar": "Bogotá", "pais": "Colombia", "puntaje": 8.5,
                                             "puntajes": {}} if destino else {})
    return {"propuesta": p.__dict__, "carpeta": str(tmp_path), "chat_id": "1"}


def test_prendido_por_santi():
    assert load_settings().efemerides.sin_aprobar is True     # 2026-11-15


@pytest.mark.parametrize("destino", ["", "facebook"])
def test_arma_programa_y_manda_con_cancelar(conn, tmp_path, monkeypatch, destino):
    import dataclasses
    s0 = load_settings()     # publicar_sola: solo si Santi lo vuelve a prender
    s = dataclasses.replace(s0, efemerides=dataclasses.replace(s0.efemerides, publicar_sola=True))
    orden, enviados = [], []
    meta = {"clip_id": "efemeride_x", "efemeride": {"voz": "gemini:Laomedeia"}}
    monkeypatch.setattr(ef, "hacer_video", lambda *a, **k: (orden.append("video"), meta)[1])
    monkeypatch.setattr(m, "_subir", lambda c, st, mt, canal: (orden.append(f"subir:{canal}"),
                                                                ["📤 Programado para las 11:00"])[1])
    monkeypatch.setattr(m, "_claude_textos", lambda st: (None, None))
    monkeypatch.setattr(m, "_texto_efemeride", lambda st, g: None)
    monkeypatch.setattr(m, "_gemini", lambda st: None)

    def enviar(tg, chat, c, clip_id, mt, n, h, encabezado="", extra_filas=None, **k):
        orden.append("enviar")
        enviados.append((encabezado, extra_filas))
    monkeypatch.setattr(m, "enviar_clip", enviar)
    assert m._efe_auto(conn, None, ["1"], "abc", _estado(tmp_path, destino), s) is None
    assert orden == ["video", "subir:pequena_historia", "enviar"]     # programado ANTES de mandarlo
    encabezado, extra = enviados[0]
    assert "Se publica sola" in encabezado and "11:00" in encabezado and extra == []
    assert db.get_valor(conn, "efe:abc") is None


def test_una_falla_se_devuelve_como_aviso(conn, tmp_path, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("se cortó la luz")
    monkeypatch.setattr(ef, "hacer_video", falla)
    monkeypatch.setattr(m, "_texto_efemeride", lambda st, g: None)
    monkeypatch.setattr(m, "_gemini", lambda st: None)
    r = m._efe_auto(conn, None, ["1"], "abc", _estado(tmp_path), load_settings())
    assert "se cortó la luz" in r


def test_la_falla_de_calidad_no_se_sube(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "hacer_video", lambda *a, **k: (_ for _ in ()).throw(
        ef.SinFotosReales("menos del 70 % con fotos reales")))
    monkeypatch.setattr(m, "_subir", lambda *a, **k: pytest.fail("no se sube"))
    monkeypatch.setattr(m, "_texto_efemeride", lambda st, g: None)
    monkeypatch.setattr(m, "_gemini", lambda st: None)
    r = m._efe_auto(conn, None, ["1"], "abc", _estado(tmp_path), load_settings())
    assert "70" in r


def test_publicar_sola_apagado_por_santi():
    assert load_settings().efemerides.publicar_sola is False     # 2026-11-17, el Short de Colón


@pytest.mark.parametrize("destino", ["", "facebook"])
def test_sin_ok_no_se_publica(conn, tmp_path, monkeypatch, destino):
    """Santi, 2026-11-17: todo video de Pequeña Historia llega con ✅ Publicar / ❌ Cancelar; sin respuesta no sale."""
    s = load_settings()
    enviados = []
    meta = {"clip_id": "efemeride_x", "efemeride": {"voz": "gemini:Laomedeia"}}
    monkeypatch.setattr(ef, "hacer_video", lambda *a, **k: meta)
    monkeypatch.setattr(m, "_subir", lambda *a, **k: pytest.fail("no se programa sin el OK"))
    monkeypatch.setattr(m, "_claude_textos", lambda st: (None, None))
    monkeypatch.setattr(m, "_texto_efemeride", lambda st, g: None)
    monkeypatch.setattr(m, "_gemini", lambda st: None)
    monkeypatch.setattr(m, "enviar_clip", lambda *a, encabezado="", extra_filas=None, **k:
                        enviados.append((encabezado, extra_filas)))
    assert m._efe_auto(conn, None, ["1"], "abc", _estado(tmp_path, destino), s) is None
    encabezado, extra = enviados[0]
    assert "Esperando tu OK" in encabezado and "Se publica sola" not in encabezado
    datos = [b["callback_data"] for fila in extra for b in fila]
    textos = [b["text"] for fila in extra for b in fila]
    assert "sub:pub:efemeride_x" in datos and "sub:no:efemeride_x" in datos and "✅ Publicar" in textos
