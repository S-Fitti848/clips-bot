"""Animación vectorial (clips_bot/animacion): SVG válido, línea de tiempo y un render chico."""
import json
import math
import subprocess
import wave
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from clips_bot.animacion import audio as au
from clips_bot.animacion import escenas as esc
from clips_bot.animacion import personajes as per
from clips_bot.animacion import render as rd
from clips_bot.animacion import texto as tx
from clips_bot.animacion.easing import CURVAS
from clips_bot.animacion.svg import documento
from clips_bot.animacion.timeline import ErrorGuion, Pista, Video


def _es_svg(cuerpo: str) -> ET.Element:
    raiz = ET.fromstring(documento(cuerpo))
    assert raiz.tag.endswith("svg")
    return raiz


# ---- dibujo -----------------------------------------------------------------------


@pytest.mark.parametrize("nombre", list(per.ELENCO))
@pytest.mark.parametrize("gesto", list(per.GESTOS))
def test_personajes_arman_svg_valido(nombre, gesto):
    e = per.estado_de_gesto(gesto)
    e.parpadeo, e.boca, e.apertura = 0.5, "a", 0.8
    _es_svg(per.personaje(nombre).svg(e))


def test_la_boca_y_los_ojos_cambian_el_dibujo():
    p = per.personaje("narrador")
    cerrada = p.svg(per.Estado())
    assert p.svg(per.Estado(boca="a", apertura=0.9)) != cerrada
    assert p.svg(per.Estado(parpadeo=1.0)) != cerrada
    assert p.svg(per.Estado(respiracion=1.0)) != cerrada


def test_variacion_parametrica():
    a = per.personaje("pibe").svg()
    b = per.personaje("pibe", ropa="#00aa88", sombrero="galera").svg()
    assert "#00aa88" in b and a != b


@pytest.mark.parametrize("tipo", sorted(esc.FONDOS))
def test_fondos(tipo):
    _es_svg(esc.fondo(tipo))
    assert esc.fondo(tipo) == esc.fondo(tipo)   # deterministas: el caché depende de esto


@pytest.mark.parametrize("nombre", sorted(esc.PROPS))
def test_props(nombre):
    _es_svg(esc.prop(nombre))


def test_texto_gancho_y_subtitulos():
    _es_svg(tx.gancho("¿Por qué pasa esto?", 0.4, "palabras"))
    _es_svg(tx.gancho("¿Por qué pasa esto?", 0.2, "rebote"))
    assert tx.gancho("Hola mundo", 0.0, "palabras") == ""        # todavía no entró nada
    palabras = tx.palabras_de_texto("Esto es una prueba de subtítulos largos, bien.", 1.0, 4.0)
    assert palabras[0].inicio == 1.0 and abs(palabras[-1].fin - 4.0) < 1e-9
    grupos = tx.agrupar(palabras)
    assert all(1 <= len(g) <= 3 for g in grupos)
    assert sum(len(g) for g in grupos) == len(palabras)
    s = tx.subtitulo(grupos, palabras[1].inicio + 0.01)
    _es_svg(s)
    assert "#ffd23f" in s.lower()          # la palabra activa va en color
    assert tx.subtitulo(grupos, 10.0) == ""


# ---- línea de tiempo --------------------------------------------------------------


def test_easing_extremos():
    for nombre, f in CURVAS.items():
        assert abs(f(0.0)) < 1e-9, nombre
        assert abs(f(1.0) - 1) < 1e-9, nombre


def test_pista_interpola():
    p = Pista([{"t": 0, "x": 0}, {"t": 2, "x": 100, "easing": "lineal"},
               {"t": 4, "x": 0, "easing": "suave"}])
    assert p.valor("x", -1, 5) == 0          # antes del primero: el primero
    assert p.valor("x", 1, 5) == pytest.approx(50)
    assert p.valor("x", 3, 5) == pytest.approx(50)   # suave: la mitad en la mitad
    assert p.valor("x", 2.5, 5) > 50 + 0      # suave arranca lento (todavía arriba de 50)
    assert p.valor("x", 9, 5) == 0
    assert p.valor("y", 1, 7) == 7           # sin keyframes: el valor base


def _guion(**extra):
    d = {"escenas": [
        {"duracion": 1.0, "fondo": "cielo", "elementos": [
            {"tipo": "personaje", "nombre": "narrador", "x": 540, "y": 1700, "habla": True,
             "gestos": [{"t": 0, "gesto": "senalar"}]},
            {"tipo": "gancho", "texto": "Hola"}]},
        {"duracion": 1.0, "fondo": {"tipo": "oficina"},
         "transicion": {"tipo": "barrido", "duracion": 0.4},
         "camara": [{"t": 0, "zoom": 1.0}, {"t": 1, "zoom": 1.2, "x": 5000}],
         "elementos": [{"tipo": "prop", "nombre": "moneda", "entrada": "rebote"}]},
    ], "subtitulos": [{"texto": "uno dos tres cuatro", "inicio": 0.1, "fin": 1.8}]}
    d.update(extra)
    return d


def test_video_desde_dict_y_transicion():
    v = Video.desde_dict(_guion())
    assert v.duracion == 2.0 and v.total_cuadros == 60
    c = v.cuadro(33)                      # 0,1 s dentro de la escena 2 → en la transición
    assert c.b is not None and c.transicion[0] == "barrido"
    assert 0 < c.transicion[1] < 1
    assert v.cuadro(50).b is None
    assert v.cuadro(10).encima             # hay subtítulo
    _es_svg(c.a.frente + c.a.fijo + c.encima)
    json.dumps(_guion())                   # el formato es JSON puro


