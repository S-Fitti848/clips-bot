"""2026-11-10 (Santi): (1) la prueba manual vs API, cancelada; (2) Rots todos los días sin cortar: la
entrega diaria se sube sola en sus horarios; (3) la efeméride también como Reel de Facebook a las
12:00, registrada aparte de la historia de las 19:00 para la comparación del 24/11."""
import json
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import clips_bot.__main__ as m
from clips_bot import db, facebook
from clips_bot.config import load_settings
from clips_bot.seleccion import Opcion

AHORA = datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc)


def _meta(cid, streamer):
    return {"clip_id": cid, "streamer": streamer, "grupo": "argentinos", "salida": f"{cid}.mp4",
            "plataforma": "kick", "puntaje": 8,
            "textos": {"titulo": f"t {cid}", "descripcion": "d", "hashtags": ["#Shorts"],
                       "depende_de_fecha": False}}


def _preparar(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    ops = [Opcion(c, s, 10, AHORA, meta=_meta(c, s), grupo="argentinos")
           for c, s in (("c1", "davooxeneize"), ("c2", "coker"))]
    monkeypatch.setattr(m, "_opciones_pendientes", lambda ready, settings: list(ops))
    monkeypatch.setattr(m, "_fuera_de_diarios", lambda conn, opciones: opciones)
    monkeypatch.setattr(m, "_streamers", lambda *a: [SimpleNamespace(login=s, permitido=True)
                                                    for s in ("davooxeneize", "coker")])
    monkeypatch.setattr(m, "env", lambda k: "x")
    enviados, subidos, mensajes = [], [], []
    monkeypatch.setattr(m, "TelegramClient", lambda tok: SimpleNamespace(
        send_message=lambda chat, texto: mensajes.append(texto)))
    monkeypatch.setattr(m, "enviar_clip", lambda tg, chats, conn, cid, meta, i, horario, **k:
                        enviados.append((cid, horario)))

    def programar(conn, settings, meta, canal, hora):
        subidos.append((meta["clip_id"], canal, hora, len(enviados)))
        return "⚠️ No pude subirlo a YouTube (Rots): cuota" if meta["clip_id"] == "c2" else "📤 Programado"

    monkeypatch.setattr(m, "_programar_subida", programar)
    return enviados, subidos, mensajes


def test_la_entrega_diaria_se_sube_sola_antes_de_mandarse(monkeypatch, tmp_path):
    enviados, subidos, mensajes = _preparar(monkeypatch, tmp_path)
    m.ejecutar_seleccion(load_settings(), None, enviar=True, destinos=["1"], subir=True)
    assert [c for c, *_ in subidos] == ["c1", "c2"]
    # cada uno se sube ANTES de mandarlo (el mensaje ya llega con "📤 Programado"), en su horario
    assert [(c, h, antes) for c, _, h, antes in subidos] == [("c1", "13:00", 0), ("c2", "18:00", 1)]
    assert {canal for _, canal, _, _ in subidos} == {"rots"}
    assert [c for c, _ in enviados] == ["c1", "c2"]
    # la que falló se avisa, y la entrega sigue igual
    assert len(mensajes) == 1 and mensajes[0].startswith("#2 · ⚠️")


def test_sin_subir_o_apagado_no_sube(monkeypatch, tmp_path):
    enviados, subidos, _ = _preparar(monkeypatch, tmp_path)
    m.ejecutar_seleccion(load_settings(), None, enviar=True, destinos=["1"])      # /seleccionar a mano
    s = load_settings()
    apagado = replace(s, publicacion=replace(s.publicacion, subir_solo=False))
    m.ejecutar_seleccion(apagado, None, enviar=True, destinos=["1"], subir=True)
    assert subidos == [] and len(enviados) == 4


def test_settings_del_10_11():
    s = load_settings()
    assert s.publicacion.prueba_manual_desde == ""          # cancelada: no marca nada a mano
    assert s.publicacion.subir_solo is True
    assert s.facebook.hora_efemeride == "12:00"
    assert s.historias_fb.hora_publicacion == "19:00"


def test_la_prueba_manual_no_marca_nada(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    elegidos = [SimpleNamespace(clip_id="a", streamer="davo", meta={})]
    assert m._manual_del_dia(conn, load_settings(), elegidos, ("13:00",)) is None


def _efe(clip_id, destino=""):
    return {"clip_id": clip_id, "salida": "x.mp4",
            "efemeride": {"fecha": "2026-11-11", "anio": 1918, "destino": destino,
                          "local": {"lugar": "Epecuén", "pais": "Argentina"} if destino else {}},
            "textos": {"titulo": "T", "descripcion": "D", "hashtags": ["#Historia"]}}


def test_la_efemeride_sale_en_facebook_a_las_12_y_queda_registrada(monkeypatch, tmp_path):
    conn = db.connect(tmp_path / "t.db")
    horas = []
    monkeypatch.setattr(facebook, "subir_reel", lambda video, texto, cuando, version:
                        horas.append(cuando) or f"FB{len(horas)}")
    monkeypatch.setattr(m, "_portada_de", lambda meta: None)
    s = load_settings()
    ahora = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)          # 09:00 AR
    m._subir_facebook(conn, s, _efe("efemeride_1111_1918"), ahora=ahora)
    m._subir_facebook(conn, s, _efe("historia_fb_1111_1985", "facebook"), ahora=ahora,
                      hora=s.historias_fb.hora_publicacion)
    assert [h.astimezone(m.AR).strftime("%H:%M") for h in horas] == ["12:00", "19:00"]
    reg = json.loads(db.get_valor(conn, m.HISTORIAS_FB_REGISTRO))
    assert [(r["clip_id"], r["reel"]) for r in reg] == [("efemeride_1111_1918", "efemeride"),
                                                        ("historia_fb_1111_1985", "historia")]
    assert reg[1]["lugar"] == "Epecuén" and reg[0]["video_id"] == "FB1"
