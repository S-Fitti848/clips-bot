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
        self.teclados = []

    def send_message(self, chat_id, texto, teclado=None):
        self.mensajes.append(texto)
        self.teclados.append(teclado)


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
    """Un /buscar completo (período y cantidad): así arranca sin preguntar con botones."""
    return {"comando": "/buscar", "args": args + ["7", "x3"], "chat_id": "1", "usuario": "santi",
            "user_id": "7"}


def test_si_corre_el_diario_la_busqueda_queda_en_cola(conn, monkeypatch):
    corridas, cola, tg = [], [], FakeTG()
    monkeypatch.setattr(m, "_buscar", _falso_buscar(conn, corridas))
    monkeypatch.setattr(m, "load_streamers", lambda: [])
    monkeypatch.setattr(m, "_gemini", lambda s: None)
    cfg = load_settings()

    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:123", maximo=1)
    m._despachar(conn, tg, _cmd(["davoo"]), cfg, cola)
    assert corridas == [] and [x["args"] for x in cola] == [["davoo", "7", "x3"]]
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
    assert "¿Qué necesitás?" in tg.mensajes[1]   # la ayuda arranca por secciones
    assert cola == []


# ---- /ya ------------------------------------------------------------------------


def test_ya_usa_el_mismo_turno_que_buscar(conn, monkeypatch):
    """/ya corre la mezcla diaria, que es lo más pesado de todo: comparte turno y cola con /buscar."""
    cola, tg = [], FakeTG()
    corridas = []

    def falso_diario(args, settings, atender=True, destinos=None, cuantos=None):
        assert atender is False, "desde /ya no se atiende Telegram: le robaría los updates al modo escucha"
        assert destinos == ["1"], "lo pidió por este chat: la entrega va acá, no a los destinos"
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
                        lambda a, s, atender=True, destinos=None, cuantos=None:
                        vistos.append(db.hay_trabajo_pesado(conn)) or 0)
    monkeypatch.setattr(m, "_cuantos_entregados", lambda conn_: 0)

    m._despachar(conn, tg, {"comando": "/ya", "args": [], "chat_id": "1", "usuario": "",
                            "user_id": "7"}, load_settings(), cola)
    assert vistos and vistos[0].startswith("diario:ya")   # lo tenía mientras corría
    assert db.hay_trabajo_pesado(conn) is None            # y lo soltó al terminar
    assert "no salió ninguno" in tg.mensajes[-1]


def test_ayuda_por_secciones_con_un_ejemplo_por_comando():
    """Con once comandos, la lista entera en un mensaje es una pared que nadie lee."""
    portada = m._ayuda()
    assert "¿Qué necesitás?" in portada
    assert "/buscar" not in portada              # la portada NO lista comandos

    vistos = []
    for i, (nombre, comandos) in enumerate(m.SECCIONES):
        texto = m._ayuda_seccion(i)
        assert nombre in texto
        for uso, que, ejemplo in comandos:
            assert uso in texto and que in texto
            assert f"<code>{ejemplo}</code>" in texto
            vistos.append(uso.split()[0])
    assert set(vistos) == {"/streamers", "/buscar", "/ya", "/agregar", "/quitar", "/cantidad",
                           "/reclamo", "/editar", "/narrar", "/destinos", "/aca", "/envivo", "/serie", "/efemeride", "/subidas",
                           "/permitir", "/sacar_acceso", "/gemini", "/metricas", "/demo", "/lang"}
    botones = [b for f in m.teclado_ayuda()["inline_keyboard"] for b in f]
    assert [b["callback_data"] for b in botones] == [f"ay:s:{i}" for i in range(len(m.SECCIONES))]


