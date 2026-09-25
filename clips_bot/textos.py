"""§3 paso 7: título, descripción, hashtags y crédito con Gemini. Salida JSON validada estrictamente."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass

from .config import Textos
from .gemini import GeminiClient

# Tipo de gancho del título: se guarda para el análisis de métricas (§4b).
GANCHOS = ("reaccion", "frase_textual", "pregunta", "situacion", "resultado")
CAMPOS = ("titulo", "descripcion", "hashtags", "gancho", "depende_de_fecha", "sensible",
          "puntaje")
MOTIVO_FECHA = "depende_de_fecha"      # motivos de descarte en la DB
MOTIVO_SENSIBLE = "tono_sensible"      # muerte, duelo, enfermedad, violencia real, salud mental
MOTIVO_SIN_REMATE = "sin_remate"       # no se entiende solo o no tiene remate
MAX_TRANSCRIPCION = 3000

_HASHTAG = re.compile(r"^#[^\W_]\w*$")

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "titulo": {"type": "STRING"},
        "descripcion": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "gancho": {"type": "STRING", "enum": list(GANCHOS)},
        "depende_de_fecha": {"type": "BOOLEAN"},
        "sensible": {"type": "BOOLEAN"},
        "puntaje": {"type": "INTEGER"},
    },
    "required": list(CAMPOS),
    "propertyOrdering": list(CAMPOS),
}

SISTEMA = """Escribís los textos de YouTube Shorts hechos con clips de streamers de Twitch.
Reglas:
- Título: gancho basado en lo que REALMENTE pasa en el clip. Nada de clickbait falso ni de inventar
  hechos que no están en la transcripción. Sin hashtags. Como mucho un emoji.
- Descripción: 1 a 3 oraciones que den contexto (quién, qué juego o situación, qué pasa).
  Sin hashtags y sin links: el crédito al streamer lo agrega el sistema.
- Hashtags: entre 3 y 5, SIEMPRE más de uno, cada uno como un elemento separado del array. Incluí
  #Shorts; el resto relevantes (streamer, juego o tema). Una sola palabra cada uno, sin espacios,
  empezando con #. Nunca mandes todos los hashtags juntos en un solo texto.
- gancho: clasificá el tipo de gancho del título: reaccion (reacción del streamer), frase_textual
  (cita algo que dice), pregunta, situacion (describe lo que pasa), resultado (cómo termina).
- Español neutro, en el mismo registro informal del clip.
- depende_de_fecha: true si el clip hace referencia a algo puntual de ese día o esa semana, de modo
  que publicado semanas o meses después pierde sentido o queda desactualizado: una noticia o evento
  del momento, un partido, un anuncio o lanzamiento ("mañana sale", "hoy anunciaron"), un sorteo,
  un cumpleaños, una fecha especial, un drama o tendencia de esos días. false si se entiende y
  funciona igual en cualquier momento (jugadas, reacciones, charlas, anécdotas).
  Ante la duda, true.
- sensible: true si el clip trata de muerte, duelo, homenajes o memoriales, enfermedad, accidentes,
  llanto real (no de risa), violencia real entre personas (algo que pasó de verdad y se muestra o
  se cuenta), o salud mental. Ante la duda, true.
  NO es sensible: el humor normal, las puteadas, las derrotas, las peleas DENTRO de un juego, ni una
  charla hipotética sobre quién ganaría una pelea.
- puntaje: del 1 al 10, cuánto se entiende el clip SOLO, sin saber lo que pasó antes, y si tiene un
  remate (algo que cierra: una reacción, una frase, un desenlace). Si te mandan frames, contá lo que
  se VE: un fail, un susto o una cara valen como remate aunque no se diga nada. 10 = se entiende
  solo y tiene remate claro. 1 = no se entiende qué pasa ni mirando las imágenes.
