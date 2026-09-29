"""Picos de chat (pedido 2026-09-29): para un clip de Twitch con VOD, cuántos mensajes por segundo
hubo en el chat alrededor del momento, comparado con el ritmo normal de ESE stream.

Helix no da el chat grabado: sale del GraphQL interno de Twitch (el mismo que usa la web para el
chat de los VODs, `VideoCommentsByOffsetOrCursor`), sin login. No está documentado: si falla, el
clip sigue sin la señal. Probado el 2026-09-29 con un VOD real de auronplay: responde.

Kick no tiene chat grabado accesible: la señal es solo para Twitch. En el modo en vivo tampoco
aplica (Twitch no da `vod_offset` mientras el stream está al aire).
"""

from __future__ import annotations

import logging
import math
import statistics

import requests

log = logging.getLogger(__name__)

GQL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"   # el de la web de Twitch (público)
HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"
VENTANA_S = 30        # el momento: 30 s alrededor del offset del clip
MUESTRAS = 5          # para el ritmo normal del stream
PUNTOS = 3            # páginas por ventana (una por pedido: el cursor ya no anda sin login)


class Chat:
    def __init__(self, session: requests.Session | None = None, timeout: float = 20):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._base: dict[str, float] = {}      # ritmo normal por VOD (una vez por VOD)

    def _pagina(self, video_id: str, offset: float | None = None, cursor: str | None = None) -> dict:
        variables = {"videoID": video_id}
        if cursor:
            variables["cursor"] = cursor
        else:
            variables["contentOffsetSeconds"] = max(0, int(offset or 0))
        r = self.session.post(GQL, timeout=self.timeout, headers={"Client-Id": CLIENT_ID}, json=[{
            "operationName": "VideoCommentsByOffsetOrCursor", "variables": variables,
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": HASH}}}])
        r.raise_for_status()
        return ((r.json()[0].get("data") or {}).get("video") or {}).get("comments") or {}

    def ritmo(self, video_id: str, desde: float, segundos: float = VENTANA_S) -> float:
        """Mensajes por segundo en la ventana [desde, desde + segundos]: una página del chat en
        `PUNTOS` lugares de la ventana, y en cada una los mensajes divididos por el tiempo que cubre.

        Medido el 2026-09-29: sin login, la paginación con cursor devuelve páginas VACÍAS, así que
        cada pedido da una sola página (~50 mensajes; en el chat de Auron, ~12 s). La primera versión
        contaba esa página sobre los 30 s de la ventana y daba ~1,2 mensajes/s para todos."""
        tasas = []
        for k in range(PUNTOS):
            edges = self._pagina(video_id, desde + k * segundos / PUNTOS).get("edges") or []
            tiempos = [(e.get("node") or {}).get("contentOffsetSeconds", 0) for e in edges]
            if len(tiempos) >= 2 and tiempos[-1] > tiempos[0]:
                tasas.append((len(tiempos) - 1) / (tiempos[-1] - tiempos[0]))
            elif tiempos:
                tasas.append(len(tiempos) / segundos)
        return statistics.median(tasas) if tasas else 0.0

    def base(self, video_id: str, duracion: float) -> float:
        """El ritmo normal del stream: la mediana de MUESTRAS ventanas repartidas por el VOD."""
        if video_id not in self._base:
            puntos = [duracion * (k + 1) / (MUESTRAS + 1) for k in range(MUESTRAS)]
            self._base[video_id] = statistics.median(self.ritmo(video_id, p) for p in puntos)
        return self._base[video_id]

    def pico(self, video_id: str, vod_offset: float, duracion: float) -> float | None:
        """Cuántas veces más mensajes por segundo que lo normal hubo en el momento del clip. El clip
        termina en `vod_offset + duración del clip`; la reacción del chat viene justo después del
        hecho, así que la ventana arranca 5 s antes del offset. None si no se pudo medir."""
        try:
            base = self.base(video_id, duracion)
            momento = self.ritmo(video_id, max(0.0, vod_offset - 5))
        except Exception as e:
            log.warning("chat de %s: %s", video_id, e)
            return None
        if base <= 0:
            return None if momento <= 0 else 4.0
        return round(momento / base, 2)


def factor_pico(pico: float | None, peso: float) -> float:
    """1 + peso × (log2 del pico, entre 0 y 2) / 2: un pico de ×4 o más suma todo el peso; un chat
    normal o más tranquilo que lo normal no resta (no saber no castiga)."""
    if not pico or pico <= 1 or not peso:
        return 1.0
    return 1 + peso * min(math.log2(pico), 2.0) / 2
