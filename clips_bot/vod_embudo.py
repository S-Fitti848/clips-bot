"""El original de un Short que "pegó", buscado en el VOD con un embudo (diseño aprobado 2026-10-29).

El Short de otro canal es solo una PISTA: se baja su audio y 3 cuadros a 360p para comparar, y se
borran. Lo que se procesa siempre se corta del VOD (vod.cortar), como antes.

Antes se bajaba el audio de CADA VOD entero de los días anteriores (10 a 40 min por VOD en la Pi la
primera vez) y se buscaba el Short en todo. Medido el 2026-10-29 sobre los 18 Shorts de Davo que se
buscaron: 3 encontrados, y 2 búsquedas cortadas por tiempo. Lo que dijeron los datos:
  - los 3 originales se publicaron 8, 10 y 17 min DESPUÉS del momento, con el stream todavía en
    vivo: los canales de clips cortan en vivo → la hora de publicación es la mejor pista;
  - los clips de la comunidad en Kick no traen la posición (`vod_starts_at` = 0; se calcula con la
    hora de creación) y los más cercanos a los originales estaban a 10,6 y 24 min.

Embudo:
  1. Stream: los VODs de `vod_dias_antes` (7) días antes de publicado, con puntaje por: en vivo a la
     hora de publicación (lo que más pesa), texto (título y descripción del Short contra título y
     categoría del stream) e imagen (UNA llamada a Gemini: 3 cuadros del Short contra la miniatura y
     2 cuadros de cada VOD: ropa, fondo, luz). Los 2 mejores.
  2. Momento: hasta 3 ventanas por VOD — la de la hora (de 45 min antes de publicado hasta la
     publicación, si el VOD estaba en vivo), clips de la comunidad con título parecido a lo que se
     dice en el Short (Whisper) ±10 min, y en Twitch el pico de chat ±10 min.
  3. Confirmar: el audio SOLO de esas ventanas, contra el del Short (el mismo umbral de siempre).
  4. Respaldo: si nada coincide y sobra tiempo del tope de la vuelta de las 02:00, el VOD mejor
     puntuado entero, como antes (vod.buscar_en_vods, con su huella guardada).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import audio_huella as ah
from . import vod as vd
from .media import find_bin

log = logging.getLogger(__name__)

VENTANA_HORA_S = 45 * 60    # el momento, hasta 45 min antes de publicado (medido: 8, 10 y 17 min)
MARGEN_S = 10 * 60          # clips y picos de chat: ±10 min
MAX_VENTANAS = 3
MAX_VODS = 2
CUADROS_SHORT = 3
CUADROS_VOD = 2
VODS_A_GEMINI = 6           # los mejores por hora y texto van a la comparación de imágenes
PASO_CHAT_S = 300           # Twitch: una página de chat cada 5 min…
MAX_PEDIDOS_CHAT = 60       # …con tope de pedidos

_PALABRA = re.compile(r"[a-z0-9ñ]{4,}")
_VACIAS = {"para", "como", "pero", "esta", "este", "esto", "todo", "todos", "porque", "cuando", "donde",
           "shorts", "short", "stream", "streamer", "kick", "twitch", "clip", "clips", "video", "viral",
           "parte", "sobre", "entre", "desde", "hasta", "tiene", "hace", "aguante", "vivo", "directo",
           "nada", "algo", "solo", "bien", "ahora", "despues", "antes", "mucho", "muy", "eso", "esa"}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def palabras(texto: str, sacar: set[str] = frozenset()) -> set[str]:
    """Las palabras con contenido (4+ letras, sin las vacías ni los nombres del streamer). Los
    hashtags no cuentan: los canales de clips los usan de relleno."""
    sin_hash = re.sub(r"#\S+", " ", texto or "")
    return {p for p in _PALABRA.findall(_norm(sin_hash)) if p not in _VACIAS and p not in sacar}


def parecido(a: set[str], b: set[str]) -> float:
    """Qué parte de las palabras del más corto está en el otro (0 a 1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ---- 0. la pista: el Short (audio + 3 cuadros a 360p; se borra después) --------------------------

@dataclass
class Pista:
    id: str
    titulo: str
    descripcion: str
    publicado: datetime | None
    duracion: float
    audio: Path
    cuadros: list[Path] = field(default_factory=list)
    transcripcion: str = ""

    def texto(self) -> str:
        return f"{self.titulo} {self.descripcion} {self.transcripcion[:400]}"


def bajar_pista(short_id: str, carpeta: Path) -> Pista:
    """UNA bajada del Short en 360p (con audio): de ahí salen el audio, los cuadros y los datos."""
    from yt_dlp import YoutubeDL

    carpeta.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/shorts/{short_id}"
    with YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True,
                    "format": "18/best[height<=480][acodec!=none][vcodec!=none]/bestaudio/best",
                    "outtmpl": str(carpeta / f"short_{short_id}.%(ext)s")}) as y:
        info = y.extract_info(url, download=True)
        ruta = Path(y.prepare_filename(info))
    publicado = None
    if info.get("timestamp"):
        publicado = datetime.fromtimestamp(int(info["timestamp"]), tz=timezone.utc)
    elif info.get("upload_date"):
        publicado = datetime.strptime(info["upload_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
    duracion = float(info.get("duration") or 30.0)
    cuadros = []
    if info.get("vcodec") not in (None, "none"):
        for k in range(CUADROS_SHORT):
            destino = carpeta / f"short_{k}.jpg"
            t = duracion * (k + 1) / (CUADROS_SHORT + 1)
            r = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss",
                                f"{t:.2f}", "-i", str(ruta), "-frames:v", "1", "-vf", "scale=384:-2",
                                str(destino)], capture_output=True, timeout=60)
            if r.returncode == 0 and destino.exists():
                cuadros.append(destino)
    return Pista(short_id, str(info.get("title") or ""), str(info.get("description") or "")[:500],
                 publicado, duracion, ruta, cuadros)


