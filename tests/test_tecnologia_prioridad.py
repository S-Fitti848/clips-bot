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
    assert pr.nivel_necesario(20.4, por_rec, hoy, n)[0] == n


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
