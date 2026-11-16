"""El estándar de calidad (Santi, 2026-11-16; ESTANDAR_CALIDAD.md y clips_bot/calidad.py)."""
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from clips_bot import calidad


def test_el_documento_tiene_las_reglas_de_los_dos_canales():
    an, ph = calidad.reglas("asinacio"), calidad.reglas("pequena_historia")
    assert len(an) >= 18 and len(ph) >= 12
    for rs, pre in ((an, "AN-"), (ph, "PH-")):
        ids = [r.id for r in rs]
        assert len(ids) == len(set(ids)) and all(i.startswith(pre) for i in ids)
        assert {r.tipo for r in rs} == {"revisión", "código"}
    from clips_bot.animacion import marcas

    assert all(r.arreglo in marcas.ARREGLOS for r in calidad.de_revision("asinacio"))
    assert all(r.arreglo in ("cambiar_foto", "otro") for r in calidad.de_revision("pequena_historia"))
    # las reglas que pidió Santi están
    textos = " ".join(r.texto for r in an).lower()
    for clave in ("gancho", "lo que dice la voz", "manos que tocan", "en uso", "parado sin hacer nada", "época",
                  "flotando", "no se pisan", "sin la voz", "según el guion"):
        assert clave in textos, clave


def test_una_regla_nueva_en_el_documento_entra_sola(tmp_path, monkeypatch):
    doc = tmp_path / "e.md"
    doc.write_text("- **AN-01** · revisión · arreglo: cambiar_accion — UNO: algo\n", encoding="utf-8")
    monkeypatch.setattr(calidad, "DOC", doc)
    assert [r.id for r in calidad.reglas("asinacio")] == ["AN-01"]
    import os
    import time

    doc.write_text(doc.read_text(encoding="utf-8") + "- **AN-02** · revisión · arreglo: otro — DOS: otra\n",
                   encoding="utf-8")
    os.utime(doc, (time.time() + 5, time.time() + 5))
    assert [r.id for r in calidad.reglas("asinacio")] == ["AN-01", "AN-02"]
    assert "AN-02: DOS: otra" in calidad.para_prompt("asinacio")


def test_fallas_y_mensaje():
    resp = [{"id": "an-05", "cumple": False, "cuadro": 3, "que": "el inventor parado"},
            {"id": "AN-01", "cumple": True, "cuadro": 0, "que": ""},
            {"id": "AN-99", "cumple": False, "cuadro": 1, "que": "inventada"},
            {"id": "AN-20", "cumple": False, "cuadro": 1, "que": "de código, no se revisa"}]
    f = calidad.fallas_de(resp, "asinacio")
    assert [x["id"] for x in f] == ["AN-05"]
    total = len(calidad.de_revision("asinacio"))
    t = calidad.texto_estandar("asinacio", f, ["AN-07"])
    assert f"{total - 1}/{total}" in t and "❌ AN-05" in t and "el inventor parado" in t and "AN-07" in t
    assert "✅" in calidad.texto_estandar("asinacio", [])
    assert "no respondió" in calidad.texto_estandar("asinacio", [], revisado=False)


def test_la_falla_sin_problema_se_corrige_con_el_arreglo_de_la_regla():
    from clips_bot.animacion import marcas

    fallas = [{"id": "AN-05", "cuadro": 3, "que": "parado"}, {"id": "AN-11", "cuadro": 2, "que": "dos textos"},
              {"id": "AN-01", "cuadro": 9, "que": "cuadro que no existe"}]
    ya = [{"cuadro": 2, "que": "texto pisado", "arreglo": "sacar_texto", "objeto": ""}]
    out = marcas.problemas_del_estandar(fallas, ya, 8)
    assert {(p["cuadro"], p["arreglo"]) for p in out} == {(2, "sacar_texto"), (3, "cambiar_accion")}


def _conn():
    c = sqlite3.connect(":memory:")
    return c


