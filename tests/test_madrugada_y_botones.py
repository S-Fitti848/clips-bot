"""Santi, 2026-11-26: (1) los videos del día (tecnología y Latinoamérica) se arman de madrugada y están listos a las
03:00, con su horario, esperando ✅; las pruebas no pisan ese rato; (2) los botones responden siempre, aunque haya un
render: el render va en otro hilo y, si un botón no se puede hacer en ese momento, "⏳ en cola, se hace cuando termine
el render"."""

import threading
from datetime import date, datetime

import clips_bot.__main__ as m
from clips_bot import banco, db, gemini, reserva_tec
from clips_bot.config import load_settings


def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def test_los_del_dia_arrancan_a_las_00_05():
    s = load_settings()
    assert s.efemerides.hora_propuesta == "00:05" and s.historias_fb.hora == "00:05"
    assert db.VENTANA_PRODUCCION == ("00:00", "03:00")
    assert reserva_tec.MADRUGADA_HASTA <= "02:30"


def test_un_boton_liviano_lo_contesta_quien_lo_atiende(tmp_path):
    c = _conn(tmp_path)
    assert m._respuesta_inmediata(c, {"data": "det:x"}, atencion_ocupada=False) is None
    assert "Un momento" in m._respuesta_inmediata(c, {"data": "efe:ok:abc"}, atencion_ocupada=False)


def test_con_un_render_andando_contesta_en_cola(tmp_path):
    c = _conn(tmp_path)
    assert db.tomar_turno(c, db.RECURSO_PESADO, "efemeride:madrugada", maximo=1, vencimiento_s=3600)
    assert m._respuesta_inmediata(c, {"data": "efe:ok:abc"}, atencion_ocupada=False) == m.EN_COLA_RENDER
    # un botón liviano con el render andando en el OTRO hilo: lo atiende al toque, sin el aviso
    assert m._respuesta_inmediata(c, {"data": "sub:pub:x"}, atencion_ocupada=False) is None
    # si el que atiende está ocupado (un render pedido a mano), todo botón recibe el aviso
    assert m._respuesta_inmediata(c, {"data": "sub:pub:x"}, atencion_ocupada=True) == m.EN_COLA_RENDER
    db.soltar_turno(c, db.RECURSO_PESADO, "efemeride:madrugada", 3600)
    assert m._respuesta_inmediata(c, {"data": "det:x"}, atencion_ocupada=True) == "⏳ en cola, ya lo hago"
    assert m.EN_COLA_RENDER == "⏳ en cola, se hace cuando termine el render"


def test_el_origen_de_cada_hilo_es_suyo():
    antes = gemini.ORIGEN
    visto = []

    def hilo():
        gemini.fijar_origen(gemini.A_MANO)
        with gemini.origen(gemini.PRODUCCION):
            visto.append(gemini.origen_actual())
        visto.append(gemini.origen_actual())

    t = threading.Thread(target=hilo)
    t.start()
    t.join()
    assert visto == [gemini.PRODUCCION, gemini.A_MANO]
    assert gemini.ORIGEN == antes and gemini.origen_actual() == antes      # el hilo principal no cambió


def test_las_pruebas_no_toman_el_turno_de_madrugada(tmp_path, monkeypatch):
    c = _conn(tmp_path)
    assert db.en_ventana_produccion(datetime(2026, 11, 27, 1, 0, tzinfo=m.AR))
    assert not db.en_ventana_produccion(datetime(2026, 11, 27, 3, 0, tzinfo=m.AR))
    assert not db.en_ventana_produccion(datetime(2026, 11, 26, 23, 59, tzinfo=m.AR))
    monkeypatch.setattr(db, "en_ventana_produccion", lambda ahora=None: True)
    assert not db.tomar_turno(c, db.RECURSO_PESADO, "prueba:fotos_primero", maximo=1, vencimiento_s=3600)
    assert db.tomar_turno(c, db.RECURSO_PESADO, "efemeride:madrugada", maximo=1, vencimiento_s=3600)


