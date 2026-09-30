"""Cliente mínimo de Gemini (REST generateContent) con salida JSON forzada por schema."""

from __future__ import annotations

import json
import base64
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone

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

# Dos claves (pedido 2026-09-29): siempre la principal; la segunda SOLO cuando la principal se
# quedó sin la cuota del día (429 de cuota), y recién después de las dos, el modelo de respaldo.
PRINCIPAL, SEGUNDA = "principal", "segunda"
VARIABLES = ((PRINCIPAL, "GEMINI_API_KEY"), (SEGUNDA, "GEMINI_API_KEY_2"))
CLAVE_INVALIDA = "gemini_clave_invalida"      # bot_estado: {nombre: huella de la clave inválida}
CLAVE_SEGUNDA_DIA = "gemini_segunda_dia"      # bot_estado: día (AR) en que ya se avisó el uso


def huella(clave: str) -> str:
    """Para reconocer la clave sin guardarla: si Santi la cambia, la huella cambia y se vuelve a probar."""
    return hashlib.sha256(clave.encode()).hexdigest()[:12]


def _dia_pacifico() -> str:
    """La cuota diaria de Gemini se renueva a la medianoche del Pacífico (UTC-7 en verano)."""
    return (datetime.now(timezone.utc) - timedelta(hours=7)).date().isoformat()


def es_clave_invalida(status: int, texto: str) -> bool:
    t = texto.lower()
    # 401 "invalid authentication credentials": lo que devuelve con una clave que no es de AI
    # Studio (medido 2026-09-29 con una de 53 caracteres que no empieza con "AIza").
    return status in (400, 401, 403) and ("api_key_invalid" in t or "api key not valid" in t
                                          or "api key expired" in t or "permission_denied" in t
                                          or "invalid authentication credentials" in t
                                          or "unauthenticated" in t)


def es_sin_cuota(status: int, texto: str) -> bool:
    return status == 429 and "quota" in texto.lower()


def claves(conn=None) -> list[tuple[str, str]]:
    """[(nombre, clave)] del .env, sin la segunda si ya se sabe que es inválida (misma huella)."""
    from .config import env

    invalidas = {}
    if conn is not None:
        from . import db

        invalidas = json.loads(db.get_valor(conn, CLAVE_INVALIDA) or "{}")
    out = []
    for nombre, var in VARIABLES:
        k = env(var, requerido=False)
        if not k or any(k == c for _, c in out):
            continue
        if nombre != PRINCIPAL and invalidas.get(nombre) == huella(k):
            log.info("Gemini: la clave %s es inválida (ya avisado): la ignoro", nombre)
            continue
        out.append((nombre, k))
    return out


def claves_activas() -> list[tuple[str, str]]:
    from . import db
    from .config import DB_PATH

    conn = db.connect(DB_PATH)
    try:
        return claves(conn)
    finally:
        conn.close()


