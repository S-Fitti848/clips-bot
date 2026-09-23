"""Cliente mínimo de Gemini (REST generateContent) con salida JSON forzada por schema."""

from __future__ import annotations

import json
import logging
import time

import requests

log = logging.getLogger(__name__)

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"


class GeminiError(RuntimeError):
    pass


class GeminiClient:
    def __init__(self, api_key: str, modelo: str, session: requests.Session | None = None,
                 timeout: float = 90, max_reintentos: int = 4, sleep=time.sleep):
        self.api_key = api_key
        self.modelo = modelo
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_reintentos = max_reintentos
        self._sleep = sleep

    def json(self, sistema: str, prompt: str, schema: dict, temperatura: float = 0.7) -> str:
        """Devuelve el texto crudo de la respuesta (debería ser JSON; lo valida quien llama)."""
        cuerpo = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": schema,
                "temperature": temperatura,
            },
        }
        intento = 0
        while True:
            try:
                r = self.session.post(
                    URL.format(modelo=self.modelo),
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
            # 429 por cuota agotada (la del día) no se arregla reintentando: cortar y avisar.
            reintentable = (r is None or r.status_code >= 500 or
                            (r.status_code == 429 and not sin_cuota))
            intento += 1
            if not reintentable or intento > self.max_reintentos:
                raise GeminiError(f"Gemini ({self.modelo}): {error}")
            log.warning("Gemini %s, reintento %d", error[:80], intento)
            self._sleep(10 * intento)  # 503 "overloaded" es común; la corrida diaria puede esperar


def _texto(respuesta: dict) -> str:
    try:
        cand = respuesta["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        motivo = (respuesta.get("promptFeedback") or {}).get("blockReason") or json.dumps(respuesta)[:300]
        raise GeminiError(f"Respuesta de Gemini sin texto: {motivo}") from None
