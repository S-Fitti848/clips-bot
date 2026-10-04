"""Lo que pega en otros canales → el momento original en Twitch/Kick (pedido 2026-09-29).

Una vez por día (y en /buscar), por cada streamer de las carpetas con diarios: se buscan en YouTube
los Shorts recientes de OTROS canales que lo nombran (por su login o sus apodos: "Davo" y no
"davooxeneize"), ordenados por vistas. Para los que pegaron, se busca el mismo momento entre los
clips originales del streamer de los días cercanos a la publicación del Short, comparando el audio
(`audio_huella`). Si aparece, ese clip ORIGINAL entra como candidato con un bonus grande y el
mensaje dice "🔥 Pegó en otro canal: X vistas". Si no aparece, el Short queda anotado igual y se
avisa con su link ("no encontré el original"): el momento pegó y Santi lo puede buscar a mano.

NUNCA se usa el video del otro canal: su audio se baja solo para comparar y se tira. Lo que se
procesa y se sube es siempre el clip original de Twitch/Kick.

Búsqueda: con la API de YouTube si hay credencial (`YOUTUBE_API_KEY` en el .env), que cuesta 100
unidades por búsqueda de las 10.000 diarias; si no hay, yt-dlp (la página de resultados, sin cuota).
En los dos casos, tope de `pego.busquedas_por_dia`. Una sola búsqueda por streamer con todos sus
nombres unidos por "|" (el OR de YouTube).

Calibrado 2026-09-29 en la Pi con clips reales de Spreen: un pedazo de 20 s de un clip, con ruido
o un tono encima y recomprimido, da 0,70-0,95 contra su clip y a lo sumo 0,39 contra los demás.
Umbral 0,55. Un Short real de otro canal ("Spreen le escribe a Vicky…", Axor, 1802 vistas) no
coincidió con ninguno de los 15 clips más vistos de esos días (máx. 0,24): no salió de un clip.

Lo que se aprendió con Davo (2026-09-29, 🔥 no devolvía nada): la búsqueda por "davooxeneize" traía
25 Shorts, pero los 3 más vistos que "lo nombraban" eran memes de fútbol de MordoTv con
#davooxeneize de relleno en el título. Por eso un nombre que aparece SOLO como hashtag no cuenta.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from . import db
from .candidates import Clip
from .config import Streamer

log = logging.getLogger(__name__)

CLAVE_BUSQUEDAS = "pego_busquedas"      # bot_estado: {"fecha": "AAAA-MM-DD", "n": 12}
API = "https://www.googleapis.com/youtube/v3"
SEGURO = 0.70          # con esto ya es el mismo momento (calibrado): no hace falta mirar el resto
DIAS_HUELLAS = 30      # las huellas de los clips originales se guardan un mes


class SinTiempo(Exception):
    """Se terminó el tope de la vuelta: lo que quedó a medio comparar no se anota (se retoma)."""


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


@dataclass
class Recuento:
    """Paso por paso, qué pasó con la búsqueda de un streamer (para que "no salió ninguno" diga por qué)."""
    streamer: str
    consulta: str = ""
    resultados: int = 0          # lo que devolvió YouTube
    cortos: int = 0              # de ≤ 61 s
    con_vistas: int = 0          # y con ≥ min_vistas
    nombran: int = 0             # y lo nombran de verdad (no solo en un hashtag), de otro canal
    ya_vistos: int = 0           # ya comparados otro día
    comparados: int = 0          # Shorts comparados hoy
    clips: list[int] = field(default_factory=list)   # contra cuántos originales, por Short
    encontrados: int = 0
    sin_original: list[ShortAjeno] = field(default_factory=list)
    error: str = ""

    def texto(self, min_vistas: int) -> str:
        if self.error:
            return f"{self.streamer}: la búsqueda falló ({self.error})"
        partes = [f"{self.streamer}: YouTube dio {self.resultados} Shorts",
                  f"{self.cortos} de hasta 61 s", f"{self.con_vistas} con {min_vistas:,}+ vistas".replace(",", "."),
                  f"{self.nombran} lo nombran de verdad"]
        if self.ya_vistos:
            partes.append(f"{self.ya_vistos} ya comparados antes")
        if self.comparados:
            partes.append(f"comparé {self.comparados} contra {'/'.join(map(str, self.clips))} clips suyos")
        partes.append(f"encontré {self.encontrados} original" + ("" if self.encontrados == 1 else "es"))
        return " → ".join(partes)


def _norm(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", t.lower()).strip() + " "


def nombres(s: Streamer) -> list[str]:
    """El login y los apodos, sin repetir (el orden importa: es el de la consulta)."""
    out, vistos = [], set()
    for n in (s.login, *getattr(s, "apodos", ())):
        k = _norm(n)
        if k.strip() and k not in vistos:
            vistos.add(k)
            out.append(str(n).strip())
    return out


def consulta(s: Streamer) -> str:
    """Una búsqueda con todos los nombres: `davooxeneize|Davo|"Davo Xeneize"` (OR de YouTube)."""
    return "|".join(f'"{n}"' if " " in n else n for n in nombres(s))


def nombra(s: Streamer, titulo: str, canal: str) -> bool:
    """El título lo nombra fuera de los hashtags (palabra entera: "spreen", no "spreenlandia"), o
    el canal lleva el nombre, aunque sea pegado ("SpreenClips" es un canal de clips de Spreen).
    Un nombre que está SOLO como hashtag no cuenta: MordoTv pone #davooxeneize en memes de fútbol."""
    sin_tags = _norm(re.sub(r"#\S+", " ", titulo or ""))
    canal_pegado = _norm(canal).replace(" ", "")
    for n in nombres(s):
        k = _norm(n)
        if k in sin_tags or (len(k.strip()) >= 4 and k.strip().replace(" ", "") in canal_pegado):
            return True
    return False


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
        "maxResults": 50, "relevanceLanguage": "es", "key": clave})
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


