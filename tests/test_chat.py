"""Picos de chat (chat.py): el ritmo del chat en el momento del clip contra el normal del stream."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from clips_bot.candidates import Clip, con_picos_de_chat
from clips_bot.chat import Chat, factor_pico
from clips_bot.telegram import por_que


class Resp:
    def __init__(self, edges):
        self._d = [{"data": {"video": {"comments": {"edges": edges, "pageInfo": {"hasNextPage": True}}}}}]

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


class SesionChat:
    """Un chat con `base` mensajes/s y `pico` mensajes/s entre 1000 y 1060 s. Cada pedido da una
    página de 50 mensajes desde el offset pedido (como la API real sin login)."""

    def __init__(self, base=2.0, pico=10.0):
        self.base, self.pico, self.pedidos = base, pico, 0

    def post(self, url, timeout=None, headers=None, json=None):
        self.pedidos += 1
        t = float(json[0]["variables"]["contentOffsetSeconds"])
        edges = []
        while len(edges) < 50:
            tasa = self.pico if 1000 <= t < 1060 else self.base
            edges.append({"node": {"contentOffsetSeconds": t}, "cursor": "x"})
            t += 1 / tasa
        return Resp(edges)


def test_ritmo_por_pagina_y_pico_contra_lo_normal():
    ch = Chat(session=SesionChat(base=2.0, pico=10.0))
    assert ch.ritmo("v", 100) == pytest.approx(2.0, rel=0.05)
    assert ch.ritmo("v", 1010) == pytest.approx(10.0, rel=0.05)
    assert ch.pico("v", 1015, duracion=6000) == pytest.approx(5.0, rel=0.1)


def test_el_ritmo_normal_se_mide_una_vez_por_vod():
    s = SesionChat()
    ch = Chat(session=s)
    ch.pico("v", 1015, 6000)
    antes = s.pedidos
    ch.pico("v", 3000, 6000)
    assert s.pedidos - antes == 3            # solo la ventana del momento (3 páginas)


def test_factor_pico_suma_y_nunca_resta():
    assert factor_pico(None, 0.5) == factor_pico(0.5, 0.5) == factor_pico(1.0, 0.5) == 1.0
    assert factor_pico(2.0, 0.5) == pytest.approx(1.25)
    assert factor_pico(4.0, 0.5) == factor_pico(16.0, 0.5) == pytest.approx(1.5)
    assert factor_pico(8.0, 0.0) == 1.0      # peso 0: apagado


def _clip(id, video="v1", offset=100):
    return Clip(id=id, url=f"https://clips.twitch.tv/{id}", broadcaster_login="auronplay",
                broadcaster_name="auron", title="t", view_count=10, duration=30, language="es",
                created_at=datetime(2026, 9, 28, tzinfo=timezone.utc), game_id="", game_name="",
                vod_offset=offset, video_id=video)


def test_los_picos_se_piden_solo_para_los_primeros_y_con_vod():
    class Twitch:
        def get_video_duracion(self, v):
            return 5000.0

    class ChatFalso:
        def pico(self, video_id, offset, duracion):
            return {"a": 3.5, "b": 1.2}.get(video_id, 0.0)

    clips = [_clip("x", "a"), replace(_clip("y", ""), vod_offset=None), _clip("z", "b")]
    out = con_picos_de_chat(clips, Twitch(), ChatFalso(), cuantos=2)
    assert [c.chat_pico for c in out] == [3.5, 0.0, 0.0]    # z quedó afuera de los primeros 2


def test_la_linea_muestra_el_chat():
    assert "chat ×5,2" in por_que({"vistas": 300, "clips_mismo_momento": 1, "chat_pico": 5.2})
