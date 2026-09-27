"""Efemérides para el canal "Pasó Hoy": un Short por día con un hecho de la fecha.

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

import html
import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import requests

from .media import find_bin, run
from .narrar import NarrarError
from .textos import nombres_propios

log = logging.getLogger(__name__)

# Wikimedia pide un User-Agent que diga qué es el bot. Sin mail a propósito.
UA = "PasoHoyBot/0.26 (bot personal de efemérides; python-requests)"
FEED = "https://{lang}.wikipedia.org/api/rest_v1/feed/onthisday/events/{mm:02d}/{dd:02d}"
API = "https://{lang}.wikipedia.org/w/api.php"

MIN_FOTOS = 4
MIN_ANCHO = 800          # la foto se escala a 1080 de ancho en fit_blur: menos que esto se nota
# Las que ve Gemini; el resto queda de reserva para "🔁 cambiar foto N". Eran 8: la Piedra de
# Rosetta tenía 11 que pasaban las reglas y quedó afuera con 3 que Gemini nunca vio.
MAX_FOTOS_GUION = 12
PALABRAS_MIN, PALABRAS_MAX = 88, 115   # 35-45 s a ~2,5 palabras por segundo (86 daba ~34 s)

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
    pass


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

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Foto":
        return cls(**d)


class Wiki:
    def __init__(self, session: requests.Session | None = None, timeout: float = 30,
                 sleep=time.sleep):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._sleep = sleep

    PAUSA_S = 0.5   # entre llamadas: el 2026-09-27, con varias corridas seguidas, la API dio 429

    def _pedir(self, url: str, params: dict | None = None, timeout: float | None = None):
        """GET con pausa entre llamadas y reintentos. Lo usan las consultas Y las descargas de
        fotos: upload.wikimedia.org también devuelve 429 (pasó bajando la foto del lanzamiento
        de la sonda Dawn, el 2026-09-27)."""
        for intento in range(4):
            self._sleep(self.PAUSA_S)
            try:
                r = self.session.get(url, params=params, timeout=timeout or self.timeout,
                                     headers={"User-Agent": UA})
            except requests.RequestException as e:
                error, espera = str(e), 3 * (intento + 1)
            else:
                if r.status_code == 200:
                    return r
                error = f"{r.status_code} {r.text[:150]}"
                if r.status_code < 500 and r.status_code != 429:
                    break
                # 429: la API dice cuánto esperar. Se respeta (con tope, para no colgar la escucha).
                pedido = r.headers.get("Retry-After", "")
                espera = min(int(pedido), 60) if pedido.isdigit() else 10 * (intento + 1)
            self._sleep(espera)
        raise WikiError(f"Wikipedia {url[:120]}: {error}")

    def _get(self, url: str, params: dict | None = None) -> dict:
        return self._pedir(url, params).json()

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

    def info(self, lang: str, archivos: list[str]) -> list[dict]:
        """imageinfo con licencia, autor y epígrafe. Sirve para archivos locales y de Commons."""
        out = []
        for i in range(0, len(archivos), 50):
            d = self._get(API.format(lang=lang), {
                "action": "query", "format": "json", "prop": "imageinfo",
                # 1280 es uno de los anchos estándar de las miniaturas de Wikimedia (1600 no lo es,
                # y para fotos más chicas devolvía el original: más pesado, y más 429).
                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1280,
                "iiextmetadatalanguage": "es", "titles": "|".join(archivos[i:i + 50])})
            for p in (d.get("query") or {}).get("pages", {}).values():
                if p.get("imageinfo"):
                    out.append({"archivo": p["title"], **p["imageinfo"][0]})
        return out

    def bajar(self, url: str, destino: Path) -> Path:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(self._pedir(url, timeout=60).content)
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


SISTEMA_ELEGIR = """Elegís efemérides para un canal de videos cortos, "Pasó Hoy", para un público
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
MAX_GUIONES = 2     # eventos que llegan a guion por día. Cada uno son hasta 3 llamadas (con los
                    # reintentos de la validación): peor caso 1 + 2 × 3 = 7 de las ~20 diarias


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


