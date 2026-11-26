"""Efemérides para el canal "Pequeña Historia": un Short por día con un hecho de la fecha.

1. Tema: Wikipedia "On this day" (es y en). Gemini elige los 3 más interesantes para un público
   joven, con fecha exacta y sin temas sensibles; antes, un filtro de palabras saca lo obvio.
2. Fotos: SOLO de los artículos del evento, con su licencia y autor de Commons. Reglas fijas
   (licencia libre, formato de foto, ≥ 800 px de ancho, nada de mapas, banderas, escudos, firmas,
   diagramas ni logos) y, en la misma llamada del guion, Gemini MIRA las fotos y descarta lo que
   las reglas no ven: gráficos, retratos de alguien que no protagoniza el hecho. Menos de 4 → el
   evento siguiente.
3. Guion: solo con el texto del artículo. Se valida que los nombres, números y meses que dice
   estén en el artículo, que arranque con "Un día como hoy, en <año>" y que cierre con pregunta.
4-6. La aprobación, el video y los créditos están en __main__ (Telegram) y en `armar_video`.

Todo lo que es red pasa por `Wiki`, que en los tests se reemplaza.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import logging
import re
import shutil
import subprocess
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import requests

from .config import DATA_DIR, user_agent
from .media import chequear_audio, find_bin, preparar_audio, run, X264
from . import ilustrar
from .narrar import NarrarError
from .reglas import REGLA_GANCHO_CONCRETO, REGLAS_CLARIDAD, gancho_generico
from .textos import nombres_propios
from .videos_libres import Video

log = logging.getLogger(__name__)

FEED = "https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/events/{mm:02d}/{dd:02d}"
API = "https://{lang}.wikipedia.org/w/api.php"

TONOS_GUION = ("alegre", "epico", "misterioso", "curioso", "emotivo")   # = musica.TONOS
MIN_ANCHO = 800          # la foto se escala a 1080 de ancho en fit_blur: menos que esto se nota
# Fotos de época (regla fija, 2026-09-29): una foto sacada más de MARGEN_EPOCA años después del
# hecho no se usa en una frase que habla del pasado (en la del 29/09, de 1940, salieron un avión de
# 2008 y otro de 2010). El año sale de DateTimeOriginal de Commons.
MARGEN_EPOCA = 10
_EPOCA = re.compile(r"\b(1[4-9]\d\d|20\d\d)s?\b|\b\d{1,2}(st|nd|rd|th) century\b", re.I)
# Cuántas fotos y cuánto tiempo cada una: reglas fijas en ilustrar.py (mínimo 6 distintas, ninguna
# más de 6 s seguidos). Cuántas se buscan y cuántas ve Gemini: FOTOS_*_MAX y POOL_MAX, más abajo.
# Largo del guion, según la voz (todo MEDIDO en la Pi el 2026-09-27):
#   Gemini TTS (la voz elegida el 28/09): ~2,3 palabras/s (113 palabras en 48,7 s, sin contar
#     la instrucción que al principio leía en voz alta). 85-105 palabras son ~37-46 s: casi no
#     hace falta la aceleración de hasta ×1,25 (efemerides.tts_acelerar_max).
#   Piper (el respaldo): 3,0-3,2 palabras/s con las pausas: 85 palabras son ~28 s, algo corto.
# El rango sale de la voz principal. Antes fue 105-135 (para Piper) y, antes, 88-115 (estimado).
# Mínimo 70 desde el 2026-09-28 (Santi: "~30 s está bien para un Short"): con 85, la regla de
# claridad hacía que flash-lite quedara en 68-82 palabras y la efeméride entera fallaba. Se le
# sigue PIDIENDO 80-100 (el prompt apunta más alto que el mínimo para que no quede justo).
PALABRAS_MIN, PALABRAS_MAX = 70, 105
# La historia de Facebook corta (2026-11-10): 20-30 s a ~2,3 palabras/s; se le piden 50-70.
PALABRAS_MIN_CORTO, PALABRAS_MAX_CORTO = 45, 72
CORTO_MAX_S = 30.0
# Las de Latinoamérica, 30-40 s (Santi, 2026-11-13): se le piden 70-90 palabras.
LATAM_PALABRAS, LATAM_MAX_S = (65, 95), 40.0

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]

# Primer filtro, sin gastar Gemini: lo obvio sensible sale antes de mostrárselo. Gemini decide el
# resto. "Guerras recientes": las palabras de guerra solo cuentan desde 1945.
_SENSIBLE = re.compile(
    r"\b(atentad\w*|terroris\w*|masacr\w*|massacre\w*|genocid\w*|asesina\w*|assassinat\w*|"
    r"murder\w*|tiroteo\w*|shooting\w*|bomb\w*|kill\w*|muert[oa]s|muere\w*|mueren|die[sd]|death\w*|"
    r"dead|víctima\w*|victim\w*|accidente\w*|crash\w*|desastre\w*|disaster\w*|catástrofe\w*|"
    r"terremoto\w*|earthquake\w*|huracán|hurricane\w*|erupci\w*|eruption\w*|naufrag\w*|"
    r"hostage\w*|rehén\w*|suicid\w*|execut\w*|ejecut\w*)\b", re.I)
_GUERRA = re.compile(r"\b(guerra|war|invasi\w*|invade\w*|ofensiva|offensive|batalla|battle|"
                     r"bombard\w*|militar\w*|military|coup|golpe de estado)\b", re.I)
_CAPTURA = re.compile(r"screen ?shot|captura de pantalla|screen capture|homepage|home page|"
                      r"web ?page|website|p[aá]gina web|sitio web|facebook|twitter|instagram|reddit|"
                      r"youtube|tiktok|\bforum\b|foro", re.I)
_HABLA_DE_WEB = re.compile(r"p[aá]gina|sitio|web|foro|forum|internet|red(es)? social|facebook|twitter|"
                           r"instagram|reddit|youtube|tiktok|4chan|imageboard|app\b|aplicaci[oó]n", re.I)
_SIN_FECHA = re.compile(r"\b(durante siglos|over centuries|se construy\w*|was built|"
                        r"a lo largo de|over the course of)\b", re.I)

# Ficción (Santi, 2026-11-11, Ash Ketchum): NO hechos que pasan DENTRO de una ficción (lo que le pasa
# a un personaje en un episodio, juego o película). Cultura pop sí, solo desde la vida real.
_FICCION = (r"(anim[eé]|manga|serie|episodio|cap[ií]tulo|videojuego|juego|pel[ií]cula|c[oó]mic|"
            r"historieta|novela|telenovela|saga|anime|series|episode|video ?game|game|film|movie|"
            r"comic|novel|show)")
_TRAMA = re.compile(rf"^\s*(en|in)\s+(el|la|los|las|un|una|the|an?)?\s*([\w'’.:-]+\s+){{0,3}}{_FICCION}\b"
                    rf"[^,.;]{{0,60}},", re.I)
# En el guion: "en la serie, Ash…" = la trama contada adentro (la regla dice: solo lo real).
_TRAMA_GUION = re.compile(rf"\b(en|dentro de)\s+(el|la|los|las)\s+([\w'’.:-]+\s+){{0,2}}{_FICCION}"
                          rf"(\s+de\s+[\w'’.:-]+){{0,3}}\s*,", re.I)

# Fotos que no sirven aunque la licencia sea libre. Se busca en el nombre del archivo, el epígrafe
# y las categorías de Commons.
_NO_FOTO = re.compile(
    r"\b(map|maps|mapa|mapas|locator|location|ubicaci\w*|flag|flags|bandera\w*|coats?[ _]of[ _]arms|"
    r"escudo\w*|emblem\w*|emblema\w*|seal|sello|signature|firma|autograph|diagram\w*|diagrama\w*|"
    r"chart|gr[aá]fico\w*|graph|logo\w*|icon\w*|[ií]cono\w*|symbol|s[ií]mbolo|"
    # Imágenes duras: pasan por licencia pero no van en un Short para público joven (el
    # 2026-09-27, el artículo del Pacto del Eje traía un carro cargado de cadáveres).
    r"corpse\w*|cad[aá]ver\w*|dead|muert[oa]s|body|bodies|execution|ejecuci\w*|massacre|masacre|"
    r"victim\w*|v[ií]ctima\w*|wounded|herido\w*)\b", re.I)
_MIMES = ("image/jpeg", "image/png", "image/tiff", "image/webp")


class WikiError(RuntimeError):
    def __init__(self, mensaje: str, status: int = 0):
        super().__init__(mensaje)
        self.status = status     # 429 = Wikimedia nos está limitando


def _norm(t: str) -> str:
    sin = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin.lower())


def _norm_art(t) -> str:
    """Un título de artículo comparable: sin tildes, en minúsculas y con espacios en vez de guiones bajos."""
    return _norm(str(t or "").replace("_", " ")).strip()


def sin_html(t: str) -> str:
    """Commons a veces manda el HTML escapado ("&lt;abbr ..."): se desescapa ANTES de sacar tags.
    Los bloques <style> y <script> se sacan ENTEROS: el 5/11 el autor de una foto de Commons trajo
    el CSS de Wikipedia (".mw-parser-output .hlist …", cientos de caracteres) y la descripción del
    video de Android pasó el largo de un mensaje de Telegram."""
    t = html.unescape(str(t or ""))
    t = re.sub(r"<(style|script)\b[^>]*>.*?</\1\s*>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


# ---- red: Wikipedia y Commons -------------------------------------------------------

@dataclass
class Evento:
    lang: str
    anio: int
    texto: str
    paginas: list[str]                # títulos de los artículos, el primero es el principal

    def a_dict(self) -> dict:
        return asdict(self)


@dataclass
class Foto:
    archivo: str                      # "File:..." tal como lo da la API
    url: str                          # miniatura de 1280 px (o el original si es más chico)
    ancho: int
    alto: int
    licencia: str
    autor: str
    epigrafe: str
    pagina: str                       # la página del archivo en Commons, para el crédito
    articulo: str
    ruta: str = ""                    # la copia local, cuando se baja
    anio: int | None = None           # cuándo se sacó (DateTimeOriginal de Commons), si se sabe
    # Santi, 2026-11-18 (capa 1): de un artículo GENERAL (un país, una ciudad entera): solo sirve como paisaje o vista
    # de ese lugar, nunca para una frase sobre una persona, un club o un hecho.
    general: bool = False

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Foto":
        return cls(**d)


CACHE_DIR = DATA_DIR / "cache_wiki"
CACHE_API_S = 3 * 86400       # consultas (hechos, textos, imageinfo): cambian poco en 3 días
CACHE_BORRAR_S = 30 * 86400   # nada vive más de 30 días (las fotos: ~4 MB por día)
# Las miniaturas que se piden. Tienen que ser anchos ESTÁNDAR de Wikimedia: los otros se generan
# a pedido y son lo primero que upload.wikimedia.org limita. Si la foto original no es más ancha
# que la miniatura, la API devuelve el ORIGINAL (así se bajó el que dio 429 el 2026-09-28, un
# Bundesarchiv de menos de 1280 px): ahí se prueba la de 960, y si tampoco, la foto no se usa.
MINIATURAS = (1280, 960)


COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def es_miniatura(url: str) -> bool:
    return "/thumb/" in url


def _api(lang: str) -> str:
    """lang "commons" = la API de Commons; si no, la de esa Wikipedia."""
    return COMMONS_API if lang == "commons" else API.format(lang=lang)


class Wiki:
    def __init__(self, session: requests.Session | None = None, timeout: float = 30,
                 sleep=time.sleep, cache: Path | None = CACHE_DIR):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._sleep = sleep
        self.cache = cache
        self.ua = user_agent()
        if cache:
            self._limpiar_cache()

    PAUSA_S = 0.5         # entre consultas: el 2026-09-27, con varias corridas seguidas, dio 429
    PAUSA_FOTOS_S = 2.0   # entre descargas de upload.wikimedia.org, que limita mucho más
    ESPERA_MAX_S = 120    # tope al Retry-After, para no colgar la escucha

    def _limpiar_cache(self) -> None:
        limite = time.time() - CACHE_BORRAR_S
        for f in self.cache.glob("*/*"):
            try:
                if f.stat().st_mtime < limite:
                    f.unlink()
            except OSError:
                pass

    def _en_cache(self, tipo: str, clave: str, ext: str) -> Path | None:
        if not self.cache:
            return None
        return self.cache / tipo / (hashlib.sha1(clave.encode()).hexdigest() + ext)

    def _pedir(self, url: str, params: dict | None = None, timeout: float | None = None):
        """GET con pausa entre llamadas y reintentos. Lo usan las consultas Y las descargas de
        fotos: upload.wikimedia.org también devuelve 429 (pasó bajando la foto del lanzamiento
        de la sonda Dawn, el 2026-09-27, y un Bundesarchiv el 2026-09-28)."""
        # Las miniaturas vienen de upload.wikimedia.org o de thumb.wikimedia.org (las de Commons,
        # visto el 2026-09-28): a las dos, la pausa larga.
        foto = "upload.wikimedia.org" in url or es_miniatura(url)
        status = 0
        for intento in range(4):
            self._sleep(self.PAUSA_FOTOS_S if foto else self.PAUSA_S)
            try:
                r = self.session.get(url, params=params, timeout=timeout or self.timeout,
                                     headers={"User-Agent": self.ua})
            except requests.RequestException as e:
                error, espera = str(e), 3 * (intento + 1)
            else:
                if r.status_code == 200:
                    return r
                status = r.status_code
                error = f"{r.status_code} {r.text[:150]}"
                if r.status_code < 500 and r.status_code != 429:
                    break
                # 429: Wikimedia dice cuánto esperar. Se respeta, con tope.
                pedido = r.headers.get("Retry-After", "").strip()
                espera = (min(int(pedido), self.ESPERA_MAX_S) if pedido.isdigit()
                          else (15 if foto else 10) * (intento + 1))
            if intento < 3:
                self._sleep(espera)
        raise WikiError(f"Wikipedia {url[:120]}: {error}", status)

    def _get(self, url: str, params: dict | None = None) -> dict:
        ruta = self._en_cache("api", url + json.dumps(params or {}, sort_keys=True), ".json")
        if ruta and ruta.exists() and time.time() - ruta.stat().st_mtime < CACHE_API_S:
            try:
                return json.loads(ruta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        d = self._pedir(url, params).json()
        if ruta:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return d

    def eventos(self, lang: str, dia: date) -> list[Evento]:
        d = self._get(FEED.format(lang=lang, mm=dia.month, dd=dia.day))
        out = []
        for e in d.get("events") or []:
            if not isinstance(e.get("year"), int):
                continue
            paginas = [str(p.get("title") or "") for p in e.get("pages") or [] if p.get("title")]
            out.append(Evento(lang, e["year"], str(e.get("text") or ""), paginas))
        return out

    def texto(self, lang: str, titulo: str) -> str:
        d = self._get(API.format(lang=lang), {"action": "query", "format": "json", "prop": "extracts",
                                              "explaintext": 1, "redirects": 1, "titles": titulo})
        return "\n".join(str(p.get("extract") or "") for p in d["query"]["pages"].values())

    def en_espanol(self, titulo_en: str) -> str | None:
        """El artículo equivalente en es.wikipedia, si existe (para validar el guion en castellano)."""
        d = self._get(API.format(lang="en"), {"action": "query", "format": "json", "prop": "langlinks",
                                              "lllang": "es", "redirects": 1, "titles": titulo_en})
        for p in d["query"]["pages"].values():
            for l in p.get("langlinks") or []:
                return l.get("*")
        return None

    def en_ingles(self, titulo_es: str) -> str | None:
        """El artículo equivalente en en.wikipedia (Santi, 2026-11-24: buscar fotos con el nombre en inglés)."""
        d = self._get(API.format(lang="es"), {"action": "query", "format": "json", "prop": "langlinks",
                                              "lllang": "en", "redirects": 1, "titles": titulo_es})
        for p in d["query"]["pages"].values():
            for l in p.get("langlinks") or []:
                return l.get("*")
        return None

    def archivos(self, lang: str, titulo: str) -> list[str]:
        d = self._get(API.format(lang=lang), {"action": "query", "format": "json", "prop": "images",
                                              "imlimit": 50, "redirects": 1, "titles": titulo})
        return [i["title"] for p in d["query"]["pages"].values() for i in p.get("images") or []]

    def info(self, lang: str, archivos: list[str], ancho: int = MINIATURAS[0]) -> list[dict]:
        """imageinfo con licencia, autor, epígrafe y la URL de la miniatura de `ancho` px (o la del
        original, si no es más ancho). Sirve para archivos locales y de Commons."""
        out = []
        for i in range(0, len(archivos), 50):
            d = self._get(_api(lang), {
                "action": "query", "format": "json", "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": ancho,
                "iiextmetadatalanguage": "es", "titles": "|".join(archivos[i:i + 50])})
            for p in (d.get("query") or {}).get("pages", {}).values():
                if p.get("imageinfo"):
                    out.append({"archivo": p["title"], **p["imageinfo"][0]})
        return out

    def buscar_commons(self, terminos: str, cuantas: int = 6) -> list[dict]:
        """Fotos de Commons para `terminos` ("Penicillium mold"), con su imageinfo: primero las que
        encuentra el buscador (solo mapas de bits), después las de la categoría que mejor coincide.
        Los filtros de licencia y de contenido los aplica quien llama (`filtrar_infos`)."""
        imageinfo = {"prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                     "iiurlwidth": MINIATURAS[0], "iiextmetadatalanguage": "es"}
        d = self._get(COMMONS_API, {"action": "query", "format": "json", "generator": "search",
                                    "gsrsearch": f"{terminos} filetype:bitmap", "gsrnamespace": 6,
                                    "gsrlimit": cuantas, **imageinfo})
        paginas = sorted((d.get("query") or {}).get("pages", {}).values(),
                         key=lambda p: p.get("index", 0))
        cat = self._get(COMMONS_API, {"action": "query", "format": "json", "list": "search",
                                      "srsearch": terminos, "srnamespace": 14, "srlimit": 1})
        for c in (cat.get("query") or {}).get("search", [])[:1]:
            d = self._get(COMMONS_API, {"action": "query", "format": "json",
                                        "generator": "categorymembers", "gcmtitle": c["title"],
                                        "gcmtype": "file", "gcmlimit": cuantas, **imageinfo})
            paginas += list((d.get("query") or {}).get("pages", {}).values())
        out, vistos = [], set()
        for p in paginas:
            if p.get("imageinfo") and p["title"] not in vistos:
                vistos.add(p["title"])
                out.append({"archivo": p["title"], **p["imageinfo"][0]})
        return out

    def coordenadas(self, lang: str, titulo: str) -> tuple[float, float] | None:
        """(lat, lon) del artículo, si Wikipedia las tiene (para el mapa con el punto)."""
        d = self._get(API.format(lang=lang), {"action": "query", "format": "json", "prop": "coordinates",
                                              "redirects": 1, "titles": titulo})
        for p in (d.get("query") or {}).get("pages", {}).values():
            for c in p.get("coordinates") or []:
                if str(c.get("globe") or "earth").lower() != "earth":   # la Luna, Marte: no van al mapa
                    continue
                return float(c["lat"]), float(c["lon"])
        return None

    def mapa_base(self, carpeta: Path) -> Path:
        """El mapa del mundo (NASA Blue Marble, dominio público) en miniatura de 2560 px, en caché."""
        from .graficos import MAPA_BASE

        info = self.info("commons", [MAPA_BASE], 2560)
        if not info or not es_miniatura(info[0].get("thumburl") or ""):
            raise WikiError("no pude conseguir el mapa base")
        return self.bajar(info[0]["thumburl"], carpeta / "mapa_base.png")

    def bajar(self, url: str, destino: Path) -> Path:
        """Solo miniaturas (ver MINIATURAS), y cada una una sola vez: queda en la caché."""
        if not es_miniatura(url):
            raise WikiError(f"no es una miniatura, no la bajo: {url[:120]}")
        destino.parent.mkdir(parents=True, exist_ok=True)
        ruta = self._en_cache("fotos", url, Path(url).suffix[:5] or ".jpg")
        if ruta and ruta.exists() and ruta.stat().st_size > 0:
            shutil.copyfile(ruta, destino)
            return destino
        datos = self._pedir(url, timeout=60).content
        destino.write_bytes(datos)
        if ruta:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(datos)
        return destino


# ---- 1. candidatos -------------------------------------------------------------------

def motivo_evento(e: Evento, hoy: date) -> str | None:
    """Por qué el evento no entra ni a la lista que ve Gemini."""
    if not e.paginas:
        return "sin artículo"
    if e.anio > hoy.year:
        return "fecha rara"
    if _SENSIBLE.search(e.texto):
        return "tema sensible"
    if e.anio >= 1945 and _GUERRA.search(e.texto):
        return "guerra reciente"
    if _SIN_FECHA.search(e.texto):
        return "sin fecha exacta"
    if _TRAMA.search(e.texto):
        return "trama de una ficción"
    return None


SISTEMA_ELEGIR = """Elegís efemérides para un canal de videos cortos, "Pequeña Historia", para un público
joven (15 a 30 años) de habla hispana. Te paso los hechos que pasaron en la fecha de hoy.

Ordená los más interesantes, del mejor al peor: los que generan "¿en serio pasó eso?", los de
ciencia, espacio, inventos, cultura pop, deportes, récords, cosas curiosas. Tienen que cumplir:
- Fecha EXACTA: algo que pasó ESE día (un lanzamiento, un estreno, un descubrimiento, un récord).
  Nada de procesos largos ("se construyó durante siglos") ni de "en esta década".
- NADA sensible: guerras recientes, atentados, masacres, muertes trágicas, accidentes, desastres.
- NADA que pase DENTRO de una ficción: lo que le pasa a un personaje en un episodio, un juego, una
  película o un libro ("en el animé, Ash se proclama campeón") NO es un hecho. La cultura pop SÍ,
  pero solo lo que pasó en la vida real: el estreno, el lanzamiento, quién lo creó, cómo se hizo,
  qué impacto tuvo, récords.
