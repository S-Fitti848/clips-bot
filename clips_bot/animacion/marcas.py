"""Canal de animación: el origen de las marcas, con humor y sarcasmo (Santi, 2026-11-14).

Un video por día, dibujado por código (sin IA generativa de imagen y SIN logos: el nombre de la
marca, como mucho, escrito en la fuente común del canal):

  1. catálogo (`marcas.yaml`, 457 marcas verificadas contra Wikipedia) y ROTACIÓN: un ángulo de una
     marca no se repite nunca, y una marca no sale dos veces en 7 días (tabla `animacion_videos`);
  2. candidatos que pasan la rotación (uno por marca) + un pedazo de su artículo de Wikipedia;
  3. Sonnet elige y puntúa (marca conocida, dato sorprendente, giro, humor: 1-10 cada uno); pasan
     los de promedio ≥ 8 que no tocan nada sensible. Si ninguno llega, ese día no sale y se avisa;
  4. Sonnet escribe el guion (gancho → giro → final que paga el gancho, 30-45 s, con sarcasmo) y la
     escena de cada frase; se valida como en Pequeña Historia (nombres, cifras y meses tienen que
     estar en el artículo) y, si no pasa, se reintenta con los errores;
  5. voz (`efemerides.voz_efemeride`), Whisper para los tiempos reales, subtítulos de la base, la
     boca del narrador con la voz, música de `musica.py` baja, y el render de `render.py`;
  6. a Telegram, SIN subir a ningún lado: el canal de YouTube ("animacion") todavía no existe.

Lo prende `animacion.activo` (settings.yaml); lo corre `_animacion_tick` en la escucha.
CLI: `python -m clips_bot.animacion.marcas [--dia AAAA-MM-DD] [--enviar] [--sin-registrar]`.
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import escenas as esc
from . import paleta as P
from . import personajes as per

log = logging.getLogger(__name__)

CATALOGO = Path(__file__).with_name("marcas.yaml")
CANAL = "animacion"          # el nombre del canal de YouTube cuando se conecte (CANALES del módulo de YouTube)

ANGULOS = {
    "origen": "cómo nació la marca (quién, dónde, cómo empezó)",
    "nombre": "de dónde sale el nombre",
    "logo": "la historia del logo (contada, NUNCA dibujada)",
    "casi_quiebra": "cuando estuvo a punto de quebrar y cómo se salvó",
    "rival": "su rival y la pelea entre las dos",
    "producto_fracasado": "un producto que lanzó y fracasó",
    "mascota": "la historia de su mascota o personaje",
    "slogan": "la historia de un slogan o una publicidad",
}
# Las palabras que buscan en el artículo el pedazo que habla de cada ángulo.
_CLAVES_ANGULO = {
    "origen": r"fund|naci|cre[oó]|comenz|inici|orig",
    "nombre": r"nombre|llam|denomin|significa|proviene|deriva",
    "logo": r"logo|logotipo|isotipo|emblema|imagen corporativa|dise[nñ]",
    "casi_quiebra": r"quiebra|bancarrota|crisis|deuda|p[eé]rdida|rescate|salv",
    "rival": r"compet|rival|guerra|enfrent|demand",
    "producto_fracasado": r"fracas|retir|discontinu|dej[oó] de|fall[oó]|no tuvo [eé]xito",
    "mascota": r"mascota|personaje|caricatura|dibujo",
    "slogan": r"eslogan|slogan|lema|publicidad|campa[nñ]a|anuncio|comercial",
}

CRITERIOS = ("marca_conocida", "dato_sorprendente", "giro", "humor")
PUNTAJE_MIN = 8.0
DIAS_SIN_REPETIR_MARCA = 7

PALABRAS_MIN, PALABRAS_MAX = 70, 108      # a ~2,3 palabras/s: 30-47 s (se piden 80-100)
FRASES_MIN, FRASES_MAX = 7, 12
GANCHO_MAX_PALABRAS = 16
MAX_S = 45.0

# Nunca humor sobre tragedias, muertes, accidentes ni temas sensibles (Santi). El modelo lo marca al
# elegir y, además, el guion no puede nombrarlos.
_SENSIBLE = re.compile(
    r"\b(muert\w*|muri[oóe]\w*|morir\w*|falleci\w*|mat[oó]|mataron|asesin\w*|suicid\w*|accident\w*|"
    r"tragedi\w*|tr[aá]gic\w*|v[ií]ctima\w*|cad[aá]ver\w*|nazi\w*|holocaust\w*|genocid\w*|esclav\w*|"
    r"c[aá]ncer\w*|enfermedad\w*|epidemi\w*|pandemi\w*|atentad\w*|terror\w*|secuestr\w*|abus\w*|"
    r"violaci[oó]n\w*|guerra mundial|guerra civil|dictadura\w*|bombarde\w*|masacre\w*|"
    r"incendio\w*|derrumb\w*|naufragi\w*|herid[oa]s?)\b", re.I)
_ARRANQUES_PROHIBIDOS = re.compile(r"^\s*(¿?\s*sab[ií]as|un d[ií]a como hoy|hoy te (cuento|voy)|"
                                   r"hola\b|bienvenid)", re.I)

# Escenas: lo que puede pedir el guion (la base de animación + los props genéricos de marcas).
FONDOS = ("cielo", "ciudad", "oficina", "globo", "fabrica", "tienda", "escenario")
PROPS = tuple(sorted(esc.PROPS)) + ("ninguno",)
GESTOS = tuple(per.GESTOS)
TRANSICIONES = ("corte", "fundido", "zoom", "barrido")
# Personajes secundarios por ROL, armados del elenco con cambios (nadie se parece a una persona
# real ni a una mascota oficial: son siempre los mismos muñecos del canal).
ROLES = {
    "ninguno": None,
    "fundador": ("abuelo", {}),
    "inventor": ("abuelo", {"anteojos": True, "ropa": P.BLANCO, "sombrero": "ninguno",
                            "peinado": "rulos"}),
    "empresario": ("narrador", {"ropa": P.GRIS_OSCURO, "anteojos": False, "bigote": True,
                                "sombrero": "galera", "color_sombrero": "#2b2b33"}),
    "rival": ("narrador", {"ropa": P.ROJO, "peinado": "corto", "bigote": True, "anteojos": False,
                           "pelo": P.PELO[3]}),
    "cliente": ("vecina", {}),
    "joven": ("pibe", {}),
    "publicista": ("vecina", {"ropa": P.VIOLETA, "anteojos": True, "peinado": "largo"}),
}
COLORES_PROP = (P.ROJO, P.AZUL, P.VERDE, P.NARANJA, P.VIOLETA, P.TURQUESA, P.AMARILLO, P.ROSA)


class SinCandidato(RuntimeError):
    """Ningún candidato de hoy llegó al puntaje (o no queda ninguno en la rotación): no sale video."""


class GuionInvalido(RuntimeError):
    pass


# ---- 1. catálogo ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Marca:
    nombre: str
    pais: str
    categoria: str
    wiki_es: str
    angulos: tuple[str, ...]
    wiki_en: str = ""


def cargar_catalogo(ruta: Path = CATALOGO) -> list[Marca]:
    datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8")) or {}
    out, vistos = [], set()
    for m in datos.get("marcas") or []:
        angulos = tuple(m.get("angulos") or ())
        malos = set(angulos) - set(ANGULOS)
        if malos:
            raise ValueError(f"{m.get('nombre')}: ángulos desconocidos {sorted(malos)}")
        if not m.get("nombre") or not m.get("wiki_es") or not angulos:
            raise ValueError(f"marca incompleta en {ruta}: {m}")
        if m["nombre"] in vistos:
            raise ValueError(f"marca repetida en {ruta}: {m['nombre']}")
        vistos.add(m["nombre"])
        out.append(Marca(str(m["nombre"]), str(m.get("pais") or ""), str(m.get("categoria") or ""),
                         str(m["wiki_es"]), angulos, str(m.get("wiki_en") or "")))
    return out


# ---- 2. rotación ------------------------------------------------------------------------------

TABLA = """
CREATE TABLE IF NOT EXISTS animacion_videos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dia       TEXT NOT NULL,            -- AAAA-MM-DD (AR) en que salió
    marca     TEXT NOT NULL,
    angulo    TEXT NOT NULL,
    puntaje   REAL,
    titulo    TEXT,
    video     TEXT,
    creado    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (marca, angulo)
);
"""


def _tabla(conn) -> None:
    conn.executescript(TABLA)


def usados(conn) -> set[tuple[str, str]]:
    """Los (marca, ángulo) que ya salieron: no se repiten NUNCA."""
    _tabla(conn)
    return {(m, a) for m, a in conn.execute("SELECT marca, angulo FROM animacion_videos")}


def marcas_recientes(conn, hoy: date, dias: int = DIAS_SIN_REPETIR_MARCA) -> set[str]:
    """Las marcas que salieron en los últimos `dias` días (hoy incluido): no vuelven esta semana."""
    _tabla(conn)
    desde = (hoy - timedelta(days=dias - 1)).isoformat()
    return {m for (m,) in conn.execute("SELECT marca FROM animacion_videos WHERE dia >= ?", (desde,))}


def disponibles(conn, catalogo: list[Marca], hoy: date,
                dias: int = DIAS_SIN_REPETIR_MARCA) -> list[tuple[Marca, str]]:
    ya, recientes = usados(conn), marcas_recientes(conn, hoy, dias)
    return [(m, a) for m in catalogo if m.nombre not in recientes for a in m.angulos
            if (m.nombre, a) not in ya]


def registrar(conn, marca: str, angulo: str, dia: date, puntaje: float = 0.0, titulo: str = "",
              video: str = "") -> None:
    _tabla(conn)
    conn.execute("INSERT OR REPLACE INTO animacion_videos (dia, marca, angulo, puntaje, titulo, video) "
                 "VALUES (?, ?, ?, ?, ?, ?)", (dia.isoformat(), marca, angulo, puntaje, titulo, video))
    conn.commit()


def candidatos(conn, catalogo: list[Marca], hoy: date, n: int = 8, azar=None,
               dias: int = DIAS_SIN_REPETIR_MARCA) -> list[tuple[Marca, str]]:
    """`n` candidatos que pasan la rotación, de marcas DISTINTAS. El ángulo de cada marca sale al azar
    con más peso para los que no son "origen" (casi todas lo tienen: así no son todos iguales)."""
    azar = azar or random.Random(hoy.toordinal())
    por_marca: dict[str, list[str]] = {}
    marcas = {}
    for m, a in disponibles(conn, catalogo, hoy, dias):
        por_marca.setdefault(m.nombre, []).append(a)
        marcas[m.nombre] = m
    nombres = list(por_marca)
    azar.shuffle(nombres)
    out = []
    for nombre in nombres[:n]:
        angs = por_marca[nombre]
        pesos = [1 if a == "origen" else 2 for a in angs]
        out.append((marcas[nombre], azar.choices(angs, pesos)[0]))
    return out


# ---- 3. textos de Wikipedia --------------------------------------------------------------------

def extracto(texto: str, angulo: str, base: int = 2500, extra: int = 3500) -> str:
    """El principio del artículo + los párrafos que hablan del ángulo (para elegir sin mandar el
    artículo entero)."""
    texto = texto or ""
    out = texto[:base]
    clave = re.compile(_CLAVES_ANGULO.get(angulo, "."), re.I)
    sumado = 0
    for par in texto[base:].split("\n"):
        if par.strip() and clave.search(par) and sumado < extra:
            out += "\n" + par[:900]
            sumado += min(len(par), 900)
    return out


def fuente_de(wiki, m: Marca) -> str:
    """El artículo en castellano y, si es corto, también el de inglés: de acá salen TODOS los datos."""
    partes = [wiki.texto("es", m.wiki_es)]
    if m.wiki_en:
        try:
            partes.append(wiki.texto("en", m.wiki_en))
        except Exception as e:   # el de inglés es un extra: sin él, sigue con el de castellano
            log.warning("no pude bajar %s (en): %s", m.wiki_en, e)
    return "\n\n".join(p for p in partes if p)


# ---- 4. elegir y puntuar -----------------------------------------------------------------------

SISTEMA_ELEGIR = """Elegís el tema del día para un canal de videos cortos animados (YouTube Shorts) sobre el
origen de marcas conocidas en Latinoamérica, contado con humor y sarcasmo, para un público joven
latinoamericano. Cada candidato es una marca + un ÁNGULO (origen, nombre, logo, casi quiebra, rival,
producto fracasado, mascota, slogan) + un pedazo de su artículo de Wikipedia.

