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

from clips_bot import calidad

from . import reemplazo as _rz

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
def _fondos_nuevos() -> list[str]:
    """Los lugares dibujados y guardados (entran en la lista del guion desde el próximo arranque)."""
    try:
        from . import dibujos

        return [f for f in dibujos.fondos_guardados()][:40]
    except Exception:  # noqa: BLE001
        return []


FONDOS = ("casa", "taller", "fabrica", "tienda", "oficina", "ciudad", "escenario", "cielo", "globo",
          "laboratorio", "hospital", "campo", "puerto", "playa", "estadio", "cocina")
# mesa y estante no son objetos de la historia: son el APOYO (`soporte`) y el render los pone contra la pared
# Los efectos que agrega el render (polvo, líneas de movimiento, destellos, primer plano) NO los elige el guion.
EFECTOS_RENDER = ("polvo", "lineas_mov", "destello", "primer_plano", "rayos", "cinta_frente")
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

REGLA 8 — ESCENARIOS DE LA HISTORIA REAL (Santi, 2026-11-17). Cada momento pasa DONDE pasó de verdad según el
artículo (`fondo`): playa, estadio, cocina, fábrica, tienda, laboratorio, oficina de época, calle, hospital, campo,
puerto, escenario…; nunca un living o un taller genéricos para algo que pasó en otro lado (si la frase dice "en la
playa", el fondo es `playa`, no `puerto`). La casa y el taller solo si la historia pasa ahí. CADA VIDEO ES ÚNICO:
como mucho un tercio de las escenas puede repetir la misma acción y el mismo lugar de los últimos 10 videos del
canal (te paso cuáles) y solo si la historia lo pide, y NINGUNA escena puede ser igual entera (lugar, acción,
objetos, plano y movimiento) a una de esos videos. DISEÑÁ CADA ESCENA PARA ESTA HISTORIA y armala con las piezas que
ya existen (personajes, manos, fondos, objetos, efectos: se reusan libremente); lo único que tiene que ser nuevo es
la combinación. Si el LUGAR real no está en la lista de `fondo`, poné el más parecido en `fondo` y describilo en
`lugar_nuevo` (ej. "bolera de los años 50 con pistas de madera y pinos al fondo"): se dibuja una vez y queda guardado
para los próximos videos; si está en la lista, `lugar_nuevo` vacío. Si falta un objeto, `dibujo_nuevo` (REGLA 13).
Cuando cambia el momento, cambia el lugar: al menos 3 lugares
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
- La PRIMERA frase es el GANCHO: el DATO concreto más fuerte o divertido de ESTA historia (nada de fórmulas
  genéricas: "pasó algo que nadie esperaba", "nadie lo podía creer", "lo que pasó después te va a sorprender"),
  máximo 8 palabras (dura menos de 3 s),
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
  PERSONAJES SEGÚN QUIÉN ES Y SU ROL (Santi, 2026-11-17): el protagonista es la persona real, con su `genero` y la
  `edad` que tenía en ESA escena; los demás tienen el rol de lo que hacen ahí: obrero/obrera en la fábrica,
  cajero/cajera o vendedor/vendedora en el negocio, cliente comprando, empresario/fundador el de traje,
  inventor/cientifica/medico con guardapolvo, repartidor cargando. Nadie sin rol ni de relleno. La ropa la pone el
  código según el rol y el año de la escena. Cada uno HACE algo de su rol: `quieto` en un obrero, cajero, vendedor,
  cliente o repartidor = trabaja con lo suyo en las manos (cajas, billetes, el producto); en cualquier otro rol,
  `quieto` no vale: elegí la acción de la frase.
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
                "fondo": {"type": "STRING", "enum": list(FONDOS) + _fondos_nuevos()},
                "lugar_nuevo": {"type": "STRING"},
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


def schema_guion() -> dict:
    """El schema del guion (el mismo con o sin reglas_v3: las opciones de gancho y el decorado van en un pedido
    aparte, `completar_v3`, porque sumados acá la gramática pasaba el tope de Claude, 2026-11-16)."""
    return SCHEMA_GUION


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


# ---- cada video único en escenas y los lugares de la historia real (Santi, 2026-11-17, el Frisbee) ---------------
ESCENAS_RECIENTES = "animacion_escenas"   # bot_estado: [{video, marca, firmas}] de los últimos videos
VIDEOS_UNICOS = 10                         # contra cuántos videos se compara
ESCENAS_PREVIAS: list[list[str]] = []      # las firmas de los últimos videos (las carga armar_video)
COMPLETAS_PREVIAS: list[list[str]] = []    # las escenas enteras de los últimos videos (ídem)
# Lo que la frase dice del lugar → el fondo donde tiene que pasar (solo lugares que no tienen otro sentido común).
def _en(palabras: str) -> re.Pattern:
    """La frase dice que la acción pasa AHÍ: "en la playa", "a una playa", "en su fábrica" (no "una ciudad de playa")."""
    return re.compile(r"\b(?:en|a|al|desde|hacia|por)\s+(?:la|las|el|los|una|unas|un|su|sus)?\s*(?:" + palabras + r")\b",
                      re.I)


# Lo que la frase dice del lugar → el fondo donde tiene que pasar (solo lugares que no tienen otro sentido común).
LUGAR_DE_FRASE = (("playa", _en(r"playas?|orilla del mar")),
                  ("estadio", _en(r"estadios?|cancha|tribunas?")),
                  ("cocina", _en(r"cocina")),
                  ("fabrica", _en(r"f[aá]bricas?|planta industrial")),
                  ("tienda", _en(r"tiendas?|almac[eé]n|supermercados?|kioscos?")),
                  ("hospital", _en(r"hospital(?:es)?|cl[ií]nica")),
                  ("laboratorio", _en(r"laboratorios?")),
                  ("puerto", _en(r"puertos?|muelles?")))


def firma_escena(e: dict) -> str:
    """Qué es una escena para "¿ya la usamos?": la acción de la biblioteca (o, si es libre, lo que hacen los
    personajes) y el lugar."""
    acc = str(e.get("accion_escena") or "libre")
    if acc in ("libre", "nueva", ""):
        acc = "libre:" + "+".join(sorted({str(a.get("accion") or "") for a in e.get("actores") or []})) or "libre"
    return f"{acc}@{e.get('fondo') or ''}"


def firma_completa(e: dict, prota: str = "") -> str:
    """La escena entera (Santi, 2026-11-17: "lo único es la combinación de lugar, acción, objetos, plano y
    movimiento"): las piezas se reusan, la combinación no. El protagonista cuenta como `{prota}`."""
    objs = sorted({("{prota}" if prota and prop_real(o) == prota else prop_real(o)) for o in e.get("objetos") or []
                   if prop_real(o)})
    return f"{firma_escena(e)}|{e.get('plano') or ''}|{e.get('camara') or ''}|{'+'.join(objs)}"


def completas_recientes(conn) -> list[list[str]]:
    try:
        return [list(x.get("completas") or []) for x in json.loads(_get_valor(conn, ESCENAS_RECIENTES) or "[]")]
    except ValueError:
        return []


def escenas_recientes(conn) -> list[list[str]]:
    try:
        return [list(x.get("firmas") or []) for x in json.loads(_get_valor(conn, ESCENAS_RECIENTES) or "[]")]
    except ValueError:
        return []


def anotar_escenas(conn, d: dict, video: str, marca: str) -> None:
    from clips_bot import db

    try:
        lista = [x for x in json.loads(_get_valor(conn, ESCENAS_RECIENTES) or "[]") if x.get("video") != video]
    except ValueError:
        lista = []
    prota = prop_real(d.get("protagonista") or {})
    lista.append({"video": video, "marca": marca, "firmas": [firma_escena(e) for e in (d.get("escenas") or [])[1:]],
                  "completas": [firma_completa(e, prota) for e in (d.get("escenas") or [])[1:]]})
    db.set_valor(conn, ESCENAS_RECIENTES, json.dumps(lista[-VIDEOS_UNICOS:], ensure_ascii=False))


def repetidas(d: dict, previas: list[list[str]]) -> list[int]:
    """Las escenas (número desde 1, sin el gancho) que repiten acción y lugar de los últimos videos."""
    usadas = {f for v in previas[-VIDEOS_UNICOS:] for f in v}
    return [i + 1 for i, e in enumerate(d.get("escenas") or []) if i > 0 and firma_escena(e) in usadas]


def tope_repetidas(d: dict) -> int:
    return max(0, len(d.get("escenas") or []) - 1) // 3


def errores_unicas(d: dict, previas: list[list[str]] | None = None,
                   completas: list[list[str]] | None = None) -> list[str]:
    """Ninguna escena repite ENTERA (lugar, acción, objetos, plano y movimiento) una de los últimos 10 videos, y como
    mucho un tercio repite acción y lugar (AN-25)."""
    previas = ESCENAS_PREVIAS if previas is None else previas
    completas = COMPLETAS_PREVIAS if completas is None else completas
    escenas = d.get("escenas") or []
    prota = prop_real(d.get("protagonista") or {})
    usadas = {f for v in completas[-VIDEOS_UNICOS:] for f in v}
    iguales = [i + 1 for i, e in enumerate(escenas) if i > 0 and firma_completa(e, prota) in usadas]
    errs = ([f"cada escena es única: las escenas {iguales} son IGUALES (lugar, acción, objetos, plano y movimiento) a "
             "escenas de videos anteriores: diseñalas para esta historia (otro plano, otros objetos de la historia, "
             "otro movimiento o el lugar real)"] if iguales else [])
    rep = repetidas(d, previas)
    if len(rep) <= tope_repetidas(d):
        return errs
    return errs + [f"cada video es único: las escenas {rep} repiten la misma acción en el mismo lugar que videos anteriores "
            f"({', '.join(firma_escena(escenas[i - 1]) for i in rep[:6])}) y pueden ser como mucho "
            f"{tope_repetidas(d)}: cambiá la acción o el lugar de las que sobran, según dónde y cómo pasó de verdad"]


def errores_lugar(d: dict) -> list[str]:
    """Si la frase dice dónde pasó (playa, estadio, cocina, fábrica, tienda…), la escena va en ese lugar (AN-25)."""
    malos = []
    for i, e in enumerate(d.get("escenas") or []):
        frase = str(e.get("frase") or "")
        for fondo, rx in LUGAR_DE_FRASE:
            if rx.search(frase):
                if e.get("fondo") != fondo:
                    malos.append(f"escena {i + 1} («{frase[:70]}») dice {fondo} y el fondo es {e.get('fondo')}")
                break
    return ([f"el lugar de la escena tiene que ser el de la historia real: {'; '.join(malos)}"] if malos else [])


def texto_escenas_recientes(previas: list[list[str]]) -> str:
    usadas = sorted({f for v in previas[-VIDEOS_UNICOS:] for f in v})
    return ", ".join(usadas)


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


FLOTA = {"gira", "aparece", "crece", "vuela", "rebota", "llueve"}
FLOTA_MAX = 2
EN_USO_MIN = 0.6


PLATA_SIMBOLO = {"moneda", "bolsa_plata"}


def errores_plata(d: dict) -> list[str]:
    """Regla 17 (Santi, 2026-11-16): nada de monedas con $ ni bolsas de plata gigantes; la plata con acciones reales."""
    malas = [i for i, e_ in enumerate(d.get("escenas") or [], 1)
             if any(prop_real(o) in PLATA_SIMBOLO for o in e_.get("objetos") or [])]
    if not malas:
        return []
    return [f"escenas {malas}: nada de monedas o bolsas de plata gigantes; la plata con una acción real (contar_billetes, "
            "abrir_caja, apreton_manos, firmar, contador_ventas)"]


def errores_uso(d: dict) -> list[str]:
    """Reglas_v3 del guion (Santi, 2026-11-16): el producto en uso en la mayoría de las escenas, flotando o girando como
    mucho 2 veces, y algo nuevo para la biblioteca en cada video."""
    errores = []
    prota = prop_real(d.get("protagonista") or {})
    escenas = (d.get("escenas") or [])[1:]           # la 1 es el gancho (la imagen imposible)
    if not escenas:
        return errores
    flotan, con = [], []
    for i, e_ in enumerate(escenas, 2):
        suyos = [o for o in e_.get("objetos") or [] if prop_real(o) == prota]
        if e_.get("accion_escena") == "objeto_gira" or any(o.get("efecto") in FLOTA or o.get("soporte") == "aire"
                                                             for o in suyos):
            flotan.append(i)
        if suyos or (e_.get("accion_escena") or _lib.LIBRE) not in (_lib.LIBRE, "nueva"):
            con.append(i)
    if len(flotan) > FLOTA_MAX:
        errores.append(f"el producto flota o gira en las escenas {flotan}: como mucho en {FLOTA_MAX} y solo si la frase "
                       "lo justifica; en las otras, en uso (en la mano de alguien o donde se usa)")
    if len(con) < EN_USO_MIN * len(escenas):
        faltan = [i for i in range(2, len(escenas) + 2) if i not in con]
        errores.append(f"el producto ({prota}) no se ve en uso en las escenas {faltan[:6]}: mostralo funcionando aunque la "
                       "frase hable de otra cosa")
    nuevas = [e_ for e_ in escenas if e_.get("accion_escena") == "nueva" and str(e_.get("accion_nueva") or "").strip()
              and str(e_["accion_nueva"]).strip() not in _lib.todas_las_acciones()]
    if not nuevas:
        errores.append("falta algo NUEVO para la biblioteca: 1 escena con `accion_escena` = nueva y un `accion_nueva` que "
                       "todavía no exista (una acción de este producto)")
    return errores


def errores_v3(d: dict) -> list[str]:
    """Regla 16 (Santi, 2026-11-16): 3 opciones de gancho distintas con texto de 3 a 5 palabras, y decorado de
    contexto en la mayoría de las escenas."""
    from . import gancho_v3 as gv

    from clips_bot.reglas import gancho_generico

    errores = []
    ops = gv.opciones_de(d)
    genericas = [o["texto"] for o in ops if gancho_generico(o["texto"])]
    if genericas:
        errores.append(f"`ganchos`: textos genéricos ({', '.join(genericas)}): el dato concreto más fuerte de la historia")
    if len(ops) < 3 or len({o["tipo"] for o in ops}) < 3:
        errores.append("`ganchos`: 3 opciones de tipos DISTINTOS (" + ", ".join(gv.TIPOS) + ") con un `texto` de 3 a 5 "
                       "palabras que intrigue")
    escenas = (d.get("escenas") or [])[1:]
    sin = [i + 2 for i, e in enumerate(escenas) if not (e.get("decorado") or [])]
    if escenas and len(sin) > len(escenas) // 2:
        errores.append(f"`decorado`: poné 1 a 3 objetos de contexto en las escenas {sin[:6]} (nada de mesas vacías)")
    return errores


SISTEMA_V3 = """Te paso el guion de un video corto animado de "Así Nació" (el origen de una marca). Agregás dos cosas
(Santi, 2026-11-16):
1. `ganchos`: 3 OPCIONES de gancho para los primeros 3 segundos, con el producto protagonista en una imagen
   sorprendente o imposible. `tipo`, uno de: explota (estalla en pedazos de colores), gigante (crece hasta ser enorme),
   multiplica (se multiplica por toda la pantalla), vuela (cruza volando), multitud (una multitud se pelea por él); los
   3 de tipos DISTINTOS. `texto`: una pregunta o un dato de ESTA historia que intrigue, de 3 a 5 palabras, que va grande
   arriba ("¿UN JUGUETE DE JABÓN?", "VENDIÓ UN MILLÓN EN 1949"); datos solo del guion. Nada de fórmulas genéricas
   ("ALGO QUE NADIE ESPERABA", "NO VAS A CREERLO"): el dato concreto más fuerte.
2. `decorado`: para cada escena (desde la 2), 1 a 3 objetos de la lista que dan CONTEXTO a la historia en ese lugar y
   esa época (una cocina de 1946: botella, jarrón, radio; una oficina: teléfono de disco, calendario). Van atrás, sobre
   el estante, la mesa o el piso. Solo nombres de la lista. Nada que no tenga relación con la historia ni que no
   existiera en el año de esa escena (nada de celulares, teles ni monitores en una escena de 1938).
3. `uso`: UNA escena (desde la 2; la que habla del producto o de cómo se usaba) donde dos manos de cerca usan el
   producto como se usa de verdad, paso a paso. `pasos`, en orden, de: agarrar, abrir_tapa, meter, cerrar_tapa,
   apretar (el Tupper: agarrar, abrir_tapa, meter, cerrar_tapa, apretar), amasar, moldear (el Play-Doh: agarrar,
   amasar, moldear), girar (el cubo: agarrar, girar), apilar. Si el producto tiene tapa, `cuerpo` y `tapa` dicen cómo
   es cada parte por separado (forma, material, colores), para dibujarlas; si no, vacíos. `contenido`: lo que se mete
   adentro (comida, para el Tupper), descrito para dibujarlo; vacío si no hay.
4. `inspiracion`: si la historia dice que ALGO INSPIRÓ al producto (la tapa de una lata de pintura inspiró la tapa del
   Tupper), `escena` = la escena donde la voz lo explica, `fuente` = cómo es eso que lo inspiró, con TODOS los detalles
   que lo hacen reconocible de un vistazo (una lata de pintura: metálica, con manija de alambre, pintura chorreando por
   el borde), `pieza` = la parte que pasa al producto, también reconocible (una tapa de lata clásica con reborde) y
   `acompana` = algo que va al lado y termina de explicarlo (un pincel con pintura), o vacío. Si no hay nada así,
   `escena` 0.
Todo lo que describís se tiene que entender SIN la voz y con los mismos detalles que dice el guion.
Respondé solo el JSON."""
SCHEMA_V3 = {"type": "OBJECT", "properties": {
    "ganchos": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "tipo": {"type": "STRING", "enum": ["explota", "gigante", "multiplica", "vuela", "multitud"]},
        "texto": {"type": "STRING"}}, "required": ["tipo", "texto"]}},
    "decorado": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "escena": {"type": "INTEGER"}, "objetos": {"type": "ARRAY", "items": {"type": "STRING"}}},
        "required": ["escena", "objetos"]}},
    "uso": {"type": "OBJECT", "properties": {
        "escena": {"type": "INTEGER"},
        "pasos": {"type": "ARRAY", "items": {"type": "STRING", "enum": ["agarrar", "abrir_tapa", "meter", "cerrar_tapa",
                                                                       "apretar", "amasar", "moldear", "girar", "apilar"]}},
        "cuerpo": {"type": "STRING"}, "tapa": {"type": "STRING"}, "contenido": {"type": "STRING"}},
        "required": ["escena", "pasos", "cuerpo", "tapa", "contenido"]},
    "inspiracion": {"type": "OBJECT", "properties": {
        "escena": {"type": "INTEGER"}, "fuente": {"type": "STRING"}, "pieza": {"type": "STRING"},
        "acompana": {"type": "STRING"}},
        "required": ["escena", "fuente", "pieza", "acompana"]}},
    "required": ["ganchos", "decorado", "uso", "inspiracion"]}