- Que se pueda contar en 40 segundos y se entienda sin saber historia.
Respondé solo con el JSON pedido."""

SCHEMA_ELEGIR = {
    "type": "OBJECT",
    "properties": {"elegidos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"indice": {"type": "INTEGER"}, "articulo": {"type": "STRING"},
                       "motivo": {"type": "STRING"},
                       # el puntaje de la de tecnología (2026-11-13), 1 a 10 cada uno
                       "marca": {"type": "INTEGER"}, "sorpresa": {"type": "INTEGER"},
                       "consecuencia": {"type": "INTEGER"}, "final": {"type": "INTEGER"}},
        "required": ["indice", "articulo", "motivo"]}}},
    "required": ["elegidos"],
}


ELEGIDOS = 14       # (8 → 14 el 2026-11-15: presupuesto de Claude para puntuar más) el ranking que devuelve Gemini: los 3 primeros son "los 3 más interesantes"
MAX_GUIONES = 4     # (3 → 4 el 2026-11-15, presupuesto de Claude) hechos que se intentan por día (2 → 3 el 2026-09-29: con la regla de 4 fotos
                    # de época se pasa más seguido al siguiente). Cada uno son 2 llamadas (guion +
                    # fotos) más los reintentos del guion: caso normal 1 + 3 × 2 = 7


# Nicho (Santi, 2026-11-12): la efeméride diaria es SOLO "historia de la tecnología e internet".
TEMAS = {"tecnologia": """
TEMA DE ESTE CANAL: SOLO historia de la TECNOLOGÍA e INTERNET, contada desde la vida real: inventos,
lanzamientos de productos, empresas, creadores, la primera vez que algo funcionó, récords, sitios y
servicios de internet, computadoras, teléfonos, consolas, videojuegos como producto (su lanzamiento,
no su trama). NADA de otros temas (política, guerras, arte, deportes, religión, historia general),
aunque sean interesantes. Si ningún hecho de hoy es de este tema, devolvé `elegidos` VACÍO: es
preferible no sacar video que sacar uno de otro tema.
PUNTUÁ cada elegido del 1 al 10 en cuatro cosas (sé exigente):
- `marca`: ¿es una marca o un producto que TODOS conocen (Google, Windows, PlayStation, WhatsApp)?
- `sorpresa`: ¿tiene un dato sorprendente?
- `consecuencia`: ¿tuvo una consecuencia grande, algo que cambió cómo usamos internet o la tecnología?
- `final`: ¿se puede cerrar con un dato que impacte?
EJEMPLO DE 10 EN LAS CUATRO: "el error que le hizo perder a Netscape la guerra de los navegadores",
contado con giro (dominaba la web, se saltó una versión entera, la siguiente salió lenta y rota, e
Internet Explorer se quedó con todo). Un estándar técnico que nadie conoce (UML) no pasa de 3 en marca.
QUÉ HISTORIAS PRIMERO (Santi, 2026-11-23, con las vistas de YouTube): la MAYORÍA, historias de MARCAS y empresas
conocidas (cómo nació, cuando casi quiebra, su rival, el producto que fracasó); el resto, VIDEOJUEGOS y consolas.
Inventos e internet (protocolos, la primera web, redes) SOLO si la historia es muy fuerte: elegilos últimos."""}


NO_ES_DE_HOY = ("ESTA HISTORIA NO PASÓ UN DÍA COMO HOY (es del banco de reserva): no digas «hoy», «un día como "
               "hoy», «se cumplen» ni «aniversario»; contala como una historia, con su año.\n")


class SinTema(NarrarError):
    """Ningún hecho del día es del tema del canal: no sale video y se avisa (sin reintentos)."""


CRITERIOS_TEC = ("marca", "sorpresa", "consecuencia", "final")
PUNTAJE_TEC_MIN = 7.5     # Santi, 2026-11-13
# Santi, 2026-11-23: la mayoría de marcas, el resto videojuegos; inventos e internet solo si la historia es muy fuerte.
SUBTEMAS_FUERTES = ("inventos", "internet")
PUNTAJE_TEC_FUERTE = 8.5


SUBTEMAS_FACILES = ("marcas", "empresas", "videojuegos")   # fotos fáciles: la reserva los prueba primero
PRECHEQUEO_MIN = 4      # fotos usables (artículo + Commons) para pedir el guion: medido el 23/11, AlphaGo 0, Max
#                         Headroom 0 y WorldWideWeb 3 (los tres sin 70 % de fotos); Engelbart 4 y Martin Cooper 4 pasan


def fotos_previas(wiki: "Wiki", e: "Evento", fotos_articulo: list) -> int:
    """Cuántas fotos usables hay para el hecho SIN Claude ni descargas: las del artículo que pasan las reglas más las
    de Commons buscando el título del artículo (Santi, 2026-11-23: "contá las fotos antes de pedir el guion")."""
    titulo = e.paginas[0].replace("_", " ")
    vistos = {clave_archivo(f.archivo) for f in fotos_articulo}
    try:
        infos = wiki.buscar_commons(titulo, cuantas=12)
        nuevas, _ = filtrar_infos(wiki, "commons", infos, titulo, e.anio)
    except Exception as err:     # noqa: BLE001 — Commons caído: que no frene, cuenta solo el artículo
        log.info("chequeo previo de fotos: Commons «%s» falló (%s)", titulo, str(err)[:80])
        return len(vistos) + PRECHEQUEO_MIN     # sin datos no se descarta
    return len(vistos | {clave_archivo(f.archivo) for f in nuevas})


def fotos_libres(wiki: "Wiki", e: "Evento", minimo: int, fuentes=None) -> int:
    """Fotos libres que hay para la historia, SIN Claude ni descargas (Santi, 2026-11-24: "el banco, comprobando antes
    que tengan fotos libres suficientes, sin gastar en Claude para el control"): las del artículo y de Commons
    (`fotos_previas`) y, si no llegan a `minimo`, las de Openverse (Flickr CC, museos), Flickr e Internet Archive con el
    nombre del artículo (también en inglés). Corta apenas llega a `minimo`."""
    fotos, _ = fotos_del_evento(wiki, e)
    n = fotos_previas(wiki, e, fotos)
    if n >= minimo:
        return n
    from . import fuentes_fotos

    nombres = [e.paginas[0].replace("_", " ")]
    if e.lang == "es":
        try:
            en = wiki.en_ingles(e.paginas[0])
        except Exception:  # noqa: BLE001
            en = None
        if en:
            nombres.insert(0, en.replace("_", " "))
    otras = fuentes or fuentes_fotos.Fuentes()
    vistos = set()
    # Cada fuente directo (sin `buscar`): no toca la corrida de fotos del video que se esté armando en paralelo.
    for fuente in (otras.openverse, otras.flickr, otras.archive):
        for q in dict.fromkeys(re.sub(r"\s*\(.*?\)", "", x).strip() for x in nombres):
            try:
                halladas = fuente(q)
            except Exception:  # noqa: BLE001 — una fuente caída no cuenta
                continue
            for h in halladas:
                if h.get("url") and h.get("licencia") and not _NO_FOTO.search(str(h.get("epigrafe") or "")):
                    vistos.add(h.get("archivo"))
            if n + len(vistos) >= minimo:
                return n + len(vistos)
    return n + len(vistos)


def minimo_tec(subtema: str | None) -> float:
    return PUNTAJE_TEC_FUERTE if subtema in SUBTEMAS_FUERTES else PUNTAJE_TEC_MIN


def elegir(cliente, eventos: list[Evento], cuantos: int = ELEGIDOS, tema: str = "",
           notas: dict | None = None) -> list[tuple[int, str]]:
    """(índice, artículo del evento) de los elegidos, del mejor al peor.

    El artículo lo elige Gemini entre los del hecho porque el primero de la lista suele ser el
    país ("Nicaragua" para el cierre de El Nuevo Diario, medido 2026-09-27) y traía fotos de playas
    y presidentes. Las fotos y el texto del guion salen SOLO de ese artículo. Si el que devuelve
    no es uno de la lista, se usa el último (el más específico, en el feed en castellano)."""
    lista = "\n".join(f"{i}. ({e.anio}) {e.texto}  [artículos: {' | '.join(e.paginas)}]"
                      for i, e in enumerate(eventos, 1))
    hasta = f"Elegí hasta {cuantos} (solo los del tema)" if tema else f"Elegí {cuantos}"
    d = json.loads(cliente.json(
        SISTEMA_ELEGIR + TEMAS.get(tema, ""), f"Hechos de hoy:\n{lista}\n\n{hasta}; `indice` es el "
        "número de la lista y `articulo` es, de sus artículos, el que trata ESPECÍFICAMENTE de ese "
        "hecho (no el país ni la ciudad), copiado tal cual.", SCHEMA_ELEGIR, temperatura=0.4))
    out: list[tuple[int, str]] = []
    for x in d.get("elegidos") or []:
        i = x.get("indice") if isinstance(x, dict) else None
        if isinstance(i, int) and 1 <= i <= len(eventos) and i - 1 not in [o[0] for o in out]:
            paginas = eventos[i - 1].paginas
            art = str(x.get("articulo") or "").strip().replace(" ", "_")
            out.append((i - 1, art if art in paginas else paginas[-1]))
            if notas is not None:     # {índice: {"puntaje": promedio, criterio: nota}}
                n = {k: x.get(k) for k in CRITERIOS_TEC if isinstance(x.get(k), int)}
                notas[i - 1] = {**n, "puntaje": round(sum(n.values()) / len(CRITERIOS_TEC), 2)
                                if len(n) == len(CRITERIOS_TEC) else 0.0}
                if tema == "tecnologia":     # Santi, 2026-11-23: qué subtema rinde más (temas.py)
                    from . import temas

                    notas[i - 1]["subtema"] = temas.subtema_tec(eventos[i - 1].texto)
    return out[:cuantos]


# ---- 2. fotos ------------------------------------------------------------------------

def licencia_libre(corta: str) -> bool:
    """Dominio público, CC0, CC BY y CC BY-SA. Nada de NC, ND, fair use ni "todos los derechos"."""
    c = _norm(corta).replace("-", " ")
    if any(x in c for x in ("fair use", "non free", "nonfree", " nc", " nd", "no comercial")):
        return False
    return bool(re.match(r"^(public domain|pd\b|cc0|cc by( sa)?\b)", c))


# Santi, 2026-11-17 (Colón: recortes de diario de 500 px agrandados a 1080, borrosos e ilegibles): nada de fotos de
# baja resolución, tampoco las de época. Era 500 para las de la época del hecho desde el 2026-10-02.
MIN_ANCHO_EPOCA = MIN_ANCHO
# Nitidez: la varianza del laplaciano en la zona más nítida de la foto (percentil 90 de cuadros de 100 px, con la foto
# a 800 de ancho). Medido con las 57 fotos del Short de Colón: los recortes de diario dan 87-493 (y miden 500 px), las
# fotos buenas 1.000-19.000; un retrato de fondo liso, 159. Debajo de esto la foto no se usa.
NITIDEZ_MIN = 150


def nitidez(ruta) -> float:
    import cv2
    import numpy as np

    im = cv2.imread(str(ruta), cv2.IMREAD_GRAYSCALE)
    if im is None:
        return 0.0
    h, w = im.shape
    esc = 800 / max(1, w)
    im = cv2.resize(im, (800, max(1, int(h * esc))), interpolation=cv2.INTER_AREA if esc < 1 else cv2.INTER_CUBIC)
    lap = cv2.Laplacian(im, cv2.CV_64F)
    H, W = lap.shape
    t = 100
    vs = [lap[y:y + t, x:x + t].var() for y in range(0, H - t + 1, t) for x in range(0, W - t + 1, t)]
    return float(np.percentile(vs, 90)) if vs else float(lap.var())


def motivo_calidad(ruta) -> str | None:
    """Regla fija (Santi, 2026-11-17): nada de fotos de baja resolución ni borrosas. Mira el archivo bajado de verdad
    (no lo que dice la fuente): menos de MIN_ANCHO px de ancho o menos de NITIDEZ_MIN de nitidez = afuera."""
    try:
        from PIL import Image

        with Image.open(ruta) as im:
            ancho = im.size[0]
    except OSError as err:
        return f"no se puede abrir ({err})"
    if ancho < MIN_ANCHO:
        return f"baja resolución ({ancho} px, mínimo {MIN_ANCHO})"
    n = nitidez(ruta)
    if n < NITIDEZ_MIN:
        return f"borrosa (nitidez {n:.0f}, mínimo {NITIDEZ_MIN})"
    return None


def motivo_foto(info: dict, anio_hecho: int | None = None) -> str | None:
    """Por qué la foto no sirve, o None. Las reglas fijas: lo que se ve lo mira Gemini después.
    `anio_hecho`: con él, una foto FECHADA en la época del hecho (hasta MARGEN_EPOCA años después)
    pasa desde MIN_ANCHO_EPOCA px (2026-10-02: las de Onzari de 1924 miden menos de 800 y no
    entraba ninguna; para lo demás sigue MIN_ANCHO)."""
    em = info.get("extmetadata") or {}

    def meta(k: str) -> str:
        return sin_html((em.get(k) or {}).get("value", ""))

    if info.get("mime") not in _MIMES:
        return f"formato {info.get('mime')}"
    corta = meta("LicenseShortName")
    if meta("NonFree").lower() in ("true", "1") or not licencia_libre(corta):
        return f"licencia no libre ({corta or 'sin dato'})"
    ancho = int(info.get("width") or 0)
    if ancho < MIN_ANCHO:
        anio = anio_de(meta("DateTimeOriginal")) or anio_de(info.get("archivo", ""))
        de_epoca = anio_hecho is not None and anio is not None and anio <= anio_hecho + MARGEN_EPOCA
        if not (de_epoca and ancho >= MIN_ANCHO_EPOCA):
            return f"menos de {MIN_ANCHO} px ({info.get('width')})"
    # CC BY / BY-SA obligan a nombrar al autor: si Commons no lo dice en ningún campo, no se usa.
    if meta("AttributionRequired").lower() == "true" and not autor_de(em):
        return "sin autor para atribuir"
    texto = " ".join([info.get("archivo", "").replace("_", " "), meta("ObjectName"),
                      meta("ImageDescription"), meta("Categories").replace("|", " ")])
    m = _NO_FOTO.search(texto)
    if m:
        return f"no es una foto del hecho ({m.group(0).lower()})"
    return None


def autor_de(em: dict) -> str:
    """El autor para el crédito. Commons no siempre lo pone en `Artist`: en la prueba del 27/09,
    dos fotos CC BY-SA de la piedra de Rosetta salían "autor desconocido" y lo tenían en
    `Attribution` ("Carlos Delgado") o en `Credit` ("Captmondo (Own work)")."""
    for k in ("Artist", "Attribution", "Credit"):
        v = sin_html((em.get(k) or {}).get("value", ""))
        # Nota de traslado ("Transferido desde de.wikipedia a Commons por X. Original uploader was
        # Bautsch at de.wikipedia"): el autor es quien lo subió originalmente, no quien lo movió.
        m = re.search(r"original uploader was\s+([^\s.,]+(?:\s+[^\s.,]+)?)\s+at\b", v, re.I)
        if m:
            return m.group(1)
        if re.match(r"(transferido|transferred)\b", v, re.I):
            continue
        v = re.sub(r"\s*\(\s*(own work|trabajo propio)\s*\)\s*", "", v, flags=re.I).strip(" ,;")
        if v and not re.fullmatch(r"own work|trabajo propio|unknown( author)?|desconocido", v, re.I):
            return v
    return ""


def a_foto(info: dict, articulo: str) -> Foto:
    em = info.get("extmetadata") or {}

    def meta(k: str) -> str:
        return sin_html((em.get(k) or {}).get("value", ""))

    epigrafe = meta("ImageDescription") or meta("ObjectName") or \
        info["archivo"].split(":", 1)[-1].rsplit(".", 1)[0].replace("_", " ")
    return Foto(archivo=info["archivo"], url=info.get("thumburl") or info.get("url") or "",
                ancho=int(info.get("width") or 0), alto=int(info.get("height") or 0),
                licencia=meta("LicenseShortName"), autor=autor_de(em) or "autor desconocido",
                epigrafe=epigrafe[:160], pagina=info.get("descriptionurl") or "", articulo=articulo,
                anio=anio_de(meta("DateTimeOriginal")))


def anio_de(fecha: str) -> int | None:
    """El año de la fecha de una foto de Commons, venga como venga: "2008-08-17", "Tomada el 20 de
    septiembre de 2010", "circa 1940s", "1 January 1940". El primero que aparezca; None si no hay."""
    m = re.search(r"(?<!\d)(1[4-9]\d\d|20\d\d)(?!\d)", fecha or "")   # "1940s" también
    return int(m.group(1)) if m else None


def filtrar_infos(wiki: Wiki, lang: str, infos: list[dict], articulo: str,
                  anio_hecho: int | None = None) -> tuple[list[Foto], dict]:
    """Las que pasan las reglas fijas (licencia, formato, tamaño, sin mapas ni imágenes duras) y
    tienen miniatura, en su orden, y por qué quedaron afuera las otras. Vale igual para las fotos
    del artículo y para las que se buscan en Commons."""
    fotos, descartes = [], {}
    for info in infos:
        m = motivo_foto(info, anio_hecho)
        if m:
            descartes[m.split(" (")[0]] = descartes.get(m.split(" (")[0], 0) + 1
        else:
            fotos.append(a_foto(info, articulo))
    # Solo miniaturas: a las que la API dio el original, se les pide la siguiente más chica.
    for ancho in MINIATURAS[1:] + ((MIN_ANCHO_EPOCA,) if anio_hecho is not None else ()):
        # La de 500 es SOLO para fotos FECHADAS en la época del hecho (las viejas son chicas): una
        # moderna o sin fecha de 900 px no puede terminar en una miniatura de 500.
        faltan = [f.archivo for f in fotos if not es_miniatura(f.url) and f.ancho > ancho
                  and (ancho != MIN_ANCHO_EPOCA
                       or (f.anio is not None and f.anio <= anio_hecho + MARGEN_EPOCA))]
        if faltan:
            urls = {i["archivo"]: i.get("thumburl") or "" for i in wiki.info(lang, faltan, ancho)}
            for f in fotos:
                if f.archivo in urls and es_miniatura(urls[f.archivo]):
                    f.url = urls[f.archivo]
    sin = [f for f in fotos if not es_miniatura(f.url)]
    if sin:
        descartes["sin miniatura"] = descartes.get("sin miniatura", 0) + len(sin)
        fotos = [f for f in fotos if es_miniatura(f.url)]
    return fotos, descartes


ARTICULOS_GENERALES = {
    "argentina", "mexico", "colombia", "peru", "chile", "venezuela", "uruguay", "paraguay", "bolivia", "ecuador",
    "cuba", "brasil", "guatemala", "honduras", "nicaragua", "costa rica", "panama", "el salvador", "puerto rico",
    "republica dominicana", "haiti", "estados unidos", "espana", "francia", "italia", "alemania", "reino unido",
    "japon", "china", "rusia", "america latina", "latinoamerica", "america del sur", "sudamerica", "europa",
    "united states", "spain", "france", "germany", "italy", "japan", "mexico city", "ciudad de mexico"}


def es_general(titulo: str) -> bool:
    """Un artículo de un país o de una región entera (Santi, 2026-11-18: en Colón el artículo del hecho era
    "Argentina" y de ahí salieron Illia y Cristina Kirchner en Atucha)."""
    return _norm(re.sub(r"\s*\(.*?\)\s*", " ", str(titulo or ""))).strip() in ARTICULOS_GENERALES


def fotos_del_evento(wiki: Wiki, e: Evento) -> tuple[list[Foto], dict]:
    """Las fotos del artículo del evento (`e.paginas[0]`) que pasan las reglas, en su orden, y por
    qué quedaron afuera las otras. Las de un artículo general (un país) quedan marcadas `general`."""
    titulo = e.paginas[0]
    archivos = list(dict.fromkeys(wiki.archivos(e.lang, titulo)))
    fotos, desc = filtrar_infos(wiki, e.lang, wiki.info(e.lang, archivos), titulo, e.anio)
    if es_general(titulo):
        for f in fotos:
            f.general = True
    return fotos, desc


def bajar_fotos(wiki: Wiki, fotos: list[Foto], carpeta: Path, prefijo: str, cuantas: int,
                avisar=log.info) -> tuple[list[Foto], list[Foto]]:
    """Baja hasta `cuantas` fotos, en orden. La que falla se saltea y se sigue con la próxima
    (antes, una sola foto con 429 tiraba la efeméride entera, el 2026-09-28). Devuelve las bajadas
    y las que no se llegaron a probar (la reserva). Tres 429 seguidos = upload.wikimedia.org nos
    está limitando: se corta ahí, porque insistir solo alarga el castigo."""
    bajadas: list[Foto] = []
    seguidos = 0
    for n, f in enumerate(fotos):
        if len(bajadas) >= cuantas:
            return bajadas, fotos[n:]
        try:
            destino = carpeta / f"foto_{prefijo}_{n:02d}.jpg"
            if es_de_otra_fuente(f):
                from . import fuentes_fotos

                try:
                    f.ruta = str(fuentes_fotos.bajar(f.url, destino, CACHE_DIR / "otras"))
                except (requests.RequestException, ValueError, OSError) as err:
                    raise WikiError(f"{f.archivo}: {err}") from err
                from PIL import Image

                with Image.open(f.ruta) as im:
                    f.ancho, f.alto = im.size
            else:
                f.ruta = str(wiki.bajar(f.url, destino))
        except WikiError as err:
            avisar(f"  foto salteada ({f.archivo[:60]}): {str(err)[:120]}")
            seguidos = seguidos + 1 if err.status == 429 else 0
            if seguidos >= 3:
                raise WikiError("upload.wikimedia.org nos está limitando (429 en 3 fotos "
                                "seguidas)", 429) from err
            continue
        seguidos = 0
        malo = motivo_calidad(f.ruta)
        if malo:
            avisar(f"  foto salteada ({f.archivo[:60]}): {malo}")
            continue
        bajadas.append(f)
    return bajadas, []


def es_de_otra_fuente(f: Foto) -> bool:
    """Las que no son de Wikimedia: su `archivo` es "openverse:…", "europeana:…", etc."""
    return not f.archivo.startswith("File:") and ":" in f.archivo.split(" ")[0]


def creditos(fotos: list[Foto]) -> str:
    """Autor y licencia de cada foto, en el orden en que aparecen, UNA vez cada una. Va al final de
    la descripción. Una tarjeta lleva el crédito de su foto de base: con 4 tarjetas sobre la misma
    foto salía 4 veces la misma línea (Epecuén, 2026-11-09); ahora se cuenta una sola vez, también
    si la foto de base aparece además sola."""
    lineas = ["Fotos:" if any(es_de_otra_fuente(f) for f in fotos) else "Fotos (Wikimedia Commons):"]
    vistas: set[tuple] = set()
    for f in fotos:
        clave = (f.autor, f.licencia, f.pagina)
        if clave in vistas:
            continue
        vistas.add(clave)
        lineas.append(f"{len(vistas)}. {f.autor} — {f.licencia}" + (f" — {f.pagina}" if f.pagina else ""))
    return "\n".join(lineas)


# ---- 3. guion ------------------------------------------------------------------------

SISTEMA_GUION = """Escribís la voz en off de un video vertical de 35 a 45 segundos para "Pequeña Historia",
un canal de efemérides para público joven, en español rioplatense (vos, no tú).

REGLA DE ORO: usás SOLO lo que dice el texto del artículo que te paso. Nada de tu memoria: ni un
nombre, ni un número, ni una fecha que no esté ahí. Si el artículo no lo dice, no lo digas.

- La PRIMERA frase es el GANCHO: lo más sorprendente del hecho, desde la primera palabra, en 14
  palabras como mucho y SIN fecha ("Una banda terminó una canción 45 años después."). Nada de
  "Un día como hoy" ni de arranques de relleno ("¿Sabías que…?", "Hoy te cuento…").
- La SEGUNDA frase suma INTRIGA, sin el año: algo que haga querer saber cómo siguió ("Y lo hicieron
  sin ejército…", "Y tenía un solo barco…"). NO arranca con "En <año>" (en Facebook la gente se iba
  justo ahí: 98 % hasta el segundo 3 y 40 % en el 8). El año y el lugar ya van escritos en pantalla.
- El AÑO se dice recién en la TERCERA o CUARTA frase ("Fue en 1811.").
- ESTRUCTURA (Santi, 2026-11-13: en Facebook la gente se va después del segundo 3): GANCHO → TENSIÓN →
  GIRO → un FINAL QUE PAGA lo que prometió el gancho. El gancho deja una PREGUNTA ABIERTA que solo se
  responde al final (por eso se quedan). La tensión es el problema, el peligro o lo que estaba en
  juego ("Pero había un problema…"); el giro, lo que nadie esperaba; el pago, la respuesta a la
  pregunta del gancho, en la ANTEÚLTIMA frase (la última es la pregunta al público). Decí en `pregunta_gancho` cuál es esa
  pregunta y en `frase_tension`, `frase_giro` y `frase_pago` el número de cada frase (desde 1).
- Tono: como alguien que te cuenta algo que lo sorprendió, con ganas. Nada de tono de manual.
- Frases CORTAS: ninguna de más de 14 palabras. Mejor dos frases que una larga con comas.
- Al menos UNA pregunta ("¿Sabés qué hizo después?") y al menos UNA exclamación ("¡Y funcionó!")
  en el medio del guion, para que no suene plano.
- GIRO A LA MITAD (Santi, 2026-11-16: la gente se va entre el segundo 10 y el 20): justo en el medio del
  guion, una frase CORTA que renueve la intriga y anuncie que viene algo inesperado ("Pero lo que nadie
  sabía…", "Y ahí todo cambió.", "Pero faltaba lo peor…"), dicha con las palabras de ESTA historia. Decí
  en `frase_intriga` su número (va entre el 30 % y el 60 % de las frases, nunca la 1 ni la 2).
- CIERRE (Santi, 2026-11-16): la ÚLTIMA frase es una PREGUNTA CORTA al público que invite a comentar,
  sobre ESTA historia (12 palabras como mucho, termina con "?"): "¿Vos hubieras hecho lo mismo?",
  "¿Sabías que esto pasó en tu país?", "¿Cuál otra historia así conocés?". El pago del gancho va en la
  ANTEÚLTIMA frase. Nada de cierres tipo "y así fue" ni de "suscribite" o "dale like".
- Entre 80 y 100 palabras en total (contalas: menos de 70 queda corto y más de 105 se pasa de
  45 segundos), en 8 a 14 frases, habladas, no escritas. Si el artículo da para poco,
  contá más detalle de lo que SÍ dice.
- Números: solo los que están en el artículo, escritos igual. Nada de "hoy tiene millones de…"
  si el artículo no lo dice con esas palabras.
- Sin emojis, sin hashtags, sin "suscribite".
- FICCIÓN (series, animé, juegos, películas, libros): contá SOLO la vida real: el estreno o el
  lanzamiento, quién lo creó, cómo se hizo, qué impacto tuvo, récords. NUNCA la trama: nada de lo
  que hace o le pasa a un personaje ("en la serie, Ash viajó…", "Pikachu lo salvó"). Si el hecho
  es algo que pasa dentro de la historia, no sirve. Poné `cuenta_trama` en true si alguna frase
  cuenta la trama (y entonces reescribila).
""" + REGLAS_CLARIDAD + REGLA_GANCHO_CONCRETO + """
- NADA ABSTRACTO (Santi, 2026-11-25): cada frase habla de algo que se pueda MOSTRAR con una foto (una persona, un
  objeto, un lugar, un momento), no de ideas sueltas ("la mitad del mercado", "su importancia", "el éxito"). Si
  querés dar un dato abstracto, atalo a algo que se ve ("Medio Japón caminaba con un Walkman puesto."). Solo la
  frase del giro a la mitad y la pregunta final pueden no tener imagen propia.
- LOS PRODUCTOS SE NOMBRAN SIEMPRE: "un Walkman", "el Nokia 3310", "la Game Boy"; nunca "un aparato", "el
  dispositivo", "un artefacto azul y plateado" ni "el invento" sin decir cuál es.
- "Menos datos" NO es un guion más corto: sigue siendo de 80 a 100 palabras. Las palabras que
  dejás de gastar en fechas y nombres van a explicar el cómo y el porqué.
- Cada frase lleva `mostrar`: qué tendría que verse en pantalla mientras se dice, como búsqueda
  para Wikimedia Commons, EN INGLÉS y concreta, de 3 a 7 palabras. Tiene que nombrar la COSA
  PUNTUAL de esta historia (la persona, el objeto, el lugar, el organismo), no una categoría
  general. BIEN: "Penicillium mold", "penicillin petri dish", "Alexander Fleming laboratory",
  "penicillin vial 1940s". MAL (dan fotos de cualquier cosa): "microscope view",
  "medical research", "historical laboratory", "discovery", "importance". Si una frase habla
  de una idea, mostrá la cosa concreta que la ilustra. Variá: frases distintas, cosas distintas.
  ÉPOCA Y LUGAR (regla fija): cada `mostrar` lleva el AÑO o la DÉCADA del hecho y, si se puede,
  el país o el lugar, para que la foto sea de ese momento y no de hoy. BIEN: "1940 RAAF Avro
  Anson Australia", "1940 German fighter aircraft grounded", "1928 London laboratory". MAL:
  "airplane", "Avro Anson" (da fotos de aviones de exhibición de 2008).
  DISTINTO EN CADA FRASE: cada `mostrar` busca otra cosa según lo que dice esa frase (la persona, el
  lugar, el rival, el objeto, la multitud, la época). Nunca dos frases con el mismo `mostrar`.
- Cada frase lleva `objeto`: la COSA o la ACCIÓN que se ve mientras se dice, GENÉRICA, en inglés, de
  2 a 4 palabras, SIN año ni lugar ni nombres propios: "steam locomotive", "burning train wagon",
  "flooded town street", "nun writing letter". Es para buscar una foto del objeto cuando no hay una
  del hecho, así que tiene que ser algo que se pueda fotografiar.
- Cada frase lleva `central`: true si cuenta el HECHO MISMO, su lugar o su protagonista (ahí va una
  foto real de eso: el pueblo inundado, el tren en llamas, la persona); false si nombra una cosa AL
  PASAR para explicar (un muro, un juego, un animal, un objeto): ahí alcanza una foto genérica.
- Cada frase lleva `presente`: true SOLO si la frase habla de HOY (algo que sigue existiendo o
  pasa ahora: "hoy ese avión está en un museo"); si no, false. Con false, las fotos de mucho
  después del hecho no se usan.
- `accion`: true en 2 o 3 frases (nunca más), las de ACCIÓN o el MOMENTO CLAVE: donde pasa algo
  que se puede ver en movimiento (un despegue, una explosión controlada, un descubrimiento, algo en
  el espacio, una multitud que festeja). Esas van con video en vez de foto. false en las de
  contexto (quién era, dónde, por qué importa) y en la primera frase.
- `claves`: 2 a 4 palabras SUELTAS del guion, escritas tal cual aparecen, que conviene ver grandes
  en pantalla cuando la voz las dice (la cosa, el nombre o la cifra clave). No "hoy" ni "año".
- `idea_clave`: en una frase, lo que un chico de 15 años tiene que haber entendido al final (qué
  pasó y por qué importa). El guion tiene que explicarlo.
- `titulo`: hasta 55 caracteres, con gancho, sin clickbait falso. `descripcion`: 1 a 3 frases
  sobre el hecho, sin hashtags ni links. `hashtags`: 3 a 5, incluido #Shorts.
- `tono`: el clima de la historia, para elegir la música de fondo: alegre, epico, misterioso,
  curioso o emotivo.
- HUMOR (Santi, 2026-11-14): cuando la historia lo permite, UN toque de humor o ironía suave, como lo
  diría alguien que cuenta algo con gracia ("y sí, le salió bastante mal"), en una frase que no sea el
  gancho ni el pago. Nada de chistes forzados ni de remates de stand-up: si no sale natural, sin
  humor. NUNCA en muertes, ejecuciones, tragedias, guerras, enfermedades, abusos ni temas sensibles:
  ahí el tono es serio de punta a punta.
Respondé solo con el JSON pedido."""

SISTEMA_GUION_HABLADO = SISTEMA_GUION.replace(
    """- Frases CORTAS: ninguna de más de 14 palabras. Mejor dos frases que una larga con comas.""",
    """- ESCRITO PARA SER DICHO EN VOZ ALTA (lo lee una voz y tiene que sonar a una persona contando una
  historia, no a un texto leído): rioplatense de verdad ("mirá", "imaginate", "resulta que").
- Frases de LARGO VARIADO: alternás frases muy cortas (2 a 5 palabras: "Y funcionó.", "Nadie le
  creía.") con otras más largas (hasta 16 palabras). Nunca tres seguidas del mismo largo.
- Una o dos muletillas naturales, no más: "y acá viene lo mejor", "pero esperá", "posta",
  "¿y sabés qué?". Que no sea siempre la misma ni vaya en la primera frase.
- Pausas escritas: comas donde una persona respira y puntos suspensivos (…) una o dos veces, antes
  de lo sorprendente ("Y adentro encontraron… nada.").""").replace(
    """- Números: solo los que están en el artículo, escritos igual. Nada de "hoy tiene millones de…"
  si el artículo no lo dice con esas palabras.""",
    """- Números COMO SE DICEN: redondeados y con letras, con "casi", "más de", "unos" o "cerca de"
  ("casi cien años", "más de dos mil personas"), y solo redondeando un número que ESTÁ en el
  artículo o los años que pasaron desde el hecho. Nada de números que no salgan de ahí. Los años
  del hecho van en cifras ("en 1928").""")

def a_corto(sistema: str, segundos: tuple[int, int] = (20, 30),
            palabras: tuple[int, int] = (50, 70), frases: tuple[int, int] = (7, 11)) -> str:
    """El mismo prompt para el formato corto: 20-30 s y 50-70 palabras (la de tecnología, desde el
    2026-11-12) o, con otros números, 30-40 s y 70-90 (las de Latinoamérica, 2026-11-13: en Facebook
    los Reels de 30-45 s promedian 3.800 reproducciones y los de 15-30 s, 256)."""
    (s0, s1), (p0, p1), (f0, f1) = segundos, palabras, frases
    out = sistema.replace(
        "un video vertical de 35 a 45 segundos", f"un video vertical de {s0} a {s1} segundos").replace(
        "- Entre 80 y 100 palabras en total (contalas: menos de 70 queda corto y más de 105 se pasa de\n"
        "  45 segundos), en 8 a 14 frases, habladas, no escritas.",
        f"- Entre {p0} y {p1} palabras en total (contalas: menos de {p0 - 5} queda corto y más de "
        f"{p1 + 2} se pasa de\n  {s1} segundos), en {f0} a {f1} frases, habladas, no escritas. "
        "Directo a lo interesante: nada de\n  contexto que no haga falta para entender.").replace(
        '- "Menos datos" NO es un guion más corto: sigue siendo de 80 a 100 palabras.',
        f'- "Menos datos" NO es un guion más corto que {p0} palabras.')
    assert out.count(f"{s0} a {s1} segundos") == 1 and f"Entre {p0} y {p1}" in out \
        and f"más corto que {p0}" in out
    return out


SISTEMA_GUION_CORTO = a_corto(SISTEMA_GUION)

SCHEMA_GUION = {
    "type": "OBJECT",
    "properties": {
        "frases": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"texto": {"type": "STRING"}, "mostrar": {"type": "STRING"},
                           "objeto": {"type": "STRING"}, "central": {"type": "BOOLEAN"},
                           "presente": {"type": "BOOLEAN"}, "accion": {"type": "BOOLEAN"}},
            "required": ["texto", "mostrar", "presente", "accion"]}},
        "idea_clave": {"type": "STRING"},
        "claves": {"type": "ARRAY", "items": {"type": "STRING"}},
        "titulo": {"type": "STRING"},
        "descripcion": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tono": {"type": "STRING", "enum": ["alegre", "epico", "misterioso", "curioso", "emotivo"]},
        "cuenta_trama": {"type": "BOOLEAN"},
        "pregunta_gancho": {"type": "STRING"},
        "frase_tension": {"type": "INTEGER"},
        "frase_giro": {"type": "INTEGER"},
        "frase_pago": {"type": "INTEGER"},
        "frase_intriga": {"type": "INTEGER"},
    },
    "required": ["frases", "idea_clave", "titulo", "descripcion", "hashtags"],
}


