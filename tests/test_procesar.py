import pytest

from clips_bot.config import Camara, Render, Subtitulos
from clips_bot.download import DescargaError, parse_clip_url
from clips_bot.layout import cara_estable, decidir_layout, recorte
from clips_bot.media import parse_silencio
from clips_bot.render import filtro
from clips_bot.subtitles import Palabra, _t_ass, _t_srt, armar_subtitulos

W, H = 1920, 1080
R, CAM = Render(), Camara()


# ---- URL ---------------------------------------------------------------------


def test_parse_clip_url():
    assert parse_clip_url("https://clips.twitch.tv/FunnySlug-abc123") == ("FunnySlug-abc123", None, "twitch")
    assert parse_clip_url("https://www.twitch.tv/Streamer/clip/Slug_1?filter=clips") == ("Slug_1", "streamer", "twitch")
    assert parse_clip_url("https://kick.com/DavooXeneize/clips/clip_01M35JEAF") == (
        "clip_01M35JEAF", "davooxeneize", "kick")
    with pytest.raises(DescargaError):
        parse_clip_url("https://www.youtube.com/watch?v=x")
    with pytest.raises(DescargaError):
        parse_clip_url("https://kick.com/davooxeneize")  # el canal, no un clip


# ---- silencio -------------------------------------------------------------------


def test_parse_silencio():
    log = """
[silencedetect @ 0x1] silence_start: 1.5
[silencedetect @ 0x1] silence_end: 4.0 | silence_duration: 2.5
[silencedetect @ 0x1] silence_start: 8
"""
    assert parse_silencio(log, 10.0) == pytest.approx(2.5 + 2.0)
    assert parse_silencio("", 10.0) == 0.0


# ---- layout ----------------------------------------------------------------------


def test_recorte_respeta_ratio_y_bordes():
    c = recorte(W, H, 9 / 16, cx=50, cy=540, alto=H)
    assert c.x == 0 and c.h == H and abs(c.w / c.h - 9 / 16) < 0.01
    c = recorte(W, H, 9 / 16, cx=1900, cy=540, alto=H)
    assert c.x + c.w <= W
    assert all(v % 2 == 0 for v in (c.x, c.y, c.w, c.h))


def test_sin_caras_es_sincam():
    lay = decidir_layout(W, H, [[] for _ in range(20)], CAM, R)
    assert lay.tipo == "sincam" and lay.camara is None
    assert lay.principal.h == pytest.approx(H / R.zoom_sin_camara, abs=2)


def test_cara_chica_estable_es_split():
    cara = (1650, 800, 90, 90)  # facecam abajo a la derecha
    frames = [[cara] for _ in range(15)] + [[] for _ in range(5)]
    lay = decidir_layout(W, H, frames, CAM, R)
    assert lay.tipo == "split"
    assert lay.presencia == pytest.approx(0.75)
    c = lay.camara
    assert c.x <= 1650 and c.x + c.w >= 1740 and c.y <= 800 and c.y + c.h >= 890
    assert c.x + c.w <= W and c.y + c.h <= H
    assert abs(c.w / c.h - R.ancho / (R.alto_camara - R.separador_px)) < 0.02


def test_juego_se_corre_si_pisa_la_camara():
    cara = (180, 750, 150, 150)  # facecam abajo a la izquierda, como elxokas
    lay = decidir_layout(W, H, [[cara] for _ in range(20)], CAM, R)
    cam, juego = lay.camara, lay.principal
    assert juego.x >= cam.x + cam.w  # ya no se superponen
    # y se aleja del overlay estimado (proporción de webcam), no del recorte de cámara: no depende del
    # alto del panel de salida ni del recorte de abajo
    otros = [Render(recorte_inferior_camara_px=0), Render(alto_camara=700), Render(alto_camara=900)]
    for r in otros:
        assert decidir_layout(W, H, [[cara] for _ in range(20)], CAM, r).principal.x == juego.x
    assert juego.x >= 180 + 75 + 1.5 * 150 * 2.3 / 2 - 2  # borde derecho del overlay estimado
    assert juego.x + juego.w <= W


def test_cara_grande_es_fullcam():
    frames = [[(800, 300, 320, 320)] for _ in range(20)]
    lay = decidir_layout(W, H, frames, CAM, R)
    assert lay.tipo == "fullcam"
    assert lay.principal.x <= 800 and lay.principal.x + lay.principal.w >= 1120