def _slug(t: str, largo: int = 22) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    palabras = [w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 3 and w not in ("con", "sin", "una", "del", "las",
                                                                                    "los", "que", "para", "texto", "logos")]
    out = "_".join(palabras[:3])[:largo].strip("_")
    return out if len(out) >= 3 and out[0].isalpha() else ""


PASOS_USO_REAL = ("abrir_tapa", "meter", "cerrar_tapa", "apretar", "amasar", "moldear", "girar", "apilar")


def preparar_uso(cliente, d: dict, avisar=log.info) -> list[str]:
    """Santi, 2026-11-16: la escena de USO REAL con las manos (el producto por partes: cuerpo, tapa y lo que se guarda) y
    la de la INSPIRACIÓN (lo que lo inspiró y la pieza que pasa al producto). Dibuja las partes que falten (quedan
    guardadas) y marca esas escenas con `uso_manos` / `inspiracion`. Devuelve qué hizo."""
    from . import dibujos

    escenas = d.get("escenas") or []
    prota = prop_real(d.get("protagonista") or {})
    hechos = []
    partes_uso: dict = {}

    def dibujo(nombre: str, desc: str, frase: str = "") -> str:
        if not nombre or not desc.strip():
            return ""
        if esc.es_prop(nombre):
            return dibujos.actual(nombre)
        try:
            # el dibujo con los mismos detalles que describe el guion (Santi, 2026-11-16): la frase va de contexto
            dibujos.dibujar(cliente, nombre, desc, f"lo que dice la voz en esa escena: {frase}" if frase else "")
            return nombre
        except Exception as err:  # noqa: BLE001
            avisar(f"no pude dibujar {nombre}: {str(err)[:100]}")
            return ""

    u = d.get("uso") or {}
    k = int(u.get("escena") or 0) - 1
    # Frisbee, 17/11 (Santi: "manos levantadas y vacías en un living"): un uso de solo "agarrar" no muestra ningún uso
    # (un producto que se tira no se usa sobre una mesa). Sin un paso de uso de verdad, la escena queda como la
    # escribió el guion (sus personajes haciendo la acción en su lugar).
    reales = [p_ for p_ in u.get("pasos") or [] if isinstance(p_, str) and p_ in PASOS_USO_REAL]
    if 1 <= k < len(escenas) and prota and not reales:
        avisar(f"uso en la escena {k + 1}: sin un paso de uso real ({u.get('pasos')}); queda la escena del guion")
        k = -1
    if 1 <= k < len(escenas) and prota:
        base = prota[:20]
        partes = {"cuerpo": "", "tapa": "", "contenido": ""}
        if str(u.get("tapa") or "").strip() and str(u.get("cuerpo") or "").strip():
            partes["cuerpo"] = dibujo(f"{base}_cuerpo", str(u["cuerpo"]) + ", sin tapa, visto de costado")
            partes["tapa"] = dibujo(f"{base}_tapa", str(u["tapa"]) + ", sola, vista de costado")
            if not (partes["cuerpo"] and partes["tapa"]):
                partes["cuerpo"] = partes["tapa"] = ""
        cont = str(u.get("contenido") or "").strip()
        if cont:
            partes["contenido"] = cont if esc.es_prop(cont) else dibujo(_slug(cont) or "contenido", cont)
        if not partes["cuerpo"]:
            partes["cuerpo"] = prota
        escenas[k]["accion_escena"], escenas[k]["plano"] = "uso_manos", "manos"
        escenas[k]["uso"] = {"partes": partes, "pasos": [p_ for p_ in u.get("pasos") or [] if isinstance(p_, str)]}
        partes_uso = partes
        hechos.append(f"uso en la escena {k + 1}: {', '.join(escenas[k]['uso']['pasos'])}")
    ins = d.get("inspiracion") or {}
    k = int(ins.get("escena") or 0) - 1
    if 1 <= k < len(escenas) and prota and str(ins.get("fuente") or "").strip() and str(ins.get("pieza") or "").strip():
        frase_k = str(escenas[k].get("frase") or "")
        nombre = _slug(ins["fuente"]) or "inspiracion"
        fuente = dibujo(nombre, str(ins["fuente"]) + ", sin la pieza que pasa al producto", frase_k)
        pieza = dibujo(f"{nombre[:22]}_pieza", str(ins["pieza"]), frase_k)
        acomp = str(ins.get("acompana") or "").strip()
        acompana = (acomp if esc.es_prop(acomp) else dibujo(_slug(acomp) or "", acomp, frase_k)) if acomp else ""
        if fuente and pieza:
            escenas[k]["accion_escena"], escenas[k]["plano"] = "inspiracion", "cerca"
            # el producto empieza SIN su parte y la pieza se transforma en ella (la tapa de pintura → la tapa del Tupper)
            con_partes = bool(partes_uso.get("cuerpo") and partes_uso.get("tapa") and partes_uso["cuerpo"] != prota)
            escenas[k]["inspiracion"] = {"fuente": fuente, "pieza": pieza, "acompana": acompana,
                                         "producto": partes_uso["cuerpo"] if con_partes else prota,
                                         "resultado": partes_uso["tapa"] if con_partes else ""}
            hechos.append(f"inspiración en la escena {k + 1}: {fuente} → {prota}")
    if hechos:
        avisar("escenas nuevas: " + " | ".join(hechos))
    return hechos


