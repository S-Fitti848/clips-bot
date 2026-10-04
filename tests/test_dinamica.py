"""Pequeña Historia más dinámica (2026-09-30): parallax, fotos más altas, año contando, mapa,
palabras clave y whoosh. Con ffmpeg real donde importa la duración."""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from clips_bot import efemerides as ef, graficos as gr, parallax as px
from clips_bot.config import load_settings
from clips_bot.media import find_bin
from clips_bot.subtitles import Palabra

sin_ffmpeg = pytest.mark.skipif(not find_bin("ffmpeg"), reason="sin ffmpeg")


def _dur(p: Path) -> float:
    return float(subprocess.run([find_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True).stdout)


def test_una_foto_horizontal_ocupa_al_menos_el_72_por_ciento_del_alto():
    s, w, h = px.caja(1920, 1080, 1080, 1920)
    assert h >= int(0.72 * 1920) and w == 1080              # se recortan los costados
    s, w, h = px.caja(1000, 1500, 1080, 1920)                  # vertical: ancho completo
    assert w == 1080 and h == 1620


def test_una_figura_con_agujeros_queda_llena():
    import cv2

    img = np.full((600, 800, 3), (200, 180, 150), np.uint8)
    cv2.rectangle(img, (300, 150), (500, 600), (30, 30, 30), -1)     # una "persona" oscura
    cv2.rectangle(img, (380, 300), (420, 330), (200, 180, 150), -1)  # la "boca" del color del fondo
    alfa, fondo = px.capas(img, (0.5, 0.3))
    if alfa.max() > 0:                                               # GrabCut la encontró
        assert alfa[315, 400] > 0.5                                  # la boca es parte de la figura


def test_el_anio_cuenta_hasta_el_anio_y_se_queda():
    ev = gr.anio_contando(1957)
    valores = [int(e.rsplit(",", 1)[1].split("}")[-1]) for e in ev]
    assert 1897 < valores[0] < 1957 and valores[-1] == 1957 and valores == sorted(valores)


def test_las_palabras_clave_aparecen_cuando_se_dicen():
    palabras = [Palabra(0.1, 0.3, "Un"), Palabra(3.0, 3.6, "Sputnik,"), Palabra(3.6, 3.8, "el"),
                Palabra(4.0, 4.9, "satélite"), Palabra(9.0, 9.5, "Sputnik")]
    ev = gr.claves_en_tiempo(palabras, ["sputnik", "satelite"])
    assert len(ev) == 1 and "0:00:03.00" in ev[0] and "SPUTNIK" in ev[0]   # la 2ª se pisaría: afuera
    assert ef.claves_del_guion(["Sputnik", "cohete espacial", "Marte", "año"],
                               ["Un día como hoy lanzaron el Sputnik.", "¡Fue en 1957 y hoy!"]) == ["Sputnik"]


@sin_ffmpeg
def test_el_whoosh_no_cambia_el_largo_del_audio(tmp_path):
    voz = tmp_path / "voz.wav"
    subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=220:d=8",
                    str(voz)], check=True)
    salida = gr.mezclar_whoosh(voz, [2.0, 5.5], gr.whoosh(tmp_path / "w.wav"), tmp_path / "vw.wav")
    assert _dur(salida) == pytest.approx(8.0, abs=0.05)


@sin_ffmpeg
def test_el_mapa_pone_el_punto_en_el_lugar(tmp_path):
    from PIL import Image

    base = tmp_path / "base.png"
    Image.new("RGB", (3600, 1800), (20, 40, 90)).save(base)
    m = gr.mapa(base, -34.6, -58.4, tmp_path / "mapa.png")                  # Buenos Aires
    im = Image.open(m)
    assert im.size == (572, 372)
    rojos = np.argwhere((np.asarray(im)[..., 0] > 200) & (np.asarray(im)[..., 1] < 80))
    cy, cx = rojos.mean(axis=0)
    assert abs(cx - 286) < 30 and abs(cy - 186) < 30                        # al centro del recuadro


