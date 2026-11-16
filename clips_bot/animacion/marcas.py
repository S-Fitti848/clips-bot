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
from . import subtitulos_virales as sv
from . import texto as tx

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
GANCHO_SIN_ACCION = {"objeto_gira", "contador_ventas", "reunion", "estantes_llenan"}
QUIETAS = {"quieto", "pensar", "senalar"}   # sin acción: nadie hace solo esto (Santi, 2026-11-15)
PISO_ABSOLUTO = 6.0    # Santi, 2026-11-15: en el último intento del día sale la mejor si tiene 6; si no, el banco
DIAS_SIN_REPETIR_MARCA = 7

PALABRAS_MIN, PALABRAS_MAX = 68, 98      # frases + locutor: con la voz ×1,065 y pausas cortas, 32-38 s
FRASES_MIN, FRASES_MAX = 7, 12
GANCHO_MAX_PALABRAS = 8                   # el gancho dura menos de 3 s
MAX_S = 38.0            # Santi (2026-11-14): 32-38 s; fuera de eso, ±8 % de velocidad y si no alcanza se reescribe
MIN_S = 32.0
VELOCIDAD_VOZ = 1.065   # atempo (sin cambiar el tono): ×1,13 quedó "un pelín rápido" (Santi, 2026-11-14)
PAUSA_MAX_S = 0.22      # el silencio entre frases, como mucho
AJUSTE_VEL_MAX = 0.08   # Santi (2026-11-15): fuera de 32-38 s, primero la velocidad del audio que ya está (±8 %,
                        # sin cambiar el tono); recién si no alcanza se reescribe el guion y se paga otra voz


def ajuste_velocidad(fin: float, minimo: float = MIN_S, maximo: float = MAX_S,
                     tope: float = AJUSTE_VEL_MAX) -> float | None:
    """El atempo que lleva una voz de `fin` s adentro del rango (con medio segundo de margen); None si ya está
    adentro o si haría falta más de ±`tope` (ahí se reescribe)."""
    if minimo <= fin <= maximo:
        return None
    objetivo = (maximo - 0.5) if fin > maximo else (minimo + 0.5)
    factor = fin / objetivo
    return factor if abs(factor - 1) <= tope else None

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
FONDOS = ("casa", "taller", "fabrica", "tienda", "oficina", "ciudad", "escenario", "cielo", "globo",
          "laboratorio", "hospital", "campo", "puerto")
# mesa y estante no son objetos de la historia: son el APOYO (`soporte`) y el render los pone contra la pared
# Los efectos que agrega el render (polvo, líneas de movimiento, destellos, primer plano) NO los elige el guion.
EFECTOS_RENDER = ("polvo", "lineas_mov", "destello", "primer_plano")
PROPS = tuple(sorted(n for n in esc.PROPS if n not in ("pedazo", "microfono", "mesa", "estante") + EFECTOS_RENDER))
# Lo que puede pedir el guion: la biblioteca, los dibujos guardados y "dibujo_nuevo" (Claude lo dibuja, dibujos.py)
DIBUJO_NUEVO = "dibujo_nuevo"


def _props_guion() -> tuple:
    from . import dibujos

    return tuple(sorted(set(PROPS) | set(dibujos.biblioteca()))) + (DIBUJO_NUEVO,)


PROPS_GUION = _props_guion()

from . import escenas_lib as _lib  # noqa: E402


def _acciones_guion() -> list[str]:
    """La biblioteca de escenas (las de código y las recetas guardadas), "libre" y "nueva"."""
    return sorted(_lib.todas_las_acciones()) + [_lib.LIBRE, "nueva"]
TRANSICIONES = ("corte", "fundido", "zoom", "barrido")


class SinCandidato(RuntimeError):
    """Ningún candidato de hoy llegó al puntaje (o no queda ninguno en la rotación): no sale video."""


class GuionInvalido(RuntimeError):
    pass


class GuionesFallidos(RuntimeError):
    """Hubo marcas de 8 pero ningún guion validó: NO es "no hay candidato" (2026-11-15: Popeyes falló 16
    veces en el día). Esas marcas quedan afuera hoy y quien llama reintenta más tarde con otras."""


FALLIDOS = "animacion_fallidos"   # bot_estado, animacion_fallidos:<día>: marcas cuyo guion no validó hoy


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


def fallidos_de(conn, hoy: date) -> set[str]:
    try:
        return set(json.loads(_get_valor(conn, f"{FALLIDOS}:{hoy.isoformat()}") or "[]"))
    except ValueError:
        return set()


def anotar_fallidos(conn, hoy: date, marcas_: list[str]) -> None:
    from clips_bot import db

    if conn is None:
        return
    db.set_valor(conn, f"{FALLIDOS}:{hoy.isoformat()}", json.dumps(sorted(fallidos_de(conn, hoy) | set(marcas_)),
                                                                   ensure_ascii=False))


def candidatos(conn, catalogo: list[Marca], hoy: date, n: int = 8, azar=None,
               dias: int = DIAS_SIN_REPETIR_MARCA, excluir: set | None = None) -> list[tuple[Marca, str]]:
    """`n` candidatos que pasan la rotación, de marcas DISTINTAS. El ángulo de cada marca sale al azar
    con más peso para los que no son "origen" (casi todas lo tienen: así no son todos iguales)."""
    excluir = excluir or set()
    # la semilla cambia con lo ya excluido: el segundo video del día (o un reintento) ve otras marcas
    azar = azar or random.Random(hoy.toordinal() * 1000 + len(excluir))
    por_marca: dict[str, list[str]] = {}
    marcas = {}
    for m, a in disponibles(conn, catalogo, hoy, dias):
        if m.nombre in excluir:
            continue
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
    aviso: str = ""        # "⚠️ salió con puntaje 6,5" o "📦 del banco de reserva" (Santi, 2026-11-15)
    banco_id: str = ""

    @property
    def promedio(self) -> float:
        return round(sum(self.notas[c] for c in CRITERIOS) / len(CRITERIOS), 2)


def elegir(cliente, cands: list[tuple[Marca, str, str]], minimo: float = PUNTAJE_MIN,
           todos: dict | None = None) -> list[Elegido]:
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
        if not isinstance(i, int) or not 0 <= i < len(cands):
            continue
        if c.get("sensible"):
            if todos is not None:
                todos[i] = "tema sensible"
            continue
        notas = {k: max(1, min(10, int(c.get(k) or 1))) for k in CRITERIOS}
        e = Elegido(cands[i][0], cands[i][1], notas, str(c.get("dato") or ""))
        if todos is not None:
            todos[i] = e.promedio
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
              "cohete", "camion", "reloj_bolsillo", "megafono", "trofeo", "pelota", "jarron", "moneda", "billete",
              "cubo_rubik"}
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
que dice la frase. La MAYORÍA de las escenas son ACCIÓN de la historia: gente fabricando (`fabricar`),
inventando (`martillar`, `pensar` con la idea), vendiendo (`vender`), usando o probando el producto (`usar`,
`probar`), corriendo, festejando; máquinas, multitudes (`multitud`: true pone gente atrás festejando o
caminando, para un lanzamiento, una cola, una fábrica llena, un estadio). NADA de dos personas paradas
hablando: un diálogo solo si la historia lo pide, corto, y como mucho en 2 escenas.

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

REGLA 5 — GANCHO PROPIO DE ESTA MARCA (Santi, 2026-11-15). La escena 1 muestra EL momento más
sorprendente o visual de ESTA historia, sacado del texto, en el lugar donde pasó (en Kleenex: algo de su
origen real, no un chico tirando una botella). NADA de "un chico rompe cosas en un living" (eso fue el
gancho de Nerf, porque Nerf era justo eso): la `cadena` va VACÍA salvo que la historia sea de algo que rompe
cosas. Nunca repetir el arranque de un video anterior (te paso los últimos: otro lugar, otra acción, otro
objeto).

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

REGLA 8 — ESCENARIOS SEGÚN LA ESCENA. Cada momento pasa DONDE corresponde a la historia (`fondo`):
fábrica, laboratorio, oficina de época, calle, tienda, hospital, campo, puerto, escenario, casa…; la casa
y el taller solo si la historia pasa ahí. Cuando cambia el momento, cambia el lugar: al menos 3 lugares
distintos en el video y nunca más de 2 escenas seguidas en el mismo. Muy visual. Los personajes reaccionan
con el cuerpo y la cara (`cara`); nunca dos en el mismo lugar (cada uno en su `desde`, sin cruzarse).

REGLA 11 — EL OBJETO DESDE EL PRINCIPIO (Santi, 2026-11-15). El gancho MUESTRA el protagonista (el producto)
o el momento clave de su historia: en el cubo de Rubik se ve el cubo (de colores, girando, alguien intentando
resolverlo). El `protagonista` va en los `objetos` de la escena 1.