def gv_palabras(t) -> set:
    from . import gancho_v3 as gv

    return gv._palabras(t)


def completar_v3(cliente, d: dict, avisar=log.info) -> bool:
    """Las 3 opciones de gancho y el decorado de cada escena, en un pedido aparte (reglas_v3). Si no salen, el video
    sigue con el gancho de siempre. Devuelve si quedaron las 3 opciones."""
    if cliente is None:
        return False
    lista = ", ".join(p for p in PROPS if p not in esc.NO_REEMPLAZO)
    guion_txt = "\n".join(f"{i + 1}. [{e_.get('fondo')}, {e_.get('anio_escena') or 'hoy'}] {e_.get('frase')}"
                          for i, e_ in enumerate(d.get("escenas") or []))
    prota = (d.get("protagonista") or {}).get("que_es") or prop_real(d.get("protagonista") or {})
    errores: list[str] = []
    for _ in range(3):
        pedido = (f"Producto protagonista: {prota}\nObjetos de la lista: {lista}\n\nGUION:\n{guion_txt}"
                  + (f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""))
        try:
            r = json.loads(cliente.json(SISTEMA_V3, pedido, SCHEMA_V3, 0.7))
        except Exception as err:  # noqa: BLE001
            avisar(f"opciones de gancho: no salieron ({str(err)[:120]})")
            return False
        d2 = {**d, "ganchos": r.get("ganchos") or []}
        errores = [x for x in errores_v3({**d2, "escenas": []}) if "ganchos" in x]
        frase1 = gv_palabras(frases_de(d)[0] if frases_de(d) else "")
        repetidos = [o.get("texto") for o in d2["ganchos"]
                     if gv_palabras(o.get("texto")) and len(gv_palabras(o.get("texto")) & frase1) * 2 >= len(gv_palabras(o.get("texto")))]
        if repetidos:   # Santi, 2026-11-16: ningún texto repite lo que dice la voz (la frase 1 sale en el subtítulo)
            errores.append(f"`ganchos`: estos textos repiten lo que dice la voz en la frase 1 ({', '.join(map(str, repetidos))}): "
                           "poné otro dato o una pregunta que no esté en esa frase")
        if errores:
            continue
        d["ganchos"] = r["ganchos"]
        for x in r.get("decorado") or []:
            k = int(x.get("escena") or 0) - 1
            if 1 <= k < len(d.get("escenas") or []):
                d["escenas"][k]["decorado"] = [str(o) for o in x.get("objetos") or []][:3]
        avisar("opciones de gancho: " + " | ".join(f"{o['tipo']} «{o['texto']}»" for o in d["ganchos"]))
        d["uso"], d["inspiracion"] = r.get("uso") or {}, r.get("inspiracion") or {}
        try:
            if USO_V4:
                preparar_uso(cliente, d, avisar)
        except Exception as err:  # noqa: BLE001 — sin las escenas de uso, el video sale igual
            avisar(f"escenas de uso e inspiración: no salieron ({str(err)[:120]})")
        return True
    avisar(f"opciones de gancho: no validaron ({'; '.join(errores)[:150]}); va el gancho de siempre")
    return False


def errores_quietos(d: dict) -> list[str]:
    """Nadie parado sin hacer nada (Santi, 2026-11-17): `quieto` solo en los roles que trabajan con algo en las manos
    (obrero, cajero, vendedor, cliente, repartidor: `ac.TRABAJO_ROL`)."""
    return [f"escena {i}: {a.get('rol')} queda quieto sin hacer nada (Santi, 2026-11-17): dale una acción de su rol "
            f"que muestre lo que dice la frase"
            for i, e in enumerate(d.get("escenas") or []) for a in e.get("actores") or []
            if a.get("accion") == "quieto" and a.get("rol") in ac.ROLES and a.get("rol") not in ac.TRABAJO_ROL]


def validar_guion(d: dict, m: Marca, fuente: str, ganchos_previos: list[dict] | None = None) -> list[str]:
    """Los errores del guion (vacío = sirve): datos contra el artículo (como Pequeña Historia),
    estructura, escenas con acción, locutor y presentación de cada empresa o persona."""
    from clips_bot.efemerides import no_respaldados

    from clips_bot.reglas import gancho_generico

    errores = []
    escenas = d.get("escenas") or []
    frases = frases_de(d)
    n = len(frases)
    if REGLAS_V3:
        errores += errores_uso(d)
    if USO_V4:
        errores += errores_plata(d)
    if frases and gancho_generico(frases[0]):    # Santi, 2026-11-16: el gancho dice el dato concreto
        errores.append(f"el gancho (frase 1) usa una frase genérica de intriga («{gancho_generico(frases[0])}»): "
                       "decí el dato concreto más fuerte de esta historia")
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
    errores += errores_lugar(d) + errores_unicas(d)        # la historia real y cada video único (2026-11-17)
    errores += errores_gancho_repetido(escenas, ganchos_previos or [])
    errores += errores_protagonista(d)
    errores += errores_fieles(d)
    errores += errores_accion(d)
    errores += errores_quietos(d)
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
        if e.get("fondo") not in FONDOS and not esc.es_fondo(str(e.get("fondo") or "")):
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
    return SISTEMA_GUION.replace("{BIBLIOTECA}", lista) + (REGLA_16 if REGLAS_V3 else "") + (REGLA_17 if USO_V4 else "")


REGLAS_V3 = False      # armar_video lo prende con `animacion.reglas_v3` (Santi, 2026-11-16)
USO_V4 = False         # armar_video lo prende con `animacion.uso_manos` (escenas de uso con las manos e inspiración)

REGLA_17 = """
REGLA 17 — MANOS QUE SE ENTIENDEN Y LA PLATA DE VERDAD (Santi, 2026-11-16).
- La PLATA se muestra con acciones reales y reconocibles: contar_billetes, abrir_caja (la caja registradora), apreton_manos
  (cerrar un trato), firmar (un contrato o un cheque), contador_ventas (el gráfico que sube). NUNCA una moneda con $ o una
  bolsa de plata gigante en las manos o en el medio de la escena (parece que la están lavando).
- Cada movimiento de manos se lee como UNA acción concreta en 1 segundo (agarrar, abrir, guardar, contar, firmar, dar).
- Objetos con detalle: nada de siluetas ni etiquetas en blanco; si un objeto no tiene un dibujo bueno, dibujo_nuevo."""


REGLA_16 = """
REGLA 16 — ESCENAS VIVAS (Santi, 2026-11-16; las 3 opciones de gancho y el decorado se piden aparte).
- Las MANOS siempre hacen algo con el objeto: lo agarran, lo abren, lo llenan, lo apilan (objeto con `soporte`
  mano, acción `fabricar`, `usar`, `probar` o `vender`). Nunca manos abiertas al costado ni el objeto flotando.
- EL PRODUCTO EN USO (Santi, 2026-11-16): en casi todas las escenas se ve el protagonista haciendo lo que hace, en la
  mano de alguien que lo usa (`soporte` mano) o apoyado donde se usa: el Tupper guardando comida, cerrándose con la
  tapa, apilado en la heladera, en una reunión de venta en una casa; el Play-Doh amasado por chicos; el cubo siendo
  resuelto. Aunque la frase hable de otra cosa (la quiebra, el nombre, el rival), se ve el producto funcionando o la
  escena de esa parte de la historia. El producto FLOTANDO o GIRANDO (`gira`, `aparece`, `crece`, `vuela`, `rebota`,
  soporte `aire`, `objeto_gira`) como mucho en 2 escenas y solo si la frase lo justifica.
- NADIE PARADO SIN HACER NADA, nunca: cada persona hace algo con las manos o el cuerpo que muestra la frase.
- ALGO NUEVO EN CADA VIDEO: al menos 1 escena con `accion_escena` = nueva y un `accion_nueva` que todavía no exista
  (una acción de ESTE producto), que queda en la biblioteca para los próximos videos.
- El OBJETO PROTAGONISTA tiene que parecerse al real: el Tupper es un recipiente de plástico bajo con tapa
  hermética, no una olla. Si ningún dibujo de la lista ES ese objeto (no uno parecido), `dibujo_nuevo` con una
  descripción precisa de su forma, material y colores.
- Cada frase dura 3 segundos como mucho al decirla (8 a 10 palabras): el video corta a otra toma cada 3 s.
- ÉPOCA DE CADA OBJETO: nada que no existiera en el `anio_escena` (ni un celular, una tele o un monitor en 1938):
  el código saca lo que no corresponde.
- Nada de objetos sin relación con la historia ni con etiquetas de texto escritas, salvo que la historia lo pida.
- CADA ESCENA SE ENTIENDE DE UN VISTAZO SIN LA VOZ (Santi, 2026-11-16): con los elementos que la hacen reconocible
  (una lata de pintura es metálica, con manija y pintura chorreando, y al lado un pincel; un trato es dos personas en una
  mesa con un contrato que se dan la mano). Los dibujos usan los MISMOS detalles que describe el guion."""


