"""Modo escucha de Telegram: cola de /buscar y turno de trabajo pesado.

No hay red ni video: se reemplaza `_buscar` por una función que dice si el turno estaba libre.
"""

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import load_settings


class FakeTG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat_id, texto):
        self.mensajes.append(texto)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _falso_buscar(conn_, corridas):
    """Se comporta como el real: toma el turno pesado y devuelve OCUPADO si no puede."""

    def buscar(conn, tg, chat_id, args, settings, streamers, gemini):
        token = f"buscar:{args[0]}"
        if not db.tomar_turno(conn, db.RECURSO_PESADO, token, maximo=1):
            return m.OCUPADO
        try:
            corridas.append(args[0])
            return f"Listo: {args[0]}"
        finally:
            db.soltar_turno(conn, db.RECURSO_PESADO, token)

    return buscar


def _cmd(args):
    return {"comando": "/buscar", "args": args, "chat_id": "1", "usuario": "santi", "user_id": "7"}


def test_si_corre_el_diario_la_busqueda_queda_en_cola(conn, monkeypatch):
    corridas, cola, tg = [], [], FakeTG()
    monkeypatch.setattr(m, "_buscar", _falso_buscar(conn, corridas))
    monkeypatch.setattr(m, "load_streamers", lambda: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)
    cfg = load_settings()

    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:123", maximo=1)
    m._despachar(conn, tg, _cmd(["davoo"]), cfg, cola)
    assert corridas == [] and [x["args"] for x in cola] == [["davoo"]]
    assert "En cola" in tg.mensajes[-1] and "la corrida diaria" in tg.mensajes[-1]

    # mientras el diario siga andando, drenar no hace nada
    m._drenar_cola(conn, tg, cola, cfg)
    assert corridas == [] and len(cola) == 1

    # cuando termina, la búsqueda arranca sola
    db.soltar_turno(conn, db.RECURSO_PESADO, "diario:123")
    m._drenar_cola(conn, tg, cola, cfg)
    assert corridas == ["davoo"] and cola == []
    assert tg.mensajes[-1] == "Listo: davoo"


def test_el_mensaje_distingue_quien_esta_ocupando(conn, monkeypatch):
    corridas, cola, tg = [], [], FakeTG()
    monkeypatch.setattr(m, "_buscar", _falso_buscar(conn, corridas))
    monkeypatch.setattr(m, "load_streamers", lambda: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)

    db.tomar_turno(conn, db.RECURSO_PESADO, "buscar:spreen:999", maximo=1)
    m._despachar(conn, tg, _cmd(["davoo"]), load_settings(), cola)
    assert "la búsqueda anterior" in tg.mensajes[-1]


def test_la_cola_tiene_tope(conn, monkeypatch):
    """El tope es el mismo MAX_BUSQUEDAS de antes: ahora limita la cola, porque la ejecución ya la
    serializa el turno pesado."""
    corridas, cola, tg = [], [], FakeTG()
    monkeypatch.setattr(m, "_buscar", _falso_buscar(conn, corridas))
    monkeypatch.setattr(m, "load_streamers", lambda: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)
    cfg = load_settings()

    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1)
    for quien in ("a", "b", "c"):
        m._despachar(conn, tg, _cmd([quien]), cfg, cola)
    assert [x["args"][0] for x in cola] == ["a", "b"]
    assert f"{m.MAX_BUSQUEDAS} búsquedas en cola" in tg.mensajes[-1]

    # y salen en orden cuando se libera
    db.soltar_turno(conn, db.RECURSO_PESADO, "diario:1")
    m._drenar_cola(conn, tg, cola, cfg)
    assert corridas == ["a", "b"]


def test_sin_cola_la_busqueda_arranca_al_toque(conn, monkeypatch):
    corridas, cola, tg = [], [], FakeTG()
    monkeypatch.setattr(m, "_buscar", _falso_buscar(conn, corridas))
    monkeypatch.setattr(m, "load_streamers", lambda: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)

    m._despachar(conn, tg, _cmd(["davoo"]), load_settings(), cola)
    assert corridas == ["davoo"] and cola == []
    assert tg.mensajes == ["Listo: davoo"]


def test_los_comandos_livianos_no_pasan_por_la_cola(conn, monkeypatch):
    """/reclamo y /ayuda contestan aunque haya una corrida pesada: no procesan nada."""
    cola, tg = [], FakeTG()
    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1)
    monkeypatch.setattr(m, "_reclamo", lambda conn_, args: "reclamo anotado")

    m._despachar(conn, tg, {"comando": "/reclamo", "args": ["x"], "chat_id": "1",
                            "usuario": "", "user_id": "7"}, load_settings(), cola)
    m._despachar(conn, tg, {"comando": "/ayuda", "args": [], "chat_id": "1",
                            "usuario": "", "user_id": "7"}, load_settings(), cola)
    assert tg.mensajes[0] == "reclamo anotado"
    assert "/buscar" in tg.mensajes[1]
    assert cola == []


# ---- /ya ------------------------------------------------------------------------