def test_la_ayuda_navega_editando_el_mismo_mensaje():
    class TG:
        def __init__(self):
            self.editados = []

        def answer_callback(self, cid, texto=""):
            pass

        def edit_message(self, chat, mid, texto, teclado=None):
            self.editados.append((texto, teclado))

    tg = TG()
    cb = {"data": "ay:s:1", "chat_id": "1", "message_id": 5, "callback_id": "q"}
    m._ayuda_callback(tg, cb)
    texto, teclado = tg.editados[-1]
    assert "Editar videos" in texto and "/narrar" in texto
    assert teclado["inline_keyboard"][0][0]["callback_data"] == "ay:r"

    m._ayuda_callback(tg, {**cb, "data": "ay:r"})
    assert "¿Qué necesitás?" in tg.editados[-1][0]
    m._ayuda_callback(tg, {**cb, "data": "ay:s:99"})   # sección inexistente: vuelve a la portada
    assert "¿Qué necesitás?" in tg.editados[-1][0]


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


# ---- la prueba del multi-POV ------------------------------------------------------


def _voto_multipov(conn, tg, clip_id, voto=-1):
    up = [{"callback_query": {"id": "q", "data": f"voto:{voto}:{clip_id}", "from": {"id": 7},
                              "message": {"message_id": 3, "chat": {"id": "9"}}}}]
    return m._atender_votos(conn, tg, up, {"7"})


class TGvotos(FakeTG):
    def edit_reply_markup(self, chat_id, message_id, teclado):
        pass

    def answer_callback(self, callback_id, texto=""):
        pass


def test_dos_pulgares_abajo_apagan_el_multipov(conn, monkeypatch, tmp_path):
    """El trato del 2026-09-24: dos 👎 a multi-POV en dos semanas y se apaga hasta revisarlo."""
    from datetime import datetime, timezone

    monkeypatch.setattr("clips_bot.process.READY_DIR", tmp_path)
    tg = TGvotos()
    db.arrancar_prueba_multipov(conn, datetime.now(timezone.utc).isoformat())
    assert db.multipov_apagado(conn) is None

    # un 👎 avisa pero no apaga
    _voto_multipov(conn, tg, "multipov_uno")
    assert db.multipov_apagado(conn) is None
    assert "1" in tg.mensajes[-1] and "apago" in tg.mensajes[-1]

    # un 👍 a otro no suma
    _voto_multipov(conn, tg, "multipov_dos", voto=1)
    assert db.multipov_apagado(conn) is None

    # y un 👎 a un clip normal tampoco
    _voto_multipov(conn, tg, "clip_normal")
    assert db.multipov_apagado(conn) is None

    # el segundo 👎 a un multi-POV sí
    _voto_multipov(conn, tg, "multipov_tres")
    assert db.multipov_apagado(conn)
    assert "apagado" in tg.mensajes[-1].lower()
    assert db.pulgares_abajo_multipov(conn) == ["multipov_uno", "multipov_tres"]


def test_cambiar_el_voto_no_cuenta_dos_veces(conn, monkeypatch, tmp_path):
    """Se cuenta un clip por multi-POV, no un voto: si votás 👎 dos veces al mismo, es uno."""
    from datetime import datetime, timezone

    monkeypatch.setattr("clips_bot.process.READY_DIR", tmp_path)
    tg = TGvotos()
    db.arrancar_prueba_multipov(conn, datetime.now(timezone.utc).isoformat())
    _voto_multipov(conn, tg, "multipov_uno")
    _voto_multipov(conn, tg, "multipov_uno")
    assert db.multipov_apagado(conn) is None
    assert db.pulgares_abajo_multipov(conn) == ["multipov_uno"]


def test_pasadas_las_dos_semanas_el_trato_se_vence(conn, monkeypatch, tmp_path):
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr("clips_bot.process.READY_DIR", tmp_path)
    tg = TGvotos()
    viejo = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
    db.arrancar_prueba_multipov(conn, viejo)
    _voto_multipov(conn, tg, "multipov_uno")
    _voto_multipov(conn, tg, "multipov_dos")
    assert db.multipov_apagado(conn) is None   # el trato era por dos semanas


# ---- que un comando roto no tumbe la escucha -------------------------------------