def transcribir_pista(p: Pista, cfg_subtitulos) -> str:
    """Lo que se dice en el Short (Whisper): para comparar con los títulos de los clips."""
    from . import subtitles as sub

    modelo = sub.cargar_modelo(cfg_subtitulos)
    try:
        return " ".join(w.texto for w in sub.transcribir(modelo, p.audio, cfg_subtitulos, p.duracion))
    finally:
        del modelo


# ---- 1. el stream ----------------------------------------------------------------------------------

def en_vivo(v: vd.Vod, cuando: datetime | None, margen_s: float = 300) -> bool:
    """¿El stream estaba al aire cuando se publicó el Short? Un VOD de Kick todavía en vivo tiene
    duración 0."""
    if cuando is None:
        return False
    fin = v.inicio + timedelta(seconds=v.duracion_s) if v.duracion_s else datetime.now(timezone.utc)
    return v.inicio <= cuando <= fin + timedelta(seconds=margen_s)


@dataclass
class Puntaje:
    vod: vd.Vod
    vivo: bool = False
    texto: float = 0.0
    imagen: float | None = None     # 0 a 10, de Gemini; None si no se pudo

    @property
    def total(self) -> float:
        return 3.0 * self.vivo + 2.0 * self.texto + 0.3 * (self.imagen or 0.0)

    def detalle(self) -> str:
        img = f"{self.imagen:.0f}/10" if self.imagen is not None else "—"
        return (f"VOD {self.vod.id} «{self.vod.titulo[:40]}»: {'en vivo, ' if self.vivo else ''}"
                f"texto {self.texto:.2f}, imagen {img} → {self.total:.1f}")


def cuadro_vod(v: vd.Vod, segundo: float, destino: Path) -> Path | None:
    """Un cuadro del VOD en la variante chica (seek en el HLS: unos segundos)."""
    url = v.url if v.plataforma == "kick" else vd._ytdlp_url(v.pagina, "worst[height>=144]/worst")
    try:
        r = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                            "-rw_timeout", "20000000", "-ss", f"{segundo:.0f}", "-i", url,
                            "-frames:v", "1", "-vf", "scale=384:-2", str(destino)],
                           capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        return None
    return destino if r.returncode == 0 and destino.exists() else None


