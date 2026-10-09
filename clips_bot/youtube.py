"""Subida a YouTube (§3 paso 9): preparada, APAGADA hasta la auditoría (`youtube_upload_enabled`).

Dos canales de la misma cuenta de Google, cada uno con su token:
    rots               los clips
    pequena_historia   las efemérides

Sin librerías de Google a propósito (en la Pi cada dependencia es un problema más): OAuth de
"aplicación de escritorio" con redirección a 127.0.0.1 y la API REST con `requests`.

    config/client_secret.json            la credencial OAuth (se baja de Google Cloud; NO va a git)
    config/youtube_token_<canal>.json    el refresh token de cada canal (NO va a git)

Cómo conseguir todo eso, paso a paso: docs/auditoria-youtube.md.

Por qué apagado: los videos subidos por API desde un proyecto SIN auditar quedan bloqueados como
privados para siempre (§1). Con `youtube_upload_enabled: false` nada de esto se llama desde el bot.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

from .config import CONFIG_DIR

log = logging.getLogger(__name__)

CANALES = {"rots": "Rots (clips)", "pequena_historia": "Pequeña Historia (efemérides)"}
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube",       # para cancelar (videos.update) y listar
          "https://www.googleapis.com/auth/yt-analytics.readonly"]   # métricas de los Shorts (§4b)
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
AR = timezone(timedelta(hours=-3), "AR")
MAX_TITULO, MAX_DESCRIPCION, MAX_TAGS = 100, 5000, 500   # límites de YouTube


class YouTubeError(RuntimeError):
    pass


def ruta_secreto() -> Path:
    return CONFIG_DIR / "client_secret.json"


def ruta_token(canal: str) -> Path:
    return CONFIG_DIR / f"youtube_token_{canal}.json"


def _secreto(ruta: Path | None = None) -> dict:
    ruta = ruta or ruta_secreto()
    if not ruta.exists():
        raise YouTubeError(f"Falta {ruta}: bajalo de Google Cloud (docs/auditoria-youtube.md, paso 4).")
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return d.get("installed") or d.get("web") or d


# ---- OAuth -----------------------------------------------------------------------------

def url_autorizacion(client_id: str, redirect: str, estado: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": estado})


def autorizar(canal: str, puerto: int = 8765, abrir=None, esperar=None,
              session: requests.Session | None = None) -> dict:
    """El primer login, en una máquina con navegador (la de Windows). Abre Google, Santi elige la
    cuenta y DESPUÉS EL CANAL (hay que elegir el de ese canal, no la cuenta personal), y el código
    vuelve a 127.0.0.1. Guarda el refresh token en config/youtube_token_<canal>.json; ese archivo
    se copia a la Pi."""
    import webbrowser

    if canal not in CANALES:
        raise YouTubeError(f"Canal {canal!r}: los que hay son {', '.join(CANALES)}")
    s = _secreto()
    redirect = f"http://127.0.0.1:{puerto}/"
    estado = secrets.token_urlsafe(16)
    url = url_autorizacion(s["client_id"], redirect, estado)
    print(f"\nAbrí esto si no se abrió solo, y elegí el canal «{CANALES[canal]}»:\n{url}\n")
    (abrir or webbrowser.open)(url)
    codigo = (esperar or _esperar_codigo)(puerto, estado)
    session = session or requests.Session()
    r = session.post(TOKEN_URL, data={"code": codigo, "client_id": s["client_id"],
                                      "client_secret": s["client_secret"], "redirect_uri": redirect,
                                      "grant_type": "authorization_code"}, timeout=30)
    if r.status_code != 200:
        raise YouTubeError(f"Google no dio el token: {r.status_code} {r.text[:200]}")
    tok = r.json()
    if not tok.get("refresh_token"):
        raise YouTubeError("Google no dio refresh_token. Sacale el permiso a la app en "
                           "myaccount.google.com/permissions y volvé a intentar.")
    datos = {"canal": canal, "refresh_token": tok["refresh_token"]}
    cliente = Cliente(canal, session=session, token=datos)
    info = cliente.mi_canal()
    datos.update(channel_id=info["id"], channel_title=info["titulo"])
    ruta_token(canal).write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


def _esperar_codigo(puerto: int, estado: str, timeout_s: float = 300) -> str:
    """Un servidor de una sola respuesta en 127.0.0.1: ahí vuelve Google con el código."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    recibido: dict = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            recibido.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("Listo, ya podés cerrar esta pestaña y volver a la consola.".encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", puerto), H)
    srv.timeout = timeout_s
    srv.handle_request()
    if recibido.get("state") != estado:
        raise YouTubeError("La respuesta de Google no corresponde a este pedido (state distinto).")
    if "code" not in recibido:
        raise YouTubeError(f"Google no autorizó: {recibido.get('error', 'sin código')}")
    return recibido["code"]


