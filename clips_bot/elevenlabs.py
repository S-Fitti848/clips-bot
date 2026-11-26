"""ElevenLabs: la voz de Tito y los efectos de sonido de Así Nació (Santi, 2026-11-15).

- Voz: SOLO Así Nació (`animacion.elevenlabs_voz`). Pequeña Historia y Lo Encontré siguen con Gemini gratis
  (Santi, 2026-11-15): `efemerides.voz_efemeride` usa ElevenLabs solo si quien llama le pasa la config de Así
  Nació. Si falta la clave o la voz, o la llamada falla (sin créditos, caída), sigue la voz de siempre.
- Efectos: `animacion/sfx.py` los genera UNA vez con la API de efectos y los guarda; después se reusan.
- Créditos: cada pedido se anota en `elevenlabs_uso` (tipo, créditos, origen) y el ciclo de la suscripción
  se lee de `/v1/user/subscription`: /costos lo muestra y la escucha avisa al 75 % y al 100 %.

API: POST /v1/text-to-speech/{voice_id} y /v1/sound-generation con `xi-api-key`; la clave sale del .env
(ELEVENLABS_API_KEY, nunca en el código). Cobra por carácter (voz) y por segundo (efectos)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

API = "https://api.elevenlabs.io/v1"
FORMATO = "pcm_24000"          # PCM 16 bits mono a 24 kHz (el de 44,1 kHz pide un plan más caro)
SR = 24000
MODELO_EFECTOS = "eleven_text_to_sound_v3"
CREDITOS_POR_SEGUNDO_EFECTO = 40   # si la respuesta no trae el costo (lo dice la doc de precios)
AVISO_CICLO = (0.75, 1.0)          # avisos a Santi sobre los créditos del ciclo (Santi, 2026-11-15)


class ElevenLabsError(RuntimeError):
    pass


def clave() -> str:
    from .config import env

    return env("ELEVENLABS_API_KEY", requerido=False) or ""


def lista(cfg) -> bool:
    """¿Está todo para usarla? (la clave en el .env y la voz elegida en settings)."""
    return bool(cfg is not None and clave() and getattr(cfg, "elevenlabs_voz", ""))


def _costo(r, defecto: int) -> int:
    """Los créditos que cobró el pedido: la respuesta los trae en un encabezado (`character-cost` en la voz);
    si no está, la estimación."""
    for h in ("character-cost", "x-character-count", "credits-used"):
        v = (getattr(r, "headers", None) or {}).get(h)
        if v and str(v).isdigit():
            return int(v)
    return defecto


def anotar(tipo: str, creditos: int, detalle: str = "") -> None:
    """Una fila en `elevenlabs_uso`. Nunca tumba el pedido."""
    from . import db
    from .config import DB_PATH
    from .gemini import origen_actual

    try:
        conn = db.connect(DB_PATH)
        try:
            db.anotar_elevenlabs(conn, tipo, creditos, detalle, origen=origen_actual())
        finally:
            conn.close()
    except Exception as e:     # noqa: BLE001 — medir no puede romper lo que se mide
        log.warning("ElevenLabs: no pude anotar el uso: %s", e)


def hablar(texto: str, voz: str, modelo: str, api_key: str | None = None, estabilidad: float = 0.45,
           parecido: float = 0.8, estilo: float = 0.3, sesion=None, timeout: float = 180) -> tuple[bytes, int]:
    """(PCM 16 bits mono, frecuencia) de todo el texto en una llamada."""
    api_key = api_key or clave()
    if not api_key:
        raise ElevenLabsError("falta ELEVENLABS_API_KEY en el .env")
    if not voz:
        raise ElevenLabsError("falta elevenlabs_voz (el id de la voz)")
    ajustes = {"stability": estabilidad, "similarity_boost": parecido}
    if not modelo.startswith("eleven_v4"):        # v4 solo acepta estabilidad y parecido
        ajustes.update(style=estilo, use_speaker_boost=True)
    cuerpo = {"text": texto, "model_id": modelo, "voice_settings": ajustes}
    if modelo != "eleven_multilingual_v2":         # ese modelo no acepta language_code
        cuerpo["language_code"] = "es"
    s = sesion or requests
    try:
        r = s.post(f"{API}/text-to-speech/{voz}", params={"output_format": FORMATO},
                   headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                   json=cuerpo, timeout=timeout)
    except requests.RequestException as e:
        raise ElevenLabsError(f"ElevenLabs no respondió: {e}") from e
    if r.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    if len(r.content) < SR:      # menos de medio segundo de audio: algo salió mal
        raise ElevenLabsError("ElevenLabs devolvió un audio vacío")
    creditos = _costo(r, len(texto))
    anotar("voz", creditos, voz)
    log.info("ElevenLabs: %d caracteres (%d créditos) → %.1f s", len(texto), creditos, len(r.content) / 2 / SR)
    return r.content, SR


def efecto(texto: str, duracion: float | None = None, influencia: float = 0.5, nombre: str = "",
           api_key: str | None = None, sesion=None, timeout: float = 120) -> bytes:
    """Un efecto de sonido (mp3 44,1 kHz) a partir de su descripción."""
    api_key = api_key or clave()
    if not api_key:
        raise ElevenLabsError("falta ELEVENLABS_API_KEY en el .env")
    cuerpo = {"text": texto, "model_id": MODELO_EFECTOS, "prompt_influence": influencia}
    if duracion:
        cuerpo["duration_seconds"] = max(0.5, min(30.0, float(duracion)))
    try:
        r = (sesion or requests).post(f"{API}/sound-generation", params={"output_format": "mp3_44100_128"},
                                      headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                                      json=cuerpo, timeout=timeout)
    except requests.RequestException as e:
        raise ElevenLabsError(f"ElevenLabs no respondió: {e}") from e
    if r.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    if len(r.content) < 1000:
        raise ElevenLabsError("ElevenLabs devolvió un efecto vacío")
    creditos = _costo(r, round(CREDITOS_POR_SEGUNDO_EFECTO * (duracion or 5)))
    anotar("efecto", creditos, nombre or texto[:40])
    log.info("ElevenLabs: efecto %s (%d créditos)", nombre or texto[:40], creditos)
    return r.content


def suscripcion(api_key: str | None = None, sesion=None) -> dict:
    """{usados, limite, reinicio (datetime UTC), plan} del ciclo actual de la cuenta."""
    api_key = api_key or clave()
    if not api_key:
        raise ElevenLabsError("falta ELEVENLABS_API_KEY en el .env")
    try:
        r = (sesion or requests).get(f"{API}/user/subscription", headers={"xi-api-key": api_key}, timeout=30)
    except requests.RequestException as e:
        raise ElevenLabsError(f"ElevenLabs no respondió: {e}") from e
    if r.status_code != 200:
        raise ElevenLabsError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    d = r.json()
    reinicio = d.get("next_character_count_reset_unix")
    return {"usados": int(d.get("character_count") or 0), "limite": int(d.get("character_limit") or 0),
            "reinicio": datetime.fromtimestamp(int(reinicio), timezone.utc) if reinicio else None,
            "plan": d.get("tier") or ""}


def miles(n: int) -> str:
    """12345 → "12.345"."""
    return f"{int(n or 0):,}".replace(",", ".")


def texto_creditos(conn, mes: str, sub: dict | None) -> str:
    """El bloque de ElevenLabs para /costos: el ciclo de la cuenta y lo anotado en el mes, por tipo y origen."""
    from . import db

    lineas = ["", "<b>ElevenLabs</b>"]
    if sub and sub.get("limite"):
        pct = sub["usados"] / sub["limite"]
        hasta = sub["reinicio"].astimezone().strftime("%d/%m") if sub.get("reinicio") else "?"
        lineas.append(f"Ciclo ({sub.get('plan') or 'plan'}, se renueva el {hasta}): "
                      f"{miles(sub['usados'])} de {miles(sub['limite'])} créditos ({pct:.0%})")
    elif sub is None:
        lineas.append("Ciclo: no pude leer la cuenta")
    filas = db.uso_elevenlabs_mes(conn, mes)
    if not filas:
        lineas.append(f"{mes}: nada usado")
    else:
        total = sum(f[3] or 0 for f in filas)
        lineas.append(f"{mes}: {miles(total)} créditos")
        nombres = {"voz": "voces", "efecto": "efectos"}
        for tipo, origen, n, cr in filas:
            lineas.append(f"  · {nombres.get(tipo, tipo)} ({origen or '?'}): {n} pedidos, {miles(cr)} créditos")
    return "\n".join(lineas)


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
