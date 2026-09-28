"""La mezcla diaria revisada el 2026-09-28: sin cupo del Dedsafío, Famosos (Auron), multi-POV
apagado, peso por los votos de Santi y 1 clip por streamer también en el relleno."""

import re
from datetime import datetime, timezone

import pytest

import clips_bot.__main__ as m
from clips_bot import db
from clips_bot.config import Seleccion, load_settings, load_streamers
from clips_bot.seleccion import Opcion, factor_votos, factores_votos, seleccionar

AHORA = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
SANTI = "8668060171"


def test_la_mezcla_no_tiene_cupo_del_evento_y_el_multipov_esta_apagado():
    s = load_settings()
    assert s.seleccion.mezcla == {"argentinos": 2, "famosos": 1}
    assert s.seleccion.max_por_streamer == 1
    assert s.seleccion.votos_de == (SANTI,)
    assert s.multipov.activo is False


def test_auron_esta_en_famosos():
    auron = next(x for x in load_streamers() if x.login == "auronplay")
    assert auron.plataforma == "twitch" and auron.grupo == "famosos" and auron.permitido


@pytest.mark.parametrize("a_favor,en_contra,esperado", [
    (0, 0, 1.0), (2, 0, 1.2), (10, 0, 1.3846), (0, 10, 0.6154), (3, 3, 1.0),
])
def test_factor_votos(a_favor, en_contra, esperado):
    assert factor_votos(a_favor, en_contra, 0.5, 3) == pytest.approx(esperado, abs=1e-3)


def test_votos_por_streamer_cuenta_solo_los_de_santi(tmp_path):
    c = db.connect(tmp_path / "t.db")
    for cid, streamer in [("c1", "coker"), ("c2", "coker"), ("c3", "davooxeneize")]:
        c.execute("INSERT INTO clips (clip_id, broadcaster, estado) VALUES (?, ?, 'entregado')",
                  (cid, streamer))
    db.votar(c, "c1", 1, SANTI)
    db.votar(c, "c2", -1, SANTI)
    db.votar(c, "c2", 1, SANTI)                   # cambió de opinión: vale el último
    db.votar(c, "c3", -1, "8824893712")           # Tommy: no cuenta
    db.votar(c, "multipov_x", 1, SANTI)           # no está en clips: no cuenta
    assert db.votos_por_streamer(c, [SANTI]) == {"coker": (2, 0)}
    assert db.votos_por_streamer(c, []) == {}


def _op(cid, streamer, vistas, grupo="argentinos"):
    return Opcion(cid, streamer, vistas, AHORA, fuente="reciente", grupo=grupo)


def test_los_votos_pueden_dar_vuelta_el_orden():
    cfg = Seleccion(mezcla={"argentinos": 1})
    ops = [_op("a", "goncho", 500), _op("b", "coker", 300)]    # log: 3,70 contra 3,48
    assert [o.clip_id for o in seleccionar(ops, cfg, AHORA)] == ["a"]
    factores = factores_votos({"coker": (4, 0)}, cfg)           # ×1,29
    assert [o.clip_id for o in seleccionar(ops, cfg, AHORA, factores=factores)] == ["b"]


def test_famosos_tiene_su_cupo_y_el_evento_ya_no():
    cfg = load_settings().seleccion
    ops = [_op("a1", "spreen", 900), _op("a2", "coker", 800), _op("a3", "goncho", 700),
           _op("f1", "auronplay", 50, "famosos"), _op("e1", "rivers_gg", 99999, "evento")]
    elegidos = seleccionar(ops, cfg, AHORA)
    assert [o.clip_id for o in elegidos] == ["a1", "a2", "f1"]


# ---- el relleno respeta 1 por streamer --------------------------------------------------------

def _meta(cid, streamer, relleno=False, puntaje=7):
    return {"clip_id": cid, "streamer": streamer, "grupo": "argentinos", "salida": f"{cid}.mp4",
            "relleno": relleno, "puntaje": puntaje,
            "textos": {"titulo": f"t {cid}", "descripcion": "d", "hashtags": ["#Shorts"],
                       "depende_de_fecha": False}}


def test_el_relleno_no_repite_streamer(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    ops = [Opcion("a1", "spreen", 10, AHORA, meta=_meta("a1", "spreen"), grupo="argentinos"),
           Opcion("r1", "spreen", 10, AHORA, meta=_meta("r1", "spreen", True, 4), grupo="argentinos"),
           Opcion("r2", "coker", 10, AHORA, meta=_meta("r2", "coker", True, 3), grupo="argentinos")]
    monkeypatch.setattr(m, "_opciones_pendientes", lambda ready, settings: list(ops))
    monkeypatch.setattr(m, "_streamers", lambda *a: [])
    m.ejecutar_seleccion(load_settings(), None, enviar=False)
    salida = capsys.readouterr().out
    elegidos = re.findall(r"^\d+\. \[\w+\] score [\d.,]+ .*?(\w+)  \(", salida, re.M)
    assert elegidos == ["spreen", "coker"]
