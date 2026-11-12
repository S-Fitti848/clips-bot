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

TIPOS = ("heroe_de_pueblo", "gente_comun", "anecdota", "momento_emotivo", "fundacion", "otro")

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
# de Latinoamérica es el de Venezuela (más el del estado Nueva Esparta).
ANEXOS_EFEMERIDES = ("Anexo:Efemérides en Venezuela", "Anexo:Efemérides del Estado Nueva Esparta")

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


FRASES_HISTORIA = ('"el {d} de" vecinos', '"el {d} de" pobladores')


def historia_de_ciudades(wiki: ef.Wiki, dia: date, lugares: list[str], tope: int = 12) -> list[Candidato]:
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
    cuenta["conmemoraciones con año"] = sum(1 for c in todos if c.seccion == "celebracion")
    vistos = {(c.anio, ef._norm(c.paginas[0])) for c in todos if c.paginas}
    for c in fund + hist:
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

SISTEMA_CLASIFICAR = """Clasificás hechos históricos para un canal de videos cortos de historias
humanas de Latinoamérica ("Pequeña Historia"). Para CADA hecho de la lista decí:
- `humana`: true si es una HISTORIA HUMANA: hay personas concretas (o un pueblo entero) que hacen o
  viven algo notable que se puede contar como una historia (un héroe de pueblo, gente común que hizo
  algo, una anécdota, un momento emotivo, la fundación de un pueblo con quienes la hicieron). false
  si es un trámite institucional, una ley, un cambio de gobierno, una elección, un tratado, la
  fundación de una empresa, un canal de TV, un club o una universidad sin historia detrás, un
  resultado deportivo suelto o política partidaria.
- `lugar`: el pueblo o la ciudad CONCRETA donde pasó (no el país). Vacío si no hay uno.
- `region`: la provincia, estado o departamento, si se sabe. `pais`: el país de hoy.
- `tipo`: heroe_de_pueblo, gente_comun, anecdota, momento_emotivo, fundacion u otro.
- `tragedia_sola`: true si lo central es una muerte, un desastre, un crimen o una represión SIN un
  acto heroico o algo luminoso que contar. (Un maquinista que muere salvando a su pueblo: false.
  Un terremoto con miles de muertos: true. Una heroína fusilada por defender la independencia: false.)
- `conmemora`: si alguna de las conmemoraciones de hoy recuerda este hecho o a su protagonista,
  cuál (corta); si no, vacío.
- `interes` de 1 a 10: cuánto engancharía a gente de ese lugar y de Latinoamérica ("¡eso pasó en mi
  pueblo!"), como el maquinista de Nacozari.
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


def buenos(cands: list[Candidato]) -> list[Candidato]:
    """Historias con un lugar concreto, sin tragedias solas, de mejor a peor. Calendario (Santi,
    2026-11-11: "esos días tienen prioridad sobre cualquier otro hecho"): primero las fechas que se
    recuerdan hoy (aunque Haiku no las vea como historia humana), y entre ellas los países con más
    público; después, el interés."""
    ok = [c for c in cands if (c.clasif.get("humana") or en_calendario(c))
          and str(c.clasif.get("lugar") or "").strip() and not c.clasif.get("tragedia_sola")]
    return sorted(ok, key=lambda c: (not en_calendario(c), prioridad_pais(c.clasif.get("pais")),
                                     -int(c.clasif.get("interes") or 0)))


# ---- 3. Sonnet elige -------------------------------------------------------------------------

SISTEMA_ELEGIR = """Elegís la historia del día para "Pequeña Historia" en Facebook: un video corto
con una historia HUMANA y REAL de un lugar concreto de Latinoamérica. El modelo a seguir es el
maquinista Jesús García, que en 1907 alejó un tren con dinamita encendida y salvó a Nacozari: la
gente de ese lugar se siente identificada, la comparte y cuenta sus recuerdos.

