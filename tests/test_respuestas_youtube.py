"""Las respuestas completas de YouTube (2026-10-09: los dos videos de /demo desaparecieron sin rastro):
al subir, al cancelar, y el chequeo del estado 2 minutos después."""
import json
from dataclasses import replace

import pytest

import clips_bot.__main__ as m
import clips_bot.youtube as yt
from clips_bot import db
from clips_bot.config import load_settings


class Resp:
    def __init__(self, status, cuerpo, headers=None):
        self.status_code, self._c, self.headers = status, cuerpo, headers or {}
        self.text = json.dumps(cuerpo)

    def json(self):
        return self._c


class Sesion:
    def __init__(self, items=None, put_status=200):
        self.items, self.put_status, self.pedidos = items, put_status, []

    def post(self, url, **kw):
        self.pedidos.append(("POST", url))
        return Resp(200, {}, {"Location": "https://upload/x"})

    def put(self, url, **kw):
        self.pedidos.append(("PUT", url))
        if "upload" in url:
            return Resp(200, {"id": "VID1", "status": {"uploadStatus": "uploaded", "privacyStatus": "private",
                                                       "publishAt": "2026-10-10T16:00:00Z"}})
        return Resp(self.put_status, {"id": "VID1", "status": {"privacyStatus": "private"}}
                    if self.put_status == 200 else {"error": {"message": "forbidden"}})

    def get(self, url, **kw):
        self.pedidos.append(("GET", url))
        return Resp(200, {"items": self.items or [], "pageInfo": {"totalResults": len(self.items or [])}})

    def delete(self, *a, **k):
        raise AssertionError("nunca se borra un video")


class _ClienteReal(yt.Cliente):          # el de verdad, sin OAuth
    def _headers(self):
        return {"Authorization": "Bearer t"}


def _cliente(sesion):
    return _ClienteReal("rots", session=sesion, token={"refresh_token": "r"})


def test_subir_guarda_la_respuesta_completa(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    sesion = Sesion()
    monkeypatch.setattr(yt, "Cliente", lambda canal: _cliente(sesion))
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 100)
    meta = {"clip_id": "demo_1", "salida": str(video), "textos": {"titulo": "t", "descripcion": "d", "hashtags": []}}
    m._programar_subida(conn, replace(load_settings(), youtube_upload_enabled=False), meta, "rots", "13:00", demo=True)
    fila = conn.execute("SELECT respuesta FROM subidas WHERE clip_id = 'demo_1'").fetchone()
    r = json.loads(fila[0])
    assert r["status"]["uploadStatus"] == "uploaded" and r["status"]["publishAt"]


@pytest.mark.parametrize("put_status", [200, 403])
def test_cancelar_es_videos_update_y_guarda_la_respuesta_aunque_falle(tmp_path, monkeypatch, put_status):
    conn = db.connect(tmp_path / "t.db")
    sid = db.crear_subida(conn, "demo_1", "rots", "programada", video_id="VID1", publish_at="2026-10-10T16:00:00Z")
    sesion = Sesion(put_status=put_status)
    monkeypatch.setattr(yt, "Cliente", lambda canal: _cliente(sesion))
    s = db.subidas(conn, ("programada",))[0]
    if put_status == 200:
        m._cancelar_youtube(conn, s)
    else:
        with pytest.raises(yt.YouTubeError):
            m._cancelar_youtube(conn, s)
    assert sesion.pedidos == [("PUT", f"{yt.API}/videos")]          # videos.update, nada de delete
    r = json.loads(conn.execute("SELECT respuesta_cancelar FROM subidas WHERE id = ?", (sid,)).fetchone()[0])
    assert r["http"] == put_status


class TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, teclado=None):
        self.mensajes.append((chat, texto))


def test_chequeo_a_los_2_minutos(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    a = db.crear_subida(conn, "demo_a", "rots", "programada", video_id="EXISTE")
    b = db.crear_subida(conn, "demo_b", "rots", "programada", video_id="BORRADO")
    c = db.crear_subida(conn, "demo_c", "rots", "programada", video_id="RECHAZADO")
    db.crear_subida(conn, "efe_fb", "facebook", "programada", video_id="FB1")    # Facebook no se chequea acá
    viejo = db.crear_subida(conn, "demo_viejo", "rots", "programada", video_id="VIEJO")
    conn.execute("UPDATE subidas SET creada = datetime('now', '-3 minutes')")
    conn.execute("UPDATE subidas SET creada = datetime('now', '-3 days') WHERE id = ?", (viejo,))
    conn.commit()
    items = {"EXISTE": [{"id": "EXISTE", "snippet": {"channelId": "UCz"}, "status": {"uploadStatus": "processed",
                                                                                     "privacyStatus": "private"}}],
             "BORRADO": [],
             "RECHAZADO": [{"id": "RECHAZADO", "snippet": {}, "status": {"uploadStatus": "rejected",
                                                                        "rejectionReason": "duplicate"}}]}

    class Cli:
        def __init__(self, canal):
            pass

        def estado_video(self, vid):
            sesion = Sesion(items=items[vid])
            return _cliente(sesion).estado_video(vid)

    tg = TG()
    assert m._chequeo_subidas_tick(conn, tg, cliente_de=Cli) == 3
    estados = {r[0]: json.loads(r[1]) for r in conn.execute("SELECT id, chequeo FROM subidas WHERE chequeo IS NOT NULL")}
    assert estados[a]["existe"] is True and estados[a]["uploadStatus"] == "processed"
    assert estados[b]["existe"] is False
    assert estados[c]["rejectionReason"] == "duplicate"
    assert viejo not in estados                                      # lo de antes de esto no se re-chequea
    assert len(tg.mensajes) == 2 and all(ch == m.DUENO for ch, _ in tg.mensajes)
    assert m._chequeo_subidas_tick(conn, tg, cliente_de=Cli) == 0      # una sola vez por subida


def test_un_subido_recien_no_se_chequea_antes_de_2_minutos(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.crear_subida(conn, "demo_a", "rots", "programada", video_id="X")
    assert db.subidas_sin_chequear(conn, minutos=2) == []
