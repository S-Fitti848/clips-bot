"""Texto con Claude (pedido de Santi, 2026-11-09: "dejá de depender del cupo de Gemini"). Hoy lo usa
el video de Pequeña Historia para Facebook (`locales.py`): Sonnet elige el hecho y escribe el guion,
Haiku clasifica los candidatos. Gemini queda para lo que mira imágenes (las fotos) y para la voz.

Misma forma que `GeminiClient.json` (sistema, prompt, schema → texto JSON), así las funciones de
efemerides.py que reciben un `cliente` sirven con cualquiera de los dos. El schema viene en el formato
de Gemini ("OBJECT", "STRING"…) y se pasa a JSON Schema para las salidas estructuradas de Claude
(`output_config.format`), que garantizan JSON válido con esa forma.

Cada llamada se anota en la tabla `gemini_uso` (misma tabla, `clave` = "claude") con los tokens: de
ahí sale el costo por día. Ante un rechazo del modelo principal, Sonnet sigue en el de respaldo que
elige la API (`fallbacks: "default"`)."""

from __future__ import annotations

import logging

from .gemini import GeminiError, _llamador

log = logging.getLogger(__name__)

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
# US$ por millón de tokens (entrada, salida), precios de la API de Anthropic (2026-11).
PRECIOS = {SONNET: (2.00, 10.00), HAIKU: (0.10, 0.50)}
BETA_FALLBACK = "server-side-fallback-2026-07-01"
MAX_IMAGENES = 100        # tope de la API por pedido


class ClaudeError(GeminiError):
    """Hereda de GeminiError para que lo atrapen los mismos `except` del flujo de efemérides."""


_TIPOS = {"OBJECT": "object", "ARRAY": "array", "STRING": "string", "INTEGER": "integer",
          "NUMBER": "number", "BOOLEAN": "boolean"}


def a_json_schema(s: dict) -> dict:
    """El schema de Gemini → JSON Schema: tipos en minúscula y objetos cerrados
    (`additionalProperties: false`, lo piden las salidas estructuradas)."""
    out: dict = {}
    t = s.get("type")
    if t:
        out["type"] = _TIPOS.get(str(t).upper(), str(t).lower())
    if "enum" in s:
        out["enum"] = list(s["enum"])
    if "description" in s:
        out["description"] = s["description"]
    if "items" in s:
        out["items"] = a_json_schema(s["items"])
    if "properties" in s:
        out["properties"] = {k: a_json_schema(v) for k, v in s["properties"].items()}
        out["required"] = list(s.get("required") or [])
        out["additionalProperties"] = False
    return out


def costo(modelo: str, entrada: int, salida: int) -> float:
    pe, ps = PRECIOS.get(modelo, PRECIOS[SONNET])
    return (entrada * pe + salida * ps) / 1e6