REGLA 12 — ACCIONES ESPECÍFICAS. Mostrá lo concreto de ESTA historia: el objeto, la máquina, el ingrediente o
el proceso real (Rubik armando el cubo con piezas y girando las caras: `fabricar` con el cubo en la mano y
`gira`). `martillar` y los engranajes solo si de verdad se martilla o hay una máquina de engranajes.

REGLA 13 — PERSONAJES FIELES Y ÉPOCA. Cada actor lleva `genero` (hombre/mujer), `edad` (chico, joven, adulto,
mayor) y, si es una persona real del texto, `persona_real` con su nombre (vacío si no): el protagonista real
coincide con la persona (Ernő Rubik es un hombre adulto). `anio_escena`: el año del momento que muestra la
escena (también el gancho, si muestra un momento del pasado; 0 si es hoy): la decoración sale de ese año
(nada de monitores en 1974).

REGLA 14 — SI FALTA UN DIBUJO. Si la escena necesita algo que no está en la lista de objetos (un cubo de
Rubik, una lupa de detective), poné `prop` = dibujo_nuevo y en `dibujo` un nombre corto en minúsculas con
guiones bajos (ej. cubo_rubik), y agregalo en `dibujos_nuevos` con qué es (forma, colores, sin texto ni
logos): se dibuja para este video y queda guardado. Para un personaje que no está (un detective), usá un
rol parecido con un objeto que lo identifique (un dibujo nuevo en la mano). En los demás objetos, `dibujo`
vacío.

REGLA 15 — LO QUE SE VE ES LO QUE DICE LA VOZ (Santi, 2026-11-15). Cada escena muestra la ACCIÓN CONCRETA de
su frase, con una escena de la BIBLIOTECA (`accion_escena`) y su `plano`:
{{BIBLIOTECA}}
Planos: arriba (cenital: las manos sobre la mesa), manos (primer plano de las manos), lejos, espaldas, cerca,
frente (cada acción tiene los suyos; si pedís otro, va el primero). Ej.: "armó un rompecabezas" = armar_mesa
desde arriba o de espaldas en la mesa; "lo vendió" = vender_tienda; "vendió millones" = contador_ventas. El
objeto protagonista se MUEVE (gira, se resuelve, avanza en la cinta, vuela al barco, se apila). Usá `libre`
(actores y objetos como hasta ahora) solo si ninguna sirve, y como mucho en 4 de cada 10 escenas; si la acción
no está y la vas a necesitar seguido, `nueva` con `accion_nueva` = un nombre corto (se guarda para reusarla).
`festejar` o `saltar` SOLO cuando la frase habla de un éxito; engranajes, martillo, el taller y la fábrica SOLO
si la frase habla de una máquina, un taller o una fábrica. NADIE PARADO SIN HACER NADA: cada persona hace algo
de lo que dice la frase (nada de `quieto`, ni una escena solo con `pensar` o `senalar`). EL GANCHO (escena 1)
es lo más importante del video (en Facebook se va el 65 % entre el segundo 3 y el 7): el momento MÁS
SORPRENDENTE de la historia, con ACCIÓN y el objeto protagonista a la vista; nunca objeto_gira, contador_ventas,
reunion, estantes_llenan ni el fondo `escenario`.

REGLA 10 — PERSONAJES SEGÚN LA HISTORIA Y LA ÉPOCA. Elegí los `rol` que hay en esa historia (obrero, obrera,
científica, inventora, médico, enfermera, granjero, marinero, cocinero, deportista, empresario, vendedor,
cliente, estudiante…): al menos 3 roles distintos en el video. Los chicos (nene, nena) solo si la historia
tiene chicos.

REGLA 9 — SUBTÍTULOS CON GANCHO. En cada frase y en cada comentario de Tito marcá `claves`: 0 a 2
palabras COPIADAS TAL CUAL del texto que más importan (un nombre, un número o año, la palabra del giro o
la del chiste); salen más grandes y en color. Y `emoji` (ninguno, explosion si algo se rompe, plata si hay
plata, susto en una sorpresa, risa en el chiste): pocas veces, solo cuando suma (como mucho uno cada 2 o 3
frases).

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
- `cadena` (casi siempre VACÍA; solo en el gancho y solo si la historia es de algo que rompe cosas, 2 a
  4): las cosas que se rompen una tras otra, cada una con `prop`, `soporte` y `donde`.
- `multitud`: true si en esa escena hay mucha gente (un lanzamiento, una cola, una fábrica llena).
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
    "cara": {"type": "STRING", "enum": list(ac.CARAS)},
    "genero": {"type": "STRING", "enum": list(ac.GENEROS)},
    "edad": {"type": "STRING", "enum": list(ac.EDADES)},
    "persona_real": {"type": "STRING"}},
    "required": ["rol", "accion", "desde", "hacia", "cara", "genero", "edad", "persona_real"]}
_OBJETO = {"type": "OBJECT", "properties": {
    "prop": {"type": "STRING", "enum": list(PROPS_GUION)},
    "efecto": {"type": "STRING", "enum": list(ac.EFECTOS)},
    "donde": {"type": "STRING", "enum": list(ac.LADOS)},
    "soporte": {"type": "STRING", "enum": list(ac.SOPORTES)},
    "texto": {"type": "STRING"}, "dibujo": {"type": "STRING"}},
    "required": ["prop", "efecto", "donde", "soporte", "texto", "dibujo"]}
_CADENA = {"type": "OBJECT", "properties": {
    "prop": {"type": "STRING", "enum": sorted(ROMPIBLES)},
    "soporte": {"type": "STRING", "enum": list(ac.SOPORTES)},
    "donde": {"type": "STRING", "enum": list(ac.LADOS)}},
    "required": ["prop", "soporte", "donde"]}
EMOJIS_SUB = ("ninguno", "explosion", "plata", "susto", "risa")
_CLAVES = {"type": "ARRAY", "items": {"type": "STRING"}}
_EMOJI = {"type": "STRING", "enum": list(EMOJIS_SUB)}
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
                "claves": _CLAVES, "emoji": _EMOJI, "multitud": {"type": "BOOLEAN"},
                "anio_escena": {"type": "INTEGER"},
                "accion_escena": {"type": "STRING"},   # sin enum: la gramática de Claude se pasaba de tamaño (15/11)
                "plano": {"type": "STRING"},
                "accion_nueva": {"type": "STRING"},
            },
            "required": ["frase", "parte", "fondo", "actores", "objetos", "camara", "texto_pantalla",
                         "transicion", "cadena", "viaje_a_anio", "vuelve_al_presente", "claves", "emoji",
                         "multitud", "anio_escena", "accion_escena", "plano", "accion_nueva"]}},
        "locutor": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "despues_de_frase": {"type": "INTEGER"}, "texto": {"type": "STRING"},
            "claves": _CLAVES, "emoji": _EMOJI},
            "required": ["despues_de_frase", "texto", "claves", "emoji"]}},
        "protagonista": {"type": "OBJECT", "properties": {
            "prop": {"type": "STRING"},
            "que_es": {"type": "STRING"}, "dibujo": {"type": "STRING"}},
            "required": ["prop", "que_es", "dibujo"]},
        "dibujos_nuevos": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "nombre": {"type": "STRING"}, "descripcion": {"type": "STRING"}},
            "required": ["nombre", "descripcion"]}},
        "entidades": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "nombre": {"type": "STRING"}, "presentacion": {"type": "STRING"},
            "frase": {"type": "INTEGER"}}, "required": ["nombre", "presentacion", "frase"]}},
    },
    "required": ["titulo", "descripcion", "tono", "pregunta_gancho", "escenas", "locutor", "entidades",
                 "protagonista", "dibujos_nuevos"],
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
        if i > 1 and cadena:
            errores.append(f"escena {i}: la `cadena` va solo en el gancho (y casi siempre vacía)")
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


def prop_real(o: dict) -> str:
    """El nombre del dibujo de un objeto del guion (el de la biblioteca o el `dibujo` de un dibujo_nuevo)."""
    return str(o.get("dibujo") or "").strip() if o.get("prop") == DIBUJO_NUEVO else str(o.get("prop") or "")


_EXITO = re.compile(r"\b(éxito|exito|vend\w*|mill[oó]n\w*|r[eé]cord\w*|famos\w*|triunf\w*|gan[oó]|furor|"
                    r"el m[aá]s|la m[aá]s|celebr\w*|festej\w*|lo logr\w*|funcion[oó])\b", re.I)
_MAQUINA = re.compile(r"\b(m[aá]quina\w*|maquinaria|taller\w*|herramient\w*|motor\w*|f[aá]brica\w*|fabric\w*|"
                      r"mec[aá]nic\w*|engranaje\w*|industria\w*|planta)\b", re.I)


