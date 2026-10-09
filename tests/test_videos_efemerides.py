"""Videos en las frases de acción de Pequeña Historia (2026-09-29). Sin red: las fuentes son fakes."""

import json
import subprocess
from pathlib import Path

import pytest

from clips_bot import efemerides as ef, videos_libres as vl
from clips_bot.config import load_settings
from clips_bot.media import find_bin


def _v(fuente="archive", anio=1957, dur=45.0, titulo="New Moon", frames=None):
    return vl.Video(fuente, titulo, "https://x/v.mp4", "https://archive.org/details/x", "Dominio público",
                    "British Pathé", anio, dur, momentos=[9.0, 22.5, 36.0], frames=frames or ["a", "b", "c"])


def test_gemini_marca_hasta_3_frases_de_accion_y_nunca_la_primera():
    frases = [{"accion": True}, {"accion": False}, {"accion": True}, {"accion": True},
              {"accion": True}, {"accion": True}]
    assert ef.frases_de_accion(frases) == [2, 3, 4]
    assert ef.SCHEMA_GUION["properties"]["frases"]["items"]["required"][-1] == "accion"
    assert "`accion`" in ef.SISTEMA_GUION


def test_la_eleccion_del_video_respeta_la_epoca():
    videos = {2: [_v(), _v("pexels", None, titulo="stock")], 5: [_v()], 6: [_v()]}
    frases = [{}] * 2 + [{"video": 1, "momento": 3, "video_de_epoca": True}] + [{}] * 2 \
        + [{"video": 1, "momento": 1, "video_de_epoca": False}] + [{"video": 0}]
    out = ef.video_elegido(frases, videos, [False] * 7)
    assert list(out) == [2]                           # la 5 es un anacronismo, la 6 no eligió
    assert out[2].momento == 36.0 and out[2].frames == ["c"]
    hoy = ef.video_elegido(frases, videos, [False] * 5 + [True, False])
    assert 5 in hoy                                   # en una frase de hoy, lo moderno sirve


class B:
    """Buscador falso: `archivo` y `stock` son lo que devuelve cada etapa."""

    def __init__(self, archivo=(), stock=(), nasa=()):
        self.a, self.s, self.n, self.pedidos = list(archivo), list(stock), list(nasa), []

    def commons(self, q):
        self.pedidos.append(("commons", q))
        return self.a

    def archive(self, q, anio=None):
        self.pedidos.append(("archive", q, anio))
        return []

    def pexels(self, q):
        self.pedidos.append(("pexels", q))
        return self.s

    def pixabay(self, q):
        return []

    def nasa(self, q):
        self.pedidos.append(("nasa", q))
        return self.n

    candidatos = vl.Buscador.candidatos


def test_primero_la_filmacion_de_archivo_y_recien_si_no_hay_el_stock():
    b = B(archivo=[_v()], stock=[_v("pexels", None)])
    assert [v.fuente for v in b.candidatos("1957 Sputnik launch Soviet Union", 1957, False)] == ["archive"]
    assert b.pedidos[0] == ("commons", "Sputnik launch Soviet Union")   # sin el año
    assert not any(p[0] == "pexels" for p in b.pedidos)
    b = B(archivo=[_v(anio=2008)], stock=[_v("pexels", None)], nasa=[_v("nasa", 2005)])
    out = b.candidatos("1957 Sputnik launch", 1957, False)
    # el de archivo de 2008 es de otra época → etapa 2; NASA por ser de espacio, pero de 2005: afuera
    assert [v.fuente for v in out] == ["pexels"]
    assert not any(p[0] == "nasa" for p in B().pedidos)
    b = B()
    b.candidatos("1928 London laboratory mold", 1928, False)
    assert not any(p[0] == "nasa" for p in b.pedidos)                   # no es de espacio


def _guion(n=6, **kw):
    return ef.Guion(frases=[f"frase {i}" for i in range(n)], fotos=list(range(n)), descartadas=[],
                    titulo="t", descripcion="d", hashtags=["#Shorts", "#a", "#b"],
                    mostrar=["1957 x"] * n, ranking=[[i] for i in range(n)], presente=[False] * n, **kw)


def _propuesta(g, n=6):
    fotos = [ef.Foto(f"File:{i}.jpg", "u", 1200, 800, "CC0", "a", "e", "p", "art", ruta=f"{i}.jpg",
                     anio=1957).a_dict() for i in range(n)]
    return ef.Propuesta(fecha="2026-10-04", evento={"lang": "es", "anio": 1957, "texto": "Sputnik",
                                                    "paginas": ["Sputnik 1"]},
                        fotos=fotos, reserva=[], guion=g.a_dict())


