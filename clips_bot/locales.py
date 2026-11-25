"""Pequeña Historia para Facebook: un video APARTE por día con una historia humana real de un lugar
concreto de Latinoamérica (prueba de 2 semanas pedida por Santi el 2026-11-09).

De dónde sale: el Reel de Nacozari (07/11, Jesús García salva al pueblo de un tren con dinamita, en
el Día del Ferrocarrilero de México) hizo 16.841 reproducciones, 602 reacciones y 86 compartidos,
100 % orgánico, contra ~200 reproducciones de los otros. Lo que funcionó: historia humana, lugar
concreto, en el día en que ese lugar la recuerda, y un acto heroico (no una tragedia sola).

1. Candidatos: la página de cada día de Wikipedia en español ("10 de noviembre"): los
   acontecimientos que nombran un lugar de Latinoamérica y, si una celebración del día homenajea a
   una persona (el Día de la Mujer Colombiana → La Pola), sus nacimientos y fallecimientos.
2. Haiku clasifica todos en UNA llamada (¿historia humana?, lugar, país, tipo, ¿tragedia sola?).
3. Sonnet ordena los mejores y dice el artículo del hecho y el del lugar.
4. Guion con Sonnet (las reglas de siempre más el lugar en el título, la primera frase y los
   hashtags) y fotos con Gemini (lo único que mira imágenes), primero las del artículo del lugar.
YouTube no cambia nada: este video va solo a Facebook (`Propuesta.destino = "facebook"`)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import efemerides as ef
from . import ilustrar

log = logging.getLogger(__name__)

TIPOS = ("heroe_de_pueblo", "gente_comun", "anecdota", "momento_emotivo", "fundacion",
         # Santi, 2026-11-15: "historias curiosas y reales de Latinoamérica", no solo héroes y personas
         "lugar_curioso", "invento", "costumbre", "record", "misterio", "dato_sorprendente",
         # Santi, 2026-11-16: ídolos latinoamericanos de antes (época de oro del cine, cantantes, actores, deportistas)
         "idolo",
         # Santi, 2026-11-23 (con los números de Facebook: Colón campeón 14.730 reproducciones, los próceres ~200): el
         # fútbol aparte, y los próceres, conquistadores y batallas aparte, para mandarlos al final
         "futbol", "procer",
         # Santi, 2026-11-25: música aparte (canciones, géneros, discos que hicieron historia), para variar el tema
         "musica", "otro")

# Lugares de Latinoamérica: países, sus gentilicios y las provincias, estados y ciudades que más
# aparecen en las páginas de cada día. Sin esto, Haiku vería ~150 líneas por día.
_LUGARES = (
    "argentin|méxic|mexic|chile|perú|peru|colombia|venezuel|urugua|paragua|bolivia|ecuador|cuba|"
    "brasil|brasileñ|guatemal|hondur|nicaragu|costa rica|panam|salvador|puerto ric|dominican|"
    "latinoam|hispanoam|"
    "buenos aires|córdoba|rosario|mendoza|tucumán|santa fe|corrientes|entre ríos|salta|jujuy|"
    "misiones|chaco|patagoni|neuquén|río negro|chubut|santa cruz|tierra del fuego|la pampa|"
    "san juan|san luis|catamarca|la rioja|santiago del estero|formosa|carhué|mar del plata|"
    "jalisco|sonora|oaxaca|yucatán|veracruz|puebla|chihuahua|coahuila|nuevo león|guanajuato|"
    "michoacán|zacatecas|chiapas|guadalajara|monterrey|tijuana|"
    "lima|cusco|cuzco|arequipa|bogotá|medellín|cali|cartagena|caracas|maracaibo|montevideo|"
    "asunción|la paz|potosí|quito|guayaquil|la habana|santiago de cuba|valparaíso|antofagasta|"
    "san josé|tegucigalpa|managua|ciudad de guatemala|santo domingo|río de janeiro|são paulo")
LUGAR_RE = re.compile(rf"\b({_LUGARES})", re.I)
# Lo que NO va ni a la lista que ve Haiku. Las muertes, los fusilamientos o un accidente sí pasan:
# con el criterio de Nacozari decide el modelo (acto heroico sí; tragedia sola, no).
_DURO = re.compile(r"\b(atentad\w*|terroris\w*|masacr\w*|genocid\w*|tiroteo\w*|bomb\w*|suicid\w*|"
                   r"rehén\w*|secuestr\w*|violaci\w*|feminicid\w*|asesina\w*|decapit\w*|tortur\w*)\b", re.I)


@dataclass
class Candidato:
    seccion: str                     # acontecimientos | nacimientos | fallecimientos
    anio: int
    texto: str
    paginas: list[str]               # artículos enlazados, en orden
    clasif: dict = field(default_factory=dict)


def _limpiar(t: str) -> str:
    """Wikitexto de una línea → texto: [[A|B]] → B, sin plantillas, refs, etiquetas ni negritas."""
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\{\{(?:esd|nbsp)\}\}", " ", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:Archivo|File|Imagen):[^\]]*\]\]", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", t)
    t = re.sub(r"'{2,}", "", t).replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def _enlaces(t: str) -> list[str]:
    out = []
    for m in re.finditer(r"\[\[([^|\]#]+)", t):
        x = m.group(1).strip()
        if x and not re.match(r"(Archivo|File|Imagen|Categoría):", x) and not x.isdigit():
            out.append(x)
    return list(dict.fromkeys(out))


def _secciones(wikitexto: str) -> dict[str, str]:
    out, actual = {}, None
    for linea in wikitexto.splitlines():
        m = re.match(r"^==\s*([^=].*?)\s*==\s*$", linea)
        if m:
            actual = ef._norm(m.group(1))
            out[actual] = ""
        elif actual:
            out[actual] += linea + "\n"
    return out


def titulo_dia(dia: date) -> str:
    return f"{dia.day} de {ef.MESES[dia.month - 1]}"


def _wikitexto_dia(wiki: ef.Wiki, dia: date) -> str:
    d = wiki._get(ef.API.format(lang="es"), {"action": "parse", "page": titulo_dia(dia), "prop": "wikitext",
                                              "format": "json", "formatversion": 2, "redirects": 1})
    texto = (d.get("parse") or {}).get("wikitext") or ""
    return texto.get("*", "") if isinstance(texto, dict) else texto


def celebraciones(secs: dict[str, str]) -> list[dict]:
    """Las líneas de las secciones de celebraciones del día: {pais (None = de afuera o sin país),
    texto, enlaces, linea}."""
    out = []
    for nombre, cuerpo in secs.items():
        if not nombre.startswith(("celebraciones", "fiestas", "conmemoraciones")):
            continue
        pais = None
        for linea in cuerpo.splitlines():
            t = linea.strip()
            m = re.match(r"^\*\s*\{\{([A-Z]{3})\}\}", t)
            if m:
                pais = PAISES_PLANTILLA.get(m.group(1))    # None = país de afuera
                continue
            # El país vale para sus sub-ítems ("** …"): una subsección ("=== Santoral católico ===",
            # 2026-11-11: los santos salían como de Perú) o un ítem de primer nivel lo cortan.
            if t.startswith("=") or re.match(r"^\*(?!\*)", t):
                pais = None
            if not t.startswith("*") or len(_limpiar(linea.lstrip("*: "))) <= 3:
                continue
            if _limpiar(linea.lstrip("*: ")).rstrip().endswith(":"):
                continue        # un título ("Por provincias:", "Misiones:"), no una fecha
            out.append({"pais": pais, "texto": _limpiar(linea.lstrip("*: ")), "enlaces": _enlaces(linea)})
    return out


def leer_dia(wiki: ef.Wiki, dia: date) -> tuple[list[Candidato], list[str], set[str]]:
    """(candidatos, conmemoraciones del día en texto, personas homenajeadas ese día). Los
    candidatos todavía sin filtrar."""
    secs = _secciones(_wikitexto_dia(wiki, dia))
    conmemoraciones, homenajeados = [], set()
    out: list[Candidato] = []
    for c in celebraciones(secs):
        pais, limpio = c["pais"], c["texto"]
        conmemoraciones.append(((pais + ": ") if pais else "") + limpio[:220])
        homenajeados.update(c["enlaces"])
        # Fuente 1 (2026-11-10): la conmemoración de un lugar que trae el año del hecho
        # ("Independencia de Ambato… ocurrida el 12 de noviembre de 1820") es un candidato
        # aunque Acontecimientos no tenga la línea.
        anio = anio_celebracion(limpio, dia)
        if anio and (pais or LUGAR_RE.search(limpio)) and c["enlaces"]:
            out.append(Candidato("celebracion", anio, ((pais + ": ") if pais else "") + limpio[:400],
                                 c["enlaces"]))
    for nombre, cuerpo in secs.items():
        seccion = next((s for s in ("acontecimientos", "nacimientos", "fallecimientos")
                        if nombre.startswith(s)), None)
        if not seccion:
            continue
        for linea in cuerpo.splitlines():
            m = re.match(r"^\*+\s*\[?\[?(\d{3,4})\]?\]?\s*(?:[:–—-]|\(|,)\s*(.+)$", linea.strip())
            if not m:
                continue
            out.append(Candidato(seccion, int(m.group(1)), _limpiar(m.group(2)), _enlaces(m.group(2))))
    return out, conmemoraciones, homenajeados


# ---- fuentes extra (pedido de Santi, 2026-11-10: que ningún día quede sin una historia fuerte) ---
# El conteo del mes dio 2 días sin ninguna historia buena y 10 sin ninguna fuerte con solo la página
# del día. Estas fuentes se suman a esa; si alguna falla (429, red), se avisa y sigue sin ella.

PAISES_PLANTILLA = {
    "ARG": "Argentina", "MEX": "México", "CHI": "Chile", "CHL": "Chile", "PER": "Perú",
    "COL": "Colombia", "VEN": "Venezuela", "URU": "Uruguay", "PAR": "Paraguay", "BOL": "Bolivia",
    "ECU": "Ecuador", "CUB": "Cuba", "BRA": "Brasil", "GUA": "Guatemala", "HON": "Honduras",
    "NIC": "Nicaragua", "CRC": "Costa Rica", "CRI": "Costa Rica", "PAN": "Panamá",
    "SLV": "El Salvador", "ESA": "El Salvador", "PUR": "Puerto Rico", "PRI": "Puerto Rico",
    "DOM": "República Dominicana"}

# Medido el 2026-11-10: de los anexos "Efemérides de/en <país>" de es.wikipedia, el único de un país
# de Latinoamérica es el de Venezuela (más el del estado Nueva Esparta). 2026-11-15 (Santi: "sumá más
# fuentes"): también los de días festivos, feriados y conmemoraciones por país y las fiestas de
# provincias (medido con la búsqueda por prefijo de es.wikipedia: estos existen).
ANEXOS_EFEMERIDES = ("Anexo:Efemérides en Venezuela", "Anexo:Efemérides del Estado Nueva Esparta")
ANEXOS_PAIS = {
    "Anexo:Conmemoraciones en México": "México", "Anexo:Días festivos en México": "México",
    "Anexo:Días festivos en Colombia": "Colombia", "Anexo:Días festivos en Argentina": "Argentina",
    "Feriados de Argentina": "Argentina", "Feriados en Chile": "Chile", "Anexo:Días festivos en Perú": "Perú",
    "Anexo:Días festivos en Paraguay": "Paraguay", "Anexo:Días festivos en Bolivia": "Bolivia",
    "Anexo:Días festivos en Guatemala": "Guatemala", "Anexo:Días festivos en Honduras": "Honduras",
    "Anexo:Días festivos en Panamá": "Panamá", "Anexo:Feriados eventuales en Uruguay": "Uruguay",
    "Anexo:Fiestas Patronales en Puerto Rico": "Puerto Rico",
    "Anexo:Fiestas y celebraciones en Buenos Aires": "Argentina",
    "Anexo:Fiestas y celebraciones en la provincia de Córdoba (Argentina)": "Argentina",
    "Anexo:Fiestas y celebraciones en Santa Fe": "Argentina", "Anexo:Fiestas y celebraciones en Mendoza": "Argentina",
    "Anexo:Fiestas y celebraciones en la provincia de Entre Ríos": "Argentina",
    "Anexo:Fiestas y celebraciones en la provincia de San Juan": "Argentina",
    "Anexo:Fiestas y celebraciones en San Luis": "Argentina", "Anexo:Fiestas de La Guajira": "Colombia",
}

# Lo que dice qué ES el artículo (las primeras líneas): un lugar sí; un club, una empresa, no.
_ES_LUGAR = re.compile(r"\b(ciudad|localidad|pueblo|municipio|barrio|villa|comuna|distrito|parroquia|"
                       r"cant[oó]n|corregimiento|poblaci[oó]n|aldea|caser[ií]o|partido|departamento|"
                       r"provincia|estado|capital|puerto|colonia|asentamiento)\b", re.I)
_NO_LUGAR = re.compile(r"\b(club|f[uú]tbol|equipo|universidad|colegio|instituto|escuela|empresa|"
                       r"compa[nñ][ií]a|banco|aerol[ií]nea|radio|televisi[oó]n|canal|revista|diario|"
                       r"peri[oó]dico|iglesia|hermandad|cofrad[ií]a|logia|congregaci[oó]n|sindicato|"
                       r"orquesta|banda|federaci[oó]n|liga|asociaci[oó]n|sociedad|partido pol[ií]tico|"
                       r"organizaci[oó]n|museo|hospital|marca|cooperativa)\b", re.I)


def anio_celebracion(texto: str, dia: date) -> int | None:
    """El año del HECHO que recuerda una conmemoración ("ocurrida el 12 de noviembre de 1820",
    "el nacimiento de Sor Juana…, ocurrido en 1651"). El año en que se instituyó el día ("por decreto
    en 1979") no sirve: sin uno de estos dos, None."""
    mes = ef.MESES[dia.month - 1]
    m = re.search(rf"\b{dia.day}\s+de\s+{mes}\s+del?\s+(\d{{3,4}})\b", texto, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(?:ocurrid[ao]s?|sucedid[ao]s?|fundad[ao]s?|nacid[ao]|naci[oó]|muri[oó]|fallecid[ao]|"
                  r"proclamad[ao]|librad[ao])\b[^.]{0,40}?\b(?:en|el a[nñ]o)\s+(\d{3,4})\b", texto, re.I)
    return int(m.group(1)) if m else None


def _fecha_re(dia: date) -> re.Pattern:
    return re.compile(rf"\b(?:el\s+)?{dia.day}\s+de\s+{ef.MESES[dia.month - 1]}\s+del?\s+(\d{{3,4}})\b", re.I)


def leer_anexos(wiki: ef.Wiki, dia: date) -> tuple[list[str], set[str]]:
    """Fuente 2: las líneas de hoy de los anexos de efemérides por país ("14 de noviembre: natalicio
    del General José Antonio Anzoátegui"): van a las conmemoraciones y sus personas cuentan como
    homenajeadas, así su nacimiento o muerte de la página del día pasa el filtro."""
    conm, homen = [], set()
    patron = re.compile(rf"^\*+\s*{dia.day}\s+de\s+{ef.MESES[dia.month - 1]}\s*[:–—-]\s*(.+)$", re.I)
    for titulo in ANEXOS_EFEMERIDES:
        d = wiki._get(ef.API.format(lang="es"), {"action": "parse", "page": titulo, "prop": "wikitext",
                                                  "format": "json", "formatversion": 2, "redirects": 1})
        texto = (d.get("parse") or {}).get("wikitext") or ""
        if isinstance(texto, dict):
            texto = texto.get("*", "")
        pais = re.sub(r"^Anexo:Efemérides (?:de|del|en)\s+", "", titulo)
        for linea in texto.splitlines():
            m = patron.match(linea.strip())
            if m:
                conm.append(f"{pais}: {_limpiar(m.group(1))[:200]}")
                homen.update(_enlaces(m.group(1)))
    return conm, homen


def leer_anexos_pais(wiki: ef.Wiki, dia: date) -> tuple[list[str], set[str]]:
    """Fuente 2b (2026-11-15): las filas de hoy de los anexos de días festivos, feriados, conmemoraciones
    y fiestas por país (tablas o listas: cualquier fila que tenga "20 de noviembre")."""
    conm, homen = [], set()
    fecha = re.compile(rf"(?<!\d){dia.day}\s+de\s+{ef.MESES[dia.month - 1]}\b", re.I)
    for titulo, pais in ANEXOS_PAIS.items():
        d = wiki._get(ef.API.format(lang="es"), {"action": "parse", "page": titulo, "prop": "wikitext",
                                                  "format": "json", "formatversion": 2, "redirects": 1})
        texto = (d.get("parse") or {}).get("wikitext") or ""
        if isinstance(texto, dict):
            texto = texto.get("*", "")
        for fila in re.split(r"\n\|-|\n(?=\*)", texto):
            if not fecha.search(fila):
                continue
            limpio = _limpiar(re.sub(r"\s*\|\|?\s*", " · ", fila)).strip(" ·")
            if 8 <= len(limpio) <= 400 and f"{pais}: {limpio[:220]}" not in conm:
                conm.append(f"{pais}: {limpio[:220]}")
                homen.update(_enlaces(fila))
    return conm, homen


def _buscar(wiki: ef.Wiki, frase: str, limite: int = 50) -> list[tuple[str, str]]:
    d = wiki._get(ef.API.format(lang="es"), {"action": "query", "list": "search", "srsearch": frase,
                                              "srlimit": limite, "srprop": "snippet", "format": "json"})
    return [(x["title"], ef.sin_html(x.get("snippet") or "")) for x in (d.get("query") or {}).get("search") or []]


def _intros(wiki: ef.Wiki, titulos: list[str]) -> dict[str, str]:
    """Las primeras líneas de cada artículo (de a 20 por pedido): dicen qué es y de qué país."""
    out = {}
    for i in range(0, len(titulos), 20):
        lote = titulos[i:i + 20]
        d = wiki._get(ef.API.format(lang="es"), {"action": "query", "prop": "extracts", "exintro": 1,
                                                  "explaintext": 1, "exlimit": 20, "exchars": 400,
                                                  "titles": "|".join(lote), "format": "json"})
        for p in ((d.get("query") or {}).get("pages") or {}).values():
            out[p.get("title", "")] = str(p.get("extract") or "")
    return out


def es_lugar_latino(intro: str) -> bool:
    """¿El artículo es un pueblo o una ciudad de Latinoamérica? Mira la primera oración."""
    primera = re.split(r"(?<=[.;])\s", intro.strip(), maxsplit=1)[0][:300]
    return bool(_ES_LUGAR.search(primera)) and not _NO_LUGAR.search(primera) and bool(LUGAR_RE.search(intro))


FRASES_FUNDACION = ("fundada el {d}", "fundado el {d}", "se fundó el {d}", "fundó el {d}")


def buscar_fundaciones(wiki: ef.Wiki, dia: date) -> list[Candidato]:
    """Fuente 3: pueblos y ciudades de Latinoamérica fundados un día como hoy (el buscador de
    es.wikipedia con la frase "fundada el 21 de noviembre", y solo los artículos que son un lugar de
    Latinoamérica). Un club o una universidad fundados ese día no entran."""
    fecha = f"{dia.day} de {ef.MESES[dia.month - 1]}"
    fre = _fecha_re(dia)
    hits: dict[str, str] = {}
    for f in FRASES_FUNDACION:
        for titulo, snip in _buscar(wiki, '"' + f.format(d=fecha) + '"'):
            if fre.search(snip) and titulo not in hits:
                hits[titulo] = snip
    intros = _intros(wiki, list(hits))
    out = []
    for titulo, snip in hits.items():
        intro = intros.get(titulo, "")
        if not es_lugar_latino(intro):
            continue
        out.append(Candidato("fundacion", int(fre.search(snip).group(1)),
                             f"Fundación de {titulo}: {snip[:250]} ({intro[:200]})", [titulo]))
    return out


FRASES_HISTORIA = ('"el {d} de" vecinos', '"el {d} de" pobladores', '"el {d} de" habitantes',
                   '"el {d} de" pueblo', '"el {d} de" inundación', '"el {d} de" incendio')
TOPE_CIUDADES = 25      # artículos de ciudades que se leen por día (eran 12)


def historia_de_ciudades(wiki: ef.Wiki, dia: date, lugares: list[str], tope: int = TOPE_CIUDADES) -> list[Candidato]:
    """Fuente 4: la historia de cada ciudad. En el artículo de los lugares que ya son candidatos de
    hoy (fundaciones, conmemoraciones) y de los que el buscador encuentra con "el 21 de noviembre de"
    y "vecinos" o "pobladores", las oraciones que cuentan algo que pasó un día como hoy."""
    fecha = f"{dia.day} de {ef.MESES[dia.month - 1]}"
    fre = _fecha_re(dia)
    candidatos = list(dict.fromkeys(lugares))
    buscados = []
    for f in FRASES_HISTORIA:
        buscados += [t for t, s in _buscar(wiki, f.format(d=fecha), 30) if fre.search(s)]
    intros = _intros(wiki, [t for t in dict.fromkeys(buscados) if t not in candidatos])
    candidatos += [t for t, i in intros.items() if es_lugar_latino(i)]
    out = []
    for titulo in candidatos[:tope]:
        texto = wiki.texto("es", titulo)
        for oracion in re.split(r"(?<=[.!?])\s+|\n+", texto):
            m = fre.search(oracion)
            if m and 40 <= len(oracion) <= 600:
                out.append(Candidato("historia_ciudad", int(m.group(1)),
                                     f"Historia de {titulo}: {oracion.strip()[:400]}", [titulo]))
    return out


# Fuente 5 (2026-11-15): personajes populares y hazañas. El buscador de es.wikipedia con la fecha y una
# palabra de historia humana; solo artículos de Latinoamérica, y de cada uno la oración con la fecha.
FRASES_PERSONAJES = ('"el {d} de" héroe', '"el {d} de" heroína', '"el {d} de" hazaña', '"el {d} de" salvó',
                     '"el {d} de" rescate', '"el {d} de" leyenda', '"el {d} de" popular', '"el {d} de" ídolo',
                     # historias curiosas (2026-11-15): lugares, inventos, costumbres, récords, misterios
                     '"el {d} de" récord', '"el {d} de" misterio', '"el {d} de" inventó', '"el {d} de" invento',
                     '"el {d} de" curioso', '"el {d} de" tradición', '"el {d} de" primera vez',
                     '"el {d} de" insólito', '"el {d} de" enigma', '"el {d} de" patentó',
                     # ídolos de antes (2026-11-16)
                     '"el {d} de" actor', '"el {d} de" actriz', '"el {d} de" cantante', '"el {d} de" "época de oro"',
                     '"el {d} de" futbolista', '"el {d} de" boxeador')
TOPE_PERSONAJES = 40


def buscar_personajes(wiki: ef.Wiki, dia: date, tope: int = TOPE_PERSONAJES) -> list[Candidato]:
    fecha = f"{dia.day} de {ef.MESES[dia.month - 1]}"
    fre = _fecha_re(dia)
    hits: list[str] = []
    for f in FRASES_PERSONAJES:
        hits += [t for t, sn in _buscar(wiki, f.format(d=fecha), 30) if fre.search(sn) and t not in hits]
    intros = _intros(wiki, hits)
    latinos = [t for t in hits if LUGAR_RE.search(intros.get(t, "")) and not _NO_LUGAR.search(
        re.split(r"(?<=[.;])\s", intros.get(t, "").strip(), maxsplit=1)[0][:300])]
    out = []
    for titulo in latinos[:tope]:
        texto = wiki.texto("es", titulo)
        for oracion in re.split(r"(?<=[.!?])\s+|\n+", texto):
            m = fre.search(oracion)
            if m and 40 <= len(oracion) <= 600:
                out.append(Candidato("personaje", int(m.group(1)),
                                     f"{titulo}: {oracion.strip()[:400]} ({intros.get(titulo, '')[:150]})", [titulo]))
                break
    return out


def leer_todo(wiki: ef.Wiki, dia: date, avisar=log.info) -> tuple[list[Candidato], list[str], set[str]]:
    """La página del día más las fuentes extra. Sin repetir el mismo hecho (mismo año y mismo primer
    artículo)."""
    todos, conm, homen = leer_dia(wiki, dia)
    cuenta = {}
    try:
        c2, h2 = leer_anexos(wiki, dia)
        conm += c2
        homen |= h2
        cuenta["anexos"] = len(c2)
    except Exception as err:  # noqa: BLE001 — una fuente extra caída no frena la propuesta
        avisar(f"anexos de efemérides: no salió ({err})")
    try:
        c3, h3 = leer_anexos_pais(wiki, dia)
        conm += c3
        homen |= h3
        cuenta["anexos por país"] = len(c3)
    except Exception as err:  # noqa: BLE001
        avisar(f"anexos por país: no salió ({err})")
    try:
        fund = buscar_fundaciones(wiki, dia)
        cuenta["fundaciones"] = len(fund)
    except Exception as err:  # noqa: BLE001
        fund = []
        avisar(f"fundaciones: no salió ({err})")
    lugares = [c.paginas[0] for c in fund] + [c.paginas[0] for c in todos if c.seccion == "celebracion"]
    try:
        hist = historia_de_ciudades(wiki, dia, lugares)
        cuenta["historia de ciudades"] = len(hist)
    except Exception as err:  # noqa: BLE001
        hist = []
        avisar(f"historia de ciudades: no salió ({err})")
    try:
        pers = buscar_personajes(wiki, dia)
        cuenta["personajes"] = len(pers)
    except Exception as err:  # noqa: BLE001
        pers = []
        avisar(f"personajes: no salió ({err})")
    # Nacimientos y muertes de gente de Latinoamérica (personajes populares de cada país): antes solo
    # entraban si una conmemoración del día los homenajeaba.
    for c in todos:
        if c.seccion in ("nacimientos", "fallecimientos") and LUGAR_RE.search(c.texto):
            c.seccion = "personaje_" + c.seccion
    cuenta["conmemoraciones con año"] = sum(1 for c in todos if c.seccion == "celebracion")
    vistos = {(c.anio, ef._norm(c.paginas[0])) for c in todos if c.paginas}
    for c in fund + hist + pers:
        clave = (c.anio, ef._norm(c.paginas[0]))
        if clave not in vistos:
            vistos.add(clave)
            todos.append(c)
    avisar(f"fuentes extra del {dia:%d/%m}: {cuenta}")
    return todos, conm, homen


_TRATAMIENTO = re.compile(r"^(sor|san|santa|santo|beato|beata|fray|don|doña)\s+")


def _persona(titulo: str) -> str:
    """El nombre para comparar: sin tildes, sin "Sor/San/…" y sin la aclaración entre paréntesis."""
    return _TRATAMIENTO.sub("", re.sub(r"\s*\(.*?\)", "", ef._norm(titulo))).strip()


def homenajeado(titulo: str, homenajeados: set[str]) -> bool:
    """¿La conmemoración del día homenajea a esta persona? Los enlaces no siempre coinciden: el 12/11
    el nacimiento enlaza "Juana Inés de la Cruz" y el Día Nacional del Libro, la redirección
    "Sor Juana Inés de la Cruz" (por eso no entraba, medido el 2026-11-09)."""
    p = _persona(titulo)
    return bool(p) and any(_persona(h) == p for h in homenajeados)


def motivo_local(c: Candidato, hoy: date, homenajeados: set[str]) -> str | None:
    """Por qué el candidato no llega ni a Haiku."""
    if not c.paginas:
        return "sin artículo"
    if c.anio > hoy.year:
        return "fecha rara"
    if c.seccion in ("nacimientos", "fallecimientos") and not homenajeado(c.paginas[0], homenajeados):
        return "nacimiento o muerte sin conmemoración"
    if not LUGAR_RE.search(c.texto):
        return "sin lugar de Latinoamérica"
    if _DURO.search(c.texto):
        return "tema sensible"
    if c.anio >= 1945 and ef._GUERRA.search(c.texto):
        return "guerra reciente"
    if ef._TRAMA.search(c.texto):
        return "trama de una ficción"
    return None


def filtrar(cands: list[Candidato], hoy: date, homenajeados: set[str]) -> tuple[list[Candidato], dict]:
    ok, motivos = [], {}
    for c in cands:
        m = motivo_local(c, hoy, homenajeados)
        if m:
            motivos[m] = motivos.get(m, 0) + 1
        else:
            ok.append(c)
    return ok, motivos


# ---- 2. Haiku clasifica -------------------------------------------------------------------------

SISTEMA_CLASIFICAR = """Clasificás hechos para un canal de videos cortos de HISTORIAS CURIOSAS Y REALES de
Latinoamérica ("Pequeña Historia"): héroes y gente común, pero también lugares insólitos, inventos de la
región, costumbres y tradiciones, récords, misterios y datos sorprendentes de ciudades y países. Para CADA
hecho de la lista decí:
- `humana`: true si se puede contar como una HISTORIA CURIOSA REAL que engancha: gente concreta que hace o
  vive algo notable, o un lugar, un invento, una costumbre, un récord, un misterio o un dato sorprendente con
  algo que contar (cómo nació, qué tiene de raro, qué pasó). false si es un trámite institucional, una ley, un
  cambio de gobierno, una elección, un tratado, la fundación de una empresa, un canal de TV, un club o una
  universidad sin nada curioso detrás, un resultado deportivo suelto sin historia o política partidaria. El
  FÚTBOL con historia SÍ es humana: un club que sale campeón después de años, un partido histórico, un ídolo, una
  hinchada, un arquero o un gol que se recuerda.
- `lugar`: el pueblo o la ciudad CONCRETA donde pasó; si es un dato de un país entero, el país. Vacío si no
  hay ninguno.
- `region`: la provincia, estado o departamento, si se sabe. `pais`: el país de hoy.
- `tipo`: heroe_de_pueblo, gente_comun, anecdota, momento_emotivo, fundacion, lugar_curioso, invento,
  costumbre, record, misterio, dato_sorprendente, idolo (un ídolo latinoamericano de antes: la época de oro del cine
  mexicano y argentino, cantantes, actores, deportistas; contado como historia real de su vida, con un giro y
  emoción, no como ficha biográfica), futbol (clubes, ídolos del fútbol, partidos históricos, títulos, hinchadas,
  mundiales), musica (una canción, un género, un disco o un músico que hicieron historia: cómo nació el tango, la
  cumbia o un bolero famoso), procer (próceres, conquistadores, virreyes, generales, batallas, independencia, revueltas, gobernantes)
  u otro.
- `tragedia_sola`: true si lo central es una muerte, un desastre, un crimen o una represión SIN un acto
  heroico o algo luminoso que contar. (Un maquinista que muere salvando a su pueblo: false. Un terremoto
  con miles de muertos: true. Una heroína fusilada por defender la independencia: false.)
- `conmemora`: si alguna de las conmemoraciones de hoy recuerda este hecho o a su protagonista, cuál
  (corta); si no, vacío.
- `interes` de 1 a 10: cuánto engancharía a gente de ese lugar y de Latinoamérica ("¡eso pasó en mi
  pueblo!", "¡no sabía que eso se inventó acá!"), como el maquinista de Nacozari.
Respondé solo con el JSON pedido, una entrada por hecho, con su número."""

SCHEMA_CLASIFICAR = {
    "type": "OBJECT",
    "properties": {"hechos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"n": {"type": "INTEGER"}, "humana": {"type": "BOOLEAN"},
                       "lugar": {"type": "STRING"}, "region": {"type": "STRING"},
                       "pais": {"type": "STRING"}, "tipo": {"type": "STRING", "enum": list(TIPOS)},
                       "tragedia_sola": {"type": "BOOLEAN"}, "conmemora": {"type": "STRING"},
                       "interes": {"type": "INTEGER"}},
        "required": ["n", "humana", "lugar", "region", "pais", "tipo", "tragedia_sola",
                     "conmemora", "interes"]}}},
    "required": ["hechos"],
}


