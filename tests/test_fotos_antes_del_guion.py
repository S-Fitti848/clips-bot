"""Santi, 2026-11-23 (el Mundial 96 de la reserva: 6/9, US$ 0,61): fotos contadas antes del guion, historias que
fallaron por fotos marcadas, la reserva con marcas y videojuegos primero, el plan B de la frase sin foto antes que
la tarjeta (máximo 2), y las tarjetas con un número justo cuando la voz lo dice."""
from __future__ import annotations

import inspect
import sqlite3
from types import SimpleNamespace

from clips_bot import banco, calidad, db, reserva_tec
from clips_bot import efemerides as ef


def _conn():
    conn = sqlite3.connect(":memory:")
    db.init(conn) if hasattr(db, "init") else conn.execute(
        "create table if not exists bot_estado (clave text primary key, valor text)")
    return conn


def _g(**k):
    base = dict(titulo="t", descripcion="d", hashtags=[], frases=["a"], fotos=[0], descartadas=[])
    base.update(k)
    return ef.Guion(**base)


def _tarjeta(texto):
    return {"archivo": f"tarjeta:{texto}", "articulo": "tarjeta", "epigrafe": f"tarjeta: {texto}"}


def _foto(n):
    return {"archivo": f"File:{n}.jpg", "articulo": "A", "epigrafe": n}


def _w(texto, t):
    return SimpleNamespace(texto=texto, inicio=t, fin=t + 0.3)


# ---- 1. fotos antes del guion ----------------------------------------------------------------------------------

def test_fotos_previas_cuenta_articulo_y_commons_sin_repetir(monkeypatch):
    e = ef.Evento("es", 1996, "Nintendo lanza Pokémon", ["Pokémon"])
    art = [ef.Foto(archivo="Archivo:A.jpg", url="", ancho=900, alto=600, licencia="CC0", autor="x",
                   epigrafe="", pagina="", articulo="Pokémon")]
    wiki = SimpleNamespace(buscar_commons=lambda q, cuantas=12: [{"archivo": "File:A.jpg"}, {"archivo": "File:B.jpg"}])
    monkeypatch.setattr(ef, "filtrar_infos", lambda w, l, infos, a, anio: (
        [ef.Foto(archivo=i["archivo"], url="", ancho=900, alto=600, licencia="CC0", autor="x", epigrafe="",
                 pagina="", articulo=a) for i in infos], {}))
    assert ef.fotos_previas(wiki, e, art) == 2         # A está en los dos: cuenta una vez


def test_el_chequeo_previo_va_antes_del_guion_y_no_cuenta_como_guion():
    src = inspect.getsource(ef.proponer)
    assert src.index("fotos_previas(wiki, e, fotos)") < src.index("escribir_guion(")
    assert src.index("previas < PRECHEQUEO_MIN") < src.index("guiones += 1")


# ---- 2. historias marcadas sin fotos -----------------------------------------------------------------------------

def test_marcar_sin_fotos_saca_del_banco_y_no_vuelve_a_entrar():
    conn = _conn()
    banco.guardar(conn, "tecnologia", [{"id": "tec:Pokémon", "articulo": "Pokémon", "puntaje": 8.5},
                                       {"id": "tec:Wii", "articulo": "Wii", "puntaje": 8.5}])
    banco.marcar_sin_fotos(conn, "tecnologia", "Pokémon", "solo 61 %")
    assert [x["id"] for x in banco.leer(conn, "tecnologia")] == ["tec:Wii"]
    assert "pokemon" in banco.sin_fotos(conn, "tecnologia")
    assert banco.agregar(conn, "tecnologia", [{"id": "tec:Pokémon", "articulo": "Pokémon", "puntaje": 9}]) == 0


def test_proponer_saltea_los_marcados_y_anota_los_que_fallan():
    src = inspect.getsource(ef.proponer)
    assert "_norm_art(articulo) in {_norm_art(x) for x in sin_fotos" in src
    assert src.count("al_fallar_fotos(articulo") >= 3     # chequeo previo, PocasFotos y fotos insuficientes
    assert ef._norm_art("AlphaGo_versus_Lee_Sedol") == ef._norm_art("AlphaGo versus Lee Sedol")


