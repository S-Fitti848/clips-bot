"""/buscar "viejos" (2026-11-01): los Shorts de otros canales que más pegaron en los últimos meses,
buscados en el stream con el embudo de "pegó" y cortados de ahí, salteando lo que ya subí. Sin red."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import clips_bot.__main__ as m
from clips_bot import db, pego
from clips_bot.config import Pego, Streamer, load_settings

DAVO = Streamer("davooxeneize", plataforma="kick", experimento=True, apodos=("Davo",))
AHORA = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def _short(sid, titulo, vistas=90000, dias=20, canal="OtroCanal", dur=40):
    return pego.ShortAjeno(sid, titulo, canal, vistas, dur,
                           (AHORA - timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ"))


def test_candidatos_viejos_filtra_y_ordena(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    shorts = [
        _short("a", "DAVO no puede creer lo que pasó", 50000),
        _short("b", "DAVO se enoja en vivo", 120000),
        _short("c", "TOP 5 ENOJOS DE DAVO"),                       # compilado
        _short("d", "DAVO y Gastón Edul debaten"),                 # nombra a otro
        _short("e", "DAVO el más viejo", dias=45),                 # antes del VOD más viejo
        _short("f", "DAVO otra vez", canal="Rots"),                # canal propio
        _short("g", "DAVO ya subido"),
        _short("h", "Davo poco visto", 200),                       # no pegó
        _short("i", "Hasta acá llegó Puerrul DAVO", canal="Gastón Edul"),   # del canal de otro
    ]
    pego.guardar(conn, shorts[6], "davooxeneize", None)
    conn.execute("UPDATE pegados SET vod_clip_id = 'vod_x' WHERE short_id = 'g'")
    db.registrar_clip(conn, "vod_x", "davooxeneize", "entregado", None)
    v = pego.candidatos_viejos(conn, DAVO, Pego(), "k", AHORA - timedelta(days=60), AHORA - timedelta(days=7),
                               AHORA - timedelta(days=30), ("Rots",), buscar=lambda q, d, k: shorts)
    assert [x.id for x in v.candidatos] == ["b", "a"]                      # los más vistos primero
    assert v.filtrados["compilado"] == 1 and v.filtrados["nombra a Gastón Edul"] == 1
    assert v.filtrados["es de antes del VOD más viejo que queda"] == 1
    assert v.filtrados["ya lo subí"] == 1
    assert v.filtrados["es del canal de Gastón Edul"] == 1
    assert "quedan 2 para buscar en el stream" in pego.texto_viejos(v)


def test_el_mismo_momento_que_ya_salio_no_se_vuelve_a_cortar(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    viejo, nuevo = _short("v1", "DAVO grita"), _short("v2", "DAVO grita (otro canal)")
    for x in (viejo, nuevo):
        pego.guardar(conn, x, "davooxeneize", None)
    conn.execute("UPDATE pegados SET vod_url = 'https://kick.com/d/videos/1', vod_segundo = 3000, "
                 "vod_clip_id = 'vod_kick_1_2990' WHERE short_id = 'v1'")
    db.registrar_clip(conn, "vod_kick_1_2990", "davooxeneize", "entregado", None)
    conn.commit()
    from clips_bot import vod_embudo as em

    monkeypatch.setattr(em, "bajar_pista", lambda sid, tmp: SimpleNamespace(publicado=None, duracion=30.0))
    monkeypatch.setattr(em, "buscar", lambda *a, **k: SimpleNamespace(
        vod=SimpleNamespace(pagina="https://kick.com/d/videos/1", titulo="stream", id="1", plataforma="kick"),
        segundo=3020.0, valor=0.97))
    monkeypatch.setattr("clips_bot.vod.vods_kick", lambda *a: [])
    monkeypatch.setattr(pego, "originales", lambda *a, **k: [])
    procesados = []
    r = pego.vod_de_un_short(conn, "v2", nuevo.titulo, nuevo.vistas, nuevo.publicado, nuevo.canal, DAVO,
                             Pego(), tmp_path, object(), procesar_tramo=lambda *a: procesados.append(a))
    assert r.encontrado and "ya lo subí" in r.resultado and procesados == []


def test_buscar_viejos_manda_los_clips_y_el_resumen(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    ready = tmp_path / "ready"
    ready.mkdir()
    monkeypatch.setattr("clips_bot.process.READY_DIR", ready)
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    monkeypatch.setattr(m, "_twitch", lambda: None)
    monkeypatch.setattr(m, "DATA_DIR", tmp_path)
    monkeypatch.setattr("clips_bot.vod.vods_kick", lambda *a: [SimpleNamespace(inicio=AHORA - timedelta(days=30))])
    cands = [_short("b", "DAVO se enoja", 120000), _short("a", "DAVO grita", 50000)]
    monkeypatch.setattr(pego, "candidatos_viejos",
                        lambda *a, **k: pego.Viejos("davooxeneize", 10, {"compilado": 2}, cands, AHORA))

    def un_short(conn, sid, *a, **k):
        if sid == "b":
            (ready / "vod_kick_9_100.json").write_text('{"textos": {"titulo": "t"}}', encoding="utf-8")
            return pego.EnVod(True, "vod_kick_9_100", "listo", SimpleNamespace(descartado=None))
        return pego.EnVod(False, None, "no apareció en los VODs")

    monkeypatch.setattr(pego, "vod_de_un_short", un_short)
    enviados, mensajes = [], []
    monkeypatch.setattr(m, "enviar_clip", lambda tg, chat, conn, cid, meta, n, *a, **k: enviados.append(cid) or 1)
    tg = SimpleNamespace(send_message=lambda chat, t, *a, **k: mensajes.append(t))
    settings = replace(load_settings())
    texto = m._buscar_viejos(conn, tg, "1", [DAVO], 3, settings, [DAVO], None, "tok")
    assert enviados == ["vod_kick_9_100"]
    assert "Listo: <b>1</b>" in texto and "no apareció en los VODs" in texto and "120.000 vistas" in texto
    assert "Viejos" in mensajes[0] and "2 compilado" in mensajes[0]
