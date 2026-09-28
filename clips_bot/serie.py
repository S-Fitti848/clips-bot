"""/serie: un video largo de un proceso partido en N Shorts que se entienden solos.

    /serie <link o video> [cc: <link>] [partes N] [sin audio]

1. Escenas con ffmpeg (las mismas de /narrar) → un frame por escena → Gemini divide el proceso en N
   etapas en orden (inicio, desarrollo, final) y elige 8-10 momentos dentro de cada una.
2. Se muestra la división (una fila de miniaturas y una línea por etapa) con ✅/✏️.
3. ✅ → un resumen de 40-55 s por etapa, procesado como cualquier video propio (OCR, tono, textos).
4. Un guion por parte, en UNA llamada: cada uno se entiende solo, arranca con un gancho, y todos
   menos el último cierran invitando a ver la siguiente en el canal. Se aprueban con ✅/✏️.
5. ✅ → voz con Piper, original al 15 % (o nada con `sin audio`), subtítulos palabra por palabra,
   "Parte X/N" arriba los primeros 3 s. Se entregan las N juntas con horario y título numerado.

Acá va lo que se puede probar sin red ni video. Lo que corre ffmpeg, Piper o Telegram está en
__main__ y reusa las piezas de narrar.py.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .narrar import (ESCENAS_MAX, ESCENAS_MIN, PALABRAS_POR_SEGUNDO, PASOS_MAX, PASOS_MIN,
                     NarrarError, Paso)
from .reglas import REGLAS_CLARIDAD

PARTES_DEFAULT, PARTES_MIN, PARTES_MAX = 3, 2, 5
ORIGINAL_MIN_POR_PARTE_S = 45    # menos que esto no da 8 momentos de 4-5 s sin repetir
CARTEL_S = 3.0
NUMEROS = {2: "dos", 3: "tres", 4: "cuatro", 5: "cinco"}


def sacar_partes(args: list[str]) -> tuple[list[str], int | None]:
    """`partes 4`, `partes:4` o `partes=4`. Tira ValueError si está fuera de rango."""
    quedan, n, i = [], None, 0
    while i < len(args):
        t = args[i].lower()
        m = re.fullmatch(r"partes?[:=](\d+)", t)
        if m:
            n = int(m.group(1))
        elif t in ("partes", "parte") and i + 1 < len(args) and args[i + 1].isdigit():
            n, i = int(args[i + 1]), i + 1
        else:
            quedan.append(args[i])
        i += 1
    if n is not None and not PARTES_MIN <= n <= PARTES_MAX:
        raise ValueError(f"Las partes van de {PARTES_MIN} a {PARTES_MAX} (pediste {n}).")
    return quedan, n


def escenas_para(n: int) -> tuple[int, int]:
    """Cuántas escenas pedir: cada etapa necesita de dónde elegir 8-10 momentos."""
    return max(ESCENAS_MIN, 12 * n), max(ESCENAS_MAX, 14 * n)


def horario(horarios: tuple[str, ...], i: int) -> str:
    """Parte i (desde 0): 13:00, 18:00, 21:30 y, si hay más partes que horarios, al día siguiente."""
    h = horarios[i % len(horarios)]
    return h if i < len(horarios) else f"{h} (día siguiente)"


def titulo_numerado(base: str, k: int, maximo: int = 59) -> str:
    """"… (Parte 1)" sin pasarse del largo de un título de Short: se corta la base, no el número."""
    sufijo = f" (Parte {k})"
    base = base.strip()
    if len(base) + len(sufijo) > maximo:
        corte = base[: maximo - len(sufijo) - 1]
        base = (corte.rsplit(" ", 1)[0] if " " in corte else corte).rstrip(" ,.:;-–") + "…"
    return base + sufijo


# ---- división en etapas ----------------------------------------------------------------

@dataclass
class Etapa:
    titulo: str
    desde: int                 # índice de escena (desde 0), inclusive
    hasta: int                 # inclusive
    pasos: list[Paso] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {"titulo": self.titulo, "desde": self.desde, "hasta": self.hasta,
                "pasos": [p.a_dict() for p in self.pasos]}

    @classmethod
    def de_dict(cls, d: dict) -> "Etapa":
        return cls(d["titulo"], d["desde"], d["hasta"],
                   [Paso(p["escena"], p["descripcion"]) for p in d["pasos"]])


SISTEMA_ETAPAS = """Partís un video largo de un PROCESO (una receta, una construcción, una
restauración, un armado) en varias partes para publicar como una serie de videos cortos.