def errores_accion(d: dict) -> list[str]:
    """Regla 15: la escena muestra lo que dice la frase (biblioteca), festejar solo con éxito, engranajes y
    martillo solo con máquinas o taller, y el gancho en su época."""
    errores = []
    escenas = d.get("escenas") or []
    libres = [i for i, e in enumerate(escenas, 1) if (e.get("accion_escena") or _lib.LIBRE) == _lib.LIBRE]
    if len(escenas) >= 5 and len(libres) > len(escenas) * 0.4:
        errores.append(f"demasiadas escenas `libre` ({', '.join(map(str, libres))}): usá la escena de la biblioteca "
                       "que muestra lo que dice cada frase")
    validas = set(_acciones_guion())
    # El gancho (Santi, 2026-11-15: en Facebook se va el 65 % entre el segundo 3 y el 7): el momento más
    # sorprendente CON ACCIÓN y el objeto protagonista; nada de escenario vacío, contador ni reunión.
    if escenas:
        e1 = escenas[0]
        if e1.get("accion_escena") in GANCHO_SIN_ACCION or e1.get("fondo") == "escenario":
            errores.append("el gancho (escena 1) es lo más importante del video: mostrá el momento más sorprendente "
                           "de la historia CON ACCIÓN (alguien haciendo algo con el objeto protagonista, en su lugar), "
                           f"no {e1.get('accion_escena') or e1.get('fondo')}")
    # Nadie parado sin hacer nada (Santi, 2026-11-15).
    for i, e in enumerate(escenas, 1):
        if (e.get("accion_escena") or _lib.LIBRE) != _lib.LIBRE:
            continue
        quietos = [a.get("persona_real") or a.get("rol") for a in e.get("actores") or []
                   if a.get("accion") in QUIETAS]
        if quietos and len(quietos) == len(e.get("actores") or []) or any(
                a.get("accion") == "quieto" for a in e.get("actores") or []):
            errores.append(f"escena {i}: {', '.join(map(str, quietos)) or 'alguien'} parado sin hacer nada: que "
                           "cada persona haga algo de lo que dice la frase (fabricar, vender, usar, probar, caminar…)")
    # Variedad (2026-11-15, la prueba del Rubik: 5 de 10 escenas eran el cubo girando en el escenario).
    for accion, tope in (("objeto_gira", 2), ("contador_ventas", 1)):
        usos = [i for i, e in enumerate(escenas, 1) if e.get("accion_escena") == accion]
        if len(usos) > tope:
            errores.append(f"`{accion}` en {len(usos)} escenas ({', '.join(map(str, usos))}): como mucho {tope}; "
                           "en las otras mostrá la acción que dice la frase (quién hace qué y dónde)")
    for i, e in enumerate(escenas, 1):
        frase = str(e.get("frase") or "")
        if (e.get("accion_escena") or _lib.LIBRE) not in validas:
            errores.append(f"escena {i}: `accion_escena` {e.get('accion_escena')!r} no existe (elegí una de: "
                           f"{', '.join(sorted(validas))})")
        if (e.get("plano") or "") and e.get("plano") not in _lib.PLANOS:
            errores.append(f"escena {i}: `plano` {e.get('plano')!r} no existe ({', '.join(_lib.PLANOS)})")
        if e.get("accion_escena") == "nueva" and not str(e.get("accion_nueva") or "").strip():
            errores.append(f"escena {i}: `nueva` necesita `accion_nueva` (un nombre corto)")
        libre = (e.get("accion_escena") or _lib.LIBRE) == _lib.LIBRE    # las de la biblioteca arman sus actores
        if libre and any(a.get("accion") in ("festejar", "saltar") for a in e.get("actores") or []) \
                and not _EXITO.search(frase):
            errores.append(f"escena {i}: festejan o saltan pero la frase no habla de un éxito: mostrá lo que dice "
                           f"(«{frase[:60]}»)")
        maquina = libre and (any(a.get("accion") == "martillar" for a in e.get("actores") or [])
                   or any(prop_real(o) in ("engranaje", "martillo") for o in e.get("objetos") or [])
                   or e.get("fondo") in ("taller", "fabrica") and (e.get("accion_escena") or _lib.LIBRE) == _lib.LIBRE)
        if maquina and not _MAQUINA.search(frase):
            errores.append(f"escena {i}: martillo, engranajes o taller sin que la frase hable de una máquina o un "
                           "taller: usá el lugar y la acción de lo que dice")
    anios = [int(x) for x in re.findall(r"\b(1[5-9]\d\d)\b", " ".join(str(e.get("frase") or "") for e in escenas))]
    if escenas and anios and min(anios) < 1990:
        e1 = escenas[0]
        if e1.get("fondo") in ("oficina", "taller", "laboratorio", "fabrica") and \
                not int(e1.get("anio_escena") or 0) and (e1.get("accion_escena") or "") != "objeto_gira":
            errores.append(f"el gancho muestra el momento clave en un interior: poné su año en `anio_escena` "
                           f"({min(anios)}: nada de monitores ni cosas de hoy)")
    return errores


def errores_fieles(d: dict) -> list[str]:
    """Reglas 11-14 (Santi, 2026-11-15): el protagonista en el gancho, acciones específicas, personajes fieles,
    época por escena y los dibujos nuevos bien pedidos."""
    from . import dibujos

    errores = []
    escenas = d.get("escenas") or []
    pr = d.get("protagonista") or {}
    prota = prop_real(pr)
    if escenas and prota and not any(prop_real(o) == prota for o in escenas[0].get("objetos") or []) \
            and not any(c.get("prop") == prota for c in escenas[0].get("cadena") or []):
        errores.append(f"el gancho (escena 1) tiene que MOSTRAR el protagonista ({prota}): ponelo en sus `objetos`")
    nuevos = {str(x.get("nombre") or "").strip() for x in d.get("dibujos_nuevos") or []}
    for x in d.get("dibujos_nuevos") or []:
        if not dibujos.nombre_valido(x.get("nombre")):
            errores.append(f"dibujo nuevo {x.get('nombre')!r}: nombre corto en minúsculas con guiones bajos")
    pedidos = [prop_real(o) for e in escenas for o in e.get("objetos") or [] if o.get("prop") == DIBUJO_NUEVO]
    if pr.get("prop") == DIBUJO_NUEVO:
        pedidos.append(prota)
    for n_ in pedidos:
        if n_ not in nuevos and not esc.es_prop(n_):
            errores.append(f"`{n_}` es un dibujo nuevo que no está en `dibujos_nuevos` (agregalo con qué es)")
    martillos = sum(1 for e in escenas if any(a.get("accion") == "martillar" for a in e.get("actores") or []))
    engranajes = sum(1 for e in escenas if any(prop_real(o) == "engranaje" for o in e.get("objetos") or []))
    if martillos > 1 or engranajes > 1:
        errores.append("acciones genéricas (martillo o engranajes en varias escenas): mostrá el proceso real de "
                       "ESTA historia (`fabricar` con el objeto en la mano, la máquina, el ingrediente)")
    personas: dict[str, set] = {}
    for e in escenas:
        for a in e.get("actores") or []:
            if str(a.get("persona_real") or "").strip():
                personas.setdefault(a["persona_real"].strip(), set()).add((a.get("genero"), a.get("edad") == "chico"))
    for nombre, vistos in personas.items():
        if len({g for g, _ in vistos}) > 1:
            errores.append(f"{nombre} aparece como hombre y como mujer: tiene que ser siempre igual (fiel a la persona)")
    return errores


def errores_protagonista(d: dict) -> list[str]:
    """Regla 7: el objeto de la historia, dibujado con detalle (no un rótulo) y en 2 escenas o más."""
    errores = []
    pr = d.get("protagonista") or {}
    prop = prop_real(pr)
    nuevos = {str(x.get("nombre") or "").strip() for x in d.get("dibujos_nuevos") or []}
    if prop not in DETALLADOS and prop not in nuevos and not (prop and esc.es_prop(prop) and prop not in esc.PROPS):
        errores.append(f"`protagonista`: {prop!r} no es un objeto dibujado con detalle (elegí uno de: "
                       f"{', '.join(sorted(DETALLADOS))})")
    elif not str(pr.get("que_es") or "").strip():
        errores.append("`protagonista`: falta `que_es`")
    else:
        apariciones = 0
        for e in d.get("escenas") or []:
            en_objetos = any(prop_real(o) == prop for o in e.get("objetos") or [])
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


# ---- gancho propio, lugares, acción y personajes (Santi, 2026-11-15; regla permanente) -------------------
LUGARES_MIN = 3
MISMO_LUGAR_SEGUIDO = 2
SOLO_SI_PASA_AHI = {"casa": 2, "taller": 2}      # como mucho estas escenas en estos lugares
DIALOGOS_MAX = 2
ROLES_MIN = 3
GANCHOS_RECIENTES = "animacion_ganchos"          # bot_estado: los arranques de los últimos videos
GANCHOS_GUARDADOS = 12
# El arranque de Nerf (el ejemplo con el que se armó el canal) cuenta siempre como "ya usado".
GANCHO_NERF = {"marca": "Nerf", "fondo": "casa", "cadena": True, "props": ["pelota_espuma", "tele", "lampara", "cuadro"],
               "acciones": ["tirar", "retar"], "frase": "¡Una pelota destrozó el living entero!"}


