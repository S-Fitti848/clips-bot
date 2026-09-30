"""Lo que pega en otros canales → el clip original (pego.py) y el comparador de audio."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from clips_bot import audio_huella as ah, db, pego
from clips_bot.candidates import Clip
from clips_bot.config import Pego, Streamer
from clips_bot.telegram import por_que

AHORA = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
SPREEN = Streamer("spreen", plataforma="kick", fuentes=("reciente",), grupo="argentinos", experimento=True)


def _short(id, titulo="Spreen se cae", canal="Otro", vistas=50000, dur=40):
    return pego.ShortAjeno(id, titulo, canal, vistas, dur, AHORA.isoformat())


def test_relevantes_nombran_al_streamer_pegaron_y_no_son_propios():
    shorts = [_short("a", vistas=90000), _short("b", titulo="Otro streamer", vistas=900000),
              _short("c", vistas=500), _short("d", canal="Rots"), _short("e", dur=120),
              _short("f", titulo="clip", canal="SpreenClips", vistas=60000), _short("g", vistas=20000)]
    elegidos = pego.relevantes(shorts, SPREEN, 10000, 2, ("Rots",))
    assert [x.id for x in elegidos] == ["a", "f"]            # los 2 más vistos que califican


def test_buscar_api_pide_shorts_por_vistas():
    class R:
        def __init__(self, d):
            self.status_code, self._d, self.text = 200, d, ""

        def json(self):
            return self._d

    pedidos = []

    class S:
        def get(self, url, params=None, timeout=None):
            pedidos.append((url, params))
            if url.endswith("/search"):
                return R({"items": [{"id": {"videoId": "v1"}}]})
            return R({"items": [{"id": "v1", "snippet": {"title": "Spreen", "channelTitle": "X",
                                                          "publishedAt": "2026-09-28T10:00:00Z"},
                                 "statistics": {"viewCount": "123456"},
                                 "contentDetails": {"duration": "PT45S"}}]})

    r = pego.buscar_api("spreen", AHORA - timedelta(days=7), "KEY", session=S())
    assert r[0].vistas == 123456 and r[0].duracion == 45.0 and r[0].publicado.startswith("2026-09-28")
    p = pedidos[0][1]
    assert p["order"] == "viewCount" and p["videoDuration"] == "short" and p["type"] == "video"


def _clip(id, vistas=100):
    return Clip(id=id, url=f"https://kick.com/spreen/clips/{id}", broadcaster_login="spreen",
                broadcaster_name="spreen", title="t", view_count=vistas, duration=30, language="",
                created_at=AHORA - timedelta(days=2), game_id="", game_name="", vod_offset=None,
                plataforma="kick")


def test_de_punta_a_punta_encuentra_guarda_y_devuelve_el_original(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(pego, "bajar_audio_short", lambda short, d: (d / "a.m4a", AHORA))
    monkeypatch.setattr(pego, "originales",
                        lambda s, cuando, dias, maximo, tw, k, ahora: [_clip("c1"), _clip("c2")])
    monkeypatch.setattr(pego, "encontrar",
                        lambda audio, clips, d, umbral, **k: (clips[1], 0.81) if "a" in str(audio) else (None, 0.2))
    buscar = lambda consulta, desde: [_short("s1", vistas=80000), _short("s2", vistas=30000)]
    recs = pego.buscar_pegados(conn, [SPREEN], Pego(), tmp_path, buscar=buscar, ahora=AHORA)
    assert recs[0].encontrados == 2 and recs[0].comparados == 2 and recs[0].clips == [2, 2]
    cands = pego.como_candidatos(conn, [SPREEN], vistos=set())
    assert [c.id for c in cands] == ["c2"]                          # dos Shorts, el mismo clip
    assert cands[0].pego_vistas == 80000 and cands[0].grupo == "argentinos"
    assert pego.como_candidatos(conn, [SPREEN], vistos={"c2"}) == []
    # el mismo Short no se vuelve a comparar
    llamadas = []
    monkeypatch.setattr(pego, "encontrar", lambda *a: llamadas.append(1))
    pego.buscar_pegados(conn, [SPREEN], Pego(), tmp_path, buscar=buscar, ahora=AHORA)
    assert llamadas == []


def test_el_tope_de_busquedas_por_dia(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    hechas = []
    buscar = lambda consulta, desde: hechas.append(consulta) or []
    otros = [Streamer(f"s{i}", plataforma="kick", experimento=True) for i in range(5)]
    pego.buscar_pegados(conn, otros, Pego(busquedas_por_dia=3), tmp_path, buscar=buscar, ahora=AHORA)
    assert hechas == ["s0", "s1", "s2"]
    pego.buscar_pegados(conn, otros, Pego(busquedas_por_dia=3), tmp_path, buscar=buscar, ahora=AHORA)
    assert len(hechas) == 3                                           # hoy ya no busca más


def test_la_linea_dice_que_pego():
    meta = {"vistas": 300, "mediana_vistas": 100, "clips_mismo_momento": 1, "puntaje": 7,
            "pego": {"vistas": 85000, "canal": "SpreenClips"}}
    assert por_que(meta).startswith("🔥 Pegó en otro canal: 85.000 vistas (SpreenClips) · 📊 300 vistas")


# ---- el comparador de audio, con señales sintéticas (sin ffmpeg) -------------------------------

def _voz(segundos, semilla):
    """Ruido con envolvente y timbre cambiante: se parece más a una voz que el ruido blanco."""
    rng = np.random.default_rng(semilla)
    n = int(segundos * ah.SR)
    env = np.repeat(rng.random(int(segundos * 8)) ** 2, ah.SR // 8)[:n]
    ruido = rng.standard_normal(n)
    tono = np.sin(2 * np.pi * np.cumsum(rng.uniform(100, 900, n)) / ah.SR)
    return ((ruido * 0.3 + tono) * env).astype(np.float32)


def test_un_pedazo_con_ruido_coincide_con_su_original_y_no_con_otro():
    original = _voz(40, 1)
    otro = _voz(40, 2)
    pedazo = original[5 * ah.SR:25 * ah.SR] + 0.2 * np.random.default_rng(3).standard_normal(20 * ah.SR).astype(np.float32)
    propio, desfase = ah.coincidencia(ah.huella(pedazo), ah.huella(original))
    ajeno, _ = ah.coincidencia(ah.huella(pedazo), ah.huella(otro))
    assert propio >= Pego().umbral > ajeno
    assert desfase == pytest.approx(5.0, abs=0.1)


def test_muy_corto_no_compara():
    assert ah.coincidencia(ah.huella(_voz(2, 1)), ah.huella(_voz(30, 1)))[0] == 0.0


# ---- v0.41.0: apodos, hashtags de relleno, más originales, avisar sin original -----------------

DAVO = Streamer("davooxeneize", plataforma="kick", grupo="argentinos", experimento=True,
                apodos=("Davo", "Davo Xeneize", "Davoo"))


def test_la_consulta_lleva_login_y_apodos():
    assert pego.consulta(DAVO) == 'davooxeneize|Davo|"Davo Xeneize"|Davoo'
    assert pego.nombres(Streamer("spreen", apodos=("Spreen", "SPREEN"))) == ["spreen"]


@pytest.mark.parametrize("titulo,canal,sirve", [
    ("DAVO es del MADRID?😭 #shorts", "santiamadorr", True),          # el apodo, en mayúsculas
    ("El MODO CARRERA de DAVO XENEIZE en el FIFA", "Luca Nivio", True),
    ("Lo consumieron los 1000 goles😂 #cristianoronaldo #lacobraaa #davooxeneize", "MordoTv", False),
    ("Boca eliminó a Racing", "Davo Clips", True),                    # el canal lo nombra
    ("Davoxeneize se enoja", "X", False),                             # otra palabra
    ("davidson juega", "X", False),
])
def test_nombra_solo_fuera_de_los_hashtags(titulo, canal, sirve):
    assert pego.nombra(DAVO, titulo, canal) is sirve


def test_el_recuento_dice_donde_se_cayo_cada_cosa():
    shorts = [_short("a", titulo="DAVO se enoja", vistas=90000),
              _short("b", titulo="goles #davooxeneize", vistas=700000),     # hashtag de relleno
              _short("c", titulo="DAVO y el mate", vistas=900),              # pocas vistas
              _short("d", titulo="DAVO", dur=90)]                            # largo
    rec = pego.Recuento("davooxeneize")
    ok = pego.filtrar(shorts, DAVO, 5000, (), rec)
    assert [x.id for x in ok] == ["a"]
    assert (rec.resultados, rec.cortos, rec.con_vistas, rec.nombran) == (4, 3, 2, 1)
    rec.comparados, rec.clips = 1, [60]
    t = rec.texto(5000)
    assert "YouTube dio 4 Shorts → 3 de hasta 61 s → 2 con 5.000+ vistas → 1 lo nombran" in t
    assert "comparé 1 contra 60 clips" in t and "encontré 0 originales" in t


def test_sin_original_se_avisa_con_link_y_vistas(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(pego, "bajar_audio_short", lambda short, d: (d / "a.m4a", AHORA))
    monkeypatch.setattr(pego, "originales",
                        lambda s, cuando, dias, maximo, tw, k, ahora: [_clip(f"c{i}") for i in range(40)])
    monkeypatch.setattr(pego, "encontrar", lambda audio, clips, d, umbral, **k: (None, 0.31))
    buscar = lambda consulta, desde: [_short("s1", titulo="DAVO se enoja", vistas=438428),
                                      _short("s2", titulo="goles #davooxeneize", vistas=700000)]
    recs = pego.buscar_pegados(conn, [DAVO], Pego(min_vistas=5000), tmp_path, buscar=buscar, ahora=AHORA)
    assert recs[0].nombran == 1 and [x.id for x in recs[0].sin_original] == ["s1"]
    # una fila vieja con la regla de antes (solo hashtag) no se avisa
    pego.guardar(conn, _short("viejo", titulo="goles #davooxeneize", vistas=600000), "davooxeneize",
                 None, 15)
    filas = pego.sin_original(conn, [DAVO], AHORA - timedelta(days=30), 5000)
    assert [f["url"] for f in filas] == ["https://www.youtube.com/shorts/s1"]
    assert filas[0]["comparados"] == 40
    t = pego.texto_sin_original(filas)
    assert "438.428 vistas" in t and "No encontré el original" in t and 'href="https://www.youtube.com/shorts/s1"' in t
    assert pego.texto_sin_original([]) == ""


def test_encontrar_usa_la_huella_guardada_y_corta_si_es_seguro(tmp_path, monkeypatch):
    base = _voz(40, 1)
    pedazo = base[5 * ah.SR:25 * ah.SR]
    monkeypatch.setattr(ah, "leer_audio", lambda ruta, max_s=180.0: pedazo)
    huellas = {"c0": ah.huella(_voz(40, 7)), "c1": ah.huella(base), "c2": ah.huella(_voz(40, 9))}
    pedidas = []

    def huella_de(c):
        pedidas.append(c.id)
        return huellas[c.id]

    clip, valor = pego.encontrar(tmp_path / "s.m4a", [_clip("c0"), _clip("c1"), _clip("c2")],
                                 tmp_path, 0.55, huella_de=huella_de)
    assert clip.id == "c1" and valor >= pego.SEGURO and pedidas == ["c0", "c1"]    # c2 ni se mira
    clip, valor = pego.encontrar(tmp_path / "s.m4a", [_clip("c0")], tmp_path, 0.55, huella_de=huella_de)
    assert clip is None and 0 <= valor < 0.55                        # la mejor igual se informa


def test_la_huella_de_un_clip_se_baja_una_sola_vez(tmp_path, monkeypatch):
    monkeypatch.setattr(ah, "leer_audio", lambda ruta, max_s=180.0: _voz(20, 4))
    bajadas = []

    def bajar(url, d):
        d.mkdir(parents=True, exist_ok=True)
        f = d / "c.mp4"
        f.write_bytes(b"x")
        bajadas.append(url)
        return f

    h1 = pego.huella_de_clip(_clip("c1"), tmp_path / "huellas", tmp_path / "tmp", bajar=bajar)
    h2 = pego.huella_de_clip(_clip("c1"), tmp_path / "huellas", tmp_path / "tmp", bajar=bajar)
    assert len(bajadas) == 1 and np.array_equal(h1, h2)
    assert not (tmp_path / "tmp" / "c.mp4").exists()                 # el mp4 no se guarda


def test_originales_de_los_dias_cercanos_a_la_publicacion():
    cuando = AHORA - timedelta(days=4)
    fechas = {"lejos": cuando - timedelta(days=5), "cerca": cuando - timedelta(days=1),
              "justo": cuando + timedelta(hours=6), "despues": cuando + timedelta(days=2)}

    class K:
        pedidos = []

        def get_clips(self, slug, n, orden, ventana):
            self.pedidos.append((n, orden, ventana))
            return [{"id": k, "created_at": f.isoformat(), "view_count": 10, "duration": 30,
                     "title": k, "category": {"name": "x"}} for k, f in fechas.items()]

    k = K()
    ids = [c.id for c in pego.originales(SPREEN, cuando, 3, 60, kick=k, ahora=AHORA)]
    assert sorted(ids) == ["cerca", "justo"] and k.pedidos == [(300, "view", "month")]


def test_los_apodos_de_telegram_mandan_sobre_el_yaml(tmp_path):
    from clips_bot import registro

    conn = db.connect(tmp_path / "t.db")
    assert registro.combinar([DAVO], conn)[0].apodos == ("Davo", "Davo Xeneize", "Davoo")
    assert registro.guardar_apodos(conn, "davooxeneize", " Davo ,Davo  Xeneize, davooxeneize, davo", "1") == (
        "Davo", "Davo Xeneize")
    assert registro.combinar([DAVO], conn)[0].apodos == ("Davo", "Davo Xeneize")
    registro.guardar_apodos(conn, "davooxeneize", "-", "1")
    assert registro.combinar([DAVO], conn)[0].apodos == ()


def test_el_boton_de_apodos_entra_en_64_bytes():
    from clips_bot.menu import LIMITE_CALLBACK, teclado_streamer

    t = teclado_streamer(99, 99, 9, ("Davo", "Davo Xeneize", "Davoo", "El Davo del pueblo"))
    botones = [b for f in t["inline_keyboard"] for b in f]
    ap = next(b for b in botones if b["text"].startswith("🏷 Apodos:"))
    assert len(ap["callback_data"].encode()) <= LIMITE_CALLBACK and len(ap["text"]) <= 40


def test_la_config_real_busca_mas_originales_y_davo_tiene_apodos():
    from clips_bot.config import load_settings, load_streamers

    cfg = load_settings().pego
    assert cfg.max_originales >= 60 and cfg.dias_antes == 3
    davo = next(s for s in load_streamers() if s.login == "davooxeneize")
    assert "Davo" in davo.apodos
