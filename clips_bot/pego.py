"""Lo que pega en otros canales → el momento original en Twitch/Kick (pedido 2026-09-29).

Una vez por día (y en /buscar), por cada streamer de las carpetas con diarios: se buscan en YouTube
los Shorts recientes de OTROS canales que lo nombran, ordenados por vistas. Para los que pegaron,
se busca el mismo momento entre los clips originales del streamer (los de los días anteriores a
que se publicara el Short) comparando el audio (`audio_huella`). Si aparece, ese clip ORIGINAL
entra como candidato con un bonus grande y el mensaje dice "🔥 Pegó en otro canal: X vistas".

NUNCA se usa el video del otro canal: su audio se baja solo para comparar y se tira. Lo que se
procesa y se sube es siempre el clip original de Twitch/Kick.

Búsqueda: con la API de YouTube si hay credencial (`YOUTUBE_API_KEY` en el .env, o la conexión
OAuth del canal), que cuesta 100 unidades por búsqueda de las 10.000 diarias; si no hay, yt-dlp
(la página de resultados, sin cuota). En los dos casos, tope de `pego.busquedas_por_dia`.

Calibrado 2026-09-29 en la Pi con clips reales de Spreen: un pedazo de 20 s de un clip, con ruido
o un tono encima y recomprimido, da 0,70-0,95 contra su clip y a lo sumo 0,39 contra los demás.
Umbral 0,55. Un Short real de otro canal ("Spreen le escribe a Vicky…", Axor, 1802 vistas) no
coincidió con ninguno de los 15 clips más vistos de esos días (máx. 0,24): no salió de un clip.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import db
from .candidates import Clip
from .config import Streamer

log = logging.getLogger(__name__)

CLAVE_BUSQUEDAS = "pego_busquedas"      # bot_estado: {"fecha": "AAAA-MM-DD", "n": 12}
API = "https://www.googleapis.com/youtube/v3"


@dataclass
class ShortAjeno:
    id: str
    titulo: str
    canal: str
    vistas: int
    duracion: float
    publicado: str = ""      # ISO; vacío si la búsqueda no lo dio (yt-dlp): se pide al bajarlo

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/shorts/{self.id}"


def _norm(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", t.lower()).strip() + " "


# ---- el tope de búsquedas por día -------------------------------------------------------------

def busquedas_hechas(conn: sqlite3.Connection, hoy: str) -> int:
    d = json.loads(db.get_valor(conn, CLAVE_BUSQUEDAS) or "{}")
    return int(d.get("n", 0)) if d.get("fecha") == hoy else 0


def anotar_busqueda(conn: sqlite3.Connection, hoy: str) -> None:
    db.set_valor(conn, CLAVE_BUSQUEDAS, json.dumps({"fecha": hoy, "n": busquedas_hechas(conn, hoy) + 1}))


# ---- buscar en YouTube ------------------------------------------------------------------------

def buscar_api(consulta: str, desde: datetime, clave: str,
               session: requests.Session | None = None) -> list[ShortAjeno]:
    """search.list (100 unidades) ordenado por vistas, Shorts (menos de 4 min) desde `desde`, y
    videos.list (1 unidad) para vistas y duración exactas."""
    s = session or requests.Session()
    r = s.get(f"{API}/search", timeout=30, params={
        "part": "snippet", "q": consulta, "type": "video", "videoDuration": "short",
        "order": "viewCount", "publishedAfter": desde.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "maxResults": 25, "relevanceLanguage": "es", "key": clave})
    if r.status_code != 200:
        raise RuntimeError(f"YouTube search: {r.status_code} {r.text[:200]}")
    ids = [it["id"]["videoId"] for it in r.json().get("items") or []]
    if not ids:
        return []
    r = s.get(f"{API}/videos", timeout=30, params={"part": "snippet,statistics,contentDetails",
                                                   "id": ",".join(ids), "key": clave})
    if r.status_code != 200:
        raise RuntimeError(f"YouTube videos: {r.status_code} {r.text[:200]}")
    out = []
    for v in r.json().get("items") or []:
        out.append(ShortAjeno(v["id"], v["snippet"]["title"], v["snippet"]["channelTitle"],
                              int(v["statistics"].get("viewCount") or 0),
                              _iso8601_s(v["contentDetails"].get("duration", "")),
                              v["snippet"]["publishedAt"]))
    return out


def _iso8601_s(d: str) -> float:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return float(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else 0.0


# sp de YouTube: subido "esta semana" + "menos de 4 minutos" (lo que la web arma con los filtros).
SP_SEMANA_CORTOS = "EgYIAxABGAE%3D"


def buscar_ytdlp(consulta: str, desde: datetime | None = None) -> list[ShortAjeno]:
    """La página de resultados de YouTube con yt-dlp, sin credencial ni cuota. Sin fecha exacta:
    el filtro es "esta semana"; la fecha se pide después, al bajar el audio."""
    from urllib.parse import quote

    from yt_dlp import YoutubeDL

    url = f"https://www.youtube.com/results?search_query={quote(consulta)}&sp={SP_SEMANA_CORTOS}"
    with YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as y:
        info = y.extract_info(url, download=False)
    return [ShortAjeno(e["id"], e.get("title") or "", e.get("channel") or "",
                       int(e.get("view_count") or 0), float(e.get("duration") or 0))
            for e in info.get("entries") or [] if e.get("id")]


def relevantes(shorts: list[ShortAjeno], s: Streamer, min_vistas: int, cuantos: int,
               propios: tuple[str, ...] = ()) -> list[ShortAjeno]:
    """Los que nombran al streamer (en el título o el nombre del canal), duran hasta 61 s, pegaron
    (≥ min_vistas) y no son de los canales propios. Los más vistos primero."""
    nombre = _norm(s.login)
    pegado = nombre.strip().replace(" ", "")
    propios_n = {_norm(p) for p in propios}
    # En el título, la palabra entera ("spreen", no "spreenlandia"); en el canal, también pegado
    # ("SpreenClips" es un canal de clips de Spreen).
    ok = [x for x in shorts
          if 0 < x.duracion <= 61 and x.vistas >= min_vistas and _norm(x.canal) not in propios_n
          and (nombre in _norm(x.titulo) or pegado in _norm(x.canal).replace(" ", ""))]
    return sorted(ok, key=lambda x: -x.vistas)[:cuantos]


# ---- el momento original ----------------------------------------------------------------------

def originales(s: Streamer, hasta: datetime, dias: int, maximo: int, twitch=None, kick=None) -> list[Clip]:
    """Los clips del streamer creados en los `dias` antes del Short (más 1 día de margen), los más
    vistos primero. Twitch por fechas; Kick trae los 100 más vistos del mes y se filtran acá."""
    from .kick import a_clip

    desde, tope = hasta - timedelta(days=dias), hasta + timedelta(days=1)
    clips: list[Clip] = []
    if s.plataforma == "twitch" and twitch is not None:
        bid = twitch.get_user_ids([s.login]).get(s.login)
        if bid:
            clips = [Clip.from_helix(d, s.login) for d in twitch.get_clips(bid, desde, tope, 100)]
    elif s.plataforma == "kick" and kick is not None:
        for d in kick.get_clips(s.login, 100, "view", "month"):
            p = a_clip(d, s.login)
            clips.append(Clip.from_helix(p, s.login, p["_game_name"], "", "reciente", "kick"))
    clips = [c for c in clips if desde <= c.created_at <= tope]
    return sorted(clips, key=lambda c: -c.view_count)[:maximo]


def bajar_audio_short(short: ShortAjeno, carpeta: Path) -> tuple[Path, datetime | None]:
    """El audio del Short (solo para comparar; se borra después) y su fecha de publicación."""
    from yt_dlp import YoutubeDL

    carpeta.mkdir(parents=True, exist_ok=True)
    with YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True,
                    "format": "bestaudio/best", "outtmpl": str(carpeta / f"short_{short.id}.%(ext)s")}) as y:
        info = y.extract_info(short.url, download=True)
        ruta = Path(y.prepare_filename(info))
    fecha = (datetime.strptime(info["upload_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
             if info.get("upload_date") else None)
    return ruta, fecha


def encontrar(short_audio: Path, clips: list[Clip], carpeta: Path, umbral: float,
              bajar=None, comparar=None) -> tuple[Clip, float] | None:
    """El clip cuyo audio coincide con el del Short (el mejor, si pasa el umbral)."""
    from . import audio_huella as ah
    from .download import descargar

    bajar = bajar or (lambda url, d: descargar(url, d).path)
    comparar = comparar or ah.comparar
    mejor: tuple[Clip, float] | None = None
    for c in clips:
        try:
            ruta = bajar(c.url, carpeta)
            valor, _ = comparar(short_audio, ruta)
        except Exception as e:
            log.warning("pegó: no pude comparar %s: %s", c.id, e)
            continue
        if valor >= umbral and (mejor is None or valor > mejor[1]):
            mejor = (c, valor)
    return mejor


# ---- la tabla ---------------------------------------------------------------------------------

def guardar(conn: sqlite3.Connection, short: ShortAjeno, streamer: str,
            hallado: tuple[Clip, float] | None) -> None:
    """Se guarda también cuando NO se encontró: así el mismo Short no se vuelve a comparar."""
    clip, valor = hallado if hallado else (None, 0.0)
    datos = asdict(clip) if clip else None
    if datos:
        datos["created_at"] = clip.created_at.isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO pegados (short_id, streamer, vistas, canal, titulo, publicado,
               clip_id, clip_json, coincidencia, fecha) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (short.id, streamer, short.vistas, short.canal, short.titulo, short.publicado,
         clip.id if clip else None, json.dumps(datos, ensure_ascii=False) if datos else None,
         valor, datetime.now(timezone.utc).isoformat()))
    conn.commit()


def ya_visto(conn: sqlite3.Connection, short_id: str) -> bool:
    return conn.execute("SELECT 1 FROM pegados WHERE short_id = ?", (short_id,)).fetchone() is not None


def como_candidatos(conn: sqlite3.Connection, streamers: list[Streamer], vistos: set[str],
                    dias: int = 14) -> list[Clip]:
    """Los originales encontrados en los últimos `dias`, como candidatos: con las vistas del Short
    que pegó (el más visto, si hubo varios del mismo clip) y el grupo del streamer."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    grupos = {s.login: s.grupo_de("reciente") for s in streamers}
    filas = conn.execute(
        """SELECT clip_json, vistas, canal FROM pegados WHERE clip_id IS NOT NULL AND fecha >= ?
           ORDER BY vistas DESC""", (desde,)).fetchall()
    out, ya = [], set()
    for datos, vistas, canal in filas:
        d = json.loads(datos)
        if d["id"] in vistos or d["id"] in ya or d["broadcaster_login"] not in grupos:
            continue
        ya.add(d["id"])
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["creadores"] = tuple(d.get("creadores") or ())
        c = Clip(**d)
        out.append(replace(c, grupo=grupos[c.broadcaster_login], pego_vistas=int(vistas),
                           pego_canal=canal or ""))
    return out


