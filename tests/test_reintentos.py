"""Gemini caído (503 "high demand", 2026-09-28): reintentos 30/60/120 s por modelo, el otro modelo,
y si igual falla, la efeméride y los clips que faltan se reintentan solos en una hora.

Sin red: la sesión HTTP, Telegram y la selección son fakes."""

import json
from dataclasses import replace
from datetime import datetime

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import load_settings
from clips_bot.gemini import GeminiClient, GeminiError
from clips_bot.seleccion import Opcion

OK = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}


class Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._p = status, payload or {}
        self.text = json.dumps(self._p)

    def json(self):
        return self._p


class Sesion:
    def __init__(self, *respuestas):
        self.respuestas, self.urls = list(respuestas), []

    def post(self, url, headers=None, json=None, timeout=None):
        self.urls.append(url)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _cliente(sesion, esperas, reloj=lambda: 0.0):
    return GeminiClient("K", "principal", session=sesion, sleep=esperas.append,
                        modelo_fallback="lite", reloj=reloj)


# ---- el cliente --------------------------------------------------------------------------------

def test_503_reintenta_con_30_60_120():
    esperas = []
    s = Sesion(Resp(503), Resp(503), Resp(503), Resp(200, OK))
    assert _cliente(s, esperas).json("s", "p", {}) == "{}"
    assert esperas == [30, 60, 120] and all("principal" in u for u in s.urls)


def test_despues_de_3_reintentos_prueba_el_otro_modelo():
    import requests

    esperas = []
    s = Sesion(Resp(503), requests.Timeout("read timed out"), Resp(503), Resp(503), Resp(200, OK))
    assert _cliente(s, esperas).json("s", "p", {}) == "{}"
    assert esperas == [30, 60, 120] and "lite" in s.urls[-1] and len(s.urls) == 5


def test_si_los_dos_fallan_es_pasajero_y_no_insiste_por_15_min():
    esperas, ahora = [], [0.0]
    s = Sesion(*[Resp(503)] * 8)
    c = _cliente(s, esperas, reloj=lambda: ahora[0])
    with pytest.raises(GeminiError) as e:
        c.json("s", "p", {})
    assert e.value.pasajero and len(s.urls) == 8 and esperas == [30, 60, 120] * 2
    with pytest.raises(GeminiError) as e:        # el clip siguiente: falla al toque
        c.json("s", "p", {})
    assert e.value.pasajero and len(s.urls) == 8
    ahora[0] = 15 * 60 + 1
    s.respuestas = [Resp(200, OK)]
    assert c.json("s", "p", {}) == "{}"


def test_sin_cuota_pasa_al_otro_modelo_sin_esperar():
    esperas = []
    s = Sesion(Resp(429, {"error": "Quota exceeded"}), Resp(200, OK))
    assert _cliente(s, esperas).json("s", "p", {}) == "{}"
    assert esperas == [] and "lite" in s.urls[1]


def test_sin_cuota_en_los_dos_no_es_pasajero():
    s = Sesion(Resp(429, {"error": "quota"}), Resp(429, {"error": "quota"}))
    with pytest.raises(GeminiError) as e:
        _cliente(s, []).json("s", "p", {})
    assert not e.value.pasajero


def test_un_400_no_reintenta_ni_cambia_de_modelo():
    s = Sesion(Resp(400, {"error": "bad"}))
    with pytest.raises(GeminiError) as e:
        _cliente(s, []).json("s", "p", {})
    assert not e.value.pasajero and len(s.urls) == 1


# ---- cuándo es "en una hora" --------------------------------------------------------------------

def test_en_un_rato_respeta_el_tope_del_dia():
    s = load_settings()
    assert m._en_un_rato(s, datetime(2026, 9, 28, 16, 42, tzinfo=m.AR)) == "17:42"
    assert m._en_un_rato(s, datetime(2026, 9, 28, 21, 0, tzinfo=m.AR)) == "22:00"
    assert m._en_un_rato(s, datetime(2026, 9, 28, 21, 1, tzinfo=m.AR)) is None
    assert m._en_un_rato(s, datetime(2026, 9, 28, 23, 30, tzinfo=m.AR)) is None


# ---- la efeméride --------------------------------------------------------------------------------