def _numeros(t: str) -> set[str]:
    """Números normalizados: "1.000", "1,000" y "1000" son lo mismo."""
    return {re.sub(r"[.,](?=\d{3}\b)", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", t)}


_NUM = (r"un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|"
        r"dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|"
        r"cien|ciento|cientos|quinientos|quinientas|\w+cientos|\w+cientas|mil|miles|millon|millones|billon|billones|"
        r"docena|docenas|decenas|centenares")
_NUM_FRASE = re.compile(rf"\b(?:(?:{_NUM})(?:\s+(?:y|de)\s+|\s+))*(?:{_NUM})\b")
_SUELTOS = {"un", "una"}   # "un día como hoy", "una empresa": son artículos, no cantidades


def _numeros_en_letras(texto_norm: str) -> list[str]:
    out = []
    for m in _NUM_FRASE.finditer(texto_norm):
        frase = m.group(0).strip()
        if frase in _SUELTOS or re.fullmatch(r"(un|una)\s+(y|de)", frase):
            continue
        out.append(re.sub(r"^(un|una)\s+", "", frase))
    return out


_UNIDADES = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
             "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
             "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
             "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21, "veintiuna": 21,
             "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
             "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30,
             "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
             "noventa": 90, "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200,
             "trescientos": 300, "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400,
             "quinientos": 500, "quinientas": 500, "seiscientos": 600, "seiscientas": 600,
             "setecientos": 700, "setecientas": 700, "ochocientos": 800, "ochocientas": 800,
             "novecientos": 900, "novecientas": 900}
# Lo que en un guion hablado marca que el número está redondeado ("casi cien años").
# El orden importa: "poco mas de" antes que "mas de".
_APROX = (r"poco mas de|poco menos de|casi|unos|unas|cerca de|mas de|menos de|alrededor de|"
          r"aproximadamente")
MARGEN_REDONDEO = 0.15


def valor_en_letras(frase: str) -> int | None:
    """"dos mil quinientos" -> 2500. None si no es una cantidad exacta ("miles", "docenas")."""
    total, actual = 0, 0
    for w in frase.split():
        if w in ("y", "de"):
            continue
        if w in _UNIDADES:
            actual += _UNIDADES[w]
        elif w == "mil":
            total += (actual or 1) * 1000
            actual = 0
        elif w in ("millon", "millones"):
            total = (total + (actual or 1)) * 1_000_000
            actual = 0
        else:
            return None
    return total + actual or None


def redondeo_valido(valor: float, permitidos: set[float], como: str = "unos") -> bool:
    """¿El número dicho ("más de mil") respeta alguno de los reales (`permitidos`)? Según la palabra:
      casi / poco menos de: el real está apenas abajo (de 85 % a 100 % de lo dicho);
      más de / poco más de: el real está arriba, pero no tanto (de 100 % a 150 %): 1.356 kg es
        "más de mil kilos", 9.000 no;
      menos de: el real está abajo (de 67 % a 100 %);
      unos / cerca de / alrededor de / aproximadamente: a ±15 %."""
    for n in permitidos:
        if n <= 0:
            continue
        if como in ("casi", "poco menos de"):
            ok = valor * (1 - MARGEN_REDONDEO) <= n <= valor
        elif como in ("mas de", "poco mas de"):
            ok = valor <= n <= valor * 1.5
        elif como == "menos de":
            ok = valor * 0.67 <= n <= valor
        else:
            ok = abs(valor - n) / n <= MARGEN_REDONDEO
        if ok:
            return True
    return False


def no_respaldados(guion: str, fuente: str, anio: int | None = None, hoy: date | None = None) -> list[str]:
    """Nombres, números y meses del guion que NO están en el artículo (ni en el texto del evento).

    Los nombres salen de la heurística de mayúscula en medio de la oración (la misma de los títulos
    de los clips). Los números en cifras se comparan normalizados; los escritos con letras, como
    frase ("mil millones" tiene que estar tal cual): el 2026-09-27 el primer guion real dijo "más
    de mil millones de búsquedas diarias", que no estaba en el artículo, y el chequeo de cifras no
    lo vio. Los meses, en castellano o en inglés.

    Redondeos (guion hablado, 2026-11-01): "casi cien años", "más de dos mil personas" pasan si van
    con casi/más de/unos/cerca de y quedan a menos del 15 % de un número del artículo o de los años
    que pasaron desde el hecho (`anio`). Sin esa palabra, el número tiene que estar tal cual."""
    fuente_n = _norm(fuente)
    guion_n = _norm(guion)
    palabras_fuente = set(re.findall(r"[a-z0-9]+", fuente_n))
    faltan = []
    for frase in re.split(r"(?<=[.!?¿¡])\s+", guion):
        for nombre in nombres_propios(frase):
            if _norm(nombre) not in palabras_fuente:
                faltan.append(nombre)
    nums_fuente = _numeros(fuente)
    # "3,10" (metros) es 3.1: la coma decimal del castellano.
    permitidos = {float(n.replace(",", ".")) for n in nums_fuente if re.fullmatch(r"\d+(?:[.,]\d+)?", n)}
    if anio:
        permitidos.add(float((hoy or date.today()).year - anio))

    def aproximado(texto_num: str, valor: float | None) -> bool:
        m = re.search(rf"\b({_APROX})\s+{re.escape(texto_num)}\b", guion_n)
        return valor is not None and m is not None and redondeo_valido(valor, permitidos, m.group(1))

    faltan += [n for n in sorted(_numeros(guion))
               if n not in nums_fuente and not (n.isdigit() and aproximado(n, float(n)))]
    faltan += [f for f in _numeros_en_letras(guion_n)
               if f not in fuente_n and not aproximado(f, valor_en_letras(f))]
    for i, mes in enumerate(MESES):
        if re.search(rf"\b{mes}\b", _norm(guion)) and mes not in palabras_fuente \
                and MONTHS[i] not in palabras_fuente:
            faltan.append(mes)
    return list(dict.fromkeys(faltan))


@dataclass
class Guion:
    frases: list[str]
    fotos: list[int]                  # índice (desde 0, en Propuesta.fotos) de la foto de cada frase
    descartadas: list[int]            # índices desde 0 que Gemini vio y no sirven (o sacados con 🔁)
    titulo: str
    descripcion: str
    hashtags: list[str]
    tono: str = ""                    # para la música: alegre, epico, misterioso, curioso, emotivo
    mostrar: list[str] = field(default_factory=list)       # qué mostrar en cada frase (búsqueda)
    ranking: list[list[int]] = field(default_factory=list)  # las que sirven para cada frase, en orden
    idea_clave: str = ""              # lo que tiene que quedar entendido (regla de claridad)
    presente: list[bool] = field(default_factory=list)  # la frase habla de hoy (fotos modernas ok)
    del_hecho: list[int] = field(default_factory=list)  # fotos del artículo del hecho (el respaldo)
    modernas: list[int] = field(default_factory=list)   # fotos de más de MARGEN_EPOCA años después
    minimo_fotos: int = ilustrar.MIN_FOTOS_DISTINTAS     # baja si no hay tantas fotos de época
    sin_alternativa: bool = False     # ningún hecho del día llegó a 4 fotos de época: es el que más tenía
    # Videos (2026-09-29): las frases de acción que marcó Gemini, el video elegido para cada frase
    # ({"3": Video como dict}) y las que van con video (lo que eligió Gemini, o lo que cambió Santi
    # con 🎬). `con_videos`: la propuesta se armó buscando videos (lo respeta ✏️).
    accion: list[int] = field(default_factory=list)
    claves: list[str] = field(default_factory=list)   # palabras que se ven grandes al decirlas
    videos: dict = field(default_factory=dict)
    con_video: list[int] = field(default_factory=list)
    con_videos: bool = False
    fotos_respaldo: bool = False      # las fotos las eligió el modelo de respaldo: revisarlas (2026-10-21)
    tarjetas: list[int] = field(default_factory=list)   # frases que van con la tarjeta del año o una clave
    # Edición nueva (Santi, 2026-11-10): `objeto` = la cosa genérica de cada frase (búsquedas b y c);
    # `imagen_frase` = fotos en orden hecho/lugar → objeto en Commons → objeto en Pexels;
    # `corto` = la historia de Facebook de 20-30 s (gancho primero, cortes de 1,5-2,5 s, karaoke).
    objeto: list[str] = field(default_factory=list)
    central: list[bool] = field(default_factory=list)   # cuenta el hecho mismo: foto real obligatoria
    imagen_frase: bool = False
    corto: bool = False
    pregunta_gancho: str = ""   # la pregunta que deja abierta el gancho (se responde al final)
    max_s: float = 0.0     # tope de la voz (0 = el del formato): 40 s las de Latinoamérica
    # Control de calidad (Santi, 2026-11-11): qué parte del tiempo va con fotos reales (no tarjetas) y
    # si es la segunda búsqueda (con Claude, sin la regla de época, documentos del hecho permitidos).
    fotos_reales: float = 0.0
    segunda_busqueda: bool = False
    # Nunca un día sin video (Santi, 2026-11-15): si ningún hecho llega al 70 %, el mejor sale con el
    # mínimo bajado de a 5 puntos hasta el 50 % (este es el mínimo con el que salió; 0 = el de siempre).
    umbral_fotos: float = 0.0
    # Las tarjetas que ya están en el pool (índices): el corto las usa antes de repetir una foto.
    tarjetas_fotos: list[int] = field(default_factory=list)
    # Estilo nuevo (Santi, 2026-11-14): más video y menos fotos quietas (frases_video).
    mas_video: bool = False

    @property
    def texto(self) -> str:
        return " ".join(self.frases)

    def rankings(self) -> list[list[int]]:
        """El de cada frase; las propuestas de antes del 2026-09-28 no lo tienen: su foto sola."""
        if len(self.ranking) == len(self.frases):
            return [list(r) for r in self.ranking]
        return [[f] for f in self.fotos]

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Guion":
        return cls(**d)


_VAGO = re.compile(r"\b(un|una|el|la|ese|esa|este|esta|aquel|aquella|su|sus|los|las)\s+(aparatos?|dispositivos?|"
                   r"artefactos?|objetos?|cosas?|cacharros?|chiches?|maquinitas?|gadgets?|inventos?|productos?)\b", re.I)


def frases_vagas(frases: list[str]) -> list[int]:
    """Las frases (desde 1) que nombran un producto como "un aparato" o "el dispositivo" sin su nombre propio (Santi,
    2026-11-25): si la frase tiene un nombre propio (una mayúscula que no es la primera palabra), pasa."""
    out = []
    for i, f in enumerate(frases):
        if not _VAGO.search(f):
            continue
        palabras = re.findall(r"[\wÁÉÍÓÚÑáéíóúñ]+", f)
        if not any(w[:1].isupper() for w in palabras[1:]):
            out.append(i + 1)
    return out


def errores_estructura(d: dict, n: int) -> list[str]:
    """Gancho → tensión → giro → final que paga (Santi, 2026-11-13). El guion dice qué pregunta deja
    abierta el gancho y en qué frase va cada parte (desde 1): la tensión desde la tercera (la primera
    es el gancho y la segunda la intriga), después el giro, y el pago en la última o la anteúltima."""
    errores = []
    if not str(d.get("pregunta_gancho") or "").strip():
        errores.append("falta `pregunta_gancho`: la pregunta que deja abierta el gancho y se responde al final")
    t, g, p = (d.get(k) for k in ("frase_tension", "frase_giro", "frase_pago"))
    if not all(isinstance(x, int) for x in (t, g, p)):
        return errores + ["faltan `frase_tension`, `frase_giro` y `frase_pago` (el número de cada frase)"]
    if not 3 <= t < g <= p <= n:
        errores.append(f"la estructura no está en orden (tensión {t}, giro {g}, pago {p}): tensión desde "
                       "la frase 3, después el giro y el final que paga el gancho")
    elif p != n - 1:
        errores.append(f"el pago del gancho va en la anteúltima frase (la {n - 1}; está en la {p}): la última "
                       "es la pregunta al público")
    # Giro a la mitad (Santi, 2026-11-16: frenar la caída del segundo 10 al 20).
    i = d.get("frase_intriga")
    lo, hi = rango_intriga(n)
    if not isinstance(i, int):
        errores.append(f"falta `frase_intriga`: la frase corta de la mitad que renueva la intriga "
                       f"(\"Pero lo que nadie sabía…\"), entre la {lo} y la {hi}")
    elif not lo <= i <= hi:
        errores.append(f"la frase que renueva la intriga va a la MITAD del video (entre la {lo} y la {hi}; "
                       f"está en la {i})")
    return errores


def rango_intriga(n: int) -> tuple[int, int]:
    """Las frases donde va el giro de la mitad (30-60 % del guion, nunca la 1 ni la 2)."""
    return max(3, round(n * 0.3)), max(3, round(n * 0.6))


def validar_guion(d: dict, anio: int, fuente: str, corto: bool = False,
                  rango: tuple[int, int] | None = None) -> list[str]:
    if not isinstance(d, dict) or not isinstance(d.get("frases"), list) or not d["frases"]:
        return ["faltan las frases"]
    frases = [str((f or {}).get("texto") or "").strip() for f in d["frases"]]
    mostrar = [str((f or {}).get("mostrar") or "").strip() for f in d["frases"]]
    texto = " ".join(frases)
    errores = []
    n = len(re.findall(r"\S+", texto))
    # El aviso dice cuánto y qué hacer: con "tienen que ser entre 85 y 105" a secas, flash-lite
    # devolvió 75, 68 y 68 palabras en la prueba del 28/09, sin moverse.
    minimo, maximo = rango or ((PALABRAS_MIN_CORTO, PALABRAS_MAX_CORTO) if corto else (PALABRAS_MIN, PALABRAS_MAX))
    if n < minimo:
        errores.append(f"el guion tiene {n} palabras y el mínimo es {minimo}: te faltan "
                       f"{minimo - n + 5} palabras. Agregá 1 o 2 frases cortas que expliquen "
                       f"mejor el cómo o el porqué, con lo que dice el artículo")
    elif n > maximo:
        errores.append(f"el guion tiene {n} palabras y el máximo es {maximo}: sacá "
                       f"{n - maximo + 5} palabras (datos, no la explicación)")
    # Gancho primero en TODO Pequeña Historia (Santi, 2026-11-12: en Facebook la mayoría se iba en el
    # 0:04, justo cuando terminaba "Un día como hoy…"; en YouTube la mitad desliza al arranque): la
    # primera frase es lo más sorprendente, sin fecha; el año va en la segunda, "En <año>,".
    if _norm(frases[0]).startswith(("un dia como hoy", "sabias que", "hoy te cuento")):
        errores.append('la primera frase es el GANCHO (lo más sorprendente), sin "Un día como hoy" ni relleno')
    if str(anio) in frases[0]:
        errores.append("la primera frase (el gancho) va SIN el año: el año va en la segunda")
    if len(frases[0].split()) > 14:
        errores.append("la primera frase (el gancho) tiene que tener 14 palabras como mucho")
    generica = gancho_generico(frases[0])
    if generica:     # Santi, 2026-11-16: el gancho dice el dato concreto más fuerte, nada de fórmulas
        errores.append(f'el gancho usa una frase genérica de intriga («{generica}»): decí el DATO concreto más fuerte '
                       'de la historia (MAL: "la fusilaron y pasó algo que no esperaban"; BIEN: "la fusilaron a los 22 '
                       'y antes gritó una frase que todavía se recuerda")')
    # La segunda suma intriga y el año va en la 3.ª o 4.ª (Santi, 2026-11-12: el Reel de Cartagena
    # tenía 98 % hasta el segundo 3 y caía a 40 % en el 8, justo en "En 1811, en Cartagena…").
    if len(frases) > 1 and (str(anio) in frases[1] or re.match(r"en\s+\d", _norm(frases[1]))):
        errores.append('la segunda frase suma INTRIGA ("Y tenía un solo barco…"), sin el año: el año va '
                       "en la tercera o la cuarta")
    if not any(str(anio) in f for f in frases[2:4]):
        errores.append(f"el año ({anio}) se dice en la tercera o la cuarta frase")
    errores += errores_estructura(d, len(frases))
    vagas = frases_vagas(frases)
    if vagas:      # Santi, 2026-11-25 (el Walkman: "un aparato azul y plateado")
        errores.append(f"frases {vagas}: nombrá el producto o la cosa por su nombre (\"un Walkman\", \"el Nokia "
                       "3310\"), nunca \"un aparato\", \"el dispositivo\" ni \"el invento\" sin decir cuál es")
    # Pedido 2026-09-27 ("la voz suena triste y plana"): frases cortas, al menos una pregunta y
    # una exclamación, y cierre con gancho. Piper entona distinto una frase con ¿? o ¡!.
    if not frases[-1].rstrip().endswith("?") or len(frases[-1].split()) > 12:
        errores.append("la última frase es una PREGUNTA CORTA al público que invite a comentar, sobre esta "
                       "historia (12 palabras como mucho, termina con \"?\")")
    if "?" not in texto or "!" not in texto:
        errores.append("tiene que haber al menos una pregunta (¿…?) y una exclamación (¡…!)")
    largas = [i + 1 for i, f in enumerate(frases) if len(f.split()) > 16]
    if largas:
        errores.append(f"frases demasiado largas (más de 14 palabras): {largas}; partilas")
    sin_mostrar = [i + 1 for i, m in enumerate(mostrar) if not 1 <= len(m.split()) <= 8]
    if sin_mostrar:
        errores.append(f"frases sin `mostrar` (3 a 7 palabras en inglés): {sin_mostrar}")
    # Regla 2026-10-02 (gol olímpico: 2 fotos repetidas en todo el video): cada frase busca otra cosa.
    vistos: dict[str, int] = {}
    iguales = []
    for i, m in enumerate(mostrar):
        k = " ".join(sorted(re.findall(r"[a-z]+", _EPOCA.sub(" ", _norm(m)))))
        if k and k in vistos:
            iguales.append(f"{vistos[k] + 1} y {i + 1}")
        vistos.setdefault(k, i)
    if iguales:
        errores.append("estas frases buscan lo mismo en `mostrar`: " + ", ".join(iguales)
                       + ". Cada una tiene que mostrar otra cosa (la persona, el lugar, el rival, la época)")
    # Regla fija de época (2026-09-28: en una historia de 1940 apareció un avión de 2008): lo que se
    # busca para una frase del pasado lleva el año o la década.
    presente = [bool((f or {}).get("presente")) for f in d["frases"]]
    sin_epoca = [i + 1 for i, (m, hoy) in enumerate(zip(mostrar, presente))
                 if m and not hoy and not _EPOCA.search(m)]
    if sin_epoca:
        errores.append(f"a `mostrar` de las frases {sin_epoca} le falta la época: poné el año o la "
                       f"década del hecho ({anio}) y el lugar, ej. \"{anio} ... <país>\"")
    if not str(d.get("idea_clave") or "").strip():
        errores.append("falta `idea_clave`: qué tiene que entender un chico de 15 años al final")
    # Ficción (Santi, 2026-11-11): nunca la trama, solo la vida real.
    trama = [i + 1 for i, f in enumerate(frases) if _TRAMA_GUION.search(f)]
    if trama or d.get("cuenta_trama") is True:
        errores.append("contaste la trama de una ficción" + (f" (frases {trama})" if trama else "")
                       + ": contá SOLO la vida real (estreno, lanzamiento, quién lo creó, cómo se hizo, "
                         "impacto, récords), nada de lo que hace o le pasa a un personaje")
    faltan = no_respaldados(texto, fuente, anio)
    if faltan:
        # Con el número de frase, así la corrección puntual reescribe SOLO esa (Santi, 2026-11-26, Goycochea).
        donde = []
        for x in faltan:
            nums = [i + 1 for i, f in enumerate(frases) if x.lower() in f.lower()]
            donde.append(f"{x} (frase {', '.join(map(str, nums))})" if nums else x)
        errores.append("esto NO está en el artículo, reescribí solo esas frases con lo que dice el artículo: "
                       + ", ".join(donde))
    titulo = str(d.get("titulo") or "").strip()
    if not titulo or len(titulo) > 55:
        errores.append("el título tiene que tener entre 1 y 55 caracteres")
    tags = d.get("hashtags") or []
    if not (3 <= len(tags) <= 5 and "#Shorts" in tags
            and all(re.fullmatch(r"#[^\W_]\w*", str(t)) for t in tags)):
        errores.append("hashtags: entre 3 y 5, de una palabra, incluido #Shorts")
    return errores


MAX_VIDEOS = 3
MAX_VIDEOS_NUEVO = 6     # estilo nuevo: hasta 6 frases buscan video (archivo libre o stock)


def frases_video(g: "Guion") -> list[int]:
    """Qué frases buscan video. Como siempre, las de acción (hasta 3). Con el estilo nuevo
    (`mas_video`), también el gancho (un clip real arranca moviéndose desde el cuadro 1) y las que
    nombran algo al pasar (stock de Pexels, como sus fotos); las centrales siguen con lo real del
    hecho (archivo libre de su época o foto)."""
    if not g.mas_video:
        return list(g.accion)
    al_pasar = [i for i in range(len(g.frases)) if not es_central(g, i)]
    return sorted(dict.fromkeys([0] + list(g.accion) + al_pasar))[:MAX_VIDEOS_NUEVO]


def claves_del_guion(claves, frases: list[str]) -> list[str]:
    """Hasta 4 palabras sueltas que estén de verdad en el guion (lo demás, afuera sin reintentar)."""
    palabras = set(re.findall(r"\w+", _norm(" ".join(frases))))
    out = []
    for c in claves or []:
        c = str(c).strip(" ,.;:¡!¿?\"'«»")
        if c and len(c.split()) == 1 and _norm(c) in palabras and c not in out:
            out.append(c)
    return out[:4]


def frases_de_accion(frases: list[dict]) -> list[int]:
    """Las que Gemini marcó con `accion`, sin la primera (es el "Un día como hoy") y hasta 3."""
    return [i for i, f in enumerate(frases) if i > 0 and (f or {}).get("accion")][:MAX_VIDEOS]


SISTEMA_PAGO = """Revisás el final de un guion de video corto. El gancho (la primera frase) deja una
pregunta abierta, y el final la tiene que RESPONDER: la anteúltima o la última frase dice la
respuesta concreta a esa pregunta (si el gancho promete "terminó en un billete", el final dice lo del
billete) y la ÚLTIMA es una pregunta corta al público (12 palabras como mucho, sobre esta historia) que
invite a comentar. Si ya está así, `responde` true y repetís las dos últimas frases igual. Si no,
`responde` false y reescribís SOLO las dos últimas frases: la anteúltima responde la pregunta del gancho y
la última es la pregunta corta al público, que termina en "?". Usás SOLO lo que dice el artículo (ni un nombre, número ni
fecha que no esté ahí), frases de 14 palabras como mucho, español rioplatense, mismo tono.
Respondé solo con el JSON pedido."""

SCHEMA_PAGO = {"type": "OBJECT",
               "properties": {"responde": {"type": "BOOLEAN"}, "anteultima": {"type": "STRING"},
                              "ultima": {"type": "STRING"}, "motivo": {"type": "STRING"}},
               "required": ["responde", "anteultima", "ultima", "motivo"]}


def final_que_paga(cliente, d: dict, e: Evento, fuente: str, corto: bool = False,
                   rango: tuple[int, int] | None = None, validar_extra=None, avisar=log.info) -> dict:
    """Segunda revisión (Santi, 2026-11-13: en La Pola el gancho prometía "terminó en un billete" y
    el final hablaba del Día de la Mujer): ¿el final responde la pregunta del gancho? Si no, se
    reescriben las dos últimas frases y se vuelve a validar todo; si lo nuevo no valida, queda el
    guion como estaba (nunca uno peor). Devuelve el guion (dict) a usar."""
    frases = [str((f or {}).get("texto") or "") for f in d.get("frases") or []]
    if len(frases) < 4:
        return d
    prompt = (f"Gancho: {frases[0]}\nPregunta que deja: {d.get('pregunta_gancho') or '(no dicha)'}\n\n"
              "Guion entero:\n" + "\n".join(f"{i + 1}. {f}" for i, f in enumerate(frases))
              # El artículo entero (hasta 20.000): en La Pola el billete estaba en "Homenajes",
              # después de los primeros 8.000 caracteres, y la revisión no lo veía.
              + f"\n\nTEXTO DEL ARTÍCULO (lo único que podés usar):\n{fuente[:20000]}")
    from .gemini import GeminiError

    errores: list[str] = []
    for _ in range(2):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        try:
            r = json.loads(cliente.json(SISTEMA_PAGO, prompt + extra, SCHEMA_PAGO, temperatura=0.3))
        except (GeminiError, ValueError) as err:
            avisar(f"  revisión del final: no respondió ({str(err)[:80]}); queda como estaba")
            return d
        if r.get("responde") is True:
            return d
        nuevo = json.loads(json.dumps(d))
        nuevo["frases"][-2]["texto"] = str(r.get("anteultima") or "").strip()
        nuevo["frases"][-1]["texto"] = str(r.get("ultima") or "").strip()
        nuevo["frase_pago"] = len(frases) - 1
        errores = validar_guion(nuevo, e.anio, fuente + "\n" + e.texto + f" {e.anio}", corto=corto, rango=rango)
        if validar_extra and not errores:
            errores = validar_extra(nuevo)
        if not errores:
            avisar(f"  revisión del final: reescrito ({str(r.get('motivo') or '')[:100]})")
            return nuevo
    avisar(f"  revisión del final: lo nuevo no valida ({'; '.join(errores)[:120]}); queda como estaba")
    return d


def escribir_guion(cliente, e: Evento, fuente: str, correccion: str = "", anterior: str = "",
                   reintentos: int = 3, hablado: bool = False, sistema: str | None = None,
                   validar_extra=None, contexto: str = "", corto: bool = False,
                   rango: tuple[int, int] | None = None, max_s: float = 0.0,
                   revisar_final: bool = True, respaldo: str = "") -> Guion:
    """Gemini (o Claude, en el video de Facebook) con el artículo, SIN fotos: el guion y qué mostrar
    en cada frase. Las fotos se buscan después para cada frase (`fotos_para_guion`). Reintenta con
    los errores de la validación. `sistema`/`validar_extra`/`contexto`: los del video de Facebook
    (el lugar en el título, la primera frase y los hashtags)."""
    prompt = (f"Hecho ({e.anio}): {e.texto}\n{contexto}\nTEXTO DEL ARTÍCULO (lo único que podés usar):\n"
              f"{fuente[:12000]}")
    if correccion:
        prompt += f"\n\nEl guion anterior no sirvió:\n{anterior}\nLo que hay que cambiar: {correccion}"
    from . import correcciones

    errores: list[str] = []
    d, puntuales = None, 0
    base = sistema or (SISTEMA_GUION_HABLADO if hablado else SISTEMA_GUION)   # efemerides.guion_hablado
    from . import aprendizaje      # lo que más retuvo en Facebook (Santi, 2026-11-18)

    base += aprendizaje.para_prompt("pequena_historia")
    # Corregir solo lo que falla (Santi, 2026-11-15): las frases que no validan, con el resto como contexto;
    # el guion entero de nuevo solo después de CORRECCIONES_MAX correcciones puntuales fallidas.
    correcciones.reiniciar()      # como mucho 4 pedidos de corrección por candidato (Santi, 2026-11-19)
    for _ in range(reintentos + 1 + correcciones.CORRECCIONES_MAX):
        try:
            if d is not None and errores and puntuales < correcciones.CORRECCIONES_MAX:
                puntuales += 1
                d = correcciones.corregir(cliente, base, prompt, d, errores, SCHEMA_GUION, "frases", "frase")
            else:
                extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
                puntuales = 0
                if errores:
                    correcciones.anotar()      # la reescritura entera también cuenta para el tope
                d = json.loads(cliente.json(base, prompt + extra, SCHEMA_GUION, temperatura=0.5))
        except correcciones.TopeCorrecciones as err:
            log.info("guion de %s: %s", e.anio, err)
            errores = errores or [str(err)]
            break
        # `respaldo`: el lugar de la historia, que validar_lugar EXIGE nombrar, cuenta como dato del artículo; si no,
        # el lugar que no figura en el artículo ("Nápoles" en el de Goycochea) se sacaba y se volvía a pedir hasta el
        # tope de correcciones (Santi, 2026-11-26).
        errores = validar_guion(d, e.anio, fuente + "\n" + e.texto + f" {e.anio}\n{respaldo}", corto=corto,
                                rango=rango)
        if validar_extra and not errores:
            errores = validar_extra(d)
        if not errores and revisar_final:
            d = final_que_paga(cliente, d, e, fuente, corto=corto, rango=rango, validar_extra=validar_extra)
        if not errores:
            return Guion(frases=[f["texto"].strip() for f in d["frases"]], fotos=[],
                         descartadas=[], titulo=d["titulo"].strip(),
                         descripcion=d["descripcion"].strip(), hashtags=list(d["hashtags"]),
                         tono=d.get("tono") if d.get("tono") in TONOS_GUION else "",
                         mostrar=[f["mostrar"].strip() for f in d["frases"]],
                         idea_clave=str(d["idea_clave"]).strip(),
                         presente=[bool(f.get("presente")) for f in d["frases"]],
                         objeto=[str(f.get("objeto") or "").strip() for f in d["frases"]],
                         central=[f.get("central") is not False for f in d["frases"]],
                         corto=corto, max_s=max_s,
                         pregunta_gancho=str(d.get("pregunta_gancho") or "").strip(),
                         accion=frases_de_accion(d["frases"]),
                         claves=claves_del_guion(d.get("claves"), [f["texto"] for f in d["frases"]]))
    raise NarrarError("El guion no pasó la validación: " + "; ".join(errores))


# ---- 3b. las fotos de cada frase (regla fija: ilustrar.py) ------------------------------------

SISTEMA_FOTOS = """Elegís las fotos de un video corto narrado. Te paso las frases del guion, qué
conviene mostrar en cada una, y fotos numeradas (la imagen k es la foto k).

Para CADA frase, MIRÁ las imágenes y ordená de mejor a peor hasta 3 fotos que muestren lo que dice
LA FRASE o el tema DIRECTO del hecho (no solo la búsqueda). Si dudás de una foto, NO la pongas. En
`seguro` confirmá que la primera muestra eso de verdad (no algo parecido ni del mismo país ni de la
misma época): si no estás seguro, false. Nada de capturas de pantalla de páginas web, redes sociales
o programas (una página de Facebook no es "el hecho"), salvo que la frase hable de esa página. Primero fijate en las de su búsqueda, pero podés elegir cualquier
foto de la lista. En `se_ve` decí en pocas palabras qué se ve de verdad en la foto que pusiste
primera: si lo que se ve no tiene que ver con la frase, no la elijas. Si ninguna muestra lo que
se dice, dejá la lista vacía: es mejor vacía que una foto que no tiene nada que ver (una postal,
una máquina de otro tema, un edificio cualquiera). Buscá variedad: si otra foto sirve igual, no
pongas primera la misma foto en frases distintas.

PERSONAS (regla fija de Santi, 2026-11-17): NUNCA fotos de políticos ni de actos de gobierno (presidentes,
funcionarios, inauguraciones, fotos oficiales), salvo que la historia sea de esa persona; NUNCA retratos de
personas que la historia no nombra (un señor mayor cualquiera, un presidente de otra época). Tampoco fotos
borrosas, ilegibles o recortes de diario que no se leen. Si una frase no tiene foto que muestre lo que
dice, dejala vacía: va una tarjeta de texto.

ÉPOCA Y LUGAR: te digo el año del hecho y, al lado de cada foto, cuándo se sacó (si se sabe). Para
una frase del pasado, elegí fotos DE ESA ÉPOCA y de ese lugar: un avión de 2008 no sirve para
contar un choque de 1940, aunque sea del mismo modelo. En `de_epoca` confirmá si la foto que
pusiste primera es de la época y el lugar de la frase (para las frases marcadas "habla de hoy",
una foto actual sirve y va true).

VIDEOS: algunas frases (las de acción) tienen además videos candidatos, V1, V2…, y de cada uno
ves 3 cuadros. Para esas frases, en `video` poné el número del video que muestra LO QUE DICE la
frase (0 si ninguno sirve: mejor la foto que un video que no tiene nada que ver) y en `momento`
cuál de sus 3 cuadros (1, 2 o 3) es el mejor lugar para cortar. Preferí la filmación de la época
(la marcada "de archivo"). En `video_de_epoca` confirmá que el video no es un anacronismo para la
frase: un cohete moderno no sirve para 1957; el cielo, el mar o el espacio pueden servir.
Nada de dibujos animados, animaciones ni ilustraciones (0), salvo que la frase hable justamente de
eso; tampoco videos con texto encima tapando la imagen, ni recreaciones hechas por computadora.

TIPO DE CADA FOTO (en `tipos`, una entrada por CADA foto de la lista, con su número): decí qué es:
"foto" (una fotografía o una pintura/grabado de algo real), "captura" (captura de pantalla de una
página o de un programa), "interfaz" (la pantalla de una app o de un celular), "documento" (una
hoja escrita, un diario, una carta, una placa con mucho texto), "planilla" (una tabla o grilla),
"grafico" (un gráfico de precios, barras o curvas), "diagrama", "mapa", "logo" u "otro". En
`otro_idioma` decí si se lee texto en un idioma que NO es castellano ni inglés (otro alfabeto, o
filipino, ruso, chino…). Una captura, una app, un documento o una planilla solo sirven si la frase
habla justo de eso. En `anacronismo` decí si en la foto se ve algo que NO existía en el año del
hecho (autos o ropa de hoy, celulares, carteles o edificios modernos, plástico, LED): true si se ve.

QUE NO CONTRADIGA: en `contradice` decí si la primera foto que pusiste muestra lo CONTRARIO de lo
que dice la frase: si la frase dice que algo sube, un gráfico que baja o una flecha para abajo la
contradice; si dice que ganó, una foto de la derrota. Si contradice, true.

`descartadas`: MIRÁ las fotos y descartá las que no sirven para nada: mapas, gráficos, diagramas,
banderas, escudos, firmas, logos, capturas de pantalla, retratos de alguien que NO protagoniza el
hecho, fotos de otro tema, y cualquier imagen violenta o con muertos o heridos. Nunca las pongas en
ninguna frase.

`impactantes`: de las fotos que SIRVEN (que no descartaste), las 3 más impactantes a la vista, la
mejor primero: la que haría frenar el dedo en el feed (un momento fuerte, una cara, algo raro o
enorme), del hecho o del lugar. La primera va al principio del video, con el gancho: tiene que ser
la MÁS LLAMATIVA, no la más "oficial" (una estatua o un monumento vistos de lejos son flojos). Si hay
una foto con una CARA HUMANA clara del protagonista real (un retrato, una pintura, una foto de él o
de ella), esa va primera; si no, la escena más fuerte.
Respondé solo con el JSON pedido."""

ORDEN_FOTOS = """REGLAS DE SANTI PARA ESTE VIDEO (le ganan a lo que diga más abajo):
- Frases marcadas CENTRAL (cuentan el hecho mismo, su lugar o su protagonista): primero una foto
  REAL de eso (si habla del pueblo inundado, ESE pueblo inundado). Si no hay, sirve una ESCENA
  ILUSTRATIVA que muestre la situación que dice la frase aunque no sea del hecho exacto (Santi,
  2026-11-14: para "ya presa, leía las cartas", un preso leyendo papeles en una celda): manos que
  escriben una carta, soldados marchando, una celda, una vela, una multitud. Nunca una que se
  confunda con lo central: nada de una cara en primer plano que parezca ser el protagonista real,
  ni otro lugar presentado como el del hecho, ni nada que no existía en esa época. Si la primera
  que ponés es una escena así, marcá `escena` true (ahí `de_epoca` puede ir false: lo que importa es
  que no se vea nada moderno, eso va en `anacronismo`; y `seguro` va true si la escena muestra la
  situación que dice la frase). Si no hay nada, dejá la lista vacía. Una frase central con una
  escena que sirve es MEJOR que dejarla vacía: vacía va una tarjeta con texto.
- Frases marcadas AL PASAR (nombran una cosa de pasada: un muro, Pokémon, un tren): sirve una foto
  genérica de esa cosa, de Commons o de stock, aunque no sea del hecho ni de la época. Si la frase
  dice "Pokémon", un Pikachu o unas cartas de Pokémon sirven: ahí `seguro` va true. `de_epoca` no
  importa en esas frases.
- En las dos, la imagen es LO QUE SE DICE en esa frase, no algo del mismo tema en general. Entre
  dos que sirven igual, preferí la del hecho o del lugar, después "foto del objeto" y por último
  "foto de stock del objeto".

"""

SCHEMA_FOTOS = {
    "type": "OBJECT",
    "properties": {
        "frases": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"se_ve": {"type": "STRING"},
                           "fotos": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                           "de_epoca": {"type": "BOOLEAN"}, "seguro": {"type": "BOOLEAN"},
                           "video": {"type": "INTEGER"}, "momento": {"type": "INTEGER"},
                           "video_de_epoca": {"type": "BOOLEAN"}, "contradice": {"type": "BOOLEAN"},
                           "escena": {"type": "BOOLEAN"}},
            "required": ["se_ve", "fotos", "de_epoca", "seguro", "contradice", "escena"]}},
        "descartadas": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "impactantes": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "tipos": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"foto": {"type": "INTEGER"},
                           "tipo": {"type": "STRING", "enum": ["foto", "captura", "interfaz", "documento",
                                                              "planilla", "grafico", "diagrama", "mapa",
                                                              "logo", "otro"]},
                           "otro_idioma": {"type": "BOOLEAN"}, "anacronismo": {"type": "BOOLEAN"}},
            "required": ["foto", "tipo", "otro_idioma", "anacronismo"]}},
    },
    "required": ["frases", "descartadas", "tipos"],
}

# Lo que NO es una foto del hecho (2026-10-21, la de bitcoin: una app con "Something went wrong", una
# planilla de frase semilla, un gráfico en picada y placas con texto en filipino). Cada tipo sirve solo
# para una frase que hable de eso.
_HABLA_DE_APP = re.compile(r"\bapp\b|aplicaci[oó]n|pantalla|programa|software|celular|billetera|"
                           r"wallet|interfaz|computadora|p[aá]gina|sitio|web|internet|red(es)? social", re.I)
_HABLA_DE_DOC = re.compile(r"documento|carta|acta|tratado|\bley\b|decreto|constituci[oó]n|manuscrito|"
                           r"peri[oó]dico|diario|libro|placa|planilla|tabla|white ?paper|art[ií]culo|"
                           r"firm[oó]|publica", re.I)
_HABLA_DE_GRAFICO = re.compile(r"gr[aá]fico|curva|cotiza|precio|vale|valor|estad[ií]stic|diagrama|"
                               r"esquema|sub(e|i[oó])|baj(a|[oó])|r[eé]cord|m[aá]ximo|m[ií]nimo|super[oó]|d[oó]lar", re.I)
_HABLA_DE_MAPA = re.compile(r"\bmapa|territorio|frontera|ruta|recorrido", re.I)
PERMITE_TIPO = {"captura": _HABLA_DE_APP, "interfaz": _HABLA_DE_APP, "documento": _HABLA_DE_DOC,
                "planilla": _HABLA_DE_DOC, "grafico": _HABLA_DE_GRAFICO, "diagrama": _HABLA_DE_GRAFICO,
                "mapa": _HABLA_DE_MAPA, "logo": _HABLA_DE_APP}
UMBRAL_TEXTO_OCR = 0.07    # calibrado con las 40 de bitcoin: app 8,5 %, documentos 13-15 %, placas
                           # 8-11 %, diagrama 8,4 %; las fotos de verdad, ≤ 6 % (un congreso con carteles)


def fraccion_texto(ruta: Path) -> float:
    """Qué parte de la imagen es texto legible (cajas de palabras de tesseract). 0 si no hay OCR."""
    try:
        import pytesseract
        from PIL import Image

        from .pantalla import find_tesseract

        pytesseract.pytesseract.tesseract_cmd = find_tesseract()
        im = Image.open(ruta).convert("L")
        im.thumbnail((1000, 1000))
        d = pytesseract.image_to_data(im, lang="eng", output_type=pytesseract.Output.DICT, config="--psm 11")
    except Exception as e:      # sin tesseract (o una imagen rota) no se frena nada: queda Gemini
        log.debug("OCR de %s: %s", ruta, e)
        return 0.0
    area = sum(w * h for t, c, w, h in zip(d["text"], d["conf"], d["width"], d["height"])
               if len((t or "").strip()) >= 2 and float(c) >= 60 and sum(ch.isalnum() for ch in t) >= 2)
    return area / float(im.width * im.height or 1)


# Segunda búsqueda (2026-11-11): en una frase central valen el documento o el dibujo del hecho mismo
# (los planos de la patente del refrigerador de Einstein salían como "diagrama").
TIPOS_DEL_HECHO = ("documento", "diagrama", "planilla")


def sirve_para(frase: str, tipo: str, mucho_texto: bool, otro_idioma: bool) -> bool:
    """¿Esta imagen puede ir en esta frase? Nunca con texto en otro idioma; un tipo que no es foto
    (o con mucho texto) solo si la frase habla justo de eso."""
    if otro_idioma:
        return False
    if tipo in PERMITE_TIPO and not PERMITE_TIPO[tipo].search(frase):
        return False
    if mucho_texto and not (_HABLA_DE_DOC.search(frase) or _HABLA_DE_APP.search(frase)):
        return False
    return True


def tipos_de(d: dict, n_pool: int) -> dict[int, tuple[str, bool]]:
    """{foto (desde 0): (tipo, otro_idioma)} de la respuesta de Gemini."""
    out = {}
    for t in (d.get("tipos") or []) if isinstance(d, dict) else []:
        k = (t or {}).get("foto")
        if isinstance(k, int) and 1 <= k <= n_pool:
            out[k - 1] = (str(t.get("tipo") or "foto"), bool(t.get("otro_idioma")))
    return out

ANIO_MODERNO = 2000        # desde acá, primero fotos de stock (Pexels/Unsplash) antes que Commons
FOTOS_STOCK_MAX = 2        # de stock, por frase, en los hechos modernos
FOTOS_ARTICULO_MAX = 8     # del artículo del hecho: son candidatas para todas las frases
TOPE_FOTOS_S = 600         # búsqueda de fotos (y videos) de UN hecho; vencido, sigue con lo que hay
FOTOS_BUSQUEDA_MAX = 4     # de Commons, por frase
POOL_MAX = 40              # las que ve Gemini en la llamada (cada una ~250 tokens)
# Orden nuevo de las fotos (efemerides.imagen_frase, 2026-11-10): por frase, hasta 2 del hecho o el
# lugar, 1 del objeto en Commons y 1 del objeto en Pexels. Gemini ve hasta POOL_MAX_ORDEN.
FOTOS_HECHO_FRASE = 3          # frase central: solo del hecho o del lugar
FOTOS_HECHO_AL_PASAR = 1       # frase que nombra algo al pasar: 1 del hecho, 2 del objeto, 2 de Pexels
FOTOS_OBJETO_FRASE = 2
FOTOS_PEXELS_FRASE = 2
POOL_MAX_ORDEN = 56


def _foto_de(h: dict, busqueda: str) -> "Foto":
    """Una foto de las otras fuentes (fuentes_fotos) como Foto."""
    # la fuente la pone el despachador (Fuentes.buscar); una fuente llamada directo (Europeana en la segunda
    # búsqueda) no la trae (2026-11-15: KeyError en la historia del banco)
    return Foto(archivo=h["archivo"], url=h["url"], ancho=h["ancho"], alto=h["alto"],
                licencia=h["licencia"], autor=h.get("autor") or "autor desconocido",
                epigrafe=(h.get("epigrafe") or "")[:160], pagina=h.get("pagina") or h["url"],
                articulo=f"{h.get('fuente') or 'otra fuente'}: {busqueda}", anio=h.get("anio"))


def es_central(g: "Guion", i: int) -> bool:
    """La frase cuenta el hecho mismo (foto real obligatoria). Sin el dato (guiones viejos), sí."""
    return g.central[i] if i < len(g.central) else True


def sin_epoca(g: "Guion") -> list[bool]:
    """Por frase, si la regla de época NO aplica: las que hablan de hoy y, con imagen = lo que se
    dice, las que nombran algo al pasar (Santi, 2026-11-10: "un Pikachu sirve")."""
    if g.segunda_busqueda:
        return [True] * len(g.frases)
    return [(i < len(g.presente) and g.presente[i]) or (g.imagen_frase and not es_central(g, i))
            for i in range(len(g.frases))]


def es_stock(f: "Foto") -> bool:
    return f.articulo.startswith(("pexels:", "unsplash:"))


def rankings_de(d: dict, candidatas: list[list[int]],
                presente: list[bool] | None = None) -> tuple[list[list[int]], set[int]]:
    """La respuesta de Gemini → (ranking de cada frase, desde 0; descartadas). Lo que no es una
    candidata de esa frase o está descartado se ignora (flash-lite a veces se sale de la lista).
    Si Gemini dice que su primera foto NO es de la época (`de_epoca: false`) en una frase del
    pasado, esa foto sale del ranking de esa frase."""
    if not isinstance(d, dict) or not isinstance(d.get("frases"), list) \
            or len(d["frases"]) != len(candidatas):
        raise ValueError(f"tienen que ser exactamente {len(candidatas)} frases")
    descartadas = {x - 1 for x in d.get("descartadas") or [] if isinstance(x, int)}
    rankings = []
    for i, (f, cands) in enumerate(zip(d["frases"], candidatas)):
        ok = [x - 1 for x in (f or {}).get("fotos") or [] if isinstance(x, int)]
        ok = [x for x in dict.fromkeys(ok) if x in cands and x not in descartadas]
        hoy = bool(presente and i < len(presente) and presente[i])
        # Una escena ilustrativa (2026-11-14) no es "de la época" pero puede ir: lo que no puede es
        # tener algo moderno a la vista, y eso lo filtra `anacronismo` (stock).
        if ok and (f or {}).get("de_epoca") is False and not hoy and not (f or {}).get("escena"):
            ok = ok[1:]
        # Relevancia dura (2026-10-02: en la de 4chan entró una página militar de Facebook): si
        # Gemini no está seguro de que la primera muestre lo que dice la frase, sale.
        if ok and (f or {}).get("seguro") is False and not (f or {}).get("escena"):
            ok = ok[1:]
        # Que no contradiga (2026-10-21: "el precio subió muchísimo" con un gráfico en picada).
        if ok and (f or {}).get("contradice") is True:
            ok = ok[1:]
        rankings.append(ok[:ilustrar.RANKING_MAX])
    return rankings, descartadas


# ---- Primer filtro con Haiku (Santi, 2026-11-15: "el 14/11 fueron US$ 2,57, casi la mitad en elegir
# fotos"). Cada pedido de Sonnet veía ~50 fotos y escribía un `tipo` por cada una (2.000-10.000 tokens
# de salida: lo caro). Ahora Haiku describe cada foto UNA vez (guardado por foto: la misma foto no se
# vuelve a pagar) y, solo con texto, ordena las candidatas de cada frase; Sonnet mira las mejores
# PREFILTRO_POR_FRASE de cada una (la frase 1, una más: la del gancho) y decide como siempre.
PREFILTRO_POR_FRASE = 3      # 2026-11-18 (capa 4): 2 o 3 finalistas por frase, las únicas que se miran con imagen
VIDEOS_POR_FRASE = 3          # (2026-11-15: 3) con el estilo nuevo eran hasta 4 videos × 3 cuadros por frase: lo más caro
PREFILTRO_MIN = 0             # 2026-11-18: siempre (la imagen la miran solo las finalistas)
CACHE_DESCRIPCIONES = DATA_DIR / "cache_claude" / "fotos"

SISTEMA_DESCRIBIR = """Describís fotos para un primer filtro. La imagen k es la foto k. Para CADA foto:
`se_ve`: qué se ve de verdad, concreto y corto (máx. 15 palabras, en castellano; ej.: "tren de vapor
cruzando un puente de hierro, blanco y negro, unas 1900"); `tipo`: "foto" (fotografía, pintura o
grabado de algo real), "captura", "interfaz", "documento", "planilla", "grafico", "diagrama", "mapa",
"logo" u "otro"; `otro_idioma`: si se lee texto en un idioma que no es castellano ni inglés; `dura`:
si muestra muertos, heridos o violencia real; `politico`: si muestra a un político, un funcionario o un
acto de gobierno (presidentes, ministros, legisladores, una inauguración oficial, un acto de campaña,
una foto oficial), aunque no sepas quién es; `retrato`: si el tema principal es una persona concreta
(o dos o tres) posando o en primer plano (retrato, foto oficial, foto de prensa de alguien), no una
multitud, un equipo entero ni gente haciendo algo de fondo; `quien`: los nombres de las personas
identificables, por el epígrafe o el nombre del archivo que te paso, o porque es alguien muy conocido
("" si no se sabe). Respondé solo con el JSON pedido."""

