"""Clips de Kick vía la API interna de la web: GET kick.com/api/v2/channels/{slug}/clips.

OJO: no es una API pública documentada. Puede cambiar o empezar a pedir verificación de navegador
sin aviso. Por eso el que la usa tiene que tolerar el error: se loguea, se avisa por Telegram y la
corrida sigue con Twitch (§ pipeline).

Parámetros útiles (probados 2026-09-22): `sort=view` + `time=day|week|month` devuelve los más
VISTOS de esa ventana; sin parámetros devuelve los últimos subidos, que en un canal grande son cientos
de clips de la última hora con 2 o 3 vistas. Por eso la fuente reciente usa sort=view&time=week.
`sort=view` sin `time` es el equivalente al catálogo (los mejores de siempre).

La respuesta trae `clips` y `nextCursor`. De cada clip se usa: id, title, view_count, duration,
created_at, category.name, channel.slug, livestream_id y vod_starts_at (los dos últimos sirven para
agrupar clips del mismo momento, igual que vod_offset en Twitch).
Kick NO informa idioma: esos clips no pasan por el filtro de idioma.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

API = "https://kick.com/api/v2/channels/{slug}/clips"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")


class KickError(RuntimeError):
    pass


def url_clip(slug: str, clip_id: str) -> str:
    return f"https://kick.com/{slug}/clips/{clip_id}"


class KickClient:
    def __init__(self, session: requests.Session | None = None, timeout: float = 25,
                 max_reintentos: int = 2, sleep=time.sleep):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_reintentos = max_reintentos
        self._sleep = sleep

    def _get(self, url: str, params: dict | None = None) -> dict:
        intento = 0
        while True:
            try:
                r = self.session.get(url, params=params or {}, timeout=self.timeout,
                                     headers={"User-Agent": UA, "Accept": "application/json"})
            except requests.RequestException as e:
                r, error = None, f"error de red: {e}"
            else:
                error = f"{r.status_code} {r.text[:200]}"
            if r is not None and r.status_code == 200:
                try:
                    return r.json()
                except ValueError as e:  # HTML de Cloudflare en vez de JSON
                    error = f"respuesta no JSON ({e})"
            intento += 1
            if intento > self.max_reintentos:
                raise KickError(f"Kick {url}: {error}")
            log.warning("Kick %s, reintento %d", error[:80], intento)
            self._sleep(5 * intento)

    def get_clips(self, slug: str, max_clips: int = 100, orden: str = "view",
                  ventana: str = "week") -> list[dict]:
        """Clips del canal paginando con nextCursor. Por default, los más vistos de la semana."""
        clips: list[dict] = []
        cursor: str | None = None
        while len(clips) < max_clips:
            params = {"sort": orden}
            if ventana:
                params["time"] = ventana
            if cursor:
                params["cursor"] = cursor
            data = self._get(API.format(slug=slug), params)
            page = data.get("clips") or []
            clips.extend(page)
            cursor = data.get("nextCursor") or None
            if not page or not cursor:
                break
        return clips[:max_clips]


def a_clip(d: dict, login: str) -> dict:
    """Clip de Kick con las mismas claves que usa Clip.from_helix, para que el pipeline no cambie."""
    creado = str(d.get("created_at") or "").replace("Z", "+00:00")
    try:
        fecha = datetime.fromisoformat(creado).astimezone(timezone.utc)
    except ValueError:
        fecha = datetime.now(timezone.utc)
    return {
        "id": str(d.get("id") or ""),
        "url": url_clip(str((d.get("channel") or {}).get("slug") or login), str(d.get("id") or "")),
        "broadcaster_name": str((d.get("channel") or {}).get("username") or login),
        "title": str(d.get("title") or ""),
        "view_count": int(d.get("view_count") or d.get("views") or 0),
        "duration": float(d.get("duration") or 0),
        "language": "",  # Kick no lo informa
        "game_id": str((d.get("category") or {}).get("id") or ""),
        "created_at": fecha.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vod_offset": int(d.get("vod_starts_at") or 0) or None,
        "video_id": str(d.get("livestream_id") or ""),
        "_game_name": str((d.get("category") or {}).get("name") or ""),
    }
