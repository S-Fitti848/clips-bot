"""Videos para las frases de acción de Pequeña Historia (pedido 2026-09-29).

2 o 3 frases por Short (las marca Gemini al escribir el guion: `accion`) se ilustran con video en
vez de foto. Las fuentes, en este orden:
  1. filmación real de la época, dominio público o licencia libre: Wikimedia Commons (mismas
     reglas de licencia que las fotos) y archive.org (solo dominio público: `licenseurl` con
     "publicdomain");
  2. si la 1 no trae nada: video libre de stock (Pexels y Pixabay, con su clave en el .env) y NASA
     para temas de espacio. Sin fecha o modernos: para una frase del pasado solo sirven si Gemini
     confirma que no son un anacronismo (cielo, mar, fuego, el espacio);
  3. si tampoco, la frase sigue con su foto.
Nada de video generado por IA. El audio del video nunca se usa (va la voz y la música).

Medido 2026-09-29 con el Sputnik (4/10/1957): Commons y archive.org tienen el noticiero original
"New Moon" (Universal Newsreel, dominio público, 45 s); NASA para "Sputnik" devuelve material de
2005 (lo saca la regla de época).

Gemini elige el video y el MOMENTO dentro de la misma llamada en la que elige las fotos
(efemerides.elegir_fotos): de cada video candidato ve 3 cuadros, y dice cuál sirve. Ese cuadro es
también la miniatura de la hoja de aprobación.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from .config import env, user_agent
from .media import find_bin

log = logging.getLogger(__name__)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ARCHIVE_BUSCAR = "https://archive.org/advancedsearch.php"
NASA_BUSCAR = "https://images-api.nasa.gov/search"
POR_FUENTE = 3            # candidatos por fuente y frase
FRAMES = (0.2, 0.5, 0.8)  # qué cuadros ve Gemini de cada video (fracción del largo usable)
LARGO_USABLE_S = 600      # de una película larga de archive.org se mira solo el principio
DURACION_MIN_S = 3.0
PAUSA_WIKIMEDIA_S = 2.0   # como con las fotos: upload.wikimedia.org limita
DERIVADOS = ("720p.vp9.webm", "480p.vp9.webm", "720p.webm", "480p.webm", "360p.mpeg4.mov",
             "360p.vp9.webm")
_ESPACIO = re.compile(r"\b(space|rocket|satellite|moon|lunar|orbit\w*|astronaut\w*|cosmonaut\w*|"
                      r"planet\w*|launch\w*|nasa|spacecraft|shuttle|telescope|galaxy|mars|apollo|"
                      r"sputnik|comet|asteroid|star|stars)\b", re.I)
_ANIOS = re.compile(r"\b(1[4-9]\d\d|20\d\d)s?\b|\b\d{1,2}(st|nd|rd|th) century\b", re.I)
ARCHIVO = ("commons", "archive")          # filmación de archivo (etapa 1)

# Estudios y marcas que no se usan NUNCA, venga de donde venga el video (Santi, 2026-10-08: una
# efeméride intentó bajar un "disne…" de archive.org). Se mira título, autor, links y, en archive.org,
# también la colección, los temas y la descripción del item.
MARCAS_PROHIBIDAS = ("disney", "pixar", "warner", "universal", "paramount", "fox", "sony",
                     "dreamworks", "marvel", "nintendo")
_MARCAS = re.compile(r"(?<![a-z])(" + "|".join(MARCAS_PROHIBIDAS) + r")", re.I)

# Tope de cada llamada a ffmpeg/ffprobe sobre un video remoto, y un reintento: un servidor lento
# (archive.org) no puede tumbar la efeméride (2026-10-08: TimeoutExpired bajando un video).
TOPE_FRAME_S = 60
TOPE_TRAMO_S = 180
TOPE_PROBE_S = 45


def marca_prohibida(*textos) -> str:
    """La marca prohibida que aparece en alguno de los textos ("" si ninguna)."""
    for t in textos:
        for x in (t if isinstance(t, (list, tuple)) else [t]):
            m = _MARCAS.search(str(x or ""))
            if m:
                return m.group(1).lower()
    return ""


def licencia_archive(meta: dict) -> str:
    """La licencia de un item de archive.org SEGÚN SUS METADATOS (`licenseurl` o `rights`), solo si
    dice explícitamente dominio público, CC0 o CC BY (sin NC, ND ni SA). "" = no sirve."""
    url = str(meta.get("licenseurl") or "").lower()
    if url:
        if "publicdomain/zero" in url:
            return "CC0"
        if "publicdomain" in url:
            return "Dominio público"
        m = re.search(r"creativecommons\.org/licenses/by/(\d\.\d)", url)
        if m:
            return f"CC BY {m.group(1)}"
        return ""                       # by-sa, by-nc, by-nd y cualquier otra: afuera
    derechos = meta.get("rights") or ""
    derechos = " ".join(derechos) if isinstance(derechos, list) else str(derechos)
    d = derechos.lower()
    if re.search(r"\b(non-?commercial|no ?deriv|share ?alike|all rights reserved|copyright ©|\bnc\b|\bnd\b|\bsa\b)", d):
        return ""
    if "public domain" in d or "dominio público" in d:
        return "Dominio público"
    if re.search(r"\bcc0\b", d):
        return "CC0"
    if re.search(r"\bcc[ -]by\b", d):
        return "CC BY"
    return ""


def _ejecutar(args: list[str], tope_s: float, intentos: int = 2, **kw):
    """subprocess.run con tope de tiempo y UN reintento. None si se pasó del tope las dos veces."""
    for _ in range(intentos):
        try:
            return subprocess.run(args, capture_output=True, timeout=tope_s, **kw)
        except subprocess.TimeoutExpired:
            log.warning("ffmpeg tardó más de %.0f s (%s): %s", tope_s, args[0], args[-1][:120])
    return None


@dataclass
class Video:
    fuente: str               # commons | archive | nasa | pexels | pixabay
    titulo: str
    url: str                  # el archivo a bajar (un derivado chico cuando hay)
    pagina: str               # para el crédito
    licencia: str
    autor: str
    anio: int | None
    duracion: float
    momentos: list[float] = field(default_factory=list)   # segundos de los cuadros que ve Gemini
    frames: list[str] = field(default_factory=list)       # esos cuadros, bajados
    momento: float = 0.0      # el cuadro que eligió Gemini: el tramo se corta alrededor
    ruta: str = ""            # el tramo ya bajado (al armar el video)

    @property
    def de_archivo(self) -> bool:
        return self.fuente in ARCHIVO

    def etiqueta(self) -> str:
        nombres = {"commons": "Wikimedia Commons", "archive": "archive.org", "nasa": "NASA",
                   "pexels": "Pexels", "pixabay": "Pixabay"}
        return f"{nombres.get(self.fuente, self.fuente)}{f', {self.anio}' if self.anio else ''}"

    def credito(self) -> str:
        return f"{self.titulo[:80]} — {self.autor} — {self.licencia} — {self.pagina}"

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Video":
        return cls(**d)


def sin_anios(q: str) -> str:
    """La búsqueda sin el año ni la década: los buscadores de video los toman como palabra
    obligatoria y no traen nada; la época se controla con los datos de cada video."""
    return " ".join(_ANIOS.sub(" ", q).split())


def consultas(mostrar: str, tema: str = "") -> list[str]:
    """De la más puntual a la más general. Medido 2026-09-29 con el Sputnik: "R-7 rocket launch
    pad" no trae nada en Commons ni en archive.org; "rocket launch" (con los años 1955-1967 en
    archive.org) trae primero el noticiero de 1957, y el tema del artículo ("Sputnik 1") también."""
    palabras = sin_anios(mostrar).split()
    out = [" ".join(palabras[:k]) for k in range(len(palabras), 1, -1)]
    out += [" ".join(palabras[k:k + 2]) for k in range(1, len(palabras) - 1)]
    if tema:
        out.append(sin_anios(tema.replace("_", " ")))
    return [q for q in dict.fromkeys(out) if q]


def es_de_espacio(q: str) -> bool:
    return bool(_ESPACIO.search(q or ""))


def _anio(texto) -> int | None:
    m = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", str(texto or ""))
    return int(m.group(1)) if m else None


def _segundos(v) -> float:
    """archive.org da el largo como "45.28" o "12:34" o "1:02:03"."""
    try:
        partes = [float(x) for x in str(v).split(":")]
    except ValueError:
        return 0.0
    s = 0.0
    for p in partes:
        s = s * 60 + p
    return s


class Buscador:
    def __init__(self, session: requests.Session | None = None, timeout: float = 30, sleep=time.sleep):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = user_agent()
        self.timeout = timeout
        self._sleep = sleep

    def _json(self, url: str, **kw) -> dict:
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.json()

    # ---- etapa 1: filmación de archivo ----------------------------------------------------

    def commons(self, q: str, n: int = POR_FUENTE) -> list[Video]:
        from .efemerides import autor_de, licencia_libre, sin_html

        d = self._json(COMMONS_API, params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{q} filetype:video", "gsrnamespace": 6, "gsrlimit": n * 2,
            "prop": "videoinfo", "viprop": "url|size|mime|extmetadata|derivatives",
            "viextmetadatalanguage": "es"})
        paginas = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        out = []
        for p in paginas:
            vi = (p.get("videoinfo") or [{}])[0]
            em = vi.get("extmetadata") or {}

            def meta(k: str) -> str:
                return sin_html((em.get(k) or {}).get("value", ""))

            lic = meta("LicenseShortName")
            if meta("NonFree").lower() in ("true", "1") or not licencia_libre(lic):
                continue
            autor = autor_de(em)
            if meta("AttributionRequired").lower() == "true" and not autor:
                continue
            dur = float(vi.get("duration") or 0)
            ders = {x.get("transcodekey"): x.get("src") for x in vi.get("derivatives") or []}
            url = next((ders[k] for k in DERIVADOS if ders.get(k)), vi.get("url") or "")
            if dur < DURACION_MIN_S or not url:
                continue
            titulo = meta("ObjectName") or p["title"].split(":", 1)[-1].rsplit(".", 1)[0].replace("_", " ")
            out.append(Video("commons", titulo, url, vi.get("descriptionurl") or "", lic,
                             autor or "autor desconocido", _anio(meta("DateTimeOriginal")), dur))
            if len(out) >= n:
                break
        return out

    def archive(self, q: str, anio: int | None = None, n: int = POR_FUENTE) -> list[Video]:
        """Solo items cuyos METADATOS dicen explícitamente dominio público, CC0 o CC BY
        (`licenseurl` o `rights`, `licencia_archive`); si no lo dicen, afuera. Nunca de las marcas
        prohibidas. Con `anio`, solo los de ese año a 10 después (una frase del pasado)."""
        consulta = (f"({q}) AND mediatype:movies AND (licenseurl:*publicdomain* OR "
                    f"licenseurl:*licenses/by/* OR rights:\"public domain\")")
        if anio:
            consulta += f" AND year:[{anio - 2} TO {anio + 10}]"
        d = self._json(ARCHIVE_BUSCAR, params={"q": consulta, "fl[]": ["identifier", "title", "year",
                                                                        "licenseurl", "creator"],
                                                "rows": n * 2, "output": "json"})
        out = []
        for doc in d.get("response", {}).get("docs", []):
            ident = doc.get("identifier")
            try:
                m = self._json(f"https://archive.org/metadata/{ident}")
            except (requests.RequestException, ValueError):
                continue
            md = m.get("metadata") or {}
            lic = licencia_archive(md)
            if not lic:
                log.info("archive.org %s: sin licencia libre explícita en los metadatos, afuera", ident)
                continue
            marca = marca_prohibida(ident, md.get("title"), md.get("creator"), md.get("collection"),
                                    md.get("subject"), md.get("description"), md.get("publisher"))
            if marca:
                log.info("archive.org %s: %s (marca prohibida), afuera", ident, marca)
                continue
            mp4s = [f for f in m.get("files", []) if str(f.get("name", "")).lower().endswith(".mp4")]
            # El más liviano que no sea una miniatura animada: "512Kb MPEG4" o "h.264".
            mp4s.sort(key=lambda f: int(f.get("size") or 0))
            elegido = next((f for f in mp4s if int(f.get("size") or 0) > 200_000), None)
            if not elegido:
                continue
            dur = _segundos(elegido.get("length") or 0)
            if dur < DURACION_MIN_S:
                continue
            creador = md.get("creator") or doc.get("creator")
            creador = ", ".join(creador) if isinstance(creador, list) else str(creador or "archive.org")
            out.append(Video("archive", str(doc.get("title") or ident),
                             f"https://archive.org/download/{ident}/{elegido['name']}",
                             f"https://archive.org/details/{ident}", lic, creador,
                             _anio(doc.get("year")), dur))
            if len(out) >= n:
                break
        return out

    # ---- etapa 2: stock y NASA ------------------------------------------------------------

    def nasa(self, q: str, n: int = POR_FUENTE) -> list[Video]:
        d = self._json(NASA_BUSCAR, params={"q": q, "media_type": "video"})
        out = []
        for it in (d.get("collection") or {}).get("items", [])[:n * 2]:
            dd = (it.get("data") or [{}])[0]
            try:
                archivos = self._json(it["href"])
            except (requests.RequestException, ValueError, KeyError):
                continue
            mp4 = next((a for suf in ("~mobile.mp4", "~medium.mp4", "~small.mp4", "~orig.mp4")
                        for a in archivos if a.endswith(suf)), None)
            if not mp4:
                continue
            dur = duracion_url(mp4.replace("http://", "https://"))
            if dur < DURACION_MIN_S:
                continue
            nid = dd.get("nasa_id", "")
            out.append(Video("nasa", dd.get("title") or nid, mp4.replace("http://", "https://"),
                             f"https://images.nasa.gov/details/{nid}", "NASA (dominio público)",
                             dd.get("center") or "NASA", _anio(dd.get("date_created")), dur))
            if len(out) >= n:
                break
        return out

    def pexels(self, q: str, n: int = POR_FUENTE) -> list[Video]:
        clave = env("PEXELS_API_KEY", requerido=False)
        if not clave:
            return []
        d = self._json("https://api.pexels.com/videos/search", params={"query": q, "per_page": n},
                       headers={"Authorization": clave})
        out = []
        for v in d.get("videos") or []:
            archivos = sorted((f for f in v.get("video_files") or [] if f.get("file_type") == "video/mp4"),
                              key=lambda f: abs(int(f.get("width") or 0) - 1280))
            if not archivos or float(v.get("duration") or 0) < DURACION_MIN_S:
                continue
            out.append(Video("pexels", v.get("url", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
                             archivos[0]["link"], v.get("url", ""), "Licencia de Pexels",
                             (v.get("user") or {}).get("name") or "Pexels", None, float(v["duration"])))
        return out

    def pixabay(self, q: str, n: int = POR_FUENTE) -> list[Video]:
        clave = env("PIXABAY_API_KEY", requerido=False)
        if not clave:
            return []
        d = self._json("https://pixabay.com/api/videos/", params={"key": clave, "q": q, "per_page": max(3, n)})
        out = []
        for v in (d.get("hits") or [])[:n]:
            arch = (v.get("videos") or {}).get("medium") or (v.get("videos") or {}).get("small") or {}
            if not arch.get("url") or float(v.get("duration") or 0) < DURACION_MIN_S:
                continue
            out.append(Video("pixabay", v.get("tags") or "video", arch["url"], v.get("pageURL", ""),
                             "Licencia de Pixabay", v.get("user") or "Pixabay", None, float(v["duration"])))
        return out

    # ---- las dos etapas -------------------------------------------------------------------

    def candidatos(self, mostrar: str, anio: int, presente: bool, avisar=log.info,
                   tema: str = "", cuantos: int = 4) -> list[Video]:
        """Etapa 1 (archivo); solo si no trae nada, la 2 (stock y NASA). En cada etapa, las
        búsquedas de `consultas` en orden, hasta juntar `cuantos`. La regla de época: en una frase
        del pasado, nada con fecha de más de MARGEN_EPOCA años después del hecho."""
        from .efemerides import MARGEN_EPOCA

        def epoca_ok(v: Video) -> bool:
            return presente or v.anio is None or v.anio <= anio + MARGEN_EPOCA

        def etapas(q: str) -> list[list[tuple]]:
            return [[("commons", lambda: self.commons(q)),
                     ("archive", lambda: self.archive(q, None if presente else anio))],
                    [("pexels", lambda: self.pexels(q)), ("pixabay", lambda: self.pixabay(q))]
                    + ([("nasa", lambda: self.nasa(q))] if es_de_espacio(mostrar + " " + tema) else [])]

        qs = consultas(mostrar, tema)
        for n_etapa in range(2):
            out, urls, afuera = [], set(), 0
            for q in qs:
                for nombre, buscar in etapas(q)[n_etapa]:
                    try:
                        halladas = buscar()
                    except (requests.RequestException, ValueError) as e:
                        avisar(f"    video: {nombre} «{q}» falló ({str(e)[:80]})")
                        continue
                    for v in halladas:
                        if v.url in urls:
                            continue
                        urls.add(v.url)
                        if marca_prohibida(v.titulo, v.autor, v.url, v.pagina):
                            avisar(f"    video: «{v.titulo[:50]}» es de una marca prohibida, afuera")
                            continue
                        if epoca_ok(v):
                            out.append(v)
                        else:
                            afuera += 1
                if len(out) >= cuantos:
                    break
            if afuera:
                avisar(f"    video: {afuera} de otra época afuera")
            if out:
                return out[:cuantos]
        return []


# ---- ffmpeg sobre la URL: sin bajar el video entero ------------------------------------------

def _ffmpeg_url(url: str) -> list[str]:
    ua = user_agent()
    return ["-user_agent", ua, "-rw_timeout", "30000000"] if url.startswith("http") else []


def _pausa(url: str) -> None:
    if "wikimedia.org" in url:
        time.sleep(PAUSA_WIKIMEDIA_S)


def duracion_url(url: str) -> float:
    r = _ejecutar([find_bin("ffprobe"), "-v", "error", *_ffmpeg_url(url), "-show_entries",
                   "format=duration", "-of", "default=nw=1:nk=1", url], TOPE_PROBE_S, text=True)
    try:
        return float(r.stdout.strip()) if r else 0.0
    except ValueError:
        return 0.0


def sacar_frames(v: Video, carpeta: Path, nombre: str) -> Video:
    """Los cuadros que ve Gemini (y la miniatura de la hoja): a 20, 50 y 80 % del largo usable."""
    carpeta.mkdir(parents=True, exist_ok=True)
    usable = min(v.duracion, LARGO_USABLE_S)
    v.momentos, v.frames = [], []
    for k, frac in enumerate(FRAMES):
        t = round(usable * frac, 1)
        salida = carpeta / f"{nombre}_{k}.jpg"
        if not salida.exists():
            _pausa(v.url)
            r = _ejecutar([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                           "-ss", str(t), *_ffmpeg_url(v.url), "-i", v.url, "-frames:v", "1",
                           "-vf", "scale=512:-2", str(salida)], TOPE_FRAME_S)
            if r is None:     # servidor lento: este video se saltea entero (no se insiste cuadro por cuadro)
                log.warning("video %s: no bajó ni un cuadro a tiempo, se saltea", v.pagina)
                v.momentos, v.frames = [], []
                return v
            if r.returncode != 0 or not salida.exists():
                continue
        v.momentos.append(t)
        v.frames.append(str(salida))
    return v


def bajar_tramo(v: Video, dur: float, salida: Path) -> Path:
    """El pedazo que se ve: `dur` segundos alrededor del cuadro elegido (sin pasarse del video).
    Sin audio. Si el video es más corto que la frase, se baja entero y el render lo repite."""
    inicio = max(0.0, min(v.momento - dur / 2, max(v.duracion - dur, 0.0)))
    largo = min(dur + 0.5, v.duracion - inicio) if v.duracion else dur + 0.5
    salida.parent.mkdir(parents=True, exist_ok=True)
    _pausa(v.url)
    # Al archivo local, con tope y un reintento; si no baja, RuntimeError y esa frase vuelve a su foto.
    r = _ejecutar([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                   "-ss", f"{inicio:.2f}", *_ffmpeg_url(v.url), "-i", v.url, "-t", f"{largo:.2f}",
                   "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                   "-pix_fmt", "yuv420p", str(salida)], TOPE_TRAMO_S)
    if r is None:
        salida.unlink(missing_ok=True)
        raise RuntimeError(f"el tramo de {v.pagina} no bajó en {TOPE_TRAMO_S} s (dos intentos)")
    if r.returncode != 0 or not salida.exists():
        raise RuntimeError(f"no pude bajar el tramo de {v.pagina}: {r.stderr[-200:]!r}")
    v.ruta = str(salida)
    return salida


def encuadre_video(frame: Path, alto_min: float = 0.72, W: int = 1080, H: int = 1920) -> tuple[float, bool]:
    """(centro x del recorte 0-1, ¿mostrar el cuadro entero?) a partir del cuadro elegido: el
    recorte se centra en las caras y, si no entran con margen, el video va entero (caras enteras)."""
    import cv2

    from .parallax import caras, zona_caras

    img = cv2.imread(str(frame))
    if img is None:
        return 0.5, False
    h, w = img.shape[:2]
    zona = zona_caras(caras(img), w, h)
    if not zona:
        return 0.5, False
    visible = W / (alto_min * H * w / h)          # qué fracción del ancho se ve al recortar
    if (zona[2] - zona[0]) / w > visible:
        return 0.5, True
    return ((zona[0] + zona[2]) / 2) / w, False


def filtro_video(W: int, H: int, blur: float, fps: int = 30, cx: float = 0.5, entero: bool = False) -> str:
    """fit_blur para un video: el cuadro al centro sobre el mismo video agrandado y borroso. Ocupa
    al menos el 72 % del alto recortando los costados hacia `cx` (las caras); con `entero`, el cuadro
    completo (cuando recortar cortaría una cara)."""
    frente = (f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[frente];" if entero else
              f"[b]scale=-2:{int(H * 0.72) // 2 * 2},"
              f"crop='min(iw,{W})':ih:'max(0,min(iw-ow,iw*{cx:.3f}-ow/2))':0,setsar=1[frente];")
    return (f"[0:v]fps={fps},split[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma={blur},setsar=1[fondo];"
            + frente +
            f"[fondo][frente]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")


def creditos(videos: list[Video]) -> str:
    if not videos:
        return ""
    return "Videos:\n" + "\n".join(f"{i}. {v.credito()}" for i, v in enumerate(videos, 1))


def resumen(v: Video) -> str:
    return json.dumps({"fuente": v.fuente, "anio": v.anio, "dur": round(v.duracion)}, ensure_ascii=False)
