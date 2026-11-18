"""Así Nació: escenas con sentido (Santi, 2026-11-18, "la causa de casi todas mis correcciones": el guion elegía escenas por
palabras sueltas en vez de pensar qué vería una persona). Regla para TODOS los videos.

Antes de dibujar, Sonnet hace de DIRECTOR DE CINE: para cada frase escribe "qué ve el espectador" (quién, dónde, qué hace,
con qué y por qué eso cuenta la frase) y se pregunta "¿alguien que no escucha la voz entiende qué pasa?". Las escenas que
no pasan (o que caen en lo prohibido) se corrigen SOLO a ellas con la corrección puntual de siempre; si el motor no tiene
la pieza, la escena pide `dibujo_nuevo` / `lugar_nuevo` (se crean y quedan guardadas) o se reescribe a algo que se
entienda. Nunca una escena genérica de relleno. La nota del director queda en cada escena (`que_ve`) y la revisión visual
compara cada cuadro contra ella (`marcas.texto_ficha`).
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

EJEMPLOS = """EJEMPLOS DE SANTI (seguí este criterio):
- Frase sobre CREAR Twitter: NO unas manos sobre un celular. SÍ alguien trabajando en una computadora de la época (2006:
  monitor de tubo o laptop gris), y un zoom a la pantalla con la primera página de Twitter.
- Frase sobre PERDER PLATA o VENTAS QUE BAJAN: NO una persona con las manos juntas al lado de un gráfico. SÍ una
  habitación oscura, alguien sentado con una lámpara de mesa, agarrándose la cabeza mientras mira el papel de las ventas.
- Frase sobre que Twitter NACIÓ DE LOS SMS de 140 caracteres: un celular viejo de teclas mandando un SMS, con un contador
  de 140 caracteres que se llena."""

PROHIBIDO = """PROHIBIDO (si una escena cae en esto, NO se entiende y hay que cambiarla):
- objetos adentro de otros sin sentido (un teléfono vibrando adentro de otro teléfono);
- manos trabajando sobre algo que no se trabaja con las manos (manos "fabricando" un sitio web, un nombre o una idea);
- objetos de otra época (un smartphone con botón en 2006, una pantalla plana en 1985, un celular antes de 1985);
- escenas genéricas que no cuentan ESA parte de la historia (gente parada al lado de un gráfico, un celular flotando,
  un martillo y engranajes, una persona con las manos juntas mirando a cámara)."""

SISTEMA = f"""Sos el DIRECTOR DE CINE de un video corto animado de "Así Nació" (el origen de una marca), ANTES de que se
dibuje. Te paso el guion: cada frase con la escena que hoy está planeada (fondo, gente, acciones, objetos).

Para CADA frase escribí `que_ve`: lo que ve el espectador en pantalla, como lo describiría un director: QUIÉN aparece,
DÓNDE (el lugar real de esa parte de la historia, en su año), QUÉ HACE, CON QUÉ, y POR QUÉ eso cuenta la frase (una
línea, concreta). Después preguntate: "¿alguien que NO escucha la voz entiende qué pasa?". En `se_entiende` respondé
true/false sobre la escena PLANEADA (no sobre la tuya). Si es false, en `problema` decí qué tiene de malo y en `cambio`
cómo tiene que quedar la escena planeada para que se vea lo que escribiste en `que_ve` (con las piezas del motor:
fondo, actores con su acción, objetos con su soporte, plano; si falta un objeto o un lugar, que lo pida como dibujo
nuevo o lugar nuevo). Nunca propongas una escena genérica de relleno: si no se puede dibujar lo que cuenta la frase,
proponé OTRA escena concreta que sí lo cuente.

{EJEMPLOS}

{PROHIBIDO}

Respondé solo con el JSON pedido."""

SCHEMA = {"type": "OBJECT", "properties": {"escenas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "frase": {"type": "INTEGER"}, "que_ve": {"type": "STRING"}, "se_entiende": {"type": "BOOLEAN"},
    "problema": {"type": "STRING"}, "cambio": {"type": "STRING"}},
    "required": ["frase", "que_ve", "se_entiende", "problema", "cambio"]}}}, "required": ["escenas"]}

# Lo mismo, como regla del guion (va en el prompt del guion: así ya sale pensado así).
REGLA_DIRECTOR = f"""
REGLA 18 — ESCENAS CON SENTIDO (Santi, 2026-11-18; para TODOS los videos). Antes de elegir una escena, pensá como un
director de cine qué VE el espectador: quién, dónde, qué hace, con qué, y por qué eso cuenta la frase. Si alguien que no
escucha la voz no entendería qué pasa, la escena está mal. Nada de elegir escenas por palabras sueltas.
{EJEMPLOS}
{PROHIBIDO}"""


def dirigir(cliente, d: dict, describir, marca: str = "", anio: int | None = None, avisar=log.info) -> list[dict]:
    """La nota del director de cada frase (y la deja en `d["escenas"][k]["que_ve"]`). Devuelve las escenas que no se
    entienden: [{"frase": k (desde 0), "problema", "cambio", "que_ve"}]."""
    escenas = d.get("escenas") or []
    if cliente is None or not escenas:
        return []
    pedido = (f"MARCA: {marca}" + (f" (la historia empieza en {anio})" if anio else "")
              + "\n\nEL GUION (frases numeradas desde 1, con la escena planeada):\n" + describir(d))
    try:
        r = json.loads(cliente.json(SISTEMA, pedido, SCHEMA, 0.3))
    except Exception as err:  # noqa: BLE001 — si el director no responde, el video sigue como estaba
        avisar(f"director: no respondió ({str(err)[:120]})")
        return []
    malas = []
    for x in r.get("escenas") or []:
        k = int(x.get("frase") or 0) - 1
        if not 0 <= k < len(escenas):
            continue
        escenas[k]["que_ve"] = str(x.get("que_ve") or "")[:300]
        if x.get("se_entiende") is False:
            malas.append({"frase": k, "problema": str(x.get("problema") or "")[:300],
                          "cambio": str(x.get("cambio") or "")[:400], "que_ve": escenas[k]["que_ve"]})
    avisar(f"director: {len(escenas)} escenas, {len(malas)} no se entienden sin la voz"
           + (": " + "; ".join(f"{m['frase'] + 1}: {m['problema'][:60]}" for m in malas[:4]) if malas else ""))
    return malas


def errores_para_corregir(malas: list[dict]) -> list[str]:
    """Las escenas a corregir, en el formato de la corrección puntual (correcciones.corregir)."""
    return [f"escena {m['frase'] + 1}: NO SE ENTIENDE SIN LA VOZ ({m['problema']}). Tiene que verse: {m['que_ve']}. "
            f"Cambio: {m['cambio']}" for m in malas]