Ordená del mejor al peor (hasta 8) los que más se parecen a eso:
- gente concreta que hizo algo notable (héroes de pueblo, gente común, anécdotas, momentos
  emotivos), en un pueblo o ciudad que se pueda nombrar;
- los marcados ★ CALENDARIO se recuerdan HOY (aniversario, fundación, día nacional, fiesta del
  lugar): van SIEMPRE primero, antes que cualquier otro, y entre ellos primero México, Colombia,
  Argentina, Perú, Chile y Venezuela (es cuando la gente lo comparte);
- que se pueda contar en 40 segundos y se entienda sin saber historia;
- nada de tragedias solas (muertes, desastres, crímenes sin un acto heroico), ni política
  partidaria, ni guerras recientes;
- nada que pase DENTRO de una ficción (lo que le pasa a un personaje de una serie, telenovela,
  juego o película): la cultura pop solo si se cuenta desde la vida real (estreno, quién lo creó,
  cómo se hizo, impacto, récords).
Para cada uno: `articulo` = el título EXACTO, de la lista de artículos del hecho, del artículo que
cuenta ESE hecho (no el del país ni el de una fecha); `articulo_lugar` = el título, de la misma
lista, del artículo del pueblo o ciudad (vacío si no está). Respondé solo con el JSON pedido."""

SCHEMA_ELEGIR = {
    "type": "OBJECT",
    "properties": {"elegidos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"n": {"type": "INTEGER"}, "articulo": {"type": "STRING"},
                       "articulo_lugar": {"type": "STRING"}, "motivo": {"type": "STRING"}},
        "required": ["n", "articulo", "articulo_lugar", "motivo"]}}},
    "required": ["elegidos"],
}


def elegir(sonnet, cands: list[Candidato], cuantos: int = 8) -> list[tuple[Candidato, str, str]]:
    """[(candidato, artículo del hecho, artículo del lugar)], del mejor al peor."""
    lineas = []
    for i, c in enumerate(cands):
        k = c.clasif
        marca = "★ CALENDARIO " if en_calendario(c) else ""
        lineas.append(f"{i + 1}. {marca}({c.anio}) {c.texto[:300]}\n   lugar: {k.get('lugar')}, {k.get('region')}, "
                      f"{k.get('pais')} · tipo: {k.get('tipo')} · conmemora hoy: {k.get('conmemora') or 'no'}"
                      f"\n   artículos: {' | '.join(c.paginas[:8])}")
    d = json.loads(sonnet.json(SISTEMA_ELEGIR, "\n".join(lineas), SCHEMA_ELEGIR, temperatura=0.2))
    out, vistos = [], set()
    for x in d.get("elegidos") or []:
        n = x.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(cands) or n in vistos:
            continue
        c = cands[n - 1]
        art = x.get("articulo") if x.get("articulo") in c.paginas else c.paginas[0]
        lug = x.get("articulo_lugar") if x.get("articulo_lugar") in c.paginas else ""
        vistos.add(n)
        out.append((c, art, lug if lug != art else ""))
    # El calendario manda aunque Sonnet no lo respete (sorted es estable: dentro de cada grupo, su orden).
    out.sort(key=lambda x: not en_calendario(x[0]))
    return out[:cuantos]


# ---- 4. guion con el lugar -------------------------------------------------------------------

SISTEMA_GUION_LOCAL = ef.SISTEMA_GUION.replace(
    "un canal de efemérides para público joven, en español rioplatense (vos, no tú).",
    "un canal de efemérides para público joven, en español rioplatense (vos, no tú). Este video es\n"
    "para Facebook y lo va a ver sobre todo gente de ESE lugar de Latinoamérica: la historia es de\n"
    "ellos, contala con respeto y con orgullo (que alguien de ahí diga \"¡eso pasó en mi pueblo!\").").replace(
    '- La SEGUNDA frase arranca EXACTAMENTE con "En <año>," y cuenta cuándo y dónde.',
    '- La SEGUNDA frase arranca EXACTAMENTE con "En <año>, en <lugar>," (el pueblo o la ciudad,\n'
    '  escrito igual que te lo paso) y cuenta dónde y cuándo.\n'
    '- El LUGAR va también en el `titulo` (escrito igual) y como hashtag (sin espacios ni tildes,\n'
    '  ej. #VillaEpecuen), además de un hashtag del país.\n'
    '- Si te digo que hoy se conmemora, podés nombrarlo SOLO si el artículo lo dice.').replace(
    "el país o el lugar, para que la foto sea de ese momento y no de hoy.",
    "el NOMBRE DEL LUGAR (el pueblo o la ciudad), para que la foto sea de ese lugar y de ese momento.")


# Formato corto (Santi, 2026-11-10; historias_fb.formato_corto): 20-30 s, el gancho primero y la fecha
# en la segunda frase. Lo demás (solo el artículo, claridad, lugar en título y hashtag) igual.
SISTEMA_GUION_CORTO = SISTEMA_GUION_LOCAL.replace(
    "un video vertical de 35 a 45 segundos", "un video vertical de 20 a 30 segundos").replace(
    "- Entre 80 y 100 palabras en total (contalas: menos de 70 queda corto y más de 105 se pasa de\n"
    "  45 segundos), en 8 a 14 frases, habladas, no escritas.",
    "- Entre 50 y 70 palabras en total (contalas: menos de 45 queda corto y más de 72 se pasa de\n"
    "  30 segundos), en 7 a 11 frases, habladas, no escritas. Directo a lo interesante: nada de\n"
    "  contexto que no haga falta para entender.").replace(
    '- "Menos datos" NO es un guion más corto: sigue siendo de 80 a 100 palabras.',
    '- "Menos datos" NO es un guion más corto que 50 palabras.')
assert (SISTEMA_GUION_CORTO.count("20 a 30 segundos") == 1 and "Entre 50 y 70" in SISTEMA_GUION_CORTO
        and "La PRIMERA frase es el GANCHO" in SISTEMA_GUION_CORTO and "más corto que 50" in SISTEMA_GUION_CORTO)


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
        # Gancho primero (2026-11-12, en los dos formatos): el lugar en la primera o la segunda frase.
        primera = " ".join(_sin_tildes(str((f or {}).get("texto") or "")) for f in frases[:2])
        if clave not in primera:
            errores.append(f'la segunda frase tiene que nombrar el lugar: "En <año>, en {lugar},"')
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


def local_de(c: Candidato) -> dict:
    k = c.clasif
    return {"lugar": k.get("lugar"), "region": k.get("region"), "pais": k.get("pais"),
            "tipo": k.get("tipo"), "conmemora": k.get("conmemora"), "seccion": c.seccion}


def proponer(wiki: ef.Wiki, sonnet, haiku, gemini, dia: date, carpeta: Path, avisar=log.info,
             videos: bool = False, tope_fotos_s: float | None = None, hecho: str = "",
             imagen_frase: bool = False, corto: bool = False, elector=None,
             elector_reintento=None) -> ef.Propuesta:
    """La propuesta del día para Facebook. Mismo armado que la efeméride (fotos, hoja, aprobación),
    con otra fuente de hechos y Claude para el texto."""
    from . import fuentes_fotos

    fuentes_fotos.nueva_corrida()
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
    if not cands:
        raise ef.NarrarError("Ningún hecho de hoy tiene un lugar de Latinoamérica" +
                             (f" (con «{hecho}»)" if hecho else ""))
    clasificar(haiku, cands, conmemoraciones)
    for c in cands:     # un aniversario de fundación: el lugar es la ciudad misma
        if c.seccion == "fundacion" and c.clasif and not str(c.clasif.get("lugar") or "").strip():
            c.clasif["lugar"] = c.paginas[0]
    lista = buenos(cands)
    if hecho:
        # Lo eligió una persona (/historia 10/11 Epecuén, o el fijado para el día): Haiku no lo
        # descarta. Medido el 2026-11-09: con Epecuén solo en la lista dijo "no es una historia
        # humana"; con el día entero, "gente común, interés 8". Sin lugar, el del primer artículo.
        lista = lista + [c for c in cands if c not in lista]
        for c in lista:
            if not str(c.clasif.get("lugar") or "").strip():
                c.clasif["lugar"] = c.paginas[0]
    avisar(f"Haiku: {len(lista)} historias humanas con lugar concreto")
    if not lista:
        raise ef.NarrarError("Ningún hecho de hoy es una historia humana con un lugar concreto")
    elegidos = elegir(sonnet, lista[:20])
    avisar("Sonnet eligió: " + " | ".join(f"{c.anio} {c.clasif.get('lugar')}: {c.texto[:50]} [{a}]"
                                          for c, a, _ in elegidos))
    fallas, respaldo, descartes = [], None, {}
    for c, articulo, art_lugar in elegidos[:ef.MAX_GUIONES]:
        e = ef.Evento("es", c.anio, c.texto, [articulo] + [x for x in c.paginas if x != articulo])
        fotos, desc = ef.fotos_del_evento(wiki, e)
        if art_lugar:
            # Fotos primero del lugar real (pedido de Santi): las del artículo del pueblo o la ciudad
            # se suman a las del hecho, con las mismas reglas (licencia, época, contenido).
            lug = ef.Evento("es", c.anio, c.texto, [art_lugar])
            f_lugar, d2 = ef.fotos_del_evento(wiki, lug)
            fotos += [f for f in f_lugar if f.archivo not in {x.archivo for x in fotos}]
            for k, v in d2.items():
                desc[k] = desc.get(k, 0) + v
        for k, v in desc.items():
            descartes[k] = descartes.get(k, 0) + v
        fuente = ef.texto_fuente(wiki, e)
        if art_lugar:
            fuente += "\n" + wiki.texto("es", art_lugar)[:6000]
        lugar = str(c.clasif.get("lugar") or "").strip()
        avisar(f"{e.anio} {lugar}: {len(fotos)} fotos del hecho y del lugar")
        try:
            g = ef.escribir_guion(sonnet, e, fuente, sistema=SISTEMA_GUION_CORTO if corto else SISTEMA_GUION_LOCAL,
                                  validar_extra=validar_lugar(lugar, corto), contexto=contexto_de(c),
                                  corto=corto)
            g.imagen_frase = imagen_frase or corto
            pool, g = ef.fotos_con_control(wiki, gemini, e, g, fotos, carpeta, avisar, videos=videos,
                                           tope_s=tope_fotos_s, elector=elector,
                                           elector_reintento=elector_reintento)
        except ef.PocasFotos as pocas:
            avisar(f"  {pocas}")
            fallas.append(f"{e.anio}: {pocas}")
            if ef.respaldo_sirve(pocas) and (respaldo is None or pocas.disponibles > respaldo[3]):
                respaldo = (e, fuente, pocas, pocas.disponibles, c)
            continue
        except ef.NarrarError as err:
            avisar(f"  no salió: {err}")
            fallas.append(f"{e.anio}: {err}")
            continue
        return ef.Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in pool],
                            reserva=[], guion=g.a_dict(), fuente=fuente[:20000], descartes=descartes,
                            destino="facebook", local=local_de(c))
    if respaldo:
        e, fuente, pocas, n, c = respaldo
        avisar(f"Ningún hecho llegó a {ilustrar.MIN_FOTOS_ABSOLUTO} fotos de época: uso {e.anio} ({n})")
        pocas.guion.sin_alternativa = True
        return ef.Propuesta(fecha=dia.isoformat(), evento=e.a_dict(), fotos=[f.a_dict() for f in pocas.pool],
                            reserva=[], guion=pocas.guion.a_dict(), fuente=fuente[:20000],
                            descartes=descartes, destino="facebook", local=local_de(c))
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
                          validar_extra=validar_lugar(lugar, corto), contexto=contexto_de(c), corto=corto)
    g.imagen_frase = anterior.imagen_frase
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
