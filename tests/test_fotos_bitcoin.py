"""Reglas de fotos de la efeméride de bitcoin (2026-10-21): nada de capturas, apps, documentos,
planillas ni gráficos salvo que la frase hable de eso; nada con texto en otro idioma; nada que
contradiga la frase; solo el modelo principal (y si no, el aviso); stock primero en lo moderno;
la tarjeta antes que una foto mala."""
import json

import pytest
from PIL import Image, ImageDraw

from clips_bot import efemerides as ef, fuentes_fotos
from clips_bot.gemini import GeminiError


def _guion(frases):
    return ef.Guion(frases=frases, fotos=[], descartadas=[], titulo="t", descripcion="d",
                    hashtags=["#Shorts"], mostrar=["bitcoin 2021"] * len(frases), idea_clave="x",
                    claves=["Bitcoin"])


def _pool(n):
    return [ef.Foto(f"File:{i}.jpg", "u", 800, 600, "CC0", "a", "e", "p", "art", ruta=f"{i}.jpg")
            for i in range(n)]


class Gem:
    modelo, modelo_fallback = "principal", "respaldo"

    def __init__(self, resp, falla_principal=False):
        self.resp, self.falla, self.modelos = resp, falla_principal, []

    def json(self, *a, modelo=None, **k):
        self.modelos.append(modelo)
        if self.falla and modelo == "principal":
            raise GeminiError("503")
        return json.dumps(self.resp)


@pytest.fixture(autouse=True)
def _sin_jpeg(monkeypatch):
    monkeypatch.setattr(ef, "_jpeg_chico", lambda ruta, ancho=512: b"x")


def _frase(fotos, contradice=False):
    return {"se_ve": "x", "fotos": fotos, "de_epoca": True, "seguro": True, "contradice": contradice}


def test_una_app_o_planilla_no_va_en_una_frase_que_no_habla_de_eso():
    g = _guion(["Bitcoin superó los 66.000 dólares.", "La gente festejó en las calles."])
    resp = {"frases": [_frase([1, 3]), _frase([2, 3])], "descartadas": [],
            "tipos": [{"foto": 1, "tipo": "grafico", "otro_idioma": False},
                      {"foto": 2, "tipo": "interfaz", "otro_idioma": False},
                      {"foto": 3, "tipo": "foto", "otro_idioma": False}]}
    rankings, malas = ef.elegir_fotos(Gem(resp), g, _pool(3), [[0, 1, 2]] * 2)
    assert rankings[0] == [0, 2]           # el gráfico sí: la frase habla de un valor
    assert rankings[1] == [2]              # la app no: la frase habla de la gente
    assert 1 in malas                      # y no queda de reserva para otras


def test_texto_en_otro_idioma_nunca():
    g = _guion(["Bitcoin superó su récord."])
    resp = {"frases": [_frase([1, 2])], "descartadas": [],
            "tipos": [{"foto": 1, "tipo": "foto", "otro_idioma": True},
                      {"foto": 2, "tipo": "foto", "otro_idioma": False}]}
    rankings, _ = ef.elegir_fotos(Gem(resp), g, _pool(2), [[0, 1]])
    assert rankings == [[1]]


def test_mucho_texto_por_ocr_queda_afuera_salvo_que_hable_de_un_documento():
    g = _guion(["La gente festejó en las calles.", "Publicó el documento con las reglas."])
    resp = {"frases": [_frase([1, 2]), _frase([1, 2])], "descartadas": [],
            "tipos": [{"foto": 1, "tipo": "foto", "otro_idioma": False},
                      {"foto": 2, "tipo": "foto", "otro_idioma": False}]}
    rankings, _ = ef.elegir_fotos(Gem(resp), g, _pool(2), [[0, 1]] * 2, ocr={0: 0.13, 1: 0.02})
    assert rankings == [[1], [0, 1]]


def test_si_la_primera_contradice_la_frase_sale():
    g = _guion(["El precio subió muchísimo."])
    resp = {"frases": [_frase([1, 2], contradice=True)], "descartadas": [], "tipos": []}
    rankings, _ = ef.elegir_fotos(Gem(resp), g, _pool(2), [[0, 1]])
    assert rankings == [[1]]


