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
from .media import chequear_audio, find_bin, preparar_audio, run
from . import ilustrar
from .narrar import NarrarError
from .reglas import REGLAS_CLARIDAD
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


def sin_html(t: str) -> str:
    """Commons a veces manda el HTML escapado ("&lt;abbr ..."): se desescapa ANTES de sacar tags."""
    t = re.sub(r"<[^>]+>", " ", html.unescape(str(t or "")))
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
    return None


SISTEMA_ELEGIR = """Elegís efemérides para un canal de videos cortos, "Pequeña Historia", para un público
joven (15 a 30 años) de habla hispana. Te paso los hechos que pasaron en la fecha de hoy.

Ordená los más interesantes, del mejor al peor: los que generan "¿en serio pasó eso?", los de
ciencia, espacio, inventos, cultura pop, deportes, récords, cosas curiosas. Tienen que cumplir:
- Fecha EXACTA: algo que pasó ESE día (un lanzamiento, un estreno, un descubrimiento, un récord).
  Nada de procesos largos ("se construyó durante siglos") ni de "en esta década".
- NADA sensible: guerras recientes, atentados, masacres, muertes trágicas, accidentes, desastres.
- Que se pueda contar en 40 segundos y se entienda sin saber historia.
Respondé solo con el JSON pedido."""

SCHEMA_ELEGIR = {
    "type": "OBJECT",
    "properties": {"elegidos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"indice": {"type": "INTEGER"}, "articulo": {"type": "STRING"},
                       "motivo": {"type": "STRING"}},
        "required": ["indice", "articulo", "motivo"]}}},
    "required": ["elegidos"],
}


ELEGIDOS = 8        # el ranking que devuelve Gemini: los 3 primeros son "los 3 más interesantes"
MAX_GUIONES = 3     # hechos que se intentan por día (2 → 3 el 2026-09-29: con la regla de 4 fotos
                    # de época se pasa más seguido al siguiente). Cada uno son 2 llamadas (guion +
                    # fotos) más los reintentos del guion: caso normal 1 + 3 × 2 = 7


def elegir(cliente, eventos: list[Evento], cuantos: int = ELEGIDOS) -> list[tuple[int, str]]:
    """(índice, artículo del evento) de los elegidos, del mejor al peor.

    El artículo lo elige Gemini entre los del hecho porque el primero de la lista suele ser el
    país ("Nicaragua" para el cierre de El Nuevo Diario, medido 2026-09-27) y traía fotos de playas
    y presidentes. Las fotos y el texto del guion salen SOLO de ese artículo. Si el que devuelve
    no es uno de la lista, se usa el último (el más específico, en el feed en castellano)."""
    lista = "\n".join(f"{i}. ({e.anio}) {e.texto}  [artículos: {' | '.join(e.paginas)}]"
                      for i, e in enumerate(eventos, 1))
    d = json.loads(cliente.json(
        SISTEMA_ELEGIR, f"Hechos de hoy:\n{lista}\n\nElegí {cuantos}; `indice` es el número de la "
        "lista y `articulo` es, de sus artículos, el que trata ESPECÍFICAMENTE de ese hecho (no el "
        "país ni la ciudad), copiado tal cual.", SCHEMA_ELEGIR, temperatura=0.4))
    out: list[tuple[int, str]] = []
    for x in d.get("elegidos") or []:
        i = x.get("indice") if isinstance(x, dict) else None
        if isinstance(i, int) and 1 <= i <= len(eventos) and i - 1 not in [o[0] for o in out]:
            paginas = eventos[i - 1].paginas
            art = str(x.get("articulo") or "").strip().replace(" ", "_")
            out.append((i - 1, art if art in paginas else paginas[-1]))
    return out[:cuantos]


# ---- 2. fotos ------------------------------------------------------------------------

def licencia_libre(corta: str) -> bool:
    """Dominio público, CC0, CC BY y CC BY-SA. Nada de NC, ND, fair use ni "todos los derechos"."""
    c = _norm(corta).replace("-", " ")
    if any(x in c for x in ("fair use", "non free", "nonfree", " nc", " nd", "no comercial")):
        return False
    return bool(re.match(r"^(public domain|pd\b|cc0|cc by( sa)?\b)", c))


MIN_ANCHO_EPOCA = 500   # las fotos de la época del hecho (las viejas son chicas): ver motivo_foto


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


def fotos_del_evento(wiki: Wiki, e: Evento) -> tuple[list[Foto], dict]:
    """Las fotos del artículo del evento (`e.paginas[0]`) que pasan las reglas, en su orden, y por
    qué quedaron afuera las otras."""
    titulo = e.paginas[0]
    archivos = list(dict.fromkeys(wiki.archivos(e.lang, titulo)))
    return filtrar_infos(wiki, e.lang, wiki.info(e.lang, archivos), titulo, e.anio)


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
        bajadas.append(f)
    return bajadas, []


def es_de_otra_fuente(f: Foto) -> bool:
    """Las que no son de Wikimedia: su `archivo` es "openverse:…", "europeana:…", etc."""
    return not f.archivo.startswith("File:") and ":" in f.archivo.split(" ")[0]


def creditos(fotos: list[Foto]) -> str:
    """Autor y licencia de cada foto, en el orden en que aparecen. Va al final de la descripción."""
    lineas = ["Fotos:" if any(es_de_otra_fuente(f) for f in fotos) else "Fotos (Wikimedia Commons):"]
    for i, f in enumerate(fotos, 1):
        lineas.append(f"{i}. {f.autor} — {f.licencia}" + (f" — {f.pagina}" if f.pagina else ""))
    return "\n".join(lineas)


