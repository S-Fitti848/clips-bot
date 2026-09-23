"""§3 paso 10: entrega por Telegram (mp4 + textos en bloques copiables)."""

from __future__ import annotations

import html
import re
from pathlib import Path

import requests

API = "https://api.telegram.org/bot{token}/{metodo}"
MAX_ARCHIVO_BYTES = 50 * 1024 * 1024  # límite de subida de la Bot API
MAX_CAPTION = 1024

# Va en todos los mensajes de entrega: con streamers que entran por experimento, Studio es el único
# chequeo de copyright real que tenemos antes de publicar.
RECORDATORIO = "Subir en PRIVADO → esperar Chequeos de copyright en Studio → si sale limpio, publicar"


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, session: requests.Session | None = None, timeout: float = 120):
        self.token = token
        self.session = session or requests.Session()
        self.timeout = timeout

    def _llamar(self, metodo: str, data: dict | None = None, files: dict | None = None) -> object:
        try:
            r = self.session.post(API.format(token=self.token, metodo=metodo), data=data, files=files,
                                  timeout=self.timeout)
            cuerpo = r.json()
        except (requests.RequestException, ValueError) as e:
            raise TelegramError(f"{metodo}: {e}") from e
        if not cuerpo.get("ok"):
            raise TelegramError(f"{metodo}: {cuerpo.get('error_code')} {cuerpo.get('description')}")
        return cuerpo["result"]

    def get_updates(self, offset: int | None = None, timeout: int = 0) -> list[dict]:
        """offset = primer update_id que todavía no se procesó (confirma los anteriores)."""
        data: dict = {"timeout": str(timeout)}
        if offset is not None:
            data["offset"] = str(offset)
        return self._llamar("getUpdates", data)  # type: ignore[return-value]

    def send_message(self, chat_id: str, texto_html: str) -> None:
        self._llamar("sendMessage", {"chat_id": chat_id, "text": texto_html, "parse_mode": "HTML",
                                     "disable_web_page_preview": "true"})

    def send_video(self, chat_id: str, path: Path, caption: str = "", *, width: int | None = None,
                   height: int | None = None, duration: int | None = None, thumbnail: Path | None = None) -> None:
        """Sin width/height (y sin miniatura) la app de Telegram no sabe que es vertical y lo muestra
        en un cuadro que no corresponde, con negro arriba y abajo. Siempre pasar las dimensiones."""
        _chequear_tamano(path)
        data = {"chat_id": chat_id, "caption": caption[:MAX_CAPTION], "supports_streaming": "true"}
        for clave, valor in (("width", width), ("height", height), ("duration", duration)):
            if valor:
                data[clave] = str(valor)
        with path.open("rb") as f:
            files = {"video": (path.name, f, "video/mp4")}
            if thumbnail:
                with thumbnail.open("rb") as t:
                    files["thumbnail"] = (thumbnail.name, t, "image/jpeg")
                    self._llamar("sendVideo", data, files)
            else:
                self._llamar("sendVideo", data, files)

    def send_document(self, chat_id: str, path: Path, caption: str = "") -> None:
        _chequear_tamano(path)
        with path.open("rb") as f:
            self._llamar("sendDocument", {"chat_id": chat_id, "caption": caption[:MAX_CAPTION]},
                         {"document": (path.name, f)})


def _chequear_tamano(path: Path) -> None:
    if path.stat().st_size > MAX_ARCHIVO_BYTES:
        mb = path.stat().st_size / 1024 / 1024
        raise TelegramError(f"{path.name} pesa {mb:.1f} MB; la Bot API acepta hasta 50 MB")


def chats(updates: list[dict]) -> list[dict]:
    """Chats únicos que le escribieron al bot: [{id, tipo, nombre}]."""
    vistos: dict[str, dict] = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        chat = msg.get("chat")
        if not chat:
            continue
        nombre = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
        if chat.get("username"):
            nombre += f" (@{chat['username']})"
        vistos[str(chat["id"])] = {"id": str(chat["id"]), "tipo": chat.get("type", ""), "nombre": nombre.strip()}
    return list(vistos.values())


