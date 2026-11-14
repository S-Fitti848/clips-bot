"""Texto animado: el gancho grande (rebote o palabra por palabra) y los subtítulos estilo Shorts
(2-3 palabras por vez, letra gruesa con borde, la palabra que se dice en color y con un saltito)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import paleta as P
from .easing import rebote, recortar, salida
from .svg import ancho_texto, g, texto_con_borde


def partir_lineas(texto: str, tam: int, ancho_max: float) -> list[list[str]]:
    """Palabras repartidas en líneas que entren en `ancho_max` (medido con la fuente real)."""
    lineas: list[list[str]] = [[]]
    esp = ancho_texto(" ", tam)
    actual = 0.0
    for p in texto.split():
        w = ancho_texto(p, tam)
        if lineas[-1] and actual + esp + w > ancho_max:
            lineas.append([])
            actual = 0.0
        actual += (esp if lineas[-1] else 0) + w
        lineas[-1].append(p)
    return [ln for ln in lineas if ln]


def gancho(texto: str, t: float, modo: str = "palabras", y: float = 380, tam: int = 104,
           color: str = P.TEXTO_GANCHO, ancho_max: float = 960, x: float = P.ANCHO / 2,
           ritmo_s: float = 0.14) -> str:
    """El título/gancho en el segundo `t` desde que aparece.
    - "rebote": entra todo junto, escalando desde 0 con un rebote (0,45 s).
    - "palabras": cada palabra aparece a `ritmo_s` de la anterior con un pop."""
    lineas = partir_lineas(texto.upper(), tam, ancho_max)
    alto_linea = tam * 1.12
    y0 = y - alto_linea * (len(lineas) - 1) / 2
    esp = ancho_texto(" ", tam)
    partes = []
    i = 0
    for k, linea in enumerate(lineas):
        ly = y0 + k * alto_linea
        anchos = [ancho_texto(p, tam) for p in linea]
        cx = x - (sum(anchos) + esp * (len(linea) - 1)) / 2
        for p, w in zip(linea, anchos):
            if modo == "palabras":
                u = recortar((t - i * ritmo_s) / 0.3)
                if u > 0:
                    esc = max(0.0, rebote(u))
                    partes.append(g(texto_con_borde(p, 0, tam * 0.35, tam, color=color),
                                    cx + w / 2, ly, escala=esc))
            else:
                partes.append(texto_con_borde(p, cx + w / 2, ly + tam * 0.35, tam, color=color))
            cx += w + esp
            i += 1
    if modo != "palabras":
        u = recortar(t / 0.45)
        return _escalar_en(partes, x, y, rebote(u)) if u > 0 else ""
    return "".join(partes)


# ---- subtítulos ---------------------------------------------------------------


@dataclass
class Palabra:
    texto: str
    inicio: float
    fin: float


def palabras_de_texto(texto: str, inicio: float, fin: float) -> list[Palabra]:
    """Reparte el tiempo entre las palabras según su largo (sin alineación con la voz: para eso
    pasar los tiempos de Whisper)."""
    ps = texto.split()
    if not ps:
        return []
    pesos = [len(re.sub(r"\W", "", p)) + 2 for p in ps]
    total = sum(pesos)
    out, t = [], inicio
    for p, w in zip(ps, pesos):
        d = (fin - inicio) * w / total
        out.append(Palabra(p, t, t + d))
        t += d
    return out


def agrupar(palabras: list[Palabra], max_palabras: int = 3, max_chars: int = 16) -> list[list[Palabra]]:
    """Grupos de 2-3 palabras: corta por cantidad, por largo o después de un signo de puntuación."""
    grupos: list[list[Palabra]] = []
    actual: list[Palabra] = []
    for p in palabras:
        largo = sum(len(q.texto) + 1 for q in actual) + len(p.texto)
        if actual and (len(actual) >= max_palabras or largo > max_chars):
            grupos.append(actual)
            actual = []
        actual.append(p)
        if re.search(r"[.,;:!?…]$", p.texto) and len(actual) >= 1:
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def subtitulo(grupos: list[list[Palabra]], t: float, y: float = 1500, tam: int = 92,
              color: str = P.TEXTO, activo: str = P.TEXTO_ACTIVO, x: float = P.ANCHO / 2) -> str:
    """El grupo que corresponde al segundo `t` (global), con la palabra activa en color, un poco
    más grande y con un salto de 0,15 s al empezar."""
    grupo = None
    for i, gr in enumerate(grupos):
        fin = grupos[i + 1][0].inicio if i + 1 < len(grupos) else gr[-1].fin + 0.3
        if gr[0].inicio <= t < min(fin, gr[-1].fin + 0.6):
            grupo = gr
            break
    if not grupo:
        return ""
    textos = [p.texto.upper() for p in grupo]
    esp = ancho_texto(" ", tam) * 1.7   # más aire: la palabra activa crece un poco
    anchos = [ancho_texto(s, tam) for s in textos]
    total = sum(anchos) + esp * (len(textos) - 1)
    escala_grupo = min(1.0, 980 / total) if total else 1.0
    cx = x - total * escala_grupo / 2
    partes = []
    # entrada del grupo: pop corto
    pop = rebote(recortar((t - grupo[0].inicio) / 0.18))
    for p, s, w in zip(grupo, textos, anchos):
        w *= escala_grupo
        es_activa = p.inicio <= t < p.fin
        salto = 0.0
        esc = escala_grupo
        if es_activa:
            u = recortar((t - p.inicio) / 0.15)
            salto = -18 * math.sin(math.pi * u)
            esc *= 1.05
        partes.append(g(texto_con_borde(s, 0, tam * 0.35, tam, color=activo if es_activa
                                        else color), cx + w / 2, y + salto, escala=esc))
        cx += w + esp * escala_grupo
    return _escalar_en(partes, x, y, 0.85 + 0.15 * pop)


def _escalar_en(partes: list[str], x: float, y: float, esc: float) -> str:
    """Escala un grupo alrededor de (x, y) (SVG escala alrededor del origen)."""
    contenido = "".join(partes)
    if abs(esc - 1) < 1e-3:
        return contenido
    if esc <= 0:
        return ""
    return g(g(contenido, -x, -y), x, y, escala=esc)


def entrada_lateral(contenido: str, t: float, dur: float = 0.35, desde_x: float = -P.ANCHO) -> str:
    """Ayuda: desliza un contenido desde un costado (para carteles armados a mano)."""
    u = salida(recortar(t / dur))
    return g(contenido, desde_x * (1 - u), 0)
