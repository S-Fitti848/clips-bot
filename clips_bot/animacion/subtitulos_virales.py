"""Subtítulos de "Así Nació" estilo Shorts virales (Santi, 2026-11-14, REGLA para todos los videos del canal):

1. de 1 a 3 palabras por vez, nunca frases largas;
2. Montserrat Black (OFL, `letra.py`, dibujada como caminos: sale igual en cualquier rasterizador),
   contorno negro grueso y una sombra suave;
3. cada palabra entra con un "pop" (crece rápido y rebota apenas) JUSTO cuando la voz la empieza a decir
   (tiempos de Whisper alineados al guion);
4. las palabras CLAVE (las marca el guion: nombres, números, la palabra del giro o del chiste) más grandes y
   en amarillo; las de IMPACTO (algo se rompe, el remate) en rojo y con un temblor corto;
5. un emoji chico dibujado por código al lado de la clave cuando suma (💥 explosión, 💰 plata, 😱 susto,
   🤣 risa), como mucho uno cada 4,5 s;
6. arriba, en la franja de siempre (la escena no sube de ahí: `acciones.BANDA_SUBTITULOS`): nada se sale
   del ancho ni de la franja (si no entra, se achica la clave y después el grupo).
"""
from __future__ import annotations

import math
import re

from . import letra
from . import paleta as P
from .easing import recortar

TAM = 70                 # palabra común (px)
TAM_CLAVE = 92           # palabra clave
ANCHO_MAX = 900          # el grupo entero (con el emoji) entra acá; con el pop (+12 %) y el temblor, igual entra en 1080
Y = 225                  # centro vertical de la línea (la escena no sube de y = 300)
EMOJI = 0.95             # alto del emoji / tamaño de la clave
TOPE_Y = 300             # nada del subtítulo baja de acá
BLANCO = "#ffffff"
AMARILLO = P.AMARILLO    # clave
ROJO = "#ff4b3e"         # impacto (se rompe algo, el remate)
CONTORNO = "#111111"
POP_S = 0.16             # cuánto tarda el pop
TEMBLOR_S = 0.45
EMOJI_CADA_S = 4.5
EMOJIS = ("explosion", "plata", "susto", "risa")
MAX_PALABRAS = 3
MAX_LETRAS = 15


def pop(u: float) -> float:
    """Crece rápido y rebota apenas: 0 → 1,12 → 1 (en `u` de 0 a 1)."""
    if u <= 0:
        return 0.0
    if u >= 1:
        return 1.0
    if u < 0.55:
        return 1.12 * math.sin(u / 0.55 * math.pi / 2)
    return 1.12 - 0.12 * math.sin((u - 0.55) / 0.45 * math.pi / 2)


def agrupar(palabras: list) -> list[list]:
    """Grupos de 1 a 3 palabras: corta por cantidad, por largo, después de un signo, ANTES de una clave si
    ya hay 2 (la clave no queda apretada) y DESPUÉS de una clave con emoji (el emoji necesita lugar)."""
    grupos, actual = [], []
    for p in palabras:
        largo = sum(len(q.texto) + 1 for q in actual) + len(p.texto)
        if actual and (len(actual) >= MAX_PALABRAS or largo > MAX_LETRAS
                       or (getattr(p, "clave", False) and len(actual) >= 2)):
            grupos.append(actual)
            actual = []
        actual.append(p)
        if re.search(r"[.,;:!?…]$", p.texto) or getattr(p, "emoji", ""):
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    return grupos


def grupo_en(grupos: list[list], t: float):
    for i, gr in enumerate(grupos):
        fin = grupos[i + 1][0].inicio if i + 1 < len(grupos) else gr[-1].fin + 0.4
        if gr[0].inicio - 0.02 <= t < min(fin, gr[-1].fin + 0.6):
            return gr
    return None


