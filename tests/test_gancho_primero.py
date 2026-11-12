"""Gancho primero en todo Pequeña Historia y la medición (Santi, 2026-11-12). Sin red."""

import json
import wave
from datetime import date, datetime, timezone

import numpy as np
import pytest

from clips_bot import db, locales, medicion_ph
from clips_bot import efemerides as ef
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def test_los_cuatro_guiones_arrancan_con_el_gancho():
    for sistema in (ef.SISTEMA_GUION, ef.SISTEMA_GUION_HABLADO, locales.SISTEMA_GUION_LOCAL,
                    locales.SISTEMA_GUION_CORTO):
        assert "La PRIMERA frase es el GANCHO" in sistema
        assert 'arranca EXACTAMENTE con "Un día como hoy' not in sistema
    assert 'La SEGUNDA frase arranca EXACTAMENTE con "En <año>, en <lugar>,"' in locales.SISTEMA_GUION_LOCAL
    assert 'La SEGUNDA frase arranca EXACTAMENTE con "En <año>, en <lugar>,"' in locales.SISTEMA_GUION_CORTO


def test_el_lugar_va_en_la_segunda_frase_tambien_en_el_formato_largo():
    v = locales.validar_lugar("Nacozari")
    d = {"frases": [{"texto": "Un maquinista alejó un tren en llamas de su pueblo."},
                    {"texto": "En 1907, en Nacozari, Jesús García lo hizo."}],
         "titulo": "El héroe de Nacozari", "hashtags": ["#Nacozari", "#Mexico", "#Shorts"]}
    assert v(d) == []


def test_interruptores_prendidos():
    s = load_settings()
    assert s.efemerides.imagen_frase is True and s.historias_fb.formato_corto is True


def _wav(ruta, x, sr=48000):
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def test_la_voz_arranca_en_el_primer_cuadro(tmp_path):
    from clips_bot import narrar

    sr = 48000
    voz = 0.3 * np.sin(np.linspace(0, 3000, sr * 2))
    ruta = tmp_path / "v.wav"
    _wav(ruta, np.concatenate([np.zeros(int(sr * 0.4)), voz]))
    assert narrar.sacar_silencio_inicial(ruta) == pytest.approx(0.38, abs=0.02)
    assert narrar.duracion_wav(ruta) == pytest.approx(2.02, abs=0.02)
    assert narrar.sacar_silencio_inicial(ruta) == 0.0          # ya arranca con voz: no toca


def test_la_primera_foto_es_la_mas_impactante():
    g = ef.Guion(frases=["El gancho.", "En 1907, en el pueblo."], fotos=[], descartadas=[],
                 titulo="t", descripcion="d", hashtags=[])
    pool = [ef.Foto(archivo=f"F{i}.jpg", url="", ancho=1000, alto=800, licencia="CC0", autor="x",
                    epigrafe="e", pagina="", articulo="A", ruta="") for i in range(3)]

    class Elector:
        def json(self, *a, **k):
            return json.dumps({"frases": [{"se_ve": "x", "fotos": [1], "de_epoca": True, "seguro": True,
                                           "contradice": False},
                                          {"se_ve": "y", "fotos": [3, 2], "de_epoca": True, "seguro": True,
                                           "contradice": False}],
                               "descartadas": [], "impactantes": [3, 1], "tipos": []})

    import clips_bot.efemerides as m
    original = m._jpeg_chico
    m._jpeg_chico = lambda *a, **k: b""
    try:
        rankings, _ = ef.elegir_fotos(None, g, pool, [[0, 1, 2], [0, 1, 2]], elector=Elector(),
                                      avisar=lambda *_: None)
    finally:
        m._jpeg_chico = original
    assert rankings[0][0] == 2 and 0 in rankings[0]


def test_segundo_en_que_se_va_la_mayoria():
    curva = {"0": 1, "1": 1, "2": 1, "3": 0.97, "4": 0.86, "5": 0.76, "6": 0.60, "7": 0.51, "8": 0.48}
    assert medicion_ph.segundo_que_se_va(curva) == 8
    assert medicion_ph.segundo_que_se_va({"0": 1, "1": 0.9}) is None


