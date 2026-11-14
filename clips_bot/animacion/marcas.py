"""Canal de animación: el origen de las marcas, con humor y sarcasmo (Santi, 2026-11-14).

Un video por día, dibujado por código (sin IA generativa de imagen y SIN logos: el nombre de la
marca, como mucho, escrito en la fuente común del canal):

  1. catálogo (`marcas.yaml`, 457 marcas verificadas contra Wikipedia) y ROTACIÓN: un ángulo de una
     marca no se repite nunca, y una marca no sale dos veces en 7 días (tabla `animacion_videos`);
  2. candidatos que pasan la rotación (uno por marca) + un pedazo de su artículo de Wikipedia;
  3. Sonnet elige y puntúa (marca conocida, dato sorprendente, giro, humor: 1-10 cada uno); pasan
     los de promedio ≥ 8 que no tocan nada sensible. Si ninguno llega, ese día no sale y se avisa;
  4. Sonnet escribe el guion (gancho de acción → problema → idea → qué pasó → final sorpresa, con
     sarcasmo), la ESCENA DE ACCIÓN de cada frase y 1-3 pausas de la mascota-locutor; se valida como en Pequeña Historia (nombres, cifras y meses tienen que
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

from . import acciones as ac
from . import escenas as esc
from . import paleta as P

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

PALABRAS_MIN, PALABRAS_MAX = 68, 98      # frases + locutor: con la voz ×1,065 y pausas cortas, 32-38 s
FRASES_MIN, FRASES_MAX = 7, 12
GANCHO_MAX_PALABRAS = 8                   # el gancho dura menos de 3 s
MAX_S = 38.0            # Santi (2026-11-14): 32-38 s; fuera de eso se REESCRIBE el guion (nunca más aceleración)
MIN_S = 32.0
VELOCIDAD_VOZ = 1.065   # atempo (sin cambiar el tono): ×1,13 quedó "un pelín rápido" (Santi, 2026-11-14)
PAUSA_MAX_S = 0.22      # el silencio entre frases, como mucho

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

# Escenas: lo que puede pedir el guion (la base de animación + lo del canal de marcas).
FONDOS = ("casa", "taller", "fabrica", "tienda", "oficina", "ciudad", "escenario", "cielo", "globo")
# mesa y estante no son objetos de la historia: son el APOYO (`soporte`) y el render los pone contra la pared
PROPS = tuple(sorted(n for n in esc.PROPS if n not in ("pedazo", "microfono", "mesa", "estante")))
TRANSICIONES = ("corte", "fundido", "zoom", "barrido")


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
# Santi, 2026-11-14, viendo Nerf y Monopoly ("muy básicos y aburridos: dos personajes hablando no
# engancha"). REGLAS para todos los videos del canal: (1) mostrar, no contar: cada frase es una escena
# con acción; (2) la mascota-locutor aparece 1-3 veces, la escena se congela en gris y comenta; (3)
# guion claro: toda empresa o persona se presenta en pocas palabras la primera vez, y en orden
# problema → idea → qué pasó → final sorpresa; (4) movimiento: personajes que caminan, corren,
# saltan; objetos que vuelan o se rompen; cámara y efectos de sonido.

def _lista(xs) -> str:
    return ", ".join(xs)


PARTES = ("gancho", "problema", "idea", "que_paso", "giro", "final")
# el orden que se exige: el giro va dentro de "qué pasó" (puede haber qué pasó después del giro)
RANGO_PARTE = {"gancho": 0, "problema": 1, "idea": 2, "que_paso": 3, "giro": 3, "final": 4}
# El objeto PROTAGONISTA de la historia (Santi, 2026-11-14: "el juego de mesa es una caja con la
# palabra 'Juego'; queda pobre"): se dibuja con detalle y se entiende SIN leer. Nada de rótulos.
DETALLADOS = {"pelota_espuma", "juego_mesa", "hamburguesa", "chocolate", "galletitas", "auto", "telefono_disco",
              "radio", "consola", "tele", "botella", "lata", "zapatilla", "control", "celular", "lampara",
              "cohete", "camion", "reloj_bolsillo", "megafono", "trofeo", "pelota", "jarron", "moneda", "billete"}
ROTULOS = {"caja", "cartel", "calendario"}
# Lo que se puede romper en la cadena del gancho (cosas de una casa, una oficina o un negocio).
ROMPIBLES = {"tele", "lampara", "cuadro", "jarron", "ventana", "botella", "lata", "caja", "trofeo", "celular"}
CADENA_MIN, CADENA_MAX = 2, 4
_PRESENTE = re.compile(r"\b(hoy|actualmente|en la actualidad|hoy en d[ií]a|ahora)\b", re.I)
LOCUTOR_MIN, LOCUTOR_MAX = 1, 3

SISTEMA_GUION = f"""Escribís un video vertical ANIMADO de 32 a 38 segundos (ritmo ágil) para un canal sobre el origen de las
marcas. Castellano neutro latinoamericano con algo de rioplatense, informal, tuteo. TONO: sarcasmo y humor.

El canal se llama "Así Nació". Su locutor y mascota es el ABUELO TITO: un inventor jubilado con
antiparras de soldador, bigote blanco y un reloj de bolsillo dorado con el que viaja en el tiempo.

REGLA 1 — MOSTRAR, NO CONTAR. Cada frase de la voz en off es UNA escena donde PASA algo que muestra lo
que dice la frase: personajes que caminan, corren, saltan, se caen, retan, martillan, tiran cosas;
objetos que rebotan, vuelan, caen y se rompen. NADA de personajes parados hablando. La voz en off
cuenta y la escena lo muestra.
Ejemplo (Nerf): GANCHO = un nene tira una pelota adentro de su casa: rompe la tele, rebota, tira la
lámpara y se cae un cuadro (efecto dominó) mientras la mamá lo reta. Después: el inventor pensando la
solución (lamparita), martillando en su taller la pelota de espuma, y los chicos jugando adentro sin
romper nada.

REGLA 2 — TITO, EL LOCUTOR. Tito interrumpe 1 a 3 veces: la escena se congela en gris, él aparece al
costado y comenta algo con humor o aclara un dato (`locutor`: después de qué frase y su texto, 5 a 20
palabras). Es la misma voz que narra. No después de la última frase.

REGLA 3 — GUION CLARO. No des nada por sabido: TODA empresa o persona se presenta en pocas palabras la
PRIMERA vez que aparece ("Parker Brothers, la fábrica de juegos de mesa más grande de la época,…";
"Reyn Guyer, un inventor de juegos de Minnesota,…"). Listalas en `entidades` con su presentación (las
mismas palabras que dice la frase) y la frase donde aparecen por primera vez. Contá en orden, con causa
y efecto: problema → idea → qué pasó → final sorpresa (cada frase dice su `parte`: {_lista(PARTES)}).

REGLA 4 — ESCENAS CON SENTIDO. Cada objeto está donde estaría en la vida real (`soporte`): la lámpara
de pie en el piso al lado del sillón, la tele sobre una mesa, el cuadro y la ventana en la pared, un
jarrón en un estante, una botella sobre la mesa. NADA aparece de la nada ni cae del cielo: lo que cae,
cae de su mesa o su estante; "aparece" y "crece" solo para íconos (pregunta, exclamación, lamparita de
idea, gráfico, cartel, calendario); "llueve" solo billetes o monedas.

REGLA 5 — DESTRUCCIÓN EN CADENA EN EL GANCHO. La escena 1 tiene una `cadena` de 2 a 4 cosas que se
rompen o se caen una detrás de otra (tele → lámpara → cuadro), cada una en su lugar; exagerado y
gracioso, pero que se entienda cada golpe. Un actor que "tira" la empieza.

REGLA 6 — VIAJE EN EL TIEMPO. Cada vez que la historia va a otra época (ej. 1969), en ESA frase (o
antes) marcá `viaje_a_anio` con el año: Tito levanta el reloj, la escena gira en remolino, el año
cuenta hacia atrás y todo pasa a tono antiguo hasta que la historia vuelve al presente
(`vuelve_al_presente` en la frase que habla de hoy). El gancho es en el presente (sin viaje). El año
tiene que estar en el TEXTO.

