"""Modo /narrar: mirar el video, escribir un guion y ponerle voz.

Tres cosas que lo separan de /editar:

1. **Gemini VE el video.** Se le mandan frames y se le pide que describa paso a paso lo que pasa
   antes de escribir nada. Sin eso el guion sale de la transcripción, que en un clip de juego son
   gritos sueltos, y el resultado es una voz en off hablando de algo que no está en pantalla.
2. **El guion se aprueba antes de gastar nada.** Gemini puede inventar detalles: ya pasó con un
   Short titulado "Reconoce que no conoce a Zelda" donde Zelda era un perro muerto. Narrar algo
   inventado con voz de locutor es bastante peor que escribirlo. Por eso el guion llega primero.
3. **La voz es local.** Piper, por cuota más que por calidad: el free tier de Gemini son ~20
   requests/día y ya se agota con los textos. Ver la comparación medida en settings.yaml.
"""

from __future__ import annotations

import json
import logging
import math
import re
import wave
from dataclasses import dataclass
from pathlib import Path

from .media import find_bin, run

log = logging.getLogger(__name__)

# Una voz en español ronda las 2,5 palabras por segundo a ritmo de narración. Sirve para pedirle a
# Gemini un guion del largo correcto y para avisar cuando se pasó.
PALABRAS_POR_SEGUNDO = 2.5