def motivo_foto(info: dict) -> str | None:
    """Por qué la foto no sirve, o None. Las reglas fijas: lo que se ve lo mira Gemini después."""
    em = info.get("extmetadata") or {}

    def meta(k: str) -> str:
        return sin_html((em.get(k) or {}).get("value", ""))

    if info.get("mime") not in _MIMES:
        return f"formato {info.get('mime')}"
    corta = meta("LicenseShortName")
    if meta("NonFree").lower() in ("true", "1") or not licencia_libre(corta):
        return f"licencia no libre ({corta or 'sin dato'})"
    if int(info.get("width") or 0) < MIN_ANCHO:
        return f"menos de {MIN_ANCHO} px ({info.get('width')})"
    texto = " ".join([info.get("archivo", "").replace("_", " "), meta("ObjectName"),
                      meta("ImageDescription"), meta("Categories").replace("|", " ")])
    m = _NO_FOTO.search(texto)
    if m:
        return f"no es una foto del hecho ({m.group(0).lower()})"
    return None


def a_foto(info: dict, articulo: str) -> Foto:
    em = info.get("extmetadata") or {}

    def meta(k: str) -> str:
        return sin_html((em.get(k) or {}).get("value", ""))

    epigrafe = meta("ImageDescription") or meta("ObjectName") or \
        info["archivo"].split(":", 1)[-1].rsplit(".", 1)[0].replace("_", " ")
    return Foto(archivo=info["archivo"], url=info.get("thumburl") or info.get("url") or "",
                ancho=int(info.get("width") or 0), alto=int(info.get("height") or 0),
                licencia=meta("LicenseShortName"), autor=meta("Artist") or "autor desconocido",
                epigrafe=epigrafe[:160], pagina=info.get("descriptionurl") or "", articulo=articulo)


def fotos_del_evento(wiki: Wiki, e: Evento) -> tuple[list[Foto], dict]:
    """Las fotos del artículo del evento (`e.paginas[0]`) que pasan las reglas, en su orden, y por
    qué quedaron afuera las otras."""
    fotos, descartes, vistos = [], {}, set()
    for titulo in e.paginas[:1]:
        archivos = [a for a in wiki.archivos(e.lang, titulo) if a not in vistos]
        vistos.update(archivos)
        for info in wiki.info(e.lang, archivos):
            m = motivo_foto(info)
            if m:
                descartes[m.split(" (")[0]] = descartes.get(m.split(" (")[0], 0) + 1
            else:
                fotos.append(a_foto(info, titulo))
    return fotos, descartes


def creditos(fotos: list[Foto]) -> str:
    """Autor y licencia de cada foto, en el orden en que aparecen. Va al final de la descripción."""
    lineas = ["Fotos (Wikimedia Commons):"]
    for i, f in enumerate(fotos, 1):
        lineas.append(f"{i}. {f.autor} — {f.licencia}" + (f" — {f.pagina}" if f.pagina else ""))
    return "\n".join(lineas)


# ---- 3. guion ------------------------------------------------------------------------

SISTEMA_GUION = """Escribís la voz en off de un video vertical de 35 a 45 segundos para "Pasó Hoy",
un canal de efemérides para público joven, en español rioplatense (vos, no tú).

REGLA DE ORO: usás SOLO lo que dice el texto del artículo que te paso. Nada de tu memoria: ni un
nombre, ni un número, ni una fecha que no esté ahí. Si el artículo no lo dice, no lo digas.

- La primera frase arranca EXACTAMENTE con "Un día como hoy, en <año>," y sigue con el gancho.
- La última frase es una pregunta al público (termina con "?").
- Entre 90 y 110 palabras en total (contalas: menos de 88 queda corto), en 8 a 12 frases cortas,
  habladas, no escritas. Si el artículo da para poco, contá más detalle de lo que SÍ dice.
- Números: solo los que están en el artículo, escritos igual. Nada de "hoy tiene millones de…"
  si el artículo no lo dice con esas palabras.
- Sin emojis, sin hashtags, sin "suscribite".
- Cada frase lleva `foto`: el número de la foto que se ve mientras se dice. Usá al menos 4 fotos
  distintas y la que mejor acompañe cada frase.
- `fotos_descartadas`: MIRÁ las fotos y descartá las que no sirven para contar el hecho: mapas,
  gráficos, diagramas, banderas, escudos, firmas, logos, retratos de una persona que NO
  protagoniza este hecho, fotos de otro tema, y cualquier imagen violenta o con muertos o
  heridos. No uses esas en ninguna frase.
- `titulo`: hasta 55 caracteres, con gancho, sin clickbait falso. `descripcion`: 1 a 3 frases
  sobre el hecho, sin hashtags ni links. `hashtags`: 3 a 5, incluido #Shorts.
Respondé solo con el JSON pedido."""

