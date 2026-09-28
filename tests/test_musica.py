"""Biblioteca de música de Pequeña Historia: filtros por fuente, elección, no repetir y veto.

Sin red: los catálogos son datos de ejemplo con la forma real (probada el 2026-09-28).
"""

import json
import random

import pytest

from clips_bot import db, musica as mu


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _tema(ruta, fuente="kevin", etiquetas=()):
    return mu.Tema(ruta=ruta, titulo=ruta, autor="x", licencia="CC BY 4.0", link="l", fuente=fuente,
                   etiquetas=list(etiquetas))


# ---- lo que pone Santi en musica/youtube/ -----------------------------------------------------

def test_los_de_youtube_se_leen_del_nombre(tmp_path):
    yt = tmp_path / "youtube"
    yt.mkdir()
    for n in ("Happy Tails - Blue Deer Studio.mp3",
              "Shining (feat. Leon Albertson & Adryon de León) - Leon Albertson.mp3", "notas.txt"):
        (yt / n).write_bytes(b"x")
    temas = mu.cargar(tmp_path)
    assert [(t.titulo, t.autor, t.fuente) for t in temas] == [("Happy Tails", "Blue Deer Studio", "youtube")]


def test_youtube_tiene_prioridad():
    temas = [_tema("kevin/a.mp3", etiquetas=["happy"]), _tema("youtube/b.mp3", "youtube")]
    assert all(mu.elegir(temas, "alegre", azar=random.Random(s)).fuente == "youtube" for s in range(20))


def test_por_tono_elige_entre_los_que_mejor_coinciden():
    temas = [_tema("kevin/feliz.mp3", etiquetas=["happy", "bright"]),
             _tema("kevin/oscuro.mp3", etiquetas=["dark", "mysterious"]),
             _tema("kevin/nada.mp3")]
    assert mu.elegir(temas, "misterioso", azar=random.Random(1)).ruta == "kevin/oscuro.mp3"
    assert mu.elegir(temas, "alegre", azar=random.Random(1)).ruta == "kevin/feliz.mp3"


def test_no_repite_en_5_videos_seguidos():
    temas = [_tema(f"kevin/{i}.mp3") for i in range(7)]
    usados = []
    for s in range(30):
        t = mu.elegir(temas, recientes=usados, azar=random.Random(s))
        assert t.ruta not in usados[-5:]
        usados.append(t.ruta)


def test_con_pocos_temas_repite_el_mas_viejo_pero_nunca_un_vetado():
    temas = [_tema("kevin/a.mp3"), _tema("kevin/b.mp3"), _tema("kevin/c.mp3")]
    t = mu.elegir(temas, recientes=["kevin/a.mp3", "kevin/b.mp3", "kevin/c.mp3"],
                  vetados={"kevin/a.mp3"})
    assert t.ruta == "kevin/b.mp3"                      # el más viejo que no está vetado
    assert mu.elegir(temas, vetados={"kevin/a.mp3", "kevin/b.mp3", "kevin/c.mp3"}) is None


def test_recientes_y_vetados_en_la_db(conn):
    for r in ("a", "b", "a"):
        mu.anotar_uso(conn, r)
    assert mu.recientes(conn) == ["a", "b", "a"]
    assert mu.vetar(conn, "b") and not mu.vetar(conn, "b")
    assert mu.vetados(conn) == {"b"}


# ---- lo que se baja solo ------------------------------------------------------------------

def test_kevin_sin_voces_y_de_1_a_4_minutos():
    catalogo = [
        {"title": "Carefree", "filename": "Carefree.mp3", "length": "00:03:22",
         "instruments": "Piano, Bass", "feel": "Bright, Humorous", "description": "Silly"},
        {"title": "Larga", "filename": "Larga.mp3", "length": "00:05:07", "instruments": "Lute",
         "feel": "Epic"},
        {"title": "Coral", "filename": "Coral.mp3", "length": "00:02:00", "instruments": "Choir, Strings",
         "feel": "Epic"},
        {"title": "Corta", "filename": "Corta.mp3", "length": "00:00:40", "instruments": "Piano",
         "feel": "Calm"},
    ]
    t, = mu.candidatos_kevin(catalogo)
    assert (t.ruta, t.licencia, t.duracion_s) == ("kevin/Carefree.mp3", "CC BY 4.0", 202)
    assert "bright" in t.etiquetas and mu.puntaje(t, "alegre") >= 1
    assert "Kevin MacLeod (incompetech.com)" in t.credito() and "Attribution 4.0" in t.credito()


def _ov(**k):
    base = {"id": "abc123", "title": "Little Tomcat (Instrumental Version)", "creator": "Josh Woodward",
            "license": "by", "license_version": "3.0", "foreign_landing_url": "https://jamendo/1",
            "url": "https://jamendo/1.mp3", "duration": 197000, "filesize": 4_000_000,
            "genres": ["folk"], "tags": [{"name": "instrumental"}, {"name": "happy"}]}
    return {**base, **k}


