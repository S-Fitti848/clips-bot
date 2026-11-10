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
    """Wikitexto de una línea → texto: [[A|B]] → B, sin plantillas, refs ni negritas."""
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", t, flags=re.S)
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


def leer_dia(wiki: ef.Wiki, dia: date) -> tuple[list[Candidato], list[str], set[str]]:
    """(candidatos, conmemoraciones del día en texto, personas homenajeadas ese día). Los
    candidatos todavía sin filtrar."""
    titulo = f"{dia.day} de {ef.MESES[dia.month - 1]}"
    d = wiki._get(ef.API.format(lang="es"), {"action": "parse", "page": titulo, "prop": "wikitext",
                                              "format": "json", "formatversion": 2, "redirects": 1})
    texto = (d.get("parse") or {}).get("wikitext") or ""
    if isinstance(texto, dict):
        texto = texto.get("*", "")
    secs = _secciones(texto)
    conmemoraciones, homenajeados = [], set()
    for nombre, cuerpo in secs.items():
        if nombre.startswith(("celebraciones", "fiestas", "conmemoraciones")):
            for linea in cuerpo.splitlines():
                if linea.lstrip().startswith("*") and len(_limpiar(linea.lstrip("*: "))) > 3:
                    conmemoraciones.append(_limpiar(linea.lstrip("*: "))[:220])
                    homenajeados.update(_enlaces(linea))
    out: list[Candidato] = []
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
    if c.seccion != "acontecimientos" and not homenajeado(c.paginas[0], homenajeados):
        return "nacimiento o muerte sin conmemoración"
    if not LUGAR_RE.search(c.texto):
        return "sin lugar de Latinoamérica"
    if _DURO.search(c.texto):
        return "tema sensible"
    if c.anio >= 1945 and ef._GUERRA.search(c.texto):
        return "guerra reciente"
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


def buenos(cands: list[Candidato]) -> list[Candidato]:
    """Historias humanas con un lugar concreto, sin tragedias solas, de mejor a peor (los que
    coinciden con una conmemoración del día, primero)."""
    ok = [c for c in cands if c.clasif.get("humana") and str(c.clasif.get("lugar") or "").strip()
          and not c.clasif.get("tragedia_sola")]
    return sorted(ok, key=lambda c: (bool(c.clasif.get("conmemora")), int(c.clasif.get("interes") or 0)),
                  reverse=True)


# ---- 3. Sonnet elige -------------------------------------------------------------------------