def clasificar(haiku, cands: list[Candidato], conmemoraciones: list[str]) -> list[Candidato]:
    """Una llamada a Haiku para todos. Deja `clasif` en cada candidato (None = ya clasificados)."""
    if not cands or haiku is None:
        return cands
    lineas = [f"{i + 1}. ({c.anio}, {c.seccion}) {c.texto[:300]}" for i, c in enumerate(cands)]
    prompt = ("CONMEMORACIONES DE HOY:\n" + ("\n".join(f"- {x}" for x in conmemoraciones) or "(ninguna)")
              + "\n\nHECHOS:\n" + "\n".join(lineas))
    d = json.loads(haiku.json(SISTEMA_CLASIFICAR, prompt, SCHEMA_CLASIFICAR, temperatura=0.1))
    for h in d.get("hechos") or []:
        n = h.get("n")
        if isinstance(n, int) and 1 <= n <= len(cands):
            cands[n - 1].clasif = h
    return cands


# Los países con más público (Santi, 2026-11-11), en este orden.
PAISES_PRIORIDAD = ("México", "Colombia", "Argentina", "Perú", "Chile", "Venezuela")


def prioridad_pais(pais: str | None) -> int:
    """0 = México … 5 = Venezuela; el resto, 6."""
    p = _sin_tildes(str(pais or "")).strip()
    for k, x in enumerate(PAISES_PRIORIDAD):
        if _sin_tildes(x) in p:
            return k
    return len(PAISES_PRIORIDAD)