@pytest.mark.parametrize("cambio,pasa", [
    ({}, True),
    ({"license": "cc0", "license_version": "1.0"}, True),
    ({"license": "by-nc"}, False),
    ({"license": "by-nd"}, False),
    ({"license": "by-sa"}, False),
    ({"duration": 30000}, False),
    ({"duration": 300000}, False),
    ({"title": "Little Tomcat", "tags": [{"name": "happy"}]}, False),          # sin "instrumental"
    ({"tags": [{"name": "instrumental"}, {"name": "vocals"}]}, False),
    ({"filesize": 40_000_000}, False),
])
def test_openverse_solo_cc0_y_cc_by_instrumental(cambio, pasa):
    temas = mu.candidatos_openverse([_ov(**cambio)])
    assert bool(temas) is pasa
    if pasa:
        assert temas[0].link == "https://jamendo/1" and temas[0].__dict__["_url"] == "https://jamendo/1.mp3"


def test_la_mezcla_baja_la_musica_cuando_habla_y_se_apaga_al_final():
    f = mu.filtro(0.12, 42.0)
    assert "volume=0.12" in f and "afade=t=out:st=40.50:d=1.5" in f
    assert "[mus][disparo]sidechaincompress" in f and "amix=inputs=2:duration=first" in f


class _Resp:
    def __init__(self, datos=None, contenido=b"", status=200):
        self.datos, self.content, self.status_code = datos, contenido, status

    def json(self):
        return self.datos


class _Sesion:
    """Catálogo de Kevin, Openverse vacío y los mp3 de 100 KB."""
    def __init__(self):
        self.pedidos, self.params_ov = [], []

    def get(self, url, **k):
        self.pedidos.append(url)
        if url == mu.OPENVERSE:
            self.params_ov.append(k.get("params"))
        if url == mu.KEVIN_CATALOGO:
            return _Resp([{"title": f"T{i}", "filename": f"T{i}.mp3", "length": "00:02:00",
                           "instruments": "Piano", "feel": f"{list(mu.TONOS.values())[i % 5][0]}"}
                          for i in range(12)])
        if url == mu.OPENVERSE:
            return _Resp({"results": []})
        return _Resp(contenido=b"x" * 100_000)


def test_llenar_completa_hasta_el_objetivo_y_anota_los_creditos(tmp_path):
    s = _Sesion()
    assert mu.llenar(tmp_path, por_fuente=5, session=s, azar=random.Random(0), pausa_s=0) == 5
    indice = json.loads((tmp_path / "biblioteca.json").read_text(encoding="utf-8"))
    assert len(indice) == 5 and all(v["licencia"] == "CC BY 4.0" for v in indice.values())
    assert len({tuple(v["etiquetas"][:1]) for v in indice.values()}) >= 4    # repartidos entre tonos
    assert mu.llenar(tmp_path, por_fuente=5, session=_Sesion(), pausa_s=0) == 0   # ya está lleno


def test_reclamo_sobre_una_efemeride_veta_el_tema_y_no_excluye_a_nadie(conn, tmp_path, monkeypatch):
    import clips_bot.__main__ as m
    from clips_bot import process

    monkeypatch.setattr(process, "READY_DIR", tmp_path)
    (tmp_path / "efemeride_0927_1822.json").write_text(json.dumps(
        {"clip_id": "efemeride_0927_1822", "efemeride": {"musica": "youtube/Happy Tails - X.mp3"}}))
    r = m._reclamo(conn, ["efemeride_0927_1822"])
    assert "queda vetado" in r and mu.vetados(conn) == {"youtube/Happy Tails - X.mp3"}
    assert db.excluidos(conn) == {}
    assert "ya estaba vetado" in m._reclamo(conn, ["efemeride_0927_1822"])


def test_youtube_toma_el_tono_del_titulo_y_de_tonos_json(tmp_path):
    yt = tmp_path / "youtube"
    yt.mkdir()
    (yt / "Happy Tails - Blue Deer Studio.mp3").write_bytes(b"x")
    (yt / "Vibe Check - Blue Deer Studio.mp3").write_bytes(b"x")
    (yt / "tonos.json").write_text(json.dumps({"Vibe Check - Blue Deer Studio.mp3": "misterioso"}))
    temas = {t.titulo: t for t in mu.cargar(tmp_path)}
    assert mu.puntaje(temas["Happy Tails"], "alegre") >= 1
    assert mu.puntaje(temas["Vibe Check"], "misterioso") >= 1
    assert mu.elegir(list(temas.values()), "misterioso").titulo == "Vibe Check"


def test_openverse_pide_de_a_20(tmp_path):
    s = _Sesion()
    mu.llenar(tmp_path, por_fuente=1, session=s, pausa_s=0)
    assert len(s.params_ov) == 2 * len(mu.TONOS)          # 2 páginas por tono
    assert all(p["page_size"] == 20 for p in s.params_ov)  # más que 20 da 401 sin cuenta
