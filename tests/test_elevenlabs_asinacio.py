"""ElevenLabs en Así Nació (Santi, 2026-11-15): la voz de Tito, la biblioteca de efectos generada una sola vez y
reusada, Pequeña Historia con Gemini, y los créditos del mes en /costos con aviso al 75 %."""

import subprocess
import wave
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from clips_bot import __main__ as m
from clips_bot import db
from clips_bot import efemerides as ef
from clips_bot import elevenlabs
from clips_bot.animacion import sfx
from clips_bot.config import load_settings
from clips_bot.media import find_bin


class _Resp:
    def __init__(self, status, content=b"", js=None, headers=None):
        self.status_code, self.content, self.text, self._js = status, content, "error", js
        self.headers = headers or {}

    def json(self):
        return self._js


class _Sesion:
    def __init__(self, resp):
        self.resp, self.pedidos = resp, []

    def post(self, url, **k):
        self.pedidos.append((url, k))
        return self.resp

    def get(self, url, **k):
        self.pedidos.append((url, k))
        return self.resp


class _TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, *a, **k):
        self.mensajes.append(texto)


def _mp3(tmp_path, seg=0.6) -> bytes:
    p = tmp_path / "t.mp3"
    subprocess.run([find_bin("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"anullsrc=r=44100:cl=mono:d=0.2", "-f", "lavfi", "-i", f"sine=f=600:d={seg}",
                    "-filter_complex", "[0][1]concat=n=2:v=0:a=1", "-b:a", "128k", str(p)], check=True)
    return p.read_bytes()


# ---- la voz: solo Así Nació ----------------------------------------------------------------------

def test_pequena_historia_nunca_usa_elevenlabs(monkeypatch, tmp_path):
    """Sin la config de Así Nació, ElevenLabs no se llama aunque haya clave (Pequeña Historia sigue con Gemini)."""
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    monkeypatch.setattr(elevenlabs, "hablar", lambda *a, **k: pytest.fail("Pequeña Historia llamó a ElevenLabs"))
    s = load_settings()
    s = replace(s, efemerides=replace(s.efemerides, voz_motor="gemini"),
                animacion=replace(s.animacion, elevenlabs_voz="tito"))
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    _, _, motor = ef.voz_efemeride(["Hola."], s, tmp_path, tts=lambda k, t, **kw: (b"\x00\x01" * 24000, 24000))
    assert motor.startswith("gemini:")
    assert not hasattr(s.efemerides, "elevenlabs_voz")


def test_asinacio_usa_la_voz_de_tito(monkeypatch, tmp_path):
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    pedidos = []

    def hablar(texto, voz, modelo, **kw):
        pedidos.append((voz, modelo, kw))
        return b"\x00\x01" * 24000, 24000

    monkeypatch.setattr(elevenlabs, "hablar", hablar)
    s = load_settings()
    an = replace(s.animacion, elevenlabs_voz="tito", elevenlabs_nombre="Abuelo")
    _, _, motor = ef.voz_efemeride(["Hola."], s, tmp_path, elevenlabs_cfg=an)
    assert motor == "elevenlabs:Abuelo" and pedidos[0][:2] == ("tito", "eleven_v4")
    assert pedidos[0][2]["estabilidad"] == an.elevenlabs_estabilidad


def test_una_prueba_no_gasta_elevenlabs(monkeypatch, tmp_path):
    """La voz falsa de las pruebas va antes que ElevenLabs (las voces reales solo para lo que se publica)."""
    monkeypatch.delenv("CLIPS_VOZ_REAL", raising=False)
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    monkeypatch.setattr(elevenlabs, "hablar", lambda *a, **k: pytest.fail("una prueba gastó ElevenLabs"))
    s = load_settings()
    _, _, motor = ef.voz_efemeride(["Hola."], s, tmp_path,
                                   elevenlabs_cfg=replace(s.animacion, elevenlabs_voz="tito"))
    assert motor.startswith("falsa:")


def test_v4_no_manda_estilo_y_anota_los_creditos(monkeypatch):
    anotados = []
    monkeypatch.setattr(elevenlabs, "anotar", lambda *a, **k: anotados.append(a))
    s = _Sesion(_Resp(200, b"\x00\x01" * 24000, headers={"character-cost": "123"}))
    elevenlabs.hablar("Hola", "tito", "eleven_v4", api_key="k", sesion=s)
    ajustes = s.pedidos[0][1]["json"]["voice_settings"]
    assert set(ajustes) == {"stability", "similarity_boost"}
    assert anotados == [("voz", 123, "tito")]


# ---- la biblioteca de efectos ----------------------------------------------------------------------

def test_la_biblioteca_tiene_todo_el_catalogo():
    """Generada una vez y en git: la Pi no paga ninguno de estos de nuevo."""
    for nombre in sfx.CATALOGO:
        p = sfx.BIBLIOTECA / f"{nombre}.wav"
        assert p.exists(), nombre
        with wave.open(str(p)) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (48000, 1, 2), nombre


def test_lo_que_esta_en_la_biblioteca_no_se_genera(monkeypatch, tmp_path):
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    monkeypatch.setattr(elevenlabs, "efecto", lambda *a, **k: pytest.fail("pagó un efecto que ya estaba"))
    assert sfx.generar("golpe") == sfx.BIBLIOTECA / "golpe.wav"


def test_uno_nuevo_se_genera_una_sola_vez(monkeypatch, tmp_path):
    lib, nuevos = tmp_path / "lib", tmp_path / "nuevos"
    monkeypatch.setattr(sfx, "BIBLIOTECA", lib)
    monkeypatch.setattr(sfx, "NUEVOS", nuevos)
    monkeypatch.setattr(sfx, "GENERAR", True)
    monkeypatch.setattr(sfx, "_CACHE", {})
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    mp3 = _mp3(tmp_path)
    pedidos = []
    monkeypatch.setattr(elevenlabs, "efecto", lambda texto, dur, inf, nombre="": pedidos.append(nombre) or mp3)
    x = sfx.sonido("aplausos")
    assert pedidos == ["aplausos"] and len(x) > 0 and abs(float(np.max(np.abs(x))) - 1) < 1e-3
    # sin el silencio del principio: el sonido arranca en su cuadro
    assert float(np.max(np.abs(x[:480]))) > 0.05
    assert (nuevos / "aplausos.wav").exists() and "aplausos" in (nuevos / "biblioteca.json").read_text("utf-8")
    sfx._CACHE.clear()
    sfx.sonido("aplausos")
    assert pedidos == ["aplausos"]          # la segunda vez sale del archivo


def test_sin_elevenlabs_va_el_sintetizado_o_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(sfx, "BIBLIOTECA", tmp_path / "vacia")
    monkeypatch.setattr(sfx, "NUEVOS", tmp_path / "vacia2")
    monkeypatch.setattr(sfx, "_CACHE", {})
    assert len(sfx.sonido("golpe")) > 0               # el sintetizado
    assert len(sfx.sonido("aplausos")) == 0           # sin sintetizado: nada
    pista = sfx.pista([(0.1, "aplausos"), (0.2, "golpe"), (0.3, "inventado")], 1.0)
    assert len(pista) == 48001 and float(np.max(np.abs(pista))) > 0


def test_efecto_pide_el_modelo_de_efectos():
    s = _Sesion(_Resp(200, b"\xff" * 5000))
    elevenlabs.efecto("cash register", 1.2, 0.6, nombre="caja", api_key="k", sesion=s)
    url, k = s.pedidos[0]
    assert url.endswith("/sound-generation") and k["json"]["model_id"] == elevenlabs.MODELO_EFECTOS
    assert k["json"]["duration_seconds"] == 1.2 and k["json"]["prompt_influence"] == 0.6


def test_las_escenas_usan_los_efectos_nuevos():
    from clips_bot.animacion import escenas_lib as lib

    assert all(sfx.conocido(n) for n in ("caja_registradora", "aplausos", "cohete", "maquina"))
    src = open(lib.__file__, encoding="utf-8").read()
    assert '"caja_registradora"' in src and '"cohete"' in src and '"maquina"' in src


# ---- créditos: /costos y el aviso al 75 % ---------------------------------------------------------------

def _sub(usados, limite=40000):
    return {"usados": usados, "limite": limite, "plan": "starter",
            "reinicio": datetime(2026, 12, 15, 22, 30, tzinfo=timezone.utc)}


def test_aviso_al_75_y_al_100_una_vez(monkeypatch, tmp_path):
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    conn = db.connect(tmp_path / "c.db")
    tg, s = _TG(), load_settings()
    m._elevenlabs_tick(conn, tg, s, sub=_sub(20000))
    assert tg.mensajes == []
    m._elevenlabs_tick(conn, tg, s, sub=_sub(30500))
    m._elevenlabs_tick(conn, tg, s, sub=_sub(31000))
    assert len(tg.mensajes) == 1 and "76%" in tg.mensajes[0] and "Claude Code" in tg.mensajes[0]
    m._elevenlabs_tick(conn, tg, s, sub=_sub(40000))
    assert len(tg.mensajes) == 2 and "Gemini" in tg.mensajes[1]


def test_la_cuenta_se_mira_cada_media_hora(monkeypatch, tmp_path):
    monkeypatch.setattr(elevenlabs, "clave", lambda: "k")
    llamadas = []
    monkeypatch.setattr(elevenlabs, "suscripcion", lambda: llamadas.append(1) or _sub(100))
    conn = db.connect(tmp_path / "c.db")
    t = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    m._elevenlabs_tick(conn, _TG(), load_settings(), ahora=t)
    m._elevenlabs_tick(conn, _TG(), load_settings(), ahora=t + timedelta(minutes=10))
    m._elevenlabs_tick(conn, _TG(), load_settings(), ahora=t + timedelta(minutes=31))
    assert len(llamadas) == 2


def test_costos_muestra_los_creditos_del_mes(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    db.anotar_elevenlabs(conn, "voz", 520, "tito", origen="produccion")
    db.anotar_elevenlabs(conn, "voz", 480, "tito", origen="produccion")
    db.anotar_elevenlabs(conn, "efecto", 25, "aplausos", origen="a_mano")
    mes = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m")
    txt = elevenlabs.texto_creditos(conn, mes, _sub(1025))
    assert "1.025 de 40.000 créditos (3%)" in txt.replace(" %", "%")
    assert "voces (produccion): 2 pedidos, 1.000 créditos" in txt and "efectos (a_mano): 1 pedidos, 25" in txt


# ---- duración: primero la velocidad, después reescribir ------------------------------------------------

def test_ajuste_de_velocidad_antes_de_reescribir():
    from clips_bot.animacion import marcas

    assert marcas.ajuste_velocidad(27.0) is None                      # adentro (25-30 s): nada
    assert marcas.ajuste_velocidad(31.0) == pytest.approx(31.0 / 29.5)  # 5 % más rápido: alcanza
    assert marcas.ajuste_velocidad(24.0) == pytest.approx(24.0 / 25.5)  # 6 % más lento: alcanza
    assert marcas.ajuste_velocidad(33.5) is None                      # haría falta 12 %: se reescribe
    assert marcas.ajuste_velocidad(22.5) is None