REGLA 7 — OBJETOS LLAMATIVOS. El objeto de la historia (el producto de la marca o lo que la historia
necesita) es el `protagonista`: elegí el prop que lo DIBUJA ({_lista(sorted(DETALLADOS))}) y decí qué es
(`que_es`). Tiene que aparecer en al menos 2 escenas (en `objetos`, o como lo que se tira en la
cadena). NADA de una caja o un cartel con un rótulo ("Juego") en lugar del objeto: si no hay prop
para algo, elegí otro que se entienda sin leer.

REGLA 8 — MOVIMIENTO Y LUGARES. Los personajes reaccionan con el cuerpo (caminan, corren, saltan,
festejan, se asustan) y la cara (`cara`). Nunca dos en el mismo lugar: si hay 2 o 3, cada uno en su
`desde` (izquierda, centro, derecha) y sin cruzarse. Variá los lugares (casa, taller, fábrica,
oficina, ciudad, tienda); el render decora cada lugar según la época del viaje en el tiempo.

ESTRUCTURA:
- La PRIMERA frase es el GANCHO: lo más sorprendente o divertido, máximo 8 palabras (dura menos de 3 s),
  sin año, sin "¿Sabías que…?", sin saludar. Su escena es pura ACCIÓN.
- El final paga el gancho (responde la pregunta que dejó abierta: `pregunta_gancho`).
- 7 a 11 frases cortas, 55 a 75 palabras en total en las frases; Tito suma 12 a 25 más (todo junto,
  70 a 95). Frases cortas y con ritmo: el video dura 32 a 38 segundos.

DATOS: todo nombre, cifra, año, mes y lugar sale del TEXTO (Wikipedia). Nada de tu memoria. Los chistes
son comentarios, no datos inventados. NUNCA humor sobre muertes, accidentes, tragedias, guerras,
enfermedades ni temas sensibles. NADA de logos: el nombre de la marca puede aparecer como texto común.

ESCENA de cada frase:
- `fondo`: {_lista(FONDOS)}.
- `actores` (1 a 3): `rol` ({_lista(ac.ROLES)}), `accion` ({_lista(ac.ACCIONES)}), `desde` y `hacia`
  (izquierda, centro, derecha, afuera_izq, afuera_der; `hacia` "ninguno" si no se mueve de lugar) y
  `cara` ({_lista(ac.CARAS)}).
- `objetos` (0 a 3): `prop` ({_lista(PROPS)}), `efecto` ({_lista(ac.EFECTOS)}), `donde` (izquierda,
  centro, derecha), `soporte` ({_lista(ac.SOPORTES)}) y `texto` (etiqueta, máx. 12 letras, o vacío).
  Un "tirar" + un objeto que "vuela" o "rebota" sale de la mano; si además hay uno que "se_rompe",
  lo que vuela le pega y lo rompe.
- `cadena` (solo en el gancho, 2 a 4; vacía en las demás): las cosas que se rompen una tras otra, cada
  una con `prop`, `soporte` y `donde`.