def test_un_comando_que_explota_avisa_y_no_tumba_nada(conn, monkeypatch):
    """El 2026-09-25 un /buscar sobre un streamer de Twitch se llevó puesto el servicio con un
    TypeError. Ahora avisa, queda en el log y el bot sigue escuchando."""
    cola, tg = [], FakeTG()

    def explota(*a, **k):
        raise TypeError("TwitchClient.__init__() missing 1 required positional argument")

    monkeypatch.setattr(m, "_pesado", explota)
    m._despachar(conn, tg, _cmd(["davoo"]), load_settings(), cola)
    assert "Falló" in tg.mensajes[-1] and "TypeError" in tg.mensajes[-1]
    assert cola == []          # y NO se encola: encolarlo lo haría fallar para siempre


def test_lo_que_falla_sale_de_la_cola(conn, monkeypatch):
    cola, tg = [], FakeTG()
    intentos = []

    def explota(conn_, tg_, chat, comando, args, settings, user_id=""):
        intentos.append(args[0])
        raise RuntimeError("boom")

    monkeypatch.setattr(m, "_pesado", explota)
    cola[:] = [{"chat_id": "1", "comando": "/buscar", "args": ["a"]},
               {"chat_id": "1", "comando": "/buscar", "args": ["b"]}]
    m._drenar_cola(conn, tg, cola, load_settings())
    assert intentos == ["a", "b"]   # probó los dos
    assert cola == []               # y ninguno quedó dando vueltas


def test_seguro_devuelve_lo_que_devuelve_la_funcion(conn):
    tg = FakeTG()
    assert m._seguro(tg, "1", "x", lambda: "resultado") == "resultado"
    assert m._seguro(tg, "1", "x", lambda: m.OCUPADO) is m.OCUPADO
    assert tg.mensajes == []


# ---- /streamers, /agregar, /quitar -------------------------------------------------


def test_los_botones_entran_en_los_64_bytes_de_telegram(conn):
    """Telegram corta el callback_data en 64 bytes. Por eso viajan índices y no logins: con 54
    streamers del Dedsafío, varios logins largos no entrarían."""
    from clips_bot.config import Streamer
    from clips_bot.menu import LIMITE_CALLBACK, teclado_grupos, teclado_streamer, teclado_streamers

    largos = [Streamer("x" * 40 + str(i), grupo="evento") for i in range(54)]
    teclados = [teclado_grupos({"evento": largos}),
                teclado_streamers(0, largos, 4, {largos[50].login: "reclamo"}),
                teclado_streamer(0, 53, 4)]
    for t in teclados:
        for fila in t["inline_keyboard"]:
            for boton in fila:
                assert len(boton["callback_data"].encode()) <= LIMITE_CALLBACK


def test_paginado_y_excluidos(conn):
    from clips_bot.config import Streamer
    from clips_bot.menu import POR_PAGINA, teclado_streamers

    lista = [Streamer(f"s{i:02d}", grupo="evento") for i in range(30)]
    primera = teclado_streamers(0, lista, 0, {})
    botones = [b for f in primera["inline_keyboard"] for b in f]
    assert sum(1 for b in botones if b["callback_data"].startswith("st:s:")) == POR_PAGINA
    assert "◀️" not in [b["text"] for b in botones]      # en la primera no hay "anterior"
    assert "▶️" in [b["text"] for b in botones]
    ultima = teclado_streamers(0, lista, 2, {})
    textos = [b["text"] for f in ultima["inline_keyboard"] for b in f]
    assert "◀️" in textos and "▶️" not in textos          # en la última no hay "siguiente"
    assert "⬅️ Volver" in textos

    # un excluido se ve pero su botón no lleva a ningún lado
    con_excl = teclado_streamers(0, lista, 0, {"s03": "reclamo de copyright"})
    excl = [b for f in con_excl["inline_keyboard"] for b in f if b["text"].startswith("🚫")]
    assert len(excl) == 1 and excl[0]["callback_data"].startswith("st:x:")