# ---- 3. la reserva: marcas y videojuegos primero, y la pausa ------------------------------------------------------

def test_reserva_ordena_marcas_y_videojuegos_antes_que_inventos():
    src = inspect.getsource(ef.proponer)
    assert "SUBTEMAS_FACILES" in src and "key=clave_banco" in src
    assert set(ef.SUBTEMAS_FACILES) == {"marcas", "empresas", "videojuegos"}


def test_la_reserva_pausada_no_arma():
    conn = _conn()
    assert reserva_tec.hay_que_armar(conn, 3, __import__("datetime").date(2026, 11, 24), "10:00")
    db.set_valor(conn, reserva_tec.PAUSA, "1")
    assert not reserva_tec.hay_que_armar(conn, 3, __import__("datetime").date(2026, 11, 24), "10:00")


# ---- 4. plan B antes que la tarjeta, como mucho 2 tarjetas ---------------------------------------------------------

def test_frases_flojas_son_las_sin_foto_real():
    pool = [ef.Foto.de_dict({**_foto("x"), "url": "", "ancho": 1, "alto": 1, "licencia": "", "autor": "",
                             "pagina": ""}),
            ef.Foto.de_dict({**_tarjeta("1876"), "url": "", "ancho": 1, "alto": 1, "licencia": "", "autor": "",
                             "pagina": ""})]
    g = _g(frases=["a", "b", "c"], fotos=[0, 1, 0], ranking=[[0], [1], []])
    assert ef.frases_flojas(g, pool) == [1, 2]


def test_fotos_con_control_reescribe_antes_de_rendirse(monkeypatch, tmp_path):
    llamadas = []

    def fpg(*a, **k):
        llamadas.append(k)
        if len(llamadas) < 3:
            pool = [ef.Foto(archivo="File:x.jpg", url="", ancho=900, alto=600, licencia="CC0", autor="a",
                            epigrafe="x", pagina="", articulo="A")]
            raise ef.FotosInsuficientes(pool, _g(frases=["a", "b"], ranking=[[0], []]), 0.55)
        return [], _g()

    monkeypatch.setattr(ef, "fotos_para_guion", fpg)
    pedidas = []

    def reescribir(g, idx, pool, forz=None):
        pedidas.append(idx)
        forz[1] = 0
        return True

    ef.fotos_con_control(object(), None, ef.Evento("es", 1, "x", ["x"]), _g(), [], tmp_path, lambda *_: None,
                         reescribir=reescribir)
    assert pedidas == [[1]] and llamadas[-1]["forzadas"] == {1: 0}


def test_como_mucho_2_tarjetas(tmp_path):
    from PIL import Image

    r = tmp_path / "b.jpg"
    Image.new("RGB", (900, 600), (90, 90, 90)).save(r)
    pool = [ef.Foto(archivo="b.jpg", url="", ancho=900, alto=600, licencia="CC0", autor="a", epigrafe="b",
                    pagina="", articulo="A", ruta=str(r))]
    g = _g(frases=["el acta", "el sello", "la firma"], fotos=[0, 0, 0], ranking=[[0], [0], [0]],
           claves=["acta", "sello", "firma"])
    nueva = ef.fabrica_tarjetas(g, 1811, tmp_path, lambda k: pool[k], lambda f: (pool.append(f), len(pool) - 1)[1])
    assert nueva(0) is not None and nueva(1) is not None
    assert nueva(2) is None


def test_las_tarjetas_del_armado_no_se_juzgan_como_foto():
    src = inspect.getsource(calidad.revisar_y_reemplazar)
    assert 'enumerate(cortes) if str(c.get("archivo") or "").startswith("tarjeta")' in src


# ---- 5. tarjetas con un número, cuando la voz lo dice ---------------------------------------------------------------