def firma_gancho(d: dict, marca: str = "") -> dict:
    e = (d.get("escenas") or [{}])[0]
    props = [o.get("prop") for o in e.get("objetos") or []] + [c.get("prop") for c in e.get("cadena") or []]
    return {"marca": marca, "fondo": e.get("fondo"), "cadena": bool(e.get("cadena")),
            "props": sorted({x for x in props if x}), "acciones": sorted({a.get("accion") for a in e.get("actores") or []
                                                                         if a.get("accion")}),
            "frase": str(e.get("frase") or "")[:120]}


def ganchos_recientes(conn) -> list[dict]:
    try:
        guardados = json.loads(_get_valor(conn, GANCHOS_RECIENTES) or "[]")
    except ValueError:
        guardados = []
    return [GANCHO_NERF] + guardados


def anotar_gancho(conn, d: dict, marca: str) -> None:
    from clips_bot import db

    guardados = ganchos_recientes(conn)[1:]
    guardados.append(firma_gancho(d, marca))
    db.set_valor(conn, GANCHOS_RECIENTES, json.dumps(guardados[-GANCHOS_GUARDADOS:], ensure_ascii=False))


def _get_valor(conn, clave: str):
    from clips_bot import db

    return db.get_valor(conn, clave) if conn is not None else None


def texto_ganchos(previos: list[dict]) -> str:
    return "\n".join(f"- {g.get('marca') or '?'}: {g.get('frase')} (lugar {g.get('fondo')}, acciones "
                     f"{', '.join(g.get('acciones') or []) or '-'}, objetos {', '.join(g.get('props') or []) or '-'}"
                     + (", destrucción en cadena" if g.get("cadena") else "") + ")" for g in previos)


def errores_gancho_repetido(escenas: list[dict], previos: list[dict]) -> list[str]:
    """El arranque no puede parecerse al de un video anterior: otra destrucción en cadena, o el mismo lugar
    con la misma acción o el mismo objeto."""
    if not escenas:
        return []
    f = firma_gancho({"escenas": escenas})
    for g in previos:
        if f["cadena"] and g.get("cadena"):
            return [f"el gancho repite la destrucción en cadena de {g.get('marca')}: mostrá el momento más "
                    "sorprendente de ESTA historia (vaciá `cadena`)"]
        if f["fondo"] == g.get("fondo") and (set(f["acciones"]) & set(g.get("acciones") or [])
                                              or set(f["props"]) & set(g.get("props") or [])):
            return [f"el gancho se parece al de {g.get('marca')} ({g.get('fondo')}, "
                    f"{', '.join(g.get('acciones') or [])}): cambiá el lugar y la acción del arranque"]
    return []


