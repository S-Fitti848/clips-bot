"""Para todos los tests: nada sale a la red por "lo que pegó en otros canales" (pego.py).

`/buscar` y `diario` buscan Shorts en YouTube antes de procesar; sin esto, un test de /buscar
tardaba 64 s haciendo búsquedas reales con yt-dlp. Los tests de pego.py pasan su propio buscador.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _sin_busquedas_de_youtube(monkeypatch):
    import clips_bot.__main__ as m

    monkeypatch.setattr(m, "_buscador_pego", lambda: (lambda consulta, desde: []))


# Ningún test sale nunca a YouTube ni a Facebook ni usa un token real, esté como esté
# `youtube_upload_enabled` (2026-10-30: con la subida prendida, la suite se colgó en el 27 %). Un
# pedido real a estos hosts falla AL INSTANTE con un error que dice qué test lo intentó.
HOSTS_PROHIBIDOS = ("googleapis.com", "youtube.com", "accounts.google.com", "facebook.com")


class SalidaProhibida(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _sin_youtube_ni_facebook(monkeypatch, tmp_path_factory):
    import requests

    from clips_bot import facebook, youtube

    original = requests.Session.request

    def bloqueado(self, method, url, *a, **k):
        if any(h in str(url) for h in HOSTS_PROHIBIDOS):
            registro = os.environ.get("CLIPS_REGISTRO_SALIDAS")   # para auditar qué test lo intentó
            if registro:
                with open(registro, "a", encoding="utf-8") as f:
                    f.write(f"{os.environ.get('PYTEST_CURRENT_TEST', '?')}\t{method}\t{str(url)[:120]}\n")
            raise SalidaProhibida(f"un test intentó salir a {url}: los tests no hablan con YouTube ni Facebook")
        return original(self, method, url, *a, **k)

    monkeypatch.setattr(requests.Session, "request", bloqueado)
    # Ni los tokens reales de config/ ni las credenciales del .env.
    vacia = tmp_path_factory.mktemp("sin_tokens")

    def anotar(que: str) -> None:
        registro = os.environ.get("CLIPS_REGISTRO_SALIDAS")
        if registro:
            with open(registro, "a", encoding="utf-8") as f:
                f.write(f"{os.environ.get('PYTEST_CURRENT_TEST', '?')}\tTOKEN\t{que}\n")

    def ruta_token(canal):
        anotar(f"youtube {canal}")
        return vacia / f"youtube_token_{canal}.json"

    def env_fb(nombre, requerido=True):
        anotar(f"facebook {nombre}")
        return ""

    monkeypatch.setattr(youtube, "ruta_token", ruta_token)
    monkeypatch.setattr(youtube, "_secreto", lambda *a, **k: {"client_id": "test", "client_secret": "test"})
    monkeypatch.setattr(facebook, "env", env_fb)


@pytest.fixture(autouse=True)
def _sin_fuentes_de_fotos(monkeypatch):
    """Las fuentes de fotos que no son Commons (fuentes_fotos.py) tampoco salen a la red: los tests
    que las prueban pasan su propia sesión."""
    from clips_bot import fuentes_fotos

    monkeypatch.setattr(fuentes_fotos, "BUSCAR_REAL", fuentes_fotos.Fuentes.buscar, raising=False)
    monkeypatch.setattr(fuentes_fotos.Fuentes, "buscar", lambda self, *a, **k: [])