def test_camara_no_se_sale_del_dibujo():
    v = Video.desde_dict(_guion())
    z, dx, dy, _ = v.escenas[1].camara_en(1.0)
    assert z == pytest.approx(1.2)
    assert dx == pytest.approx(540 * (1 - 1 / 1.2), abs=0.2)   # 5000 recortado al borde


@pytest.mark.parametrize("cambio,texto", [
    ({"escenas": [{"duracion": 1, "elementos": [{"tipo": "dragon"}]}]}, "dragon"),
    ({"escenas": [{"duracion": 1, "fondo": "playa"}]}, "playa"),
    ({"escenas": [{"duracion": 1, "elementos": [{"tipo": "prop", "nombre": "auto"}]}]}, "auto"),
    ({"escenas": [{"duracion": 1, "transicion": "giro"}]}, "giro"),
    ({"escenas": [{"elementos": []}]}, "duracion"),
    ({"escenas": [{"duracion": 1, "elementos": [
        {"tipo": "personaje", "gestos": [{"t": 0, "gesto": "bailar"}]}]}]}, "bailar"),
    ({"escenas": [{"duracion": 1, "elementos": [
        {"tipo": "prop", "nombre": "flecha", "keyframes": [{"t": 0, "color": 1}]}]}]}, "color"),
    ({"escenas": []}, "escenas"),
])
def test_errores_de_guion_dicen_que_esta_mal(cambio, texto):
    with pytest.raises(ErrorGuion, match=texto):
        Video.desde_dict(cambio)


def test_cuadros_iguales_se_detectan():
    v = Video.desde_dict({"escenas": [{"duracion": 1, "fondo": "ciudad", "elementos": [
        {"tipo": "texto", "texto": "QUIETO"}]}]})
    assert v.cuadro(3) == v.cuadro(4)


# ---- audio ------------------------------------------------------------------------


def test_envolvente_sigue_la_voz(tmp_path):
    wav = au.voz_de_prueba(tmp_path / "v.wav", [(0.5, 1.5)], 2.0)
    env = au.envolvente(wav, 30)
    assert len(env) == 60
    assert max(env[:12]) == 0.0            # silencio: boca cerrada
    assert max(env[18:42]) > 0.5           # hablando: se abre
    assert au.vocal(0, 0.0) == "cerrada" and au.vocal(0, 0.9) == "a"


def test_boca_del_que_habla_sigue_el_audio(tmp_path):
    wav = au.voz_de_prueba(tmp_path / "v.wav", [(0.0, 1.0)], 1.0)
    d = {"audio": str(wav), "escenas": [{"duracion": 1, "elementos": [
        {"tipo": "personaje", "habla": True}, {"tipo": "personaje", "nombre": "pibe"}]}]}
    v = Video.desde_dict(d)
    abiertos = [i for i in range(30) if v.envolvente[i] > 0.5]
    assert abiertos
    callado = per.personaje("narrador").svg(per.Estado())
    assert "#5a1e2a" in v.cuadro(abiertos[0]).a.frente   # interior de la boca abierta
    assert callado


# ---- render -----------------------------------------------------------------------


def _ffprobe(ruta):
    from clips_bot.media import find_bin

    r = subprocess.run([find_bin("ffprobe"), "-v", "error", "-count_frames", "-show_entries",
                        "stream=codec_type,width,height,nb_read_frames,pix_fmt", "-of", "json",
                        str(ruta)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return {s["codec_type"]: s for s in json.loads(r.stdout)["streams"]}


@pytest.mark.skipif(not rd.disponibles(), reason="no hay rasterizador de SVG instalado")
@pytest.mark.parametrize("procesos", [1, 2])
def test_render_de_10_cuadros_da_un_mp4_valido(tmp_path, procesos):
    wav = au.voz_de_prueba(tmp_path / "v.wav", [(0.0, 0.3)], 0.4)
    v = Video.desde_dict(_guion(audio=str(wav)))
    r = rd.renderizar(v, tmp_path / "x.mp4", procesos=procesos, escala=0.125, max_cuadros=10,
                      preset="ultrafast")
    s = _ffprobe(r.salida)
    assert (s["video"]["width"], s["video"]["height"]) == (136, 240)
    assert int(s["video"]["nb_read_frames"]) == 10
    assert s["video"]["pix_fmt"] == "yuv420p"
    assert "audio" in s
    assert r.cuadros == 10


@pytest.mark.skipif(not rd.disponibles(), reason="no hay rasterizador de SVG instalado")
def test_cuadro_png_y_camara_mueve_el_fondo(tmp_path):
    from PIL import Image

    v = Video.desde_dict(_guion())
    a = rd.cuadro_png(v, 45, tmp_path / "a.png", escala=0.125)
    b = rd.cuadro_png(v, 59, tmp_path / "b.png", escala=0.125)
    ia, ib = np.asarray(Image.open(a)), np.asarray(Image.open(b))
    assert ia.shape == (240, 136, 3)
    assert np.abs(ia.astype(int) - ib.astype(int)).mean() > 1   # la cámara se movió


def test_coeficientes_camara_identidad():
    a, b, c, d, e, f = rd.coeficientes_camara((1.0, 0.0, 0.0, 0.0), 1080, 1920)
    assert (a, b, d, e) == (1, 0, 0, 1) or (math.isclose(a, 1) and math.isclose(e, 1))
    assert abs(c) < 1e-9 and abs(f) < 1e-9