def test_ya_usa_el_mismo_turno_que_buscar(conn, monkeypatch):
    """/ya corre la mezcla diaria, que es lo más pesado de todo: comparte turno y cola con /buscar."""
    cola, tg = [], FakeTG()
    corridas = []

    def falso_diario(args, settings, atender=True):
        assert atender is False, "desde /ya no se atiende Telegram: le robaría los updates al modo escucha"
        corridas.append("diario")
        return 0

    monkeypatch.setattr(m, "_diario", falso_diario)
    monkeypatch.setattr(m, "_cuantos_entregados", lambda conn_: 3 if corridas else 1)
    cfg = load_settings()
    cmd = {"comando": "/ya", "args": [], "chat_id": "1", "usuario": "santi", "user_id": "7"}

    # con el turno tomado, queda en cola
    db.tomar_turno(conn, db.RECURSO_PESADO, "buscar:spreen:1", maximo=1)
    m._despachar(conn, tg, cmd, cfg, cola)
    assert corridas == [] and len(cola) == 1 and cola[0]["comando"] == "/ya"
    assert "En cola" in tg.mensajes[-1]

    # liberado, arranca y avisa cuántos salieron
    db.soltar_turno(conn, db.RECURSO_PESADO, "buscar:spreen:1")
    m._drenar_cola(conn, tg, cola, cfg)
    assert corridas == ["diario"] and cola == []
    assert "2" in tg.mensajes[-1]  # 3 entregados menos 1 que ya había


def test_ya_toma_el_turno_y_lo_suelta(conn, monkeypatch):
    cola, tg = [], FakeTG()
    vistos = []
    monkeypatch.setattr(m, "_diario",
                        lambda a, s, atender=True: vistos.append(db.hay_trabajo_pesado(conn)) or 0)
    monkeypatch.setattr(m, "_cuantos_entregados", lambda conn_: 0)

    m._despachar(conn, tg, {"comando": "/ya", "args": [], "chat_id": "1", "usuario": "",
                            "user_id": "7"}, load_settings(), cola)
    assert vistos and vistos[0].startswith("diario:ya")   # lo tenía mientras corría
    assert db.hay_trabajo_pesado(conn) is None            # y lo soltó al terminar
    assert "no salió ninguno" in tg.mensajes[-1]


def test_ayuda_lista_todos_los_comandos_con_ejemplo():
    texto = m._ayuda()
    for uso, que, ejemplo in m.COMANDOS:
        assert uso in texto and que in texto
        assert f"<code>{ejemplo}</code>" in texto
    assert {c[0].split()[0] for c in m.COMANDOS} == {"/ya", "/buscar", "/reclamo", "/ayuda"}


# ---- votos 👍/👎 ----------------------------------------------------------------


def test_los_votos_se_guardan_con_el_puntaje(conn, monkeypatch, tmp_path):
    """El puntaje va junto al voto: es lo que después deja elegir el corte con datos en vez de
    con un número puesto a ojo."""
    import json

    from clips_bot import telegram as tgmod

    ready = tmp_path / "ready"
    ready.mkdir()
    (ready / "c1.json").write_text(json.dumps({"puntaje": 4, "relleno": True}), encoding="utf-8")
    monkeypatch.setattr("clips_bot.process.READY_DIR", ready)

    class TG(FakeTG):
        def __init__(self):
            super().__init__()
            self.editados, self.contestados = [], []

        def edit_reply_markup(self, chat_id, message_id, teclado):
            self.editados.append(teclado)

        def answer_callback(self, callback_id, texto=""):
            self.contestados.append(texto)

    tg = TG()
    up = [{"callback_query": {"id": "q", "data": "voto:-1:c1", "from": {"id": 7},
                              "message": {"message_id": 3, "chat": {"id": 9}}}}]
    assert m._atender_votos(conn, tg, up, {"7"}) == 1
    assert db.voto_de(conn, "c1", "7") == -1
    assert db.votos_por_puntaje(conn) == [(4, 0, 1)]
    assert tg.contestados == ["👎 anotado"]          # sin esto el botón queda girando
    botones = tg.editados[0]["inline_keyboard"][0]    # y queda marcado cuál votaste
    assert botones[1]["text"].endswith("✓") and not botones[0]["text"].endswith("✓")

    # el mismo voto de otra persona no pisa el tuyo
    up[0]["callback_query"]["from"]["id"] = 55
    assert m._atender_votos(conn, tg, up, {"7"}) == 0  # 55 no está autorizado
    assert db.voto_de(conn, "c1", "55") is None


def test_el_corte_sale_de_donde_ganan_los_pulgares_arriba(conn):
    """Regla que acordamos: el corte es el puntaje desde el cual hay más 👍 que 👎."""
    for i, (puntaje, voto) in enumerate(
            [(3, -1), (3, -1), (4, -1), (4, 1), (4, -1), (5, 1), (5, 1), (5, -1), (6, 1), (6, 1)]):
        db.votar(conn, f"c{i}", voto, "7", puntaje=puntaje)
    tabla = db.votos_por_puntaje(conn)
    assert tabla == [(3, 0, 2), (4, 1, 2), (5, 2, 1), (6, 2, 0)]
    corte = next(p for p, arriba, abajo in tabla if arriba > abajo)
    assert corte == 5
