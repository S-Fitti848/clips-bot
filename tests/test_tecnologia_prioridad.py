"""Tecnología, prioridad número uno (Santi, 2026-11-23: ~10.000 vistas por video en YouTube): 2 por día, una reserva de 3
videos ya armados, el presupuesto primero para tecnología, YouTube solo de tecnología, los temas que rinden primero y,
en Facebook, fútbol, ídolos y curiosidades antes que próceres."""
import dataclasses
import json
from datetime import date, datetime

import clips_bot.__main__ as m
from clips_bot import aviso_corto, db, locales, reserva_tec, temas
from clips_bot import presupuesto as pr
from clips_bot.config import load_settings


def _conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def _settings(**efe):
    s = load_settings()
    return dataclasses.replace(s, efemerides=dataclasses.replace(s.efemerides, **efe))


def test_config_youtube_solo_tecnologia_dos_por_dia():
    s = load_settings()
    assert not s.historias_fb.youtube                  # Latinoamérica solo en Facebook hasta el 15/12
    assert s.efemerides.tema == "tecnologia" and s.efemerides.por_dia == 2 and s.efemerides.reserva == 3
    assert list(s.efemerides.horas_youtube) == ["11:00", "20:00"]


def test_el_mensaje_corto_dice_cual_es():
    assert aviso_corto.resumen(8, 9, 0.3, "11:00", etiqueta="💻 Tecnología").startswith("💻 Tecnología · ✅ 8/9")


def test_subtemas_y_grupos():
    assert temas.subtema_tec("Half-Life 2: el juego filtrado que ganó 39 premios") == "videojuegos"
    assert temas.subtema_tec("¡El nacimiento de la World Wide Web!") == "internet"
    assert temas.subtema_tec("El procesador barato de Intel que salió mal") == "marcas"
    assert temas.subtema_tec("Inventó el ratón y casi no ganó nada") == "inventos"
    assert temas.grupo_latam("momento_emotivo", "Santa Fe: Colón campeón tras 116 años de espera") == "futbol"
    assert temas.grupo_latam("heroe_de_pueblo", "Aquiles Serdán: la revuelta que se adelantó en Puebla") == "procer"
    assert temas.grupo_latam("fundacion", "Banfield: la ciudad que nació de un tren") == "procer"
    assert temas.grupo_latam("idolo", "Pedro Infante") == "idolo"


def test_los_pesos_suben_lo_que_rinde(tmp_path):
    c = _conn(tmp_path)
    yt = {f"v{k}": {"tipo": "tecnologia", "titulo": t, "vistas": v} for k, (t, v) in enumerate([
        ("El chip de Intel", 24000), ("El procesador de Intel", 14000), ("La consola más débil", 2700),
        ("Half-Life 2", 2600), ("La World Wide Web", 600), ("ARPANET", 400)])}
    db.set_valor(c, "ph_medicion", json.dumps({"fb": {}, "yt": yt}))
    p = temas.calcular(c)
    assert p["tec"]["marcas"] > 0 > p["tec"]["internet"]
    assert p["latam"]["futbol"] > p["latam"]["humana"] > p["latam"]["procer"]     # lo que pidió Santi, aun sin datos
    assert "Tecnología" in temas.texto_semana(p) and len(temas.texto_semana(p).splitlines()) <= 3


def test_futbol_antes_que_proceres_aunque_sean_del_calendario():
    def cand(tipo, texto, seccion="acontecimientos"):
        c = locales.Candidato(seccion, 1900, texto, ["A"])
        c.clasif = {"humana": True, "lugar": "X", "pais": "México", "tipo": tipo, "interes": 7}
        return c

    procer = cand("procer", "Batalla de la independencia", seccion="celebracion")
    futbol = cand("futbol", "Colón campeón")
    humana = cand("gente_comun", "Una maestra")
    assert locales.buenos([procer, humana, futbol]) == [futbol, humana, procer]


