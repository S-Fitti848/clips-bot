"""/serie: división en etapas, guiones encadenados, título numerado, horarios y la cola.

Sin red ni video: Gemini es un fake, y ffmpeg/Piper/Whisper se reemplazan donde hace falta.
"""

import json
from pathlib import Path

import pytest

import clips_bot.__main__ as m
from clips_bot import db, narrar, serie
from clips_bot.config import load_settings
from clips_bot.subtitles import Palabra, palabra_por_palabra, escribir_ass


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


# ---- argumentos, horarios, títulos --------------------------------------------------

@pytest.mark.parametrize("args,resto,n", [
    (["https://a", "partes", "4"], ["https://a"], 4),
    (["partes:2", "https://a"], ["https://a"], 2),
    (["https://a"], ["https://a"], None),
])
def test_sacar_partes(args, resto, n):
    assert serie.sacar_partes(args) == (resto, n)


def test_partes_fuera_de_rango():
    with pytest.raises(ValueError):
        serie.sacar_partes(["partes", "9"])


def test_horarios_y_dia_siguiente():
    h = ("13:00", "18:00", "21:30")
    assert [serie.horario(h, i) for i in range(4)] == \
        ["13:00", "18:00", "21:30", "13:00 (día siguiente)"]


def test_titulo_numerado_no_se_pasa_de_59():
    assert serie.titulo_numerado("Restauro una silla vieja", 2) == "Restauro una silla vieja (Parte 2)"
    largo = serie.titulo_numerado("Restauro una silla de madera de mi abuela que estaba destruida", 1)
    assert len(largo) <= 59 and largo.endswith("… (Parte 1)")


# ---- etapas ----------------------------------------------------------------------

def _etapas(rangos, por_etapa=8):
    out = []
    for desde, hasta in rangos:
        nums = list(range(desde, hasta + 1))[:por_etapa]
        out.append({"titulo": f"de {desde} a {hasta}", "desde": desde, "hasta": hasta,
                    "momentos": [{"escena": x, "descripcion": f"m{x}"} for x in nums]})
    return {"etapas": out, "sensible": False}


def test_validar_etapas():
    assert serie.validar_etapas(_etapas([(1, 12), (13, 24), (25, 36)]), 36, 3) == []
    assert "exactamente 3" in serie.validar_etapas(_etapas([(1, 18), (19, 36)]), 36, 3)[0]
    pisadas = serie.validar_etapas(_etapas([(1, 12), (10, 24), (25, 36)]), 36, 3)
    assert any("antes de que termine" in e for e in pisadas)
    pocos = serie.validar_etapas(_etapas([(1, 12), (13, 24), (25, 36)], por_etapa=5), 36, 3)
    assert any("entre 8 y 10" in e for e in pocos)
    fuera = _etapas([(1, 12), (13, 24), (25, 36)])
    fuera["etapas"][0]["momentos"][0]["escena"] = 30
    assert any("entre la escena 1 y la 12" in e for e in serie.validar_etapas(fuera, 36, 3))


class FakeGemini:
    def __init__(self, *respuestas):
        self.respuestas, self.prompts, self.audios, self.imagenes = list(respuestas), [], [], []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None, audio=None):
        self.prompts.append(prompt)
        self.audios.append(audio)
        self.imagenes.append(len(imagenes or []))
        return json.dumps(self.respuestas.pop(0))


ESC = [(i * 10.0, i * 10.0 + 10) for i in range(36)]


def test_dividir_reintenta_y_pasa_a_indices_desde_0():
    g = FakeGemini(_etapas([(1, 18), (19, 36)]), _etapas([(1, 12), (13, 24), (25, 36)]))
    etapas, sensible = serie.dividir(g, ESC, [b""] * 36, 3)
    assert [(e.desde, e.hasta) for e in etapas] == [(0, 11), (12, 23), (24, 35)]
    assert etapas[1].pasos[0].escena == 12 and "exactamente 3" in g.prompts[1]


