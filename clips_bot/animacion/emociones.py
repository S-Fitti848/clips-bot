"""Expresiones según el momento de la historia (Santi, 2026-11-20, para todos los personajes y escenas).

El guion marca la `emocion` de cada frase y el motor elige la cara y el cuerpo:

    exito        muy feliz: sonrisa grande, brazos arriba, saltando
    perdida      triste o devastado: cabeza baja, manos en la cara
    determinado  ceño firme, puños cerrados, mirando adelante, arremangándose (la escena después de una pérdida)
    idea         sorprendido: ojos grandes, boca abierta, la lamparita
    trabajo      concentrado: la mirada fija en lo que hace
    duda         preocupado: ceño fruncido, rascándose la cabeza
    burla        los demás se ríen o niegan con la cabeza; el protagonista, frustrado
    neutral      la cara que trae la escena

Sin `emocion` en el guion, sale de la frase (palabras como "quiebra", "millones", "se le ocurrió") y si no, de la escena
de la biblioteca (crisis → perdida, éxito → exito, fábrica → trabajo…).

El CUERPO solo se cambia en quien tiene las manos libres (de frente): el que está de perfil trabajando con el producto
en las manos lo sigue haciendo y cambia solo la cara (así no se suelta lo que tiene agarrado).
"""
from __future__ import annotations

import re

EMOCIONES = ("exito", "perdida", "determinado", "idea", "trabajo", "duda", "burla", "neutral")

CARA = {"exito": "euforico", "perdida": "devastado", "determinado": "determinado", "idea": "sorprendido",
        "trabajo": "concentrado", "duda": "preocupado", "burla": "frustrado"}

# (gesto a, gesto b, cada cuántos segundos alterna, salta)
CUERPO = {"exito": ("festejar", "festejar_b", 0.28, True), "perdida": ("cara_manos", "cara_manos_b", 0.7, False),
          "determinado": ("punos", "arremangar", 0.6, False), "idea": ("sorpresa", "sorpresa", 1.0, False),
          "duda": ("rascar", "rascar_b", 0.35, False), "burla": ("brazos_cruzados", "brazos_cruzados", 1.0, False)}

POR_ACCION = {"crisis": "perdida", "exito_multitud": "exito", "fabrica_produce": "trabajo", "taller_inventor": "idea",
              "lanzamiento": "exito", "armar_mesa": "trabajo"}

_PALABRAS = (
    ("burla", r"se (burlaron|re[ií]an)|burla|rechaz|nadie (le )?cre|se rieron|lo echaron|le dijeron que no"),
    ("perdida", r"quiebr|banca?rrot|fracas|perdi[óo]|deudas?\b|cerr[óo]|nadie (lo )?compr|no se vend|ruina|fundi"),
    ("determinado", r"no se rindi|volvi[óo] a|insisti|otra vez|de nuevo|empez[óo] de cero|sigui[óo] adelante"),
    ("exito", r"millones|[ée]xito|furor|r[ée]cord|agot|todos lo quer|vendi[óo] (miles|millones)|se hizo famos"),
    ("idea", r"se le ocurri|idea|descubri|invent[óo]|se dio cuenta|naci[óo] la"),
    ("duda", r"\bdud|problema|no sab[ií]a|preocup|c[óo]mo hacer|no funcionaba"),
)


def de_escena(spec: dict) -> str:
    """La emoción de la escena: la del guion si es válida; si no, la de la frase; si no, la de la escena base."""
    e = str(spec.get("emocion") or "").strip().lower()
    if e in EMOCIONES:
        return e
    frase = str(spec.get("frase") or "")
    for emo, rx in _PALABRAS:
        if re.search(rx, frase, re.I):
            return emo
    return POR_ACCION.get(str(spec.get("accion_escena") or ""), "neutral")


def _alternar(a: str, b: str, dur: float, paso: float, t0: float = 0.0) -> list[dict]:
    out, t, k = [{"t": round(t0, 3), "gesto": a}], t0 + paso, 1
    while t < dur:
        out.append({"t": round(t, 3), "gesto": b if k % 2 else a})
        t += paso
        k += 1
    return out


def manos_libres(el: dict) -> bool:
    """De frente y sin el producto agarrado (los de perfil trabajan con lo suyo en las manos)."""
    return not el.get("perfil") and not el.get("lleva") and not el.get("_sostiene")


def aplicar(actores: list[dict], emocion: str, dur: float, elementos: list[dict] | None = None,
            lamparita=None) -> list[dict]:
    """Cambia la cara (y el cuerpo, si tiene las manos libres) del protagonista (el primer actor) según la emoción; en
    una burla, los demás se ríen y niegan. Devuelve los elementos a sumar (la lamparita de la idea)."""
    gente = [a for a in actores if a.get("tipo") == "personaje" and not a.get("multitud")]
    if not gente or emocion not in CARA:
        return []
    prota, otros = gente[0], gente[1:]
    nuevos = []
    if emocion == "idea":           # concentrado → ¡la idea!
        t_i = round(dur * 0.45, 2)
        prota["caras"] = [{"t": 0, "cara": "concentrado"}, {"t": t_i, "cara": "sorprendido"}]
        if lamparita and not any(el.get("nombre") == "lamparita" for el in (elementos or [])):
            nuevos.append(lamparita(prota, t_i))
    else:
        prota["caras"] = [{"t": 0, "cara": CARA[emocion]}]
    prota["cara"] = prota["caras"][-1]["cara"]
    if emocion in CUERPO and manos_libres(prota):
        a, b, paso, salta = CUERPO[emocion]
        prota["gestos"] = _alternar(a, b, dur, paso)
        if salta:
            y0 = float(prota.get("y", 0))
            kf, t, k = [], 0.0, 0
            while t <= dur:
                kf.append({"t": round(t, 3), "y": y0 - (34 if k % 2 else 0), "easing": "suave"})
                t += paso
                k += 1
            prota["keyframes"] = [x for x in prota.get("keyframes", []) if "y" not in x] + kf
    if emocion == "burla":
        for o in otros:
            o["caras"] = [{"t": 0, "cara": "risa"}]
            o["cara"] = "risa"
            if manos_libres(o):
                o["gestos"] = _alternar("reirse_senalar", "negar_a", dur, 0.4) if o is otros[0] else \
                    _alternar("negar_a", "negar_b", dur, 0.3)
    elif emocion == "exito":
        for o in otros:
            o["caras"] = [{"t": 0, "cara": "feliz"}]
            o["cara"] = "feliz"
    elif emocion == "perdida":
        for o in otros:
            o["caras"] = [{"t": 0, "cara": "triste"}]
            o["cara"] = "triste"
    return nuevos