def bajar_miniatura(v: vd.Vod, destino: Path) -> Path | None:
    import requests
    from PIL import Image

    if not v.miniatura:
        return None
    try:
        r = requests.get(v.miniatura, timeout=15)
        r.raise_for_status()
        import io

        Image.open(io.BytesIO(r.content)).convert("RGB").save(destino, quality=85)
        return destino
    except Exception as e:     # una miniatura que no baja no frena nada
        log.info("miniatura de %s: %s", v.id, e)
        return None


SISTEMA_IMAGEN = """Comparás un Short (los primeros cuadros) con varios streams (VODs) del mismo
streamer, para saber de cuál stream salió. Mirá la ROPA de la persona, el FONDO (cuarto, decorado,
luces, objetos) y la LUZ. No importa el texto sobreimpreso ni el recorte vertical del Short. Para cada
VOD, de 0 a 10: 10 = mismo día (misma ropa y mismo lugar), 5 = mismo lugar con otra ropa, 0 = nada
que ver. Si no podés ver a la persona, juzgá por el fondo."""

SCHEMA_IMAGEN = {"type": "OBJECT", "properties": {"vods": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"vod": {"type": "INTEGER"}, "parecido": {"type": "INTEGER"}},
    "required": ["vod", "parecido"]}}}, "required": ["vods"]}


def puntaje_imagen(gemini, pista: Pista, puntajes: list[Puntaje], carpeta: Path) -> None:
    """UNA llamada a Gemini: los cuadros del Short y, por VOD, la miniatura y 2 cuadros."""
    if gemini is None or not pista.cuadros:
        return
    imagenes = [p.read_bytes() for p in pista.cuadros]
    partes = [f"Cuadros 1 a {len(imagenes)}: el Short."]
    for n, pt in enumerate(puntajes, 1):
        v, desde = pt.vod, len(imagenes) + 1
        fotos = [bajar_miniatura(v, carpeta / f"vod{n}_mini.jpg")]
        dur = v.duracion_s or 3600
        fotos += [cuadro_vod(v, dur * (k + 1) / (CUADROS_VOD + 1), carpeta / f"vod{n}_{k}.jpg")
                  for k in range(CUADROS_VOD)]
        fotos = [f for f in fotos if f]
        if not fotos:
            continue
        imagenes += [f.read_bytes() for f in fotos]
        partes.append(f"VOD {n}: cuadros {desde} a {len(imagenes)}.")
    try:
        d = json.loads(gemini.json(SISTEMA_IMAGEN, "\n".join(partes), SCHEMA_IMAGEN, temperatura=0.0,
                                   imagenes=imagenes))
    except Exception as e:     # Gemini caído: el embudo sigue con la hora y el texto
        log.info("embudo: imagen salteada (%s)", str(e)[:120])
        return
    for item in d.get("vods") or []:
        n = int(item.get("vod") or 0)
        if 1 <= n <= len(puntajes):
            puntajes[n - 1].imagen = max(0.0, min(10.0, float(item.get("parecido") or 0)))


def elegir_vods(pista: Pista, vods: list[vd.Vod], gemini, carpeta: Path, nombres: set[str],
                avisar=log.info) -> list[Puntaje]:
    texto = palabras(f"{pista.titulo} {pista.descripcion}", nombres)
    puntajes = [Puntaje(v, en_vivo(v, pista.publicado),
                        parecido(texto, palabras(f"{v.titulo} {v.categoria}", nombres))) for v in vods]
    puntajes.sort(key=lambda p: -p.total)
    a_gemini = puntajes[:VODS_A_GEMINI]
    puntaje_imagen(gemini, pista, a_gemini, carpeta)
    puntajes.sort(key=lambda p: -p.total)
    for p in puntajes[:VODS_A_GEMINI]:
        avisar(f"    {p.detalle()}")
    return puntajes[:MAX_VODS]