def _medidas(grupo: list) -> tuple[list[float], list[float], float, float]:
    """(tamaños, anchos, espacio, ancho del emoji) que entran en ANCHO_MAX: primero se achica la clave
    (hasta el tamaño común), después todo el grupo."""
    textos = [p.texto.upper() for p in grupo]
    hay_emoji = any(getattr(p, "emoji", "") for p in grupo)
    tam_clave = TAM_CLAVE
    while True:
        tams = [tam_clave if getattr(p, "clave", False) else TAM for p in grupo]
        anchos = [letra.ancho(s, k) for s, k in zip(textos, tams)]
        esp = TAM * 0.45      # con aire: cada palabra crece un 12 % en su pop
        emoji = tam_clave * EMOJI + esp if hay_emoji else 0.0
        total = sum(anchos) + esp * (len(grupo) - 1) + emoji
        if total <= ANCHO_MAX or tam_clave <= TAM:
            break
        tam_clave = max(TAM, tam_clave - 4)
    if total > ANCHO_MAX:
        k = ANCHO_MAX / total
        tams = [x * k for x in tams]
        anchos = [x * k for x in anchos]
        esp *= k
        emoji *= k
    return tams, anchos, esp, emoji


def _palabra(texto: str, tam: float, color: str, cx: float, base: float, esc: float, rot: float = 0.0) -> str:
    """Una palabra centrada en `cx`, con la línea de base en `base`: sombra suave (dos copias corridas y
    transparentes), contorno negro grueso y el relleno; escalada desde su centro (el pop)."""
    d = letra.camino(texto, tam)
    if not d or esc <= 0.001:
        return ""
    w = letra.ancho(texto, tam)
    alto = tam * 0.7
    borde = max(6.0, tam * 0.2)
    cy = base - alto / 2
    t = (f'translate({cx:.1f} {cy:.1f}) rotate({rot:.2f}) scale({esc:.3f}) '
         f'translate({-w / 2:.1f} {alto / 2:.1f})')
    j = 'stroke-linejoin="round" stroke-linecap="round"'
    return (f'<g transform="{t}">'
            f'<path d="{d}" fill="#000" stroke="#000" stroke-width="{borde * 1.5:.1f}" {j} opacity="0.16" '
            f'transform="translate({tam * 0.1:.1f} {tam * 0.13:.1f})"/>'
            f'<path d="{d}" fill="#000" stroke="#000" stroke-width="{borde:.1f}" {j} opacity="0.3" '
            f'transform="translate({tam * 0.05:.1f} {tam * 0.07:.1f})"/>'
            f'<path d="{d}" fill="{CONTORNO}" stroke="{CONTORNO}" stroke-width="{borde:.1f}" {j}/>'
            f'<path d="{d}" fill="{color}"/></g>')


def subtitulo(grupos: list[list], t: float, y: float = Y) -> str:
    """El SVG de los subtítulos en el segundo `t` (global)."""
    grupo = grupo_en(grupos, t)
    if not grupo:
        return ""
    tams, anchos, esp, ancho_emoji = _medidas(grupo)
    total = sum(anchos) + esp * (len(grupo) - 1) + ancho_emoji
    x = (P.ANCHO - total) / 2
    out = []
    for p, k, w in zip(grupo, tams, anchos):
        u = recortar((t - p.inicio) / POP_S)
        esc = pop(u) if t >= p.inicio - 0.01 else 0.0
        clave = getattr(p, "clave", False)
        impacto = clave and getattr(p, "impacto", False)
        color = ROJO if impacto else AMARILLO if clave else BLANCO
        dx = dy = rot = 0.0
        if impacto and 0 <= t - p.inicio < TEMBLOR_S:     # temblor corto que se apaga
            a = 1 - (t - p.inicio) / TEMBLOR_S
            dx, dy, rot = 7 * a * math.sin(t * 97), 5 * a * math.cos(t * 83), 4 * a * math.sin(t * 71)
        base = y + k * 0.35
        out.append(_palabra(p.texto.upper(), k, color, x + w / 2 + dx, base + dy, esc, rot))
        x += w
        emoji = getattr(p, "emoji", "")
        if emoji and ancho_emoji:
            x += esp
            lado = ancho_emoji - esp
            u2 = recortar((t - p.inicio - 0.08) / POP_S)
            if t >= p.inicio and u2 > 0:
                out.append(f'<g transform="translate({x + lado / 2:.1f} {y:.1f}) rotate({-8 + 8 * u2:.1f}) '
                           f'scale({pop(u2) * lado / 100:.3f})">{emoji_svg(emoji)}</g>')
            x += lado
        x += esp
    return "".join(out)