def test_agregar_y_quitar_van_a_la_db_y_no_al_yaml(conn, monkeypatch, tmp_path):
    """La lista efectiva es el YAML combinado con la DB: así una alta por Telegram no choca con
    el git de la Pi."""
    import json

    from clips_bot import registro
    from clips_bot.config import Streamer

    yaml = [Streamer("delyaml", grupo="argentinos", experimento=True),
            Streamer("otro", grupo="evento", experimento=True)]
    monkeypatch.setattr(m, "load_streamers", lambda: yaml)

    assert sorted(s.login for s in m._streamers(conn)) == ["delyaml", "otro"]

    # alta
    registro.guardar(conn, "nuevo", registro.ALTA, "7", plataforma="kick", grupo="argentinos")
    efectivos = {s.login: s for s in m._streamers(conn)}
    assert set(efectivos) == {"delyaml", "otro", "nuevo"}
    assert efectivos["nuevo"].plataforma == "kick"
    assert efectivos["nuevo"].experimento and efectivos["nuevo"].permitido

    # baja de uno que viene del YAML: no se toca el YAML, manda la DB
    assert "Saqué" in m._quitar(conn, ["delyaml"], "7")
    assert "delyaml" not in {s.login for s in m._streamers(conn)}
    assert [s.login for s in yaml] == ["delyaml", "otro"]   # el YAML quedó intacto

    # baja de uno que habías agregado vos: se borra la anotación
    assert "por Telegram" in m._quitar(conn, ["nuevo"], "7")
    assert registro.anotados(conn).get("nuevo") is None

    # quitar algo que no está
    assert "no está" in m._quitar(conn, ["fantasma"], "7")
    assert "Uso:" in m._quitar(conn, [], "7")


def test_aca_suma_este_chat_a_los_destinos(conn):
    """El id de un grupo no se puede poner en el .env antes de tiempo: recién se sabe estando
    adentro. /aca lo suma desde ahí, y se pueden tener varios destinos prendidos a la vez."""
    db.ver_chat(conn, "-1001234567890", "supergroup", "rots clips")
    db.ver_chat(conn, "8668060171", "private", "Santi", "8668060171")
    assert db.destinos(conn) == []

    r = m._aca(conn, "-1001234567890", [])
    assert "Sumado" in r and db.destinos(conn) == ["-1001234567890"]

    r = m._aca(conn, "8668060171", [])           # se suma sin sacar el anterior
    assert "rots clips" in r                      # y avisa a quién más le llega
    assert sorted(db.destinos(conn)) == ["-1001234567890", "8668060171"]

    m._aca(conn, "8668060171", ["no"])            # se saca de a uno
    assert db.destinos(conn) == ["-1001234567890"]