def escribir_guion(cliente, e: Elegido, fuente: str, reintentos: int = 6, avisar=log.info,
                   revisor=None, extra: str = "", ganchos_previos: list[dict] | None = None) -> dict:
    """El guion validado (dict del schema). Primero el chequeo del código; si pasa, el de Haiku
    (`revisor`). Si no valida, reintenta con los errores; si nunca valida, GuionInvalido."""
    pedido = (f"MARCA: {e.marca.nombre} ({e.marca.pais})\nÁNGULO: {e.angulo} — {ANGULOS[e.angulo]}\n"
              f"Dato para el gancho (sugerido): {e.dato}\n\nTEXTO (Wikipedia; los datos salen SOLO de "
              f"acá):\n{fuente[:20000]}" + (f"\n\n{extra}" if extra else "")
              + ("\n\nARRANQUES DE LOS VIDEOS ANTERIORES (el tuyo tiene que ser distinto: otro lugar, otra "
                 "acción, otro objeto):\n" + texto_ganchos(ganchos_previos) if ganchos_previos else "")
              + ("\n\nESCENAS YA USADAS EN LOS ÚLTIMOS 10 VIDEOS (acción@lugar; como mucho un tercio de las tuyas "
                 "puede repetirse, y solo si la historia lo pide): " + texto_escenas_recientes(ESCENAS_PREVIAS)
                 if ESCENAS_PREVIAS else ""))
    from clips_bot.gemini import GeminiError

    from clips_bot import correcciones

    # Corregir solo lo que falla (Santi, 2026-11-15): con un guion entero que no valida, se piden SOLO las
    # escenas o los campos a cambiar; recién con CORRECCIONES_MAX correcciones fallidas seguidas, el guion
    # entero de nuevo. Cada pedido (entero o corrección) cuenta como un intento.
    correccion, ultimo, d, puntuales = "", [], None, 0
    mejor: tuple[dict, list[str]] | None = None     # el mejor sin errores de datos ni de seguridad (Santi, 2026-11-16)
    for intento in range(reintentos):
        try:
            if d is not None and ultimo and puntuales < correcciones.CORRECCIONES_MAX:
                puntuales += 1
                d = correcciones.corregir(cliente, sistema_guion(), pedido, d, ultimo, schema_guion(), "escenas",
                                          "escena")
            else:
                puntuales = 0
                d = json.loads(cliente.json(sistema_guion(), pedido + correccion, schema_guion(), 0.9))
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
        if not any(bloquea(x) for x in ultimo) and (mejor is None or len(ultimo) < len(mejor[1])):
            mejor = (json.loads(json.dumps(d)), list(ultimo))
        avisar(f"guion de {e.marca.nombre} ({e.angulo}), intento {intento + 1}"
               f"{' (corrección puntual)' if puntuales else ''}: {'; '.join(ultimo)[:400]}")
        if puntuales >= correcciones.CORRECCIONES_MAX:
            correccion = ("\n\nTU GUION ANTERIOR:\n" + describir(d) +
                          "\n\nNO SIRVIÓ POR ESTO (corregilo y devolvé el guion entero):\n- " + "\n- ".join(ultimo))
    if mejor is not None:
        # Santi, 2026-11-16 (8 intentos fallidos por "presentá a Brownie Wise"): solo los datos verdaderos y la
        # seguridad frenan un video; si una regla de estilo no se cumplió, el video sale igual y se avisa cuál.
        d, pendientes = mejor
        d["_estilo_pendiente"] = pendientes
        avisar(f"guion de {e.marca.nombre}: sale con reglas de estilo sin cumplir: {'; '.join(pendientes)[:300]}")
        return d
    raise GuionInvalido(f"{e.marca.nombre} ({e.angulo}): {'; '.join(ultimo)[:400]}")


# Lo único que frena un video (Santi, 2026-11-16): un dato que no está en la fuente, un tema sensible, o un guion que
# técnicamente no se puede armar. Todo lo demás (estilo) sale con aviso.
_BLOQUEA = re.compile(r"no está en el artículo|NO está en el|temas sensibles|escena sin frase|faltan las escenas|"
                      r"respuesta que no es JSON|Claude \(|sin escenas", re.I)


def bloquea(error: str) -> bool:
    return bool(_BLOQUEA.search(str(error or "")))


def aviso_estilo(d: dict) -> str:
    """Lo que el video no cumplió de las reglas de estilo (sale igual; Santi, 2026-11-16)."""
    pend = [str(x) for x in d.get("_estilo_pendiente") or []]
    return ("⚠️ salió sin cumplir estas reglas de estilo: " + "; ".join(p_[:140] for p_ in pend))[:600] if pend else ""


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
                                   d, errores, schema_guion(), "escenas", "escena")
        if not validar_guion(d2, e.marca, fuente) or not fuente:
            return d2
    except Exception as err:  # noqa: BLE001
        avisar(f"no pude reformular sin {fallidos}: {str(err)[:150]}")
    # último recurso: el objeto más parecido de la biblioteca (Santi, 2026-11-16: nunca frena el video)
    resolver_objetos(None, d, e, avisar)
    return d


def crear_lugares(cliente, d: dict, avisar=log.info) -> list[str]:
    """Santi, 2026-11-17: un lugar que no existe (`lugar_nuevo` en la escena) se dibuja UNA vez con Claude y queda
    guardado para los próximos videos; la escena pasa a ese lugar. Si no se puede, queda el `fondo` más parecido que
    eligió el guion. Devuelve lo que creó o reusó."""
    from . import dibujos

    hechos = []
    for i, e in enumerate(d.get("escenas") or []):
        desc = str(e.get("lugar_nuevo") or "").strip()
        if not desc:
            continue
        nombre = ("lugar_" + _slug(desc, 22))[:30].rstrip("_")
        if not dibujos.nombre_valido(nombre):
            continue
        if dibujos.fondo_guardado(nombre) is None:
            if cliente is None:
                continue
            try:
                dibujos.dibujar_fondo(cliente, nombre, desc, int(e.get("anio_escena") or 0))
                hechos.append(f"lugar nuevo: {nombre} ({desc[:60]})")
            except Exception as err:  # noqa: BLE001 — sin el lugar nuevo queda el más parecido
                avisar(f"no pude dibujar el lugar {nombre}: {str(err)[:100]}; queda {e.get('fondo')}")
                e["lugar_nuevo"] = ""
                continue
        else:
            hechos.append(f"lugar reusado: {nombre}")
        e["fondo"] = nombre
    if hechos:
        avisar("; ".join(hechos))
    return hechos


def resolver_objetos(cliente, d: dict, e: "Elegido | None" = None, avisar=log.info) -> list[str]:
    """Santi, 2026-11-16 ('masa_gris' frenó el video del 16/11: lo trajo la reescritura por duración, después de
    dibujar): TODO objeto del guion que no está en la biblioteca se dibuja con Claude (queda guardado) y, si no
    se puede (o no hay cliente), pasa a ser el más parecido de la biblioteca. Corre después de dibujar, después
    de cada reescritura y antes de armar la línea de tiempo. Devuelve lo que cambió. Los lugares nuevos también
    (`crear_lugares`, 2026-11-17)."""
    from . import dibujos

    descr = {str(x.get("nombre") or "").strip(): str(x.get("descripcion") or "") for x in d.get("dibujos_nuevos") or []}
    resueltos: dict[str, str] = {}
    cambios: list[str] = crear_lugares(cliente, d, avisar)
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
        vigente = dibujos.actual(nombre) if nombre else nombre   # una versión nueva reemplaza a la vieja (2026-11-16)
        if vigente != nombre:
            cambios.append(f"{nombre} → {vigente} (versión nueva)")
            if o.get(clave) == DIBUJO_NUEVO:
                o["dibujo"] = vigente
            else:
                o[clave] = vigente
            nombre = vigente
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
        if esc_.get("decorado"):     # el decorado de contexto (reglas_v3): lo que no está, el más parecido
            esc_["decorado"] = [n_ if esc.es_prop(str(n_)) else esc.prop_parecido(str(n_))
                                for n_ in esc_["decorado"] if str(n_ or "").strip()]
    pr = d.get("protagonista")
    if isinstance(pr, dict):
        arreglar(pr)
        cambios += unificar_protagonista(d)
    return cambios


def unificar_protagonista(d: dict) -> list[str]:
    """Santi, 2026-11-16: dos dibujos del mismo objeto en un video (el Tupper olla de una prueba vieja y el nuevo):
    todo dibujo guardado que sea el mismo objeto que el protagonista pasa a ser el del protagonista, en todas las
    escenas, y el viejo sale de la biblioteca (dibujos.reemplazar)."""
    from . import dibujos

    pr = d.get("protagonista") or {}
    prota = prop_real(pr)
    guardados = dibujos.biblioteca()
    if prota not in guardados:
        return []
    desc = guardados[prota] + " " + str(pr.get("que_es") or "")
    cambios = []
    for e_ in d.get("escenas") or []:
        for o in e_.get("objetos") or []:
            n_ = prop_real(o)
            if n_ != prota and n_ in guardados and dibujos.mismo_objeto(guardados[n_], desc):
                dibujos.reemplazar(n_, prota)
                guardados.pop(n_, None)
                cambios.append(f"{n_} → {prota} (el mismo objeto)")
            if dibujos.actual(n_) == prota and n_ != prota:
                o["prop"], o["dibujo"] = (DIBUJO_NUEVO, prota) if o.get("prop") == DIBUJO_NUEVO else (prota, "")
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
                    subtitulos: str = "viral", visual: bool = False,
                    v3: bool | None = None) -> tuple[dict, list[tuple[float, str]]]:
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
    from . import gancho_v3 as gv

    v3 = REGLAS_V3 if v3 is None else v3
    ac.MANOS_V3 = bool(v3)          # usar/probar/fabricar = las manos con el objeto (2026-11-16)
    ac.SIN_PLATA_SIMBOLO = bool(v3) and USO_V4
    opciones = gv.opciones_de(d) if v3 else []
    ultimo_lugar = ""
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
        if v3 and vis is not None and vis.get("rotulo"):
            # el rótulo lleva año y lugar ("1938 · Massachusetts", Santi 2026-11-16)
            partes = [x.strip() for x in str(vis["rotulo"]).split("·") if x.strip()]
            # el año de la escena manda (es el que decide la decoración): nunca un rótulo de 1958 con monitores de hoy
            anio_r = str(anio_esc) if anio_esc else (next((x for x in partes if x.isdigit()), "") or str(anio_actual))
            lugar_r = next((x for x in partes if not x.isdigit()), "") or ultimo_lugar
            ultimo_lugar = lugar_r or ultimo_lugar
            vis = {**vis, "rotulo": " · ".join(x for x in (anio_r, lugar_r) if x)}
        if v3 and k == 0 and opciones:
            # el gancho: 2 o 3 cortes de ~1 s con la imagen imposible (gancho_v3); si la frase dura más, sigue la escena
            op = opciones[min(int(d.get("gancho_elegido") or 0), len(opciones) - 1)]
            dg = round(min(dur, 3.3) if dur - min(dur, 3.3) >= 0.6 else dur, 3)
            esc_g, fx = gv.escena_gancho(op, prota, e.get("fondo") or "ciudad", ac.semilla_fondo(anio_actual, variante),
                                         dg, seed=len(prota))
            esc_g["frase"] = k
            escenas.append(esc_g)
            sfx += [(round(t + x, 3), s_) for x, s_ in fx]
            t += dg
            dur = round(dur - dg, 3)
            if dur < 0.6:
                continue
        e = {**e, "objetos": [{**o, "prop": prop_real(o)} for o in e.get("objetos") or [] if prop_real(o)]}
        esc_d, fx = ac.escena_accion(e, dur, k, primera=(k == 0), tono=1.0 if pasado else 0.0,
                                     anio=anio_esc if 1800 <= anio_esc < presente else anio_actual,
                                     variante=variante, reservar=reservar, proyectil=proyectil, visual=vis,
                                     protagonista=prota)
        esc_d["frase"] = k          # para la revisión visual: qué frase del guion es esta escena
        if v3 and e.get("accion_escena") not in _lib.ACCIONES_V4:   # las escenas de uso traen su propia cámara
            gv.planos(esc_d)        # 2 planos o más por frase, ninguno de más de 3 s, siempre con zoom lento
            gv.sin_textos_repetidos(esc_d, str(e.get("frase") or ""))   # ningún texto se repite ni se pisa
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


