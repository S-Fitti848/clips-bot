# Estándar de calidad

El estándar fijo para TODOS los videos de Así Nació y de Pequeña Historia (Santi, 2026-11-16). Junta las reglas que
fuimos aprobando (el detalle y la historia de cada una están en CLAUDE.md §1).

Cómo se usa (`clips_bot/calidad.py`):

1. Antes de publicar, la revisión (Claude, mirando los cuadros del video o la hoja de fotos) puntúa cada video contra
   las reglas marcadas **revisión** y corrige sola lo que no pasa (con el `arreglo` de la regla).
2. Así Nació, después de las 2 vueltas (Santi, 2026-11-16; `animacion/reemplazo.py`): una escena que sigue sin pasar
   se reemplaza SOLO a ella por una de la **biblioteca de escenas aprobadas** (las que pasaron el estándar en otros
   videos, `data/animacion/escenas_estandar.json`), adaptada a esa frase (mismo protagonista, los mismos personajes,
   lugar, época y luz), sin dibujos nuevos. Cada candidata la mira Haiku con 3 cuadros. El empalme no mueve nada:
   misma duración, la misma transición, la voz y los subtítulos intactos, y el resto del video igual (un solo render
   al final). Si ninguna pasa, el aviso y esa regla va PRIMERA en las mejoras al motor de la semana. Tope: si las
   correcciones de un video pasan de US$ 0,50, se frena y el mensaje lo dice.
3. Si después de corregir algo sigue sin cumplirse, el video sale igual y el mensaje dice qué regla no cumplió
   ("📏 Estándar 12/14 · ❌ AN-05 …"). Las reglas marcadas **código** las chequea el código (validación del guion,
   fotos, audio); si una no se cumple, también va en el mensaje.
4. **Mínimo para publicarse sola (Santi, 2026-11-17):** si después de las correcciones el video queda debajo de
   **12/14** (Así Nació, desde el 17/11; antes 11) o **7/9** (Pequeña Historia), NO se programa: le llega a Santi con ✅ Publicar igual /
   ❌ Cancelar y, si no responde, no sale (`calidad.MINIMO_PUBLICAR`, `retener`). El aviso solo alcanza con 1 o 2
   reglas sin cumplir.
5. Cada regla nueva que apruebe Santi se suma ACÁ, con el próximo número libre de su canal. El código lee este archivo:
   una regla nueva de revisión entra en la próxima revisión sin tocar nada más.
6. Cada falla queda anotada (tabla `calidad_fallas`) y los lunes desde las 09:30 le llega a Santi qué reglas fallaron
   más en la semana, para mejorar el motor (Santi no revisa video por video).

Formato de cada regla (lo lee el código; no cambiarlo):
`- **ID** · revisión|código · arreglo: <arreglo> — texto` (el arreglo solo en las de revisión).

## Así Nació

Arreglos: `rehacer_gancho` (prueba otra opción de gancho o lo reescribe), `cambiar_accion` (reescribe esa escena),
`redibujar_objeto`, `mover_objeto`, `separar_personajes`, `sacar_objeto`, `sacar_texto`, `otro`.

