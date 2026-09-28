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
    pass


class GeminiClient:
    """Cliente de Gemini con fallback de modelo cuando se acaba la cuota.

    El free tier de los modelos Flash está en ~20 requests por día (bajó de 250), y resetea a
    medianoche hora del Pacífico. Con 3 clips/día y UNA llamada por clip entramos cómodos; los que
    queman la cuota son los reintentos y las pruebas. Por eso: ante un 429 por cuota se pasa una vez
    al modelo de fallback (flash-lite, que tiene su propia cuota) en vez de reintentar el mismo.
    """

    def __init__(self, api_key: str, modelo: str, session: requests.Session | None = None,
                 timeout: float = 90, max_reintentos: int = 4, sleep=time.sleep,
                 modelo_fallback: str = ""):
        self.api_key = api_key
        self.modelo = modelo
        self.modelo_fallback = modelo_fallback
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_reintentos = max_reintentos
        self._sleep = sleep

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
        intento = 0
        modelo = self.modelo
        while True:
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
            sin_cuota = r is not None and r.status_code == 429 and "quota" in r.text.lower()
            if sin_cuota and self.modelo_fallback and modelo != self.modelo_fallback:
                # Sin cuota en el modelo principal: se pasa al de fallback, que tiene la suya.
                log.warning("Gemini %s sin cuota; sigo con %s", modelo, self.modelo_fallback)
                modelo = self.modelo_fallback
                continue
            # 429 por cuota agotada (la del día) no se arregla reintentando: cortar y avisar.
            reintentable = (r is None or r.status_code >= 500 or
                            (r.status_code == 429 and not sin_cuota))
            intento += 1
            if not reintentable or intento > self.max_reintentos:
                raise GeminiError(f"Gemini ({modelo}): {error}")
            log.warning("Gemini %s, reintento %d", error[:80], intento)
            self._sleep(10 * intento)  # 503 "overloaded" es común; la corrida diaria puede esperar


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