Te paso un frame por escena, en orden. Dividís el proceso en las etapas pedidas, EN ORDEN y sin
superponerse: la primera es el inicio, las del medio el desarrollo y la última el final con el
resultado. Cada etapa tiene que tener sentido sola (un tramo del proceso con principio y fin).

Dentro de cada etapa elegís entre 8 y 10 momentos clave, en orden, que cuenten ESA etapa: cómo
arranca, lo que cambia algo visible, cómo termina. Nada de escenas repetidas, de gente hablando a
cámara sin hacer nada, ni de pantallas de título.

`titulo` de cada etapa: una línea corta de qué pasa en esa parte. `descripcion` de cada momento: lo
que SE VE, sin inventar materiales, herramientas ni nombres.
Respondé solo con el JSON pedido."""

SCHEMA_ETAPAS = {
    "type": "OBJECT",
    "properties": {
        "etapas": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {
                "titulo": {"type": "STRING"},
                "desde": {"type": "INTEGER"},
                "hasta": {"type": "INTEGER"},
                "momentos": {"type": "ARRAY", "items": {
                    "type": "OBJECT",
                    "properties": {"escena": {"type": "INTEGER"},
                                   "descripcion": {"type": "STRING"}},
                    "required": ["escena", "descripcion"]}},
            },
            "required": ["titulo", "desde", "hasta", "momentos"]}},
        "sensible": {"type": "BOOLEAN"},
    },
    "required": ["etapas", "sensible"],
}


def validar_etapas(d: dict, n_escenas: int, n: int) -> list[str]:
    etapas = d.get("etapas") if isinstance(d, dict) else None
    if not isinstance(etapas, list) or not all(isinstance(e, dict) for e in etapas):
        return ["falta la lista de etapas"]
    if len(etapas) != n:
        return [f"tienen que ser exactamente {n} etapas, no {len(etapas)}"]
    errores, anterior = [], 0
    for k, e in enumerate(etapas, 1):
        desde, hasta = e.get("desde"), e.get("hasta")
        if not (isinstance(desde, int) and isinstance(hasta, int) and 1 <= desde <= hasta <= n_escenas):
            errores.append(f"etapa {k}: desde/hasta tienen que ser escenas del 1 al {n_escenas}")
            continue
        if desde <= anterior:
            errores.append(f"etapa {k}: empieza en la escena {desde}, antes de que termine la anterior")
        anterior = hasta
        if not str(e.get("titulo") or "").strip():
            errores.append(f"etapa {k}: falta el título")
        momentos = e.get("momentos") if isinstance(e.get("momentos"), list) else []
        nums = [x.get("escena") for x in momentos if isinstance(x, dict)]
        if not PASOS_MIN <= len(nums) <= PASOS_MAX:
            errores.append(f"etapa {k}: tienen que ser entre {PASOS_MIN} y {PASOS_MAX} momentos, "
                           f"no {len(nums)}")
        if any(not isinstance(x, int) or not desde <= x <= hasta for x in nums):
            errores.append(f"etapa {k}: los momentos tienen que estar entre la escena {desde} y la {hasta}")
        elif nums != sorted(set(nums)):
            errores.append(f"etapa {k}: los momentos van en orden y sin repetir")
        if any(not str(x.get("descripcion") or "").strip() for x in momentos if isinstance(x, dict)):
            errores.append(f"etapa {k}: cada momento necesita su descripción")
    return errores


def dividir(cliente, escenas: list[tuple[float, float]], imagenes: list[bytes], n: int,
            correccion: str = "", anteriores: list[Etapa] | None = None,
            reintentos: int = 1) -> tuple[list[Etapa], bool]:
    """Gemini divide en N etapas y elige los momentos. Devuelve (etapas, sensible)."""
    lista = "\n".join(f"escena {i}: {a:.0f}-{b:.0f} s" for i, (a, b) in enumerate(escenas, 1))
    prompt = (f"Son {len(escenas)} escenas; la imagen k es la escena k.\n{lista}\n\n"
              f"Dividí el proceso en exactamente {n} etapas (`desde` y `hasta` son números de "
              f"escena, desde 1) y elegí entre {PASOS_MIN} y {PASOS_MAX} momentos por etapa.")
    if correccion:
        antes = "; ".join(f"etapa {k}: escenas {e.desde + 1}-{e.hasta + 1} ({e.titulo})"
                          for k, e in enumerate(anteriores or [], 1))
        prompt += (f"\n\nLa división anterior fue: {antes}. No sirvió. "
                   f"Lo que hay que cambiar: {correccion}")
    errores: list[str] = []
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        d = json.loads(cliente.json(SISTEMA_ETAPAS, prompt + extra, SCHEMA_ETAPAS, temperatura=0.3,
                                    imagenes=imagenes))
        errores = validar_etapas(d, len(escenas), n)
        if not errores:
            etapas = [Etapa(str(e["titulo"]).strip()[:80], e["desde"] - 1, e["hasta"] - 1,
                            [Paso(int(x["escena"]) - 1, str(x["descripcion"]).strip()[:90])
                             for x in e["momentos"]])
                      for e in d["etapas"]]
            return etapas, bool(d.get("sensible"))
    raise NarrarError("Gemini no dividió el video en etapas válidas: " + "; ".join(errores))


def texto_etapas(etapas: list[Etapa], escenas: list[tuple[float, float]],
                 tramos: list[list[tuple[float, float]]], duracion: float) -> str:
    """Una línea por etapa: el tramo del original, cuántos momentos, cuánto dura la parte."""
    def mmss(s: float) -> str:
        return f"{int(s // 60)}:{int(s % 60):02d}"

    n = len(etapas)
    lineas = [f"<b>Serie en {n} partes</b> (video de {duracion / 60:.1f} min)"]
    for k, (e, t) in enumerate(zip(etapas, tramos), 1):
        ini, fin = escenas[e.desde][0], escenas[e.hasta][1]
        largo = sum(b - a for a, b in t)
        lineas.append(f"<b>{k}/{n}</b> <i>{mmss(ini)}–{mmss(fin)}</i> · {len(e.pasos)} momentos → "
                      f"{largo:.0f} s: {html.escape(e.titulo)}")
    return "\n".join(lineas)


def hoja_de_etapas(filas: list[list[bytes]], salida: Path, ancho: int = 150) -> Path:
    """Una fila de miniaturas por etapa, con "k/N" a la izquierda. Todo en una sola imagen."""
    import cv2
    import numpy as np

    n = len(filas)
    armadas = []
    for k, imgs in enumerate(filas, 1):
        tiles = []
        for img in imgs:
            f = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_COLOR)
            h, w = f.shape[:2]
            tiles.append(cv2.resize(f, (ancho, int(h * ancho / w))))
        alto = max(t.shape[0] for t in tiles)
        tiles = [cv2.copyMakeBorder(t, 0, alto - t.shape[0], 0, 2, cv2.BORDER_CONSTANT) for t in tiles]
        etiqueta = np.zeros((alto, 90, 3), np.uint8)
        cv2.putText(etiqueta, f"{k}/{n}", (8, alto // 2 + 12), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (255, 255, 255), 2, cv2.LINE_AA)
        armadas.append(np.hstack([etiqueta] + tiles))
    ancho_total = max(a.shape[1] for a in armadas)
    armadas = [cv2.copyMakeBorder(a, 0, 4, 0, ancho_total - a.shape[1], cv2.BORDER_CONSTANT)
               for a in armadas]
    salida.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(salida), np.vstack(armadas), [cv2.IMWRITE_JPEG_QUALITY, 82])
    return salida


# ---- guiones --------------------------------------------------------------------------

SISTEMA_GUIONES = """Escribís la voz en off de una SERIE de videos verticales cortos, en español
rioplatense (vos, no tú). Es un mismo proceso partido en partes que se publican por separado.