def en_calendario(c: Candidato) -> bool:
    """¿Es una fecha del calendario de hoy? Una conmemoración (con el año del hecho), un aniversario de
    fundación, o un hecho que Haiku dice que se conmemora hoy."""
    return c.seccion in ("celebracion", "fundacion") or bool(str(c.clasif.get("conmemora") or "").strip())


def otro_pais_primero(lista: list[Candidato], evitar: set | None) -> list[Candidato]:
    """Los de un país que ya salió hoy, al final (en el mismo orden): "si se puede"."""
    malos = {_sin_tildes(str(p)).strip() for p in (evitar or set()) if str(p or "").strip()}
    return sorted(lista, key=lambda c: _sin_tildes(str(c.clasif.get("pais") or "")).strip() in malos)


def peso_tema(c: Candidato, pesos: dict | None = None) -> float:
    """Santi, 2026-11-23: fútbol, ídolos de antes y curiosidades primero; próceres y fundaciones al final (temas.py,
    con lo que rinde cada grupo en Facebook)."""
    from . import temas

    return float((pesos or temas.BASE_LATAM).get(temas.grupo_latam(c.clasif.get("tipo"), c.texto), 0.0))


def es_procer(c: Candidato) -> bool:
    from . import temas

    return temas.grupo_latam(c.clasif.get("tipo"), c.texto) == "procer"


