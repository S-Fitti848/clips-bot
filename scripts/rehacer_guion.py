"""Rehace SOLO el guion de una historia de Latinoamérica con las reglas de hoy, sin fotos, voz ni video, y le pasa el
control de comprensión (PH-27) al guion viejo y al nuevo para compararlos (Santi, 2026-11-27, el de Sixto Rodríguez).

Uso (en la Pi, gasta Claude real: ~US$ 0,15):
  CLIPS_CLAUDE_REAL=1 PYTHONPATH=. .venv/bin/python scripts/rehacer_guion.py <estado.json> <lugar>
"""

import json
import sys
from pathlib import Path

import clips_bot.__main__ as m
from clips_bot import efemerides as ef
from clips_bot import gemini, locales
from clips_bot.config import load_settings


def main() -> int:
    import logging

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    estado = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    lugar = sys.argv[2]
    p = estado["propuesta"]
    e = ef.Evento(**p["evento"])
    settings = load_settings()
    gemini.fijar_origen(gemini.PRUEBA)
    sonnet, haiku = m._claude_textos(settings)
    viejo = p["guion"]
    print("=== ANTES:", viejo.get("titulo"))
    for i, f in enumerate(viejo["frases"]):
        print(f"  {i + 1}. {f}")
    ef.comprension(haiku, viejo["frases"], viejo.get("idea_clave") or "", avisar=print)
    fuente = ef.texto_fuente(ef.Wiki(), e)
    contexto = f"Lugar: {lugar}."
    g = ef.escribir_guion(sonnet, e, fuente, sistema=locales.SISTEMA_GUION_CORTO,
                          validar_extra=locales.validar_lugar(lugar, True), contexto=contexto, corto=True,
                          rango=ef.LATAM_PALABRAS, max_s=ef.LATAM_MAX_S, respaldo=contexto, lector=haiku)
    print("\n=== DESPUÉS:", g.titulo)
    for i, f in enumerate(g.frases):
        print(f"  {i + 1}. {f}")
    print("idea clave:", g.idea_clave)
    ef.comprension(haiku, g.frases, g.idea_clave, avisar=print)
    return 0


if __name__ == "__main__":
    sys.exit(main())