def aviso_por_telegram(evento: str, nombre: str, clave: str, detalle: str = "") -> None:
    """Lo que Santi tiene que saber de las claves, por Telegram (TELEGRAM_CHAT_ID):
    "segunda" = la primera vez del día que se usa la segunda; "invalida" = la segunda no sirve
    (se anota su huella y no se vuelve a probar hasta que cambie). Nunca tumba la llamada."""
    from . import db
    from .config import DB_PATH, env

    try:
        conn = db.connect(DB_PATH)
        try:
            if evento == "segunda":
                hoy = datetime.now(timezone(timedelta(hours=-3))).date().isoformat()
                if db.get_valor(conn, CLAVE_SEGUNDA_DIA) == hoy:
                    return
                db.set_valor(conn, CLAVE_SEGUNDA_DIA, hoy)
                texto = ("🔑 Gemini: la clave principal se quedó sin la cuota de hoy; "
                         "sigo con la segunda (GEMINI_API_KEY_2).")
            elif evento == "invalida":
                inv = json.loads(db.get_valor(conn, CLAVE_INVALIDA) or "{}")
                inv[nombre] = huella(clave)
                db.set_valor(conn, CLAVE_INVALIDA, json.dumps(inv))
                texto = (f"⚠️ Gemini: la clave {nombre} (GEMINI_API_KEY_2) es inválida y la ignoro. "
                         f"Revisala en AI Studio y cambiala en el .env. ({detalle[:120]})")
            else:
                return
        finally:
            conn.close()
        from .telegram import TelegramClient

        chat = env("TELEGRAM_CHAT_ID", requerido=False)
        if chat:
            TelegramClient(env("TELEGRAM_BOT_TOKEN")).send_message(chat, texto)
    except Exception as e:     # un aviso que falla no puede tumbar los textos del clip
        log.warning("Gemini: no pude avisar %s: %s", evento, e)


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

    def __init__(self, api_key, modelo: str, session: requests.Session | None = None,
                 timeout: float = 90, esperas: tuple = ESPERAS_PASAJERO, sleep=time.sleep,
                 modelo_fallback: str = "", reloj=time.monotonic, aviso=None):
        # `api_key`: una clave, o [(nombre, clave)] en orden (principal, segunda).
        self.claves = [(PRINCIPAL, api_key)] if isinstance(api_key, str) else list(api_key)
        self.api_key = self.claves[0][1]
        self.aviso = aviso or (lambda *a, **k: None)
        self._sin_cuota: dict[tuple[str, str], str] = {}   # (modelo, clave) -> día del Pacífico
        self._invalidas: set[str] = set()
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
        error, sin_cuota = "sin claves válidas", False
        hoy = _dia_pacifico()
        for n, modelo in enumerate(modelos):
            # Por modelo, las claves en orden: la segunda solo si la principal está sin cuota.
            for nombre, clave in self.claves:
                if nombre in self._invalidas or self._sin_cuota.get((modelo, nombre)) == hoy:
                    continue
                sin_cuota = caido = False
                for intento in range(len(self.esperas) + 1):
                    try:
                        r = self.session.post(
                            URL.format(modelo=modelo),
                            headers={"x-goog-api-key": clave, "Content-Type": "application/json"},
                            json=cuerpo,
                            timeout=self.timeout,
                        )
                    except requests.RequestException as e:
                        r, error = None, str(e)
                    else:
                        error = f"{r.status_code} {r.text[:300]}"
                    if r is not None and r.status_code == 200:
                        log.info("Gemini %s con la clave %s", modelo, nombre)
                        if nombre != PRINCIPAL:
                            self.aviso("segunda", nombre, clave)
                        return _texto(r.json())
                    # 429 por cuota agotada (la del día) no se arregla reintentando: otra clave
                    # y, si no hay, el otro modelo.
                    if r is not None and es_sin_cuota(r.status_code, r.text):
                        sin_cuota = True
                        self._sin_cuota[(modelo, nombre)] = hoy
                        log.warning("Gemini %s: la clave %s sin cuota del día", modelo, nombre)
                        break
                    if r is not None and nombre != PRINCIPAL and es_clave_invalida(r.status_code, r.text):
                        log.warning("Gemini: la clave %s es inválida (%s): la ignoro", nombre, error[:80])
                        self._invalidas.add(nombre)
                        self.aviso("invalida", nombre, clave, error)
                        break
                    reintentable = r is None or r.status_code >= 500 or r.status_code == 429
                    if not reintentable:
                        raise GeminiError(f"Gemini ({modelo}): {error}")
                    pasajero = caido = True
                    if intento < len(self.esperas):
                        log.warning("Gemini %s %s, reintento %d en %d s", modelo, error[:80],
                                    intento + 1, self.esperas[intento])
                        self._sleep(self.esperas[intento])
                if caido:     # el modelo no responde: otra clave no lo arregla
                    break
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
    try:
        r = (session or requests.Session()).post(
            URL.format(modelo=modelo), json=cuerpo, timeout=timeout,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    except requests.RequestException as e:
        # Un timeout no puede tumbar la efeméride: con GeminiError sigue Piper (2026-09-30, la
        # muestra del Sputnik se cayó con "Read timed out" en vez de pasar al respaldo).
        raise GeminiError(f"Gemini TTS ({modelo}): {e}", pasajero=True) from e
    if r.status_code != 200:
        raise GeminiError(f"Gemini TTS ({modelo}): {r.status_code} {r.text[:300]}")
    try:
        parte = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError, ValueError) as e:
        raise GeminiError(f"Gemini TTS sin audio: {r.text[:300]}") from e
    m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
    return base64.b64decode(parte["data"]), int(m.group(1)) if m else 24000


def hablar_con_claves(claves_: list[tuple[str, str]], texto: str, aviso=None, **kw) -> tuple[bytes, int]:
    """`hablar` con la principal y, solo si se quedó sin cuota del día, con la segunda."""
    aviso = aviso or (lambda *a, **k: None)
    ultimo: GeminiError | None = None
    for nombre, clave in claves_:
        try:
            r = hablar(clave, texto, **kw)
        except GeminiError as e:
            ultimo, t = e, str(e)
            codigo = int(t.split(": ", 1)[1][:3]) if ": " in t and t.split(": ", 1)[1][:3].isdigit() else 0
            if es_sin_cuota(codigo, t):
                log.warning("Gemini TTS: la clave %s sin cuota del día", nombre)
                continue
            if nombre != PRINCIPAL and es_clave_invalida(codigo, t):
                aviso("invalida", nombre, clave, t)
                continue
            raise
        log.info("Gemini TTS con la clave %s", nombre)
        if nombre != PRINCIPAL:
            aviso("segunda", nombre, clave)
        return r
    raise ultimo or GeminiError("sin GEMINI_API_KEY")


def _texto(respuesta: dict) -> str:
    try:
        cand = respuesta["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        motivo = (respuesta.get("promptFeedback") or {}).get("blockReason") or json.dumps(respuesta)[:300]
        raise GeminiError(f"Respuesta de Gemini sin texto: {motivo}") from None
