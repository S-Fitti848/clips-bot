"""§3 paso 7: título, descripción, hashtags y crédito con Gemini. Salida JSON validada estrictamente."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .config import Textos
from .gemini import GeminiClient

# Tipo de gancho del título: se guarda para el análisis de métricas (§4b).
GANCHOS = ("reaccion", "frase_textual", "pregunta", "situacion", "resultado")
CAMPOS = ("titulo", "descripcion", "hashtags", "gancho", "depende_de_fecha")
MOTIVO_FECHA = "depende_de_fecha"  # motivo de descarte en la DB
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

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hashtags"] = list(self.hashtags)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TextosClip":
        return cls(d["titulo"], d["descripcion"], tuple(d["hashtags"]), d["gancho"], d["credito"],
                   bool(d.get("depende_de_fecha", False)))


def credito(canal: str, login: str) -> str:
    return f"Clip de {canal} — twitch.tv/{login}"


def validar(data: object, cfg: Textos) -> list[str]:
    """Lista de errores (vacía = válido). Estricto: tipos, claves exactas, largos y formato."""
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
    return errores


def parsear(texto: str, cfg: Textos, canal: str, login: str) -> tuple[TextosClip | None, list[str]]:
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
            titulo_twitch: str, duracion: float, transcripcion: str, fecha: str | None = None) -> TextosClip:
    prompt = armar_prompt(canal, categoria, titulo_twitch, duracion, transcripcion, cfg, fecha)
    errores: list[str] = []
    for _ in range(1 + cfg.reintentos):
        p = prompt
        if errores:
            p += "\n\nTu respuesta anterior no era válida. Corregí esto:\n- " + "\n- ".join(errores)
        textos, errores = parsear(cliente.json(SISTEMA, p, SCHEMA), cfg, canal, login)
        if textos:
            return textos
    raise TextosError("Gemini no devolvió textos válidos: " + "; ".join(errores))