- `viaje_a_anio` (0 si no) y `vuelve_al_presente` (true/false).
- `camara`: {_lista(ac.CAMARAS)} (en los golpes la cámara se sacude sola).
- `texto_pantalla`: 1 a 4 palabras grandes (un año, una cifra, "NA, MENTIRA") o vacío.
- `transicion`: {_lista(TRANSICIONES)}.
`titulo` (< 70 caracteres, con la marca), `descripcion` (1-2 frases, sin hashtags), `tono` de la música."""

_ACTOR = {"type": "OBJECT", "properties": {
    "rol": {"type": "STRING", "enum": list(ac.ROLES)},
    "accion": {"type": "STRING", "enum": list(ac.ACCIONES)},
    "desde": {"type": "STRING", "enum": list(ac.POS)},
    "hacia": {"type": "STRING", "enum": list(ac.POS) + ["ninguno"]},
    "cara": {"type": "STRING", "enum": list(ac.CARAS)}},
    "required": ["rol", "accion", "desde", "hacia", "cara"]}
_OBJETO = {"type": "OBJECT", "properties": {
    "prop": {"type": "STRING", "enum": list(PROPS)},
    "efecto": {"type": "STRING", "enum": list(ac.EFECTOS)},
    "donde": {"type": "STRING", "enum": list(ac.LADOS)},
    "soporte": {"type": "STRING", "enum": list(ac.SOPORTES)},
    "texto": {"type": "STRING"}},
    "required": ["prop", "efecto", "donde", "soporte", "texto"]}
_CADENA = {"type": "OBJECT", "properties": {
    "prop": {"type": "STRING", "enum": sorted(ROMPIBLES)},
    "soporte": {"type": "STRING", "enum": list(ac.SOPORTES)},
    "donde": {"type": "STRING", "enum": list(ac.LADOS)}},
    "required": ["prop", "soporte", "donde"]}
SCHEMA_GUION = {
    "type": "OBJECT",
    "properties": {
        "titulo": {"type": "STRING"}, "descripcion": {"type": "STRING"},
        "tono": {"type": "STRING", "enum": ["alegre", "epico", "misterioso", "curioso", "emotivo"]},
        "pregunta_gancho": {"type": "STRING"},
        "escenas": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {
                "frase": {"type": "STRING"},
                "parte": {"type": "STRING", "enum": list(PARTES)},
                "fondo": {"type": "STRING", "enum": list(FONDOS)},
                "actores": {"type": "ARRAY", "items": _ACTOR},
                "objetos": {"type": "ARRAY", "items": _OBJETO},
                "camara": {"type": "STRING", "enum": list(ac.CAMARAS)},
                "texto_pantalla": {"type": "STRING"},
                "transicion": {"type": "STRING", "enum": list(TRANSICIONES)},
                "cadena": {"type": "ARRAY", "items": _CADENA},
                "viaje_a_anio": {"type": "INTEGER"},
                "vuelve_al_presente": {"type": "BOOLEAN"},
            },
            "required": ["frase", "parte", "fondo", "actores", "objetos", "camara", "texto_pantalla",
                         "transicion", "cadena", "viaje_a_anio", "vuelve_al_presente"]}},
        "locutor": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "despues_de_frase": {"type": "INTEGER"}, "texto": {"type": "STRING"}},
            "required": ["despues_de_frase", "texto"]}},
        "protagonista": {"type": "OBJECT", "properties": {
            "prop": {"type": "STRING", "enum": sorted(DETALLADOS)}, "que_es": {"type": "STRING"}},
            "required": ["prop", "que_es"]},
        "entidades": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "nombre": {"type": "STRING"}, "presentacion": {"type": "STRING"},
            "frase": {"type": "INTEGER"}}, "required": ["nombre", "presentacion", "frase"]}},
    },
    "required": ["titulo", "descripcion", "tono", "pregunta_gancho", "escenas", "locutor", "entidades",
                 "protagonista"],
}


def frases_de(d: dict) -> list[str]:
    return [str(e.get("frase") or "").strip() for e in d.get("escenas") or []]


def locutor_de(d: dict) -> list[tuple[int, str]]:
    """[(después de qué frase, desde 1; texto)], en orden."""
    out = []
    for x in d.get("locutor") or []:
        try:
            out.append((int(x.get("despues_de_frase")), str(x.get("texto") or "").strip()))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def segmentos(d: dict) -> list[tuple[str, int, str]]:
    """Lo que dice la voz, en orden: ("frase", índice, texto) y ("locutor", k, texto)."""
    loc = locutor_de(d)
    out = []
    for i, f in enumerate(frases_de(d)):
        out.append(("frase", i, f))
        for k, (despues, texto) in enumerate(loc):
            if despues == i + 1 and texto:
                out.append(("locutor", k, texto))
    return out


def textos_en_pantalla(d: dict) -> list[str]:
    out = []
    for e in d.get("escenas") or []:
        out.append(str(e.get("texto_pantalla") or ""))
        out += [str(o.get("texto") or "") for o in e.get("objetos") or []]
    return [t for t in out if t.strip()]


def _sin_mayusculas(t: str) -> str:
    """"NA, MENTIRA" → "Na, mentira": el chequeo de nombres propios mira las mayúsculas en medio de
    la oración, y un texto de pantalla va todo en mayúsculas (cada palabra sería un "nombre"). Las
    cifras se siguen chequeando; los nombres de pantalla salen de las frases, que sí se chequean."""
    if not any(c.islower() for c in t):
        t = t.lower()
    return t[:1].upper() + t[1:]


def _norm(t: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def _palabras(t: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _norm(t))


_PREP_LUGAR = re.compile(r"\b(en|de|desde|hacia|del|a|por)\s+((?:[A-ZÁÉÍÓÚÑ][\w'’-]*\s*)+)$")


def es_lugar(frase: str, nombre: str) -> bool:
    """¿El nombre va después de "en", "de", "desde"…? ("un inventor de Minnesota", "en Estados Unidos"):
    un lugar no hace falta presentarlo. Las empresas y las personas (que sí) suelen ser el sujeto."""
    i = frase.find(nombre)
    if i < 0:
        return False
    antes = frase[:i + len(nombre)]
    return bool(_PREP_LUGAR.search(antes))


def entidades_sin_presentar(d: dict, m: Marca) -> list[str]:
    """Los nombres propios de las frases que no están en `entidades`, y las entidades cuya
    presentación no se dice en la frase donde aparecen por primera vez (o en la siguiente)."""
    from clips_bot.textos import nombres_propios

    frases = frases_de(d)
    ents = [x for x in d.get("entidades") or [] if str(x.get("nombre") or "").strip()]
    errores = []
    for x in ents:
        nombre, pres = str(x["nombre"]), str(x.get("presentacion") or "")
        i = next((k for k, f in enumerate(frases) if _norm(nombre) in _norm(f)), None)
        if i is None:
            continue
        cerca = _norm(" ".join(frases[i:i + 2]))
        clave = [w for w in _palabras(pres) if len(w) > 3 and w not in _palabras(nombre)]
        if len(pres.split()) < 3 or not clave or sum(w in cerca for w in clave) < max(1, len(clave) // 2):
            errores.append(f"{nombre}: presentalo en pocas palabras la primera vez que aparece (frase {i + 1})")
    presentados = " ".join(_norm(str(x["nombre"])) for x in ents)
    sueltos = []
    for f in frases:
        for n in nombres_propios(f):
            if _norm(n) in presentados or _norm(n) in _norm(m.nombre) or n in sueltos or es_lugar(f, n):
                continue
            sueltos.append(n)
    if sueltos:
        errores.append("estos nombres no están en `entidades` (toda empresa o persona se presenta la "
                       "primera vez): " + ", ".join(sueltos[:8]))
    return errores


def errores_escenas_con_sentido(escenas: list[dict]) -> list[str]:
    """Reglas 4 y 5 de Santi: cada objeto en su lugar real, nada que aparezca o caiga de la nada, y la
    destrucción en cadena del gancho (2 a 4 golpes)."""
    errores = []
    for i, e in enumerate(escenas, 1):
        for o in e.get("objetos") or []:
            prop, ef, sop = o.get("prop"), o.get("efecto"), o.get("soporte")
            icono = prop in ac.ICONOS
            if ef in ("aparece", "crece") and not icono:
                errores.append(f"escena {i}: {prop} «{ef}» de la nada: solo los íconos aparecen; un objeto "
                               "real ya está en su lugar (quieto en la mesa, en el estante…) o lo trae alguien")
            if ef == "llueve" and prop not in ac.LLUEVEN:
                errores.append(f"escena {i}: solo llueven billetes o monedas (no {prop})")
            if ef == "cae_y_se_rompe" and sop not in ("mesa", "estante", "pared"):
                errores.append(f"escena {i}: {prop} cae y se rompe, pero ¿de dónde? Ponelo sobre una mesa, un "
                               "estante o colgado en la pared (`soporte`)")
            if sop == "aire" and not icono and ef not in ("vuela", "llueve"):
                errores.append(f"escena {i}: {prop} flotando en el aire: apoyalo (piso, mesa, estante, pared o mano)")
            if prop in ac.SOPORTE_OBLIGADO and sop and sop not in ac.SOPORTE_OBLIGADO[prop]:
                errores.append(f"escena {i}: {prop} va en {' o '.join(sorted(ac.SOPORTE_OBLIGADO[prop]))}, no en {sop}")
        cadena = e.get("cadena") or []
        if i == 1 and not CADENA_MIN <= len(cadena) <= CADENA_MAX:
            errores.append(f"el gancho necesita una destrucción en cadena (`cadena`) de {CADENA_MIN} a "
                           f"{CADENA_MAX} cosas que se rompen una tras otra (tiene {len(cadena)})")
        if len(cadena) > CADENA_MAX:
            errores.append(f"escena {i}: la cadena va de {CADENA_MAX} cosas como mucho (que se entienda cada golpe)")
        for c in cadena:
            if c.get("prop") not in ROMPIBLES:
                errores.append(f"escena {i}: {c.get('prop')!r} no se puede romper en la cadena")
            elif c.get("prop") in ac.SOPORTE_OBLIGADO and c.get("soporte") not in ac.SOPORTE_OBLIGADO[c["prop"]]:
                errores.append(f"escena {i}: en la cadena, {c['prop']} va en "
                               f"{' o '.join(sorted(ac.SOPORTE_OBLIGADO[c['prop']]))}")
        if cadena and len({(c.get("soporte"), c.get("donde")) for c in cadena}) < len(cadena):
            errores.append(f"escena {i}: dos cosas de la cadena en el mismo lugar: repartilas (izquierda, centro, derecha)")
    return errores


def errores_protagonista(d: dict) -> list[str]:
    """Regla 7: el objeto de la historia, dibujado con detalle (no un rótulo) y en 2 escenas o más."""
    errores = []
    pr = d.get("protagonista") or {}
    prop = pr.get("prop")
    if prop not in DETALLADOS:
        errores.append(f"`protagonista`: {prop!r} no es un objeto dibujado con detalle (elegí uno de: "
                       f"{', '.join(sorted(DETALLADOS))})")
    elif not str(pr.get("que_es") or "").strip():
        errores.append("`protagonista`: falta `que_es`")
    else:
        apariciones = 0
        for e in d.get("escenas") or []:
            en_objetos = any(o.get("prop") == prop for o in e.get("objetos") or [])
            en_cadena = bool(e.get("cadena")) and prop in ac.LANZABLES
            apariciones += en_objetos or en_cadena
        if apariciones < 2:
            errores.append(f"el protagonista ({prop}) aparece en {apariciones} escena(s): que se vea en 2 o más")
    for i, e in enumerate(d.get("escenas") or [], 1):
        for o in e.get("objetos") or []:
            if o.get("prop") == "caja" and str(o.get("texto") or "").strip():
                errores.append(f"escena {i}: una caja con el rótulo «{o['texto']}» no se entiende: dibujá el objeto "
                               "(juego_mesa, chocolate, galletitas…) o sacale el rótulo")
    return errores


def errores_viajes(d: dict, presente: int | None = None) -> list[str]:
    """Regla 6: cada vez que la historia cambia de época hay un viaje (Tito, el reloj, el año contando).
    Una frase que nombra un año del pasado tiene que estar en el pasado (un viaje en ella o antes); una
    que habla de hoy, en el presente (vuelve_al_presente en ella o antes)."""
    from datetime import date as _date

    presente = presente or _date.today().year
    errores, pasado = [], False
    for i, e in enumerate(d.get("escenas") or [], 1):
        anio = e.get("viaje_a_anio") or 0
        vuelve = bool(e.get("vuelve_al_presente"))
        if anio and not (1500 <= int(anio) < presente):
            errores.append(f"escena {i}: viaje_a_anio {anio} no es un año del pasado")
            anio = 0
        if i == 1 and anio:
            errores.append("el gancho es en el presente: el viaje al pasado va después")
        if vuelve and not pasado and not anio:
            errores.append(f"escena {i}: vuelve_al_presente sin haber viajado al pasado")
        if vuelve:
            pasado = False
        if anio:
            pasado = True
        frase = str(e.get("frase") or "")
        anios = [int(x) for x in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", frase) if int(x) < presente - 1]
        if anios and not pasado and i > 1:
            errores.append(f"escena {i} habla de {anios[0]}: marcá el viaje al pasado (`viaje_a_anio`) en esa "
                           "frase o antes")
        if pasado and _PRESENTE.search(frase) and not anios:
            errores.append(f"escena {i} habla de hoy: marcá `vuelve_al_presente` en esa frase")
    return errores


def validar_guion(d: dict, m: Marca, fuente: str) -> list[str]:
    """Los errores del guion (vacío = sirve): datos contra el artículo (como Pequeña Historia),
    estructura, escenas con acción, locutor y presentación de cada empresa o persona."""
    from clips_bot.efemerides import no_respaldados

    errores = []
    escenas = d.get("escenas") or []
    frases = frases_de(d)
    n = len(frases)
    if not FRASES_MIN <= n <= FRASES_MAX:
        errores.append(f"van {FRASES_MIN} a {FRASES_MAX} frases (escenas), hay {n}")
    if any(not f for f in frases):
        errores.append("hay una escena sin frase")
    loc = locutor_de(d)
    p_frases = sum(len(f.split()) for f in frases)
    p_loc = sum(len(t.split()) for _, t in loc)
    if not PALABRAS_MIN <= p_frases + p_loc <= PALABRAS_MAX:
        errores.append(f"entre frases ({p_frases}) y locutor ({p_loc}) son {p_frases + p_loc} palabras: "
                       f"tienen que ser entre {PALABRAS_MIN} y {PALABRAS_MAX}")
    if frases:
        g = frases[0]
        if len(g.split()) > GANCHO_MAX_PALABRAS:
            errores.append(f"el gancho (primera frase) tiene {len(g.split())} palabras: máximo "
                           f"{GANCHO_MAX_PALABRAS} (tiene que durar menos de 3 segundos)")
        if re.search(r"\b1[5-9]\d\d\b|\b20\d\d\b", g):
            errores.append("el gancho no lleva año: el año va después")
        if _ARRANQUES_PROHIBIDOS.search(g):
            errores.append("el gancho arranca con una fórmula gastada (¿Sabías…?, Hoy te cuento…, hola): "
                           "arrancá con la acción")
    if escenas:
        primera = escenas[0]
        if not primera.get("cadena") and \
                not any(a.get("accion") in ac.MOVIMIENTO for a in primera.get("actores") or []) and \
                not any(o.get("efecto") in ac.DINAMICOS for o in primera.get("objetos") or []):
            errores.append("el gancho (escena 1) tiene que ser ACCIÓN: alguien que corre, tira, se cae, "
                           "o algo que vuela o se rompe; no alguien hablando")
    # Mostrar, no contar: ninguna escena estática.
    estaticas = [str(i) for i, e in enumerate(escenas, 1) if not ac.es_dinamica(e)]
    if estaticas:
        errores.append(f"escenas estáticas (solo personajes parados): {', '.join(estaticas)}. Cada frase "
                       "tiene que MOSTRAR lo que dice con acción (moverse, tirar, romper, martillar…)")
    # Orden: problema → idea → qué pasó → final.
    partes = [e.get("parte") for e in escenas]
    if partes:
        if partes[0] != "gancho":
            errores.append("la primera frase es la parte `gancho`")
        orden = [RANGO_PARTE.get(p, -1) for p in partes]
        if any(b < a for a, b in zip(orden, orden[1:])):
            errores.append("las partes van en orden: gancho → problema → idea → que_paso (con el giro adentro) → final "
                           f"(vino: {' → '.join(str(p) for p in partes)})")
        for falta in ("problema", "idea", "que_paso", "final"):
            if falta not in partes:
                errores.append(f"falta la parte `{falta}` (problema → idea → qué pasó → final sorpresa)")
        if partes[-1] != "final":
            errores.append("la última frase es el final sorpresa que paga el gancho")
    if not str(d.get("pregunta_gancho") or "").strip():
        errores.append("falta `pregunta_gancho`")
    errores += errores_escenas_con_sentido(escenas)
    errores += errores_protagonista(d)
    errores += errores_viajes(d)
    # El locutor (Tito).
    if not LOCUTOR_MIN <= len(loc) <= LOCUTOR_MAX:
        errores.append(f"el locutor interrumpe {LOCUTOR_MIN} a {LOCUTOR_MAX} veces (hay {len(loc)})")
    for despues, texto in loc:
        if not 1 <= despues < n:
            errores.append(f"locutor después de la frase {despues}: va entre la 1 y la {n - 1}")
        if not 4 <= len(texto.split()) <= 22:
            errores.append(f"el comentario del locutor «{texto[:40]}» va de 5 a 20 palabras")
    if len({x for x, _ in loc}) != len(loc):
        errores.append("dos comentarios del locutor en el mismo lugar")
    for i, e in enumerate(escenas, 1):
        if len(str(e.get("texto_pantalla") or "").split()) > 4:
            errores.append(f"escena {i}: `texto_pantalla` de 4 palabras como mucho")
        if e.get("fondo") not in FONDOS:
            errores.append(f"escena {i}: fondo {e.get('fondo')!r} no existe")
        actores, objetos = e.get("actores") or [], e.get("objetos") or []
        if len(actores) > 3 or len(objetos) > 3:
            errores.append(f"escena {i}: 3 actores y 3 objetos como mucho")
        for a in actores:
            if a.get("rol") not in ac.ROLES or a.get("accion") not in ac.ACCIONES:
                errores.append(f"escena {i}: actor {a.get('rol')!r}/{a.get('accion')!r} no existe")
        for o in objetos:
            if o.get("prop") not in PROPS or o.get("efecto") not in ac.EFECTOS:
                errores.append(f"escena {i}: objeto {o.get('prop')!r}/{o.get('efecto')!r} no existe")
            if len(str(o.get("texto") or "")) > 12:
                errores.append(f"escena {i}: el texto de un objeto va de 12 letras como mucho")
    titulo = str(d.get("titulo") or "")
    if not titulo.strip() or len(titulo) > 70:
        errores.append("`titulo`: entre 1 y 70 caracteres")
    hablado = frases + [t for _, t in loc]
    todo = " ".join(hablado + [titulo, str(d.get("descripcion") or "")] + textos_en_pantalla(d))
    sens = sorted({x.group(0).lower() for x in _SENSIBLE.finditer(todo)})
    if sens:
        errores.append(f"nada de temas sensibles (aparece: {', '.join(sens)}): contá otra parte de la historia")
    errores += entidades_sin_presentar(d, m)
    base = f"{fuente}\n{m.nombre} {m.pais}"
    anios = [str(e.get("viaje_a_anio")) for e in escenas if isinstance(e.get("viaje_a_anio"), int)
             and e.get("viaje_a_anio") > 0]
    texto = " ".join(hablado + [titulo] + [_sin_mayusculas(t) + "." for t in textos_en_pantalla(d)] + anios)
    faltan = no_respaldados(texto, base)
    if faltan:
        errores.append("esto no está en el artículo de Wikipedia (sacalo o usá lo que dice el texto): "
                       + ", ".join(faltan[:12]))
    return errores


# Chequeo de calidad con Haiku (barato): lo que el código no puede ver.
SISTEMA_CALIDAD = """Revisás el guion de un video animado corto para un público que NO sabe nada del tema.
Te paso cada frase (voz en off) con lo que se VE en su escena, y los comentarios del locutor.
Marcá SOLO problemas reales:
- `sin_presentar`: empresas, personas o cosas (no la marca del video) que aparecen sin explicar qué o
  quién son en pocas palabras la primera vez (ej. "Parker Brothers" a secas: no se sabe que es una
  fábrica de juegos).
