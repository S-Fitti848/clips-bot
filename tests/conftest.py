"""Para todos los tests: nada sale a la red por "lo que pegó en otros canales" (pego.py).

`/buscar` y `diario` buscan Shorts en YouTube antes de procesar; sin esto, un test de /buscar
tardaba 64 s haciendo búsquedas reales con yt-dlp. Los tests de pego.py pasan su propio buscador.
"""

import pytest


@pytest.fixture(autouse=True)
def _sin_busquedas_de_youtube(monkeypatch):
    import clips_bot.__main__ as m

    monkeypatch.setattr(m, "_buscador_pego", lambda: (lambda consulta, desde: []))


@pytest.fixture(autouse=True)
def _sin_fuentes_de_fotos(monkeypatch):
    """Las fuentes de fotos que no son Commons (fuentes_fotos.py) tampoco salen a la red: los tests
    que las prueban pasan su propia sesión."""
    from clips_bot import fuentes_fotos

    monkeypatch.setattr(fuentes_fotos, "BUSCAR_REAL", fuentes_fotos.Fuentes.buscar, raising=False)
    monkeypatch.setattr(fuentes_fotos.Fuentes, "buscar", lambda self, *a, **k: [])