# ---- 3. guion ------------------------------------------------------------------------

SISTEMA_GUION = """Escribís la voz en off de un video vertical de 35 a 45 segundos para "Pequeña Historia",
un canal de efemérides para público joven, en español rioplatense (vos, no tú).

REGLA DE ORO: usás SOLO lo que dice el texto del artículo que te paso. Nada de tu memoria: ni un
nombre, ni un número, ni una fecha que no esté ahí. Si el artículo no lo dice, no lo digas.

- La primera frase arranca EXACTAMENTE con "Un día como hoy, en <año>," y sigue con el gancho.
- Tono: como alguien que te cuenta algo que lo sorprendió, con ganas. Nada de tono de manual.
- Frases CORTAS: ninguna de más de 14 palabras. Mejor dos frases que una larga con comas.
- Al menos UNA pregunta ("¿Sabés qué hizo después?") y al menos UNA exclamación ("¡Y funcionó!")
  en el medio del guion, para que no suene plano.
- Cierre con gancho: la última frase es una pregunta al público o una exclamación que deje algo
  picando (termina con "?" o "!"). Nada de cierres tipo "y así fue".
- Entre 80 y 100 palabras en total (contalas: menos de 70 queda corto y más de 105 se pasa de
  45 segundos), en 8 a 14 frases, habladas, no escritas. Si el artículo da para poco,
  contá más detalle de lo que SÍ dice.
- Números: solo los que están en el artículo, escritos igual. Nada de "hoy tiene millones de…"
  si el artículo no lo dice con esas palabras.
- Sin emojis, sin hashtags, sin "suscribite".
""" + REGLAS_CLARIDAD + """
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
Respondé solo con el JSON pedido."""

SCHEMA_GUION = {
    "type": "OBJECT",
    "properties": {
        "frases": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"texto": {"type": "STRING"}, "mostrar": {"type": "STRING"},
                           "presente": {"type": "BOOLEAN"}, "accion": {"type": "BOOLEAN"}},
            "required": ["texto", "mostrar", "presente", "accion"]}},
        "idea_clave": {"type": "STRING"},
        "claves": {"type": "ARRAY", "items": {"type": "STRING"}},
        "titulo": {"type": "STRING"},
        "descripcion": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tono": {"type": "STRING", "enum": ["alegre", "epico", "misterioso", "curioso", "emotivo"]},
    },
    "required": ["frases", "idea_clave", "titulo", "descripcion", "hashtags"],
}


