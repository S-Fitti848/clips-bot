"""Santi, 2026-11-16: (1) el banco es la excepción: cuántas veces por semana lo usa cada canal, en /costos,
con aviso si un canal pasa de 2; (2) la segunda de Latinoamérica tampoco queda vacía: sin ninguna de 8 (o 7),
una del banco, nunca una de menos de 8; (3) ningún video termina con un pico arriba de -3 dB."""

import subprocess
from datetime import date
from pathlib import Path

from clips_bot import __main__ as m
from clips_bot import banco, db, locales, media

LUNES = date(2026, 11, 16)


class _TG:
    def __init__(self):
        self.mensajes = []

    def send_message(self, chat, texto, *a, **k):
        self.mensajes.append((chat, texto))


def test_cada_uso_queda_anotado_y_se_cuenta_por_semana(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    banco.guardar(conn, "latam", [{"id": "a"}, {"id": "b"}])
    banco.sacar(conn, "latam", "a", hoy=date(2026, 11, 15))      # domingo: semana anterior
    banco.sacar(conn, "latam", "b", hoy=LUNES)
    banco.sacar(conn, "tecnologia", "t1", hoy=date(2026, 11, 18))
    banco.sacar(conn, "latam", None, hoy=LUNES)                   # sin banco: no cuenta
    assert banco.usos_semana(conn, date(2026, 11, 20)) == {"latam": 1, "tecnologia": 1, "asinacio": 0}
    assert banco.leer(conn, "latam") == []
    txt = banco.texto_usos(conn, date(2026, 11, 20))
    assert "Latinoamérica 1 (la anterior 1)" in txt and "16/11" in txt


def test_aviso_si_un_canal_pasa_de_2_una_vez_por_semana(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    tg = _TG()
    for i in range(2):
        banco.sacar(conn, "asinacio", f"x{i}", hoy=LUNES)
    m._banco_usos_tick(conn, tg, hoy=LUNES)
    assert tg.mensajes == []                                    # 2 todavía está bien
    banco.sacar(conn, "asinacio", "x2", hoy=LUNES)
    m._banco_usos_tick(conn, tg, hoy=LUNES)
    m._banco_usos_tick(conn, tg, hoy=LUNES)
    assert len(tg.mensajes) == 1
    chat, texto = tg.mensajes[0]
    assert chat == m.DUENO and texto.startswith("🔧 Claude Code:") and "Así Nació" in texto and "3 veces" in texto
    banco.sacar(conn, "asinacio", "y", hoy=date(2026, 11, 23))   # otra semana: arranca de cero
    m._banco_usos_tick(conn, tg, hoy=date(2026, 11, 23))
    assert len(tg.mensajes) == 1


def test_costos_muestra_el_banco(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "c.db")
    assert "Banco de reserva" in m._texto_costos(conn, 7)


def test_la_segunda_de_latam_tambien_tiene_banco(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    banco.guardar(conn, "latam", [{"id": "latam:X", "puntaje": 8.5}])
    hoy = LUNES
    db.set_valor(conn, f"{m.PH_LATAM}:{hoy.isoformat()}", '[{"texto": "t", "puntaje": 8.2}]')
    piso = m._piso_latam(conn, hoy)
    assert piso["piso_alternativo"] == locales.PISO_UNA_POR_DIA and piso["banco"]
    db.set_valor(conn, f"{m.PH_LATAM}:{hoy.isoformat()}", '[{"texto": "t", "puntaje": 6.5}]')
    piso = m._piso_latam(conn, hoy)
    assert piso["piso_alternativo"] is None and piso["banco"]      # ya salió una floja: banco o nada


def test_el_banco_nunca_da_una_de_menos_de_8():
    items = [{"id": "a", "puntaje": 7.9, "texto": "a", "anio": 1900, "paginas": ["A"]},
             {"id": "b", "puntaje": 8.4, "texto": "b", "anio": 1910, "paginas": ["B"]}]
    assert [c.texto for c, _, _ in locales.de_banco(items)] == ["b"]


def test_ningun_final_pasa_de_menos_3_db(tmp_path):
    ff = media.find_bin("ffmpeg")
    a = tmp_path / "a.wav"
    expr = "'0.18*sin(2*PI*220*t)+if(between(t,4.3,4.4),0.94*sin(2*PI*90*t),0)'"   # un golpe a -0,5 dB al final
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc={expr}:s=48000:d=5",
                    "-c:a", "pcm_s16le", str(a)], check=True)
    final = media.preparar_audio(a, 5.0, tmp_path / "final.wav")
    v = tmp_path / "v.mp4"
    subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=5:r=30",
                    "-i", str(final), "-c:v", "libx264", "-c:a", "aac", "-b:a", "160k", "-shortest", str(v)],
                   check=True)
    assert media.chequear_audio(Path(v)) == []
    assert media.pico_final_db(v, 5.0) <= media.PICO_MAX_DB - 0.5
    dv, da = media.duraciones_streams(v)
    assert abs(da - 5.0) < 0.03
