"""Cliente mínimo de Gemini (REST generateContent) con salida JSON forzada por schema."""

from __future__ import annotations

import json
import base64
import logging
import time

import requests

log = logging.getLogger(__name__)

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


class GeminiError(RuntimeError):
    def __init__(self, mensaje: str, pasajero: bool = False):
        super().__init__(mensaje)
        # True = falló por algo que se arregla solo (503 "high demand", timeout, 5xx): vale la pena
        # reintentar más tarde. False = cuota del día agotada, pedido mal armado, respuesta rota.
        self.pasajero = pasajero


# Esperas entre reintentos de un error pasajero, por modelo (pedido 2026-09-28: el 503 "high
# demand" duró más de 10 minutos ese día, y con 10/20/30 s se quemaban los reintentos en 1 minuto).
ESPERAS_PASAJERO = (30, 60, 120)


class GeminiClient:
    """Cliente de Gemini con fallback de modelo cuando se acaba la cuota.

    El free tier de los modelos Flash está en ~20 requests por día (bajó de 250), y resetea a
    medianoche hora del Pacífico. Con 3 clips/día y UNA llamada por clip entramos cómodos; los que
    queman la cuota son los reintentos y las pruebas. Por eso: ante un 429 por cuota se pasa al
    modelo de fallback (flash-lite, que tiene su propia cuota) en vez de reintentar el mismo.

    Error pasajero (5xx, 429 que no es de cuota, timeout): 3 reintentos con `esperas` (30, 60 y
    120 s) y, si sigue, el otro modelo con las mismas esperas. Si todo falla, GeminiError con
    `pasajero=True`: quien llama decide reintentar más tarde en vez de avisar la falla.
    """

    def __init__(self, api_key: str, modelo: str, session: requests.Session | None = None,
                 timeout: float = 90, esperas: tuple = ESPERAS_PASAJERO, sleep=time.sleep,
                 modelo_fallback: str = "", reloj=time.monotonic):
        self.api_key = api_key
        self.modelo = modelo
        self.modelo_fallback = modelo_fallback
        self.session = session or requests.Session()
        self.timeout = timeout
        self.esperas = tuple(esperas)
        self._sleep = sleep
        self._reloj = reloj
        self._caido_hasta = 0.0

    # Después de una falla pasajera completa (los dos modelos, ~10-19 min de esperas), las llamadas
    # siguientes del mismo cliente fallan al toque durante este rato. Sin esto, una corrida diaria
    # con 15 clips y Gemini caído tenía la Pi ocupada horas; el reintento de una hora lo recupera.
    PAUSA_CAIDO_S = 15 * 60

    def json(self, sistema: str, prompt: str, schema: dict, temperatura: float = 0.7,
             imagenes: list[bytes] | None = None, audio: bytes | None = None) -> str:
        """Devuelve el texto crudo de la respuesta (debería ser JSON; lo valida quien llama).

        `imagenes`: JPEG en bytes, van en la misma llamada que el texto. Hacen falta porque el
        puntaje de calidad sacado solo de la transcripción castiga al humor visual: medido sobre 30
        clips, los marcados como "solo se entiende con la imagen" puntuaban 4,0 de mediana contra
        5,0 el resto, y tenían 1,60 palabras/s contra 2,45.

        `audio`: MP3 en bytes (el de /narrar, para que diga si hay música antes de poner la voz).
        """
        partes: list[dict] = [{"text": prompt}]
        for img in imagenes or []:
            partes.append({"inlineData": {"mimeType": "image/jpeg",
                                          "data": base64.b64encode(img).decode()}})
        if audio:
            partes.append({"inlineData": {"mimeType": "audio/mp3",
                                          "data": base64.b64encode(audio).decode()}})
        cuerpo = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
                "temperature": temperatura,
            },
        }
        if self._reloj() < self._caido_hasta:
            raise GeminiError("Gemini no responde (falló hace menos de 15 min; no insisto)",
                              pasajero=True)
        modelos = [self.modelo]
        if self.modelo_fallback and self.modelo_fallback != self.modelo:
            modelos.append(self.modelo_fallback)
        pasajero = False     # si ALGÚN modelo falló por algo pasajero, más tarde puede andar
        for n, modelo in enumerate(modelos):
            for intento in range(len(self.esperas) + 1):
                try:
                    r = self.session.post(
                        URL.format(modelo=modelo),
                        headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                        json=cuerpo,
                        timeout=self.timeout,
                    )
                except requests.RequestException as e:
                    r, error = None, str(e)
                else:
                    error = f"{r.status_code} {r.text[:300]}"
                if r is not None and r.status_code == 200:
                    return _texto(r.json())
                # 429 por cuota agotada (la del día) no se arregla reintentando: al otro modelo.
                sin_cuota = r is not None and r.status_code == 429 and "quota" in r.text.lower()
                if sin_cuota:
                    break
                reintentable = r is None or r.status_code >= 500 or r.status_code == 429
                if not reintentable:
                    raise GeminiError(f"Gemini ({modelo}): {error}")
                pasajero = True
                if intento < len(self.esperas):
                    log.warning("Gemini %s %s, reintento %d en %d s", modelo, error[:80],
                                intento + 1, self.esperas[intento])
                    self._sleep(self.esperas[intento])
            if n + 1 < len(modelos):
                log.warning("Gemini %s %s; sigo con %s", modelo,
                            "sin cuota" if sin_cuota else "no responde", modelos[n + 1])
        if pasajero:
            self._caido_hasta = self._reloj() + self.PAUSA_CAIDO_S
        raise GeminiError(f"Gemini ({modelo}): {error}", pasajero=pasajero)


def hablar(api_key: str, texto: str, instruccion: str = "", voz: str = "Puck",
           modelo: str = "gemini-3.8-flash-tts", session: requests.Session | None = None,
           timeout: float = 180) -> tuple[bytes, int]:
    """Gemini TTS: texto → PCM 16 bits mono y su frecuencia de muestreo. GASTA una request de la
    cuota diaria (por eso /narrar usa Piper; ver la comparación en settings.yaml → voz). La
    instrucción de tono va en el mismo texto ("Decilo con entusiasmo: …"), así lo pide la API."""
    import re

    cuerpo = {
        "contents": [{"parts": [{"text": f"{instruccion}\n\n{texto}" if instruccion else texto}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}},
        },
    }
    r = (session or requests.Session()).post(
        URL.format(modelo=modelo), json=cuerpo, timeout=timeout,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    if r.status_code != 200:
        raise GeminiError(f"Gemini TTS ({modelo}): {r.status_code} {r.text[:300]}")
    try:
        parte = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError, ValueError) as e:
        raise GeminiError(f"Gemini TTS sin audio: {r.text[:300]}") from e
    m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
    return base64.b64decode(parte["data"]), int(m.group(1)) if m else 24000


def _texto(respuesta: dict) -> str:
    try:
        cand = respuesta["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        motivo = (respuesta.get("promptFeedback") or {}).get("blockReason") or json.dumps(respuesta)[:300]
        raise GeminiError(f"Respuesta de Gemini sin texto: {motivo}") from None