def _numeros(t: str) -> set[str]:
    """Números normalizados: "1.000", "1,000" y "1000" son lo mismo."""
    return {re.sub(r"[.,](?=\d{3}\b)", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", t)}


_NUM = (r"un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince|"
        r"dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|"
        r"cien|ciento|cientos|\w+cientos|\w+cientas|mil|miles|millon|millones|billon|billones|"
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


def no_respaldados(guion: str, fuente: str) -> list[str]:
    """Nombres, números y meses del guion que NO están en el artículo (ni en el texto del evento).

    Los nombres salen de la heurística de mayúscula en medio de la oración (la misma de los títulos
    de los clips). Los números en cifras se comparan normalizados; los escritos con letras, como
    frase ("mil millones" tiene que estar tal cual): el 2026-09-27 el primer guion real dijo "más
    de mil millones de búsquedas diarias", que no estaba en el artículo, y el chequeo de cifras no
    lo vio. Los meses, en castellano o en inglés."""
    fuente_n = _norm(fuente)
    palabras_fuente = set(re.findall(r"[a-z0-9]+", fuente_n))
    faltan = []
    for frase in re.split(r"(?<=[.!?¿¡])\s+", guion):
        for nombre in nombres_propios(frase):
            if _norm(nombre) not in palabras_fuente:
                faltan.append(nombre)
    nums_fuente = _numeros(fuente)
    faltan += [n for n in sorted(_numeros(guion)) if n not in nums_fuente]
    faltan += [f for f in _numeros_en_letras(_norm(guion)) if f not in fuente_n]
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


def validar_guion(d: dict, anio: int, fuente: str) -> list[str]:
    if not isinstance(d, dict) or not isinstance(d.get("frases"), list) or not d["frases"]:
        return ["faltan las frases"]
    frases = [str((f or {}).get("texto") or "").strip() for f in d["frases"]]
    mostrar = [str((f or {}).get("mostrar") or "").strip() for f in d["frases"]]
    texto = " ".join(frases)
    errores = []
    n = len(re.findall(r"\S+", texto))
    # El aviso dice cuánto y qué hacer: con "tienen que ser entre 85 y 105" a secas, flash-lite
    # devolvió 75, 68 y 68 palabras en la prueba del 28/09, sin moverse.
    if n < PALABRAS_MIN:
        errores.append(f"el guion tiene {n} palabras y el mínimo es {PALABRAS_MIN}: te faltan "
                       f"{PALABRAS_MIN - n + 5} palabras. Agregá 2 o 3 frases cortas que expliquen "
                       f"mejor el cómo o el porqué, con lo que dice el artículo")
    elif n > PALABRAS_MAX:
        errores.append(f"el guion tiene {n} palabras y el máximo es {PALABRAS_MAX}: sacá "
                       f"{n - PALABRAS_MAX + 5} palabras (datos, no la explicación)")
    if not _norm(frases[0]).startswith("un dia como hoy") or str(anio) not in frases[0]:
        errores.append(f'la primera frase tiene que arrancar con "Un día como hoy, en {anio},"')
    # Pedido 2026-09-27 ("la voz suena triste y plana"): frases cortas, al menos una pregunta y
    # una exclamación, y cierre con gancho. Piper entona distinto una frase con ¿? o ¡!.
    if not frases[-1].rstrip().endswith(("?", "!")):
        errores.append("la última frase tiene que ser un gancho: una pregunta (?) o una exclamación (!)")
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
    faltan = no_respaldados(texto, fuente)
    if faltan:
        errores.append("esto NO está en el artículo, sacalo o cambialo por lo que dice el artículo: "
                       + ", ".join(faltan))
    titulo = str(d.get("titulo") or "").strip()
    if not titulo or len(titulo) > 55:
        errores.append("el título tiene que tener entre 1 y 55 caracteres")
    tags = d.get("hashtags") or []
    if not (3 <= len(tags) <= 5 and "#Shorts" in tags
            and all(re.fullmatch(r"#[^\W_]\w*", str(t)) for t in tags)):
        errores.append("hashtags: entre 3 y 5, de una palabra, incluido #Shorts")
    return errores


MAX_VIDEOS = 3


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


def escribir_guion(cliente, e: Evento, fuente: str, correccion: str = "", anterior: str = "",
                   reintentos: int = 2) -> Guion:
    """Gemini con el artículo, SIN fotos: el guion y qué mostrar en cada frase. Las fotos se buscan
    después para cada frase (`fotos_para_guion`). Reintenta con los errores de la validación."""
    prompt = (f"Hecho ({e.anio}): {e.texto}\n\nTEXTO DEL ARTÍCULO (lo único que podés usar):\n"
              f"{fuente[:12000]}")
    if correccion:
        prompt += f"\n\nEl guion anterior no sirvió:\n{anterior}\nLo que hay que cambiar: {correccion}"
    errores: list[str] = []
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        d = json.loads(cliente.json(SISTEMA_GUION, prompt + extra, SCHEMA_GUION, temperatura=0.5))
        errores = validar_guion(d, e.anio, fuente + "\n" + e.texto + f" {e.anio}")
        if not errores:
            return Guion(frases=[f["texto"].strip() for f in d["frases"]], fotos=[],
                         descartadas=[], titulo=d["titulo"].strip(),
                         descripcion=d["descripcion"].strip(), hashtags=list(d["hashtags"]),
                         tono=d.get("tono") if d.get("tono") in TONOS_GUION else "",
                         mostrar=[f["mostrar"].strip() for f in d["frases"]],
                         idea_clave=str(d["idea_clave"]).strip(),
                         presente=[bool(f.get("presente")) for f in d["frases"]],
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

`descartadas`: MIRÁ las fotos y descartá las que no sirven para nada: mapas, gráficos, diagramas,
banderas, escudos, firmas, logos, capturas de pantalla, retratos de alguien que NO protagoniza el
hecho, fotos de otro tema, y cualquier imagen violenta o con muertos o heridos. Nunca las pongas en
ninguna frase.
Respondé solo con el JSON pedido."""

SCHEMA_FOTOS = {
    "type": "OBJECT",
    "properties": {
        "frases": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"se_ve": {"type": "STRING"},
                           "fotos": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                           "de_epoca": {"type": "BOOLEAN"}, "seguro": {"type": "BOOLEAN"},
                           "video": {"type": "INTEGER"}, "momento": {"type": "INTEGER"},
                           "video_de_epoca": {"type": "BOOLEAN"}},
            "required": ["se_ve", "fotos", "de_epoca", "seguro"]}},
        "descartadas": {"type": "ARRAY", "items": {"type": "INTEGER"}},
    },
    "required": ["frases", "descartadas"],
}

FOTOS_ARTICULO_MAX = 8     # del artículo del hecho: son candidatas para todas las frases
FOTOS_BUSQUEDA_MAX = 4     # de Commons, por frase
POOL_MAX = 40              # las que ve Gemini en la llamada (cada una ~250 tokens)


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
        if ok and (f or {}).get("de_epoca") is False and not hoy:
            ok = ok[1:]
        # Relevancia dura (2026-10-02: en la de 4chan entró una página militar de Facebook): si
        # Gemini no está seguro de que la primera muestre lo que dice la frase, sale.
        if ok and (f or {}).get("seguro") is False:
            ok = ok[1:]
        rankings.append(ok[:ilustrar.RANKING_MAX])
    return rankings, descartadas


def elegir_fotos(cliente, g: Guion, pool: list[Foto], candidatas: list[list[int]],
                 propias: list[list[int]] | None = None, reintentos: int = 1,
                 avisar=log.info, anio: int | None = None, videos: dict | None = None,
                 elegidos: dict | None = None) -> tuple[list[list[int]], set[int]]:
    """UNA llamada: Gemini ve todas las fotos y ordena las que sirven para cada frase.
    `propias`: las que salieron de la búsqueda de esa frase (se le muestran primero). `anio`: el
    del hecho; junto con el año de cada foto, para que confirme la época (`de_epoca`).
    `videos`: {frase: [Video con sus cuadros]} de las frases de acción; en la MISMA llamada Gemini
    elige cuál y en qué momento, y lo elegido queda en `elegidos` ({frase: Video})."""
    lineas = []
    for i, (frase, cands) in enumerate(zip(g.frases, candidatas), 1):
        mostrar = g.mostrar[i - 1] if i - 1 < len(g.mostrar) else ""
        suyas = propias[i - 1] if propias else []
        hoy = " (habla de hoy)" if i - 1 < len(g.presente) and g.presente[i - 1] else ""
        lineas.append(f"frase {i}{hoy}: {frase}\n  mostrar: {mostrar}\n  candidatas: "
                      + ", ".join(str(c + 1) for c in cands)
                      + (f"\n  de su búsqueda: {', '.join(str(c + 1) for c in suyas)}" if suyas else ""))
    epigrafes = "\n".join(f"foto {k} ({f.anio or 'sin fecha'}): {f.epigrafe[:120]}"
                          for k, f in enumerate(pool, 1))
    prompt = ((f"EL HECHO ES DE {anio}.\n\n" if anio else "") + "FRASES:\n" + "\n".join(lineas)
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
    error = ""
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior no servía: {error}" if error else ""
        d = json.loads(cliente.json(SISTEMA_FOTOS, prompt + extra, SCHEMA_FOTOS, temperatura=0.2,
                                    imagenes=imagenes))
        try:
            rankings, malas = rankings_de(d, candidatas, g.presente)
        except ValueError as e:
            error = str(e)
            continue
        # Con videos, después de las fotos van sus cuadros: Gemini a veces "descarta" esos
        # números, que no son fotos (en la muestra del Sputnik tiró un IndexError).
        malas = {x for x in malas if 0 <= x < len(pool)}
        for i, (f, rk) in enumerate(zip(d["frases"], rankings), 1):   # para juzgar la elección
            epoca = "" if (f or {}).get("de_epoca") is not False else " (NO es de la época)"
            avisar(f"    frase {i}: {[x + 1 for x in rk]} — se ve: "
                   f"{str((f or {}).get('se_ve'))[:80]}{epoca}")
        if elegidos is not None:
            elegidos.update(video_elegido(d["frases"], videos, g.presente, avisar))
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
    for i in (g.accion if frases is None else frases):
        if i >= len(g.mostrar):
            continue
        hoy = i < len(g.presente) and g.presente[i]
        vs = buscador.candidatos(g.mostrar[i], anio, hoy, avisar, tema=tema)[:4]
        vs = [vl.sacar_frames(v, carpeta / "videos", f"f{i:02d}_v{k}") for k, v in enumerate(vs)]
        out[i] = [v for v in vs if v.frames]
        avisar(f"    frase {i + 1} (acción): {len(out[i])} videos candidatos "
               f"({', '.join(v.etiqueta() for v in out[i]) or 'ninguno'})")
    return out


def fotos_para_guion(wiki: Wiki, cliente, e: Evento, g: Guion, fotos_articulo: list[Foto],
                     carpeta: Path, avisar=log.info, pool: list[Foto] | None = None,
                     descartadas: set[int] | None = None, videos: bool = False,
                     buscador=None, fuentes=None) -> tuple[list[Foto], Guion]:
    """Busca candidatas para cada frase (las del artículo + Commons con su `mostrar`), las baja,
    Gemini elige, y arma la foto de cada frase con las reglas de `ilustrar`. Devuelve el pool (las
    fotos que se bajaron, en su numeración) y el guion con `fotos`, `ranking` y `descartadas`.

    `pool`: el de una propuesta anterior (✏️), para que los números no cambien. NarrarError si no
    se llega a ilustrar.MIN_FOTOS_DISTINTAS."""
    pool = list(pool or [])
    por_archivo = {f.archivo: i for i, f in enumerate(pool)}
    descartadas = set(descartadas or ())

    def sumar(fotos: list[Foto], cuantas: int) -> list[int]:
        nuevas = [f for f in fotos if f.archivo not in por_archivo][:cuantas]
        espacio = POOL_MAX - len(pool)
        # El nombre lleva la posición en el pool: con ✏️ el pool crece y nada pisa lo anterior.
        bajadas, _ = bajar_fotos(wiki, nuevas, carpeta, f"{e.anio}_p{len(pool):02d}",
                                 max(espacio, 0), avisar)
        for f in bajadas:
            por_archivo[f.archivo] = len(pool)
            pool.append(f)
        return [por_archivo[f.archivo] for f in fotos if f.archivo in por_archivo][:cuantas]

    del_hecho = [i for i in sumar(fotos_articulo, FOTOS_ARTICULO_MAX) if i not in descartadas]
    propias, descartes = [], {}
    from . import fuentes_fotos
    from .videos_libres import consultas as achicar_consultas, es_de_espacio, sin_anios

    argentino = fuentes_fotos.es_argentino(f"{e.texto} {' '.join(e.paginas)}")
    otras = fuentes or fuentes_fotos.Fuentes()
    for i, mostrar in enumerate(g.mostrar):
        # Commons, de la búsqueda puntual a la general (2026-10-02: "1924 Onzari Argentina" pedía
        # todas las palabras y no traía nada) y, si el hecho es argentino, las fotos PD-AR-Photo.
        qs = achicar_consultas(mostrar)
        # La búsqueda tal cual primero (con el año, en Commons a veces trae más que sin él).
        consultas_commons = list(dict.fromkeys([mostrar] + qs[:3])) +             ([f'{sin_anios(mostrar)} incategory:"PD-AR-Photo"'] if argentino else [])
        halladas: list[Foto] = []
        for q in consultas_commons:
            if len(halladas) >= FOTOS_BUSQUEDA_MAX:
                break
            nuevas, desc = filtrar_infos(wiki, "commons", wiki.buscar_commons(q), f"Commons: {mostrar}",
                                         e.anio)
            for k, v in desc.items():
                descartes[k] = descartes.get(k, 0) + v
            halladas += [f for f in nuevas if f.archivo not in {h.archivo for h in halladas}]
        # Si Commons no alcanza: las otras fuentes, en orden (fuentes_fotos).
        if len(halladas) < FOTOS_BUSQUEDA_MAX:
            hoy = i < len(g.presente) and g.presente[i]
            for h in otras.buscar(qs, hoy, es_de_espacio(mostrar), FOTOS_BUSQUEDA_MAX - len(halladas), avisar):
                halladas.append(Foto(archivo=h["archivo"], url=h["url"], ancho=h["ancho"], alto=h["alto"],
                                     licencia=h["licencia"], autor=h["autor"] or "autor desconocido",
                                     epigrafe=h["epigrafe"][:160], pagina=h["pagina"],
                                     articulo=f"{h['fuente']}: {mostrar}", anio=h["anio"]))
        propias.append([i for i in sumar(halladas, FOTOS_BUSQUEDA_MAX) if i not in descartadas])
    # Regla fija de época: las fotos sacadas más de MARGEN_EPOCA años después del hecho no son
    # candidatas de las frases del pasado. Las del artículo del hecho quedan de respaldo igual
    # (de_reserva): antes una del artículo repetida que una moderna.
    modernas = {i for i, f in enumerate(pool) if f.anio and f.anio > e.anio + MARGEN_EPOCA}
    presente = [i < len(g.presente) and g.presente[i] for i in range(len(g.frases))]
    avisar(f"  fotos: {len(pool)} bajadas ({len(del_hecho)} del artículo, {len(modernas)} de más de "
           f"{MARGEN_EPOCA} años después de {e.anio}); descartes {descartes}")
    # Cada frase puede elegir CUALQUIER foto del pool, empezando por las de su búsqueda: en la
    # prueba del 28/09 la frase "el hongo mataba a las bacterias" solo podía elegir entre lo que
    # trajo su búsqueda (mala) y no las placas de Petri que había traído otra frase.
    todas = [i for i in range(len(pool)) if i not in descartadas]
    # Capturas de páginas web o redes: solo para las frases que hablan de una página (2026-10-02).
    capturas = {i for i, f in enumerate(pool) if _CAPTURA.search(f"{f.archivo} {f.epigrafe}")}
    de_web = [bool(_HABLA_DE_WEB.search(f"{g.frases[i]} {g.mostrar[i] if i < len(g.mostrar) else ''}"))
              for i in range(len(g.frases))]
    candidatas = [[x for x in dict.fromkeys(p + del_hecho + todas)
                   if (hoy or x not in modernas) and (web or x not in capturas)]
                  for p, hoy, web in zip(propias, presente, de_web)]
    candidatos_video = (buscar_videos(g, e.anio, carpeta, buscador, avisar, tema=e.paginas[0])
                        if videos else {})
    elegidos: dict = {}
    rankings, vistas_malas = elegir_fotos(cliente, g, pool, candidatas, propias, avisar=avisar,
                                          anio=e.anio, videos=candidatos_video, elegidos=elegidos)
    g.con_videos = videos
    g.videos = {str(i): v.a_dict() for i, v in elegidos.items()}
    g.con_video = sorted(elegidos)
    descartadas |= vistas_malas
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
    g.fotos = ilustrar.completar_distintas(ilustrar.asignar(rankings, reserva), rankings, reserva,
                                           g.minimo_fotos)
    errores = ilustrar.errores_plan(plan_estimado(g, len(pool)), g.minimo_fotos)
    if any("aparecen más de" in e for e in errores):
        # Pocas fotos para tantas frases sin repetir más de 2 veces: como con menos de 4, al siguiente.
        raise PocasFotos(pool, g, disponibles)
    if errores:
        raise NarrarError("las fotos no alcanzan: " + "; ".join(errores))
    if g.minimo_fotos < ilustrar.MIN_FOTOS_ABSOLUTO:
        raise PocasFotos(pool, g, disponibles)
    return pool, g


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
    malas, modernas = set(g.descartadas), set(g.modernas)
    del_hecho = [x for x in g.del_hecho if x not in malas]
    rankeadas = [x for x in dict.fromkeys(x for r in g.rankings() for x in r)
                 if x not in malas and x not in modernas]
    return list(dict.fromkeys(del_hecho + rankeadas)) or \
        [i for i in range(n_pool) if i not in malas and i not in modernas]


def duraciones_estimadas(g: Guion) -> list[float]:
    return [max(1.0, len(f.split()) / PALABRAS_POR_S_VOZ) for f in g.frases]


def plan_estimado(g: Guion, n_pool: int) -> list[tuple[int, int, float]]:
    """(frase, foto, segundos) con la duración estimada de cada frase: lo que muestra la hoja."""
    return ilustrar.tramos(g.fotos, duraciones_estimadas(g), g.rankings(), de_reserva(g, n_pool))


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
                  ancho: int = 1000, miniatura: int = 220, videos: dict | None = None) -> Path:
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
    hoja = Image.new("RGB", (ancho, sum(r.height + 4 for r in renglones)), (0, 0, 0))
    y = 0
    for r in renglones:
        hoja.paste(r, (0, y))
        y += r.height + 4
    salida.parent.mkdir(parents=True, exist_ok=True)
    hoja.save(salida, quality=85)
    return salida


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
    if g.idea_clave:
        lineas.append(f"<b>Tiene que quedar claro:</b> {html.escape(g.idea_clave)}")
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
                efecto: str = "") -> Path:
    """Una foto por frase (cada tramo dura lo que su frase), la voz, y los subtítulos + el año que
    ya están en `dir_subs/subs.ass`. Cada tramo se encodea aparte y al final se pegan."""
    from PIL import Image

    from .videos_libres import filtro_video

    W, H = render.ancho, render.alto
    partes = []
    for i, (foto, dur) in enumerate(tramos):
        frames = max(1, int(round(dur * fps)))
        if Path(foto).suffix.lower() in (".mp4", ".webm", ".mov", ".mkv"):
            # Un tramo de video: dura EXACTO lo de su frase (si es más corto, se repite).
            parte = dir_subs / f"tramo_{i:02d}.mp4"
            run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-stream_loop", "-1", "-i", str(Path(foto).resolve()),
                 "-filter_complex", filtro_video(W, H, render.blur_sigma, fps,
                                                 *(encuadres or {}).get(str(foto), (0.5, False))),
                 "-map", "[v]", "-an",
                 "-frames:v", str(frames), "-c:v", "libx264", "-preset", render.x264_preset,
                 "-crf", "18", "-pix_fmt", "yuv420p", str(parte.resolve())])
            partes.append(parte)
            continue
        fx, fy = foco(foto)
        parte = dir_subs / f"tramo_{i:02d}.mp4"
        efecto = efecto or ("parallax" if parallax else "zoom")
        if efecto == "fija":
            # Foto quieta: un solo cuadro (encuadre con caras enteras) repetido lo que dura el tramo.
            import cv2

            from . import parallax as px

            fija = dir_subs / f"fija_{i:02d}.png"
            cv2.imwrite(str(fija), px.cuadro_fijo(Path(foto).resolve(), W, H, render.blur_sigma, (fx, fy)))
            run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-loop", "1", "-framerate", str(fps), "-i", str(fija.resolve()),
                 "-frames:v", str(frames), "-c:v", "libx264", "-preset", render.x264_preset,
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
             "-map", "[v]", "-frames:v", str(frames), "-c:v", "libx264", "-preset",
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
         "-c:v", "libx264", "-preset", render.x264_preset, "-crf", str(render.crf),
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


def proponer(wiki: Wiki, cliente, dia: date, carpeta: Path, avisar=log.info,
             correccion: str = "", saltear: int = 0, hecho: str = "", videos: bool = False) -> Propuesta:
    """Elige el evento, escribe el guion (con qué mostrar en cada frase), busca y elige las fotos
    de cada frase. Si un evento no llega a ilustrar.MIN_FOTOS_DISTINTAS fotos distintas que
    sirvan, pasa al siguiente del ranking.

    El ranking es de ELEGIDOS y no de 3: el 2026-09-27 los 3 primeros (Google, el ovni de Vorónezh,
    E=mc²) no llegaban a 4 fotos del artículo. Desde el 2026-09-28 las fotos salen también de
    Commons, frase por frase, así que eso pasa menos; cada evento que se intenta son 2 llamadas
    (guion y fotos), por eso el tope de MAX_GUIONES.

    `hecho`: solo los eventos cuyo texto lo contiene ("penicilina"): para rehacer uno a mano."""
    todos = wiki.eventos("es", dia) + wiki.eventos("en", dia)
    candidatos, motivos = [], {}
    for e in todos:
        m = motivo_evento(e, date.today())
        if m:
            motivos[m] = motivos.get(m, 0) + 1
        elif not hecho or _norm(hecho) in _norm(e.texto):
            candidatos.append(e)
    avisar(f"{len(todos)} hechos del {dia:%d/%m}; {len(candidatos)} pasan el primer filtro {motivos}")
    if not candidatos:
        raise NarrarError("Ningún hecho de hoy pasa el filtro de temas sensibles"
                          + (f" (con «{hecho}»)" if hecho else "") + ".")
    elegidos = elegir(cliente, candidatos)
    avisar("Gemini eligió: " + " | ".join(f"{candidatos[i].anio} {candidatos[i].texto[:50]} [{a}]"
                                          for i, a in elegidos))
    descartes: dict = {}
    guiones = 0
    fallas: list[str] = []
    respaldo = None   # (evento, fuente, PocasFotos, fotos): el de más fotos de los que no llegaron a 4
    for i, articulo in elegidos[saltear:]:
        if guiones >= MAX_GUIONES:
            break
        # El artículo del evento va primero: de ahí salen las fotos y el texto del guion.
        e = Evento(candidatos[i].lang, candidatos[i].anio, candidatos[i].texto,
                   [articulo] + [x for x in candidatos[i].paginas if x != articulo])
        fotos, desc = fotos_del_evento(wiki, e)
        for k, v in desc.items():
            descartes[k] = descartes.get(k, 0) + v
        avisar(f"{e.anio} {e.texto[:60]}: {len(fotos)} fotos del artículo pasan las reglas {desc}")
        fuente = texto_fuente(wiki, e)
        guiones += 1
        try:
            g = escribir_guion(cliente, e, fuente, correccion)
            pool, g = fotos_para_guion(wiki, cliente, e, g, fotos, carpeta, avisar, videos=videos)
        except PocasFotos as pocas:
            # Menos de 4 fotos de época: al siguiente. Se guarda el que más tenga, por si ninguno llega.
            avisar(f"  {pocas}")
            fallas.append(f"{e.anio}: {pocas}")
            if respaldo is None or pocas.disponibles > respaldo[3]:
                respaldo = (e, fuente, pocas, pocas.disponibles)
            continue
        except NarrarError as err:
            avisar(f"  no salió: {err}")
            fallas.append(f"{e.anio}: {err}")
            continue
        for k in g.descartadas:        # para poder juzgar si el descarte visual es razonable
            if 0 <= k < len(pool):
                avisar(f"    descartada {k + 1}: {pool[k].epigrafe[:90]}")
        return Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in pool],
                         reserva=[], guion=g.a_dict(), fuente=fuente[:20000], descartes=descartes)
    if respaldo:
        e, fuente, pocas, n = respaldo
        avisar(f"Ningún hecho llegó a {ilustrar.MIN_FOTOS_ABSOLUTO} fotos de época: uso {e.anio} "
               f"({n} fotos), con aviso")
        pocas.guion.sin_alternativa = True
        return Propuesta(fecha=dia.isoformat(), evento=e.a_dict(),
                         fotos=[f.a_dict() for f in pocas.pool], reserva=[],
                         guion=pocas.guion.a_dict(), fuente=fuente[:20000], descartes=descartes)
    # Con la causa de cada uno: el 28/09 decía "no llegó a 6 fotos" cuando lo que falló fue el guion.
    raise NarrarError(f"Ninguno de los {len(elegidos)} hechos elegidos salió ({guiones} intentados). "
                      + " | ".join(fallas)[:600])


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
                  avisar=log.info) -> Propuesta:
    """✏️: el guion de nuevo con la corrección, y las fotos de sus frases otra vez. El pool de antes
    se conserva (los números no cambian) y lo ya descartado sigue descartado."""
    e = Evento(**p.evento)
    anterior = Guion.de_dict(p.guion)
    g = escribir_guion(cliente, e, p.fuente, correccion=correccion, anterior=anterior.texto)
    fotos, _ = fotos_del_evento(wiki, e)
    try:
        pool, g = fotos_para_guion(wiki, cliente, e, g, fotos, carpeta, avisar,
                                   pool=[Foto.de_dict(f) for f in p.fotos],
                                   descartadas=set(anterior.descartadas), videos=anterior.con_videos)
    except PocasFotos as pocas:   # es el hecho que ya se eligió: se sigue con lo que haya, con aviso
        pool, g = pocas.pool, pocas.guion
        g.sin_alternativa = anterior.sin_alternativa
    return Propuesta(fecha=p.fecha, evento=p.evento, fotos=[f.a_dict() for f in pool],
                     reserva=p.reserva, guion=g.a_dict(), fuente=p.fuente, descartes=p.descartes)


# La música de fondo vive en musica.py (biblioteca, elección por tono, mezcla con ducking).


VIDEO = -1   # en un plan, (frase, VIDEO, segundos) = esa frase entera va con su video


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


def plan_de(p: Propuesta, duraciones: list[float] | None = None) -> list[tuple[int, int, float]]:
    """(frase, foto, segundos) de la propuesta: con las duraciones reales de la voz, o estimadas.
    Las frases con video salen como (frase, VIDEO, segundos de la frase)."""
    g = Guion.de_dict(p.guion)
    if duraciones is None:
        return con_videos(plan_estimado(g, len(p.fotos)), g)
    return con_videos(ilustrar.tramos(g.fotos, duraciones, g.rankings(), de_reserva(g, len(p.fotos))), g)


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
    orden = list(dict.fromkeys(f for _, f, _ in (plan or plan_de(p)) if f != VIDEO))
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
    """atempo: más rápido sin cambiar el tono. En el mismo archivo."""
    tmp = wav.with_name(wav.stem + ".rapido.wav")
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav.resolve()),
         "-af", f"atempo={factor:.4f}", str(tmp.resolve())])
    tmp.replace(wav)
    return wav


def voz_efemeride(frases: list[str], settings, carpeta: Path, avisar=log.info,
                  tts=None) -> tuple[Path, list[float] | None, str]:
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
    if cfg.voz_motor == "gemini":
        try:
            claves = claves_activas() if env("GEMINI_API_KEY", requerido=False) else []
            if not claves:
                raise GeminiError("sin GEMINI_API_KEY")
            kw = dict(instruccion=cfg.tts_instruccion, voz=cfg.tts_voz, modelo=cfg.tts_modelo)
            pcm, sr = (tts(claves[0][1], " ".join(frases), **kw) if tts else
                       hablar_con_claves(claves, " ".join(frases), aviso=aviso_por_telegram,
                                         uso=registrar_uso, **kw))
            wav = _escribir_wav(pcm, sr, carpeta / "voz.wav")
            dur = len(pcm) / 2 / sr
            if dur > cfg.tts_max_s:
                factor = min(dur / cfg.tts_max_s, cfg.tts_acelerar_max)
                acelerar(wav, factor)
                avisar(f"voz Gemini de {dur:.1f} s: acelerada ×{factor:.2f}")
            return wav, None, f"gemini:{cfg.tts_voz}"
        except GeminiError as e:
            avisar(f"Gemini TTS no anduvo ({str(e)[:120]}): sigo con Piper")
            motivo = "sin cuota" if "quota" in str(e).lower() or "429" in str(e) else "Gemini no respondió"
    ajustes = replace(settings.voz, length_scale=cfg.piper_length_scale,
                      noise_scale=cfg.piper_noise_scale, noise_w_scale=cfg.piper_noise_w_scale,
                      semitonos=cfg.piper_semitonos)
    modelo = Path(settings.voz.modelo)
    if not modelo.exists():
        raise NarrarError(f"Falta la voz en {modelo}")
    wav, duraciones = narrar.sintetizar_frases(frases, modelo, carpeta / "voz.wav", ajustes=ajustes)
    # El motivo viaja pegado ("piper:…|sin cuota"): la entrega dice qué voz salió y por qué.
    return wav, duraciones, f"piper:{modelo.stem}" + (f"|{motivo}" if motivo else "")


def texto_voz(motor: str) -> str:
    """Lo que dice el mensaje del video: "Voz: Laomedeia" o "Voz: Piper (respaldo, sin cuota)"."""
    if motor.startswith("gemini:"):
        return f"Voz: {motor.split(':', 1)[1]}"
    motivo = motor.partition("|")[2]
    return "Voz: Piper (respaldo" + (f", {motivo}" if motivo else "") + ")"


def es_piper(motor: str) -> bool:
    return motor.startswith("piper:")


def hacer_video(p: Propuesta, settings, carpeta: Path, avisar=log.info, conn=None) -> dict:
    """Propuesta aprobada → mp4 + meta listo para `enviar_clip`. Esto es lo que gasta la Pi:
    Piper, Whisper sobre la voz y un encode por foto.

    `conn`: la DB, para elegir la música sin repetir los últimos temas ni usar los vetados por
    /reclamo, y anotar cuál se usó. Sin DB se elige igual, sin esas dos reglas."""
    from . import musica, narrar, subtitles as sub

    g, e = Guion.de_dict(p.guion), Evento(**p.evento)
    t0 = time.time()
    wav, duraciones, motor = voz_efemeride(g.frases, settings, carpeta, avisar)
    fin = narrar.duracion_wav(wav)
    avisar(f"voz ({motor}): {fin:.1f} s en {time.time() - t0:.0f} s")
    t0 = time.time()
    # Whisper da los tiempos; el texto de los subtítulos es el del guion aprobado.
    oidas = narrar.palabras_de_voz(wav, settings.subtitulos)
    oidas, recortado = narrar.recortar_inicio(wav, oidas, g.frases)
    if recortado:
        fin = narrar.duracion_wav(wav)
        avisar(f"la voz dijo {recortado:.1f} s de algo antes del guion: recortado")
    palabras, inicios = narrar.alinear_a_guion(oidas, g.frases, fin)
    if duraciones is None:   # Gemini: un solo audio, los cortes salen de la alineación
        duraciones = [b - a for a, b in zip(inicios, inicios[1:] + [fin])]
    subs = sub.palabra_por_palabra(palabras, settings.subtitulos)
    sub.escribir_ass(subs, carpeta / "subs.ass", settings.subtitulos, settings.render,
                     cartel=str(e.anio), cartel_s=2.0, cartel_grande=True)
    cfg_ef = settings.efemerides
    if cfg_ef.graficos:
        # El año contando (en vez de quieto) y las palabras clave grandes cuando la voz las dice.
        from . import graficos as gr

        gr.sacar_cartel(carpeta / "subs.ass")
        gr.agregar_al_ass(carpeta / "subs.ass",
                          gr.estilos(settings.render.ancho, settings.render.alto, settings.subtitulos.fuente),
                          gr.anio_contando(e.anio) + gr.claves_en_tiempo(palabras, g.claves))
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
    tramos = [(rutas_video[i] if f == VIDEO else Path(p.fotos[f]["ruta"]), s) for i, f, s in plan]
    mapa = None
    if cfg_ef.graficos:
        from . import graficos as gr

        # Un whoosh suave en cada cambio de foto o video (en la voz+música, antes de las reglas de
        # audio que aplica armar_video).
        cortes, t = [], 0.0
        for _, _, s in plan[:-1]:
            t += round(s * 30) / 30
            cortes.append(t)
        audio = gr.mezclar_whoosh(audio, cortes, gr.whoosh(carpeta / "whoosh.wav"),
                                  carpeta / "voz_musica_whoosh.wav")
        # El mapa con el punto, durante la segunda frase (si el artículo tiene coordenadas).
        try:
            wiki = Wiki()
            coords = wiki.coordenadas(e.lang, e.paginas[0])
            if coords and gr.distancia_ok(*coords) and len(inicios) > 1:
                desde = inicios[1]
                hasta = min(desde + 3.5, inicios[2] if len(inicios) > 2 else fin)
                mapa = (gr.mapa(wiki.mapa_base(carpeta), *coords, carpeta / "mapa.png"), desde, hasta)
                avisar(f"mapa: {coords[0]:.2f}, {coords[1]:.2f} de {desde:.1f} a {hasta:.1f} s")
        except (WikiError, OSError, KeyError, ValueError) as err:
            avisar(f"mapa: no salió ({str(err)[:100]})")
    t0 = time.time()
    dia = date.fromisoformat(p.fecha)
    clip_id = f"efemeride_{dia:%m%d}_{e.anio}"
    salida = armar_video(tramos, audio, carpeta, carpeta / f"{clip_id}.mp4", settings.render,
                         parallax=cfg_ef.parallax, mapa=mapa, encuadres=encuadres,
                         efecto=cfg_ef.efecto_fotos)
    avisar(f"video: {time.time() - t0:.0f} s, {len(tramos)} tramos, "
           f"{len({f for _, f, _ in plan if f != VIDEO})} fotos distintas, {len(rutas_video)} videos")
    for problema in chequear_audio(salida):
        avisar(f"⚠️ audio: {problema}")
    from .videos_libres import creditos as creditos_videos

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
                          "musica": tema.ruta if tema else None, "tono": g.tono, "voz": motor}}


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