SCHEMA_DESCRIBIR = {
    "type": "OBJECT",
    "properties": {"fotos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"foto": {"type": "INTEGER"}, "se_ve": {"type": "STRING"},
                       "tipo": {"type": "STRING", "enum": ["foto", "captura", "interfaz", "documento",
                                                          "planilla", "grafico", "diagrama", "mapa",
                                                          "logo", "otro"]},
                       "otro_idioma": {"type": "BOOLEAN"}, "dura": {"type": "BOOLEAN"},
                       "politico": {"type": "BOOLEAN"}, "retrato": {"type": "BOOLEAN"},
                       "quien": {"type": "STRING"}},
        "required": ["foto", "se_ve", "tipo", "otro_idioma", "dura", "politico", "retrato", "quien"]}}},
    "required": ["fotos"],
}

SISTEMA_PREFILTRO = """Primer filtro de las fotos de un video corto narrado, SOLO CON EL TEXTO (no ves las imágenes).
Te paso las frases del guion (qué conviene mostrar y los números de sus candidatas) y, de cada foto, cuándo se sacó, el
nombre del archivo, su descripción y de qué artículo viene. Para CADA frase, ordená de mejor a peor hasta {k} de SUS
candidatas que muestren lo que dice LA FRASE (no solo el tema en general).
DESCARTÁ (no las pongas) las que por su nombre o descripción muestran OTRA persona, OTRO lugar u OTRO año que los de la
frase o del hecho (un presidente, un retrato de alguien que la frase no nombra, una central nuclear en una historia de
fútbol, una ciudad de otro país, una foto de 2024 en una frase de 1921), y las de políticos o actos de gobierno (salvo
que la historia sea de esa persona). Las marcadas ARTÍCULO GENERAL (de un país o una ciudad entera) solo sirven como
paisaje o vista de ESE lugar, para una frase que hable del lugar: nunca para una persona, un club o un hecho. Preferí: la foto del hecho o del lugar; para una frase del pasado,
fotos de esa época; para una frase CENTRAL, una foto real del hecho o, si no hay, una escena que ilustre
la situación; para una AL PASAR, una foto clara de la cosa que se nombra. Nada de mapas, logos,
capturas, gráficos ni documentos salvo que la frase hable de eso. Si dudás entre dos, poné las dos:
después alguien mira las imágenes y decide. Si una frase tiene VIDEOS candidatos (V1, V2…), en `videos`
ordená de mejor a peor hasta {v} que muestren lo que dice la frase (preferí la filmación de archivo de la
época; vacío si ninguno sirve). Respondé solo con el JSON pedido."""

SCHEMA_PREFILTRO = {
    "type": "OBJECT",
    "properties": {"frases": {"type": "ARRAY", "items": {
        "type": "OBJECT", "properties": {"fotos": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                                        "videos": {"type": "ARRAY", "items": {"type": "INTEGER"}}},
        "required": ["fotos", "videos"]}}},
    "required": ["frases"],
}


def _huella_jpeg(img: bytes) -> str:
    return hashlib.sha256(img).hexdigest()[:32]


DESCRIPCION_V = 2      # 2026-11-17: con `politico`, `retrato` y `quien` (las de antes se vuelven a describir)


def describir_fotos(haiku, imagenes: list[bytes], carpeta: Path | None = None,
                    avisar=log.info, textos: list[str] | None = None) -> list[dict]:
    """Una descripción por imagen ({se_ve, tipo, otro_idioma, dura, politico, retrato, quien}). Las ya descriptas se
    leen de `carpeta` (por huella del JPEG): solo las nuevas van a Haiku, en UN pedido. `textos`: el epígrafe o el
    nombre del archivo de cada una (para saber quién es)."""
    carpeta = CACHE_DESCRIPCIONES if carpeta is None else carpeta
    out: list = []
    faltan = []
    for k, img in enumerate(imagenes):
        f = carpeta / f"{_huella_jpeg(img)}.json"
        try:
            x = json.loads(f.read_text(encoding="utf-8"))
            if x.get("v") != DESCRIPCION_V:
                raise ValueError("descripción vieja")
            out.append(x)
        except (OSError, ValueError):
            out.append(None)
            faltan.append(k)
    if faltan:
        lista = "\n".join(f"foto {j}: {(textos[k] if textos and k < len(textos) else '')[:140]}"
                          for j, k in enumerate(faltan, 1))
        d = json.loads(haiku.json(SISTEMA_DESCRIBIR,
                                  f"Son {len(faltan)} fotos, numeradas de 1 a {len(faltan)}. Epígrafe o archivo de "
                                  f"cada una:\n{lista}",
                                  SCHEMA_DESCRIBIR, imagenes=[imagenes[k] for k in faltan]))
        por_num = {x.get("foto"): x for x in d.get("fotos") or [] if isinstance(x, dict)}
        for j, k in enumerate(faltan, 1):
            x = por_num.get(j)
            if not x:
                continue
            x = {c: x.get(c) for c in ("se_ve", "tipo", "otro_idioma", "dura", "politico", "retrato", "quien")}
            x["v"] = DESCRIPCION_V
            out[k] = x
            try:
                carpeta.mkdir(parents=True, exist_ok=True)
                (carpeta / f"{_huella_jpeg(imagenes[k])}.json").write_text(
                    json.dumps(x, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
    avisar(f"    primer filtro: {len(imagenes) - len(faltan)} fotos ya descriptas, {len(faltan)} nuevas")
    return [x or {} for x in out]


def _sin_tildes(t: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _palabras_nombre(texto: str) -> set[str]:
    return set(re.findall(r"[a-zñ]{4,}", _sin_tildes(texto.lower())))


def motivo_persona(desc: dict, historia: str) -> str | None:
    """Regla fija (Santi, 2026-11-17, Colón con Cristina Kirchner en Atucha y un retrato de Illia): nunca fotos de
    políticos ni de actos de gobierno, ni retratos de personas que la historia no nombra, salvo que la historia sea de
    esa persona (su nombre está en el guion). `desc`: la de `describir_fotos`."""
    quien = str(desc.get("quien") or "")
    nombrada = bool(_palabras_nombre(quien) & _palabras_nombre(historia)) if quien else False
    if desc.get("politico") and not nombrada:
        return f"político o acto de gobierno ({quien or 'sin nombre'}) que la historia no nombra"
    if desc.get("retrato") and not nombrada:
        return f"retrato de alguien que la historia no nombra ({quien or 'sin nombre'})"
    return None


def prefiltrar_fotos(haiku, lineas: list[str], pool: list[Foto], imagenes: list[bytes],
                     candidatas: list[list[int]], propias: list[list[int]] | None,
                     anio: int | None, avisar=log.info, carpeta: Path | None = None,
                     videos: dict | None = None, historia: str = "",
                     fuera: set | None = None) -> set[int]:
    """Las fotos (índices del pool) que va a mirar Sonnet: por frase, las mejores PREFILTRO_POR_FRASE de
    sus candidatas según Haiku (la frase 1, una más), completando con las de su búsqueda si Haiku
    devuelve menos. Lo que Haiku ve como duro (muertos, heridos) no pasa. `videos` ({frase: [Video]}) se
    recorta EN EL LUGAR a los VIDEOS_POR_FRASE mejores de cada frase (Haiku mira el cuadro del medio)."""
    videos = {i: vs for i, vs in (videos or {}).items() if len(vs) > VIDEOS_POR_FRASE}
    medios = [(i, k, v) for i, vs in sorted(videos.items()) for k, v in enumerate(vs) if v.frames]
    # Capa 3 (Santi, 2026-11-18): Haiku lee SOLO el título y la descripción de cada foto (sin la imagen).
    duras: set[int] = set()
    fotos = "\n".join(f"foto {k} ({f.anio or 'sin fecha'}): {f.archivo.replace('File:', '').replace('_', ' ')[:90]} — "
                      f"{f.epigrafe[:140]} — de «{f.articulo[:60]}»"
                      + (" [ARTÍCULO GENERAL: solo paisaje de ese lugar]" if getattr(f, "general", False) else "")
                      for k, f in enumerate(pool, 1))
    vids = "\n".join(f"frase {i + 1}, V{k + 1}: {v.titulo[:80]} ({'de archivo' if v.de_archivo else 'stock'}, "
                     f"{v.etiqueta()})" for (i, k, v) in medios)
    prompt = ((f"EL HECHO ES DE {anio}.\n\n" if anio else "") + "FRASES:\n" + "\n".join(lineas)
              + "\n\nFOTOS:\n" + fotos + (f"\n\nVIDEOS:\n{vids}" if vids else ""))
    d = json.loads(haiku.json(SISTEMA_PREFILTRO.replace("{k}", str(PREFILTRO_POR_FRASE))
                              .replace("{v}", str(VIDEOS_POR_FRASE)), prompt, SCHEMA_PREFILTRO))
    frases = d.get("frases") or []
    for i, vs in videos.items():
        dichos = ((frases[i] or {}).get("videos") if i < len(frases) else None) or []
        orden = [x - 1 for x in dichos if isinstance(x, int) and 1 <= x <= len(vs)]
        orden += [k for k in range(len(vs)) if k not in orden]
        vs[:] = [vs[k] for k in orden[:VIDEOS_POR_FRASE]]
    keep: set[int] = set()
    for i, cands in enumerate(candidatas):
        tope = PREFILTRO_POR_FRASE + (1 if i == 0 else 0)
        validas = set(cands) - duras
        dichas = ((frases[i] or {}).get("fotos") if i < len(frases) else None) or []
        elegidas = [x - 1 for x in dichas if isinstance(x, int) and x - 1 in validas]
        suyas = propias[i] if propias and i < len(propias) else []
        # Capa 3 (Santi, 2026-11-18): lo que Haiku descartó por el texto NO vuelve por relleno. Solo si no respondió
        # nada para esta frase, las de su propia búsqueda (nunca las de un artículo general).
        orden = elegidas if dichas else [x for x in suyas + cands if x in validas
                                         and not getattr(pool[x], "general", False)]
        vistas: list[int] = []
        for x in orden:
            if x not in vistas:
                vistas.append(x)
            if len(vistas) >= tope:
                break
        keep.update(vistas)
    # Capa 4: solo las finalistas se miran con imagen (Haiku, en miniatura): personas, dureza y las de un artículo
    # general que no son un paisaje.
    finalistas = sorted(keep)
    if finalistas:
        desc = describir_fotos(haiku, [imagenes[k] for k in finalistas], carpeta, avisar,
                               textos=[f"{pool[k].archivo} — {pool[k].epigrafe}" for k in finalistas])
        for k, x in zip(finalistas, desc):
            malo = ("muestra muertos o heridos" if x.get("dura") else motivo_persona(x, historia))
            if not malo and getattr(pool[k], "general", False) and (x.get("retrato") or x.get("politico")
                                                                    or x.get("tipo") not in (None, "foto")):
                malo = "de un artículo general y no es un paisaje del lugar"
            if malo:
                keep.discard(k)
                duras.add(k)
                avisar(f"    foto {k + 1} afuera: {malo}")
    if fuera is not None:
        fuera.update(duras)
    avisar(f"    primer filtro (Haiku, por texto): {len(keep)} finalistas de {len(pool)} fotos"
           + (f" y {VIDEOS_POR_FRASE} videos por frase" if videos else ""))
    return keep


def elegir_fotos(cliente, g: Guion, pool: list[Foto], candidatas: list[list[int]],
                 propias: list[list[int]] | None = None, reintentos: int = 1,
                 avisar=log.info, anio: int | None = None, videos: dict | None = None,
                 elegidos: dict | None = None, ocr: dict[int, float] | None = None,
                 extra: dict | None = None, elector=None,
                 prefiltrado: bool = False) -> tuple[list[list[int]], set[int]]:
    """UNA llamada: el modelo ve todas las fotos y ordena las que sirven para cada frase.
    `elector`: Claude (Sonnet) para elegir y verificar (Santi, 2026-11-10: "así no dependemos de la
    cuota gratis"); si falla, Gemini (`cliente`) de respaldo.
    `propias`: las que salieron de la búsqueda de esa frase (se le muestran primero). `anio`: el
    del hecho; junto con el año de cada foto, para que confirme la época (`de_epoca`).
    `videos`: {frase: [Video con sus cuadros]} de las frases de acción; en la MISMA llamada Gemini
    elige cuál y en qué momento, y lo elegido queda en `elegidos` ({frase: Video})."""
    lineas = []
    for i, (frase, cands) in enumerate(zip(g.frases, candidatas), 1):
        mostrar = g.mostrar[i - 1] if i - 1 < len(g.mostrar) else ""
        suyas = propias[i - 1] if propias else []
        hoy = " (habla de hoy)" if i - 1 < len(g.presente) and g.presente[i - 1] else ""
        if g.imagen_frase:
            if es_central(g, i - 1) and g.segunda_busqueda:
                hoy += (" (CENTRAL, segunda búsqueda: sirve una foto REAL del protagonista, del lugar,"
                        " de un monumento o del documento o dibujo del hecho, como la patente o el acta,"
                        " aunque sea de otra época; nunca una foto genérica o de stock)")
            elif es_central(g, i - 1):
                hoy += " (CENTRAL: tiene que ser una foto real del hecho o del lugar)"
            else:
                obj = g.objeto[i - 1] if i - 1 < len(g.objeto) else ""
                hoy += f" (AL PASAR: sirve una foto genérica de «{obj or mostrar}», de cualquier época)"
        lineas.append(f"frase {i}{hoy}: {frase}\n  mostrar: {mostrar}\n  candidatas: "
                      + ", ".join(str(c + 1) for c in cands)
                      + (f"\n  de su búsqueda: {', '.join(str(c + 1) for c in suyas)}" if suyas else ""))
    orden = g.imagen_frase
    haiku = getattr(elector, "prefiltro", None) if elector is not None else None
    if haiku is not None and not prefiltrado and len(pool) >= PREFILTRO_MIN:
        try:
            fuera: set = set()
            keep = prefiltrar_fotos(haiku, lineas, pool, [_jpeg_chico(Path(f.ruta), 384) for f in pool],
                                    candidatas, propias, anio, avisar, videos=videos,
                                    historia=" ".join([g.titulo] + list(g.frases)), fuera=fuera)
        except Exception as e:    # el filtro solo ahorra: si falla, Sonnet mira todas, como antes
            avisar(f"    primer filtro: falló ({str(e)[:80]}), Sonnet mira todas")
            keep = None
        if keep and len(keep) < len(pool):
            idx = sorted(keep)
            nuevo = {v: k for k, v in enumerate(idx)}

            def sub(listas):
                return [[nuevo[c] for c in l if c in nuevo] for l in listas]

            sub_extra = {} if extra is not None else None
            rk, malas = elegir_fotos(cliente, g, [pool[i] for i in idx], sub(candidatas),
                                     sub(propias) if propias else None, reintentos, avisar, anio, videos,
                                     elegidos, {nuevo[k]: v for k, v in (ocr or {}).items() if k in nuevo},
                                     sub_extra, elector=elector, prefiltrado=True)
            if extra is not None:
                extra.update({k: v for k, v in sub_extra.items() if k != "tipos"})
                if "tipos" in sub_extra:
                    extra["tipos"] = {idx[k]: v for k, v in sub_extra["tipos"].items()}
            return [[idx[x] for x in r] for r in rk], {idx[x] for x in malas} | fuera

    def origen(f: Foto) -> str:
        if not orden:
            return ""
        if es_stock(f):
            return ", foto de stock del objeto"
        if f.articulo.startswith("Commons (objeto)"):
            return ", foto del objeto"
        return ", del hecho o del lugar"

    epigrafes = "\n".join(f"foto {k} ({f.anio or 'sin fecha'}{origen(f)}): {f.epigrafe[:120]}"
                          for k, f in enumerate(pool, 1))
    prompt = ((f"EL HECHO ES DE {anio}.\n\n" if anio else "") + (ORDEN_FOTOS if orden else "")
              + "FRASES:\n" + "\n".join(lineas)
              + "\n\nFOTOS (entre paréntesis, cuándo se sacó):\n" + epigrafes)
    imagenes = [_jpeg_chico(Path(f.ruta), 384) for f in pool]
    videos = {i: vs for i, vs in (videos or {}).items() if vs}
    if videos:
        partes = ["\n\nVIDEOS (después de las fotos vienen sus cuadros, 3 por video, en este orden):"]
        for i, vs in sorted(videos.items()):
            for k, v in enumerate(vs, 1):
                tipo = "de archivo" if v.de_archivo else "stock, sin fecha" if v.anio is None else "stock"
                partes.append(f"frase {i + 1}, V{k}: {v.titulo[:90]} ({tipo}, {v.etiqueta()}, "
                              f"{v.duracion:.0f} s) — imágenes {len(imagenes) + 1} a "
                              f"{len(imagenes) + len(v.frames)}")
                imagenes += [_jpeg_chico(Path(fr), 384) for fr in v.frames]
        prompt += "\n".join(partes)
    # SOLO el modelo principal (2026-10-21: el de respaldo eligió una app con error, una planilla y
    # un gráfico en picada). Si el principal no está, el de respaldo, pero la hoja lo avisa.
    from .gemini import GeminiError

    principal = getattr(cliente, "modelo", None)
    respaldo = getattr(cliente, "modelo_fallback", None)

    def pedir(texto: str) -> str:
        if elector is not None and len(imagenes) <= 100:
            try:
                return elector.json(SISTEMA_FOTOS, texto, SCHEMA_FOTOS, imagenes=imagenes)
            except GeminiError as e:     # ClaudeError hereda de GeminiError
                avisar(f"    fotos: Claude no respondió ({str(e)[:80]}): uso Gemini")
        if not principal:
            return cliente.json(SISTEMA_FOTOS, texto, SCHEMA_FOTOS, temperatura=0.2, imagenes=imagenes)
        try:
            return cliente.json(SISTEMA_FOTOS, texto, SCHEMA_FOTOS, temperatura=0.2, imagenes=imagenes,
                                modelo=principal)
        except GeminiError as e:
            if not respaldo or respaldo == principal:
                raise
            avisar(f"    fotos: el modelo principal no respondió ({str(e)[:80]}): uso el de respaldo")
            if extra is not None:
                extra["respaldo"] = True
            return cliente.json(SISTEMA_FOTOS, texto, SCHEMA_FOTOS, temperatura=0.2, imagenes=imagenes,
                                modelo=respaldo)

    error = ""
    ocr = ocr or {}
    for _ in range(reintentos + 1):
        texto_error = f"\n\nTu respuesta anterior no servía: {error}" if error else ""
        d = json.loads(pedir(prompt + texto_error))
        try:
            rankings, malas = rankings_de(d, candidatas, sin_epoca(g))
        except ValueError as e:
            error = str(e)
            continue
        # Lo que no es una foto del hecho, con texto en otro idioma o con mucho texto: solo en la
        # frase que habla justo de eso, y nunca de reserva para otras.
        tipos = tipos_de(d, len(pool))
        no_aptas = set()
        for k in range(len(pool)):
            tipo, idioma = tipos.get(k, ("foto", False))
            mucho = ocr.get(k, 0.0) > UMBRAL_TEXTO_OCR
            if tipo in PERMITE_TIPO or idioma or mucho:
                no_aptas.add(k)
        for i, rk in enumerate(rankings):
            frase = f"{g.frases[i]} {g.mostrar[i] if i < len(g.mostrar) else ''}"
            antes = list(rk)
            doc_ok = g.segunda_busqueda and es_central(g, i)
            rankings[i] = [x for x in rk if sirve_para(frase, tipos.get(x, ("foto", False))[0],
                                                     ocr.get(x, 0.0) > UMBRAL_TEXTO_OCR,
                                                     tipos.get(x, ("foto", False))[1])
                           or (doc_ok and tipos.get(x, ("foto", False))[0] in TIPOS_DEL_HECHO
                               and not tipos.get(x, ("foto", False))[1])]
            for x in antes:
                if x not in rankings[i]:
                    t, idi = tipos.get(x, ("foto", False))
                    avisar(f"    frase {i + 1}: foto {x + 1} afuera ({t}"
                           + (", texto en otro idioma" if idi else "")
                           + (f", {ocr.get(x, 0) * 100:.0f} % texto" if ocr.get(x, 0) > UMBRAL_TEXTO_OCR else "") + ")")
        if orden:
            # Pexels (2026-11-10): en una frase del pasado, solo si Gemini confirma que no se ve
            # nada fuera de época.
            anac = {t.get("foto") - 1: t.get("anacronismo") for t in (d.get("tipos") or [])
                    if isinstance(t, dict) and isinstance(t.get("foto"), int)}
            libres = sin_epoca(g)
            for i, rk in enumerate(rankings):
                if i < len(libres) and libres[i]:
                    continue
                for x in [x for x in rk if es_stock(pool[x]) and anac.get(x) is not False]:
                    rk.remove(x)
                    avisar(f"    frase {i + 1}: foto {x + 1} afuera (stock con algo fuera de época)")
        usadas = {x for r in rankings for x in r}
        malas |= {x for x in no_aptas if x not in usadas}
        # La primera foto del video = la más impactante (Santi, 2026-11-12): va con el gancho, si es
        # una candidata de la frase 1 (época, capturas y "solo del hecho" ya filtrados) y sirve.
        if rankings and candidatas:
            imp = [x - 1 for x in d.get("impactantes") or [] if isinstance(x, int)]
            x = next((x for x in imp if x in candidatas[0] and x in usadas and x not in malas
                      and x not in no_aptas), None)
            if x is not None and (not rankings[0] or rankings[0][0] != x):
                rankings[0] = [x] + [y for y in rankings[0] if y != x]
                avisar(f"    frase 1: foto {x + 1} primero (la más impactante)")
        if extra is not None:
            extra["tipos"] = tipos
        # Con videos, después de las fotos van sus cuadros: Gemini a veces "descarta" esos
        # números, que no son fotos (en la muestra del Sputnik tiró un IndexError).
        malas = {x for x in malas if 0 <= x < len(pool)}
        for i, (f, rk) in enumerate(zip(d["frases"], rankings), 1):   # para juzgar la elección
            epoca = "" if (f or {}).get("de_epoca") is not False else " (NO es de la época)"
            avisar(f"    frase {i}: {[x + 1 for x in rk]} — se ve: "
                   f"{str((f or {}).get('se_ve'))[:80]}{epoca}")
        if elegidos is not None:
            elegidos.update(video_elegido(d["frases"], videos, sin_epoca(g), avisar))
        return rankings, malas
    raise NarrarError(f"Gemini no eligió bien las fotos: {error}")


def video_elegido(frases: list, videos: dict, presente: list[bool], avisar=log.info) -> dict:
    """{frase: Video} de la respuesta: el que eligió Gemini, cortado en el cuadro que dijo. Afuera
    si dice que es un anacronismo en una frase del pasado, o si el número no existe."""
    out, usados = {}, {}     # usados: {url: momentos ya tomados por otra frase}
    for i, vs in sorted(videos.items()):
        f = frases[i] if i < len(frases) else {}
        k, m = (f or {}).get("video"), (f or {}).get("momento")
        if not isinstance(k, int) or not 1 <= k <= len(vs):
            avisar(f"    frase {i + 1}: ningún video sirve, queda la foto")
            continue
        hoy = i < len(presente) and presente[i]
        if (f or {}).get("video_de_epoca") is False and not hoy:
            avisar(f"    frase {i + 1}: el video V{k} es de otra época, queda la foto")
            continue
        v = Video.de_dict(vs[k - 1].a_dict())   # una copia: la lista de candidatos no cambia
        cuadro = (m - 1) if isinstance(m, int) and 1 <= m <= len(v.momentos) else len(v.momentos) // 2
        # El mismo video en dos frases: la segunda, en otro momento (en la muestra del Sputnik las
        # frases 5 y 6 eligieron el mismo noticiero en el mismo segundo). Sin momento libre, foto.
        tomados = usados.setdefault(v.url, set())
        if cuadro < len(v.momentos) and v.momentos[cuadro] in tomados:
            libres = [c for c, t in enumerate(v.momentos) if t not in tomados]
            if not libres:
                avisar(f"    frase {i + 1}: el video V{k} ya se usa entero en otra frase, queda la foto")
                continue
            cuadro = libres[0]
        v.momento = v.momentos[cuadro] if v.momentos else 0.0
        tomados.add(v.momento)
        v.frames = [v.frames[cuadro]] if v.frames else []
        out[i] = v
        avisar(f"    frase {i + 1}: 🎬 video V{k} ({v.etiqueta()}) en {v.momento:.0f} s")
    return out


def buscar_videos(g: Guion, anio: int, carpeta: Path, buscador=None, avisar=log.info,
                  frases: list[int] | None = None, tema: str = "") -> dict:
    """{frase: [Video con 3 cuadros]} para las frases de acción (o las pedidas). `tema`: el
    artículo del hecho ("Sputnik 1"), la búsqueda de último recurso."""
    from . import videos_libres as vl

    buscador = buscador or vl.Buscador()
    out = {}
    for i in (frases_video(g) if frases is None else frases):
        if i >= len(g.mostrar):
            continue
        hoy = i < len(g.presente) and g.presente[i]
        vs = buscador.candidatos(g.mostrar[i], anio, hoy, avisar, tema=tema)[:4]
        listos = []
        for k, v in enumerate(vs):
            try:
                listos.append(vl.sacar_frames(v, carpeta / "videos", f"f{i:02d}_v{k}"))
            except (OSError, subprocess.SubprocessError) as err:   # un video nunca tumba la efeméride
                avisar(f"    frase {i + 1}: video {v.pagina} salteado ({str(err)[:80]})")
        vs = listos
        out[i] = [v for v in vs if v.frames]
        avisar(f"    frase {i + 1} (acción): {len(out[i])} videos candidatos "
               f"({', '.join(v.etiqueta() for v in out[i]) or 'ninguno'})")
    return out


def clave_archivo(archivo: str) -> str:
    """El mismo archivo de Commons llega como "Archivo:X.jpg" (es.wikipedia) y "File:X.jpg" (Commons): sin
    el prefijo, para no meterlo dos veces en el pool (2026-11-14: en La Pola la misma estatua dos veces)."""
    nombre = str(archivo or "").split(":", 1)[-1] if ":" in str(archivo or "")[:12] else str(archivo or "")
    return nombre.replace("_", " ").strip().lower()


# Escenas ilustrativas también en las frases centrales (Santi, 2026-11-14: "más escenas así, que
# ilustran lo que se dice aunque no sean del hecho exacto, sin confundir sobre lo central"). Antes el
# stock iba solo en las frases "al pasar" y las centrales sin foto de época quedaban con tarjetas:
# el 14/11 La Pola (8,5) llegó a 68 % de fotos reales y no salió.
ESCENAS_EN_CENTRALES = True
MAX_IMAGENES_ELECTOR = 100     # el tope de imágenes por pedido de Claude


def recortar_videos(videos: dict, lugar: int) -> dict:
    """{frase: [Video]} sin pasarse de `lugar` cuadros en total: se baja de a uno el tope de
    candidatos por frase (se quedan los primeros, que son los mejores de la búsqueda) y, si ni con
    uno por frase entra, quedan las primeras frases."""
    videos = {i: list(vs) for i, vs in videos.items() if vs}

    def cuadros(d):
        return sum(len(v.frames) for vs in d.values() for v in vs)

    tope = max((len(vs) for vs in videos.values()), default=0)
    while tope > 1 and cuadros(videos) > max(lugar, 0):
        tope -= 1
        videos = {i: vs[:tope] for i, vs in videos.items()}
    while videos and cuadros(videos) > max(lugar, 0):
        videos.pop(max(videos))
    return videos


def fotos_para_guion(wiki: Wiki, cliente, e: Evento, g: Guion, fotos_articulo: list[Foto],
                     carpeta: Path, avisar=log.info, pool: list[Foto] | None = None,
                     descartadas: set[int] | None = None, videos: bool = False,
                     buscador=None, fuentes=None,
                     tope_s: float | None = None, elector=None,
                     segunda: bool = False, forzadas: dict | None = None,
                     flojas: list[int] | None = None, puntual: dict | None = None,
                     primero=None) -> tuple[list[Foto], Guion]:
    """`primero` (fotos_primero.Banco, Santi 2026-11-25): las fotos ya juntadas y descriptas ANTES del guion; no se
    busca por frase ni se elige mirando imágenes: Haiku dice qué fotos van con cada frase (solo texto) y sigue el armado
    de siempre. En la segunda búsqueda (`segunda`) no se usa: es la búsqueda de siempre sobre el mismo pool.

    `segunda`: la segunda búsqueda del control de calidad (ver fotos_con_control). `forzadas` ({frase: foto}):
    las frases reescritas para hablar de una foto (plan B, 2026-11-23) van primero con esa foto. `flojas` (con
    `segunda`): las frases que en la primera vuelta se quedaron sin foto real (o con una que no mostraba lo que dicen):
    se buscan otra vez con otras palabras (el nombre del producto o la persona, en inglés, con el modelo y el año) en
    Commons y en todas las otras fuentes (Santi, 2026-11-24); `puntual` ({frase: (consultas, fotos nuevas)}) lo anota.

    Busca candidatas para cada frase (las del artículo + Commons con su `mostrar`), las baja,
    Gemini elige, y arma la foto de cada frase con las reglas de `ilustrar`. Devuelve el pool (las
    fotos que se bajaron, en su numeración) y el guion con `fotos`, `ranking` y `descartadas`.

    `pool`: el de una propuesta anterior (✏️), para que los números no cambien. NarrarError si no
    se llega a ilustrar.MIN_FOTOS_DISTINTAS."""
    modo_primero = primero is not None and not segunda
    if modo_primero and not pool:
        pool = list(primero.pool)
    pool = list(pool or [])
    por_archivo = {clave_archivo(f.archivo): i for i, f in enumerate(pool)}
    descartadas = set(descartadas or ())
    if modo_primero:
        descartadas |= {k for k in range(len(primero.pool)) if k not in primero.buenas}
        videos = False

    def sumar(fotos: list[Foto], cuantas: int) -> list[int]:
        nuevas, vistas = [], set()
        for f in fotos:
            k = clave_archivo(f.archivo)
            if k not in por_archivo and k not in vistas:
                vistas.add(k)
                nuevas.append(f)
        nuevas = nuevas[:cuantas]
        espacio = (POOL_MAX_ORDEN if g.imagen_frase else POOL_MAX) - len(pool)
        # El nombre lleva la posición en el pool: con ✏️ el pool crece y nada pisa lo anterior.
        bajadas, _ = bajar_fotos(wiki, nuevas, carpeta, f"{e.anio}_p{len(pool):02d}",
                                 max(espacio, 0), avisar)
        for f in bajadas:
            por_archivo[clave_archivo(f.archivo)] = len(pool)
            pool.append(f)
        claves = dict.fromkeys(clave_archivo(f.archivo) for f in fotos)
        return [por_archivo[k] for k in claves if k in por_archivo][:cuantas]

    g.segunda_busqueda = segunda
    g.tarjetas = []
    g.tarjetas_fotos = []
    del_hecho = [i for i in sumar(fotos_articulo, FOTOS_ARTICULO_MAX) if i not in descartadas]
    if segunda:
        # Fotos reales del protagonista y del lugar: Commons con el título de cada artículo del hecho y,
        # desde el 2026-11-15 (Santi: "nunca un día sin video"), la búsqueda mejorada: en castellano y en
        # inglés con la época, en las categorías de los archivos nacionales que están en Commons y en
        # Europeana.
        for q in consultas_segunda(wiki, e):
            nuevas, _ = filtrar_infos(wiki, "commons", wiki.buscar_commons(q), f"Commons: {q}", e.anio)
            del_hecho += [i for i in sumar(nuevas, FOTOS_BUSQUEDA_MAX)
                          if i not in descartadas and i not in del_hecho]
        from . import fuentes_fotos as _ff
        for titulo in e.paginas[:2]:
            try:
                halladas = (fuentes or _ff.Fuentes()).europeana(titulo.replace("_", " "))
            except Exception as err:   # una fuente caída no frena la búsqueda
                avisar(f"    fotos: Europeana «{titulo}» falló ({str(err)[:80]})")
                continue
            nuevas = [_foto_de({"fuente": "europeana", **h}, titulo) for h in halladas
                      if h.get("url") and h.get("licencia")]
            del_hecho += [i for i in sumar(nuevas, FOTOS_BUSQUEDA_MAX)
                          if i not in descartadas and i not in del_hecho]
    propias, descartes = ([[] for _ in g.mostrar] if modo_primero else []), {}
    if modo_primero:
        del_hecho = [k for k in primero.buenas if k not in descartadas]
    from . import fuentes_fotos
    from .videos_libres import consultas as achicar_consultas, es_de_espacio, sin_anios

    argentino = fuentes_fotos.es_argentino(f"{e.texto} {' '.join(e.paginas)}")
    otras = fuentes or fuentes_fotos.Fuentes()
    # Tope total de la búsqueda (2026-10-29: pasó de 45 min y systemd mató la corrida): vencido, se
    # sigue con lo que ya se bajó.
    corrida = fuentes_fotos.CORRIDA
    corrida.con_tope(TOPE_FOTOS_S if tope_s is None else tope_s)
    for i, mostrar in ([] if modo_primero else enumerate(g.mostrar)):
        if corrida.vencida():
            if len(propias) == i:
                avisar(f"    fotos: pasó el tope de {(TOPE_FOTOS_S if tope_s is None else tope_s) / 60:.0f} "
                       f"min de búsqueda: sigo con lo que hay (frases {i + 1} a {len(g.mostrar)} sin buscar)")
            propias.append([])
            continue
        # Commons, de la búsqueda puntual a la general (2026-10-02: "1924 Onzari Argentina" pedía
        # todas las palabras y no traía nada) y, si el hecho es argentino, las fotos PD-AR-Photo.
        qs = achicar_consultas(mostrar)
        # La búsqueda tal cual primero (con el año, en Commons a veces trae más que sin él).
        consultas_commons = list(dict.fromkeys([mostrar] + qs[:3])) +             ([f'{sin_anios(mostrar)} incategory:"PD-AR-Photo"'] if argentino else [])
        halladas: list[Foto] = []
        hoy = i < len(g.presente) and g.presente[i]
        orden = g.imagen_frase
        # Orden nuevo (2026-11-10, Santi): (a) foto del hecho o del lugar (Commons y las otras
        # fuentes de archivo, con `mostrar`), (b) foto del OBJETO o la acción en Commons, (c) el
        # objeto en Pexels. La tarjeta, solo si no queda ninguna.
        # Lo central del hecho, real (2026-11-10): una frase CENTRAL busca solo fotos del hecho o del
        # lugar; una que nombra algo AL PASAR, sobre todo fotos genéricas de esa cosa.
        central = es_central(g, i)
        lim_a = (FOTOS_HECHO_FRASE if central else FOTOS_HECHO_AL_PASAR) if orden else FOTOS_BUSQUEDA_MAX
        # Temas modernos (2026-10-21): primero Pexels/Unsplash, antes que capturas de Commons.
        if not orden and (e.anio >= ANIO_MODERNO or hoy):
            for h in otras.stock(qs, FOTOS_STOCK_MAX, avisar):
                halladas.append(_foto_de(h, mostrar))
        for q in consultas_commons:
            if len(halladas) >= lim_a or corrida.vencida():
                break
            nuevas, desc = filtrar_infos(wiki, "commons", wiki.buscar_commons(q), f"Commons: {mostrar}",
                                         e.anio)
            for k, v in desc.items():
                descartes[k] = descartes.get(k, 0) + v
            halladas += [f for f in nuevas if f.archivo not in {h.archivo for h in halladas}]
        # Si Commons no alcanza: las otras fuentes, en orden (fuentes_fotos).
        if len(halladas) < lim_a and not corrida.vencida():
            for h in otras.buscar(qs, hoy, es_de_espacio(mostrar), lim_a - len(halladas), avisar):
                halladas.append(_foto_de(h, mostrar))
        halladas = halladas[:lim_a]
        if orden and not central and not corrida.vencida():
            obj = (g.objeto[i] if i < len(g.objeto) else "") or sin_anios(mostrar)
            nuevas, desc = filtrar_infos(wiki, "commons", wiki.buscar_commons(obj),
                                         f"Commons (objeto): {obj}", e.anio)
            for k, v in desc.items():
                descartes[k] = descartes.get(k, 0) + v
            halladas += [f for f in nuevas if f.archivo not in {h.archivo for h in halladas}][:FOTOS_OBJETO_FRASE]
            # Pexels: solo para lo que se nombra al pasar (objetos genéricos).
            halladas += [_foto_de(h, obj) for h in otras.stock([obj], FOTOS_PEXELS_FRASE, avisar)
                         if h["fuente"] == "pexels"]
        elif orden and central and ESCENAS_EN_CENTRALES and not corrida.vencida():
            # Una escena que ilustra la situación (2026-11-14): Pexels con el objeto o la acción de la
            # frase. La elige el modelo solo si no hay foto real y no se confunde con lo central.
            obj = (g.objeto[i] if i < len(g.objeto) else "") or sin_anios(mostrar)
            halladas += [_foto_de(h, obj) for h in otras.stock([obj], FOTOS_PEXELS_FRASE, avisar)
                         if h["fuente"] == "pexels"]
        propias.append([i for i in sumar(halladas, len(halladas) if orden else FOTOS_BUSQUEDA_MAX)
                        if i not in descartadas])
    if segunda and flojas:
        for i in flojas:
            if not 0 <= i < len(propias) or corrida.vencida():
                continue
            qs = consultas_frase(wiki, e, g, i)
            halladas = []
            for q in qs[:4]:
                if len(halladas) >= FOTOS_PUNTUAL_FRASE or corrida.vencida():
                    break
                nuevas, desc = filtrar_infos(wiki, "commons", wiki.buscar_commons(q), f"Commons (puntual): {q}",
                                             e.anio)
                for k_, v in desc.items():
                    descartes[k_] = descartes.get(k_, 0) + v
                halladas += [f for f in nuevas if f.archivo not in {h.archivo for h in halladas}]
            if len(halladas) < FOTOS_PUNTUAL_FRASE and not corrida.vencida():
                # Openverse (Flickr CC, museos), Smithsonian, Europeana, Flickr e Internet Archive; nada de stock
                for h in otras.buscar(qs, False, False, FOTOS_PUNTUAL_FRASE - len(halladas), avisar):
                    halladas.append(_foto_de(h, qs[0]))
            nuevas_idx = [x for x in sumar(halladas, FOTOS_PUNTUAL_FRASE) if x not in descartadas]
            propias[i] = list(dict.fromkeys(nuevas_idx + propias[i]))
            if puntual is not None:
                puntual[i] = (qs[:4], len(nuevas_idx))
            avisar(f"    fotos: frase {i + 1} buscada otra vez ({' | '.join(qs[:3])}): +{len(nuevas_idx)}")
    # Regla fija de época: las fotos sacadas más de MARGEN_EPOCA años después del hecho no son
    # candidatas de las frases del pasado. Las del artículo del hecho quedan de respaldo igual
    # (de_reserva): antes una del artículo repetida que una moderna.
    modernas = set() if segunda or modo_primero else \
        {i for i, f in enumerate(pool) if f.anio and f.anio > e.anio + MARGEN_EPOCA}
    presente = [i < len(g.presente) and g.presente[i] for i in range(len(g.frases))]
    avisar(f"  fotos: {len(pool)} bajadas ({len(del_hecho)} del artículo, {len(modernas)} de más de "
           f"{MARGEN_EPOCA} años después de {e.anio}); descartes {descartes}")
    # Cada frase puede elegir CUALQUIER foto del pool, empezando por las de su búsqueda: en la
    # prueba del 28/09 la frase "el hongo mataba a las bacterias" solo podía elegir entre lo que
    # trajo su búsqueda (mala) y no las placas de Petri que había traído otra frase.
    todas = [i for i in range(len(pool)) if i not in descartadas and not es_tarjeta(pool[i])]
    # Capturas de páginas web o redes: solo para las frases que hablan de una página (2026-10-02).
    capturas = {i for i, f in enumerate(pool) if _CAPTURA.search(f"{f.archivo} {f.epigrafe}")}
    de_web = [bool(_HABLA_DE_WEB.search(f"{g.frases[i]} {g.mostrar[i] if i < len(g.mostrar) else ''}"))
              for i in range(len(g.frases))]
    # Frases que hablan de hoy o, con imagen = lo que se dice, que nombran algo al pasar: sin la
    # regla de época. Las CENTRALES, solo fotos del hecho o del lugar (nada de stock ni "objeto").
    libres = sin_epoca(g)
    genericas = {i for i, f in enumerate(pool)
                 if es_stock(f) or f.articulo.startswith("Commons (objeto)")} if g.imagen_frase else set()
    candidatas = [[x for x in dict.fromkeys(p + del_hecho + todas)
                   if (libre or x not in modernas) and (web or x not in capturas)
                   and not (g.imagen_frase and es_central(g, k) and x in genericas and not ESCENAS_EN_CENTRALES)]
                  for k, (p, libre, web) in enumerate(zip(propias, libres, de_web))]
    if videos and corrida.vencida():
        avisar("    videos: sin buscar (pasó el tope de la búsqueda)")
    candidatos_video = (buscar_videos(g, e.anio, carpeta, buscador, avisar, tema=e.paginas[0])
                        if videos and not corrida.vencida() else {})
    # Claude ve hasta 100 imágenes por pedido: los cuadros de los videos no pueden empujar las fotos
    # a Gemini (con el estilo nuevo buscan video hasta 6 frases).
    candidatos_video = recortar_videos(candidatos_video, MAX_IMAGENES_ELECTOR - len(pool))
    corrida.con_tope(None)
    elegidos: dict = {}
    # Qué parte de cada foto es texto (OCR): una captura, un documento o una placa no pasan.
    ocr = {k: fraccion_texto(Path(f.ruta)) for k, f in enumerate(pool) if f.ruta}
    extra: dict = {}
    if modo_primero:
        from . import fotos_primero as _fp

        rankings = _fp.asignar(primero.haiku, g.frases, primero, avisar, mostrar=g.mostrar)
        # la foto que eligió el guion al escribir cada frase va primera (Santi, 2026-11-25: el guion A PARTIR de las
        # fotos); Haiku completa las demás
        elegidas = list(getattr(primero, "elegidas", None) or [])
        rankings = [list(dict.fromkeys(([elegidas[i]] if i < len(elegidas) and elegidas[i] is not None else [])
                                       + r)) for i, r in enumerate(rankings)]
        rankings = [[x for x in r if x not in descartadas] for r in rankings]
        vistas_malas = set()
    else:
        rankings, vistas_malas = elegir_fotos(cliente, g, pool, candidatas, propias, avisar=avisar,
                                              anio=e.anio, videos=candidatos_video, elegidos=elegidos,
                                              ocr=ocr, extra=extra, elector=elector)
    g.fotos_respaldo = bool(extra.get("respaldo"))
    g.con_videos = videos
    g.videos = {str(i): v.a_dict() for i, v in elegidos.items()}
    g.con_video = sorted(elegidos)
    descartadas |= vistas_malas
    for i, f in (forzadas or {}).items():
        if 0 <= i < len(rankings) and 0 <= f < len(pool) and f not in descartadas:
            rankings[i] = [f] + [x for x in rankings[i] if x != f]
    g.ranking, g.descartadas = rankings, sorted(descartadas)
    g.del_hecho, g.modernas, g.presente = del_hecho, sorted(modernas), presente
    reserva = de_reserva(g, len(pool))
    # La época le gana a la cantidad: si no hay 6 fotos de época, el mínimo baja a las que haya.
    # Con menos de ilustrar.MIN_FOTOS_ABSOLUTO (4), PocasFotos: `proponer` pasa al hecho siguiente
    # y se guarda este por si ninguno llega (con MIN_FOTOS_RESPALDO como piso).
    disponibles = len(set(reserva) | {x for r in rankings for x in r})
    g.minimo_fotos = min(ilustrar.MIN_FOTOS_DISTINTAS, disponibles)
    if g.minimo_fotos < ilustrar.MIN_FOTOS_RESPALDO:
        raise NarrarError(f"solo {disponibles} fotos de época que sirvan")
    gen = generales(g)
    try:
        asignadas = ilustrar.asignar(rankings, reserva, gen)
    except ValueError as err:
        # las frases del principio sin foto (no hay una anterior que alargar): plan B o el hecho siguiente
        primeras = []
        for i, r in enumerate(rankings):
            if r:
                break
            primeras.append(i)
        raise FraseSinFoto(pool, g, primeras or [0]) from err
    g.fotos = ilustrar.completar_distintas(asignadas, rankings, reserva, g.minimo_fotos, gen)
    errores = ilustrar.errores_plan(plan_estimado(g, len(pool)), g.minimo_fotos)
    # Una frase sin una foto buena (2026-10-21): antes que una mala, una del tema general o la de la
    # frase anterior alargada (2026-11-09: nunca la foto de OTRA frase puntual, como los billetes de
    # rupias de Android) y, si ya no se puede, la tarjeta con el año o una palabra clave.
    vacias = [i for i, r in enumerate(rankings) if not r]
    sin_propia = list(vacias)
    base = next(iter(dict.fromkeys(list(reserva) + [x for r in rankings for x in r])), None)
    while (vacias and base is not None and len(set(g.tarjetas_fotos or [])) < MAX_TARJETAS
           and any("aparecen más de" in x or "seguidos" in x for x in errores)):
        i = vacias.pop()
        # La palabra clave de la frase o, si no tiene, el año (Santi, 2026-11-11: la de "2022"
        # queda bien; el 2026-11-10 se había sacado el año). Desde el 2026-11-23, el año solo si la frase lo dice.
        texto = texto_tarjeta(g, i, e.anio)
        if not texto:
            continue
        t = tarjeta(pool[base], texto, carpeta / f"tarjeta_{i + 1:02d}.jpg")
        pool.append(t)
        rankings[i] = [len(pool) - 1]
        g.tarjetas = sorted(set(g.tarjetas) | {i})
        g.tarjetas_fotos = list(g.tarjetas_fotos or []) + [len(pool) - 1]
        avisar(f"    frase {i + 1}: sin foto buena → tarjeta «{t.epigrafe}»")
        g.ranking = rankings
        reserva = de_reserva(g, len(pool))
        g.fotos = ilustrar.completar_distintas(ilustrar.asignar(rankings, reserva, gen), rankings,
                                               reserva, g.minimo_fotos, gen)
        errores = ilustrar.errores_plan(plan_estimado(g, len(pool)), g.minimo_fotos)
    if any("aparecen más de" in e for e in errores):
        # Pocas fotos para tantas frases sin repetir más de 2 veces: como con menos de 4, al siguiente.
        raise PocasFotos(pool, g, disponibles)
    if errores and g.imagen_frase and all("seguidos" in x for x in errores):
        # "Si no hay foto, alargá la anterior antes que poner una tarjeta" (Santi, 2026-11-10).
        avisar(f"    fotos: {'; '.join(errores)} (se alarga la anterior antes que poner una tarjeta)")
        errores = []
    if errores:
        raise FotosNoAlcanzan(pool, g, errores)
    if g.minimo_fotos < ilustrar.MIN_FOTOS_ABSOLUTO:
        raise PocasFotos(pool, g, disponibles)
    plan = plan_estimado(g, len(pool))
    if g.imagen_frase and not segunda:
        # Santi, 2026-11-11 (Cartagena): frases sin foto propia, o un corto que tendría que repetir
        # una foto en más de 2 cortes → primero buscar más (la segunda búsqueda: Commons en general,
        # sin la regla de época, y Pexels para lo que se nombra al pasar).
        faltas: list = []
        if g.corto:
            plan_rapido(plan, g, faltas=faltas)
        if sin_propia or faltas:
            motivo = []
            if sin_propia:
                motivo.append(f"frases sin foto propia: {[i + 1 for i in sin_propia]}")
            if faltas:
                motivo.append(f"el corto repetiría fotos en {len(faltas)} cortes")
            raise FotosNoAlcanzan(pool, g, motivo)
    if g.corto:
        # Lo que todavía falte, con tarjetas (la clave de la frase o el año), y el 70 % se mide sobre
        # el corto tal cual va a salir.
        nueva = fabrica_tarjetas(g, e.anio, carpeta, lambda k: pool[k],
                                 lambda f: (pool.append(f), len(pool) - 1)[1])
        plan, _ = plan_rapido(plan, g, nueva_tarjeta=nueva)
    control_calidad(pool, g, plan)
    return pool, g


# ---- control de calidad (Santi, 2026-11-11) --------------------------------------------------
# "Si menos del 70 % del tiempo tiene fotos reales (no tarjetas), NO lo armes. Primero reintentá
# buscar fotos con Claude; si sigue sin alcanzar, elegí otro hecho del día. Si ninguno alcanza,
# avisame." El ejemplo del refrigerador de Einstein (10/11) pasó ~27 de 37 s con tarjetas.
UMBRAL_FOTOS_REALES = 0.70
UMBRAL_FOTOS_PISO = 0.50     # Santi, 2026-11-15: el 70 % baja de a 5 puntos hasta el 50 % (nunca menos)
PASO_UMBRAL = 0.05


def umbral_relajado(pct: float) -> float | None:
    """El mínimo más alto (70, 65, 60, 55 o 50 %) que `pct` alcanza; None si no llega ni al 50 %."""
    u = UMBRAL_FOTOS_REALES
    while u >= UMBRAL_FOTOS_PISO - 1e-9:
        if pct >= u - 1e-9:
            return round(u, 2)
        u -= PASO_UMBRAL
    return None


def umbral_de(g) -> float:
    """El mínimo de fotos reales de ESTE guion (el relajado, si salió con uno)."""
    return float(getattr(g, "umbral_fotos", 0) or 0) or UMBRAL_FOTOS_REALES


def aviso_fotos(g) -> str:
    """El aviso para Telegram cuando salió con el mínimo relajado; vacío si no."""
    if not getattr(g, "umbral_fotos", 0) or g.umbral_fotos >= UMBRAL_FOTOS_REALES:
        return ""
    return (f"⚠️ fotos reales {g.fotos_reales * 100:.0f} % (mínimo {UMBRAL_FOTOS_REALES * 100:.0f}; "
            f"salió con el mínimo bajado a {g.umbral_fotos * 100:.0f} %, el resto con mapa, retratos y texto)")


def aceptar_relajado(err: "FotosInsuficientes", avisar=log.info, piso: float = UMBRAL_FOTOS_PISO) -> bool:
    """Si las fotos de `err` llegan al 50 % (o a `piso`: la reserva de tecnología pide 60), el guion queda con el
    mínimo relajado y sirve."""
    u = umbral_relajado(err.pct)
    if u is None or err.pct < piso - 1e-9:
        return False
    err.guion.umbral_fotos = u
    err.guion.fotos_reales = round(err.pct, 3)
    avisar(f"  ningún hecho llegó al {UMBRAL_FOTOS_REALES * 100:.0f} %: sale con {err.pct * 100:.0f} % "
           f"(mínimo bajado a {u * 100:.0f} %)")
    return True


def es_tarjeta(f) -> bool:
    """Una tarjeta (texto sobre una foto difuminada), como Foto o como dict de una Propuesta."""
    articulo = f.get("articulo") if isinstance(f, dict) else getattr(f, "articulo", "")
    archivo = f.get("archivo") if isinstance(f, dict) else getattr(f, "archivo", "")
    return articulo == "tarjeta" or str(archivo or "").startswith("tarjeta:")


def fraccion_real(pool: list, plan: list[tuple[int, int, float]]) -> float:
    """Qué parte del tiempo del plan va con una foto real o un video (no una tarjeta)."""
    total = sum(s for *_, s in plan)
    if total <= 0:
        return 0.0
    reales = sum(s for _, f, s in plan
                 if f in (VIDEO, MAPA) or (0 <= f < len(pool) and not es_tarjeta(pool[f])))
    return reales / total


class FotosInsuficientes(NarrarError):
    """Menos del UMBRAL_FOTOS_REALES del tiempo con fotos reales: ese hecho no se arma."""

    def __init__(self, pool: list, g: "Guion", pct: float):
        super().__init__(f"solo {pct * 100:.0f} % del tiempo con fotos reales (mínimo "
                         f"{UMBRAL_FOTOS_REALES * 100:.0f} %)")
        self.pool, self.guion, self.pct = pool, g, pct


class FotosNoAlcanzan(NarrarError):
    """El plan no cumple la regla fija 1 (menos de 6 distintas, una foto más de 6 s): como con menos
    del 70 %, primero la segunda búsqueda con Claude y después el hecho siguiente (el Ash Ketchum del
    11/11 se salteaba la segunda búsqueda)."""

    def __init__(self, pool: list, g: "Guion", errores: list[str]):
        super().__init__("las fotos no alcanzan: " + "; ".join(errores))
        self.pool, self.guion = pool, g


def control_calidad(pool: list, g: "Guion", plan: list[tuple[int, int, float]]) -> float:
    pct = fraccion_real(pool, plan)
    g.fotos_reales = round(pct, 3)
    if pct < UMBRAL_FOTOS_REALES:
        raise FotosInsuficientes(pool, g, pct)
    return pct


# Archivos nacionales cuyas fotos están en Commons (2026-11-15): la Biblioteca del Congreso de EE. UU. y la
# Biblioteca Digital Hispánica bloquean a los bots (403) y Memoria Chilena no tiene API: se usan sus
# copias en Commons, con las licencias que Commons ya verificó.
ARCHIVOS_COMMONS = ("Archivo General de la Nación Argentina", "Archivo General de la Nación (Mexico)",
                    "Images from the Biblioteca Nacional de Chile", "Biblioteca Nacional de Colombia",
                    "Images from Biblioteca Nacional de España", "Images from the Library of Congress",
                    "Archivo Histórico de Guayaquil", "Biblioteca Nacional del Perú")


def consultas_segunda(wiki: "Wiki", e: "Evento") -> list[str]:
    """Las búsquedas de la segunda vuelta: cada artículo del hecho (persona, lugar), en castellano y en
    inglés, con la década; y los mismos nombres en las categorías de los archivos nacionales."""
    decada = f"{e.anio // 10 * 10}s" if e.anio else ""
    nombres = []
    for t in e.paginas[:3]:
        nombres.append(t.replace("_", " "))
        try:
            otro = wiki.en_espanol(t) if e.lang == "en" else None
        except Exception:
            otro = None
        if otro:
            nombres.append(otro.replace("_", " "))
    nombres = list(dict.fromkeys(n for n in nombres if n))
    out = []
    for n in nombres:
        out.append(n)
        if decada:
            out.append(f"{n} {decada}")
    cats = "|".join(f'"{c}"' for c in ARCHIVOS_COMMONS)
    out += [f"{n} incategory:{cats}" for n in nombres[:2]]
    return list(dict.fromkeys(out))[:10]


FOTOS_PUNTUAL_FRASE = 5     # fotos nuevas por frase floja en la búsqueda puntual (Santi, 2026-11-24)


def consultas_frase(wiki: "Wiki", e: "Evento", g: "Guion", i: int) -> list[str]:
    """Otras palabras para buscar la foto de una frase que se quedó sin una (Santi, 2026-11-24: "el nombre del producto,
    el modelo, el año, en inglés"): el nombre del artículo del hecho (y su título en inglés) con las claves de esa frase
    o con el año, ese nombre con la cosa que se ve, y lo que la frase muestra sin el año. Nunca la cosa genérica sola:
    eso trae fotos de banco que no son ESE producto ni ESA persona."""
    from .videos_libres import sin_anios

    nombres = []
    for t in e.paginas[:2]:
        nombres.append(t.replace("_", " "))
        if e.lang == "es":
            try:
                en = wiki.en_ingles(t)
            except Exception:  # noqa: BLE001 — sin el título en inglés, con el de siempre
                en = None
            if en:
                nombres.append(en.replace("_", " "))
    nombres = [re.sub(r"\s*\(.*?\)", "", n).strip() for n in dict.fromkeys(nombres)]
    nombres = list(dict.fromkeys(n for n in nombres if n))
    frase = _norm(g.frases[i]) if i < len(g.frases) else ""
    claves = [c for c in g.claves if _norm(c) and _norm(c) in frase]
    mostrar = sin_anios(g.mostrar[i]) if i < len(g.mostrar) else ""
    obj = sin_anios(g.objeto[i]) if i < len(g.objeto) else ""
    nombres = nombres[:3]
    # de la más puntual a la más general: el modelo, el año, lo que muestra la frase, la cosa con su nombre, el nombre
    out = [f"{n} {c}" for n in nombres for c in claves[:2] if _norm(c) not in _norm(n)]
    out += [f"{n} {e.anio}" for n in nombres if e.anio]
    out += [mostrar] if mostrar else []
    out += [f"{n} {obj}" for n in nombres if obj]
    out += nombres
    return [q for q in dict.fromkeys(" ".join(x.split()) for x in out) if q][:10]


class FraseSinFoto(NarrarError):
    """Una frase (del principio: no hay anterior que alargar) sin ninguna foto posible. Antes era un ValueError que
    cortaba toda la propuesta (el 20 y el 21/11 no salió ni tecnología ni Latinoamérica): ahora primero se reescribe
    SOLO esa frase para que hable de algo con foto y, si no, es un NarrarError: el hecho siguiente y después el banco."""

    def __init__(self, pool: list, g: "Guion", frases: list[int]):
        super().__init__(f"la frase {frases[0] + 1} no tiene ninguna foto posible")
        self.pool, self.guion, self.frases = pool, g, frases


SISTEMA_FRASE_CON_FOTO = (
    "Sos editor de guiones de Shorts de historia. Algunas frases del guion no tienen ninguna foto que las muestre. "
    "Reescribí SOLO esas frases para que hablen de algo que SÍ muestra una de las fotos disponibles (el lugar, la "
    "persona, un objeto de la época), sin cambiar la historia ni el orden, con un largo parecido (±4 palabras) y usando "
    "SOLO datos del texto del artículo. Si es la frase 1 es el GANCHO: el dato concreto más fuerte, sin fecha ni "
    "'Un día como hoy', sin fórmulas de intriga genéricas. `mostrar`: qué se ve, en inglés, 3 a 7 palabras, con "
    "año o década y lugar si es del pasado. `foto`: el número de la foto disponible que la va a mostrar.")
SCHEMA_FRASE_CON_FOTO = {"type": "OBJECT", "properties": {"frases": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"n": {"type": "INTEGER"}, "frase": {"type": "STRING"},
                                     "mostrar": {"type": "STRING"}, "foto": {"type": "INTEGER"}},
    "required": ["n", "frase", "mostrar", "foto"]}}}, "required": ["frases"]}


