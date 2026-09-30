"""Formato de los clips de Rots (2026-09-30): en charla o IRL, zoom siguiendo la cara; título grande
arriba con el streamer chiquito encima."""

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from clips_bot import layout as lay, subtitles as sub
from clips_bot.config import load_settings
from clips_bot.media import find_bin
from clips_bot.render import renderizar

S = load_settings()


def test_la_persona_ocupa_al_menos_el_60_por_ciento_y_el_recorte_la_sigue():
    puntos = [(t * 2.0, (400 + 40 * t, 300, 120, 120)) for t in range(10)]
    l = lay.layout_sigue(1920, 1080, S.render, puntos, (400, 300, 120, 120), 1.0)
    assert l.tipo == "sigue"
    assert 3.3 * 120 / l.principal.h >= 0.6                      # la persona, sobre el alto del recorte
    assert abs(l.principal.w / l.principal.h - 1080 / 1920) < 0.01
    xs = [x for _, x, _ in l.camino]
    assert xs == sorted(xs) and xs[-1] > xs[0]                   # se mueve con la cara
    assert all(0 <= x <= 1920 - l.principal.w for x in xs)


def test_sin_cara_en_casi_ningun_cuadro_no_sigue():
    puntos = [(t, None) for t in range(10)] + [(11, (400, 300, 120, 120))]
    assert lay.layout_sigue(1920, 1080, S.render, puntos, (400, 300, 120, 120), 1.0) is None


def test_decide_sigue_solo_en_charla_con_una_persona_y_prendido():
    cam = replace(S.camara, seguir_cara=True)
    frames = [[(900, 300, 110, 110)] for _ in range(20)]
    puntos = [(t, (900, 300, 110, 110)) for t in range(12)]
    assert lay.decidir_layout(1920, 1080, frames, cam, S.render, charla=True, puntos=puntos).tipo == "sigue"
    assert lay.decidir_layout(1920, 1080, frames, S.camara, S.render, charla=True, puntos=puntos).tipo != "sigue"
    dos = [[(300, 300, 110, 110), (1400, 300, 110, 110)] for _ in range(20)]
    assert lay.decidir_layout(1920, 1080, dos, cam, S.render, charla=True, puntos=puntos).tipo == "fit_blur"
    assert lay.decidir_layout(1920, 1080, frames, cam, S.render, forzado="fit_blur", charla=True,
                              puntos=puntos).tipo == "fit_blur"


def test_el_titulo_entra_en_dos_lineas():
    tam, lineas = sub.lineas_titulo("Spreen se cae de la silla y el chat explota en risas otra vez")
    assert len(lineas) <= 2 and tam in (84, 70, 60)
    tam, lineas = sub.lineas_titulo("Corto")
    assert (tam, lineas) == (84, ["Corto"])


@pytest.mark.skipif(not find_bin("ffmpeg"), reason="sin ffmpeg")
def test_render_real_con_recorte_movil_y_titulo(tmp_path):
    video = tmp_path / "in.mp4"
    subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30", "-f", "lavfi", "-i", "sine=f=300",
                    "-t", "3", "-shortest", str(video)], check=True)
    puntos = [(0.0, (300, 200, 90, 90)), (1.5, (600, 220, 90, 90)), (3.0, (800, 200, 90, 90))]
    l = lay.layout_sigue(1280, 720, S.render, puntos, (300, 200, 90, 90), 1.0)
    sub.escribir_titulo_ass(tmp_path / "titulo.ass", "El chat no lo puede creer", "Spreen",
                            S.subtitulos, S.render)
    render = replace(S.render, x264_preset="ultrafast")
    renderizar(video, tmp_path / "out.mp4", l, render, None, tmp_path)
    info = subprocess.run([find_bin("ffprobe"), "-v", "error", "-select_streams", "v", "-show_entries",
                           "stream=width,height", "-of", "csv=p=0", str(tmp_path / "out.mp4")],
                          capture_output=True, text=True).stdout.strip()
    assert info == "1080,1920"