@pytest.fixture
def base(monkeypatch, tmp_path):
    """DB temporal con el grupo como destino, Telegram que anota y Gemini presente."""
    dbp = tmp_path / "t.db"
    monkeypatch.setattr(m, "DB_PATH", dbp)
    c = db.connect(dbp)
    db.ver_chat(c, "-100", "group", "Rots clips")
    db.marcar_destino(c, "-100", True)
    mensajes = []

    class TG:
        def __init__(self, token=""):
            pass

        def send_message(self, chat, texto, teclado=None):
            mensajes.append((chat, texto))

    monkeypatch.setattr(m, "TelegramClient", TG)
    monkeypatch.setattr(m, "env", lambda *a, **k: "x")
    monkeypatch.setattr(m, "_gemini", lambda s: object())
    return c, TG(), mensajes, load_settings()


def _hoy(h, mi=0):
    d = datetime.now(m.AR).date()
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=m.AR)


def test_efe_proponer_marca_el_503_como_pasajero(base, monkeypatch):
    from clips_bot import efemerides as ef

    c, tg, _, s = base
    monkeypatch.setattr(ef, "Wiki", lambda: object())

    def gemini_caido(*a, **k):
        raise GeminiError("Gemini (lite): 503 high demand", pasajero=True)

    monkeypatch.setattr(ef, "proponer", gemini_caido)
    error = m._efe_proponer(c, tg, ["-100"], _hoy(16).date(), s, object())
    assert isinstance(error, m.ErrorPasajero) and "503" in error

    def sin_fotos(*a, **k):
        raise ef.NarrarError("ninguno tuvo 4 fotos")

    monkeypatch.setattr(ef, "proponer", sin_fotos)
    assert not isinstance(m._efe_proponer(c, tg, ["-100"], _hoy(16).date(), s, object()),
                          m.ErrorPasajero)


def test_la_diaria_con_gemini_caido_no_avisa_y_reintenta_en_una_hora(base, monkeypatch):
    from clips_bot import musica

    c, _, mensajes, s = base
    monkeypatch.setattr(musica, "llenar", lambda *a, **k: 0)
    monkeypatch.setattr(m, "_efe_proponer", lambda *a: m.ErrorPasajero("No salió: 503"))
    monkeypatch.setattr(m, "_efe_horas_que_faltan", lambda horas, ahora: [])   # ya pasaron 7 y 10
    monkeypatch.setattr(m, "_en_un_rato", lambda s, ahora: "17:42")
    m.efemeride_del_dia(s)
    assert mensajes == []
    assert json.loads(db.get_valor(c, m.EFE_REINTENTO))["horas"] == ["17:42"]


def test_el_reintento_sigue_cada_hora_hasta_el_tope_y_recien_ahi_avisa(base, monkeypatch):
    c, tg, mensajes, s = base
    llamadas = []
    monkeypatch.setattr(m, "_efe_proponer",
                        lambda *a: llamadas.append(1) or m.ErrorPasajero("No salió: 503"))
    db.set_valor(c, m.EFE_REINTENTO, json.dumps({
        "fecha": _hoy(0).date().isoformat(), "chats": ["-100"], "horas": ["21:00"],
        "error": "x", "intentos": ["05:00", "07:00", "10:00"]}))
    m._efe_reintento_tick(c, tg, s, ahora=_hoy(21))
    assert mensajes == [] and json.loads(db.get_valor(c, m.EFE_REINTENTO))["horas"] == ["22:00"]
    m._efe_reintento_tick(c, tg, s, ahora=_hoy(22))       # 23:00 ya se pasa del tope
    assert len(llamadas) == 2 and db.get_valor(c, m.EFE_REINTENTO) is None
    chat, texto = mensajes[-1]
    assert chat == "-100" and "hoy no hay propuesta" in texto and "21:00, 22:00" in texto


def test_un_error_que_no_es_pasajero_no_suma_reintentos(base, monkeypatch):
    c, tg, mensajes, s = base
    monkeypatch.setattr(m, "_efe_proponer", lambda *a: "No salió: ninguno tuvo 4 fotos")
    db.set_valor(c, m.EFE_REINTENTO, json.dumps({
        "fecha": _hoy(0).date().isoformat(), "chats": ["-100"], "horas": ["10:00"],
        "error": "x", "intentos": ["05:00", "07:00"]}))
    m._efe_reintento_tick(c, tg, s, ahora=_hoy(10))
    assert db.get_valor(c, m.EFE_REINTENTO) is None and "4 fotos" in mensajes[-1][1]