def test_caras_que_se_mueven_no_son_camara():
    # personajes del juego: una cara por frame, siempre en otro lugar
    frames = [[(100 + i * 80, 100 + (i % 5) * 150, 80, 80)] for i in range(20)]
    _, presencia = cara_estable(W, H, frames)
    assert presencia < CAM.min_presencia
    assert decidir_layout(W, H, frames, CAM, R).tipo == "sincam"


def test_filtro_ffmpeg():
    frames = [[(1650, 800, 90, 90)] for _ in range(20)]
    f = filtro(decidir_layout(W, H, frames, CAM, R), R, con_subs=True)
    assert "vstack=inputs=2" in f and "scale=1080:1152" in f  # juego 60 %
    assert "scale=1080:762:flags=lanczos,setsar=1,pad=1080:768:0:0:black" in f  # cámara 40 % con separador de 6 px
    assert 768 + 1152 == R.alto  # llenan los 1920 sin franjas
    assert f.endswith("ass=subs.ass[v]")
    f = filtro(decidir_layout(W, H, [], CAM, R), R, con_subs=False)
    assert "scale=1080:1920" in f and "ass=" not in f


# ---- subtítulos ------------------------------------------------------------------


def _palabras(texto: str, inicio=0.0, paso=0.3):
    return [Palabra(inicio + i * paso, inicio + i * paso + 0.25, w) for i, w in enumerate(texto.split())]


def test_subtitulos_max_lineas_y_largo():
    cfg = Subtitulos(max_chars_linea=24, max_lineas=2, max_duracion_s=10)
    texto = "che no puede ser lo que acaba de pasar recien en la partida de hoy mira mira"
    subs = armar_subtitulos(_palabras(texto), cfg)
    assert len(subs) > 1
    for s in subs:
        assert 1 <= len(s.lineas) <= 2
        assert all(len(l) <= 24 for l in s.lineas)
    assert " ".join(" ".join(s.lineas) for s in subs) == texto


def test_subtitulos_cortan_en_pausa_y_no_se_pisan():
    cfg = Subtitulos(max_duracion_s=10)
    palabras = _palabras("hola que tal") + _palabras("todo bien", inicio=5.0)
    subs = armar_subtitulos(palabras, cfg)
    assert [s.lineas for s in subs] == [("hola que tal",), ("todo bien",)]
    assert subs[0].fin <= subs[1].inicio


def test_subtitulos_respetan_duracion_maxima():
    cfg = Subtitulos(max_duracion_s=1.0, max_chars_linea=100)
    subs = armar_subtitulos(_palabras("a b c d e f g h"), cfg)
    assert all(s.fin - s.inicio <= 1.3 for s in subs)


def test_recortar_abajo_saca_el_pie_y_mantiene_proporcion():
    from clips_bot.layout import Caja, recortar_abajo

    ratio = 1080 / 694
    c = recortar_abajo(Caja(0, 700, 560, 360), 50, ratio)
    assert c.y == 700 and c.h == 310  # el borde de arriba no se mueve; el pie sube 50
    assert abs(c.w / c.h - ratio) < 0.02
    assert c.x + c.w / 2 == pytest.approx(280, abs=2)  # mismo centro horizontal
    assert recortar_abajo(Caja(0, 0, 100, 100), 0, 1.0) == Caja(0, 0, 100, 100)
    assert recortar_abajo(Caja(0, 0, 100, 100), 90, 1.0).h == 70  # nunca más del 30 %


def test_ass_centra_el_bloque_en_posicion_y(tmp_path):
    from clips_bot.subtitles import Subtitulo, escribir_ass

    escribir_ass([Subtitulo(0, 1, ("hola", "que tal"))], tmp_path / "s.ass", Subtitulos(posicion_y=0.80), R)
    texto = (tmp_path / "s.ass").read_text(encoding="utf-8")
    assert r"{\an5\pos(540,1536)}hola\Nque tal" in texto
    assert 1536 < 1920 * 0.85  # por encima del 15 % inferior que tapan los botones


def test_formatos_de_tiempo():
    assert _t_srt(3661.5) == "01:01:01,500"
    assert _t_ass(61.25) == "0:01:01.25"