def test_presupuesto_tecnologia_nunca_se_recorta():
    hoy = date(2026, 11, 24)
    por = {f"2026-11-{d}": 2.0 for d in range(18, 24)}
    assert pr.nivel_necesario(12.0, por, hoy, 0)[0] == 0                       # 2/día × 21 días = 42 + 12 < 70
    por = {f"2026-11-{d}": 3.4 for d in range(18, 24)}
    n, _ = pr.nivel_necesario(20.4, por, hoy, 0)
    assert 1 <= n <= len(pr.RECORTES)
    assert all("ecnolog" not in t for _, t, _ in pr.RECORTES)
    # con Así Nació pausado, bajarlo no ahorra: hace falta un recorte más
    assert pr.nivel_necesario(20.4, por, hoy, 0, {1: False})[0] >= n
    # ya recortado: el promedio trae el ahorro, no vuelve atrás por eso solo
    por_rec = {f"2026-11-{d}": 3.4 - pr._ahorro(n) for d in range(18, 24)}
    assert pr.nivel_necesario(20.4, por_rec, hoy, n, niveles={d: n for d in por_rec})[0] == n


def test_el_recorte_frena_comunidad_y_latinoamerica(tmp_path):
    c = _conn(tmp_path)
    db.set_valor(c, pr.NIVEL, "4")
    llamadas = []
    m._fb_tick(c, None, load_settings(), ahora=datetime(2026, 11, 24, 6, 0, tzinfo=m.AR),
               proponer=lambda *a, **k: llamadas.append(1))
    assert llamadas == [] and m._web_latam(c, load_settings()) is None


def test_la_reserva_completa_el_dia_y_corta_los_reintentos(tmp_path, monkeypatch):
    c = _conn(tmp_path)
    hoy = date(2026, 11, 24)
    db.set_valor(c, m.EFE_DIA, hoy.isoformat())
    db.set_valor(c, m.EFE_REINTENTO, json.dumps({"fecha": hoy.isoformat(), "horas": ["07:00"]}))
    reserva_tec.guardar(c, [{"token": "a", "clip_id": "c1"}, {"token": "b", "clip_id": "c2"},
                            {"token": "z", "clip_id": "c3"}])
    mandados = []

    def entregar(conn, tg, chats, settings, item):
        mandados.append(item["clip_id"])
        reserva_tec.contar_entregado(conn, hoy)
        return True

    monkeypatch.setattr(m, "_entregar_de_reserva", entregar)
    m._tec_del_dia_tick(c, None, _settings(), ahora=datetime(2026, 11, 24, 5, 0, tzinfo=m.AR))
    assert mandados == ["c1", "c2"] and len(reserva_tec.leer(c)) == 1      # el del día falló: los 2 de la reserva
    assert db.get_valor(c, m.EFE_REINTENTO) is None
    m._tec_del_dia_tick(c, None, _settings(), ahora=datetime(2026, 11, 24, 6, 0, tzinfo=m.AR))
    assert mandados == ["c1", "c2"]                                         # ya están los 2 del día


def test_si_el_del_dia_salio_la_reserva_pone_solo_el_segundo(tmp_path, monkeypatch):
    c = _conn(tmp_path)
    hoy = date(2026, 11, 24)
    db.set_valor(c, m.EFE_DIA, hoy.isoformat())
    reserva_tec.contar_entregado(c, hoy)
    reserva_tec.guardar(c, [{"token": "a", "clip_id": "c1"}, {"token": "b", "clip_id": "c2"}])
    mandados = []
    monkeypatch.setattr(m, "_entregar_de_reserva",
                        lambda conn, tg, ch, s, it: (mandados.append(it["clip_id"]),
                                                     reserva_tec.contar_entregado(conn, hoy))[0] or True)
    m._tec_del_dia_tick(c, None, _settings(), ahora=datetime(2026, 11, 24, 5, 0, tzinfo=m.AR))
    assert mandados == ["c1"]