def test_informe_contra_los_10_anteriores_y_por_tema():
    antes = {f"a{k}": {"publicado": f"2026-11-0{k}", "titulo": "x", "vistas": 1200, "se_queda_pct": 55.0,
                       "empujon": False, "suscriptos_pct": 0.1} for k in range(1, 10)}
    antes["viejo"] = {"publicado": "2026-10-01", "titulo": "y", "vistas": 99999, "se_queda_pct": 1.0}
    antes["a10"] = {"publicado": "2026-11-10", "titulo": "z", "vistas": 1200, "se_queda_pct": 55.0}
    antes["a11"] = {"publicado": "2026-11-11", "titulo": "z", "vistas": 1200, "se_queda_pct": 55.0}
    despues = {"t": {"publicado": "2026-11-14", "titulo": "Tec", "vistas": 3000, "se_queda_pct": 68.0,
                     "empujon": True, "tipo": "tecnologia"},
               "l": {"publicado": "2026-11-15", "titulo": "Lat", "vistas": 2000, "se_queda_pct": 64.0,
                     "empujon": False, "tipo": "latam"}}
    datos = {"fb": {"f1": {"publicado": "2026-11-08", "se_va_s": 4, "reproducciones": 200, "medio_s": 5.5},
                    "f2": {"publicado": "2026-11-13", "se_va_s": 9, "reproducciones": 600, "medio_s": 9.0}},
             "yt": {**antes, **despues}}
    texto = medicion_ph.informe(datos, hasta=date(2026, 11, 26))
    assert "(10 antes, 2 después)" in texto            # los 10 anteriores, no el viejo de octubre
    assert "1200 → 2500" in texto and "55 % → 66 %" in texto
    assert "segundo empujón: 0 % → 50 %" in texto
    assert "Tecnología (1): se queda 68 %" in texto and "Latinoamérica (1): se queda 64 %" in texto
    assert "segundo en que se va la mayoría: 4 s → 9 s" in texto
    assert "Tec" in medicion_ph.por_video(datos) and "con segundo empujón" in medicion_ph.por_video(datos)


def test_calibracion_con_los_de_studio():
    # Santi, 2026-11-12: Nacozari 63,9 (API 56,1), Beatles 61,6 (50,3), Capilla 28,4 (28,2).
    for api, studio in medicion_ph.CALIBRACION:
        assert abs(medicion_ph.calibrado(api) - studio) <= 3.5
    assert medicion_ph.calibrado(None) is None and 0 <= medicion_ph.calibrado(2) <= 100


def test_segundo_empujon():
    assert medicion_ph.hubo_empujon([1286, 140, 394, 26])        # Beatles: el día 2
    assert not medicion_ph.hubo_empujon([1203, 76, 64])          # Nacozari
    assert not medicion_ph.hubo_empujon([20, 1156, 7, 9])        # Android: publicado a la noche
    assert not medicion_ph.hubo_empujon([470, 711, 16, 1])       # vela solar: el paquete en 2 días
    assert not medicion_ph.hubo_empujon([])


def test_la_medicion_corre_una_vez_por_dia_y_el_informe_a_la_semana(conn):
    import clips_bot.__main__ as m

    class TG:
        def __init__(self):
            self.mensajes = []

        def send_message(self, chat, texto, **k):
            self.mensajes.append((chat, texto))

    tg, veces = TG(), []

    def medir(c, s):
        veces.append(1)
        return medicion_ph.guardar(c, {}, {})

    s = load_settings()
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 13, 8, 0, tzinfo=m.AR), medir=medir)
    assert veces == []                                    # antes de la hora
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 13, 9, 30, tzinfo=m.AR), medir=medir)
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 13, 11, 0, tzinfo=m.AR), medir=medir)
    assert veces == [1] and tg.mensajes == []             # una vez por día, sin informe todavía
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 19, 9, 5, tzinfo=m.AR), medir=medir)
    assert tg.mensajes == []                              # a las 2 semanas, no a la semana
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 26, 9, 5, tzinfo=m.AR), medir=medir)
    assert len(tg.mensajes) == 1 and tg.mensajes[0][0] == m.DUENO
    m._medicion_ph_tick(conn, tg, s, ahora=datetime(2026, 11, 27, 9, 5, tzinfo=m.AR), medir=medir)
    assert len(tg.mensajes) == 1                          # el informe va una sola vez


def test_la_efemeride_es_de_tecnologia_y_corta():
    s = load_settings()
    assert s.efemerides.tema == "tecnologia" and s.efemerides.corto is True
    assert "TECNOLOGÍA" in ef.TEMAS["tecnologia"] and "VACÍO" in ef.TEMAS["tecnologia"]
    assert "20 a 30 segundos" in ef.SISTEMA_GUION_CORTO and "La PRIMERA frase es el GANCHO" in ef.SISTEMA_GUION_CORTO


def test_sin_hechos_del_tema_no_sale_video(monkeypatch, tmp_path):
    class W:
        def eventos(self, lang, dia):
            return [ef.Evento("es", 1950, "Se firma un tratado.", ["Tratado"])] if lang == "es" else []

    class G:
        def json(self, *a, **k):
            return json.dumps({"elegidos": []})

    with pytest.raises(ef.SinTema):
        ef.proponer(W(), G(), date(2026, 11, 12), tmp_path, tema="tecnologia")