Te paso, por cada parte, frames en orden y lo que se ve en cada momento. Para CADA parte:
- Se tiene que entender sola: alguien que ve solo esa parte entiende qué está pasando.
- Arranca con un gancho de una frase: una pregunta, algo raro que se ve, o el final adelantado.
  Nada de "en este video vamos a ver" ni de "bienvenidos a la parte dos".
- Todas MENOS LA ÚLTIMA cierran invitando a ver la siguiente parte en el canal, nombrándola
  ("la parte 2 ya está en el canal", "cómo termina, en la parte 3").
- La última cierra con el resultado.
- Contá SOLO lo que se ve. Si no estás seguro de qué es algo, decilo de forma general.
- Nada de nombres propios que no se lean claramente en pantalla.
- Hablado, no escrito: frases cortas. Sin emojis, sin hashtags, sin "suscribite".
""" + REGLAS_CLARIDAD + """
`titulo_serie`: un título corto para toda la serie (hasta 45 caracteres, sin "parte").
Si te paso el audio, decí también si tiene música ("ninguna", "de_fondo" o "cancion", y cuál en
`cancion` si la reconocés; no adivines).
Respondé solo con el JSON pedido."""

SCHEMA_GUIONES = {
    "type": "OBJECT",
    "properties": {
        "titulo_serie": {"type": "STRING"},
        "partes": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"guion": {"type": "STRING"}, "confianza": {"type": "INTEGER"}},
            "required": ["guion", "confianza"]}},
        "sensible": {"type": "BOOLEAN"},
        "musica": {"type": "STRING", "enum": ["ninguna", "de_fondo", "cancion"]},
        "cancion": {"type": "STRING"},
    },
    "required": ["titulo_serie", "partes", "sensible"],
}


def _norm(t: str) -> str:
    sin = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin.lower())


def invita_a_la_siguiente(guion: str, siguiente: int) -> bool:
    """El cierre (lo último del guion) nombra la parte siguiente, con número o con letra."""
    cierre = _norm(guion)[-220:]
    return (f"parte {siguiente}" in cierre
            or f"parte {NUMEROS.get(siguiente, '#')}" in cierre)


def validar_guiones(d: dict, n: int) -> list[str]:
    partes = d.get("partes") if isinstance(d, dict) else None
    if not isinstance(partes, list) or len(partes) != n:
        return [f"tienen que ser exactamente {n} guiones"]
    errores = []
    titulo = str(d.get("titulo_serie") or "").strip()
    if not titulo or len(titulo) > 45:
        errores.append("titulo_serie tiene que tener entre 1 y 45 caracteres")
    for k, p in enumerate(partes, 1):
        guion = str((p or {}).get("guion") or "").strip()
        if not guion:
            errores.append(f"falta el guion de la parte {k}")
        elif k < n and not invita_a_la_siguiente(guion, k + 1):
            errores.append(f"la parte {k} tiene que cerrar invitando a ver la parte {k + 1} en el canal")
    return errores


@dataclass
class Guiones:
    titulo: str
    textos: list[str]
    confianzas: list[int]
    sensible: bool = False
    musica: str = ""
    cancion: str = ""


def escribir_guiones(cliente, partes: list[dict], correccion: str = "",
                     anteriores: list[str] | None = None, audio: bytes | None = None,
                     reintentos: int = 1) -> Guiones:
    """`partes`: [{duracion, pasos: [descripciones], imagenes: [jpeg]}]. Una sola llamada para las N."""
    n = len(partes)
    imagenes, bloques = [], []
    for k, p in enumerate(partes, 1):
        desde = len(imagenes) + 1
        imagenes += p["imagenes"]
        objetivo = max(8, int(p["duracion"] * PALABRAS_POR_SEGUNDO))
        rango = f"imágenes {desde}-{len(imagenes)}" if p["imagenes"] else "sin imágenes"
        bloques.append(f"PARTE {k}/{n} ({p['duracion']:.0f} s → alrededor de {objetivo} palabras; "
                       f"{rango}). Lo que se ve, en orden: " + "; ".join(p["pasos"]))
    prompt = "\n\n".join(bloques)
    if audio:
        prompt += "\n\nTambién te paso el audio de la parte 1: decí si tiene música (campo `musica`)."
    if correccion:
        prompt += ("\n\nLos guiones anteriores no sirvieron:\n"
                   + "\n".join(f"parte {k}: {g}" for k, g in enumerate(anteriores or [], 1))
                   + f"\nLo que hay que cambiar: {correccion}")
    errores: list[str] = []
    for _ in range(reintentos + 1):
        extra = f"\n\nTu respuesta anterior tenía estos errores: {'; '.join(errores)}" if errores else ""
        d = json.loads(cliente.json(SISTEMA_GUIONES, prompt + extra, SCHEMA_GUIONES, temperatura=0.6,
                                    imagenes=imagenes, audio=audio))
        errores = validar_guiones(d, n)
        if not errores:
            musica = str(d.get("musica") or "") if audio else ""
            return Guiones(
                titulo=str(d["titulo_serie"]).strip(),
                textos=[str(p["guion"]).strip() for p in d["partes"]],
                confianzas=[int(p.get("confianza") or 0) for p in d["partes"]],
                sensible=bool(d.get("sensible")),
                musica=musica if musica in ("ninguna", "de_fondo", "cancion") else "",
                cancion=str(d.get("cancion") or "").strip() if musica == "cancion" else "")
    raise NarrarError("Gemini no escribió guiones válidos: " + "; ".join(errores))