def filtrar(shorts: list[ShortAjeno], s: Streamer, min_vistas: int,
            propios: tuple[str, ...] = (), rec: Recuento | None = None) -> list[ShortAjeno]:
    """Los que duran hasta 61 s, pegaron (≥ min_vistas), lo nombran de verdad y no son de los
    canales propios. Los más vistos primero. Si se pasa `rec`, anota cuántos quedan en cada paso."""
    propios_n = {_norm(p) for p in propios}
    cortos = [x for x in shorts if 0 < x.duracion <= 61]
    con_vistas = [x for x in cortos if x.vistas >= min_vistas]
    ok = [x for x in con_vistas if _norm(x.canal) not in propios_n and nombra(s, x.titulo, x.canal)]
    if rec is not None:
        rec.resultados, rec.cortos, rec.con_vistas, rec.nombran = (
            len(shorts), len(cortos), len(con_vistas), len(ok))
    return sorted(ok, key=lambda x: -x.vistas)


def relevantes(shorts: list[ShortAjeno], s: Streamer, min_vistas: int, cuantos: int,
               propios: tuple[str, ...] = ()) -> list[ShortAjeno]:
    return filtrar(shorts, s, min_vistas, propios)[:cuantos]


# ---- el momento original ----------------------------------------------------------------------

def originales(s: Streamer, cuando: datetime, dias_antes: int, maximo: int, twitch=None, kick=None,
               ahora: datetime | None = None) -> list[Clip]:
    """Los clips del streamer de los días cercanos a la publicación del Short: desde `dias_antes`
    días antes hasta 12 h después (un Short se sube después del momento), los más vistos primero.
    Twitch por fechas (Helix ya los da por vistas dentro del rango). Kick no filtra por fecha:
    los más vistos de la semana (o del mes, si el Short es más viejo), bien hondo, y se filtran acá.
    Medido 2026-09-29: Davo hace ~500 clips por día en Kick, así que ir en orden cronológico no
    llega ni a dos días."""
    from .kick import a_clip

    ahora = ahora or datetime.now(timezone.utc)
    desde, tope = cuando - timedelta(days=dias_antes), cuando + timedelta(hours=12)
    clips: list[Clip] = []
    if s.plataforma == "twitch" and twitch is not None:
        bid = twitch.get_user_ids([s.login]).get(s.login)
        if bid:
            clips = [Clip.from_helix(d, s.login) for d in twitch.get_clips(bid, desde, tope, maximo)]
    elif s.plataforma == "kick" and kick is not None:
        ventana = "week" if ahora - desde <= timedelta(days=6) else "month"   # margen: la "week" de Kick
        for d in kick.get_clips(s.login, max(300, maximo), "view", ventana):
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