- **AN-01** · revisión · arreglo: rehacer_gancho — GANCHO que frena el dedo: los primeros 3 s son la imagen imposible del producto (gigante, explotando, multiplicado, volando o una multitud peleándose por él), con el producto reconocible y a la vista y colores fuertes. Nunca un escenario vacío, gente parada, el objeto girando solo ni un arranque parecido a uno anterior del canal.
- **AN-02** · revisión · arreglo: cambiar_accion — LO QUE SE VE ES LO QUE DICE LA VOZ: cada escena muestra la acción concreta de su frase (si dice que lo arma, se ve armándolo); festejar solo si la frase habla de un éxito.
- **AN-03** · revisión · arreglo: cambiar_accion — SE ENTIENDE SIN LA VOZ: cada escena se lee de un vistazo (1 segundo), con los elementos que la hacen reconocible (la lata de pintura con su pincel, el contrato sobre la mesa).
- **AN-04** · revisión · arreglo: cambiar_accion — PRODUCTO EN USO en la mayoría de las escenas (el Tupper guardando comida, el Play-Doh amasado, el cubo resuelto), aunque la voz hable de otra cosa.
- **AN-05** · revisión · arreglo: cambiar_accion — NADIE PARADO SIN HACER NADA (brazos abajo, quieto, mirando). Dos personas hablando, solo si la frase cuenta una charla, y como mucho 2 escenas.
- **AN-06** · revisión · arreglo: cambiar_accion — MANOS QUE TOCAN EL OBJETO: el objeto en la mano o apoyado sobre algo, nunca cerca de una mano sin agarrarlo; las manos hacen algo que se lee en 1 segundo (agarrar, abrir, guardar, contar, firmar, dar). Los primeros planos encuadran las manos con el objeto, no cortan caras. Manos levantadas, vacías o que no tocan nada = no cumple (Frisbee, 2026-11-17).
- **AN-07** · revisión · arreglo: cambiar_accion — NADA FLOTANDO sin motivo (valen los íconos de dibujo animado, la lluvia de billetes, algo que alguien tiró y el gancho, que flota a propósito). El producto flotando o girando, como mucho 2 veces y solo si la frase lo justifica.
- **AN-08** · revisión · arreglo: otro — ÉPOCA: nada aparece antes de existir (ni un monitor en 1974 ni un celular en 1950); cada escena con la decoración de su año; los personajes fieles a la persona real (género, edad, ropa de la época).
- **AN-09** · revisión · arreglo: redibujar_objeto — DETALLE SEGÚN EL GUION: cada dibujo tiene los detalles que describe el guion y se reconoce sin leer; nada de siluetas negras, etiquetas en blanco ni cajas con un rótulo.
- **AN-10** · revisión · arreglo: cambiar_accion — LA PLATA CON ACCIONES REALES (contar billetes, abrir la caja registradora, un apretón de manos, firmar); nunca monedas con $ ni bolsas de plata gigantes en las manos.
- **AN-11** · revisión · arreglo: sacar_texto — TEXTOS QUE NO SE PISAN: un solo texto grande a la vez, nada que ya diga el subtítulo, la misma cifra o año no se repite, ningún texto cortado o ilegible.
- **AN-12** · revisión · arreglo: separar_personajes — COMPOSICIÓN: ningún brazo u objeto sobre una cara, nadie tapado por un mueble u otro personaje, cada objeto en un lugar lógico (nada de una pelota sobre un sombrero).
- **AN-13** · revisión · arreglo: cambiar_accion — LUGAR DE LA HISTORIA REAL Y DECORADO CON SENTIDO: el lugar de cada escena es donde pasó esa parte de la historia (playa, fábrica, tienda, estadio, cocina…), no un living o un taller genéricos (una playa no es un puerto); el decorado tiene que ver con la historia (nada de decoración sin relación ni ventanas o cuadros flotando).
- **AN-14** · revisión · arreglo: cambiar_accion — ACCIONES ESPECÍFICAS: martillo o engranajes solo si la frase habla de un taller o una máquina; fabricar = las manos trabajando sobre el objeto.
- **AN-20** · código — DATOS VERDADEROS: todo dato está en el artículo de la fuente (es lo único que frena un video, junto con los temas sensibles).
- **AN-21** · código — GUION: gancho con el dato concreto (nada de "pasó algo que no esperaban"), empresa o persona presentada la primera vez, orden problema → idea → qué pasó → final sorpresa, al menos 3 lugares y 3 roles distintos.
- **AN-22** · código — DURACIÓN Y VOZ: 32-38 s; la voz se ajusta como mucho ±8 % sin cambiar el tono, si no se reescribe el guion.
- **AN-23** · código — AUDIO: nada arriba de −3 dB, fade in y fade out, el audio termina con el video.
- **AN-25** · código — CADA VIDEO ÚNICO EN ESCENAS (Santi, 2026-11-17): como mucho un tercio de las escenas (acción y lugar) se repite de los últimos 10 videos, y solo si el contexto lo pide; vale también para el reemplazo de escenas de la biblioteca. Si la frase dice dónde pasó (playa, estadio, cocina, fábrica, tienda…), la escena va en ese lugar.
- **AN-24** · código — MARCA DEL CANAL: viaje al pasado (reloj, cuentakilómetros, remolino, sepia) cuando cambia la época; en el pasado todo sepia menos el producto; subtítulos virales en la franja de arriba.

