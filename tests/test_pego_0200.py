""""Pegó" fuera de la corrida diaria (2026-09-30: se comió los 90 min y no se entregó nada)."""

from datetime import datetime, timedelta, timezone

import clips_bot.__main__ as m
from clips_bot import db, pego
from clips_bot.config import Pego, Streamer, load_settings

AHORA = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)


def _streamers(n=3):
    return [Streamer(f"s{i}", plataforma="kick", experimento=True) for i in range(n)]


def test_el_tope_corta_y_la_proxima_vuelta_arranca_por_el_que_quedo(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    reloj = [0.0]
    buscados = []

    def buscar(consulta, desde):
        buscados.append(consulta)
        reloj[0] += 400          # cada streamer "tarda" 400 s
        return []

    tope = 15 * 60
    pego.buscar_pegados(conn, _streamers(), Pego(), tmp_path, buscar=buscar, ahora=AHORA,
                        hasta=tope, reloj=lambda: reloj[0])
    assert buscados == ["s0", "s1", "s2"][:3]            # 0, 400, 800 < 900: los tres arrancan
    reloj[0] = 0.0
    buscados.clear()
    pego.buscar_pegados(conn, _streamers(), Pego(), tmp_path, buscar=buscar,
                        ahora=AHORA + timedelta(days=1), hasta=500, reloj=lambda: reloj[0])
    assert buscados == ["s0", "s1"]                       # 0 y 400 < 500; a los 800 se corta
    assert db.get_valor(conn, pego.CLAVE_SIGUIENTE) == "s2"
    buscados.clear()
    reloj[0] = 0.0
    pego.buscar_pegados(conn, _streamers(), Pego(), tmp_path, buscar=buscar,
                        ahora=AHORA + timedelta(days=2), hasta=100, reloj=lambda: reloj[0])
    assert buscados == ["s2"]                             # arrancó por el que había quedado


def test_a_mitad_de_un_short_no_se_anota_y_se_retoma(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(pego, "bajar_audio_short", lambda short, d: (d / "a.m4a", AHORA))
    monkeypatch.setattr(pego, "originales", lambda *a: [])

    def encontrar(*a, **k):
        raise pego.SinTiempo()

    monkeypatch.setattr(pego, "encontrar", encontrar)
    corto = pego.ShortAjeno("x1", "s0 se cae", "Otro", 90000, 30, AHORA.isoformat())
    recs = pego.buscar_pegados(conn, _streamers(), Pego(), tmp_path,
                               buscar=lambda q, d: [corto], ahora=AHORA)
    assert not pego.ya_visto(conn, "x1") and "se terminó el tiempo" in recs[0].error
    assert db.get_valor(conn, pego.CLAVE_SIGUIENTE) == "s0" and len(recs) == 1


def test_el_tick_corre_una_vez_por_dia_desde_las_02(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(m, "_streamers", lambda c=None: _streamers(1))
    llamadas = []
    monkeypatch.setattr(m, "_pegados_para",
                        lambda s, sts, buscar_ahora, avisar=None, tope_s=None: llamadas.append(tope_s) or [])
    settings = load_settings()
    AR = m.AR
    m._pego_tick(conn, settings, ahora=datetime(2026, 10, 1, 1, 59, tzinfo=AR))
    assert llamadas == []
    m._pego_tick(conn, settings, ahora=datetime(2026, 10, 1, 2, 0, tzinfo=AR))
    m._pego_tick(conn, settings, ahora=datetime(2026, 10, 1, 3, 0, tzinfo=AR))
    assert llamadas == [settings.pego.tope_min * 60]      # una sola vez ese día, con el tope
    assert db.hay_trabajo_pesado(conn) is None            # soltó el turno
    m._pego_tick(conn, settings, ahora=datetime(2026, 10, 2, 2, 5, tzinfo=AR))
    assert len(llamadas) == 2


def test_la_corrida_diaria_no_busca_y_un_extra_que_falla_no_la_tumba(tmp_path, monkeypatch):
    import argparse
    import inspect

    fuente = inspect.getsource(m._diario)          # antes de reemplazarla
    assert "buscar_ahora=False" in fuente and "buscar_ahora=True" not in fuente
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    orden = []
    monkeypatch.setattr(m, "_diario", lambda args, settings: orden.append("clips") or 0)
    monkeypatch.setattr(m, "actualizar_metricas", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(m, "_resumen_pego", lambda s, simular: orden.append("pego"))
    monkeypatch.setattr(m, "efemeride_del_dia", lambda s, simular: orden.append("efemeride"))
    assert m.cmd_diario(argparse.Namespace(simular=True)) == 0
    assert orden == ["clips", "pego", "efemeride"]


def test_el_resumen_diario_lleva_titulo_vistas_y_link():
    t = pego.texto_sin_original([{"url": "https://www.youtube.com/shorts/abc", "streamer": "davooxeneize",
                                  "vistas": 438737, "canal": "santiamadorr", "titulo": "DAVO es del MADRID?",
                                  "coincidencia": 0.15, "comparados": 42}])
    assert t.startswith("🔥 <b>Pegó en otros canales</b>")
    assert "DAVO es del MADRID?" in t and "438.737 vistas" in t and "shorts/abc" in t


def test_message_is_not_modified_se_ignora_y_los_demas_errores_no():
    import pytest

    from clips_bot.telegram import TelegramClient, TelegramError

    class R:
        def __init__(self, texto):
            self.status_code, self.text = 400, texto

        def json(self):
            return {"ok": False, "description": self.text}

    class S:
        def __init__(self, texto):
            self.texto = texto

        def post(self, *a, **k):
            return R(self.texto)

    TelegramClient("T", session=S("Bad Request: message is not modified: specified new message "
                                   "content and reply markup are exactly the same")).edit_message("1", 2, "x")
    TelegramClient("T", session=S("Bad Request: message is not modified")).edit_reply_markup("1", 2, {})
    with pytest.raises(TelegramError):
        TelegramClient("T", session=S("Bad Request: message to edit not found")).edit_message("1", 2, "x")


def test_en_el_vod_se_prueban_solo_los_2_con_mas_vistas_y_se_avisa_donde(tmp_path, monkeypatch):
    from clips_bot import vod as vd

    conn = db.connect(tmp_path / "t.db")
    davo = Streamer("davooxeneize", plataforma="kick", experimento=True, apodos=("Davo",))
    for i, vistas in enumerate((900000, 500000, 300000)):
        pego.guardar(conn, pego.ShortAjeno(f"s{i}", f"DAVO {i}", "Otro", vistas, 30,
                                           AHORA.isoformat()), "davooxeneize", None, 40)
    probados = []
    monkeypatch.setattr(pego, "bajar_audio_short", lambda short, d: probados.append(short.id) or (d / "a", AHORA))
    monkeypatch.setattr(vd, "vods_kick", lambda k, slug, a, b: ["vod"])
    monkeypatch.setattr(vd, "buscar_en_vods", lambda *a, **k: (
        vd.Vod("1", "kick", "u", "https://kick.com/davooxeneize/videos/x", AHORA, 3600), 3725.0, 0.8)
        if probados[-1] == "s0" else None)
    n = pego.buscar_en_vod_del_dia(conn, [davo], Pego(), tmp_path, kick=object())
    assert probados == ["s0", "s1"] and n == 1
    t = pego.texto_sin_original(pego.sin_original(conn, [davo], AHORA - timedelta(days=2)))
    assert "salió del VOD" in t and "1:02:05" in t and "No encontré el original" in t


def test_el_vod_prendido_solo_para_el_que_mas_pego():
    cfg = load_settings().pego
    assert cfg.vod is True and cfg.vod_por_dia == 1


def test_el_vod_va_dentro_de_la_vuelta_de_las_02(tmp_path, monkeypatch):
    from dataclasses import replace

    from clips_bot import pego as pg

    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(m, "_streamers", lambda c=None: _streamers(1))
    orden = []
    monkeypatch.setattr(m, "_pegados_para", lambda *a, **k: orden.append("pego") or [])
    monkeypatch.setattr(pg, "buscar_en_vod_del_dia", lambda *a, **k: orden.append("vod") or 0)
    s = load_settings()
    m._pego_tick(conn, s, ahora=datetime(2026, 10, 5, 2, 1, tzinfo=m.AR))
    assert orden == ["pego", "vod"]
    orden.clear()
    m._pego_tick(conn, replace(s, pego=replace(s.pego, vod=False)), ahora=datetime(2026, 10, 6, 2, 1, tzinfo=m.AR))
    assert orden == ["pego"]