SCHEMA_GUION = {
    "type": "OBJECT",
    "properties": {
        "frases": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"texto": {"type": "STRING"}, "foto": {"type": "INTEGER"}},
            "required": ["texto", "foto"]}},
        "fotos_descartadas": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        "titulo": {"type": "STRING"},
        "descripcion": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["frases", "fotos_descartadas", "titulo", "descripcion", "hashtags"],
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
    fotos: list[int]                  # índice (desde 0) de la foto de cada frase
    descartadas: list[int]            # índices desde 0 que Gemini vio y no sirven
    titulo: str
    descripcion: str
    hashtags: list[str]

    @property
    def texto(self) -> str:
        return " ".join(self.frases)

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "Guion":
        return cls(**d)


def validar_guion(d: dict, anio: int, n_fotos: int, fuente: str) -> list[str]:
    if not isinstance(d, dict) or not isinstance(d.get("frases"), list) or not d["frases"]:
        return ["faltan las frases"]
    frases = [str((f or {}).get("texto") or "").strip() for f in d["frases"]]
    fotos = [(f or {}).get("foto") for f in d["frases"]]
    descartadas = {x for x in d.get("fotos_descartadas") or [] if isinstance(x, int)}
    texto = " ".join(frases)
    errores = []
    n = len(re.findall(r"\S+", texto))
    if not PALABRAS_MIN <= n <= PALABRAS_MAX:
        errores.append(f"el guion tiene {n} palabras: tienen que ser entre {PALABRAS_MIN} y {PALABRAS_MAX}")
    if not _norm(frases[0]).startswith("un dia como hoy") or str(anio) not in frases[0]:
        errores.append(f'la primera frase tiene que arrancar con "Un día como hoy, en {anio},"')
    if not frases[-1].rstrip().endswith("?"):
        errores.append("la última frase tiene que ser una pregunta al público")
    if any(not isinstance(f, int) or not 1 <= f <= n_fotos for f in fotos):
        errores.append(f"cada frase lleva una foto del 1 al {n_fotos}")
    elif set(fotos) & descartadas:
        errores.append(f"usaste fotos que descartaste: {sorted(set(fotos) & descartadas)}")
    elif len(set(fotos)) < min(MIN_FOTOS, n_fotos - len(descartadas)):
        errores.append(f"usá al menos {MIN_FOTOS} fotos distintas")
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


def escribir_guion(cliente, e: Evento, fuente: str, fotos: list[Foto], imagenes: list[bytes],
                   correccion: str = "", anterior: str = "", reintentos: int = 2) -> Guion:
    """Gemini con el artículo y las fotos. Reintenta con los errores de la validación."""
    lista = "\n".join(f"foto {i}: {f.epigrafe}" for i, f in enumerate(fotos, 1))
    prompt = (f"Hecho ({e.anio}): {e.texto}\n\nTEXTO DEL ARTÍCULO (lo único que podés usar):\n"
              f"{fuente[:12000]}\n\nFOTOS (la imagen k es la foto k):\n{lista}")
    if correccion:
        prompt += f"\n\nEl guion anterior no sirvió:\n{anterior}\nLo que hay que cambiar: {correccion}"
    errores: list[str] = []
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        d = json.loads(cliente.json(SISTEMA_GUION, prompt + extra, SCHEMA_GUION, temperatura=0.5,
                                    imagenes=imagenes))
        errores = validar_guion(d, e.anio, len(fotos), fuente + "\n" + e.texto + f" {e.anio}")
        if not errores:
            return Guion(frases=[f["texto"].strip() for f in d["frases"]],
                         fotos=[f["foto"] - 1 for f in d["frases"]],
                         descartadas=sorted({x - 1 for x in d["fotos_descartadas"]
                                             if isinstance(x, int) and 1 <= x <= len(fotos)}),
                         titulo=d["titulo"].strip(), descripcion=d["descripcion"].strip(),
                         hashtags=list(d["hashtags"]))
    raise NarrarError("El guion no pasó la validación: " + "; ".join(errores))


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