def huella_de_clip(c: Clip, cache: Path, tmp: Path, bajar=None):
    """La huella del audio de un clip original, guardada por id: el mismo clip se baja UNA vez
    aunque se compare contra varios Shorts (o varios días)."""
    import numpy as np

    from . import audio_huella as ah
    from .download import descargar

    cache.mkdir(parents=True, exist_ok=True)
    archivo = cache / f"{re.sub(r'[^A-Za-z0-9_-]', '_', c.id)}.npy"
    if archivo.exists():
        return np.load(archivo)
    bajar = bajar or (lambda url, d: descargar(url, d).path)
    ruta = bajar(c.url, tmp)
    try:
        h = ah.huella(ah.leer_audio(ruta))
    finally:
        Path(ruta).unlink(missing_ok=True)
    np.save(archivo, h)
    return h


def limpiar_huellas(cache: Path, dias: int = DIAS_HUELLAS) -> None:
    if not cache.exists():
        return
    limite = time.time() - dias * 86400
    for f in cache.glob("*.npy"):
        if f.stat().st_mtime < limite:
            f.unlink(missing_ok=True)


def encontrar(short_audio: Path, clips: list[Clip], carpeta: Path, umbral: float,
              huella_de=None, hasta: float | None = None,
              reloj=time.monotonic) -> tuple[Clip | None, float]:
    """El clip cuyo audio coincide con el del Short: (el mejor si pasa el umbral, o None; la mejor
    coincidencia vista). Corta apenas uno pasa `SEGURO`. SinTiempo si se pasa de `hasta`."""
    from . import audio_huella as ah

    huella_de = huella_de or (lambda c: huella_de_clip(c, carpeta.parent / "huellas", carpeta))
    corto = ah.huella(ah.leer_audio(short_audio))
    mejor: tuple[Clip | None, float] = (None, 0.0)
    for c in clips:
        if hasta is not None and reloj() >= hasta:
            raise SinTiempo()
        try:
            valor, _ = ah.coincidencia(corto, huella_de(c))
        except Exception as e:
            log.warning("pegó: no pude comparar %s: %s", c.id, e)
            continue
        if valor > mejor[1]:
            mejor = (c, valor)
            if valor >= SEGURO:
                break
    return (mejor[0], mejor[1]) if mejor[1] >= umbral else (None, mejor[1])


# ---- la tabla ---------------------------------------------------------------------------------

def guardar(conn: sqlite3.Connection, short: ShortAjeno, streamer: str,
            hallado: tuple[Clip | None, float] | None, comparados: int = 0) -> None:
    """Se guarda también cuando NO se encontró: así el mismo Short no se vuelve a comparar, y queda
    para avisar que pegó sin original (con la mejor coincidencia que hubo)."""
    clip, valor = hallado if hallado else (None, 0.0)
    datos = asdict(clip) if clip else None
    if datos:
        datos["created_at"] = clip.created_at.isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO pegados (short_id, streamer, vistas, canal, titulo, publicado,
               clip_id, clip_json, coincidencia, fecha, comparados) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (short.id, streamer, short.vistas, short.canal, short.titulo, short.publicado,
         clip.id if clip else None, json.dumps(datos, ensure_ascii=False) if datos else None,
         valor, datetime.now(timezone.utc).isoformat(), comparados))
    conn.commit()


DIAS_DATOS_AJENOS = 30   # datos públicos de Shorts de OTROS canales (título, canal, vistas): se borran a los 30 días


def purgar_viejos(conn: sqlite3.Connection, ahora: datetime | None = None, dias: int = DIAS_DATOS_AJENOS) -> int:
    """Regla de los 30 días de las Políticas para Desarrolladores de YouTube: lo que se guardó de
    Shorts de otros canales se borra a los `dias`. Solo se usa unas dos semanas (como_candidatos mira
    14 días y la búsqueda, los Shorts de la última semana), así que no se pierde nada útil."""
    limite = ((ahora or datetime.now(timezone.utc)) - timedelta(days=dias)).isoformat()
    n = conn.execute("DELETE FROM pegados WHERE fecha < ?", (limite,)).rowcount
    conn.commit()
    return n


def ya_visto(conn: sqlite3.Connection, short_id: str) -> bool:
    return conn.execute("SELECT 1 FROM pegados WHERE short_id = ?", (short_id,)).fetchone() is not None