def buenos(cands: list[Candidato], pesos: dict | None = None) -> list[Candidato]:
    """Historias con un lugar concreto, sin tragedias solas, de mejor a peor. Desde el 2026-11-23 (Santi) manda el
    tema: fútbol, ídolos y curiosidades primero, próceres y fundaciones al final (aunque sean del calendario). Dentro de
    cada tema, el calendario (Santi, 2026-11-11), los países con más público y el interés."""
    ok = [c for c in cands if (c.clasif.get("humana") or en_calendario(c))
          and str(c.clasif.get("lugar") or "").strip() and not c.clasif.get("tragedia_sola")]
    return sorted(ok, key=lambda c: (-peso_tema(c, pesos), not en_calendario(c), prioridad_pais(c.clasif.get("pais")),
                                     -int(c.clasif.get("interes") or 0)))


# ---- 3. Sonnet elige -------------------------------------------------------------------------

SISTEMA_ELEGIR = """Elegís la historia del día para "Pequeña Historia": un video corto con una historia
CURIOSA y REAL de Latinoamérica (Santi, 2026-11-15): héroes y gente común, y también lugares insólitos,
inventos, costumbres, récords, misterios y datos sorprendentes de ciudades y países, siempre desde un hecho
real con fecha. El modelo a seguir es el
maquinista Jesús García, que en 1907 alejó un tren con dinamita encendida y salvó a Nacozari: la
gente de ese lugar se siente identificada, la comparte y cuenta sus recuerdos.

Ordená del mejor al peor (hasta {cuantos}) los que más se parecen a eso, y puntuá TODOS los que pongas:
- gente concreta que hizo algo notable (héroes de pueblo, gente común, anécdotas, momentos
  emotivos), en un pueblo o ciudad que se pueda nombrar; o un lugar, un invento, una costumbre, un récord,
  un misterio o un dato de un país que sorprenda y tenga una historia detrás;
- ídolos latinoamericanos de antes (época de oro del cine mexicano y argentino, cantantes, actores, deportistas:
  Jorge Negrete, Carlos Gardel, Pedro Infante, Tita Merello…), contados como una historia real de su vida, con
  persona, giro y emoción (el momento que cambió su carrera, lo que nadie sabía de él con un dato concreto);
- LO QUE MÁS RINDE EN FACEBOOK (Santi, 2026-11-23, medido en los Reels): el FÚTBOL (clubes, ídolos, partidos
  históricos, títulos después de años: Colón campeón tras 116 años hizo 14.730 reproducciones, 50 veces más que el
  resto), los ídolos de antes y las curiosidades; después, historias humanas de gente común. Los PRÓCERES,
  conquistadores, batallas, revueltas y fundaciones de ciudades rinden lo peor (~200): ponelos al final aunque sean
  del calendario;
- los marcados ★ CALENDARIO se recuerdan HOY (aniversario, fundación, día nacional, fiesta del
  lugar): van primero dentro de cada grupo (salvo próceres y fundaciones), y entre ellos primero México, Colombia,
  Argentina, Perú, Chile y Venezuela (es cuando la gente lo comparte);
- que se pueda contar en 40 segundos y se entienda sin saber historia;
- nada de tragedias solas (muertes, desastres, crímenes sin un acto heroico), ni política
  partidaria, ni guerras recientes;
- nada que pase DENTRO de una ficción (lo que le pasa a un personaje de una serie, telenovela,
  juego o película): la cultura pop solo si se cuenta desde la vida real (estreno, quién lo creó,
  cómo se hizo, impacto, récords).
PUNTUÁ cada uno del 1 al 10 en cuatro cosas (Santi, 2026-11-13: la gente se va después del
segundo 3, hacen falta historias que atrapen):
- `persona`: ¿hay un protagonista concreto, con nombre, en el centro? (10 = alguien con nombre que hace
  algo, o un lugar o un invento con nombre propio que "hace" algo insólito; 1 = una institución o una ley);
- `peligro`: ¿hay peligro, conflicto, misterio o algo en juego? (10 = vidas en riesgo o un misterio sin
  resolver; 1 = nada en juego);
- `sorpresa` (SOLO para las historias CURIOSAS: lugar insólito, invento, costumbre, récord, misterio o
  dato sorprendente; para las de personas poné 0): ¿el dato o el giro hace decir "no puede ser"? (10 =
  increíble pero cierto; 1 = un dato común). En las curiosas, `sorpresa` reemplaza a `peligro` (poné
  `peligro` igual, pero no cuenta);
- `giro`: ¿hay un giro o un final sorprendente?;
- `emocion`: ¿genera emoción (orgullo, asombro, tristeza)?;
- `rareza` (para TODOS, Santi 2026-11-25): ¿tiene algo FUERA DE LO COMÚN, un dato increíble o un giro que haga decir
  "no puede ser"? 10 = Nacozari, o Colón campeón tras 116 años; 2 = una estación de tren, un edificio o una
  emisora que se inaugura, una ciudad que se funda o una batalla de la independencia contada como siempre.
  Las estaciones, edificios, fundaciones, inauguraciones y próceres NO están prohibidos, pero su puntaje final es
  el MENOR entre el promedio y la `rareza`: solo entran si de verdad tienen algo increíble.
SÉ EXIGENTE CON LOS NÚMEROS: una estación de tren o un edificio no tienen "peligro" (1-2) ni "persona" (salvo que
haya alguien con nombre haciendo algo notable); una inundación sin un protagonista con nombre no pasa de 4 en
persona. No infles: 8 o más es para historias que la gente compartiría.
VARIEDAD (Santi, 2026-11-25): buscamos fútbol, ídolos de antes, curiosidades, historias humanas sorprendentes,
música e inventos latinos; preferí un buen tema antes que la historia que tenga más fotos.
EJEMPLO DE 10 EN LAS CUATRO: Nacozari (1907): el maquinista Jesús García ve que el tren lleva
dinamita prendida, lo saca del pueblo a toda máquina y muere en la explosión salvando a todos; hoy
el pueblo se llama Nacozari de García. Sé exigente: una fundación sin protagonista o un decreto
no pasan de 4 en persona y en peligro.
Para cada uno: `articulo` = el título EXACTO, de la lista de artículos del hecho, del artículo que
cuenta ESE hecho (no el del país ni el de una fecha); `articulo_lugar` = el título, de la misma
lista, del artículo del pueblo o ciudad (vacío si no está). Respondé solo con el JSON pedido."""

