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

import hashlib
import json as _json
import logging
import time
from pathlib import Path

from .gemini import GeminiError, _llamador

log = logging.getLogger(__name__)

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
# US$ por millón de tokens (entrada, salida), precios de la API de Anthropic (2026-11).
PRECIOS = {SONNET: (2.00, 10.00), HAIKU: (0.10, 0.50)}
BETA_FALLBACK = "server-side-fallback-2026-07-01"
MAX_IMAGENES = 100        # tope de la API por pedido
# Caché de lo ya evaluado (Santi, 2026-11-15: "no pagar dos veces la misma foto"): un pedido CON
# imágenes idéntico a uno anterior (mismo modelo, sistema, prompt, schema e imágenes) devuelve la
# respuesta guardada. Solo con imágenes: los guiones tienen que poder salir distintos si se reintentan.
CACHE_DIAS = 30
MAX_TOKENS_TOPE = 64000   # el reintento de una respuesta cortada no pasa de acá


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
    """US$ del pedido. El modelo puede venir con versión ("claude-haiku-5-5-2026…"): se busca por nombre."""
    m = str(modelo or "")
    pe, ps = next((v for k, v in PRECIOS.items() if m.startswith(k)),
                  PRECIOS[HAIKU] if "haiku" in m else PRECIOS[SONNET])
    return (entrada * pe + salida * ps) / 1e6


# Para qué es cada función que llama a Claude (el informe de costo, 2026-11-13).
QUE_ES = {"textos.generar": "Rots: textos de los clips", "revision.revisar": "Rots: chequeo visual",
          "seleccion.desempatar": "Rots: desempate", "locales.clasificar": "Latinoamérica: clasificar (Haiku)",
          "locales.elegir": "Latinoamérica: elegir y puntuar", "efemerides.elegir": "Tecnología: elegir y puntuar",
          "efemerides.escribir_guion": "Guiones (Latinoamérica y tecnología)",
          "efemerides.final_que_paga": "Revisión del final", "efemerides.pedir": "Fotos (elegir y verificar)",
          "efemerides.elegir_fotos": "Fotos (elegir y verificar)",
          "efemerides.prefiltrar_fotos": "Fotos: primer filtro (Haiku)",
          "marcas.revisar_visual": "Animación: revisión visual", "marcas.chequear_calidad": "Animación: chequeo (Haiku)",
          "marcas.marcar_claves": "Animación: claves de subtítulos (Haiku)",
          "efemerides.acortar_guion": "Acortar guion",
          "marcas.elegir": "Animación: elegir y puntuar la marca", "marcas.escribir_guion": "Animación: guion"}


ORIGENES = (("produccion", "Producción (lo que el bot hace solo)"),
            ("a_mano", "A mano por Telegram (✏️, 🔁, /efemeride, /historia…)"),
            ("prueba", "Pruebas y rehechos (scripts y comandos a mano)"))


def resumen_costo(conn, dia: str, origen: str | None = None) -> tuple[float, list[tuple[str, int, float]]]:
    """(US$ total, [(qué es, pedidos, US$)]) de Claude en el día `dia` (AR, AAAA-MM-DD), de gemini_uso.
    `origen`: solo ese (produccion | a_mano | prueba; "" = filas anteriores al 2026-11-15)."""
    por: dict[str, list] = {}
    sql = "SELECT funcion, modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND dia = ?"
    params: tuple = (dia,)
    if origen is not None:
        sql += " AND origen = ?"
        params += (origen,)
    for funcion, modelo, entrada, salida in conn.execute(sql, params):
        k = QUE_ES.get(funcion, funcion)
        x = por.setdefault(k, [0, 0.0])
        x[0] += 1
        x[1] += costo(modelo, entrada or 0, salida or 0)
    filas = sorted(((k, n, round(c, 4)) for k, (n, c) in por.items()), key=lambda r: -r[2])
    return round(sum(c for _, _, c in filas), 4), filas


# Presupuesto (Santi, 2026-11-15): el crédito es de US$ 100 por mes y se renueva; el tope propio es ~US$ 80.
PRESUPUESTO_MES = 80.0
AVISO_MES = (0.75, 1.0)     # avisa al pasar el 75 % y al llegar al 100 % del tope (una vez cada uno)


def costo_mes(conn, mes: str) -> float:
    """US$ de Claude en el mes `mes` (AAAA-MM), todos los orígenes."""
    total = 0.0
    for modelo, entrada, salida in conn.execute(
            "SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND dia LIKE ?", (mes + "-%",)):
        total += costo(modelo, entrada or 0, salida or 0)
    return round(total, 2)


def proyeccion_mes(gastado: float, dia: str) -> float:
    """Lo que se gastaría en el mes a este ritmo (`dia` = el último día contado, AAAA-MM-DD)."""
    import calendar

    a, m, d = (int(x) for x in dia.split("-"))
    return round(gastado / max(1, d) * calendar.monthrange(a, m)[1], 2)