# ---- 2. el momento ---------------------------------------------------------------------------------

@dataclass
class Ventana:
    inicio: float      # segundos dentro del VOD
    fin: float
    motivo: str


def posicion_clip(c, v: vd.Vod) -> float | None:
    """Dónde está el clip en el VOD: `vod_offset` (Twitch) o, en Kick (que lo da en 0), la hora de
    creación menos el inicio del VOD menos lo que dura el clip (los clips se hacen en vivo)."""
    if getattr(c, "vod_offset", None):
        return float(c.vod_offset)
    creado = getattr(c, "created_at", None)
    if creado is None:
        return None
    return (creado - v.inicio).total_seconds() - float(getattr(c, "duration", 0) or 0)


def picos_chat(chat, v: vd.Vod) -> list[float]:
    """Twitch: los segundos del VOD con más mensajes por segundo (una página de chat cada 5 min)."""
    if chat is None or v.plataforma != "twitch" or not v.duracion_s:
        return []
    paso = max(PASO_CHAT_S, v.duracion_s / MAX_PEDIDOS_CHAT)
    tasas = []
    t = 0.0
    while t < v.duracion_s:
        try:
            edges = chat._pagina(v.id, t).get("edges") or []
        except Exception:
            break
        tiempos = [(e.get("node") or {}).get("contentOffsetSeconds", 0) for e in edges]
        if len(tiempos) >= 2 and tiempos[-1] > tiempos[0]:
            tasas.append(((len(tiempos) - 1) / (tiempos[-1] - tiempos[0]), t))
        t += paso
    return [s for _, s in sorted(tasas, reverse=True)[:2]]


def ventanas(v: vd.Vod, pista: Pista, clips: list, nombres: set[str], chat=None) -> list[Ventana]:
    out: list[Ventana] = []
    dur = v.duracion_s or (datetime.now(timezone.utc) - v.inicio).total_seconds()
    if pista.publicado and en_vivo(v, pista.publicado):
        pub = (pista.publicado - v.inicio).total_seconds()
        out.append(Ventana(pub - VENTANA_HORA_S, pub + 60, "hora de publicación"))
    dicho = palabras(pista.texto(), nombres)
    candidatos = []
    for c in clips:
        if str(getattr(c, "video_id", "") or "") != v.id:
            continue
        pos = posicion_clip(c, v)
        sim = parecido(dicho, palabras(getattr(c, "title", ""), nombres))
        if pos is not None and sim > 0:
            candidatos.append((sim, getattr(c, "view_count", 0), pos, getattr(c, "title", "")))
    for sim, _, pos, titulo in sorted(candidatos, reverse=True)[:2]:
        out.append(Ventana(pos - MARGEN_S, pos + MARGEN_S, f"clip «{titulo[:30]}» ({sim:.2f})"))
    for s in picos_chat(chat, v)[:1]:
        out.append(Ventana(s - MARGEN_S, s + MARGEN_S, "pico de chat"))
    # Dentro del VOD, y las que se pisan, juntas.
    out = [Ventana(max(0.0, w.inicio), min(dur, w.fin), w.motivo) for w in out if w.fin > 0 and w.inicio < dur]
    juntas: list[Ventana] = []
    for w in sorted(out, key=lambda w: w.inicio):
        if juntas and w.inicio <= juntas[-1].fin:
            juntas[-1] = Ventana(juntas[-1].inicio, max(juntas[-1].fin, w.fin),
                                 f"{juntas[-1].motivo} + {w.motivo}")
        else:
            juntas.append(w)
    # La de la hora primero (es la que más acierta), después las demás.
    juntas.sort(key=lambda w: "hora" not in w.motivo)
    return juntas[:MAX_VENTANAS]


# ---- 3. confirmar con el audio, solo en las ventanas ---------------------------------------------