SCHEMA_ELEGIR = {
    "type": "OBJECT",
    "properties": {"elegidos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"n": {"type": "INTEGER"}, "articulo": {"type": "STRING"},
                       "articulo_lugar": {"type": "STRING"}, "motivo": {"type": "STRING"},
                       "persona": {"type": "INTEGER"}, "peligro": {"type": "INTEGER"},
                       "giro": {"type": "INTEGER"}, "emocion": {"type": "INTEGER"},
                       "sorpresa": {"type": "INTEGER"}, "rareza": {"type": "INTEGER"}},
        "required": ["n", "articulo", "articulo_lugar", "motivo", "persona", "peligro", "giro",
                     "emocion", "sorpresa", "rareza"]}}},
    "required": ["elegidos"],
}


CRITERIOS = ("persona", "peligro", "giro", "emocion")
PUNTAJE_MIN = 8.0    # Santi, 2026-11-13: solo pasan las de 8 o más de promedio
MAX_VERIFICAR = 3      # Santi, 2026-11-25: verificar solo las 3 mejores (y 3 del banco)
CURIOSAS = {"lugar_curioso", "invento", "costumbre", "record", "misterio", "dato_sorprendente"}


def es_curiosa(c: "Candidato") -> bool:
    """Una historia curiosa (no de personas): ahí "peligro" se mide como "sorpresa" (Santi, 2026-11-15)."""
    return str(c.clasif.get("tipo") or "") in CURIOSAS
PISO_UNA_POR_DIA = 7.0   # Santi, 2026-11-15: sin ninguna de 8, la mejor del día si tiene 7 (una por día)
A_PUNTUAR = 30       # cuántas puntúa Sonnet por propuesta (eran 8 de 20; presupuesto de 2026-11-15)


def puntaje_de(notas: dict, tipo: str | None, texto: str) -> float:
    """El promedio de persona, peligro (o sorpresa), giro y emoción; en un tema común (estación, edificio, fundación,
    inauguración, prócer) el MENOR entre ese promedio y la rareza (Santi, 2026-11-25: solo entran si tienen algo fuera
    de lo común)."""
    from . import temas

    if not all(k in notas for k in CRITERIOS):
        return 0.0
    prom = round(sum(notas[k] for k in CRITERIOS) / len(CRITERIOS), 2)
    if temas.tema_comun(tipo, texto) and isinstance(notas.get("rareza"), int):
        return float(min(prom, notas["rareza"]))
    return prom


def grupo_de(c: "Candidato") -> str:
    from . import temas

    return temas.grupo_latam(c.clasif.get("tipo"), c.texto)


def elegir(sonnet, cands: list[Candidato], cuantos: int = A_PUNTUAR) -> list[tuple[Candidato, str, str]]:
    """[(candidato, artículo del hecho, artículo del lugar)], del mejor al peor."""
    lineas = []
    for i, c in enumerate(cands):
        k = c.clasif
        marca = "★ CALENDARIO " if en_calendario(c) else ""
        lineas.append(f"{i + 1}. {marca}({c.anio}) {c.texto[:300]}\n   lugar: {k.get('lugar')}, {k.get('region')}, "
                      f"{k.get('pais')} · tipo: {k.get('tipo')} · conmemora hoy: {k.get('conmemora') or 'no'}"
                      f"\n   artículos: {' | '.join(c.paginas[:8])}")
    d = json.loads(sonnet.json(SISTEMA_ELEGIR.replace("{cuantos}", str(cuantos)), "\n".join(lineas),
                               SCHEMA_ELEGIR, temperatura=0.2))
    out, vistos = [], set()
    for x in d.get("elegidos") or []:
        n = x.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(cands) or n in vistos:
            continue
        c = cands[n - 1]
        art = x.get("articulo") if x.get("articulo") in c.paginas else c.paginas[0]
        lug = x.get("articulo_lugar") if x.get("articulo_lugar") in c.paginas else ""
        vistos.add(n)
        notas = {k: x.get(k) for k in CRITERIOS if isinstance(x.get(k), int)}
        if es_curiosa(c) and isinstance(x.get("sorpresa"), int) and x.get("sorpresa") > 0:
            # Santi, 2026-11-15: en las historias curiosas "peligro" pasa a ser "sorpresa"
            notas["peligro"] = x["sorpresa"]
            notas["sorpresa"] = x["sorpresa"]
        if isinstance(x.get("rareza"), int):
            notas["rareza"] = x["rareza"]
        c.clasif["puntajes"] = notas
        c.clasif["puntaje"] = puntaje_de(notas, c.clasif.get("tipo"), c.texto)
        out.append((c, art, lug if lug != art else ""))
    # El calendario manda aunque Sonnet no lo respete (sorted es estable: dentro de cada grupo, su orden), salvo los
    # próceres y las fundaciones, que van al final (Santi, 2026-11-23: son lo que peor rinde en Facebook).
    out.sort(key=lambda x: (es_procer(x[0]), not en_calendario(x[0])))
    return out[:cuantos]


# ---- 4. guion con el lugar -------------------------------------------------------------------

SISTEMA_GUION_LOCAL = ef.SISTEMA_GUION.replace(
    "un canal de efemérides para público joven, en español rioplatense (vos, no tú).",
    "un canal de efemérides para público joven, en español rioplatense (vos, no tú). Este video es\n"
    "para Facebook y lo va a ver sobre todo gente de ESE lugar de Latinoamérica: la historia es de\n"
    "ellos, contala con respeto y con orgullo (que alguien de ahí diga \"¡eso pasó en mi pueblo!\").").replace(
    '- El AÑO se dice recién en la TERCERA o CUARTA frase ("Fue en 1811.").',
    '- El AÑO y el LUGAR (el pueblo o la ciudad, escrito igual que te lo paso) se dicen recién en la\n'
    '  TERCERA o CUARTA frase ("Fue en 1811, en Cartagena de Indias.").\n'
    '- El LUGAR va también en el `titulo` (escrito igual) y como hashtag (sin espacios ni tildes,\n'
    '  ej. #VillaEpecuen), además de un hashtag del país.\n'
    '- Si te digo que hoy se conmemora, podés nombrarlo SOLO si el artículo lo dice.').replace(
    "el país o el lugar, para que la foto sea de ese momento y no de hoy.",
    "el NOMBRE DEL LUGAR (el pueblo o la ciudad), para que la foto sea de ese lugar y de ese momento.")