# ---- emojis dibujados (estilo del canal: contorno oscuro, colores planos con una sombra) -----------
# Centrados en (0, 0), ~100 px. Propios: no dependen de una fuente de emojis del sistema ni de Twemoji.

_C = "#1f1a24"
_T = f'stroke="{_C}" stroke-linejoin="round" stroke-linecap="round"'


def _cara(fondo: str = "#ffd23f") -> str:
    return (f'<circle r="46" fill="{fondo}" {_T} stroke-width="6"/>'
            f'<path d="M-30 30 A46 46 0 0 0 40 20 A40 40 0 0 1 -30 30 Z" fill="#e8a920"/>'
            f'<ellipse cx="-16" cy="-24" rx="14" ry="8" fill="#fff6c8" opacity="0.8"/>')


def emoji_svg(nombre: str) -> str:
    if nombre == "explosion":         # 💥
        pts = []
        for i in range(16):
            r = 50 if i % 2 == 0 else 24
            a = math.pi * 2 * i / 16 - math.pi / 2
            pts.append(f"{r * math.cos(a):.1f} {r * math.sin(a):.1f}")
        chico = []
        for i in range(12):
            r = 28 if i % 2 == 0 else 13
            a = math.pi * 2 * i / 12 - math.pi / 3
            chico.append(f"{r * math.cos(a):.1f} {r * math.sin(a):.1f}")
        return (f'<path d="M{" L".join(pts)} Z" fill="#ff4b3e" {_T} stroke-width="6"/>'
                f'<path d="M{" L".join(chico)} Z" fill="#ffd23f" {_T} stroke-width="4"/>'
                f'<circle r="8" fill="#fff6c8"/>')
    if nombre == "plata":             # 💰
        signo = letra.camino("$", 56)
        return (f'<path d="M-14 -36 Q-26 -50 -12 -54 L12 -54 Q26 -50 14 -36 Q52 -14 48 22 Q44 48 0 48 '
                f'Q-44 48 -48 22 Q-52 -14 -14 -36 Z" fill="#d6a45a" {_T} stroke-width="6"/>'
                f'<path d="M-30 30 Q0 50 40 26 Q40 44 0 46 Q-30 46 -30 30 Z" fill="#b07d3a"/>'
                f'<path d="M-18 -36 L18 -36" {_T} stroke-width="8"/>'
                f'<g transform="translate({-letra.ancho("$", 56) / 2:.1f} 22)">'
                f'<path d="{signo}" fill="#2f8a45" stroke="{_C}" stroke-width="5" stroke-linejoin="round"/>'
                f'<path d="{signo}" fill="#4cb963"/></g>')
    if nombre == "susto":             # 😱
        return (_cara("#ffd23f")
                + '<path d="M-46 -6 A46 46 0 0 1 46 -6 Q0 -30 -46 -6 Z" fill="#7fb7e8" opacity="0.9"/>'
                + f'<ellipse cx="-16" cy="-8" rx="9" ry="12" fill="#fff" {_T} stroke-width="4"/>'
                + f'<ellipse cx="16" cy="-8" rx="9" ry="12" fill="#fff" {_T} stroke-width="4"/>'
                + f'<circle cx="-16" cy="-6" r="4" fill="{_C}"/><circle cx="16" cy="-6" r="4" fill="{_C}"/>'
                + f'<ellipse cx="0" cy="24" rx="11" ry="16" fill="#5a1e2a" {_T} stroke-width="4"/>'
                + f'<path d="M-50 10 Q-60 30 -40 44 Q-34 30 -36 16 Z M50 10 Q60 30 40 44 Q34 30 36 16 Z" '
                  f'fill="#ffd23f" {_T} stroke-width="5"/>')
    if nombre == "risa":              # 🤣
        return (f'<g transform="rotate(-18)">{_cara("#ffd23f")}'
                f'<path d="M-26 -14 Q-16 -24 -6 -14 M6 -14 Q16 -24 26 -14" fill="none" {_T} stroke-width="6"/>'
                f'<path d="M-28 6 Q0 4 28 6 Q24 36 0 38 Q-24 36 -28 6 Z" fill="#5a1e2a" {_T} stroke-width="5"/>'
                f'<path d="M-24 8 Q0 6 24 8 L22 14 Q0 12 -22 14 Z" fill="#fff"/>'
                f'<path d="M-36 -10 Q-56 0 -50 16 Q-40 14 -34 -2 Z M36 -10 Q56 0 50 16 Q40 14 34 -2 Z" '
                f'fill="#7fd0ff" {_T} stroke-width="4"/></g>')
    return ""