def reescribir_frases_con_foto(cliente, e: "Evento", fuente: str, g: "Guion", idxs: list[int], pool: list,
                               avisar=log.info, forzadas: dict | None = None) -> bool:
    """Plan B (Santi, 2026-11-21: "nunca más 'la frase 1 no tiene ninguna foto posible'"): reescribe SOLO esas
    frases para que hablen de algo que muestra una foto que ya pasó los filtros (las que la elección dejó en alguna
    frase y las del artículo del hecho), con los datos del artículo. Una sola llamada; True si quedaron válidas."""
    from . import reglas
    from .gemini import GeminiError

    malas = set(g.descartadas or [])
    usables = [k for k in dict.fromkeys([x for r in (g.ranking or []) for x in r] + list(g.del_hecho or []))
               if 0 <= k < len(pool) and k not in malas]
    if not usables or not idxs:
        return False
    lista = "\n".join(f"{k + 1}. {(pool[k].epigrafe or pool[k].archivo)[:140]}"
                      + (f" ({pool[k].anio})" if getattr(pool[k], "anio", None) else "") for k in usables[:30])
    prompt = ("Guion:\n" + "\n".join(f"{i + 1}. {f}" for i, f in enumerate(g.frases))
              + "\n\nFrases SIN foto (reescribí solo estas): " + ", ".join(str(i + 1) for i in idxs)
              + f"\n\nFOTOS DISPONIBLES:\n{lista}\n\nTEXTO DEL ARTÍCULO (lo único que podés usar):\n{fuente[:12000]}")
    try:
        r = json.loads(cliente.json(SISTEMA_FRASE_CON_FOTO, prompt, SCHEMA_FRASE_CON_FOTO, temperatura=0.3))
    except (GeminiError, ValueError, NarrarError) as err:
        avisar(f"  plan B de la frase sin foto: no respondió ({str(err)[:80]})")
        return False
    nuevas = {int(x.get("n") or 0) - 1: x for x in r.get("frases") or []}
    cambios = {}
    for i in idxs:
        x = nuevas.get(i)
        texto = str((x or {}).get("frase") or "").strip()
        if not texto or abs(len(texto.split()) - len(g.frases[i].split())) > 6:
            avisar(f"  plan B: la frase {i + 1} no volvió bien")
            return False
        if no_respaldados(texto, fuente + "\n" + e.texto + f" {e.anio}", e.anio):
            avisar(f"  plan B: la frase {i + 1} nueva trae datos que no están en el artículo")
            return False
        if i == 0 and (reglas.gancho_generico(texto) or texto.lower().startswith("un día como hoy")):
            avisar("  plan B: el gancho nuevo es genérico")
            return False
        k = int(x.get("foto") or 0) - 1
        cambios[i] = (texto, str(x.get("mostrar") or "").strip(), k if k in usables else None)
    for i, (texto, mostrar, k) in cambios.items():
        if forzadas is not None and k is not None:
            forzadas[i] = k
        avisar(f"  plan B: frase {i + 1} reescrita para que tenga foto: «{texto[:90]}»")
        g.frases[i] = texto
        if mostrar and i < len(g.mostrar):
            g.mostrar[i] = mostrar
    return True


def frases_flojas(g: "Guion", pool: list) -> list[int]:
    """Las frases que se quedaron sin foto real (ninguna, o solo tarjetas, o una sola en el corto, que necesita 2
    para no repetir): las que el plan B reescribe antes de poner tarjetas (Santi, 2026-11-23)."""
    out = set(g.tarjetas or [])
    for i, r in enumerate(g.rankings()):
        reales = [x for x in r if 0 <= x < len(pool) and not es_tarjeta(pool[x])]
        if not reales or (g.corto and len(reales) < 2 and i > 0):
            out.add(i)
    return sorted(out)[:MAX_REESCRITAS]


MAX_REESCRITAS = 4     # frases que el plan B reescribe de una vez (más que eso, es otra historia)


def fotos_con_control(wiki: "Wiki", cliente, e: "Evento", g: "Guion", fotos_articulo: list,
                      carpeta: Path, avisar=log.info, elector=None, elector_reintento=None,
                      reescribir=None, **k) -> tuple[list, "Guion"]:
    """fotos_para_guion con el control de calidad. Si falla, primero se arregla lo que falló, en orden (Santi,
    2026-11-24: "que no pase a otra historia a ciegas"):
    1. SEGUNDA búsqueda con Claude: Commons con el título de cada artículo del hecho, sin la regla de época, y las
       frases que se quedaron sin foto real (o con una que no mostraba lo que dicen: el elector la descarta) se buscan
       otra vez, una por una, con otras palabras (el producto o la persona, en inglés, con el modelo y el año) en
       Commons y en todas las otras fuentes (`consultas_frase`).
    2. PLAN B (Santi, 2026-11-21/23): las frases que siguen sin foto real se reescriben (Haiku, un pedido) para que
       hablen de algo que muestra una foto que ya pasó los filtros, y se eligen las fotos otra vez.
    3. Recién si nada de eso funciona, la excepción sigue de largo (quien llama pasa a otra historia), con
       `.intentos`: qué falló y qué se intentó, para la bitácora."""
    pasos: list[str] = []
    try:
        return _fotos_con_control(wiki, cliente, e, g, fotos_articulo, carpeta, avisar, elector, elector_reintento,
                                  reescribir, pasos, **k)
    except NarrarError as err:
        if not getattr(err, "intentos", None):
            err.intentos = pasos + [f"final: {err}"]
        raise


def _texto_puntual(puntual: dict) -> str:
    if not puntual:
        return "búsqueda puntual: ninguna frase sin foto"
    partes = [f"frase {i + 1} con «{(qs or [''])[0]}» +{n}" for i, (qs, n) in sorted(puntual.items())]
    return "búsqueda puntual en todas las fuentes: " + "; ".join(partes)


def _fotos_con_control(wiki, cliente, e, g, fotos_articulo, carpeta, avisar, elector, elector_reintento,
                       reescribir, pasos: list, **k):
    try:
        return fotos_para_guion(wiki, cliente, e, g, fotos_articulo, carpeta, avisar, elector=elector, **k)
    except FraseSinFoto as err:
        pasos.append(f"1.ª búsqueda: {err}")
        # Plan B (Santi, 2026-11-21): la frase sin foto se reescribe para hablar de algo que sí tiene foto
        forzadas: dict = {}
        if reescribir is None or not reescribir(err.guion, err.frases, err.pool, forzadas):
            pasos.append(f"reescribir la frase {err.frases[0] + 1} hacia una foto: no se pudo")
            err.intentos = pasos + [f"final: {err}"]
            raise
        pasos.append(f"reescrita la frase {[i + 1 for i in err.frases]} hacia una foto")
        anterior, pool_antes = err.guion, err.pool
        k2 = {**k, "pool": pool_antes, "descartadas": set(anterior.descartadas), "forzadas": forzadas}
        try:
            return fotos_para_guion(wiki, cliente, e, anterior, fotos_articulo, carpeta, avisar, elector=elector,
                                    **k2)
        except (FotosInsuficientes, FotosNoAlcanzan, PocasFotos) as err2:
            pasos.append(f"con la frase reescrita: {err2}")
            avisar(f"  {err2}: segunda búsqueda de fotos con Claude")
            anterior, pool_antes = err2.guion, err2.pool
    except (FotosInsuficientes, FotosNoAlcanzan, PocasFotos) as err:
        pasos.append(f"1.ª búsqueda: {err}")
        avisar(f"  {err}: segunda búsqueda de fotos con Claude")
        anterior, pool_antes = err.guion, err.pool
    puntual: dict = {}
    k = {**k, "pool": pool_antes, "descartadas": set(anterior.descartadas)}
    try:
        return fotos_para_guion(wiki, cliente, e, anterior, fotos_articulo, carpeta, avisar,
                                elector=elector_reintento or elector, segunda=True,
                                flojas=frases_flojas(anterior, pool_antes), puntual=puntual, **k)
    except (FotosInsuficientes, FotosNoAlcanzan) as err3:
        pasos.append(f"2.ª búsqueda ({_texto_puntual(puntual)}): {err3}")
        idxs = frases_flojas(err3.guion, err3.pool)
        forzadas = {}
        if reescribir is None or not idxs or not reescribir(err3.guion, idxs, err3.pool, forzadas):
            pasos.append(f"reescribir las frases {[i + 1 for i in idxs]} hacia una foto: no se pudo")
            err3.intentos = list(pasos)
            raise
        pasos.append(f"reescritas las frases {[i + 1 for i in idxs]} hacia fotos que hay")
        avisar(f"  plan B: reescribí las frases {[i + 1 for i in idxs]} hacia fotos que hay; elijo de nuevo")
        k3 = {**k, "pool": err3.pool, "descartadas": set(err3.guion.descartadas), "forzadas": forzadas}
        try:
            return fotos_para_guion(wiki, cliente, e, err3.guion, fotos_articulo, carpeta, avisar,
                                    elector=elector_reintento or elector, segunda=True, **k3)
        except (FotosInsuficientes, FotosNoAlcanzan) as err4:
            pasos.append(f"con las frases reescritas: {err4}")
            # el que más se acercó, para que `proponer` pueda decidir con el mejor de los dos
            mejor = err4 if getattr(err4, "pct", 0) >= getattr(err3, "pct", 0) else err3
            mejor.intentos = list(pasos)
            raise mejor from err4


def _control_real(g, pct: float, avisar=log.info) -> None:
    """El control con los tiempos REALES de la voz: el mínimo del guion; si la voz lo baja, el mínimo
    baja de a 5 puntos hasta el 50 % (con aviso). Debajo del 50 %, no se arma."""
    if pct >= umbral_de(g) - 1e-9:
        return
    u = umbral_relajado(pct)
    if u is None:
        raise SinFotosReales(f"solo {pct * 100:.0f} % del tiempo con fotos reales (mínimo "
                             f"{UMBRAL_FOTOS_PISO * 100:.0f} % aun bajándolo): no armo el video")
    g.umbral_fotos, g.fotos_reales = u, round(pct, 3)
    avisar(f"⚠️ con la voz real quedan {pct * 100:.0f} % de fotos reales: mínimo bajado a {u * 100:.0f} %")


def respaldo_sirve(pocas: "PocasFotos") -> bool:
    """El hecho de respaldo (el de más fotos, cuando ninguno llegó a 4) solo si igual pasa el 70 %."""
    try:
        return fraccion_real(pocas.pool, plan_estimado(pocas.guion, len(pocas.pool))) >= UMBRAL_FOTOS_REALES
    except (IndexError, ValueError, NarrarError):
        return False


MAX_TARJETAS = 2     # Santi, 2026-11-23: la tarjeta es el último recurso, como mucho 2 por video


def dice_anio(g: Guion, i: int, anio: int) -> bool:
    return i < len(g.frases) and re.search(r"(?<!\d)" + str(anio) + r"(?!\d)", g.frases[i]) is not None


def texto_tarjeta(g: Guion, i: int, anio: int, solo_clave: bool = False) -> str | None:
    """La palabra clave de esa frase (si alguna de `g.claves` está en ella) o, si no, el año, SOLO si esa frase lo
    dice (Santi, 2026-11-23: en Meucci salió «1876» mientras la voz decía 1854).
    `solo_clave`: sin clave, None (no hay tarjeta: el año suelto no tiene que ver con la frase)."""
    frase = _norm(g.frases[i]) if i < len(g.frases) else ""
    for c in g.claves:
        if _norm(c) and _norm(c) in frase:
            return c.upper()
    return None if solo_clave or not dice_anio(g, i, anio) else str(anio)


def tarjeta(base: Foto, texto: str, salida: Path) -> Foto:
    """Una imagen 9:16 con el texto grande sobre la foto `base` difuminada (para la frase que no
    tiene una foto buena). Lleva el crédito de la foto de base."""
    from PIL import Image, ImageDraw, ImageFilter

    W, H = 1080, 1920
    fondo = Image.open(base.ruta).convert("RGB")
    escala = max(W / fondo.width, H / fondo.height)
    fondo = fondo.resize((int(fondo.width * escala) + 1, int(fondo.height * escala) + 1))
    x0, y0 = (fondo.width - W) // 2, (fondo.height - H) // 2
    fondo = fondo.crop((x0, y0, x0 + W, y0 + H)).filter(ImageFilter.GaussianBlur(28))
    fondo = Image.blend(fondo, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
    d = ImageDraw.Draw(fondo)
    tam = 260 if len(texto) <= 4 else max(90, int(1700 / max(len(texto), 1)))
    fuente = _fuente_ttf(tam)
    caja = d.textbbox((0, 0), texto, font=fuente, stroke_width=8)
    while caja[2] - caja[0] > W - 140 and tam > 40:     # que entre con margen (HELADERA se cortaba)
        tam = int(tam * 0.9)
        fuente = _fuente_ttf(tam)
        caja = d.textbbox((0, 0), texto, font=fuente, stroke_width=8)
    x = (W - (caja[2] - caja[0])) // 2 - caja[0]
    y = (H - (caja[3] - caja[1])) // 2 - caja[1]
    d.text((x, y), texto, font=fuente, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))
    salida.parent.mkdir(parents=True, exist_ok=True)
    fondo.save(salida, quality=92)
    return Foto(archivo=f"tarjeta:{salida.stem}", url="", ancho=W, alto=H, licencia=base.licencia,
                autor=base.autor, epigrafe=f"tarjeta: {texto}", pagina=base.pagina, articulo="tarjeta",
                ruta=str(salida), anio=base.anio)


