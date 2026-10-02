"""Cliente mínimo de Gemini (REST generateContent) con salida JSON forzada por schema."""

from __future__ import annotations

import json
import base64
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


IMAGEN_MAX_PX = 384           # ninguna imagen a Gemini más grande que esto (pedido 2026-10-02)
CACHE_DIAS = 7                # una respuesta a un pedido IDÉNTICO se reusa esta cantidad de días


def achicar(img: bytes, lado: int = IMAGEN_MAX_PX) -> bytes:
    """La imagen con su lado mayor ≤ `lado` (JPEG). Las que ya son chicas pasan igual."""
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(img)) as im:
            if max(im.size) <= lado:
                return img
            im = im.convert("RGB")
            im.thumbnail((lado, lado))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            return buf.getvalue()
    except OSError:
        return img


def _llamador() -> str:
    """Qué función del bot pidió la llamada ("textos.generar", "efemerides.elegir_fotos"…), para
    medir el uso por función sin tener que pasarlo en cada llamada."""
    import sys

    f = sys._getframe(2)
    while f is not None and f.f_globals.get("__name__") == __name__:
        f = f.f_back
    if f is None:
        return "?"
    return f"{f.f_globals.get('__name__', '?').rsplit('.', 1)[-1]}.{f.f_code.co_name}"


def registrar_uso(funcion: str, modelo: str, clave: str, entrada: int, salida: int,
                  cache: bool = False) -> None:
    """Una fila por llamada en la tabla `gemini_uso`. Nunca tumba la llamada."""
    from . import db
    from .config import DB_PATH

    try:
        conn = db.connect(DB_PATH)
        try:
            db.anotar_gemini(conn, funcion, modelo, clave, entrada, salida, cache)
        finally:
            conn.close()
    except Exception as e:     # medir no puede romper lo que se mide
        log.warning("Gemini: no pude anotar el uso: %s", e)


def _tokens(respuesta: dict) -> tuple[int, int]:
    u = respuesta.get("usageMetadata") or {}
    return int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0) + \
        int(u.get("thoughtsTokenCount") or 0)


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
        # Se ignora solo el MISMO día: una clave recién creada puede dar 401 unos minutos (le pasó
        # a la del amigo el 2026-09-29; al día siguiente andaba) y no puede quedar afuera para siempre.
        marca = invalidas.get(nombre)
        if nombre != PRINCIPAL and isinstance(marca, dict) and marca.get("huella") == huella(k)                 and marca.get("dia") == _dia_pacifico():
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
                inv[nombre] = {"huella": huella(clave), "dia": _dia_pacifico()}
                db.set_valor(conn, CLAVE_INVALIDA, json.dumps(inv))
                texto = (f"🔧 Claude Code: la clave {nombre} de Gemini (GEMINI_API_KEY_2) dio inválida; "
                         f"hoy la ignoro y mañana la vuelvo a probar. ({detalle[:120]})")
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
                 modelo_fallback: str = "", reloj=time.monotonic, aviso=None, uso=None,
                 cache_dir=None):
        # `api_key`: una clave, o [(nombre, clave)] en orden (principal, segunda).
        self.claves = [(PRINCIPAL, api_key)] if isinstance(api_key, str) else list(api_key)
        self.api_key = self.claves[0][1]
        self.aviso = aviso or (lambda *a, **k: None)
        # `uso(funcion, modelo, clave, entrada, salida, cache)`: anota cada llamada (registrar_uso).
        self.uso = uso
        # Respuestas guardadas por pedido idéntico (mismo sistema, prompt, schema, imágenes y audio).
        self.cache_dir = Path(cache_dir) if cache_dir else None
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

    def _clave_cache(self, sistema, prompt, schema, temperatura, imagenes, audio) -> str | None:
        if not self.cache_dir:
            return None
        h = hashlib.sha256(json.dumps([self.modelo, sistema, prompt, schema, temperatura],
                                      sort_keys=True, ensure_ascii=False).encode())
        for b in list(imagenes) + ([audio] if audio else []):
            h.update(hashlib.sha256(b).digest())
        return h.hexdigest()

    def _de_cache(self, clave: str | None) -> str | None:
        if not clave:
            return None
        f = self.cache_dir / f"{clave}.json"
        if not f.exists() or time.time() - f.stat().st_mtime > CACHE_DIAS * 86400:
            return None
        try:
            return json.loads(f.read_text(encoding="utf-8"))["texto"]
        except (OSError, ValueError, KeyError):
            return None

    def _a_cache(self, clave: str | None, texto: str) -> None:
        if not clave:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{clave}.json").write_text(json.dumps({"texto": texto}, ensure_ascii=False),
                                                         encoding="utf-8")
            limite = time.time() - CACHE_DIAS * 86400
            for viejo in self.cache_dir.glob("*.json"):
                if viejo.stat().st_mtime < limite:
                    viejo.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Gemini: no pude guardar en la caché: %s", e)

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
        funcion = _llamador()
        imagenes = [achicar(img) for img in imagenes or []]
        clave_cache = self._clave_cache(sistema, prompt, schema, temperatura, imagenes, audio)
        guardado = self._de_cache(clave_cache)
        if guardado is not None:
            log.info("Gemini (caché) para %s", funcion)
            if self.uso:
                self.uso(funcion, "cache", "", 0, 0, True)
            return guardado
        partes: list[dict] = [{"text": prompt}]
        for img in imagenes:
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
                        respuesta = r.json()
                        entrada, salida = _tokens(respuesta)
                        log.info("Gemini %s con la clave %s para %s (%d + %d tokens)", modelo, nombre,
                                 funcion, entrada, salida)
                        if nombre != PRINCIPAL:
                            self.aviso("segunda", nombre, clave)
                        if self.uso:
                            self.uso(funcion, modelo, nombre, entrada, salida, False)
                        texto = _texto(respuesta)
                        self._a_cache(clave_cache, texto)
                        return texto
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
           timeout: float = 180, tokens: list | None = None) -> tuple[bytes, int]:
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
    if tokens is not None:
        tokens.extend(_tokens(r.json()))
    try:
        parte = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError, ValueError) as e:
        raise GeminiError(f"Gemini TTS sin audio: {r.text[:300]}") from e
    m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
    return base64.b64decode(parte["data"]), int(m.group(1)) if m else 24000


def hablar_con_claves(claves_: list[tuple[str, str]], texto: str, aviso=None, uso=None,
                      **kw) -> tuple[bytes, int]:
    """`hablar` con la principal y, solo si se quedó sin cuota del día, con la segunda."""
    aviso = aviso or (lambda *a, **k: None)
    ultimo: GeminiError | None = None
    for nombre, clave in claves_:
        tokens: list = []
        try:
            r = hablar(clave, texto, tokens=tokens, **kw)
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
        log.info("Gemini TTS con la clave %s (%s tokens)", nombre, sum(tokens) if tokens else "?")
        if nombre != PRINCIPAL:
            aviso("segunda", nombre, clave)
        if uso:
            uso("efemerides.voz", kw.get("modelo", "tts"), nombre,
                tokens[0] if tokens else 0, tokens[1] if len(tokens) > 1 else 0, False)
        return r
    raise ultimo or GeminiError("sin GEMINI_API_KEY")


def _texto(respuesta: dict) -> str:
    try:
        cand = respuesta["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        motivo = (respuesta.get("promptFeedback") or {}).get("blockReason") or json.dumps(respuesta)[:300]
        raise GeminiError(f"Respuesta de Gemini sin texto: {motivo}") from None