# ---- la API ------------------------------------------------------------------------------

class Cliente:
    """Un canal. El access token se renueva solo con el refresh token guardado."""

    def __init__(self, canal: str, session: requests.Session | None = None, token: dict | None = None,
                 secreto: dict | None = None):
        self.canal = canal
        self.session = session or requests.Session()
        if token is None:
            ruta = ruta_token(canal)
            if not ruta.exists():
                raise YouTubeError(f"Falta {ruta}: corré `python -m clips_bot youtube-auth {canal}` "
                                   "en la compu con navegador y copiá el archivo a la Pi.")
            token = json.loads(ruta.read_text(encoding="utf-8"))
        self.token = token
        self._secreto = secreto
        self._access: str | None = None
        self._vence = 0.0

    def _headers(self) -> dict:
        if not self._access or time.time() > self._vence - 60:
            s = self._secreto or _secreto()
            r = self.session.post(TOKEN_URL, data={
                "client_id": s["client_id"], "client_secret": s["client_secret"],
                "refresh_token": self.token["refresh_token"], "grant_type": "refresh_token"},
                timeout=30)
            if r.status_code != 200:
                raise YouTubeError(f"No pude renovar el acceso de {self.canal}: {r.status_code} "
                                   f"{r.text[:200]}")
            d = r.json()
            self._access, self._vence = d["access_token"], time.time() + int(d.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._access}"}

    def mi_canal(self) -> dict:
        r = self.session.get(f"{API}/channels", params={"part": "snippet", "mine": "true"},
                             headers=self._headers(), timeout=30)
        items = (r.json() or {}).get("items") or [] if r.status_code == 200 else []
        if not items:
            raise YouTubeError(f"No encontré el canal de {self.canal}: {r.status_code} {r.text[:200]}")
        return {"id": items[0]["id"], "titulo": items[0]["snippet"]["title"]}

    def subir(self, video: Path, titulo: str, descripcion: str, tags: list[str],
              publicar: datetime, categoria: str = "24") -> str:
        """Sube en PRIVADO con `publishAt`: YouTube lo hace público solo a esa hora. Devuelve el id.
        Upload reanudable (dos pasos): el mp4 entero en un PUT; son 20-40 MB."""
        cuerpo = metadatos(titulo, descripcion, tags, publicar, categoria)
        tam = video.stat().st_size
        r = self.session.post(UPLOAD, params={"uploadType": "resumable", "part": "snippet,status"},
                              headers={**self._headers(), "Content-Type": "application/json",
                                       "X-Upload-Content-Type": "video/mp4",
                                       "X-Upload-Content-Length": str(tam)},
                              data=json.dumps(cuerpo), timeout=60)
        if r.status_code != 200 or not r.headers.get("Location"):
            raise YouTubeError(f"YouTube no aceptó la subida: {r.status_code} {r.text[:300]}")
        with video.open("rb") as f:
            r2 = self.session.put(r.headers["Location"], data=f, timeout=600,
                                  headers={"Content-Type": "video/mp4", "Content-Length": str(tam)})
        if r2.status_code not in (200, 201):
            raise YouTubeError(f"La subida se cortó: {r2.status_code} {r2.text[:300]}")
        self.respuesta_subida = r2.json()       # COMPLETA: uploadStatus, privacyStatus, publishAt…
        log.info("videos.insert %s: %s", self.canal, json.dumps(self.respuesta_subida, ensure_ascii=False)[:2000])
        return self.respuesta_subida["id"]

    def mis_videos(self, desde: datetime, maximo: int = 200) -> list[dict]:
        """Los videos subidos al canal desde `desde`, más nuevos primero: [{id, titulo, publicado}].
        Sale de la lista de "uploads" del canal (1 unidad por página de 50)."""
        r = self.session.get(f"{API}/channels", params={"part": "contentDetails", "mine": "true"},
                             headers=self._headers(), timeout=30)
        items = (r.json() or {}).get("items") or [] if r.status_code == 200 else []
        if not items:
            raise YouTubeError(f"No encontré los videos de {self.canal}: {r.status_code} {r.text[:200]}")
        lista = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        out, pagina = [], None
        while len(out) < maximo:
            params = {"part": "snippet,contentDetails", "playlistId": lista, "maxResults": 50}
            if pagina:
                params["pageToken"] = pagina
            r = self.session.get(f"{API}/playlistItems", params=params, headers=self._headers(),
                                 timeout=30)
            if r.status_code != 200:
                raise YouTubeError(f"playlistItems: {r.status_code} {r.text[:200]}")
            d = r.json()
            for it in d.get("items") or []:
                publicado = it["contentDetails"].get("videoPublishedAt") or it["snippet"]["publishedAt"]
                cuando = datetime.fromisoformat(publicado.replace("Z", "+00:00"))
                if cuando < desde:
                    return out
                out.append({"id": it["contentDetails"]["videoId"], "titulo": it["snippet"]["title"],
                            "publicado": cuando.isoformat()})
            pagina = d.get("nextPageToken")
            if not pagina:
                break
        return out

    def _analytics(self, params: dict) -> list[list]:
        r = self.session.get(ANALYTICS, params={"ids": "channel==MINE", **params},
                             headers=self._headers(), timeout=60)
        if r.status_code != 200:
            raise YouTubeError(f"YouTube Analytics: {r.status_code} {r.text[:300]}")
        return (r.json() or {}).get("rows") or []

    def metricas(self, video_ids: list[str], desde: datetime, hasta: datetime) -> dict[str, dict]:
        """{video_id: {vistas, duracion_media_s, pct_visto_medio}} (YouTube Analytics, por video)."""
        out: dict[str, dict] = {}
        for i in range(0, len(video_ids), 200):
            filas = self._analytics({
                "startDate": desde.strftime("%Y-%m-%d"), "endDate": hasta.strftime("%Y-%m-%d"),
                "metrics": "views,averageViewDuration,averageViewPercentage", "dimensions": "video",
                "filters": "video==" + ",".join(video_ids[i:i + 200])})
            for vid, vistas, dur, pct in filas:
                out[vid] = {"vistas": int(vistas), "duracion_media_s": float(dur),
                            "pct_visto_medio": float(pct)}
        return out

    def pct_entero(self, video_id: str, desde: datetime, hasta: datetime) -> float | None:
        """% de la audiencia que sigue mirando al final (curva de retención en 100 %): lo más
        parecido que da YouTube a "lo mira entero". En un Short puede pasar de 100 (repeticiones)."""
        filas = self._analytics({
            "startDate": desde.strftime("%Y-%m-%d"), "endDate": hasta.strftime("%Y-%m-%d"),
            "metrics": "audienceWatchRatio", "dimensions": "elapsedVideoTimeRatio",
            "filters": f"video=={video_id}"})
        return round(float(filas[-1][1]) * 100, 1) if filas else None

    def cancelar(self, video_id: str) -> None:
        """Saca la programación: el video queda privado y sin fecha (no se borra: se puede
        publicar a mano desde Studio o borrar ahí)."""
        r = self.session.put(f"{API}/videos", params={"part": "status"},
                             headers={**self._headers(), "Content-Type": "application/json"},
                             data=json.dumps({"id": video_id, "status": {
                                 "privacyStatus": "private", "selfDeclaredMadeForKids": False}}),
                             timeout=30)
        self.respuesta_cancelar = {"http": r.status_code, "cuerpo": _json_o_texto(r)}
        log.info("videos.update (cancelar) %s %s: %s", self.canal, video_id,
                 json.dumps(self.respuesta_cancelar, ensure_ascii=False)[:2000])
        if r.status_code != 200:
            raise YouTubeError(f"No pude cancelar {video_id}: {r.status_code} {r.text[:200]}")

    def estado_video(self, video_id: str) -> dict:
        """videos.list del video (status, processingDetails, snippet). {"existe": False, …} si YouTube
        no lo devuelve (borrado o sacado); con uploadStatus, failureReason y rejectionReason si existe."""
        r = self.session.get(f"{API}/videos", params={"part": "status,processingDetails,snippet",
                                                      "id": video_id}, headers=self._headers(), timeout=30)
        cuerpo = _json_o_texto(r)
        items = (cuerpo.get("items") or []) if isinstance(cuerpo, dict) else []
        if r.status_code != 200:
            return {"existe": None, "http": r.status_code, "cuerpo": cuerpo}
        if not items:
            return {"existe": False, "http": 200, "cuerpo": cuerpo}
        it = items[0]
        st = it.get("status") or {}
        return {"existe": True, "http": 200, "uploadStatus": st.get("uploadStatus"),
                "failureReason": st.get("failureReason"), "rejectionReason": st.get("rejectionReason"),
                "privacyStatus": st.get("privacyStatus"), "publishAt": st.get("publishAt"),
                "canal": (it.get("snippet") or {}).get("channelId"),
                "procesamiento": (it.get("processingDetails") or {}).get("processingStatus"),
                "item": it}