SISTEMA = """Escribís la voz en off de un video vertical corto, en español rioplatense (vos, no tú).

Te paso frames del video en orden y, si hay, lo que se escucha. Primero DESCRIBÍS lo que pasa paso
a paso, mirando las imágenes; después escribís el guion.

Reglas del guion:
- Arranca con un gancho de una frase que haga quedarse: una pregunta, algo raro que se ve, o el
  final adelantado. Nada de "en este video vamos a ver".
- Contá SOLO lo que se ve. Si no estás seguro de qué es algo, no lo nombres: decilo de forma
  general. Es preferible un guion vago a uno que inventa.
- Nada de nombres propios (juegos, personas, lugares, marcas) que no aparezcan en lo que se
  escucha o no se lean claramente en pantalla.
- Hablado, no escrito: frases cortas, como se lo contarías a un amigo.
- Sin emojis, sin hashtags, sin "suscribite".

Respondé solo con el JSON pedido."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "que_pasa": {"type": "ARRAY", "items": {"type": "STRING"}},
        "guion": {"type": "STRING"},
        "sensible": {"type": "BOOLEAN"},
        "confianza": {"type": "INTEGER"},
    },
    "required": ["que_pasa", "guion", "sensible", "confianza"],
}


@dataclass
class Guion:
    texto: str
    que_pasa: tuple[str, ...] = ()
    sensible: bool = False
    confianza: int = 0          # 1 a 10: cuánto entendió de lo que vio
    palabras: int = 0
    segundos_estimados: float = 0.0

    def a_dict(self) -> dict:
        return {"texto": self.texto, "que_pasa": list(self.que_pasa), "sensible": self.sensible,
                "confianza": self.confianza, "palabras": self.palabras,
                "segundos_estimados": round(self.segundos_estimados, 1)}

    @classmethod
    def de_dict(cls, d: dict) -> "Guion":
        return cls(d["texto"], tuple(d.get("que_pasa") or ()), bool(d.get("sensible")),
                   int(d.get("confianza") or 0), int(d.get("palabras") or 0),
                   float(d.get("segundos_estimados") or 0))


def _medir(texto: str) -> tuple[int, float]:
    n = len(re.findall(r"[^\s]+", texto))
    return n, n / PALABRAS_POR_SEGUNDO


def escribir(cliente, duracion: float, transcripcion: str, imagenes: list[bytes],
             correccion: str = "") -> Guion:
    """Le pide a Gemini el guion. `correccion` es lo que pediste cambiar en el intento anterior."""
    objetivo = max(4, int(duracion * PALABRAS_POR_SEGUNDO))
    prompt = (f"El video dura {duracion:.0f} segundos, así que el guion tiene que tener alrededor "
              f"de {objetivo} palabras (ni la mitad ni el doble).\n"
              f"Te mando {len(imagenes)} frames en orden.\n")
    if transcripcion.strip():
        prompt += f"Lo que se escucha: {transcripcion[:1500]}\n"
    else:
        prompt += "No se escucha nada claro: guiate por las imágenes.\n"
    prompt += ("\nconfianza: del 1 al 10, cuánto entendiste REALMENTE de lo que pasa mirando los "
               "frames. Si es bajo, escribí un guion más general en vez de inventar.")
    if correccion:
        prompt += f"\n\nEl guion anterior no sirvió. Lo que hay que cambiar: {correccion}"
    crudo = cliente.json(SISTEMA, prompt, SCHEMA, temperatura=0.6, imagenes=imagenes)
    d = json.loads(crudo)
    texto = str(d.get("guion") or "").strip()
    palabras, segundos = _medir(texto)
    return Guion(texto=texto, que_pasa=tuple(d.get("que_pasa") or ()),
                 sensible=bool(d.get("sensible")), confianza=int(d.get("confianza") or 0),
                 palabras=palabras, segundos_estimados=segundos)


def sintetizar(texto: str, modelo: Path, salida: Path) -> Path:
    """Piper: texto → wav. Corre local, sin red y sin cuota."""
    from piper import PiperVoice

    salida.parent.mkdir(parents=True, exist_ok=True)
    voz = PiperVoice.load(str(modelo))
    with wave.open(str(salida), "wb") as w:
        voz.synthesize_wav(texto, w)
    return salida


def duracion_wav(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def mezclar(video: Path, voz: Path, salida: Path, volumen_original: float = 0.15) -> Path:
    """Voz encima, audio del video de fondo. Si el video no tiene audio, va solo la voz.

    El video NO se re-encodea: se copia el stream de imagen y solo se rearma el audio. En la Pi el
    render es la etapa más cara, y volver a pasarlo por x264 acá lo duplicaría al pedo.
    """
    salida.parent.mkdir(parents=True, exist_ok=True)
    tiene_audio = _tiene_audio(video)
    if tiene_audio:
        filtro = (f"[0:a]volume={volumen_original}[fondo];"
                  f"[1:a]aresample=48000[voz];"
                  f"[fondo][voz]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        mapeo = ["-map", "0:v", "-map", "[a]"]
    else:
        filtro = "[1:a]aresample=48000[a]"
        mapeo = ["-map", "0:v", "-map", "[a]"]
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video.resolve()), "-i", str(voz.resolve()),
         "-filter_complex", filtro, *mapeo,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
         str(salida.resolve())])
    return salida


def _tiene_audio(video: Path) -> bool:
    from .media import probe

    try:
        return probe(video).tiene_audio
    except Exception:
        return False


def subtitular_voz(wav: Path, cfg_subs, texto_guion: str = "") -> list:
    """Subtítulos de LA VOZ, no del audio original: se transcribe el wav sintetizado.

    Se pasa Whisper por encima de la propia voz en vez de repartir el guion a ojo por la duración.
    Suena al revés (ya sabemos qué dice), pero es lo que da los tiempos REALES de cada palabra, que
    es lo único que hace que el subtítulo caiga cuando se escucha. Repartir el texto de forma
    pareja se desfasa apenas hay una pausa.
    """
    from . import subtitles as sub

    modelo = sub.cargar_modelo(cfg_subs)
    try:
        palabras = sub.transcribir(modelo, wav, cfg_subs, duracion_wav(wav))
    finally:
        del modelo
    return sub.armar_subtitulos(palabras, cfg_subs)


def aviso_largo(guion: Guion, duracion: float) -> str:
    """Si el guion no entra en el video, hay que decirlo ANTES de sintetizar."""
    if duracion <= 0:
        return ""
    ratio = guion.segundos_estimados / duracion
    if ratio > 1.25:
        sobra = guion.segundos_estimados - duracion
        return (f"⚠️ El guion son ~{guion.segundos_estimados:.0f}s hablados y el video dura "
                f"{duracion:.0f}s: sobran ~{sobra:.0f}s. Pedime que lo acorte con ✏️.")
    if ratio < 0.5:
        return (f"⚠️ El guion son ~{guion.segundos_estimados:.0f}s y el video dura "
                f"{duracion:.0f}s: va a quedar mucho silencio.")
    return ""
