"""§3 paso 6: transcripción con faster-whisper y armado de subtítulos (SRT + ASS para quemar)."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

from .config import Render, Subtitulos

PAUSA_CORTE_S = 0.7  # una pausa más larga que esto arranca un subtítulo nuevo
HUECO_UNIR_S = 0.3  # huecos menores entre subtítulos se tapan para que no parpadee
MIN_DURACION_S = 0.6


@dataclass(frozen=True)
class Palabra:
    inicio: float
    fin: float
    texto: str


@dataclass(frozen=True)
class Subtitulo:
    inicio: float
    fin: float
    lineas: tuple[str, ...]


def cargar_modelo(cfg: Subtitulos):
    from faster_whisper import WhisperModel

    return WhisperModel(cfg.modelo, device="cpu", compute_type=cfg.compute_type, cpu_threads=cfg.cpu_threads)


def transcribir(modelo, audio: Path, cfg: Subtitulos) -> list[Palabra]:
    segmentos, _ = modelo.transcribe(
        str(audio), language=cfg.idioma, word_timestamps=True, vad_filter=True, beam_size=5
    )
    palabras = []
    for seg in segmentos:  # generador: la transcripción corre acá
        for w in seg.words or []:
            texto = w.word.strip()
            if texto:
                palabras.append(Palabra(float(w.start), float(w.end), texto))
    return palabras


def _envolver(texto: str, ancho: int) -> list[str]:
    return textwrap.wrap(texto, width=ancho, break_long_words=False) or [texto]


def armar_subtitulos(palabras: list[Palabra], cfg: Subtitulos) -> list[Subtitulo]:
    """Agrupa palabras en subtítulos de ≤ max_lineas líneas, cortando en pausas y por duración."""
    grupos: list[list[Palabra]] = []
    actual: list[Palabra] = []
    for p in palabras:
        if actual:
            texto = " ".join(x.texto for x in actual + [p])
            if (
                len(_envolver(texto, cfg.max_chars_linea)) > cfg.max_lineas
                or p.inicio - actual[-1].fin > PAUSA_CORTE_S
                or p.fin - actual[0].inicio > cfg.max_duracion_s
            ):
                grupos.append(actual)
                actual = []
        actual.append(p)
    if actual:
        grupos.append(actual)

    subs: list[Subtitulo] = []
    for g in grupos:
        texto = " ".join(x.texto for x in g)
        if cfg.mayusculas:
            texto = texto.upper()
        lineas = _envolver(texto, cfg.max_chars_linea)
        if len(lineas) > cfg.max_lineas:  # una sola palabra larguísima; se junta lo que sobra
            lineas = lineas[: cfg.max_lineas - 1] + [" ".join(lineas[cfg.max_lineas - 1 :])]
        subs.append(Subtitulo(g[0].inicio, max(g[-1].fin, g[0].inicio + MIN_DURACION_S), tuple(lineas)))

    for i in range(len(subs) - 1):
        a, b = subs[i], subs[i + 1]
        fin = b.inicio if b.inicio - a.fin < HUECO_UNIR_S else a.fin
        subs[i] = Subtitulo(a.inicio, min(fin, b.inicio), a.lineas)
    return subs


def _t_srt(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def _t_ass(s: float) -> str:
    cs = int(round(s * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def escribir_srt(subs: list[Subtitulo], path: Path) -> None:
    bloques = [f"{i}\n{_t_srt(s.inicio)} --> {_t_srt(s.fin)}\n" + "\n".join(s.lineas) for i, s in enumerate(subs, 1)]
    path.write_text("\n\n".join(bloques) + "\n", encoding="utf-8")


def _escapar_ass(t: str) -> str:
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def escribir_ass(subs: list[Subtitulo], path: Path, cfg: Subtitulos, render: Render) -> None:
    # BorderStyle 3 = caja opaca detrás del texto; su color es OutlineColour (&HAABBGGRR, AA=00 opaco).
    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {render.ancho}
PlayResY: {render.alto}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg.fuente},{cfg.tamano},&H00FFFFFF,&H000000FF,&H60000000,&H60000000,-1,0,0,0,100,100,0,0,3,12,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # \an5 + \pos: el centro del bloque queda en posicion_y, tenga 1 o 2 líneas.
    pos = f"{{\\an5\\pos({render.ancho // 2},{round(render.alto * cfg.posicion_y)})}}"
    eventos = [
        f"Dialogue: 0,{_t_ass(s.inicio)},{_t_ass(s.fin)},Default,,0,0,0,,{pos}"
        + "\\N".join(_escapar_ass(l) for l in s.lineas)
        for s in subs
    ]
    path.write_text(cabecera + "\n".join(eventos) + "\n", encoding="utf-8")
