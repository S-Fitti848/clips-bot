"""Videos de archive.org en efemérides (2026-10-08): una descarga lenta nunca tira la efeméride,
licencia explícita en los metadatos del item y lista negra de estudios y marcas."""
import subprocess
from pathlib import Path

import pytest

from clips_bot import videos_libres as vl


def test_licencia_explicita_en_los_metadatos():
    assert vl.licencia_archive({"licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/"}) == "Dominio público"
    assert vl.licencia_archive({"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/"}) == "CC0"
    assert vl.licencia_archive({"licenseurl": "https://creativecommons.org/licenses/by/4.0/"}) == "CC BY 4.0"
    for mala in ("https://creativecommons.org/licenses/by-nc/3.0/", "https://creativecommons.org/licenses/by-sa/4.0/",
                 "https://creativecommons.org/licenses/by-nd/4.0/", "http://example.com/license"):
        assert vl.licencia_archive({"licenseurl": mala}) == ""
    assert vl.licencia_archive({"rights": "This film is in the public domain."}) == "Dominio público"
    assert vl.licencia_archive({"rights": "Public domain, non-commercial use only"}) == ""
    assert vl.licencia_archive({"rights": "© All rights reserved"}) == ""
    assert vl.licencia_archive({}) == ""                       # si no lo dice, descartado


def test_marcas_prohibidas():
    for t in ("Walt Disney's Steamboat Willie", "disneyland_1955", "Warner Bros. cartoon",
              "Universal Newsreel 1957", "20th Century Fox Movietone", "Paramount News",
              "Sony Pictures", "DreamWorks trailer", "Marvel comics", "Nintendo commercial", "pixar short"):
        assert vl.marca_prohibida(t), t
    assert vl.marca_prohibida("Sputnik launch newsreel", "British Pathé") == ""
    assert vl.marca_prohibida(["moon", "x"], ["Disney"]) == "disney"


class Sesion:
    """archive.org falso: búsqueda + metadatos por item."""
    def __init__(self, items):
        self.items = items
        self.headers = {}

    def get(self, url, params=None, timeout=None, **kw):
        class R:
            status_code = 200

            def __init__(s, d):
                s.d = d

            def json(s):
                return s.d

            def raise_for_status(s):
                pass
        if "advancedsearch" in url:
            return R({"response": {"docs": [{"identifier": i, "title": i, "year": "1957"} for i in self.items]}})
        ident = url.rsplit("/", 1)[1]
        md = self.items[ident]
        return R({"metadata": md, "files": [{"name": "film.mp4", "size": "5000000", "length": "60"}]})


def test_archive_solo_lo_libre_y_sin_marcas():
    b = vl.Buscador(session=Sesion({
        "new_moon_1957": {"title": "New Moon", "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/"},
        "disney_space_1957": {"title": "Man in Space", "creator": "Walt Disney",
                              "licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/"},
        "sin_licencia": {"title": "Rocket film"},
        "con_nc": {"title": "Rocket", "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"},
    }), sleep=lambda s: None)
    vs = b.archive("rocket launch", 1957, n=5)
    assert [v.pagina.rsplit("/", 1)[1] for v in vs] == ["new_moon_1957"]
    assert vs[0].licencia == "Dominio público"


def test_un_servidor_lento_saltea_el_video_sin_tumbar_nada(tmp_path, monkeypatch):
    llamadas = []

    def lento(*a, **k):
        llamadas.append(k.get("timeout"))
        raise subprocess.TimeoutExpired(a[0], k.get("timeout"))

    monkeypatch.setattr(vl.subprocess, "run", lento)
    v = vl.Video("archive", "x", "https://archive.org/download/x/x.mp4", "https://archive.org/details/x",
                 "Dominio público", "a", 1957, 60.0)
    out = vl.sacar_frames(v, tmp_path, "f")
    assert out.frames == [] and len(llamadas) == 2              # un reintento y se saltea
    assert all(t == vl.TOPE_FRAME_S for t in llamadas)
    llamadas.clear()
    v.momento = 10
    with pytest.raises(RuntimeError, match="no bajó"):
        vl.bajar_tramo(v, 4.0, tmp_path / "tramo.mp4")
    assert llamadas == [vl.TOPE_TRAMO_S, vl.TOPE_TRAMO_S]
    assert vl.duracion_url(v.url) == 0.0


def test_buscar_videos_sigue_si_un_video_explota(tmp_path, monkeypatch):
    from clips_bot import efemerides as ef

    v1 = vl.Video("archive", "a", "u1", "p1", "CC0", "x", 1957, 30.0)
    v2 = vl.Video("commons", "b", "u2", "p2", "CC0", "x", 1957, 30.0)

    class B:
        def candidatos(self, *a, **k):
            return [v1, v2]

    def frames(v, carpeta, nombre):
        if v is v1:
            raise subprocess.TimeoutExpired("ffmpeg", 60)
        v.frames = ["f.jpg"]
        return v

    monkeypatch.setattr(vl, "sacar_frames", frames)
    g = ef.Guion(frases=["a"], fotos=[], descartadas=[], titulo="", descripcion="", hashtags=[],
                 mostrar=["1957 rocket launch"], accion=[0])
    out = ef.buscar_videos(g, 1957, tmp_path, buscador=B())
    assert out[0] == [v2]