def hoja_de_fotos(fotos: list[Foto], salida: Path, columnas: int = 2, ancho: int = 420,
                  numeros: list[int] | None = None) -> Path:
    """Las fotos numeradas con su epígrafe abajo (con tildes: por eso PIL y no cv2.putText).
    `numeros`: los de la propuesta (los del guion: "[6]" es la foto 6), si no son 1, 2, 3…"""
    import textwrap

    from PIL import Image, ImageDraw

    chica, grande = _fuente_ttf(17), _fuente_ttf(34)
    tiles = []
    for n, f in zip(numeros or range(1, len(fotos) + 1), fotos):
        img = Image.open(f.ruta).convert("RGB")
        img = img.resize((ancho, max(1, int(img.height * ancho / img.width))))
        img = img.crop((0, 0, ancho, min(img.height, int(ancho * 0.75))))
        lineas = textwrap.wrap(f.epigrafe, 44)[:3]
        tile = Image.new("RGB", (ancho, img.height + 16 + 22 * len(lineas)), (20, 20, 20))
        tile.paste(img, (0, 0))
        d = ImageDraw.Draw(tile)
        d.rectangle((0, 0, 52 if n < 10 else 72, 46), fill=(0, 0, 0))
        d.text((10, 4), str(n), font=grande, fill=(255, 255, 255))
        for i, l in enumerate(lineas):
            d.text((8, img.height + 8 + 22 * i), l, font=chica, fill=(230, 230, 230))
        tiles.append(tile)
    alto_fila = max(t.height for t in tiles)
    filas = (len(tiles) + columnas - 1) // columnas
    hoja = Image.new("RGB", (columnas * (ancho + 6), filas * (alto_fila + 6)), (0, 0, 0))
    for i, t in enumerate(tiles):
        hoja.paste(t, ((i % columnas) * (ancho + 6), (i // columnas) * (alto_fila + 6)))
    salida.parent.mkdir(parents=True, exist_ok=True)
    hoja.save(salida, quality=85)
    return salida


def texto_aprobacion(e: Evento, g: Guion, fotos: list[Foto], fecha: date) -> str:
    """El guion frase por frase con su foto, y los créditos que van a ir en la descripción."""
    lineas = [f"📅 <b>Pasó Hoy · {fecha.day} de {MESES[fecha.month - 1]}</b> — {e.anio}",
              f"<i>{html.escape(e.texto[:200])}</i>",
              f"\n<b>Título:</b> {html.escape(g.titulo)}", "\n<b>Guion</b> (foto → frase):"]
    for texto, foto in zip(g.frases, g.fotos):
        lineas.append(f"[{foto + 1}] {html.escape(texto)}")
    palabras = len(g.texto.split())
    lineas.append(f"\n{palabras} palabras, ~{palabras / 2.5:.0f} s de voz.")
    lineas.append("\n<b>Créditos</b>\n" + html.escape(creditos(fotos)))
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
                render, fps: int = 30) -> Path:
    """Una foto por frase (cada tramo dura lo que su frase), la voz, y los subtítulos + el año que
    ya están en `dir_subs/subs.ass`. Cada tramo se encodea aparte y al final se pegan."""
    from PIL import Image

    W, H = render.ancho, render.alto
    partes = []
    for i, (foto, dur) in enumerate(tramos):
        frames = max(1, int(round(dur * fps)))
        with Image.open(foto) as im:
            ancho, alto = im.size
        fx, fy = foco(foto)
        parte = dir_subs / f"tramo_{i:02d}.mp4"
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
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "concat", "-safe", "0", "-i", "tramos.txt", "-i", str(voz.resolve()),
         "-filter_complex", "[0:v]ass=subs.ass[v]", "-map", "[v]", "-map", "1:a",
         "-c:v", "libx264", "-preset", render.x264_preset, "-crf", str(render.crf),
         "-pix_fmt", "yuv420p", "-maxrate", f"{render.maxrate_kbps}k",
         "-bufsize", f"{2 * render.maxrate_kbps}k", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-shortest", "-movflags", "+faststart", str(salida.resolve())], cwd=dir_subs)
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
             correccion: str = "", saltear: int = 0) -> Propuesta:
    """Elige el evento, junta las fotos, escribe el guion. Si un evento no da 4 fotos que sirvan
    (por reglas o porque Gemini las descartó al verlas), pasa al siguiente del ranking.

    El ranking es de ELEGIDOS y no de 3: el 2026-09-27 los 3 primeros (Google, el ovni de Vorónezh,
    E=mc²) no llegaban a 4 fotos (Google tenía 8 por reglas y Gemini, con razón, descartó 5: un
    edificio de la UE, una protesta, una captura de YouTube...). Con 3 ese día no había video. Los
    que no llegan por reglas no gastan cuota; los guiones sí, por eso el tope de MAX_GUIONES."""
    todos = wiki.eventos("es", dia) + wiki.eventos("en", dia)
    candidatos, motivos = [], {}
    for e in todos:
        m = motivo_evento(e, date.today())
        if m:
            motivos[m] = motivos.get(m, 0) + 1
        else:
            candidatos.append(e)
    avisar(f"{len(todos)} hechos del {dia:%d/%m}; {len(candidatos)} pasan el primer filtro {motivos}")
    if not candidatos:
        raise NarrarError("Ningún hecho de hoy pasa el filtro de temas sensibles.")
    elegidos = elegir(cliente, candidatos)
    avisar("Gemini eligió: " + " | ".join(f"{candidatos[i].anio} {candidatos[i].texto[:50]} [{a}]"
                                          for i, a in elegidos))
    descartes: dict = {}
    guiones = 0
    for i, articulo in elegidos[saltear:]:
        if guiones >= MAX_GUIONES:
            break
        # El artículo del evento va primero: de ahí salen las fotos y el texto del guion.
        e = Evento(candidatos[i].lang, candidatos[i].anio, candidatos[i].texto,
                   [articulo] + [x for x in candidatos[i].paginas if x != articulo])
        fotos, desc = fotos_del_evento(wiki, e)
        for k, v in desc.items():
            descartes[k] = descartes.get(k, 0) + v
        avisar(f"{e.anio} {e.texto[:60]}: {len(fotos)} fotos pasan las reglas {desc}")
        if len(fotos) < MIN_FOTOS:
            continue
        for n, f in enumerate(fotos[:MAX_FOTOS_GUION]):
            f.ruta = str(wiki.bajar(f.url, carpeta / f"foto_{e.anio}_{n:02d}.jpg"))
        usadas = fotos[:MAX_FOTOS_GUION]
        fuente = wiki.texto(e.lang, e.paginas[0])
        if e.lang == "en":            # el guion va en castellano: se valida contra los dos
            es = wiki.en_espanol(e.paginas[0])
            if es:
                fuente += "\n" + wiki.texto("es", es)
        imagenes = [_jpeg_chico(Path(f.ruta)) for f in usadas]
        guiones += 1
        try:
            g = escribir_guion(cliente, e, fuente, usadas, imagenes, correccion)
        except NarrarError as err:
            avisar(f"  el guion no salió: {err}")
            continue
        sirven = len(usadas) - len(g.descartadas)
        if sirven < MIN_FOTOS:
            avisar(f"  Gemini descartó {len(g.descartadas)} al verlas: quedan {sirven}, paso al siguiente")
        for i in g.descartadas:        # para poder juzgar si el descarte visual es razonable
            avisar(f"    descartada {i + 1}: {usadas[i].epigrafe[:90]}")
        if sirven < MIN_FOTOS:
            continue
        return Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in usadas],
                         reserva=[f.a_dict() for f in fotos[MAX_FOTOS_GUION:]], guion=g.a_dict(),
                         fuente=fuente[:20000], descartes=descartes)
    raise NarrarError(f"Ninguno de los {len(elegidos)} hechos elegidos tuvo {MIN_FOTOS} fotos "
                      f"libres que sirvan ({guiones} guiones intentados; descartes: {descartes}).")