def test_cada_parte_dura_entre_40_y_55():
    etapas, _ = serie.dividir(FakeGemini(_etapas([(1, 12), (13, 24), (25, 36)], 9)), ESC, [], 3)
    for e in etapas:
        total = sum(b - a for a, b in narrar.ventanas(ESC, e.pasos, 360))
        assert 40 <= total <= 55


def test_texto_una_linea_por_etapa():
    etapas, _ = serie.dividir(FakeGemini(_etapas([(1, 12), (13, 24), (25, 36)])), ESC, [], 3)
    tramos = [narrar.ventanas(ESC, e.pasos, 360) for e in etapas]
    txt = serie.texto_etapas(etapas, ESC, tramos, 360)
    assert "<b>1/3</b> <i>0:00–2:00</i> · 8 momentos → 40 s: de 1 a 12" in txt
    assert txt.count("\n") == 3


# ---- guiones ---------------------------------------------------------------------

def _guiones(textos, titulo="Restauro una silla"):
    return {"titulo_serie": titulo, "partes": [{"guion": t, "confianza": 8} for t in textos],
            "sensible": False}


BUENOS = ["¿Se puede salvar esto? Arranca lijando. Cómo sigue, en la parte 2 del canal.",
          "Ahora el pegamento. El final está en la parte tres, en el canal.",
          "Y así quedó."]


@pytest.mark.parametrize("texto,siguiente,ok", [
    ("… mirá la parte 2 en el canal.", 2, True),
    ("… cómo termina, en la parte tres.", 3, True),
    ("… y eso fue todo.", 2, False),
    ("Esta es la parte 2 del proceso y sigue con muchas cosas más que pasan acá y que no tienen "
     "nada que ver con una invitación, sino con lo que se ve en pantalla durante un buen rato, "
     "así que el final no invita a nada de nada y termina con la lija.", 2, False),
])
def test_invita_a_la_siguiente_mira_el_cierre(texto, siguiente, ok):
    assert serie.invita_a_la_siguiente(texto, siguiente) is ok


def test_validar_guiones():
    assert serie.validar_guiones(_guiones(BUENOS), 3) == []
    sin_invitar = _guiones([BUENOS[0], "Ahora el pegamento.", BUENOS[2]])
    assert "la parte 2 tiene que cerrar" in serie.validar_guiones(sin_invitar, 3)[0]
    assert "entre 1 y 45" in serie.validar_guiones(_guiones(BUENOS, "x" * 60), 3)[0]


def test_escribir_guiones_una_sola_llamada_con_todas_las_imagenes():
    g = FakeGemini(_guiones(["sin invitar", "tampoco", "fin"]), _guiones(BUENOS))
    partes = [{"duracion": 45, "pasos": ["lija"], "imagenes": [b"a", b"b", b"c"]}] * 3
    r = serie.escribir_guiones(g, partes, audio=b"mp3")
    assert r.titulo == "Restauro una silla" and len(r.textos) == 3
    assert g.imagenes[0] == 9 and "PARTE 3/3" in g.prompts[0] and "imágenes 7-9" in g.prompts[0]
    assert "la parte 1 tiene que cerrar" in g.prompts[1]      # reintentó con el error


# ---- subtítulos palabra por palabra y el cartel ------------------------------------------

def test_palabra_por_palabra_sin_parpadeo():
    ps = [Palabra(0.0, 0.3, "Mirá"), Palabra(0.35, 0.6, "esto"), Palabra(2.0, 2.2, "ahora")]
    subs = palabra_por_palabra(ps, load_settings().subtitulos)
    assert [s.lineas for s in subs] == [("Mirá",), ("esto",), ("ahora",)]
    assert subs[0].fin == 0.35           # hueco chico: se queda hasta la siguiente
    assert subs[1].fin == 0.6            # hueco grande: se va