Puntuá cada candidato de 1 a 10 en cuatro criterios:
- marca_conocida: ¿la conoce cualquier pibe de México, Colombia, Argentina, Perú o Chile? (10 =
  Coca-Cola, McDonald's, Nintendo; 3 = una marca local que conoce solo un país).
- dato_sorprendente: el dato del ÁNGULO que está EN EL TEXTO, ¿hace decir "no sabía"? Si el texto
  no tiene datos de ese ángulo, 1 (el guion solo puede usar lo que dice el texto).
- giro: ¿la historia tiene una vuelta inesperada (empezó vendiendo otra cosa, casi desaparece, el
  nombre era un error…)?
- humor: ¿se presta para un chiste sarcástico SIN burlarse de nadie que sufrió?
`dato`: en una frase, el dato del texto que usarías como gancho.
`sensible`: true si el ángulo pasa por muertes, accidentes, tragedias, guerras, enfermedades,
violencia, nazismo, esclavitud, abusos o cualquier tema con el que no se hace humor. Esos no van.
Sé exigente: un 8 es "esto lo comparto"."""

SCHEMA_ELEGIR = {
    "type": "OBJECT",
    "properties": {"candidatos": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"indice": {"type": "INTEGER"}, "dato": {"type": "STRING"},
                       **{c: {"type": "INTEGER"} for c in CRITERIOS},
                       "sensible": {"type": "BOOLEAN"}},
        "required": ["indice", "dato", *CRITERIOS, "sensible"]}}},
    "required": ["candidatos"],
}


@dataclass
class Elegido:
    marca: Marca
    angulo: str
    notas: dict
    dato: str = ""

    @property
    def promedio(self) -> float:
        return round(sum(self.notas[c] for c in CRITERIOS) / len(CRITERIOS), 2)


def elegir(cliente, cands: list[tuple[Marca, str, str]], minimo: float = PUNTAJE_MIN) -> list[Elegido]:
    """Los candidatos (marca, ángulo, extracto) puntuados por el modelo; quedan los de promedio ≥
    `minimo` que no son sensibles, de mejor a peor. Lista vacía = ninguno llega."""
    if not cands:
        return []
    bloques = [f"[{i}] {m.nombre} ({m.pais}, {m.categoria}) — ÁNGULO: {a} ({ANGULOS[a]})\n{t[:6000]}"
               for i, (m, a, t) in enumerate(cands)]
    d = json.loads(cliente.json(SISTEMA_ELEGIR, "\n\n---\n\n".join(bloques), SCHEMA_ELEGIR, 0.4))
    out = []
    for c in d.get("candidatos") or []:
        i = c.get("indice")
        if not isinstance(i, int) or not 0 <= i < len(cands) or c.get("sensible"):
            continue
        notas = {k: max(1, min(10, int(c.get(k) or 1))) for k in CRITERIOS}
        e = Elegido(cands[i][0], cands[i][1], notas, str(c.get("dato") or ""))
        if e.promedio >= minimo and all(x.marca.nombre != e.marca.nombre for x in out):
            out.append(e)
    return sorted(out, key=lambda e: -e.promedio)


# ---- 5. guion ------------------------------------------------------------------------------------

def _lista(xs) -> str:
    return ", ".join(xs)


SISTEMA_GUION = f"""Escribís la voz en off de un video vertical ANIMADO de 30 a 45 segundos (80 a 100
palabras en total) para un canal sobre el origen de las marcas. Castellano neutro latinoamericano con
algo de rioplatense, informal, tuteo. TONO: sarcasmo y humor, como alguien que cuenta un chisme
increíble. Un recurso que funciona: el engaño que se aclara enseguida ("La Starship estaba bajando y
explotó… na, mentira: la atraparon con la torre. ¡Momento histórico!").

ESTRUCTURA (obligatoria):
1. La PRIMERA frase es el GANCHO: lo más sorprendente del ángulo, sin rodeos, máximo
   {GANCHO_MAX_PALABRAS} palabras, sin año, sin "¿Sabías que…?", sin "Hoy te cuento", sin saludar.
2. Después, la historia paso a paso, clara para un chico de 15 años.
3. Un GIRO: la vuelta inesperada (`frase_giro`, el número de esa frase, desde 1).
4. El FINAL que PAGA el gancho: responde la pregunta que abrió la primera frase, en la última o la
   anteúltima frase (`frase_pago`). Puede cerrar con un remate sarcástico.
`pregunta_gancho`: la pregunta que deja abierta el gancho.

REGLAS DE DATOS: todo nombre, cifra, año, mes y lugar tiene que estar en el TEXTO que te paso (de
Wikipedia). Nada de tu memoria. Si un dato no está, no lo digas. Los chistes son comentarios, no
datos inventados: nada de personajes, nombres o cifras de fantasía.
NUNCA humor sobre muertes, accidentes, tragedias, guerras, enfermedades, violencia ni temas
sensibles: si la historia pasa por ahí, contá otra parte. No te burles de nadie por su origen,
cuerpo o país.
NADA de logos: si el ángulo es el logo, se CUENTA su historia; en pantalla nunca se dibuja.

ESCENAS: una por frase (cada frase es una escena). Para cada una:
- `fondo`: {_lista(FONDOS)}.
- `personaje`: un secundario al lado del narrador ({_lista(ROLES)}). El narrador está siempre y es
  el que habla.
- `gesto` (del narrador) y `gesto_personaje`: {_lista(GESTOS)}.
- `prop`: un objeto genérico dibujado ({_lista(PROPS)}). `texto_prop`: lo que dice su etiqueta o
  cartel, máximo 12 letras (puede ser el nombre de la marca en letra común, un año, "$"); vacío si
  no lleva.
- `texto_pantalla`: 1 a 4 palabras GRANDES en pantalla que remarcan la frase (un año, una cifra, la
  palabra clave, "NA, MENTIRA"); vacío si no hace falta (no en todas).
- `transicion` para entrar a esa escena: {_lista(TRANSICIONES)} ("corte" para el remate).
`gancho_pantalla`: el gancho escrito en la primera escena, máximo 7 palabras.
`titulo`: para YouTube, menos de 70 caracteres, con gancho y el nombre de la marca.
`descripcion`: 1 o 2 frases, sin hashtags ni links.
`tono` de la música: alegre, epico, misterioso, curioso o emotivo."""

SCHEMA_GUION = {
    "type": "OBJECT",
    "properties": {
        "titulo": {"type": "STRING"}, "descripcion": {"type": "STRING"},
        "tono": {"type": "STRING", "enum": ["alegre", "epico", "misterioso", "curioso", "emotivo"]},
        "pregunta_gancho": {"type": "STRING"}, "gancho_pantalla": {"type": "STRING"},
        "frase_giro": {"type": "INTEGER"}, "frase_pago": {"type": "INTEGER"},
        "escenas": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {
                "frase": {"type": "STRING"},
                "fondo": {"type": "STRING", "enum": list(FONDOS)},
                "personaje": {"type": "STRING", "enum": list(ROLES)},
                "gesto": {"type": "STRING", "enum": list(GESTOS)},
                "gesto_personaje": {"type": "STRING", "enum": list(GESTOS)},
                "prop": {"type": "STRING", "enum": list(PROPS)},
                "texto_prop": {"type": "STRING"},
                "texto_pantalla": {"type": "STRING"},
                "transicion": {"type": "STRING", "enum": list(TRANSICIONES)},
            },
            "required": ["frase", "fondo", "personaje", "gesto", "gesto_personaje", "prop",
                         "texto_prop", "texto_pantalla", "transicion"]}},
    },
    "required": ["titulo", "descripcion", "tono", "pregunta_gancho", "gancho_pantalla",
                 "frase_giro", "frase_pago", "escenas"],
}


def frases_de(d: dict) -> list[str]:
    return [str(e.get("frase") or "").strip() for e in d.get("escenas") or []]


def textos_en_pantalla(d: dict) -> list[str]:
    out = [str(d.get("gancho_pantalla") or "")]
    for e in d.get("escenas") or []:
        out += [str(e.get("texto_pantalla") or ""), str(e.get("texto_prop") or "")]
    return [t for t in out if t.strip()]


def _sin_mayusculas(t: str) -> str:
    """"NA, MENTIRA" → "Na, mentira": el chequeo de nombres propios mira las mayúsculas en medio de
    la oración, y un texto de pantalla va todo en mayúsculas (cada palabra sería un "nombre"). Las
    cifras se siguen chequeando; los nombres de pantalla salen de las frases, que sí se chequean."""
    if not any(c.islower() for c in t):
        t = t.lower()
    return t[:1].upper() + t[1:]


def validar_guion(d: dict, m: Marca, fuente: str) -> list[str]:
    """Los errores del guion (vacío = sirve). Los datos, contra el artículo, como Pequeña Historia."""
    from clips_bot.efemerides import no_respaldados

    errores = []
    escenas = d.get("escenas") or []
    frases = frases_de(d)
    n = len(frases)
    if not FRASES_MIN <= n <= FRASES_MAX:
        errores.append(f"van {FRASES_MIN} a {FRASES_MAX} frases (escenas), hay {n}")
    if any(not f for f in frases):
        errores.append("hay una escena sin frase")
    palabras = sum(len(f.split()) for f in frases)
    if not PALABRAS_MIN <= palabras <= PALABRAS_MAX:
        errores.append(f"el guion tiene {palabras} palabras: tienen que ser entre 80 y 100 "
                       f"({'sobran' if palabras > PALABRAS_MAX else 'faltan'} "
                       f"{abs(palabras - (PALABRAS_MAX if palabras > PALABRAS_MAX else PALABRAS_MIN))})")
    if frases:
        g = frases[0]
        if len(g.split()) > GANCHO_MAX_PALABRAS:
            errores.append(f"el gancho (primera frase) tiene {len(g.split())} palabras: máximo "
                           f"{GANCHO_MAX_PALABRAS}")
        if re.search(r"\b1[5-9]\d\d\b|\b20\d\d\b", g):
            errores.append("el gancho no lleva año: el año va después")
        if _ARRANQUES_PROHIBIDOS.search(g):
            errores.append("el gancho arranca con una fórmula gastada (¿Sabías…?, Hoy te cuento…, hola): "
                           "arrancá con el dato")
    if not str(d.get("pregunta_gancho") or "").strip():
        errores.append("falta `pregunta_gancho`")
    giro, pago = d.get("frase_giro"), d.get("frase_pago")
    if not isinstance(giro, int) or not isinstance(pago, int):
        errores.append("faltan `frase_giro` y `frase_pago` (el número de cada frase, desde 1)")
    elif n:
        if not 2 <= giro < pago:
            errores.append(f"el giro (frase {giro}) va después del gancho y antes del final que paga ({pago})")
        if pago < n - 1 or pago > n:
            errores.append(f"el final que paga el gancho va en la última o la anteúltima frase (está en la {pago})")
    gp = str(d.get("gancho_pantalla") or "")
    if not gp.strip() or len(gp.split()) > 7:
        errores.append("`gancho_pantalla`: de 1 a 7 palabras")
    for i, e in enumerate(escenas, 1):
        if len(str(e.get("texto_pantalla") or "").split()) > 4:
            errores.append(f"escena {i}: `texto_pantalla` de 4 palabras como mucho")
        if len(str(e.get("texto_prop") or "")) > 12:
            errores.append(f"escena {i}: `texto_prop` de 12 letras como mucho")
        if e.get("fondo") not in FONDOS:
            errores.append(f"escena {i}: fondo {e.get('fondo')!r} no existe")
        if e.get("prop") not in PROPS:
            errores.append(f"escena {i}: prop {e.get('prop')!r} no existe")
        if e.get("personaje") not in ROLES:
            errores.append(f"escena {i}: personaje {e.get('personaje')!r} no existe")
        for k in ("gesto", "gesto_personaje"):
            if e.get(k) not in GESTOS:
                errores.append(f"escena {i}: {k} {e.get(k)!r} no existe")
    titulo = str(d.get("titulo") or "")
    if not titulo.strip() or len(titulo) > 70:
        errores.append("`titulo`: entre 1 y 70 caracteres")
    todo = " ".join(frases + [titulo, str(d.get("descripcion") or "")] + textos_en_pantalla(d))
    sens = sorted({x.group(0).lower() for x in _SENSIBLE.finditer(todo)})
    if sens:
        errores.append(f"nada de temas sensibles (aparece: {', '.join(sens)}): contá otra parte de la historia")
    base = f"{fuente}\n{m.nombre} {m.pais}"
    texto = " ".join(frases + [titulo] + [_sin_mayusculas(t) + "." for t in textos_en_pantalla(d)])
    faltan = no_respaldados(texto, base)
    if faltan:
        errores.append("esto no está en el artículo de Wikipedia (sacalo o usá lo que dice el texto): "
                       + ", ".join(faltan[:12]))
    return errores


def escribir_guion(cliente, e: Elegido, fuente: str, reintentos: int = 3, avisar=log.info) -> dict:
    """El guion validado (dict del schema). Si no valida, reintenta con los errores; si nunca valida,
    GuionInvalido."""
    pedido = (f"MARCA: {e.marca.nombre} ({e.marca.pais})\nÁNGULO: {e.angulo} — {ANGULOS[e.angulo]}\n"
              f"Dato para el gancho (sugerido): {e.dato}\n\nTEXTO (Wikipedia; los datos salen SOLO de "
              f"acá):\n{fuente[:20000]}")
    correccion, ultimo = "", []
    for intento in range(reintentos):
        d = json.loads(cliente.json(SISTEMA_GUION, pedido + correccion, SCHEMA_GUION, 0.9))
        ultimo = validar_guion(d, e.marca, fuente)
        if not ultimo:
            return d
        avisar(f"guion de {e.marca.nombre} ({e.angulo}), intento {intento + 1}: {'; '.join(ultimo)[:300]}")
        correccion = ("\n\nTU GUION ANTERIOR:\n" + "\n".join(frases_de(d)) +
                      "\n\nNO SIRVIÓ POR ESTO (corregilo y devolvé el guion entero):\n- " + "\n- ".join(ultimo))
    raise GuionInvalido(f"{e.marca.nombre} ({e.angulo}): {'; '.join(ultimo)[:400]}")


def hashtags(m: Marca) -> list[str]:
    limpio = re.sub(r"[^\w]", "", m.nombre.replace("&", "y"))
    return ["#Shorts", "#marcas", f"#{limpio}"] if limpio else ["#Shorts", "#marcas"]


# ---- 6. escenas → línea de tiempo ------------------------------------------------------------

def cortes(inicios: list[float], fin: float, cola_s: float = 0.8) -> list[float]:
    """La duración de cada escena: de un poquito antes de su frase a un poquito antes de la
    siguiente (la imagen cambia justo antes de que se diga), la última hasta `fin` + `cola_s`."""
    arranques = [0.0] + [max(0.0, t - 0.12) for t in inicios[1:]]
    finales = arranques[1:] + [fin + cola_s]
    return [round(max(0.4, b - a), 3) for a, b in zip(arranques, finales)]


def escena(e: dict, i: int, dur: float, primera: bool, gancho_pantalla: str) -> dict:
    """Una escena del guion → el dict de `timeline.Escena`."""
    rol = ROLES.get(e.get("personaje") or "ninguno")
    prop = e.get("prop") if e.get("prop") in esc.PROPS else None
    hay_lado = rol is not None or prop is not None
    gesto = e.get("gesto") if e.get("gesto") in per.GESTOS else "explicar"
    otro = "senalar" if gesto == "explicar" else "explicar"
    narrador = {"tipo": "personaje", "nombre": "narrador", "x": 290 if hay_lado else 540,
                "y": 1800, "escala": 0.95 if hay_lado else 1.1, "habla": True,
                "gestos": [{"t": 0, "gesto": gesto}, {"t": round(dur * 0.6, 2), "gesto": otro}]}
    if primera:
        narrador["entrada"] = "abajo"
    elementos = [narrador]
    if rol is not None:
        nombre, cambios = rol
        elementos.append({"tipo": "personaje", "nombre": nombre, "cambios": cambios, "x": 820,
                          "y": 1820, "escala": 0.85, "entrada": "derecha", "desde": 0.15,
                          "keyframes": [{"t": 0, "mirada": -1}],
                          "gestos": [{"t": 0.5, "gesto": e.get("gesto_personaje") or "reposo"}]})
        narrador["keyframes"] = [{"t": 0, "mirada": 1}]
    if prop is not None:
        x, y, s = (760, 900, 1.0) if rol is not None else (770, 1040, 1.25)
        el = {"tipo": "prop", "nombre": prop, "x": x, "y": y, "escala": s, "entrada": "rebote",
              "desde": 0.3, "color": COLORES_PROP[i % len(COLORES_PROP)],
              "keyframes": [{"t": 0.9, "rotacion": 0}, {"t": 0.9 + dur * 0.4, "rotacion": 5},
                            {"t": 0.9 + dur * 0.8, "rotacion": -4}]}
        if str(e.get("texto_prop") or "").strip():
            el["texto"] = str(e["texto_prop"]).strip()[:12]
        elementos.append(el)
    texto = gancho_pantalla if primera else str(e.get("texto_pantalla") or "").strip()
    if texto:
        elementos.append({"tipo": "gancho", "texto": texto, "y": 380 if primera else 400,
                          "modo": "palabras" if primera else "rebote", "tam": 96 if primera else 110,
                          "desde": 0.0 if primera else 0.25})
    tr = e.get("transicion") if e.get("transicion") in TRANSICIONES else "fundido"
    z0, z1 = (1.0, 1.07) if i % 2 == 0 else (1.07, 1.0)
    fondo = e.get("fondo") if e.get("fondo") in esc.FONDOS else "ciudad"
    return {"duracion": dur, "fondo": {"tipo": fondo, "semilla": i + 1},
            "transicion": {"tipo": "corte" if primera else tr, "duracion": 0.4},
            "camara": [{"t": 0, "zoom": z0}, {"t": dur, "zoom": z1, "easing": "suave"}],
            "elementos": elementos}


def linea_de_tiempo(d: dict, inicios: list[float], fin: float, palabras: list, voz: Path | None) -> dict:
    """El guion + los tiempos reales de la voz → el dict de `timeline.Video`."""
    escenas_d = d.get("escenas") or []
    durs = cortes(inicios, fin)
    out = {"fps": P.FPS,
           "escenas": [escena(e, i, dur, i == 0, str(d.get("gancho_pantalla") or ""))
                       for i, (e, dur) in enumerate(zip(escenas_d, durs))]}
    if voz is not None:
        out["audio"] = str(voz)
    if palabras:
        out["subtitulos"] = [{"palabras": [{"texto": p.texto, "inicio": round(p.inicio, 3),
                                            "fin": round(p.fin, 3)} for p in palabras]}]
    return out


# ---- 7. el video entero -----------------------------------------------------------------------

@dataclass
class Resultado:
    marca: str
    angulo: str
    notas: dict
    promedio: float
    titulo: str
    descripcion: str
    hashtags: list[str]
    frases: list[str]
    video: str
    duracion_s: float
    motor_voz: str
    musica: str = ""
    credito_musica: str = ""
    articulo: str = ""
    render_s: float = 0.0
    total_s: float = 0.0
    costo_usd: float = 0.0
    tiempos: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        return asdict(self)


def costo_desde(conn, fila: int) -> float:
    """US$ de Claude anotados en gemini_uso después de la fila `fila` (lo de ESTE video)."""
    from clips_bot import claude

    return round(sum(claude.costo(mod, e or 0, s or 0) for mod, e, s in conn.execute(
        "SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND rowid > ?", (fila,))), 4)


def ultima_fila_uso(conn) -> int:
    try:
        return int(conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM gemini_uso").fetchone()[0])
    except Exception:
        return 0


def proponer(conn, cliente, wiki, hoy: date, catalogo: list[Marca] | None = None, n: int = 8,
             minimo: float = PUNTAJE_MIN, max_intentos: int = 3, avisar=log.info) -> tuple[Elegido, dict, str]:
    """(elegido, guion validado, fuente). SinCandidato si ninguno llega al puntaje o ningún guion valida."""
    catalogo = catalogo if catalogo is not None else cargar_catalogo()
    cands = candidatos(conn, catalogo, hoy, n)
    if not cands:
        raise SinCandidato("no queda ninguna marca/ángulo que pase la rotación")
    textos = []
    for m, a in cands:
        try:
            textos.append((m, a, extracto(wiki.texto("es", m.wiki_es), a)))
        except Exception as e:
            avisar(f"no pude leer el artículo de {m.nombre}: {str(e)[:120]}")
    elegidos = elegir(cliente, textos, minimo)
    avisar("candidatos: " + ", ".join(f"{m.nombre}/{a}" for m, a, _ in textos) +
           f" → pasan {len(elegidos)}: " + ", ".join(f"{e.marca.nombre}/{e.angulo} {e.promedio}" for e in elegidos))
    if not elegidos:
        raise SinCandidato(f"ninguno de los {len(textos)} candidatos de hoy llegó a {minimo:g} de promedio")
    errores = []
    for e in elegidos[:max_intentos]:
        fuente = fuente_de(wiki, e.marca)
        try:
            return e, escribir_guion(cliente, e, fuente, avisar=avisar), fuente
        except GuionInvalido as err:
            errores.append(str(err))
    raise SinCandidato("ningún guion pasó la validación: " + " | ".join(errores)[:600])


def armar_video(conn, settings, carpeta: Path, cliente=None, wiki=None, hoy: date | None = None,
                avisar=log.info, procesos: int = 2, catalogo: list[Marca] | None = None,
                elegido: tuple | None = None) -> Resultado:
    """De punta a punta: elegir → guion → voz → Whisper → animación → mp4. No sube nada a ningún lado."""
    from clips_bot import claude, musica, narrar
    from clips_bot import efemerides as ef
    from clips_bot.config import ROOT

    from . import render as rd
    from .timeline import Video

    hoy = hoy or date.today()
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    cfg = settings.animacion
    t_total = time.time()
    tiempos = {}
    fila0 = ultima_fila_uso(conn)
    cliente = cliente or claude.cliente(cfg.modelo_texto)
    if cliente is None:
        raise SinCandidato("sin ANTHROPIC_API_KEY: el texto de este canal va con Claude")
    wiki = wiki or ef.Wiki()
    t0 = time.time()
    e, d, fuente = elegido or proponer(conn, cliente, wiki, hoy, catalogo, cfg.candidatos,
                                       cfg.puntaje_min, cfg.max_intentos, avisar)
    tiempos["guion_s"] = round(time.time() - t0, 1)
    (carpeta / "guion.json").write_text(json.dumps({"marca": e.marca.nombre, "angulo": e.angulo,
                                                    "notas": e.notas, "guion": d}, ensure_ascii=False,
                                                   indent=1), encoding="utf-8")
    frases = frases_de(d)
    # Voz: la misma cadena que Pequeña Historia (ElevenLabs si está, Gemini TTS, Piper de respaldo).
    t0 = time.time()
    wav, duraciones, motor = ef.voz_efemeride(frases, settings, carpeta, avisar)
    ef.ajustar_duracion(wav, duraciones, MAX_S, settings.efemerides.tts_acelerar_max, avisar)
    narrar.sacar_silencio_inicial(wav)
    fin = narrar.duracion_wav(wav)
    tiempos["voz_s"] = round(time.time() - t0, 1)
    t0 = time.time()
    oidas = narrar.palabras_de_voz(wav, settings.subtitulos)
    oidas, recortado = narrar.recortar_inicio(wav, oidas, frases)
    if recortado:
        fin = narrar.duracion_wav(wav)
    palabras, inicios = narrar.alinear_a_guion(oidas, frases, fin)
    tiempos["whisper_s"] = round(time.time() - t0, 1)
    avisar(f"voz ({motor}): {fin:.1f} s")
    # Música baja, con ducking (musica.mezclar). La boca sigue la voz SOLA (la envolvente sale de
    # la voz; el audio del mp4 es la mezcla).
    tema = None
    if cfg.musica:
        carpeta_musica = ROOT / settings.efemerides.carpeta_musica
        tema = musica.elegir(musica.cargar(carpeta_musica), str(d.get("tono") or "curioso"),
                             musica.recientes(conn), musica.vetados(conn))
    audio = (musica.mezclar(wav, ROOT / settings.efemerides.carpeta_musica / tema.ruta,
                            carpeta / "voz_musica.wav", cfg.musica_volumen) if tema else wav)
    if tema:
        musica.anotar_uso(conn, tema.ruta)   # así no sale siempre el mismo tema (en los 2 ejemplos se repitió)
    datos = linea_de_tiempo(d, inicios, fin, palabras, wav)
    (carpeta / "linea_de_tiempo.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
    video = Video.desde_dict(datos)
    video.audio = str(audio)
    salida = carpeta / f"marca_{re.sub(r'[^a-z0-9]+', '_', e.marca.nombre.lower())}_{e.angulo}.mp4"
    t0 = time.time()
    r = rd.renderizar(video, salida, "auto", procesos, crf=22, preset="medium",
                      hilos_x264=rd.hilos_x264_defecto())
    tiempos["render_s"] = round(time.time() - t0, 1)
    avisar(r.resumen())
    return Resultado(
        marca=e.marca.nombre, angulo=e.angulo, notas=e.notas, promedio=e.promedio,
        titulo=str(d.get("titulo") or ""), descripcion=str(d.get("descripcion") or ""),
        hashtags=hashtags(e.marca), frases=frases, video=str(salida), duracion_s=round(video.duracion, 1),
        motor_voz=motor, musica=tema.ruta if tema else "", credito_musica=tema.credito() if tema else "",
        articulo=f"https://es.wikipedia.org/wiki/{e.marca.wiki_es.replace(' ', '_')}",
        render_s=tiempos["render_s"], total_s=round(time.time() - t_total, 1),
        costo_usd=costo_desde(conn, fila0), tiempos=tiempos)


# ---- 8. a Telegram (sin subir a ningún lado) -----------------------------------------------------

NOMBRES_CRITERIOS = {"marca_conocida": "marca conocida", "dato_sorprendente": "dato sorprendente",
                     "giro": "giro", "humor": "humor"}


def texto_mensaje(r: Resultado, encabezado: str = "") -> str:
    import html

    notas = " · ".join(f"{NOMBRES_CRITERIOS[c]} {r.notas[c]}" for c in CRITERIOS)
    partes = [encabezado] if encabezado else []
    partes += [
        f"🎨 <b>Marcas animadas</b> · <b>{html.escape(r.marca)}</b> · ángulo: {html.escape(r.angulo.replace('_', ' '))}",
        f"⭐ Puntaje {r.promedio:g} ({notas})",
        f"⏱ {r.duracion_s:.0f} s · render {r.render_s:.0f} s · Claude US$ {r.costo_usd:.3f} · "
        f"{html.escape(r.motor_voz)}",
        "",
        f"<b>Título:</b>\n<code>{html.escape(r.titulo)}</code>",
        f"<b>Descripción:</b>\n<code>{html.escape(r.descripcion)}\n\n{' '.join(r.hashtags)}\n\n"
        f"Fuente: {html.escape(r.articulo)}"
        + (f"\nMúsica: {html.escape(r.credito_musica)}" if r.credito_musica else "") + "</code>",
        "",
        "📵 No se sube a ningún lado: el canal de YouTube todavía no está conectado.",
    ]
    return "\n".join(partes)


def enviar(tg, chats, r: Resultado, encabezado: str = "") -> int:
    """El mp4 (con ancho, alto y duración: si no, Telegram lo muestra angosto) + el mensaje."""
    from clips_bot.media import miniatura, probe
    from clips_bot.telegram import partir_html

    video = Path(r.video)
    info = probe(video)
    thumb = miniatura(video, video.with_suffix(".thumb.jpg"), 1.0)
    llegaron, file_id = 0, None
    plano = re.sub(r"<[^>]+>", "", encabezado)
    caption = (f"{plano} · " if plano else "") + f"{r.marca} · {r.titulo}"
    for chat in ([chats] if isinstance(chats, (str, int)) else list(chats)):
        enviado = tg.send_video(chat, video, caption[:1024], width=info.ancho, height=info.alto,
                                duration=round(info.duracion), thumbnail=thumb, file_id=file_id)
        file_id = file_id or (enviado or {}).get("video", {}).get("file_id")
        for parte in partir_html(texto_mensaje(r, encabezado)):
            tg.send_message(chat, parte)
        llegaron += 1
    return llegaron


# ---- CLI --------------------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse

    from clips_bot import db
    from clips_bot.config import DB_PATH, DATA_DIR, env, load_settings

    ap = argparse.ArgumentParser(description="Un video del canal de marcas animadas (no sube nada).")
    ap.add_argument("--dia", default="", help="AAAA-MM-DD (por defecto hoy)")
    ap.add_argument("--enviar", default="", help="chat de Telegram al que mandarlo (vacío = no se manda)")
    ap.add_argument("--sin-registrar", action="store_true", help="no anotarlo en la rotación")
    ap.add_argument("--procesos", type=int, default=2)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    hoy = date.fromisoformat(a.dia) if a.dia else date.today()
    settings = load_settings()
    conn = db.connect(DB_PATH)
    r = armar_video(conn, settings, DATA_DIR.parent / "output" / "animacion" / hoy.strftime("%m%d"),
                    hoy=hoy, avisar=print, procesos=a.procesos)
    print(json.dumps(r.a_dict(), ensure_ascii=False, indent=1))
    if a.enviar:
        from clips_bot.telegram import TelegramClient

        enviar(TelegramClient(env("TELEGRAM_BOT_TOKEN")), a.enviar, r)
    if not a.sin_registrar:
        registrar(conn, r.marca, r.angulo, hoy, r.promedio, r.titulo, r.video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