def test_la_reserva_se_repone_fuera_de_la_madrugada(tmp_path):
    c = _conn(tmp_path)
    from clips_bot import banco

    banco.guardar(c, "tecnologia", [{"id": "tec:X", "puntaje": 9, "texto": "x", "anio": 1990, "paginas": ["X"]}])
    armados = []
    s = _settings()
    m._reserva_tec_tick(c, None, s, ahora=datetime(2026, 11, 24, 4, 30, tzinfo=m.AR),
                        armar=lambda *a: armados.append(1))
    assert armados == []                                     # la madrugada es de los videos del día
    m._reserva_tec_tick(c, None, s, ahora=datetime(2026, 11, 24, 11, 0, tzinfo=m.AR),
                        armar=lambda *a: armados.append(1))
    assert armados == [1]
    reserva_tec.guardar(c, [{}, {}, {}])
    m._reserva_tec_tick(c, None, s, ahora=datetime(2026, 11, 24, 12, 0, tzinfo=m.AR),
                        armar=lambda *a: armados.append(1))
    assert armados == [1]                                    # con 3, no arma más


def test_quitar_del_banco_no_cuenta_como_uso(tmp_path):
    from clips_bot import banco

    c = _conn(tmp_path)
    banco.guardar(c, "tecnologia", [{"id": "tec:X"}, {"id": "tec:Y"}])
    banco.quitar(c, "tecnologia", "tec:X")
    assert [x["id"] for x in banco.leer(c, "tecnologia")] == ["tec:Y"]
    assert banco.usos_semana(c, date(2026, 11, 24))["tecnologia"] == 0


def test_dos_horarios_de_youtube():
    s = _settings()
    ahora = datetime(2026, 11, 24, 5, 0, tzinfo=m.AR)
    primero = m.hora_ph_youtube(s, [], ahora)
    assert primero.strftime("%H:%M") == "11:00"
    assert m.hora_ph_youtube(s, [primero], ahora).strftime("%H:%M") == "20:00"


# ---- 2026-11-23 (tarde): después del corte de luz ---------------------------------------------------------------

def test_un_turno_de_antes_del_arranque_no_cuenta(tmp_path, monkeypatch):
    import time

    c = _conn(tmp_path)
    db.set_valor(c, db._clave_turno(db.RECURSO_PESADO), json.dumps([["efemeride:reserva", time.time() - 600]]))
    monkeypatch.setattr(db, "arranque_sistema", lambda: time.time() - 60)
    assert db.hay_trabajo_pesado(c) is None
    monkeypatch.setattr(db, "arranque_sistema", lambda: time.time() - 6000)
    assert db.hay_trabajo_pesado(c) == "efemeride:reserva"


def test_los_logs_tapan_claves_y_tokens():
    from clips_bot import logseguro

    t = logseguro.tapar("400 for url: https://graph.facebook.com/v23.0/1?access_token=EAAWcWL520RABSZBVdYdGcb08P6tQ&x=1"
                        " /bot8824436710:AAHfake_token-123/getUpdates key=AIzaSyA1234567890123456789012345678901"
                        " sk-ant-api03-abcdef")
    for secreto in ("EAAWc", "AAHfake", "AIzaSy", "sk-ant-api03"):
        assert secreto not in t
    assert "access_token=***" in t and "/bot***" in t


def test_el_formateador_tapa_tambien_el_traceback():
    import logging

    from clips_bot import logseguro

    f = logseguro.Formateador(logging.Formatter("%(message)s"))
    try:
        raise ValueError("url?access_token=EAAabcdefghijklmnopqrstuvwxyz")
    except ValueError:
        import sys
        rec = logging.LogRecord("x", logging.INFO, "", 0, "falló %s", ("token=secreto123",), sys.exc_info())
    salida = f.format(rec)
    assert "secreto123" not in salida and "EAAabc" not in salida


