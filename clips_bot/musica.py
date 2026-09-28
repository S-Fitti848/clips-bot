"""Biblioteca de música de fondo para Pequeña Historia (§3c).

    musica/youtube/     lo que pone Santi (Biblioteca de audio de YouTube): tiene PRIORIDAD
    musica/kevin/       Kevin MacLeod (incompetech.com), CC BY 4.0: se baja solo
    musica/openverse/   Openverse, solo CC0 y CC BY (nada NC ni ND): se baja solo
    musica/biblioteca.json  lo bajado: título, autor, licencia, link y etiquetas de cada tema

La carpeta entera está fuera de git (pesa). Lo que se bajó solo se rearma en cualquier máquina con
`python -m clips_bot musica --llenar`.

Por video: se elige un tema según el TONO del guion (lo dice Gemini en la misma llamada del
guion), sin repetir ninguno de los últimos 5 videos y sin los temas vetados por /reclamo. Se usa
al 12 % y bajando cuando habla la voz (ducking).

OJO: §1 decía "sin música agregada" por Content ID. Esto es una excepción pedida por Santi para
Pequeña Historia (2026-09-27). YouTube Audio Library es lo único garantizado sin reclamos en
YouTube; Kevin MacLeod casi nunca tiene, y los de Openverse (sobre todo de Jamendo) pueden tener.
Si llega un reclamo, /reclamo veta el tema.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests

from .config import user_agent
from .media import find_bin, run

log = logging.getLogger(__name__)

KEVIN_CATALOGO = "https://incompetech.com/music/royalty-free/pieces.json"
KEVIN_MP3 = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/{archivo}"
OPENVERSE = "https://api.openverse.org/v1/audio/"
EXT = (".mp3", ".ogg", ".m4a", ".wav", ".flac", ".opus")
DUR_MIN_S, DUR_MAX_S = 60, 240        # 1 a 4 minutos
MAX_MB = 15
SIN_REPETIR = 5                       # videos seguidos sin repetir tema
CLAVE_RECIENTES = "musica_recientes"  # bot_estado: json con los últimos temas usados
CLAVE_VETADOS = "musica_vetados"      # bot_estado: json con los temas vetados por /reclamo

# El tono del guion (lo elige Gemini) → palabras que lo describen en las etiquetas de cada fuente
# ("feel" de Kevin, tags de Openverse/Jamendo).
TONOS = {
    "alegre": ["happy", "bright", "upbeat", "cheerful", "fun", "uplifting", "positive", "energetic",
               "light", "sunny", "optimistic"],
    "epico": ["epic", "dramatic", "action", "heroic", "intense", "driving", "powerful", "grand",
              "cinematic", "triumphant"],
    "misterioso": ["mysterious", "mystery", "dark", "suspense", "suspenseful", "tension", "eerie",
                   "ominous", "strange", "unnerving"],
    "curioso": ["quirky", "playful", "whimsical", "curious", "humorous", "funny", "bouncy",
                "silly", "light"],
    "emotivo": ["calm", "somber", "relaxed", "peaceful", "sentimental", "gentle", "melancholic",
                "sad", "emotional", "tender", "reflective"],
}
_VOCES = re.compile(r"\b(voice|vocal\w*|choir|singer|singing|sung|lyrics?|rap|spoken|voz|voces|"
                    r"coro|feat\.?|featuring)\b", re.I)


@dataclass
class Tema:
    ruta: str                     # relativa a la carpeta de música, ej. "kevin/Carefree.mp3"
    titulo: str
    autor: str
    licencia: str                 # "CC BY 4.0", "CC0 1.0", "YouTube Audio Library"
    link: str
    fuente: str                   # youtube | kevin | openverse
    duracion_s: float = 0.0
    etiquetas: list[str] = field(default_factory=list)

    def credito(self) -> str:
        if self.fuente == "kevin":   # el formato que pide incompetech para CC BY
            return (f'"{self.titulo}" Kevin MacLeod (incompetech.com) — Licensed under Creative '
                    f"Commons: By Attribution 4.0 — {self.link}")
        partes = [f'"{self.titulo}"', self.autor, self.licencia, self.link]
        return " — ".join(p for p in partes if p)


# ---- la biblioteca ------------------------------------------------------------------------

def _indice(carpeta: Path) -> dict:
    try:
        return json.loads((carpeta / "biblioteca.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_indice(carpeta: Path, indice: dict) -> None:
    (carpeta / "biblioteca.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1),
                                             encoding="utf-8")


def de_youtube(archivo: Path, tonos: dict | None = None) -> Tema | None:
    """Los de la Biblioteca de YouTube vienen como "Título - Artista.mp3". None si parece tener
    voces: "Shining (feat. …)" está en la carpeta, y una canción cantada tapa la narración.

    El mp3 no trae el ánimo (el único tag es "encoder: Google", visto el 2026-09-28): para el tono
    cuentan las palabras del título ("Happy Tails" → alegre) y, si existe, lo que diga
    musica/youtube/tonos.json ({"archivo.mp3": "alegre,curioso"}), que se edita a mano."""
    nombre = archivo.stem
    if _VOCES.search(nombre):
        return None
    titulo, _, autor = nombre.partition(" - ")
    etiquetas = re.findall(r"[a-z]+", titulo.lower())
    for tono in str((tonos or {}).get(archivo.name) or "").split(","):
        etiquetas += TONOS.get(tono.strip().lower(), [])[:3]
    return Tema(ruta=f"youtube/{archivo.name}", titulo=titulo.strip(), autor=autor.strip(),
                licencia="YouTube Audio Library", link="", fuente="youtube", etiquetas=etiquetas)


def cargar(carpeta: Path) -> list[Tema]:
    """Todos los temas usables: los de youtube/ (siempre releídos) y los del índice que existen."""
    temas = []
    yt = carpeta / "youtube"
    if yt.exists():
        try:
            tonos = json.loads((yt / "tonos.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tonos = {}
        temas += [t for t in (de_youtube(p, tonos) for p in sorted(yt.iterdir())
                              if p.suffix.lower() in EXT) if t]
    for ruta, d in _indice(carpeta).items():
        if (carpeta / ruta).exists():
            temas.append(Tema(**{**d, "ruta": ruta}))
    return temas


def puntaje(t: Tema, tono: str) -> int:
    palabras = TONOS.get(tono, [])
    texto = " ".join(t.etiquetas).lower()
    return sum(1 for p in palabras if re.search(rf"\b{p}\b", texto))


def elegir(temas: list[Tema], tono: str = "", recientes: list[str] | None = None,
           vetados: set[str] | None = None, azar=None) -> Tema | None:
    """El tema para un video.

    1. Afuera los vetados (/reclamo) y los de los últimos SIN_REPETIR videos. Si con eso no queda
       nada (hay pocos temas), se relaja la regla de no repetir, nunca la del veto.
    2. Los de youtube/ primero: si queda alguno, se elige entre ellos.
    3. Entre los que quedan, los que mejor coinciden con el tono; al azar entre los empatados.
    """
    azar = azar or random
    recientes = (recientes or [])[-SIN_REPETIR:]
    vetados = vetados or set()
    validos = [t for t in temas if t.ruta not in vetados]
    libres = [t for t in validos if t.ruta not in recientes] or \
        sorted(validos, key=lambda t: recientes.index(t.ruta) if t.ruta in recientes else -1)[:1]
    if not libres:
        return None
    pool = [t for t in libres if t.fuente == "youtube"] or libres
    if tono:
        mejor = max(puntaje(t, tono) for t in pool)
        pool = [t for t in pool if puntaje(t, tono) == mejor]
    return azar.choice(pool)


def recientes(conn) -> list[str]:
    from . import db

    try:
        return json.loads(db.get_valor(conn, CLAVE_RECIENTES) or "[]")
    except ValueError:
        return []


def anotar_uso(conn, ruta: str) -> None:
    from . import db

    db.set_valor(conn, CLAVE_RECIENTES, json.dumps((recientes(conn) + [ruta])[-20:], ensure_ascii=False))


def vetados(conn) -> set[str]:
    from . import db

    try:
        return set(json.loads(db.get_valor(conn, CLAVE_VETADOS) or "[]"))
    except ValueError:
        return set()


def vetar(conn, ruta: str) -> bool:
    """/reclamo sobre un video con música: ese tema no se vuelve a usar. False si ya estaba."""
    from . import db

    v = vetados(conn)
    if ruta in v:
        return False
    db.set_valor(conn, CLAVE_VETADOS, json.dumps(sorted(v | {ruta}), ensure_ascii=False))
    return True


# ---- la mezcla -----------------------------------------------------------------------------

def filtro(volumen: float, duracion: float, fundido_s: float = 1.5) -> str:
    """Voz ([0:a]) + música ([1:a], en loop) al `volumen`, con ducking: la música baja cuando
    suena la voz (sidechaincompress con la voz como disparador) y se va apagando al final.

    En mono: la voz es mono, y pasarla a estéreo le bajaba 3 dB (medido en la Pi: -17,7 dB sola,
    -20,6 dB en la mezcla estéreo)."""
    return (f"[1:a]aresample=48000,aformat=channel_layouts=mono,volume={volumen},"
            f"afade=t=out:st={max(duracion - fundido_s, 0):.2f}:d={fundido_s}[mus];"
            f"[0:a]aresample=48000,aformat=channel_layouts=mono,asplit=2[voz][disparo];"
            f"[mus][disparo]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[bajo];"
            f"[voz][bajo]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")


def mezclar(voz: Path, pista: Path, salida: Path, volumen: float = 0.12) -> Path:
    """La voz con la música de fondo, en un solo audio que dura lo que la voz."""
    from .narrar import duracion_wav

    dur = duracion_wav(voz)
    salida.parent.mkdir(parents=True, exist_ok=True)
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(voz.resolve()),
         "-stream_loop", "-1", "-i", str(pista.resolve()), "-filter_complex", filtro(volumen, dur),
         "-map", "[a]", "-t", f"{dur:.2f}", "-c:a", "pcm_s16le", str(salida.resolve())])
    return salida


# ---- llenar la biblioteca sola ------------------------------------------------------------------

def _duracion(texto: str) -> float:
    """"00:02:31" → 151."""
    try:
        h, m, s = (int(x) for x in texto.split(":"))
        return h * 3600 + m * 60 + s
    except ValueError:
        return 0.0


def candidatos_kevin(catalogo: list[dict]) -> list[Tema]:
    """Del catálogo de incompetech: 1 a 4 min, sin voces ni coro entre los instrumentos."""
    out = []
    for d in catalogo:
        dur = _duracion(str(d.get("length") or ""))
        texto = f"{d.get('instruments', '')} {d.get('description', '')} {d.get('title', '')}"
        if not (DUR_MIN_S <= dur <= DUR_MAX_S) or _VOCES.search(texto) or not d.get("filename"):
            continue
        etiquetas = [x.strip().lower() for x in str(d.get("feel") or "").split(",") if x.strip()]
        etiquetas += re.findall(r"[a-z]+", str(d.get("description") or "").lower())
        out.append(Tema(ruta=f"kevin/{d['filename']}", titulo=str(d["title"]), autor="Kevin MacLeod",
                        licencia="CC BY 4.0", link="https://incompetech.com", fuente="kevin",
                        duracion_s=dur, etiquetas=etiquetas))
    return out


def candidatos_openverse(resultados: list[dict]) -> list[Tema]:
    """De Openverse: solo CC0 y CC BY, 1 a 4 min, marcados como instrumentales y sin voces."""
    out = []
    for d in resultados:
        lic = str(d.get("license") or "").lower()
        dur = (d.get("duration") or 0) / 1000
        tags = [str(t.get("name") or "").lower() for t in d.get("tags") or [] if isinstance(t, dict)]
        texto = " ".join(tags + [str(d.get("title") or "")]).lower()
        if lic not in ("cc0", "by") or not (DUR_MIN_S <= dur <= DUR_MAX_S):
            continue
        if "instrumental" not in texto or _VOCES.search(" ".join(t for t in tags if t != "instrumental")):
            continue
        if int(d.get("filesize") or 0) > MAX_MB * 1024 * 1024:
            continue
        ident = str(d.get("id") or "")[:12] or re.sub(r"\W+", "_", str(d.get("title")))[:40]
        licencia = "CC0 1.0" if lic == "cc0" else f"CC BY {d.get('license_version') or ''}".strip()
        tema = Tema(ruta=f"openverse/{ident}.mp3", titulo=str(d.get("title") or ""),
                    autor=str(d.get("creator") or ""), licencia=licencia,
                    link=str(d.get("foreign_landing_url") or ""), fuente="openverse",
                    duracion_s=dur, etiquetas=tags + [g.lower() for g in d.get("genres") or []])
        tema.__dict__["_url"] = str(d.get("url") or "")   # de dónde bajarlo; no va al índice
        out.append(tema)
    return out


def _repartir(temas: list[Tema], cuantos: int, azar) -> list[Tema]:
    """`cuantos` temas repartidos entre los tonos: así la biblioteca no queda toda alegre."""
    elegidos: list[Tema] = []
    por_tono = {tono: sorted([t for t in temas if puntaje(t, tono) > 0],
                             key=lambda t: -puntaje(t, tono)) for tono in TONOS}
    for lista in por_tono.values():
        azar.shuffle(lista)
    while len(elegidos) < cuantos and any(por_tono.values()):
        for lista in por_tono.values():
            while lista and lista[0] in elegidos:
                lista.pop(0)
            if lista and len(elegidos) < cuantos:
                elegidos.append(lista.pop(0))
    return elegidos


def llenar(carpeta: Path, por_fuente: int = 10, session: requests.Session | None = None,
           azar=None, avisar=log.info, pausa_s: float = 1.0) -> int:
    """Completa hasta `por_fuente` temas de Kevin y de Openverse. Devuelve cuántos bajó.
    Si una fuente falla, se anota y sigue con la otra (la biblioteca es un extra, no bloquea)."""
    azar = azar or random.Random()
    session = session or requests.Session()
    indice = _indice(carpeta)
    tenia = {r for r in indice if (carpeta / r).exists()}
    bajados = 0

    def cuantos(fuente: str) -> int:
        return por_fuente - sum(1 for r in tenia if indice[r]["fuente"] == fuente)

    faltan = {"kevin": cuantos("kevin"), "openverse": cuantos("openverse")}
    candidatos: dict[str, list[Tema]] = {"kevin": [], "openverse": []}
    if faltan["kevin"] > 0:
        try:
            r = session.get(KEVIN_CATALOGO, headers={"User-Agent": user_agent()}, timeout=60)
            candidatos["kevin"] = candidatos_kevin(r.json())
        except (requests.RequestException, ValueError) as e:
            avisar(f"música: el catálogo de Kevin MacLeod no anduvo ({e})")
    if faltan["openverse"] > 0:
        # Sin cuenta, Openverse da hasta 20 por página (con 40 contesta 401): 2 páginas por tono.
        for tono, palabras in TONOS.items():
            for pagina in (1, 2):
                try:
                    r = session.get(OPENVERSE, headers={"User-Agent": user_agent()}, timeout=60, params={
                        "q": f"{palabras[0]} instrumental", "license": "cc0,by",
                        "category": "music", "page_size": 20, "page": pagina})
                    if r.status_code != 200:
                        avisar(f"música: Openverse {r.status_code} para {tono}")
                        break
                    candidatos["openverse"] += candidatos_openverse(r.json().get("results") or [])
                except (requests.RequestException, ValueError) as e:
                    avisar(f"música: Openverse no anduvo para {tono} ({e})")
                    break
                time.sleep(pausa_s)
    for fuente, lista in candidatos.items():
        nuevos = [t for t in lista if t.ruta not in indice]
        for t in _repartir(nuevos, max(faltan[fuente], 0), azar):
            url = KEVIN_MP3.format(archivo=quote(t.ruta.split("/", 1)[1])) if fuente == "kevin" \
                else t.__dict__.get("_url", "")
            destino = carpeta / t.ruta
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                r = session.get(url, headers={"User-Agent": user_agent()}, timeout=120)
                if r.status_code != 200 or len(r.content) > MAX_MB * 1024 * 1024 or len(r.content) < 50_000:
                    avisar(f"música: {t.titulo} no se pudo bajar ({r.status_code}, {len(r.content)} bytes)")
                    continue
                destino.write_bytes(r.content)
            except requests.RequestException as e:
                avisar(f"música: {t.titulo} no se pudo bajar ({e})")
                continue
            datos = {k: v for k, v in asdict(t).items() if k != "ruta"}
            indice[t.ruta] = datos
            _guardar_indice(carpeta, indice)
            bajados += 1
            avisar(f"música: + {t.ruta} ({t.licencia}, {', '.join(t.etiquetas[:4])})")
            time.sleep(pausa_s)
    return bajados