Respondé solo con el JSON pedido."""


class TextosError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextosClip:
    titulo: str
    descripcion: str  # incluye el crédito al final
    hashtags: tuple[str, ...]
    gancho: str
    credito: str
    depende_de_fecha: bool = False
    sensible: bool = False   # muerte, duelo, enfermedad, violencia real, salud mental
    puntaje: int = 0         # 1 a 10: se entiende solo + tiene remate

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hashtags"] = list(self.hashtags)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TextosClip":
        return cls(d["titulo"], d["descripcion"], tuple(d["hashtags"]), d["gancho"], d["credito"],
                   bool(d.get("depende_de_fecha", False)), bool(d.get("sensible", False)),
                   int(d.get("puntaje", 0)))


# Palabras que arrancan en mayúscula pero no nombran nada: pronombres, días, y el arranque de una
# oración. Se sacan antes de pedirle a Gemini que justifique un nombre propio.
_NO_SON_NOMBRES = frozenset("""
el la los las un una unos unas y o pero si no que se de del al en con por para como cuando donde
yo tu vos el ella nosotros ustedes ellos me te le lo nos les su sus mi mis tu tus
lunes martes miercoles jueves viernes sabado domingo hoy ayer manana
que quien cual cuanto porque ahora despues antes siempre nunca nada todo algo
""".split())

# Tras estos caracteres, una mayúscula es principio de oración y no dice nada de si es un nombre.
_ABRE_ORACION = ('', '.', '!', '?', '¡', '¿', ':', ';', '-', '—', '"', "'")


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _palabras(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _sin_tildes(texto).lower()))


def nombres_propios(titulo: str) -> list[str]:
    """Palabras del título que nombran algo: mayúscula en medio de la oración.

    Es una heurística, no un NER: alcanza porque lo que nos interesa (un juego, una persona, un
    objeto) casi siempre va en mayúscula, y los falsos positivos los resuelve el propio chequeo
    (si la palabra está en lo que se dice, pasa igual).
    """
    tokens = re.findall(r"[^\W\d_]+", titulo, flags=re.UNICODE)
    if not tokens:
        return []
    nombres, previo = [], ""
    for t in tokens:
        antes = titulo[: titulo.index(t, len(previo) and titulo.index(previo) + len(previo))].rstrip()
        arranca_oracion = not antes or antes[-1] in _ABRE_ORACION
        base = _sin_tildes(t).lower()
        if t[0].isupper() and not arranca_oracion and base not in _NO_SON_NOMBRES and len(t) > 2:
            nombres.append(t)
        previo = t
    return nombres


def nombres_sin_respaldo(titulo: str, contexto: str) -> list[str]:
    """Los nombres del título que NO aparecen en el contexto (transcripción + categoría + título
    original del clip y del stream).

    El 2026-09-24 salió un Short titulado "Reconoce que no conoce a Zelda" sobre tres momentos sin
    relación. OJO: ese caso NO lo agarra este chequeo — "Zelda" sí estaba en la transcripción
    ("en memoria de Zelda", de unos créditos). Esto cubre el otro problema, el de inventar un
    nombre que nadie dijo; lo de juntar momentos distintos se arregla en la agrupación.
    """
    respaldo = _palabras(contexto)
    return [n for n in nombres_propios(titulo) if _sin_tildes(n).lower() not in respaldo]


def credito(canal: str, login: str) -> str:
    return f"Clip de {canal} — twitch.tv/{login}"


def validar(data: object, cfg: Textos, contexto: str = "") -> list[str]:
    """Lista de errores (vacía = válido). Estricto: tipos, claves exactas, largos y formato.

    `contexto` es lo que realmente hay en el clip (transcripción + categoría + títulos): si el
    título nombra algo que no está ahí, se cuenta como error y `generar` lo manda a regenerar.
    """
    if not isinstance(data, dict):
        return ["la respuesta no es un objeto JSON"]
    errores = []
    faltan = [c for c in CAMPOS if c not in data]
    sobran = [c for c in data if c not in CAMPOS]
    if faltan:
        errores.append(f"faltan campos: {faltan}")
    if sobran:
        errores.append(f"campos no permitidos: {sobran}")

    titulo = data.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        errores.append("titulo tiene que ser un texto no vacío")
    else:
        if len(titulo.strip()) > cfg.max_titulo:
            errores.append(f"titulo tiene {len(titulo.strip())} caracteres (máximo {cfg.max_titulo})")
        if "\n" in titulo or "#" in titulo:
            errores.append("titulo no puede tener saltos de línea ni hashtags")
        inventados = nombres_sin_respaldo(titulo, contexto) if contexto else []
        if inventados:
            errores.append(
                f"el titulo nombra {inventados}, que no aparece en lo que se dice en el clip. "
                "Usá solo nombres (juegos, personas, objetos) que estén en la transcripción, "
                "la categoría o el título original")

    desc = data.get("descripcion")
    if not isinstance(desc, str) or not desc.strip():
        errores.append("descripcion tiene que ser un texto no vacío")
    else:
        if len(desc) > cfg.max_descripcion:
            errores.append(f"descripcion tiene {len(desc)} caracteres (máximo {cfg.max_descripcion})")
        if "#" in desc or "http" in desc.lower():
            errores.append("descripcion no puede tener hashtags ni links")

    tags = data.get("hashtags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        errores.append("hashtags tiene que ser una lista de textos")
    else:
        if not cfg.min_hashtags <= len(tags) <= cfg.max_hashtags:
            errores.append(f"hashtags: {len(tags)} (tienen que ser entre {cfg.min_hashtags} y {cfg.max_hashtags})")
        malos = [t for t in tags if not _HASHTAG.match(t)]
        if malos:
            errores.append(f"hashtags con formato inválido (una palabra, empieza con #): {malos}")
        bajos = [t.lower() for t in tags]
        if len(set(bajos)) != len(bajos):
            errores.append("hashtags repetidos")
        if "#shorts" not in bajos:
            errores.append("falta #Shorts en hashtags")

    if data.get("gancho") not in GANCHOS:
        errores.append(f"gancho tiene que ser uno de {list(GANCHOS)}")
    if not isinstance(data.get("depende_de_fecha"), bool):
        errores.append("depende_de_fecha tiene que ser true o false")
    if not isinstance(data.get("sensible"), bool):
        errores.append("sensible tiene que ser true o false")
    p = data.get("puntaje")
    if not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= 10:
        errores.append("puntaje tiene que ser un entero de 1 a 10")
    return errores


def parsear(texto: str, cfg: Textos, canal: str, login: str,
            contexto: str = "") -> tuple[TextosClip | None, list[str]]:
    try:
        data = json.loads(texto)
    except json.JSONDecodeError as e:
        return None, [f"no es JSON válido: {e}"]
    # Única normalización: espacios alrededor de cada hashtag (Gemini a veces manda " #Shorts").
    # Todo lo demás se valida tal cual llega.
    if isinstance(data, dict) and isinstance(data.get("hashtags"), list):
        data["hashtags"] = [t.strip() if isinstance(t, str) else t for t in data["hashtags"]]
    errores = validar(data, cfg)
    if errores:
        return None, errores
    cred = credito(canal, login)
    return (
        TextosClip(
            titulo=data["titulo"].strip(),
            descripcion=f"{data['descripcion'].strip()}\n\n{cred}",
            hashtags=tuple(data["hashtags"]),
            gancho=data["gancho"],
            credito=cred,
            depende_de_fecha=data["depende_de_fecha"],
            sensible=data["sensible"],
            puntaje=data["puntaje"],
        ),
        [],
    )


def armar_prompt(canal: str, categoria: str, titulo_twitch: str, duracion: float, transcripcion: str,
                 cfg: Textos, fecha: str | None = None) -> str:
    trans = transcripcion.strip() or "(sin habla)"
    if len(trans) > MAX_TRANSCRIPCION:
        trans = trans[:MAX_TRANSCRIPCION] + "…"
    return f"""Streamer: {canal}
