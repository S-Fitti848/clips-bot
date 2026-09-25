"""Cliente mínimo de Twitch Helix con app token (client credentials).

Endpoints usados:
  POST https://id.twitch.tv/oauth2/token        → app access token
  GET  /helix/users?login=...                  → login → broadcaster_id
  GET  /helix/clips?broadcaster_id=...         → clips (Twitch los devuelve ordenados por vistas)
  GET  /helix/games?id=...                     → game_id → nombre de categoría
  GET  /helix/videos?id=...                    → video_id (VOD) → título del stream
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Iterable

import requests

log = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.twitch.tv/helix"
MAX_IDS_POR_REQUEST = 100  # límite de Helix para login= / id= repetidos


class TwitchError(RuntimeError):
    pass


def rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chunks(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


class TwitchClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        session: requests.Session | None = None,
        timeout: float = 15,
        max_reintentos: int = 3,
        sleep=time.sleep,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_reintentos = max_reintentos
        self._sleep = sleep
        self._token: str | None = None

    # ---- auth -------------------------------------------------------------

    def _pedir_token(self) -> str:
        r = self.session.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise TwitchError(f"No se pudo obtener token de Twitch ({r.status_code}): {r.text[:200]}")
        self._token = r.json()["access_token"]
        return self._token

    def _headers(self) -> dict[str, str]:
        token = self._token or self._pedir_token()
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {token}"}

    # ---- request con reintentos --------------------------------------------

    def _get(self, path: str, params: list[tuple[str, str]]) -> dict:
        """GET a Helix. Renueva el token una vez ante 401, respeta 429 y reintenta 5xx con backoff."""
        token_renovado = False
        intento = 0
        while True:
            try:
                r = self.session.get(f"{API_URL}{path}", params=params, headers=self._headers(), timeout=self.timeout)
            except requests.RequestException as e:
                intento += 1
                if intento > self.max_reintentos:
                    raise TwitchError(f"GET {path}: error de red tras {self.max_reintentos} reintentos: {e}") from e
                self._sleep(2**intento)
                continue

            if r.status_code == 200:
                return r.json()
            if r.status_code == 401 and not token_renovado:
                token_renovado = True
                self._pedir_token()
                continue
            if r.status_code == 429 or r.status_code >= 500:
                intento += 1
                if intento > self.max_reintentos:
                    raise TwitchError(f"GET {path}: {r.status_code} tras {self.max_reintentos} reintentos")
                espera = float(2**intento)
                reset = r.headers.get("Ratelimit-Reset")
                if r.status_code == 429 and reset and reset.isdigit():
                    espera = min(max(int(reset) - time.time(), 1), 60)
                log.warning("GET %s → %s, reintento %d en %.0fs", path, r.status_code, intento, espera)
                self._sleep(espera)
                continue
            raise TwitchError(f"GET {path}: {r.status_code} {r.text[:200]}")

    # ---- endpoints --------------------------------------------------------

    def get_user_ids(self, logins: list[str]) -> dict[str, str]:
        """login → broadcaster_id. Los logins que no existen no aparecen en el resultado."""
        out: dict[str, str] = {}
        for grupo in _chunks(logins, MAX_IDS_POR_REQUEST):
            data = self._get("/users", [("login", l) for l in grupo])
            for u in data.get("data", []):
                out[u["login"].lower()] = u["id"]
        return out

    def get_users(self, logins: list[str]) -> list[dict]:
        """Los usuarios que existen, con su login, nombre visible y descripción.

        Twitch ya no deja leer la cantidad de seguidores con un app token (hace falta el token del
        propio canal), así que para un alta la señal es: existe + tiene clips.
        """
        out = []
        for grupo in _chunks(logins, MAX_IDS_POR_REQUEST):
            for u in self._get("/users", [("login", l) for l in grupo]).get("data", []):
                out.append({"login": u["login"].lower(), "id": u["id"],
                            "nombre": u.get("display_name") or u["login"],
                            "descripcion": (u.get("description") or "")[:120]})
        return out

    def search_channels(self, consulta: str, limite: int = 8) -> list[dict]:
        """Canales que se parecen al nombre. Para cuando lo que pidieron es ambiguo."""
        data = self._get("/search/channels", [("query", consulta), ("first", str(limite))])
        return [{"login": c["broadcaster_login"].lower(), "id": c.get("id", ""),
                 "nombre": c.get("display_name") or c["broadcaster_login"],
                 "en_vivo": bool(c.get("is_live")), "juego": c.get("game_name") or ""}
                for c in data.get("data", [])]

    def get_clips(
        self, broadcaster_id: str, started_at: datetime, ended_at: datetime, max_clips: int = 100
    ) -> list[dict]:
        """Clips del broadcaster creados en [started_at, ended_at], paginando hasta max_clips."""
        clips: list[dict] = []
        cursor: str | None = None
        while len(clips) < max_clips:
            page, cursor = self.get_clips_pagina(
                broadcaster_id, started_at, ended_at, min(100, max_clips - len(clips)), cursor
            )
            clips.extend(page)
            if not page or not cursor:
                break
        return clips[:max_clips]

    def get_clips_pagina(
        self, broadcaster_id: str, started_at: datetime, ended_at: datetime, first: int, after: str | None = None
    ) -> tuple[list[dict], str | None]:
        """Una página de clips (ordenados por vistas) y el cursor de la siguiente (None = no hay más).
        El cursor solo vale para la misma consulta: mismo broadcaster y mismas fechas."""
        params = [
            ("broadcaster_id", broadcaster_id),
            ("started_at", rfc3339(started_at)),
            ("ended_at", rfc3339(ended_at)),
            ("first", str(min(max(first, 1), 100))),
        ]
        if after:
            params.append(("after", after))
        data = self._get("/clips", params)
        return data.get("data", []), (data.get("pagination") or {}).get("cursor") or None

    def get_game_names(self, game_ids: Iterable[str]) -> dict[str, str]:
        ids = sorted({g for g in game_ids if g})
        out: dict[str, str] = {}
        for grupo in _chunks(ids, MAX_IDS_POR_REQUEST):
            data = self._get("/games", [("id", g) for g in grupo])
            for g in data.get("data", []):
                out[g["id"]] = g["name"]
        return out

    def get_video_titles(self, video_ids: Iterable[str]) -> dict[str, str]:
        """video_id del VOD → título del stream. Los VODs borrados o vencidos no aparecen."""
        ids = sorted({v for v in video_ids if v})
        out: dict[str, str] = {}
        for grupo in _chunks(ids, MAX_IDS_POR_REQUEST):
            try:
                data = self._get("/videos", [("id", v) for v in grupo])
            except TwitchError as e:
                # Helix devuelve 404 si algún id del lote no existe; no es motivo para cortar la corrida.
                log.warning("No pude leer títulos de VODs: %s", e)
                continue
            for v in data.get("data", []):
                out[v["id"]] = v.get("title") or ""
        return out