def test_el_cartel_va_arriba_los_primeros_3_s(tmp_path):
    cfg = load_settings()
    escribir_ass([], tmp_path / "s.ass", cfg.subtitulos, cfg.render, cartel="Parte 2/3")
    ass = (tmp_path / "s.ass").read_text(encoding="utf-8")
    assert "Style: Cartel," in ass and ",8,40,40,140,1" in ass      # Alignment 8 = arriba al centro
    assert "Dialogue: 1,0:00:00.00,0:00:03.00,Cartel,,0,0,0,,Parte 2/3" in ass


# ---- el flujo en el bot --------------------------------------------------------------

class FakeTG:
    def __init__(self):
        self.mensajes, self.fotos, self.respuestas = [], [], []

    def send_message(self, chat_id, texto, teclado=None):
        self.mensajes.append((texto, teclado))

    def send_photo(self, chat_id, path, caption="", teclado=None):
        self.fotos.append(path)

    def answer_callback(self, cid, texto=""):
        self.respuestas.append(texto)

    def edit_message(self, *a, **k):
        pass


def test_sin_video_queda_esperando_con_las_partes(conn):
    r = m._serie(conn, FakeTG(), "1", "7", ["partes", "4", "sin", "audio"], None)
    assert "Mandame el video" in r and "lo parto en 4" in r
    assert db.get_valor(conn, f"{m.ESPERA_VIDEO}:7") == "serie:4"
    assert db.get_valor(conn, f"{m.ESPERA_SIN_AUDIO}:7") == "1"


def test_proponer_etapas_manda_una_fila_por_parte_y_los_botones(conn, monkeypatch, tmp_path):
    from clips_bot import process

    monkeypatch.setattr(process, "WORK_DIR", tmp_path)
    monkeypatch.setattr(m, "_gemini", lambda s: FakeGemini(_etapas([(1, 12), (13, 24), (25, 36)])))
    monkeypatch.setattr(narrar, "cortes_de_escena", lambda v: [])
    monkeypatch.setattr(narrar, "frames_en", lambda v, ts: [b"jpg"] * len(ts))
    filas = []
    monkeypatch.setattr(serie, "hoja_de_etapas", lambda f, salida: filas.extend(f) or salida)
    tg = FakeTG()
    estado = {"raw": "x.mp4", "duracion": 360.0, "partes": 3, "chat_id": "1", "user_id": "7"}
    assert m._proponer_etapas(conn, tg, "1", estado, None) is None
    assert len(filas) == 3 and all(len(f) == 8 for f in filas)
    texto, teclado = tg.mensajes[-1]
    assert "Serie en 3 partes" in texto
    datos = [b["callback_data"] for b in teclado["inline_keyboard"][0]]
    assert [d.split(":")[1] for d in datos] == ["ok", "no"]
    guardado = m._serie_estado(conn, datos[0].split(":")[2])
    assert len(guardado["tramos"]) == 3 and len(guardado["escenas"]) >= 36


def test_aprobar_con_algo_pesado_andando_va_a_la_cola(conn):
    db.set_valor(conn, "serie:0a1b2c", json.dumps({"partes": 3}))
    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1)
    tg, cola = FakeTG(), []
    m._serie_callback(conn, tg, {"data": "ser:ok:0a1b2c", "chat_id": "1", "message_id": 3,
                                 "callback_id": "q", "user_id": "7"}, None, cola)
    assert cola == [{"chat_id": "1", "comando": "serie:partes", "args": ["0a1b2c"], "user_id": "7"}]
    assert "En cola" in tg.mensajes[-1][0]


def test_cambiar_los_guiones_deja_esperando_la_correccion(conn):
    db.set_valor(conn, "serie:0a1b2c", json.dumps({"partes": 3}))
    m._serie_callback(conn, FakeTG(), {"data": "ser:gno:0a1b2c", "chat_id": "1", "message_id": 3,
                                       "callback_id": "q", "user_id": "7"}, None, [])
    assert json.loads(db.get_valor(conn, f"{m.ESPERA_SERIE}:7")) == {"token": "0a1b2c",
                                                                      "fase": "guiones"}