def texto_costo(conn, dia: str) -> str:
    """El informe del día, separado por origen (Santi, 2026-11-15): la producción normal arriba, con su
    proyección por mes; lo hecho a mano y las pruebas aparte, para que no inflen la cuenta."""
    total, _ = resumen_costo(conn, dia)
    prod, filas = resumen_costo(conn, dia, "produccion")
    lineas = [f"🔧 Claude Code: <b>Costo de Claude del {dia[8:10]}/{dia[5:7]}</b>: US$ {total:.2f} en total",
              "",
              f"<b>Producción</b>: US$ {prod:.2f} (≈ US$ {prod * 30:.0f} por mes a este ritmo)"]
    lineas += [f"• {k}: US$ {c:.3f} ({n} pedido{'s' if n != 1 else ''})" for k, n, c in filas]
    for clave, nombre in ORIGENES[1:] + (("", "Sin origen anotado (antes del 15/11)"),):
        sub, filas = resumen_costo(conn, dia, clave)
        if not filas:
            continue
        lineas += ["", f"<b>{nombre}</b>: US$ {sub:.2f}"]
        lineas += [f"• {k}: US$ {c:.3f} ({n})" for k, n, c in filas]
    mes = costo_mes(conn, dia[:7])
    lineas += ["", f"<b>En el mes</b>: US$ {mes:.2f} de US$ {PRESUPUESTO_MES:.0f} "
                   f"(a este ritmo, ≈ US$ {proyeccion_mes(mes, dia):.0f} al cerrar el mes)"]
    return "\n".join(lineas)


class ClaudeClient:
    def __init__(self, api_key: str, modelo: str = SONNET, cliente=None, uso=None,
                 max_tokens: int = 16000, esfuerzo: str | None = None, timeout: float = 300,
                 cache_dir=None):
        import anthropic

        self.cache_dir = Path(cache_dir) if cache_dir else None
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
        clave_cache = self._clave_cache(modelo, sistema, prompt, schema, imagenes)
        guardado = self._de_cache(clave_cache)
        if guardado is not None:
            log.info("Claude %s para %s: de la caché (US$ 0)", modelo, funcion)
            if self.uso:
                self.uso(funcion, modelo, "claude", 0, 0, True)
            return guardado
        contenido = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": base64.standard_b64encode(img).decode()}}
                     for img in imagenes or []]
        contenido.append({"type": "text", "text": prompt})
        # Si la respuesta se corta (max_tokens: el 15/11 el guion de Así Nació pidió 16.000 y no entró), se
        # reintenta UNA vez con el doble de límite (hasta MAX_TOKENS_TOPE) antes de rendirse.
        limites = [self.max_tokens] + ([min(MAX_TOKENS_TOPE, self.max_tokens * 2)]
                                       if self.max_tokens < MAX_TOKENS_TOPE else [])
        for n_lim, limite in enumerate(limites):
            pedido = dict(model=modelo, max_tokens=limite, system=sistema,
                          messages=[{"role": "user", "content": contenido if imagenes else prompt}],
                          output_config={"format": {"type": "json_schema", "schema": a_json_schema(schema)},
                                         **({"effort": self.esfuerzo} if self.esfuerzo else {})})
            try:
                r = self._pedir(pedido, modelo, limite)
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
            if r.stop_reason != "max_tokens":
                break
            if n_lim + 1 < len(limites):
                log.warning("Claude %s para %s: se cortó con %d tokens, reintento con %d", modelo, funcion,
                            limite, limites[n_lim + 1])
        if r.stop_reason == "refusal":
            raise ClaudeError(f"Claude ({modelo}) no quiso responder")
        if r.stop_reason == "max_tokens":
            raise ClaudeError(f"Claude ({modelo}): la respuesta se cortó (max_tokens {limites[-1]})")
        texto = next((b.text for b in r.content if b.type == "text"), "")
        if not texto:
            raise ClaudeError(f"Claude ({modelo}): respuesta sin texto")
        self._a_cache(clave_cache, texto)
        return texto

    def _pedir(self, pedido: dict, modelo: str, limite: int):
        """Un pedido. Con límites grandes va por streaming (la API no deja pedidos largos sin stream)."""
        extra = dict(betas=[BETA_FALLBACK], fallbacks="default") if modelo == SONNET else {}
        api = self._c.beta.messages if modelo == SONNET else self._c.messages
        if limite > 16000 and hasattr(api, "stream"):
            with api.stream(**pedido, **extra) as st:
                return st.get_final_message()
        return api.create(**pedido, **extra)

    def _clave_cache(self, modelo, sistema, prompt, schema, imagenes) -> str | None:
        if not self.cache_dir or not imagenes:
            return None
        h = hashlib.sha256(_json.dumps([modelo, self.esfuerzo, sistema, prompt, schema], sort_keys=True,
                                       ensure_ascii=False).encode())
        for img in imagenes:
            h.update(hashlib.sha256(img).digest())
        return h.hexdigest()

    def _de_cache(self, clave: str | None) -> str | None:
        if not clave:
            return None
        f = self.cache_dir / f"{clave}.json"
        try:
            if time.time() - f.stat().st_mtime > CACHE_DIAS * 86400:
                return None
            return _json.loads(f.read_text(encoding="utf-8"))["texto"]
        except (OSError, ValueError, KeyError):
            return None

    def _a_cache(self, clave: str | None, texto: str) -> None:
        if not clave:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{clave}.json").write_text(_json.dumps({"texto": texto}, ensure_ascii=False),
                                                         encoding="utf-8")
            limite = time.time() - CACHE_DIAS * 86400
            for viejo in self.cache_dir.glob("*.json"):
                if viejo.stat().st_mtime < limite:
                    viejo.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Claude: no pude guardar en la caché: %s", e)


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


def cliente(modelo: str = SONNET, esfuerzo: str | None = None, max_tokens: int = 16000) -> ClaudeClient | None:
    """Con ANTHROPIC_API_KEY del .env; None si no está."""
    from .config import env
    from .gemini import registrar_uso

    from .config import DATA_DIR

    clave = env("ANTHROPIC_API_KEY", requerido=False)
    if not clave:
        return None
    return ClaudeClient(clave, modelo, uso=registrar_uso, esfuerzo=esfuerzo, max_tokens=max_tokens,
                        cache_dir=DATA_DIR / "cache_claude")
