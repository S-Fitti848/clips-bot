"""Tema primero en Latinoamérica (Santi, 2026-11-25): variedad de temas, rareza en los temas comunes, el mismo tema no
sale dos días seguidos y el banco se revisa con la regla nueva."""
import json
from datetime import date
from pathlib import Path

from clips_bot import banco, db, locales, temas

CONCORDIA = "Estación Concordia Central: Fue estación terminal del Ferrocarril Argentino del Este"
COLON = "Santa Fe: Colón campeón tras 116 años de espera"


def test_temas_nuevos():
    assert temas.grupo_latam("musica", "Nace el tango La Cumparsita") == "musica"
    assert temas.grupo_latam("anecdota", "Gerardo Matos Rodríguez compuso La Cumparsita") == "musica"
    assert temas.grupo_latam("invento", "Ladislao Biro patenta el bolígrafo") == "invento"
    assert temas.grupo_latam("idolo", "Carlos Gardel graba su primer tango") == "idolo"
    assert set(temas.BASE_LATAM) == set(temas.GRUPOS_LATAM) == set(temas.NOMBRE_LATAM)


def test_tema_comun():
    assert temas.tema_comun("fundacion", CONCORDIA)
    assert temas.tema_comun("invento", "en México se inaugura la CYL, una de las primeras emisoras de radio")
    assert temas.tema_comun("heroe_de_pueblo", "Josefa Ortiz de Domínguez, insurgente durante la Independencia")
    assert not temas.tema_comun("momento_emotivo", COLON)
    assert not temas.tema_comun("idolo", "Pedro Infante en el teatro")


def test_un_tema_comun_vale_lo_que_su_rareza():
    notas = {"persona": 9, "peligro": 7, "giro": 8, "emocion": 9, "rareza": 2}
    assert locales.puntaje_de(notas, "fundacion", CONCORDIA) == 2.0
    # con algo increíble sí entra
    assert locales.puntaje_de(dict(notas, rareza=9), "fundacion", CONCORDIA) == 8.25
    # en un buen tema, la rareza no recorta
    assert locales.puntaje_de(dict(notas, rareza=3), "futbol", COLON) == 8.25


def _item(texto, tipo, puntaje, art):
    return {"id": f"latam:{art}", "texto": texto, "anio": 1900, "paginas": [art], "articulo": art,
            "puntaje": puntaje, "clasif": {"lugar": "X", "pais": "Argentina", "tipo": tipo}}


def test_el_banco_va_por_tema_y_evita_el_de_ayer():
    b = [_item("Josefa Ortiz, insurgente de la Independencia", "procer", 9.0, "Josefa"),
         _item(COLON, "futbol", 8.5, "Colón"),
         _item("Pedro Infante y su último vuelo", "idolo", 8.5, "Infante")]
    orden = [a for _, a, _ in locales.de_banco(b)]
    assert orden == ["Colón", "Infante", "Josefa"]
    orden = [a for _, a, _ in locales.de_banco(b, evitar_temas={"futbol"})]
    assert orden == ["Infante", "Josefa", "Colón"]


def test_temas_de_ayer_y_hoy(tmp_path: Path):
    from clips_bot.__main__ import PH_LATAM, _temas_latam_recientes

    conn = db.connect(tmp_path / "x.db")
    db.set_valor(conn, f"{PH_LATAM}:2026-11-24", json.dumps([{"texto": COLON, "grupo": "futbol"}]))
    db.set_valor(conn, f"{PH_LATAM}:2026-11-25", json.dumps([{"texto": "Pedro Infante", "tipo": "idolo"}]))
    db.set_valor(conn, f"{PH_LATAM}:2026-11-23", json.dumps([{"texto": "algo", "grupo": "musica"}]))
    assert _temas_latam_recientes(conn, date(2026, 11, 25)) == {"futbol", "idolo"}


class _Punt:
    """Puntúa: Concordia con rareza 2, Colón alto."""

    def json(self, sistema, prompt, schema, temperatura=0.2, **kw):
        assert "rareza" in sistema
        el = []
        for n, linea in enumerate(l for l in prompt.splitlines() if l[:1].isdigit()):
            rareza = 2 if "Estación" in linea else 9
            el.append({"n": n + 1, "articulo": "", "articulo_lugar": "", "motivo": "", "persona": 9, "peligro": 8,
                       "giro": 8, "emocion": 9, "sorpresa": 0, "rareza": rareza})
        return json.dumps({"elegidos": el})


def test_revisar_el_banco(tmp_path: Path):
    conn = db.connect(tmp_path / "x.db")
    banco.guardar(conn, "latam", [_item(CONCORDIA, "fundacion", 8.25, "Estación Concordia Central"),
                                  _item(COLON, "futbol", 8.0, "Colón")])
    quedan, salen = banco.revisar_latam(conn, _Punt(), avisar=lambda *_: None)
    assert [x["articulo"] for x in quedan] == ["Colón"]
    assert len(salen) == 1 and "Concordia" in salen[0] and "rareza 2" in salen[0]
    assert db.get_valor(conn, banco.REGLA_LATAM) == banco.VERSION_REGLA_LATAM
    assert [x["articulo"] for x in banco.leer(conn, "latam")] == ["Colón"]


def test_el_tick_revisa_el_banco_una_vez(tmp_path: Path, monkeypatch):
    from datetime import datetime

    from clips_bot import __main__ as m
    from clips_bot.config import load_settings

    db_path = tmp_path / "x.db"
    conn = db.connect(db_path)
    monkeypatch.setattr(m, "DB_PATH", db_path)
    monkeypatch.setattr(m, "_puntuador", lambda st: _Punt())
    avisos = []
    monkeypatch.setattr(m, "_aviso", lambda tg, t, *a, **k: avisos.append(t))
    pasos = []
    monkeypatch.setattr(banco, "paso", lambda *a, **k: pasos.append(1))
    banco.guardar(conn, "latam", [_item(CONCORDIA, "fundacion", 8.25, "Estación Concordia Central")])
    s = load_settings()
    monkeypatch.setattr(m, "_banco_activo", lambda st, canal: canal == "latam")
    ahora = datetime(2026, 11, 25, 16, 0, tzinfo=m.AR)
    m._bancos_tick(conn, None, s, ahora, correr=lambda f: f())
    assert banco.leer(conn, "latam") == [] and pasos == [] and "salen 1" in avisos[0]
    m._bancos_tick(conn, None, s, ahora, correr=lambda f: f())
    assert len(avisos) == 1          # una sola vez; después sigue llenando como siempre
