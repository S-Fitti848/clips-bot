"""Lo que retiene, aplicado a los próximos videos, y el resumen semanal de 5 líneas (Santi, 2026-11-18)."""
from datetime import datetime

import clips_bot.__main__ as m
from clips_bot import aprendizaje as ap, db


def _x(canal, gancho, p3, r10, vistas, dia="2026-11-12"):
    return {"canal": canal, "gancho": gancho, "titulo": gancho[:20], "pasa_3s": p3, "ret_10": r10, "ret_final": 20,
            "vistas": vistas, "publicado": f"{dia}T15:00:00"}


MEDIDOS = {str(k): _x("facebook", f"gancho {k}", 40 + 5 * k, 20 + k, 100 * k) for k in range(6)}


def test_las_lecciones_van_al_prompt(tmp_path):
    arch = tmp_path / "lecciones.json"
    ap.guardar(MEDIDOS, arch)
    txt = ap.para_prompt("pequena_historia", arch)
    assert "LOS QUE MÁS RETUVIERON" in txt and txt.index("gancho 5") < txt.index("gancho 0")
    assert ap.para_prompt("asinacio", arch) == ""            # sin Reels medidos de ese canal


def test_resumen_de_5_lineas():
    medidos = dict(MEDIDOS)
    medidos["n"] = _x("facebook", "nuevo", 60, 30, 900, dia="2026-11-18")
    t = ap.resumen_semana(medidos, ["tope de costo", "escenas con sentido"], datetime(2026, 11, 23, 10, 0))
    assert len(t.splitlines()) <= 5 and "Pequeña Historia" in t and "tope de costo" in t


def test_el_reel_a_las_24_h_no_se_manda(tmp_path, monkeypatch):
    c = db.connect(tmp_path / "t.db")
    mandados = []

    class Tg:
        def send_message(self, chat, texto, *a, **k):
            mandados.append(texto)

    monkeypatch.setattr(ap, "ARCHIVO", tmp_path / "lecciones.json")
    from datetime import timezone, timedelta
    pub = datetime.now(timezone.utc) - timedelta(hours=30)
    db.crear_subida(c, "historia_fb_1", "facebook", "publicada", video_id="v1", publish_at=pub.isoformat())
    m._fb_24h_tick(c, Tg(), __import__('clips_bot.config', fromlist=['x']).load_settings(), ahora=datetime.now(timezone.utc),
                   medir=lambda canal, vid, p: {"vistas": 100, "pasa_3s": 50, "ret_10": 20, "ret_final": 10,
                                                "interaccion": 3, "reacciones": 3, "comentarios": 0, "compartidos": 0})
    assert mandados == []
