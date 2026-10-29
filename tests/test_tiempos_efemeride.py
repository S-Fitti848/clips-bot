"""La corrida del 2026-10-29 murió por timeout buscando fotos de la efeméride (Openverse colgado,
Smithsonian con 429 por la DEMO_KEY). Topes por fuente y por búsqueda, y la efeméride aparte."""
import argparse
from pathlib import Path

import pytest
import requests

import clips_bot.__main__ as m
from clips_bot import db, efemerides as ef, fuentes_fotos as ff


@pytest.fixture(autouse=True)
def _corrida_nueva():
    ff.nueva_corrida()
    yield
    ff.nueva_corrida()


class SesionCaida:
    def __init__(self):
        self.pedidos = []
        self.headers = {}

    def get(self, url, timeout=None, **kw):
        self.pedidos.append((url, timeout))
        raise requests.ReadTimeout("Read timed out")


def test_cada_pedido_tiene_10_s_y_una_fuente_caida_se_saltea_despues_de_2_fallas(monkeypatch):
    monkeypatch.setattr(ff, "env", lambda *a, **k: "")
    s = SesionCaida()
    f = ff.Fuentes(session=s, sleep=lambda x: None)
    avisos = []
    for _ in range(4):   # cuatro frases
        ff.BUSCAR_REAL(f, ["thieves window", "thieves"], presente=False, de_espacio=False, cuantas=4,
                       avisar=avisos.append)
    openverse = [u for u, _ in s.pedidos if "openverse" in u]
    assert len(openverse) == 2                                   # después de 2 fallas, no más
    assert all(t == 10 for _, t in s.pedidos)
    assert any("la salteo el resto de la corrida" in a for a in avisos)


def test_una_propuesta_nueva_vuelve_a_probar_las_fuentes(monkeypatch):
    monkeypatch.setattr(ff, "env", lambda *a, **k: "")
    s = SesionCaida()
    f = ff.Fuentes(session=s, sleep=lambda x: None)
    for _ in range(3):
        ff.BUSCAR_REAL(f, ["x"], False, False, 4, avisar=lambda *_: None)
    ff.nueva_corrida()
    antes = len(s.pedidos)
    ff.BUSCAR_REAL(f, ["x"], False, False, 4, avisar=lambda *_: None)
    assert len(s.pedidos) > antes


def test_smithsonian_sin_clave_propia_no_se_llama(monkeypatch):
    monkeypatch.setattr(ff, "env", lambda *a, **k: "")
    s = SesionCaida()
    assert ff.Fuentes(session=s, sleep=lambda x: None).smithsonian("x") == []
    assert s.pedidos == []                                       # nada de DEMO_KEY


def test_con_el_tope_vencido_no_se_busca_mas(monkeypatch):
    monkeypatch.setattr(ff, "env", lambda *a, **k: "")
    s = SesionCaida()
    ff.CORRIDA.con_tope(-1)
    assert ff.BUSCAR_REAL(ff.Fuentes(session=s, sleep=lambda x: None), ["x"], True, True, 4) == []
    assert s.pedidos == []


class WikiCuenta:
    def __init__(self):
        self.busquedas = []

    def archivos(self, lang, titulo):
        return []

    def info(self, lang, archivos, ancho=1280):
        return []

    def buscar_commons(self, terminos, cuantas=6):
        self.busquedas.append(terminos)
        return []


def test_fotos_para_guion_corta_la_busqueda_al_pasar_el_tope(tmp_path):
    wiki = WikiCuenta()
    g = ef.Guion(frases=[f"Frase {i}." for i in range(4)], fotos=[], descartadas=[], titulo="t",
                 descripcion="d", hashtags=["#Shorts"], mostrar=[f"cosa {i}" for i in range(4)],
                 idea_clave="x")
    avisos = []
    with pytest.raises(Exception):     # sin fotos no hay video, pero no se buscó nada
        ef.fotos_para_guion(wiki, object(), ef.Evento("es", 1964, "x", ["X"]), g, [], tmp_path,
                            avisos.append, tope_s=-1, fuentes=ff.Fuentes(session=SesionCaida()))
    assert wiki.busquedas == []
    assert any("pasó el tope" in a for a in avisos)


# ---- la efeméride aparte de la corrida de clips ----------------------------------------------------

def test_con_el_timer_propio_instalado_diario_no_hace_la_efemeride(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    llamadas = []
    monkeypatch.setattr(m, "_diario", lambda args, s: llamadas.append("clips") or 0)
    monkeypatch.setattr(m, "actualizar_metricas", lambda: llamadas.append("metricas"))
    monkeypatch.setattr(m, "_resumen_pego", lambda s, simular: llamadas.append("pego"))
    monkeypatch.setattr(m, "efemeride_del_dia", lambda s, simular=False: llamadas.append("efemeride"))
    args = argparse.Namespace(simular=False)
    monkeypatch.setattr(m, "efemeride_aparte", lambda: True)
    m.cmd_diario(args)
    assert llamadas == ["clips", "metricas", "pego"]
    llamadas.clear()
    monkeypatch.setattr(m, "efemeride_aparte", lambda: False)   # hasta instalarlo, va al final
    m.cmd_diario(args)
    assert llamadas == ["clips", "metricas", "pego", "efemeride"]


def test_efemeride_diaria_no_pisa_a_los_clips_y_queda_para_los_reintentos(monkeypatch, tmp_path):
    import json

    dbp = tmp_path / "t.db"
    monkeypatch.setattr(m, "DB_PATH", dbp)
    c = db.connect(dbp)
    db.ver_chat(c, "-100", "group", "Rots clips")
    db.marcar_destino(c, "-100", True)
    assert db.tomar_turno(c, db.RECURSO_PESADO, "diario:1", maximo=1, vencimiento_s=3600)
    c.close()
    monkeypatch.setattr(m, "time", type("T", (), {"sleep": staticmethod(lambda s: None)}))
    monkeypatch.setattr(m, "efemeride_del_dia", lambda s, simular=False: pytest.fail("pisó a los clips"))
    hora = type("D", (), {})
    from datetime import datetime
    monkeypatch.setattr(m, "datetime", type("DT", (datetime,), {
        "now": classmethod(lambda cls, tz=None: datetime(2026, 10, 29, 6, 31, tzinfo=tz))}))
    assert m.cmd_efemeride_diaria(argparse.Namespace(simular=False)) == 0
    c = db.connect(dbp)
    d = json.loads(db.get_valor(c, m.EFE_REINTENTO))
    assert d["horas"] == ["07:00", "10:00"] and d["chats"] == ["-100"] and d["intentos"] == ["06:31"]


def test_las_unidades_de_la_efemeride_estan_y_van_con_lf():
    raiz = Path(__file__).resolve().parents[1] / "deploy"
    servicio = (raiz / "clips-bot-efemeride.service").read_text(encoding="utf-8")
    assert "correr.sh efemeride-diaria" in servicio and "TimeoutStartSec=" in servicio
    assert "06:00:00" in (raiz / "clips-bot-efemeride.timer").read_text(encoding="utf-8")
    assert "efemeride-diaria" in (raiz / "correr.sh").read_text(encoding="utf-8")
    assert "clips-bot-efemeride.timer" in (raiz / "instalar.sh").read_text(encoding="utf-8")
