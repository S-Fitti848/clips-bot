import pytest

from clips_bot.config import Camara, Render, Subtitulos
from clips_bot.download import DescargaError, parse_clip_url
from clips_bot.layout import cara_estable, caras_estables, decidir_layout, recorte
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


def test_sin_caras_es_fit_blur():
    """Antes era un recorte central, y en los clips de juego sin cámara cortaba el chat y el HUD."""
    lay = decidir_layout(W, H, [[] for _ in range(20)], CAM, R)
    assert lay.tipo == "fit_blur" and lay.camara is None


def test_dos_caras_separadas_es_fit_blur():
    """Dos personas en una mesa: cualquier recorte 9:16 agarra la pared del medio y corta a las dos."""
    izq, der = (200, 400, 260, 260), (1450, 400, 260, 260)
    frames = [[izq, der] for _ in range(20)]
    caras = caras_estables(W, H, frames, CAM.min_presencia)
    assert len(caras) == 2
    assert decidir_layout(W, H, frames, CAM, R).tipo == "fit_blur"


def test_una_cara_grande_pero_al_costado_es_fit_blur():
    from clips_bot.layout import cortada_por, pegada_al_borde, recorte

    # cara grande contra el borde derecho del frame: el recorte no puede centrarse mas alla del
    # borde, asi que la cara queda al filo (es el caso de la persona sentada al costado de la mesa)
    cara = (1620, 300, 300, 300)
    lay = decidir_layout(W, H, [[cara] for _ in range(20)], CAM, R)
    assert lay.tipo == "fit_blur"
    # y una cara grande bien centrada sigue siendo fullcam
    centrada = (860, 300, 300, 300)
    lay = decidir_layout(W, H, [[centrada] for _ in range(20)], CAM, R)
    assert lay.tipo == "fullcam"
    assert not cortada_por(lay.principal, centrada) and not pegada_al_borde(lay.principal, centrada)


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


def test_caras_en_la_zona_del_juego_cancelan_el_split():
    """coker, 2026-09-23: es un podcast multicámara. No hay juego abajo, así que el split repetía
    la escena y cortaba al segundo. Se mide sobre las detecciones crudas porque al segundo Haar lo
    agarra de a ratos, nunca como cara estable."""
    cam_chica = (1650, 800, 90, 90)          # facecam del streamer, abajo a la derecha
    otro = (300, 400, 150, 150)              # la otra persona, en la zona que el split usaría de juego
    solo_facecam = [[cam_chica] for _ in range(20)]
    assert decidir_layout(W, H, solo_facecam, CAM, R).tipo == "split"

    # aparece en 8 de 20 frames (40 % > presencia_juego_max): no hay juego
    con_otro = [[cam_chica, otro] if i < 8 else [cam_chica] for i in range(20)]
    assert decidir_layout(W, H, con_otro, CAM, R).tipo == "fit_blur"

    # en 2 de 20 (10 %) sigue siendo split: un falso positivo suelto no cancela nada
    casi_nunca = [[cam_chica, otro] if i < 2 else [cam_chica] for i in range(20)]
    assert decidir_layout(W, H, casi_nunca, CAM, R).tipo == "split"


def test_las_caras_chicas_del_juego_no_cuentan():
    """Haar ve "caras" en los skins de Minecraft y en la gente de una transmisión. Medido: las
    personas de un podcast miden 6,7-8,8 % del ancho; los skins de Vegetta, 4,8-6,2 %."""
    from clips_bot.layout import caras_en_caja, Caja

    caja = Caja(0, 0, 1080, 1080)
    # los skins se mueven por la pantalla, como en el juego; el ancho es lo que los distingue
    skins = [[(100 + i * 40, 200 + (i % 4) * 90, int(0.05 * W), 96)] for i in range(20)]
    personas = [[(100 + i * 40, 200 + (i % 4) * 90, int(0.08 * W), 154)] for i in range(20)]
    assert caras_en_caja(W, H, skins, caja, min_ancho=CAM.cara_juego_min) == 0.0
    assert caras_en_caja(W, H, personas, caja, min_ancho=CAM.cara_juego_min) > 0.5

    cam_chica = (1650, 800, 90, 90)
    assert decidir_layout(W, H, [[cam_chica] + s for s in skins], CAM, R).tipo == "split"
    assert decidir_layout(W, H, [[cam_chica] + s for s in personas], CAM, R).tipo == "fit_blur"


def test_layout_forzado():
    """streamers.yaml: layout_forzado. Es para los canales cuyo formato la heurística no ve."""
    cam_chica = [[(1650, 800, 90, 90)] for _ in range(20)]
    assert decidir_layout(W, H, cam_chica, CAM, R).tipo == "split"
    assert decidir_layout(W, H, cam_chica, CAM, R, forzado="fit_blur").tipo == "fit_blur"
    assert decidir_layout(W, H, cam_chica, CAM, R, forzado="fullcam").tipo == "fullcam"
    # forzar split sin cara estable no se puede: cae a fit_blur, el único que no depende de nada
    assert decidir_layout(W, H, [[] for _ in range(20)], CAM, R, forzado="split").tipo == "fit_blur"
    # y un split forzado se respeta aunque haya otra persona en la zona del juego
    con_otro = [[(1650, 800, 90, 90), (300, 400, 150, 150)] for _ in range(20)]
    assert decidir_layout(W, H, con_otro, CAM, R).tipo == "fit_blur"
    assert decidir_layout(W, H, con_otro, CAM, R, forzado="split").tipo == "split"


def test_layout_forzado_invalido_no_carga(tmp_path):
    from clips_bot.config import ConfigError, load_streamers

    yaml = tmp_path / "s.yaml"
    yaml.write_text("streamers:\n  - login: x\n    layout_forzado: vertical\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_streamers(yaml)


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
    assert decidir_layout(W, H, frames, CAM, R).tipo == "fit_blur"


def test_filtro_ffmpeg():
    frames = [[(1650, 800, 90, 90)] for _ in range(20)]
    f = filtro(decidir_layout(W, H, frames, CAM, R), R, con_subs=True)
    assert "vstack=inputs=2" in f and "scale=1080:1152" in f  # juego 60 %
    assert "scale=1080:762:flags=lanczos,setsar=1,pad=1080:768:0:0:black" in f  # cámara 40 % con separador de 6 px
    assert 768 + 1152 == R.alto  # llenan los 1920 sin franjas
    assert f.endswith("ass=subs.ass[v]")
    f = filtro(decidir_layout(W, H, [], CAM, R), R, con_subs=False)
    assert "ass=" not in f


def test_filtro_fit_blur_no_recorta_el_video():
    from clips_bot.layout import layout_fit_blur

    f = filtro(layout_fit_blur(W, H, R), R, con_subs=True)
    frente = f.split("[fg]")[-1].split("[frente]")[0]  # la rama del frente, no la del fondo
    assert "crop" not in frente                       # el 16:9 entra entero
    assert f"scale={R.ancho}:-2" in frente            # 1080 de ancho, alto por proporción
    assert f"gblur=sigma={R.blur_sigma}" in f         # y el fondo es el mismo video, borroso
    assert "overlay=0:(H-h)/2" in f and f.endswith("ass=subs.ass[v]")


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
