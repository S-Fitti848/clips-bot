"""Santi, 2026-11-16: a las 24 h de cada Reel de Facebook (Pequeña Historia y Así Nació), el resumen con el gancho
contra la mediana de los otros Reels del canal, una vez, guardado para el informe del 26/11."""

import json
from datetime import datetime, timedelta, timezone

from clips_bot import __main__ as m
from clips_bot import db
from clips_bot import stats_fb as sf
from clips_bot.config import load_settings

T0 = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)


def test_curva_y_retencion():
    pts = sf.curva({"0": 1, "3": 1, "4": 0.68, "9": 0.4, "10": 0.32, "35": 0.12, "x": 5})
    assert sf.retencion_en(pts, 4) == 68.0 and sf.retencion_en(pts, 10) == 32.0
    assert sf.retencion_en(pts, 20) == 32.0 and pts[-1] == (35, 0.12)


class _TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, *a, **k):
        self.mensajes.append((chat, texto))



def _fake(vistas):
    def medir(canal, vid, pub):
        return {"vistas": vistas.get(vid, 100), "pasa_3s": 70.0, "ret_10": 40.0, "ret_final": 15.0, "medio_s": 6.0,
                "seguidores_reel": 1, "reacciones": 5, "comentarios": 2, "compartidos": 1, "interaccion": 8,
                "link": f"https://fb/{vid}"}
    return medir


def test_a_las_24h_manda_una_vez_con_la_mediana(monkeypatch, tmp_path):
    conn = db.connect(tmp_path / "c.db")
    subidas = [{"canal": "facebook", "video_id": "v1", "clip_id": "historia_fb_1115_1925",
                "publish_at": (T0 - timedelta(hours=30)).isoformat()},
               {"canal": "facebook", "video_id": "v0", "clip_id": "a", "publish_at": (T0 - timedelta(days=5)).isoformat()},
               {"canal": "facebook", "video_id": "v9", "clip_id": "b", "publish_at": (T0 - timedelta(hours=3)).isoformat()},
               {"canal": "youtube", "video_id": "y", "clip_id": "c", "publish_at": (T0 - timedelta(hours=30)).isoformat()}]
    monkeypatch.setattr(db, "subidas", lambda conn, estados=None: subidas)
    monkeypatch.setattr(sf, "gancho_y_titulo", lambda clip, root: ("Una ciudad eligió su cumpleaños.", "CDMX"))
    tg = _TG()
    m._fb_24h_tick(conn, tg, load_settings(), ahora=T0, medir=_fake({"v1": 900, "v0": 300}))
    assert len(tg.mensajes) == 1                          # solo el de 24-48 h (ni el viejo ni el de 3 h)
    chat, texto = tg.mensajes[0]
    assert chat == m.DUENO and texto.startswith("🔧 Claude Code:") and "Pequeña Historia" in texto
    assert "«Una ciudad eligió su cumpleaños.»" in texto and "Reproducciones: 900 (200)" in texto
    assert "datos de hoy" in texto                        # todavía sin 3 medidos a las 24 h
    m._fb_24h_tick(conn, tg, load_settings(), ahora=T0 + timedelta(hours=1), medir=_fake({}))
    assert len(tg.mensajes) == 1                          # una sola vez
    guardado = sf.cargar(conn)["v1"]
    assert guardado["gancho"] and guardado["canal"] == "facebook" and guardado["vistas"] == 900
    assert "Reels de Facebook a las 24 h" in sf.resumen_informe(conn)