# Formato corto (Santi, 2026-11-10; historias_fb.formato_corto): 20-30 s, el gancho primero y la fecha
# en la segunda frase. Lo demás (solo el artículo, claridad, lugar en título y hashtag) igual.
# 30-40 s (Santi, 2026-11-13: en Facebook los de 30-45 s promedian 3.800 reproducciones; los de
# 15-30 s, 256). La de tecnología sigue en 20-30 s (ef.SISTEMA_GUION_CORTO).
SISTEMA_GUION_CORTO = ef.a_corto(SISTEMA_GUION_LOCAL, segundos=(30, 40), palabras=(70, 90), frases=(8, 12))
assert "La PRIMERA frase es el GANCHO" in SISTEMA_GUION_CORTO


def _sin_tildes(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch)).lower()


def _compacto(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _sin_tildes(t))


def validar_lugar(lugar: str, corto: bool = False):
    """El lugar en el título, en la primera frase y en un hashtag (regla de Santi, 2026-11-09). En
    el formato corto (gancho primero), en la primera o la segunda ("En <año>, en <lugar>,")."""
    def validar(d: dict) -> list[str]:
        errores = []
        clave = _sin_tildes(lugar).strip()
        frases = d.get("frases") or []
        # El lugar se dice en la 3.ª o 4.ª frase, con el año (2026-11-12: la 2.ª suma intriga).
        tercera = " ".join(_sin_tildes(str((f or {}).get("texto") or "")) for f in frases[2:4])
        if clave not in tercera:
            errores.append(f'la tercera o la cuarta frase tiene que nombrar el lugar: "Fue en <año>, en {lugar}."')
        if clave not in _sin_tildes(str(d.get("titulo") or "")):
            errores.append(f"el título tiene que nombrar el lugar ({lugar})")
        if not any(_compacto(lugar) == _compacto(str(h)) for h in d.get("hashtags") or []):
            errores.append(f"falta el hashtag del lugar: #{re.sub(r'[^A-Za-z0-9]', '', _sin_tildes(lugar).title())}")
        return errores
    return validar


def contexto_de(c: Candidato) -> str:
    k = c.clasif
    return (f"Lugar: {k.get('lugar')} ({k.get('region') or '-'}, {k.get('pais')}). "
            f"Hoy se conmemora: {k.get('conmemora') or 'nada en particular'}.\n")


def local_de(c: Candidato, aviso: str = "") -> dict:
    k = c.clasif
    out = {"lugar": k.get("lugar"), "region": k.get("region"), "pais": k.get("pais"),
           "tipo": k.get("tipo"), "conmemora": k.get("conmemora"), "seccion": c.seccion,
           "puntaje": k.get("puntaje"), "puntajes": k.get("puntajes")}
    out["grupo"] = grupo_de(c)
    if k.get("banco_id"):
        out["banco_id"] = k["banco_id"]
    out["origen"] = "banco" if k.get("banco_id") else ("web" if c.seccion == "web" else "wikipedia")
    if k.get("verificados"):
        out["verificados"] = k["verificados"]
        from . import bitacora

        bitacora.dato(fuentes=[{"dato": x["dato"], "fuentes": x["fuentes"]} for x in k["verificados"]],
                      origen_historia=out["origen"])
    if k.get("fuentes"):
        out["fuentes_web"] = list(k["fuentes"])
    if aviso:
        out["aviso"] = aviso
    return out


PISO_ABSOLUTO = 6.0   # Santi, 2026-11-15: la mejor del día sale si tiene 6 o más; debajo, el banco


def candidatos_web(web, dia: date, excluir: set | None = None, avisar=log.info) -> list[Candidato]:
    """Historias de diarios, sitios de historia, museos y archivos (web_historias.buscar, Santi 2026-11-16),
    ya clasificadas por la misma búsqueda; pasan las mismas reglas duras que las de Wikipedia."""
    from . import web_historias as wh

    try:
        halladas = wh.buscar(web, dia, evitar=sorted(excluir or set())[:10])
    except wh.WebError as err:
        avisar(f"búsqueda web: no salió ({err}); sigo con Wikipedia")
        return []
    out = []
    for h in halladas:
        texto = str(h["texto"]).strip()
        if texto in (excluir or set()) or h["anio"] > date.today().year or _DURO.search(texto) \
                or (h["anio"] >= 1945 and ef._GUERRA.search(texto)) or ef._TRAMA.search(texto):
            continue
        paginas = [p for p in (str(h.get("articulo_wikipedia") or "").strip(),
                               str(h.get("articulo_lugar") or "").strip()) if p]
        lugar = str(h.get("lugar") or h.get("pais") or "").strip()
        tipo = h.get("tipo") if h.get("tipo") in TIPOS else "otro"
        clasif = {"humana": True, "lugar": lugar, "region": str(h.get("region") or ""),
                  "pais": str(h.get("pais") or ""), "tipo": tipo, "tragedia_sola": False, "conmemora": "",
                  "interes": int(h.get("interes") or 6) if str(h.get("interes") or "").isdigit() else 6,
                  "fuentes": h["fuentes"], "web": True, "del_dia": wh.es_del_dia(h, dia)}
        out.append(Candidato("web", h["anio"], texto, paginas or [lugar], clasif))
    avisar(f"búsqueda web: {len(out)} historias de diarios, museos y sitios de historia")
    return out


def de_banco(banco: list[dict] | None, excluir: set | None = None, evitar_temas: set | None = None,
             pesos: dict | None = None) -> list[tuple[Candidato, str, str]]:
    """Las historias del banco de reserva como candidatos elegidos: primero el tema (el que rinde y no salió ayer,
    Santi 2026-11-25), después el puntaje."""
    from . import temas

    def clave(x):
        k = x.get("clasif") or {}
        g = temas.grupo_latam(k.get("tipo"), x.get("texto") or "")
        return (g in (evitar_temas or set()), g == "procer",
                -(float(x.get("puntaje") or 0) + float((pesos or temas.BASE_LATAM).get(g, 0.0))))

    out = []
    for it in sorted(banco or [], key=clave):
        if it.get("texto") in (excluir or set()) or it.get("articulo") in (excluir or set()):
            continue
        if float(it.get("puntaje") or 0) < PUNTAJE_MIN:     # nunca una de menos de 8 (Santi, 2026-11-16)
            continue
        clasif = dict(it.get("clasif") or {}, banco_id=it.get("id"), puntaje=it.get("puntaje"), conmemora="")
        c = Candidato("banco", int(it["anio"]), it["texto"], list(it["paginas"]), clasif)
        out.append((c, it.get("articulo") or c.paginas[0], it.get("articulo_lugar") or ""))
    return out


