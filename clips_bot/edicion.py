"""Edición nueva de Rots (propuesta aprobada por Santi el 2026-11-10; `render.edicion_rots`).

Sobre el clip ya bajado y transcripto, antes del layout y el render:
  1. `tramos_a_dejar`: se sacan el principio y el final muertos y las pausas de más de
     `PAUSA_MAX_S` (cortes secos, "jump cuts"), salvo que en la pausa haya ruido fuerte (una risa o un
     grito sin palabras). El resultado va de `MIN_S` a `MAX_S` (15-35 s): si sale más largo, se queda
     el tramo seguido con más habla que contiene el pico de volumen (el remate); si sacando pausas
     quedara por debajo de 15 s, solo se recortan el principio y el final.
  2. `cortar`: un mp4 nuevo con solo esos tramos (el audio con el crossfade corto de las reglas fijas).
  3. `mapear`: los tiempos de las palabras pasan al video cortado (los subtítulos no se vuelven a
     transcribir).
  4. `risas`: los momentos de risa de la transcripción, para el zoom de reacción.
El texto del primer segundo, los subtítulos karaoke y la pregunta del cierre los arma process.py.
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path

from .media import CROSSFADE_S, audio_con_crossfade, find_bin, run
from .subtitles import Palabra

PAUSA_MAX_S = 0.6        # una pausa más larga que esto se corta
MARGEN_S = 0.15          # lo que se deja antes y después de cada tramo con habla
COLA_S = 0.6             # después de la última palabra (la reacción respira un poco)
MIN_S, MAX_S = 15.0, 35.0
RUIDO_FACTOR = 1.6       # una pausa con RMS ≥ 1,6 × la mediana es una risa o un grito: no se corta
MIN_TRAMO_S = 0.35
CONGELAR_S = 2.0         # la pantalla final con la pregunta

_RISA = re.compile(r"^(?:j[aeij]){2,}|^(?:ja)+j?$|jaj|jsj|^xd+$", re.I)


def _total(tramos: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in tramos)


def _ruidosa(a: float, b: float, rms: list[float], ventana_s: float, umbral: float) -> bool:
    if not rms or umbral <= 0:
        return False
    i, j = int(a / ventana_s), int(b / ventana_s) + 1
    trozo = rms[i:j]
    return bool(trozo) and max(trozo) >= umbral


def tramos_con_habla(palabras: list[Palabra], duracion: float, rms: list[float] | None = None,
                     ventana_s: float = 0.1, pausa_max: float = PAUSA_MAX_S) -> list[tuple[float, float]]:
    """Los tramos con habla (o con ruido fuerte entre palabras), sin las pausas largas."""
    if not palabras:
        return [(0.0, duracion)]
    umbral = RUIDO_FACTOR * statistics.median(rms) if rms else 0.0
    out = []
    a = max(0.0, palabras[0].inicio - MARGEN_S)
    b = palabras[0].fin
    for p in palabras[1:]:
        hueco = p.inicio - b
        if hueco > pausa_max and not _ruidosa(b, p.inicio, rms or [], ventana_s, umbral):
            out.append((a, min(duracion, b + MARGEN_S)))
            a = max(0.0, p.inicio - MARGEN_S)
        b = max(b, p.fin)
    out.append((a, min(duracion, b + COLA_S)))
    # Tramos que se tocan (por los márgenes) se juntan; los muy cortos también se pegan al anterior.
    unidos: list[tuple[float, float]] = []
    for x, y in out:
        if unidos and (x <= unidos[-1][1] + 0.05 or y - x < MIN_TRAMO_S):
            unidos[-1] = (unidos[-1][0], max(unidos[-1][1], y))
        else:
            unidos.append((x, y))
    return [(round(x, 3), round(y, 3)) for x, y in unidos]


def _pico(rms: list[float], ventana_s: float) -> float | None:
    if not rms:
        return None
    i = max(range(len(rms)), key=lambda k: rms[k])
    return (i + 0.5) * ventana_s


def tramos_a_dejar(palabras: list[Palabra], duracion: float, rms: list[float] | None = None,
                   ventana_s: float = 0.1, min_s: float = MIN_S, max_s: float = MAX_S) -> list[tuple[float, float]]:
    """Qué partes del clip quedan (en segundos del original), en orden. Ver el docstring del módulo."""
    tramos = tramos_con_habla(palabras, duracion, rms, ventana_s)
    if _total(tramos) < min_s:
        # Sacando pausas queda muy corto: solo el principio y el final muertos.
        a, b = tramos[0][0], tramos[-1][1]
        if b - a < min_s:
            faltan = min_s - (b - a)
            a, b = max(0.0, a - faltan / 2), min(duracion, b + faltan / 2)
        return [(round(a, 3), round(b, 3))]
    if _total(tramos) <= max_s:
        return tramos
    # Más largo que el tope: el bloque seguido de tramos con más palabras que entra en max_s y
    # contiene el pico de volumen (el remate). Si ninguno lo contiene, el de más palabras.
    pico = _pico(rms or [], ventana_s)

    def palabras_en(ts):
        return sum(1 for p in palabras if any(x <= p.inicio < y for x, y in ts))

    mejor, mejor_clave = None, None
    for i in range(len(tramos)):
        bloque = []
        for j in range(i, len(tramos)):
            if _total(bloque + [tramos[j]]) > max_s:
                break
            bloque.append(tramos[j])
            if _total(bloque) < min_s:
                continue
            tiene = pico is not None and bloque[0][0] <= pico <= bloque[-1][1]
            clave = (tiene, palabras_en(bloque))
            if mejor_clave is None or clave > mejor_clave:
                mejor, mejor_clave = list(bloque), clave
    if mejor is None:
        # Un solo tramo de habla seguida más largo que el tope: se corta alrededor del pico.
        x, y = max(tramos, key=lambda t: t[1] - t[0])
        centro = pico if pico is not None and x <= pico <= y else (x + y) / 2
        a = max(x, min(centro - max_s * 0.65, y - max_s))
        return [(round(a, 3), round(min(y, a + max_s), 3))]
    return mejor


def mapear(palabras: list[Palabra], tramos: list[tuple[float, float]]) -> list[Palabra]:
    """Las palabras con los tiempos del video cortado; las que cayeron en un corte, afuera."""
    out, offset = [], 0.0
    for a, b in tramos:
        for p in palabras:
            medio = (p.inicio + p.fin) / 2
            if a <= medio < b:
                ini = offset + max(0.0, p.inicio - a)
                fin = offset + min(b - a, p.fin - a)
                out.append(Palabra(round(ini, 3), round(max(fin, ini + 0.05), 3), p.texto))
        offset += b - a
    return out


def mapear_t(t: float, tramos: list[tuple[float, float]]) -> float | None:
    offset = 0.0
    for a, b in tramos:
        if a <= t < b:
            return offset + t - a
        offset += b - a
    return None


def risas(palabras: list[Palabra]) -> list[float]:
    """Los segundos donde alguien se ríe ("jajaja", "jsjs", "xd")."""
    return [round((p.inicio + p.fin) / 2, 2) for p in palabras
            if _RISA.search(re.sub(r"[^\wñ]", "", p.texto.lower()))]


def cortar(entrada: Path, tramos: list[tuple[float, float]], duracion: float, salida: Path,
           tiene_audio: bool = True, preset: str = "veryfast") -> Path:
    """Un mp4 con solo `tramos`: el video con cortes secos y el audio con el crossfade de 0,04 s
    de las reglas fijas (media.audio_con_crossfade, que no corre la sincronía)."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    partes = [f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}]" for i, (a, b) in enumerate(tramos)]
    grafo = ";".join(partes) + ";" + "".join(f"[v{i}]" for i in range(len(tramos))) \
        + f"concat=n={len(tramos)}:v=1:a=0[v]"
    mapa = ["-map", "[v]"]
    if tiene_audio:
        grafo += ";" + audio_con_crossfade([("[0:a]", a, b, duracion) for a, b in tramos], "[a]",
                                           CROSSFADE_S)
        mapa += ["-map", "[a]"]
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(Path(entrada).resolve()),
         "-filter_complex", grafo, *mapa, "-c:v", "libx264", "-preset", preset, "-crf", "16",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(salida.resolve())])
    return salida