def usadas_en_orden(p: Propuesta) -> list[Foto]:
    """Las fotos que aparecen en el video, en el orden en que aparecen (para los créditos)."""
    orden = list(dict.fromkeys(p.guion["fotos"]))
    return [Foto.de_dict(p.fotos[i]) for i in orden]


def numeros_usados(p: Propuesta) -> list[int]:
    """Los números (desde 1) de las fotos del guion, ordenados: los de la hoja y los botones 🔁."""
    return sorted({i + 1 for i in p.guion["fotos"]})


def cambiar_foto(p: Propuesta, n: int, wiki: Wiki, carpeta: Path) -> Foto | None:
    """"🔁 cambiar foto N": la N pasa a descartada y en su lugar va la siguiente que sirva.

    Primero las que Gemini ya vio y no descartó (y no están en el guion); si no hay, las de reserva,
    que pasaron las reglas pero Gemini no vio. Las frases que usaban la N pasan a la nueva.
    None si no queda ninguna: el evento no tiene más fotos libres."""
    g = Guion.de_dict(p.guion)
    i = n - 1
    libres = [k for k in range(len(p.fotos)) if k not in g.fotos and k not in g.descartadas and k != i]
    if libres:
        nueva = libres[0]
    elif p.reserva:
        foto = Foto.de_dict(p.reserva.pop(0))
        foto.ruta = str(wiki.bajar(foto.url, carpeta / f"foto_reserva_{len(p.fotos):02d}.jpg"))
        p.fotos.append(foto.a_dict())
        nueva = len(p.fotos) - 1
    else:
        return None
    g.fotos = [nueva if f == i else f for f in g.fotos]
    g.descartadas = sorted(set(g.descartadas) | {i})
    p.guion = g.a_dict()
    return Foto.de_dict(p.fotos[nueva])


