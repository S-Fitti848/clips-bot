"""Santi, 2026-11-25: fotos primero, guion después (fotos_primero.py)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from clips_bot import efemerides as ef
from clips_bot import fotos_primero as fp


def _desc(**k):
    return {"se_ve": "una Game Boy", "nitida": True, "epoca": "1989", "de_epoca": True, "de_la_historia": True,
            "tipo": "foto", **k}


def test_motivo_descarta_borrosas_modernas_y_ajenas():
    h = "Nintendo lanza la Game Boy"
    assert fp.motivo(_desc(), h) is None
    assert fp.motivo(_desc(nitida=False), h) == "borrosa"
    assert fp.motivo(_desc(de_epoca=False, moderno="autos de hoy en la calle"), h) == "de otra época"
    # la estación de 1874 fotografiada hoy: sin nada moderno a la vista, es de la época (Santi, 2026-11-25)
    assert fp.motivo(_desc(de_epoca=False, moderno=""), h) is None
    assert fp.motivo(_desc(de_la_historia=False), h) == "no es de la historia"
    assert fp.motivo(_desc(tipo="logo"), h) == "es un logo"
    assert fp.motivo(_desc(retrato=True, quien="Pedro Pérez"), h) == "persona que la historia no nombra"
    assert fp.motivo(_desc(retrato=True, quien="Gunpei Yokoi"), h + " de Gunpei Yokoi") is None


class Haiku:
    def __init__(self, desc):
        self.desc, self.pedidos = desc, []

    def json(self, sistema, prompt, schema, imagenes=None, **k):
        self.pedidos.append(sistema)
        if sistema == fp.SISTEMA:
            return json.dumps({"fotos": [dict(d, foto=j) for j, d in enumerate(self.desc, 1)]})
        return json.dumps({"frases": [{"frase": 1, "fotos": [2, 1, 9]}, {"frase": 2, "fotos": []}]})


def _foto(tmp_path, k):
    from PIL import Image

    r = tmp_path / f"f{k}.jpg"
    Image.new("RGB", (900, 600), (k * 20 % 255, 80, 120)).save(r)
    return ef.Foto(archivo=f"File:F{k}.jpg", url="u", ancho=900, alto=600, autor="a", licencia="CC0",
                   pagina="", epigrafe=f"foto {k}", articulo="x", ruta=str(r))


def _juntar(monkeypatch, tmp_path, desc):
    fotos = [_foto(tmp_path, k) for k in range(len(desc))]
    monkeypatch.setattr(fp, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(fp, "candidatas", lambda *a, **k: fotos)
    monkeypatch.setattr(ef, "bajar_fotos", lambda wiki, fs, *a, **k: (fs, []))
    monkeypatch.setattr(ef, "motivo_calidad", lambda r: None)
    monkeypatch.setattr(ef, "fraccion_texto", lambda r: 0.0)
    h = Haiku(desc)
    e = ef.Evento("es", 1989, "Nintendo lanza la Game Boy", ["Game_Boy"])
    return fp.juntar(None, h, e, [], tmp_path, e.texto, lambda *_: None), h


def test_con_menos_de_8_buenas_no_hay_guion(monkeypatch, tmp_path):
    with pytest.raises(fp.FotosPrevias) as err:
        _juntar(monkeypatch, tmp_path, [_desc()] * 7 + [_desc(nitida=False)] * 3)
    assert err.value.buenas == 7 and "borrosa 3" in str(err.value)


def test_el_guion_ve_las_fotos_y_cada_frase_recibe_las_suyas(monkeypatch, tmp_path):
    desc = [_desc(se_ve=f"cosa {k}") for k in range(8)] + [_desc(de_epoca=False, moderno="un celular")]
    b, h = _juntar(monkeypatch, tmp_path, desc)
    assert b.buenas == list(range(8)) and "F1: cosa 0 (1989)" in b.contexto()
    r = fp.asignar(h, ["frase uno", "frase dos"], b, lambda *_: None)
    assert r == [[1, 0], []]                    # la 9 no existe: no se inventa
