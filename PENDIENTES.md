# PENDIENTES

Lista corta de lo que está en curso. El detalle y la historia van en CLAUDE.md (§1, §9, §10).
Se actualiza al terminar cada tarea.

## Así Nació: escenas de uso, inspiración, apretón y firma (`animacion.uso_manos`, `uso_v3.py`)

- [x] Escena 7, apretón (2026-11-16, noche): plano medio con las dos personas cerca, detrás de la mesa con el
      contrato grande, y los brazos calculados para que las manos se junten justo en el medio
      (`per.brazo_hacia`, gestos `brazo_der:H:C` / `brazo_izq:H:C`); primer plano con el dibujo nuevo `apreton`
      (de costado: palma contra palma, los dedos envolviendo, los pulgares cruzados arriba) y 2-3 sacudidas.
      Hoja mandada a Santi (`output/animacion/prueba_apreton_v5/hoja_escena_7.jpg` en la Pi).
- [x] `uso_manos` PRENDIDO para todos desde el video del 17/11 a las 07:00 (Santi lo revisa con ❌ Cancelar).
- [ ] Mirar el primer video real con uso_manos (17/11, 13:00) y anotar lo que salga flojo (uso, inspiración,
      firma, contar billetes, caja). Si Santi cancela, ver por qué.
- [ ] Visto en la hoja, sin arreglar: la escena 7 del Tupper de prueba arranca con el cuadro del viaje en el tiempo
      (el reloj con "2026") en sus primeras décimas; es del motor de antes, no del apretón.

## Latinoamérica: prueba de fuentes web (`web_historias.py`, `historias_fb.web`)

- [ ] 17/11: primer día de producción con búsqueda web. Al terminar el día, `_web_latam_tick` mide el costo: hasta
      `web_tope_usd` (0,45) queda andando y avisa; si se pasa, se apaga sola (`bot_estado.web_latam_apagado`).
      Revisar el aviso y, si queda andando, proponer lo mismo para tecnología y Así Nació.

## Mejoras al motor de Así Nació (jueves 19/11, `_mejoras_motor_tick`)

- [ ] Llegan solas lunes y jueves desde las 10:00; las pedidas por Santi encabezan el mensaje
      (`bot_estado.mejoras_pedidas`). Ya hechas en v1.22.0-v1.23.0: uso real con las manos, manos con detalle,
      inspiración animada. Quedan del 16/11: el remolino del viaje en el tiempo deforma las caras.
- [ ] Esperar qué aprueba Santi y programarlo.
