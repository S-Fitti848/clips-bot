"""Chequeo visual antes de mandar un clip (2026-10-25).

Un clip de Auron salió con la cara de una foto en pantalla arriba en vez de su webcam, subtítulos
dobles y la pantalla cortada a la izquierda. Ninguna de las capas de antes lo miraba TERMINADO.
Acá Gemini ve 2 cuadros del 9:16 final en UNA llamada y contesta tres preguntas; si algo falla,
`process.procesar` rehace el clip (fit_blur, o sin nuestros subtítulos).

Si Gemini no responde, el clip sigue igual: es una red más, no una puerta.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from .gemini import GeminiError
from .media import frames_jpeg

log = logging.getLogger(__name__)

CUADROS = 2

SISTEMA = """Revisás Shorts verticales (9:16) armados con clips de streamers ANTES de publicarlos.
Te paso cuadros del video terminado. Contestá solo lo que se VE, sin suponer.

1. `camara_ok`: si el video está partido en dos (un panel arriba y otro abajo), ¿el panel de
   ARRIBA muestra la cámara del streamer (una persona frente a su cámara, en su cuarto o estudio)?
   false si arriba se ve otra cosa: una foto o una imagen que está en pantalla, un personaje del
   juego, la cara de alguien en una captura, una pared vacía, el juego, un pedazo de interfaz.
   Si el video NO está partido en dos, true.
2. `subtitulos_dobles`: ¿hay DOS subtítulos distintos al mismo tiempo (por ejemplo unos que ya
   venían en el clip y otros agregados encima o abajo, con distinta letra o en distinto lugar)?
   Un título grande arriba no es un subtítulo.
3. `cortado`: ¿algo importante quedó cortado por un borde: una cara partida, la pantalla o el
   contenido que se está mostrando cortado a un costado, un texto que se sale del cuadro?
   El fondo difuminado de relleno no cuenta.
4. `detalle`: en una línea, qué viste que falla (vacío si nada)."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "camara_ok": {"type": "BOOLEAN"},
        "subtitulos_dobles": {"type": "BOOLEAN"},
        "cortado": {"type": "BOOLEAN"},
        "detalle": {"type": "STRING"},
    },
    "required": ["camara_ok", "subtitulos_dobles", "cortado", "detalle"],
}


@dataclass
class Revision:
    camara_ok: bool = True
    subtitulos_dobles: bool = False
    cortado: bool = False
    detalle: str = ""
    error: str = ""      # Gemini no respondió: no se rehace nada

    @property
    def falla_encuadre(self) -> bool:
        """La cámara de arriba no es la del streamer, o algo quedó cortado: va fit_blur."""
        return not self.error and (not self.camara_ok or self.cortado)

    @property
    def falla_subtitulos(self) -> bool:
        return not self.error and self.subtitulos_dobles

    def a_dict(self) -> dict:
        return asdict(self)


def revisar(cliente, video: Path, layout: str, con_subs: bool) -> Revision:
    """Una llamada a Gemini con CUADROS cuadros del video terminado."""
    imagenes = frames_jpeg(video, CUADROS, ancho=384)
    if not imagenes:
        return Revision(error="no pude sacar cuadros del video")
    prompt = (f"Layout: {'partido en dos (cámara arriba, contenido abajo)' if layout == 'split' else layout}. "
              f"Subtítulos agregados por nosotros: {'sí, abajo' if con_subs else 'no'}. "
              f"Te paso {len(imagenes)} cuadros del video terminado.")
    try:
        d = json.loads(cliente.json(SISTEMA, prompt, SCHEMA, temperatura=0.0, imagenes=imagenes))
    except (GeminiError, ValueError) as e:
        log.warning("Chequeo visual salteado: %s", e)
        return Revision(error=str(e)[:200])
    return Revision(camara_ok=bool(d.get("camara_ok", True)),
                    subtitulos_dobles=bool(d.get("subtitulos_dobles", False)),
                    cortado=bool(d.get("cortado", False)),
                    detalle=str(d.get("detalle") or "")[:200])