- `confuso`: saltos que no se entienden (falta la causa o el efecto, un "eso" que no se sabe qué es,
  algo que pasa sin que se haya contado el problema o la idea).
- `no_muestra`: frases cuya escena no muestra lo que dice la frase (ej. la frase habla de una fábrica
  y la escena es alguien saltando en la calle), o que son solo gente parada.
- `rotulo`: un objeto clave de la historia que se muestra como una caja o un cartel con su nombre
  escrito en vez de dibujarlo (ej. una caja que dice "Juego" en vez de un juego de mesa).
- `sin_sentido`: objetos en lugares absurdos (una lámpara en el medio de la calle, una tele en el piso
  de una fábrica) o cosas que aparecen o caen de la nada. OJO: los ÍCONOS de dibujo animado (la
  lamparita de una idea arriba de la cabeza, un signo de pregunta, un gráfico, un cartel, un
  calendario) van en el aire a propósito, y la "lluvia" de billetes o monedas es una metáfora de
  "ganaron mucha plata": eso NO es un problema.
Si está bien, listas vacías."""

SCHEMA_CALIDAD = {"type": "OBJECT", "properties": {
    "sin_presentar": {"type": "ARRAY", "items": {"type": "STRING"}},
    "confuso": {"type": "ARRAY", "items": {"type": "STRING"}},
    "no_muestra": {"type": "ARRAY", "items": {"type": "STRING"}},
    "sin_sentido": {"type": "ARRAY", "items": {"type": "STRING"}},
    "rotulo": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["sin_presentar", "confuso", "no_muestra", "sin_sentido", "rotulo"]}


def describir(d: dict) -> str:
    pr = d.get("protagonista") or {}
    lineas = [f"PROTAGONISTA: {pr.get('que_es') or '?'} (dibujado como {pr.get('prop') or '?'})"] if pr else []
    loc = dict(locutor_de(d))
    for i, e in enumerate(d.get("escenas") or [], 1):
        actores = "; ".join(f"{a.get('rol')} {a.get('accion')}" + (
            f" hacia {a.get('hacia')}" if a.get("hacia") not in (None, "ninguno") else "")
            for a in e.get("actores") or [])
        objetos = "; ".join(f"{o.get('prop')} ({o.get('soporte') or '?'}) {o.get('efecto')}"
                            for o in e.get("objetos") or [])
        cadena = " → ".join(f"{c.get('prop')} ({c.get('soporte')})" for c in e.get("cadena") or [])
        viaje = (f" [VIAJE a {e['viaje_a_anio']}]" if e.get("viaje_a_anio") else "") + \
            (" [VUELVE AL PRESENTE]" if e.get("vuelve_al_presente") else "")
        lineas.append(f"{i}. «{e.get('frase')}»{viaje} — SE VE: {e.get('fondo')}; {actores or 'nadie'}; "
                      f"{objetos or 'sin objetos'}" + (f"; se rompen en cadena: {cadena}" if cadena else ""))
        if i in loc:
            lineas.append(f"   (PAUSA, Tito: «{loc[i]}»)")
    return "\n".join(lineas)


def chequear_calidad(cliente, d: dict, m: Marca) -> list[str]:
    """Errores de claridad y de "mostrar, no contar" según Haiku (vacío = bien o no se pudo chequear)."""
    if cliente is None:
        return []
    try:
        r = json.loads(cliente.json(SISTEMA_CALIDAD, f"MARCA DEL VIDEO: {m.nombre}\n\n{describir(d)}",
                                    SCHEMA_CALIDAD, 0.2))
    except Exception as e:     # el chequeo es una ayuda: si Haiku no responde, sigue
        log.warning("chequeo de calidad con Haiku: %s", e)
        return []
    errores = []
    if r.get("sin_presentar"):
        errores.append("presentá en pocas palabras, la primera vez que aparecen: " + "; ".join(r["sin_presentar"][:5]))
    if r.get("confuso"):
        errores.append("no se entiende (contalo con causa y efecto): " + "; ".join(r["confuso"][:4]))
    if r.get("no_muestra"):
        errores.append("la escena no muestra lo que dice la frase: " + "; ".join(r["no_muestra"][:4]))
    if r.get("rotulo"):
        errores.append("objeto clave que es solo un rótulo (dibujalo con su prop): " + "; ".join(r["rotulo"][:3]))
    if r.get("sin_sentido"):
        errores.append("escena sin sentido (cada cosa en su lugar real, nada de la nada): "
                       + "; ".join(r["sin_sentido"][:4]))
    return errores


def escribir_guion(cliente, e: Elegido, fuente: str, reintentos: int = 6, avisar=log.info,
                   revisor=None, extra: str = "") -> dict:
    """El guion validado (dict del schema). Primero el chequeo del código; si pasa, el de Haiku
    (`revisor`). Si no valida, reintenta con los errores; si nunca valida, GuionInvalido."""
    pedido = (f"MARCA: {e.marca.nombre} ({e.marca.pais})\nÁNGULO: {e.angulo} — {ANGULOS[e.angulo]}\n"
              f"Dato para el gancho (sugerido): {e.dato}\n\nTEXTO (Wikipedia; los datos salen SOLO de "
              f"acá):\n{fuente[:20000]}" + (f"\n\n{extra}" if extra else ""))
    correccion, ultimo = "", []
    for intento in range(reintentos):
        d = json.loads(cliente.json(SISTEMA_GUION, pedido + correccion, SCHEMA_GUION, 0.9))
        ultimo = validar_guion(d, e.marca, fuente)
        if not ultimo:
            ultimo = chequear_calidad(revisor, d, e.marca)
        if not ultimo:
            return d
        avisar(f"guion de {e.marca.nombre} ({e.angulo}), intento {intento + 1}: {'; '.join(ultimo)[:400]}")
        correccion = ("\n\nTU GUION ANTERIOR:\n" + describir(d) +
                      "\n\nNO SIRVIÓ POR ESTO (corregilo y devolvé el guion entero):\n- " + "\n- ".join(ultimo))
    raise GuionInvalido(f"{e.marca.nombre} ({e.angulo}): {'; '.join(ultimo)[:400]}")


def hashtags(m: Marca) -> list[str]:
    limpio = re.sub(r"[^\w]", "", m.nombre.replace("&", "y"))
    return ["#Shorts", "#marcas", f"#{limpio}"] if limpio else ["#Shorts", "#marcas"]


# ---- 6. escenas → línea de tiempo ------------------------------------------------------------

def cortes(inicios: list[float], fin: float, cola_s: float = 0.8) -> list[float]:
    """La duración de cada tramo: de un poquito antes de lo que se dice a un poquito antes de lo
    siguiente (la imagen cambia justo antes de que se diga), el último hasta `fin` + `cola_s`."""
    arranques = [0.0] + [max(0.0, t - 0.12) for t in inicios[1:]]
    finales = arranques[1:] + [fin + cola_s]
    return [round(max(0.4, b - a), 3) for a, b in zip(arranques, finales)]


def linea_de_tiempo(d: dict, inicios: list[float], fin: float, palabras: list,
                    voz: Path | None, presente: int | None = None) -> tuple[dict, list[tuple[float, str]]]:
    """El guion + los tiempos reales de la voz (un inicio por SEGMENTO: frases y comentarios de Tito,
    en orden) → (dict de `timeline.Video`, SFX con su segundo global).

    Los viajes en el tiempo se meten al principio de la frase que los marca (le sacan ~1,25 s a su
    escena: la voz sigue hablando mientras el año cuenta); las escenas del pasado van en sepia."""
    from datetime import date as _date

    presente = presente or _date.today().year
    segs = segmentos(d)
    escenas_d = d.get("escenas") or []
    durs = cortes(inicios, fin)
    escenas, sfx, t = [], [], 0.0
    anio_actual, pasado = presente, False
    prota = str((d.get("protagonista") or {}).get("prop") or "")
    proyectil = prota if prota in ac.LANZABLES else "pelota"
    vistas: dict[tuple, int] = {}     # (fondo, década) → cuántas veces: la variante, para no repetir igual
    for n_seg, ((tipo, k, _), dur) in enumerate(zip(segs, durs)):
        if tipo == "locutor":
            esc_d, fx = ac.escena_locutor(dur, k)
            escenas.append(esc_d)
            sfx += [(round(t + x, 3), s) for x, s in fx]
            t += dur
            continue
        e = escenas_d[k]
        viaje_a = int(e.get("viaje_a_anio") or 0)
        destino = None
        if viaje_a and k > 0 and viaje_a < presente and abs(viaje_a - anio_actual) >= SALTO_MIN:
            destino = viaje_a
        elif e.get("vuelve_al_presente") and pasado:
            destino = presente
        if destino is not None and escenas:
            dv = min(ac.VIAJE_S, max(0.8, dur - 1.0))
            esc_v, fx = ac.escena_viaje(dv, anio_actual, destino, presente)
            escenas.append(esc_v)
            sfx += [(round(t + x, 3), s) for x, s in fx]
            t += dv
            dur = round(dur - dv, 3)
            anio_actual, pasado = destino, destino < presente
        sigue = segs[n_seg + 1] if n_seg + 1 < len(segs) else None
        reservar = ac.lado_tito(sigue[1]) if sigue and sigue[0] == "locutor" else None
        clave = (e.get("fondo"), anio_actual // 10)
        variante = vistas.get(clave, 0)
        vistas[clave] = variante + 1
        esc_d, fx = ac.escena_accion(e, dur, k, primera=(k == 0), tono=1.0 if pasado else 0.0,
                                     anio=anio_actual, variante=variante, reservar=reservar,
                                     proyectil=proyectil)
        esc_d["frase"] = k          # para la revisión visual: qué frase del guion es esta escena
        pisados = ac.superposiciones(esc_d)
        if pisados:
            log.warning("escena %d: personajes que se pisan en %s", k + 1, pisados[:3])
        if destino is not None:
            esc_d["transicion"] = {"tipo": "zoom", "duracion": 0.25}
        escenas.append(esc_d)
        sfx += [(round(t + x, 3), s) for x, s in fx]
        t += dur
    out = {"fps": P.FPS, "escenas": escenas, "subtitulos_y": SUBTITULOS_Y, "subtitulos_tam": SUBTITULOS_TAM,
           "subtitulos_banda": True}
    if voz is not None:
        out["audio"] = str(voz)
    if palabras:
        out["subtitulos"] = [{"palabras": [{"texto": p.texto, "inicio": round(p.inicio, 3),
                                            "fin": round(p.fin, 3)} for p in palabras]}]
    return out, sorted(sfx)


# ---- 7. el video entero -----------------------------------------------------------------------

def acortar_pausas(wav: Path, max_s: float = PAUSA_MAX_S, umbral_db: float = -38.0,
                   ventana_s: float = 0.01) -> float:
    """Los silencios ENTRE frases a `max_s` como mucho (Santi: "menos pausas"): se saca el medio de cada
    silencio largo y queda la mitad de `max_s` de cada lado (nada de cortes secos en una palabra).
    Devuelve los segundos sacados. Solo PCM de 16 bits; el principio y el final no se tocan acá."""
    import wave

    import numpy as np

    with wave.open(str(wav)) as w:
        prm = w.getparams()
        datos = w.readframes(w.getnframes())
    if prm.sampwidth != 2 or not prm.nframes:
        return 0.0
    x = np.frombuffer(datos, dtype="<i2").reshape(-1, prm.nchannels)
    sr = prm.framerate
    paso = max(1, int(sr * ventana_s))
    xf = x.astype(np.float32).mean(axis=1) / 32768.0
    n_v = len(xf) // paso
    rms = np.sqrt(np.mean(xf[:n_v * paso].reshape(n_v, paso) ** 2, axis=1) + 1e-12)
    silencio = 20 * np.log10(rms) < umbral_db
    quedan, i, sacado = [], 0, 0
    tramos = []
    k = 0
    while k < n_v:
        if silencio[k]:
            j = k
            while j < n_v and silencio[j]:
                j += 1
            if k > 0 and j < n_v and (j - k) * ventana_s > max_s:
                tramos.append((k * paso, j * paso))
            k = j
        else:
            k += 1
    if not tramos:
        return 0.0
    medio = int(sr * max_s / 2)
    for a, b in tramos:
        quedan.append(x[i:a + medio])
        sacado += (b - a) - 2 * medio
        i = b - medio
    quedan.append(x[i:])
    y = np.concatenate(quedan)
    with wave.open(str(wav), "wb") as w:
        w.setparams(prm)
        w.writeframes(y.astype("<i2").tobytes())
    return round(sacado / sr, 2)


def niveles(ruta: Path) -> dict:
    """{"medio": dB, "pico": dB} con ffmpeg volumedetect (para confirmar que se oyen voz, música y SFX)."""
    import subprocess

    from clips_bot.media import find_bin

    r_ = subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-nostats", "-i", str(ruta), "-vn", "-af",
                         "volumedetect", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    medio = re.search(r"mean_volume: (-?[\d.]+) dB", r_.stderr)
    pico = re.search(r"max_volume: (-?[\d.]+) dB", r_.stderr)
    return {"medio": float(medio.group(1)) if medio else None, "pico": float(pico.group(1)) if pico else None}


# ---- revisión visual automática (Santi, 2026-11-14) -------------------------------------------------
SISTEMA_REVISION = """Revisás cuadros de un video animado corto (dibujos planos, estilo dibujo animado) ANTES de
publicarlo. Cada imagen es un cuadro clave (te digo de qué escena). Marcá SOLO cosas absurdas o feas
que un espectador notaría:
- un objeto flotando sin razón (salvo íconos de dibujo animado: una lamparita de idea arriba de una
  cabeza, un signo de pregunta, la lluvia de billetes o monedas, un objeto que vuela porque lo tiraron);