def fabrica_tarjetas(g: Guion, anio: int, carpeta: Path, foto_de, agregar):
    """Para el corto (plan_rapido): una tarjeta nueva cuando ya no queda una foto que se pueda usar
    sin pasar de 2 cortes ni de 4 s seguidos (Santi, 2026-11-11: "usá una tarjeta como la de
    2022"). El texto, en orden y sin repetir: la palabra clave de ESA frase, el año, otra clave del
    guion. La base va rotando entre las fotos buenas del hecho. `foto_de(índice) -> Foto` y
    `agregar(Foto) -> índice` son del pool de quien llama (Fotos en la propuesta, dicts en el video)."""
    usados = set()
    for k in g.tarjetas_fotos or []:
        try:
            usados.add(foto_de(k).epigrafe.removeprefix("tarjeta: "))
        except (IndexError, AttributeError):
            pass

    def nueva(i: int, propia: bool = False) -> int | None:
        # Santi, 2026-11-23: como mucho MAX_TARJETAS por video (contando las del armado).
        if len(set(g.tarjetas_fotos or [])) >= MAX_TARJETAS:
            return None
        # `propia` (2026-11-20, la tarjeta «MELAZA» en la frase de Paint): solo la clave de ESA frase o el año, nunca
        # la clave de otra frase (la revisión final la marca como PH-02). El año, solo si esa frase lo dice.
        textos = [texto_tarjeta(g, i, anio, solo_clave=True), str(anio) if dice_anio(g, i, anio) else None] + (
            [] if propia else [c.upper() for c in g.claves])
        texto = next((t for t in textos if t and t not in usados), None)
        bases = [x for x in dict.fromkeys(generales(g) + [x for r in g.rankings() for x in r])
                 if x not in set(g.tarjetas_fotos or []) and x != VIDEO]
        if texto is None or not bases:
            return None
        base = foto_de(bases[len(usados) % len(bases)])
        t = tarjeta(base, texto, carpeta / f"tarjeta_extra_{len(usados) + 1:02d}.jpg")
        usados.add(texto)
        idx = agregar(t)
        g.tarjetas_fotos = list(g.tarjetas_fotos or []) + [idx]
        return idx

    return nueva


class SinFotosReales(NarrarError):
    """Ningún hecho del día llegó: se avisa y NO se reintenta solo (sería el mismo resultado)."""


class PocasFotos(NarrarError):
    """El hecho tiene menos de ilustrar.MIN_FOTOS_ABSOLUTO fotos de época: se prueba el siguiente.
    Trae lo ya armado (pool y guion con sus fotos) por si ninguno del día llega."""

    def __init__(self, pool: list[Foto], g: Guion, disponibles: int):
        super().__init__(f"solo {disponibles} fotos de época (mínimo {ilustrar.MIN_FOTOS_ABSOLUTO}): "
                         "paso al hecho siguiente")
        self.pool, self.guion, self.disponibles = pool, g, disponibles


# Gemini TTS lee a ~2,3 palabras/s (medido el 2026-09-28): con eso se estima cuánto dura cada frase
# para la hoja de aprobación. El video usa los tiempos reales de la voz.
PALABRAS_POR_S_VOZ = 2.3


def de_reserva(g: Guion, n_pool: int) -> list[int]:
    """Las fotos para cuando una frase se queda sin las suyas, en este orden:
    1. las del ARTÍCULO del hecho (regla de época, 2026-09-29: antes una del artículo, aunque se
       repita, que una moderna);
    2. las que Gemini puso para alguna frase (las vio y dijo que muestran algo de la historia),
       menos las modernas (más de MARGEN_EPOCA años después del hecho).
    Nunca las descartadas, y nunca resultados de búsqueda que nadie miró (así se coló una postal
    de Hamburgo en la prueba del 28/09). Si no queda nada, lo que quede del pool que no sea moderno."""
    # Santi, 2026-11-18 (capa 1, después de Colón): ninguna. Antes acá entraban las del artículo del hecho y las de
    # OTRAS frases (así se coló Atucha); ahora cada frase usa solo las fotos elegidas para ella, o una tarjeta.
    return []


def generales(g: Guion) -> list[int]:
    """Las fotos "del tema general" que puede usar una frase sin foto propia. Desde el 2026-11-17 (Santi, el Short de
    Colón: el artículo del hecho era "Argentina" y salieron Illia y Cristina Kirchner en Atucha) NINGUNA: cada foto
    tiene que mostrar lo que dice su frase; una frase sin foto alarga la de la frase anterior o va con una tarjeta."""
    return []


def duraciones_estimadas(g: Guion) -> list[float]:
    return [max(1.0, len(f.split()) / PALABRAS_POR_S_VOZ) for f in g.frases]


def plan_estimado(g: Guion, n_pool: int) -> list[tuple[int, int, float]]:
    """(frase, foto, segundos) con la duración estimada de cada frase: lo que muestra la hoja."""
    return ilustrar.tramos(g.fotos, duraciones_estimadas(g), g.rankings(), de_reserva(g, n_pool),
                           generales=generales(g))


# ---- 4. la hoja para aprobar -----------------------------------------------------------

def _fuente_ttf(tamano: int):
    from PIL import ImageFont

    for nombre in ("DejaVuSans.ttf", "arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                   "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default(tamano)


def filas_de_hoja(plan: list[tuple[int, int, float]], frases: list[str]) -> list[tuple[list[int], str]]:
    """Una fila por frase: las fotos que se ven mientras se dice (1, o 2 si se parte por los 6 s)
    y la frase. Es lo que dibuja la hoja: cada foto con su frase al lado."""
    filas: list[tuple[list[int], str]] = []
    for i, frase in enumerate(frases):
        fotos = list(dict.fromkeys(f for j, f, _ in plan if j == i))
        filas.append((fotos, frase))
    return filas


def hoja_de_guion(fotos: list[Foto], filas: list[tuple[list[int], str]], salida: Path,
                  ancho: int = 1000, miniatura: int = 220, videos: dict | None = None,
                  aviso: str = "") -> Path:
    """La hoja para aprobar: por cada frase, su foto (o sus dos fotos) numerada a la izquierda y la
    frase al lado (con tildes: por eso PIL y no cv2.putText). Una frase con video muestra el
    cuadro elegido con "VIDEO" y de dónde sale (`videos`: {frase: Video})."""
    import textwrap

    from PIL import Image, ImageDraw

    chica, grande = _fuente_ttf(26), _fuente_ttf(30)
    alto_mini = int(miniatura * 0.75)
    renglones = []
    for fila_i, (nums, frase) in enumerate(filas):
        x_texto = 12 + len(nums) * (miniatura + 8) + 8
        lineas = textwrap.wrap(frase, max(20, int((ancho - x_texto) / 14)))
        alto = max(alto_mini, 30 * len(lineas)) + 16
        fila = Image.new("RGB", (ancho, alto), (20, 20, 20))
        d = ImageDraw.Draw(fila)
        for k, n in enumerate(nums):
            if n == VIDEO:
                v = (videos or {}).get(fila_i)
                x = 12 + k * (miniatura + 8)
                if v is not None and v.frames:
                    img = Image.open(v.frames[0]).convert("RGB")
                    img = img.resize((miniatura, max(1, int(img.height * miniatura / img.width))))
                    fila.paste(img.crop((0, 0, miniatura, min(img.height, alto_mini))), (x, 8))
                d.rectangle((x, 8, x + 110, 48), fill=(170, 20, 20))
                d.text((x + 8, 10), "VIDEO", font=grande, fill=(255, 255, 255))
                etiqueta = v.etiqueta() if v is not None else "video"
                d.rectangle((x, alto_mini - 28, x + min(miniatura, 13 * len(etiqueta) + 12), alto_mini + 6),
                            fill=(0, 0, 0))
                d.text((x + 6, alto_mini - 26), etiqueta, font=chica, fill=(255, 220, 120))
                continue
            img = Image.open(fotos[n].ruta).convert("RGB")
            img = img.resize((miniatura, max(1, int(img.height * miniatura / img.width))))
            img = img.crop((0, 0, miniatura, min(img.height, alto_mini)))
            x = 12 + k * (miniatura + 8)
            fila.paste(img, (x, 8))
            d.rectangle((x, 8, x + (44 if n + 1 < 10 else 62), 48), fill=(0, 0, 0))
            d.text((x + 8, 10), str(n + 1), font=grande, fill=(255, 255, 255))
            # El año de la foto al lado de su número (regla de época): "s/f" si Commons no lo dice.
            anio = str(fotos[n].anio) if fotos[n].anio else "s/f"
            d.rectangle((x, alto_mini - 28, x + 16 * len(anio) + 12, alto_mini + 6), fill=(0, 0, 0))
            d.text((x + 6, alto_mini - 26), anio, font=chica, fill=(255, 220, 120))
        for j, l in enumerate(lineas):
            d.text((x_texto, 10 + 30 * j), l, font=chica, fill=(235, 235, 235))
        renglones.append(fila)
    if aviso:   # arriba de todo, en amarillo (ej. las fotos las eligió el modelo de respaldo)
        cartel = Image.new("RGB", (ancho, 56), (120, 90, 0))
        ImageDraw.Draw(cartel).text((12, 12), aviso, font=grande, fill=(255, 255, 255))
        renglones.insert(0, cartel)
    hoja = Image.new("RGB", (ancho, sum(r.height + 4 for r in renglones)), (0, 0, 0))
    y = 0
    for r in renglones:
        hoja.paste(r, (0, y))
        y += r.height + 4
    salida.parent.mkdir(parents=True, exist_ok=True)
    hoja.save(salida, quality=85)
    return salida


AVISO_RESPALDO = "⚠️ Fotos elegidas con el modelo de respaldo: revisalas"


def texto_aprobacion(e: Evento, g: Guion, fotos: list[Foto], fecha: date,
                     plan: list[tuple[int, int, float]] | None = None,
                     pool: list[Foto] | None = None) -> str:
    """El guion frase por frase con su foto (o sus fotos, si se parte) y el año de cada una, la
    idea que tiene que quedar clara, y los créditos que van a ir en la descripción. `fotos`: las
    del video en orden (créditos); `pool`: todas, en su numeración (para el año de cada número)."""
    fotos_por_num = dict(enumerate(pool or []))
    lineas = [f"📅 <b>Pequeña Historia · {fecha.day} de {MESES[fecha.month - 1]}</b> — {e.anio}",
              f"<i>{html.escape(e.texto[:200])}</i>",
              f"\n<b>Título:</b> {html.escape(g.titulo)}"]
    if g.pregunta_gancho:
        lineas.append(f"<b>Pregunta que deja el gancho:</b> {html.escape(g.pregunta_gancho)}")
    if g.idea_clave:
        lineas.append(f"<b>Tiene que quedar claro:</b> {html.escape(g.idea_clave)}")
    if g.fotos_respaldo:
        lineas.append(AVISO_RESPALDO)
    if g.sin_alternativa:
        lineas.append(f"⚠️ Ningún hecho de hoy llegó a {ilustrar.MIN_FOTOS_ABSOLUTO} fotos de la época: "
                      f"este es el que más tiene ({g.minimo_fotos}), así que se repiten. Si no te "
                      "convence, probá ✏️ o pedí otro con /efemeride.")
    elif g.minimo_fotos < ilustrar.MIN_FOTOS_DISTINTAS:
        lineas.append(f"⚠️ Solo hay {g.minimo_fotos} fotos de la época: algunas se repiten "
                      "(antes que usar fotos modernas).")
    from .videos_libres import Video

    lineas.append("\n<b>Guion</b> (foto → frase; 🎬 = video):")
    filas = filas_de_hoja(plan, g.frases) if plan else [([f], t) for f, t in zip(g.fotos, g.frases)]
    for i, (nums, texto) in enumerate(filas):
        if VIDEO in nums and str(i) in g.videos:
            v = Video.de_dict(g.videos[str(i)])
            lineas.append(f"🎬 {i + 1}. [video: {html.escape(v.etiqueta())} — "
                          f"{html.escape(v.titulo[:60])}] {html.escape(texto)}")
            continue
        cuales = "→".join(f"{n + 1} ({fotos_por_num[n].anio or 's/f'})" if n in fotos_por_num
                          else str(n + 1) for n in nums)
        accion = " (acción: sin video libre, va con foto)" if i in g.accion and g.con_videos else ""
        lineas.append(f"{i + 1}. [{cuales}] {html.escape(texto)}{accion}")
    palabras = len(g.texto.split())
    # Con la voz de Gemini (~2,3 palabras/s medido), acelerada hasta 45 s si hace falta.
    videos = [Video.de_dict(g.videos[str(i)]) for i, (nums, _) in enumerate(filas)
              if VIDEO in nums and str(i) in g.videos]
    lineas.append(f"\n{palabras} palabras, ~{min(palabras / PALABRAS_POR_S_VOZ, 45):.0f} s de voz, "
                  f"{len({n for nums, _ in filas for n in nums if n != VIDEO})} fotos distintas"
                  + (f", {len(videos)} con video" if videos else "") + ".")
    if g.con_videos:
        lineas.append("Con 🎬 N pasás una frase de foto a video o al revés.")
    from .videos_libres import creditos as creditos_videos

    lineas.append("\n<b>Créditos</b>\n" + html.escape(creditos(fotos))
                  + (("\n" + html.escape(creditos_videos(videos))) if videos else ""))
    return "\n".join(lineas)[:4000]


# ---- 5. el video ------------------------------------------------------------------------

def foco(ruta: Path) -> tuple[float, float]:
    """Hacia dónde va el zoom: el centro de la cara más grande, o el centro de la foto."""
    import cv2

    img = cv2.imread(str(ruta))
    if img is None:
        return 0.5, 0.5
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascada = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    caras = cascada.detectMultiScale(gris, 1.1, 5, minSize=(max(24, img.shape[1] // 25),) * 2)
    if len(caras) == 0:
        return 0.5, 0.5
    x, y, w, h = max(caras, key=lambda c: c[2] * c[3])
    return round((x + w / 2) / img.shape[1], 3), round((y + h / 2) / img.shape[0], 3)


def filtro_tramo(ancho: int, alto: int, W: int, H: int, frames: int, fx: float, fy: float,
                 blur: float, zoom_max: float = 1.10, fps: int = 30) -> str:
    """fit_blur con zoom suave para UNA foto: fondo borroso tapando el 9:16 y la foto entera al
    centro, acercándose de 100 % a `zoom_max` hacia (fx, fy).

    El zoom se hace sobre la foto agrandada 4×: zoompan redondea la posición a píxeles enteros y,
    a tamaño normal, eso se ve como un temblor. Con 4× el redondeo cae 4 veces más fino."""
    fw = W
    fh = int(round(alto * W / ancho / 2)) * 2
    if fh > H:                       # foto vertical: manda el alto
        fh, fw = H, int(round(ancho * H / alto / 2)) * 2
    z = f"min(1+{zoom_max - 1:.3f}*on/{max(frames - 1, 1)},{zoom_max})"
    x = f"max(0,min(iw-iw/zoom,{fx}*iw-iw/zoom/2))"
    y = f"max(0,min(ih-ih/zoom,{fy}*ih-ih/zoom/2))"
    return (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma={blur},setsar=1[fondo];"
            f"[1:v]scale={fw * 4}:{fh * 4}:flags=lanczos,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={fw}x{fh}:fps={fps},setsar=1[foto];"
            f"[fondo][foto]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]")


def armar_video(tramos: list[tuple[Path, float]], voz: Path, dir_subs: Path, salida: Path,
                render, fps: int = 30, parallax: bool = False,
                mapa: tuple[Path, float, float] | None = None, encuadres: dict | None = None,
                efecto: str = "", movimientos: list[str] | None = None, rehacer: set[int] | None = None) -> Path:
    """Una foto por frase (cada tramo dura lo que su frase), la voz, y los subtítulos + el año que
    ya están en `dir_subs/subs.ass`. Cada tramo se encodea aparte y al final se pegan."""
    from PIL import Image

    from .videos_libres import filtro_video

    W, H = render.ancho, render.alto
    partes = []
    for i, (foto, dur) in enumerate(tramos):
        frames = max(1, int(round(dur * fps)))
        ya = dir_subs / f"tramo_{i:02d}.mp4"
        if rehacer is not None and i not in rehacer and ya.exists():
            partes.append(ya)       # el corte no cambió (Santi, 2026-11-18): no se vuelve a encodear
            continue
        if Path(foto).suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
            # Un tramo de video: dura EXACTO lo de su frase (si es más corto, se repite).
            parte = dir_subs / f"tramo_{i:02d}.mp4"
            run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-stream_loop", "-1", "-i", str(Path(foto).resolve()),
                 "-filter_complex", filtro_video(W, H, render.blur_sigma, fps,
                                                 *(encuadres or {}).get(str(foto), (0.5, False))),
                 "-map", "[v]", "-an",
                 "-frames:v", str(frames), *X264, "-preset", render.x264_preset,
                 "-crf", "18", "-pix_fmt", "yuv420p", str(parte.resolve())])
            partes.append(parte)
            continue
        fx, fy = foco(foto)
        parte = dir_subs / f"tramo_{i:02d}.mp4"
        efecto = efecto or ("parallax" if parallax else "zoom")
        if efecto == "mov":
            # Formato corto: el cuadro armado (caras enteras, foto ≥ 72 % del alto) al doble de
            # tamaño y un movimiento distinto en cada corte (plan_rapido).
            import cv2

            from . import parallax as px

            cuadro = px.cuadro_fijo(Path(foto).resolve(), W, H, render.blur_sigma, (fx, fy))
            grande = dir_subs / f"mov_{i:02d}.png"
            cv2.imwrite(str(grande), cv2.resize(cuadro, (2 * W, 2 * H), interpolation=cv2.INTER_CUBIC))
            mov = (movimientos or [])[i] if movimientos and i < len(movimientos) else "in"
            run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(grande.resolve()),
                 "-vf", filtro_movimiento(frames, fx, fy, mov, W, H, fps),
                 "-frames:v", str(frames), *X264, "-preset", render.x264_preset,
                 "-crf", "18", "-pix_fmt", "yuv420p", str(parte.resolve())])
            partes.append(parte)
            continue
        if efecto == "fija":
            # Foto quieta: un solo cuadro (encuadre con caras enteras) repetido lo que dura el tramo.
            import cv2

            from . import parallax as px

            fija = dir_subs / f"fija_{i:02d}.png"
            cv2.imwrite(str(fija), px.cuadro_fijo(Path(foto).resolve(), W, H, render.blur_sigma, (fx, fy)))
            run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-loop", "1", "-framerate", str(fps), "-i", str(fija.resolve()),
                 "-frames:v", str(frames), *X264, "-preset", render.x264_preset,
                 "-tune", "stillimage", "-crf", "18", "-pix_fmt", "yuv420p", str(parte.resolve())])
            partes.append(parte)
            continue
        if efecto == "parallax":
            from . import parallax as px

            try:
                px.renderizar(Path(foto).resolve(), frames / fps, parte.resolve(), W, H,
                              render.blur_sigma, (fx, fy), fps=fps, preset=render.x264_preset)
                partes.append(parte)
                continue
            except RuntimeError as e:     # si falla, esa foto va con el zoom de siempre
                log.warning("parallax de %s falló (%s): va con zoom", foto, e)
        with Image.open(foto) as im:
            ancho, alto = im.size
        run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
             "-loop", "1", "-framerate", str(fps), "-t", f"{frames / fps:.3f}", "-i", str(foto.resolve()),
             "-i", str(foto.resolve()),
             "-filter_complex", filtro_tramo(ancho, alto, W, H, frames, fx, fy, render.blur_sigma,
                                             fps=fps),
             "-map", "[v]", "-frames:v", str(frames), *X264, "-preset",
             render.x264_preset, "-crf", "18", "-pix_fmt", "yuv420p", str(parte.resolve())])
        partes.append(parte)
    lista = dir_subs / "tramos.txt"
    lista.write_text("".join(f"file '{p.name}'\n" for p in partes), encoding="utf-8")
    salida.parent.mkdir(parents=True, exist_ok=True)
    # Audio limpio (media.cola_audio): del largo exacto del video, con los fundidos. La voz es un
    # solo audio continuo, así que acá no hay uniones de audio que cruzar. Va en un paso aparte
    # (media.preparar_audio): con la entrada concat, el mismo filtro dentro de este comando cortaba
    # el audio a 26,7 s en un video de 35,4 s.
    total = sum(max(1, int(round(d * fps))) for _, d in tramos) / fps
    audio = preparar_audio(voz, total, dir_subs / "audio_final.wav")
    entrada_mapa, filtro = [], "[0:v]ass=subs.ass[v]"
    if mapa:
        from .graficos import filtro_mapa

        entrada_mapa = ["-loop", "1", "-i", str(Path(mapa[0]).resolve())]
        filtro = ("[0:v]null[base];" + filtro_mapa(2, mapa[1], mapa[2], W, H).replace(
            "enable=", "shortest=1:enable=") + "[vm];[vm]ass=subs.ass[v]")
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", "tramos.txt", "-i", str(audio.resolve()), *entrada_mapa,
         "-filter_complex", filtro, "-map", "[v]", "-map", "1:a",
         *X264, "-preset", render.x264_preset, "-crf", str(render.crf),
         "-pix_fmt", "yuv420p", "-maxrate", f"{render.maxrate_kbps}k",
         "-bufsize", f"{2 * render.maxrate_kbps}k", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", str(salida.resolve())], cwd=dir_subs)
    return salida


# ---- de punta a punta: fecha → propuesta para aprobar -------------------------------------

@dataclass
class Propuesta:
    fecha: str
    evento: dict
    fotos: list[dict]                 # las del guion, en su numeración (1 = la primera)
    reserva: list[dict]               # para "🔁 cambiar foto N"
    guion: dict
    fuente: str = ""
    descartes: dict = field(default_factory=dict)
    destino: str = ""        # "facebook": el video aparte de Facebook (locales.py), no va a YouTube
    local: dict = field(default_factory=dict)   # lugar, país, tipo de historia, conmemoración


def proponer(wiki: Wiki, cliente, dia: date, carpeta: Path, avisar=log.info,
             correccion: str = "", saltear: int = 0, hecho: str = "", videos: bool = False,
             tope_fotos_s: float | None = None, hablado: bool = False,
             imagen_frase: bool = False, elector=None, elector_reintento=None,
             tema: str = "", corto: bool = False, texto=None, mas_video: bool = False,
             puntuador=None, piso: float | None = None, banco: list[dict] | None = None,
             solo_banco: bool = False, pesos: dict | None = None, evitar=(), sin_fotos=(),
             al_fallar_fotos=None, max_guiones: int = MAX_GUIONES,
             piso_fotos: float = UMBRAL_FOTOS_PISO, fecha_fuerte: float | None = None,
             fotos_primero: bool = False) -> Propuesta:
    """`fotos_primero` (Santi, 2026-11-25, efemerides.fotos_primero): las fotos se juntan y se describen ANTES del
    guion (fotos_primero.py); sin 8 buenas la historia no se usa y el guion se escribe a partir de ellas.

    `fecha_fuerte` (Santi, 2026-11-25: "el banco como fuente normal y la fecha solo cuando haya un hecho fuerte de
    marcas o videojuegos"): con banco, de los hechos del día solo entran los de marcas, empresas y videojuegos con ese
    puntaje o más; si no hay, directo al banco (sin el piso de 6).

    `sin_fotos` (Santi, 2026-11-23): artículos que ya fallaron por fotos (no se vuelven a intentar);
    `al_fallar_fotos(articulo, motivo)`: se llama cuando uno falla por fotos (o no pasa el chequeo previo), para
    anotarlo; con una historia del banco, también si falla el guion (Santi, 2026-11-24: "nunca una que ya falló").
    `max_guiones`: cuántas historias se intentan (la reserva, de a una: cada intento cuenta en su tope del día). Antes de pedir el guion, `fotos_previas` cuenta las fotos usables sin Claude (artículo + Commons).

    `solo_banco` (Santi, 2026-11-23, la reserva de tecnología): sin los hechos del día, directo del `banco` (historias
    que no dependen de la fecha). `pesos` ({subtema: bonus}, temas.py): los subtemas que más rinden van primero.

    `piso` y `banco` (Santi, 2026-11-15, "nunca un día sin video"): si ningún hecho de tecnología
    llega a PUNTAJE_TEC_MIN, sale el mejor si tiene `piso` (6) o más; si tampoco (o no hay ninguno),
    uno del banco de reserva (historias que no dependen de la fecha, puntuadas de antemano con 8+).

    `tema` (2026-11-12, efemerides.tema): solo hechos de ese tema (TEMAS); si no hay ninguno,
    SinTema (no sale video). `corto`: el formato corto (SISTEMA_GUION_CORTO, 20-30 s).

    Elige el evento, escribe el guion (con qué mostrar en cada frase), busca y elige las fotos
    de cada frase. Si un evento no llega a ilustrar.MIN_FOTOS_DISTINTAS fotos distintas que
    sirvan, pasa al siguiente del ranking.

    El ranking es de ELEGIDOS y no de 3: el 2026-09-27 los 3 primeros (Google, el ovni de Vorónezh,
    E=mc²) no llegaban a 4 fotos del artículo. Desde el 2026-09-28 las fotos salen también de
    Commons, frase por frase, así que eso pasa menos; cada evento que se intenta son 2 llamadas
    (guion y fotos), por eso el tope de MAX_GUIONES.

    `hecho`: solo los eventos cuyo texto lo contiene ("penicilina"): para rehacer uno a mano.
    `tope_fotos_s`: el tope de la búsqueda de fotos de cada hecho (efemerides.tope_fotos_min)."""
    from . import fuentes_fotos

    from . import bitacora

    fuentes_fotos.nueva_corrida()   # las fuentes caídas se cuentan en toda la propuesta
    bitacora.paso("busqueda")
    todos = [] if solo_banco else wiki.eventos("es", dia) + wiki.eventos("en", dia)
    candidatos, motivos = [], {}
    for e in todos:
        m = motivo_evento(e, date.today())
        if m:
            motivos[m] = motivos.get(m, 0) + 1
        elif not hecho or _norm(hecho) in _norm(e.texto):
            candidatos.append(e)
    if evitar:      # Santi, 2026-11-23: ninguna marca de Así Nació de esta semana
        from .marcas_semana import menciona as _menciona
        sacados = [e for e in candidatos if _menciona(e.texto + " " + " ".join(e.paginas), evitar)]
        candidatos = [e for e in candidatos if e not in sacados]
        if sacados:
            motivos["marca de Así Nació esta semana"] = len(sacados)
    avisar(f"{len(todos)} hechos del {dia:%d/%m}; {len(candidatos)} pasan el primer filtro {motivos}")
    if not candidatos and not solo_banco:
        raise NarrarError("Ningún hecho de hoy pasa el filtro de temas sensibles"
                          + (f" (con «{hecho}»)" if hecho else "") + ".")
    escritor = texto or cliente     # 2026-11-12: el texto con Claude; `cliente` (Gemini) para las fotos
    notas: dict = {}
    fila_elegir = bitacora.fila_actual()
    # Puntuar y elegir con Haiku (Santi, 2026-11-15: "Sonnet solo para escribir y corregir guiones").
    elegidos = elegir(puntuador or escritor, candidatos, tema=tema, notas=notas) if candidatos else []
    aviso_puntaje, del_banco = "", None

    def usar_banco(motivo: str) -> list[tuple[int, str]]:
        nonlocal del_banco, aviso_puntaje
        from . import temas as _t

        # Santi, 2026-11-23: del banco, primero los subtemas que más rinden (temas.py)
        # Santi, 2026-11-23: primero marcas, empresas y videojuegos (fotos fáciles: productos, logos de época,
        # consolas), después inventos y personas poco conocidas; dentro de cada grupo, por puntaje y por lo que rinde.
        def clave_banco(it):
            sub = it.get("subtema") or _t.subtema_tec(it.get("texto") or "")
            facil = 0 if tema != "tecnologia" or sub in SUBTEMAS_FACILES else 1
            return (facil, -(float(it.get("puntaje") or 0) + (pesos or {}).get(sub, 0.0)))

        sin = {_norm_art(x) for x in sin_fotos or ()}
        orden = sorted([it for it in banco or [] if _norm_art(it.get("articulo") or (it.get("paginas") or [""])[0])
                        not in sin], key=clave_banco)
        from .marcas_semana import menciona as _menciona

        for item in orden:
            if evitar and _menciona(str(item.get("texto") or "") + " " + " ".join(item.get("paginas") or []), evitar):
                continue
            sub = item.get("subtema") or _t.subtema_tec(item.get("texto") or "")
            if tema == "tecnologia" and float(item.get("puntaje") or 0) < minimo_tec(sub):
                continue        # inventos e internet del banco, solo los muy fuertes (Santi, 2026-11-23)
            ev = Evento(item.get("lang", "es"), int(item["anio"]), item["texto"], list(item["paginas"]))
            candidatos.append(ev)
            i = len(candidatos) - 1
            notas[i] = dict(item.get("notas") or {}, puntaje=item.get("puntaje"),
                            subtema=item.get("subtema") or _t.subtema_tec(item["texto"]))
            del_banco = del_banco or {}
            del_banco[i] = item.get("id")
            yield_ = (i, item.get("articulo") or ev.paginas[0])
            elegidos_banco.append(yield_)
        if elegidos_banco:
            aviso_puntaje = f"📦 del banco de reserva ({motivo})"
            avisar(f"banco de reserva: {len(elegidos_banco)} historias ({motivo})")
        return elegidos_banco

    elegidos_banco: list = []
    if tema and not elegidos:
        if not usar_banco("reserva de tecnología" if solo_banco else "hoy no hay ningún hecho del tema"):
            raise SinTema(f"Hoy no hay ningún hecho de «{tema}» que sirva y el banco de reserva está vacío.")
        elegidos = list(elegidos_banco)
    if tema == "tecnologia":
        # Puntaje propio (Santi, 2026-11-13): marca conocida, sorpresa, consecuencia y final; pasan
        # las de PUNTAJE_TEC_MIN (7,5) o más, de mejor a peor.
        for i, _ in elegidos:
            n = notas.get(i, {})
            avisar(f"  {n.get('puntaje', 0):.2f} {candidatos[i].anio} {candidatos[i].texto[:60]} {n}")
        flojos = [i for i, _ in elegidos
                  if notas.get(i, {}).get("puntaje", 0) < minimo_tec(notas.get(i, {}).get("subtema"))]
        if flojos:   # a la bitácora: los que no llegan, con su parte del pedido de puntaje
            parte = bitacora.costo_entre_activa(fila_elegir) / max(1, len(elegidos))
            for i in flojos:
                bitacora.descarte(f"{candidatos[i].anio} {candidatos[i].texto[:90]}",
                                  f"puntaje {notas.get(i, {}).get('puntaje', 0):.2f} < "
                                  f"{minimo_tec(notas.get(i, {}).get('subtema')):g}",
                                  "puntaje", costo=parte)
        todos_tec = list(elegidos)
        # Santi, 2026-11-23: los subtemas que más rinden en YouTube (temas.py) suman al ORDEN, no al mínimo
        elegidos = sorted([x for x in elegidos if x[0] not in flojos],
                          key=lambda x: -(notas.get(x[0], {}).get("puntaje", 0)
                                          + (pesos or {}).get(notas.get(x[0], {}).get("subtema"), 0.0)))
        if fecha_fuerte is not None and banco and not solo_banco:
            fuertes = [x for x in elegidos if notas.get(x[0], {}).get("subtema") in SUBTEMAS_FACILES
                       and (notas.get(x[0], {}).get("puntaje") or 0) >= fecha_fuerte]
            if len(fuertes) < len(elegidos):
                avisar(f"{len(elegidos) - len(fuertes)} hechos del día no son de marcas o videojuegos con "
                       f"{fecha_fuerte:g} o más: quedan {len(fuertes)}")
            elegidos = fuertes
            if not elegidos and not elegidos_banco and usar_banco(
                    f"hoy ningún hecho de marcas o videojuegos llega a {fecha_fuerte:g}".replace(".", ",")):
                elegidos = list(elegidos_banco)
        if not elegidos and not elegidos_banco:
            mejor = max(todos_tec, key=lambda x: notas.get(x[0], {}).get("puntaje", 0), default=None)
            nota = notas.get(mejor[0], {}).get("puntaje", 0) if mejor else 0
            if mejor and piso is not None and nota >= piso:
                elegidos = [mejor]
                aviso_puntaje = f"⚠️ salió con puntaje {nota:.1f} (mínimo {PUNTAJE_TEC_MIN:g})".replace(".", ",")
                avisar(f"ninguno llega a {PUNTAJE_TEC_MIN:g}: sale el mejor ({nota:.2f}, piso {piso:g})")
            elif not usar_banco(f"el mejor del día tenía {nota:.1f}".replace(".", ",")):
                raise SinTema(f"Hoy ningún hecho de tecnología llega a {PUNTAJE_TEC_MIN:g} (marca, sorpresa, "
                              "consecuencia y final): no saco uno flojo.")
            else:
                elegidos = list(elegidos_banco)
    avisar("Gemini eligió: " + " | ".join(f"{candidatos[i].anio} {candidatos[i].texto[:50]} [{a}]"
                                          for i, a in elegidos))
    descartes: dict = {}
    guiones = 0
    fallas: list[str] = []
    respaldo = None   # (evento, fuente, PocasFotos, fotos): el de más fotos de los que no llegaron a 4
    insuf = None      # (FotosInsuficientes, evento, fuente, índice): el que más se acercó al 70 %
    def intentar(i, articulo):
        nonlocal guiones, respaldo, insuf
        # El artículo del evento va primero: de ahí salen las fotos y el texto del guion.
        e = Evento(candidatos[i].lang, candidatos[i].anio, candidatos[i].texto,
                   [articulo] + [x for x in candidatos[i].paginas if x != articulo])
        fotos, desc = fotos_del_evento(wiki, e)
        for k, v in desc.items():
            descartes[k] = descartes.get(k, 0) + v
        avisar(f"{e.anio} {e.texto[:60]}: {len(fotos)} fotos del artículo pasan las reglas {desc}")
        if _norm_art(articulo) in {_norm_art(x) for x in sin_fotos or ()}:
            avisar(f"  {articulo}: ya falló por fotos antes, no lo intento")
            return None
        # Santi, 2026-11-23: contar las fotos usables ANTES de pagar el guion (sin Claude: artículo + Commons)
        previas = fotos_previas(wiki, e, fotos)
        if previas < PRECHEQUEO_MIN:
            motivo = f"solo {previas} fotos usables antes del guion (mínimo {PRECHEQUEO_MIN})"
            avisar(f"  {motivo}: no pido el guion")
            fallas.append(f"{e.anio}: {motivo}")
            bitacora.descarte(f"{e.anio} {e.texto[:90]}", motivo, "fotos", costo=0.0,
                              encontrado=f"{previas} fotos (artículo + Commons)")
            if al_fallar_fotos:
                al_fallar_fotos(articulo, motivo)
            return None
        fuente = texto_fuente(wiki, e)
        banco_f = None
        if fotos_primero:
            from . import fotos_primero as fp

            fila_f = bitacora.fila_actual()
            bitacora.paso("fotos")
            try:
                banco_f = fp.juntar(wiki, puntuador or escritor, e, fotos, carpeta,
                                    f"{e.texto} {e.paginas[0].replace('_', ' ')}. {fuente[:900]}", avisar)
            except (fp.FotosPrevias, NarrarError) as err:
                avisar(f"  {err}: no pido el guion")
                fallas.append(f"{e.anio}: {err}")
                bitacora.descarte(f"{e.anio} {e.texto[:90]}", str(err), "fotos", desde_fila=fila_f,
                                  encontrado="fotos primero (Haiku)")
                if al_fallar_fotos:
                    al_fallar_fotos(articulo, str(err))
                return None
        guiones += 1
        fila_h, g = bitacora.fila_actual(), None
        try:
            bitacora.paso("guion")
            g = escribir_guion(escritor, e, fuente, correccion, hablado=hablado and not corto,
                               sistema=SISTEMA_GUION_CORTO if corto else None, corto=corto,
                               contexto=(NO_ES_DE_HOY if del_banco and i in del_banco else "")
                               + (banco_f.contexto() if banco_f else ""))
            if banco_f:
                avisar(f"  fotos primero: el guion eligió foto en {banco_f.tomar_de_mostrar(g)} de {len(g.frases)} "
                       "frases")
            g.imagen_frase = imagen_frase or corto      # efemerides.imagen_frase (2026-11-10)
            g.mas_video = mas_video                     # efemerides.estilo_nuevo (2026-11-14)
            bitacora.paso("fotos")
            pool, g = fotos_con_control(wiki, cliente, e, g, fotos, carpeta, avisar, videos=videos,
                                        elector=elector, elector_reintento=elector_reintento,
                                        tope_s=tope_fotos_s, primero=banco_f,
                                        reescribir=lambda g_, idx, pool_, forz=None: reescribir_frases_con_foto(
                                            puntuador or escritor, e, fuente, g_, idx, pool_, avisar, forz))
        except PocasFotos as pocas:
            # Menos de 4 fotos de época: al siguiente. Se guarda el que más tenga, por si ninguno llega.
            avisar(f"  {pocas}")
            fallas.append(f"{e.anio}: {pocas}")
            bitacora.descarte(f"{e.anio} {e.texto[:90]}", str(pocas), "fotos", desde_fila=fila_h,
                              buscado=list(getattr(pocas.guion, "mostrar", []) or []),
                              encontrado=f"{pocas.disponibles} fotos de época que sirven ({len(pocas.pool)} en el pool)",
                              intentos=getattr(pocas, "intentos", None))
            if respaldo_sirve(pocas) and (respaldo is None or pocas.disponibles > respaldo[3]):
                respaldo = (e, fuente, pocas, pocas.disponibles)
            if al_fallar_fotos:
                al_fallar_fotos(articulo, str(pocas))
            return None
        except NarrarError as err:
            avisar(f"  no salió: {err}")
            fallas.append(f"{e.anio}: {err}")
            if isinstance(err, FotosInsuficientes) and (insuf is None or err.pct > insuf[0].pct):
                insuf = (err, e, fuente, i)
            en_fotos = g is not None
            if al_fallar_fotos and (en_fotos or (del_banco and i in del_banco)):
                al_fallar_fotos(articulo, str(err))
            bitacora.descarte(f"{e.anio} {e.texto[:90]}", str(err), "fotos" if en_fotos else "guion", desde_fila=fila_h,
                              buscado=list(g.mostrar) if en_fotos else None,
                              encontrado=f"{len(fotos)} fotos del artículo; {str(err)[:150]}" if en_fotos else "",
                              intentos=getattr(err, "intentos", None))
            return None
        for k in g.descartadas:        # para poder juzgar si el descarte visual es razonable
            if 0 <= k < len(pool):
                avisar(f"    descartada {k + 1}: {pool[k].epigrafe[:90]}")
        n = notas.get(i) or {}
        local = ({"puntaje": n.get("puntaje"), "puntajes": {k: n.get(k) for k in CRITERIOS_TEC},
                  "subtema": n.get("subtema")} if tema else {})
        if del_banco and i in del_banco:
            local["banco_id"] = del_banco[i]
        if aviso_puntaje:
            local["aviso"] = aviso_puntaje
        return Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in pool],
                         reserva=[], guion=g.a_dict(), fuente=fuente[:20000], descartes=descartes,
                         local=local)

    # Plan B de tecnología (Santi, 2026-11-18: el Minecraft del 18/11 quedó en 49 % de fotos reales y no salió nada):
    # si los de PUNTAJE_TEC_MIN fallan por fotos o guion, se prueban los demás desde el piso (6), y después el banco.
    cola = list(elegidos[saltear:])
    extra_aviso: dict = {}
    if tema == "tecnologia" and piso is not None and not (fecha_fuerte is not None and banco):
        ya = {x[0] for x in cola}
        for x in sorted(todos_tec, key=lambda x: -notas.get(x[0], {}).get("puntaje", 0)):
            nota = notas.get(x[0], {}).get("puntaje", 0) or 0
            if x[0] not in ya and nota >= piso:
                cola.append(x)
                extra_aviso[x[0]] = f"⚠️ salió con puntaje {nota:.1f} (mínimo {PUNTAJE_TEC_MIN:g})".replace(".", ",", 1)
    for i, articulo in cola:
        if guiones >= max_guiones:
            break
        if i in extra_aviso:
            aviso_puntaje = extra_aviso[i]
        prop = intentar(i, articulo)
        if prop is not None:
            return prop
    # Santi, 2026-11-20: tecnología sale todos los días; si los hechos del día no pasan las fotos, el banco ANTES que
    # bajar el mínimo de fotos reales (el 20/11 salió Windows 1.0 con 51 % y una tarjeta mal, y quedó retenido).
    if tema == "tecnologia" and banco and not elegidos_banco and usar_banco("los de hoy no llegaron a las fotos"):
        guiones = 0
        for i, articulo in list(elegidos_banco):
            if guiones >= max_guiones:
                break
            prop = intentar(i, articulo)
            if prop is not None:
                return prop
    if insuf and not respaldo and aceptar_relajado(insuf[0], avisar, piso_fotos):
        err, e, fuente, i = insuf
        n = notas.get(i) or {}
        local = ({"puntaje": n.get("puntaje"), "puntajes": {k: n.get(k) for k in CRITERIOS_TEC},
                  "subtema": n.get("subtema")} if tema else {})
        if del_banco and i in del_banco:
            local["banco_id"] = del_banco[i]
        if aviso_puntaje:
            local["aviso"] = aviso_puntaje
        return Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in err.pool],
                         reserva=[], guion=err.guion.a_dict(), fuente=fuente[:20000], descartes=descartes,
                         local=local)
    if respaldo:
        e, fuente, pocas, n = respaldo
        avisar(f"Ningún hecho llegó a {ilustrar.MIN_FOTOS_ABSOLUTO} fotos de época: uso {e.anio} "
               f"({n} fotos), con aviso")
        pocas.guion.sin_alternativa = True
        return Propuesta(fecha=dia.isoformat(), evento=e.a_dict(),
                         fotos=[f.a_dict() for f in pocas.pool], reserva=[],
                         guion=pocas.guion.a_dict(), fuente=fuente[:20000], descartes=descartes)
    # Con la causa de cada uno: el 28/09 decía "no llegó a 6 fotos" cuando lo que falló fue el guion.
    raise SinFotosReales(f"Ninguno de los {len(elegidos)} hechos elegidos salió ({guiones} intentados): "
                         "no armo un video malo. " + " | ".join(fallas)[:600])