def test_el_anio_solo_si_la_frase_lo_dice():
    g = _g(frases=["En 1854 Meucci lo probó.", "Bell lo patentó."], fotos=[0, 0])
    assert ef.texto_tarjeta(g, 0, 1854) == "1854"
    assert ef.texto_tarjeta(g, 1, 1876) is None         # «1876» mientras la voz decía otra cosa: nunca más


def test_meucci_la_tarjeta_se_corre_a_cuando_la_voz_dice_el_numero():
    fotos = [_foto("meucci"), _foto("bell"), _tarjeta("1876")]
    plan = [(0, 0, 3.0), (1, 2, 3.0), (2, 1, 3.0)]        # la tarjeta 1876 de 3 a 6 s
    palabras = [_w("En", 3.0), _w("1854", 3.3), _w("Bell", 6.0), _w("en", 6.5), _w("1876", 7.0)]
    assert ef.tarjetas_a_destiempo(plan, fotos, palabras) == [1]
    plan2, movs = ef.alinear_tarjetas(list(plan), None, fotos, palabras, lambda *_: None)
    assert ef.tarjetas_a_destiempo(plan2, fotos, palabras) == []
    t = 0.0
    for _i, f, s in plan2:
        if f == 2:
            assert abs(t - 7.0) < 0.01                   # entra justo cuando dice 1876
        t += s
    assert abs(sum(s for *_, s in plan2) - 9.0) < 0.01    # el largo no cambia


def test_una_tarjeta_con_un_numero_que_la_voz_no_dice_vuelve_a_la_foto():
    fotos = [_foto("a"), _tarjeta("1999")]
    plan = [(0, 0, 2.0), (0, 1, 2.0)]
    plan2, _ = ef.alinear_tarjetas(list(plan), None, fotos, [_w("hola", 0.1)], lambda *_: None)
    assert all(f == 0 for _, f, _ in plan2)


def test_tarjeta_a_tiempo_no_se_toca():
    fotos = [_foto("a"), _tarjeta("1876")]
    plan = [(0, 0, 2.0), (0, 1, 2.0)]
    palabras = [_w("1876", 2.05)]
    assert ef.tarjetas_a_destiempo(plan, fotos, palabras) == []


def test_la_revision_final_controla_las_tarjetas_sin_claude():
    src = inspect.getsource(ef.hacer_video)
    assert "alinear_tarjetas(plan, movimientos, p.fotos, palabras" in src
    assert '"PH-26"' in src
    assert "PH-26" in {r.id for r in calidad.reglas("pequena_historia")}


# ---- fuentes ------------------------------------------------------------------------------------------------------

def test_flickr_y_el_resto_sin_el_user_agent_de_wikimedia():
    from clips_bot import config, fuentes_fotos

    assert "@" not in config.user_agent_corto() and "(" not in config.user_agent_corto()
    src = inspect.getsource(fuentes_fotos.bajar)
    assert 'endswith("wikimedia.org") else user_agent_corto()' in src
    assert '("archive", self.archive)' in inspect.getsource(fuentes_fotos.BUSCAR_REAL)


def test_informe_del_dia_siguiente(tmp_path):
    import json
    from datetime import date

    conn = sqlite3.connect(":memory:")
    conn.execute("create table videos_registro (dia text, formato text, estado text, costo_usd real)")
    conn.executemany("insert into videos_registro values ('2026-11-24','tecnologia_reserva',?,?)",
                     [("reserva", 0.30), ("descartado", 0.10)])
    d = tmp_path / "efemerides" / "reserva_x"
    d.mkdir(parents=True)
    (d / "efemeride_1124_1990.json").write_text(json.dumps({"efemeride": {"cortes": [
        {"dur": 8, "archivo": "File:a.jpg"}, {"dur": 2, "archivo": "tarjeta:x"}]}}), encoding="utf-8")
    t = reserva_tec.informe(conn, date(2026, 11, 24), tmp_path)
    assert len(t.splitlines()) == 3
    assert "80 %" in t and "2 intentos, 1 entraron, US$ 0,40" in t
