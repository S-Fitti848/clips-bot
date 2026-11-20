# PENDIENTES

Lista corta de lo que está en curso. El detalle y la historia van en CLAUDE.md (§1, §9, §10).
Se actualiza al terminar cada tarea.

## PLAN DE ASÍ NACIÓ hasta el 15/12 (Santi, 2026-11-20)

Este mes es para dejar el motor perfecto; el **15/12 arranca la producción**. Así Nació sigue pausado hasta entonces.
Pruebas con un tope de **US$ 1 por día** aparte de la producción (`claude.TOPE_PRUEBAS_DIA`; al llegar, frena hasta el
día siguiente y avisa en una línea); render local siempre que se pueda. **Lunes a las 10:00: 5 líneas a Santi de cómo
vamos** (tarea programada `asinacio-plan-lunes`).

| semana | meta | estado |
|---|---|---|
| 20/11 – 22/11 | manos y apretón | en curso: manos nuevas (v1.46.0) en todos lados; Pepsi tito5 18/19 (US$ 0,04); laboratorio, firma y apretón de cerca rehechos, hoja mandada el 20/11. Falta: OK de Santi a la hoja → video completo con la voz de Tito |
| 23/11 – 29/11 | escenas que faltan y expresiones | |
| 30/11 – 06/12 | gancho y viaje al pasado | |
| 07/12 – 10/12 | prueba final con 10 marcas | |
| **10/12** | **decisión**: si 8 de 10 pasan 15/19 con menos de US$ 0,60 por video, queda listo para el 15/12 | |

## Pequeña Historia: tecnología todos los días (2026-11-20)

- [x] El 20/11 el de tecnología (Windows 1.0) SÍ se armó y se mandó a las 04:26, pero retenido por el estándar: la
      revisión final tomó como "foto borrosa / de otra cosa" una tarjeta «MELAZA» (clave de otra frase). Arreglado: las
      tarjetas de la revisión usan solo la clave de su frase o el año y no se juzgan como foto (PH-02/PH-12).
- [x] Orden: hechos del día → banco → recién ahí el mínimo de fotos relajado; los reintentos no arrancan después de las
      16:30 (llega para aprobar antes de las 18:00).
- [ ] Mirar el 21/11 que llegue a la madrugada y que no quede retenido por una tarjeta.

## Pequeña Historia: fotos después del Short de Colón (2026-11-17, v1.33.0)

- [x] No se publica sola (`efemerides.publicar_sola: false`): todo llega con ✅ Publicar / ❌ Cancelar.
- [x] Reglas de fotos (políticos, retratos sin nombrar, foto = su frase, nitidez y 800 px, año real) y revisión del
      video terminado que frena (PH-02, PH-10 a PH-13, PH-25).
- [x] YouTube a privado (2026-11-18): Colón, Ambato, Santiago de Cuba, Banfield, La Pola, Túpac Katari, Morelia,
      Colonia Alberdi y Sor Juana (CDMX no tiene YouTube). Intel y Half-Life quedan (Santi).
- [x] Facebook: la API no deja ocultar un Reel; los 10 los oculta Santi desde Meta Business Suite (2026-11-18).
- [ ] Mirar los primeros videos con las reglas nuevas (18/11, madrugada): cuántas fotos saca el filtro de personas y
      el de nitidez, cuántas tarjetas de más, y si la revisión del video terminado frena de más.

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

## Estándar de calidad (`ESTANDAR_CALIDAD.md`, `clips_bot/calidad.py`)

- [x] 2026-11-17: personajes por rol y época, todos trabajando, línea de producción, fondos de época, ficha por escena,
      Tito sin tapar (AN-15 a AN-19, AN-26; mínimo = como mucho 2 reglas sin cumplir). Hoja del Hershey mandada a Santi.
- [ ] Mirar los primeros videos con esto (18/11): ropa y trabajo por rol, que la revisión use la ficha y marque lo que
      no es de época (la máquina violeta guardada, por ejemplo).
- [x] 2026-11-17: nada tapa el texto grande ni los subtítulos (AN-27); la caja violeta era una receta sin su dibujo;
      piezas guardadas con año y descripciones limpias. Mínimo 17/19 confirmado por Santi.
- [x] 2026-11-17: Así Nació único (AN-25 con la escena entera), lugares nuevos que se crean y guardan, rescate antes de
      retener, /costos con piezas nuevas por video y aviso desde US$ 1,50.
- [ ] Mirar el primer video con un `lugar_nuevo` real: que el lugar se lea y que los personajes queden bien parados.

- [x] 2026-11-16: documento con las reglas de Así Nació (AN-01…AN-24) y Pequeña Historia (PH-01…PH-23); la revisión
      puntúa cada video, corrige sola y lo que quede va en el mensaje (📏); registro en `calidad_fallas`.
- [ ] Mirar los primeros mensajes con 📏 (17/11): que la revisión puntúe todas las reglas y no invente fallas.
- [ ] Lunes 23/11, 09:30: primer resumen semanal del estándar a Santi (`_calidad_semana_tick`).
- [x] 2026-11-16: reemplazo por escena aprobada de la biblioteca después de las 2 vueltas (Haiku con 3 cuadros,
      empalme sin mover nada, tope US$ 0,50, la regla sin arreglo va primera en las mejoras).
- [ ] La biblioteca de escenas aprobadas arranca VACÍA (`data/animacion/escenas_estandar.json`): mirar que se llene con
      los primeros videos y el primer reemplazo real (línea 🔁 en el mensaje).
- [ ] Cada regla nueva que apruebe Santi → sumarla al documento con el próximo número libre.
- [x] 2026-11-17 (Frisbee): la revisión mira cada escena (no el reloj del viaje), rechaza manos vacías y lugares que
      no son los de la historia; sin ventanas flotando; regla AN-25 (videos únicos, lugares reales); playa, estadio y
      cocina nuevos.
- [ ] Mirar los videos del 18/11: que las escenas salgan en los lugares de la historia y que la revisión marque cada una.

## Publicación de comunidad (`comunidad_fb.py`)

- [x] 2026-11-17: la de Colón salió con la foto de los presidentes del Mercosur; borrada de la página.
- [x] 2026-11-17: la foto la mira Claude contra el texto (PH-24); sin foto, la otra historia; sin ninguna, no sale y aviso.
- [ ] 18/11 13:00: mirar la primera publicación (o el aviso de que no salió). Si muchos días no sale, buscar fotos
      también en Commons por el tema (hoy solo el artículo, y a veces es el del país).

## Latinoamérica: prueba de fuentes web (`web_historias.py`, `historias_fb.web`)

- [ ] 17/11: primer día de producción con búsqueda web. Al terminar el día, `_web_latam_tick` mide el costo: hasta
      `web_tope_usd` (0,45) queda andando y avisa; si se pasa, se apaga sola (`bot_estado.web_latam_apagado`).
      Revisar el aviso y, si queda andando, proponer lo mismo para tecnología y Así Nació.

## Mejoras al motor de Así Nació (jueves 19/11, `_mejoras_motor_tick`)

- [ ] Llegan solas lunes y jueves desde las 10:00; las pedidas por Santi encabezan el mensaje
      (`bot_estado.mejoras_pedidas`). Ya hechas en v1.22.0-v1.23.0: uso real con las manos, manos con detalle,
      inspiración animada. Quedan del 16/11: el remolino del viaje en el tiempo deforma las caras.
- [ ] Esperar qué aprueba Santi y programarlo.
