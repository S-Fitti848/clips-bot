"""Para todos los tests: nada sale a la red por "lo que pegó en otros canales" (pego.py).

`/buscar` y `diario` buscan Shorts en YouTube antes de procesar; sin esto, un test de /buscar
tardaba 64 s haciendo búsquedas reales con yt-dlp. Los tests de pego.py pasan su propio buscador.
"""

import pytest


@pytest.fixture(autouse=True)
def _sin_busquedas_de_youtube(monkeypatch):
    import clips_bot.__main__ as m

    monkeypatch.setattr(m, "_buscador_pego", lambda: (lambda consulta, desde: []))
