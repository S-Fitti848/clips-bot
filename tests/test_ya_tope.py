"""/ya (2026-11-05 07:03): la mezcla diaria reventaba con "TypeError: '>=' not supported between
instances of 'int' and 'NoneType'" apenas había candidatos, porque /ya armaba los args con
max_procesar=None. Pasaba desde que existe /ya (falló igual el 30/10)."""
import argparse
from types import SimpleNamespace

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import load_settings


class Paro(Exception):
    pass


def _preparar(tmp_path, monkeypatch, procesados):
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    db.connect(tmp_path / "t.db").close()
    monkeypatch.setattr(m, "_streamers", lambda conn=None: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)
    clip = SimpleNamespace(id="c1", url="https://kick.com/x/clips/c1", fuente="reciente", grupo="argentinos",
                           clips_mismo_momento=1, mediana_vistas=0, aviso="", chat_pico=None)
    monkeypatch.setattr(m, "buscar_todo", lambda *a, **k: SimpleNamespace(candidatos=[clip], catalogo=[]))
    monkeypatch.setattr(m, "_pegados_para", lambda *a, **k: [])
    monkeypatch.setattr(m, "_imprimir", lambda *a, **k: None)
    monkeypatch.setattr(m, "procesar_multipov_del_dia", lambda *a: 0)

    def procesar(url, *a, **k):
        procesados.append(url)
        raise Paro()        # llegó a procesar: la comparación con el tope ya pasó

    monkeypatch.setattr("clips_bot.process.procesar", procesar)


def test_sin_tope_usa_el_de_siempre_y_no_revienta(tmp_path, monkeypatch):
    procesados = []
    _preparar(tmp_path, monkeypatch, procesados)
    args = argparse.Namespace(simular=True, max_procesar=None, incluir_sin_permiso=False)
    with pytest.raises(Paro):
        m._diario(args, load_settings(), atender=False, destinos=["1"], cuantos=3)
    assert procesados == ["https://kick.com/x/clips/c1"]


def test_ya_arma_los_args_con_el_tope(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    vistos = {}
    monkeypatch.setattr(m, "_diario", lambda args, *a, **k: vistos.update(tope=args.max_procesar) or 0)
    tg = SimpleNamespace(send_message=lambda *a, **k: None)
    m._ya(conn, tg, "1", load_settings(), [])
    assert vistos["tope"] == m.MAX_PROCESAR