def texto_fuente(wiki: Wiki, e: Evento) -> str:
    """El texto del artículo del hecho; si es en inglés, más el equivalente en castellano (el
    guion va en castellano y se valida contra los dos)."""
    fuente = wiki.texto(e.lang, e.paginas[0])
    if e.lang == "en":
        es = wiki.en_espanol(e.paginas[0])
        if es:
            fuente += "\n" + wiki.texto("es", es)
    return fuente


def rehacer_guion(p: Propuesta, wiki: Wiki, cliente, carpeta: Path, correccion: str,
                  avisar=log.info, hablado: bool = False, elector=None,
                  elector_reintento=None, texto=None) -> Propuesta:
    """✏️: el guion de nuevo con la corrección, y las fotos de sus frases otra vez. El pool de antes
    se conserva (los números no cambian) y lo ya descartado sigue descartado."""
    e = Evento(**p.evento)
    anterior = Guion.de_dict(p.guion)
    g = escribir_guion(texto or cliente, e, p.fuente, correccion=correccion, anterior=anterior.texto,
                       hablado=hablado and not anterior.corto,
                       sistema=SISTEMA_GUION_CORTO if anterior.corto else None, corto=anterior.corto)
    g.imagen_frase = anterior.imagen_frase
    g.mas_video = anterior.mas_video
    fotos, _ = fotos_del_evento(wiki, e)
    try:
        pool, g = fotos_con_control(wiki, cliente, e, g, fotos, carpeta, avisar,
                                    pool=[Foto.de_dict(f) for f in p.fotos],
                                    descartadas=set(anterior.descartadas), videos=anterior.con_videos,
                                    elector=elector, elector_reintento=elector_reintento)
    except PocasFotos as pocas:   # es el hecho que ya se eligió: se sigue con lo que haya, con aviso
        if not respaldo_sirve(pocas):
            raise SinFotosReales(f"{pocas}; ni con la segunda búsqueda llega al 70 % de fotos reales")
        pool, g = pocas.pool, pocas.guion
        g.sin_alternativa = anterior.sin_alternativa
    except FotosInsuficientes as f:
        if not aceptar_relajado(f, avisar):
            raise SinFotosReales(f"{f}, también con la segunda búsqueda: no armo el video") from f
        pool, g = f.pool, f.guion
    return Propuesta(fecha=p.fecha, evento=p.evento, fotos=[f.a_dict() for f in pool],
                     reserva=p.reserva, guion=g.a_dict(), fuente=p.fuente, descartes=p.descartes)


# La música de fondo vive en musica.py (biblioteca, elección por tono, mezcla con ducking).


VIDEO = -1   # en un plan, (frase, VIDEO, segundos) = esa frase entera va con su video
MAPA = -2    # estilo nuevo: (frase, MAPA, segundos) = el mapa acercándose hasta el lugar


def con_videos(plan: list[tuple[int, int, float]], g: Guion) -> list[tuple[int, int, float]]:
    """Las frases que van con video pasan a UN tramo del largo de toda la frase (el video se corta
    a lo que dura su frase; la regla de 6 s es para las fotos quietas)."""
    usar = {i for i in g.con_video if str(i) in g.videos}
    if not usar:
        return plan
    out, hecho = [], set()
    for i, f, s in plan:
        if i not in usar:
            out.append((i, f, s))
        elif i not in hecho:
            hecho.add(i)
            out.append((i, VIDEO, round(sum(x for j, _, x in plan if j == i), 3)))
    return out


CORTE_MAX_S, CORTE_MIN_S = 4.0, 2.5     # formato corto: un cambio de imagen cada 2,5-4 s (Santi, 2026-11-10)
FOTO_MAX_S = 4.0       # ninguna foto más que esto seguida (Santi, 2026-11-11)
GANCHO_MAX_S = 2.5     # la primera, la del gancho
# Santi, 2026-11-25: la cantidad de cortes se ajusta a las fotos buenas que hay; con pocas, cortes más largos con
# movimiento de cámara (hasta el tope de la regla fija 1, 6 s) antes que tarjetas de relleno
CORTE_LARGO_MAX_S = ilustrar.MAX_TRAMO_S
MOVIMIENTOS = ("in", "der", "out", "izq")
MONTAJE_CORTES, MONTAJE_MIN_S = 3, 0.6   # estilo nuevo: el gancho en 3 imágenes con golpe de zoom


def plan_rapido(plan: list[tuple[int, int, float]], g: Guion,
                max_apariciones: int = ilustrar.MAX_APARICIONES, nueva_tarjeta=None,
                faltas: list | None = None,
                montaje: bool = False) -> tuple[list[tuple[int, int, float]], list[str]]:
    """Formato corto: cada tramo se parte en cortes de 2,5 a 4 s. Los cortes de una frase alternan
    entre SUS fotos (las que el modelo puso para esa frase: la imagen sigue siendo lo que se dice).

    Topes duros (Santi, 2026-11-11): NINGUNA foto más de FOTO_MAX_S (4 s) seguida en pantalla,
    aunque el corte quede de menos de 2,5 s; la primera (la del gancho) hasta GANCHO_MAX_S (2,5 s);
    y ninguna en más de `max_apariciones` (2) CORTES en todo el video (el acta de Cartagena salía
    en 3 cortes, 5,9 s seguidos al principio: con otro movimiento se ve igual la misma foto). Para
    cada corte: otra foto de esa frase, una del tema general del hecho (`generales`), una tarjeta
    ya hecha o, con `nueva_tarjeta(frase) -> índice | None`, una tarjeta nueva (palabra clave o
    año, "como la de 2022"). Recién si no queda nada, la que menos se usó, y ese corte va a
    `faltas`. Devuelve el plan y el movimiento de cada corte ("" en los videos)."""
    rk = g.rankings()
    hechas = [x for x in (g.tarjetas_fotos or [])]
    # Santi, 2026-11-17 (Colón): cada foto muestra lo que dice SU frase. Nada de fotos "del tema general" en los cortes.
    gen: list[int] = []
    out, movs = [], []
    veces: dict[int, int] = {}
    m = 0
    seguido = 0.0          # cuánto lleva en pantalla la foto de ahora, sin cortar a otra

    def partes(s: float) -> list[float]:
        n = max(1, math.ceil(s / CORTE_MAX_S - 1e-9))
        while n > 1 and s / n < CORTE_MIN_S and s / (n - 1) <= CORTE_MAX_S + 1e-9:
            n -= 1
        return [round(s / n, 3)] * n

    def tope_de(x) -> float:
        # Santi, 2026-11-25: una foto puede seguir con otro movimiento hasta 6 s antes que cortar a una tarjeta
        return GANCHO_MAX_S if all(o[1] == x for o in out) else CORTE_LARGO_MAX_S

    def sirve(x, t, previa) -> bool:
        if x is None or x == VIDEO or veces.get(x, 0) >= max_apariciones:
            return False
        return x != previa or seguido + t <= tope_de(x) + 1e-9

    def segun_fotos(trozos: list[float], propias: list[int], previa) -> list[float]:
        """Tantos cortes como fotos de la frase que todavía se pueden usar (Santi, 2026-11-25): con pocas, cortes más
        largos (hasta CORTE_LARGO_MAX_S) en vez de tarjetas de relleno."""
        libres = [x for x in dict.fromkeys(propias) if x is not None and x != VIDEO
                  and veces.get(x, 0) < max_apariciones]
        n = max(1, len(libres))
        if len(trozos) <= n:
            return trozos
        total = round(sum(trozos), 3)
        # el gancho corta a los 2,5 s solo si la frase tiene otra foto; con una sola, la sigue con movimiento
        primero = trozos[0] if not out and len(trozos) > 1 and trozos[0] == GANCHO_MAX_S and n > 1 else None
        resto = round(total - primero, 3) if primero else total
        k = max(1, n - (1 if primero else 0))
        while resto / k > CORTE_LARGO_MAX_S + 1e-9:
            k += 1
        partes_ = [round(resto / k, 3)] * k
        partes_[-1] = round(resto - sum(partes_[:-1]), 3)     # sin perder milésimas: el total no cambia
        return ([primero] if primero else []) + partes_

    for i, f, s in plan:
        if f == VIDEO:
            out.append((i, f, s))
            movs.append("")
            seguido = 0.0
            continue
        if montaje and not out and i == 0:
            # Estilo nuevo (Santi, 2026-11-14): el gancho como montaje rápido de 3 imágenes con golpe
            # de zoom: la más impactante primero (es la primera del ranking), después otras de la
            # frase o del tema general. Cada una cuenta como aparición (ninguna en más de 2 cortes).
            n = max(1, min(MONTAJE_CORTES, int(s // MONTAJE_MIN_S)))
            # Si la frase del gancho tiene pocas, la mejor de cada frase siguiente (un adelanto).
            cand = list(dict.fromkeys([f] + [x for x in (rk[i] if i < len(rk) else []) if x != VIDEO]))
            cand = [x for x in cand if x is not None and x >= 0][:n] or [f]
            trozos = [round(s / len(cand), 3)] * len(cand)
            for x, t in zip(cand, trozos):
                veces[x] = veces.get(x, 0) + 1
                out.append((i, x, t))
                movs.append("golpe")
            seguido = trozos[-1]
            continue
        if not out and s > GANCHO_MAX_S + 1e-9:
            trozos = [GANCHO_MAX_S] + partes(round(s - GANCHO_MAX_S, 3))
        else:
            trozos = partes(s)
        propias = [f] + [x for x in (rk[i] if i < len(rk) else []) if x != f]
        trozos = segun_fotos(trozos, propias, out[-1][1] if out else None)
        for k, t in enumerate(trozos):
            previa = out[-1][1] if out else None
            rot = propias[k % len(propias):] + propias[:k % len(propias)]
            orden = [x for x in rot if x != previa] + [x for x in gen if x != previa] + \
                [x for x in hechas if x != previa] + [previa]
            quiere = next((x for x in orden if sirve(x, t, previa)), None)
            if quiere is None and nueva_tarjeta is not None:
                nueva = nueva_tarjeta(i)
                if nueva is not None:
                    hechas.append(nueva)
                    quiere = nueva
            if quiere is None:      # no queda nada: la que menos se usó (y queda anotado)
                if faltas is not None:
                    faltas.append(i)
                opciones = [x for x in dict.fromkeys(propias + hechas) if x != previa] or [f]
                quiere = min(opciones, key=lambda x: veces.get(x, 0))
            veces[quiere] = veces.get(quiere, 0) + 1
            if quiere != previa:
                seguido = 0.0
            seguido += t
            mov = MOVIMIENTOS[m % len(MOVIMIENTOS)]
            m += 1
            if out and out[-1][1] == quiere and movs[-1] == mov:
                mov = MOVIMIENTOS[m % len(MOVIMIENTOS)]
                m += 1
            out.append((i, quiere, t))
            movs.append(mov)
    return out, movs


def seguidos_max(plan: list[tuple[int, int, float]]) -> tuple[float, float]:
    """(lo más que una foto queda seguida en pantalla, lo que dura la primera): para el control."""
    largos, actual, previa = [], 0.0, object()
    for _, f, s in plan:
        if f == previa and f != VIDEO:
            actual += s
        else:
            if actual:
                largos.append(actual)
            actual, previa = s, f
    if actual:
        largos.append(actual)
    return (max(largos) if largos else 0.0), (largos[0] if largos else 0.0)


def filtro_movimiento(frames: int, fx: float, fy: float, mov: str, W: int, H: int, fps: int = 30,
                      zoom: float = 1.08) -> str:
    """zoompan sobre el cuadro ya armado (foto sobre su fondo, al doble de tamaño): acercarse hacia
    la cara (in), alejarse (out) o un paneo con el zoom puesto (der/izq)."""
    t = f"on/{max(frames - 1, 1)}"
    dz = f"{zoom - 1:.3f}"
    z = {"in": f"1+{dz}*{t}", "out": f"{zoom:.3f}-{dz}*{t}",
         # Golpe de zoom (estilo nuevo): entra de 1,25 a 1,12 en 6 cuadros y sigue acercándose lento.
         "golpe": f"if(lt(on,6),1.25-0.13*on/6,1.12+0.06*{t})"}.get(mov, f"{zoom:.3f}")
    cx = f"clip(iw*{fx:.3f}-iw/zoom/2,0,iw-iw/zoom)"
    cy = f"clip(ih*{fy:.3f}-ih/zoom/2,0,ih-ih/zoom)"
    x = {"der": f"(iw-iw/zoom)*{t}", "izq": f"(iw-iw/zoom)*(1-{t})"}.get(mov, cx)
    return f"zoompan=z='{z}':x='{x}':y='{cy}':d={frames}:s={W}x{H}:fps={fps},setsar=1,format=yuv420p"


MAPA_ANTES_S, MAPA_DESPUES_S = 1.8, 0.5   # el mapa arranca 1,8 s antes de que se diga el lugar


def momento_de_palabra(palabras: list, texto: str) -> float | None:
    """Cuándo empieza a decirse `texto` (su primera palabra) en la voz, o None."""
    clave = _norm(str(texto or "").split(",")[0]).split()
    if not clave:
        return None
    norm = [_norm(getattr(w, "texto", "")).strip(".,;:!?¡¿«»\"'") for w in palabras]
    for k in range(len(norm) - len(clave) + 1):
        if norm[k:k + len(clave)] == clave:
            return float(palabras[k].inicio)
    return None


def insertar_tramo(plan: list, movs: list | None, desde: float, dur: float, item: int, mov: str):
    """Mete (frase, item, dur) en el plan a partir del segundo `desde`, recortando lo que tapa. El
    largo total no cambia. La frase del tramo nuevo es la del corte donde cae."""
    movs = list(movs) if movs is not None else [""] * len(plan)
    out, out_m, t, puesto = [], [], 0.0, False
    hasta = desde + dur
    for (i, f, s), m in zip(plan, movs):
        a, b = t, t + s
        t = b
        if b <= desde or a >= hasta:
            out.append((i, f, s))
            out_m.append(m)
            continue
        if a < desde:
            out.append((i, f, round(desde - a, 3)))
            out_m.append(m)
        if not puesto:
            out.append((i, item, round(dur, 3)))
            out_m.append(mov)
            puesto = True
        if b > hasta:
            out.append((i, f, round(b - hasta, 3)))
            out_m.append(m)
    # Pedacitos de menos de 0,4 s: se los come el corte de al lado que no es el tramo nuevo (el tramo
    # nuevo tiene que durar justo lo que su video).
    limpio, limpio_m, arrastre = [], [], 0.0
    for x, m in zip(out, out_m):
        if x[1] != item and x[2] < 0.4:
            if limpio and limpio[-1][1] != item:
                limpio[-1] = (limpio[-1][0], limpio[-1][1], round(limpio[-1][2] + x[2], 3))
            else:
                arrastre += x[2]
            continue
        if arrastre and x[1] != item:
            x = (x[0], x[1], round(x[2] + arrastre, 3))
            arrastre = 0.0
        limpio.append(x)
        limpio_m.append(m)
    if arrastre and limpio:      # quedó al final después del tramo nuevo: se lo come el anterior
        j = max(k for k, x in enumerate(limpio) if x[1] != item) if any(x[1] != item for x in limpio) else None
        if j is not None:
            limpio[j] = (limpio[j][0], limpio[j][1], round(limpio[j][2] + arrastre, 3))
    return limpio, limpio_m


# ---- tarjetas con un número, justo cuando la voz lo dice (Santi, 2026-11-23: en Meucci «1876» apareció mientras
# la voz decía 1854) -------------------------------------------------------------------------------------------------
TARJETA_TOLERANCIA_S = 0.15     # la tarjeta puede entrar hasta esto antes de que se diga el número (un cuadro y algo)
_NUMERO = re.compile(r"\d[\d.,]*\d|\d")


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", str(t or ""))


def numeros_de_tarjeta(foto) -> list[str]:
    """Los números de una tarjeta ("tarjeta: 1876" → ["1876"]); [] si no es tarjeta o no tiene números."""
    if not es_tarjeta(foto):
        return []
    epi = foto.get("epigrafe") if isinstance(foto, dict) else getattr(foto, "epigrafe", "")
    return [_digitos(x) for x in _NUMERO.findall(str(epi or "").removeprefix("tarjeta:"))]


def momentos_de_numero(palabras: list, num: str) -> list[float]:
    """Cuándo dice la voz `num` (todas las veces), por los tiempos de los subtítulos."""
    return [float(w.inicio) for w in palabras if _digitos(getattr(w, "texto", "")) == num and num]


def tarjetas_a_destiempo(plan: list, fotos: list, palabras: list) -> list[int]:
    """Los cortes con una tarjeta de un número que aparece ANTES de que la voz lo diga (o que la voz no dice mientras
    está en pantalla). Sin Claude: lo controla la revisión final."""
    malos, t = [], 0.0
    for k, (_i, f, s) in enumerate(plan):
        a, b = t, t + s
        t = b
        if not (0 <= f < len(fotos)):
            continue
        for num in numeros_de_tarjeta(fotos[f]):
            if not any(a - TARJETA_TOLERANCIA_S <= m < b for m in momentos_de_numero(palabras, num)):
                malos.append(k)
                break
    return malos


def alinear_tarjetas(plan: list, movs: list | None, fotos: list, palabras: list, avisar=log.info):
    """Mueve cada tarjeta con un número al momento en que la voz lo dice: lo que queda antes en ese corte vuelve a la
    imagen anterior; si la voz no lo dice en ese corte pero sí después, la tarjeta va ahí (insertar_tramo); si no lo
    dice nunca, ese corte vuelve a la imagen anterior. El largo total no cambia."""
    movs = list(movs) if movs is not None else [""] * len(plan)
    for _ in range(len(plan) + 2):
        malos = tarjetas_a_destiempo(plan, fotos, palabras)
        if not malos:
            break
        k = malos[0]
        i, f, s = plan[k]
        a = sum(x[2] for x in plan[:k])
        b = a + s
        previa = next((plan[j][1] for j in range(k - 1, -1, -1) if not (0 <= plan[j][1] < len(fotos)
                       and es_tarjeta(fotos[plan[j][1]]))), None)
        if previa is None:
            previa = next((x[1] for x in plan[k + 1:] if not (0 <= x[1] < len(fotos) and es_tarjeta(fotos[x[1]]))), f)
        num = numeros_de_tarjeta(fotos[f])[0]
        momentos = momentos_de_numero(palabras, num)
        luego = next((m for m in momentos if m >= a - TARJETA_TOLERANCIA_S), None)
        plan[k] = (i, previa, s)          # el corte vuelve a la imagen anterior
        if luego is not None and luego < sum(x[2] for x in plan):
            total = sum(x[2] for x in plan)
            dur = round(min(max(s, 1.5), FOTO_MAX_S, total - luego), 3)
            if dur >= 0.5:
                plan, movs = insertar_tramo(plan, movs, luego, dur, f, movs[k] if k < len(movs) else "in")
                avisar(f"tarjeta «{num}»: la corrí a {luego:.1f} s, cuando la voz lo dice (estaba en {a:.1f} s)")
                continue
        avisar(f"tarjeta «{num}»: la voz no lo dice después de {a:.1f} s; ese corte vuelve a la imagen anterior")
    return plan, movs


def plan_de(p: Propuesta, duraciones: list[float] | None = None) -> list[tuple[int, int, float]]:
    """(frase, foto, segundos) de la propuesta: con las duraciones reales de la voz, o estimadas.
    Las frases con video salen como (frase, VIDEO, segundos de la frase)."""
    g = Guion.de_dict(p.guion)
    if duraciones is None:
        return con_videos(plan_estimado(g, len(p.fotos)), g)
    return con_videos(ilustrar.tramos(g.fotos, duraciones, g.rankings(), de_reserva(g, len(p.fotos)),
                                      generales=generales(g)), g)


def videos_en_orden(p: Propuesta, plan: list[tuple[int, int, float]] | None = None):
    from .videos_libres import Video

    g = Guion.de_dict(p.guion)
    return [Video.de_dict(g.videos[str(i)]) for i, f, _ in (plan or plan_de(p)) if f == VIDEO]


SISTEMA_VIDEO = """Elegís el video para UNA frase de un video corto narrado de historia. Te paso la
frase, el año del hecho y videos candidatos V1, V2…; de cada uno ves 3 cuadros (las imágenes, en
orden: 3 por video). En `video` poné el número del que muestra LO QUE DICE la frase (0 si ninguno:
mejor una foto que un video que no tiene nada que ver) y en `momento` su mejor cuadro (1, 2 o 3).
En `video_de_epoca` confirmá que no es un anacronismo (un cohete moderno no sirve para 1957).
Nada de dibujos animados, animaciones ni ilustraciones (0), salvo que la frase hable de eso; tampoco
videos con texto encima tapando la imagen ni recreaciones por computadora.
Respondé solo con el JSON pedido."""

SCHEMA_VIDEO = {"type": "OBJECT",
                "properties": {"se_ve": {"type": "STRING"}, "video": {"type": "INTEGER"},
                               "momento": {"type": "INTEGER"}, "video_de_epoca": {"type": "BOOLEAN"}},
                "required": ["se_ve", "video", "momento", "video_de_epoca"]}


def revisar_video(cliente, frase: str, anio: int, presente: bool, vs: list, avisar=log.info):
    """UNA llamada: Gemini mira los 3 cuadros de cada candidato con la frase y la época y elige uno
    (o ninguno). Es lo mismo que pasa en la llamada de las fotos, para una frase suelta (🎬)."""
    if not vs:
        return None
    lineas = [f"EL HECHO ES DE {anio}.", f"FRASE{' (habla de hoy)' if presente else ''}: {frase}",
              "VIDEOS:"]
    imagenes = []
    for k, v in enumerate(vs, 1):
        tipo = "de archivo" if v.de_archivo else "stock"
        lineas.append(f"V{k}: {v.titulo[:90]} ({tipo}, {v.etiqueta()}, {v.duracion:.0f} s) — "
                      f"imágenes {len(imagenes) + 1} a {len(imagenes) + len(v.frames)}")
        imagenes += [_jpeg_chico(Path(fr), 384) for fr in v.frames]
    d = json.loads(cliente.json(SISTEMA_VIDEO, "\n".join(lineas), SCHEMA_VIDEO, temperatura=0.2,
                                imagenes=imagenes))
    avisar(f"    🎬 revisión: se ve {str(d.get('se_ve'))[:80]}")
    return video_elegido({0: d}, {0: vs}, [presente], avisar).get(0)


def alternar_video(p: Propuesta, n: int, carpeta: Path, buscador=None, avisar=log.info,
                   cliente=None) -> str:
    """"🎬 frase N": de video a foto o de foto a video. Si la frase no tiene video elegido, lo busca
    en el momento y Gemini mira los cuadros de los candidatos con la frase y la época
    (`revisar_video`); si ninguno corresponde, queda la foto. Devuelve qué pasó, en castellano."""
    g, e = Guion.de_dict(p.guion), Evento(**p.evento)
    i = n - 1
    if not 0 <= i < len(g.frases):
        return "Esa frase no existe."
    if i in g.con_video:
        g.con_video = [x for x in g.con_video if x != i]
        p.guion = g.a_dict()
        return f"Frase {n}: vuelve a foto."
    if str(i) not in g.videos:
        halladas = buscar_videos(g, e.anio, carpeta, buscador, avisar, frases=[i],
                                 tema=e.paginas[0] if e.paginas else "").get(i) or []
        if not halladas:
            return f"No encontré un video libre para la frase {n} (queda con foto)."
        if cliente is None:
            return f"Sin Gemini no puedo revisar los videos de la frase {n} (queda con foto)."
        hoy = i < len(g.presente) and g.presente[i]
        v = revisar_video(cliente, g.frases[i], e.anio, hoy, halladas, avisar)
        if v is None:
            return (f"Encontré {len(halladas)} videos para la frase {n} pero ninguno muestra lo que "
                    "dice (o no es de la época): queda con foto.")
        g.videos[str(i)] = v.a_dict()
    g.con_video = sorted(set(g.con_video) | {i})
    p.guion = g.a_dict()
    from .videos_libres import Video

    return f"Frase {n}: 🎬 video ({Video.de_dict(g.videos[str(i)]).etiqueta()})."


def usadas_en_orden(p: Propuesta, plan: list[tuple[int, int, float]] | None = None) -> list[Foto]:
    """Las fotos que aparecen en el video, en el orden en que aparecen (para los créditos)."""
    orden = list(dict.fromkeys(f for _, f, _ in (plan or plan_de(p)) if f >= 0))
    return [Foto.de_dict(p.fotos[i]) for i in orden]


def numeros_usados(p: Propuesta) -> list[int]:
    """Los números (desde 1) de las fotos que se ven, ordenados: los de la hoja y los botones 🔁."""
    return sorted({f + 1 for _, f, _ in plan_de(p) if f != VIDEO})


def cambiar_foto(p: Propuesta, n: int, wiki: Wiki, carpeta: Path) -> Foto | None:
    """"🔁 cambiar foto N": la N pasa a descartada y cada frase que la usaba pasa a la siguiente
    de SU lista que no se esté viendo; si no queda ninguna de su lista, una del resto del pool
    (Gemini ya las vio y no las descartó); si tampoco, una de la reserva vieja (propuestas de antes
    del 2026-09-28). None si no hay con qué reemplazarla: no cambia nada."""
    g = Guion.de_dict(p.guion)
    i = n - 1
    antes = plan_de(p)
    g.descartadas = sorted(set(g.descartadas) | {i})
    rankings = [[x for x in r if x != i] for r in g.rankings()]
    if i not in g.fotos:
        # Solo se veía como segunda foto de una frase partida: con descartarla, el reparto de
        # tramos elige otra. Se devuelve la que queda en su lugar.
        g.ranking = rankings
        p.guion = g.a_dict()
        despues = plan_de(p)
        lugar = next((k for k, (_, f, _) in enumerate(antes) if f == i), None)
        if lugar is None or lugar >= len(despues) or despues[lugar][1] == i:
            return None
        return Foto.de_dict(p.fotos[despues[lugar][1]])
    nuevas = list(g.fotos)
    primera = None
    for j, f in enumerate(g.fotos):
        if f != i:
            continue
        en_uso = set(nuevas)
        # Acá sí vale todo lo que Gemini vio y no descartó: el 🔁 lo pide Santi y la foto nueva la
        # mira él en la hoja antes de aprobar.
        vistas = [x for x in range(len(p.fotos)) if x not in set(g.descartadas)]
        opciones = [x for x in dict.fromkeys(rankings[j] + de_reserva(g, len(p.fotos)) + vistas)
                    if x not in en_uso]
        while not opciones and p.reserva:   # la que no baja se saltea, como en la propuesta
            foto = Foto.de_dict(p.reserva.pop(0))
            try:
                foto.ruta = str(wiki.bajar(foto.url, carpeta / f"foto_reserva_{len(p.fotos):02d}.jpg"))
            except WikiError as err:
                log.warning("foto de reserva salteada (%s): %s", foto.archivo, err)
                continue
            p.fotos.append(foto.a_dict())
            opciones = [len(p.fotos) - 1]
        if not opciones:
            return None
        nuevas[j] = opciones[0]
        primera = primera if primera is not None else opciones[0]
    if primera is None:
        return None
    g.fotos, g.ranking = nuevas, rankings
    p.guion = g.a_dict()
    return Foto.de_dict(p.fotos[primera])


def _escribir_wav(pcm: bytes, sr: int, salida: Path) -> Path:
    import wave

    salida.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return salida


def acelerar(wav: Path, factor: float) -> Path:
    """atempo: más rápido SIN cambiar el tono, a 48 kHz (la voz ya viene a 48 kHz). En el mismo
    archivo. Como mucho `efemerides.tts_acelerar_max` (×1,1): si no entra, se acorta el guion."""
    tmp = wav.with_name(wav.stem + ".rapido.wav")
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav.resolve()),
         "-af", f"atempo={factor:.4f}", "-ar", "48000", "-c:a", "pcm_s16le", str(tmp.resolve())])
    tmp.replace(wav)
    return wav


