"""Portada de Pequeña Historia (2026-10-20): el cuadro con el año FINAL, no a mitad de la cuenta
(la del Al Capone mostraba "1880")."""
import json
from pathlib import Path

import clips_bot.__main__ as m
from clips_bot import facebook, graficos
from clips_bot.config import load_settings


def test_portada_despues_de_la_cuenta_y_antes_del_fundido():
    assert graficos.CONTAR_S + 0.26 < graficos.PORTADA_S < graficos.AÑO_HASTA_S - 0.25
    assert graficos.PORTADA_S < 2.0      # sin gráficos, el cartel del año dura 2 s: también se ve


def test_el_cuadro_de_la_portada_tiene_el_anio_final(tmp_path):
    # el ASS del año: en PORTADA_S solo está activo el evento del año final
    ev = graficos.anio_contando(1931)
    activos = []
    for linea in ev:
        _, a, b, *_ , texto = linea.split(",", 9)
        def seg(t):
            h, mi, s = t.split(":")
            return int(h) * 3600 + int(mi) * 60 + float(s)
        if seg(a) <= graficos.PORTADA_S < seg(b):
            activos.append(texto)
    assert len(activos) == 1 and activos[0].endswith("1931")


class Resp:
    status_code = 200

    def __init__(self, d):
        self._d = d
        self.text = json.dumps(d)

    def json(self):
        return self._d


class Sesion:
    def __init__(self):
        self.posts = []

    def post(self, url, **kw):
        self.posts.append((url, kw.get("data"), sorted((kw.get("files") or {}).keys())))
        return Resp({"success": True})


def test_facebook_sube_la_portada_preferida(tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(b"jpg")
    s = Sesion()
    facebook.poner_portada("123", img, "v23.0", token="t", session=s)
    url, data, files = s.posts[0]
    assert url.endswith("/123/thumbnails") and data["is_preferred"] == "true" and files == ["source"]


def test_subir_a_facebook_pone_la_portada_y_si_falla_sigue(tmp_path, monkeypatch):
    from clips_bot import db

    conn = db.connect(tmp_path / "t.db")
    video = tmp_path / "efe.mp4"
    video.write_bytes(b"x")
    meta = {"clip_id": "efemeride_1017_1931", "salida": str(video), "efemeride": {"anio": 1931},
            "textos": {"titulo": "t", "descripcion": "d", "hashtags": []}}
    monkeypatch.setattr(facebook, "subir_reel", lambda *a, **k: "VID")
    monkeypatch.setattr(m, "_portada_de", lambda meta: tmp_path / "p.jpg")
    puestas = []
    monkeypatch.setattr(facebook, "poner_portada", lambda vid, img, version: puestas.append((vid, img.name)))
    m._subir_facebook(conn, load_settings(), meta)
    assert puestas == [("VID", "p.jpg")]

    def falla(*a, **k):
        raise facebook.FacebookError("no")

    monkeypatch.setattr(facebook, "poner_portada", falla)
    meta2 = dict(meta, clip_id="efemeride_1018_2019")
    assert "No pude" not in m._subir_facebook(conn, load_settings(), meta2)


def test_un_clip_comun_no_lleva_portada():
    assert m._portada_de({"clip_id": "clip_x", "salida": "x.mp4"}) is None


def test_youtube_thumbnails_set(tmp_path):
    import clips_bot.youtube as yt

    class Cli(yt.Cliente):
        def _headers(self):
            return {"Authorization": "Bearer t"}

    img = tmp_path / "p.jpg"
    img.write_bytes(b"jpg")
    s = Sesion()
    c = Cli("pequena_historia", session=s, token={"refresh_token": "r"})
    c.poner_portada("VID", img)
    assert s.posts[0][0] == yt.THUMBNAILS and c.respuesta_portada["http"] == 200