@sin_ffmpeg
def test_render_con_parallax_y_mapa_dura_lo_que_tiene_que_durar(tmp_path):
    from PIL import Image, ImageDraw

    foto = tmp_path / "f.jpg"
    im = Image.new("RGB", (1600, 1000), (180, 170, 150))
    ImageDraw.Draw(im).ellipse((650, 250, 950, 1000), fill=(40, 40, 60))
    im.save(foto)
    voz = tmp_path / "voz.wav"
    subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=5",
                    str(voz)], check=True)
    (tmp_path / "subs.ass").write_text("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
                                       "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,20\n\n"
                                       "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
                                       "MarginV, Effect, Text\n", encoding="utf-8")
    render = load_settings().render
    mapa = tmp_path / "mapa.png"
    Image.new("RGB", (572, 372), (255, 255, 255)).save(mapa)
    salida = ef.armar_video([(foto, 2.5), (foto, 2.5)], voz, tmp_path, tmp_path / "out.mp4", render,
                            parallax=True, mapa=(mapa, 1.0, 3.0))
    assert _dur(salida) == pytest.approx(5.0, abs=0.1)


def test_una_cara_en_el_borde_queda_entera_con_margen_arriba():
    # foto horizontal 1920x1080, cara chica pegada a la izquierda y arriba
    cara = [(40, 120, 120, 120)]
    zona = px.zona_caras(cara, 1920, 1080)
    assert zona[1] < 120 - 100                                     # margen arriba de la cabeza
    s, vw, vh, x0, y0 = px.encuadre(1920, 1080, 1080, 1920, zona, (0.5, 0.5))
    assert x0 <= zona[0] * s and x0 + vw >= zona[2] * s            # entra a lo ancho
    assert y0 <= zona[1] * s and y0 + vh >= zona[3] * s            # y a lo alto


def test_dos_caras_lejos_achican_la_foto_antes_que_cortar_una():
    cs = [(100, 300, 150, 150), (1650, 300, 150, 150)]
    zona = px.zona_caras(cs, 1920, 1080)
    s_sin, vw_sin, _ = px.caja(1920, 1080, 1080, 1920)
    s, vw, vh, x0, _ = px.encuadre(1920, 1080, 1080, 1920, zona, (0.5, 0.5))
    assert s < s_sin and x0 <= zona[0] * s and x0 + vw >= zona[2] * s


@sin_ffmpeg
def test_el_video_se_recorta_hacia_las_caras_o_va_entero(tmp_path):
    from clips_bot import videos_libres as vl

    video = tmp_path / "v.mp4"
    subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=640x480:rate=25", "-t", "1", str(video)], check=True)
    for cx, entero in ((0.2, False), (0.5, True)):
        out = tmp_path / f"o{entero}.mp4"
        subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-i", str(video),
                        "-filter_complex", vl.filtro_video(1080, 1920, 20, 30, cx, entero),
                        "-map", "[v]", "-frames:v", "10", str(out)], check=True)
        assert out.exists()
    assert vl.encuadre_video(tmp_path / "no_existe.jpg") == (0.5, False)


@sin_ffmpeg
def test_la_foto_fija_no_se_mueve_y_dura_exacto(tmp_path):
    from PIL import Image, ImageDraw

    foto = tmp_path / "f.jpg"
    im = Image.new("RGB", (1600, 1000), (180, 170, 150))
    ImageDraw.Draw(im).ellipse((650, 250, 950, 1000), fill=(40, 40, 60))
    im.save(foto)
    voz = tmp_path / "voz.wav"
    subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=3",
                    str(voz)], check=True)
    (tmp_path / "subs.ass").write_text("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
                                       "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,20\n\n"
                                       "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
                                       "MarginV, Effect, Text\n", encoding="utf-8")
    ef.armar_video([(foto, 3.0)], voz, tmp_path, tmp_path / "out.mp4", load_settings().render, efecto="fija")
    assert _dur(tmp_path / "out.mp4") == pytest.approx(3.0, abs=0.1)
    cuadros = []
    for n in (0, 80):
        destino = tmp_path / f"c{n}.png"
        subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-i", str(tmp_path / "tramo_00.mp4"),
                        "-vf", f"select=eq(n\,{n})", "-frames:v", "1", str(destino)], check=True)
        cuadros.append(np.asarray(Image.open(destino).convert("L"), dtype=float))
    assert abs(cuadros[0] - cuadros[1]).mean() < 1.0            # quieta: el primero = el último


def test_de_fabrica_las_fotos_son_fijas():
    assert load_settings().efemerides.efecto_fotos == "fija"