LUGARES_TITO = ((150, 640), (930, 640), (150, 860), (930, 860), (150, 480), (930, 480))
CAJA_TITO = (125, 110)     # medio ancho y medio alto de la ventanita (con el signo de al lado)


def cajas_en_pantalla(e: dict, t0: float, t1: float) -> list[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) en la pantalla de lo que no se puede tapar entre t0 y t1: las personas (del sombrero a los
    pies), los objetos (menos los efectos y el decorado del fondo) y los textos grandes, con la cámara aplicada."""
    from .timeline import Elemento, Escena as _Esc

    try:
        esc_ = _Esc.desde_dict(e, 0)
    except Exception:  # noqa: BLE001
        esc_ = None
    cajas = []
    for el_d in e.get("elementos") or []:
        tipo = el_d.get("tipo")
        if el_d.get("fijo") or el_d.get("nombre") in esc.NO_REEMPLAZO + ("tito_reaccion",) or el_d.get("mueble"):
            if tipo != "gancho" and el_d.get("nombre") not in ("rotulo", "cita", "dato", "cartel_comic"):
                continue
        try:
            el = Elemento.desde_dict(el_d, "", float(e["duracion"]))
        except Exception:  # noqa: BLE001
            continue
        for t in (t0, (t0 + t1) / 2, t1):
            if "desde" in el_d and t < float(el_d["desde"]) or "hasta" in el_d and t > float(el_d["hasta"]):
                continue
            x = el.pista.valor("x", t, el.base["x"])
            y = el.pista.valor("y", t, el.base["y"])
            k = el.pista.valor("escala", t, el.base.get("escala", 1.0))
            if tipo == "personaje":
                caja = (x - 140 * k, y - 820 * k, x + 140 * k, y)
            elif tipo == "gancho" or el_d.get("nombre") in ("rotulo", "cita", "dato", "cartel_comic"):
                caja = (40.0, y - 80, 1040.0, y + 80)
            else:
                caja = (x - 120 * k, y - 120 * k, x + 120 * k, y + 120 * k)
            if not el_d.get("fijo") and esc_ is not None:
                try:
                    z, dx, dy, _r = esc_.camara_en(t)
                except Exception:  # noqa: BLE001
                    z, dx, dy = 1.0, 0.0, 0.0
                cx, cy = esc.W / 2, esc.H / 2
                caja = ((caja[0] - cx - dx) * z + cx, (caja[1] - cy - dy) * z + cy,
                        (caja[2] - cx - dx) * z + cx, (caja[3] - cy - dy) * z + cy)
            cajas.append(caja)
    return cajas


def lugar_tito(e: dict, tl: float, k: int = 0) -> tuple[float | None, float | None]:
    """Dónde va la ventanita de Tito para que no tape a ninguna persona ni objeto importante (Santi, 2026-11-17):
    la primera esquina libre, empezando por la que toca (se alternan). None si no hay ninguna libre."""
    cajas = cajas_en_pantalla(e, tl, tl + 1.6)
    hw, hh = CAJA_TITO
    orden = LUGARES_TITO[k % 2::2] + LUGARES_TITO[1 - k % 2::2]
    for x, y in orden:
        if not any(x - hw < c[2] and c[0] < x + hw and y - hh < c[3] and c[1] < y + hh for c in cajas):
            return x, y
    return None, None


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
            x, y = lugar_tito(e, tl, k)
            if x is None:          # no hay lugar libre en la pantalla: esta vez Tito no aparece (nunca tapa a nadie)
                proxima += 2.0
                continue
            e["elementos"].append({"tipo": "prop", "nombre": "tito_reaccion", "forma": k % 3, "fijo": True,
                                   "x": x, "y": y, "escala": 0.8, "desde": tl, "hasta": round(tl + 1.6, 2),
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
                                               "rehacer_gancho", "redibujar_objeto", "otro"]},
        "objeto": {"type": "STRING"}},
    "required": ["cuadro", "que", "arreglo", "objeto"]}},
    "reglas": calidad.SCHEMA_REGLAS}, "required": ["problemas", "reglas"]}
ARREGLOS = ("mover_objeto", "cambiar_soporte", "sacar_objeto", "separar_personajes", "sacar_texto", "cambiar_accion",
            "rehacer_gancho", "redibujar_objeto", "otro")
CUADROS_REVISION = 8
VUELTAS_REVISION = 2      # vueltas de corrección; después, una última que solo mira (estándar de calidad)
RESCATE_USD = 0.50        # el rescate de un video que quedaría retenido, aparte del tope de las correcciones
AVISO_VIDEO_USD = 1.50    # Santi, 2026-11-17: si un video pasa de esto en total, se le avisa


def cuadros_clave(datos: dict, maximo: int = CUADROS_REVISION) -> list[tuple[float, int, str]]:
    """(segundo, índice de escena en `datos`, qué es) de los cuadros a revisar: el gancho, el viaje en
    el tiempo y el medio de cada escena de acción (hasta `maximo`)."""
    # Frisbee, 17/11: con 4 viajes en el tiempo y el mapa, 5 de los 8 cuadros eran el reloj y el mapa, y la escena de
    # las manos vacías no la vio nadie. Ahora: UN cuadro por cada escena de la historia (gancho incluido); el viaje y
    # el mapa (siempre iguales, de la marca del canal) no se miran. Si hay más escenas que `maximo`, se miran todas
    # igual: la revisión tiene que ver cada frase.
    t, out = 0.0, []
    vistas: set = set()
    for i, e in enumerate(datos["escenas"]):
        dur = float(e["duracion"])
        k = e.get("frase")
        if not e.get("girar") and not e.get("congela") and isinstance(k, int) and k not in vistas:
            vistas.add(k)
            frac = 0.75 if not out else 0.55
            out.append((t + dur * frac, i, "gancho" if not out else f"escena {k + 1}"))
        t += dur
    return out


def _jpeg_512(png: Path) -> bytes:
    import io

    from PIL import Image

    im = Image.open(png).convert("RGB")
    im.thumbnail((512, 512))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    return b.getvalue()


SISTEMA_ELEGIR_GANCHO = """Elegís el GANCHO de un video corto animado (los primeros 3 segundos; en Facebook se va el 65 %
entre el segundo 3 y el 7). Cada imagen es una opción: sus 2 o 3 cortes, uno al lado del otro. La pregunta es una sola:
¿FRENARÍAS EL DEDO CON ESTO, scrolleando el celular? Gana la más sorprendente o imposible, la que se entiende en un
golpe de vista, con el producto bien visible, colores fuertes y movimiento; pierde la confusa, la vacía o la que tapa
el producto. `mejor` es el número de la opción (desde 1) y `por_que`, corto."""
SCHEMA_ELEGIR_GANCHO = {"type": "OBJECT", "properties": {"mejor": {"type": "INTEGER"}, "por_que": {"type": "STRING"}},
                        "required": ["mejor", "por_que"]}


def tira_del_gancho(datos: dict, carpeta: Path, n: int, capturar=None) -> bytes:
    """Los cortes del gancho (escena 0) en una sola imagen, uno al lado del otro (JPEG chico)."""
    import io

    from PIL import Image

    from . import render as rd
    from .timeline import Video

    esc0 = datos["escenas"][0]
    dur = float(esc0["duracion"])
    cortes = 3 if dur >= 2.4 else 2
    video = Video.desde_dict({**datos, "audio": None})
    pngs = []
    for c in range(cortes):
        png = carpeta / f"gancho_{n}_{c}.png"
        t = dur * (c + 0.6) / cortes
        if capturar:
            capturar(datos, t, png)
        else:
            rd.cuadro_png(video, min(video.total_cuadros - 1, int(t * video.fps)), png, escala=0.35)
        pngs.append(Image.open(png).convert("RGB"))
    alto = min(im.height for im in pngs)
    pngs = [im.resize((int(im.width * alto / im.height), alto)) for im in pngs]
    tira = Image.new("RGB", (sum(im.width for im in pngs) + 8 * (len(pngs) - 1), alto), "white")
    x = 0
    for im in pngs:
        tira.paste(im, (x, 0))
        x += im.width + 8
    tira.thumbnail((900, 900))
    b = io.BytesIO()
    tira.save(b, "JPEG", quality=80)
    (carpeta / f"gancho_opcion_{n + 1}.jpg").write_bytes(b.getvalue())
    return b.getvalue()


def elegir_gancho(cliente, d: dict, armar, carpeta: Path, avisar=log.info, capturar=None) -> str:
    """Santi, 2026-11-16: 3 opciones de gancho por video y la revisión visual elige la más llamativa. `armar(d)`
    devuelve los datos de la línea de tiempo. Deja `d["gancho_elegido"]` y devuelve qué eligió."""
    from . import gancho_v3 as gv

    ops = gv.opciones_de(d)
    if cliente is None or len(ops) < 2:
        return ""
    tiras = []
    for j in range(len(ops)):
        d["gancho_elegido"] = j
        tiras.append(tira_del_gancho(armar(d), carpeta, j, capturar))
    lista = "\n".join(f"Opción {j + 1}: {o['tipo']} — texto «{o['texto']}»" for j, o in enumerate(ops))
    try:
        r = json.loads(cliente.json(SISTEMA_ELEGIR_GANCHO, lista, SCHEMA_ELEGIR_GANCHO, 0.2, imagenes=tiras))
        mejor = int(r.get("mejor") or 1)
    except Exception as err:  # noqa: BLE001 — sin respuesta, la primera opción
        avisar(f"elección del gancho: no respondió ({str(err)[:120]}); va la 1")
        mejor, r = 1, {"por_que": "sin respuesta"}
    mejor = max(1, min(len(ops), mejor))
    d["gancho_elegido"] = mejor - 1
    o = ops[mejor - 1]
    txt = f"gancho elegido: opción {mejor} de {len(ops)} ({o['tipo']}, «{o['texto']}»): {str(r.get('por_que') or '')[:140]}"
    avisar(txt)
    return txt


GANCHO_REHACER = ("el GANCHO (escena 1) es lo más importante del video (en Facebook se va el 65 % entre el segundo 3 "
                  "y el 7): mostrá el momento MÁS SORPRENDENTE de esta historia CON ACCIÓN (alguien haciendo algo, en "
                  "su lugar) y el objeto protagonista a la vista; nada de escenario vacío, gente parada, el objeto "
                  "girando solo ni un arranque anterior del canal")


def sistema_revision_v3() -> str:
    """La revisión con las reglas_v3 (Santi, 2026-11-16): el gancho ya no se juzga como una escena de la historia con
    gente (es a propósito la imagen imposible del producto), y se suman el producto en uso, los textos y el decorado."""
    base = SISTEMA_REVISION
    for desde in ("- (Santi, 2026-11-15) el GANCHO (cuadro 1) no muestra algo",
                  "- (2026-11-15) el gancho NO muestra el producto",
                  "- (2026-11-15) EL GANCHO (cuadro 1) repetido"):
        if desde in base:
            a = base.index(desde)
            b = base.find("\n- ", a + 3)
            fin = base.find("Para cada problema:", a)
            if b == -1 or (fin != -1 and fin < b):
                base = base[:a] + base[fin:]
            else:
                base = base[:a] + base[b + 1:]
    return base + REVISION_V3


REVISION_V4 = """
(Santi, 2026-11-16) Y además:
- MANOS cuyo movimiento no se lee como una acción concreta en 1 segundo (agarrar, abrir, guardar, contar, firmar, dar), o
  manos sosteniendo una moneda con $ o una bolsa de plata gigante: `arreglo` = cambiar_accion.