def test_una_frase_con_video_es_un_solo_tramo_del_largo_de_la_frase():
    g = _guion(accion=[2], videos={"2": _v().a_dict()}, con_video=[2], con_videos=True)
    p = _propuesta(g)
    plan = ef.plan_de(p, [3.0, 4.0, 8.5, 3.0, 3.0, 3.0])
    assert [x for x in plan if x[0] == 2] == [(2, ef.VIDEO, 8.5)]      # 8,5 s, sin partir en 6
    assert ef.VIDEO not in {f for i, f, _ in plan if i != 2}
    assert 3 not in ef.numeros_usados(p)                             # la foto de la frase 2 no se ve
    assert [v.titulo for v in ef.videos_en_orden(p, plan)] == ["New Moon"]


def test_el_boton_pasa_de_video_a_foto_y_de_foto_a_video(tmp_path, monkeypatch):
    g = _guion(accion=[2], videos={"2": _v().a_dict()}, con_video=[2], con_videos=True)
    p = _propuesta(g)
    assert ef.alternar_video(p, 3, tmp_path) == "Frase 3: vuelve a foto."
    assert ef.Guion.de_dict(p.guion).con_video == []
    assert "🎬 video (archive.org, 1957)" in ef.alternar_video(p, 3, tmp_path)
    # una frase sin video: lo busca en el momento y Gemini MIRA los cuadros antes de usarlo
    monkeypatch.setattr(ef, "buscar_videos",
                        lambda g, anio, c, b, avisar, frases, tema: {frases[0]: [_v("commons", 1957)]})
    monkeypatch.setattr(ef, "_jpeg_chico", lambda ruta, ancho=512: b"x")

    class Gem:
        def __init__(self, respuesta):
            self.r, self.vistas = respuesta, []

        def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
            self.vistas.append((prompt, len(imagenes or [])))
            return json.dumps(self.r)

    gem = Gem({"se_ve": "un cohete despegando", "video": 1, "momento": 3, "video_de_epoca": True})
    assert "Wikimedia Commons" in ef.alternar_video(p, 5, tmp_path, cliente=gem)
    assert gem.vistas[0][1] == 3 and "EL HECHO ES DE 1957" in gem.vistas[0][0]
    g2 = ef.Guion.de_dict(p.guion)
    assert g2.con_video == [2, 4] and g2.videos["4"]["momento"] == 36.0
    dibujo = Gem({"se_ve": "un dibujo animado", "video": 0, "momento": 1, "video_de_epoca": True})
    assert "ninguno muestra lo que dice" in ef.alternar_video(p, 4, tmp_path, cliente=dibujo)
    assert "Sin Gemini" in ef.alternar_video(p, 2, tmp_path)
    monkeypatch.setattr(ef, "buscar_videos", lambda *a, **k: {})
    assert "No encontré" in ef.alternar_video(p, 6, tmp_path)


def test_la_aprobacion_marca_los_videos_y_sus_creditos():
    g = _guion(accion=[2, 4], videos={"2": _v().a_dict()}, con_video=[2], con_videos=True)
    p = _propuesta(g)
    plan = ef.plan_de(p)
    t = ef.texto_aprobacion(ef.Evento(**p.evento), g, ef.usadas_en_orden(p, plan),
                            __import__("datetime").date(2026, 10, 4), plan,
                            [ef.Foto.de_dict(f) for f in p.fotos])
    assert "🎬 3. [video: archive.org, 1957 — New Moon] frase 2" in t
    assert "5. [5 (1957)] frase 4 (acción: sin video libre, va con foto)" in t
    assert "1 con video" in t and "Videos:\n1. New Moon — British Pathé — Dominio público" in t


def test_la_hoja_dibuja_el_cuadro_del_video(tmp_path):
    from PIL import Image

    for i in range(3):
        Image.new("RGB", (800, 600), (40 * i, 90, 90)).save(tmp_path / f"{i}.jpg")
    Image.new("RGB", (640, 480), (200, 30, 30)).save(tmp_path / "cuadro.jpg")
    fotos = [ef.Foto(f"File:{i}.jpg", "u", 800, 600, "CC0", "a", "e", "p", "art",
                     ruta=str(tmp_path / f"{i}.jpg")) for i in range(3)]
    salida = ef.hoja_de_guion(fotos, [([0], "uno"), ([ef.VIDEO], "despega"), ([2], "tres")],
                              tmp_path / "hoja.jpg", videos={1: _v(frames=[str(tmp_path / "cuadro.jpg")])})
    assert salida.exists() and Image.open(salida).height > 3 * 150


