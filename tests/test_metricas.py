"""Métricas del canal (§4b): emparejar los Shorts con los clips, guardar vistas / duración media /
% que lo mira entero, y los pesos por streamer y tipo de clip (solo con n ≥ min_n)."""

import json
from datetime import datetime, timedelta, timezone

from clips_bot import db, metricas, youtube
from clips_bot.config import Seleccion
from clips_bot.seleccion import Opcion, score

AHORA = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)


def _meta(cid, titulo, streamer="spreen", dias=3, dur=40, layout="split"):
    return {"clip_id": cid, "streamer": streamer, "duracion_s": dur, "layout": layout,
            "textos": {"titulo": titulo}, "entregado": {"fecha": (AHORA - timedelta(days=dias)).isoformat()}}


def test_empareja_por_titulo_y_despues_de_la_entrega():
    clips = [_meta("a", "Spreen se cae de la silla 😂"), _meta("b", "Coscu y el pato", dias=1)]
    videos = [{"id": "v1", "titulo": "Spreen se cae de la silla 😂 #shorts", "publicado": (AHORA - timedelta(days=2)).isoformat()},
              {"id": "v2", "titulo": "Coscu y el pato", "publicado": (AHORA - timedelta(days=5)).isoformat()},  # antes
              {"id": "v3", "titulo": "otra cosa", "publicado": AHORA.isoformat()}]
    pares = metricas.emparejar(videos, clips)
    assert {k: v["id"] for k, v in pares.items()} == {"a": "v1"}


class ClienteFalso:
    def mis_videos(self, desde):
        return [{"id": "v1", "titulo": "Spreen se cae de la silla", "publicado": AHORA.isoformat()}]

    def metricas(self, ids, desde, hasta):
        return {"v1": {"vistas": 1500, "duracion_media_s": 21.5, "pct_visto_medio": 71.0}}

    def pct_entero(self, vid, desde, hasta):
        return 64.2


def test_actualizar_guarda_por_clip(tmp_path):
    ready = tmp_path / "ready"
    ready.mkdir()
    (ready / "a.json").write_text(json.dumps(_meta("a", "Spreen se cae de la silla", dias=1)), encoding="utf-8")
    conn = db.connect(tmp_path / "t.db")
    assert metricas.actualizar(conn, ClienteFalso(), ready, ahora=AHORA) == 1
    fila = conn.execute("SELECT video_id, vistas, duracion_media_s, pct_visto_medio, pct_entero, "
                        "streamer, camara FROM metricas WHERE clip_id='a'").fetchone()
    assert fila == ("v1", 1500, 21.5, 71.0, 64.2, "spreen", 1)


def _cargar(conn, filas):
    for i, (streamer, vistas, dur, layout) in enumerate(filas):
        conn.execute("INSERT INTO metricas (clip_id, video_id, actualizado, vistas, streamer, duracion_s, "
                     "layout, camara) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (f"c{i}", f"v{i}", "x", vistas, streamer, dur, layout,
                      1 if layout in ("split", "fullcam") else 0))


def test_los_pesos_solo_se_mueven_con_n_suficiente(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    # mediana general 2500 (entre los 1000 de goncho y los 4000 de spreen)
    _cargar(conn, [("spreen", 4000, 40, "split")] * 15 + [("goncho", 1000, 40, "fit_blur")] * 15
            + [("coker", 100, 20, "fit_blur")] * 2 + [("coker", 50000, 20, "fit_blur")] * 2)
    t = metricas.factores(conn, 0.5, 15)
    assert "coker" not in t["streamer"]                     # 3 Shorts: se mide, no se toca
    assert t["streamer"]["spreen"] > 1 > t["streamer"]["goncho"]
    assert 0.5 <= t["streamer"]["goncho"] and t["streamer"]["spreen"] <= 1.5
    assert metricas.factores(conn, 0.0, 15) == {}           # peso 0: apagado
    assert metricas.factor_de({"streamer": "spreen", "duracion_s": 40, "layout": "split"}, t) > 1


def test_score_usa_el_factor_del_clip_antes_que_el_del_streamer():
    o = Opcion("x", "spreen", 100, AHORA, fuente="reciente")
    base = score(o, AHORA, Seleccion())
    assert score(o, AHORA, Seleccion(), {"spreen": 2.0}) == base * 2
    assert score(o, AHORA, Seleccion(), {"spreen": 2.0, "x": 3.0}) == base * 3


class Resp:
    def __init__(self, datos, status=200):
        self.status_code, self._d, self.text, self.headers = status, datos, json.dumps(datos), {}

    def json(self):
        return self._d


class Sesion:
    def __init__(self, respuestas):
        self.respuestas, self.pedidos = list(respuestas), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.pedidos.append((url, params))
        return self.respuestas.pop(0)


def test_cliente_lee_analytics(monkeypatch):
    s = Sesion([Resp({"rows": [["v1", 1500, 21.5, 71.0]]}),
                Resp({"rows": [[0.5, 0.9], [1.0, 0.642]]})])
    c = youtube.Cliente("rots", session=s, token={"refresh_token": "r"}, secreto={"client_id": "i", "client_secret": "s"})
    monkeypatch.setattr(c, "_headers", lambda: {})
    assert c.metricas(["v1"], AHORA, AHORA) == {"v1": {"vistas": 1500, "duracion_media_s": 21.5,
                                                        "pct_visto_medio": 71.0}}
    assert c.pct_entero("v1", AHORA, AHORA) == 64.2
    assert s.pedidos[0][1]["ids"] == "channel==MINE" and "averageViewPercentage" in s.pedidos[0][1]["metrics"]
    assert "yt-analytics.readonly" in " ".join(youtube.SCOPES)
