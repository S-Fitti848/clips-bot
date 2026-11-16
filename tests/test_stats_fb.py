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
    monkeypatch.setattr(cf, "foto_de_la_historia", lambda wiki, h, c: (foto, "Foto: X · Dominio público"))

    class Cli:
        def json(self, *a, **k):
            return json.dumps({"pregunta": "¿Tu abuelo te contó esta historia?", "texto": "En 1907 un maquinista salvó a Nacozari."})

    hechos = []
    tg.send_photo = lambda chat, path, caption="": hechos.append((Path(path), caption))
    m._comunidad_tick(conn, tg, s, ahora=ahora, cliente=Cli(), wiki=object(),
                      programar=lambda img, msg, cuando, v, p, t: hechos.append((cuando, msg)) or "post_1")
    cuando, msg = hechos[0]
    assert cuando.hour == 13 and "¿Tu abuelo te contó esta historia?" in msg and "Foto: X" in msg
    sub = [x for x in db.subidas(conn) if x["canal"] == cf.CANAL][0]
    assert sub["video_id"] == "post_1" and sub["publish_at"].startswith("2026-11-17T16:00")
    assert hechos[1][0].exists()
    m._comunidad_tick(conn, tg, s, ahora=ahora.replace(hour=11))
    assert len([x for x in db.subidas(conn) if x["canal"] == cf.CANAL]) == 1      # una por día