def _json_o_texto(r):
    try:
        return r.json()
    except ValueError:
        return r.text[:2000]


def metadatos(titulo: str, descripcion: str, tags: list[str], publicar: datetime,
              categoria: str = "24") -> dict:
    """El cuerpo de videos.insert, con los límites de YouTube aplicados. `publishAt` exige
    privacyStatus private; los hashtags van en la descripción y, sin el #, como tags."""
    limpios, total = [], 0
    for t in tags:
        t = t.lstrip("#").strip()
        if t and total + len(t) + 1 <= MAX_TAGS:
            limpios.append(t)
            total += len(t) + 1
    return {
        "snippet": {"title": titulo[:MAX_TITULO], "description": descripcion[:MAX_DESCRIPCION],
                    "tags": limpios, "categoryId": categoria, "defaultLanguage": "es",
                    "defaultAudioLanguage": "es"},
        "status": {"privacyStatus": "private",
                   "publishAt": publicar.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": False},
    }


# ---- cuándo publicar ---------------------------------------------------------------------------

def proximo_horario(hora: str, ahora: datetime | None = None, margen_min: int = 20,
                    ocupados: set[str] | None = None, horarios: list[str] | None = None) -> datetime:
    """La próxima vez que sea `hora` (AR) con al menos `margen_min` para que YouTube procese el
    video. Si ese horario ya está tomado en el canal, el siguiente de `horarios` (o el mismo al día
    siguiente). `ocupados`: ISO UTC de lo ya programado."""
    ahora = (ahora or datetime.now(timezone.utc)).astimezone(AR)
    ocupados = ocupados or set()
    horas = horarios or [hora]
    empezar = horas.index(hora) if hora in horas else 0
    for dia in range(0, 8):
        for k in range(len(horas)):
            if dia == 0 and k < empezar:
                continue
            hh, mm = (int(x) for x in horas[k].split(":"))
            t = (ahora + timedelta(days=dia)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            iso = t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if t >= ahora + timedelta(minutes=margen_min) and iso not in ocupados:
                return t
    raise YouTubeError("No encontré un horario libre en la próxima semana.")