# ---- de punta a punta -------------------------------------------------------------------------

def buscar_pegados(conn: sqlite3.Connection, streamers: list[Streamer], cfg, carpeta: Path,
                   twitch=None, kick=None, buscar=None, avisar=log.info,
                   ahora: datetime | None = None) -> int:
    """Una vuelta: busca, filtra, compara y guarda. Devuelve cuántos originales encontró.
    `buscar(consulta, desde)`: el buscador (API o yt-dlp); lo elige quien llama."""
    import shutil

    ahora = ahora or datetime.now(timezone.utc)
    hoy = ahora.astimezone(timezone(timedelta(hours=-3))).date().isoformat()
    buscar = buscar or buscar_ytdlp
    encontrados = 0
    for s in streamers:
        if busquedas_hechas(conn, hoy) >= cfg.busquedas_por_dia:
            avisar(f"pegó: llegué al tope de {cfg.busquedas_por_dia} búsquedas de hoy")
            break
        try:
            resultados = buscar(s.login, ahora - timedelta(days=cfg.dias))
        except Exception as e:
            avisar(f"pegó: la búsqueda de {s.login} falló: {e}")
            continue
        finally:
            anotar_busqueda(conn, hoy)
        for short in relevantes(resultados, s, cfg.min_vistas, cfg.por_streamer, cfg.canales_propios):
            if ya_visto(conn, short.id):
                continue
            tmp = carpeta / short.id
            try:
                audio, fecha = bajar_audio_short(short, tmp)
                short.publicado = short.publicado or (fecha.isoformat() if fecha else "")
                cuando = datetime.fromisoformat(short.publicado.replace("Z", "+00:00")) if short.publicado else ahora
                clips = originales(s, cuando, cfg.dias, cfg.max_originales, twitch, kick)
                hallado = encontrar(audio, clips, tmp, cfg.umbral)
            except Exception as e:
                avisar(f"pegó: {short.id} ({short.canal}): {e}")
                continue
            finally:
                shutil.rmtree(tmp, ignore_errors=True)   # el video ajeno no se guarda
            guardar(conn, short, s.login, hallado)
            if hallado:
                encontrados += 1
                avisar(f"pegó: {s.login} — «{short.titulo[:50]}» ({short.canal}, {short.vistas:,} "
                       f"vistas) = {hallado[0].url} (coincidencia {hallado[1]:.2f})")
            else:
                avisar(f"pegó: {s.login} — «{short.titulo[:50]}»: no está en sus {len(clips)} clips")
    return encontrados
