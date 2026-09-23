"""§3 paso 3: descarga de clips con yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

# https://clips.twitch.tv/<slug>  |  https://www.twitch.tv/<login>/clip/<slug>
_CLIP_URL = re.compile(
    r"^https?://(?:(?:www|m)\.)?(?:clips\.twitch\.tv/(?:embed\?clip=)?(?P<slug1>[\w-]+)"
    r"|twitch\.tv/(?P<login>\w+)/clip/(?P<slug2>[\w-]+))",
    re.IGNORECASE,
)
# https://kick.com/<slug>/clips/<clip_id>
_CLIP_KICK = re.compile(r"^https?://(?:www\.)?kick\.com/(?P<login>[\w-]+)/clips/(?P<slug>[\w-]+)", re.IGNORECASE)


class DescargaError(RuntimeError):
    pass


@dataclass(frozen=True)
class Descarga:
    path: Path
    clip_id: str
    url: str
    titulo: str
    plataforma: str
    streamer: str  # login si se pudo saber, si no el nombre que devuelve yt-dlp
    canal: str  # nombre visible del canal (para el crédito)
    duracion: float
    vistas: int
    creado: datetime | None
    categoria: str


def parse_clip_url(url: str) -> tuple[str, str | None, str]:
    """(slug, login o None, plataforma). Tira DescargaError si no es una URL de clip conocida."""
    if m := _CLIP_URL.match(url.strip()):
        login = m.group("login")
        return m.group("slug1") or m.group("slug2"), (login.lower() if login else None), "twitch"
    if m := _CLIP_KICK.match(url.strip()):
        return m.group("slug"), m.group("login").lower(), "kick"
    raise DescargaError(f"No parece una URL de clip de Twitch ni de Kick: {url}")


def descargar(url: str, destino: Path) -> Descarga:
    slug, login, plataforma = parse_clip_url(url)
    destino.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(destino / f"{slug}.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except DownloadError as e:
        raise DescargaError(str(e)) from e
    if not path.exists():
        raise DescargaError(f"yt-dlp terminó pero no está el archivo {path}")
    canal = str(info.get("channel") or info.get("creator") or login or "?")
    ts = info.get("timestamp")
    return Descarga(
        path=path,
        clip_id=slug,
        url=url,
        titulo=info.get("title") or "",
        plataforma=plataforma,
        streamer=(login or canal).lower(),
        canal=canal,
        duracion=float(info.get("duration") or 0),
        vistas=int(info.get("view_count") or 0),
        creado=datetime.fromtimestamp(ts, timezone.utc) if ts else None,
        categoria=((info.get("categories") or [""])[0]) or "",
    )