def errores_lugares_y_personajes(escenas: list[dict]) -> list[str]:
    errores = []
    fondos = [e.get("fondo") for e in escenas]
    if len(escenas) >= 5 and len(set(fondos)) < LUGARES_MIN:
        errores.append(f"usá al menos {LUGARES_MIN} lugares distintos (`fondo`): cada momento donde pasó "
                       f"(hay {', '.join(sorted(set(f for f in fondos if f)))})")
    seguidas = 1
    for a, b in zip(fondos, fondos[1:]):
        seguidas = seguidas + 1 if a == b else 1
        if seguidas > MISMO_LUGAR_SEGUIDO:
            errores.append(f"más de {MISMO_LUGAR_SEGUIDO} escenas seguidas en {b}: cuando cambia el momento, "
                           "cambia el lugar")
            break
    for lugar, tope in SOLO_SI_PASA_AHI.items():
        if fondos.count(lugar) > tope:
            errores.append(f"{fondos.count(lugar)} escenas en {lugar}: como mucho {tope} (solo si la historia "
                           "pasa ahí)")
    dialogos = [str(i) for i, e in enumerate(escenas, 1) if e.get("actores") and not e.get("multitud")
                and all(a.get("accion") in ("quieto", "senalar", "pensar", "retar") for a in e["actores"])
                and not any(o.get("efecto") in ac.DINAMICOS for o in e.get("objetos") or [])]
    if len(dialogos) > DIALOGOS_MAX:
        errores.append(f"demasiadas escenas de gente hablando ({', '.join(dialogos)}): como mucho {DIALOGOS_MAX}; "
                       "el resto, acción (fabricar, vender, usar, probar, multitud…)")
    roles = [a.get("rol") for e in escenas for a in e.get("actores") or []]
    if len(escenas) >= 5 and len(set(roles)) < ROLES_MIN:
        errores.append(f"usá al menos {ROLES_MIN} personajes distintos (`rol`) según la historia y la época")
    con_chicos = sum(1 for e in escenas if any(a.get("rol") in ac.NINOS for a in e.get("actores") or []))
    if con_chicos > max(2, len(escenas) // 3):
        errores.append(f"los chicos (nene, nena) están en {con_chicos} escenas: solo si la historia tiene chicos")
    return errores


def validar_guion(d: dict, m: Marca, fuente: str, ganchos_previos: list[dict] | None = None) -> list[str]:
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
    errores += errores_lugares_y_personajes(escenas)
    errores += errores_gancho_repetido(escenas, ganchos_previos or [])
    errores += errores_protagonista(d)
    errores += errores_fieles(d)
    errores += errores_accion(d)
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
            if a.get("genero") and a.get("genero") not in ac.GENEROS:
                errores.append(f"escena {i}: genero {a.get('genero')!r} (hombre o mujer)")
            if a.get("rol") not in ac.ROLES or a.get("accion") not in ac.ACCIONES:
                errores.append(f"escena {i}: actor {a.get('rol')!r}/{a.get('accion')!r} no existe")
        for o in objetos:
            if (o.get("prop") not in PROPS and o.get("prop") != DIBUJO_NUEVO and not esc.es_prop(o.get("prop"))) \
                    or o.get("efecto") not in ac.EFECTOS:
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
    # Los números chicos (hasta 12) son palabras de todos los días ("dos hermanos", "cuatro amigos"), no
    # cifras: el 15/11 el guion de Popeyes falló 8 veces porque "2" y "4" no estaban en el artículo.
    faltan = [x for x in no_respaldados(texto, base) if not (x.isdigit() and int(x) <= NUMERO_CHICO)]
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


def sistema_guion() -> str:
    """El prompt del guion con la biblioteca de escenas de hoy (las recetas guardadas también)."""
    lista = "\n".join(f"  - {k}: {v}" for k, v in sorted(_lib.todas_las_acciones().items()))
    return SISTEMA_GUION.replace("{BIBLIOTECA}", lista)


def escribir_guion(cliente, e: Elegido, fuente: str, reintentos: int = 6, avisar=log.info,
                   revisor=None, extra: str = "", ganchos_previos: list[dict] | None = None) -> dict:
    """El guion validado (dict del schema). Primero el chequeo del código; si pasa, el de Haiku
    (`revisor`). Si no valida, reintenta con los errores; si nunca valida, GuionInvalido."""
    pedido = (f"MARCA: {e.marca.nombre} ({e.marca.pais})\nÁNGULO: {e.angulo} — {ANGULOS[e.angulo]}\n"
              f"Dato para el gancho (sugerido): {e.dato}\n\nTEXTO (Wikipedia; los datos salen SOLO de "
              f"acá):\n{fuente[:20000]}" + (f"\n\n{extra}" if extra else "")
              + ("\n\nARRANQUES DE LOS VIDEOS ANTERIORES (el tuyo tiene que ser distinto: otro lugar, otra "
                 "acción, otro objeto):\n" + texto_ganchos(ganchos_previos) if ganchos_previos else ""))
    from clips_bot.gemini import GeminiError

    from clips_bot import correcciones

    # Corregir solo lo que falla (Santi, 2026-11-15): con un guion entero que no valida, se piden SOLO las
    # escenas o los campos a cambiar; recién con CORRECCIONES_MAX correcciones fallidas seguidas, el guion
    # entero de nuevo. Cada pedido (entero o corrección) cuenta como un intento.
    correccion, ultimo, d, puntuales = "", [], None, 0
    for intento in range(reintentos):
        try:
            if d is not None and ultimo and puntuales < correcciones.CORRECCIONES_MAX:
                puntuales += 1
                d = correcciones.corregir(cliente, sistema_guion(), pedido, d, ultimo, SCHEMA_GUION, "escenas",
                                          "escena")
            else:
                puntuales = 0
                d = json.loads(cliente.json(sistema_guion(), pedido + correccion, SCHEMA_GUION, 0.9))
        except GeminiError as err:   # ClaudeError hereda: una respuesta cortada cuenta como un intento
            if getattr(err, "pasajero", False):
                raise
            ultimo = [str(err)[:200]]
            avisar(f"guion de {e.marca.nombre} ({e.angulo}), intento {intento + 1}: {ultimo[0]}")
            continue
        except ValueError as err:     # JSON roto: otro intento
            ultimo = [f"respuesta que no es JSON: {str(err)[:120]}"]
            continue
        ultimo = validar_guion(d, e.marca, fuente, ganchos_previos)
        if not ultimo:
            ultimo = chequear_calidad(revisor, d, e.marca)
        if not ultimo:
            return d
        avisar(f"guion de {e.marca.nombre} ({e.angulo}), intento {intento + 1}"
               f"{' (corrección puntual)' if puntuales else ''}: {'; '.join(ultimo)[:400]}")
        if puntuales >= correcciones.CORRECCIONES_MAX:
            correccion = ("\n\nTU GUION ANTERIOR:\n" + describir(d) +
                          "\n\nNO SIRVIÓ POR ESTO (corregilo y devolvé el guion entero):\n- " + "\n- ".join(ultimo))
    raise GuionInvalido(f"{e.marca.nombre} ({e.angulo}): {'; '.join(ultimo)[:400]}")


def guardar_acciones_nuevas(d: dict) -> None:
    """Las escenas `nueva` quedan en la biblioteca como receta (el protagonista y los roles como variables)."""
    prota = prop_real(d.get("protagonista") or {})
    for e in d.get("escenas") or []:
        if e.get("accion_escena") == "nueva" and str(e.get("accion_nueva") or "").strip():
            nombre = re.sub(r"[^a-z0-9_]", "_", str(e["accion_nueva"]).lower())[:30]
            spec = json.loads(json.dumps(e))
            for o in spec.get("objetos") or []:
                if prop_real(o) == prota:
                    o["prop"], o["dibujo"] = "{objeto}", ""
            try:
                _lib.guardar_receta(nombre, str(e.get("frase") or "")[:120], spec)
            except OSError:
                pass
            e["accion_escena"] = nombre if nombre in _lib.recetas() else _lib.LIBRE


def asegurar_dibujos(cliente, d: dict, e: "Elegido", fuente: str, avisar=log.info) -> dict:
    """Dibuja con Claude los `dibujos_nuevos` que no están guardados. Si uno no se puede dibujar, se le pide a
    Claude que reformule esas escenas con objetos de la lista (corrección puntual) y se vuelve a validar."""
    from clips_bot import correcciones

    from . import dibujos

    fallidos = []
    for x in d.get("dibujos_nuevos") or []:
        nombre = str(x.get("nombre") or "").strip()
        if not nombre or esc.es_prop(nombre):
            continue
        try:
            dibujos.dibujar(cliente, nombre, str(x.get("descripcion") or ""), f"{e.marca.nombre}: {e.angulo}")
            avisar(f"dibujo nuevo: {nombre} ({x.get('descripcion')})")
        except Exception as err:  # noqa: BLE001
            avisar(f"no pude dibujar {nombre}: {str(err)[:150]}")
            fallidos.append(nombre)
    if not fallidos:
        return d
    errores = [f"no se pudo dibujar «{n}»: reemplazalo por un objeto de la lista o reformulá esa frase" for n in fallidos]
    try:
        d2 = correcciones.corregir(cliente, sistema_guion(), f"MARCA: {e.marca.nombre}\nTEXTO:\n{fuente[:12000]}",
                                   d, errores, SCHEMA_GUION, "escenas", "escena")
        if not validar_guion(d2, e.marca, fuente) or not fuente:
            return d2
    except Exception as err:  # noqa: BLE001
        avisar(f"no pude reformular sin {fallidos}: {str(err)[:150]}")
    # último recurso: el objeto más parecido de la biblioteca (Santi, 2026-11-16: nunca frena el video)
    resolver_objetos(None, d, e, avisar)
    return d


def resolver_objetos(cliente, d: dict, e: "Elegido | None" = None, avisar=log.info) -> list[str]:
    """Santi, 2026-11-16 ('masa_gris' frenó el video del 16/11: lo trajo la reescritura por duración, después de
    dibujar): TODO objeto del guion que no está en la biblioteca se dibuja con Claude (queda guardado) y, si no
    se puede (o no hay cliente), pasa a ser el más parecido de la biblioteca. Corre después de dibujar, después
    de cada reescritura y antes de armar la línea de tiempo. Devuelve lo que cambió."""
    from . import dibujos

    descr = {str(x.get("nombre") or "").strip(): str(x.get("descripcion") or "") for x in d.get("dibujos_nuevos") or []}
    resueltos: dict[str, str] = {}
    cambios: list[str] = []
    contexto = f"{e.marca.nombre}: {e.angulo}" if e is not None else ""

    def resolver(nombre: str, que_es: str = "") -> str:
        if nombre in resueltos:
            return resueltos[nombre]
        texto = descr.get(nombre) or que_es or nombre.replace("_", " ")
        if cliente is not None and dibujos.nombre_valido(nombre):
            try:
                dibujos.dibujar(cliente, nombre, texto, contexto)
                avisar(f"dibujo nuevo (faltaba): {nombre} ({texto})")
                resueltos[nombre] = nombre
                return nombre
            except Exception as err:  # noqa: BLE001 — si no se puede dibujar, el más parecido
                avisar(f"no pude dibujar {nombre}: {str(err)[:150]}")
        nuevo = esc.prop_parecido(nombre, texto)
        avisar(f"objeto {nombre!r} sin dibujo: va {nuevo!r} (el más parecido de la biblioteca)")
        cambios.append(f"{nombre} → {nuevo}")
        resueltos[nombre] = nuevo
        return nuevo

    def arreglar(o: dict, clave: str = "prop", que_es: str = "") -> None:
        nombre = prop_real(o) if clave == "prop" else str(o.get(clave) or "")
        if not nombre or esc.es_prop(nombre):
            return
        nuevo = resolver(nombre, que_es or str(o.get("que_es") or ""))
        if nuevo != nombre:
            o[clave] = nuevo
            o.pop("dibujo", None)
        elif o.get(clave) != DIBUJO_NUEVO:
            o[clave] = nuevo

    for esc_ in d.get("escenas") or []:
        for o in esc_.get("objetos") or []:
            arreglar(o)
        for c in esc_.get("cadena") or []:
            arreglar(c)
    pr = d.get("protagonista")
    if isinstance(pr, dict):
        arreglar(pr)
    return cambios


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
                    voz: Path | None, presente: int | None = None,
                    subtitulos: str = "viral", visual: bool = False) -> tuple[dict, list[tuple[float, str]]]:
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
    prota = prop_real(d.get("protagonista") or {})
    proyectil = prota if prota in ac.LANZABLES else "pelota"
    vistas: dict[tuple, int] = {}     # (fondo, década) → cuántas veces: la variante, para no repetir igual
    mapa_hecho = False
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
            dv = min(ac.VIAJE_S, max(1.0, dur - 1.0))
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
        vis = (d.get("visual") or [])[k] if visual and k < len(d.get("visual") or []) else ({} if visual else None)
        if vis and vis.get("coords") and not mapa_hecho and dur >= 2.6:
            # el mapa con el pin que hace zoom al lugar, la primera vez que aparece (visuales, 2026-11-15)
            from . import visuales

            mapa_hecho = True
            esc_m, fx = escena_mapa(visuales.MAPA_S, *vis["coords"])
            escenas.append(esc_m)
            sfx += [(round(t + x, 3), s_) for x, s_ in fx]
            t += visuales.MAPA_S
            dur = round(dur - visuales.MAPA_S, 3)
        anio_esc = int(e.get("anio_escena") or 0)
        e = {**e, "objetos": [{**o, "prop": prop_real(o)} for o in e.get("objetos") or [] if prop_real(o)]}
        esc_d, fx = ac.escena_accion(e, dur, k, primera=(k == 0), tono=1.0 if pasado else 0.0,
                                     anio=anio_esc if 1800 <= anio_esc < presente else anio_actual,
                                     variante=variante, reservar=reservar, proyectil=proyectil, visual=vis,
                                     protagonista=prota)
        esc_d["frase"] = k          # para la revisión visual: qué frase del guion es esta escena
        pisados = ac.superposiciones(esc_d)
        if pisados:
            log.warning("escena %d: personajes que se pisan en %s", k + 1, pisados[:3])
        if destino is not None:
            esc_d["transicion"] = {"tipo": "zoom", "duracion": 0.25}
        escenas.append(esc_d)
        sfx += [(round(t + x, 3), s) for x, s in fx]
        t += dur
    if visual:
        reacciones_tito(escenas)
    out = {"fps": P.FPS, "escenas": escenas, "subtitulos_y": SUBTITULOS_Y, "subtitulos_tam": SUBTITULOS_TAM,
           "subtitulos_estilo": subtitulos}
    if voz is not None:
        out["audio"] = str(voz)
    if palabras:
        golpes = [t_ for t_, s_ in sfx if s_ in ("golpe", "vidrio")]
        marcadas = sv.marcar([tx.Palabra(p.texto, p.inicio, p.fin) for p in palabras],
                             segmentos_subtitulos(d), golpes)
        out["subtitulos"] = [{"palabras": [{"texto": p.texto, "inicio": round(p.inicio, 3),
                                            "fin": round(p.fin, 3), "clave": p.clave, "impacto": p.impacto,
                                            "emoji": p.emoji} for p in marcadas]}]
    return out, sorted(sfx)