def sin_original(conn: sqlite3.Connection, streamers: list[Streamer], desde: datetime,
                 min_vistas: int = 0) -> list[dict]:
    """Los Shorts que pegaron y cuyo original no apareció, anotados desde `desde`. Se vuelve a
    mirar que lo nombren (las filas viejas se guardaron con la regla de antes, hashtags incluidos)."""
    por_login = {s.login: s for s in streamers}
    filas = conn.execute(
        """SELECT short_id, streamer, vistas, canal, titulo, coincidencia, comparados, vod_url,
                  vod_segundo, vod_programa, vod_clip_id, vod_resultado FROM pegados
           WHERE clip_id IS NULL AND fecha >= ? AND vistas >= ? ORDER BY vistas DESC""",
        (desde.isoformat(), min_vistas)).fetchall()
    out = []
    for (sid, login, vistas, canal, titulo, valor, comparados, vod_url, vod_seg, vod_programa,
         vod_clip, vod_res) in filas:
        s = por_login.get(login)
        if s is None or not nombra(s, titulo or "", canal or ""):
            continue
        out.append({"url": f"https://www.youtube.com/shorts/{sid}", "streamer": login,
                    "vistas": int(vistas or 0), "canal": canal or "", "titulo": titulo or "",
                    "coincidencia": float(valor or 0), "comparados": int(comparados or 0),
                    "vod_url": vod_url or "", "vod_segundo": float(vod_seg or 0),
                    "vod_programa": vod_programa or "", "vod_clip_id": vod_clip or "",
                    "vod_resultado": vod_res or ""})
    return out


def buscar_en_vod_del_dia(conn: sqlite3.Connection, streamers: list[Streamer], cfg, carpeta: Path,
                          kick=None, avisar=log.info, hasta: float | None = None,
                          reloj=time.monotonic, twitch=None, procesar_tramo=None,
                          carpeta_tramos: Path | None = None) -> int:
    """Los `cfg.vod_por_dia` Shorts sin original con más vistas (de las últimas 24 h, sin probar en
    el VOD) se buscan en los VODs del streamer (Kick o Twitch) de los `dias_antes` días antes de
    publicado. Si aparece: si el stream es de un programa de terceros excluido, se anota y NO se
    procesa (el resumen lo dice); si es de uno en experimento (el 412), se procesa con "⚠️ 412";
    si no, el tramo se corta del VOD y `procesar_tramo(descarga, aviso, pego)` lo procesa como un
    clip normal, con todos los filtros. Devuelve cuántos encontró."""
    import shutil

    from . import vod as vd
    from .candidates import AVISO_PROGRAMA, es_programa_de_terceros
    from .download import Descarga
    from .media import probe

    por_login = {s.login: s for s in streamers}
    desde = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    filas = conn.execute(
        """SELECT short_id, streamer, titulo, vistas, publicado, canal FROM pegados
           WHERE clip_id IS NULL AND COALESCE(vod_intentado, 0) = 0 AND fecha >= ?
           ORDER BY vistas DESC""", (desde,)).fetchall()
    hallados = intentados = 0
    for sid, login, titulo, vistas, publicado, canal in filas:
        if intentados >= cfg.vod_por_dia or (hasta is not None and reloj() >= hasta):
            break
        s = por_login.get(login)
        cliente = kick if s is not None and s.plataforma == "kick" else twitch
        if s is None or cliente is None or not nombra(s, titulo or "", ""):
            continue
        intentados += 1
        conn.execute("UPDATE pegados SET vod_intentado = 1 WHERE short_id = ?", (sid,))
        conn.commit()
        tmp = carpeta / f"vod_{sid}"
        try:
            audio, fecha = bajar_audio_short(ShortAjeno(sid, titulo or "", "", vistas, 0), tmp)
            try:
                dur_short = probe(audio).duracion or 30.0
            except Exception:
                dur_short = 30.0
            cuando = (datetime.fromisoformat(publicado.replace("Z", "+00:00")) if publicado
                      else fecha or datetime.now(timezone.utc))
            buscar = vd.vods_kick if s.plataforma == "kick" else vd.vods_twitch
            vods = buscar(cliente, s.login, cuando - timedelta(days=cfg.dias_antes), cuando)
            mejor = vd.buscar_en_vods(audio, vods, carpeta / "huellas", cfg.umbral, avisar, hasta, reloj)
        except Exception as e:
            avisar(f"pegó (VOD): {sid}: {str(e)[:150]}")
            continue
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if not mejor:
            continue
        v, seg, valor = mejor
        hallados += 1
        # ¿Stream de un programa de terceros? Excluido: no se procesa; en experimento: con aviso.
        bloqueado = next((p for p in s.palabras_programa if es_programa_de_terceros(v.titulo, (p,))), "")
        experimento = next((p for p in s.programa_aviso if es_programa_de_terceros(v.titulo, (p,))), "")
        programa = bloqueado or experimento
        conn.execute("""UPDATE pegados SET vod_url = ?, vod_segundo = ?, coincidencia = ?, vod_programa = ?
                        WHERE short_id = ?""", (v.pagina, seg, valor, programa or None, sid))
        conn.commit()
        avisar(f"pegó (VOD): «{(titulo or '')[:50]}» está en {v.pagina} a los {seg / 60:.1f} min "
               f"({valor:.2f})" + (f" — stream del {programa}" if programa else ""))
        if bloqueado:
            conn.execute("UPDATE pegados SET vod_resultado = ? WHERE short_id = ?",
                         (f"no lo procesé: el {bloqueado} está excluido", sid))
            conn.commit()
            continue
        if procesar_tramo is None or (hasta is not None and reloj() >= hasta):
            continue
        inicio, dur = vd.tramo(seg, dur_short)
        clip_id = f"vod_{v.plataforma}_{v.id}_{int(inicio)}"
        try:
            ruta = vd.cortar(v, inicio, dur, (carpeta_tramos or carpeta / "tramos") / f"{clip_id}.mp4")
            d = Descarga(ruta, clip_id, f"{v.pagina}?t={int(inicio)}s", v.titulo, v.plataforma, s.login,
                         s.login, dur, 0, v.inicio + timedelta(seconds=inicio), "", de_streamer=True)
            aviso = (AVISO_PROGRAMA.format(experimento) + " (stream del programa: revisalo con más cuidado)"
                     if experimento else "")
            r = procesar_tramo(d, aviso, {"vistas": int(vistas or 0), "canal": canal or ""})
            resultado = f"se descartó: {r.descartado}" if r.descartado else "listo"
        except Exception as e:
            avisar(f"pegó (VOD): no pude cortar o procesar {clip_id}: {str(e)[:150]}")
            clip_id, resultado = None, f"no pude cortarlo: {str(e)[:80]}"
        conn.execute("UPDATE pegados SET vod_clip_id = ?, vod_resultado = ? WHERE short_id = ?",
                     (clip_id, resultado, sid))
        conn.commit()
    return hallados