def hacer_video(p: Propuesta, settings, carpeta: Path, avisar=log.info) -> dict:
    """Propuesta aprobada → mp4 + meta listo para `enviar_clip`. Esto es lo que gasta la Pi:
    Piper, Whisper sobre la voz y un encode por foto."""
    from . import narrar, subtitles as sub

    g, e = Guion.de_dict(p.guion), Evento(**p.evento)
    modelo = Path(settings.voz.modelo)
    if not modelo.exists():
        raise NarrarError(f"Falta la voz en {modelo}")
    t0 = time.time()
    wav, duraciones = narrar.sintetizar_frases(g.frases, modelo, carpeta / "voz.wav")
    avisar(f"voz: {sum(duraciones):.1f} s en {time.time() - t0:.0f} s")
    t0 = time.time()
    subs = narrar.subtitular_voz(wav, settings.subtitulos, palabra_por_palabra=True)
    sub.escribir_ass(subs, carpeta / "subs.ass", settings.subtitulos, settings.render,
                     cartel=str(e.anio), cartel_s=2.0, cartel_grande=True)
    avisar(f"subtítulos: {len(subs)} palabras en {time.time() - t0:.0f} s")
    tramos = [(Path(p.fotos[i]["ruta"]), d) for i, d in zip(g.fotos, duraciones)]
    t0 = time.time()
    dia = date.fromisoformat(p.fecha)
    clip_id = f"efemeride_{dia:%m%d}_{e.anio}"
    salida = armar_video(tramos, wav, carpeta, carpeta / f"{clip_id}.mp4", settings.render)
    avisar(f"video: {time.time() - t0:.0f} s")
    cred = creditos(usadas_en_orden(p))
    return {"clip_id": clip_id, "streamer": "Pasó Hoy", "salida": str(salida),
            "subtitulos_quemados": True, "duracion_s": round(sum(duraciones), 1),
            "textos": {"titulo": g.titulo, "descripcion": f"{g.descripcion}\n\n{cred}",
                       "hashtags": g.hashtags, "credito": cred},
            "efemeride": {"fecha": p.fecha, "anio": e.anio, "evento": e.texto,
                          "articulo": e.paginas[0], "lang": e.lang, "guion": g.frases}}


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