def test_solo_el_modelo_principal_y_si_falla_el_respaldo_con_aviso():
    g = _guion(["Bitcoin superó su récord."])
    resp = {"frases": [_frase([1])], "descartadas": [], "tipos": []}
    gem, extra = Gem(resp), {}
    ef.elegir_fotos(gem, g, _pool(1), [[0]], extra=extra)
    assert gem.modelos == ["principal"] and not extra.get("respaldo")
    gem, extra = Gem(resp, falla_principal=True), {}
    ef.elegir_fotos(gem, g, _pool(1), [[0]], extra=extra)
    assert gem.modelos == ["principal", "respaldo"] and extra["respaldo"]


def test_el_aviso_del_respaldo_sale_en_la_aprobacion_y_en_la_hoja(tmp_path):
    g = _guion(["Bitcoin superó su récord."])
    g.fotos_respaldo = True
    e = ef.Evento("es", 2021, "Bitcoin supera los 66.000 dólares", ["Bitcoin"])
    from datetime import date
    assert ef.AVISO_RESPALDO in ef.texto_aprobacion(e, g, [], date(2026, 10, 21), [], [])
    Image.new("RGB", (800, 600), (40, 90, 160)).save(tmp_path / "0.jpg")
    foto = ef.Foto("File:0.jpg", "u", 800, 600, "CC0", "a", "e", "p", "art", ruta=str(tmp_path / "0.jpg"))
    sin = ef.hoja_de_guion([foto], [([0], "frase")], tmp_path / "a.jpg")
    con = ef.hoja_de_guion([foto], [([0], "frase")], tmp_path / "b.jpg", aviso=ef.AVISO_RESPALDO)
    assert Image.open(con).height > Image.open(sin).height


def test_la_tarjeta_lleva_la_clave_de_la_frase_o_el_anio(tmp_path):
    g = _guion(["Bitcoin superó su récord.", "La gente festejó."])
    assert ef.texto_tarjeta(g, 0, 2021) == "BITCOIN"
    assert ef.texto_tarjeta(g, 1, 2021) == "2021"
    Image.new("RGB", (800, 600), (40, 90, 160)).save(tmp_path / "base.jpg")
    base = ef.Foto("File:b.jpg", "u", 800, 600, "CC BY 4.0", "Ana", "e", "pag", "art",
                   ruta=str(tmp_path / "base.jpg"), anio=2021)
    t = ef.tarjeta(base, "2021", tmp_path / "t.jpg")
    assert Image.open(t.ruta).size == (1080, 1920)
    assert (t.autor, t.licencia, t.pagina) == ("Ana", "CC BY 4.0", "pag")     # crédito de la base


def test_stock_primero_pexels_y_unsplash():
    f = fuentes_fotos.Fuentes()
    llamadas = []
    f.pexels = lambda q, n=5: (llamadas.append(("pexels", q)) or
                               [{"archivo": "pexels:1", "url": "u", "ancho": 1, "alto": 1, "licencia": "L",
                                 "autor": "a", "epigrafe": "bitcoin coin", "pagina": "p", "anio": None}])
    f.unsplash = lambda q, n=5: llamadas.append(("unsplash", q)) or []
    out = f.stock(["bitcoin", "crypto"], 2, avisar=lambda *_: None)
    assert [h["fuente"] for h in out] == ["pexels"]
    assert llamadas[0] == ("pexels", "bitcoin")


def test_fraccion_texto_separa_un_documento_de_una_foto(tmp_path):
    from clips_bot.pantalla import find_tesseract
    try:
        find_tesseract()
    except Exception:
        pytest.skip("sin tesseract")
    doc = Image.new("RGB", (900, 900), "white")
    d = ImageDraw.Draw(doc)
    fuente = ef._fuente_ttf(34)
    for y in range(30, 870, 48):
        d.text((30, y), "The quick brown fox jumps over", font=fuente, fill="black")
    doc.save(tmp_path / "doc.jpg")
    Image.new("RGB", (900, 900), (60, 120, 60)).save(tmp_path / "liso.jpg")
    assert ef.fraccion_texto(tmp_path / "doc.jpg") > ef.UMBRAL_TEXTO_OCR
    assert ef.fraccion_texto(tmp_path / "liso.jpg") == 0
