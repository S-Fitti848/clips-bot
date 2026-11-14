"""Voz de Pequeña Historia con ElevenLabs (Santi, 2026-11-14: "dejalo preparado; la clave la pongo yo
en el .env cuando elija voz; mientras tanto, sigue la actual").

Se usa SOLO si están las dos cosas: `ELEVENLABS_API_KEY` en el .env y `efemerides.elevenlabs_voz` (el
id de la voz) en settings. Si falta alguna, o la llamada falla, sigue la voz de siempre (Gemini y
Piper de respaldo). Pide PCM crudo (sin mp3 en el medio) y se pasa a 48 kHz como las otras voces.

API: POST /v1/text-to-speech/{voice_id}?output_format=pcm_24000 con `xi-api-key`; GET /v1/voices
para listar las voces de la cuenta (`python -m clips_bot voces-elevenlabs`). Cobra por carácter."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

API = "https://api.elevenlabs.io/v1"
FORMATO = "pcm_24000"          # PCM 16 bits mono a 24 kHz (el de 44,1 kHz pide un plan más caro)
SR = 24000


class ElevenLabsError(RuntimeError):
    pass


def clave() -> str:
    from .config import env

    return env("ELEVENLABS_API_KEY", requerido=False) or ""


def lista(cfg) -> bool:
    """¿Está todo para usarla? (la clave en el .env y la voz elegida en settings)."""
    return bool(clave() and getattr(cfg, "elevenlabs_voz", ""))


def hablar(texto: str, voz: str, modelo: str, api_key: str | None = None, estabilidad: float = 0.45,
           parecido: float = 0.8, estilo: float = 0.3, sesion=None, timeout: float = 180) -> tuple[bytes, int]:
    """(PCM 16 bits mono, frecuencia) de todo el texto en una llamada."""
    api_key = api_key or clave()
    if not api_key:
        raise ElevenLabsError("falta ELEVENLABS_API_KEY en el .env")
    if not voz:
        raise ElevenLabsError("falta efemerides.elevenlabs_voz (el id de la voz)")
    s = sesion or requests
    try:
        r = s.post(f"{API}/text-to-speech/{voz}", params={"output_format": FORMATO},
                   headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                   json={"text": texto, "model_id": modelo, "language_code": "es",
                         "voice_settings": {"stability": estabilidad, "similarity_boost": parecido,
                                            "style": estilo, "use_speaker_boost": True}},
                   timeout=timeout)
    except requests.RequestException as e:
        raise ElevenLabsError(f"ElevenLabs no respondió: {e}") from e
    if r.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    if len(r.content) < SR:      # menos de medio segundo de audio: algo salió mal
        raise ElevenLabsError("ElevenLabs devolvió un audio vacío")
    log.info("ElevenLabs: %d caracteres → %.1f s", len(texto), len(r.content) / 2 / SR)
    return r.content, SR


def voces(api_key: str | None = None, sesion=None) -> list[dict]:
    """[{id, nombre, idioma, descripción}] de las voces de la cuenta (las propias y las agregadas)."""
    api_key = api_key or clave()
    if not api_key:
        raise ElevenLabsError("falta ELEVENLABS_API_KEY en el .env")
    r = (sesion or requests).get(f"{API}/voices", headers={"xi-api-key": api_key}, timeout=60)
    if r.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    out = []
    for v in r.json().get("voices", []):
        etiquetas = v.get("labels") or {}
        out.append({"id": v.get("voice_id", ""), "nombre": v.get("name", ""),
                    "idioma": etiquetas.get("language") or etiquetas.get("accent") or "",
                    "descripcion": etiquetas.get("description") or v.get("description") or ""})
    return out
