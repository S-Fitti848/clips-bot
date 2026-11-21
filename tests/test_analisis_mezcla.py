"""El análisis de un Short puntual cuando Analytics tiene sus datos, y la propuesta de cambiar la mezcla si
tecnología rinde más que Latinoamérica en YouTube (Santi, 2026-11-14)."""

from datetime import date

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot import medicion_ph as mp


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


class Cliente:
    def __init__(self, con_datos=True):
        self.con_datos = con_datos

    def _analytics(self, p):
        dim = p.get("dimensions")
        if dim == "video":
            filas = [["otro1", 1200, 600, 24, 60, 30, 0, 1, 2], ["otro2", 1250, 700, 20, 55, 28, 1, 0, 3]]
            return filas + ([["intel", 3220, 2000, 22, 75, 67, 1, 9, 6]] if self.con_datos else [])
        if dim == "insightTrafficSourceType":
            return [["SHORTS", 3000], ["YT_SEARCH", 220]]
        if dim == "day":
            return [["2026-11-13", 1300], ["2026-11-14", 400], ["2026-11-15", 1500]]
        return []


class TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((chat, texto))


def test_el_analisis_espera_a_analytics_y_sale_una_vez(conn):
    db.set_valor(conn, mp.CLAVE_ANALISIS, "intel")
    tg = TG()
    m._analisis_y_mezcla(conn, tg, {"yt": {}}, date(2026, 11, 14), cliente=Cliente(con_datos=False))
    assert tg.mensajes == [] and db.get_valor(conn, mp.CLAVE_ANALISIS) == "intel"   # todavía no
    m._analisis_y_mezcla(conn, tg, {"yt": {}}, date(2026, 11, 16), cliente=Cliente())
    (chat, corto), = tg.mensajes
    assert chat == m.DUENO and len(corto.splitlines()) <= 3          # Santi, 2026-11-20: 3 líneas; el resto en 📋
    from clips_bot import aviso_corto

    c2 = db.connect(aviso_corto.DB)
    texto = aviso_corto.leer(c2) or corto
    assert "Vistas: 3220" in texto and "feed de Shorts 93 %" in texto
    assert "segundo empujón" in texto and "tuvo segundo empujón" in texto
    assert db.get_valor(conn, mp.CLAVE_ANALISIS) is None


def _yt(tec, lat):
    yt = {}
    for k, v in enumerate(tec):
        yt[f"t{k}"] = {"tipo": "tecnologia", "publicado": f"2026-11-{13 + k}", "vistas": v}
    for k, v in enumerate(lat):
        yt[f"l{k}"] = {"tipo": "latam", "publicado": f"2026-11-{12 + k}", "vistas": v}
    return yt


def test_la_mezcla_se_propone_con_datos_suficientes_y_una_sola_vez(conn):
    hoy = date(2026, 11, 25)
    assert mp.comparar_mezcla(_yt([3000, 2500], [1200] * 6), hoy) is None          # pocos de tecnología
    comp = mp.comparar_mezcla(_yt([3000, 2500, 2000, 1900], [1200] * 6), hoy)
    assert comp["rinde_mas"] and comp["n_tec"] == 4
    assert not mp.comparar_mezcla(_yt([1300] * 4, [1200] * 6), hoy)["rinde_mas"]   # parejos: nada
    tg = TG()
    datos = {"yt": _yt([3000, 2500, 2000, 1900], [1200] * 6)}
    m._analisis_y_mezcla(conn, tg, datos, hoy, cliente=Cliente())
    m._analisis_y_mezcla(conn, tg, datos, hoy, cliente=Cliente())
    assert len(tg.mensajes) == 1 and "2 de tecnología y 1 de Latinoamérica" in tg.mensajes[0][1]
