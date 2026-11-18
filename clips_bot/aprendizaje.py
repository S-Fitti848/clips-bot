"""Lo que retiene, aplicado solo a los próximos videos (Santi, 2026-11-18: "las estadísticas de 24 h no me las mandes:
usalas vos para mejorar los videos (qué ganchos, temas y escenas retienen más) y aplicalo a los próximos").

- `lecciones(medidos, canales)`: de los Reels medidos a las 24 h (stats_fb, `bot_estado.fb_reels_24h`), los ganchos y temas
  que más retienen (los que más pasan los 3 s y siguen en el segundo 10) y los que menos, con lo más flojo de la revisión
  en Así Nació. Queda en `data/lecciones.json` y entra en el prompt del guion de cada canal (`para_prompt`).
- `resumen_semana(...)`: el resumen de los lunes a Santi, 5 líneas: qué cambió y cómo vienen las vistas.
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from .config import DATA_DIR

log = logging.getLogger(__name__)

ARCHIVO = DATA_DIR / "lecciones.json"
CANALES = {"pequena_historia": ("facebook",), "asinacio": ("facebook_asinacio",)}
MIN_MEDIDOS = 4         # con menos Reels medidos no hay nada que aprender todavía
CUANTOS = 3


def _puntaje(x: dict) -> float:
    """Cuánto retiene: lo que pasa los 3 s pesa más (ahí se va la mayoría), después el segundo 10 y el final."""
    a, b, c = (float(x.get(k) or 0) for k in ("pasa_3s", "ret_10", "ret_final"))
    return 0.5 * a + 0.3 * b + 0.2 * c


def lecciones(medidos: dict, canal: str) -> dict:
    fb = CANALES.get(canal, ())
    xs = [x for x in medidos.values() if x.get("canal") in fb and x.get("gancho")]
    if len(xs) < MIN_MEDIDOS:
        return {}
    xs.sort(key=_puntaje, reverse=True)
    def fila(x):
        return {"gancho": x.get("gancho", "")[:160], "titulo": x.get("titulo", "")[:100],
                "pasa_3s": x.get("pasa_3s"), "ret_10": x.get("ret_10"), "vistas": x.get("vistas"),
                "flojas": [f.get("que", "")[:120] for f in x.get("flojas") or []][:2]}
    return {"canal": canal, "n": len(xs), "mejores": [fila(x) for x in xs[:CUANTOS]],
            "peores": [fila(x) for x in xs[-CUANTOS:]], "actualizado": datetime.now().isoformat(timespec="minutes")}


def guardar(medidos: dict, archivo: Path | None = None) -> dict:
    archivo = archivo or ARCHIVO
    todo = {c: lecciones(medidos, c) for c in CANALES}
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as err:
        log.warning("lecciones: no pude guardarlas (%s)", err)
    return todo


def para_prompt(canal: str, archivo: Path | None = None) -> str:
    """El bloque para el prompt del guion: qué ganchos y temas retuvieron más y cuáles menos en este canal."""
    try:
        d = json.loads((archivo or ARCHIVO).read_text(encoding="utf-8")).get(canal) or {}
    except (OSError, ValueError):
        return ""
    if not d.get("mejores"):
        return ""
    def linea(x):
        return (f"- «{x['gancho']}» ({x['titulo']}): {x.get('pasa_3s') or '?'} % pasa los 3 s, "
                f"{x.get('ret_10') or '?'} % sigue en el segundo 10")
    txt = (f"\n\nLO QUE RETIENE EN ESTE CANAL (Reels medidos a las 24 h, {d['n']} hasta ahora; usalo para el gancho, el "
           "tema y las escenas de este video, sin copiar):\nLOS QUE MÁS RETUVIERON:\n" + "\n".join(map(linea, d["mejores"]))
           + "\nLOS QUE MENOS RETUVIERON (no hagas algo parecido):\n" + "\n".join(map(linea, d["peores"])))
    flojas = [f for x in d["peores"] for f in x.get("flojas") or []]
    if flojas:
        txt += "\nLo más flojo de esos según la revisión: " + " · ".join(flojas[:3])
    return txt


def resumen_semana(medidos: dict, cambios: list[str], hoy: datetime) -> str:
    """5 líneas: qué cambió y cómo vienen las vistas (mediana de reproducciones a las 24 h, esta semana contra la
    anterior, por canal)."""
    lunes = (hoy - timedelta(days=hoy.weekday())).date()
    desde, antes = lunes - timedelta(days=7), lunes - timedelta(days=14)

    def med(canales, a, b):
        vs = [x.get("vistas") or 0 for x in medidos.values() if x.get("canal") in canales
              and a.isoformat() <= str(x.get("publicado") or "")[:10] < b.isoformat()]
        return (round(statistics.median(vs)) if vs else None), len(vs)

    lineas = ["🔧 Claude Code: semana del " + f"{desde:%d/%m} al {(lunes - timedelta(days=1)):%d/%m}"]
    for nombre, canal in (("Pequeña Historia", "pequena_historia"), ("Así Nació", "asinacio")):
        ahora_, n = med(CANALES[canal], desde, lunes)
        prev, _ = med(CANALES[canal], antes, desde)
        if ahora_ is None:
            lineas.append(f"{nombre}: sin Reels medidos esta semana.")
        else:
            flecha = "" if prev is None else (" ↑" if ahora_ > prev else " ↓" if ahora_ < prev else " =")
            lineas.append(f"{nombre}: {n} Reels, mediana {ahora_:,} vistas a las 24 h"
                          .replace(",", ".") + (f" (antes {prev:,}{flecha})".replace(",", ".") if prev is not None else "") + ".")
    lineas.append("Cambié: " + ("; ".join(cambios[:3]) if cambios else "nada nuevo") + ".")
    lineas.append("Apliqué a los próximos lo que más retuvo (ganchos y temas) y dejé de lado lo que menos.")
    return "\n".join(lineas[:5])