def texto_sin_original(filas: list[dict]) -> str:
    """El resumen en HTML de Telegram: título, vistas y link de cada Short sin original."""
    import html

    if not filas:
        return ""
    lineas = ["🔥 <b>Pegó en otros canales</b> — no encontré el clip original, buscalo vos:"]
    for f in filas:
        vistas = f"{f['vistas']:,}".replace(",", ".")
        cuantos = f", comparé con {f['comparados']} clips" if f["comparados"] else ""
        if f.get("vod_url"):
            m, s = divmod(int(f["vod_segundo"]), 60)
            h, m = divmod(m, 60)
            donde = (f"No hay clip, pero salió del VOD: <a href=\"{f['vod_url']}\">acá</a>, en el "
                     f"{h}:{m:02d}:{s:02d}.")
            if f.get("vod_programa"):   # el 412: se avisa, no se descarta en silencio
                donde += f" ⚠️ Pegó, pero es del {html.escape(f['vod_programa'])}."
            res = f.get("vod_resultado") or ""
            if res == "listo":
                donde += (f" Lo corté del VOD y lo procesé: compite en la próxima entrega "
                          f"(<code>{html.escape(f['vod_clip_id'])}</code>).")
            elif res:
                donde += f" {html.escape(res[0].upper() + res[1:])}."
        else:
            donde = "No encontré el original."
        lineas.append(f"• <a href=\"{f['url']}\">{html.escape(f['titulo'][:70])}</a> — "
                      f"{html.escape(f['canal'])}, {vistas} vistas ({html.escape(f['streamer'])}"
                      f"{cuantos}). {donde}")
    return "\n".join(lineas)


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

CLAVE_SIGUIENTE = "pego_siguiente"      # bot_estado: el login por el que arranca la próxima vuelta


def rotar(conn: sqlite3.Connection, streamers: list[Streamer]) -> list[Streamer]:
    """Arranca por el que quedó pendiente la vuelta anterior: con el tope de tiempo, si siempre se
    empezara por el primero, Davo se comería los 15 minutos todos los días y nadie más."""
    siguiente = db.get_valor(conn, CLAVE_SIGUIENTE)
    logins = [s.login for s in streamers]
    if siguiente in logins:
        k = logins.index(siguiente)
        return streamers[k:] + streamers[:k]
    return list(streamers)