## Pequeña Historia

Arreglos: `cambiar_foto` (pasa a la siguiente foto que sirve para esa frase), `otro` (solo se avisa).

- **PH-01** · revisión · arreglo: cambiar_foto — GANCHO: la primera frase dice el dato concreto más fuerte (sin fecha, sin "Un día como hoy", nada de fórmulas genéricas) y la primera foto es la más impactante (una cara clara del protagonista, si hay).
- **PH-02** · revisión · arreglo: cambiar_foto — CADA FOTO MUESTRA LO QUE DICE SU FRASE (o el tema directo del hecho); en las frases centrales, fotos reales del hecho o del lugar.
- **PH-03** · revisión · arreglo: cambiar_foto — FOTOS DE ÉPOCA: nada moderno en una frase del pasado (un avión de 2008 en una historia de 1940).
- **PH-04** · revisión · arreglo: cambiar_foto — FOTOS QUE SIRVEN: nada de capturas, apps, documentos, planillas, gráficos, mapas o logos salvo que la frase hable de eso; nada con texto en otro idioma que no sea castellano o inglés.
- **PH-05** · revisión · arreglo: cambiar_foto — NINGUNA FOTO CONTRADICE SU FRASE (un gráfico en picada cuando la frase dice que subió).
- **PH-06** · revisión · arreglo: cambiar_foto — NADA DURO NI FALSO: sin cadáveres ni heridos, sin imágenes generadas con IA; una escena ilustrativa solo si no confunde (nunca una cara que pase por el protagonista, otro lugar o algo moderno).
- **PH-07** · revisión · arreglo: otro — SE ENTIENDE: el cómo y el porqué paso a paso, para un chico de 15 años, sin nada técnico dado por sabido.
- **PH-08** · revisión · arreglo: otro — ESTRUCTURA: gancho → la 2.ª frase suma intriga → el año (y el lugar) en la 3.ª o 4.ª → tensión → un giro a la mitad que renueva la intriga → la anteúltima paga el gancho → la última es una pregunta corta al público sobre esa historia.
- **PH-09** · revisión · arreglo: otro — FICCIÓN Y TONO: nunca la trama de una ficción (cultura pop solo desde la vida real); humor suave solo si la historia lo permite, nunca en muertes, tragedias ni temas sensibles.
- **PH-20** · código — DATOS VERDADEROS: todo nombre, cifra y fecha está en el artículo; en Latinoamérica, cada dato en 2 fuentes de sitios distintos.
- **PH-21** · código — FOTOS: al menos 6 distintas (4 de época como mínimo), ninguna más de 6 s seguidos (4 s en el corto), ninguna en más de 2 cortes, y 70 % o más del tiempo con fotos reales (no tarjetas).
- **PH-22** · código — AUDIO LIMPIO: fade in 0,1 s y fade out 0,5 s, nada arriba de −3 dB, el audio termina con el video.
- **PH-24** · código — PUBLICACIÓN DE COMUNIDAD (Santi, 2026-11-17, la de Colón con los presidentes del Mercosur): antes de programarla, Claude mira las fotos candidatas contra el texto de la historia (`comunidad_fb.foto_que_coincide`): solo una que muestre la persona, el hecho, el objeto, el club o el lugar puntual donde pasó; nunca políticos ni actos de gobierno salvo que la historia sea de esa persona; nunca mapas, logos ni capturas. Si ninguna coincide, se prueba la otra historia del día; si tampoco, ese día no sale y se le avisa a Santi.
- **PH-23** · código — DURACIÓN Y TEMA: tecnología 20-30 s, Latinoamérica 30-40 s; nada fuera de los temas del canal; Latinoamérica con 8 o más de puntaje (7 para una por día).