def escena_mapa(dur: float, lat: float, lon: float) -> tuple[dict, list[tuple[float, str]]]:
    """El mapa del mundo que hace zoom hasta el pin del lugar (fondo cacheado: el pin está en el dibujo)."""
    from . import visuales

    (_, _, _, _), (px, py) = visuales.recorte(lat, lon)
    dx, dy = px - P.ANCHO / 2, py - P.ALTO / 2
    camara = [{"t": 0, "zoom": 1.0, "x": 0, "y": 0}, {"t": dur, "zoom": 2.6, "x": round(dx, 1), "y": round(dy, 1),
                                                     "easing": "suave"}]
    return ({"duracion": dur, "fondo": {"tipo": "mapa_geo", "semilla": visuales.codificar(lat, lon)},
             "transicion": {"tipo": "zoom", "duracion": 0.25}, "camara": camara, "elementos": []},
            [(0.0, "whoosh"), (round(dur * 0.7, 2), "pop")])


def reacciones_tito(escenas: list[dict]) -> None:
    """Tito en una ventanita, en una esquina de arriba, cada ~9 s (sorprendido, riéndose, señalando), solo en
    las escenas de acción (no en sus pausas, el viaje ni el mapa). Esquinas alternadas."""
    from . import visuales

    t, proxima, k = 0.0, visuales.TITO_CADA_S, 0
    for e in escenas:
        dur = float(e["duracion"])
        accion = not e.get("congela") and e.get("fondo", {}).get("tipo") not in ("mapa_geo", "color")
        while accion and t <= proxima < t + dur - 1.2:
            tl = round(proxima - t, 2)
            x = 150 if k % 2 == 0 else 930
            e["elementos"].append({"tipo": "prop", "nombre": "tito_reaccion", "forma": k % 3, "fijo": True,
                                   "x": x, "y": 640, "escala": 0.8, "desde": tl, "hasta": round(tl + 1.6, 2),
                                   "keyframes": [{"t": tl, "escala": 0.05}, {"t": tl + 0.25, "escala": 0.8,
                                                                            "easing": "rebote"},
                                                 {"t": tl + 1.35, "escala": 0.8}, {"t": tl + 1.6, "escala": 0.05,
                                                                                   "easing": "entrada"}]})
            k += 1
            proxima += visuales.TITO_CADA_S
        t += dur
        if not accion and proxima < t:
            proxima = t + 1.0


def segmentos_subtitulos(d: dict) -> list[dict]:
    """Lo que dice la voz, en orden, con lo que el guion marcó para los subtítulos (claves, emoji) y si es
    un REMATE (la frase del giro, la última frase o el chiste de Tito): ahí la clave tiembla."""
    escenas_d = d.get("escenas") or []
    loc = [x for x in d.get("locutor") or [] if str(x.get("texto") or "").strip()]
    out = []
    ultima = len(escenas_d) - 1
    for tipo, k, texto in segmentos(d):
        if tipo == "frase":
            e = escenas_d[k]
            out.append({"texto": texto, "claves": e.get("claves") or [], "emoji": _emoji(e.get("emoji")),
                        "remate": e.get("parte") == "giro" or k == ultima})
        else:
            x = next((y for y in loc if str(y.get("texto") or "").strip() == texto), {})
            out.append({"texto": texto, "claves": x.get("claves") or [], "emoji": _emoji(x.get("emoji")),
                        "remate": x.get("emoji") == "risa"})
    return out


def _emoji(e) -> str:
    return str(e) if e in sv.EMOJIS else ""


# Guiones escritos antes de la REGLA 9 (o si el modelo no marcó nada): una llamada chica (Haiku) marca las
# claves y los emojis SOBRE el guion ya hecho, sin reescribirlo.
SISTEMA_CLAVES = """Marcás los SUBTÍTULOS de un video corto ya escrito (no cambiás ni reescribís nada).
Para cada texto (en orden, con su índice) devolvé `claves`: 0 a 2 palabras COPIADAS TAL CUAL del texto que
más importan para enganchar (un nombre propio, un número o año, la palabra del giro o la del chiste), y
`emoji`: ninguno, explosion (algo se rompe), plata (plata, ventas, millones), susto (una sorpresa) o risa
(el chiste). Emojis POCOS: como mucho uno cada 2 o 3 textos, solo cuando suma."""
SCHEMA_CLAVES = {"type": "OBJECT", "properties": {"textos": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"indice": {"type": "INTEGER"}, "claves": _CLAVES, "emoji": _EMOJI},
    "required": ["indice", "claves", "emoji"]}}}, "required": ["textos"]}


def tiene_claves(d: dict) -> bool:
    return any("claves" in e for e in d.get("escenas") or [])