def test_el_gancho_sale_de_lo_guardado(tmp_path):
    (tmp_path / "output" / "ready").mkdir(parents=True)
    (tmp_path / "output" / "ready" / "historia_fb_1115_1925.json").write_text(json.dumps(
        {"textos": {"titulo": "T"}, "efemeride": {"guion": ["El gancho.", "Segunda."]}}), encoding="utf-8")
    assert sf.gancho_y_titulo("historia_fb_1115_1925", tmp_path) == ("El gancho.", "T")
    d = tmp_path / "output" / "animacion" / "20261116_2"
    d.mkdir(parents=True)
    (d / "guion.json").write_text(json.dumps({"guion": {"titulo": "Play", "escenas": [{"frase": "¡Explotó!"}]}}),
                                  encoding="utf-8")
    gancho, titulo = sf.gancho_y_titulo("asinacio_20261116_2", tmp_path)
    assert titulo == "Play"
    assert sf.gancho_y_titulo("no_existe", tmp_path) == ("", "")


def test_publicacion_de_comunidad_programada(tmp_path, monkeypatch):
    """Santi, 2026-11-16: 1 por día a las 13:00 con la historia de hoy (apagado hasta que apruebe los ejemplos)."""
    from dataclasses import replace
    from pathlib import Path

    from PIL import Image

    from clips_bot import comunidad_fb as cf
    from clips_bot import config

    conn = db.connect(tmp_path / "c.db")
    s = load_settings()
    assert s.historias_fb.comunidad is True and s.historias_fb.comunidad_hora == "13:00"   # prendida el 16/11
    tg = _TG()
    ahora = datetime(2026, 11, 17, 10, 30, tzinfo=m.AR)
    m._comunidad_tick(conn, tg, replace(s, historias_fb=replace(s.historias_fb, comunidad=False)), ahora=ahora)
    assert not tg.mensajes                                       # apagado: nada
    s = replace(s, historias_fb=replace(s.historias_fb, comunidad=True))
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    m._comunidad_tick(conn, tg, s, ahora=ahora)
    assert not tg.mensajes and m.db.get_valor(conn, m.COMUNIDAD_DIA) is None   # sin la historia de hoy, espera
    db.set_valor(conn, f"{m.PH_LATAM}:2026-11-17", json.dumps([{"texto": "1907 Nacozari: el maquinista", "articulo": "Jesús García",
                                                                "pais": "México"}]))
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (900, 700), "gray").save(foto)
    monkeypatch.setattr(cf, "fotos_candidatas", lambda wiki, h, c: [(foto, "Foto: X · Dominio público")])
    monkeypatch.setattr(cf, "foto_que_coincide", lambda cli, h, cand: (cand[0], "el maquinista"))

    class Cli:
        def json(self, *a, **k):
            return json.dumps({"pregunta": "¿Tu abuelo te contó esta historia?", "texto": "En 1907 un maquinista salvó a Nacozari."})

    hechos = []
    tg.send_photo = lambda chat, path, caption="": hechos.append((Path(path), caption))
    m._comunidad_tick(conn, tg, s, ahora=ahora, cliente=Cli(), wiki=object(), revisor=object(),
                      programar=lambda img, msg, cuando, v, p, t: hechos.append((cuando, msg)) or "post_1")
    cuando, msg = hechos[0]
    assert cuando.hour == 13 and "¿Tu abuelo te contó esta historia?" in msg and "Foto: X" in msg
    sub = [x for x in db.subidas(conn) if x["canal"] == cf.CANAL][0]
    assert sub["video_id"] == "post_1" and sub["publish_at"].startswith("2026-11-17T16:00")
    assert hechos[1][0].exists()
    m._comunidad_tick(conn, tg, s, ahora=ahora.replace(hour=11))
    assert len([x for x in db.subidas(conn) if x["canal"] == cf.CANAL]) == 1      # una por día


class _Revisor:
    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.imagenes = []

    def json(self, sistema, prompt, schema, temp, imagenes=None):
        self.imagenes.append(len(imagenes or []))
        return json.dumps(self.respuestas.pop(0))


def _fotos(tmp_path, n):
    from PIL import Image

    out = []
    for k in range(n):
        p = tmp_path / f"c{k}.jpg"
        Image.new("RGB", (900, 700), "gray").save(p)
        out.append((p, f"Foto: autor{k} · CC BY"))
    return out