class ClaudeClient:
    def __init__(self, api_key: str, modelo: str = SONNET, cliente=None, uso=None,
                 max_tokens: int = 16000, esfuerzo: str | None = None, timeout: float = 300):
        import anthropic

        self.modelo = modelo
        self.uso = uso
        self.max_tokens = max_tokens
        self.esfuerzo = esfuerzo
        self._c = cliente or anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=3)

    def json(self, sistema: str, prompt: str, schema: dict, temperatura: float = 0.7,
             imagenes: list[bytes] | None = None, audio: bytes | None = None,
             modelo: str | None = None) -> str:
        """El texto JSON de la respuesta. `temperatura` se ignora (los modelos actuales no la
        aceptan). `imagenes`: JPEG, van antes del texto en el orden en que vienen (desde el
        2026-11-10 Sonnet elige y verifica las fotos de Pequeña Historia). El audio sigue en Gemini."""
        import anthropic
        import base64

        if audio:
            raise ClaudeError("Claude acá no recibe audio: eso va con Gemini")
        if imagenes and len(imagenes) > MAX_IMAGENES:
            raise ClaudeError(f"Claude: {len(imagenes)} imágenes (máximo {MAX_IMAGENES} por pedido)")
        modelo = modelo or self.modelo
        funcion = _llamador()
        contenido = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": base64.standard_b64encode(img).decode()}}
                     for img in imagenes or []]
        contenido.append({"type": "text", "text": prompt})
        pedido = dict(model=modelo, max_tokens=self.max_tokens, system=sistema,
                      messages=[{"role": "user", "content": contenido if imagenes else prompt}],
                      output_config={"format": {"type": "json_schema", "schema": a_json_schema(schema)},
                                     **({"effort": self.esfuerzo} if self.esfuerzo else {})})
        try:
            if modelo == SONNET:
                r = self._c.beta.messages.create(**pedido, betas=[BETA_FALLBACK], fallbacks="default")
            else:
                r = self._c.messages.create(**pedido)
        except anthropic.RateLimitError as e:
            raise ClaudeError(f"Claude ({modelo}): límite de uso ({e.message})", pasajero=True) from e
        except anthropic.APIStatusError as e:
            raise ClaudeError(f"Claude ({modelo}): {e.status_code} {e.message}",
                              pasajero=e.status_code >= 500) from e
        except anthropic.APIConnectionError as e:
            raise ClaudeError(f"Claude ({modelo}): sin conexión ({e})", pasajero=True) from e
        entrada, salida = r.usage.input_tokens, r.usage.output_tokens
        log.info("Claude %s para %s (%d + %d tokens, US$ %.4f)", r.model, funcion, entrada, salida,
                 costo(modelo, entrada, salida))
        if self.uso:
            self.uso(funcion, r.model, "claude", entrada, salida, False)
        if r.stop_reason == "refusal":
            raise ClaudeError(f"Claude ({modelo}) no quiso responder")
        if r.stop_reason == "max_tokens":
            raise ClaudeError(f"Claude ({modelo}): la respuesta se cortó (max_tokens)")
        texto = next((b.text for b in r.content if b.type == "text"), "")
        if not texto:
            raise ClaudeError(f"Claude ({modelo}): respuesta sin texto")
        return texto


class ConRespaldo:
    """Texto con Claude y Gemini SOLO si Claude falla o hace falta audio (Santi, 2026-11-12: "que
    madrugar no empeore la calidad": a las 03:30 la cuota gratis de Gemini ya está gastada). Misma
    forma que GeminiClient.json."""

    def __init__(self, principal, respaldo=None):
        self.principal, self.respaldo = principal, respaldo
        self.modelo = getattr(principal, "modelo", None)

    def json(self, sistema: str, prompt: str, schema: dict, temperatura: float = 0.7,
             imagenes: list[bytes] | None = None, audio: bytes | None = None,
             modelo: str | None = None) -> str:
        if audio is None and self.principal is not None:
            try:
                return self.principal.json(sistema, prompt, schema, temperatura, imagenes=imagenes)
            except GeminiError as e:
                if self.respaldo is None:
                    raise
                log.warning("Claude no respondió (%s): uso Gemini", str(e)[:120])
        if self.respaldo is None:
            raise ClaudeError("sin Claude ni Gemini para este pedido")
        return self.respaldo.json(sistema, prompt, schema, temperatura, imagenes=imagenes, audio=audio)


def para_texto(gemini, modelo: str = SONNET, esfuerzo: str | None = None):
    """El cliente de texto: Claude (`modelo`) con Gemini de respaldo; sin ANTHROPIC_API_KEY, Gemini."""
    c = cliente(modelo, esfuerzo)
    return ConRespaldo(c, gemini) if c is not None else gemini


def cliente(modelo: str = SONNET, esfuerzo: str | None = None) -> ClaudeClient | None:
    """Con ANTHROPIC_API_KEY del .env; None si no está."""
    from .config import env
    from .gemini import registrar_uso

    clave = env("ANTHROPIC_API_KEY", requerido=False)
    if not clave:
        return None
    return ClaudeClient(clave, modelo, uso=registrar_uso, esfuerzo=esfuerzo)
