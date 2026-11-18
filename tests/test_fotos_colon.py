"""Reglas de fotos para todos los videos y publicaciones (Santi, 2026-11-17, después del Short de Colón: Cristina
Kirchner en Atucha, un retrato de Illia, recortes de diario borrosos y el año contando que mostraba 1993 y 2020)."""
import json

import numpy as np
import pytest
from PIL import Image, ImageFilter

from clips_bot import calidad
from clips_bot import efemerides as ef
from clips_bot import graficos as gr

HISTORIA = "Colón esperó 116 años para ganar su primer título. Fue en 2021: Colón le ganó 3-0 a Racing."


def test_nada_de_politicos_ni_retratos_que_la_historia_no_nombra():
    assert ef.motivo_persona({"politico": True, "quien": "Cristina Fernández de Kirchner"}, HISTORIA)
    assert ef.motivo_persona({"politico": True, "quien": ""}, HISTORIA)
    assert ef.motivo_persona({"retrato": True, "quien": "Arturo Umberto Illia"}, HISTORIA)
    assert ef.motivo_persona({"retrato": True, "quien": ""}, HISTORIA)
    # la historia es de esa persona: sí
    assert ef.motivo_persona({"politico": True, "retrato": True, "quien": "Lázaro Cárdenas"},
                             "Lázaro Cárdenas recibió a los niños de Morelia.") is None
    # un equipo, una multitud: sí
    assert ef.motivo_persona({"politico": False, "retrato": False, "quien": ""}, HISTORIA) is None


def _guardar(arr, ruta):
    Image.fromarray(arr).save(ruta)
    return ruta


@pytest.mark.calidad_real
def test_nada_de_fotos_chicas_ni_borrosas(tmp_path):
    rng = np.random.default_rng(1)
    nitida = (rng.random((800, 1200, 3)) * 255).astype("uint8")
    assert ef.motivo_calidad(_guardar(nitida, tmp_path / "ok.png")) is None
    chica = nitida[:300, :500]
    assert "resolución" in ef.motivo_calidad(_guardar(chica, tmp_path / "chica.png"))
    borrosa = np.array(Image.fromarray(nitida).filter(ImageFilter.GaussianBlur(12)))
    assert "borrosa" in ef.motivo_calidad(_guardar(borrosa, tmp_path / "borrosa.png"))
    assert ef.MIN_ANCHO_EPOCA == ef.MIN_ANCHO       # sin la excepción de 500 px para las de época


def test_ninguna_foto_del_tema_general():
    g = ef.Guion(titulo="t", descripcion="d", hashtags=[], frases=["a", "b", "c"], fotos=[0, 1, 2], descartadas=[])
    g.del_hecho = [5, 6]                 # las del artículo "Argentina" (Illia, Atucha)
    assert ef.generales(g) == []


def test_los_cortes_usan_solo_fotos_de_su_frase():
    g = ef.Guion(titulo="t", descripcion="d", hashtags=[], frases=["a", "b"], fotos=[0, 1], descartadas=[])
    g.del_hecho = [7, 8]
    g.ranking = [[0], [1]]
    plan = [(0, 0, 6.0), (1, 1, 9.0)]
    tarjetas = iter(range(100, 110))
    out, _ = ef.plan_rapido(plan, g, nueva_tarjeta=lambda i: next(tarjetas), montaje=True)
    usadas = {f for _, f, _ in out}
    assert not usadas & {7, 8}
    for i, f, _ in out:
        assert f in ({0} if i == 0 else {1}) or f >= 100      # su foto o una tarjeta


def test_el_anio_no_cuenta_desde_otro():
    ev = gr.anio_contando(2021, inicio=1.0, hasta=4.0)
    assert len(ev) == 1 and ev[0].endswith("2021")
    assert "1993" not in "".join(ev) and "2020" not in "".join(ev)


def test_las_reglas_nuevas_frenan_el_video():
    for rid in ("PH-10", "PH-11", "PH-12", "PH-13"):
        assert rid in calidad.por_id("pequena_historia")
    falla = [{"id": "PH-10", "que": "Cristina Kirchner en Atucha"}]
    assert calidad.retener("pequena_historia", falla, True)
    assert "PH-10" in calidad.texto_retenido("pequena_historia", falla)
    assert not calidad.retener("pequena_historia", [{"id": "PH-07", "que": "x"}], True)


def test_revision_del_video_terminado(tmp_path, monkeypatch):
    meta = {"salida": str(tmp_path / "v.mp4"),
            "efemeride": {"anio": 2021, "evento": "Colón campeón", "guion": ["a", "b"],
                          "local": {"lugar": "Santa Fe", "pais": "Argentina"},
                          "cortes": [{"frase": 0, "inicio": 0.0, "dur": 3.0, "tipo": "foto"},
                                     {"frase": 1, "inicio": 3.0, "dur": 3.0, "tipo": "foto"}]}}
    cuadros = []
    for k in range(2):
        p = tmp_path / f"c{k}.jpg"
        p.write_bytes(b"jpg")
        cuadros.append(p)
    monkeypatch.setattr(calidad, "cuadros_de_cortes", lambda *a, **k: cuadros)

    class Cliente:
        def json(self, sistema, prompt, schema, temp, imagenes=None):
            assert "PH-10" in prompt and "Santa Fe" in prompt and len(imagenes) == 2
            return json.dumps({"reglas": [{"id": "PH-10", "cumple": False, "corte": 2, "que": "Cristina en Atucha"},
                                          {"id": "PH-12", "cumple": True, "corte": 0, "que": ""}]})

    fallas, revisado = calidad.revisar_video_ph(Cliente(), meta)
    assert revisado and [f["id"] for f in fallas] == ["PH-10"] and "3.0 s" in fallas[0]["que"]
    juntas = calidad.juntar_fallas([{"id": "PH-02", "que": "viejo"}, {"id": "PH-07", "que": "x"}], fallas)
    assert {f["id"] for f in juntas} == {"PH-10", "PH-07"}