def marcar_claves(cliente, d: dict) -> dict:
    """Agrega `claves` y `emoji` a cada frase y comentario de Tito de `d` (en el lugar), con una llamada."""
    segs = segmentos(d)
    pedido = "\n".join(f"[{i}] {texto}" for i, (_, _, texto) in enumerate(segs))
    r = json.loads(cliente.json(SISTEMA_CLAVES, pedido, SCHEMA_CLAVES, 0.3))
    por_indice = {int(x.get("indice", -1)): x for x in r.get("textos") or []}
    loc = d.get("locutor") or []
    for i, (tipo, k, texto) in enumerate(segs):
        x = por_indice.get(i, {})
        marca = {"claves": [str(c) for c in x.get("claves") or []][:2],
                 "emoji": _emoji(x.get("emoji")) or "ninguno"}
        if tipo == "frase":
            d["escenas"][k].update(marca)
        else:
            for y in loc:
                if str(y.get("texto") or "").strip() == texto:
                    y.update(marca)
    return d


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
- un texto ilegible o cortado; un subtítulo tapando algo importante;
- (Santi, 2026-11-15) el GANCHO (cuadro 1) no muestra algo de la historia de ESTA marca, o es genérico ("un
  chico rompiendo cosas en un living") o se parece a los arranques anteriores que te paso;
- un LUGAR que no tiene sentido para lo que dice la frase (una fábrica contada en un living), o el mismo
  lugar repetido cuando la historia ya cambió de momento;
- dos personas paradas hablando cuando la frase cuenta una acción;
- (2026-11-15) el gancho NO muestra el producto protagonista ni el momento clave de su historia;
- una acción genérica (martillo, engranajes) cuando la frase cuenta un proceso concreto;
- un personaje que no coincide con la persona real (otro género, otra edad, ropa de otra época);
- algo fuera de época para el año de esa escena (un monitor moderno en 1974, un celular en 1950).
Para estos usá `arreglo` = otro y decí en `que` qué escena y qué cambiar.
- (2026-11-15) LA ACCIÓN QUE SE VE NO ES LA QUE DICE LA FRASE (alguien salta cuando la voz dice que arma algo;
  gente parada con los brazos abiertos frente a engranajes) o PERSONAS PARADAS SIN HACER NADA en cualquier
  escena: `arreglo` = cambiar_accion y en `que` decí qué se ve y qué tendría que verse. Esa escena se rehace.
- (2026-11-15) EL GANCHO (cuadro 1) repetido de un arranque anterior, genérico, sin acción, con gente parada o
  sin el objeto protagonista: `arreglo` = rehacer_gancho y en `que` decí cuál sería el momento más sorprendente
  de ESTA historia con acción. Es lo más importante del video (en Facebook se va el 65 % entre el segundo 3 y
  el 7): se rehace solo.
Para cada problema: `cuadro` (el número), `que` (corto) y `arreglo`: mover_objeto (a otro lugar),
cambiar_soporte (apoyarlo en otro lado), sacar_objeto, separar_personajes, sacar_texto u otro; y
`objeto` (el nombre del objeto, si es un objeto). Si está todo bien, lista vacía. No inventes problemas."""

SCHEMA_REVISION = {"type": "OBJECT", "properties": {"problemas": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {
        "cuadro": {"type": "INTEGER"}, "que": {"type": "STRING"},
        "arreglo": {"type": "STRING", "enum": ["mover_objeto", "cambiar_soporte", "sacar_objeto",
                                               "separar_personajes", "sacar_texto", "cambiar_accion",
                                               "rehacer_gancho", "otro"]},
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


GANCHO_REHACER = ("el GANCHO (escena 1) es lo más importante del video (en Facebook se va el 65 % entre el segundo 3 "
                  "y el 7): mostrá el momento MÁS SORPRENDENTE de esta historia CON ACCIÓN (alguien haciendo algo, en "
                  "su lugar) y el objeto protagonista a la vista; nada de escenario vacío, gente parada, el objeto "
                  "girando solo ni un arranque anterior del canal")


def corregir_acciones(cliente, d: dict, e: "Elegido", fuente: str, malas: list[tuple[int, str]],
                      claves: list, datos: dict, avisar=log.info, ganchos: str = "") -> tuple[dict, str]:
    """La revisión vio algo que se corrige en el guion (una acción que no es la de la frase, gente parada, el
    gancho repetido o sin acción): se corrige SOLO esa escena (corrección puntual) y se vuelve a validar; si no
    valida, queda como estaba. `ganchos`: los arranques anteriores del canal (para no repetirlos)."""
    from clips_bot import correcciones

    errores = []
    for n_, que in malas:
        if 0 <= n_ < len(claves):
            k = datos["escenas"][claves[n_][1]].get("frase")
            if not isinstance(k, int):
                continue
            if k == 0 or claves[n_][2] == "gancho":
                errores.append(f"escena 1: {GANCHO_REHACER} (la revisión vio: {que[:200]})"
                               + (f"\nARRANQUES ANTERIORES (no repetir):\n{ganchos}" if ganchos else ""))
            else:
                errores.append(f"escena {k + 1}: lo que se ve no es lo que dice la frase ({que[:200]}): elegí la "
                               "escena de la biblioteca y el plano que la muestran, con cada persona haciendo algo")
    if not errores or cliente is None:
        return d, ""
    try:
        d2 = correcciones.corregir(cliente, sistema_guion(), f"MARCA: {e.marca.nombre}\nTEXTO:\n{(fuente or '')[:12000]}",
                                   d, errores, SCHEMA_GUION, "escenas", "escena")
    except Exception as err:  # noqa: BLE001
        avisar(f"no pude corregir: {str(err)[:120]}")
        return d, ""
    if fuente and validar_guion(d2, e.marca, fuente):
        return d, "la corrección no validó: quedó como estaba"
    return d2, "rehice " + ", ".join(x.split(":")[0] for x in errores)


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


def revisar_visual(cliente, d: dict, datos: dict, carpeta: Path, capturar=None, avisar=log.info,
                   conn=None) -> tuple[list, list]:
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
    frases = frases_de(d)
    def qd(i, q):
        k = datos["escenas"][i].get("frase")
        esc_k = (d.get("escenas") or [])[k] if isinstance(k, int) and k < len(d.get("escenas") or []) else {}
        gente = ", ".join(f"{a.get('persona_real') or a.get('rol')} ({a.get('genero')}, {a.get('edad')})"
                          for a in esc_k.get("actores") or [])
        extra = (f" — dice: «{frases[k]}» (lugar: {esc_k.get('fondo')}, año: {esc_k.get('anio_escena') or 'hoy'}; "
                 f"personajes: {gente or '-'}; protagonista: {(d.get('protagonista') or {}).get('que_es')})"
                 if isinstance(k, int) and k < len(frases) else "")
        return q + extra
    lista = "\n".join(f"Cuadro {n + 1}: {qd(i, q)}" for n, (_t, i, q) in enumerate(claves))
    lista += ("\n\nARRANQUES ANTERIORES DEL CANAL:\n" + texto_ganchos(ganchos_recientes(conn)[:-1])
              if conn is not None else "")
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
    aviso: str = ""        # puntaje bajo o banco de reserva (nunca un día sin video, 2026-11-15)
    banco_id: str = ""

    def a_dict(self) -> dict:
        return asdict(self)


NUMERO_CHICO = 12
TOPE_USD_VIDEO = 2.0   # Claude por video: pasado esto no se prueba otra marca (8 intentos × 4 marcas = ~US$ 4)


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
             revisor=None, forzar: Elegido | None = None,
             reintentos_guion: int = 6, banco: list[dict] | None = None,
             ultimo: bool = False) -> tuple[Elegido, dict, str]:
    """(elegido, guion validado, fuente). SinCandidato si ninguno llega al puntaje o ningún guion valida.
    `forzar`: una marca y ángulo elegidos a mano (para rehacer un ejemplo): sin rotación ni puntaje."""
    from clips_bot import bitacora

    bitacora.paso("busqueda")
    if forzar is not None:
        bitacora.paso("guion")
        fuente = fuente_de(wiki, forzar.marca)
        try:
            return forzar, escribir_guion(cliente, forzar, fuente, reintentos_guion, avisar=avisar,
                                          revisor=revisor, ganchos_previos=ganchos_recientes(conn)), fuente
        except GuionInvalido as err:
            raise SinCandidato(f"el guion no pasó la validación: {err}") from err
    catalogo = catalogo if catalogo is not None else cargar_catalogo()
    fallidas = fallidos_de(conn, hoy) if conn is not None else set()
    cands = candidatos(conn, catalogo, hoy, n, excluir=fallidas)

    def con_banco(motivo: str, errores_previos: list[str] | None = None):
        """Nunca un día sin video (Santi, 2026-11-15): una marca del banco de reserva (puntuada de antemano
        con 8 o más) que siga libre en la rotación."""
        libres = {(m.nombre, a) for m, a in disponibles(conn, catalogo, hoy)} if conn is not None else None
        por_nombre = {m.nombre: m for m in catalogo}
        errs = list(errores_previos or [])
        for it in sorted(banco or [], key=lambda x: -float(x.get("puntaje") or 0))[:3]:
            m = por_nombre.get(it.get("marca"))
            if m is None or (libres is not None and (m.nombre, it.get("angulo")) not in libres) \
                    or m.nombre in fallidas:
                continue
            e = Elegido(m, it["angulo"], dict(it.get("notas") or {}), str(it.get("dato") or ""),
                        aviso=f"📦 del banco de reserva ({motivo})", banco_id=str(it.get("id") or ""))
            avisar(f"banco de reserva: {m.nombre}/{e.angulo} ({motivo})")
            fuente = fuente_de(wiki, m)
            try:
                return e, escribir_guion(cliente, e, fuente, reintentos_guion, avisar=avisar, revisor=revisor,
                                         ganchos_previos=ganchos_recientes(conn)), fuente
            except GuionInvalido as err:
                errs.append(str(err))
        return None

    if not cands:
        hecho = con_banco("no queda ninguna marca en la rotación")
        if hecho:
            return hecho
        raise SinCandidato("no queda ninguna marca/ángulo que pase la rotación (y el banco de reserva no tiene)")
    textos = []
    for m, a in cands:
        try:
            textos.append((m, a, extracto(wiki.texto("es", m.wiki_es), a)))
        except Exception as e:
            avisar(f"no pude leer el artículo de {m.nombre}: {str(e)[:120]}")
    fila_elegir = bitacora.fila_actual()
    notas_todas: dict = {}
    piso = PISO_ABSOLUTO if ultimo else minimo
    elegidos = elegir(revisor or cliente, textos, min(minimo, piso), notas_todas)   # puntúa Haiku; Sonnet escribe
    altos = [x for x in elegidos if x.promedio >= minimo]
    if altos or not ultimo:
        elegidos = altos
    elif elegidos:
        # el último intento del día: la mejor si tiene 6 o más (Santi, 2026-11-15)
        elegidos = elegidos[:1]
        elegidos[0].aviso = f"⚠️ salió con puntaje {elegidos[0].promedio:.1f} (mínimo {minimo:g})".replace(".", ",")
    # los que no llegan al puntaje: a la bitácora, con su parte del pedido (Santi, 2026-11-15)
    if conn is not None and textos:
        parte = bitacora.costo_entre(conn, fila_elegir, bitacora.fila_actual()) / len(textos) if fila_elegir else 0.0
        pasan = {(x.marca.nombre, x.angulo) for x in elegidos}
        for i_, (m_, a_, _) in enumerate(textos):
            if (m_.nombre, a_) in pasan:
                continue
            nota = notas_todas.get(i_)
            motivo = (nota if isinstance(nota, str) else
                      f"promedio {nota:.2f} < {minimo:g}" if isinstance(nota, (int, float)) else "no lo puntuó")
            bitacora.descarte(f"{m_.nombre}/{a_}", motivo, "puntaje", costo=parte)
    avisar("candidatos: " + ", ".join(f"{m.nombre}/{a}" for m, a, _ in textos) +
           f" → pasan {len(elegidos)}: " + ", ".join(f"{e.marca.nombre}/{e.angulo} {e.promedio}" for e in elegidos))
    if not elegidos:
        if ultimo:
            hecho = con_banco(f"ninguna llegó a {PISO_ABSOLUTO:g}")
            if hecho:
                return hecho
        # quedan afuera hoy y el reintento (en 1 h) prueba con otras: no se pierde el día (2026-11-15)
        anotar_fallidos(conn, hoy, [m.nombre for m, _, _ in textos])
        raise GuionesFallidos(f"ninguno de los {len(textos)} candidatos llegó a {minimo:g} de promedio; "
                              "pruebo con otros en un rato")
    errores = []
    bitacora.paso("guion")
    fila0 = ultima_fila_uso(conn) if conn is not None else 0
    for e in elegidos[:max_intentos]:
        if conn is not None and errores and costo_desde(conn, fila0) > TOPE_USD_VIDEO:
            errores.append(f"corté: este video ya gastó más de US$ {TOPE_USD_VIDEO:g} de Claude")
            break
        fuente = fuente_de(wiki, e.marca)
        fila_g = bitacora.fila_actual()
        try:
            return e, escribir_guion(cliente, e, fuente, reintentos_guion, avisar=avisar, revisor=revisor,
                                     ganchos_previos=ganchos_recientes(conn)), fuente
        except GuionInvalido as err:
            errores.append(str(err))
            bitacora.descarte(f"{e.marca.nombre}/{e.angulo}", str(err).split(": ", 1)[-1], "guion", desde_fila=fila_g)
    anotar_fallidos(conn, hoy, [e.marca.nombre for e in elegidos[:max_intentos]])
    if ultimo:
        fallidas |= {e.marca.nombre for e in elegidos[:max_intentos]}
        hecho = con_banco("ningún guion del día validó", errores)
        if hecho:
            return hecho
    raise GuionesFallidos("ningún guion pasó la validación (esas marcas quedan afuera hoy): "
                          + " | ".join(errores)[:600])


VOLUMEN_SFX = 0.32
# Subtítulos (Santi, 2026-11-14): ARRIBA, en la franja que la escena no pisa (ac.BANDA_SUBTITULOS, la
# controla acciones.composicion). Desde la REGLA 9, estilo Shorts virales (subtitulos_virales.py): 1-3
# palabras, Montserrat Black con contorno y sombra, pop por palabra, claves en color, temblor y emoji.
SUBTITULOS_Y = sv.Y
SALTO_MIN = 10       # un "viaje" de menos de 10 años (1969 → 1970) no es cambio de época: no se hace
SUBTITULOS_TAM = sv.TAM


def armar_video(conn, settings, carpeta: Path, cliente=None, wiki=None, hoy: date | None = None,
                avisar=log.info, procesos: int = 2, catalogo: list[Marca] | None = None,
                forzar: Elegido | None = None, revisor=None, guion: dict | None = None,
                reescribir: bool = True, banco: list[dict] | None = None, ultimo: bool = False) -> Resultado:
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
    cliente = cliente or claude.cliente(cfg.modelo_texto, max_tokens=cfg.max_tokens)
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
                                cfg.max_intentos, avisar, revisor=revisor, forzar=forzar,
                                reintentos_guion=cfg.reintentos_guion, banco=banco, ultimo=ultimo)
    tiempos["guion_s"] = round(time.time() - t0, 1)
    if not tiene_claves(d) and revisor is not None:     # REGLA 9 con un guion que no la trae
        try:
            marcar_claves(revisor, d)
        except Exception as err:   # sin marcas el video sale igual (sin claves ni emojis)
            avisar(f"no pude marcar las claves de los subtítulos: {str(err)[:150]}")
    from clips_bot import bitacora

    bitacora.dato(titulo=str(d.get("titulo") or ""), marca=e.marca.nombre, angulo=e.angulo)
    bitacora.paso("dibujos")
    d = asegurar_dibujos(cliente, d, e, fuente or "", avisar)
    resolver_objetos(cliente, d, e, avisar)
    guardar_acciones_nuevas(d)
    if getattr(cfg, "visual_plus", False):
        from . import visuales

        visuales.enriquecer(revisor, d, fuente or fuente_de(wiki, e.marca), wiki, avisar)
    try:
        anotar_gancho(conn, d, e.marca.nombre)
    except Exception as err:  # noqa: BLE001 — anotar nunca frena el video
        avisar(f"no pude anotar el gancho: {err}")
    (carpeta / "guion.json").write_text(json.dumps({"marca": e.marca.nombre, "angulo": e.angulo,
                                                    "notas": e.notas, "guion": d}, ensure_ascii=False,
                                                   indent=1), encoding="utf-8")
    # Voz: la de Tito con ElevenLabs (Santi, 2026-11-15; `animacion.elevenlabs_voz`), y si no está o falla, la
    # cadena de Pequeña Historia (Gemini TTS, Piper de respaldo). La mascota ES el que narra. Ritmo (Santi, 2026-11-14): ×1,065
    # sin cambiar el tono y los silencios entre frases a 0,22 s; si queda fuera de 32-38 s, se REESCRIBE el
    # guion (no se acelera más).
    t0 = time.time()
    bitacora.paso("voz")
    for intento in range(3):
        segs = segmentos(d)
        hablado = [t for _, _, t in segs]
        wav, _duraciones, motor = ef.voz_efemeride(hablado, settings, carpeta, avisar,
                                                   elevenlabs_cfg=settings.animacion)
        narrar.a_48k(wav)
        ef.acelerar(wav, VELOCIDAD_VOZ)
        sacado = acortar_pausas(wav)
        narrar.sacar_silencio_inicial(wav)
        fin = narrar.duracion_wav(wav)
        avisar(f"voz: {fin:.1f} s (×{VELOCIDAD_VOZ}, {sacado:.1f} s de pausas menos)")
        ajuste = ajuste_velocidad(fin)
        if ajuste:
            # primero la velocidad del audio que ya está (no se paga otra voz)
            ef.acelerar(wav, ajuste)
            antes, fin = fin, narrar.duracion_wav(wav)
            avisar(f"voz: {antes:.1f} s → {fin:.1f} s ajustando la velocidad ×{ajuste:.3f} (sin reescribir)")
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
                               ganchos_previos=ganchos_recientes(conn)[:-1],
                               extra=(f"OJO: tu guion anterior, leído en voz alta, duró {fin:.0f} segundos y tiene "
                                      f"que durar entre {MIN_S:g} y {MAX_S:g}. Escribilo con unas {objetivo} palabras "
                                      "en total (frases + Tito), con la misma historia:\n" + describir(d)))
        except GuionInvalido as err:
            avisar(f"no pude acortar el guion: {err}")
            break
        # la reescritura puede traer objetos nuevos (el 16/11: 'masa_gris'): se dibujan o va el más parecido
        resolver_objetos(cliente, d, e, avisar)
    tiempos["voz_s"] = round(time.time() - t0, 1)
    t0 = time.time()
    bitacora.paso("whisper")
    oidas = narrar.palabras_de_voz(wav, settings.subtitulos)
    oidas, recortado = narrar.recortar_inicio(wav, oidas, hablado)
    if recortado:
        fin = narrar.duracion_wav(wav)
    palabras, inicios = narrar.alinear_a_guion(oidas, hablado, fin)
    tiempos["whisper_s"] = round(time.time() - t0, 1)
    avisar(f"voz ({motor}): {fin:.1f} s")
    resolver_objetos(cliente, d, e, avisar)
    datos, eventos = linea_de_tiempo(d, inicios, fin, palabras, wav,
                                         subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico",
                                         visual=getattr(cfg, "visual_plus", False))
    # Revisión visual (Santi, 2026-11-14): Claude mira los cuadros clave ANTES del render y, si ve algo
    # absurdo, se corrige el guion de esa escena y se vuelve a armar; como mucho 2 vueltas.
    revision: list[str] = []
    t0 = time.time()
    bitacora.paso("revision")
    for vuelta in range(2):
        problemas, claves = revisar_visual(cliente, d, datos, carpeta, avisar=avisar, conn=conn)
        if not problemas:
            revision.append(f"vuelta {vuelta + 1}: sin problemas" if vuelta else "revisión visual: sin problemas")
            break
        hechos = aplicar_revision(d, problemas, claves, datos)
        # lo que se corrige en el guion: la acción que no es la de la frase, la gente parada y el gancho
        # repetido o sin acción (Santi, 2026-11-15: "que lo corrija sola, no solo que lo marque")
        acciones_mal = [(int(pr.get("cuadro") or 0) - 1, str(pr.get("que") or "")) for pr in problemas
                        if pr.get("arreglo") in ("cambiar_accion", "rehacer_gancho")
                        or (pr.get("arreglo") == "otro" and int(pr.get("cuadro") or 0) == 1)]
        if acciones_mal:
            d, hecho = corregir_acciones(cliente, d, e, fuente, acciones_mal, claves, datos, avisar,
                                         ganchos=texto_ganchos(ganchos_recientes(conn)[:-1]) if conn is not None else "")
            if hecho:
                hechos.append(hecho)
        revision += [f"vuelta {vuelta + 1}: {h}" for h in hechos]
        avisar("revisión visual: " + "; ".join(hechos)[:300])
        resolver_objetos(cliente, d, e, avisar)
        datos, eventos = linea_de_tiempo(d, inicios, fin, palabras, wav,
                                         subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico",
                                         visual=getattr(cfg, "visual_plus", False))
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
    bitacora.paso("render")
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
        costo_usd=costo_desde(conn, fila0), tiempos=tiempos, revision=revision, niveles=niv,
        aviso=e.aviso, banco_id=e.banco_id)


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