def test_destinos_avisa_de_quien_falta_el_start(conn, monkeypatch):
    """Telegram NO deja que un bot le escriba primero a nadie: si el permitido nunca mandó /start,
    no hay chat privado al que mandarle y el destino fallaría callado."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "7,55")
    db.ver_chat(conn, "7", "private", "Santi", "7")
    assert [f["user_id"] for f in m._faltan_start(conn)] == ["55"]
    db.ver_chat(conn, "55", "private", "Tommy", "55")
    assert m._faltan_start(conn) == []


def test_el_teclado_de_destinos_marca_lo_prendido(conn):
    from clips_bot.menu import teclado_destinos

    db.ver_chat(conn, "-100", "supergroup", "rots clips")
    db.ver_chat(conn, "7", "private", "Santi", "7")
    db.marcar_destino(conn, "7", True)
    t = teclado_destinos(db.chats_conocidos(conn), [{"user_id": "55", "nombre": "Tommy"}])
    textos = [b["text"] for f in t["inline_keyboard"] for b in f]
    assert any(x.startswith("✅ 👤 Santi") for x in textos)
    assert any(x.startswith("⬜ 👥 rots clips") for x in textos)
    falta = [b for f in t["inline_keyboard"] for b in f if "falta su /start" in b["text"]][0]
    assert falta["callback_data"] == "dst:x"      # no navega: no se le puede escribir


# ---- cantidad, ➕ más y 🔁 reemplazar ---------------------------------------------


def test_xN_se_distingue_de_los_dias():
    """`/buscar davoo gol 3` son 3 DÍAS; `/buscar davoo gol x3` son 3 CLIPS. Por eso la cantidad
    lleva x adelante: si fuera un número suelto, chocaría con los días."""
    from clips_bot.telegram import parse_buscar, sacar_cantidad

    resto, n = sacar_cantidad(["davoo", "gol", "3"], 6)
    assert n is None and parse_buscar(resto)[2] == 3          # 3 días

    resto, n = sacar_cantidad(["davoo", "gol", "x3"], 6)
    assert n == 3 and parse_buscar(resto)[2] == 7             # 3 clips, días por default

    resto, n = sacar_cantidad(["davoo", "x5", "gol", "3"], 6)
    assert n == 5 and parse_buscar(resto) == (("davoo",), ("gol",), 3)

    assert sacar_cantidad(["X2"], 6)[1] == 2                   # mayúscula también
    for malo in (["x0"], ["x7"], ["x99"]):
        with pytest.raises(ValueError):
            sacar_cantidad(malo, 6)


def test_cantidad_diaria(conn):
    assert db.cantidad_diaria(conn) == db.CANTIDAD_DEFAULT
    assert "3" in m._cantidad(conn, [])                        # sin argumento, informa
    assert "5" in m._cantidad(conn, ["5"]) and db.cantidad_diaria(conn) == 5
    assert "entre 1 y 6" in m._cantidad(conn, ["9"])           # no se pasa del tope
    assert db.cantidad_diaria(conn) == 5                       # y no cambió nada
    assert "número" in m._cantidad(conn, ["muchos"])


def test_el_boton_de_mas_usa_primero_lo_ya_procesado(conn, monkeypatch, tmp_path):
    """Lo ya procesado sale al instante y no gasta una llamada a Gemini: los textos ya están."""
    import json

    ready = tmp_path / "ready"
    ready.mkdir()
    for i, (puntaje, relleno) in enumerate([(7, False), (4, True), (9, False)]):
        mp4 = ready / f"c{i}.mp4"
        mp4.write_bytes(b"x")
        (ready / f"c{i}.json").write_text(json.dumps({
            "clip_id": f"c{i}", "streamer": "spreen", "puntaje": puntaje, "relleno": relleno,
            "salida": str(mp4), "textos": {"titulo": f"t{i}"}}), encoding="utf-8")
    # uno ya entregado no vuelve a salir
    (ready / "usado.mp4").write_bytes(b"x")
    (ready / "usado.json").write_text(json.dumps({
        "clip_id": "usado", "streamer": "spreen", "salida": str(ready / "usado.mp4"),
        "textos": {"titulo": "ya salió"}, "entregado": {"fecha": "hoy"}}), encoding="utf-8")
    monkeypatch.setattr("clips_bot.process.READY_DIR", ready)

    listos = m._listos_sin_mandar(conn, {"logins": ["spreen"]}, excluir=set())
    assert [x["clip_id"] for x in listos] == ["c2", "c0", "c1"]   # mejor puntaje primero, relleno al final

    # los de otro streamer no entran
    assert m._listos_sin_mandar(conn, {"logins": ["otro"]}, excluir=set()) == []
    # y lo ya dado por este pedido tampoco
    assert [x["clip_id"] for x in m._listos_sin_mandar(conn, {"logins": ["spreen"]}, {"c2"})] == \
        ["c0", "c1"]


def test_el_teclado_del_ultimo_clip_ofrece_mas(conn):
    from clips_bot.telegram import teclado_voto

    solo = [b["callback_data"] for f in teclado_voto("c1")["inline_keyboard"] for b in f]
    assert solo == ["voto:1:c1", "voto:-1:c1"]                 # sin pedido, no hay botones extra

    ultimo = teclado_voto("c1", pedido="ab12", ultimo=True, cuantos_mas=3)
    textos = [b["text"] for f in ultimo["inline_keyboard"] for b in f]
    assert "➕ 3 más" in textos

    votado = teclado_voto("c1", elegido=-1, pedido="ab12")
    datos = [b["callback_data"] for f in votado["inline_keyboard"] for b in f]
    assert "ped:r:ab12:c1" in datos                             # el 👎 ofrece reemplazo
    assert "ped:m:ab12" not in datos                            # pero no "más": no era el último


# ---- /editar y /narrar ------------------------------------------------------------


def test_los_videos_que_llegan_se_reconocen():
    from clips_bot.telegram import videos

    def msg(**extra):
        return {"message": {"chat": {"id": 9, "type": "private", "first_name": "Santi"},
                            "from": {"id": 7}, **extra}}

    ups = [
        msg(video={"file_id": "F1", "file_size": 5 << 20, "duration": 30}, caption="/editar"),
        msg(document={"file_id": "F2", "file_size": 1 << 20, "mime_type": "video/mp4"}),
        msg(animation={"file_id": "F3", "file_size": 1 << 20}),
        msg(document={"file_id": "F4", "mime_type": "application/pdf"}),   # no es video
        msg(text="hola"),                                                   # no es archivo
    ]
    v = videos(ups)
    assert [x["file_id"] for x in v] == ["F1", "F2", "F3"]
    assert v[0]["mb"] == 5.0 and v[0]["texto"] == "/editar"


def test_el_guion_avisa_cuando_no_entra_en_el_video():
    """Sobra o falta guion: hay que decirlo ANTES de sintetizar, no después."""
    from clips_bot.narrar import Guion, _medir, aviso_largo

    def guion(texto):
        p, seg = _medir(texto)
        return Guion(texto=texto, palabras=p, segundos_estimados=seg)

    corto = guion("Mirá esto.")
    largo = guion(" ".join(["palabra"] * 100))            # ~40 s hablados
    justo = guion(" ".join(["palabra"] * 25))             # ~10 s

    assert "sobran" in aviso_largo(largo, 10)
    assert "silencio" in aviso_largo(corto, 30)
    assert aviso_largo(justo, 10) == ""
    assert aviso_largo(justo, 0) == ""                     # sin duración no se opina


def test_el_guion_sensible_no_se_narra(conn, monkeypatch, tmp_path):
    """Poner voz de locutor arriba de un duelo es peor que escribirlo mal."""
    import json

    from clips_bot import narrar

    monkeypatch.setattr(m, "_gemini", lambda s: object())
    monkeypatch.setattr("clips_bot.media.frames_jpeg", lambda *a, **k: [b"x"])
    monkeypatch.setattr(m, "probe", lambda p: type("I", (), {"duracion": 20.0})())
    monkeypatch.setattr(narrar, "escribir",
                        lambda *a, **k: narrar.Guion(texto="algo", sensible=True))

    mp4 = tmp_path / "c.mp4"
    mp4.write_bytes(b"x")
    meta = {"clip_id": "c", "salida": str(mp4), "duracion_s": 20, "transcripcion": ""}
    r = m._narrar_guion(conn, FakeTG(), "1", "7", meta, load_settings())
    assert "sensible" in r and "no le pongo voz" in r.lower()


def test_todos_los_botones_llegan_a_la_escucha():
    """Los tests de cada menú llaman al handler directo; este pasa por el filtro de verdad.

    Hasta el 2026-09-27 `callbacks` solo dejaba pasar st: y add:, y los botones de /ayuda,
    /destinos, ➕ más y ✅ del guion se perdían sin que ningún test lo viera.
    """
    from clips_bot.telegram import callbacks, teclado_voto

    teclados = [m.teclado_ayuda(), teclado_voto("c1", pedido="ab", ultimo=True, cuantos_mas=3),
                teclado_voto("c1", -1, pedido="ab")]
    datos = [b["callback_data"] for t in teclados for fila in t["inline_keyboard"] for b in fila]
    datos += ["gui:ok:ab12cd", "gui:no:ab12cd", "dst:t:-100", "st:g", "add:ok:x", "pas:ok:ab"]
    for d in datos:
        if d.startswith("voto:"):
            continue
        u = [{"update_id": 1, "callback_query": {"id": "q", "data": d, "from": {"id": 7},
                                                 "message": {"message_id": 3,
                                                             "chat": {"id": 1, "type": "private"}}}}]
        assert len(callbacks(u)) == 1, d