@pytest.mark.skipif(not find_bin("ffmpeg"), reason="sin ffmpeg")
def test_el_tramo_de_video_dura_exacto_lo_de_su_frase(tmp_path):
    """Render real: un video de 2 s (más corto que la frase: se repite) y una foto, con la voz."""
    from PIL import Image

    ff = find_bin("ffmpeg")
    video = tmp_path / "v.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=480x360:rate=25",
                    "-t", "2", str(video)], check=True)
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (1200, 800), (30, 60, 90)).save(foto)
    voz = tmp_path / "voz.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=300:d=7",
                    str(voz)], check=True)
    (tmp_path / "subs.ass").write_text("[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
                                       "Format: Name, Fontname, Fontsize\nStyle: Default,Arial,20\n\n"
                                       "[Events]\nFormat: Layer, Start, End, Style, Text\n", encoding="utf-8")
    render = load_settings().render
    salida = ef.armar_video([(foto, 3.0), (video, 4.0)], voz, tmp_path, tmp_path / "out.mp4", render)
    dur = float(subprocess.run([find_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nw=1:nk=1", str(salida)], capture_output=True,
                               text=True).stdout)
    assert dur == pytest.approx(7.0, abs=0.1)
    ancho = subprocess.run([find_bin("ffprobe"), "-v", "error", "-select_streams", "v", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(tmp_path / "tramo_01.mp4")],
                           capture_output=True, text=True).stdout.strip()
    assert ancho == f"{render.ancho},{render.alto}"


def test_commons_solo_licencias_libres_y_el_derivado_chico():
    class S:
        headers = {}

        def get(self, url, params=None, timeout=None, **k):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    def pagina(titulo, lic, dur, i):
                        return {"title": titulo, "index": i, "videoinfo": [{
                            "duration": dur, "url": "https://upload.wikimedia.org/o.ogv",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/" + titulo,
                            "derivatives": [{"transcodekey": "240p.vp9.webm", "src": "https://u/240.webm"},
                                            {"transcodekey": "480p.vp9.webm", "src": "https://u/480.webm"}],
                            "extmetadata": {"LicenseShortName": {"value": lic},
                                            "DateTimeOriginal": {"value": "1957-10-07"},
                                            "Artist": {"value": "Universal Newsreel"}}}]}
                    return {"query": {"pages": {"1": pagina("File:New Moon.ogv", "Public domain", 45.2, 1),
                                                "2": pagina("File:Otro.webm", "CC BY-NC 2.0", 30, 2),
                                                "3": pagina("File:Corto.webm", "CC0", 1.5, 3)}}}
            return R()

    b = vl.Buscador(session=S())
    out = b.commons("Sputnik")
    assert [v.titulo for v in out] == ["New Moon"] and out[0].url == "https://u/480.webm"
    assert out[0].anio == 1957 and out[0].autor == "Universal Newsreel"


def test_prendido_desde_que_santi_aprobo_la_muestra():
    assert load_settings().efemerides.videos is True    # Apolo 11, 2026-10-04


def test_sin_anios_y_espacio():
    assert vl.sin_anios("1957 Sputnik launch 1950s Soviet") == "Sputnik launch Soviet"
    assert vl.es_de_espacio("1969 Apollo 11 rocket launch") and not vl.es_de_espacio("1928 London mold")


def test_las_consultas_van_de_la_puntual_a_la_general():
    # medido con el Sputnik: la puntual no trae nada, "rocket launch" y el tema sí
    assert vl.consultas("1957 R-7 rocket launch pad", "Sputnik_1") == [
        "R-7 rocket launch pad", "R-7 rocket launch", "R-7 rocket", "rocket launch", "launch pad",
        "Sputnik 1"]


def test_si_la_puntual_no_trae_nada_prueba_la_siguiente_y_corta_al_juntar():
    class B2(B):
        def commons(self, q):
            self.pedidos.append(("commons", q))
            return [_v("commons", 1957, titulo=q)] if q in ("rocket launch", "Sputnik 1") else []

    b = B2()
    out = b.candidatos("1957 R-7 rocket launch pad", 1957, False, tema="Sputnik_1", cuantos=1)
    assert [v.titulo for v in out] == ["rocket launch"]
    assert ("commons", "Sputnik 1") not in b.pedidos            # ya había juntado lo que pedía


def test_el_mismo_video_en_dos_frases_va_en_momentos_distintos():
    vs = [_v()]
    frases = [{}] * 4 + [{"video": 1, "momento": 2, "video_de_epoca": True}] * 3 \
        + [{"video": 1, "momento": 2, "video_de_epoca": True}]
    out = ef.video_elegido(frases, {4: vs, 5: vs, 6: vs, 7: vs}, [False] * 8)
    assert [out[i].momento for i in (4, 5, 6)] == [22.5, 9.0, 36.0]
    assert 7 not in out                                    # ya no queda momento libre: foto


def test_los_cuadros_de_video_descartados_no_rompen_las_fotos():
    import json as _json

    class C:
        def json(self, *a, **k):
            return _json.dumps({"frases": [{"se_ve": "x", "fotos": [1], "de_epoca": True}],
                                "descartadas": [2, 7]})

    g = _guion(n=1)
    pool = [ef.Foto("File:a.jpg", "u", 800, 600, "CC0", "a", "e", "p", "art", ruta="a.jpg"),
            ef.Foto("File:b.jpg", "u", 800, 600, "CC0", "a", "e", "p", "art", ruta="b.jpg")]
    import clips_bot.efemerides as mod
    orig = mod._jpeg_chico
    mod._jpeg_chico = lambda ruta, ancho=512: b"x"
    try:
        _, malas = ef.elegir_fotos(C(), g, pool, [[0, 1]])
    finally:
        mod._jpeg_chico = orig
    assert malas == {1}                                    # el 7 era un cuadro de video