def resolver_chat_id(cliente: TelegramClient, configurado: str) -> str:
    """TELEGRAM_CHAT_ID si está; si no, el único chat privado que le escribió al bot (getUpdates)."""
    if configurado:
        return configurado
    privados = [c for c in chats(cliente.get_updates()) if c["tipo"] == "private"]
    if len(privados) == 1:
        return privados[0]["id"]
    if not privados:
        raise TelegramError("No hay TELEGRAM_CHAT_ID y nadie le escribió al bot todavía: "
                            "mandale un mensaje y corré `python -m clips_bot telegram-chat-id`.")
    raise TelegramError("Hay varios chats en getUpdates; fijá TELEGRAM_CHAT_ID en .env "
                        "(ver `python -m clips_bot telegram-chat-id`).")


def mensaje_textos(numero: int, streamer: str, clip_id: str, horario: str | None, textos: dict,
                   youtube_url: str | None = None) -> str:
    """Mensaje HTML con cada texto en su propio bloque <pre> (en Telegram se copia con un toque)."""
    e = html.escape
    cabecera = f"<b>#{numero} · {e(streamer)}</b>"
    if horario:
        cabecera += f" · sugerido {e(horario)} AR"
    partes = [cabecera, f"id: <code>{e(clip_id)}</code>"]
    if youtube_url:
        partes.append(f"YouTube: {e(youtube_url)}")
    for etiqueta, valor in [
        ("Título", textos["titulo"]),
        ("Descripción", textos["descripcion"]),
        ("Hashtags", " ".join(textos["hashtags"])),
        ("Crédito", textos["credito"]),
    ]:
        partes.append(f"\n<b>{etiqueta}:</b>\n<pre>{e(valor)}</pre>")
    partes.append(f"\n⚠️ <b>{e(RECORDATORIO)}</b>")
    partes.append(f"Si recibe un reclamo o strike: <code>/reclamo {e(clip_id)}</code> "
                  "(excluye al streamer de las próximas corridas).")
    return "\n".join(partes)


def comandos(updates: list[dict]) -> list[dict]:
    """Comandos /algo que le mandaron al bot: [{update_id, chat_id, user_id, usuario, comando, args}].

    `user_id` es QUIÉN escribió, no dónde: en un grupo el chat es uno solo y cualquiera de los
    miembros puede mandar /reclamo. Por eso el permiso se chequea por usuario (ver usuarios_permitidos).
    """
    out = []
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        texto = (msg.get("text") or "").strip()
        if not texto.startswith("/"):
            continue
        partes = texto.split()
        quien = msg.get("from") or {}
        nombre = " ".join(filter(None, [quien.get("first_name"), quien.get("last_name")]))
        if quien.get("username"):
            nombre = (nombre + f" (@{quien['username']})").strip()
        out.append({
            "update_id": u.get("update_id"),
            "chat_id": str((msg.get("chat") or {}).get("id", "")),
            "user_id": str(quien.get("id") or ""),
            "usuario": nombre.strip(),
            "comando": partes[0].split("@")[0].lower(),  # /reclamo@mi_bot → /reclamo
            "args": partes[1:],
        })
    return out


def usuarios_permitidos(valor: str) -> set[str]:
    """TELEGRAM_ALLOWED_USERS: ids de usuario separados por coma (o espacio)."""
    return {p for p in re.split(r"[,\s]+", (valor or "").strip()) if p}


def usuarios(updates: list[dict]) -> list[dict]:
    """Quiénes le escribieron al bot: [{id, nombre, chat_id}]. Para armar TELEGRAM_ALLOWED_USERS."""
    vistos: dict[str, dict] = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        quien = msg.get("from") or {}
        if not quien.get("id"):
            continue
        nombre = " ".join(filter(None, [quien.get("first_name"), quien.get("last_name")]))
        if quien.get("username"):
            nombre += f" (@{quien['username']})"
        vistos[str(quien["id"])] = {"id": str(quien["id"]), "nombre": nombre.strip(),
                                    "chat_id": str((msg.get("chat") or {}).get("id", ""))}
    return list(vistos.values())
