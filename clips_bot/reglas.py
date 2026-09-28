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
