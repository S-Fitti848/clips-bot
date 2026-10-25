"""El clip de Auron del 2026-10-25: la cara de una foto en pantalla arriba en vez de su webcam,
subtítulos dobles y la pantalla cortada a la izquierda. Sin red."""
import json
from pathlib import Path

import numpy as np
import pytest

from clips_bot import layout as lay
from clips_bot import pantalla, registro, revision
from clips_bot.config import Camara, ConfigError, Render, _facecam
from clips_bot.render import filtro
from clips_bot.subtitles import Palabra

W, H = 1920, 1080
CAM, R = Camara(), Render()


# ---- (1) la cara de la cámara ---------------------------------------------------------------------

def test_dos_caras_de_distinto_tamano_en_el_mismo_lugar_no_son_la_misma():
    """Auron a pantalla completa (12 % del ancho) y un chico en una foto (2,7 %) en el mismo lugar:
    antes contaban como UNA cara estable al 90 % y el split ponía la foto arriba."""
    grande, chica = (870, 330, 240, 240), (860, 450, 52, 52)
    frames = [[grande] for _ in range(8)] + [[chica] for _ in range(12)]
    cara, presencia = lay.cara_estable(W, H, frames)
    assert presencia == pytest.approx(0.6)        # la de la foto sola, no 100 %
    assert lay.decidir_layout(W, H, frames, CAM, R).tipo == "fit_blur"


def _cuadros_con_marco(n=12, caja=(1546, 20, 336, 290), cambio_de_escena=0, seed=1):
    """Cuadros con ruido que cambia y un marco fijo (la webcam). Con `cambio_de_escena`, los primeros
    n cuadros no tienen marco (otra escena)."""
    import cv2

    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        img = (rng.random((H, W, 3)) * 60).astype(np.uint8)
        if i >= cambio_de_escena:
            x, y, w, h = caja
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 255), 8)
        out.append(img)
    return out


def test_el_marco_fijo_de_la_webcam_se_encuentra_alrededor_de_la_cara():
    imgs = _cuadros_con_marco()
    cara = (1660, 100, 90, 90)
    caja = lay.recuadro_fijo(imgs, cara, W, H)
    assert caja is not None
    assert caja.x <= 1660 and caja.x + caja.w >= 1750 and caja.y <= 100 and caja.y + caja.h >= 190
    assert abs(caja.x - 1550) < 20 and abs(caja.w - 330) < 30


def test_sin_marco_todo_el_clip_no_hay_recuadro():
    """Un cambio de escena a mitad del clip (el caso de Auron): el marco no está en todo el clip."""
    imgs = _cuadros_con_marco(cambio_de_escena=6)
    assert lay.recuadro_fijo(imgs, (1660, 100, 90, 90), W, H) is None
    assert lay.marco_presente(lay.bordes_fijos(imgs), lay.Caja(1546, 20, 336, 290), W) < 3


def test_las_webcams_guardadas_van_en_orden_de_prioridad(monkeypatch):
    """En los Minecraft de Auron la webcam de la invitada (arriba a la derecha) tiene cara el 90 % del
    clip: gana la primera posición guardada que esté, no la de más presencia."""
    suya, invitada = (0.006, 0.378, 0.18, 0.30), (0.806, 0.022, 0.172, 0.265)
    imgs = _cuadros_con_marco(caja=(12, 408, 346, 324))
    pres = {lay.caja_de(suya, W, H): (0.5, (60, 450, 120, 120)),
            lay.caja_de(invitada, W, H): (0.9, (1650, 60, 100, 100))}
    monkeypatch.setattr(lay, "caras_en_recuadro", lambda imgs_, caja: pres[caja])
    L = lay.decidir_layout(W, H, [[] for _ in imgs], CAM, R, imagenes=imgs, facecams=(suya, invitada))
    assert L.tipo == "split"
    assert L.camara.x < 400 and L.camara.y >= 400          # la de Auron, no la de la invitada


def test_webcam_guardada_que_no_esta_no_fuerza_el_split(monkeypatch):
    imgs = _cuadros_con_marco(cambio_de_escena=6, caja=(1546, 20, 336, 290))
    monkeypatch.setattr(lay, "caras_en_recuadro", lambda imgs_, caja: (0.6, (1650, 60, 100, 100)))
    L = lay.decidir_layout(W, H, [[] for _ in imgs], CAM, R, imagenes=imgs,
                           facecams=((0.806, 0.022, 0.172, 0.265),))
    assert L.tipo == "fit_blur"


def test_la_camara_sale_de_adentro_del_recuadro_con_la_proporcion_del_panel():
    caja = lay.Caja(12, 408, 346, 324)
    ratio = R.ancho / (R.alto_camara - R.separador_px)
    c = lay.camara_desde_recuadro(caja, ratio, (60, 450, 120, 120))
    assert caja.x <= c.x and c.x + c.w <= caja.x + caja.w and caja.y <= c.y and c.y + c.h <= caja.y + caja.h
    assert abs(c.w / c.h - ratio) < 0.03


# ---- (3) abajo, el cuadro entero ------------------------------------------------------------------

def test_render_split_pone_el_cuadro_entero_abajo():
    L = lay.layout_split_recuadro(W, H, R, lay.Caja(12, 408, 346, 324), 0.9, None)
    f = filtro(L, R, con_subs=True)
    assert "crop=1920:1080:0:0" in f and f"scale={R.ancho}:-2" in f   # entero, a 1080 de ancho
    assert "gblur" in f and "overlay=0:0" in f                       # sobre el fondo difuminado