def proponer(wiki: ef.Wiki, sonnet, haiku, gemini, dia: date, carpeta: Path, avisar=log.info,
             videos: bool = False, tope_fotos_s: float | None = None, hecho: str = "",
             imagen_frase: bool = False, corto: bool = False, elector=None,
             elector_reintento=None, excluir: set | None = None,
             evitar_paises: set | None = None, mas_video: bool = False,
             piso_alternativo: float | None = None, puntuador=None,
             banco: list[dict] | None = None, solo_banco: bool = False, web=None,
             pesos: dict | None = None, fotos_primero: bool = False,
             evitar_temas: set | None = None) -> ef.Propuesta:
    """`fotos_primero` (Santi, 2026-11-25): las fotos antes del guion (fotos_primero.py), como en tecnología.

    `evitar_temas` (Santi, 2026-11-25): los grupos (temas.grupo_latam) que salieron ayer y hoy; esas historias van al
    final (solo salen si no hay otra), así el mismo tema no sale dos días seguidos.

    `web` (web_historias.ClienteWeb, Santi 2026-11-16): suma historias de la web a las de Wikipedia y
    verifica CADA dato de la elegida con 2 fuentes antes del guion (el guion sale solo de lo verificado).

    `solo_banco`: directo del banco de reserva, sin buscar en el día (a mano, cuando un día quedó sin
    video: Santi, 2026-11-15). `excluir`: hechos (su texto) que ya salieron hoy; `evitar_paises`: los países de esos (Santi,
    2026-11-12: 2 historias por día, sin repetir país si se puede: van al final, no afuera).

    La propuesta del día para Facebook. Mismo armado que la efeméride (fotos, hoja, aprobación),
    con otra fuente de hechos y Claude para el texto."""
    from . import fuentes_fotos

    from . import bitacora

    fuentes_fotos.nueva_corrida()
    aviso = [""]

    def seleccionar():
        nonlocal haiku
        bitacora.paso("busqueda")
        todos, conmemoraciones, homenajeados = leer_todo(wiki, dia, avisar)
        cands, motivos = filtrar(todos, date.today(), homenajeados)
        if hecho:
            # Haiku clasifica igual el día entero (solo, un hecho lo juzga distinto); después se queda
            # con los que lo mencionan.
            clasificar(haiku, cands, conmemoraciones)
            cands = [c for c in cands if ef._norm(hecho) in ef._norm(c.texto)]
            haiku = None
        avisar(f"{len(todos)} hechos del {dia:%d/%m} en es.wikipedia; {len(cands)} con lugar de "
               f"Latinoamérica {motivos}")
        web_cands = candidatos_web(web, dia, excluir, avisar) if web is not None and not hecho else []
        if not cands and not web_cands:
            raise ef.NarrarError("Ningún hecho de hoy tiene un lugar de Latinoamérica" +
                                 (f" (con «{hecho}»)" if hecho else ""))
        clasificar(haiku, cands, conmemoraciones)
        for c in cands:     # un aniversario de fundación: el lugar es la ciudad misma
            if c.seccion == "fundacion" and c.clasif and not str(c.clasif.get("lugar") or "").strip():
                c.clasif["lugar"] = c.paginas[0]
        lista = buenos(cands, pesos)
        if web_cands:       # las de la web entran siempre a la tanda que se puntúa
            lista = lista[:max(0, A_PUNTUAR - len(web_cands))] + buenos(web_cands, pesos)
        if hecho:
            # Lo eligió una persona (/historia 10/11 Epecuén, o el fijado para el día): Haiku no lo
            # descarta. Medido el 2026-11-09: con Epecuén solo en la lista dijo "no es una historia
            # humana"; con el día entero, "gente común, interés 8". Sin lugar, el del primer artículo.
            lista = lista + [c for c in cands if c not in lista]
            for c in lista:
                if not str(c.clasif.get("lugar") or "").strip():
                    c.clasif["lugar"] = c.paginas[0]
        lista = [c for c in lista if c.texto not in (excluir or set())]
        avisar(f"Haiku: {len(lista)} historias humanas con lugar concreto")
        if not lista:
            raise ef.NarrarError("Ningún hecho de hoy es una historia humana con un lugar concreto"
                                 + (" (sin contar las que ya salieron hoy)" if excluir else ""))
        lista = otro_pais_primero(lista, evitar_paises)
        # Puntúa Haiku (Santi, 2026-11-15: Sonnet solo para escribir y corregir guiones).
        fila_elegir = bitacora.fila_actual()
        elegidos = elegir(puntuador or sonnet, lista[:A_PUNTUAR], cuantos=A_PUNTUAR)
        parte_puntaje = bitacora.costo_entre_activa(fila_elegir) / max(1, len(lista[:A_PUNTUAR]))
        # Ni el mismo hecho ni la misma historia contada desde otra línea del día (2026-11-13: el 14/11 La
        # Pola aparece como nacimiento y como fusilamiento, con el mismo artículo).
        elegidos = [x for x in elegidos if x[0].texto not in (excluir or set()) and x[1] not in (excluir or set())]
        if not hecho:
            # Solo las que atrapan (Santi, 2026-11-13): 8 o más de promedio en persona, peligro, giro y
            # emoción. Si hoy no hay ninguna, no sale (y quien llama avisa): nada de relleno.
            flojas = [f"{c.anio} {c.clasif.get('lugar')}: {c.clasif.get('puntaje', 0):.1f}"
                      for c, _, _ in elegidos if c.clasif.get("puntaje", 0) < PUNTAJE_MIN]
            todos_ok = list(elegidos)
            elegidos = [x for x in elegidos if x[0].clasif.get("puntaje", 0) >= PUNTAJE_MIN]
            if flojas:
                avisar(f"debajo de {PUNTAJE_MIN:g}: " + " | ".join(flojas))
            if not elegidos and piso_alternativo:
                # Santi, 2026-11-15: si no hay ninguna de 8, sale igual la mejor del día si tiene 7 o más
                # (una sola por día: quien llama solo da el piso si hoy todavía no salió ninguna de menos de 8).
                mejor = max(todos_ok, key=lambda x: x[0].clasif.get("puntaje", 0), default=None)
                if mejor and mejor[0].clasif.get("puntaje", 0) >= piso_alternativo:
                    avisar(f"ninguna de {PUNTAJE_MIN:g}: sale la mejor ({mejor[0].clasif.get('puntaje'):.2f}, "
                           f"piso {piso_alternativo:g})")
                    elegidos = [mejor]
                    aviso[0] = (f"⚠️ salió con puntaje {mejor[0].clasif.get('puntaje', 0):.1f} "
                                f"(mínimo {PUNTAJE_MIN:g})").replace(".", ",")
            # a la bitácora: las que no pasan el puntaje, con su parte del pedido (Santi, 2026-11-15)
            quedan = {id(c) for c, _, _ in elegidos}
            for c, _, _ in todos_ok:
                if id(c) not in quedan:
                    bitacora.descarte(f"{c.anio} {c.clasif.get('lugar') or ''}: {c.texto[:80]}",
                                      f"puntaje {c.clasif.get('puntaje', 0):.2f} < {PUNTAJE_MIN:g}", "puntaje",
                                      costo=parte_puntaje)
            # Las mejores primero, con el tema que rinde (Santi, 2026-11-23): próceres al final; el calendario suma medio punto.
            elegidos.sort(key=lambda x: (grupo_de(x[0]) in (evitar_temas or set()), es_procer(x[0]),
                                         -(x[0].clasif.get("puntaje", 0) + peso_tema(x[0], pesos)
                                                            + (0.5 if en_calendario(x[0]) else 0.0))))
            if not elegidos:
                raise ef.NarrarError(f"Hoy ninguna historia llega a {PUNTAJE_MIN:g} de promedio (persona, "
                                     "peligro, giro y emoción): no saco una floja. "
                                     + ("Las mejores: " + " | ".join(flojas[:3]) if flojas else ""))
        return elegidos

    try:
        if solo_banco:
            raise ef.NarrarError("pedido a mano: directo del banco")
        elegidos = seleccionar()
    except ef.NarrarError as err:
        # Nunca un día sin video (Santi, 2026-11-15): debajo del piso (6) o sin candidatas, una historia
        # del banco de reserva (no depende de la fecha, puntuada de antemano con 8 o más).
        elegidos = de_banco(banco, excluir, evitar_temas, pesos)
        if not elegidos:
            raise
        aviso[0] = "📦 del banco de reserva (" + str(err).split(":")[0][:120] + ")"
        avisar(f"banco de reserva: {len(elegidos)} historias ({err})")
    orden = otro_pais_primero([c for c, _, _ in elegidos], evitar_paises)
    # el tema manda sobre el país (Santi, 2026-11-25): un tema que salió ayer u hoy va al final aunque sea de otro país
    elegidos = sorted(elegidos, key=lambda x: (grupo_de(x[0]) in (evitar_temas or set()), orden.index(x[0])))
    avisar("Sonnet eligió: " + " | ".join(f"{c.anio} {c.clasif.get('lugar')}: {c.texto[:50]} [{a}] ({grupo_de(c)})"
                                          for c, a, _ in elegidos))
    fallas, respaldo, descartes, insuf = [], None, {}, None
    intentos = [0]
    # Santi, 2026-11-25: se verifican solo las 3 mejores (del día; y otras 3 del banco si hace falta): con 15
    # verificaciones caídas en la semana, seguir probando las de abajo de la lista gastaba sin llegar a video
    verificadas = {"dia": 0, "banco": 0}

    def cola():
        """Las elegidas y, si ninguna sale (sin verificar, sin fotos), el banco (Santi, 2026-11-16: "nunca
        vacía"); el banco también se verifica."""
        yield from elegidos[:ef.MAX_GUIONES * 2]
        if hecho or any(c.clasif.get("banco_id") for c, _, _ in elegidos):
            return
        # Santi, 2026-11-18 (el banco se usó 3 veces en la semana): una historia del día que solo falló por fotos y
        # llega al 50 % sale con el mínimo relajado (como la de tecnología) ANTES de ir al banco (Puebla: 68 %).
        if insuf is not None and ef.umbral_relajado(insuf[0].pct) is not None and not respaldo:
            return
        extra = de_banco(banco, excluir, evitar_temas, pesos)
        if extra:
            avisar("ninguna de las del día salió: paso al banco de reserva")
            aviso[0] = "📦 del banco de reserva (las del día no salieron: " + "; ".join(fallas)[:120] + ")"
            intentos[0] = 0
            yield from extra[:ef.MAX_GUIONES]

    for c, articulo, art_lugar in cola():
        if intentos[0] >= ef.MAX_GUIONES:
            continue
        e = ef.Evento("es", c.anio, c.texto, [articulo] + [x for x in c.paginas if x != articulo])
        lugar = str(c.clasif.get("lugar") or "").strip()
        nombre_c = f"{c.anio} {lugar}: {c.texto[:80]}"
        verif, fila_v = None, bitacora.fila_actual()
        if web is not None:
            # Santi, 2026-11-16: cada dato con al menos 2 fuentes ANTES de usarlo (también las de Wikipedia
            # y las del banco); el guion se escribe solo con lo verificado.
            from . import web_historias as wh

            grupo = "banco" if c.clasif.get("banco_id") else "dia"
            if verificadas[grupo] >= MAX_VERIFICAR:
                continue
            verificadas[grupo] += 1
            bitacora.paso("verificacion")
            try:
                verif = wh.verificar(web, c.texto, c.anio, lugar, str(c.clasif.get("pais") or ""),
                                     pistas=c.clasif.get("fuentes"))
            except wh.WebError as err:
                if c.seccion == "web":      # sin verificar, una de la web no se usa
                    fallas.append(f"{e.anio}: sin verificar ({err})")
                    bitacora.descarte(nombre_c, f"no se pudo verificar: {err}", "verificacion", desde_fila=fila_v)
                    continue
                avisar(f"  verificación caída ({err}): sigo con el artículo, con aviso")
                aviso[0] = (aviso[0] + " · " if aviso[0] else "") + "⚠️ sin verificar con 2 fuentes (búsqueda caída)"
            else:
                if not verif.ok:
                    avisar(f"  no se pudo verificar: {verif.motivo}")
                    fallas.append(f"{e.anio}: no verificada ({verif.motivo[:120]})")
                    bitacora.descarte(nombre_c, f"no verificada: {verif.motivo}", "verificacion",
                                      desde_fila=fila_v, encontrado=" ".join(verif.links[:8]))
                    continue
                avisar(f"  verificada: {len(verif.datos)} datos con 2+ fuentes")
                c.clasif["verificados"] = verif.datos       # los links quedan en la propuesta y la bitácora
        intentos[0] += 1
        try:
            fotos, desc = ef.fotos_del_evento(wiki, e)
        except ef.WikiError as err:      # una de la web puede no tener artículo en Wikipedia
            if c.seccion != "web":
                raise
            avisar(f"  sin artículo para fotos ({err}): solo las búsquedas por frase")
            fotos, desc = [], {}
        if art_lugar:
            # Fotos primero del lugar real (pedido de Santi): las del artículo del pueblo o la ciudad
            # se suman a las del hecho, con las mismas reglas (licencia, época, contenido).
            lug = ef.Evento("es", c.anio, c.texto, [art_lugar])
            try:
                f_lugar, d2 = ef.fotos_del_evento(wiki, lug)
            except ef.WikiError:
                if c.seccion != "web":
                    raise
                f_lugar, d2 = [], {}
            for f in f_lugar:      # capa 1 (Santi, 2026-11-18): la ciudad entera = solo paisajes de ese lugar
                f.general = True
            fotos += [f for f in f_lugar if f.archivo not in {x.archivo for x in fotos}]
            for k, v in d2.items():
                desc[k] = desc.get(k, 0) + v
        for k, v in desc.items():
            descartes[k] = descartes.get(k, 0) + v
        if verif is not None and verif.ok:
            fuente = verif.texto        # solo lo verificado con 2 fuentes
        else:
            fuente = ef.texto_fuente(wiki, e)
            if art_lugar:
                fuente += "\n" + wiki.texto("es", art_lugar)[:6000]
        avisar(f"{e.anio} {lugar}: {len(fotos)} fotos del hecho y del lugar")
        banco_f = None
        if fotos_primero:
            from . import fotos_primero as fp

            fila_f = bitacora.fila_actual()
            bitacora.paso("fotos")
            try:
                banco_f = fp.juntar(wiki, haiku or sonnet, e, fotos, carpeta, f"{lugar}: {c.texto} {fuente[:700]}",
                                    avisar)
            except (fp.FotosPrevias, ef.NarrarError) as err:
                avisar(f"  {err}: no pido el guion")
                fallas.append(f"{e.anio}: {err}")
                bitacora.descarte(nombre_c, str(err), "fotos", desde_fila=fila_f, encontrado="fotos primero (Haiku)")
                continue
        fila_h, g = bitacora.fila_actual(), None
        no_de_hoy = c.clasif.get("banco_id") or (c.seccion == "web" and not c.clasif.get("del_dia"))
        try:
            bitacora.paso("guion")
            g = ef.escribir_guion(sonnet, e, fuente, sistema=SISTEMA_GUION_CORTO if corto else SISTEMA_GUION_LOCAL,
                                  validar_extra=validar_lugar(lugar, corto),
                                  contexto=contexto_de(c) + (ef.NO_ES_DE_HOY if no_de_hoy else "")
                                  + (banco_f.contexto() if banco_f else ""),
                                  corto=corto, rango=ef.LATAM_PALABRAS if corto else None,
                                  max_s=ef.LATAM_MAX_S if corto else 0.0)
            if banco_f:
                avisar(f"  fotos primero: el guion eligió foto en {banco_f.tomar_de_mostrar(g)} de "
                       f"{len(g.frases)} frases")
            g.imagen_frase = imagen_frase or corto
            g.mas_video = mas_video
            bitacora.paso("fotos")
            pool, g = ef.fotos_con_control(wiki, gemini, e, g, fotos, carpeta, avisar, videos=videos,
                                           tope_s=tope_fotos_s, elector=elector, primero=banco_f,
                                           elector_reintento=elector_reintento,
                                           reescribir=lambda g_, idx, pool_, forz=None: ef.reescribir_frases_con_foto(
                                               haiku or sonnet, e, fuente, g_, idx, pool_, avisar, forz))
        except ef.PocasFotos as pocas:
            avisar(f"  {pocas}")
            fallas.append(f"{e.anio}: {pocas}")
            bitacora.descarte(nombre_c, str(pocas), "fotos", desde_fila=fila_h,
                              buscado=list(getattr(pocas.guion, "mostrar", []) or []),
                              encontrado=f"{pocas.disponibles} fotos de época que sirven ({len(pocas.pool)} en el pool)")
            if ef.respaldo_sirve(pocas) and (respaldo is None or pocas.disponibles > respaldo[3]):
                respaldo = (e, fuente, pocas, pocas.disponibles, c)
            continue
        except ef.NarrarError as err:
            avisar(f"  no salió: {err}")
            fallas.append(f"{e.anio}: {err}")
            if isinstance(err, ef.FotosInsuficientes) and (insuf is None or err.pct > insuf[0].pct):
                insuf = (err, e, fuente, c)
            en_fotos = g is not None
            bitacora.descarte(nombre_c, str(err), "fotos" if en_fotos else "guion", desde_fila=fila_h,
                              buscado=list(g.mostrar) if en_fotos else None,
                              encontrado=f"{len(fotos)} fotos del hecho y del lugar; {str(err)[:150]}" if en_fotos else "")
            continue
        return ef.Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in pool],
                            reserva=[], guion=g.a_dict(), fuente=fuente[:20000], descartes=descartes,
                            destino="facebook", local=local_de(c, aviso[0]))
    if insuf and not respaldo and ef.aceptar_relajado(insuf[0], avisar):
        err, e, fuente, c = insuf
        return ef.Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in err.pool],
                            reserva=[], guion=err.guion.a_dict(), fuente=fuente[:20000], descartes=descartes,
                            destino="facebook", local=local_de(c, aviso[0]))
    if respaldo:
        e, fuente, pocas, n, c = respaldo
        avisar(f"Ningún hecho llegó a {ilustrar.MIN_FOTOS_ABSOLUTO} fotos de época: uso {e.anio} ({n})")
        pocas.guion.sin_alternativa = True
        return ef.Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in pocas.pool],
                            reserva=[], guion=pocas.guion.a_dict(), fuente=fuente[:20000],
                            descartes=descartes, destino="facebook", local=local_de(c, aviso[0]))
    raise ef.SinFotosReales("Ninguna historia de hoy salió, no armo un video malo: "
                            + " | ".join(fallas)[:600])