def huella_tramo(v: vd.Vod, inicio: float, duracion: float) -> np.ndarray:
    """La huella del audio de un tramo del VOD (seek en el HLS: no se baja el resto)."""
    r = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-rw_timeout", "30000000",
                        "-ss", f"{inicio:.0f}", "-t", f"{duracion:.0f}", "-i", vd.url_audio(v), "-vn",
                        "-ac", "1", "-ar", str(ah.SR), "-f", "s16le", "-"],
                       capture_output=True, timeout=max(120, duracion))
    audio = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
    if len(audio) < ah.VENTANA * 4:
        return np.zeros((0, ah.BANDAS), dtype=np.float32)
    return ah.huella(audio)


@dataclass
class Hallazgo:
    vod: vd.Vod
    segundo: float
    valor: float
    como: str


def confirmar(corto: np.ndarray, v: vd.Vod, vs: list[Ventana], umbral: float,
              avisar=log.info) -> Hallazgo | None:
    mejor = None
    for w in vs:
        t0 = time.monotonic()
        try:
            h = huella_tramo(v, w.inicio, w.fin - w.inicio)
        except (subprocess.SubprocessError, OSError) as e:
            avisar(f"      ventana {w.inicio / 60:.0f}-{w.fin / 60:.0f} min: no bajó ({str(e)[:80]})")
            continue
        if not len(h):
            continue
        valor, seg = ah.coincidencia_rapida(corto, h)
        avisar(f"      ventana {w.inicio / 60:.0f}-{w.fin / 60:.0f} min ({w.motivo}): {valor:.2f} "
               f"({time.monotonic() - t0:.0f} s)")
        if valor >= umbral and (mejor is None or valor > mejor.valor):
            mejor = Hallazgo(v, w.inicio + seg, valor, w.motivo)
    return mejor


# ---- todo junto ----------------------------------------------------------------------------------------

def buscar(pista: Pista, vods: list[vd.Vod], clips: list, umbral: float, carpeta: Path, nombres: set[str],
           gemini=None, chat=None, cache: Path | None = None, avisar=log.info,
           hasta: float | None = None, reloj=time.monotonic, respaldo: bool = True) -> Hallazgo | None:
    """El embudo entero. `nombres`: los del streamer (no cuentan como palabras en común)."""
    corto = ah.huella(ah.leer_audio(pista.audio))
    elegidos = elegir_vods(pista, vods, gemini, carpeta, nombres, avisar)
    for p in elegidos:
        vs = ventanas(p.vod, pista, clips, nombres, chat)
        avisar(f"    VOD {p.vod.id}: {len(vs)} ventanas")
        h = confirmar(corto, p.vod, vs, umbral, avisar)
        if h:
            return h
        if hasta is not None and reloj() >= hasta:
            return None
    if respaldo and elegidos and (hasta is None or reloj() < hasta) and cache is not None:
        avisar(f"    respaldo: el VOD {elegidos[0].vod.id} entero")
        try:
            r = vd.buscar_en_vods(pista.audio, [elegidos[0].vod], cache, umbral, avisar, hasta, reloj)
        except TimeoutError:
            return None
        if r:
            return Hallazgo(r[0], r[1], r[2], "VOD entero (respaldo)")
    return None


# ---- antes de buscar: lo que no puede estar en el VOD del streamer --------------------------------------

_COMPILADO = re.compile(r"^\W*top\b|mejores momentos|compilad|recopilaci", re.I)


def motivo_saltear(titulo: str, propios: set[str], otros: list[str]) -> str:
    """Por qué NO buscar este Short en el VOD (vacío = buscarlo): un compilado (TOP…, mejores
    momentos) o un Short que nombra a otro streamer/personaje además del nuestro (Gastón Edul, el
    Kun): esos originales no están en el VOD de este streamer. Los hashtags no cuentan."""
    t = re.sub(r"#\S+", " ", titulo or "")
    if _COMPILADO.search(t):
        return "compilado"
    plano = f" {_norm(t)} "
    for o in otros:
        n = _norm(o).strip()
        if n and n not in propios and re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", plano):
            return f"nombra a {o}"
    return ""