def test_comunidad_usa_el_id_de_la_publicacion():
    from clips_bot import stats_fb

    pedidos = []

    class R:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    class S:
        def get(self, url, **k):
            pedidos.append(url)
            return R()

    stats_fb.metricas_post("122129360859498795", "t", "1406770815844323", "v23.0", session=S())
    assert pedidos[0].endswith("/1406770815844323_122129360859498795")


def test_marcas_primero_y_internet_solo_si_es_muy_fuerte():
    from clips_bot import efemerides as ef

    assert temas.BASE_TEC["marcas"] > temas.BASE_TEC["videojuegos"] > 0 > temas.BASE_TEC["internet"]
    assert ef.minimo_tec("internet") > ef.minimo_tec("marcas") == ef.PUNTAJE_TEC_MIN


def test_temas_ignora_los_muy_nuevos_y_usa_las_vistas_de_hoy():
    yt = {"a": {"tipo": "tecnologia", "titulo": "Así nació ARPANET", "vistas": 0, "publicado": "2026-11-21"},
          "b": {"tipo": "tecnologia", "titulo": "El primer navegador de la web", "vistas": 0, "publicado": "2026-11-23"}}
    v = temas.vistas_tec(yt, {"a": 1176}, date(2026, 11, 24))
    assert v == {"internet": [1176.0]}


def test_ninguna_marca_en_los_dos_canales_la_misma_semana(tmp_path):
    from clips_bot import marcas_semana as ms

    c = _conn(tmp_path)
    ms.anotar_ph(c, date(2026, 11, 20), "1971 Intel lanza el 4004 Intel_4004 El chip que su creador firmó")
    assert ms.usadas_ph(c, date(2026, 11, 24), ["Intel", "Nintendo", "Ford"]) == {"Intel"}
    assert ms.usadas_ph(c, date(2026, 11, 28), ["Intel"]) == set()          # pasaron los 7 días
    assert ms.menciona("La Ford Motor Company", ["Ford"]) == ["Ford"] and not ms.menciona("Oxford", ["Ford"])


def test_recordatorio_de_videos_esperando(tmp_path):
    c = _conn(tmp_path)
    mandados = []

    class TG:
        def send_message(self, chat, texto, **k):
            mandados.append(texto)

    m._espera_anotar(c, "efemeride_1124_1971", "El chip de Intel")
    m._espera_tick(c, TG(), ahora=datetime(2026, 11, 24, 9, 0, tzinfo=m.AR))
    assert mandados == []
    m._espera_tick(c, TG(), ahora=datetime(2026, 11, 24, 10, 5, tzinfo=m.AR))
    m._espera_tick(c, TG(), ahora=datetime(2026, 11, 24, 11, 0, tzinfo=m.AR))
    assert len(mandados) == 1 and "«El chip de Intel»" in mandados[0] and len(mandados[0].splitlines()) == 1
    m._espera_sacar(c, "efemeride_1124_1971")
    m._espera_tick(c, TG(), ahora=datetime(2026, 11, 24, 15, 0, tzinfo=m.AR))
    assert len(mandados) == 1


def test_plan_de_asi_nacio_en_5_lineas():
    from clips_bot import plan_an

    pend = ("| 20/11 – 22/11 | manos y apretón | aprobados por Santi |\n"
            "| 23/11 – 29/11 | escenas que faltan y expresiones | |\n")
    res = [{"ok": 17, "total": 19, "costo": 0.064, "_marca": "pepsi",
            "fallas": [{"id": "AN-07"}, {"id": "AN-11"}]}]
    t = plan_an.texto(date(2026, 11, 30 - 7), pend, res, {"2026-11-22": 0.3})
    lineas = t.splitlines()
    assert len(lineas) == 5 and lineas[0].startswith("🔧 Claude Code:") and "23/11" in lineas[0]
    assert "17/19" in lineas[2] and "AN-07" in lineas[3] and "1 de 1" in lineas[4]