def rehacer(p: ef.Propuesta, wiki: ef.Wiki, sonnet, gemini, carpeta: Path, correccion: str,
            avisar=log.info, elector=None, elector_reintento=None) -> ef.Propuesta:
    """✏️ del video de Facebook: el guion de nuevo con Sonnet (mismas reglas del lugar) y las fotos
    de sus frases con Gemini; el pool de antes se conserva."""
    e = ef.Evento(**p.evento)
    anterior = ef.Guion.de_dict(p.guion)
    lugar = str(p.local.get("lugar") or "")
    c = Candidato(p.local.get("seccion") or "acontecimientos", e.anio, e.texto, e.paginas, dict(p.local))
    corto = anterior.corto
    g = ef.escribir_guion(sonnet, e, p.fuente, correccion=correccion, anterior=anterior.texto,
                          sistema=SISTEMA_GUION_CORTO if corto else SISTEMA_GUION_LOCAL,
                          validar_extra=validar_lugar(lugar, corto), contexto=contexto_de(c), corto=corto,
                          rango=ef.LATAM_PALABRAS if corto else None, max_s=ef.LATAM_MAX_S if corto else 0.0)
    g.imagen_frase = anterior.imagen_frase
    g.mas_video = anterior.mas_video
    fotos, _ = ef.fotos_del_evento(wiki, e)
    try:
        pool, g = ef.fotos_con_control(wiki, gemini, e, g, fotos, carpeta, avisar,
                                       pool=[ef.Foto.de_dict(f) for f in p.fotos],
                                       descartadas=set(anterior.descartadas), videos=anterior.con_videos,
                                       elector=elector, elector_reintento=elector_reintento)
    except ef.PocasFotos as pocas:
        if not ef.respaldo_sirve(pocas):
            raise ef.SinFotosReales(f"{pocas}; ni con la segunda búsqueda llega al 70 % de fotos reales")
        pool, g = pocas.pool, pocas.guion
        g.sin_alternativa = anterior.sin_alternativa
    except ef.FotosInsuficientes as f:
        raise ef.SinFotosReales(f"{f}, también con la segunda búsqueda: no armo el video") from f
    return ef.Propuesta(fecha=p.fecha, evento=p.evento, fotos=[f.a_dict() for f in pool],
                        reserva=p.reserva, guion=g.a_dict(), fuente=p.fuente, descartes=p.descartes,
                        destino=p.destino, local=p.local)


def contar_mes(wiki: ef.Wiki, haiku, desde: date, dias: int, avisar=print) -> list[dict]:
    """Cuántos candidatos buenos hay por día (para la medición pedida por Santi): por día, cuántos
    hechos, cuántos con lugar, y los que Haiku dice que son historias humanas con lugar concreto
    (con y sin conmemoración)."""
    from datetime import timedelta

    out = []
    for k in range(dias):
        dia = desde + timedelta(days=k)
        todos, conm, homen = leer_todo(wiki, dia, avisar)
        cands, _ = filtrar(todos, date.today(), homen)
        clasificar(haiku, cands, conm)
        b = buenos(cands)
        fila = {"dia": dia.isoformat(), "hechos": len(todos), "con_lugar": len(cands), "buenos": len(b),
                "con_conmemoracion": sum(1 for c in b if c.clasif.get("conmemora")),
                "fuertes": sum(1 for c in b if int(c.clasif.get("interes") or 0) >= 7),
                "mejores": [f"{c.anio} {c.clasif.get('lugar')} ({c.clasif.get('pais')}): {c.texto[:90]}"
                            for c in b[:3]]}
        avisar(f"{fila['dia']}: {fila['hechos']} hechos, {fila['con_lugar']} con lugar, {fila['buenos']} "
               f"buenos ({fila['fuertes']} fuertes, {fila['con_conmemoracion']} con conmemoración)")
        out.append(fila)
    return out