def test_aprobar_sin_audio_queda_en_el_estado(conn, monkeypatch):
    db.set_valor(conn, "serie:0a1b2c", json.dumps({"partes": 3}))
    llamados = []
    monkeypatch.setattr(m, "_serie_voces", lambda c, tg, chat, token, s: llamados.append(token))
    m._serie_callback(conn, FakeTG(), {"data": "ser:gokm:0a1b2c", "chat_id": "1", "message_id": 3,
                                       "callback_id": "q", "user_id": "7"}, None, [])
    assert llamados == ["0a1b2c"] and m._serie_estado(conn, "0a1b2c")["sin_audio"] is True


def test_las_partes_llegan_juntas_numeradas_y_con_horario(conn, monkeypatch, tmp_path):
    from clips_bot import layout, process, render, subtitles

    for nombre in ("READY_DIR", "WORK_DIR"):
        monkeypatch.setattr(process, nombre, tmp_path / nombre.lower())
    (tmp_path / "ready_dir").mkdir()
    ids = []
    for k in (1, 2, 3):
        cid = f"x_parte{k}"
        ids.append(cid)
        (tmp_path / "ready_dir" / f"{cid}.json").write_text(json.dumps(
            {"clip_id": cid, "streamer": "", "salida": str(tmp_path / f"{cid}.mp4"),
             "textos": {"titulo": f"otro {k}", "descripcion": "d", "hashtags": ["#Shorts"],
                        "credito": "c"}}))
    voz = tmp_path / "voces" / "v.onnx"
    voz.parent.mkdir()
    voz.write_bytes(b"")
    cfg = load_settings()
    from dataclasses import replace
    cfg = replace(cfg, voz=replace(cfg.voz, modelo=str(voz)))
    mezclas = []
    monkeypatch.setattr(narrar, "sintetizar", lambda t, mod, salida, ajustes=None: salida)
    monkeypatch.setattr(narrar, "subtitular_voz", lambda w, c, palabra_por_palabra=False:
                        [] if palabra_por_palabra else pytest.fail("tenía que ser palabra por palabra"))
    carteles = []
    monkeypatch.setattr(subtitles, "escribir_ass", lambda s, p, c, r, cartel="", cartel_s=3.0:
                        carteles.append((cartel, cartel_s)))
    monkeypatch.setattr(subtitles, "escribir_srt", lambda s, p: None)
    monkeypatch.setattr(layout, "detectar_caras", lambda p, n: (1920, 1080, [], []))
    monkeypatch.setattr(render, "renderizar", lambda *a: None)
    monkeypatch.setattr(narrar, "mezclar", lambda v, w, s, vol, sin_original=False:
                        mezclas.append((vol, sin_original)))
    enviados = []
    monkeypatch.setattr(m, "enviar_clip", lambda tg, chat, c, cid, meta, n, horario, encabezado="":
                        enviados.append((n, horario, meta["textos"]["titulo"], encabezado)))
    db.set_valor(conn, "serie:0a1b2c", json.dumps(
        {"ids": ids, "guiones": ["a", "b", "c"], "titulo_serie": "Restauro una silla"}))

    assert m._serie_voces(conn, FakeTG(), "1", "0a1b2c", cfg) is None
    assert carteles == [("Parte 1/3", 3.0), ("Parte 2/3", 3.0), ("Parte 3/3", 3.0)]
    assert mezclas == [(0.15, False)] * 3                      # original al 15 %
    assert [(n, h, t) for n, h, t, _ in enviados] == [
        (1, "13:00", "Restauro una silla (Parte 1)"),
        (2, "18:00", "Restauro una silla (Parte 2)"),
        (3, "21:30", "Restauro una silla (Parte 3)")]
    assert db.hay_trabajo_pesado(conn) is None and m._serie_estado(conn, "0a1b2c") is None
