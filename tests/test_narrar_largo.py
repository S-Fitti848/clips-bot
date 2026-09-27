"""/narrar con videos de más de 90 s: escenas, pasos, ventanas del resumen y el crédito `cc:`.

Sin red ni video: Gemini es un fake y ffmpeg no corre (eso se probó a mano, ver CLAUDE.md §8).
"""

import json

import pytest

import clips_bot.__main__ as m
from clips_bot import db, narrar
from clips_bot.telegram import sacar_cc
from clips_bot.textos import con_credito, credito, credito_cc


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


# ---- escenas ----------------------------------------------------------------------

def test_escenas_son_contiguas_y_cubren_todo():
    esc = narrar.escenas([10, 25, 40, 70, 100], 120)
    assert esc[0][0] == 0 and esc[-1][1] == 120
    assert all(a[1] == b[0] for a, b in zip(esc, esc[1:]))


def test_las_escenas_muy_cortas_se_funden():
    esc = narrar.escenas([10, 10.3, 10.6, 50], 120, minimo=1)
    assert all(b - a >= narrar.ESCENA_MIN_S for a, b in esc)


def test_un_video_muy_editado_se_achica_al_maximo():
    cortes = [i * 1.5 for i in range(1, 200)]          # un corte cada 1,5 s en 300 s
    esc = narrar.escenas(cortes, 300)
    assert len(esc) == narrar.ESCENAS_MAX
    assert esc[0][0] == 0 and esc[-1][1] == 300


def test_un_plano_secuencia_se_parte_hasta_el_minimo():
    esc = narrar.escenas([], 180)                       # ningún corte
    assert len(esc) == narrar.ESCENAS_MIN
    assert all(a[1] == b[0] for a, b in zip(esc, esc[1:]))


# ---- pasos ------------------------------------------------------------------------

def _pasos(nums):
    return {"pasos": [{"escena": n, "descripcion": f"paso {n}"} for n in nums], "sensible": False}


def test_validar_pasos():
    assert narrar.validar_pasos(_pasos(range(1, 9)), 20) == []
    assert "entre 8 y 10" in narrar.validar_pasos(_pasos(range(1, 6)), 20)[0]
    assert "orden" in narrar.validar_pasos(_pasos([1, 3, 2, 4, 5, 6, 7, 8]), 20)[0]
    assert "del 1 al 20" in narrar.validar_pasos(_pasos(range(15, 23)), 20)[0]
    # con menos escenas que el mínimo, alcanza con todas
    assert narrar.validar_pasos(_pasos(range(1, 6)), 5) == []


class FakeGemini:
    def __init__(self, respuestas):
        self.respuestas, self.prompts = list(respuestas), []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None):
        self.prompts.append(prompt)
        return json.dumps(self.respuestas.pop(0))


def test_elegir_pasos_reintenta_con_los_errores():
    esc = [(i * 10.0, i * 10.0 + 10) for i in range(20)]
    g = FakeGemini([_pasos([1, 2, 3]), _pasos([1, 4, 7, 9, 12, 15, 18, 20])])
    pasos, sensible = narrar.elegir_pasos(g, esc, [b""] * 20)
    assert [p.escena for p in pasos] == [0, 3, 6, 8, 11, 14, 17, 19]   # índices desde 0
    assert "entre 8 y 10" in g.prompts[1] and not sensible


def test_elegir_pasos_con_correccion_menciona_la_eleccion_anterior():
    esc = [(i * 10.0, i * 10.0 + 10) for i in range(20)]
    g = FakeGemini([_pasos(range(1, 9))])
    antes = [narrar.Paso(i, "x") for i in (0, 2, 4)]
    narrar.elegir_pasos(g, esc, [], correccion="sacá el 2", anteriores=antes)
    assert "escenas 1, 3, 5" in g.prompts[0] and "sacá el 2" in g.prompts[0]


def test_si_nunca_valida_avisa():
    esc = [(i * 10.0, i * 10.0 + 10) for i in range(20)]
    with pytest.raises(narrar.NarrarError):
        narrar.elegir_pasos(FakeGemini([_pasos([1]), _pasos([1])]), esc, [])


@pytest.mark.parametrize("n", [8, 9, 10])
def test_el_resumen_dura_entre_40_y_55_s(n):
    esc = [(i * 12.0, i * 12.0 + 12) for i in range(25)]
    pasos = [narrar.Paso(i * 2, "x") for i in range(n)]
    tramos = narrar.ventanas(esc, pasos, 300)
    total = sum(b - a for a, b in tramos)
    assert 40 <= total <= 55
    assert all(4 <= b - a <= 5 for a, b in tramos)
    assert all(x[1] <= y[0] for x, y in zip(tramos, tramos[1:]))      # en orden y sin pisarse


def test_las_ventanas_no_se_salen_del_video():
    esc = [(0.0, 1.5), (1.5, 3.0), (296.0, 300.0)]
    tramos = narrar.ventanas(esc, [narrar.Paso(0, "a"), narrar.Paso(1, "b"), narrar.Paso(2, "c")],
                             300)
    assert tramos[0][0] >= 0 and tramos[-1][1] <= 300
    assert all(x[1] <= y[0] for x, y in zip(tramos, tramos[1:]))


def test_texto_una_linea_por_paso_con_el_minuto():
    pasos = [narrar.Paso(0, "arranca <con> la madera"), narrar.Paso(1, "la lija")]
    txt = narrar.texto_pasos(pasos, [(5.0, 10.0), (75.0, 80.0)], 200)
    assert "1. <i>0:05</i> arranca &lt;con&gt; la madera" in txt
    assert "2. <i>1:15</i> la lija" in txt


