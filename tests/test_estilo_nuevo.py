"""Estilo nuevo de Pequeña Historia (efemerides.estilo_nuevo, Santi 2026-11-14): arranque que se mueve,
gancho y subtítulos animados, más video, el mapa acercándose al lugar."""

import json
import subprocess

from clips_bot import efemerides as ef
from clips_bot import graficos as gr
from clips_bot import subtitles as sub
from clips_bot.config import load_settings
from clips_bot.media import find_bin
from clips_bot.subtitles import Palabra


def _g(**k):
    base = dict(frases=["a b c", "d e", "f g", "h"], fotos=[0, 1, 2, 3], descartadas=[], titulo="t",
                descripcion="d", hashtags=[], ranking=[[0, 4, 5], [1], [2], [3]], corto=True)
    base.update(k)
    return ef.Guion(**base)


def test_apagado_por_defecto():
    assert load_settings().efemerides.estilo_nuevo is False


def test_el_gancho_es_un_montaje_de_3_con_golpe():
    plan, movs = ef.plan_rapido([(0, 0, 3.0), (1, 1, 3.0), (2, 2, 3.0)], _g(), montaje=True)
    gancho = [x for x in plan if x[0] == 0]
    assert [f for _, f, _ in gancho] == [0, 4, 5]               # la más impactante primero
    assert all(abs(s - 1.0) < 0.01 for *_, s in gancho)
    assert movs[:3] == ["golpe"] * 3
    assert abs(sum(s for *_, s in plan) - 9.0) < 0.01           # el largo no cambia
    sin, _ = ef.plan_rapido([(0, 0, 3.0), (1, 1, 3.0)], _g())
    assert [f for i, f, _ in sin if i == 0] == [0, 4]           # sin el estilo nuevo, como antes


def test_un_gancho_corto_hace_menos_cortes_y_un_video_no_se_toca():
    plan, _ = ef.plan_rapido([(0, 0, 1.3), (1, 1, 3.0)], _g(), montaje=True)
    assert len([x for x in plan if x[0] == 0]) == 2
    plan, movs = ef.plan_rapido([(0, ef.VIDEO, 3.0), (1, 1, 3.0)], _g(), montaje=True)
    assert plan[0] == (0, ef.VIDEO, 3.0) and movs[0] == ""


def test_golpe_de_zoom():
    f = ef.filtro_movimiento(30, 0.5, 0.5, "golpe", 1080, 1920)
    assert "if(lt(on,6),1.25" in f


def test_el_mapa_cuenta_como_imagen_real_y_no_va_a_los_creditos():
    pool = [{"ruta": "a.jpg", "archivo": "File:A.jpg"}]
    assert ef.fraccion_real(pool, [(0, 0, 2.0), (1, ef.MAPA, 2.0)]) == 1.0


def test_frases_con_video():
    g = _g(accion=[2], central=[True, False, True, False])
    assert ef.frases_video(g) == [2]                              # como siempre
    g.mas_video = True
    assert ef.frases_video(g) == [0, 1, 2, 3]                     # gancho + acción + al pasar
    g = _g(frases=["x"] * 10, central=[False] * 10, mas_video=True)
    assert len(ef.frases_video(g)) == ef.MAX_VIDEOS_NUEVO


def test_gancho_animado_palabra_por_palabra_sin_reacomodarse():
    [ev] = gr.gancho_animado("Una mujer desafió a todo un ejército", 3.0)
    assert ev.startswith("Dialogue: 3,0:00:00.00,")
    assert ev.count(r"\alpha&HFF&") == 6                          # todas menos la primera esperan
    assert r"{\alpha&H00&\fscy100}Una" in ev                      # la primera, desde el cuadro 0
    tiempos = [int(x) for x in __import__("re").findall(r"\\t\((\d+),\d+,\\alpha&H00&", ev)]
    assert tiempos == sorted(tiempos) and tiempos[-1] + 230 <= 800   # entera antes de la portada


def test_subtitulos_con_saltito(tmp_path):
    s = load_settings()
    ps = [Palabra(0.0, 0.2, "En"), Palabra(0.2, 0.5, "mil"), Palabra(0.5, 1.0, "ochocientos"),
          Palabra(1.0, 1.5, "diecisiete")]
    sub.escribir_ass_karaoke(ps, tmp_path / "s.ass", s.subtitulos, s.render, color_activo=sub.KARAOKE_PH,
                             tamano=100, rebote=True, borde=9, max_chars=14)
    txt = (tmp_path / "s.ass").read_text(encoding="utf-8")
    assert ",100,&H00FFFFFF" in txt and ",9,3,5," in txt
    assert sub.REBOTE in txt
    eventos = [l for l in txt.splitlines() if l.startswith("Dialogue")]
    assert all(len(l.split("}", 1)[1].replace(sub.REBOTE, "").split()) <= 3 for l in eventos)


def test_mapa_zoom_hace_un_video(tmp_path):
    from PIL import Image

    base = tmp_path / "base.png"
    Image.new("RGB", (720, 360), (20, 60, 140)).save(base)
    out = gr.mapa_zoom(base, 4.6, -74.1, tmp_path / "m.mp4", segundos=0.4, W=108, H=192, fps=10)
    info = json.loads(subprocess.run([find_bin("ffprobe"), "-v", "error", "-show_streams", "-of", "json",
                                      str(out)], capture_output=True, text=True).stdout)
    v = info["streams"][0]
    assert (v["width"], v["height"]) == (108, 192) and int(v["nb_frames"]) == 4


def test_los_cuadros_de_video_no_pasan_el_tope_de_claude():
    class V:
        def __init__(self):
            self.frames = ["a", "b", "c"]

    vids = {i: [V() for _ in range(4)] for i in range(6)}            # 72 cuadros
    r = ef.recortar_videos(vids, 100 - 56)                          # con un pool de 56 fotos
    assert sum(len(v.frames) for vs in r.values() for v in vs) <= 44
    assert all(len(vs) == 2 for vs in r.values())                   # 2 por frase, las 6 frases
    assert ef.recortar_videos(vids, 10) == {0: vids[0][:1], 1: vids[1][:1], 2: vids[2][:1]}
    assert ef.recortar_videos(vids, 200) == vids