def test_otro_pais_primero():
    def c(pais, n):
        return locales.Candidato("acontecimientos", 1900 + n, f"hecho {n}", [f"A{n}"],
                                 clasif={"pais": pais})
    lista = [c("México", 1), c("Colombia", 2), c("México", 3), c("Perú", 4)]
    out = locales.otro_pais_primero(lista, {"México"})
    assert [x.anio for x in out] == [1902, 1904, 1901, 1903]     # México al final, si se puede
    assert locales.otro_pais_primero(lista, None) == lista


def test_aviso_de_voces_con_lo_encontre(conn, tmp_path):
    import sqlite3

    from clips_bot import voces

    le = tmp_path / "bot2.db"
    with sqlite3.connect(le) as c:
        c.execute("CREATE TABLE estado (clave TEXT PRIMARY KEY, valor TEXT)")
        dia, desde = voces.dia_cuota()
        c.execute("INSERT INTO estado VALUES (?, ?)", (f"tts_uso:{dia}", "5"))
    ahora = datetime.now(timezone.utc)
    for clave in ("principal", "principal", "principal", "segunda"):
        conn.execute("INSERT INTO gemini_uso (ts, dia, funcion, modelo, clave, entrada, salida, cache) "
                     "VALUES (?, ?, 'hablar', 'gemini-3.8-flash-tts', ?, 0, 0, 0)",
                     (ahora.isoformat(), ahora.date().isoformat(), clave))
    conn.commit()
    uso = voces.uso_hoy(conn, le)
    assert (uso["principal"], uso["segunda"], uso["lo_encontre"]) == (3, 1, 5)
    textos = voces.avisos(conn, uso, tope=10, aviso=8)
    assert len(textos) == 1 and "principal lleva 8" in textos[0] and "5 de Lo Encontré" in textos[0]
    assert voces.avisos(conn, uso, tope=10, aviso=8) == []        # una vez por día


def test_madrugada_en_orden(conn):
    import clips_bot.__main__ as m

    s = load_settings()
    assert (s.publicacion.hora_rots, s.efemerides.hora_propuesta, s.historias_fb.hora, s.pego.hora) ==         ("03:30", "04:00", "04:00", "01:30")
    lanzadas, efes = [], []
    tick = lambda h, mi, d=13: m._madrugada_tick(conn, None, s, ahora=datetime(2026, 11, d, h, mi, tzinfo=m.AR),
                                                 lanzar=lambda: lanzadas.append(1),
                                                 efemeride=lambda st: efes.append(1))
    tick(3, 20)
    assert lanzadas == []                                   # antes de las 03:30
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "pego:x", maximo=1, vencimiento_s=3600)
    tick(3, 31)
    assert lanzadas == []                                   # "pegó" todavía andando: espera
    db.soltar_turno(conn, db.RECURSO_PESADO, "pego:x", 3600)
    tick(3, 32)
    tick(3, 40)
    assert lanzadas == [1]                                  # una sola vez
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1, vencimiento_s=3600)
    tick(4, 10)
    assert efes == []                                       # Rots andando: la de tecnología espera
    db.soltar_turno(conn, db.RECURSO_PESADO, "diario:1", 3600)
    tick(4, 20)
    assert efes == []                                       # sin terminar Rots (y antes de las 05:30)
    db.set_valor(conn, m.DIARIO_FIN, "2026-11-13")
    tick(4, 40)
    tick(4, 50)
    assert efes == [1] and db.get_valor(conn, m.EFE_DIA) == "2026-11-13"
    assert db.hay_trabajo_pesado(conn) is None


def test_el_timer_de_respaldo_no_corre_dos_veces(conn, monkeypatch, tmp_path):
    import clips_bot.__main__ as m

    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    hoy = datetime.now(m.AR).date().isoformat()
    db.set_valor(conn, m.DIARIO_FIN, hoy)
    assert m._ya_corrio_hoy(conn) == "la corrida de hoy ya terminó"
    db.set_valor(conn, m.DIARIO_FIN, "2000-01-01")
    assert m._ya_corrio_hoy(conn) is None
    assert db.tomar_turno(conn, db.RECURSO_PESADO, "diario:9", maximo=1, vencimiento_s=3600)
    assert m._ya_corrio_hoy(conn) == "la corrida de hoy está andando"


def test_la_fecha_de_madrugada_es_la_del_dia():
    import clips_bot.__main__ as m

    # a las 04:00 AR (07:00 UTC) el día de la historia es el de Argentina
    ahora = datetime(2026, 11, 13, 4, 0, tzinfo=m.AR)
    assert ahora.date() == date(2026, 11, 13) and ahora.astimezone(timezone.utc).date() == date(2026, 11, 13)