- Un OBJETO SIN DETALLE (una silueta negra, una etiqueta en blanco, un dibujo que no se reconoce): `arreglo` =
  redibujar_objeto, con su nombre en `objeto` y en `que` cómo tendría que verse."""


REVISION_V3 = """
(Santi, 2026-11-16) Con las reglas nuevas:
- El GANCHO (cuadro 1) es A PROPÓSITO la imagen imposible del producto (gigante, explotando, multiplicado, volando o
  una multitud peleándose por él) sobre rayos de colores fuertes, con el texto grande: NO lo marques por no tener gente,
  lugar ni escena de la historia. La única pregunta: ¿frenarías el dedo con esto? Si el producto no se reconoce, está
  tapado o es aburrido: `arreglo` = rehacer_gancho (se prueba otra de las opciones).
- El PRODUCTO FLOTANDO o girando en el aire sin motivo, o cerca de una mano en vez de agarrado, o una escena donde no
  se ve el producto en uso (guardando comida, siendo amasado, siendo resuelto…): `arreglo` = cambiar_accion.
- ALGUIEN PARADO SIN HACER NADA (brazos abajo, quieto, mirando): `arreglo` = cambiar_accion, SIEMPRE.
- Un PRIMER PLANO que corta caras en vez de mostrar las manos con el objeto: `arreglo` = otro.
- Un TEXTO repetido (la misma cifra o año dos veces, o lo mismo que el subtítulo) o dos textos pisados: `arreglo` =
  sacar_texto.
- DECORACIÓN sin relación con la historia: `arreglo` = sacar_objeto con su nombre en `objeto`.
- (Santi, 2026-11-17, el Frisbee) MANOS LEVANTADAS, VACÍAS o que no tocan ningún objeto (dos manos en el aire sin
  agarrar nada, o el objeto lejos de las manos): `arreglo` = cambiar_accion, SIEMPRE. No se entiende qué hacen.
- (Santi, 2026-11-17) EL LUGAR NO ES EL DE LA HISTORIA: si la frase o lo que se sabe de la historia dice dónde pasó
  (una playa, un estadio, una cocina, una fábrica, una tienda), la escena tiene que estar ahí; un living, una casa o un
  taller genéricos para algo que pasó en otro lado, o un puerto para una playa: `arreglo` = cambiar_accion y en `que`
  decí cuál es el lugar de la historia.
- Una ventana, puerta o cuadro flotando en el medio de la pared o delante de los muebles: `arreglo` = sacar_objeto.
- Una escena que NO SE ENTIENDE SIN LA VOZ (le faltan los elementos que la hacen reconocible): `arreglo` = cambiar_accion;
  un dibujo que no tiene los detalles que dice la frase (una lata que no parece de pintura): `arreglo` =
  redibujar_objeto con su nombre en `objeto`."""


CATEGORIAS_FLOJAS = ("gancho", "accion", "objeto", "personajes", "camara", "texto", "decorado", "ritmo", "efectos")
SISTEMA_FLOJAS = """Mirás los cuadros clave de un video animado corto de "Así Nació" ya terminado. Decí las 3 cosas MÁS FLOJAS
(las que más le restan al video, aunque no estén mal del todo), para mejorar el motor de animación: cada una con
`cuadro` (el número de la imagen que mejor la muestra), `categoria` y `que` (concreto: qué se ve y qué faltaría).
La categoría `gancho` es el cuadro 1. Nada de elogios."""
SCHEMA_FLOJAS = {"type": "OBJECT", "properties": {"flojas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "cuadro": {"type": "INTEGER"}, "categoria": {"type": "STRING", "enum": list(CATEGORIAS_FLOJAS)},
    "que": {"type": "STRING"}}, "required": ["cuadro", "categoria", "que"]}}}, "required": ["flojas"]}


def puntos_flojos(cliente, d: dict, datos: dict, carpeta: Path, avisar=log.info) -> list[dict]:
    """Mejora continua (Santi, 2026-11-16): después de cada video, las 3 cosas más flojas con un cuadro de ejemplo
    (los de la revisión visual). Se cruzan con las estadísticas de 24 h y alimentan las mejoras de los lunes y jueves."""
    claves = cuadros_clave(datos)
    pngs = [carpeta / f"revision_{n + 1}.png" for n in range(len(claves))]
    pngs = [p for p in pngs if p.exists()]
    if cliente is None or not pngs:
        return []
    lista = "\n".join(f"Cuadro {n + 1}: {q}" for n, (_t, _i, q) in enumerate(claves[:len(pngs)]))
    r = json.loads(cliente.json(SISTEMA_FLOJAS, f"{d.get('titulo')}\n{lista}", SCHEMA_FLOJAS, 0.3,
                                imagenes=[_jpeg_512(p) for p in pngs]))
    out = []
    for x in (r.get("flojas") or [])[:3]:
        n = int(x.get("cuadro") or 1)
        png = pngs[n - 1] if 1 <= n <= len(pngs) else pngs[0]
        out.append({"categoria": str(x.get("categoria") or "accion"), "que": str(x.get("que") or "")[:300],
                    "cuadro": str(png)})
    avisar("lo más flojo: " + " | ".join(f"{x['categoria']}: {x['que'][:80]}" for x in out))
    return out


def redibujar_objeto(cliente, nombre: str, como_es: str, avisar=log.info) -> str:
    """Santi, 2026-11-16 ("si un objeto no tiene dibujo bueno, dibujalo nuevo"): Sonnet lo dibuja de nuevo con detalle y
    la versión nueva reemplaza a la vieja en todas las escenas, también si era un dibujo de la biblioteca de código."""
    from . import dibujos

    nombre = re.sub(r"[^a-z0-9_]", "", nombre)[:24]
    if not nombre or not esc.es_prop(nombre) or cliente is None:
        return ""
    nuevo = f"{nombre}_det"[:30]
    try:
        dibujos.dibujar(cliente, nuevo, f"{nombre.replace('_', ' ')} con detalle (sin siluetas ni etiquetas en blanco). "
                                        f"Cómo tiene que verse: {como_es}")
    except Exception as err:  # noqa: BLE001
        avisar(f"no pude redibujar {nombre}: {str(err)[:120]}")
        return ""
    dibujos.reemplazar(nombre, nuevo)
    return f"redibujé {nombre} con detalle ({nuevo}): {como_es[:90]}"


def redibujar_protagonista(cliente, d: dict, como_es: str, avisar=log.info) -> str:
    """La revisión vio que el protagonista no se parece al real: Sonnet lo dibuja de nuevo con la descripción y
    reemplaza al anterior en todas las escenas (queda guardado para los próximos videos)."""
    from . import dibujos

    pr = d.get("protagonista") or {}
    viejo = prop_real(pr)
    if not viejo or cliente is None:
        return ""
    base = re.sub(r"[^a-z0-9_]", "", str(pr.get("que_es") or viejo).lower().replace(" ", "_"))[:24] or viejo
    nuevo = f"{base}_real" if base != viejo else f"{viejo}_real"
    if not dibujos.nombre_valido(nuevo):
        nuevo = f"{viejo}_real"[:30]
    try:
        dibujos.dibujar(cliente, nuevo, f"{pr.get('que_es') or viejo}. Cómo es el real: {como_es}")
    except Exception as err:  # noqa: BLE001 — si no sale, queda el de antes
        avisar(f"no pude redibujar {viejo}: {str(err)[:120]}")
        return ""
    for e_ in d.get("escenas") or []:
        for o in e_.get("objetos") or []:
            if prop_real(o) == viejo:
                o["prop"], o["dibujo"] = DIBUJO_NUEVO, nuevo
    pr["prop"], pr["dibujo"] = DIBUJO_NUEVO, nuevo
    if viejo in dibujos.biblioteca():      # la versión vieja sale de la biblioteca (Santi, 2026-11-16)
        dibujos.reemplazar(viejo, nuevo)
    return f"redibujé el protagonista ({viejo} → {nuevo}): {como_es[:100]}"


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
                                   d, errores, schema_guion(), "escenas", "escena")
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
        deco = [x for x in e.get("decorado") or [] if obj and obj in str(x).lower()]
        if arreglo == "sacar_objeto" and deco:
            e["decorado"] = [x for x in e.get("decorado") or [] if x not in deco]
            hechos.append(f"escena {k + 1}: saqué del decorado {', '.join(deco)} ({pr.get('que')})")
        elif arreglo == "sacar_objeto" and cual is not None:
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


def ficha_escena(esc_k: dict, d: dict) -> dict:
    """La FICHA de una escena (Santi, 2026-11-17: "cada escena se planifica antes de dibujarla"): quién aparece con
    su rol y su ropa, dónde, en qué año, qué hace cada uno, con qué objetos y en qué plano. El dibujo sale de acá (la
    ropa con `ac.vestir`, lo que tiene en las manos con `ac.TRABAJO_ROL`) y la revisión la usa para comparar."""
    anio = int(esc_k.get("anio_escena") or 0) or 2026
    prota = (d.get("protagonista") or {})
    gente = []
    for a in esc_k.get("actores") or []:
        rol = str(a.get("rol") or "joven")
        nombre, cambios, _ = ac.aspecto(rol, a.get("genero") or "", a.get("edad") or "")
        genero = ac.genero_de(nombre, cambios, a.get("genero") or "")
        ropa = ac.vestir(rol, anio, genero) if a.get("edad") != "chico" and rol not in ac.NINOS else {}
        piezas = ropa.get("vestuario") or "ropa común"
        sombrero = ropa.get("sombrero") or cambios.get("sombrero") or "ninguno"
        accion = str(a.get("accion") or "quieto")
        hace = ac.QUE_HACE_ROL.get(rol, "") if accion == "quieto" else accion
        lleva = ac.TRABAJO_ROL.get(rol, "").replace("{prota}", str(prota.get("prop") or "el producto")) \
            if accion == "quieto" else ""
        gente.append({"quien": a.get("persona_real") or rol, "rol": rol, "genero": genero, "edad": a.get("edad") or "",
                      "ropa": piezas.replace("+", " + "), "sombrero": sombrero, "hace": hace, "en_las_manos": lleva})
    return {"lugar": esc_k.get("lugar_nuevo") or esc_k.get("fondo") or "", "anio": anio, "gente": gente,
            "objetos": [o.get("prop") for o in esc_k.get("objetos") or [] if o.get("prop")],
            "accion_escena": esc_k.get("accion_escena") or "", "plano": esc_k.get("plano") or ""}


def texto_ficha(f: dict) -> str:
    gente = "; ".join(f"{g['quien']} ({g['rol']}, {g['genero']} {g['edad']}, {g['ropa']}, sombrero {g['sombrero']}): "
                      f"{g['hace']}{' con ' + g['en_las_manos'] if g['en_las_manos'] else ''}" for g in f["gente"])
    return (f"FICHA: lugar {f['lugar']}, año {f['anio']}; gente: {gente or '-'}; objetos: "
            f"{', '.join(f['objetos']) or '-'}; plano {f['plano'] or 'normal'}")


def guardar_fichas(d: dict, carpeta: Path) -> None:
    try:
        (carpeta / "fichas.json").write_text(json.dumps([ficha_escena(e, d) for e in d.get("escenas") or []],
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as err:
        log.warning("fichas: no pude guardarlas (%s)", err)


REVISION_FICHA = """
(Santi, 2026-11-17) Cada cuadro trae la FICHA de su escena (quién aparece con su rol y su ropa, dónde, en qué año, qué
hace cada uno). Por cada persona del cuadro respondete: ¿QUIÉN ES (se entiende su rol por la ropa y lo que hace)?,
¿QUÉ ESTÁ HACIENDO?, ¿ESTO PASABA EN ESE AÑO Y EN ESE LUGAR? Si alguna respuesta no es clara, la escena se corrige:
- una persona sin rol claro, con la ropa equivocada para su rol o su época, o de relleno: `arreglo` = cambiar_accion;
- alguien con las manos juntas o vacías mirando a cámara, o un obrero que no trabaja, un cajero que no cobra, un
  cliente que no compra: `arreglo` = cambiar_accion, SIEMPRE;
