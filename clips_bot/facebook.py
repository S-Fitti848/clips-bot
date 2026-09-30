"""Reels de Pequeña Historia a una página de Facebook (pedido 2026-09-30, APAGADO hasta que Santi
complete docs/facebook.md: `facebook.activo`).

Graph API de Meta, "Reels Publishing API", en tres pasos:
  1. POST /{page-id}/video_reels?upload_phase=start  → video_id y upload_url
  2. POST rupload.facebook.com/video-upload/{version}/{video_id} con el archivo (encabezados
     Authorization: OAuth <token>, offset: 0, file_size)
  3. POST /{page-id}/video_reels?upload_phase=finish con video_state=PUBLISHED, o SCHEDULED y
     scheduled_publish_time (unix) para que salga a la misma hora que en YouTube.
Cancelar = borrar el video (DELETE /{video_id}).

Es la página PROPIA de Santi con un token de página de larga duración: no hace falta la revisión de
Meta (la app queda en modo desarrollo y Santi es administrador de la app y de la página).
Credenciales en el .env (FACEBOOK_PAGE_ID, FACEBOOK_PAGE_TOKEN), nunca en git.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import env

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/{version}"
RUPLOAD = "https://rupload.facebook.com/video-upload/{version}/{video_id}"
MIN_PROGRAMAR_S = 15 * 60     # Facebook pide al menos ~10 min en el futuro para programar


class FacebookError(RuntimeError):
    pass


def credenciales() -> tuple[str, str]:
    page, token = env("FACEBOOK_PAGE_ID", requerido=False), env("FACEBOOK_PAGE_TOKEN", requerido=False)
    if not page or not token:
        raise FacebookError("faltan FACEBOOK_PAGE_ID o FACEBOOK_PAGE_TOKEN en el .env (docs/facebook.md)")
    return page, token


def _ok(r: requests.Response, paso: str) -> dict:
    try:
        d = r.json()
    except ValueError:
        d = {}
    if r.status_code != 200 or "error" in d:
        msg = (d.get("error") or {}).get("message") or r.text[:200]
        raise FacebookError(f"Facebook ({paso}): {r.status_code} {msg}")
    return d


def subir_reel(video: Path, descripcion: str, cuando: datetime | None, version: str,
               page_id: str | None = None, token: str | None = None,
               session: requests.Session | None = None, ahora: datetime | None = None) -> str:
    """Sube el Reel y lo publica (o lo programa para `cuando`). Devuelve el video_id."""
    if page_id is None or token is None:
        page_id, token = credenciales()
    s = session or requests.Session()
    base = GRAPH.format(version=version)
    d = _ok(s.post(f"{base}/{page_id}/video_reels", timeout=60,
                   data={"upload_phase": "start", "access_token": token}), "inicio")
    video_id = d.get("video_id")
    if not video_id:
        raise FacebookError(f"Facebook (inicio): no devolvió video_id ({d})")
    datos = video.read_bytes()
    _ok(s.post(RUPLOAD.format(version=version, video_id=video_id), timeout=600, data=datos,
               headers={"Authorization": f"OAuth {token}", "offset": "0",
                        "file_size": str(len(datos))}), "subida")
    fin = {"upload_phase": "finish", "video_id": video_id, "description": descripcion[:2000],
           "access_token": token}
    ahora = ahora or datetime.now(timezone.utc)
    if cuando is not None and (cuando - ahora).total_seconds() >= MIN_PROGRAMAR_S:
        fin.update(video_state="SCHEDULED", scheduled_publish_time=str(int(cuando.timestamp())))
    else:
        fin.update(video_state="PUBLISHED")
    _ok(s.post(f"{base}/{page_id}/video_reels", timeout=60, data=fin), "publicación")
    return str(video_id)


def cancelar(video_id: str, version: str, token: str | None = None,
             session: requests.Session | None = None) -> None:
    if token is None:
        _, token = credenciales()
    _ok((session or requests.Session()).delete(f"{GRAPH.format(version=version)}/{video_id}",
                                               params={"access_token": token}, timeout=60), "cancelar")