# ---- facecam en streamers.yaml y en /streamers ------------------------------------------------------

def test_facecam_del_yaml_se_valida():
    assert _facecam([[0.006, 0.378, 0.18, 0.3]], "x") == ((0.006, 0.378, 0.18, 0.3),)
    with pytest.raises(ConfigError):
        _facecam([[0.9, 0.1, 0.3, 0.2]], "x")           # se sale del cuadro
    with pytest.raises(ConfigError):
        _facecam([[0.1, 0.1]], "x")


def test_facecam_por_telegram_en_porcentaje_y_manda_sobre_el_yaml(tmp_path):
    from clips_bot import db
    from clips_bot.config import Streamer

    assert registro.leer_facecam("0,6 37,8 18 30; 80,6 2,2 17,2 26,5") == (
        (0.006, 0.378, 0.18, 0.3), (0.806, 0.022, 0.172, 0.265))
    assert registro.leer_facecam("-") == ()
    assert registro.leer_facecam("hola") is None
    assert registro.leer_facecam("90 10 30 20") is None    # se sale del cuadro
    conn = db.connect(tmp_path / "clips.db")
    yaml = [Streamer(login="auronplay", facecam=((0.1, 0.1, 0.2, 0.2),))]
    assert registro.combinar(yaml, conn)[0].facecam == ((0.1, 0.1, 0.2, 0.2),)
    registro.guardar_facecam(conn, "auronplay", ((0.5, 0.5, 0.2, 0.2),))
    assert registro.combinar(yaml, conn)[0].facecam == ((0.5, 0.5, 0.2, 0.2),)
    registro.guardar_facecam(conn, "auronplay", None)        # "fabrica": vuelve al YAML
    assert registro.combinar(yaml, conn)[0].facecam == ((0.1, 0.1, 0.2, 0.2),)
    assert "37,8" in registro.texto_facecam(((0.006, 0.378, 0.18, 0.3),))


def test_auron_tiene_su_webcam_y_subtitulos_propios():
    from clips_bot.config import load_streamers

    auron = next(s for s in load_streamers() if s.login == "auronplay")
    assert auron.subtitulos_propios
    assert len(auron.facecam) == 2 and auron.facecam[0][0] < 0.1     # la de los juegos, primero


def test_el_menu_del_streamer_tiene_el_boton_de_la_webcam():
    from clips_bot.menu import teclado_streamer

    filas = teclado_streamer(0, 1, 0, (), ((0.1, 0.1, 0.2, 0.2),))["inline_keyboard"]
    boton = next(b for fila in filas for b in fila if b["text"].startswith("📷"))
    assert "1 guardada" in boton["text"] and boton["callback_data"].startswith("st:fc")
    assert len(boton["callback_data"].encode()) <= 64


# ---- (4) chequeo visual con Gemini --------------------------------------------------------------------

class GeminiFalso:
    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.llamadas = respuesta, error, []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, **k):
        self.llamadas.append(len(imagenes or []))
        if self.error:
            raise self.error
        return json.dumps(self.respuesta)


def test_revision_una_llamada_con_dos_cuadros(monkeypatch, tmp_path):
    monkeypatch.setattr(revision, "frames_jpeg", lambda video, n, ancho=384: [b"a"] * n)
    g = GeminiFalso({"camara_ok": False, "subtitulos_dobles": True, "cortado": False,
                     "detalle": "arriba se ve una foto"})
    r = revision.revisar(g, tmp_path / "v.mp4", "split", True)
    assert g.llamadas == [2]
    assert r.falla_encuadre and r.falla_subtitulos and r.detalle == "arriba se ve una foto"


def test_si_gemini_no_responde_el_clip_sigue(monkeypatch, tmp_path):
    from clips_bot.gemini import GeminiError

    monkeypatch.setattr(revision, "frames_jpeg", lambda video, n, ancho=384: [b"a"] * n)
    r = revision.revisar(GeminiFalso(error=GeminiError("503")), tmp_path / "v.mp4", "split", True)
    assert r.error and not r.falla_encuadre and not r.falla_subtitulos


# ---- (2) subtítulos que ya vienen en el clip ------------------------------------------------------------

def _video_con_texto(path: Path, texto_por_seg: list[str]) -> None:
    import cv2

    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (960, 540))
    for txt in texto_por_seg:
        for _ in range(10):
            img = np.full((540, 960, 3), 40, np.uint8)
            if txt:
                (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 1.6, 4)
                cv2.putText(img, txt, ((960 - tw) // 2, 480), cv2.FONT_HERSHEY_SIMPLEX, 1.6,
                            (255, 255, 255), 4)
            vw.write(img)
    vw.release()


def test_ocr_ve_los_subtitulos_que_trae_el_clip(tmp_path):
    try:
        pantalla.find_tesseract()
    except Exception:
        pytest.skip("sin tesseract")
    frases = ["madura pero", "todo el mundo", "vea la foto", "bonito selfie", "que me enviaste",
              "traicionado pues", "quiero que", "persona madura"]
    palabras = [Palabra(i, i + 1, w) for i, f in enumerate(frases) for w in f.split()]
    con = tmp_path / "con.mp4"
    _video_con_texto(con, frases)
    hay, cuadros = pantalla.subtitulos_en_video(con, palabras, "eng")
    assert hay and cuadros >= pantalla.SUBS_CUADROS_MIN
    sin = tmp_path / "sin.mp4"
    _video_con_texto(sin, [""] * len(frases))
    assert pantalla.subtitulos_en_video(sin, palabras, "eng") == (False, 0)
