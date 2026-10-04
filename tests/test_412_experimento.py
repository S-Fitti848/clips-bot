"""El 412 como experimento (2026-10-04): no se descarta, avisa "⚠️ 412"; un /reclamo lo re-excluye."""
from datetime import datetime, timezone

from clips_bot import candidates as cand, db, registro
from clips_bot.config import Streamer


def _clip(stream_title="412 con LA COBRA, DAVOO… PROGRAMA", login="lacobraaa"):
    return cand.Clip(id="c1", url="u", broadcaster_login=login, broadcaster_name=login, title="El peor golpe",
                     view_count=10, duration=30.0, language="", created_at=datetime.now(timezone.utc),
                     game_id="", game_name="Just Chatting", vod_offset=None, stream_title=stream_title)


def _st():
    return Streamer(login="lacobraaa", plataforma="kick", palabras_programa=("412", "ANALIZAMOS"))


def test_el_412_pasa_a_aviso_y_analizamos_sigue_descartando(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    s = registro.combinar([_st()], conn)[0]
    assert s.palabras_programa == ("ANALIZAMOS",) and s.programa_aviso == ("412",)
    c = _clip()
    assert cand.motivo_descarte(c, cand.Filtros(), set(), palabras_programa=s.palabras_programa) is None
    assert cand.con_aviso_programa(c, s.programa_aviso).aviso.startswith("⚠️ 412")
    assert cand.con_aviso_programa(_clip("charla normal"), s.programa_aviso).aviso == ""
    otro = _clip("ANALIZAMOS el partido")
    assert cand.motivo_descarte(otro, cand.Filtros(), set(),
                                palabras_programa=s.palabras_programa) == cand.MOTIVO_PROGRAMA


def test_aviso_se_suma_al_de_futbol():
    from dataclasses import replace
    c = replace(_clip(), aviso="⚽ habla de fútbol")
    assert cand.con_aviso_programa(c, ("412",)).aviso.endswith("⚽ habla de fútbol")


def test_reclamo_lo_vuelve_a_excluir(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    assert registro.excluir_programa(conn, "412") is True
    assert registro.excluir_programa(conn, "412") is False
    s = registro.combinar([_st()], conn)[0]
    assert "412" in s.palabras_programa and s.programa_aviso == ()
    assert cand.motivo_descarte(_clip(), cand.Filtros(), set(),
                                palabras_programa=s.palabras_programa) == cand.MOTIVO_PROGRAMA


def _reclamo_con(tmp_path, monkeypatch, aviso, clip_id):
    import json

    from clips_bot import __main__ as m
    from clips_bot import process

    conn = db.connect(tmp_path / "c.db")
    monkeypatch.setattr(process, "READY_DIR", tmp_path)
    (tmp_path / f"{clip_id}.json").write_text(json.dumps({"clip_id": clip_id, "streamer": "davooxeneize",
                                                          "aviso": aviso}), encoding="utf-8")
    db.registrar_clip(conn, clip_id, "davooxeneize", "entregado", None)
    return conn, m._reclamo(conn, [clip_id])


def test_reclamo_del_412_excluye_solo_el_412(tmp_path, monkeypatch):
    conn, texto = _reclamo_con(tmp_path, monkeypatch, "⚠️ 412 (stream del programa: revisalo con más cuidado)", "c412")
    assert "412" in registro.programas_excluidos(conn)
    assert "davooxeneize" not in db.excluidos(conn)
    assert "sigue en las corridas" in texto and "\n" in texto


def test_reclamo_comun_sigue_excluyendo_al_streamer(tmp_path, monkeypatch):
    conn, texto = _reclamo_con(tmp_path, monkeypatch, "", "c1")
    assert "davooxeneize" in db.excluidos(conn) and registro.programas_excluidos(conn) == set()
