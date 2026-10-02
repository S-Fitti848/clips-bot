"""Más fuentes de fotos (2026-10-02). Sin red: la sesión es falsa."""

import io

import pytest
from PIL import Image

from clips_bot import fuentes_fotos as ff


class R:
    def __init__(self, d=None, contenido=b"", status=200):
        self._d, self.content, self.status_code = d, contenido, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise __import__("requests").HTTPError(str(self.status_code))

    def json(self):
        return self._d

    def iter_content(self, n):
        yield self.content


class S:
    def __init__(self, por_url):
        self.por_url, self.pedidos, self.headers = por_url, [], {}

    def get(self, url, params=None, timeout=None, headers=None, stream=False):
        self.pedidos.append((url, params))
        for clave, r in self.por_url.items():
            if clave in url:
                return r
        return R({})


def test_openverse_solo_licencias_libres_y_anchas():
    s = S({"openverse": R({"results": [
        {"id": "a", "url": "u1", "width": 1600, "height": 900, "license": "by", "license_version": "2.0",
         "creator": "Ana", "title": "Buenos Aires 1924", "source": "flickr", "foreign_landing_url": "p"},
        {"id": "b", "url": "u2", "width": 500, "height": 400, "license": "cc0", "title": "chica"},
        {"id": "c", "url": "u3", "width": 2000, "height": 1000, "license": "by-nc", "title": "NC"}]})})
    out = ff.Fuentes(session=s, sleep=lambda _: None).openverse("x")
    assert [(o["archivo"], o["licencia"], o["anio"]) for o in out] == [("openverse:a", "CC BY 2.0", 1924)]


def test_europeana_lee_los_derechos():
    s = S({"europeana": R({"items": [
        {"id": "/1/a", "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"], "edmIsShownBy": ["u"],
         "title": ["Tango"], "year": ["1925"], "dataProvider": ["Museo"], "guid": "g"},
        {"id": "/1/b", "rights": ["http://rightsstatements.org/vocab/InC/1.0/"], "edmIsShownBy": ["u2"]}]})})
    out = ff.Fuentes(session=s, sleep=lambda _: None).europeana("tango")
    assert [(o["licencia"], o["autor"], o["anio"]) for o in out] == [("Dominio público", "Museo", 1925)]


def test_el_orden_corta_al_juntar_y_pexels_solo_para_hoy(monkeypatch):
    f = ff.Fuentes(session=S({}), sleep=lambda _: None)
    llamadas = []

    def fuente(nombre, n):
        def buscar(q, n_=4):
            llamadas.append((nombre, q))
            return [{"archivo": f"{nombre}:{q}:{k}", "url": "u", "ancho": 1000, "alto": 800,
                     "licencia": "CC0", "autor": "", "epigrafe": "foto", "pagina": "", "anio": None}
                    for k in range(n)]
        return buscar

    for nombre, n in (("openverse", 0), ("smithsonian", 2), ("europeana", 5), ("flickr", 5),
                      ("pexels", 5), ("unsplash", 5), ("nasa", 5)):
        monkeypatch.setattr(f, nombre, fuente(nombre, n))
    out = ff.BUSCAR_REAL(f, ["a b c", "a b"], presente=False, de_espacio=False, cuantas=4)
    assert [o["fuente"] for o in out] == ["smithsonian", "smithsonian", "europeana", "europeana"]
    assert ("openverse", "a b") in llamadas                     # probó la consulta más general
    assert not any(n == "pexels" for n, _ in llamadas)
    llamadas.clear()
    ff.BUSCAR_REAL(f, ["x"], presente=True, de_espacio=False, cuantas=40)
    assert any(n == "pexels" for n, _ in llamadas) and not any(n == "nasa" for n, _ in llamadas)


def test_bajar_achica_y_guarda_en_cache(tmp_path):
    buf = io.BytesIO()
    Image.new("RGB", (2400, 1600), (10, 20, 30)).save(buf, "JPEG")
    s = S({"img": R(contenido=buf.getvalue())})
    p = ff.bajar("https://x/img.jpg", tmp_path / "a.jpg", tmp_path / "cache", session=s, sleep=lambda _: None)
    assert Image.open(p).size == (1280, 853)
    ff.bajar("https://x/img.jpg", tmp_path / "b.jpg", tmp_path / "cache", session=s, sleep=lambda _: None)
    assert len(s.pedidos) == 1                                   # la segunda vez, de la caché
    chica = io.BytesIO()
    Image.new("RGB", (500, 400)).save(chica, "JPEG")
    with pytest.raises(ValueError):
        ff.bajar("https://x/chica", tmp_path / "c.jpg", None, session=S({"chica": R(contenido=chica.getvalue())}),
                 sleep=lambda _: None)


def test_es_argentino():
    assert ff.es_argentino("Cesáreo Onzari marca el primer gol olímpico ante Uruguay en Buenos Aires")
    assert not ff.es_argentino("La Unión Soviética lanza el Sputnik")


def test_una_foto_chica_de_la_epoca_pasa_y_una_moderna_no():
    from clips_bot import efemerides as ef

    def info(ancho, fecha, nombre="File:Gol olimpico 1924.jpg"):
        return {"archivo": nombre, "mime": "image/jpeg", "width": ancho,
                "extmetadata": {"LicenseShortName": {"value": "Public domain"},
                                "DateTimeOriginal": {"value": fecha}}}

    assert ef.motivo_foto(info(694, "1925"), anio_hecho=1924) is None          # Onzari, 694 px
    assert ef.motivo_foto(info(694, "2012", "File:Estadio.jpg"), anio_hecho=1924).startswith("menos de 800")
    assert ef.motivo_foto(info(400, "1924"), anio_hecho=1924).startswith("menos de 800")   # muy chica
    assert ef.motivo_foto(info(694, "1925")).startswith("menos de 800")                     # sin hecho, como antes