SISTEMA_ELEGIR = """Elegís la historia del día para "Pequeña Historia" en Facebook: un video corto
con una historia HUMANA y REAL de un lugar concreto de Latinoamérica. El modelo a seguir es el
maquinista Jesús García, que en 1907 alejó un tren con dinamita encendida y salvó a Nacozari: la
gente de ese lugar se siente identificada, la comparte y cuenta sus recuerdos.

Ordená del mejor al peor (hasta 8) los que más se parecen a eso:
- gente concreta que hizo algo notable (héroes de pueblo, gente común, anécdotas, momentos
  emotivos), en un pueblo o ciudad que se pueda nombrar;
- mejor si HOY ese lugar lo conmemora (aniversario, día nacional): es cuando la gente lo comparte;
- que se pueda contar en 40 segundos y se entienda sin saber historia;
- nada de tragedias solas (muertes, desastres, crímenes sin un acto heroico), ni política
  partidaria, ni guerras recientes.
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
        lineas.append(f"{i + 1}. ({c.anio}) {c.texto[:300]}\n   lugar: {k.get('lugar')}, {k.get('region')}, "
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
    return out[:cuantos]


# ---- 4. guion con el lugar -------------------------------------------------------------------

SISTEMA_GUION_LOCAL = ef.SISTEMA_GUION.replace(
    "un canal de efemérides para público joven, en español rioplatense (vos, no tú).",
    "un canal de efemérides para público joven, en español rioplatense (vos, no tú). Este video es\n"
    "para Facebook y lo va a ver sobre todo gente de ESE lugar de Latinoamérica: la historia es de\n"
    "ellos, contala con respeto y con orgullo (que alguien de ahí diga \"¡eso pasó en mi pueblo!\").").replace(
    '- La primera frase arranca EXACTAMENTE con "Un día como hoy, en <año>," y sigue con el gancho.',
    '- La primera frase arranca EXACTAMENTE con "Un día como hoy, en <año>, en <lugar>," (el pueblo o\n'
    '  la ciudad, escrito igual que te lo paso) y sigue con el gancho.\n'
    '- El LUGAR va también en el `titulo` (escrito igual) y como hashtag (sin espacios ni tildes,\n'
    '  ej. #VillaEpecuen), además de un hashtag del país.\n'
    '- Si te digo que hoy se conmemora, podés nombrarlo SOLO si el artículo lo dice.').replace(
    "el país o el lugar, para que la foto sea de ese momento y no de hoy.",
    "el NOMBRE DEL LUGAR (el pueblo o la ciudad), para que la foto sea de ese lugar y de ese momento.")


def _sin_tildes(t: str) -> str:
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch)).lower()


def _compacto(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _sin_tildes(t))


def validar_lugar(lugar: str):
    """El lugar en el título, en la primera frase y en un hashtag (regla de Santi, 2026-11-09)."""
    def validar(d: dict) -> list[str]:
        errores = []
        clave = _sin_tildes(lugar).strip()
        frases = d.get("frases") or []
        primera = _sin_tildes(str((frases[0] or {}).get("texto") or "")) if frases else ""
        if clave not in primera:
            errores.append(f'la primera frase tiene que nombrar el lugar: "Un día como hoy, en <año>, en {lugar},"')
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
             videos: bool = False, tope_fotos_s: float | None = None, hecho: str = "") -> ef.Propuesta:
    """La propuesta del día para Facebook. Mismo armado que la efeméride (fotos, hoja, aprobación),
    con otra fuente de hechos y Claude para el texto."""
    from . import fuentes_fotos

    fuentes_fotos.nueva_corrida()
    todos, conmemoraciones, homenajeados = leer_dia(wiki, dia)
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
            g = ef.escribir_guion(sonnet, e, fuente, sistema=SISTEMA_GUION_LOCAL,
                                  validar_extra=validar_lugar(lugar), contexto=contexto_de(c))
            pool, g = ef.fotos_para_guion(wiki, gemini, e, g, fotos, carpeta, avisar, videos=videos,
                                          tope_s=tope_fotos_s)
        except ef.PocasFotos as pocas:
            avisar(f"  {pocas}")
            fallas.append(f"{e.anio}: {pocas}")
            if respaldo is None or pocas.disponibles > respaldo[3]:
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
    raise ef.NarrarError("Ninguna historia de hoy salió: " + " | ".join(fallas)[:600])


def rehacer(p: ef.Propuesta, wiki: ef.Wiki, sonnet, gemini, carpeta: Path, correccion: str,
            avisar=log.info) -> ef.Propuesta:
    """✏️ del video de Facebook: el guion de nuevo con Sonnet (mismas reglas del lugar) y las fotos
    de sus frases con Gemini; el pool de antes se conserva."""
    e = ef.Evento(**p.evento)
    anterior = ef.Guion.de_dict(p.guion)
    lugar = str(p.local.get("lugar") or "")
    c = Candidato(p.local.get("seccion") or "acontecimientos", e.anio, e.texto, e.paginas, dict(p.local))
    g = ef.escribir_guion(sonnet, e, p.fuente, correccion=correccion, anterior=anterior.texto,
                          sistema=SISTEMA_GUION_LOCAL, validar_extra=validar_lugar(lugar),
                          contexto=contexto_de(c))
    fotos, _ = ef.fotos_del_evento(wiki, e)
    try:
        pool, g = ef.fotos_para_guion(wiki, gemini, e, g, fotos, carpeta, avisar,
                                      pool=[ef.Foto.de_dict(f) for f in p.fotos],
                                      descartadas=set(anterior.descartadas), videos=anterior.con_videos)
    except ef.PocasFotos as pocas:
        pool, g = pocas.pool, pocas.guion
        g.sin_alternativa = anterior.sin_alternativa
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
        todos, conm, homen = leer_dia(wiki, dia)
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
