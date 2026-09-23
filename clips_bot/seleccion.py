"""§3 paso 8: elegir los mejores clips procesados, con cupos por fuente.

Fuentes:
  reciente  score = factor_momento × (1 + log10(1 + vistas)), con
            factor_momento = 1 + peso_momento × (clips del mismo momento − 1).
            El log achata las vistas: 0 vistas → 1,0; 10 → 2,0; 500 → 3,7; 50.000 → 5,7. Así un clip
            sin vistas que tres personas clipearon compite con uno de 500 vistas sin duplicados, y
            las vistas bajas no anulan la señal de duplicados.
  catalogo  score = vistas absolutas.

Los cupos son por GRUPO (seleccion.mezcla; el grupo de cada streamer sale de streamers.yaml, ej.
kick_reciente / evento / catalogo), y cada grupo compite solo dentro del suyo. Lo que un grupo no
llena pasa al grupo de fallback ("catalogo"); si al fallback también le sobra, vuelve a repartirse
entre los demás. El score sigue dependiendo de la FUENTE (reciente o catalogo).
Tope de clips por streamer entre todos los grupos.
Si en el corte de una fuente hay scores a menos de `empate_pct[fuente]` entre sí, ese grupo lo ordena
Gemini (si no hay Gemini o falla, queda el orden por score). El porcentaje va por fuente porque el
score reciente es logarítmico: 3 % ahí ≈ 20 % de diferencia en vistas.
(§4b: cuando haya métricas con n ≥ 15, acá entra el factor por streamer y duración.)
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from .config import GRUPO_FALLBACK, Seleccion
from .gemini import GeminiClient

log = logging.getLogger(__name__)


@dataclass
class Opcion:
    clip_id: str
    streamer: str
    vistas: int
    creado: datetime | None
    titulo: str = ""  # título generado (o el de Twitch si todavía no hay)
    transcripcion: str = ""
    meta: dict = field(default_factory=dict)  # el json completo de output/ready/
    fuente: str = "reciente"  # decide cómo se puntúa
    grupo: str = ""  # decide en qué cupo compite (seleccion.mezcla)
    clips_mismo_momento: int = 1

    def grupo_o_fuente(self) -> str:
        return self.grupo or self.fuente


def factor_momento(clips_mismo_momento: int, peso: float) -> float:
    return 1 + peso * max(clips_mismo_momento - 1, 0)


def score_reciente(vistas: int, clips_mismo_momento: int, peso_momento: float) -> float:
    return factor_momento(clips_mismo_momento, peso_momento) * (1 + math.log10(1 + max(vistas, 0)))


def score(o: Opcion, ahora: datetime, cfg: Seleccion) -> float:
    if o.fuente == "catalogo":
        return float(o.vistas)
    return score_reciente(o.vistas, o.clips_mismo_momento, cfg.peso_momento)


Desempate = Callable[[list[Opcion]], list[Opcion]]


def _ordenar(opciones: list[Opcion], cupo: int, scores: dict[str, float], empate_pct: float,
             desempatar: Desempate | None) -> list[Opcion]:
    """Orden por score; si el empate cruza el corte del cupo, ese grupo lo reordena el desempate."""
    orden = sorted(opciones, key=lambda o: scores[o.clip_id], reverse=True)
    if not desempatar or cupo <= 0 or len(orden) <= cupo:
        return orden
    corte = scores[orden[cupo - 1].clip_id]
    grupo = [o for o in orden if abs(scores[o.clip_id] - corte) <= empate_pct * corte]
    if len(grupo) < 2 or not any(o in grupo for o in orden[cupo:]):
        return orden
    try:
        nuevo = desempatar(grupo)
    except Exception as e:  # el desempate es una mejora, no puede tirar la corrida
        log.warning("Desempate falló, queda el orden por score: %s", e)
        return orden
    i0 = orden.index(grupo[0])
    return orden[:i0] + nuevo + [o for o in orden[i0:] if o not in grupo]


def _llenar(orden: list[Opcion], cupo: int, por_streamer: dict[str, int], tope: int) -> list[Opcion]:
    elegidos: list[Opcion] = []
    for o in orden:
        if len(elegidos) >= cupo:
            break
        if por_streamer.get(o.streamer, 0) >= tope:
            continue
        elegidos.append(o)
        por_streamer[o.streamer] = por_streamer.get(o.streamer, 0) + 1
    return elegidos


def seleccionar(opciones: list[Opcion], cfg: Seleccion, ahora: datetime,
                desempatar: Desempate | None = None) -> list[Opcion]:
    """Elegidos en el orden de los grupos de `mezcla`, con el fallback al final."""
    scores = {o.clip_id: score(o, ahora, cfg) for o in opciones}
    grupos = list(cfg.mezcla) + ([GRUPO_FALLBACK] if GRUPO_FALLBACK not in cfg.mezcla else [])
    orden_grupos = [g for g in grupos if g != GRUPO_FALLBACK] + [GRUPO_FALLBACK]
    disponibles = {g: [o for o in opciones if o.grupo_o_fuente() == g] for g in orden_grupos}
    cupos = {g: cfg.mezcla.get(g, 0) for g in orden_grupos}
    por_streamer: dict[str, int] = {}
    elegidos: dict[str, list[Opcion]] = {g: [] for g in orden_grupos}

    def llenar(grupo: str, cupo: int) -> int:
        """Llena lo que pueda y devuelve cuántos cupos quedaron sin usar."""
        if cupo <= 0:
            return 0
        fuente = disponibles[grupo][0].fuente if disponibles[grupo] else "reciente"
        orden = _ordenar(disponibles[grupo], cupo, scores, cfg.empate_pct.get(fuente, 0.0), desempatar)
        nuevos = _llenar(orden, cupo, por_streamer, cfg.max_por_streamer)
        elegidos[grupo] += nuevos
        disponibles[grupo] = [o for o in orden if o not in nuevos]
        return cupo - len(nuevos)

    sobrantes = sum(llenar(g, cupos[g]) for g in orden_grupos if g != GRUPO_FALLBACK)
    # Lo que no llenó ningún grupo se lo ofrece el fallback (catálogo)…
    sobrantes = llenar(GRUPO_FALLBACK, cupos[GRUPO_FALLBACK] + sobrantes)
    # …y si al fallback también le sobra, vuelve a repartirse entre los demás.
    for g in orden_grupos:
        if sobrantes <= 0:
            break
        sobrantes = llenar(g, sobrantes)
    return [o for g in orden_grupos for o in elegidos[g]]


# ---- desempate con Gemini -------------------------------------------------------

SISTEMA_DESEMPATE = """Elegís qué clips de streamers van a rendir mejor como YouTube Short.
Criterios: gancho en los primeros segundos, se entiende sin contexto previo, momento gracioso o
sorprendente, remate claro. Respondé solo con el JSON pedido."""

SCHEMA_DESEMPATE = {
    "type": "OBJECT",
    "properties": {"orden": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["orden"],
}


def validar_orden(texto: str, ids: list[str]) -> list[str]:
    """El orden devuelto tiene que ser una permutación exacta de los ids."""
    try:
        data = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f"no es JSON: {e}") from e
    orden = data.get("orden") if isinstance(data, dict) else None
    if not isinstance(orden, list) or sorted(map(str, orden)) != sorted(ids):
        raise ValueError(f"orden inválido: {orden!r} (esperaba una permutación de {ids})")
    return [str(x) for x in orden]


def desempate_gemini(cliente: GeminiClient) -> Desempate:
    def desempatar(grupo: list[Opcion]) -> list[Opcion]:
        bloques = [
            f"id: {o.clip_id}\nstreamer: {o.streamer}\ntítulo: {o.titulo}\n"
            f"transcripción: {o.transcripcion[:600] or '(sin habla)'}"
            for o in grupo
        ]
        prompt = (
            "Ordená estos clips del que más va a rendir al que menos. Devolvé todos los ids.\n\n"
            + "\n\n".join(bloques)
        )
        orden = validar_orden(cliente.json(SISTEMA_DESEMPATE, prompt, SCHEMA_DESEMPATE, 0.2),
                              [o.clip_id for o in grupo])
        por_id = {o.clip_id: o for o in grupo}
        return [por_id[i] for i in orden]

    return desempatar