# Voz natural (prueba 2026-11-01, `efemerides.voz_natural`): el silencio que queda ENTRE frases, a
# un largo distinto cada vez (Gemini TTS los deja todos parecidos), según cómo termina la frase.
PAUSA_PUNTO = (0.30, 0.60)
PAUSA_PREGUNTA = (0.40, 0.70)      # ? o !
PAUSA_SUSPENSO = (0.55, 0.85)      # … o ...
# Ecualizado suave de locutor: algo de cuerpo abajo, menos "caja" en los medios, presencia y aire.
# Sin tocar el tono ni la velocidad: solo filtros de ecualizado y un compresor suave.
EQ_LOCUTOR = ("highpass=f=75,equalizer=f=160:t=q:w=0.9:g=1.5,equalizer=f=400:t=q:w=1.4:g=-2,"
              "equalizer=f=3000:t=q:w=1.2:g=2,highshelf=f=7500:g=1.5,"
              "acompressor=threshold=-20dB:ratio=2:attack=10:release=150:makeup=1.3,alimiter=limit=0.95")


def _rango_pausa(frase: str) -> tuple[float, float]:
    f = frase.rstrip()
    if f.endswith(("…", "...")):
        return PAUSA_SUSPENSO
    if f.endswith(("?", "!")):
        return PAUSA_PREGUNTA
    return PAUSA_PUNTO


def pausas_variables(wav: Path, palabras: list, inicios: list[float], frases: list[str],
                     maximo_extra_s: float = 3.0) -> tuple[list, list[float], float]:
    """Alarga el silencio entre frases hasta un largo al azar dentro de su rango (nunca lo acorta:
    cortar puede comerse una sílaba). El azar sale del texto del guion: el mismo guion da siempre las
    mismas pausas. El silencio se mete en el medio del hueco que ya había. Devuelve las palabras y
    los inicios de cada frase corridos, y cuántos segundos se agregaron (como mucho maximo_extra_s)."""
    import random
    import wave

    import numpy as np

    from .subtitles import Palabra

    rng = random.Random(hashlib.sha256(" ".join(frases).encode()).hexdigest())
    cuantas = [len(f.split()) for f in frases]
    finales, k = [], 0
    for n in cuantas:                       # dónde termina la última palabra de cada frase
        k += n
        finales.append(palabras[k - 1].fin if n and k - 1 < len(palabras) else 0.0)
    extras = []
    for i in range(len(frases) - 1):
        hueco = max(0.0, inicios[i + 1] - finales[i])
        lo, hi = _rango_pausa(frases[i])
        extras.append((finales[i] + hueco / 2, max(0.0, rng.uniform(lo, hi) - hueco)))
    total = sum(e for _, e in extras)
    if total > maximo_extra_s > 0:
        extras = [(t, e * maximo_extra_s / total) for t, e in extras]
    elif maximo_extra_s <= 0:
        extras = [(t, 0.0) for t, _ in extras]
    with wave.open(str(wav)) as w:
        sr, params = w.getframerate(), w.getparams()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    trozos, desde = [], 0
    for t, e in extras:
        corte = min(len(audio), max(desde, int(round(t * sr))))
        trozos += [audio[desde:corte], np.zeros(int(round(e * sr)), dtype=np.int16)]
        desde = corte
    trozos.append(audio[desde:])
    with wave.open(str(wav), "wb") as w:
        w.setparams(params)
        w.writeframes(np.concatenate(trozos).tobytes())
    # Los tiempos: cada frase se corre lo que se agregó antes de ella.
    corrimiento = [0.0]
    for _, e in extras:
        corrimiento.append(corrimiento[-1] + round(e * sr) / sr)
    nuevas, k = [], 0
    for f, n in enumerate(cuantas):
        for p in palabras[k:k + n]:
            nuevas.append(Palabra(p.inicio + corrimiento[f], p.fin + corrimiento[f], p.texto))
        k += n
    nuevas += palabras[k:]
    return nuevas, [ini + corrimiento[f] for f, ini in enumerate(inicios)], corrimiento[-1]


def ecualizar_locutor(wav: Path) -> Path:
    """EQ_LOCUTOR sobre la voz, a 48 kHz, en el mismo archivo."""
    tmp = wav.with_name(wav.stem + ".eq.wav")
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav.resolve()),
         "-af", EQ_LOCUTOR, "-ar", "48000", "-c:a", "pcm_s16le", str(tmp.resolve())])
    tmp.replace(wav)
    return wav


def voz_falsa() -> bool:
    """¿Esta voz es de una PRUEBA? (Santi, 2026-11-15: la voz real de Gemini, solo para el video que se publica).
    Sí cuando corre un script o el CLI a mano (origen "prueba" en gemini.py); no en producción (los ticks, `diario`,
    `efemeride-diaria`) ni en los comandos y botones de Telegram (✅ arma el video que se publica).
    `CLIPS_VOZ_REAL=1` la fuerza real (un script que arma un video para publicar, como el Intel del 15/11) y
    `CLIPS_VOZ_FALSA=1` la fuerza falsa."""
    import os

    from . import gemini as gm

    if os.getenv("CLIPS_VOZ_REAL") == "1":
        return False
    if os.getenv("CLIPS_VOZ_FALSA") == "1":
        return True
    return gm.ORIGEN == gm.PRUEBA


def voz_de_prueba(frases: list[str], settings, carpeta: Path,
                  avisar=log.info) -> tuple[Path, list[float] | None, str]:
    """La voz de una prueba: Piper si está (frase por frase, con su duración exacta) o, si no, silencio con la
    duración estimada (PALABRAS_POR_S_VOZ, como Gemini). No gasta ninguna voz de Gemini."""
    import wave

    from dataclasses import replace

    from . import narrar

    cfg = settings.efemerides
    modelo = Path(settings.voz.modelo)
    if modelo.exists():
        ajustes = replace(settings.voz, length_scale=cfg.piper_length_scale,
                          noise_scale=cfg.piper_noise_scale, noise_w_scale=cfg.piper_noise_w_scale)
        wav, duraciones = narrar.sintetizar_frases(frases, modelo, carpeta / "voz.wav", ajustes=ajustes)
        avisar("voz de PRUEBA con Piper (no gasta voces de Gemini)")
        return wav, duraciones, f"falsa:piper:{modelo.stem}"
    duraciones = [round(max(0.8, len(f.split()) / PALABRAS_POR_S_VOZ + 0.25), 2) for f in frases]
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = carpeta / "voz.wav"
    sr = 48000
    with wave.open(str(salida), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x00" * int(sr * sum(duraciones)))
    avisar(f"voz de PRUEBA: silencio de {sum(duraciones):.1f} s (sin Piper; no gasta voces de Gemini)")
    return salida, duraciones, "falsa:silencio"


def voz_efemeride(frases: list[str], settings, carpeta: Path, avisar=log.info,
                  tts=None, segunda_primero: bool = False,
                  elevenlabs_cfg=None) -> tuple[Path, list[float] | None, str]:
    """La voz del guion: (wav, duración de cada frase o None, motor que se usó).

    Gemini TTS da un solo audio para todo el guion, así que no sabe dónde empieza cada frase:
    devuelve None y los cortes salen de alinear Whisper contra el guion. Piper sintetiza frase por
    frase y ahí la duración de cada una se sabe exacta."""
    from dataclasses import replace

    from . import narrar
    from .config import env
    from .gemini import GeminiError, aviso_por_telegram, claves_activas, hablar_con_claves, registrar_uso

    cfg = settings.efemerides
    motivo = ""
    from . import elevenlabs

    if voz_falsa():
        # Una prueba (Santi, 2026-11-15: "las voces de Gemini no alcanzan"): nada de Gemini ni ElevenLabs.
        return voz_de_prueba(frases, settings, carpeta, avisar)
    el = elevenlabs_cfg
    if elevenlabs.lista(el):
        # ElevenLabs SOLO para Así Nació (Santi, 2026-11-15: la voz de Tito; Pequeña Historia y Lo Encontré
        # siguen con Gemini gratis): va únicamente si quien llama pasa su config. Si falla, la de siempre.
        try:
            pcm, sr = elevenlabs.hablar(" ".join(frases), el.elevenlabs_voz, el.elevenlabs_modelo,
                                        estabilidad=getattr(el, "elevenlabs_estabilidad", 0.45))
            wav = narrar.a_48k(_escribir_wav(pcm, sr, carpeta / "voz.wav"))
            return wav, None, f"elevenlabs:{el.elevenlabs_nombre or el.elevenlabs_voz}"
        except elevenlabs.ElevenLabsError as e:
            avisar(f"ElevenLabs no anduvo ({str(e)[:120]}): sigo con la voz de siempre")
    if cfg.voz_motor == "gemini":
        try:
            claves = claves_activas() if env("GEMINI_API_KEY", requerido=False) else []
            if segunda_primero:
                # El video de Facebook (2026-11-09): su voz va por la segunda clave, así no le saca
                # cupo a la efeméride de YouTube ni a Lo Encontré; la principal queda de respaldo.
                claves = sorted(claves, key=lambda c: c[0] == "principal")
            if not claves:
                raise GeminiError("sin GEMINI_API_KEY")
            kw = dict(instruccion=cfg.tts_instruccion, voz=cfg.tts_voz, modelo=cfg.tts_modelo)
            for intento in range(2):
                # Un timeout suelto no alcanza para caer en Piper (2026-10-04: a las 20:51 tardó más
                # de 180 s y dos minutos después contestaba en 5 s): se prueba una vez más.
                try:
                    pcm, sr = (tts(claves[0][1], " ".join(frases), **kw) if tts else
                               hablar_con_claves(claves, " ".join(frases), aviso=aviso_por_telegram,
                                                 uso=registrar_uso, **kw))
                    break
                except GeminiError as e:
                    if intento or "timed out" not in str(e).lower():
                        raise
                    avisar("Gemini TTS tardó demasiado: pruebo una vez más")
            wav = narrar.a_48k(_escribir_wav(pcm, sr, carpeta / "voz.wav"))
            # El ruido del final (Santi, 2026-11-11: "los dos videos tienen un ruido al final").
            limpio = narrar.limpiar_cola(wav)
            if limpio:
                avisar(f"voz: saqué un ruido de {limpio:.2f} s al final")
            return wav, None, f"gemini:{cfg.tts_voz}"
        except GeminiError as e:
            avisar(f"Gemini TTS no anduvo ({str(e)[:120]}): sigo con Piper")
            motivo = "sin cuota" if "quota" in str(e).lower() or "429" in str(e) else "Gemini no respondió"
    ajustes = replace(settings.voz, length_scale=cfg.piper_length_scale,
                      noise_scale=cfg.piper_noise_scale, noise_w_scale=cfg.piper_noise_w_scale)
    modelo = Path(settings.voz.modelo)
    if not modelo.exists():
        raise NarrarError(f"Falta la voz en {modelo}")
    wav, duraciones = narrar.sintetizar_frases(frases, modelo, carpeta / "voz.wav", ajustes=ajustes)
    # El motivo viaja pegado ("piper:…|sin cuota"): la entrega dice qué voz salió y por qué.
    return wav, duraciones, f"piper:{modelo.stem}" + (f"|{motivo}" if motivo else "")


def texto_voz(motor: str) -> str:
    """Lo que dice el mensaje del video: "Voz: Laomedeia" o "Voz: Piper (respaldo, sin cuota)"."""
    if motor.startswith(("gemini:", "elevenlabs:")):
        nombre = motor.split(":", 1)[1]
        return f"Voz: {nombre}" + (" (ElevenLabs)" if motor.startswith("elevenlabs:") else "")
    if motor.startswith("falsa:"):
        return "Voz: de PRUEBA (" + ("Piper" if "piper" in motor else "silencio") + ", no gasta voces de Gemini)"
    motivo = motor.partition("|")[2]
    return "Voz: Piper (respaldo" + (f", {motivo}" if motivo else "") + ")"


def es_piper(motor: str) -> bool:
    return motor.startswith("piper:")


SISTEMA_ACORTAR = (
    "Acortás el guion de un Short de historia para que entre en el tiempo. Devolvés EXACTAMENTE la "
    "misma cantidad de frases, en el mismo orden, cada una más corta, diciendo lo mismo con menos "
    "palabras. Mantené el gancho de la primera frase (lo más sorprendente, sin fecha), la intriga de "
    "la segunda (sin fecha), el año en la misma frase en que está, el cierre "
    "con gancho y que se entienda paso a paso. No agregues nombres, cifras ni datos que no estén en "
    "el guion original. Español rioplatense neutro.")
SCHEMA_ACORTAR = {"type": "OBJECT", "properties": {"frases": {"type": "ARRAY", "items": {"type": "STRING"}}},
                  "required": ["frases"]}


def palabras_objetivo(n_palabras: int, dur_s: float, max_s: float) -> int:
    """Cuántas palabras tiene que tener el guion para durar `max_s` (con un 5 % de margen)."""
    return max(int(n_palabras * max_s / max(dur_s, 0.1) * 0.95), 1)


def validar_acortado(frases, originales: list[str], objetivo: int, fuente: str) -> list[str]:
    if not isinstance(frases, list) or len(frases) != len(originales):
        return [f"tienen que ser {len(originales)} frases, en el mismo orden"]
    frases = [str(f).strip() for f in frases]
    errores = []
    if any(len(f.split()) < 3 for f in frases):
        errores.append("hay frases vacías o de menos de 3 palabras")
    n = sum(len(f.split()) for f in frases)
    if n > objetivo:
        errores.append(f"tiene {n} palabras y tienen que ser como mucho {objetivo}")
    for k in (2, 3):     # el año se sigue diciendo en la misma frase (la 3.ª o la 4.ª)
        for anio in re.findall(r"\b(1\d{3}|20\d{2})\b", originales[k] if k < len(originales) else ""):
            if anio not in frases[k]:
                errores.append(f"la frase {k + 1} tiene que seguir diciendo el año {anio}")
    sin = no_respaldados(" ".join(frases), fuente)
    if sin:
        errores.append("esto no está en el artículo: " + ", ".join(sin[:6]))
    return errores


def acortar_guion(cliente, g: Guion, fuente: str, objetivo: int, reintentos: int = 2) -> Guion | None:
    """El mismo guion, frase por frase más corto (para no acelerar la voz más de ×1,1). Valida lo de
    siempre: mismas frases, todo respaldado por el artículo. None si no sale."""
    from dataclasses import replace

    prompt = (f"Guion (una frase por línea, {len(g.frases)} frases, {len(g.texto.split())} palabras):\n"
              + "\n".join(g.frases)
              + f"\n\nTiene que quedar en {objetivo} palabras o menos, con las mismas {len(g.frases)} frases.")
    errores: list[str] = []
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        d = json.loads(cliente.json(SISTEMA_ACORTAR, prompt + extra, SCHEMA_ACORTAR, temperatura=0.3))
        errores = validar_acortado(d.get("frases"), g.frases, objetivo, fuente)
        if not errores:
            frases = [str(f).strip() for f in d["frases"]]
            return replace(g, frases=frases, claves=claves_del_guion(g.claves, frases))
    log.warning("no pude acortar el guion: %s", "; ".join(errores))
    return None


def ajustar_duracion(wav: Path, duraciones: list[float] | None, max_s: float, max_factor: float,
                     avisar=log.info) -> tuple[list[float] | None, float]:
    """Si la voz pasa de `max_s`, atempo hasta `max_factor` (sin tocar el tono). Devuelve las
    duraciones de cada frase ajustadas y el factor usado (1.0 = nada)."""
    from . import narrar

    dur = narrar.duracion_wav(wav)
    if dur <= max_s:
        return duraciones, 1.0
    factor = min(dur / max_s, max_factor)
    acelerar(wav, factor)
    avisar(f"voz de {dur:.1f} s: atempo ×{factor:.2f} (sin cambiar el tono)")
    return ([d / factor for d in duraciones] if duraciones else duraciones), factor


def cortes_de(plan, p: Propuesta) -> list[dict]:
    """Cada corte tal como sale (Santi, 2026-11-17, Colón): la revisión final mira un cuadro de cada uno en el video
    terminado, no la hoja de antes de la voz."""
    cortes, t_c = [], 0.0
    for i, f, s in plan:
        d_c = round(s * 30) / 30
        tipo = "video" if f == VIDEO else "mapa" if f == MAPA else "foto"
        archivo = p.fotos[f].get("archivo", "") if tipo == "foto" and 0 <= f < len(p.fotos) else ""
        cortes.append({"frase": i, "inicio": round(t_c, 2), "dur": round(d_c, 2), "tipo": tipo, "foto": f,
                       "archivo": archivo})
        t_c += d_c
    return cortes


def hacer_video(p: Propuesta, settings, carpeta: Path, avisar=log.info, conn=None,
                cliente=None, revisor=None) -> dict:
    """Propuesta aprobada → mp4 + meta listo para `enviar_clip`. Esto es lo que gasta la Pi:
    Piper, Whisper sobre la voz y un encode por foto.

    `conn`: la DB, para elegir la música sin repetir los últimos temas ni usar los vetados por
    /reclamo, y anotar cuál se usó. Sin DB se elige igual, sin esas dos reglas."""
    from . import musica, narrar, subtitles as sub

    from dataclasses import replace as _replace

    g, e = Guion.de_dict(p.guion), Evento(**p.evento)
    t0 = time.time()
    cfg_v = settings.efemerides
    fb = p.destino == "facebook"
    # Estilo nuevo (Santi, 2026-11-14): arranque con montaje y golpe de zoom (o un clip real), el
    # mapa acercándose al lugar en la de Latinoamérica, gancho y subtítulos animados.
    nuevo = bool(getattr(cfg_v, "estilo_nuevo", False))
    from . import bitacora

    bitacora.paso("voz")
    wav, duraciones, motor = voz_efemeride(g.frases, settings, carpeta, avisar, segunda_primero=fb)
    # Duración (2026-10-04): atempo hasta ×1,1 y nada más. Si no entra ni así, se acorta el GUION
    # (`cliente`: Gemini) y se vuelve a sintetizar; la voz nunca se acelera más ni cambia de tono.
    dur = narrar.duracion_wav(wav)
    max_s = g.max_s or (CORTO_MAX_S if g.corto else cfg_v.tts_max_s)   # corto 30 s; Latinoamérica 40
    tope = max_s * cfg_v.tts_acelerar_max
    if dur > tope and cliente is not None:
        objetivo = palabras_objetivo(len(g.texto.split()), dur, tope)
        avisar(f"voz de {dur:.1f} s: no entra ni con ×{cfg_v.tts_acelerar_max}; acorto el guion a "
               f"{objetivo} palabras")
        corto = acortar_guion(cliente, g, p.fuente + "\n" + e.texto + f" {e.anio}", objetivo)
        if corto is not None:
            g = corto
            p = _replace(p, guion=g.a_dict())
            wav, duraciones, motor = voz_efemeride(g.frases, settings, carpeta, avisar,
                                                   segunda_primero=fb)
    duraciones, _ = ajustar_duracion(wav, duraciones, max_s, cfg_v.tts_acelerar_max, avisar)
    # Nada de segundos muertos al principio (Santi, 2026-11-12): la voz arranca en el cuadro 1.
    cortado = narrar.sacar_silencio_inicial(wav)
    if cortado:
        avisar(f"voz: saqué {cortado:.2f} s de silencio al principio")
        if duraciones:
            duraciones = [max(0.3, duraciones[0] - cortado)] + list(duraciones[1:])
    fin = narrar.duracion_wav(wav)
    avisar(f"voz ({motor}): {fin:.1f} s en {time.time() - t0:.0f} s")
    t0 = time.time()
    # Whisper da los tiempos; el texto de los subtítulos es el del guion aprobado.
    bitacora.paso("whisper")
    oidas = narrar.palabras_de_voz(wav, settings.subtitulos)
    oidas, recortado = narrar.recortar_inicio(wav, oidas, g.frases)
    if recortado:
        fin = narrar.duracion_wav(wav)
        avisar(f"la voz dijo {recortado:.1f} s de algo antes del guion: recortado")
    palabras, inicios = narrar.alinear_a_guion(oidas, g.frases, fin)
    bitacora.paso("render")
    if cfg_v.voz_natural:
        # Pausas variables entre frases (sin pasarse del tope de duración) y EQ de locutor.
        palabras, inicios, extra = pausas_variables(wav, palabras, inicios, g.frases, max(0.0, tope - fin))
        ecualizar_locutor(wav)
        fin = narrar.duracion_wav(wav)
        duraciones = None    # con las pausas nuevas, los cortes salen de la alineación corrida
        avisar(f"voz natural: +{extra:.1f} s de pausas variables y EQ de locutor ({fin:.1f} s)")
    if duraciones is None:   # Gemini: un solo audio, los cortes salen de la alineación
        duraciones = [b - a for a, b in zip(inicios, inicios[1:] + [fin])]
    subs = sub.palabra_por_palabra(palabras, settings.subtitulos)
    cfg_ef = settings.efemerides
    if cfg_ef.graficos:
        # Karaoke en los dos formatos (Santi, 2026-11-11) y, desde el 2026-11-12, el arranque:
        # el GANCHO escrito en grande desde el primer cuadro mientras la voz lo dice; el año
        # contando recién con la segunda frase ("En <año>,"); las palabras clave después.
        from . import graficos as gr

        # Estilo nuevo (2026-11-14): más grandes, 2-3 palabras, la activa con un saltito.
        estilo = dict(tamano=100, rebote=True, borde=9, max_chars=14) if nuevo else dict(tamano=78)
        sub.escribir_ass_karaoke(palabras, carpeta / "subs.ass", settings.subtitulos, settings.render,
                                 color_activo=sub.KARAOKE_PH, **estilo)
        fin_gancho = inicios[1] if len(inicios) > 1 else min(fin, 3.0)
        # El año (y el lugar, en la de Latinoamérica) escritos desde la segunda frase, mientras la
        # voz suma intriga; la voz los dice en la 3.ª o 4.ª (Santi, 2026-11-12).
        fin_intriga = inicios[2] if len(inicios) > 2 else fin_gancho + gr.AÑO_HASTA_S
        lugar = str(((p.local or {}) if p.destino == "facebook" else {}).get("lugar") or "")
        gr.agregar_al_ass(carpeta / "subs.ass",
                          gr.estilos(settings.render.ancho, settings.render.alto, settings.subtitulos.fuente),
                          (gr.gancho_animado if nuevo else gr.gancho_en_pantalla)(g.frases[0], fin_gancho)
                          + gr.anio_contando(e.anio, inicio=fin_gancho, hasta=fin_intriga)
                          + gr.lugar_en_pantalla(lugar, fin_gancho, fin_intriga)
                          + gr.claves_en_tiempo(palabras, g.claves,
                                                desde_s=max(fin_gancho + gr.AÑO_HASTA_S, fin_intriga)))
    else:
        sub.escribir_ass(subs, carpeta / "subs.ass", settings.subtitulos, settings.render)
    avisar(f"subtítulos: {len(subs)} palabras en {time.time() - t0:.0f} s")
    # La música entra DESPUÉS de los subtítulos: Whisper tiene que escuchar la voz sola.
    from .config import ROOT

    carpeta_musica = ROOT / cfg_ef.carpeta_musica
    tema = musica.elegir(musica.cargar(carpeta_musica), g.tono,
                         musica.recientes(conn) if conn else [],
                         musica.vetados(conn) if conn else set()) if cfg_ef.musica else None
    audio = musica.mezclar(wav, carpeta_musica / tema.ruta, carpeta / "voz_musica.wav",
                           cfg_ef.musica_volumen) if tema else wav
    if tema and conn:
        musica.anotar_uso(conn, tema.ruta)
    avisar(f"música: {tema.ruta if tema else 'ninguna'} (tono {g.tono or '?'})")
    # Regla fija (ilustrar.py): con los tiempos REALES de la voz, ninguna foto más de 6 s seguidos.
    plan = plan_de(p, duraciones)
    # Los videos: el tramo de cada uno, del largo REAL de su frase. Si uno no baja, esa frase
    # vuelve a su foto (el video no puede tumbar la efeméride).
    from .videos_libres import Video, bajar_tramo

    from .videos_libres import encuadre_video

    rutas_video: dict[int, Path] = {}
    encuadres: dict[str, tuple[float, bool]] = {}
    for i, f, s in plan:
        if f != VIDEO:
            continue
        v = Video.de_dict(g.videos[str(i)])
        try:
            rutas_video[i] = bajar_tramo(v, s, carpeta / f"video_frase_{i + 1:02d}.mp4")
            # Caras enteras: el recorte del video se centra en las caras del cuadro elegido.
            if v.frames:
                encuadres[str(rutas_video[i])] = encuadre_video(Path(v.frames[0]))
            avisar(f"video frase {i + 1}: {v.etiqueta()}, {s:.1f} s desde {v.momento:.0f} s")
        except (RuntimeError, OSError, subprocess.SubprocessError) as err:
            avisar(f"⚠️ video frase {i + 1} no bajó ({str(err)[:120]}): vuelve a foto")
            g.con_video = [x for x in g.con_video if x != i]
    if len(rutas_video) < sum(1 for _, f, _ in plan if f == VIDEO):
        p.guion = g.a_dict()
        plan = plan_de(p, duraciones)
    for problema in ilustrar.errores_plan([x for x in plan if x[1] != VIDEO], g.minimo_fotos):
        avisar(f"⚠️ fotos: {problema}")
    # Control de calidad con los tiempos REALES de la voz (Santi, 2026-11-11): sin 70 % de fotos
    # reales, no se arma.
    pct = fraccion_real(p.fotos, plan)
    _control_real(g, pct, avisar)
    movimientos = None
    if g.corto:
        nueva = fabrica_tarjetas(g, e.anio, carpeta, lambda k: Foto.de_dict(p.fotos[k]),
                                 lambda f: (p.fotos.append(f.a_dict()), len(p.fotos) - 1)[1])
        faltas: list = []
        plan, movimientos = plan_rapido(plan, g, nueva_tarjeta=nueva, faltas=faltas, montaje=nuevo)
        p.guion = g.a_dict()
        if faltas:
            avisar(f"⚠️ fotos: en {len(faltas)} cortes no quedaba otra foto ni tarjeta: se repite")
        pct = fraccion_real(p.fotos, plan)
        _control_real(g, pct, avisar)
        p.guion = g.a_dict()
        avisar(f"formato corto: {len(plan)} cortes de {min(s for *_, s in plan):.1f} a "
               f"{max(s for *_, s in plan):.1f} s")
    mapa = None
    ruta_mapa = None
    if nuevo and fb and cfg_ef.graficos and len(plan) > 1:
        # El mapa a pantalla completa acercándose al lugar, al empezar la segunda frase (la intriga,
        # con el lugar escrito): reemplaza al recuadro quieto. Sin coordenadas, no va.
        try:
            from . import graficos as gr

            wiki = Wiki()
            # El artículo del hecho; si es de una persona (La Pola: sin coordenadas), el del lugar.
            coords = wiki.coordenadas(e.lang, e.paginas[0])
            lugar = str((p.local or {}).get("lugar") or "")
            if not coords and lugar:
                coords = wiki.coordenadas("es", lugar)
            # Sincronizado con la voz (Santi, 2026-11-14: "tiene que llegar a Bogotá justo cuando la voz
            # dice Bogotá"): el acercamiento termina cuando se dice el lugar. Si no se encuentra la
            # palabra, al empezar la segunda frase, como antes.
            t_lugar = momento_de_palabra(palabras, lugar)
            if coords and gr.distancia_ok(*coords):
                if t_lugar is not None:
                    a = max(0.0, t_lugar - MAPA_ANTES_S)
                    dur = round(t_lugar + MAPA_DESPUES_S - a, 3)
                else:
                    k = next((k for k, (i, f, _) in enumerate(plan) if i == 1 and f != VIDEO), None)
                    a = sum(x[2] for x in plan[:k]) if k is not None else 0.0
                    dur = round(min(2.0, plan[k][2]), 3) if k is not None else 0.0
                if dur >= 1.0:
                    ruta_mapa = gr.mapa_zoom(wiki.mapa_base(carpeta), *coords, carpeta / "mapa_zoom.mp4",
                                             segundos=dur, W=settings.render.ancho, H=settings.render.alto,
                                             llegada=(dur - MAPA_DESPUES_S) / dur)
                    encuadres[str(ruta_mapa)] = (0.5, True)     # ya es 9:16: a pantalla completa
                    plan, movimientos = insertar_tramo(plan, movimientos, a, dur, MAPA, "mapa")
                    avisar(f"mapa con zoom: {coords[0]:.2f}, {coords[1]:.2f}, de {a:.1f} a {a + dur:.1f} s"
                           + (f" (llega cuando dice «{lugar}», {t_lugar:.1f} s)" if t_lugar is not None else ""))
        except (WikiError, OSError, KeyError, ValueError, RuntimeError, subprocess.SubprocessError) as err:
            avisar(f"mapa con zoom: no salió ({str(err)[:100]})")
    # Santi, 2026-11-23: una tarjeta con un año o un número aparece justo cuando la voz lo dice, nunca antes.
    plan, movs_al = alinear_tarjetas(plan, movimientos, p.fotos, palabras, avisar)
    movimientos = movs_al if movimientos is not None else None
    tramos = [(rutas_video[i] if f == VIDEO else ruta_mapa if f == MAPA else Path(p.fotos[f]["ruta"]), s)
              for i, f, s in plan]
    if cfg_ef.graficos:
        from . import graficos as gr

        # Un whoosh suave en cada cambio de foto o video (en la voz+música, antes de las reglas de
        # audio que aplica armar_video).
        cortes, t = [], 0.0
        for k, (i, f, s) in enumerate(plan[:-1]):
            t += round(s * 30) / 30
            # En el corto, solo al cambiar de frase; con el estilo nuevo también en el montaje del
            # gancho y al entrar y salir del mapa.
            if (not g.corto or plan[k + 1][0] != i
                    or (nuevo and (i == 0 or MAPA in (f, plan[k + 1][1])))):
                cortes.append(t)
        audio = gr.mezclar_whoosh(audio, cortes, gr.whoosh(carpeta / "whoosh.wav"),
                                  carpeta / "voz_musica_whoosh.wav")
        # El mapa con el punto, durante la segunda frase (si el artículo tiene coordenadas).
        try:
            wiki = Wiki()
            coords = None if ruta_mapa is not None else wiki.coordenadas(e.lang, e.paginas[0])
            if coords and gr.distancia_ok(*coords) and len(inicios) > 1:
                desde = inicios[1]
                hasta = min(desde + 3.5, inicios[2] if len(inicios) > 2 else fin)
                mapa = (gr.mapa(wiki.mapa_base(carpeta), *coords, carpeta / "mapa.png"), desde, hasta)
                avisar(f"mapa: {coords[0]:.2f}, {coords[1]:.2f} de {desde:.1f} a {hasta:.1f} s")
        except (WikiError, OSError, KeyError, ValueError) as err:
            avisar(f"mapa: no salió ({str(err)[:100]})")
    t0 = time.time()
    dia = date.fromisoformat(p.fecha)
    clip_id = f"{'historia_fb' if fb else 'efemeride'}_{dia:%m%d}_{e.anio}"
    salida = armar_video(tramos, audio, carpeta, carpeta / f"{clip_id}.mp4", settings.render,
                         parallax=cfg_ef.parallax, mapa=mapa, encuadres=encuadres,
                         efecto="mov" if g.corto else cfg_ef.efecto_fotos, movimientos=movimientos)
    avisar(f"video: {time.time() - t0:.0f} s, {len(tramos)} tramos, "
           f"{len({f for _, f, _ in plan if f != VIDEO})} fotos distintas, {len(rutas_video)} videos")
    revision_final = None
    if revisor is not None:
        # Santi, 2026-11-18: cuando el mosaico final encuentra una foto mal, NO se frena el video: se reemplaza solo esa
        # foto por la siguiente finalista de su frase (o una tarjeta) y se vuelve a revisar solo ese corte. Se frena
        # únicamente si no hay reemplazo posible.
        from . import calidad

        def armar(rehacer):
            tr = [(rutas_video[i] if f == VIDEO else ruta_mapa if f == MAPA else Path(p.fotos[f]["ruta"]), s_)
                  for i, f, s_ in plan]
            return armar_video(tr, audio, carpeta, carpeta / f"{clip_id}.mp4", settings.render,
                               parallax=cfg_ef.parallax, mapa=mapa, encuadres=encuadres,
                               efecto="mov" if g.corto else cfg_ef.efecto_fotos, movimientos=movimientos,
                               rehacer=rehacer)

        tarjeta_nueva = fabrica_tarjetas(g, e.anio, carpeta, lambda k: Foto.de_dict(p.fotos[k]),
                                         lambda f: (p.fotos.append(f.a_dict()), len(p.fotos) - 1)[1])
        revision_final = calidad.revisar_y_reemplazar(
            revisor, salida, plan, g, cortes_de(plan, p), e, p.local or {}, armar,
            lambda i: tarjeta_nueva(i, propia=True), avisar)
        salida = Path(revision_final.get("salida") or salida)
        # Control sin Claude (PH-26): las tarjetas que la revisión puso pueden quedar antes de que la voz diga su
        # número: ese corte vuelve a la imagen anterior; si igual queda alguna, cuenta como falla.
        destiempo = tarjetas_a_destiempo(plan, p.fotos, palabras)
        if destiempo:
            for k in destiempo:
                i, _f, s_ = plan[k]
                previa = next((plan[j][1] for j in range(k - 1, -1, -1)
                               if not (0 <= plan[j][1] < len(p.fotos) and es_tarjeta(p.fotos[plan[j][1]]))), None)
                if previa is not None:
                    plan[k] = (i, previa, s_)
            salida = armar(set(destiempo))
            revision_final["salida"] = str(salida)
            avisar(f"tarjetas a destiempo en los cortes {[k + 1 for k in destiempo]}: vuelven a la imagen anterior")
        quedan = tarjetas_a_destiempo(plan, p.fotos, palabras)
        if quedan:
            revision_final.setdefault("fallas", []).append(
                {"id": "PH-26", "cuadro": quedan[0] + 1,
                 "que": f"tarjeta con un número antes de que la voz lo diga (cortes {[k + 1 for k in quedan]})"})
    for problema in chequear_audio(salida):
        avisar(f"⚠️ audio: {problema}")
    from .videos_libres import creditos as creditos_videos

    cortes = cortes_de(plan, p)
    cred = creditos(usadas_en_orden(p, plan))
    if rutas_video:
        cred += "\n" + creditos_videos(videos_en_orden(p, plan))
    if mapa:
        from .graficos import MAPA_CREDITO

        cred += f"\n{MAPA_CREDITO}"
    if tema:
        cred += f"\nMúsica: {tema.credito()}"
    return {"clip_id": clip_id, "streamer": "Pequeña Historia", "salida": str(salida),
            "subtitulos_quemados": True, "duracion_s": round(sum(duraciones), 1),
            "textos": {"titulo": g.titulo, "descripcion": f"{g.descripcion}\n\n{cred}",
                       "hashtags": g.hashtags, "credito": cred},
            "efemeride": {"fecha": p.fecha, "anio": e.anio, "evento": e.texto,
                          "articulo": e.paginas[0], "lang": e.lang, "guion": g.frases,
                          "musica": tema.ruta if tema else None, "tono": g.tono, "voz": motor,
                          "destino": p.destino, "local": p.local, "aviso_fotos": aviso_fotos(g),
                          "cortes": cortes, "revision_final": revision_final}}


def _jpeg_chico(ruta: Path, ancho: int = 512) -> bytes:
    """La foto como la ve Gemini: chica alcanza para decidir si es un mapa o un retrato."""
    import io

    from PIL import Image

    with Image.open(ruta) as im:
        im = im.convert("RGB")
        im.thumbnail((ancho, ancho))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return buf.getvalue()