# ---- marcas del guion → palabras --------------------------------------------------------------------

def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ]+", "", s)


RELLENO = {"a", "al", "de", "del", "el", "la", "las", "lo", "los", "un", "una", "unos", "unas", "y", "o", "e", "en",
           "con", "por", "para", "que", "se", "su", "sus", "es", "mas", "muy", "tan", "ya", "le", "les", "me", "te"}


def marcar(palabras: list, segmentos: list[dict], golpes: list[float], max_claves: int = 2) -> list:
    """Pone `clave`, `impacto` y `emoji` en las palabras (ya con los tiempos de la voz).

    `segmentos`: lo que dice la voz en orden, cada uno {"texto", "claves": [...], "emoji": str, "remate": bool}
    (las claves son palabras de ESE texto: una clave que no está, no cuenta). `golpes`: segundos globales
    de lo que se rompe o golpea (SFX golpe/vidrio). Se hace cumplir: como mucho `max_claves` claves por
    segmento (los números cuentan como clave), un emoji cada 4,5 s y solo al lado de una clave; IMPACTO =
    clave en el remate o a menos de 0,5 s de un golpe."""
    i = 0
    ultimo_emoji = -99.0
    for seg in segmentos:
        n = len(str(seg.get("texto") or "").split())
        tramo = palabras[i:i + n]
        i += n
        # una clave de varias palabras ("pelota de espuma") marca sus palabras con contenido, no "de" ni "la"
        claves = {_norm(c) for x in seg.get("claves") or [] for c in str(x).split()
                  if _norm(c) and _norm(c) not in RELLENO}
        marcadas = 0
        primera_clave = None
        for p in tramo:
            w = _norm(p.texto)
            es = bool(w) and (w in claves or any(ch.isdigit() for ch in w))
            if es and marcadas < max_claves:
                p.clave = True
                marcadas += 1
                cerca = any(abs(p.inicio - g) <= 0.5 for g in golpes)
                p.impacto = bool(seg.get("remate")) or cerca
                primera_clave = primera_clave or p
        emoji = str(seg.get("emoji") or "")
        if emoji in EMOJIS and primera_clave is not None and primera_clave.inicio - ultimo_emoji >= EMOJI_CADA_S:
            primera_clave.emoji = emoji
            ultimo_emoji = primera_clave.inicio
    return palabras


def limites(grupos: list[list], y: float = Y) -> tuple[float, float, float, float]:
    """(x mínimo, x máximo, y mínimo, y máximo) que puede ocupar el subtítulo más grande (con el pop al
    máximo, el temblor, el contorno y la sombra): para el chequeo de que nada se sale del ancho ni de la franja."""
    x0, x1, y0, y1 = float(P.ANCHO), 0.0, float(P.ALTO), 0.0
    for gr in grupos:
        tams, anchos, esp, emoji = _medidas(gr)
        total = sum(anchos) + esp * (len(gr) - 1) + emoji
        k = max(tams)
        borde = max(6.0, k * 0.2) * 0.75
        temblor = 7.0 if any(getattr(p, "impacto", False) for p in gr) else 0.0
        mitad = (P.ANCHO - total) / 2
        x0 = min(x0, mitad - borde - temblor - 0.06 * max(anchos))
        x1 = max(x1, P.ANCHO - mitad + borde + temblor + 0.06 * max(anchos) + k * 0.1)
        alto_txt = k * 0.7 * 1.12 / 2 + borde + temblor
        alto_emo = (k * EMOJI * 1.12 / 2 + 4) if emoji else 0.0
        y0 = min(y0, y - max(alto_txt, alto_emo))
        y1 = max(y1, y + max(alto_txt + k * 0.13, alto_emo))
    return x0, x1, y0, y1