# ---- crédito cc -------------------------------------------------------------------

@pytest.mark.parametrize("args,resto,cc", [
    (["https://a", "cc:", "https://b"], ["https://a"], "https://b"),
    (["cc:https://b", "https://a"], ["https://a"], "https://b"),
    (["CC:", "https://b"], [], "https://b"),
    (["https://a"], ["https://a"], None),
])
def test_sacar_cc(args, resto, cc):
    assert sacar_cc(args) == (resto, cc)


def test_credito_cc_con_el_formato_pedido():
    assert credito_cc("Canal Tal", "https://youtu.be/x") == \
        "Video original: Canal Tal – https://youtu.be/x, licencia CC BY"


def test_un_video_propio_ya_no_sale_con_twitch_pelado():
    assert "twitch.tv" not in credito("Alguien", "")
    assert credito("Coscu", "coscu") == "Clip de Coscu — twitch.tv/coscu"


def test_con_credito_reemplaza_la_ultima_linea_de_la_descripcion():
    t = {"descripcion": "Una caída épica.\n\nVideo original: X – (completar link)",
         "credito": "Video original: X – (completar link)"}
    nuevo = con_credito(t, credito_cc("X", "https://y"))
    assert nuevo["descripcion"] == "Una caída épica.\n\nVideo original: X – https://y, licencia CC BY"
    assert nuevo["credito"].endswith("licencia CC BY")


def test_aplicar_cc_avisa_si_la_licencia_no_es_cc(monkeypatch):
    from clips_bot import download

    monkeypatch.setattr(download, "info_cc",
                        lambda link: {"canal": "El Canal", "licencia": "Standard YouTube License"})
    meta = {"textos": {"descripcion": "hola\n\nVideo original: ? – (completar link)",
                       "credito": "Video original: ? – (completar link)"}}

    class D:
        url, canal = "", ""

    aviso = m._aplicar_cc(meta, "https://youtu.be/x", D())
    assert "Standard YouTube License" in aviso
    assert meta["textos"]["credito"] == "Video original: El Canal – https://youtu.be/x, licencia CC BY"
    assert meta["cc"]["licencia"] == "Standard YouTube License"


# ---- el flujo --------------------------------------------------------------------

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


def test_cc_solo_queda_guardado_hasta_que_llega_el_video(conn):
    r = m._editar(conn, FakeTG(), "1", "7", ["cc:", "https://youtu.be/x"], None, "narrar")
    assert "Mandame el video" in r
    assert db.get_valor(conn, f"{m.ESPERA_CC}:7") == "https://youtu.be/x"
    assert db.get_valor(conn, f"{m.ESPERA_VIDEO}:7") == "narrar"


def test_proponer_pasos_manda_la_hoja_y_los_botones(conn, monkeypatch, tmp_path):
    from clips_bot import process

    monkeypatch.setattr(process, "WORK_DIR", tmp_path)
    monkeypatch.setattr(m, "_gemini", lambda s: FakeGemini([_pasos(range(1, 9))]))
    monkeypatch.setattr(narrar, "cortes_de_escena", lambda v: [])
    monkeypatch.setattr(narrar, "frames_en", lambda v, ts: [b"jpg"] * len(ts))
    monkeypatch.setattr(narrar, "hoja_de_pasos", lambda imgs, salida: salida)
    tg = FakeTG()
    estado = {"raw": "x.mp4", "url": "", "canal": "", "titulo": "", "duracion": 240.0,
              "cc": "https://y", "chat_id": "1", "user_id": "7"}
    assert m._proponer_pasos(conn, tg, "1", estado, None) is None
    assert len(tg.fotos) == 1
    texto, teclado = tg.mensajes[-1]
    assert texto.count("\n") >= 8 and "Resumen en 8 pasos" in texto
    datos = [b["callback_data"] for b in teclado["inline_keyboard"][0]]
    assert datos[0].startswith("pas:ok:") and datos[1].startswith("pas:no:")
    guardado = json.loads(db.get_valor(conn, "pasos:" + datos[0].split(":")[2]))
    assert guardado["cc"] == "https://y" and len(guardado["tramos"]) == 8


def test_aprobar_con_el_turno_ocupado_no_pierde_los_pasos(conn):
    db.set_valor(conn, "pasos:ab", json.dumps({"raw": "x.mp4", "tramos": [[0, 5]]}))
    db.tomar_turno(conn, db.RECURSO_PESADO, "diario:1", maximo=1)
    tg = FakeTG()
    m._pasos_callback(conn, tg, {"data": "pas:ok:ab", "chat_id": "1", "message_id": 3,
                                 "callback_id": "q", "user_id": "7"}, None)
    assert "en un rato" in tg.respuestas[-1]
    assert db.get_valor(conn, "pasos:ab")          # sigue ahí: el mismo ✅ sirve después


def test_cambiar_deja_esperando_la_correccion(conn):
    db.set_valor(conn, "pasos:ab", json.dumps({"raw": "x.mp4"}))
    m._pasos_callback(conn, FakeTG(), {"data": "pas:no:ab", "chat_id": "1", "message_id": 3,
                                       "callback_id": "q", "user_id": "7"}, None)
    assert db.get_valor(conn, f"{m.ESPERA_PASOS}:7") == "ab"