- un brazo o un objeto que atraviesa la cara de alguien;
- un personaje tapado por un mueble u otro personaje;
- un objeto donde no va (una pelota sobre un sombrero, una tele en el piso de la calle);
- un texto ilegible o cortado; un subtítulo tapando algo importante.
Para cada problema: `cuadro` (el número), `que` (corto) y `arreglo`: mover_objeto (a otro lugar),
cambiar_soporte (apoyarlo en otro lado), sacar_objeto, separar_personajes, sacar_texto u otro; y
`objeto` (el nombre del objeto, si es un objeto). Si está todo bien, lista vacía. No inventes problemas."""

SCHEMA_REVISION = {"type": "OBJECT", "properties": {"problemas": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {
        "cuadro": {"type": "INTEGER"}, "que": {"type": "STRING"},
        "arreglo": {"type": "STRING", "enum": ["mover_objeto", "cambiar_soporte", "sacar_objeto",
                                               "separar_personajes", "sacar_texto", "otro"]},
        "objeto": {"type": "STRING"}},
    "required": ["cuadro", "que", "arreglo", "objeto"]}}}, "required": ["problemas"]}
CUADROS_REVISION = 8


def cuadros_clave(datos: dict, maximo: int = CUADROS_REVISION) -> list[tuple[float, int, str]]:
    """(segundo, índice de escena en `datos`, qué es) de los cuadros a revisar: el gancho, el viaje en
    el tiempo y el medio de cada escena de acción (hasta `maximo`)."""
    t, out = 0.0, []
    for i, e in enumerate(datos["escenas"]):
        dur = float(e["duracion"])
        if e.get("girar"):
            out.append((t + dur * 0.55, i, "viaje en el tiempo"))
        elif not e.get("congela"):
            frac = 0.75 if not out else 0.55
            out.append((t + dur * frac, i, "gancho" if not out else f"escena {e.get('frase', i) + 1}"))
        t += dur
    if len(out) > maximo:   # el gancho, el viaje y repartidas las demás
        fijos = [c for c in out if c[2] in ("gancho", "viaje en el tiempo")]
        resto = [c for c in out if c not in fijos]
        paso = len(resto) / max(1, maximo - len(fijos))
        out = sorted(fijos + [resto[int(k * paso)] for k in range(maximo - len(fijos))])
    return out


def _jpeg_512(png: Path) -> bytes:
    import io

    from PIL import Image

    im = Image.open(png).convert("RGB")
    im.thumbnail((512, 512))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    return b.getvalue()


def aplicar_revision(d: dict, problemas: list[dict], claves: list[tuple[float, int, str]],
                     datos: dict) -> list[str]:
    """Corrige el GUION según lo que vio la revisión (en la escena de cada cuadro). Devuelve qué hizo."""
    hechos = []
    for pr in problemas:
        n = int(pr.get("cuadro") or 0) - 1
        if not 0 <= n < len(claves):
            continue
        esc_d = datos["escenas"][claves[n][1]]
        k = esc_d.get("frase")
        if k is None:
            continue
        e = d["escenas"][k]
        arreglo, obj = pr.get("arreglo"), str(pr.get("objeto") or "").strip().lower()
        objs = e.get("objetos") or []
        cual = next((o for o in objs if obj and obj in str(o.get("prop"))), objs[0] if objs else None)
        if arreglo == "sacar_objeto" and cual is not None:
            objs.remove(cual)
            hechos.append(f"escena {k + 1}: saqué {cual['prop']} ({pr.get('que')})")
        elif arreglo in ("mover_objeto", "cambiar_soporte") and cual is not None:
            cual["soporte"] = "estante" if cual.get("soporte") in ("mesa", "piso", "aire", "mano") else "piso"
            cual["donde"] = "derecha" if cual.get("donde") != "derecha" else "izquierda"
            hechos.append(f"escena {k + 1}: {cual['prop']} al {cual['soporte']} ({pr.get('que')})")
        elif arreglo == "separar_personajes" and len(e.get("actores") or []) > 1:
            e["actores"] = e["actores"][:-1] if len(e["actores"]) > 2 else e["actores"]
            for a, lado in zip(e["actores"], ("izquierda", "derecha")):
                a["desde"], a["hacia"] = lado, "ninguno" if a.get("accion") not in ("entrar", "salir") else a.get("hacia")
            hechos.append(f"escena {k + 1}: separé a los personajes ({pr.get('que')})")
        elif arreglo == "sacar_texto" and e.get("texto_pantalla"):
            e["texto_pantalla"] = ""
            hechos.append(f"escena {k + 1}: saqué el texto en pantalla ({pr.get('que')})")
        else:
            hechos.append(f"escena {k + 1}: visto sin arreglo automático: {pr.get('que')}")
    return hechos


def revisar_visual(cliente, d: dict, datos: dict, carpeta: Path, capturar=None, avisar=log.info) -> tuple[list, list]:
    """Claude mira los cuadros clave (JPEG de ~512 px) y dice qué está mal. Devuelve (problemas, claves).
    `capturar(datos, segundo, png)` dibuja un cuadro (por defecto, render.cuadro_png)."""
    from . import render as rd
    from .timeline import Video

    claves = cuadros_clave(datos)
    if cliente is None or not claves:
        return [], claves
    video = Video.desde_dict({**datos, "audio": None})
    imagenes = []
    for n, (t, _i, _q) in enumerate(claves):
        png = carpeta / f"revision_{n + 1}.png"
        if capturar:
            capturar(datos, t, png)
        else:
            rd.cuadro_png(video, min(video.total_cuadros - 1, int(t * video.fps)), png, escala=0.5)
        imagenes.append(_jpeg_512(png))
    lista = "\n".join(f"Cuadro {n + 1}: {q}" for n, (_t, _i, q) in enumerate(claves))
    try:
        r_ = json.loads(cliente.json(SISTEMA_REVISION, f"Los cuadros, en orden:\n{lista}", SCHEMA_REVISION, 0.2,
                                     imagenes=imagenes))
    except Exception as err:   # la revisión es una red de seguridad: si no responde, sigue
        avisar(f"revisión visual: no respondió ({str(err)[:120]})")
        return [], claves
    return list(r_.get("problemas") or []), claves


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
    revision: list = field(default_factory=list)      # lo que vio la revisión visual y lo que se corrigió
    niveles: dict = field(default_factory=dict)       # dB de la voz, la música, los SFX y la mezcla

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
             minimo: float = PUNTAJE_MIN, max_intentos: int = 3, avisar=log.info,
             revisor=None, forzar: Elegido | None = None) -> tuple[Elegido, dict, str]:
    """(elegido, guion validado, fuente). SinCandidato si ninguno llega al puntaje o ningún guion valida.
    `forzar`: una marca y ángulo elegidos a mano (para rehacer un ejemplo): sin rotación ni puntaje."""
    if forzar is not None:
        fuente = fuente_de(wiki, forzar.marca)
        try:
            return forzar, escribir_guion(cliente, forzar, fuente, avisar=avisar, revisor=revisor), fuente
        except GuionInvalido as err:
            raise SinCandidato(f"el guion no pasó la validación: {err}") from err
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
            return e, escribir_guion(cliente, e, fuente, avisar=avisar, revisor=revisor), fuente
        except GuionInvalido as err:
            errores.append(str(err))
    raise SinCandidato("ningún guion pasó la validación: " + " | ".join(errores)[:600])


VOLUMEN_SFX = 0.32
# Subtítulos (Santi, 2026-11-14): chicos, en una franja angosta ARRIBA, con banda semitransparente; la
# escena no sube de ac.BANDA_SUBTITULOS (lo controla acciones.composicion), así que no tapan nada.
SUBTITULOS_Y = 232          # ARRIBA (Santi, 2026-11-14): debajo de la interfaz de Shorts, la escena no sube de 300
SALTO_MIN = 10       # un "viaje" de menos de 10 años (1969 → 1970) no es cambio de época: no se hace
SUBTITULOS_TAM = 52


def armar_video(conn, settings, carpeta: Path, cliente=None, wiki=None, hoy: date | None = None,
                avisar=log.info, procesos: int = 2, catalogo: list[Marca] | None = None,
                forzar: Elegido | None = None, revisor=None, guion: dict | None = None,
                reescribir: bool = True) -> Resultado:
    """De punta a punta: elegir → guion (con el chequeo de Haiku) → voz → Whisper → escenas de acción +
    pausas del locutor → SFX → mp4. No sube nada a ningún lado."""
    from clips_bot import claude, musica, narrar
    from clips_bot import efemerides as ef
    from clips_bot.config import ROOT

    from . import render as rd
    from . import sfx as efectos
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
    revisor = revisor or claude.cliente(claude.HAIKU)
    wiki = wiki or ef.Wiki()
    t0 = time.time()
    fuente = ""
    if guion is not None and forzar is not None:   # rearmar un guion ya validado (sin gastar Claude)
        e, d = forzar, guion
    else:
        e, d, fuente = proponer(conn, cliente, wiki, hoy, catalogo, cfg.candidatos, cfg.puntaje_min,
                                cfg.max_intentos, avisar, revisor=revisor, forzar=forzar)
    tiempos["guion_s"] = round(time.time() - t0, 1)
    (carpeta / "guion.json").write_text(json.dumps({"marca": e.marca.nombre, "angulo": e.angulo,
                                                    "notas": e.notas, "guion": d}, ensure_ascii=False,
                                                   indent=1), encoding="utf-8")
    # Voz: la misma cadena que Pequeña Historia (ElevenLabs si está, Gemini TTS, Piper de respaldo).
    # Tito es la misma voz: la mascota ES el que narra. Ritmo (Santi, 2026-11-14): ×1,065
    # sin cambiar el tono y los silencios entre frases a 0,22 s; si queda fuera de 32-38 s, se REESCRIBE el
    # guion (no se acelera más).
    t0 = time.time()
    for intento in range(3):
        segs = segmentos(d)
        hablado = [t for _, _, t in segs]
        wav, _duraciones, motor = ef.voz_efemeride(hablado, settings, carpeta, avisar)
        narrar.a_48k(wav)
        ef.acelerar(wav, VELOCIDAD_VOZ)
        sacado = acortar_pausas(wav)
        narrar.sacar_silencio_inicial(wav)
        fin = narrar.duracion_wav(wav)
        avisar(f"voz: {fin:.1f} s (×{VELOCIDAD_VOZ}, {sacado:.1f} s de pausas menos)")
        if MIN_S <= fin <= MAX_S or intento == 2 or not reescribir:
            break
        # fuera de 32-38 s: se reescribe el guion (más corto o más largo), nunca se acelera más
        palabras_hoy = sum(len(x.split()) for x in hablado)
        largo = fin > MAX_S
        objetivo = int(palabras_hoy * ((MAX_S - 2) if largo else (MIN_S + 3)) / fin)
        avisar(f"la voz dura {fin:.1f} s: {'acorto' if largo else 'alargo'} el guion a {objetivo} palabras")
        if not fuente:
            fuente = fuente_de(wiki, e.marca)
        try:
            d = escribir_guion(cliente, e, fuente, avisar=avisar, revisor=revisor,
                               extra=(f"OJO: tu guion anterior, leído en voz alta, duró {fin:.0f} segundos y tiene "
                                      f"que durar entre {MIN_S:g} y {MAX_S:g}. Escribilo con unas {objetivo} palabras "
                                      "en total (frases + Tito), con la misma historia:\n" + describir(d)))
        except GuionInvalido as err:
            avisar(f"no pude acortar el guion: {err}")
            break
    tiempos["voz_s"] = round(time.time() - t0, 1)
    t0 = time.time()
    oidas = narrar.palabras_de_voz(wav, settings.subtitulos)
    oidas, recortado = narrar.recortar_inicio(wav, oidas, hablado)
    if recortado:
        fin = narrar.duracion_wav(wav)
    palabras, inicios = narrar.alinear_a_guion(oidas, hablado, fin)
    tiempos["whisper_s"] = round(time.time() - t0, 1)
    avisar(f"voz ({motor}): {fin:.1f} s")
    datos, eventos = linea_de_tiempo(d, inicios, fin, palabras, wav)
    # Revisión visual (Santi, 2026-11-14): Claude mira los cuadros clave ANTES del render y, si ve algo
    # absurdo, se corrige el guion de esa escena y se vuelve a armar; como mucho 2 vueltas.
    revision: list[str] = []
    t0 = time.time()
    for vuelta in range(2):
        problemas, claves = revisar_visual(cliente, d, datos, carpeta, avisar=avisar)
        if not problemas:
            revision.append(f"vuelta {vuelta + 1}: sin problemas" if vuelta else "revisión visual: sin problemas")
            break
        hechos = aplicar_revision(d, problemas, claves, datos)
        revision += [f"vuelta {vuelta + 1}: {h}" for h in hechos]
        avisar("revisión visual: " + "; ".join(hechos)[:300])
        datos, eventos = linea_de_tiempo(d, inicios, fin, palabras, wav)
    tiempos["revision_s"] = round(time.time() - t0, 1)
    (carpeta / "linea_de_tiempo.json").write_text(json.dumps({"video": datos, "sfx": eventos},
                                                             ensure_ascii=False, indent=1), encoding="utf-8")
    video = Video.desde_dict(datos)
    # Música baja, con ducking, y encima los SFX en su segundo. La boca sigue la voz SOLA.
    tema = None
    if cfg.musica:
        carpeta_musica = ROOT / settings.efemerides.carpeta_musica
        # un tema CON RITMO (alegre), bajo la voz con ducking (musica.mezclar); licencia verificada
        tema = musica.elegir(musica.cargar(carpeta_musica), "alegre", musica.recientes(conn), musica.vetados(conn))
    audio = (musica.mezclar(wav, ROOT / settings.efemerides.carpeta_musica / tema.ruta,
                            carpeta / "voz_musica.wav", cfg.musica_volumen) if tema else wav)
    if tema:
        musica.anotar_uso(conn, tema.ruta)   # así no sale siempre el mismo tema
    audio = efectos.mezclar(audio, eventos, carpeta / "audio_final.wav", video.duracion, VOLUMEN_SFX)
    video.audio = str(audio)
    # Niveles (que se oiga todo): la voz sola, la música sola al volumen de la mezcla, los SFX solos y
    # la mezcla final.
    import wave as _wave

    import numpy as np

    niv = {"voz": niveles(wav), "mezcla": niveles(audio)}
    pista = efectos.pista(eventos, video.duracion, VOLUMEN_SFX)
    with _wave.open(str(carpeta / "sfx_solos.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(efectos.SR)
        w.writeframes((np.clip(pista, -1, 1) * 32767).astype("<i2").tobytes())
    niv["sfx"] = niveles(carpeta / "sfx_solos.wav")
    if tema:
        from clips_bot.media import find_bin, run

        sola = carpeta / "musica_sola.wav"
        run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i",
             str((ROOT / settings.efemerides.carpeta_musica / tema.ruta).resolve()), "-t", f"{video.duracion:.2f}",
             "-af", f"aformat=channel_layouts=mono,volume={cfg.musica_volumen}", "-ar", "48000", str(sola.resolve())])
        niv["musica"] = niveles(sola)
    avisar(f"niveles: {niv}")
    salida = carpeta / f"marca_{re.sub(r'[^a-z0-9]+', '_', e.marca.nombre.lower())}_{e.angulo}.mp4"
    t0 = time.time()
    r = rd.renderizar(video, salida, "auto", procesos, crf=22, preset="medium",
                      hilos_x264=rd.hilos_x264_defecto())
    tiempos["render_s"] = round(time.time() - t0, 1)
    avisar(r.resumen())
    return Resultado(
        marca=e.marca.nombre, angulo=e.angulo, notas=e.notas, promedio=e.promedio,
        titulo=str(d.get("titulo") or ""), descripcion=str(d.get("descripcion") or ""),
        hashtags=hashtags(e.marca), frases=hablado, video=str(salida), duracion_s=round(video.duracion, 1),
        motor_voz=motor, musica=tema.ruta if tema else "", credito_musica=tema.credito() if tema else "",
        articulo=f"https://es.wikipedia.org/wiki/{e.marca.wiki_es.replace(' ', '_')}",
        render_s=tiempos["render_s"], total_s=round(time.time() - t_total, 1),
        costo_usd=costo_desde(conn, fila0), tiempos=tiempos, revision=revision, niveles=niv)


# ---- 8. a Telegram (sin subir a ningún lado) -----------------------------------------------------

NOMBRES_CRITERIOS = {"marca_conocida": "marca conocida", "dato_sorprendente": "dato sorprendente",
                     "giro": "giro", "humor": "humor"}


def texto_mensaje(r: Resultado, encabezado: str = "", subida: bool = False) -> str:
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
    ] + ([] if subida else ["📵 No quedó programado en ningún lado (mirá el aviso de arriba)."])
    if r.revision:
        partes += ["", "<b>Revisión visual:</b> " + html.escape("; ".join(r.revision))[:900]]
    if r.niveles:
        partes += ["<b>Audio (dB medio / pico):</b> " + html.escape(" · ".join(
            f"{k} {v.get('medio')} / {v.get('pico')}" for k, v in r.niveles.items()))]
    return "\n".join(partes)


def enviar(tg, chats, r: Resultado, encabezado: str = "", subida: bool = False) -> int:
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
        for parte in partir_html(texto_mensaje(r, encabezado, subida)):
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
