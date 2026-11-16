"""Reglas fijas que valen para TODOS los guiones con voz (decisión de Santi, 2026-09-28).

Efemérides, /narrar y /serie las meten tal cual en su prompt de sistema; hay un test que falla si
algún prompt deja de incluirlas. Si se cambian, cambian para todos a la vez.
"""

# Pedido 2026-09-28: el guion de Fleming decía que descubrió la penicilina, pero no quedaba claro
# que el moho mataba a las bacterias ni por qué eso lo volvía un remedio.
REGLAS_CLARIDAD = """
QUE SE ENTIENDA (regla fija, vale más que meter datos):
- Escribí para un chico de 15 años que no sabe nada del tema. Explicá el CÓMO y el PORQUÉ,
  paso a paso: qué pasó, cómo funciona y por qué importa.
- No des nada técnico por sabido: si aparece una palabra técnica (bacteria, órbita, antibiótico,
  jeroglífico), explicala en pocas palabras la primera vez que la decís, o usá una palabra común.
- Una idea por frase y en orden de causa a efecto. Conectá las frases ("entonces", "por eso",
  "así que") para que se siga el hilo.
- Menos datos si hace falta, pero que se entienda: mejor una fecha o un nombre menos que alguien
  que se queda sin entender qué pasó.
- Al terminar, el que escucha tiene que poder contar con sus palabras qué pasó y por qué importa.
  Ejemplo: si alguien descubre que un moho mata bacterias, decí que el moho MATABA a las bacterias
  y que POR ESO sirve como remedio.
"""

# Ganchos concretos (Santi, 2026-11-16; Pequeña Historia y Así Nació): nada de fórmulas genéricas de intriga. El gancho
# dice el DATO concreto más fuerte de la historia.
REGLA_GANCHO_CONCRETO = """
GANCHO CONCRETO (regla fija): el gancho dice el DATO concreto más fuerte de ESTA historia. Prohibidas las frases
genéricas de intriga: "pasó algo que no esperaban", "nadie lo podía creer", "lo que pasó después te va a
sorprender", "no vas a creer lo que pasó", "algo increíble", "nadie se lo esperaba", "lo que nadie sabía". MAL:
"Fusilaron a una joven por espía, y pasó algo que no esperaban". BIEN: "La fusilaron a los 22 y antes gritó una frase
que todavía se recuerda".
"""

import re as _re
import unicodedata as _ud

_GENERICAS = _re.compile(
    r"\b(?:"
    r"(?:paso|ocurrio|sucedio|hubo) algo (?:que )?(?:nadie |no )?(?:se )?(?:esperaba|esperaban|imaginaba|imaginaban)"
    r"|algo (?:que )?nadie (?:se )?(?:esperaba|imaginaba)"
    r"|nadie (?:lo |se lo )?(?:podia|pudo|iba a|puede|va a) creer"
    r"|nadie (?:se )?lo (?:esperaba|esperaria)|nadie se (?:lo )?esperaba"
    r"|te va a sorprender|te vas a sorprender|no (?:lo )?vas a creer|no vas a poder creer"
    r"|lo que (?:paso|vino|sucedio|ocurrio) (?:despues|luego)"
    r"|lo que nadie sabia|algo increible|algo inesperado|algo sorprendente|una historia increible"
    r"|no te (?:imaginas|vas a imaginar) (?:lo que|como)"
    r")\b")


def _sin_tildes(t: str) -> str:
    t = _ud.normalize("NFKD", str(t or "").lower())
    return "".join(ch for ch in t if not _ud.combining(ch))


def gancho_generico(texto: str) -> str | None:
    """La fórmula genérica de intriga que tiene el gancho, o None (Santi, 2026-11-16)."""
    m = _GENERICAS.search(_sin_tildes(texto))
    return m.group(0) if m else None