def buscar_pegados(conn: sqlite3.Connection, streamers: list[Streamer], cfg, carpeta: Path,
                   twitch=None, kick=None, buscar=None, avisar=log.info,
                   ahora: datetime | None = None, hasta: float | None = None,
                   reloj=time.monotonic) -> list[Recuento]:
    """Una vuelta: busca, filtra, compara y guarda. Devuelve el recuento de cada streamer.
    `buscar(consulta, desde)`: el buscador (API o yt-dlp); lo elige quien llama.
    `hasta` (en `reloj`): el tope; al pasarlo se corta, lo que quedó a medias no se anota y la
    próxima vuelta arranca por ese streamer."""
    import shutil

    ahora = ahora or datetime.now(timezone.utc)
    hoy = ahora.astimezone(timezone(timedelta(hours=-3))).date().isoformat()
    buscar = buscar or buscar_ytdlp
    limpiar_huellas(carpeta / "huellas")
    recuentos: list[Recuento] = []
    orden = rotar(conn, streamers)
    for n_s, s in enumerate(orden):
        if hasta is not None and reloj() >= hasta:
            db.set_valor(conn, CLAVE_SIGUIENTE, s.login)
            avisar(f"pegó: se terminó el tiempo; la próxima vuelta arranca por {s.login}")
            break
        rec = Recuento(s.login, consulta(s))
        if busquedas_hechas(conn, hoy) >= cfg.busquedas_por_dia:
            rec.error = f"llegué al tope de {cfg.busquedas_por_dia} búsquedas de hoy"
            recuentos.append(rec)
            avisar(f"pegó: {rec.error}")
            break
        recuentos.append(rec)
        try:
            resultados = buscar(rec.consulta, ahora - timedelta(days=cfg.dias))
        except Exception as e:
            rec.error = str(e)[:200]
            avisar(f"pegó: la búsqueda de {s.login} falló: {e}")
            continue
        finally:
            anotar_busqueda(conn, hoy)
        elegidos = filtrar(resultados, s, cfg.min_vistas, cfg.canales_propios, rec)
        nuevos = [x for x in elegidos if not ya_visto(conn, x.id)]
        rec.ya_vistos = len(elegidos) - len(nuevos)
        sin_tiempo = False
        for short in nuevos[:cfg.por_streamer]:
            tmp = carpeta / short.id
            try:
                audio, fecha = bajar_audio_short(short, tmp)
                short.publicado = short.publicado or (fecha.isoformat() if fecha else "")
                cuando = datetime.fromisoformat(short.publicado.replace("Z", "+00:00")) if short.publicado else ahora
                clips = originales(s, cuando, cfg.dias_antes, cfg.max_originales, twitch, kick, ahora)
                hallado = encontrar(audio, clips, tmp, cfg.umbral, hasta=hasta, reloj=reloj)
            except SinTiempo:
                sin_tiempo = True
                break
            except Exception as e:
                avisar(f"pegó: {short.id} ({short.canal}): {e}")
                continue
            finally:
                shutil.rmtree(tmp, ignore_errors=True)   # el video ajeno no se guarda
            rec.comparados += 1
            rec.clips.append(len(clips))
            guardar(conn, short, s.login, hallado, len(clips))
            if hallado[0] is not None:
                rec.encontrados += 1
                avisar(f"pegó: {s.login} — «{short.titulo[:50]}» ({short.canal}, {short.vistas:,} "
                       f"vistas) = {hallado[0].url} (coincidencia {hallado[1]:.2f})")
            else:
                rec.sin_original.append(short)
                avisar(f"pegó: {s.login} — «{short.titulo[:50]}»: no está en sus {len(clips)} clips "
                       f"(mejor coincidencia {hallado[1]:.2f})")
        if sin_tiempo:
            rec.error = "se terminó el tiempo a mitad de un Short (se retoma en la próxima vuelta)"
            db.set_valor(conn, CLAVE_SIGUIENTE, s.login)
            avisar(f"pegó: {rec.texto(cfg.min_vistas)}")
            break
        avisar(f"pegó: {rec.texto(cfg.min_vistas)}")
        # Terminó este: la próxima vuelta arranca por el que sigue.
        db.set_valor(conn, CLAVE_SIGUIENTE, orden[(n_s + 1) % len(orden)].login)
    return recuentos