def test_al_salir_se_sueltan_los_turnos_propios(tmp_path):
    c = _conn(tmp_path)
    assert db.tomar_turno(c, db.RECURSO_PESADO, "efemeride:reserva", maximo=1, vencimiento_s=3600)
    db.soltar_propios(c)
    assert db.hay_trabajo_pesado(c) is None


def test_el_segundo_de_tecnologia_se_arma_de_madrugada(tmp_path):
    c = _conn(tmp_path)
    s = load_settings()
    banco.guardar(c, "tecnologia", [{"id": "tec:X", "puntaje": 9, "texto": "x", "anio": 1990, "paginas": ["X"]}])
    armados = []

    def tick(h, mi):
        m._reserva_tec_tick(c, None, s, ahora=datetime(2026, 11, 27, h, mi, tzinfo=m.AR),
                            armar=lambda *a: armados.append((h, mi)))

    tick(1, 0)
    assert armados == []                       # la del día todavía no terminó
    db.set_valor(c, m.EFE_DIA, "2026-11-27")
    tick(1, 10)
    assert armados == []                       # faltan las de Latinoamérica
    db.set_valor(c, m.FB_DIA, "2026-11-27")
    tick(1, 20)
    assert armados == [(1, 20)]                # falta el segundo y la reserva está vacía: se arma ya
    reserva_tec.guardar(c, [{"x": 1}])
    tick(1, 50)
    assert armados == [(1, 20)]                # ya hay uno listo para entregar
    reserva_tec.guardar(c, [])
    tick(2, 40)
    assert armados == [(1, 20)]                # pasadas las 02:30 no arranca otro (no termina antes de las 03:00)
    tick(4, 0)
    assert armados == [(1, 20)]                # de 03:00 a 06:30, nada (las pruebas)
    assert reserva_tec.faltan_hoy(c, date(2026, 11, 27), s.efemerides.por_dia) == 2


def test_la_escucha_contesta_mientras_renderiza(tmp_path, monkeypatch):
    """De punta a punta con un Telegram falso: el hilo de trabajo "renderiza" 3 s y el botón se contesta igual."""
    import time

    import pytest

    contestados, atendidos, vueltas = [], [], []
    trabajando = threading.Event()

    class TGFalso:
        def __init__(self, *a, **k):
            self.n = 0

        def get_updates(self, offset=None, timeout=0):
            self.n += 1
            if self.n == 1:
                trabajando.wait(5)          # que el render ya esté andando
                return [{"update_id": 10, "callback_query": {
                    "id": "cb1", "data": "efe:ok:abc", "from": {"id": 7},
                    "message": {"message_id": 1, "chat": {"id": 7, "type": "private"}}}}]
            if self.n > 3:
                raise KeyboardInterrupt
            time.sleep(0.2)
            return []

        def answer_callback(self, callback_id, texto="", alerta=False):
            contestados.append((time.monotonic(), texto))

    def vuelta(conn, tg, settings, cola, estado, reloj):
        if not vueltas:
            vueltas.append(1)
            assert db.tomar_turno(conn, db.RECURSO_PESADO, "efemeride:madrugada", maximo=1, vencimiento_s=3600)
            trabajando.set()
            time.sleep(3)                   # el render
            db.soltar_turno(conn, db.RECURSO_PESADO, "efemeride:madrugada", 3600)

    monkeypatch.setattr(gemini, "ORIGEN", gemini.ORIGEN)   # la escucha fija "a mano": que no quede para otros tests
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(m, "TelegramClient", TGFalso)
    monkeypatch.setattr(m, "_permitidos", lambda: {"7"})
    monkeypatch.setattr(m, "_vuelta_trabajo", vuelta)
    monkeypatch.setattr(m, "_atender_updates", lambda conn, tg, updates, *a: atendidos.append(updates))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    inicio = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        m.escuchar_telegram(load_settings(), timeout_poll=1)
    assert contestados and contestados[0][1] == m.EN_COLA_RENDER
    assert contestados[0][0] - inicio < 2.5          # antes de que termine el render de 3 s
    deadline = time.monotonic() + 5
    while not atendidos and time.monotonic() < deadline:
        time.sleep(0.1)
    assert atendidos                                 # y el botón pasó al hilo de atención