def test_registro_y_resumen_de_la_semana():
    c = _conn()
    calidad.anotar(c, "asinacio", "v1", [{"id": "AN-05", "que": "parado en la tienda"}], ["AN-07"], dia="2026-11-17")
    calidad.anotar(c, "asinacio", "v2", [{"id": "AN-05", "que": "parada"}], [], [("AN-21", "guion largo")],
                   dia="2026-11-18")
    calidad.anotar(c, "pequena_historia", "p1", [], ["PH-03"], dia="2026-11-18")
    calidad.anotar(c, "asinacio", "viejo", [{"id": "AN-01", "que": "x"}], dia="2026-11-01")
    t = calidad.resumen_semana(c, "2026-11-16", "2026-11-23")
    assert "Así Nació</b>: 2 videos" in t and "AN-05" in t and "2 de 2" in t and "parado en la tienda" in t
    assert "AN-01" not in t                       # fuera de la semana
    assert "PH-03" in t and "corregida sola 1" in t
    calidad.anotar(c, "asinacio", "v1", [], dia="2026-11-17")      # revisado de nuevo: se reemplaza
    assert "1 de 2" in calidad.resumen_semana(c, "2026-11-16", "2026-11-23")


def test_el_resumen_sale_los_lunes_una_vez(tmp_path):
    from clips_bot import __main__ as m, db

    c = db.connect(tmp_path / "c.db")
    enviados = []

    class TG:
        def send_message(self, chat, texto, *a, **k):
            enviados.append((chat, texto))

    lunes = datetime(2026, 11, 23, 9, 40, tzinfo=m.AR)
    m._calidad_semana_tick(c, TG(), datetime(2026, 11, 23, 9, 10, tzinfo=m.AR))
    m._calidad_semana_tick(c, TG(), datetime(2026, 11, 24, 10, 0, tzinfo=m.AR))
    assert not enviados
    m._calidad_semana_tick(c, TG(), lunes)
    m._calidad_semana_tick(c, TG(), lunes)
    assert len(enviados) == 1 and enviados[0][0] == m.DUENO and "16/11 a 22/11" in enviados[0][1]


def test_pequena_historia_cambia_la_foto_que_no_pasa(monkeypatch, tmp_path):
    from clips_bot import efemerides as ef

    respuestas = [
        {"reglas": [{"id": "PH-03", "cumple": False, "frase": 2, "foto": 5, "que": "un avión de 2008"},
                    {"id": "PH-08", "cumple": False, "frase": 9, "foto": 0, "que": "no hay pregunta al final"}]},
        {"reglas": [{"id": "PH-08", "cumple": False, "frase": 9, "foto": 0, "que": "no hay pregunta al final"}]},
    ]

    class Cli:
        def json(self, sistema, prompt, schema, temp, imagenes=None):
            assert imagenes and "PH-03" in prompt
            return json.dumps(respuestas.pop(0))

    cambiadas = []
    monkeypatch.setattr(calidad, "_hoja_ph", lambda p, carpeta, nombre: _png(tmp_path / nombre))
    monkeypatch.setattr(ef, "numeros_usados", lambda p: [1, 2, 5])
    monkeypatch.setattr(ef, "Guion", type("G", (), {"de_dict": staticmethod(lambda d: type("g", (), {
        "frases": ["a", "b"], "titulo": "t"})())}))
    monkeypatch.setattr(ef, "Evento", lambda **k: type("e", (), {"anio": 1940})())
    monkeypatch.setattr(ef, "cambiar_foto", lambda p, n, wiki, carpeta: cambiadas.append(n) or object())
    p = type("P", (), {"guion": {}, "evento": {}})()
    p2, fallas, corregidas, revisado = calidad.revisar_ph(Cli(), p, tmp_path, wiki=object())
    assert cambiadas == [5] and corregidas == ["PH-03"] and [f["id"] for f in fallas] == ["PH-08"] and revisado


def test_pequena_historia_sin_claude_no_revisa(tmp_path):
    p = object()
    assert calidad.revisar_ph(None, p, tmp_path) == (p, [], [], False)


def _png(ruta: Path) -> Path:
    from PIL import Image

    Image.new("RGB", (10, 10)).save(ruta)
    return ruta