- una línea de producción vacía o sin gente trabajando en ella: `arreglo` = cambiar_accion;
- algo que no existía en ese año o en ese lugar (máquinas modernas de colores en el siglo XIX, un camión o edificios
  modernos en 1882, pantallas antes de 1980, engranajes sin que la frase hable de una máquina): `arreglo` =
  sacar_objeto con su nombre en `objeto` o cambiar_accion si es el lugar entero;
- un fondo pobre: menos de 3 detalles que digan DÓNDE y CUÁNDO (carteles pintados, faroles, carros, adoquines,
  cajas del producto, ladrillo, ropa de época): `arreglo` = otro, y en `que` cuáles faltan;
- la ventanita de Tito tapando a una persona o un objeto importante: `arreglo` = otro."""


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
        extra = (f" — dice: «{frases[k]}» ({texto_ficha(ficha_escena(esc_k, d))}; protagonista: "
                 f"{(d.get('protagonista') or {}).get('que_es')})"
                 if isinstance(k, int) and k < len(frases) else "")
        return q + extra
    lista = "\n".join(f"Cuadro {n + 1}: {qd(i, q)}" for n, (_t, i, q) in enumerate(claves))
    lista += ("\n\nARRANQUES ANTERIORES DEL CANAL:\n" + texto_ganchos(ganchos_recientes(conn)[:-1])
              if conn is not None else "")
    sistema = ((sistema_revision_v3() + (REVISION_V4 if USO_V4 else "")) if REGLAS_V3 else SISTEMA_REVISION)
    sistema += REVISION_FICHA
    guardar_fichas(d, carpeta)
    sistema += calidad.para_prompt("asinacio") + ("\nToda regla que no se cumple va TAMBIÉN en `problemas`, con su "
                                                   "cuadro y el arreglo que la corrige.")
    try:
        r_ = json.loads(cliente.json(sistema, f"Los cuadros, en orden:\n{lista}", SCHEMA_REVISION, 0.2,
                                     imagenes=imagenes))
    except Exception as err:   # la revisión es una red de seguridad: si no responde, sigue
        avisar(f"revisión visual: no respondió ({str(err)[:120]})")
        d["_estandar_ok"] = False
        return [], claves
    problemas = list(r_.get("problemas") or [])
    # el estándar de calidad (Santi, 2026-11-16): lo que no cumple y la revisión no puso en `problemas` se suma con el
    # arreglo de la regla, así se corrige igual
    fallas = calidad.fallas_de(r_.get("reglas"), "asinacio")
    d["_estandar"], d["_estandar_ok"] = fallas, True
    return problemas_del_estandar(fallas, problemas, len(claves)), claves


MEJORAS_PRIMERO = "mejoras_primero"   # bot_estado: [{fecha, video, frase, reglas, que, enviada}]


def _anotar_mejoras_primero(conn, video: str, sin_arreglo: list[dict]) -> None:
    """Una escena que ni la biblioteca pudo arreglar: su regla va PRIMERA en las mejoras al motor de la semana
    (Santi, 2026-11-16)."""
    from clips_bot import db

    try:
        lista = json.loads(db.get_valor(conn, MEJORAS_PRIMERO) or "[]")
        for x in sin_arreglo:
            lista.append({"fecha": date.today().isoformat(), "video": video, **x, "enviada": False})
        db.set_valor(conn, MEJORAS_PRIMERO, json.dumps(lista[-60:], ensure_ascii=False))
    except Exception as err:  # noqa: BLE001
        log.warning("mejoras primero: no pude anotar (%s)", err)


def problemas_del_estandar(fallas: list[dict], problemas: list[dict], n_cuadros: int) -> list[dict]:
    """Cada regla del estándar que no se cumple y que la revisión no puso en `problemas` se suma con el arreglo de la
    regla (ESTANDAR_CALIDAD.md), así se corrige igual."""
    reglas_ = calidad.por_id("asinacio")
    out = list(problemas)
    for f in fallas:
        arreglo = reglas_[f["id"]].arreglo if f["id"] in reglas_ else "otro"
        if arreglo in ARREGLOS and 1 <= f["cuadro"] <= n_cuadros and not any(
                int(pr.get("cuadro") or 0) == f["cuadro"] and pr.get("arreglo") == arreglo for pr in out):
            out.append({"cuadro": f["cuadro"], "que": f"{f['id']}: {f['que']}", "arreglo": arreglo, "objeto": ""})
    return out


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
    flojas: list = field(default_factory=list)        # las 3 cosas más flojas, con su cuadro (mejora continua, 2026-11-16)
    estandar: dict = field(default_factory=dict)      # el estándar de calidad: fallas finales, corregidas (2026-11-16)
    piezas_usd: float = 0.0                           # Claude en piezas nuevas (objetos y lugares dibujados), 2026-11-17
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


def piezas_desde(conn, fila: int) -> float:
    """US$ de Claude en piezas nuevas (dibujos de objetos y de lugares) después de la fila `fila` (Santi, 2026-11-17)."""
    from clips_bot import claude

    try:
        return round(sum(claude.costo(mod, e or 0, s or 0) for mod, e, s in conn.execute(
            "SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND rowid > ? AND funcion LIKE "
            "'%dibujos.%'", (fila,))), 4)
    except Exception:  # noqa: BLE001
        return 0.0


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
    global REGLAS_V3, USO_V4, ESCENAS_PREVIAS, COMPLETAS_PREVIAS
    REGLAS_V3 = bool(getattr(cfg, "reglas_v3", False))
    ESCENAS_PREVIAS = escenas_recientes(conn) if conn is not None else []
    COMPLETAS_PREVIAS = completas_recientes(conn) if conn is not None else []
    USO_V4 = REGLAS_V3 and bool(getattr(cfg, "uso_manos", False))
    _lib.CON_V4 = USO_V4
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
    if REGLAS_V3:
        completar_v3(cliente, d, avisar)     # las 3 opciones de gancho y el decorado (pedido aparte)
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
        if REGLAS_V3:
            completar_v3(cliente, d, avisar)
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
    if REGLAS_V3:
        # 3 opciones de gancho: la revisión visual elige la más llamativa (Santi, 2026-11-16)
        def _armar(d_):
            return linea_de_tiempo(d_, inicios, fin, palabras, wav,
                                   subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico",
                                   visual=getattr(cfg, "visual_plus", False))[0]
        elegido = elegir_gancho(cliente, d, _armar, carpeta, avisar)
        if elegido:
            revision.append(elegido)
            datos, eventos = linea_de_tiempo(d, inicios, fin, palabras, wav,
                                             subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico",
                                             visual=getattr(cfg, "visual_plus", False))
    # Estándar de calidad (Santi, 2026-11-16): 2 vueltas de corrección y una última que solo mira; lo que no se
    # cumplió después de corregir sale en el mensaje y queda anotado para el resumen de los lunes.
    primeras: list[str] | None = None
    fila_rev = ultima_fila_uso(conn) if conn is not None else 0
    tope_rev = _rz.TOPE_CORRECCIONES_USD

    def costo_rev() -> float:
        return costo_desde(conn, fila_rev) if conn is not None else 0.0

    frenado = 0.0
    ultima: tuple[list, list] = ([], [])
    for vuelta in range(VUELTAS_REVISION + 1):
        problemas, claves = revisar_visual(cliente, d, datos, carpeta, avisar=avisar, conn=conn)
        ultima = (claves, problemas)
        if primeras is None and d.get("_estandar_ok"):
            primeras = [f["id"] for f in d.get("_estandar") or []]
        if not problemas:
            revision.append(f"vuelta {vuelta + 1}: sin problemas" if vuelta else "revisión visual: sin problemas")
            break
        if vuelta == VUELTAS_REVISION:
            revision.append(f"vuelta {vuelta + 1}: quedó sin corregir: "
                            + "; ".join(str(pr.get("que") or "")[:80] for pr in problemas[:4]))
            break
        if costo_rev() > tope_rev:      # Santi, 2026-11-16: las correcciones de un video, como mucho US$ 0,50
            frenado = costo_rev()
            revision.append(f"correcciones frenadas: ya iban US$ {frenado:.2f} (tope {tope_rev:g})")
            avisar(revision[-1])
            break
        if REGLAS_V3:
            # Santi, 2026-11-16: "nadie parado sin hacer nada, nunca: la revisión lo rechaza siempre"; y el producto
            # flotando sin motivo. Aunque la revisión lo marque como "otro", esa escena se rehace (salvo el gancho, que
            # flota a propósito).
            for pr in problemas:
                n_ = int(pr.get("cuadro") or 0) - 1
                es_gancho = 0 <= n_ < len(claves) and datos["escenas"][claves[n_][1]].get("gancho_v3")
                if not es_gancho and pr.get("arreglo") in ("otro", "mover_objeto", "cambiar_soporte", "separar_personajes") \
                        and re.search(r"parad|sin hacer nada|quiet|flota|en el aire|brazos abiertos|brazos arriba",
                                      str(pr.get("que") or ""), re.I):
                    pr["arreglo"] = "cambiar_accion"
        hechos = aplicar_revision(d, problemas, claves, datos)
        prota_ = prop_real(d.get("protagonista") or {})
        for pr in [p_ for p_ in problemas if p_.get("arreglo") == "redibujar_objeto"][:2]:
            obj_ = str(pr.get("objeto") or "").strip().lower()
            if not obj_ or obj_ == prota_ or obj_ in str((d.get("protagonista") or {}).get("que_es") or "").lower():
                hecho = redibujar_protagonista(cliente, d, str(pr.get("que") or ""), avisar)
            else:
                hecho = redibujar_objeto(cliente, obj_, str(pr.get("que") or ""), avisar) if USO_V4 else ""
            if hecho:
                hechos.append(hecho)
        # lo que se corrige en el guion: la acción que no es la de la frase, la gente parada y el gancho
        # repetido o sin acción (Santi, 2026-11-15: "que lo corrija sola, no solo que lo marque")
        acciones_mal = [(int(pr.get("cuadro") or 0) - 1, str(pr.get("que") or "")) for pr in problemas
                        if pr.get("arreglo") in ("cambiar_accion", "rehacer_gancho")
                        or (pr.get("arreglo") == "otro" and int(pr.get("cuadro") or 0) == 1)]
        if REGLAS_V3 and d.get("ganchos"):
            # el gancho de las reglas nuevas no se reescribe: se prueba la opción siguiente (Santi, 2026-11-16)
            # solo "rehacer_gancho" cambia de opción; lo demás de esa escena (gente parada…) se corrige como siempre
            del_gancho = [(int(pr.get("cuadro") or 0) - 1, str(pr.get("que") or "")) for pr in problemas
                          if pr.get("arreglo") == "rehacer_gancho"]
            acciones_mal = [a for a in acciones_mal if not any(a[0] == g[0] and a[1] == g[1] for g in del_gancho)]
            probados = d.setdefault("ganchos_probados", [int(d.get("gancho_elegido") or 0)])
            libres = [j for j in range(len(d["ganchos"])) if j not in probados]
            if del_gancho and libres:
                d["gancho_elegido"] = libres[0]
                probados.append(libres[0])
                hechos.append(f"gancho: pasé a la opción {libres[0] + 1} ({del_gancho[0][1][:100]})")
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
    # Lo que sigue sin pasar después de las 2 vueltas: esa escena se reemplaza por una de la biblioteca de escenas
    # aprobadas (Santi, 2026-11-16; reemplazo.py), chequeada con Haiku; el resto del video no se toca.
    reemplazos, sin_arreglo = [], []
    claves_f, problemas_f = ultima
    revisado = bool(d.get("_estandar_ok"))
    if revisado and problemas_f and not frenado:
        from clips_bot import claude as _claude

        haiku = _claude.cliente(_claude.HAIKU, esfuerzo="low")
        por_frase: dict[int, list[str]] = {}
        for pr in problemas_f:
            n_ = int(pr.get("cuadro") or 0) - 1
            if not 0 <= n_ < len(claves_f):
                continue
            esc_t = datos["escenas"][claves_f[n_][1]]
            k = esc_t.get("frase")
            if not isinstance(k, int) or k == 0 or esc_t.get("gancho_v3") or esc_t.get("girar"):
                continue
            ids = re.findall(r"AN-\d+", str(pr.get("que") or "")) + [
                f["id"] for f in d.get("_estandar") or [] if f.get("cuadro") == n_ + 1]
            por_frase.setdefault(k, [])
            por_frase[k] += [i for i in ids if i not in por_frase[k]]

        def _armar_todo(d_):
            return linea_de_tiempo(d_, inicios, fin, palabras, wav,
                                   subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico",
                                   visual=getattr(cfg, "visual_plus", False))

        clave_video = f"{hoy.isoformat()}/{e.marca.nombre}/{e.angulo}"
        for k, ids in por_frase.items():
            if costo_rev() > tope_rev:
                frenado = costo_rev()
                revision.append(f"reemplazo de escenas frenado: ya iban US$ {frenado:.2f} (tope {tope_rev:g})")
                break
            hecho = _rz.reemplazar(haiku, d, datos, eventos, k, ids, _armar_todo, clave_video, e.marca.nombre,
                                   carpeta, sigue=lambda: costo_rev() <= tope_rev, avisar=avisar)
            if hecho:
                datos, eventos, d, texto_ = hecho
                reemplazos.append(texto_)
                revision.append(texto_)
                cuadros_k = {n + 1 for n, (_t, i, _q) in enumerate(claves_f) if datos["escenas"][i].get("frase") == k}
                d["_estandar"] = [f for f in d.get("_estandar") or [] if f.get("cuadro") not in cuadros_k]
                problemas_f = [pr for pr in problemas_f if int(pr.get("cuadro") or 0) not in cuadros_k]
            else:
                sin_arreglo.append({"frase": k + 1, "reglas": ids or ["AN-02"],
                                    "que": "; ".join(str(pr.get("que") or "")[:120] for pr in problemas_f
                                                     if 0 < int(pr.get("cuadro") or 0) <= len(claves_f)
                                                     and datos["escenas"][claves_f[int(pr["cuadro"]) - 1][1]].get("frase") == k)})
        if sin_arreglo and conn is not None:
            _anotar_mejoras_primero(conn, clave_video, sin_arreglo)
    # Rescate (Santi, 2026-11-17): antes de mandarle a Santi un video que no se publicaría solo, se rehacen ENTERAS las
    # escenas que fallan, creando lo que falte (objetos y lugares nuevos quedan guardados), y se vuelve a mirar una
    # vez. Con su propio tope de costo, aparte del de las correcciones.
    rescate = ""
    if revisado and calidad.retener("asinacio", d.get("_estandar") or [], True) and conn is not None and cliente is not None:
        fila_res = ultima_fila_uso(conn)
        malas = []
        for pr in problemas_f:
            n_ = int(pr.get("cuadro") or 0) - 1
            if 0 <= n_ < len(claves_f) and not datos["escenas"][claves_f[n_][1]].get("gancho_v3"):
                malas.append((n_, "REHACÉ LA ESCENA ENTERA para esta historia (acción, objetos, plano, movimiento y el "
                                  "lugar real; si falta un objeto, dibujo_nuevo; si falta el lugar, lugar_nuevo): "
                              + str(pr.get("que") or "")))
        if malas:
            avisar(f"rescate: el estándar quedó en {calidad.puntaje('asinacio', d.get('_estandar') or [])}; "
                   f"rehago {len(malas)} escenas")
            d, hecho = corregir_acciones(cliente, d, e, fuente, malas[:4], claves_f, datos, avisar,
                                         ganchos=texto_ganchos(ganchos_recientes(conn)[:-1]))
            resolver_objetos(cliente, d, e, avisar)
            datos, eventos = linea_de_tiempo(d, inicios, fin, palabras, wav,
                                             subtitulos="viral" if settings.animacion.subtitulos_virales else "clasico",
                                             visual=getattr(cfg, "visual_plus", False))
            if costo_desde(conn, fila_res) <= RESCATE_USD:
                problemas_f, claves_f = revisar_visual(cliente, d, datos, carpeta, avisar=avisar, conn=conn)
                revisado = bool(d.get("_estandar_ok"))
            ok_, total_ = calidad.puntaje("asinacio", d.get("_estandar") or [])
            rescate = (f"rescate: rehice {len(malas[:4])} escenas"
                       + (f" ({hecho})" if hecho else "") + f"; el estándar quedó en {ok_}/{total_}")
            revision.append(rescate)
    if revisado:
        try:
            n_ok = _rz.guardar_aprobadas(d, _rz.escenas_que_pasaron(datos, claves_f, problemas_f),
                                         f"{hoy.isoformat()}/{e.marca.nombre}/{e.angulo}", e.marca.nombre)
            avisar(f"biblioteca de escenas aprobadas: +{n_ok}")
        except Exception as err:  # noqa: BLE001 — guardar nunca frena el video
            avisar(f"biblioteca de escenas aprobadas: no pude guardar ({str(err)[:100]})")
    tiempos["revision_s"] = round(time.time() - t0, 1)
    finales = list(d.get("_estandar") or []) if revisado else []
    estandar = {"revisado": revisado, "fallas": finales,
                "corregidas": sorted(set(primeras or []) - {f["id"] for f in finales}),
                "guion": [str(x) for x in d.get("_estilo_pendiente") or []],
                "reemplazos": reemplazos, "sin_arreglo": sin_arreglo,
                "frenado_usd": round(frenado, 3), "costo_correcciones_usd": round(costo_rev(), 3), "rescate": rescate}
    try:
        anotar_escenas(conn, d, f"{hoy.isoformat()}/{e.marca.nombre}/{e.angulo}", e.marca.nombre)
    except Exception as err:  # noqa: BLE001 — anotar nunca frena el video
        avisar(f"no pude anotar las escenas: {err}")
    calidad.anotar(conn, "asinacio", f"{hoy.isoformat()}/{e.marca.nombre}/{e.angulo}", finales,
                   estandar["corregidas"], [("AN-21", g_[:240]) for g_ in estandar["guion"]], revisado,
                   dia=hoy.isoformat())
    try:
        flojas = puntos_flojos(cliente, d, datos, carpeta, avisar)      # mejora continua (Santi, 2026-11-16)
    except Exception as err:  # noqa: BLE001 — anotar nunca frena el video
        avisar(f"puntos flojos: no salieron ({str(err)[:120]})")
        flojas = []
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
        costo_usd=costo_desde(conn, fila0), piezas_usd=piezas_desde(conn, fila0), tiempos=tiempos, revision=revision, flojas=flojas, niveles=niv,
        estandar=estandar,
        aviso=" · ".join(x for x in (e.aviso, aviso_estilo(d)) if x), banco_id=e.banco_id)


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
        f"⏱ {r.duracion_s:.0f} s · render {r.render_s:.0f} s · Claude US$ {r.costo_usd:.3f}"
        + (f" (piezas nuevas US$ {r.piezas_usd:.3f})" if r.piezas_usd else "") + " · "
        f"{html.escape(r.motor_voz)}",
        "",
        f"<b>Título:</b>\n<code>{html.escape(r.titulo)}</code>",
        f"<b>Descripción:</b>\n<code>{html.escape(r.descripcion)}\n\n{' '.join(r.hashtags)}\n\n"
        f"Fuente: {html.escape(r.articulo)}"
        + (f"\nMúsica: {html.escape(r.credito_musica)}" if r.credito_musica else "") + "</code>",
        "",
    ] + ([] if subida else ["📵 No quedó programado en ningún lado (mirá el aviso de arriba)."])
    if r.estandar:
        partes += ["", calidad.texto_estandar("asinacio", r.estandar.get("fallas") or [], r.estandar.get("corregidas"),
                                              revisado=bool(r.estandar.get("revisado")))]
        partes += [f"🔁 {html.escape(x)}" for x in r.estandar.get("reemplazos") or []]
        partes += [f"⚠️ escena {x['frase']}: ninguna escena de la biblioteca pasó ({', '.join(x['reglas'])}); va primera "
                   "en las mejoras de la semana" for x in r.estandar.get("sin_arreglo") or []]
        if r.estandar.get("frenado_usd"):
            partes.append(f"💸 <b>Correcciones frenadas</b>: llegaron a US$ {r.estandar['frenado_usd']:.2f} "
                          f"(tope US$ {_rz.TOPE_CORRECCIONES_USD:.2f}); salió con lo que había")
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