Juego o categoría: {categoria or "desconocida"}
Título que le puso la comunidad al clip en Twitch: {titulo_twitch or "(sin título)"}
Duración: {duracion:.0f} s
Fecha del clip: {fecha or "desconocida"}
Transcripción:
{trans}

Generá: titulo (máximo {cfg.max_titulo} caracteres), descripcion, hashtags (entre {cfg.min_hashtags} y
{cfg.max_hashtags}, incluyendo #Shorts), gancho y depende_de_fecha."""


def generar(cliente: GeminiClient, cfg: Textos, *, canal: str, login: str, categoria: str,
            titulo_twitch: str, duracion: float, transcripcion: str, fecha: str | None = None,
            imagenes: list[bytes] | None = None) -> TextosClip:
    """`imagenes`: frames del clip, en la misma llamada. Sin ellas el puntaje castiga al humor
    visual: medido sobre 30 clips, los que solo se entienden con la imagen puntuaban 4,0 de mediana
    contra 5,0 el resto, y tenían 1,60 palabras/s contra 2,45."""
    prompt = armar_prompt(canal, categoria, titulo_twitch, duracion, transcripcion, cfg, fecha)
    # Contra esto se chequean los nombres del título. El nombre del canal entra a propósito: el
    # streamer puede ir en el título aunque no se nombre a sí mismo hablando.
    contexto = " ".join([transcripcion, categoria, titulo_twitch, canal, login])
    errores: list[str] = []
    for _ in range(1 + cfg.reintentos):
        p = prompt
        if errores:
            p += "\n\nTu respuesta anterior no era válida. Corregí esto:\n- " + "\n- ".join(errores)
        crudo = cliente.json(SISTEMA, p, SCHEMA, imagenes=imagenes)
        textos, errores = parsear(crudo, cfg, canal, login, contexto)
        if textos:
            return textos
    raise TextosError("Gemini no devolvió textos válidos: " + "; ".join(errores))