def test_comunidad_nunca_politicos_salvo_el_protagonista(tmp_path):
    """Santi, 2026-11-17: la de Colón salió con los presidentes del Mercosur."""
    from clips_bot import comunidad_fb as cf

    cand = _fotos(tmp_path, 3)
    h = {"texto": "Colón de Santa Fe salió campeón por primera vez en 116 años."}
    r = _Revisor({"mejor": 1, "fotos": [
        {"n": 1, "se_ve": "presidentes en una cumbre", "coincide": True, "politico": True, "protagonista": False},
        {"n": 2, "se_ve": "hinchas de Colón festejando", "coincide": True, "politico": False, "protagonista": False},
        {"n": 3, "se_ve": "un río", "coincide": False, "politico": False, "protagonista": False}]})
    foto, por_que = cf.foto_que_coincide(r, h, cand)
    assert foto == cand[1] and "hinchas" in por_que and r.imagenes == [3]
    # la historia ES de ese político: vale
    r = _Revisor({"mejor": 1, "fotos": [{"n": 1, "se_ve": "Perón", "coincide": True, "politico": True,
                                          "protagonista": True}]})
    assert cf.foto_que_coincide(r, {"texto": "Perón…"}, cand[:1])[0] == cand[0]
    r = _Revisor({"mejor": 0, "fotos": [{"n": 1, "se_ve": "presidentes", "coincide": False, "politico": True,
                                          "protagonista": False}]})
    foto, por_que = cf.foto_que_coincide(r, h, cand[:1])
    assert foto is None and "político" in por_que


def test_comunidad_cambia_de_tema_y_si_no_hay_no_sale(tmp_path, monkeypatch):
    from clips_bot import comunidad_fb as cf
    from clips_bot import config

    conn = db.connect(tmp_path / "c.db")
    s = load_settings()
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    ahora = datetime(2026, 11, 18, 10, 30, tzinfo=m.AR)
    db.set_valor(conn, f"{m.PH_LATAM}:2026-11-18", json.dumps([
        {"texto": "Colón campeón", "articulo": "Colón", "pais": "Argentina"},
        {"texto": "1907 Nacozari: el maquinista", "articulo": "Jesús García", "pais": "México"}]))
    fotos = _fotos(tmp_path, 1)
    monkeypatch.setattr(cf, "fotos_candidatas", lambda wiki, h, c: fotos)
    vistos = []
    monkeypatch.setattr(cf, "foto_que_coincide", lambda cli, h, cand: (
        vistos.append(h["texto"]), (None, "presidentes") if "Colón" in h["texto"] else (cand[0], "el tren"))[1])

    class Cli:
        def json(self, *a, **k):
            return json.dumps({"pregunta": "¿Tu abuelo te contó esta historia?", "texto": "En 1907 un maquinista."})

    tg = _TG()
    hechos = []
    tg.send_photo = lambda chat, path, caption="": hechos.append(caption)
    m._comunidad_tick(conn, tg, s, ahora=ahora, cliente=Cli(), wiki=object(), revisor=object(),
                      programar=lambda img, msg, cuando, v, p, t: hechos.append(msg) or "post_2")
    assert vistos == ["Colón campeón", "1907 Nacozari: el maquinista"] and "maquinista" in hechos[0]
    # ninguna coincide: no sale y avisa
    conn2 = db.connect(tmp_path / "d.db")
    db.set_valor(conn2, f"{m.PH_LATAM}:2026-11-18", json.dumps([{"texto": "Colón campeón", "articulo": "Colón"}]))
    tg2 = _TG()
    m._comunidad_tick(conn2, tg2, s, ahora=ahora, cliente=Cli(), wiki=object(), revisor=object(),
                      programar=lambda *a: pytest.fail("no se publica"))
    assert any("NO sale la publicación de comunidad" in t for _, t in tg2.mensajes)
    assert not [x for x in db.subidas(conn2) if x["canal"] == cf.CANAL]
