# Costo de Gemini si se paga el modelo principal

Calculado el 2026-09-28. **No hay nada pago activado**: esto es solo el número.

## Cuántas llamadas por día

Medido en la Pi (archivos que deja cada clip procesado, 25 al 27/09): **11 a 15 clips por día**
llevan textos de Gemini, entre la corrida de las 05:00 y los `/buscar` (32 búsquedas en 4 días).
Sumando lo nuevo:

| Llamadas/día | Qué | Tokens de entrada / salida por llamada |
|---:|---|---|
| 20 | Textos de clips (05:00 + /buscar + /ya), con reintentos | 2.500 / 350 (4 frames + transcripción) |
| 2 | Desempates y verificación del multi-POV | 2.000 / 200 |
| 3 | Modo en vivo (solo la carpeta Argentinos) | 2.500 / 350 |
| 1 | Pequeña Historia: elegir el hecho | 5.000 / 600 |
| 3 | Pequeña Historia: guion (con reintentos y algún ✏️) | 8.000 / 1.000 (artículo + 12 fotos) |
| 1 | /narrar y /serie (promedio, ~2 por semana) | 6.000 / 1.000 |
| **30** | **total de texto** | **~96.000 / ~13.000 por día** |
| 1 | Voz de Pequeña Historia (Gemini TTS) | ~45 s de audio |

Por eso la cuota gratis (~20 por día) se agota casi todos los días y el bot cae al modelo de
fallback (flash-lite).

## Cuánto costaría

Precios del plan pago (página oficial de precios de la API de Gemini, 2026-09-28):

- gemini-3.6-flash: US$0,75 por millón de tokens de entrada y US$3,75 de salida **hasta el
  31/12/2026**; desde el 1/1/2027, el doble (US$1,50 y US$7,50).
- Gemini Flash TTS: US$0,00225 cada 10 s de audio hasta fin de 2026; el doble desde 2027.

| | Por día | **Por mes** | Con margen ×2 |
|---|---:|---:|---:|
| Hasta dic. 2026 | US$0,13 | **≈ US$4** | ≈ US$8 |
| Desde ene. 2027 | US$0,26 | **≈ US$8** | ≈ US$16 |

La voz de Pequeña Historia es ≈ US$0,30 por mes (0,60 desde 2027): casi todo el costo es texto.

## Lo que no está medido

- Los tokens por imagen: la página de precios no los da para estos modelos; se tomó ~258 por
  frame chico (el conteo habitual de Gemini). Por eso el margen ×2.
- Cuánto se usa `/buscar` depende de vos: cada búsqueda son hasta 3 llamadas.
- Con el plan pago desaparece el tope de ~20 por día y no haría falta el fallback a flash-lite
  (que además juzga peor las imágenes: se vio con las fotos de las efemérides).
