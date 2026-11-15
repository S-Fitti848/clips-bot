"""Costo de Claude al elegir fotos (Santi, 2026-11-15): primer filtro con Haiku, caché de lo ya
evaluado y el informe separado por origen (producción, a mano, pruebas)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from clips_bot import claude, db, efemerides as ef, gemini
from clips_bot.config import load_settings


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    yield c
    c.close()


def _foto(tmp_path: Path, n: int) -> ef.Foto:
    from PIL import Image

    ruta = tmp_path / f"f{n}.jpg"
    Image.new("RGB", (64, 48), ((n * 13) % 255, (n * 29) % 255, 120)).save(ruta)
    return ef.Foto(archivo=f"File:{n}.jpg", url="", ancho=1280, alto=960, licencia="CC0", autor="x",
                   epigrafe=f"foto {n}", pagina="", articulo="Commons: algo", ruta=str(ruta))


class _Haiku:
    """Describe las fotos y, en el pedido de texto, pone primero las de número par."""

    def __init__(self):
        self.pedidos = []

    def json(self, sistema, prompt, schema, *a, imagenes=None, **k):
        self.pedidos.append((sistema, len(imagenes or [])))
        if sistema == ef.SISTEMA_DESCRIBIR:
            return json.dumps({"fotos": [{"foto": j, "se_ve": f"cosa {j}", "tipo": "foto",
                                          "otro_idioma": False, "dura": j == 3}
                                         for j in range(1, len(imagenes) + 1)]})
        return json.dumps({"frases": [{"fotos": [20, 18, 16, 14, 12]}, {"fotos": [3, 5, 7, 9]}]})


class _Sonnet:
    def __init__(self, haiku):
        self.prefiltro = haiku
        self.vio = []

    def json(self, sistema, prompt, schema, *a, imagenes=None, **k):
        self.vio.append(len(imagenes))
        return json.dumps({"frases": [{"se_ve": "x", "fotos": [len(imagenes) - 1, len(imagenes)], "de_epoca": True, "seguro": True,
                                       "contradice": False, "escena": False},
                                      {"se_ve": "y", "fotos": [1], "de_epoca": True,
                                       "seguro": True, "contradice": False, "escena": False}],
                           "descartadas": [], "tipos": [], "impactantes": []})


def test_sonnet_mira_solo_las_mejores_de_cada_frase(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "CACHE_DESCRIPCIONES", tmp_path / "desc")
    monkeypatch.setattr(ef, "PREFILTRO_POR_FRASE", 3)
    pool = [_foto(tmp_path, n) for n in range(20)]
    g = ef.Guion(fotos=[], descartadas=[], descripcion="d", hashtags=[], titulo="t", frases=["Una frase.", "Otra frase."], mostrar=["a 1907", "b 1907"],
                 presente=[False, False])
    haiku = _Haiku()
    sonnet = _Sonnet(haiku)
    cands = [list(range(10, 20)), list(range(0, 10))]
    rankings, _ = ef.elegir_fotos(None, g, pool, cands, avisar=lambda *_: None, anio=1907, elector=sonnet)
    # frase 1: 4 (la del gancho tiene una más), frase 2: 3, y la foto 2 (dura) nunca pasa
    assert sonnet.vio == [7]
    # los índices vuelven a los del pool entero
    assert rankings == [[17, 19], [4]]
    # la segunda vez, las descripciones salen de la caché: Haiku no vuelve a ver ninguna imagen
    haiku.pedidos.clear()
    ef.elegir_fotos(None, g, pool, cands, avisar=lambda *_: None, anio=1907, elector=sonnet)
    assert all(n == 0 for _, n in haiku.pedidos)


def test_si_el_filtro_falla_sonnet_mira_todas(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "CACHE_DESCRIPCIONES", tmp_path / "desc")

    class Roto:
        def json(self, *a, **k):
            raise RuntimeError("caído")

    pool = [_foto(tmp_path, n) for n in range(20)]
    g = ef.Guion(fotos=[], descartadas=[], descripcion="d", hashtags=[], titulo="t", frases=["Una.", "Otra."], mostrar=["a", "b"], presente=[False, False])
    sonnet = _Sonnet(Roto())
    ef.elegir_fotos(None, g, pool, [list(range(10, 20)), list(range(10))], avisar=lambda *_: None,
                    elector=sonnet)
    assert sonnet.vio == [20]


def test_cache_de_claude_solo_con_imagenes(tmp_path):
    class Uso:
        input_tokens, output_tokens = 1000, 500

    class R:
        usage, stop_reason, model = Uso(), "end_turn", claude.SONNET
        content = [type("B", (), {"type": "text", "text": '{"ok": true}'})()]

    llamadas = []

    class Api:
        class beta:
            class messages:
                @staticmethod
                def create(**k):
                    llamadas.append(k)
                    return R()

        messages = beta.messages

    c = claude.ClaudeClient("x", cliente=Api(), cache_dir=tmp_path / "cc")
    schema = {"type": "OBJECT", "properties": {"ok": {"type": "BOOLEAN"}}}
    c.json("s", "p", schema, imagenes=[b"\xff\xd8una"])
    c.json("s", "p", schema, imagenes=[b"\xff\xd8una"])     # la misma foto: no se paga de nuevo
    c.json("s", "p", schema, imagenes=[b"\xff\xd8otra"])
    c.json("s", "p", schema)
    c.json("s", "p", schema)                                  # sin imágenes no hay caché
    assert len(llamadas) == 4


def test_informe_separa_produccion_de_lo_hecho_a_mano(conn, monkeypatch):
    import clips_bot.__main__ as m

    for origen, ent in (("produccion", 10000), ("a_mano", 20000), ("prueba", 30000)):
        db.anotar_gemini(conn, "efemerides.pedir", claude.SONNET, "claude", ent, 1000, origen=origen)
    dia = conn.execute("SELECT dia FROM gemini_uso LIMIT 1").fetchone()[0]
    prod, _ = claude.resumen_costo(conn, dia, "produccion")
    assert prod == pytest.approx(0.03)
    texto = claude.texto_costo(conn, dia)
    assert "Producción</b>: US$ 0.03" in texto and "A mano por Telegram" in texto and "Pruebas" in texto

    # el tick de la escucha va como producción; el resto de la escucha, a mano
    vistos = []
    monkeypatch.setattr(gemini, "ORIGEN", gemini.A_MANO)
    m._auto(lambda: vistos.append(gemini.ORIGEN))()
    assert vistos == ["produccion"] and gemini.ORIGEN == gemini.A_MANO


def test_informe_diario_de_ayer_desde_las_9(conn):
    import clips_bot.__main__ as m

    conn.execute("INSERT INTO gemini_uso (ts, dia, funcion, modelo, clave, entrada, salida, cache, origen) "
                 "VALUES ('x', '2026-11-14', 'efemerides.pedir', 'claude-sonnet-5-5', 'claude', 1000, 100, 0,"
                 " 'produccion')")
    conn.commit()

    class TG:
        m = []

        def send_message(self, chat, texto, **k):
            self.m.append(texto)

    tg = TG()
    m._costo_claude_tick(conn, tg, load_settings(), ahora=datetime(2026, 11, 15, 8, 0, tzinfo=m.AR))
    assert tg.m == []
    m._costo_claude_tick(conn, tg, load_settings(), ahora=datetime(2026, 11, 15, 9, 5, tzinfo=m.AR))
    m._costo_claude_tick(conn, tg, load_settings(), ahora=datetime(2026, 11, 15, 12, 0, tzinfo=m.AR))
    assert len(tg.m) == 1 and "14/11" in tg.m[0]


def test_videos_quedan_los_2_mejores_por_frase(tmp_path, monkeypatch):
    monkeypatch.setattr(ef, "CACHE_DESCRIPCIONES", tmp_path / "desc")
    monkeypatch.setattr(ef, "VIDEOS_POR_FRASE", 2)
    from PIL import Image

    vids = []
    for k in range(4):
        fr = tmp_path / f"v{k}.jpg"
        Image.new("RGB", (32, 24), (k * 50, 10, 10)).save(fr)
        vids.append(type("V", (), {"frames": [str(fr)] * 3, "titulo": f"video {k}", "de_archivo": k == 3,
                                   "etiqueta": lambda self: "Pexels"})())

    class H(_Haiku):
        def json(self, sistema, prompt, schema, *a, imagenes=None, **k):
            if sistema == ef.SISTEMA_DESCRIBIR:
                return super().json(sistema, prompt, schema, imagenes=imagenes)
            assert "frase 1, V4" in prompt
            return json.dumps({"frases": [{"fotos": [], "videos": [4, 2]}, {"fotos": [], "videos": []}]})

    videos = {0: list(vids)}
    pool = [_foto(tmp_path, n) for n in range(20)]
    ef.prefiltrar_fotos(H(), ["frase 1", "frase 2"], pool, [b"x%d" % n for n in range(20)],
                        [list(range(10)), list(range(10, 20))], None, 1950, lambda *_: None, videos=videos)
    assert [v.titulo for v in videos[0]] == ["video 3", "video 1"]


def test_aviso_de_presupuesto_del_mes(conn):
    import clips_bot.__main__ as m

    class TG:
        m = []

        def send_message(self, chat, texto, **k):
            self.m.append(texto)

    tg = TG()
    db.anotar_gemini(conn, "marcas.escribir_guion", claude.SONNET, "claude", 1_000_000, 5_500_000, origen="produccion")
    dia = conn.execute("SELECT dia FROM gemini_uso LIMIT 1").fetchone()[0]
    assert claude.costo_mes(conn, dia[:7]) == pytest.approx(57.0)
    ahora = datetime.fromisoformat(dia + "T08:00").replace(tzinfo=m.AR)
    m._costo_claude_tick(conn, tg, load_settings(), ahora=ahora)
    m._costo_claude_tick(conn, tg, load_settings(), ahora=ahora)
    assert len(tg.m) == 0                                     # 57 < 60 (75 % de 80)
    db.anotar_gemini(conn, "marcas.escribir_guion", claude.SONNET, "claude", 0, 400_000, origen="produccion")
    m._costo_claude_tick(conn, tg, load_settings(), ahora=ahora)
    m._costo_claude_tick(conn, tg, load_settings(), ahora=ahora)
    assert len(tg.m) == 1 and "75%" in tg.m[0] and "US$ 61.00" in tg.m[0]


def test_respuesta_cortada_reintenta_con_mas_limite(tmp_path):
    class Uso:
        input_tokens, output_tokens = 100, 50

    def resp(stop):
        return type("R", (), {"usage": Uso(), "stop_reason": stop, "model": claude.SONNET,
                              "content": [type("B", (), {"type": "text", "text": '{"ok": true}'})()]})()

    pedidos = []

    class Api:
        class beta:
            class messages:
                @staticmethod
                def create(**k):
                    pedidos.append(k["max_tokens"])
                    return resp("max_tokens")

                @staticmethod
                def stream(**k):
                    pedidos.append(k["max_tokens"])

                    class S:
                        def __enter__(self):
                            return self

                        def __exit__(self, *a):
                            return False

                        def get_final_message(self):
                            return resp("end_turn")
                    return S()

    c = claude.ClaudeClient("x", cliente=Api(), max_tokens=16000)
    assert c.json("s", "p", {"type": "OBJECT", "properties": {}}) == '{"ok": true}'
    assert pedidos == [16000, 32000]                          # el segundo, con el doble (y por streaming)