# ---- los clips de la entrega diaria ----------------------------------------------------------

class GeminiCaido:
    def json(self, *a, **k):
        raise GeminiError("Gemini (lite): 503 high demand", pasajero=True)


def _meta(clip_id):
    return {"clip_id": clip_id, "streamer": "uno", "canal": "Uno", "categoria": "Just Chatting",
            "titulo_twitch": "t", "duracion_s": 30, "transcripcion": "hola",
            "creado": "2026-09-20T10:00:00+00:00", "textos": None}


@pytest.fixture
def seleccion(base, monkeypatch, tmp_path):
    c, _, _, s = base
    opciones = [Opcion(f"c{i}", "uno", 10, _hoy(5), meta=_meta(f"c{i}")) for i in range(3)]
    monkeypatch.setattr(m, "_opciones_pendientes", lambda ready, settings: list(opciones))
    monkeypatch.setattr(m, "_streamers", lambda *a: [])
    monkeypatch.setattr(m, "_en_un_rato", lambda s, ahora: "06:30")
    avisos = []
    monkeypatch.setattr(m, "_avisar_cero", lambda s, detalle, destinos=None: avisos.append(detalle))
    return c, s, avisos


def test_la_diaria_sin_textos_por_gemini_caido_agenda_en_vez_de_avisar(seleccion):
    c, s, avisos = seleccion
    assert m.ejecutar_seleccion(s, GeminiCaido(), enviar=True) == 1
    assert avisos == []
    d = json.loads(db.get_valor(c, m.CLIPS_REINTENTO))
    assert d["hora"] == "06:30" and d["faltan"] == db.cantidad_diaria(c)


def test_un_ya_con_gemini_caido_contesta_ahi_y_no_agenda(seleccion):
    c, s, avisos = seleccion
    m.ejecutar_seleccion(s, GeminiCaido(), enviar=True, destinos=["123"])
    assert avisos and db.get_valor(c, m.CLIPS_REINTENTO) is None


def test_simular_no_agenda(seleccion):
    c, s, avisos = seleccion
    m.ejecutar_seleccion(s, GeminiCaido(), enviar=False)
    assert db.get_valor(c, m.CLIPS_REINTENTO) is None


def test_el_reintento_de_clips_elige_solo_los_que_faltan_a_la_hora(base):
    c, _, _, s = base
    llamadas = []
    db.set_valor(c, m.CLIPS_REINTENTO, json.dumps({"fecha": _hoy(0).date().isoformat(),
                                                   "hora": "06:30", "faltan": 2}))
    fake = lambda settings, gemini, enviar, n: llamadas.append((enviar, n))
    m._clips_reintento_tick(c, s, ahora=_hoy(6, 29), seleccion=fake)
    assert llamadas == []
    db.tomar_turno(c, db.RECURSO_PESADO, "diario", maximo=1, vencimiento_s=3600)
    m._clips_reintento_tick(c, s, ahora=_hoy(6, 30), seleccion=fake)
    assert llamadas == []                                   # algo pesado andando: espera
    db.soltar_turno(c, db.RECURSO_PESADO, "diario", 3600)
    m._clips_reintento_tick(c, s, ahora=_hoy(6, 30), seleccion=fake)
    assert llamadas == [(True, 2)] and db.get_valor(c, m.CLIPS_REINTENTO) is None
    assert not db.hay_trabajo_pesado(c, 3600)               # soltó el turno


def test_el_reintento_de_clips_de_ayer_se_descarta(base):
    c, _, _, s = base
    db.set_valor(c, m.CLIPS_REINTENTO, json.dumps({"fecha": "2020-01-01", "hora": "06:30",
                                                   "faltan": 2}))
    m._clips_reintento_tick(c, s, ahora=_hoy(7), seleccion=lambda *a, **k: pytest.fail("no"))
    assert db.get_valor(c, m.CLIPS_REINTENTO) is None
