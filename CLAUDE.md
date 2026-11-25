# Clips Bot — Project Context

**Snapshot:** 2026-11-25 | **Versión:** v1.61.0 (desplegado) | **Modo:** Fase 2: corriendo solo en la Pi. **Rots APAGADO. Así Nació PAUSADO desde el 19/11** (vuelve con 1 por día, preparado la noche anterior, si 4 de 5 marcas nuevas dan 15/19 o más por menos de US$ 0,60). **Pequeña Historia: TECNOLOGÍA ES LA PRIORIDAD NÚMERO UNO desde el 23/11** (2 por día en YouTube, 11:00 y 20:00, con una reserva de 3 videos ya armados; el canal de YouTube es solo de tecnología) y **Latinoamérica 2 por día SOLO en Facebook** hasta el 15/12. Nada se publica solo desde el 17/11: llega con ✅ Publicar / ❌ Cancelar y sin respuesta no sale. Todo al privado de Santi

> **SI ESTÁS EMPEZANDO UNA SESIÓN NUEVA, LEÉ §10.** Ahí está qué está hecho, qué quedó a medias,
> qué falta, y las trampas que ya nos mordieron.

> **Reglas de trabajo sobre este archivo:** se edita con Edit o se reescribe entero. NADA de scripts
> de reemplazo encadenados: uno rompió el archivo el 2026-09-22 (37 MB de texto repetido) y hubo que
> reconstruirlo desde el transcript. Ahora hay git: **commit después de cada cambio.**

---

## 0. QUÉ ES

Bot que cada día toma los mejores clips de un set fijo de streamers de Twitch y Kick, los convierte a
formato vertical 9:16 con subtítulos, y los entrega para publicar en un canal de YouTube Shorts
(3 por día). Hasta pasar la auditoría de la YouTube Data API la subida es manual; después, el bot
sube solo con `publishAt` (ver §1). Corre 24/7 en la Raspberry Pi 4 (misma Pi que el trading bot,
servicio systemd separado: `clips-bot`).

**Idioma:** español argentino, informal. **Estilo del usuario:** directo, sin atajos, datos > opinión.
**Regla persistente:** después de CADA cambio, actualizar este archivo (versión, changelog, estado).

---

## 1. DECISIONES YA TOMADAS (no reabrir sin dato nuevo)

- **Plataformas: Twitch + Kick (2026-09-22).** Twitch tiene API oficial (Helix `GET /clips`).
  Kick NO tiene API pública de clips: se usa la interna de la web
  (`kick.com/api/v2/channels/{slug}/clips`, con `sort=view&time=week` para los más vistos de la
  semana). No está documentada y puede romperse o empezar a pedir verificación de navegador sin
  aviso: si falla, se loguea, se avisa y la corrida sigue con Twitch. Descarga: yt-dlp en las dos.
- **Streamers: con permiso citado O como experimento (política revisada 2026-09-22).**
  `config/streamers.yaml`: `permiso.cita` + `permiso.fuente` (permiso público citado) **o**
  `permiso.experimento: true`. Sin ninguno de los dos, no entra. NO se contacta a nadie por ahora.
  Con experimento, el control de copyright real es Studio: se sube en PRIVADO, se esperan los
  Chequeos de copyright y recién ahí se publica (va como recordatorio fijo en cada mensaje).
- **Un reclamo o strike excluye al streamer, automáticamente.** Queda en la DB (`streamer_estado`)
  y ninguna corrida lo vuelve a usar hasta sacarlo a mano. Hoy se dispara con `/reclamo <id>` por
  Telegram; cuando exista el módulo de métricas (§4b) se llama igual desde ahí.
- **Auronplay reclama sus directos por Content ID (revisado por Santi en Studio, 2026-11-10).**
  Solo 3 Shorts de Rots tienen reclamo: los 3 son de Auron (01/11, 08/11 y 09/11), "audiovisual"
  de sus propios directos (ej. "1_HABLAMOS_Y_JUGAMOS…"). Siguen públicos y no afectan la
  visibilidad: NO explican las pocas vistas de Rots. Ningún otro streamer reclama. Auron se sigue
  subiendo (NO usar `/reclamo` con estos: lo excluiría); en los análisis por streamer, marcarlo
  como "reclama" y, para monetizar a futuro, priorizar a los streamers que no reclaman (la plata de
  un video reclamado va al dueño y podría pasar a bloqueo).
- **Sin IA generativa de video.** Gemini se usa solo para texto: título, descripción, hashtags,
  `depende_de_fecha`, y elegir entre candidatos cuando hay empate.
- **Mezcla diaria de Rots (2026-09-28, con datos de lo subido):** lo que rinde es Davoo, Auron,
  Coscu, Coker y Spreen; Minecraft y el Dedsafío no los mira nadie. Entonces: la carpeta Dedsafío
  sin diarios ni en vivo, sin cupo del evento, cupos `argentinos: 2` + `famosos: 1` (Auron) y el
  catálogo de fallback, máximo 1 clip por streamer (relleno incluido), multi-POV APAGADO (era
  para el Dedsafío), y el score pesa los 👍/👎 de Santi por streamer (después, las vistas de
  YouTube, cuando exista §4b). **Señales prendidas por Santi el 2026-09-29, después de ver la
  medición:** picos de chat con `peso_chat` 0,5, su gusto con `ejemplos_gusto` 3, y lo que pegó en
  otros canales con `pego.activo` y `min_vistas` 5.000 (API de YouTube con `YOUTUBE_API_KEY`).
- **REGLAS FIJAS PARA TODOS LOS VIDEOS (decisión permanente de Santi, 2026-09-28).** Valen para
  efemérides, /narrar, /serie, /editar y los clips donde aplique. Están UNA vez en el código
  compartido y `tests/test_reglas_fijas.py` falla si alguna se rompe. No se tocan sin que Santi
  lo pida.
  1. **Fotos que muestran lo que se dice** (`clips_bot/ilustrar.py`; hoy lo usa Pequeña Historia,
     el único video narrado con fotos): por cada frase Gemini anota qué mostrar ("petri dish
     bacteria"); el bot busca en el artículo y en Commons por palabras y por categoría, con los
     filtros de siempre; Gemini elige la mejor para cada frase en UNA llamada. Mínimo 6 fotos
     distintas por video, ninguna más de 6 s seguidos, sin repetir salvo que no haya otra. En la
     hoja de aprobación, cada foto con su frase al lado.
     **Fotos de época (2026-09-29, un avión de 2008 en una historia de 1940):** (a) el `mostrar`
     de cada frase lleva año/década y lugar ("1940 German fighter aircraft grounded", no
     "airplane"; se valida el año en las frases del pasado); (b) una foto de Commons sacada más de
     `MARGEN_EPOCA` (10) años después del hecho no es candidata de una frase del pasado (Gemini
     marca `presente` en las que hablan de hoy); (c) al elegir, Gemini ve el año de cada foto y
     confirma `de_epoca` (si dice que no, esa foto sale); (d) sin foto de época, se repite una del
     artículo del hecho antes que usar una moderna; (e) en la hoja, el año al lado de cada foto.
     **Fotos que sirven (2026-10-21, la de bitcoin: una app con "Something went wrong", una planilla
     de frase semilla, un gráfico en picada con "el precio subió" y placas en filipino):** (f) nada
     de capturas, apps, documentos, planillas, gráficos, diagramas, mapas ni logos salvo que la
     frase hable de eso (Gemini dice el `tipo` de cada foto y el código decide por la frase); OCR:
     más de 7 % de la imagen con texto (`UMBRAL_TEXTO_OCR`) = afuera, salvo frases de documentos
     o pantallas; (g) nada con texto en otro idioma que no sea castellano o inglés
     (`otro_idioma`); (h) si la foto contradice la frase (`contradice`), sale; (i) las elige SOLO
     el modelo principal; si hay que usar el de respaldo, la hoja y el texto dicen "⚠️ Fotos
     elegidas con el modelo de respaldo: revisalas"; (j) hechos desde 2000 (o frases de hoy):
     Pexels/Unsplash antes que Commons; (k) una frase sin foto buena repite una buena y, si ya no
     se puede repetir, va una **tarjeta** (la clave de la frase o el año, grande sobre una buena
     difuminada) antes que una foto mala. **Relleno (2026-11-09, los billetes de rupias de
     Android):** una frase SIN foto propia nunca usa la que Gemini eligió para OTRA frase puntual:
     usa una del tema general del video (`efemerides.generales`: las del artículo del hecho, sin
     descartadas ni modernas) o alarga la de la frase anterior; si ni así se cumple lo de 6 s, la
     tarjeta (`tests/test_relleno_fotos.py`).
     La época le gana a la cantidad: si no hay 6 fotos de época, el mínimo baja a las que haya
     (4 o 5, con aviso). **Con menos de 4 (`ilustrar.MIN_FOTOS_ABSOLUTO`) el hecho no se usa y se
     pasa al siguiente del día** (pedido de Santi, 2026-09-29: antes que repetir fotos); solo si
     ninguno llega se usa el que más fotos tenga, con aviso (`sin_alternativa`, piso 2).
  2. **Guiones que se entienden** (`clips_bot/reglas.py`, `REGLAS_CLARIDAD`, dentro del prompt
     de efemérides, /narrar y /serie): el cómo y el porqué, paso a paso, para un chico de 15
     años, sin dar nada técnico por sabido. Menos datos si hace falta, pero que se entienda.
  3. **Audio limpio** (`clips_bot/media.py`): fade in 0,1 s y fade out 0,5 s en la mezcla final,
     el audio termina exacto con el video (nada de `-shortest`), crossfade corto (0,04 s) donde
     se pegan tramos, y después del render un chequeo que avisa si hay un pico arriba de −3 dB en
     el último segundo o si audio y video no terminan juntos (en `enviar_clip`, el aviso sale en
     el mensaje de Telegram).
- **Pequeña Historia en Facebook: Nacozari es el caso de referencia de lo que funciona (2026-11-09,
  confirmado por Santi: 100 % ORGÁNICO, sin promoción).** Reel del 07/11, "El héroe que salvó a su
  pueblo en un tren en llamas" (Jesús García, Nacozari, Sonora, 1907; el 7/11 es el Día del
  Ferrocarrilero en México): 597 reacciones (557 👍, 32 ❤️), 12 comentarios y 86 compartidos,
  contra 0-13 reacciones de los otros 25 Reels, con una página de 100 seguidores. Los comentarios
  son de mexicanos con un lazo propio (un abuelo salvado, familias ferrocarrileras, uno que trabajó
  en el puente de Nacozari). Lo que funcionó: historia humana real, lugar concreto, en el día en
  que ese lugar la conmemora, acto heroico (no tragedia sola). **YouTube NO se toca** (las
  efemérides andan ahí, ~1.000 vistas cada una): cualquier prueba con esto es solo en Facebook.
  **Insights medidos el 2026-11-09** (token de página con `read_insights`): Nacozari 16.841
  reproducciones, 45 % del video visto en promedio (16,3 de 36,5 s), 37 % llega al final, +88
  seguidores; Instagram (06/10) 7.914; el resto entre 3 y 225, y desde el 31/10 casi todos ~200.
- **Video APARTE para Facebook (prueba de 2 semanas desde el 2026-11-10, decisión de Santi del
  2026-11-09; §3d):** una historia humana real de un lugar concreto de Latinoamérica por día, en
  lo posible en su aniversario. **Texto con Claude** (Sonnet 5.5 elige el hecho y escribe el
  guion, Haiku 5.5 clasifica): deja de depender del cupo de Gemini. **Gemini solo para las fotos y
  la voz**; la voz va por la SEGUNDA clave (Piper de respaldo). YouTube no cambia nada. La escucha
  la propone a las 06:30; 📤 la sube SOLO a la página de Facebook a las 08:30 del país de la
  historia (11:00 AR sin país; Santi, 2026-11-11, antes 19:00 AR). **2 Reels por día (Santi,
  2026-11-10):** la efeméride de YouTube (✅ y 📤, como siempre) sale también en la página a las
  19:00 AR (`facebook.hora_efemeride`, desde el 11/11; antes 12:00), con 4 h como mínimo entre los dos. Las dos quedan
  en `bot_estado.historias_fb_registro` con `reel` = `efemeride` | `historia` para la comparación
  del 24/11 (las entradas sin `reel`, anteriores a esto, son historias).
- **Calendario de fechas de Latinoamérica (Santi, 2026-11-11; `calendario.py`):** aniversarios de
  fundación, días nacionales, de héroes locales, fiestas patronales y conmemoraciones, con fuente
  (Wikipedia en español), sin inventar fechas. Esos días la historia de Facebook va con esa fecha
  antes que cualquier otro hecho (México, Colombia, Argentina, Perú, Chile y Venezuela primero), el
  día exacto y nunca después; cada lunes, la lista de la semana a Santi.
- **Control de calidad de todo video de Pequeña Historia (Santi, 2026-11-11):** menos del 70 % del
  tiempo con fotos reales (no tarjetas) = NO se arma; primero otra búsqueda con Claude, después otro
  hecho del día, y si ninguno llega, aviso por Telegram en vez del video.
- **Nicho de Pequeña Historia: 3 videos por día, todos en formato corto (Santi, 2026-11-12):**
  2 de **historias reales de Latinoamérica** (`locales.py`, con prioridad a las fechas del calendario,
  sin repetir hecho y, si se puede, sin repetir país) que van a YouTube Y a Facebook (Facebook a la
  mañana del país, 4 h o más entre los dos); 1 de **historia de la tecnología e internet**
  (`efemerides.tema: tecnologia`, desde la vida real, nunca tramas) SOLO en YouTube
  (`facebook.efemeride: false`). En YouTube los 3 a 4 h o más (`efemerides.horas_youtube` 11:00 /
  15:30 / 20:00). Nada fuera de esos temas: si un día no hay suficientes buenos, salen menos y se
  avisa (`ef.SinTema`, "hoy sale 1 de 2"). Voces: aviso a Santi al llegar a 8 de ~10 por clave y
  día, contando Lo Encontré (`voces.py`). Seguimiento a 2 semanas contra los 10 Shorts anteriores
  (`medicion_ph`, 26/11).
- **Gancho primero en TODO Pequeña Historia (Santi, 2026-11-12):** efeméride e historia, YouTube y
  Facebook. En Facebook la mayoría se iba en el 0:04, justo cuando terminaba "Un día como hoy…"; en
  YouTube cada Short recibe un solo paquete de ~1.200 vistas en 24 h y la mitad desliza al arranque.
  La primera frase es lo más sorprendente (sin fecha ni "Un día como hoy"), el año va en la segunda
  ("En <año>,") y en pantalla; la voz arranca en el cuadro 1; el gancho escrito en grande desde el
  primer cuadro; la primera foto es la más impactante. Medición por video (`medicion_ph.py`) y
  comparación con los 10 anteriores el 26/11.
- **Ganchos concretos (Santi, 2026-11-16; Pequeña Historia y Así Nació, regla fija):** el gancho dice el DATO
  concreto más fuerte de la historia; las fórmulas genéricas de intriga ("pasó algo que no esperaban", "nadie lo
  podía creer", "lo que pasó después te va a sorprender", "no vas a creer", "algo increíble"…) no pasan la
  validación (`reglas.gancho_generico`, `REGLA_GANCHO_CONCRETO` en los prompts; en Así Nació también los textos de
  las 3 opciones de gancho). MAL: "Fusilaron a una joven por espía, y pasó algo que no esperaban"; BIEN: "La
  fusilaron a los 22 y antes gritó una frase que todavía se recuerda". La frase de giro de la mitad no entra.
- **Pequeña Historia: pregunta al final y giro a la mitad (Santi, 2026-11-16; las dos plataformas, todos los
  videos):** la ÚLTIMA frase es una pregunta corta al público (≤ 12 palabras, termina en "?") que invita a
  comentar, sobre esa historia; el pago del gancho pasa a la ANTEÚLTIMA. A la mitad (30-60 % de las frases,
  `frase_intriga`, `ef.rango_intriga`) una frase corta que renueva la intriga ("Pero lo que nadie sabía…") para la
  caída del segundo 10 al 20. Lo exige `validar_guion` y la revisión del final (`SISTEMA_PAGO`) lo respeta.
- **Facebook: resumen de cada Reel a las 24 h (Santi, 2026-11-16; Pequeña Historia y Así Nació, `stats_fb.py`,
  `_fb_24h_tick`):** entre las 24 y las 48 h de publicado, una vez: reproducciones, cuántos pasan los 3 s (el valor
  del segundo 4: Facebook da 100 % fijo en los segundos 0-3), siguen en el segundo 10, llegan al final, tiempo medio,
  interacción, seguidores que trajo el Reel y los de la página en esas 24 h, contra la mediana de los otros Reels
  del canal (con menos de 3 medidos a las 24 h, con los datos de hoy), y el gancho (la primera frase). Guardado en
  `bot_estado.fb_reels_24h`; va en el informe del 26/11 (`stats_fb.resumen_informe`).
- **Así Nació: reglas_v3 (Santi, 2026-11-16; `gancho_v3.py`, `animacion.reglas_v3`, PRENDIDO el 16/11 a la tarde
  después del tercer Tupper de prueba, con el OK previo de Santi "cuando esté bien, prendelo"):** GANCHO de 2-3 cortes de ~1 s con un golpe en cada corte, la imagen imposible del producto (explota,
  gigante, multiplica, vuela, multitud), rayos de cómic de colores fuertes, polvo y destellos, texto grande arriba (3
  a 5 palabras); 3 opciones por video en un pedido aparte (`completar_v3`: sumadas al schema del guion, la gramática
  pasaba el tope de Claude) y la revisión visual elige la más llamativa (`elegir_gancho`, "¿frenarías el dedo?").
  RESTO: 2 planos por frase (de lejos → de cerca a las manos o el objeto, `gv.planos`), ninguna toma de más de 3 s,
  zoom lento siempre; decorado de contexto solo en interiores (estante, mesa, piso; afuera ya hay autos y faroles);
  rótulo con año y lugar; manos haciendo algo y objeto fiel en el prompt y en la revisión (`redibujar_protagonista`).
  **Segunda vuelta (Santi, 2026-11-16, después del primer Tupper; reglas para TODOS los videos):** los 3 ganchos los
  elige la revisión sola (a Santi le llega solo el video, con ❌ Cancelar); la revisión juzga el gancho como imagen
  imposible ("¿frenarías el dedo?", sin pedirle gente) y, si no sirve, se prueba la opción siguiente
  (`sistema_revision_v3`). El PRODUCTO EN USO en la mayoría de las escenas (el Tupper guardando comida, el Play-Doh
  amasado, el cubo resuelto), aunque la voz hable de otra cosa; flotando o girando como mucho 2 veces y solo si la frase
  lo justifica (`errores_uso`: `FLOTA_MAX`, `EN_USO_MIN` 60 %). Nadie parado sin hacer nada (la revisión lo rechaza
  siempre). Los primeros planos encuadran las MANOS con el objeto (`gv.foco`: el objeto en la mano o apoyado abajo,
  nunca uno flotando ni las caras; zoom 1,55). Ningún texto se repite ni se pisa (`gv.sin_textos_repetidos`: lo que ya
  dice el subtítulo no va grande, un solo texto grande a la vez, el rótulo baja a y 420, el texto del gancho a y 600).
  Nada de decoración sin relación (la revisión la saca del decorado).
- **Así Nació: mejora continua (Santi, 2026-11-16):** (1) cada video suma algo nuevo a la biblioteca (al menos 1 escena
  `nueva` con un `accion_nueva` que no exista; con reglas_v3). (2) Después de cada video, la revisión anota las 3 cosas
  más flojas con un cuadro de ejemplo (`puntos_flojos`, `bot_estado.asinacio_flojas`) y salen al lado de los números en
  el resumen de 24 h del Reel. (3) Lunes y jueves desde las 10:00, las 5 mejoras al motor más importantes, por impacto,
  con un cuadro de cada una y al menos una del gancho (`_mejoras_motor_tick`, `bot_estado.mejoras_motor`): Santi las
  aprueba y se programan.
- **Pequeña Historia: publicaciones de comunidad en Facebook (Santi, 2026-11-16; `comunidad_fb.py`,
  `historias_fb.comunidad`, PRENDIDO por Santi el 16/11 después de ver los 5 ejemplos):** 1 por día además de los
  Reels: la foto principal del artículo de la historia de Latinoamérica del día (reglas de fotos de siempre, con autor
  y licencia) en 4:5 con una pregunta grande que pide opinión o recuerdos (Haiku), programada para las 13:00 AR
  (`_comunidad_tick`, desde las 10:00, un intento por día). En el resumen de 24 h: vistas, comentarios, compartidos y
  reacciones (`stats_fb.metricas_post`).
- **Publicación de comunidad: la foto se mira (Santi, 2026-11-17, PH-24 del estándar):** Sonnet compara hasta 6 fotos
  del artículo con el texto (`comunidad_fb.fotos_candidatas` / `foto_que_coincide`); nunca políticos ni actos de
  gobierno salvo que la historia sea de esa persona, nunca mapas, logos ni marcas de agua. **El tema empieza por la foto**
  (Santi, misma tarde): las historias del día y después las del banco de Latinoamérica con buenas fotos (ídolos,
  personajes, lugares; artículos + categoría de Commons, `cf.temas`, `bot_estado.comunidad_usados` para no repetir), y
  el texto habla de lo que muestra la foto. Si ningún tema tiene foto, no sale y aviso a Santi.
- **Latinoamérica: ídolos de antes (Santi, 2026-11-16):** tipo `idolo` (época de oro del cine mexicano y argentino,
  cantantes, actores, deportistas) como historia real con persona, giro y emoción, puntuada como las demás; también en
  la búsqueda de personajes y la web. Primer caso: **Jorge Negrete, 30/11** (nació el 30 de noviembre de 1911,
  verificado en gob.mx, imer.mx y El Siglo de Torreón): `historias_fb_hecho:2026-11-30` = "Jorge Negrete".
- **Guion de Pequeña Historia desde el 2026-11-13 (Santi, con datos de Facebook: 98 % hasta el
  segundo 3 y 40 % en el 8 en Cartagena; los Reels de 30-45 s promedian 3.800 reproducciones y los
  de 15-30 s, 256):** gancho con una pregunta abierta → la 2.ª frase suma INTRIGA (nada de "En
  <año>, en <lugar>,") → el año y el lugar se DICEN en la 3.ª o 4.ª (escritos en pantalla desde la
  2.ª) → tensión → giro → final que paga el gancho (última o anteúltima frase). Las de
  Latinoamérica duran 30-40 s (70-90 palabras); la de tecnología, 20-30 s. Solo pasan las historias
  de Latinoamérica con 8 o más de promedio en persona, peligro, giro y emoción (Sonnet las puntúa;
  Nacozari = 10); si un día no hay, salen menos y se avisa.
- **Texto con Claude, Gemini solo para voces y lo que pide audio (Santi, 2026-11-12):** los textos de
  Rots (título, frase de arranque, pregunta, descripción, puntaje y tono, con 3 cuadros), el chequeo
  visual y el desempate, y el texto del video de tecnología, con Claude (Sonnet; el desempate,
  Haiku), Gemini de respaldo (`claude.ConRespaldo`). Lo único que SOLO puede Gemini: las voces y
  escuchar audio (/narrar y /serie le pasan el audio del video para avisar si hay música).
- **Ficción (Santi, 2026-11-11, Ash Ketchum):** NO se eligen hechos que pasan dentro de una ficción
  (lo que le pasa a un personaje en un episodio, juego o película). Cultura pop sí, solo desde la vida
  real: estreno, lanzamiento, quién lo creó, cómo se hizo, impacto, récords. Nunca la trama. Vale para
  la efeméride y la historia de Facebook, y está en el chequeo del guion.
- **Así Nació: subtítulos estilo Shorts virales (aprobados por Santi, 2026-11-14; `animacion.subtitulos_virales`):**
  grupos de 1 a 3 palabras; Montserrat Black (OFL) dibujada como trazos, con contorno negro grueso y
  sombra suave; cada palabra entra con un "pop" justo cuando la voz la dice (Whisper); las claves (las
  marca el guion: nombres, números, el giro o el chiste; ≤ 2 por frase) más grandes y amarillas, rojas y
  temblando cerca de un golpe o en el remate; un emoji dibujado (💥💰😱🤣) como mucho cada 4,5 s, al lado
  de una clave; en la franja de arriba (y 168-294) sin tapar personajes ni acción.
- **Presupuesto de Claude (Santi, 2026-11-15):** el crédito es de US$ 100 por mes y se renueva; el tope propio
  es ~US$ 80 (`claude.PRESUPUESTO_MES`). No hace falta ahorrar: el margen va a calidad (Sonnet mira 5 fotos y
  3 videos por frase, puntúa 14 hechos de tecnología, 30 historias de Latinoamérica y 14 marcas, más reintentos
  de guion). Aviso por Telegram al pasar el 75 % y el 100 % del tope en el mes; informe diario a las 09:00.
- **Así Nació: 2 por día (Santi, 2026-11-15):** a las 13:00 y a las 20:00 AR, de marcas distintas (la rotación
  registra el primero antes de armar el segundo). Si un video falla por algo que no es "no hay candidato"
  (Claude cortado, Gemini caído), otro intento en 1 h, hasta las 22:00 y 4 intentos por video: no se pierde el
  día. Un guion cortado por max_tokens se reintenta solo con el doble de límite (hasta 64.000).
- **Así Nació: prueba de horarios (Santi, 2026-11-18; `animacion.horas_prueba`, `horarios_an.py`):** del 19/11 al 02/12
  se publica a las 12:30 y 18:00 (YouTube y Facebook) en vez de 13:00 y 20:00; el 03/12 vuelve solo. El resumen de los
  lunes trae una línea con la mediana de vistas por horario (YouTube: los 2 primeros días por Analytics, guardados en
  `bot_estado.asinacio_yt_2dias`; Facebook: las de 24 h de `stats_fb`), 12:30 contra 13:00 y 18:00 contra 20:00.
- **Así Nació: tope duro de US$ 1,20 por video (1,50 a la mañana del 18/11) y escenas con sentido (Santi, 2026-11-18; AN-28 y AN-29):** todo lo
  de Claude de un video como mucho US$ 1,20 (`marcas.TOPE_USD_VIDEO`, `pasado_tope`): al llegar se frena todo; si llega
  al estándar mínimo sale, si no, ese día no se publica (`TopeCosto`, una línea). Antes de dibujar, el director
  (`animacion/director.py`) escribe qué ve el espectador en cada frase y se corrigen solas las escenas que no se
  entienden sin la voz; los ejemplos de Santi van en el prompt del guion (REGLA 18).
- **Fotos de Pequeña Historia por capas (Santi, 2026-11-18; para gastar menos):** (1) origen: las de un artículo
  general (un país, `ef.es_general`, o el artículo de la ciudad en Latinoamérica) quedan marcadas `general` y solo
  sirven como paisaje de ese lugar; no hay más "reserva" (`de_reserva` vacío: cada frase usa solo las fotos elegidas
  para ella, o tarjeta); (2) calidad: 800 px y nitidez; (3) Haiku lee SOLO el nombre y la descripción de cada foto y
  descarta otra persona, otro lugar u otro año (`SISTEMA_PREFILTRO`; lo descartado no vuelve por relleno); (4) solo
  las 2-3 finalistas por frase se miran con imagen, con Haiku (`describir_fotos` + `elegir_fotos`; `_elector_fotos`
  es Haiku); (5) una sola revisión, la del video terminado, con todos los cortes en UN mosaico y todas las reglas
  (`calidad.mosaico`); la de la hoja de antes de la voz ya no corre.
- **Mensajes cortos (Santi, 2026-11-20: "demasiado texto, no los leo"; `aviso_corto.py`):** cada video llega SOLO con
  título, hashtags y una línea ("✅ 11/13 · US$ 0,31 · sale 11:00"); si necesita aprobación, ✅ / ❌ en el video y una
  línea "Motivo: …". Todo el detalle (reglas, correcciones, puntajes, fotos, textos) queda en `bot_estado`
  (`detalle:<clip>`) y sale con el botón "📋 Detalle" o `/detalle [clip]`. Los avisos e informes a Santi pasan por
  `_aviso`: 3 líneas como mucho y el resto detrás de 📋. Lo Encontré (repo bot-videos) lo hace su propia sesión.
- **Producción: tope de US$ 2,50 por día de Claude (Santi, 2026-11-24)** (`presupuesto.TOPE_DIA`): al acercarse se
  recorta en el orden de siempre (comunidad y búsqueda web de Latinoamérica, después Latinoamérica a 1); tecnología nunca.
- **Calor (Santi, 2026-11-24, hasta que resuelva el enfriamiento):** un render a la vez, 4 min de pausa como mínimo entre
  renders y hasta bajar de 58 °C (30 min como mucho), y el freno de 80 °C (`freno-calor.service`).
- **Reintentos inteligentes (Santi, 2026-11-24; todo Pequeña Historia):** un video que falla por fotos no pasa a otra
  historia a ciegas: (1) segunda búsqueda, y cada frase sin foto real (o con una que no muestra lo que dice) se busca
  otra vez con otras palabras (el producto o la persona en inglés, modelo, año; `ef.consultas_frase`, nunca la cosa
  genérica sola) en Commons, Openverse (Flickr CC), Smithsonian, Europeana, Flickr e Internet Archive; (2) plan B:
  reescribir solo esas frases hacia una foto que hay; (3) recién ahí otra historia. Library of Congress (Cloudflare) y
  las salas de prensa (sin API, fotos con derechos) siguen afuera; la LoC entra por su categoría en Commons. Cada falla
  queda en `candidatos_descartados` con `detalle.intentos`. Reserva: como mucho 5 intentos por día, de a UNA historia,
  y no arranca si no entra en el tope de US$ 2,50 (`reserva_tec.COSTO_INTENTO` 0,35); una historia del banco que falla
  (fotos, guion, video o estándar) no se vuelve a intentar. Viernes desde las 10:00, el resumen de los motivos de falla
  de la semana (`fallas.py`).
- **Reserva con 60-69 % de fotos reales (Santi, 2026-11-24):** entra igual si cumple TODAS las otras reglas del
  estándar (con revisión hecha; PH-21 no cuenta), marcada "⚠️ fotos 66 %" en la línea corta del mensaje, y Santi decide
  al aprobarla; con menos de 60 % no entra (la propuesta tampoco baja de 60: `proponer(piso_fotos=)`).
  `reserva_tec.entrada`, `marcados`, informe de un día con `informe_marcados_pedido` (22:10).
- **Banco de tecnología (Santi, 2026-11-24):** solo marcas, empresas y videojuegos (separados por palabras antes de
  puntuar) y solo con 6 o más fotos libres contadas sin Claude (`ef.fotos_libres`: artículo, Commons, Openverse, Flickr,
  Internet Archive; `banco.FOTOS_BANCO_MIN`), con el mismo mínimo de puntaje que el video del día (7,5; con 8 sumó 2
  en 60 días, `banco.minimo_banco`).
- **Ventilador (Santi, 2026-11-24):** volvió el Fan SHIM; `ventilador.service` prendido de nuevo (siempre prendido en
  los renders).
- **Pruebas: tope de US$ 1 por día (Santi, 2026-11-20),** aparte de la producción; al llegar se frena hasta el día
  siguiente y se avisa en una línea; render local siempre que se pueda.
- **Pruebas sin Claude real (Santi, 2026-11-18):** con origen "prueba" (scripts y CLI a mano) Claude y la búsqueda
  web no responden (`claude.prueba_sin_claude`) salvo con `CLIPS_CLAUDE_REAL=1`, y eso solo si Santi lo pide, avisándole
  antes cuánto va a costar.
- **Revisión final que arregla (Santi, 2026-11-18):** si el mosaico encuentra una foto mal, se cambia SOLO esa foto por
  la siguiente finalista de su frase (o una tarjeta), se rehace solo ese tramo y se revisa solo ese corte
  (`calidad.revisar_y_reemplazar`, dentro de `hacer_video`, 2 vueltas); el video se frena únicamente si no hay reemplazo.
- **Saldo de Claude hasta el 14/12 (Santi, 2026-11-18): US$ 70** (`presupuesto.py`, desde la fila de gemini_uso del
  deploy, `bot_estado.presupuesto_fila`). Cada día desde las 06:30: promedio de los días completos (7 como mucho) y
  proyección al 14/12; si no alcanza, Así Nació a 1 video por día (`asinacio_un_video`) y vuelve a 2 cuando con el
  segundo (~US$ 0,90) igual alcanza. Cada cambio, una línea a Santi.
  **Ritmo y escalones (Santi, 2026-11-25: "recortaste Latinoamérica entero por US$ 2,93/día y ayer gastaste ~1"):** el
  ritmo es el promedio de los últimos 3 días completos de producción (sin pruebas) y sin los días de reintentos ya
  arreglados (`DIAS_NO_CUENTAN`: 23/11), sumándole a cada día lo que ahorró el recorte con el que corrió
  (`bot_estado.presupuesto_niveles`). Se recorta de a UN escalón por día (saltando lo que ya está apagado: con Así Nació
  pausado, primero comunidad y búsqueda web, después Latinoamérica a 1, después sin Latinoamérica,
  `presupuesto.un_escalon`) y, si el ritmo baja, se devuelve lo recortado de una.
- **Al primer intento (Santi, 2026-11-25; la meta: 8 de cada 10 pasan el estándar y menos reintentos).** Medido del 19 al
  25/11: llegaba a video ~1 de cada 4 historias que pasaban el puntaje, 35 % del gasto se iba en reintentos y solo 2 de 24
  videos pasaban el estándar (PH-02 en 17, borrosas 9, de otra época 8). (A) **Tecnología: el banco es la fuente normal**;
  la fecha solo con un hecho de marcas, empresas o videojuegos de 8,5 o más (`ef.proponer(fecha_fuerte=)`); el banco de
  tecnología repone debajo de 20 y llena hasta 25 (`banco.MINIMOS`/`OBJETIVOS`) para no bajar nunca de 15. (B) **Fotos
  primero** (`fotos_primero.py`, `efemerides.fotos_primero`): antes del guion se juntan las fotos libres, el código saca
  chicas, borrosas y con texto, Haiku describe cada una (qué se ve, nítida, época, si es de la historia, persona) y sin 8
  buenas la historia no se usa; Sonnet escribe el guion con la lista de fotos delante y Haiku dice qué fotos van con cada
  frase. (C) **Verificación de Latinoamérica:** una respuesta cortada o sin JSON se reintenta una vez con el doble de
  lugar (`web_historias.es_tecnica`); se verifican solo las 3 mejores del día (y 3 del banco, `locales.MAX_VERIFICAR`).
  (D) **Informe de las 09:00:** "Al primer intento: N % (tecnología a/b · Latinoamérica c/d · reserva e/f)" y "Gastado
  en reintentos: US$ x de US$ y" (`fallas.lineas_informe`).
- **Tema primero; las fotos son un filtro, no la forma de elegir (Santi, 2026-11-25, después de la estación Concordia:
  "salió bien hecho, pero la historia no la vería nadie").** (1) Latinoamérica con variedad: fútbol, ídolos de antes,
  música, inventos latinos, curiosidades, historias humanas sorprendentes (`temas.GRUPOS_LATAM`, tipo `musica` nuevo);
  el mismo tema no sale dos días seguidos (`locales.proponer(evitar_temas=)` con los de ayer y hoy, `ph_latam:<día>`
  guarda el `grupo`: van al final, solo si no hay otra; el tema manda sobre el país). Tecnología: marcas y videojuegos
  primero, otros temas con 8,5 o más (ya era así). (2) Estaciones, edificios, inauguraciones, fundaciones y próceres
  (`temas.tema_comun`) no están prohibidos, pero su puntaje es el MENOR entre el promedio y la `rareza` (nuevo criterio
  1-10 de Haiku, "¿hace decir 'no puede ser'?"; `locales.puntaje_de`). (3) Las fotos (8 buenas con fotos primero)
  recién entre las que tienen buen tema. (4) El banco de Latinoamérica se revisa una vez con la regla
  (`banco.revisar_latam`, `bot_estado.banco_latam_regla`) y saca lo que no llega a 8. **Las pruebas, con historias
  variadas y de buen tema** (nunca elegir una historia de prueba por las fotos que tiene). El banco se llena también
  por tema con la búsqueda web de Haiku (`banco.TEMAS_BANCO_LATAM`, `cosechar_latam_web`, solo las que tienen artículo
  de Wikipedia; `scripts/llenar_banco_latam.py`).
  **Música e ídolos de antes (Santi, 2026-11-25):** como en las curiosidades, `peligro` se puntúa como `sorpresa` o
  momento épico (`locales.es_curiosa`). Un video ya armado se puede guardar para un día (`guardar-latam <carpeta> <día>`,
  `bot_estado.latam_guardado:<día>`): ese día sale primero, en lugar del hecho fijado (el de Jorge Negrete, para el 30/11,
  si pasa el estándar en la prueba).
- **Cortes según las fotos y guion sin frases abstractas (Santi, 2026-11-25, para todo Pequeña Historia):** (1) en el
  formato corto la cantidad de cortes de cada frase es la de sus fotos que todavía se pueden usar; con pocas, cortes
  más largos con movimiento de cámara hasta 6 s (`ef.CORTE_LARGO_MAX_S`, `plan_rapido.segun_fotos`), y el gancho corta a
  los 2,5 s solo si su frase tiene otra foto; la tarjeta queda solo si una foto pasaría de 6 s. (2) Cada frase habla de
  algo que se puede mostrar con su foto, y los productos se nombran siempre ("un Walkman", no "un aparato azul y
  plateado"): en el prompt (`SISTEMA_GUION`) y en la validación (`ef.frases_vagas`, corrección puntual).
- **Menos texto (Santi, 2026-11-18):** mensajes de 2-3 líneas. El resumen de cada Reel a las 24 h ya NO se manda: se
  guarda y alimenta los guiones (`aprendizaje.py`: los ganchos que más y menos retuvieron entran en el prompt de cada
  canal); los lunes desde las 10:00, un resumen de 5 líneas con qué cambió y cómo vienen las vistas
  (`_resumen_semana_tick`).
- **Latinoamérica sin banco (Santi, 2026-11-18; el banco se usó 3 veces en la semana):** la búsqueda web sí andaba,
  pero traía 4-6 historias que puntuaban bajo; ahora pide 8-12 que lleguen a 8 (persona, peligro o sorpresa, giro,
  emoción), con 10 búsquedas; una verificación sin JSON se reformatea en vez de caerse (`web_historias.json_de`); y
  una historia del día que solo falló por fotos (50-70 %) sale con el mínimo relajado antes de ir al banco.
  Tecnología: si los de 7,5 fallan por fotos, prueba los demás desde 6 y después el banco (el 18/11 no salió nada).
- **TECNOLOGÍA, PRIORIDAD NÚMERO UNO (Santi, 2026-11-23; es lo que mejor anda en YouTube: el chip de Intel 24.105
  vistas, el procesador barato 14.345; el resto de los Shorts ~1.200):** (1) **2 por día en YouTube**
  (`efemerides.por_dia: 2`, `horas_youtube` 11:00 y 20:00): el del día (04:00) y los que falten de la reserva
  (`_tec_del_dia_tick`, apenas termina el intento del día; si la reserva completa el día, se borran los reintentos).
  (2) **Reserva de 3 videos ya armados y revisados** (`efemerides.reserva`, `reserva_tec.py`, `bot_estado.reserva_tec`):
  del banco de tecnología (historias que no dependen de la fecha, guion sin "hoy"), `ef.proponer(solo_banco=True)` +
  `_efe_armar(reserva=True)` (arma y revisa sin mandar) y entran solo si pasan el estándar; se reponen solas de a uno
  (`_reserva_tec_tick`, 06:30-22:00, turno pesado libre, como mucho 3 fallas por día); sacar del banco para la reserva
  NO cuenta como uso del banco (`banco.quitar`). (3) **Presupuesto primero para tecnología** (`presupuesto.RECORTES`,
  `bot_estado.presupuesto_nivel`): si el saldo no llega al 14/12 se recorta, en orden, Así Nació a 1 por día →
  comunidad y búsqueda web de Latinoamérica → Latinoamérica a 1 por día → sin Latinoamérica; tecnología nunca.
  (4) **Temas** (`temas.py`, `bot_estado.temas_pesos`): subtema de cada video de tecnología (videojuegos, internet,
  empresas, marcas, inventos) y grupo de cada Reel de Latinoamérica (fútbol, ídolos, curiosidades, historias humanas,
  próceres y fundaciones), por palabras y el `tipo` de Haiku; los lunes desde las 10:15 (`_temas_semana_tick`) la
  mediana de vistas por tema en 3 líneas y los que rinden suman al ORDEN de elección (nunca al mínimo). (5) **YouTube
  solo de tecnología**: Latinoamérica sale solo en Facebook (`historias_fb.youtube: false`) hasta el 15/12, cuando se
  crea su propio canal; las 2 de Latinoamérica del 23/11 ya programadas en YouTube se pasaron a privado. (6) **Facebook:
  fútbol, ídolos de antes y curiosidades primero; próceres, conquistadores, batallas y fundaciones al final aunque sean
  del calendario** (tipos `futbol` y `procer`, `locales.buenos`/`elegir`, la búsqueda web). Medido el 23/11 (21 Reels):
  Colón campeón 14.730 reproducciones, Chapecoense 967, niños de Morelia 1.165, Huetamo 808, Pedro Infante 421;
  fundaciones y próceres 11-280. (7) El mensaje corto dice cuál es ("💻 Tecnología · ⏸ 6/9 …"): el 23/11 Santi no se dio
  cuenta de que el de tecnología había llegado.
- **Fotos antes de gastar y tarjetas como último recurso (Santi, 2026-11-23, el Mundial 96 de la reserva: 6/9 y
  US$ 0,61; la reserva gastó US$ 2,50 ese día reintentando Bell y AlphaGo):** (1) antes de pedir el guion se cuentan las
  fotos usables sin Claude (artículo + Commons con el título, `ef.fotos_previas`); con menos de 4 (`PRECHEQUEO_MIN`) no
  se escribe. (2) Una historia que falla por fotos queda marcada (`banco.marcar_sin_fotos`, `bot_estado.sin_fotos:tecnologia`),
  sale del banco y no se vuelve a intentar ni a cosechar. (3) La reserva prueba primero marcas, empresas y videojuegos
  (`ef.SUBTEMAS_FACILES`). (4) Una frase sin foto real se REESCRIBE hacia una foto que ya pasó los filtros (plan B,
  `frases_flojas` + `reescribir_frases_con_foto`, Haiku) antes que una tarjeta; como mucho 2 tarjetas por video
  (`MAX_TARJETAS`); las tarjetas (también las del armado) no se juzgan como foto. (5) Una tarjeta con un año o número
  aparece justo cuando la voz lo dice (`alinear_tarjetas`, por los subtítulos; el año solo en una frase que lo dice), y
  la revisión final lo controla sin Claude (PH-26). (6) Pausa de la reserva: `bot_estado.reserva_tec_pausa` = "1".
- **Pequeña Historia NO se publica sola (Santi, 2026-11-17, después del Short de Colón con Cristina Kirchner en
  Atucha):** `efemerides.publicar_sola: false`: los 3 videos se siguen armando solos (`sin_aprobar`), pero llegan con
  ✅ Publicar / ❌ Cancelar y, si Santi no responde, NO salen. Se vuelve a prender SOLO cuando Santi lo diga.
- **Fotos: reglas fijas para todos los videos y publicaciones (Santi, 2026-11-17, Colón; PH-02, PH-10 a PH-13 y
  PH-25 del estándar):** nunca políticos ni actos de gobierno salvo que la historia sea de esa persona; nunca retratos
  de personas que la historia no nombra (Haiku marca `politico`/`retrato`/`quien` de cada foto y el código decide con
  el guion, `efemerides.motivo_persona`; Sonnet y la publicación de comunidad tienen la misma regla); cada foto muestra
  lo que dice SU frase: los cortes del formato corto y las frases sin foto ya no usan fotos "del tema general" del
  artículo (`generales` vacío): alargar la anterior o tarjeta; nada de fotos de menos de 800 px (sin la excepción de
  500 para las de época) ni borrosas (nitidez < 150, `motivo_calidad`, medido con las de Colón); el año en pantalla es
  el del hecho desde el primer cuadro (ya no cuenta desde otra fecha). Con el video terminado, Claude mira un cuadro de
  cada corte con su frase (`calidad.revisar_video_ph`): PH-02 y PH-10 a PH-13 frenan el video (`calidad.BLOQUEANTES`).
- **Pequeña Historia sin aprobar: PRENDIDO (Santi, 2026-11-15; desde el 17/11 se arma solo pero NO se publica solo):** los 3 videos llegan ya programados con
  ❌ Cancelar y, si no se toca nada, salen a su hora. Latinoamérica: si ninguna llega a 8, sale la mejor del día
  si tiene 7 o más (una sola por día).
- **Corregir solo lo que falla (Santi, 2026-11-15):** cuando la validación rechaza una frase o escena (Así Nació
  y Pequeña Historia), Claude corrige SOLO esa parte con el resto como contexto (`correcciones.py`: cambios por
  número, agregar, sacar, campos generales) y se vuelve a validar; el guion entero de nuevo recién después de 3
  correcciones puntuales fallidas. Lo Encontré (otro repo, `bot-videos`) todavía no lo tiene.
- **Haiku puntúa, Sonnet escribe (Santi, 2026-11-15):** marcas, hechos de tecnología e historias de
  Latinoamérica los puntúa y elige Haiku (`_puntuador`, `marcas.proponer` con el revisor); Sonnet escribe y
  corrige guiones, elige las fotos y hace la revisión visual. Meta: US$ 1-1,5 por día.
- **Historias curiosas (Santi, 2026-11-15):** en las de tipo lugar_curioso, invento, costumbre, record, misterio
  o dato_sorprendente, "peligro" se puntúa como `sorpresa` ("¿hace decir 'no puede ser'?"); en las de personas
  sigue "peligro" (`locales.es_curiosa`).
- **Así Nació: fidelidad (Santi, 2026-11-15; regla permanente, en el guion, la validación y la revisión
  visual):** el gancho MUESTRA el objeto protagonista o el momento clave de su historia (va en los objetos de
  la escena 1); acciones específicas (`fabricar` = las manos trabajando sobre el objeto, sin martillo; martillo
  o engranajes como mucho en 1 escena); personajes fieles (`genero`, `edad`, `persona_real` por actor: el
  género y la edad mandan sobre el dibujo del rol, `acciones.aspecto`; una persona real siempre igual);
  `anio_escena` = la época de cada escena (la decoración sale de ahí: nada de monitores en 1974). Si falta un
  dibujo, el guion pide `dibujo_nuevo` + `dibujos_nuevos` y Sonnet lo dibuja como SVG (`dibujos.py`: solo
  formas, sin texto ni logos, probado en el rasterizador) y queda guardado en `data/animacion/dibujos/` para
  los próximos; si no se puede, se reformula la escena (corrección puntual). **Un objeto que no está NUNCA
  frena el video (Santi, 2026-11-16):** `marcas.resolver_objetos` corre después de dibujar, después de cada
  reescritura por duración y antes de cada línea de tiempo: lo que falta se dibuja con Sonnet y, si falla,
  pasa al más parecido de la biblioteca (`esc.prop_parecido`: palabras en común con el nombre y qué es,
  después las letras; nunca martillo, engranajes ni efectos; sin nada parecido, una caja). Red final en
  `timeline`: un objeto, fondo, gesto o pose de Tito desconocidos van con el más parecido y un aviso en el log.
- **Así Nació: guion y escenas (Santi, 2026-11-15; regla permanente para TODOS los videos; en el guion, la
  validación y la revisión visual):** (a) GANCHO PROPIO: los primeros 3 s muestran el momento más
  sorprendente o visual de ESA historia, del texto y en su lugar; la destrucción en cadena del living era SOLO
  de Nerf (`cadena` casi siempre vacía); nunca repetir un arranque (`animacion_ganchos` en bot_estado, los 12
  últimos + el de Nerf: otra cadena, o el mismo lugar con la misma acción u objeto, no valida). (b)
  ESCENARIOS SEGÚN LA ESCENA: al menos 3 lugares, nunca 3 escenas seguidas en el mismo, casa y taller como
  mucho 2 escenas (solo si la historia pasa ahí); lugares nuevos: laboratorio, hospital, campo, puerto. (c)
  ACCIÓN: fabricar, vender, usar, probar, multitudes (`multitud`); escenas de gente hablando, como mucho 2.
  (d) PERSONAJES según la historia y la época: 12 roles nuevos (obrero/a, científica, inventora, médico,
  enfermera, granjero, marinero, cocinero, deportista, estudiante…), al menos 3 distintos, chicos solo si la
  historia los tiene. La revisión visual marca un gancho genérico o repetido, un lugar sin sentido y dos
  personas hablando cuando la frase cuenta una acción.
- **Pequeña Historia Latinoamérica = historias curiosas y reales (Santi, 2026-11-15):** héroes y gente común, y
  también lugares insólitos, inventos, costumbres, récords, misterios y datos sorprendentes de ciudades y
  países (el lugar puede ser el país), siempre un hecho real con fecha; mismo puntaje (8, o 7 para una por día).
- **Así Nació: estilo visual (Santi, 2026-11-15; regla para TODOS los videos, motor actual;
  `tests/test_visual_asinacio.py`):** (a) volumen: toda forma con contorno lleva un degradé radial con la
  luz arriba a la izquierda y la sombra violeta abajo a la derecha, y el contorno es más grueso del lado de
  la sombra (`svg.py`, `P.VOLUMEN`); brazos y piernas con franja de sombra y brillo; ropa con botones,
  bolsillo, pliegues y costura; ojos con iris, dos brillos y párpados según la emoción, cejas con forma,
  dientes; sombra de contacto en el piso (se achica al saltar). (b) escenarios: textura de pared
  (empapelado, ladrillo, azulejo) y de piso (madera), haz de luz de la ventana, sombra donde la pared toca
  el piso y debajo de los muebles, bruma arriba (`escenas.ambiente`, en el fondo cacheado: gratis) y un
  objeto en primer plano en una esquina de abajo con parallax en una de cada dos escenas. (c) color: tinte
  cálido y viñeta por lugar sobre todo menos los subtítulos (`escenas.grade`, rasterizado una vez por
  lugar). (d) cámara: zoom suave siempre, temblor con giro en los golpes, y en los momentos fuertes (gancho,
  giro, final, cara de sorpresa o enojo, cadena) un PRIMER PLANO de la cara del primer personaje ×1,9
  durante 0,8 s después del último golpe (sin temblor encima). (e) efectos: polvo en cada golpe o rotura
  (además de los pedazos), líneas de movimiento detrás de lo que vuela (alineadas, solo a velocidad), 4
  destellos con un "ding" en el remate (en anillo alrededor de la cara, nunca encima) y transición "iris"
  hacia el giro y el final.
- **Voz falsa en las pruebas (Santi, 2026-11-15: "las voces de Gemini no alcanzan, 8 de ~10"):** la voz real de
  Gemini SOLO para el video que se publica. `ef.voz_falsa()`: con origen "prueba" (scripts y CLI a mano) la voz es
  Piper o silencio con la duración estimada (`voz_de_prueba`, motor `falsa:…`); producción (ticks, `diario`,
  `efemeride-diaria`) y Telegram (✅) usan la real. Un script que arma un video PARA PUBLICAR (como el Intel del
  15/11) tiene que correr con `CLIPS_VOZ_REAL=1`. En bot-videos lo hace su propia sesión.
- **ElevenLabs SOLO para Así Nació (Santi, 2026-11-15; plan Starter, 40.000 créditos por ciclo, se renueva el
  15 de cada mes):** (1) la voz de Tito (`animacion.elevenlabs_voz`, modelo `eleven_v4`): **Abuelo Charlie**
  (`Yb8JGzcZyW5YYzenhRCm`), elegida por Santi el 15/11 y FIJA para todos los videos desde el 16/11 07:00; sin
  créditos o con ElevenLabs caído, Gemini como siempre. **Duración (Santi, 2026-11-15):** si la voz sale de
  32-38 s, primero ±8 % de velocidad sobre el audio que ya está (atempo, sin cambiar el tono;
  `marcas.ajuste_velocidad`); recién si no alcanza se reescribe el guion y se paga otra voz.
  `voz_efemeride` usa ElevenLabs solo si quien llama pasa `elevenlabs_cfg` (lo hace únicamente Así Nació).
  (2) **Pequeña Historia y Lo Encontré siguen con Gemini gratis.** (3) **Biblioteca de efectos**
  (`animacion/sfx.py`, `CATALOGO`): generados UNA vez con ElevenLabs (`eleven_text_to_sound_v3`) en
  `assets/sfx/` (en git, con `biblioteca.json`) y reusados en todos los videos; uno nuevo solo si no existe
  (se genera en la Pi a `data/animacion/sfx/`); sin archivo ni clave, el sintetizado. (4) Créditos: cada pedido en
  `elevenlabs_uso`; `/costos` muestra el ciclo de la cuenta y el mes por tipo y origen; aviso al 75 % y al
  100 % (`_elevenlabs_tick`, la cuenta se mira cada 30 min). Las pruebas no gastan (voz falsa primero).
- **Nunca un día sin video (Santi, 2026-11-15; `banco.py`):** (1) si nadie llega al mínimo, sale la mejor
  del día con **piso absoluto de 6** (tecnología siempre; Latinoamérica solo la PRIMERA del día, la segunda
  sigue pidiendo 8, o 7 si hoy no salió ninguna de menos de 8; Así Nació en el último intento del día). (2)
  Debajo de 6, o sin candidatas: **banco de reserva** de historias que no dependen de la fecha (curiosidades,
  personajes, lugares; hechos de tecnología; marcas y ángulos de Así Nació), puntuadas de antemano con 8+;
  al menos 20 por banco, se repone solo al bajar de 10 (`_bancos_tick`, 09:30-21:30, en un hilo, cosechando
  días a más de 100 días de hoy; sin conmemoraciones ni fundaciones). El guion de una del banco no dice
  "hoy" (`ef.NO_ES_DE_HOY`). (3) Fotos: si ningún hecho llega al 70 % de fotos reales, el mejor sale con el
  mínimo bajado de a 5 puntos hasta el 50 % (`ef.umbral_relajado`, también con la voz real); la segunda
  búsqueda va en castellano y en inglés con la década, en las categorías de archivos nacionales de Commons
  (`ARCHIVOS_COMMONS`) y en Europeana. LoC y la Biblioteca Digital Hispánica dan 403 a bots y Memoria
  Chilena no tiene API: no se usan directo. (4) Aviso en el mensaje del video ("⚠️ salió con puntaje 6,2
  (mínimo 8)", "📦 del banco de reserva", "⚠️ fotos reales 55 %"). (5) A las 20:00, si un canal no tiene nada
  programado ni publicado hoy, aviso a Santi (`_sin_video_tick`). **(6) El banco es la excepción (Santi,
  2026-11-16):** cada uso queda en `bot_estado.banco_usos`; /costos muestra los de la semana (lunes a domingo)
  por canal y, si uno pasa de 2, aviso a Santi una vez por semana (`_banco_usos_tick`: su búsqueda necesita
  arreglo). **(7) La segunda de Latinoamérica tampoco queda vacía:** sin ninguna de 8 (o 7), una del banco;
  nunca una de menos de 8 (`de_banco` saltea las de menos de 8). Si ninguna de las del día sale (sin
  verificar o sin fotos), se prueba con el banco antes de rendirse.
- **Latinoamérica: fuentes web y 2 fuentes por dato (Santi, 2026-11-16, opción C; `web_historias.py`,
  `historias_fb.web`):** además de Wikipedia, Haiku busca con la búsqueda web de la API (versiones básicas:
  Haiku no tiene filtro dinámico) historias en diarios, sitios de historia, museos y archivos de cada país
  (hasta 8 búsquedas por propuesta); entran como candidatas y se puntúan igual (8 o más). Antes del guion,
  CUALQUIER historia de Latinoamérica (web, Wikipedia o banco) se verifica: cada dato en 2 o más fuentes de
  sitios distintos (lo cuenta el código; es. y en.wikipedia son UNA sola), al menos 3 datos; el guion sale
  SOLO del texto verificado. Sin verificar, una de la web no se usa; si la búsqueda está caída, una de
  Wikipedia sale con "⚠️ sin verificar". Los links quedan en la propuesta (`local.verificados`,
  `fuentes_web`, `origen`) y en la bitácora (`fuentes`). Cada búsqueda (US$ 0,01) se anota en gemini_uso como el
  modelo `web_search` (1 unidad = 1 búsqueda), así entra en /costos y el informe diario. **Prueba de un día
  real:** el primer día de producción con búsqueda web, al terminar, `_web_latam_tick` lo mide; hasta
  `web_tope_usd` (0,45) queda andando y avisa; si se pasa, se apaga sola (`bot_estado.web_latam_apagado`) y
  avisa. Medido el 16/11 (prueba, 17/11): 1 búsqueda de historias = 6 búsquedas y 101.000 tokens de entrada
  (≈ US$ 0,07, 5 historias de infobae, ámbito, billiken, icarito); 1 verificación = 2 búsquedas + lecturas,
  37.000-61.000 tokens (≈ US$ 0,03; Morelos en el Aguacatillo: 8 datos, cada uno en inehrm.gob.mx y
  memoriapoliticademexico.org o vlex). Estimado ≈ US$ 0,25-0,30 por día. Tecnología y Así Nació todavía no.
- **Audio: nada arriba de −3 dB (Santi, 2026-11-16; regla fija 3):** `media.cola_audio` arranca con un
  limitador a −4,4 dB (`LIMITADOR`: sin subir el volumen, sin correr la sincronía), así todos los videos (Así
  Nació, Pequeña Historia, clips, /narrar) terminan debajo de −3 dB aunque el último golpe venga fuerte
  (la historia de CDMX del 15/11 terminó en −2,1 dB; medido: −0,3 → −4,3 dB pasando a AAC).
- **Así Nació: gancho, viaje, sepia, manos y textos (Santi, 2026-11-15, noche; regla permanente para TODOS los
  videos):** (1) el GANCHO es lo más importante (en Facebook se va el 65 % entre el segundo 3 y el 7): el momento
  más sorprendente con ACCIÓN y el objeto protagonista; nunca objeto_gira, contador, reunión, estantes ni el fondo
  `escenario` (`GANCHO_SIN_ACCION`); si la revisión visual lo ve repetido, genérico o con gente parada
  (`rehacer_gancho`), lo CORRIGE sola con los arranques anteriores como contexto. (2) Nadie parado sin hacer nada
  (`QUIETAS`; la reunión de la biblioteca ahora es uno dándole el objeto al otro). (3) VIAJE AL PASADO, marca del
  canal, siempre igual (1,35 s, `escena_viaje`): reloj gigante con las agujas girando hacia atrás, el año como
  cuentakilómetros (`esc.odometro`), la imagen que se retuerce en remolino (`render.retorcer`), el color que se
  apaga hasta sepia y un whoosh fuerte (`sfx.viaje`). (4) En el pasado, todo sepia menos el objeto protagonista
  (`CapaEscena.color`, el sepia va por capa). (5) Manos con dedos, nudillos, uñas y pulgar (`prop_mano`). (6)
  Ningún texto se sale: los subtítulos van en dos líneas si achicarlos no alcanza (`lineas_de`, `TAM_DOS`), y el
  número gigante, el rótulo, la cita, el cartel y el texto del gancho miden con la fuente y se achican
  (`tam_que_entra`).
- **Así Nació: lo que se ve = lo que dice la voz (Santi, 2026-11-15; regla permanente para TODOS los videos;
  `escenas_lib.py`, `marcas.errores_accion`):** (1) cada frase muestra la acción concreta que dice la voz;
  festejar solo si la frase habla de un éxito. (2) **Biblioteca de escenas** reutilizables con planos (desde
  arriba, manos, de lejos, de espaldas): armar en la mesa, vender en la tienda, fábrica produciendo, reunión,
  cargar un barco, contador de ventas, estantes que se llenan, objeto girando, despegue; el guion elige
  `accion_escena` + `plano` y cambia objeto y personajes; si falta, `nueva` + `accion_nueva` y la receta queda
  guardada (`data/animacion/escenas_lib.json`). "libre" como mucho en el 40 % de las escenas. (3) el objeto
  protagonista se mueve (el cubo se arma solo con `fase`, la cinta, el barco, los estantes, el contador, el
  despegue con humo y fuego). (4) la revisión visual marca `cambiar_accion` cuando lo que se ve no es lo que
  dice la frase, y se corrige esa escena. (5) nada de engranajes ni martillo salvo que la frase hable de una
  máquina o un taller.
- **ESTÁNDAR DE CALIDAD (Santi, 2026-11-16; `ESTANDAR_CALIDAD.md`, `clips_bot/calidad.py`): el estándar fijo de Así
  Nació y Pequeña Historia.** Cada video se puntúa contra las reglas "revisión" antes de publicarse (Así Nació: la
  revisión visual de los cuadros, 2 vueltas de corrección y una última que solo mira; Pequeña Historia: Claude mira la
  hoja foto + frase antes de la voz y cambia solas las fotos que no pasan, una vuelta). Lo que sigue sin cumplirse sale
  igual y el mensaje lo dice ("📏 Estándar 12/14 · ❌ AN-05 …"). Todo queda en `calidad_fallas` / `calidad_videos` y los
  lunes desde las 09:30 le llega a Santi qué reglas fallaron más (`_calidad_semana_tick`). **Toda regla de calidad nueva
  que apruebe Santi se suma a ESTANDAR_CALIDAD.md** (con el próximo número libre; las de revisión entran solas en la
  próxima revisión). Santi no revisa video por video.
  **Mínimo para publicarse sola (Santi, 2026-11-17):** debajo de 12/14 (Así Nació; era 11 hasta la tarde del 17/11) o 7/9 (Pequeña Historia) después
  de las correcciones, el video NO se programa: llega con ✅ Publicar igual / ❌ Cancelar (`sub:pub` / `sub:no`,
  `_retenido_callback`) y, si no responde, no sale. Con 1 o 2 reglas sin cumplir, solo el aviso.
- **Así Nació: reemplazo por escena aprobada (Santi, 2026-11-16; `animacion/reemplazo.py`).** Las 2 vueltas de corrección
  siguen igual; después, una escena que sigue sin pasar se reemplaza SOLO a ella por una de la biblioteca de escenas que
  ya pasaron el estándar en otro video (`data/animacion/escenas_estandar.json`, se llena sola con cada video), adaptada
  a esa frase (mismo protagonista, sus personajes, lugar, época, luz y decorado), sin dibujos nuevos; hasta 4
  candidatas, cada una chequeada con Haiku sobre 3 cuadros. Empalme: se pega solo el tramo de esa escena (misma
  duración, misma transición; la voz, los subtítulos y los efectos de afuera, intactos; un solo render al final). Si
  ninguna pasa, aviso y esa regla va PRIMERA en las mejoras al motor (`bot_estado.mejoras_primero`). Tope: si las
  correcciones de un video pasan de US$ 0,50 (`reemplazo.TOPE_CORRECCIONES_USD`, contado desde las vueltas de
  revisión), se frena y el mensaje lo dice (💸).
- **Así Nació: motor que se autosustenta (Santi, 2026-11-20, "que ande bien sin que yo corrija escenas"; AN-02, AN-05,
  AN-18, AN-22, AN-25, AN-29):** (1) lo que existe en la biblioteca se usa todas las veces que haga falta; lo que falta se
  crea y queda solo si pasa el estándar; nada frena un video. (2) Manos con dedos (`animacion/manos.py`: abierta,
  relajada, puño, señala con el índice, agarra; los dedos se cierran ENCIMA de lo que se agarra, prop `dedos`), en todos
  los personajes y en Tito. Acciones completas de perfil (`p_tomar_alto`: la botella sube inclinada a la boca y la cabeza
  va atrás, y vuelve a bajar; comer, escribir, coser, armar, cargar). (3) EXPRESIONES según el momento
  (`animacion/emociones.py`, `emocion` por escena en el guion, REGLA 17): éxito, pérdida, determinado, idea, trabajo,
  duda, burla; cara siempre, cuerpo si tiene las manos libres; la ficha la lleva y la revisión la chequea. (4) El lugar del
  origen sale del oficio del protagonista (`protagonista.oficio`, REGLA 18; `plantillas.lugar_de_oficio`: químico →
  laboratorio con frascos y tubos, empresario → oficina escribiendo el plan, artesano → taller). (5) Menos gente: 1 o 2
  en primer plano, sin multitud de relleno (`acciones.SIN_RELLENO`, `MAX_GENTE`). (6) Éxito que se entiende: salta con
  los brazos arriba, gráfico que sube, ¡AGOTADO! y estantes vacíos (`tienda:vacia`). (7) Por ahora videos de 6-7 escenas
  de 4-5 s, 25-30 s, Tito como mucho una vez, cámara que se acerca dentro de cada plano. (8) Una sola revisión,
  CALIBRADA (`REVISION_CALIBRADA`: solo lo que se nota en 1 segundo, nunca detalles del fondo); la escena que falla se
  reemplaza por la escena base que mejor sirve para su frase (`reemplazo.reemplazar_con_base`, sin Claude ni otra
  revisión); sin vueltas de corrección ni rescate. Mínimo para publicarse sola 15/19 (`calidad.MAX_FALLAS` 4); tope
  US$ 0,60 por video. Aprobadas por Santi: tienda, fábrica, apretón, crisis y lanzamiento; el gancho lo juzga en un video real.
- **Así Nació: BIBLIOTECA BASE, reusar escenas y crear solo si hace falta (Santi, 2026-11-20; reemplaza el "cada video
  único" del 17/11; AN-25):** 10 escenas armadas y probadas (`animacion/plantillas.py`): gancho (gancho_v3) ·
  taller_inventor · fabrica_produce · vender_tienda · apreton_manos · crisis (de noche, el papel de ventas) ·
  exito_multitud · producto_en_uso (si se toma o se come, a la boca) · lanzamiento · cierre_tito. El guion las usa POR
  DEFECTO (★ en la lista, REGLA 15) cambiando el producto de esa época, los personajes según rol y año, el lugar y los
  textos; `libre` o `nueva` SOLO si ninguna sirve para la frase, y una `nueva` entra a la biblioteca solo si pasa el
  estándar (`guardar_acciones_nuevas(d, aprobadas)` después de la revisión; antes se arma como `libre`). **Sin tope de
  escenas repetidas** (ni "un tercio" ni "ninguna igual a otro video"; `errores_unicas` ya no se llama). El lugar sigue
  siendo el de la historia real (`errores_lugar`). La gente de las escenas base trabaja DE PERFIL (`perfil` en el
  personaje, gestos `p_…` de personajes.py, `mano_perfil` para poner el producto en la mano) y cada escena trae su
  cámara (plano medio → de cerca, `plantillas._cam`; gancho_v3.planos no la pisa). Santi aprueba la hoja antes de
  probar 5 marcas; Así Nació se prende si 4 pasan 17/19.
- **Así Nació: lugares de la historia real (Santi, 2026-11-17, después del Frisbee; AN-25):** el lugar de cada escena es
  donde pasó esa parte según el artículo (playa, estadio, cocina, fábrica, tienda…; fondos `playa`, `estadio` y `cocina`
  nuevos), nunca un living o un taller genéricos; si la frase dice "en la playa", el fondo es `playa`
  (`marcas.errores_lugar`, `LUGAR_DE_FRASE`). (El tope de "un tercio repetido" de ese día se sacó el 20/11.)
- **Así Nació sin hacerlo todo desde cero (Santi, 2026-11-17; AN-25):** las piezas (personajes, manos, fondos,
  objetos, efectos) se reusan. Lo que falta se crea y queda guardado: objetos
  (`dibujo_nuevo`) y LUGARES (`lugar_nuevo` → `marcas.crear_lugares` → `dibujos.dibujar_fondo`, en
  `data/animacion/fondos/`; entran en la lista de `fondo` desde el próximo arranque). **Rescate** antes de retener un
  video: se rehacen enteras las escenas que fallan creando lo que falte y se vuelve a mirar (`RESCATE_USD` 0,50 aparte);
  recién si sigue debajo de 12/14, ✅/❌. /costos muestra por video el total y las piezas nuevas
  (`bitacora.texto_piezas`); si un video pasa de US$ 1,50, aviso a Santi.
- **Así Nació: personajes por rol, trabajo por rol, época y ficha (Santi, 2026-11-17; regla para TODOS los videos,
  AN-15 a AN-19 y AN-26 del estándar):** el protagonista es la persona real (edad de esa escena, ropa de su época y
  clase); los demás se visten por ROL y AÑO (`acciones.vestir`, piezas `Personaje.vestuario`: mameluco, delantal,
  uniforme, traje, calle, guardapolvo, falda_larga; sombreros bombín, boina, cofia): obreros con delantal y gorra
  plana antes de 1940 y mameluco después, cajeros y vendedores con uniforme, clientes con ropa de calle de la época,
  empresarios de traje (galera antes de 1915, bombín hasta 1950), científicos con guardapolvo. Todos HACEN algo de su
  rol: `quieto` en obrero, cajero, vendedor, cliente o repartidor = trabaja con lo suyo en las manos
  (`TRABAJO_ROL`); en otros roles no valida (`errores_quietos`). En la fábrica con obreros, la línea de producción
  adelante con el producto que avanza (`cinta_frente`). Fondos de época: fábrica de ladrillo con vigas, ventanales,
  ollas de cobre y cajones antes de 1940, sin engranajes nunca en la pared; calle con casas de ladrillo, carteles
  pintados y adoquines antes de 1930 y carro con caballo antes de 1910; los dibujos nuevos salen de la época.
  Cada escena tiene su FICHA (`marcas.ficha_escena`, `fichas.json`), que la revisión usa para preguntar quién es cada
  uno, qué hace y si eso pasaba en ese año y lugar (`REVISION_FICHA`). La ventanita de Tito va a una esquina libre o
  esa vez no aparece (`lugar_tito`). El mínimo para publicarse sola pasa a "como mucho 2 reglas sin cumplir"
  (`calidad.MAX_FALLAS`): Así Nació 17/19, Pequeña Historia 7/9 (OK de Santi, 2026-11-17).
- **Así Nació: nada tapa el texto grande ni los subtítulos (Santi, 2026-11-17; AN-27):** tampoco con la cámara cerca
  (`acciones.despejar_textos`, al final de `linea_de_tiempo`): primero sale el decorado, después la cámara se acerca
  menos; sin cámara, se baja lo que tapa. Antes de 1920 una caja es un cajón de madera (`prop_caja(forma=1)`).
- **Así Nació PAUSADO y costo por video (Santi, 2026-11-19: US$ 2,68 en dos videos que no salieron, el segundo 8/19):**
  `animacion.activo: false` hasta que un video de prueba pase 17/19 y cueste menos de US$ 0,60; ahí vuelve con 1 por
  día. Sonnet SOLO escribe el guion de Así Nació; director, revisiones, dibujos, gancho y el resto con Haiku
  (`claude.modelo_para`). Caché de prompts en el sistema de todo pedido (`cache_control`; gemini_uso anota la entrada
  equivalente, `claude.entrada_equivalente`). Guion: el primero + 2 reintentos (`reintentos_guion: 3`). **Todos los
  canales: como mucho 4 pedidos de corrección por video (por candidato), con Haiku salvo la reescritura entera del
  guion** (`correcciones.TOPE_POR_VIDEO`, `TopeCorrecciones`); si no alcanza, la escena o la foto se reemplaza por una
  de la biblioteca o se cambia de historia o marca. Nunca más de 4.
- **Videos largos: NO por ahora (decisión de Santi, 2026-09-28).** No quiere videos largos con voz
  de IA. Si más adelante se hacen, van con SU voz grabada, no con Gemini TTS ni Piper.
- **Sin música agregada en los clips.** Cualquier música es riesgo de Content ID. Si el clip trae
  música de fondo del stream, se descarta (detección: ver §4). EXCEPCIÓN pedida por Santi
  (2026-09-27): Pequeña Historia lleva música de fondo con licencia verificada (docs/musica.md).
- **Volumen: 3 uploads/día** de clips + 1 de Pequeña Historia. Cuota (doc oficial, revisada
  2026-09-28): `videos.insert` cuesta 1 unidad de un balde aparte, *Video Uploads*, con 100 por día;
  ya no son 1600 de las 10.000 unidades generales. La cuota no es un límite para este volumen.
- **Publicación en YouTube por la API: PRENDIDA desde 2026-10-30** (`youtube_upload_enabled: true`).
  Hasta ahí era todo manual, porque se creía (y se anotó como confirmado) que los videos subidos por
  API desde un proyecto sin auditar quedaban bloqueados privados para siempre. YouTube cerró la
  auditoría diciendo que eso NO pasa, y la prueba lo confirmó: `y5TBZ5OwxoI`, subido PÚBLICO a Rots
  por `videos.insert`, quedó público, procesado y visible sin login a los 0, 10 y 60 min, sin
  restricciones. Ahora 📤 sube a Rots o a Pequeña Historia en privado con `publishAt` en su horario
  (13:00/18:00/21:30 los clips; `efemerides.hora_publicacion` la efeméride); un clip con partido en
  pantalla va privado SIN fecha (§3 paso 4). TikTok/IG siguen manuales; Facebook (Pequeña Historia)
  por su propia API.
  **Formato de la subida a Rots = el de los Shorts subidos a mano (2026-11-10, v0.82.0):** los de
  la API salían SIN ningún hashtag en la descripción (los hashtags iban solo como tags), con tags y
  en la categoría 20; los 40 subidos a mano (los que salían en el feed) tenían
  `<texto>\n\n#Shorts #streamer #tema\n\nClip de X — url`, sin tags y en la 22. Ahora
  (`textos.hashtags_youtube` / `descripcion_youtube`, `_para_youtube`): `#Shorts #<login>
  #<twitch|kick>` + el tema si hay (el juego si no es una categoría de charla, o `#futbol` si Gemini lo vio en el clip; el aviso de fútbol solo no alcanza), entre
  el texto y el crédito; sin tags; categoría 22. Los arma el código, no Gemini (traían
  "#Davoeneize" o "#Shorts射"). Pequeña Historia no cambia. `python -m clips_bot hashtags-rots
  [--aplicar]` corrige por `videos.update` los ya subidos (sin `--aplicar` solo muestra): sobre la descripción PUBLICADA (no la del json, que en `y5TBZ5OwxoI` seguía diciendo Twitch), solo le mete los hashtags antes del crédito.
- **Rots se sube SOLO todos los días (Santi, 2026-11-10: "subir todos los días sin cortar").**
  `publicacion.subir_solo: true`: la entrega diaria (05:00, su reintento y /ya; no /buscar ni
  /seleccionar a mano) se sube a Rots ANTES de mandarse, programada en su horario
  (13:00/18:00/21:30), sin tocar 📤; el mensaje llega con "📤 Programado" y ❌ Cancelar. Con
  partido en pantalla, privado sin fecha; una subida que falla se avisa en el grupo y la entrega
  sigue. Antes dependía de tocar 📤: hubo días con 1 subida y días con 4.
- **Prueba manual vs API: CANCELADA por Santi el 2026-11-10, antes de arrancar** ("no voy a subir
  nada a mano"; `prueba_manual_desde: ""`). El código queda (`clips_bot/prueba_manual.py`) por si
  se vuelve a hacer: poner la fecha de inicio. Lo que hacía: desde que sube la API, el feed de Shorts pasó de 84 % a 6 % de
  las vistas: hay que descartar que la causa sea subir por la API. Cada día, UN clip de la entrega
  diaria va con "📱 SUBILO VOS DESDE EL CELU": sin 📤 (el botón dice "📱 Lo subís vos" y el
  callback se niega a subirlo), con la descripción y los hashtags juntos en un bloque para pegar.
  La posición rota con el día (#1, #2, #3…) para que no sea siempre el mejor ni el mismo horario, y
  saltea los que tienen partido en pantalla. Registro en `bot_estado.prueba_manual`; el video que
  sube Santi se encuentra por el título (`metricas.emparejar`, 05:00). El 18/11, después de las
  métricas, le llega a Santi el informe (una vez, `prueba_manual_informe`): % de vistas del feed
  de Shorts (`insightTrafficSourceType` = SHORTS) a mano contra los subidos por la API esos mismos
  días. CLI `prueba-manual` lo arma en cualquier momento sin mandarlo. Config:
  `publicacion.prueba_manual_desde` / `prueba_manual_dias`.
- **Feedback loop obligatorio:** el bot mide cómo rinde cada video y usa eso para elegir mejor
  (ver §4b). Sin métricas el proyecto es ciego.
- **Valor agregado obligatorio en cada Short**: subtítulos quemados, layout vertical con cámara
  arriba/juego abajo (o zoom inteligente si no hay cámara), título con contexto, mención al
  streamer en descripción. Es lo que YouTube pide para no marcar "contenido reutilizado".

---

## 2. STACK

| Capa | Herramienta | Notas |
|---|---|---|
| Descubrir clips | Twitch Helix API (`Get Clips`) | app token client-credentials, gratis |
| Descubrir clips (Kick) | API interna de la web (`/api/v2/channels/{slug}/clips`) | no documentada; si falla, la corrida sigue |
| Descargar | `yt-dlp` | URL del clip → mp4 (Twitch y Kick) |
| Detectar cámara/layout | OpenCV (detección de rostro en frames muestreados) | decide layout |
| Marcador deportivo | OpenCV (esquina quieta + mucho borde) | heurística, se activa por streamer |
| Recorte + layout 9:16 | `ffmpeg` | 1080x1920, 30 fps, ≤ 59 s |
| Subtítulos | `faster-whisper` (modelo `small`, CPU) | español; quemados con ffmpeg |
| Texto (título/desc) | Gemini API (key existente) | prompt corto, salida JSON por schema |
| Upload YouTube | YouTube Data API v3 `videos.insert` | SOLO post-auditoría. OAuth, scope `youtube.upload` |
| Entrega manual | Telegram (envía mp4 + texto) | Santi sube a mano (YouTube hasta la auditoría; TikTok/IG/FB siempre) |
| Métricas | YouTube Data + Analytics API, Meta Graph API, TikTok Display API | solo cuentas propias, sin auditoría |
| Estado | SQLite (`data/clips.db`) | clips vistos, subidos, cursores, exclusiones |
| Alertas | Telegram (bot nuevo, no el del trading) | resumen diario + errores |
| Scheduler | systemd timer (1 corrida/día, 05:00 AR) | `clips-bot.timer` |
| Escucha de Telegram | systemd service siempre andando (long polling) | `clips-bot-telegram` |

Restricción de hardware (medido en la Pi el 2026-09-23, no estimado): Pi 4 Model B Rev 1.4, 8 GB,
4 núcleos, Debian 13, systemd 257, zona horaria ya en AR. **No hay undervoltage** (`throttled`
arranca en 0x0; la nota vieja estaba mal). Lo que sí hay es **throttling térmico**: con Whisper
sostenido llega a 84,7 °C y `get_throttled` pasa a 0xe0008 (límite blando de temperatura activo,
frecuencia ya capada). O sea que el cuello no es el voltaje sino el calor: conviene disipador/ventilador,
y por eso la unidad va con `Nice=10` y prioridad de CPU baja. NO paralelizar.

---

## 3. PIPELINE (una corrida diaria: `python -m clips_bot diario`)

1. Tres fuentes/grupos, según lo que declara cada streamer en `streamers.yaml`:
   - **reciente**: clips de los últimos 7 días con al menos 24 h de antigüedad
     (`antiguedad_min_h`), para que hayan juntado vistas y duplicados. Los más nuevos se descartan
     SOLO por esa corrida: no se marcan en la DB y vuelven a entrar cuando maduran.
     Clips del mismo streamer y VOD con `vod_offset` a ±60 s del más visto = mismo momento → queda
     uno solo (el más visto que pase los filtros) y cuántos hubo suma puntaje.
     Score = (1 + peso_momento × (clips del momento − 1)) × (1 + log10(1 + vistas)).
     El log achata las vistas (0 → 1,0; 10 → 2,0; 500 → 3,7; 50.000 → 5,7): un clip sin vistas que
     3 personas clipearon compite con uno de 500 vistas sin duplicados. `min_vistas` 0.
     **Vistas relativas (2026-09-29):** por streamer, solo pasan los clips del 30 % superior de
     SUS vistas en la ventana (`candidatos.vistas_top`, motivo "debajo del 30 % superior…");
     el catálogo, sobre su histórico (`umbral_historico`, guardado una semana). En /buscar con
     palabras no filtra. OJO: Kick y Twitch devuelven hasta 100 clips, así que en los canales
     grandes es el 30 % de ese tope.
   - **catalogo**: clips de 7 días a 3 años, por vistas absolutas, con su propio `min_vistas`.
     Cursor de Helix por streamer en la DB (tabla `catalogo_cursor`, junto con la ventana de fechas
     con la que se creó): cada corrida sigue donde quedó; al agotarse o si Twitch lo rechaza, ciclo
     nuevo con la ventana actualizada. `candidatos` NO mueve el cursor (listar no quema la página).
   - **evento** (streamers de una sección `evento_*`): además de los filtros comunes, solo entran
     clips de las categorías del evento (Minecraft) o con sus palabras en el título
     (dedsafio/nights), dentro del período. Los clips de DISTINTOS streamers hechos a la misma hora
     real (±2 min) cuentan como el mismo momento y suman el bonus: si 5 canales clipearon la misma
     muerte, ese momento sube mucho.
2. Filtrar (todas las fuentes): duración 15–60 s, no visto antes (`clips.db`), idioma es (Kick no
   informa idioma: esos no pasan por ese filtro), categoría no excluida.
   Co-streams y eventos de terceros fuera: palabra de `palabras_costream` en el título del clip o
   del stream (título del VOD), o categoría en `categorias_costream`. Se guardan en la DB con
   motivo `costream`. **Las palabras de fútbol (gol, Boca, River, partido, Mundial…) ya NO descartan
   (2026-09-29, Santi: "hablar de fútbol no es problema; mostrar el partido sí"):** en los
   streamers con `detectar_marcador` solo generan un aviso en el mensaje (`candidatos.aviso_futbol`,
   "⚽ habla de fútbol (…): mirá que no se vea el partido"); lo que descarta es VER el partido
   (paso 4). Las de esports (LEC, Worlds…) y las categorías Sports/Special Events siguen igual.
   **Programas de terceros** (`palabras_programa` por streamer, motivo `programa_terceros`): marca
   de un programa con formato propio en el TÍTULO DEL STREAM, no en el del clip. Si dispara, queda
   afuera TODO ese stream. En Kick el clip no trae el título del stream: sale de
   `/api/v2/channels/{slug}/videos` (una llamada por canal, `{livestream_id: session_title}`); si
   esa llamada falla, los clips quedan sin título de stream y la corrida sigue.
   **Datos personales en el título** del clip o del stream (motivo "datos personales en el
   título", `pantalla.datos_en_texto`, 2026-09-29): mails, teléfonos con prefijo internacional
   o con palabra de contexto (whatsapp, tel…), tarjetas con contexto y direcciones con calle y
   número. En texto escrito las palabras sueltas del OCR ("calle", "piso") NO cuentan.
3. Descargar los mejores candidatos con yt-dlp, solo hasta llenar el cupo de cada grupo.
4. Transmisión deportiva (streamers con `detectar_marcador`) → se detecta con DOS señales: marcador de
   TV en una esquina de arriba, o fracción de verde-césped alta en ≥ 2 de 12 frames (una cancha llena
   la pantalla). **Desde 2026-10-29 es un EXPERIMENTO (pedido de Santi): no se descarta**; el clip
   lleva `partido_en_pantalla` y el aviso "⚠️ Partido en pantalla: revisá las Verificaciones antes de
   publicar", y con la subida prendida se sube en PRIVADO y SIN fecha (nunca se publica solo; el
   botón queda "🔒 En privado: revisá Studio"). Un /reclamo sobre un clip con partido vuelve a
   descartarlos a todos (`bot_estado.partidos_excluidos`); el streamer sigue en las corridas.
   Después, filtros de audio: casi todo silencio, o muy pocas palabras por segundo.
4b. **Datos en pantalla (OCR, sin LLM).** tesseract sobre 8 frames; descarta con motivo
   `datos_en_pantalla` si aparece un mail, una palabra de pago (checkout, subtotal, CVV…) o de
   dirección (shipping, código postal…). Los NÚMEROS (teléfono, tarjeta) solo cuentan si en el mismo
   frame hay una palabra de contexto (tel, contacto, DNI): sin eso daba 3 falsos positivos y ningún
   acierto sobre 26 clips. Si tesseract no está instalado la capa se saltea y la corrida sigue.
5. Layout, tres opciones (el recorte central "a ver qué sale" se eliminó el 2026-09-23):
   - **split** — webcam fija: cámara arriba 40 % (1080x762) + línea negra de 6 px + abajo el
     cuadro ENTERO a 1080 de ancho, pegado a la línea, sobre el mismo video difuminado (desde
     2026-10-25; antes se recortaba el "juego" y cortaba la pantalla). La webcam es, en orden:
     (a) la PRIMERA de las guardadas del streamer (`facecam` en streamers.yaml, editable en
     /streamers → 📷 Webcam; Auron tiene dos) con su marco fijo en el lugar (≥ 3 lados con borde
     que no se mueve en todo el clip) y cara en ≥ 30 % de los cuadros, o cara en ≥ 80 %
     (`camara.presencia_facecam`); (b) una cara chica en ≥ 80 % de los cuadros adentro de un
     recuadro de bordes fijos (`layout.recuadro_fijo`), aunque haya otras caras; (c) una cara chica
     en ≥ 80 % de los cuadros, como antes. "Misma cara" pide también tamaño parecido (`TAMANO_MAX`
     1,6×). Una cara que no está todo el clip (foto en pantalla, cambio de escena) no es la webcam.
   - **fullcam** — UNA sola cara grande y centrada: crop 9:16 centrado en la cara.
   - **fit_blur** — todo lo demás: el 16:9 ENTERO escalado a 1080 de ancho y centrado, sobre el
     mismo video ampliado y con blur fuerte (`render.blur_sigma`) llenando el 9:16. No recorta nada,
     y los subtítulos caen en la franja de abajo, fuera del video.
   Se va a fit_blur si no hay cara estable, si hay 2+ caras separadas, si la cara quedaría a menos
   de `camara.margen_borde` (15 %) de un borde del recorte, o si en la zona que el split usaría de
   "juego" hay caras en más de `presencia_juego_max` de los frames (ahí no hay juego: es un podcast
   o un estudio, y el split repetiría la escena cortando a alguien).
   `layout_forzado` en streamers.yaml saltea toda la decisión para un canal (coker: `fit_blur`). Además, DESPUÉS del render se vuelve a
   pasar el detector de caras sobre el 9:16 final: si alguna queda pegada al borde, se re-renderiza
   con fit_blur y queda anotado en `rerender_fit_blur` del json.
   **Chequeo visual (`revision.py`, 2026-10-25):** con el 9:16 terminado, Gemini ve 2 cuadros en UNA
   llamada: ¿arriba está la cámara del streamer?, ¿subtítulos dobles?, ¿algo cortado? Cámara mal o
   algo cortado → se rehace en fit_blur; subtítulos dobles → se rehace sin los nuestros. Una sola
   vez, sin volver a preguntar. Si Gemini no responde, el clip sigue. Queda en `chequeo_visual` del
   json. Cuesta 1 llamada más por clip procesado (`render.chequeo_visual` para apagarlo).
6. Whisper → SRT → quemar subtítulos (fuente 64, bloque centrado al 80 % del alto, 2 líneas máx).
   Si el streamer tiene `subtitulos_propios: true` (ya trae subtítulos en vivo), no se queman; el
   SRT se guarda igual (título + pista de subtítulos en YouTube). Además, si el CLIP ya los trae
   (`pantalla.subtitulos_en_video`: OCR en la franja de abajo, palabras centradas que se dicen en ese
   momento, ±2,5 s; ≥ 2 de 8 cuadros), tampoco (`subtitulos_del_clip` en el json).
7. Gemini: título (< 60 chars, gancho, sin clickbait falso), descripción con crédito
   "Clip de [streamer] — twitch.tv/[login]", 3–5 hashtags incluyendo #Shorts, tipo de gancho, y
   `depende_de_fecha` (true si referencia algo puntual de ese día/semana → se descarta; ante la
   duda, true). Corre antes del render para no renderizar lo que se descarta.
   **El título se valida contra lo que se dice**: los nombres propios (mayúscula en medio de la
   oración) tienen que aparecer en la transcripción, la categoría o los títulos originales; si no,
   cuenta como error de validación y se regenera (OJO: hasta v0.34.0 NO corría, `parsear` no le
   pasaba el contexto a `validar`). Lo original del clip (título y transcripción) le llega a
   Gemini TAPADO (`pantalla.tapar_datos` → "[dato personal]"), y el título y la descripción que
   devuelve se revisan con `datos_en_texto`: si traen un dato personal, se regenera. La primera palabra no se mira: en español va en
   mayúscula siempre, y mirarla haría saltar "Reconoce" como si fuera un nombre.
   En la MISMA llamada vienen **`sensible`** y **`puntaje`**, con `textos.frames_para_puntaje` (4)
   frames del clip adjuntos:
   - **`sensible` → descarte duro** con motivo `tono_sensible`, sin excepciones y sin relleno:
     muerte, duelo, homenajes, enfermedad, accidentes, llanto real, violencia real entre personas
     (algo que pasó y se muestra o se cuenta) o salud mental. NO cuentan el humor normal, las
     puteadas, las derrotas, las peleas DENTRO de un juego ni una charla hipotética sobre quién
     ganaría una pelea.
   - **`puntaje` 1–10** (se entiende solo + tiene remate). Abajo de `textos.puntaje_min` (6 desde el
     2026-09-29; era 5) el clip
     NO se tira: se renderiza igual y queda marcado como **relleno**, y solo entra si la corrida no
     llega al cupo sin él. Sale con `RELLENO (puntaje X)` en el mensaje.
     **Los frames son imprescindibles**: sin ellos el puntaje castiga al humor visual. Medido sobre
     los mismos 27 clips, sin imagen y con 4 frames: mediana 5 → 6, y con corte 5 pasaban 14/27 →
     pasan 20/27. Los que más subieron son los visuales (renrize 2→9 con un parkour y un festejo,
     spreen 5→9 con un balde en la cabeza, vegetta777 4→8 cuando le explotan con misiles).
7b. **Multi-POV (grupo evento). APAGADO desde el 2026-09-28** (`multipov.activo: false`, pedido de
   Santi: era para el Dedsafío, que salió de los diarios; la prueba se cortó antes del 09/10 sin
   ningún multi-POV armado). Lo que sigue es cómo funcionaba, por si se vuelve a prender.
   Estuvo PRENDIDO A PRUEBA desde el 2026-09-24.
   Estuvo apagado unas horas: la agrupación de "mismo momento entre streamers" usa la hora de
   CREACIÓN del clip (±2 min), que NO es la hora del hecho, y con 54 canales cualquier ventana de
   2 min junta cosas distintas. Lo que lo destraba es la verificación de "mismo hecho" (más abajo).
   **El trato (2026-09-24): si junta `votos_negativos_max` (2) multi-POV con 👎 dentro de
   `dias_prueba` (14), el bot lo apaga SOLO y avisa por Telegram.** Ese apagado se guarda en la DB
   (`bot_estado`), no en el YAML: el YAML está en git y lo editan las personas, esto lo decide el
   bot y tiene que poder pasar sin un commit ni un deploy. Se cuenta un CLIP por multi-POV y no un
   voto, así que cambiar el voto sobre el mismo Short no cuenta dos veces. Para volver a prenderlo:
   `db.arrancar_prueba_multipov`, que además reinicia el período. Si 3+ canales clipearon el mismo momento y se procesaron 3, se
   arma ADEMÁS un Short secuencial: hasta 3 ángulos, cada uno ±4 s alrededor de su pico de reacción
   (volumen RMS + densidad de palabras del .srt), cartel con el nombre del streamer arriba durante
   su tramo, orden de menos a más visto (el final es el ángulo más fuerte) y crédito a todos en la
   descripción. Sin pantalla dividida. Se parte de los mp4 verticales ya renderizados.
   **Cada ángulo tiene que MOSTRAR algo en su tramo**: se cuenta cuántos frames del tramo son un
   rectángulo casi negro (`multipov.frames_vacios_max`, más de un tercio = no sirve). Si un ángulo
   no pasa: (1) se rehace con fit_blur, que muestra el 16:9 entero; (2) si tampoco alcanza, se
   reemplaza por otro canal del mismo momento (se procesan hasta 2 más); (3) si no se llega a
   `min_angulos`, no se arma el multi-POV.
   **Verificación de "mismo hecho"** (tienen que pasar las DOS): superposición léxica entre las
   transcripciones (`multipov.superposicion_min`, 12 %) **y** una pregunta a Gemini. La léxica va
   primero porque es gratis: si no llega, no se gasta la llamada. Probado con los 5 grupos reales
   del 2026-09-24: el único que era de verdad el mismo momento (cuatro streamers recitando el mismo
   diálogo del evento) dio 36 %, y los otros cuatro 0, 2, 4 y 5 % — incluido el que se armó y salió
   mal. El umbral cae en el medio de esa separación.
8. Elegir con cupos por GRUPO (`seleccion.mezcla`: hoy 2 argentinos + 1 famosos; el catálogo es el
   fallback y compite ahí también toda carpeta con diarios que no esté en la mezcla).
   Cada grupo compite solo en su cupo; lo que un grupo no llena pasa al grupo `catalogo`, y si a ese
   le sobra vuelve a repartirse. Tope 1 por streamer entre todos, relleno incluido. Empate en el
   corte → Gemini (`empate_pct` por fuente: 3 % recientes, porque el score es logarítmico; 10 %
   catálogo). **Peso por votos** (`seleccion.peso_votos`, `votos_de` = Santi): el score se
   multiplica por 1 + 0,5 × (👍 − 👎) / (👍 + 👎 + 3) de sus votos a clips de ese streamer
   (`db.votos_por_streamer`, `seleccion.factores_votos`): entre ×0,5 y ×1,5, casi neutro con pocos
   votos (2 👍 → ×1,2). Ahí mismo va a entrar el factor por vistas de YouTube cuando exista §4b.
9. YouTube (SOLO con la auditoría aprobada; flag `youtube_upload_enabled`, default false):
   `videos.insert` privado con `publishAt` en el slot correspondiente. Guardar `video_id` en
   `clips.db` (tabla `posts`). Reintento con backoff; si falla 3 veces, alerta y se manda igual.
10. Telegram: por cada clip, el mp4 + botones **👍/👎** (el voto va a la tabla `votos` junto con el
    puntaje que le puso Gemini: con eso, en dos semanas, el corte de calidad se elige con datos —
    el puntaje desde el cual hay más 👍 que 👎, `db.votos_por_puntaje`) + un mensaje con `Título:` / `Descripción:` / `Hashtags:` /
    `Crédito:` en bloques copiables, id interno, horario sugerido, el recordatorio fijo
    **"Subir en PRIVADO → esperar Chequeos de copyright en Studio → si sale limpio, publicar"** y el
    `/reclamo <id>` listo para copiar. Santi sube a mano y responde con los links; el bot los asocia
    al clip en `posts` (esa 2ª mitad está pendiente).

### 3b. Modo en vivo (`/envivo on|off`, `clips_bot/envivo.py`)
Pedido 2026-09-27. Corre DENTRO de la escucha de Telegram (no hay servicio nuevo), solo si está
prendido: el interruptor es el chat guardado en `bot_estado.envivo_chat`, que es además adonde van las
alertas. Todos los streamers con permiso y sin reclamo, argentinos incluidos, de cualquier grupo.
1. Quién está al aire: Twitch en lote (`/helix/streams`, cada `envivo.intervalo_twitch_s` = 5 min);
   Kick canal por canal (`/api/v2/channels/{slug}` → `livestream`, cada 2 min, con `kick.pausa_s`).
2. Clips de los últimos `ventana_min` (15) de los que están en vivo. Kick: sin `sort` la API los da
   del más nuevo al más viejo, se pagina hasta pasar la ventana.
3. Momento = creadores DISTINTOS en el mismo canal a ±60 s de `vod_offset` o, si no hay offset, a
   ±90 s de hora de creación. **Twitch no da `vod_offset` mientras el stream está al aire** (medido:
   0 de 13 clips en vivo), así que en la práctica las dos plataformas agrupan por hora. Se arranca
   por el punto más denso: el que se alerta primero es el más clipeado.
   **Umbral RELATIVO al canal (decisión 2026-09-27, v0.24.1):** dispara con
   `max(min_creadores=4, factor_base=15 × ritmo)`, donde el ritmo son los clips de la última hora
   (`ventana_base_min`) que NO son del momento, repartidos parejo en ventanas de ±90 s. Solo se
   alertan los momentos que llegaron al umbral en los últimos 15 min. Simulado vuelta por vuelta
   sobre 72 h reales: **4,7 alertas/día**, el tope por hora no dispara nunca (tabla en settings.yaml).
   Dos bases se probaron y se tiraron antes de salir, las dos por tests: con los clips del momento
   adentro un canal tranquilo con un solo pico se ponía la vara a sí mismo; con la mediana de
   densidades, un pico anterior en la misma hora se volvía la base y el segundo no disparaba.
4. Del momento, el clip más visto que pase los filtros de siempre SIN la espera de 24 h. Si ninguno
   pasa queda `sin_clip` y se reevalúa en la vuelta siguiente (alguien puede hacer uno de 30 s).
5. Alerta en `envivo_alertas`. Nunca dos del mismo momento (clips en común o misma hora). Pasado
   `alertas_por_hora` (3) se anota como `tope`, para medir cuánto se pierde. Una pendiente que esperó
   turno más de `vencimiento_min` (60) queda `vencida`.
6. Procesar con el turno pesado, ANTES que la cola de `/buscar`. `procesar(..., permitir_fecha=True)`:
   todos los filtros de seguridad y tono corren, pero `depende_de_fecha` no descarta (para subir ya,
   que sea de hoy es lo que se busca). Sin textos de Gemini no se manda: el filtro de tono va en esa
   misma llamada. Los otros clips del momento se marcan vistos (`mismo momento (ya salió en vivo)`)
   para que mañana no salgan en la corrida diaria.
7. Se manda al chat que lo prendió con "🔥 SUBIR YA — N personas clipearon este momento de X hace
   M min", y el mensaje de siempre abajo.
**Tiempos por alerta** (ISO UTC en la tabla): `momento` (primer clip), `umbral` (cuando clipeó el
N-ésimo creador: desde ahí era detectable), `detectado`, `inicio` (después de esperar turno),
`entregado`, y `tiempos` por etapa de procesar. `/envivo` solo muestra las medianas de cada tramo
en las últimas 24 h. OJO: el tramo umbral → detectado mezcla el reloj de la plataforma con el de la
Pi; si da negativo o raro, mirar `timedatectl` (el Windows de desarrollo atrasaba 6 min).
`python -m clips_bot envivo [--ventana-min N] [--min-creadores N]` hace una pasada sin procesar ni
escribir nada, para calibrar.

**Replay del 2026-09-27 (clips reales de 72 h por la misma función, con los filtros):**

| min_creadores | momentos | pasan filtros | alertas con tope 3/h | horas con tope |
|---|---|---|---|---|
| 3 (el pedido) | 397 | 225 | 81 (~27/día) | 31 |
| 4 | 242 | 133 | 74 | 29 |
| 5 | 158 | 89 | 62 | 27 |
| 6 | 111 | 62 | 51 | 24 |
| 8 | 65 | 35 | 31 | 18 |

spreen solo da 2,2 momentos por hora de stream con 3 creadores (y está subestimado: pegó en el tope
de 1200 clips), davooxeneize 2,2/h pero 0 pasan (`programa_terceros`), lacobraaa 1,6/h y pasan 5 de
76 (fútbol). En Twitch es más raro: aldo_geo 0,7/h, juansguarnizo 0,4/h. De Kick, el 38 % de los clips
dura más de 60 s (`muy largo`). Entre el primer clip y el tercer creador pasan 59 s de mediana (p90
114 s). O sea: con 3 el tope por hora era lo que mandaba casi siempre, y eran ~27 procesados pesados
por día en la Pi. Por eso se pasó al umbral relativo (punto 3).

### 3c. Efemérides para el canal "Pequeña Historia" (`/efemeride [día/mes] [tema]`, `clips_bot/efemerides.py`)
Pedido 2026-09-27. Un Short por día con un hecho de la fecha. **Desde v0.27.4 va en la corrida de
las 05:00** (`efemeride_del_dia`, después de los clips y con el mismo turno pesado): completa la
música que falte, propone la de hoy y manda guion + hoja para aprobar a `efemerides.chat` o, si
está vacío, a los mismos destinos de la entrega diaria. Recién con ✅ se arma el video. Si no sale,
**la escucha de Telegram reintenta sola a las 07:00 y a las 10:00** (`efemerides.reintentos`,
estado en `bot_estado.efemeride_reintento`, con el turno pesado) y recién después del último
avisa por qué. Si la falla es de Gemini caído (`ErrorPasajero`), además suma un intento en una
hora, cada vez, hasta `textos.reintento_hasta` (22:00). También a demanda con `/efemeride [día/mes] [tema]`
(con tema, solo los hechos que lo mencionan: `/efemeride 28/09 penicilina`) y el CLI `efemeride`.
**Wikimedia (desde v0.28.3):** User-Agent con nombre, link al repo y el mail de
`WIKIMEDIA_CONTACTO` (.env) en todo pedido a Wikipedia, Commons y la música; SOLO miniaturas de
ancho estándar (1280, o 960 si el original no pasa de 1280; si no hay ninguna, la foto no se usa),
2 s entre descargas, Retry-After respetado (tope 120 s), caché en `data/cache_wiki/` (consultas
3 días, todo se borra a los 30), y una foto que no baja se saltea (3 × 429 seguidos cortan).
1. Wikipedia "On this day" en es y en (REST `feed/onthisday/events`). Primer filtro sin Gemini
   (`motivo_evento`): palabras sensibles (muertes, atentados, accidentes, desastres…), guerra desde
   1945, "durante siglos". Medido el 27/09: 108 hechos → 84 candidatos.
2. Gemini ordena los 8 más interesantes para público joven y, para cada uno, dice cuál de sus
   artículos es EL DEL HECHO: el primero de la lista suele ser el país ("Nicaragua" para el cierre
   de El Nuevo Diario traía fotos de playas y presidentes). Fotos y texto salen solo de ese artículo.
3. Fotos (`motivo_foto`, reglas fijas): licencia libre (PD, CC0, CC BY, CC BY-SA; nada de NC, ND,
   fair use ni GFDL sola), formato de foto (sin svg/gif), ≥ 800 px de ancho, y sin mapas, banderas,
   escudos, firmas, diagramas, logos ni imágenes duras (cadáveres, heridos: el artículo del Pacto del
   Eje traía un carro con muertos). Se piden miniaturas de 1280 px (ancho estándar de Wikimedia;
   con 1600 devolvía originales y upload.wikimedia.org daba 429). Las mismas reglas valen para las
   del artículo y para las que se buscan en Commons (`filtrar_infos`).
4. Guion (llamada 1, SIN fotos): solo con el texto del artículo (si es en inglés, se suma el
   equivalente en castellano para validar), con las reglas de claridad (§1) y, por cada frase,
   `mostrar` (qué se tendría que ver, en inglés, 2 a 5 palabras) y la `idea_clave`. Validación
   (`validar_guion` / `no_respaldados`): arranca con "Un día como hoy, en <año>,", cierra con
   gancho, 70-105 palabras (se le piden 80-100; mínimo 70 desde v0.30.1), `mostrar` en cada frase, y todo nombre propio, cifra, número con
   letras ("mil millones") y mes tiene que estar en el artículo. El primer guion real dijo "más de
   mil millones de búsquedas diarias" (de la memoria de Gemini): de ahí el chequeo de números.
4b. Fotos de cada frase (regla fija, `ilustrar.py` + `fotos_para_guion`): candidatas = hasta 8 del
   artículo + hasta 4 de Commons por frase (`Wiki.buscar_commons`: buscador con
   `filetype:bitmap` + la categoría que mejor coincide), todas bajadas (miniaturas, caché) y, en
   la llamada 2, Gemini ve el pool entero (tope 40) y ordena hasta 3 por frase, y descarta lo que
   no sirve. `asignar` elige sin repetir, `completar_distintas` llega a 6, `tramos` parte lo que
   pasa de 6 s. Con menos de 4 fotos de época → el siguiente del ranking (si ninguno llega, el
   de más fotos con aviso). Tope de 3 hechos intentados por día (`MAX_GUIONES`): caso normal
   1 + 3 × 2 = 7 llamadas a Gemini (más la voz).
5. Aprobación por Telegram: hoja con UNA FILA POR FRASE (`hoja_de_guion`: su foto, o sus dos si se
   parte, numerada, y la frase al lado; PIL, por las tildes), el guion con "[3→7] frase", la idea
   que tiene que quedar clara y los créditos. ✅ Aprobar · ✏️ Cambiar guion (reescribe y vuelve a
   buscar las fotos; el pool y lo descartado se conservan) · 🔁 foto N (la siguiente de la lista
   de esa frase; después, otra del pool). Sin ✅ no se sintetiza nada.
5b. **Videos en 2-3 frases de acción** (`videos_libres.py`, `efemerides.videos`, APAGADO hasta que
   Santi apruebe una muestra): Gemini marca `accion` en el guion (misma llamada); para esas frases,
   filmación de la época en Commons (licencias de las fotos) y archive.org (solo dominio público);
   si no hay, stock (Pexels/Pixabay con clave en el .env) o NASA si es de espacio; regla de época
   igual que las fotos (y Gemini confirma `video_de_epoca`). Gemini elige video y cuadro en la
   llamada de las fotos (ve 3 cuadros por video). La frase con video es UN tramo del largo de la
   frase (plan con `VIDEO` = -1), fit_blur con movimiento, sin su audio; si no baja, vuelve a foto.
   Hoja: el cuadro con "VIDEO" y la fuente; botones 🎬/🖼 frase N para cambiar antes de aprobar.
6. Video (`hacer_video`): la voz (Gemini TTS, respaldo Piper); con sus tiempos REALES se arma el
   plan de tramos (ninguna foto más de 6 s), fit_blur con zoom suave hasta 110 % sobre la foto
   agrandada 4× (zoompan redondea a píxel entero y a tamaño normal tiembla), hacia la cara más
   grande o al centro, el año grande los primeros 2 s, subtítulos palabra por palabra, audio con
   las reglas de §1. Créditos de cada foto (autor, licencia, link a Commons) al final de la
   descripción, en el orden en que aparecen.
CLI: `python -m clips_bot efemeride [--fecha 27/09] [--hecho penicilina] [--aprobar] [--propuesta <json>]`
(`--hecho`: solo los hechos que contienen esa palabra, para rehacer uno a mano).

### 3d. Pequeña Historia para Facebook (`/historia [día/mes] [tema]`, `clips_bot/locales.py`, `claude.py`)
Pedido 2026-11-09 (§1). Prueba de 2 semanas desde el 2026-11-10. Config en `historias_fb` de settings.
1. **Candidatos**: la página de cada día de Wikipedia en español ("10 de noviembre"), sección
   Acontecimientos con un lugar de Latinoamérica (`LUGAR_RE`: países, gentilicios, provincias,
   estados, ciudades) + nacimientos y fallecimientos de las personas que una celebración del día
   homenajea (La Pola el 14/11, Sor Juana el 12/11; se comparan sin "Sor/San" ni tildes:
   `homenajeado`). Afuera sin llamar a nadie: atentados, masacres, asesinatos, secuestros,
   torturas (`_DURO`) y guerras desde 1945. Las muertes, fusilamientos o accidentes pasan: con el
   criterio de Nacozari decide el modelo (acto heroico sí; tragedia sola, no).
2. **Haiku** clasifica todos en UNA llamada (`humana`, lugar, región, país, `tipo`
   heroe_de_pueblo/gente_comun/anecdota/momento_emotivo/fundacion/otro, `tragedia_sola`,
   `conmemora`, `interes` 1-10). Buenos = humana + lugar concreto + no tragedia sola; primero los
   que se conmemoran hoy. Con un hecho elegido a mano, Haiku clasifica el día entero (solo, un
   hecho lo juzga distinto: Epecuén dio "no es humana" sola y "gente común, 8" con el día) y no lo
   puede descartar.
3. **Sonnet** ordena hasta 8 y dice el artículo del hecho y el del lugar.
4. Guion con Sonnet (`SISTEMA_GUION_LOCAL` = el de siempre + "Un día como hoy, en <año>, en
   <lugar>," + lugar en el título y como hashtag, validado por `validar_lugar`); fotos con Gemini,
   primero las del artículo del lugar (se suman a las del hecho, mismas reglas fijas).
5. Aprobación igual que la efeméride (✅ ✏️ 🔁, encabezado "📘 SOLO FACEBOOK"); el video
   (`clip_id` historia_fb_…, `meta.efemeride.destino = "facebook"`) con la voz por la segunda clave;
   📤 → `_subir_facebook(hora=19:00)` y nada a YouTube; cada subida queda en
   `bot_estado.historias_fb_registro` (lugar, país, tipo, conmemoración, video_id) para comparar.
5b. **Calendario y calidad (2026-11-11):** los hechos del calendario de hoy (conmemoración con
   año, fundación, o `conmemora`) van primero (`locales.buenos`, `en_calendario`,
   `prioridad_pais`); `_calendario_tick` arma los 90 días y manda la semana los lunes; cada video
   pasa el control del 70 % de fotos reales (`ef.fotos_con_control`), y 📤 no sube a Facebook
   nada de un día que ya pasó.
6. **La escucha** (`_fb_tick`): desde las 06:30 y hasta las 21:00, una vez por día
   (`historias_fb_dia`), con el turno pesado libre. Un hecho fijado a mano: `historias_fb_hecho`
   = {"dia","hecho"} o `historias_fb_hecho:<AAAA-MM-DD>` = texto. Una falla se avisa y no se
   reintenta (para eso, `/historia`).
CLI: `historia-fb [--fecha 10/11] [--hecho Epecuén]` (propone sin Telegram) y `historia-fb --fecha
10/11 --contar-mes 30` (cuenta candidatos buenos por día con Haiku).
**Costo medido (Epecuén, 2026-11-09):** Haiku clasifica US$ 0,001; Sonnet elige US$ 0,007; cada
intento de guion US$ 0,058-0,063 (~6.500 tokens de entrada y ~4.500-5.000 de salida, casi todo
pensamiento); esa propuesta tuvo 2 intentos → **US$ 0,13**. Peor caso (3 hechos × 3 intentos)
≈ US$ 0,55; un ✏️ ≈ US$ 0,06. Más 1 llamada de Gemini por hecho (fotos) y 1 voz por video.

### 4b. Módulo de métricas (feedback loop)
**Hecho (v0.36.0, solo YouTube, `clips_bot/metricas.py`):** en la corrida de las 05:00, si hay
token de YouTube (`youtube-auth rots`, con el permiso `yt-analytics.readonly`), se listan los
Shorts del canal, se emparejan con los clips entregados POR TÍTULO (la subida es manual y el título
es el que generó el bot; similitud ≥ 0,85 y publicado después de la entrega) y se guardan por clip
en la tabla `metricas`: vistas, duración media vista, % visto medio y % que llega al final (curva
de retención en 100 %). Con eso la selección multiplica el score por streamer, duración (corto <30
s, medio <45, largo), layout y cámara: 1 + `peso_metricas` × log2(mediana del grupo / general),
±1 en el log, SOLO con `metricas_min_n` (15) Shorts por grupo. Lo de abajo (IG/FB/TikTok, reporte
semanal, snapshots) sigue pendiente.
Job cada 6 h: para cada post de los últimos 30 días, pedir vistas/likes/comentarios/shares
(YouTube `videos.list` + Analytics API para retención promedio; Meta Graph insights para IG/FB;
TikTok Display API para la cuenta propia). Guardar snapshots a 24 h, 72 h y 7 d.
Cada clip queda etiquetado con: streamer, categoría/juego, duración, hora de publicación,
plataforma, tiene_cámara, tipo de gancho del título, palabras clave de la descripción.
Reporte semanal por Telegram: mediana de vistas a 7 d por streamer, por duración, por horario y
por plataforma; top 5 y peores 5 con su título.
Uso en la selección: el score de candidatos (§3 paso 8) incorpora un factor por streamer y por
duración derivado de la mediana a 7 d. REGLA: ajustes suaves y solo con n ≥ 15 por categoría;
con menos datos el bot solo informa, no cambia pesos. Con ~90 videos/mes recién al segundo o
tercer mes hay señal real. Las vistas a 24 h son ruidosas (las plataformas testean al azar);
la métrica que manda es la mediana a 7 d, y en YouTube la retención promedio.
Acá también entra la exclusión automática por reclamo de copyright (§1): mismo camino que
`/reclamo`, llamando a `db.excluir_streamer` y avisando por Telegram.
Si TikTok Display API se complica: carga manual semanal de números en una planilla que el bot lee.

---

## 4. FILTRO DE MÚSICA (crítico)

Sin herramienta perfecta gratis. Enfoque en capas, descartar si cualquiera dispara:
- El título/categoría del stream en Twitch es "Music" o "Just Chatting" con "music" en el título.
- Análisis espectral simple con `librosa`: si hay energía tonal sostenida y ritmo estable
  (tempo detectado con confianza alta) durante > 40 % del clip → probable música. PENDIENTE.
- Whisper devuelve muy pocas palabras para la duración → probable música/gameplay puro.
Falsos positivos aceptados: preferimos tirar 2 clips buenos que subir 1 con música.

---

## 5. FASES

**Fase 0 — Cuentas (lo hace Santi):**
- Canal de YouTube nuevo (nombre neutro, no el de un streamer).
- Cuentas de TikTok, Instagram (Creator, vinculada a una página de Facebook) y Facebook.
- Proyecto en Google Cloud → habilitar YouTube Data API v3 + YouTube Analytics API → credencial
  OAuth "Desktop app" → `client_secret.json` a `config/`. Scopes `youtube.upload` + lectura.
- App en Twitch Developer Console → client id + secret. HECHO.
- Bot de Telegram nuevo (BotFather) → token + chat id. HECHO (@Clipsito_bot).
- Todo va a `.env`, nunca al repo.

**Fase 1 — MVP local (Windows), sin upload:** pasos 1–8 del pipeline. Salida: 3 mp4 en `output/`
por corrida. Criterio de listo: Santi mira 10 Shorts generados y ≥ 7 le parecen publicables.

**Fase 2 — Telegram + Pi + auditoría:** paso 10 (entrega manual de todo, YouTube incluido),
deploy systemd + timer. Objetivo: 2 semanas seguidas sin fallar. Con ~20 Shorts subidos a mano
y públicos en el canal real, pedir la auditoría de la YouTube Data API.
En paralelo se desarrolla el paso 9 (`videos.insert` + `publishAt`) y se prueba SOLO contra un
canal descartable (sus videos van a quedar bloqueados privados, da igual). Primer OAuth
interactivo en Windows; el token cacheado se copia a la Pi. Recién con la auditoría aprobada se
activa `youtube_upload_enabled` contra el canal real.

**Fase 3 — Métricas:** módulo §4b con YouTube Data + Analytics (OAuth de lectura; funciona sin
auditoría para el canal propio), Meta Graph (cuenta Creator + página) y TikTok Display API.
Reporte semanal. Ajustar umbrales según datos.

**Fase 4 — Evaluar (a los 60–90 días):** ¿hay tracción (Shorts con > 10k vistas de forma
repetida)? Si sí, escalar streamers y contactar a los mejores con números en la mano. Si no,
replantear nicho o cerrar.

---

## 6. LO QUE FALTA INVESTIGAR

- [ ] Términos de servicio de Twitch sobre redistribución de clips y VODs (qué dicen exactamente).
- [ ] Términos de Kick sobre clips y sobre usar su API interna (no documentada).
- [x] Auditoría de la YouTube Data API: CONFIRMADO que sin auditoría los uploads por API quedan
      bloqueados privados para siempre; `videos.insert` = 1600 unidades (doc oficial).
      Pendiente solo: qué pide el formulario y cuánto tarda la aprobación.
- [x] Cuota de Gemini: el free tier es ~20/día y el bot usa ~30; pagar el principal saldría
      ≈ US$4-8/mes (docs/costo-gemini.md). Decisión de Santi.
- [ ] Qué devuelve exactamente TikTok Display API para la cuenta propia (vistas/likes por video) y
      qué necesita Meta Graph para leer insights de Reels de una cuenta Creator.
- [ ] Ruta de monetización realista para clips: AdSense Shorts exige 10 M vistas de Shorts en
      90 días; alternativas (patrocinios, acuerdos con streamers) y qué numerito hace viable cada una.
- [ ] Benchmark en la Pi (aarch64) de `faster-whisper small` + render x264 por clip de 60 s
      (referencia Windows en §8).

---

## 7. MÉTRICAS QUE DEFINEN SI ESTO SIRVE

- Vistas a 24 h y 7 d por Short (mediana, no promedio).
- % de Shorts con reclamo de copyright o bloqueados (objetivo: 0; si aparece uno, el streamer
  queda excluido automáticamente).
- Suscriptores/semana.
- Costo real: Gemini $0 con el free tier (que se agota casi todos los días: ~30 llamadas/día de
  las ~20 gratis); pagando el modelo principal, ≈ US$4/mes hasta dic. 2026 y ≈ US$8/mes desde
  2027 (docs/costo-gemini.md, calculado 2026-09-28; nada pago activado). API YouTube $0,
  electricidad de la Pi.

---

## 8. ESTADO DEL CÓDIGO

Python 3.13, deps en `requirements.txt`. Además, ffmpeg con libass (Windows: `winget install
Gyan.FFmpeg`, ya instalado 9.0.2; Pi: `apt install ffmpeg`). Si la consola no ve ffmpeg en el PATH,
el código lo busca en la instalación de winget o en `FFMPEG_DIR`.

```
config/settings.yaml     candidatos, evento, kick, catalogo, render, camara, subtitulos, filtro_audio,
                         marcador, pantalla, textos, seleccion, publicacion, youtube_upload_enabled
config/streamers.yaml    la lista "de autor". Las altas y bajas por Telegram NO se escriben acá:
                         van a la DB y se combinan al cargar (`registro.combinar`), porque el YAML
                         está en git y si el bot escribiera acá cada alta sería un conflicto en el
                         próximo `git pull` de la Pi. La DB manda sobre el YAML.
                         login, plataforma, fuentes, grupo, permiso (cita/fuente o experimento),
                         subtitulos_propios, detectar_marcador, palabras_programa, layout_forzado,
                         apodos (para 🔥; los de /streamers van a la tabla `apodos` y mandan)
                         + sección evento_dedsafio
.env                     TWITCH_*, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                         TELEGRAM_ALLOWED_USERS (ids que pueden mandar comandos; vacío = ninguno),
                         WIKIMEDIA_CONTACTO (mail del User-Agent de Wikimedia),
                         GEMINI_API_KEY_2 (segunda clave: solo con la principal sin cuota del día),
                         YOUTUBE_API_KEY (búsqueda de 🔥)
clips_bot/config.py      carga YAML + .env; Streamer.permitido = cita o experimento
clips_bot/twitch.py      Helix: token, /users, /search/channels, /clips (paginado o página con
                         cursor), /games, /videos (título del stream)
clips_bot/kick.py        API interna de Kick: clips por canal (sort=view&time=week), a_clip() los aplana,
                         get_session_titles() = títulos de stream por livestream_id (/videos)
clips_bot/candidates.py  pasos 1–2 de las 3 fuentes: filtros, es_costream, agrupar_momentos,
                         agrupar_evento/consolidar_evento, cursor del catálogo
clips_bot/download.py    paso 3: yt-dlp (Twitch y Kick) → output/raw/
clips_bot/media.py       ffmpeg/ffprobe: ubicar binario, probe, fracción de silencio, miniatura, y la
                         regla fija 3 (§1): `cola_audio`, `audio_con_crossfade`, `chequear_audio`
clips_bot/deportes.py    marcador de transmisión deportiva: esquina quieta + mucho borde (heurística)
clips_bot/pantalla.py    paso 4b: OCR (tesseract) → mails, teléfonos, tarjetas, pago, dirección
clips_bot/subtitles.py   paso 6: faster-whisper → subtítulos ≤ 2 líneas → SRT + ASS
clips_bot/layout.py      paso 5: caras (OpenCV Haar) → split / fullcam / fit_blur + chequeo
                         post-render (`cara_cortada_en_render`)
clips_bot/render.py      pasos 5–6: una pasada de ffmpeg, tope 5 Mbps (entra en los 50 MB de Telegram)
clips_bot/gemini.py      cliente REST generateContent con responseSchema (JSON forzado)
clips_bot/textos.py      paso 7: título/descripción/hashtags/gancho/depende_de_fecha + crédito
clips_bot/multipov.py    paso 7b: pico de reacción, ventanas, carteles, concat y medición del
                         panel de cada tramo (medir_panel / panel_vacio)
clips_bot/benchmark.py   `benchmark`: tiempos por etapa y comparación de modelos de Whisper
deploy/                  systemd (timer 05:00 AR + escucha de Telegram + alerta), logrotate,
                         instalar.sh y README con el orden del deploy en la Pi
clips_bot/seleccion.py   paso 8: score por fuente, cupos por grupo con fallback, desempate Gemini
clips_bot/telegram.py    paso 10: sendVideo (width/height/duration + miniatura), mensaje con bloques
                         copiables + recordatorio, getUpdates, comandos con user_id y
                         usuarios_permitidos (TELEGRAM_ALLOWED_USERS)
clips_bot/process.py     orquesta 3–7 por clip, tiempos por etapa, registra estado en la DB
clips_bot/db.py          SQLite data/clips.db: clips, posts, catalogo_cursor, streamer_estado
                         (exclusiones), votos (👍/👎 con el puntaje), streamers_extra (altas y
                         bajas por Telegram), bot_estado (offset, turnos, estado de los menús)
clips_bot/registro.py    altas/bajas/mover en la DB + `combinar` con el YAML + `resolver` un alta +
                         `filtrar` por los interruptores de las carpetas (en_vivo, diarios)
clips_bot/menu.py        teclados de /streamers y /agregar (callback_data de 64 bytes como tope)
clips_bot/narrar.py      modo /narrar: guion con Gemini viendo frames, TTS con Piper, mezcla y
                         subtítulos sacados de LA VOZ (no del audio original). Videos de más de
                         90 s: resumen por escenas (ver abajo)
clips_bot/__main__.py    CLI + todo el bot de Telegram (comandos, menús, cola, turnos)
deploy/sudoers-clips-bot permite a santi reiniciar SOLO las unidades del clips-bot sin contraseña
voces/                   modelos de Piper (NO están en git: ~110 MB, se bajan en la Pi)
clips_bot/youtube.py     subida a YouTube (apagada): OAuth, upload reanudable con publishAt, cancelar
clips_bot/musica.py      biblioteca de música de Pequeña Historia (docs/musica.md)
clips_bot/efemerides.py  Pequeña Historia (§3c): Wikipedia/Commons, filtros de eventos y fotos, guion
                         validado contra el artículo, hoja de aprobación y el video con zoom
clips_bot/serie.py       /serie: partes, división en etapas (validada), guiones encadenados,
                         título numerado, horarios, hoja de miniaturas por etapa
clips_bot/facebook.py    Reels de Pequeña Historia a la página de Facebook (apagado; docs/facebook.md)
clips_bot/parallax.py    fotos con parallax 3D (GrabCut + inpaint + dos capas)
clips_bot/graficos.py    año contando, mapa con el punto, palabras clave grandes, whoosh
clips_bot/vod.py         buscar un Short en el VOD (audio 160p, huella, FFT)
clips_bot/videos_libres.py videos de las frases de acción (Commons, archive.org, Pexels, Pixabay, NASA)
clips_bot/ilustrar.py    regla fija 1 (§1): una foto por frase sin repetir, mínimo 6 distintas,
                         ningún tramo de más de 6 s (`asignar`, `tramos`, `errores_plan`)
clips_bot/reglas.py      regla fija 2 (§1): REGLAS_CLARIDAD, dentro de todos los prompts de guion
clips_bot/pego.py        lo que pega en otros canales → el clip original (búsqueda, audio, bonus)
clips_bot/audio_huella.py ¿mismo momento? audio a 8 kHz en 16 bandas + correlación con desfase
clips_bot/chat.py        picos de chat de Twitch (GQL interno, una página por pedido) ÷ ritmo del VOD
clips_bot/metricas.py    §4b: métricas de los Shorts del canal y pesos por streamer y tipo
clips_bot/claude.py      texto con Claude (SDK oficial `anthropic`, ANTHROPIC_API_KEY): misma forma
                         que GeminiClient.json; schema de Gemini → JSON Schema; uso en gemini_uso
                         con clave "claude"; Sonnet con fallbacks "default"
clips_bot/elevenlabs.py  ElevenLabs para Así Nació: voz de Tito, efectos, créditos (suscripción + elevenlabs_uso)
assets/sfx/              biblioteca de efectos de Así Nació generada una vez con ElevenLabs (+ biblioteca.json)
clips_bot/animacion/     canal Así Nació (prendido): personajes/escenas SVG, línea de tiempo en JSON, render
                         cairosvg → ffmpeg; marcas.py (catálogo, rotación, guion, revisión visual, video),
                         tito.py (locutor), acciones.py, sfx.py, subtitulos_virales.py + letra.py
                         (Montserrat Black como trazos), mascotas.py (las 4 opciones originales)
clips_bot/animacion_remotion/ + remotion/  prototipo de Así Nació con Remotion (no en producción)
assets/fuentes/          Montserrat Black + OFL.txt
clips_bot/locales.py     §3d: historias de Latinoamérica (Wikipedia por día + la web, Haiku, Sonnet)
clips_bot/web_historias.py §1: búsqueda web con Haiku (diarios, museos, archivos) y verificación con 2 fuentes por dato
clips_bot/animacion/reemplazo.py §1: la escena que no pasa el estándar → una aprobada de la biblioteca (Haiku, empalme)
clips_bot/calidad.py     §1: el estándar de calidad (ESTANDAR_CALIDAD.md): revisión, registro y resumen de los lunes
clips_bot/stats_fb.py    §1: el resumen de cada Reel de Facebook a las 24 h (Pequeña Historia y Así Nació)
clips_bot/comunidad_fb.py §1: publicaciones de comunidad de Pequeña Historia (foto de época + pregunta)
clips_bot/animacion/uso_v3.py §9 v1.22.0: escenas de uso con las manos, plata de verdad e inspiración (uso_manos)
clips_bot/animacion/gancho_v3.py §1: reglas_v3 de Así Nació (gancho de 3 cortes, planos, opciones)
clips_bot/calendario.py  §3d: calendario de 90 días de fechas de Latinoamérica + la lista de los lunes
clips_bot/medicion_ph.py §1: seguimiento por video (segundo en que se va la mayoría en FB, % que se queda en YT calibrado con Studio, empujones)
clips_bot/voces.py       voces de Gemini de hoy por clave (con Lo Encontré) y el aviso cerca del tope
clips_bot/prueba_manual.py prueba manual vs API (§1): el clip del día a mano, registro e informe del feed
clips_bot/envivo.py      modo en vivo (§3b): quién está al aire, momentos por creadores distintos,
                         alertas en la DB (no repetir, tope, vencer) y el resumen de tiempos
tests/                   1687 tests sin red ni video (conftest.py: nada sale a YouTube, Facebook ni ElevenLabs) (test_reglas_fijas.py: las 3 reglas de §1)
```

Comandos:
- `diario [--simular] [--max-procesar N] [--incluir-sin-permiso]` — la corrida del timer de systemd:
  atiende Telegram → pasos 1–2 de las dos plataformas → procesa por grupo solo hasta llenar su cupo
  → multi-POV si corresponde → paso 8 → entrega. `--simular` hace todo menos el envío.
- `candidatos [--json] [--incluir-sin-permiso] [--avanzar-cursor]` — lista recientes y catálogo;
  guarda en la DB los descartes `costream`. Por default NO mueve el cursor del catálogo.
- `procesar <url> [<url> ...] [--forzar] [--fuente reciente|catalogo]` — pasos 3–7 de una o más URLs
  (Twitch o Kick). Sin `--fuente`: catálogo si el clip tiene ≥ 7 días.
- `seleccionar [--n N] [--enviar]` — paso 8 sobre los `procesado`. Antes de elegir genera los textos
  faltantes y descarta los que dependen de la fecha. El envío rechaza streamers sin permiso.
- `multipov <id1> <id2> [id3]` — arma el Short multi-POV con clips YA procesados.
- `atender-telegram` — procesa los comandos. `diario` lo corre al principio y el offset de
  getUpdates queda en la DB. Solo obedece a los ids de `TELEGRAM_ALLOWED_USERS` (vacío = nadie).
  - `/reclamo <id del clip>` — marca el reclamo, excluye al streamer y responde.
  - `/ya` — corre la mezcla diaria en el momento. Mismo turno pesado y misma cola que `/buscar`;
    no atiende Telegram por dentro (le robaría los updates al modo escucha).
  - **Desde v0.40.0, con botones:** `/buscar spreen` a secas pregunta el período (Últimos 7 días,
    Últimos 30 días, Viejos (más de 30 días), 🔥 Lo que pegó en otros canales) y la cantidad (1, 3,
    5); en /streamers, el período sale al elegir el streamer. Con todo en el comando
    (`/buscar spreen 30 x5`, `viejos`, `pego`) o con palabras, no pregunta nada.
  - `/buscar <streamer[,streamer]> [palabras] [días]` — busca a mano en los clips de esos
    streamers (hasta 3, separados por coma; el tope se reparte de a uno por vuelta, así lo que a
    uno le sobra lo usa otro) de los
    últimos N días (default 7, tope 90) los que tengan las palabras **en el título del clip o en el
    del stream**, con todos los filtros de siempre. Contesta "buscando…" con cuántos candidatos
    encontró, procesa hasta `TOPE_BUSCAR` (3) y los manda con el formato habitual; al final, el
    resumen de descartes, que es la mitad útil (dice POR QUÉ no quedó nada). Los días son el último
    argumento y solo si es un número, así `/buscar davoo 12 de octubre` busca esas palabras.
    Máximo `MAX_BUSQUEDAS` (2) a la vez, contando otros procesos: el turno se guarda en la DB
    (`bot_estado`) con vencimiento, porque cada búsqueda son 3 clips de Whisper + OCR + render y eso
    calienta la Pi y gasta cuota de Gemini. **El filtro de palabras corre ANTES del corte al top N**
    (si no, los clips sin las palabras se comen los lugares: es el mismo bug de orden que ya pasó
    con el evento y con los candidatos de Kick).
  - `/streamers` — menú con botones, **editando siempre el mismo mensaje**: grupos → streamers
    (2 columnas, 12 por página, ◀️ ▶️, ⬅️ Volver) → qué buscar (7 días / 30 días / con palabra).
    Los excluidos salen con 🚫 y su botón no lleva a ningún lado. Cualquier búsqueda dispara el
    `/buscar` de siempre, con la misma cola. Telegram corta el `callback_data` en **64 bytes**, así
    que viajan índices (`st:s:2:37`) y no logins: con los 54 del Dedsafío varios no entrarían.
  - `/agregar <login> [grupo]` (default `argentinos`) — lo busca en Kick y en Twitch, contesta qué
    encontró (seguidores y clips de la semana) y lo suma con ✅/❌. **No usa "Kick primero" a
    secas**: medido 2026-09-25, `vegetta777` en Kick es un slug ocupado con 166 seguidores y 0 clips
    mientras el Vegetta real está en Twitch, y `momo` en Kick tiene 707 y 0. Lo que decide es tener
    clips en 7 días. Si el que coincide exacto tiene menos de `CLIPS_SIN_DUDA` (20), se muestran
    también los parecidos y elegís vos: "momo" da un canal con 7 clips que es un gato espacial en
    inglés, no el Momo argentino.
  - `/quitar <login>` — lo saca de las corridas.
  - `/ayuda` — lista los comandos con un ejemplo copiable de cada uno (sale de `COMANDOS` en
    `__main__.py`, y hay un test que exige que todos tengan ejemplo).
- `telegram-chat-id` — lista los chats de getUpdates y los ids de usuario (TELEGRAM_ALLOWED_USERS).
  - `/envivo on|off` — modo en vivo (§3b); `/envivo` solo muestra el estado, la última vuelta y
    las medianas de cada tramo de tiempo en las últimas 24 h.
- `efemeride [--fecha 27/09] [--aprobar] [--propuesta <json>]` — Pequeña Historia sin Telegram (§3c):
  propone y deja `hoja.jpg`, `aprobacion.txt` y `propuesta.json` en `output/efemerides/<mmdd>/`;
  con `--aprobar` arma el video (necesita Piper: en la Pi).
- `envivo [--ventana-min N] [--min-creadores N]` — una pasada del modo en vivo sin procesar ni
  escribir: quién está al aire y qué momentos dispararían. Para calibrar.
- `benchmark [--clips N] [--modelos small,base] [--limite-s S]` — mide OCR, Whisper (carga y
  transcripción por modelo), detección de cámara y render sobre los mp4 que ya están en
  `output/raw/`; no descarga nada. Dice si entra en el tope por clip y deja un `.srt` por modelo
  para comparar la calidad. Es el primer paso del deploy en la Pi (ver `deploy/README.md`).

Textos (paso 7): Gemini con `responseSchema`; igual se valida todo (claves exactas, título ≤ 59 sin
# ni saltos, descripción sin hashtags ni links, 3–5 hashtags de una palabra con #Shorts, gancho del
enum, depende_de_fecha booleano). Si no valida, reintenta hasta 3 veces con los errores. El crédito
lo agrega el código, no Gemini. Modelo: `gemini-3.6-flash` fijo (2.5-flash da 404 para cuentas nuevas).

Tiempos medidos (Windows, 8 hilos, clips de 17–60 s): descarga 1–4 s · silencio 0,1–0,5 s · cargar
Whisper 2–11 s · transcribir 0,17–0,55× la duración · OCR 3–11 s · detectar cámara 4–9 s · render
0,5–1,4× la duración · Gemini 7–30 s. Total 45–170 s por clip (con `spa+eng`, 40–76 s en 2 clips).

**Whisper en la Pi (aarch64, 2026-09-23).** Cargar el modelo: `small` 59 s la primera vez (baja
467 MB), `base` 21 s. Transcribir, clips normales: `small` 0,70× (60 s) y 1,53× (22 s); `base` 0,97×
y 0,57×. O sea que `small` ENTRA cómodo para 3 clips/día. Calidad: `small` es claramente mejor —
mantiene los signos de pregunta ("¿Estás aquí atrás, verdad, gordita?" contra "estás aquí atrás,
verdad gordita,") y acierta palabras que `base` inventa ("no hay manera" contra "no es manera hue").
**Se queda `small`.**
El problema no era el modelo: un clip de 17 s se fue a 483 s (28×) con `small` y 198 s con `base`.
Es un audio de gritos sin habla clara donde el decoder entra en loop. Probado `beam_size=1` y
`condition_on_previous_text=False`, solos y juntos: 27–37× en los cuatro casos, y lo que sale es
"no no no no". Por eso ahora hay un tope de tiempo por clip
(`subtitulos.timeout_factor` × duración, mínimo `timeout_min_s`): se corta entre segmentos y el clip
se descarta con motivo `transcripcion_lenta`.

Streamers cargados (2026-09-22; revisado 2026-09-28). Mezcla diaria: **2 argentinos + 1 famosos**,
y el catálogo sin cupo propio como fallback. El evento ya no está en los diarios.
- **famosos** (1, desde 2026-09-28): auronplay (Twitch, 100 clips en 7 d, verificado con
  `registro.resolver`).
- **argentinos** (8, todos Kick, resueltos con clips en los últimos 7 días): davooxeneize (100 clips
  en 7 d), spreen (100), lacobraaa (94), coker (97), goncho (67), brunenger (62), mernuel (57),
  coscu (19). Con `detectar_marcador` (hablan de fútbol): davooxeneize, lacobraaa, coker.
  Afuera por 0 clips en 7 d: Frankkaster, Carreraaa. Afuera porque no se encontró su cuenta real
  (los slugs libres tienen 9–704 seguidores): Momo, Luquitas Rodríguez, Marito Baracus.
- **evento** (54): participantes del Dedsafío, 40 con señal de Minecraft/dedsafío y 14 sin señal
  (marcados en el YAML). Sin resolver, NO cargados: rubinavx, Dlffrent, MontokaAtr, CherryToragao,
  Maau, FalloSinEmision, Albaclouthier, Juliandns_.
- **catalogo** (1): vegetta777.

Dos bugs de orden encontrados con corridas reales (los dos del mismo tipo: un filtro o una
asignación corriendo después de lo que debía):
1. `buscar_candidatos` (Twitch) **asignaba** `res.candidatos` en vez de sumar, y borraba los de Kick:
   Davoo traía 60 clips y su cupo quedaba vacío sin motivo visible.
2. El filtro del evento corría DESPUÉS del corte al top N: los clips de Just Chatting de los mismos
   streamers del Dedsafío se comían los 8 lugares y el cupo del evento quedaba en cero. Ahora se
   descarta antes de ordenar (429 descartes por "fuera del evento" en la corrida del 2026-09-22).

Cuota de Gemini (medido 2026-09-22): el free tier de los modelos Flash está en **~20 requests por
día**, con reseteo a medianoche hora del Pacífico (bajó de 250; la doc ya no publica el número por
modelo, remite a AI Studio). La cuota que se agotó ese día fue por las pruebas, no por el uso normal:
3 clips/día × 1 llamada = 3, más algún desempate. Por eso: UNA llamada por clip (título, descripción,
hashtags y depende_de_fecha juntos), `reintentos` 2, y ante un 429 por cuota se pasa al
`modelo_fallback` (flash-lite, que tiene su propia cuota) en vez de reintentar el mismo. Si igual no
hay cuota, el clip queda con `textos_pendientes: true` en su json, conserva el render, y `seleccionar`
lo reintenta en la corrida siguiente.

Fútbol en Davoo (calibrado 2026-09-22 con 8 clips reales): el marcador de TV NO alcanzaba — un clip
que es una transmisión de fútbol con la cámara sobre la tribuna medía quietud 0,0 y bordes 0,0, y
tampoco lo agarraba el filtro de palabras (título "AGUSNETA", categoría "Just Chatting"). La segunda
señal, fracción de verde-césped, sí lo agarra: 68 % de césped en 2 de 12 frames, contra un máximo de
26 % en los clips de Minecraft, WoW, IRL y LEC (ninguno dispara). Umbral: 45 % en ≥ 2 frames, con
muestreo del 3 % al 97 % del clip (con 10 %–90 % la cancha aparecía en un solo frame). Respaldo real:
los Chequeos de copyright de Studio detectan transmisiones de partidos por Content ID antes de
publicar, así que el riesgo queda cubierto aunque la heurística falle.

**El multi-POV que salió mal (2026-09-24), en detalle.** Short "Reconoce que no conoce a Zelda 😅"
con tres momentos sin relación. Horas de creación: rivers_gg 02:04:18, gamstergaming 02:05:31,
pattymeza 02:06:25 — los tres en Minecraft y dentro de la ventana de 2 min, pero eran el menú de
pausa, unos créditos y una despedida. Era el último día de GeoWare: mucha gente clipeando a la vez
cosas distintas. Peor todavía: el clip ancla era un **memorial** ("En memoria de ZELDA, 15 NOV 24 –
14 DIC 25", con fotos de un perro muerto), o sea un duelo convertido en Short con emoji. El clip y
el multi-POV quedaron descartados con motivo `memorial / duelo`. **No hay ninguna capa que detecte
contenido sensible** (memoriales, accidentes, malas noticias): el OCR de §4b busca datos personales,
no tono. Ese título, además, NO lo agarra la validación nueva: "Zelda" sí estaba en la transcripción.

Subtítulos quemados por el streamer (detectado 2026-09-24 con OCR + cruce contra la transcripción:
si el texto en pantalla coincide con lo que se dice, son subtítulos en vivo; un HUD no). Sobre los
6 clips del evento ya procesados: **rivers_gg, arigameplays y gamstergaming** los tienen (5 a 8
palabras coincidentes en el decil de abajo); renrize tiene texto abajo pero 0 coincidencias (HUD);
pattymeza y filisgg, nada. Los tres quedaron con `subtitulos_propios: true`, confirmado mirando los
frames.

**Filtro de tono y puntaje de calidad (2026-09-24).** Antes de programarlos se pasaron los 10
últimos entregados por los criterios: con el puntaje sacado SOLO de la transcripción se habrían
descartado 9 de 10, porque el humor visual no se puede juzgar leyendo. Medido sobre 30 clips: de los
24 que no llegaban a 6, 13 estaban marcados como "solo se entiende con la imagen", con mediana 4,0
contra 5,0 del resto (1,60 palabras/s contra 2,45). Por eso van 4 frames en la llamada. Corte
provisorio en 5; el definitivo sale de los votos 👍/👎 en dos semanas.

**El crash del 2026-09-25 y lo que se arregló alrededor.** `/buscar` sobre un streamer de Twitch
tumbaba la escucha entera: `TwitchClient(load_twitch_creds())` sin desempaquetar. Tres arreglos:
(1) una sola forma de armar el cliente (`_twitch()`), con un test que pasa por las dos plataformas;
(2) cada comando corre dentro de `_seguro`, que atrapa cualquier excepción, deja el traceback en el
log, contesta por Telegram y deja el bot escuchando; (3) lo que falla no vuelve a la cola. Además,
systemd había llegado al `StartLimitBurst` y se plantó: un `restart` contesta "Start request
repeated too quickly" y hace falta `reset-failed` primero, así que ahora la alerta trae ese comando.
Y `alerta.sh` tenía DOS retornos de carro reales metidos en el código (uno partía un comentario en
dos, el otro hacía que `tr` borrara también los saltos de línea del `.env`, que quedaba en una sola
línea): la alerta estaba rota desde que se "arregló" el CRLF.

Problemas abiertos:
- **Co-streams por URL manual:** `procesar` solo ve título y categoría del clip; el título del
  stream (vía /videos) solo está en `candidatos`.
- **Subtítulos en vivo cortados:** con `subtitulos_propios`, el crop 9:16 corta los costados de los
  subtítulos del streamer si ocupan todo el ancho (visto en elxokas). Con fit_blur ya no pasa, pero
  elxokas cae en split, que sí recorta.
- **fit_blur usa menos pantalla:** el video ocupa 1080x608 de los 1920 de alto. Es el precio de no
  cortar nada. Si los datos muestran que rinde peor que un recorte, la alternativa es un zoom suave
  hasta el límite en que no se corte ninguna cara ni el HUD.
- **El OCR de la pantalla ve lo que tesseract puede leer.** Texto chico o sobre fondo con textura
  se pierde, y el modelo instalado es `eng` (sin `spa`). Es una red, no una garantía: un documento
  o una dirección escritos a mano, o en un video dentro del video, no los ve nadie.
- **La regla de "caras en la zona del juego" tiene poco margen.** Calibrada con 11 clips: 25 % y
  30 % (coker) contra 10 % del resto, y solo separa sumando un mínimo de ancho de cara. Con más
  datos puede hacer falta moverla.
- **`procesar` por URL no puede aplicar `palabras_programa`**: no tiene el título del stream (mismo
  problema que los co-streams por URL manual).
- **Franja de UI al pie de la cámara** (split): mitigada recortando 50 px + línea negra de 6 px;
  queda un filo del fondo del overlay. Sigue sin detectar los bordes reales del overlay.
- **Kick sin `sort=view` es inservible:** devolvía 100 clips de menos de 24 h con 2 a 5 vistas.
  Kick también podría alimentar el catálogo (`sort=view` sin `time`, clips de hasta 265.000 vistas):
  no está conectado.
- Capa `librosa` del filtro de música (§4): pendiente.
- Respuesta de Santi con los links de TikTok/IG/FB → tabla `posts`: pendiente.
- El multi-POV compite en la selección junto al clip individual del mismo momento.
- La detección de césped puede dar falsos positivos con juegos de campo abierto muy verde (un
  Minecraft de pradera llegó a 26 %, cerca del umbral de 45 %). Solo corre en streamers marcados.

---

## 9. CHANGELOG

- v1.61.0 (2026-11-25, noche) — Música e ídolos con sorpresa o momento épico en vez de peligro; videos de Latinoamérica
  guardados para un día (`guardar_latam`, `_entregar_guardado_latam`, CLI `guardar-latam`).
- v1.60.0 (2026-11-25, noche) — Banco de Latinoamérica por tema con la búsqueda web de Haiku; cortes según las fotos
  (más largos con movimiento, sin tarjetas de relleno) y guion sin frases abstractas, con los productos nombrados (reglas en
  §1). Cambian dos reglas viejas: "ninguna foto más de 4 s seguida" pasa a 6 s cuando faltan fotos, y el gancho de 2,5 s
  solo si su frase tiene otra foto. `tests/test_tema_primero.py`, `test_calidad_calendario.py`, `test_edicion_nueva.py`.
- v1.59.0 (2026-11-25, tarde) — **Tema primero en Latinoamérica** (regla en §1). Por qué entró Concordia: el banco
  la tenía con 8,25 (Haiku le dio persona 9, peligro 7, giro 8, emoción 9 a una estación de tren), la cosecha del banco
  solo sacaba las de la sección "fundación" de Wikipedia y esta venía de la historia de una ciudad, y para la prueba yo
  la elegí a mano porque tenía fotos. El banco tenía 12: 6 de próceres, batallas o fundaciones. `tests/test_tema_primero.py`.
- v1.58.0 (2026-11-25) — (1) **Despliegue seguro** (`deploy/desplegar.sh`): el código nuevo se prueba en un worktree con
  el settings.yaml y el .env de la Pi (`chequeo-arranque` + tests) antes de actualizar; recién sin trabajo pesado se
  actualiza y se reinicia en el mismo momento, y si la escucha no arranca vuelve al commit anterior. Un proceso andando
  que relee un settings.yaml que no carga sigue con la última configuración buena (`config._ULTIMA_BUENA`). Motivo: a
  las 09:39:52 del 25/11 la escucha vieja releyó el settings con `fotos_primero` 6 s antes del reinicio. Tests: ninguno
  lee la temperatura real (conftest) ni escribe en output/work. (2) **Época de fotos_primero por lo que se ve**
  (`moderno`, el arco completo de la historia; postales = foto; estatuas y edificios no son retratos): medido sobre las 6
  historias de la prueba + Microsoft, llegan a 8 fotos buenas 4 de 7 (antes 1). (3) **Tarjetas en la revisión final**
  (todos los videos de Pequeña Historia): `calidad.revisar_video_ph` le dice al modelo qué cortes son tarjetas y no
  cuenta PH-02/PH-12 sobre ellas (antes se sacaba recién al final y la tarjeta entraba en la vuelta de reemplazo).
- v1.57.0 (2026-11-25) — **Al primer intento: A, C y D prendidos; B (fotos primero) programado y apagado** hasta la
  prueba de 3 historias (regla en §1; si pasan 2 de 3, se prende sin esperar a Santi). `scripts/prueba_fotos_primero.py`,
  `tests/test_primer_intento.py`, `tests/test_fotos_primero.py`. 2179 tests OK.
- v1.56.0 (2026-11-25) — **Ritmo del presupuesto con 3 días y de a un escalón** (regla en §1). El 25/11 a las 06:30 el
  recorte había llegado al nivel 4 (sin Latinoamérica desde el 26/11) con un promedio de 7 días que mezclaba pruebas
  (US$ 4,5 entre el 19 y el 20/11) y los reintentos del 23/11 (US$ 4,52). Con la cuenta nueva (21, 22 y 24/11 de
  producción: US$ 1,67/día) alcanza sin recortes: nivel 0 aplicado en la Pi el mismo día. `tests/test_presupuesto.py`.
  2172 tests OK.
- v1.55.0 (2026-11-24, noche) — Reserva de tecnología: entran los de 60-69 % de fotos reales que cumplen todo lo
  demás, marcados "⚠️ fotos N %" (regla en §1). 2170 tests OK.
- v1.54.0 (2026-11-24, tarde) — **Reintentos inteligentes, banco de tecnología con fotos comprobadas y ventilador** (reglas
  en §1). Las fallas del 23 y 24/11 eran todas de fotos (5 de 7 por "% de fotos reales" o "5 fotos distintas"), y la
  segunda búsqueda solo miraba Commons y Europeana con el título del artículo: ahora busca cada frase floja en todas las
  fuentes con otras palabras antes del plan B. `fallas.py` + `_fallas_semana_tick`; `bitacora.descarte(intentos=)`;
  `ef.proponer(max_guiones=)`; `Wiki.en_ingles`. `tests/test_reintentos_inteligentes.py`. 2167 tests OK.
- v1.53.0 (2026-11-24) — **La Pi se colgó por calor y tope diario de Claude** (Santi). (1) Cuelgue: la Pi (con
  disipadores, sin ventilador) se colgó a las ~07:01 renderizando un video de la reserva de tecnología (Netscape/Mozilla,
  1998); Santi la desenchufó y arrancó a las 07:03. Tarjeta y bases sanas (`integrity_check` ok, solo el "orphan
  cleanup" del ext4). El journal no sobrevive un corte (no es persistente): la temperatura del cuelgue no quedó; los
  renders de la madrugada llegaron a 82,7-83,7 °C y los del 23/11 a 84,2-85,7 °C. Los 4 videos del día los aprobó Santi a
  las 07:29 y quedaron programados (nada perdió su horario); se perdió solo el de la reserva que se armaba (~US$ 0,10 de
  Claude). Ahora: `freno_calor.py` + servicio de usuario `freno-calor.service` (congela los ffmpeg con SIGSTOP desde
  80 °C y los suelta debajo de 72 °C; anota la temperatura de cada minuto y qué corre en `data/temperatura.log`), pausa
  entre renders de 4 min siempre y hasta bajar de 58 °C (como mucho 30 min; antes 65 °C y 10 min, `db.PAUSA_MIN_S`),
  un render a la vez (ya era así: turno pesado compartido con Lo Encontré). (2) **Tope de US$ 2,50 por día** de
  producción (todo menos pruebas, `presupuesto.TOPE_DIA`, `nivel_dia`, `nivel_hoy`): sin margen para comunidad + web →
  nivel 2; llegado el tope → nivel 3 (Latinoamérica a 1); tecnología nunca. `_recorte` usa el mayor entre el del saldo y
  el del día; una línea a Santi cuando empieza a recortar (`_tope_dia_tick`). (3) **El 23/11:** US$ 4,52, 30 guiones;
  ~US$ 2,02 fueron intentos repetidos de historias que ya habían fallado ese día (Bell 7 veces, AlphaGo 6, Pokémon 3,
  Motorola 2: la reserva volvía a sacar las mismas del banco), lo que arregló v1.52.0 (`banco.marcar_sin_fotos`).
  `tests/test_calor_y_tope_dia.py`.
- v1.52.0 (2026-11-23, noche) — **Fotos antes de gastar, plan B y tarjetas a tiempo** (regla en §1). Fuentes de
  fotos medidas en los 5 videos de tecnología de la semana (segundos en pantalla): Commons 35 %, Pexels 33 %, tarjetas
  30 %, video 2 %; Openverse, Smithsonian, Flickr y Europeana, 0. Por qué: Openverse tarda ~17 s y el timeout era de
  10 (se salteaba toda la corrida), y TODAS sus fotos de Flickr daban 403 al bajarlas por el User-Agent largo (el de
  Wikimedia, con el mail) y, de a ratos, por la palabra "Bot": `config.user_agent_corto` = "PequenaHistoria/0.28 python-requests/…" baja 15 de 15: timeout 30 s y ese User-Agent para todo lo que no es Wikimedia (la API de Openverse igual da 504 de a ratos)
  (además, el mail ya no va a Openverse, Europeana ni Pexels). Sin `FLICKR_API_KEY`, `SMITHSONIAN_API_KEY` ni
  `UNSPLASH_ACCESS_KEY` en la Pi. Nuevo: Internet Archive (imágenes con PD/CC0/CC BY en la ficha; pocas). La Library of
  Congress sigue con Cloudflare (403, probado otra vez) y las salas de prensa de las marcas y de los videojuegos no
  tienen API y sus fotos tienen derechos (uso editorial): no se suman. Chequeo previo medido sobre 18 historias: separa
  solo los casos extremos (AlphaGo 0, Max Headroom 0, WorldWideWeb 3); Intel 4004 pasó con 7 y New Shepard falló con 17.
  Marcadas sin fotos en la Pi: Teléfono (Bell), AlphaGo versus Lee Sedol, Pokémon y Martin Cooper. Informe de una vez el
  24/11 a las 22:05 (`reserva_tec.informe`, `_informe_fotos_tick`). `tests/test_fotos_antes_del_guion.py`. 2154 tests OK.
- v1.51.0 (2026-11-23, tarde) — **Después del corte de luz** (Santi desenchufó la Pi para poner disipadores, SIN el Fan
  SHIM). Tarjeta y bases bien (`integrity_check` ok, solo un "orphan cleanup" del ext4). El video de la reserva que se
  armaba quedó cortado con el turno pesado tomado: un turno de antes del arranque ya no cuenta (`db.arranque_sistema`).
  **El primero de la reserva se había perdido antes del corte** (11:25): la reserva no guardaba el meta (lo guarda
  `enviar_clip` al mandar); ahora va al lado del video (`item["meta"]`). `ventilador.service` desactivado (no hay
  ventilador; la pausa para enfriar entre renders sigue). **Tokens en los logs:** `logseguro.py` (formateador que tapa
  con *** claves y tokens, en todos los `basicConfig`) + `sed` en `correr.sh` y `escuchar.sh`; tapados los ya escritos
  en /var/log/clips-bot (40 del token de la página de Facebook, 5 del bot de Telegram). El 400 del resumen de 24 h era
  la comunidad del 21/11: se guardaba el id de la FOTO y la publicación es `<página>_<foto>` (`metricas_post`).
  **Internet "con 0 vistas":** eran mediciones de Analytics de antes de tiempo (ARPANET 1.176, Chicago 1.256, el
  navegador de hoy recién publicado, todos públicos y procesados): `temas` ignora los de menos de 3 días y usa las vistas
  de hoy (`videos.list`). **Tecnología:** marcas primero, después videojuegos; inventos e internet solo con 8,5 o más
  (`temas.BASE_TEC`, `ef.minimo_tec`, el prompt). **Ninguna marca en Pequeña Historia y Así Nació la misma semana**
  (`marcas_semana.py`). **Plan de Así Nació de los lunes desde la Pi** (`plan_an.py`, 10:00; la tarea de la compu se
  borró). **Recordatorio de videos esperando ✅** a las 10:00 y 15:00 (`_espera_tick`, `bot_estado.esperando_aprobacion`).
- v1.50.0 (2026-11-23) — **Tecnología, prioridad número uno** (regla en §1): 2 por día en YouTube (11:00 y 20:00),
  reserva de 3 videos ya armados (`reserva_tec.py`, `_reserva_tec_tick`, `_tec_del_dia_tick`, `_efe_entregar` separado de
  `_efe_armar`), recortes del presupuesto en orden sin tocar tecnología, temas que rinden (`temas.py`, lunes 10:15),
  YouTube solo de tecnología y Facebook con fútbol primero. **Por qué Santi creyó que no le había llegado el de hoy:**
  llegó a las 04:45 (Tim Berners-Lee y el primer navegador, del banco porque los del día no llegaron a las fotos,
  retenido 6/9: PH-02, PH-07, PH-08) y alguien tocó ✅ a las 08:39 (sale 11:00, `7Evb2o9sMxs`), pero el mensaje corto
  no decía que era el de tecnología. Visto en el log, sin arreglar: el resumen de 24 h del Reel `122129360859498795`
  da 400 cada 30 min (y el log guarda la URL con el token de la página). `tests/test_tecnologia_prioridad.py`.
- v1.49.0 (2026-11-21) — **Plan B de la frase sin foto** (Santi: "nunca más"). El 20 y el 21/11 no salió ni la de
  tecnología ni las de Latinoamérica: "la frase 1 no tiene ninguna foto posible" era un ValueError de
  `ilustrar.asignar` (sin reserva ni generales desde v1.36, la PRIMERA frase sin ranking no tiene anterior que alargar)
  que cortaba toda la propuesta, sin pasar al hecho siguiente ni al banco; y la de tecnología fallada no avisaba (solo
  log). No tuvo que ver con los mensajes cortos. Ahora: `ef.FraseSinFoto` (NarrarError) → primero
  `reescribir_frases_con_foto` (Haiku, una llamada: reescribe SOLO esas frases para hablar de algo que muestra una foto
  que ya pasó los filtros, con los datos del artículo; validado con `no_respaldados` y, en el gancho,
  `gancho_generico`) y se vuelven a elegir las fotos; si no se puede, el hecho siguiente y después el banco; solo si todo
  falla, una línea a Santi (también la de tecnología). `tests/test_frase_sin_foto.py`. 2116 tests OK.
- v1.48.0 (2026-11-20, noche) — (1) **Mensajes cortos** (regla en §1): `aviso_corto.py`, `enviar_clip(resumen=,
  motivo=)`, `marcas.enviar(caption=, teclado=)`, `send_video(teclado=)`, botón `det:` y `/detalle`, `_aviso` para los
  21 avisos e informes a Santi (los que se partían en varios mensajes ahora son uno de 3 líneas), la publicación de
  comunidad en 2 líneas y las fotos de las mejoras al motor recortadas. `bitacora.costo_activo` para el costo de
  Pequeña Historia. (2) **Apretón de lejos** (Santi: "manos muy grandes y a color en una escena sepia"): en el plano
  medio ya no va el dibujo grande escalado (≈2,4 veces una mano de personaje) sino las manos de los propios personajes,
  con las muñecas a 20 px del medio (`uso_v3.SOLAPE_MEDIO`) y los dedos del de adelante cerrados encima (prop `dedos`
  a la escala de los personajes); el primer plano queda igual (`color: True`, mangas `manga`/`manga2`). **Bug para
  todos los videos:** en el pasado quedaba a color todo elemento con un `color` de texto (la manga del apretón, los
  dedos), no solo los marcados `color: True`: ahora solo `True` (`timeline._capa`). Hoja del Pepsi mandada a Santi.
  `tests/test_mensajes_cortos.py`.
- v1.47.0 (2026-11-20, noche) — (1) **Plan de Así Nació hasta el 15/12** (en PENDIENTES.md, 5 líneas a Santi los
  lunes con la tarea programada `asinacio-plan-lunes`). (2) **Tope de pruebas: US$ 1 por día** aparte de la producción
  (`claude.TOPE_PRUEBAS_DIA`, `gasto_pruebas_hoy`, `TopePruebas`; avisa una vez por día). El 20/11 las pruebas ya iban
  US$ 2,72. (3) **Tecnología del 20/11:** Windows 1.0 se armó con 51 % de fotos y se mandó a las 04:26 RETENIDO: la
  revisión final tomó como foto borrosa/de otra cosa (PH-02, PH-12) una tarjeta «MELAZA» con la clave de otra frase.
  Ahora la tarjeta de la revisión usa solo la clave de su frase o el año y no se juzga como foto
  (`calidad.TARJETA_EXENTA`); el banco va antes que bajar el mínimo de fotos; los reintentos no arrancan después de
  las 16:30 (`EFE_ULTIMO_REINTENTO`). (4) **Apretón del plano medio de cerca** (`uso_v3.ZOOM_APRETON_MEDIO` 1,6, la
  cámara en las manos): hoja del Pepsi (laboratorio, apretón, firma) mandada a Santi, solo render.
  `tests/test_tecnologia_diaria.py`.
- v1.46.0 (2026-11-20, noche) — **Revisión repetible y juego fijo de manos** (Santi). (1) La temperatura no se puede
  fijar (los Claude actuales no la aceptan) y la caché devolvía la MISMA respuesta para los mismos cuadros (una
  "segunda revisión" no era otra): cada revisión lleva un sello único. Medido con el mismo Pepsi: una revisión sola,
  de 15 a 19; con 2 y el promedio, de 17 a 19; con 3 SIEMPRE y la regla fallada solo si falla en la mayoría
  (`marcas.REVISIONES` 3, `VOTO`, `combinar_revisiones`), 18,17,18,18,18,18 (≈ US$ 0,01 por video). (2) Manos
  (`animacion/manos.py`, aprobadas por Santi después de 3 hojas): pulgar que nace del costado de la palma con dos
  falanges y uña (la raíz se funde con la palma), agarrar (los dedos envuelven y el pulgar cruza por delante, `encima`),
  servir, papel por el borde (pinza), escribir en pinza con la lapicera incluida, señalar, puño, abierta, apretón con un
  solo pulgar; contorno fijo en pantalla (`TRAZO_PX`), manos de los personajes ×1,45; la otra mano relajada al costado
  (`personajes.CAIDO`); dos manos por los bordes (`cargar_caja`, `sostener_ancho`); al escribir la otra sujeta el papel;
  tomar con el pico en la boca; las manos de primer plano con la manga hasta el borde y la revisión marca manos sueltas;
  todo lo que está en una mano lleva los dedos encima (`acciones.escena_accion`). (3) Ronda 3 (antes de las manos
  nuevas): Pepsi 18, Levi's 14, Kellogg's 14 (frenada para desplegar las manos).
- v1.45.0 (2026-11-20, tarde) — **Prueba final de 5 marcas nuevas con el motor nuevo** (guion real con Sonnet, voz de
  prueba, una revisión calibrada + reemplazo por escena base y una medida final; `output/animacion/prueba5b` en la Pi,
  hoja `hoja_r2.jpg` mandada a Santi). Ronda 1 (guion nuevo): Pepsi 13, Levi's 14, Kellogg's 17, Gillette 11, Crayola 8;
  US$ 0,23-0,28 por video (todo Claude, ~20 pedidos), 14-17 min en la Pi, 26-28 s. Ronda 2 (mismo guion, motor
  arreglado, US$ 0,01-0,02 cada una): 18, 11, 13, 11, 8. **Solo 1 de 5 llega a 15/19: Así Nació sigue pausado.**
  Arreglado con la prueba: una escena base que falla ya no se cambia por otra base (la crisis y el trato terminaban
  "en uso" en un living); el reemplazo respeta el lugar de la escena; "la compró" va al apretón e "imaginó" al taller;
  el químico vuelca el matraz sobre el producto (`p_verter`, prop `chorro`); el número gigante y el texto grande que
  repiten la frase no van (AN-11 en casi todos); en el cierre el producto queda donde apunta el dedo de Tito y la ficha
  dice que es Tito; un lugar inventado puesto directo en `fondo` también se crea; lo de la cara (maquinilla, cepillo) se
  usa en la cara; las caras tristes bajan la cabeza. **Lo que sigue fallando:** la revisión varía mucho entre corridas
  (Kellogg's 17 → 13 y Levi's 14 → 11 con el mismo guion), escenas `libre`/`nueva` que no se entienden (Crayola), el
  gancho (AN-01) y la gente de la historia en escenas que el motor no tiene (una escuela, un supermercado).
- v1.44.0 (2026-11-20) — **Motor de Así Nació que se autosustenta** (§1): manos con dedos (`manos.py`) en personajes y
  Tito, dedos sobre lo agarrado, tomar/comer/escribir/coser/armar/cargar completos, expresiones por emoción
  (`emociones.py`, caras nuevas: concentrado, preocupado, determinado, devastado, frustrado, eufórico; cejas
  `concentrado`, bocas firme/torcida/abajo, `cabeza_baja`), lugar por oficio (frasco y tubos nuevos), éxito con
  `tienda:vacia`, sin multitud, 6-7 escenas y 25-30 s, una revisión calibrada y reemplazo por escena base, mínimo 15/19,
  tope US$ 0,60. Probado sin Claude con la hoja de la Coca-Cola en `~/clips_lib/output/biblio2`.
  `tests/test_motor_autosustentable.py`. 2070 tests OK.
- v1.43.0 (2026-11-20) — **Biblioteca base de Así Nació** (§1): `plantillas.py` con las escenas nuevas (taller,
  crisis, éxito, en uso, lanzamiento, cierre con Tito) y la fábrica y la tienda rehechas; personajes de perfil
  trabajando (`Estado.perfil_fijo`, gestos `p_sostener`, `p_cinta`, `p_dar`, `p_senalar`, `p_aplaudir`, `p_tomar`; el
  perfil va en `_estado` para que el chequeo de composición lo vea); el apretón de perfil y sin destellos; la multitud
  aplaude; los dibujos guardados miden como los de código (`plantillas.esc_de`, `acciones.factor_tam`, también en el
  gancho). Guion: la base por defecto, nada nuevo obligatorio, sin tope de repetidas. **Encontrado:** el `cartel` de todos
  los videos era un cartel de "prohibido" desde que una revisión pidió "un cartel de LEY SECA" y `redibujar_objeto` lo
  reemplazó para todos (`reemplazos.json`: sacado en la Pi); ahora los genéricos (`GENERICOS_FIJOS`: carteles, cajas,
  muebles, íconos) no se redibujan. La hoja de la oficina ya no es un rótulo en blanco. **Prueba de la biblioteca** con
  la botella fiel de Coca-Cola (`output/biblio` en `~/clips_lib`, un worktree de prueba en la Pi): Haiku mira 3 cuadros
  de cada escena con 14 reglas; tras 11 vueltas pasa sola **1 de 10** (el taller). Lo que más marca: la gente de atrás
  "parada", fondos con pocos detalles de época (AN-18), las manos que no se ven agarrando (AN-06) y la frase de ejemplo
  leída al pie de la letra (AN-02). Costo de las revisiones: < US$ 0,10 en Haiku. `tests/test_biblioteca_base.py`.
  1897 tests OK.
- v1.42.0 (2026-11-20) — Arreglos del Lego (producto antes de existir → lo de la época, manos humanas que agarran,
  fábrica con obreros y máquinas de época, gráficos siempre con gente, chequeo del fiel más permisivo sin agregados) y
  por tipo después de la ronda 1 (una sola escena de solo manos, `escenas_lib.una_de_manos`; festejar aplaudiendo,
  gestos `aplaudir_a/b`; manos a color en sepia; `objeto_gira` sobre una mesa; el año no va como número gigante; el
  contador llega a la cifra a la mitad). **Prueba con 5 marcas nuevas** (voz de prueba, `output/animacion/prueba5` en la
  Pi): ronda 1 Nintendo 6, Coca-Cola 9, Adidas 10, Ford 8, Colgate 4 (US$ 0,31-0,40 cada una con el guion); ronda 2 con
  el mismo guion: 6, 7, 8, 7, 8 (US$ 0,02-0,05 sin el guion). **Ninguna llega a 17/19: Así Nació sigue pausado.**
  Fallan en las 5: AN-02 (lo que se ve no es lo que dice la frase), AN-03 (no se entiende sin la voz), AN-05, AN-06
  (lugar), AN-11 y AN-16 (gente quieta). El problema ya no son piezas sueltas: el guion pide acciones concretas y la
  biblioteca de escenas las traduce a planos genéricos.
- v1.41.0 (2026-11-19, noche) — La escena de manos y la de inspiración pasan al protagonista fiel (`fiel.asegurar`
  reemplaza también en `uso.partes` e `inspiracion.producto`); en el estadio los que no hacen nada juegan (`en_juego`:
  dos se pasan la pelota en arco por arriba de las cabezas, el primer pase es un saque con salto; el festejo queda;
  `Escena.pases`). Hoja de 6 tiendas por rubro + el estadio mandada a Santi. **Prueba con Lego** (marca nueva, guion
  nuevo, voz de prueba Piper llevada a 35 s): 5/19 por US$ 0,36 (37 pedidos, 1 de Sonnet); el rescate no corrió por el
  tope de 4 correcciones. Lo que falló: el ladrillo moderno aparece en 1932 (el protagonista siempre pasa la época),
  manos de madera gigantes con un carrito flotando, la fábrica de 1949 como escenario con cortinas y un cuadro de
  Mondrian, escenas sin gente (2015, 2004). El ladrillo fiel se ve bien en la hoja, pero Haiku no lo reconoció (y la v2
  le agregó ruedas): el chequeo de "¿se reconoce?" es demasiado exigente.
- v1.40.0 (2026-11-19) — Motor de Así Nació, general para todos los videos (Santi): tiendas por rubro (`escenas.RUBROS`:
  almacén, deportes, juguetería, farmacia, concesionaria, ropa, tecnología, hogar; `tienda:<rubro>` según la frase o la
  categoría de la marca, `rubro_de`); protagonista fiel (`animacion/fiel.py`: Haiku describe el producto real, se
  dibuja con eso y Haiku chequea sobre la imagen "¿se reconoce sin leer el nombre?", una segunda versión si no;
  `data/animacion/fieles.json`); poses de acción (trabajar, jugar, comprar, cargar, preocuparse; `ACCION_DE_ROL`: quieto,
  señalar o pensar según el rol; nadie parado); física (`acciones.apoyar`: nada en el aire salvo íconos o lo que se
  mueve; afuera, al piso). Prueba con el guion y la voz del Wilson: 8/19 por US$ 0,05 (la pelota se reconoce, la tienda
  es de deportes, AN-07 pasa; siguen la escena de manos con la pelota genérica, gente parada en el estadio y la
  revisión que ve el gancho repetido porque el mismo Wilson ya se probó). La comparación con imágenes de Gemini no se
  pudo hacer: las dos claves no tienen facturación y la generación de imágenes no tiene cuota gratis.
  `tests/test_motor_general.py`.
- v1.39.0 (2026-11-19) — Así Nació pausado; Sonnet solo para el guion, Haiku para el resto y las correcciones; caché de
  prompts; 4 correcciones por video en todos los canales; 2 reintentos de guion (§1). **Diagnóstico del Wilson (8/19)**:
  la revisión acierta, falla el motor: la pelota es un círculo naranja genérico (no la Wilson de voley con su cara), la
  tienda es el fondo de siempre con botellas, los personajes quedan parados sonriendo, la cancha es de fútbol sin
  pelota, y la sombrilla y el paraguas flotan. **Prueba con el guion y la voz de hoy, todo con Haiku: 10/19 por
  US$ 0,047** (27 pedidos; el rescate arregló AN-01, 06, 08 y 15). Costo resuelto; el puntaje necesita arreglos del
  motor (fondos por tipo de tienda, objetos fieles, poses de trabajo). `tests/test_costo_por_video.py`.
- v1.38.1 (2026-11-19) — Así Nació falló a las 07:05 ("'str' object has no attribute 'get'"): la corrección puntual
  del guion de Toys "R" Us trajo `dibujos_nuevos` como lista de textos. `correcciones.aplicar` ahora controla la forma
  de cada campo general con el schema del guion (`con_forma`) y `marcas` lee esas listas solo con objetos (`_dicts`).
  El intento perdido costó US$ 0,58 de Claude (6 pedidos). `tests/test_parche_campos_forma.py`.
- v1.38.0 (2026-11-18, tarde) — Prueba de horarios de Así Nació (12:30 y 18:00 del 19/11 al 02/12) y su comparación
  en el resumen de los lunes. `tests/test_horarios_an.py`. 1722 tests OK.
- v1.37.0 (2026-11-18, tarde) — Pruebas sin Claude real; la revisión final reemplaza la foto mala en vez de frenar.
  Gasto del 18/11 hasta las 11:07: US$ 8,73 (Así Nació 5,67 con los 2 videos de antes del tope, Pequeña Historia 2,41,
  búsqueda web 0,34, pruebas y mediciones 0,31; bancos 0).
- v1.36.0 (2026-11-18, tarde) — Fotos de Pequeña Historia por capas (§1). Antes: Latinoamérica US$ 0,53 por video y
  tecnología US$ 0,25 (promedio del 11 al 18/11, bitácora). Medido después en la Pi (Belice, 19/11, de punta a punta con la voz de prueba):
  US$ 0,31 en total; las fotos US$ 0,02 (antes ~US$ 0,20), la revisión del mosaico US$ 0,04, la búsqueda web US$ 0,15.
- v1.35.0 (2026-11-18, tarde) — Saldo de US$ 70 hasta el 14/12 con Así Nació a 1 por día si no alcanza; tope por video
  de Así Nació a US$ 1,20. `tests/test_presupuesto.py`.
- v1.34.0 (2026-11-18) — Tope de US$ 1,50 por video de Así Nació, director de escenas, menos texto (aprendizaje y
  resumen semanal), Latinoamérica con menos banco y plan B de tecnología (§1). Pasados a privado en YouTube 9 videos de
  Pequeña Historia (Colón, que seguía público, CDMX no tiene YouTube); en Facebook la API no deja ocultar ni hacer
  privado un Reel (solo borrarlo): queda para Santi. `tests/test_tope_costo.py`, `test_director.py`, `test_aprendizaje.py`.
- v1.33.0 (2026-11-17, noche) — **El Short de Colón** (`historia_fb_1117_2021`, pasado a privado por Santi). Por qué
  no lo frenó el estándar: la revisión SÍ lo miró y le dio 7/9 (marcó el retrato de un señor mayor y un estadio de
  2024), justo el mínimo, y salió solo. Pero miró la HOJA de antes de la voz (una foto por frase, en miniatura): el
  video real tenía 15 cortes y los del formato corto se llenaban con fotos "del tema general" del artículo del hecho,
  que era "Argentina" (vino del banco, `latam:Argentina`): así entraron Arturo Illia (1965) en "le ganó 3-0 a Racing" y
  en "¿cuánto duró la fiesta?" y Cristina Kirchner en Atucha (`Atucha_presidencia_02.jpg`) en "caravanas y banderas
  rojinegras", que nadie había mirado. Los recortes de diario borrosos medían 500 px (la excepción para fotos de
  época). Los "1993/2020" eran el año contando hacia 2021. Arreglos: no se publica sola, reglas de fotos y revisión del
  video terminado (§1). `tests/test_fotos_colon.py`.
- v1.32.0 (2026-11-17) — **Los dos pendientes del Hershey.** (1) La "máquina violeta" de 1883 no era un dibujo
  guardado: las recetas de la biblioteca de escenas pasaban el objeto como `dibujo_nuevo` sin resolver y salía una caja
  de colores; ahora `escena_accion` usa el dibujo guardado (el caramelo). Revisadas las 22 piezas de
  `data/animacion/dibujos/`: año puesto a `masa_modelar` (1956), `tazon_tupper` (1946) y `documento_quiebra` (1890);
  limpias las descripciones de `barra_de_chocolate_con_l_real` y `un_disco_volador_plano_y_real`, que tenían el texto de
  la revisión ("AN-09: el mapa…"), y `redibujar_protagonista` ya no lo mete. (2) Nada tapa el texto grande ni los
  subtítulos (AN-27). La primera versión bajaba el encuadre y cortaba las caras: ahora sale el decorado y la cámara se
  acerca menos. Hoja del Hershey otra vez a Santi.

- v1.31.0 (2026-11-17) — **Así Nació: personajes por rol y época, todos trabajando, línea de producción, fondos de
  época, ficha por escena y Tito sin tapar** (regla en §1, AN-15 a AN-19 y AN-26). Probado en la Pi con 3 escenas del
  Hershey (mismo guion, sin voz: `output/animacion/prueba_roles_hershey/hoja_hershey_roles.jpg`, mandada a Santi).
  Visto y arreglado con la prueba: el jopo asomaba sobre la galera, la cinta muy cargada, una nube como decorado
  adentro. Sigue flojo: la máquina violeta es un dibujo guardado de antes (la revisión la marca por la época) y el
  gráfico tapa el texto grande cuando la cámara se acerca (motor de antes). `tests/test_roles_epoca.py`.

- v1.30.0 (2026-11-17) — **Así Nació: piezas reusables, escenas únicas, lugares nuevos, rescate y costo de las piezas**
  (regla en §1). Probado en la Pi: el schema del guion con `lugar_nuevo` compila en Claude (8 s) y Sonnet dibujó "una
  bolera de los años 50" que se entiende sin leer (73 s, ~US$ 0,08, guardada solo en la copia de prueba). También:
  **comunidad elige el tema por la foto** (historias del día y después el banco de Latinoamérica con buenas fotos, en
  sus artículos y en Commons; texto sobre lo que muestra la foto; `comunidad_usados`). Probado con las historias reales
  del 17/11: Colón y Veracruz sin foto que sirva → Carmen de Patagones (pintura de dominio público). Sin marcas de agua.
  `tests/test_piezas_nuevas.py`.
- v1.29.0 (2026-11-17) — (1) **Comunidad con la foto verificada** (regla en §1, PH-24). Probado con las historias
  reales del 17/11: en Colón el artículo era "Argentina" (por eso la cumbre del Mercosur) y Sonnet descartó las 6 fotos
  (presidentes, paisajes); en Veracruz descartó la catedral y una fuente, y después de sumar "nada de mapas" también el
  grabado coloreado del puerto: ese día no habría salido (con aviso). (2) **Mínimo de Así Nació 11 → 12 de 14.**
- v1.28.0 (2026-11-17) — (1) **Video con el estándar bajo = no se publica solo** (regla en §1): `calidad.MINIMO_PUBLICAR`
  / `retener` / `texto_retenido`; Así Nació separa el meta de la subida (`_animacion_meta`, `_animacion_programar`) y,
  retenido, manda el video con ✅ Publicar igual / ❌ Cancelar; Pequeña Historia igual en `_efe_armar`. ✅ programa en su
  horario (o en 30 min si ya pasó); ❌ marca "no subir". (2) **La publicación de comunidad de Colón del 17/11** salió a
  las 13:00 con la foto de la cumbre del Mercosur (presidentes, Puerto Iguazú 2023): `comunidad_fb.foto_de_la_historia`
  toma la PRIMERA foto del artículo sin mirar qué muestra. Borrada de la página por pedido de Santi (Graph DELETE,
  verificado: ya no existe) y marcada cancelada en `subidas`. El arreglo de la foto queda propuesto (PENDIENTES).
  `tests/test_publicar_retenido.py`.
- v1.27.0 (2026-11-17) — **Lo que salió mal en el Frisbee** (Santi). (1) La escena de las manos levantadas y vacías en
  el living (frase 4, uso_manos) **no la vio la revisión**: de los 8 cuadros que mira, 4 eran el reloj del viaje en el
  tiempo y 1 el mapa. El video sacó 4/14 en el estándar (fallaron AN-01 a 06, 09, 11, 12 y 13), pero ninguna falla era
  de esa escena; la biblioteca de escenas aprobadas estaba vacía (+0), así que nada se reemplazó. Arreglos:
  `cuadros_clave` mira UN cuadro por cada escena de la historia y nunca el viaje ni el mapa; la revisión rechaza
  siempre manos levantadas o vacías, el lugar que no es el de la historia y lo que flota en la pared (`REVISION_V3`);
  `preparar_uso` no arma la escena de manos si el uso es solo "agarrar" (`PASOS_USO_REAL`: un producto que se tira no
  se usa sobre una mesa). (2) La ventana flotando: el decorado ponía `ventana` apoyada en el piso del medio; ventana,
  puerta, cuadro, cortina, lámpara, mesa y estante ya no son decorado (`acciones.NO_DECORADO`). (3) Regla nueva en §1
  (cada video único, lugares reales; AN-25, y AN-06 / AN-13 más precisas en el estándar); fondos nuevos `playa` (con
  sombrilla), `estadio` (tribunas llenas, torres de luz, cancha) y `cocina` (azulejos, mesada, cocina a gas, heladera
  según la década). `tests/test_frisbee.py`.
- v1.26.0 (2026-11-16, noche) — **Así Nació: reemplazo de la escena que sigue sin pasar** (regla en §1):
  `reemplazo.py` (biblioteca de escenas aprobadas, `candidatas`, `adaptar`, `empalmar`, `chequear` con Haiku,
  `reemplazar`), el tope de US$ 0,50 en las correcciones, `marcas.MEJORAS_PRIMERO` en las mejoras de los lunes y jueves,
  y las líneas 🔁 / ⚠️ / 💸 en el mensaje. Probado en la Pi con el guion del tercer Tupper: la candidata empalma y solo
  cambia esa escena (misma duración); Haiku la rechazó con razón (una firma no muestra "presentó el tazón"). La
  biblioteca arranca vacía: hasta que haya videos que pasen, una escena sin arreglo sale con el aviso.
  `tests/test_reemplazo_escenas.py`.
- v1.25.0 (2026-11-16, noche) — **Estándar de calidad** (Santi; regla en §1): `ESTANDAR_CALIDAD.md` con 19 reglas de
  Así Nació (14 de revisión y 5 de código) y 13 de Pequeña Historia (9 y 4), juntas de lo aprobado en §1, cada una con
  su id y su arreglo. `calidad.py` lo lee (se relee si cambia), arma el pedido, anota las fallas y arma el resumen de
  los lunes. Así Nació: la revisión visual devuelve `reglas` (cumple sí/no por regla) además de `problemas`; una regla
  que falla sin problema se corrige con el arreglo de la regla (`marcas.problemas_del_estandar`); 2 vueltas de
  corrección + una que solo mira (`VUELTAS_REVISION`); `Resultado.estandar` y la línea 📏 en el mensaje. Pequeña
  Historia: `calidad.revisar_ph` en `_efe_armar` antes de la voz (cambio de foto con `ef.cambiar_foto`); el aviso de
  fotos reales cuenta como PH-21. `tests/test_calidad.py`.
- v1.24.0 (2026-11-16, noche) — **Así Nació: el apretón rehecho y `uso_manos` PRENDIDO** (Santi: "parece un saludo
  con el codo"; "puño contra puño"). Plano medio: las dos personas a 190 px del medio (antes se corrían por separado
  para dejarle lugar a Tito y se alejaban de su mesa: `dejar_lugar_a_tito` ya no toca a los que se van antes del
  final), detrás de la mesa con el contrato apoyado (`papel_firma` con `forma` 1, visto desde arriba; la mesa sin
  `decorado`, que la mandaba detrás de los personajes), y cada brazo calculado para llegar justo al medio
  (`personajes.brazo_hacia`, gestos `brazo_der:H:C` / `brazo_izq:H:C`, `gesto_valido`), con las manos enganchadas en
  chico encima. Primer plano: dibujo nuevo `apreton` (de costado: palma contra palma, los dedos de una envolviendo la
  otra, los de la otra asomando abajo, los pulgares cruzados arriba) con 2-3 sacudidas de arriba abajo. Hoja de la
  escena 7 mandada a Santi (`output/animacion/prueba_apreton_v5` en la Pi, sin guion ni voz nuevos).
  `animacion.uso_manos: true` desde el video del 17/11 a las 07:00 (lo revisa con ❌ Cancelar). `PENDIENTES.md` nuevo.
- v1.23.0 (2026-11-16, noche) — **Así Nació: el estilo ya no frena un video** (Santi, después de que el Tupper fallara
  8 veces por "presentá a Brownie Wise"): solo frenan los datos que no están en el artículo, los temas sensibles y las
  fallas técnicas (`marcas.bloquea`); si una regla de estilo sigue sin cumplirse después de las correcciones, sale el
  mejor guion y el mensaje dice cuál (`aviso_estilo`). Desplegado y escucha reiniciada. **Regla para todos los videos:**
  cada escena se entiende de un vistazo sin la voz y el dibujo usa los detalles que describe el guion (REGLA_16 y la
  revisión: `cambiar_accion` / `redibujar_objeto`). **uso_manos (sigue APAGADO):** el apretón arranca con un plano medio
  de las dos personas dándose la mano sobre la mesa con el contrato (gesto `dar_mano`, mesa con `en_medio`) y después el
  primer plano; la inspiración trae `acompana` (el pincel al lado de la lata) y el producto sin su parte, y la pieza se
  transforma en ella (la tapa de pintura cae sobre el Tupper abierto y pasa a ser la tapa blanca). Hojas de las escenas 5
  y 7 mandadas a Santi (`output/animacion/prueba_escenas_v4b`, sin guion ni voz nuevos). 1612 tests OK.
- v1.22.0 (2026-11-16, noche) — **Así Nació: uso real con las manos, plata de verdad e inspiración animada**
  (`animacion.uso_manos`, APAGADO hasta el OK de Santi; `uso_v3.py`). Escenas nuevas de la biblioteca (solo se le
  ofrecen al guion con el interruptor, `escenas_lib.ACCIONES_V4` / `CON_V4`): `uso_manos` (dos manos usan el producto
  paso a paso: agarrar, abrir_tapa, meter, cerrar_tapa, apretar, amasar, moldear, girar, apilar; el producto por partes,
  cuerpo/tapa/contenido, dibujadas una vez; las manos siempre tocan el objeto), `inspiracion` (la pieza sale de lo que
  inspiró al producto, se da vuelta, vuela y encastra, con clic, destellos y flecha), y la plata con acciones reales
  (`contar_billetes`, `abrir_caja` con la caja registradora, `apreton_manos`, `firmar` con la firma que se escribe); props
  nuevos `caja_registradora`, `papel_firma`, `lapicera`. Mano con detalle (sombra, arrugas, puño de la camisa con botón,
  manga del color de la época, los dedos se doblan al agarrar: `prop_mano(detalle=True)`). El pedido aparte del guion
  (`completar_v3`) trae `uso` e `inspiracion` y `marcas.preparar_uso` dibuja las partes y marca las escenas. Revisión:
  manos que no se leen en 1 s, plata como símbolo gigante y objetos sin detalle (`redibujar_objeto`: la versión nueva
  reemplaza también a un dibujo de código). **Arreglado para todos los videos:** `color: True` (quedar a color en sepia)
  llegaba al dibujo como color y lo pintaba de negro (botellas, latas, el protagonista en el pasado); `manga`/`detalle`
  no llegaban al dibujo; los carteles sin texto llevan una estrella (en el fondo espejado "OFERTA" salía al revés);
  etiquetas de botellas y latas con dibujo, no en blanco. Prueba por escena (sin guion ni voz nuevos, ver §10): las hojas
  de las escenas 5, 7, 8 y 9 del Tupper mandadas a Santi. 1611 tests OK.
- v1.21.0 (2026-11-16, noche) — **Comunidad prendida** (13:00, la primera el 17/11). **Así Nació:** (1) una versión
  nueva de un dibujo reemplaza a la vieja en todas las escenas y la vieja sale de la biblioteca
  (`dibujos.reemplazar` / `actual` / `mismo_objeto`, `data/animacion/dibujos/reemplazos.json` y `retirados/`;
  `marcas.unificar_protagonista`): en el tercer Tupper el laboratorio usó `tazon_maravilla` (la olla de la primera
  prueba) en vez de `tazon_tupper`; ya retirado en la Pi. (2) Época de cada objeto (`esc.ANIO_DESDE`, `existe_en`;
  los dibujos nuevos guardan su `anio_desde`): en `escena_accion` nada aparece antes de existir (el protagonista,
  siempre), para todos los videos; el rótulo usa el año de la escena. (3) Pendientes para la tanda del jueves, ya
  aprobados por Santi (`bot_estado.mejoras_pedidas`, encabezan el mensaje de las mejoras): secuencias de uso real de
  las manos paso a paso, manos con más detalle y la conexión visual de lo que inspiró al producto. 1596 tests OK.
- v1.20.0 (2026-11-16, tarde) — **reglas_v3 de Así Nació PRENDIDAS** después de 3 Tuppers de prueba
  (output/animacion/prueba_tupper_v3, v3b y v3c en la Pi; ~US$ 1,3 de Claude y 8-9 min de render cada uno). Lo que
  cambió entre el 2.º y el 3.º: `usar`/`probar` eran los gestos "atrapar"/"saltar" (brazos abiertos): ahora `usar`,
  `probar` y `fabricar` son `sostener_a/b` (las dos manos adelante) con el producto en las manos de quien lo manipula;
  el texto del gancho no puede repetir lo que dice la voz en la frase 1; la revisión rehace siempre la gente parada y el
  producto flotando (aunque la marque "otro"; el gancho flota a propósito). Quedó flojo (del motor de antes, también en
  producción): el plano "manos" de la biblioteca dibuja manos de madera gigantes y el remolino del viaje en el tiempo
  deforma las caras; van a las mejoras de los lunes y jueves. 1594 tests OK.
- v1.19.0 (2026-11-16, tarde) — Después del primer Tupper con reglas_v3 (gancho bien; objetos flotando, manos sin
  hacer nada, primer plano cortando caras, textos pegados y la revisión con el criterio viejo del gancho): segunda
  vuelta de reglas_v3, mejora continua de Así Nació, publicaciones de comunidad (5 ejemplos mandados) e ídolos de antes
  con Jorge Negrete fijado para el 30/11 (todo en §1). `tests/test_mejora_continua.py`. 1580 tests OK.
- v1.18.0 (2026-11-16, tarde) — Cinco pedidos de Santi. (1) **Telegram:** el informe de costo de las 09:00 no salió
  ("Unsupported start tag 'module'": el nombre de función `__main__.<module>`); ahora todo mensaje pasa por
  `telegram.html_seguro` (escapa `<`, `>` y `&` que no son etiquetas de Telegram) y, si igual no parsea, se reenvía como
  texto plano (`_con_html`). El informe del 15/11 se reenvió. (2) Búsqueda web: ya andando (v1.17.0). (3) **Pequeña
  Historia:** pregunta corta al final y giro a la mitad (regla en §1). (4) **Facebook:** el resumen de cada Reel a
  las 24 h (§1); probado contra las dos páginas. (5) **Así Nació reglas_v3** (§1, APAGADO): prueba con el Tupper.
  Encontrado al probar: con los campos nuevos en el schema del guion, Claude daba "compiled grammar is too large" los
  8 intentos (antes de la voz: sin créditos gastados); producción no lo tuvo (la escucha no se había reiniciado) y se
  probó contra la API que el schema de producción de Así Nació y el de Pequeña Historia (con `frase_intriga`) compilan.
  Ojo con los scripts por heredoc: `\\n` llega como un salto real y parte el string (pasó 3 veces): esos cambios, con
  Edit. `tests/test_telegram_html.py`, `test_stats_fb.py`, `test_asinacio_v3.py`. 1565 tests OK.
- v1.17.1 (2026-11-16, 07:50) — **Así Nació: nada desconocido frena el video** (regla en §1). El primero del
  16/11 falló a las 07:13: la reescritura por duración (después de dibujar `masa_modelar`) trajo `masa_gris`, que
  nadie dibujó, y la línea de tiempo lo rechazó después de pagar 447 créditos de voz. `resolver_objetos`,
  `esc.parecido` / `prop_parecido`, la red de `timeline`. Los roles ya caían en "joven" y las escenas en
  "libre". `tests/test_objeto_desconocido.py`. 1548 tests OK.
- v1.17.0 (2026-11-16) — **Latinoamérica con fuentes web y 2 fuentes por dato** (opción C de Santi; regla en
  §1): `web_historias.py` (ClienteWeb, buscar, verificar), `locales.candidatos_web` y la verificación antes de
  cada guion, el banco como última vuelta si ninguna del día sale, `_web_latam` / `_web_latam_tick` /
  `costo_web_dia`, el paso "verificacion" en la bitácora y los descartes. Prueba real en la Pi (origen prueba):
  US$ 0,13 por una búsqueda y dos verificaciones (la primera se cortó con 8.000 tokens de respuesta: ahora
  16.000). `tests/test_web_historias.py`. 1541 tests OK.
- v1.16.0 (2026-11-16) — **El banco como excepción y el pico del final** (reglas en §1). Usos del banco por
  semana y canal en /costos, con aviso si un canal pasa de 2 (`banco.anotar_uso`, `usos_semana`, `texto_usos`,
  `avisos_pendientes`, `_banco_usos_tick`); la segunda historia de Latinoamérica también cae al banco (nunca
  una de menos de 8); limitador en `media.cola_audio` (−4,4 dB) para que ningún video termine arriba de −3 dB.
  Antes, el 15/11: la historia del banco (CDMX, 1925) salió en Facebook a las 21:42; arreglado el KeyError
  'fuente' de Europeana en la segunda búsqueda de fotos. `tests/test_banco_usos.py`. 1529 tests OK.
- v1.15.0 (2026-11-15, noche) — **ElevenLabs en Así Nació** (regla en §1). Cuenta conectada con
  `npx @elevenlabs/cli onboard` (clave nueva, terminada en 5094, en el .env de la compu; copiada a la Pi, huellas
  iguales `47fff12ec9c8`). Se habla con la API directo con `requests` (como el resto del bot), sin el SDK: el
  `onboard check` del CLI sigue pidiendo el SDK por eso. 3 muestras de voz para Tito mandadas a Santi (eleven_v4,
  mismo texto de Kleenex, ~22 s cada una). Biblioteca de 14 efectos generada (viaje, whoosh, golpe, vidrio, boing,
  pop, tac, ding, aplausos, caja registradora, explosión, cohete, máquina, asombro): **163 créditos en total**,
  1,6 MB; los 6 principales mandados a Santi. Usados en las escenas: caja registradora en la primera venta,
  aplausos con la multitud, cohete en el despegue, máquina en la fábrica. Cálculo: ~60 videos × ~550 caracteres ≈
  33.000 créditos por ciclo (de 40.000) si la voz sale a la primera; cada reescritura por duración suma otra voz.
  1520 tests OK.
- v1.14.0 (2026-11-15, noche) — **Así Nació: gancho, viaje, sepia, manos y textos** (regla en §1) y
  **`animacion.visual_plus` PRENDIDO** (biblioteca + más visual) desde el video del 16/11 a las 07:00. Medido en
  la compu: el remolino usa mapas de OpenCV cacheados por fuerza (solo en los ~40 cuadros del viaje). Los
  subtítulos: "VENDIÓ CUATROCIENTOS 💰" pasa a dos líneas (x 195-890, y 159-297); "2.76 SEGUNDOS" en el número
  gigante, de 76 a 1007 px (antes la placa medía 1.450 px). 1505 tests OK.
- v1.13.0 (2026-11-15, noche) — **Nunca un día sin video** (plan aprobado por Santi con el piso de 6 y los
  bancos; regla en §1). `banco.py` (bot_estado `banco:<canal>`, `banco_llenando:<canal>`, `banco_cursor:<canal>`),
  `_bancos_tick`, `_sin_video_tick`, `_piso_latam`; `ef.proponer(piso, banco)`, `locales.proponer(banco)`
  (`de_banco`, `PISO_ABSOLUTO`), `marcas.proponer(banco, ultimo)`; `ef.umbral_relajado`, `_control_real`,
  `aceptar_relajado`, `consultas_segunda`. Además: el **Intel 4004** del 15/11 (`efe:45a83b`) se armó y quedó
  programado en Pequeña Historia para las 20:00 (`3NyyFp_M3IM`), y el schema del guion de Así Nació pasaba el
  tope de gramática de Claude ("compiled grammar is too large") con los campos de la biblioteca:
  `accion_escena`, `plano` y `protagonista.prop` van sin enum y los valida el código; y el de la corrección
  puntual (`correcciones.schema_parche`) tenía la escena DOS veces (cambios y agregar) y `campos` con todo
  opcional: ahora una sola lista `cambios` con `nuevo`, `campos` como lista de {campo, valor JSON} y sin enums
  (los dos probados contra Claude en la Pi). `cubo_rubik` pasa a DETALLADOS. `tests/test_nunca_sin_video.py`.
- v1.12.0 (2026-11-15, noche) — **Así Nació: lo que se ve = lo que dice la voz** (regla en §1). Biblioteca de
  escenas (`escenas_lib.py`: 9 acciones con planos, constructores que arman fondo, personajes, objetos, cámara
  y sfx; recetas nuevas guardadas), props nuevos (`mano`, `mostrador`, `fuego`, `cubo_rubik` con `fase`),
  fondo `mesa_arriba`, personajes de espaldas, `fase` animable, `dejar_lugar_a_tito` (los personajes de una
  escena de la biblioteca se corren enteros para no quedar debajo de Tito), `errores_accion` en la validación
  y `cambiar_accion` en la revisión visual con corrección puntual. `visual_plus` sigue APAGADO hasta el OK de
  Santi. **Prueba: Cubo de Rubik rehecho desde el guion en la Pi** (con `visual_plus` en memoria): render
  544 s (antes 550-558), pico 85,7 °C, Claude US$ 0,54, 34,4 s; mandado a Santi. Arreglado con la prueba: el
  cubo se dibujaba con la cara de arriba separada, el contador sumaba todos los dígitos de la frase (o inventaba
  1.000.000: ahora el número más grande que no es un año, o ninguno) y `objeto_gira` salía en 5 de 10 escenas
  (ahora como mucho 2). Sigue flojo: el gancho cae en el escenario (la revisión visual lo marca como repetido
  y no lo arregla sola) y "2.76 SEGUNDOS" se corta a la izquierda. 1499 tests OK.
- v1.11.0 (2026-11-15, tarde) — (1) **Diagnóstico del 15/11 sin Pequeña Historia** (sin cambios de código,
  esperando el OK del plan "nunca un día sin video"): la de tecnología (Intel 4004, 8,5) se propuso a las 04:2x
  CON aprobación (`sin_aprobar` se prendió recién a las ~12:00) y nadie tocó ✅: quedó guardada (`efe:45a83b`),
  armable hoy; Latinoamérica: ninguna de 23 llegó a 8 (la mejor, 5,2): no hubo video ni Reel. (2) **Facebook de
  Así Nació**: las claves de la compu y de la Pi son las mismas (huellas iguales), el token es de PÁGINA y no
  vence (pages_manage_posts); el Reel de Kleenex se publicó a las 13:19 y el del Cubo de Rubik quedó
  programado para las 20:00 (link mandado a Santi). Ya estaba prendido (`animacion.facebook`). (3) **Así Nació
  más visual** (`visuales.py`, `animacion.visual_plus`, APAGADO): Haiku propone por escena rótulo de noticiero
  (año · lugar), número gigante, tarjeta de cita (solo si está literal en el artículo), cartel de cómic y el
  momento del día; el código lo valida contra el texto. Render: mapa con pin que hace zoom (escena de 1,4 s con
  NASA Blue Marble, la primera vez que aparece un lugar con coordenadas), la luz del momento (atardecer, noche),
  cámara de cerca / de lejos / desde abajo rotando entre escenas, y Tito en una ventanita reaccionando cada ~9 s.
  **Prueba con el Cubo de Rubik** (mismo guion y voz, en la Pi): render 550 s contra 558 s del de hoy, pico
  84,7 °C contra 85,2: no suma tiempo ni calor; Haiku ~13 s y < US$ 0,01. Mandado a Santi para aprobar.
- v1.10.0 (2026-11-15, tarde) — **Candidatos descartados en la bitácora** (Santi; Lo Encontré lo hace él en su
  chat). Tabla `candidatos_descartados`: cada marca o historia que se cae antes de armar el video, con el paso
  (puntaje, fotos, guion, voz, render, otro), el motivo concreto, lo que costó en Claude hasta ahí (en el
  puntaje, su parte del pedido; en guion y fotos, lo gastado desde que se empezó con ese candidato) y, en
  fotos, qué se buscó (`mostrar` de cada frase) y qué se encontró. Se anotan: marcas debajo de 8 o sensibles y
  guiones que no validan (Así Nació); hechos de tecnología debajo de 7,5; historias de Latinoamérica debajo del
  puntaje; guion o fotos que fallan en los dos; y el video ya elegido que falla en la voz o el render. Sale en
  `/costos` y en el resumen de los lunes (por paso: cuántos, cuánto costaron, motivos más repetidos y un
  ejemplo de fotos). Nada más cambió. 1463 tests OK.
- v1.09.0 (2026-11-15, tarde) — **Bitácora de cada video** (Santi: "para después mejorar costos y tiempos";
  `bitacora.py`, tabla `videos_registro`, formato común en `docs/registro-videos.md`). Por video: canal y
  formato, costo de Claude por paso (elegir, guion, corrección, fotos, revisión visual, final, dibujos) con
  modelo e intentos, voces de Gemini y reintentos, segundos por etapa (búsqueda, guion, fotos, dibujos, voz,
  whisper, revisión, render, subida) y total, temperatura máxima y si se frenó por calor en el render, falla
  (paso y motivo) y estado (publicado/cancelado salen de `subidas`). Claude y las voces salen de `gemini_uso`
  por rango de filas del tramo; un video aprobado más tarde suma su tramo (`retomar`). Así Nació, la de
  tecnología y las de Latinoamérica ya registran; **Lo Encontré todavía no** (otro repo: tiene que escribir la
  misma tabla en su base; `/costos` ya la lee de `efemerides.lo_encontre_db`). **`/costos [días]`** (7 por
  defecto): por canal y formato, costo y tiempo promedio por video, fallas, cancelados, frenadas y temperatura;
  las 3 etapas más caras y las 3 más lentas. **Resumen semanal** los lunes desde las 09:00 al privado de
  Santi (`_costos_semana_tick`): lo mismo de la semana (lunes a domingo) y 2-3 ideas concretas sacadas de los
  números (sin gastar un modelo: guiones con muchos intentos, fotos > 30 % del costo, frenadas por calor,
  voces de más, etapas lentas). 1460 tests OK.
- v1.08.0 (2026-11-15, tarde) — Corrección puntual de guiones, Haiku para puntuar, "sorpresa" en las historias
  curiosas, y en Así Nació: protagonista en el gancho, fabricar sin martillo, personajes fieles, época por
  escena y dibujos nuevos con Claude (todo en §1). El inventor de base ya no se parece a una señora (era el
  dibujo de "abuelo" con rulos canosos: ahora jopo y bigote). **Conteo de 14 días (16 al 29/11) puntuando con
  Haiku y con "sorpresa" en las curiosas:** de 7 o más, 1,14 por día (antes 1,21 con Sonnet), de 8 o más, 0,29;
  5 de 14 días sin ninguna de 7; las curiosas de 7+ son 5 en total (3 el 26/11). **Costo del 15/11:** producción
  US$ 5,19, de los que US$ 4,24 fueron 31 guiones enteros de Así Nació (Popeyes y las tandas sin marca de 8):
  justo lo que evita la corrección puntual. Estimado desde hoy: Así Nació ~US$ 0,33 por video (borrador
  US$ 0,13 + ~2 correcciones de US$ 0,07 + revisión), Pequeña Historia ~US$ 0,27 la de tecnología y ~US$ 0,29
  cada una de Latinoamérica (≈1,1 por día) → ~US$ 1,3 por día (≈ US$ 40 por mes). Render de Así Nació: 460-560 s,
  ~15 min por video en total, pico ~85 °C. 1454 tests OK.
- v1.07.0 (2026-11-15, tarde) — (1) **Así Nació: gancho propio, escenarios según la escena, acción y
  personajes** (regla en §1). Nuevo en el motor: fondos `laboratorio`, `hospital`, `campo` y `puerto` (con
  su ambiente y su color), acciones `fabricar`, `vender`, `usar` y `probar`, `multitud` (5-7 personas chicas
  atrás que festejan, saltan o caminan; no cuentan para "nadie encima de nadie"), 12 roles nuevos. Arreglado:
  los efectos del render (polvo, líneas de movimiento, destellos, primer plano) aparecían en la lista de
  objetos del guion y Sonnet los ponía (`EFECTOS_RENDER`). El Kleenex de hoy ya estaba publicado a las 13:19
  (su arranque era el de siempre); el de las 20:00 se rearmó con las reglas nuevas (se cortó el que se
  estaba armando con las viejas). (2) **Latinoamérica: historias curiosas y reales** (`SISTEMA_CLASIFICAR`,
  `SISTEMA_ELEGIR`, tipos nuevos, 18 búsquedas por fecha). **Conteo de 14 días (16 al 29/11) con el tema
  ampliado:** 58 a 138 candidatas con lugar por día, 12 a 31 "buenas" (antes 7 a 35); de 7 o más, 1,21 por
  día (igual que antes), de 8 o más, 0,29; 5 de 14 días sin ninguna de 7 (antes 6) y 10 sin ninguna de 8.
  Ampliar el tema no subió los puntajes: los cuatro criterios (persona, peligro, giro, emoción) castigan a
  las curiosidades sin protagonista ni peligro. (3) **El de las 20:00 de hoy:** Popeyes (la única de 8 en la
  primera tanda) falló 8 veces más; después, ninguna de otras 20 marcas llegó a 8 y quedaba "hoy no sale".
  Ahora: una marca cuyo guion no valida, o las de una tanda donde ninguna llega a 8, quedan afuera ese día
  (`animacion_fallidos:<día>`) y se reintenta en 1 h con otras (la semilla cambia con lo excluido); "no sale"
  solo si no queda ninguna en la rotación. 20 marcas puntuadas por tanda. Arreglado: el chequeo de subidas
  consultaba en YouTube el Reel de Facebook de Así Nació (aviso repetido en el log). 1451 tests OK.
- v1.06.0 (2026-11-15, mediodía) — (1) **Así Nació no salió hoy a las 07:00**: el tercer intento de guion
  pidió 16.000 tokens de salida (casi todo pensamiento) y se cortó (`max_tokens`); los dos primeros fueron de
  14.538 y 7.188. Ahora: `animacion.max_tokens` 32.000; `ClaudeClient` reintenta solo con el doble (hasta
  64.000, por streaming, que la API pide para pedidos largos) antes de rendirse; `escribir_guion` cuenta una
  respuesta cortada como un intento y sigue (`reintentos_guion` 8); y el tick reintenta en 1 h. (2) **2 videos
  por día** (`horas_publicacion` 13:00 y 20:00, `clip_asinacio`: asinacio_AAAAMMDD y asinacio_AAAAMMDD_2,
  estado en `bot_estado.animacion_estado:<día>`); si un reintento termina pasada su hora, sale en 30 min
  (nunca al día siguiente). El de hoy se armó a mano (se borró `animacion_dia` y se reinició la escucha). (3)
  **Pequeña Historia sin aprobar PRENDIDO.** (4) **Latinoamérica con más fuentes** (`locales.leer_todo`):
  anexos de días festivos, feriados, conmemoraciones y fiestas por país (`ANEXOS_PAIS`, medidos con la
  búsqueda por prefijo: México, Colombia, Argentina, Chile, Perú, Paraguay, Bolivia, Guatemala, Honduras,
  Panamá, Uruguay, Puerto Rico y fiestas de provincias argentinas y de La Guajira), personajes y hazañas
  (`buscar_personajes`: el buscador con la fecha y "héroe", "hazaña", "salvó", "rescate"…, solo artículos de
  Latinoamérica), nacimientos y muertes de gente de Latinoamérica (antes solo con conmemoración), y la
  historia de 25 ciudades por día (eran 12) con más frases. Medido para el 16/11: 91 candidatas con lugar.
  Sonnet puntúa hasta 30 (eran 8 de 20). Piso de 7 para una por día (`PISO_UNA_POR_DIA`). (5) **Presupuesto**
  (§1): más fotos y videos por frase para Sonnet, ELEGIDOS 14, MAX_GUIONES 4, 3 reintentos de guion en
  efemérides, 14 marcas y 4 intentos en Así Nació; aviso de presupuesto mensual y el mes en el informe diario.
  (6) **Arreglos después de la primera corrida:** el guion de Popeyes falló 8 veces porque "2" y "4" ("dos",
  "cuatro") no estaban en el artículo: en Así Nació los números hasta 12 no cuentan como cifras
  (`NUMERO_CHICO`); tope de US$ 2 de Claude por video (`TOPE_USD_VIDEO`: pasado eso no se prueba otra marca);
  Haiku clasifica con 32.000 tokens (con 130+ candidatas se cortaba). **Medido hoy:** el primero (Kleenex,
  8,0) salió a las 13:19 (las 13:00 quedaban a menos de 20 min): 915 s en total, render 461 s, pico 85,2 °C,
  Claude US$ 0,68 (4 intentos de guion). **Conteo de 14 días (16 al 29/11) con las fuentes nuevas:** 55 a 136
  candidatas con lugar por día; historias de 7 o más: 1,21 por día en promedio (0 a 6), de 8 o más: 0,36;
  6 de 14 días sin ninguna de 7 y 9 sin ninguna de 8. **Costo del 15/11:** producción US$ 2,78 (US$ 2,20 en
  guiones de Así Nació, por las fallas de Popeyes), pruebas US$ 0,60 (el conteo); el mes va US$ 9,96.
  1438 tests OK.
- v1.05.0 (2026-11-15, madrugada) — Tres pedidos de Santi. (1) **Pequeña Historia: `efemerides.estilo_nuevo`
  PRENDIDO** ("ya apruebo el estilo nuevo, con el feedback de La Pola"); `sin_aprobar` sigue apagado. (2)
  **Costo de Claude en las fotos.** Medido el 14/11: US$ 2,57 en total, pero la producción (la madrugada,
  04:00-04:20 AR) fue ~US$ 0,65; el resto (~US$ 1,92) fueron rehechos a mano de La Pola y Túpac Katari y las
  pruebas de Así Nació. Cada pedido de fotos a Sonnet costaba ~US$ 0,09 (15-21 mil tokens de entrada y 4-7
  mil de salida: ~50 fotos + hasta 4 videos × 3 cuadros por frase de acción, y un `tipo` por cada foto).
  Ahora (`efemerides.prefiltrar_fotos`): Haiku describe cada foto UNA vez (guardada por huella en
  `data/cache_claude/fotos/`: la segunda búsqueda y los rehechos no la vuelven a pagar) y, solo con texto,
  ordena; Sonnet mira las 3 mejores por frase (la frase 1, 4) y los 2 mejores videos por frase; si Haiku
  falla, Sonnet mira todo como antes. Las imágenes ya iban a 384 px (menos que los 512 que sugirió Santi).
  Además, un pedido CON imágenes idéntico a uno anterior sale de la caché (`data/cache_claude/`, 30 días).
  Primer dato real (15/11, tecnología, todavía sin el recorte de videos): Sonnet miró 19 de 33 y 18 de 43
  fotos; pedidos de US$ 0,097 y 0,046 (Haiku: US$ 0,003 cada uno). (3) **Informe diario del costo**
  (`_costo_claude_tick`, desde las 09:00, el de ayer; `gemini_uso.origen`): Producción (los ticks de la
  escucha, `diario` y `efemeride-diaria`), A mano por Telegram (comandos y botones) y Pruebas (scripts y
  CLI). Arreglado de paso: lo que pasaba por `ConRespaldo` se anotaba como "claude.json". (4) **Así Nació:
  estilo visual nuevo** (regla en §1; `tests/test_visual_asinacio.py`). Nerf rehecho con el mismo guion, voz y
  tiempos del 14/11 (en la Pi: `~/remotion_prueba/nerf/nerf_visual_v2.mp4`, mandado a Santi). **Render en la
  Pi: 512 s contra 134 s del motor de ayer (+378 s, ~3,8×), pico 84,2 °C (antes 83,7)**, 1 proceso,
  arrancando a 65 °C. Medido por partes en la Pi (ms por cuadro): plano 310, todo 565; los degradés
  ~120, el contorno doble ~65, el resto (detalles, efectos, la segunda llamada de los subtítulos) ~70. Las
  formas chicas (< 34 px) quedan planas (bajó de 544 a 512 s); el tinte y la viñeta se rasterizan una vez
  por lugar (como SVG costaban ~30 % de cada cuadro). 1434 tests OK.
- v1.04.0 (2026-11-14, noche) — Así Nació dibuja con **1 proceso de cairosvg** (`animacion.procesos: 1`,
  antes 2; pedido de Santi: "dejalo si tarda casi lo mismo"). Medido en la Pi con el demo de 35 s
  (x264 con 3 hilos, arrancando debajo de 62 °C): 2 procesos 157 s y pico 84,2 °C, 1 proceso **134 s**
  y pico 83,7 °C (0,123 s por cuadro); mismo mp4. Con 2, los procesos de dibujo le peleaban la CPU a ffmpeg.
- v1.03.0 (2026-11-14, noche) — Santi aprobó los subtítulos virales de Así Nació
  (`animacion.subtitulos_virales: true`, la regla va en §1). Pendientes anotados: medir de nuevo cuando
  ponga disipadores en el chip, y que Lo Encontré respete la pausa para enfriar (en su propio chat).
- v1.02.0 (2026-11-14, noche) — **Calor de la Pi.** Diagnóstico (solo medir): nunca hubo falta de corriente
  (bit 16 de `get_throttled` en 0), sí frenadas por calor; sin overclock (1,8 GHz de fábrica); ningún
  proceso consume de más en reposo; Lo Encontré y clips comparten el turno pesado (no se superponen).
  El ventilador es un **Pimoroni Fan SHIM** (GPIO 18) y nadie lo controlaba. Ahora: (1) `ventilador.py`
  + servicio de USUARIO `ventilador.service` (`loginctl enable-linger santi`, arranca solo con la Pi;
  `systemctl --user status ventilador`, log en `journalctl _SYSTEMD_USER_UNIT=ventilador.service`): prende
  desde 55 °C, apaga debajo de 48 °C, siempre prendido con el turno pesado tomado, pin en alto si el
  servicio se cae (`pinctrl`, sin sudo); (2) pausa para enfriar: el turno pesado no arranca un render nuevo
  arriba de 65 °C en los 10 min que siguen al anterior (`db.TEMP_ARRANQUE_C`, `PAUSA_MAX_S`); (3) x264 con
  3 hilos en todos los encodes (`media.X264`, `CLIPS_FFMPEG_HILOS`). Medido con el mismo render sintético
  (antes → después): ffmpeg 1.252 → 1.434 MHz de media y frenada 35 % → 17 % del tiempo, pero el pico sigue
  en ~86 °C y tarda 755 → 840 s; la animación (2 procesos de cairosvg + ffmpeg) no mejoró (31 → 33 %).
  Conclusión: el Fan SHIM solo no alcanza a carga completa. Los subtítulos virales de Así Nació quedaron
  detrás de `animacion.subtitulos_virales: false` (así se pudo desplegar). 1417 tests OK.
- v1.01.0 (2026-11-14, noche) — **Subtítulos estilo Shorts virales en Así Nació** (commit `8a7e7b1`,
  en los dos motores, **NO desplegado en la Pi** hasta el OK de Santi): grupos de 1-3 palabras,
  Montserrat Black (SIL OFL 1.1, `assets/fuentes/` con su OFL.txt) dibujada como trazos (`letra.py`,
  `montserrat_black.json`: sale igual en cairosvg, resvg y Chrome), contorno negro grueso y sombra
  suave, "pop" a 112 % en 0,16 s desde el inicio de cada palabra según Whisper, claves (las marca el
  guion con `claves`/`emoji`, regla 9 del prompt; Haiku las agrega si faltan; ≤ 2 por frase; los
  números cuentan) más grandes y amarillas, rojas y temblando 0,45 s cerca de un golpe o en el remate,
  emojis dibujados por código (💥💰😱🤣, sin fuente de emojis ni atribución) ≤ 1 cada 4,5 s al lado de
  una clave, franja de arriba (y 168-294, ancho 93-996; si no entra, se achica la clave y después el
  grupo). Nerf: 4,8 min (actual) y 8,4 min (Remotion). 1411 tests OK. También: Facebook de Así Nació
  conectado (página «Asinacio.oficial»; el token de usuario había quedado pegado sobre el de Pequeña
  Historia en el .env de la compu: se restauró desde la Pi) y §10 reescrito.
- v1.00.0 (2026-11-14, noche) — **Prototipo de Así Nació con Remotion (NO en producción)** y análisis de
  Pequeña Historia. (1) Licencia de Remotion: gratis para una persona sola, también con fines
  comerciales (remotion.dev/docs/license/faq). (2) En la Pi (Node 24 del sistema + el navegador headless
  arm64 de Remotion, sin sudo): 35,8 s de video en 9,1 min con concurrencia 2 (0,51 s/cuadro), 86 °C
  como el motor actual; 3-4 no aceleran. (3) Estilo nuevo: sombras y brillos planos, contornos de
  grosor variable, más detalle, cuartos en perspectiva con parallax; mismo esqueleto y posiciones que
  el motor actual (sirven los chequeos). Open Peeps (CC0) no se usó: no encaja con el estilo. Código en
  `clips_bot/animacion_remotion/` y `remotion/` (`node_modules`, `out/` y lo generado fuera de git).
  Nerf con los dos motores mandado a Santi (actual 5,4 min de render, Remotion 10,1 min). Falta para
  producción: conectarlo a `marcas.armar_video` detrás de un interruptor (con el actual de respaldo),
  revisión visual sobre los cuadros de Remotion, `npm ci` en `~/clips/remotion`, redibujar los objetos
  que faltan. (4) Skill oficial `remotion-best-practices` en `.claude/skills/` (fuera de git). (5)
  Pequeña Historia: el análisis del Short de Intel (3.220 vistas el 14/11, rompió el techo de ~1.200)
  llega solo cuando Analytics tenga sus datos (`analisis_video_pedido`), y si tecnología rinde ≥ 1,3×
  Latinoamérica en YouTube (≥ 4 y ≥ 6 videos con 3 días) llega la propuesta de mezcla 2 + 1. 1401 tests OK.
- v0.99.0 (2026-11-14, noche) — **Así Nació PRENDIDO y conectado** (Santi aprobó el Nerf). Canal de
  YouTube @asinacio.oficial («Asinacio.oficial», `UCPUKDAf5NJbdINUC2Rka69A`) conectado con
  `youtube-auth animacion` desde la compu (token en `config/youtube_token_animacion.json` de la compu y
  de la Pi, chmod 600, fuera de git; verificado desde la Pi). `animacion.activo/subir: true`: la escucha
  arma 1 video por día desde las 07:00, lo programa en YouTube para las 19:00 AR
  (`_animacion_subir` → `_programar_subida(canal="animacion")`, categoría 24, crédito de la música en
  la descripción) y lo manda al privado con "🤖 Se publica sola" y un botón ❌ Cancelar
  (`sub:x:asinacio_AAAAMMDD`; el meta queda al lado del video, no en ready/). El Reel en la página de
  Facebook de Así Nació está preparado (`animacion.facebook`, apagado hasta tener
  `ASINACIO_FACEBOOK_PAGE_ID` y `ASINACIO_FACEBOOK_PAGE_TOKEN` en el .env; canal `facebook_asinacio`
  en `subidas`). El 14/11 se marcó como hecho (`animacion_dia`): el primero se arma el 15/11 y sale a
  las 19:00. Perfil: Tito con fondo celeste (#7cc6ee). Banners de YouTube rehechos con todo dentro de
  1300x350; el de Así Nació, como escena del taller de Tito (2 opciones + portadas de Facebook).
  1394 tests OK.
- v0.98.0 (2026-11-14, noche) — **Así Nació: ritmo, subtítulos arriba, composición, revisión visual,
  perfil al caminar, época en todos los lugares y audio** (REGLAS PERMANENTES, guion + escenas +
  chequeo): (a) 30-40 s con ritmo: voz ×1,13 sin cambiar el tono, pausas ≤ 0,22 s, cambio de plano en
  las escenas de más de 2,6 s; si la voz real sale de 30-40 s se reescribe el guion (nunca se acelera
  más); (b) subtítulos chicos en una franja angosta ARRIBA, debajo de la interfaz de Shorts; nada de la
  escena sube a esa franja; (c) composición: muebles contra la pared a los costados y detrás de los
  personajes, objetos en la mano o sobre algo lógico, ningún brazo u objeto sobre una cara, nada
  tapado: lo verifica y corrige el código cuadro a cuadro; (d) **revisión visual** antes del render:
  Sonnet mira 8 cuadros clave a 512 px, se corrige el guion de la escena marcada (máx. 2 vueltas) y
  queda anotado en el mensaje; (e) de perfil al caminar o correr de costado, de frente quietos; (f)
  decoración de época también en calle (auto, farol, vidriera), fábrica y tienda; (g) música de
  `musica.py` con ducking y SFX sintetizados, con los niveles medidos en el mensaje (voz −15,8 dB,
  música −27,6, SFX −27,3, mezcla −14,0). Nerf: 28,8 s (corto: el alargue de guiones cortos se sumó
  después y no está probado), render 221 s, Claude US$ 0,20. Imágenes de Tito con fondo plano o
  patrón de productos (sin rayos). Así Nació sigue APAGADO. 1390 tests OK. Después (Santi: "un pelín
  rápido"): voz ×1,065 (no ×1,13), la duración real de la voz tiene que caer en 32-38 s (si no, se
  reescribe el guion; nunca más aceleración) y 6 intentos de guion; Nerf: 33,7 s, render 262 s.
  Tito en 5 fondos lisos (mostaza, naranja, turquesa, rojo ladrillo, celeste) mandado para elegir.
- v0.97.0 (2026-11-14, noche) — **Así Nació: movimiento, sin superposiciones, escenarios de época y
  objetos con detalle** (Santi: "muchísimo mejor"; REGLAS PERMANENTES, en el guion y en el chequeo
  código + Haiku con reintento): (a) movimiento con peso: caminar y correr con ciclo (cadera, rodilla y
  pie; brazos en contrafase, rebote, cabeza), anticipación y squash & stretch en saltos y golpes, la
  cara cambia con la acción (caras nuevas: risa y grito); nadie queda de piedra; (b) nunca un personaje
  encima de otro: cada uno en su carril sin cruzarse, Tito en el borde libre; chequeo cuadro a cuadro en
  código; (c) escenarios de la época de la historia (la década sale del viaje en el tiempo: papel de
  pared, sillón, alfombra, cortinas, gramófono / radio y teléfono de disco / equipo de música / planta;
  oficina con máquina de escribir o monitor) y variados; dos escenas seguidas en el mismo lugar no son
  idénticas; (d) el objeto protagonista dibujado con detalle, que se entiende sin leer, en 2 o más
  escenas (pelota de espuma, juego de mesa, hamburguesa, chocolate, galletitas, auto, teléfono de
  disco, radio, consola); nada de cajas con un rótulo. Remotion no hizo falta. Nerf: 42 s, render 366 s,
  Claude US$ 0,30 (3 intentos). Flojo: personajes siempre de frente, la década solo cambia casa y
  oficina, cajas de superposición aproximadas con objetos grandes. 1342 tests OK.
- v0.96.0 (2026-11-14, noche) — **Así Nació (canal de marcas animadas): reglas permanentes, Tito y
  viaje en el tiempo** (feedback de Santi sobre Nerf y Monopoly: "dos personajes hablando no
  engancha"). REGLAS para TODOS los videos del canal, en el guion, las escenas y el chequeo (código +
  Haiku, con reintento mostrando los errores): (a) mostrar, no contar: cada frase es una escena con
  acción, nada de personajes parados hablando; (b) gancho de < 3 s con destrucción en cadena de 2-4
  cosas (pelota → tele → lámpara → cuadro), cada golpe con su sonido y un sacudón chico; (c) el
  locutor fijo es el **Abuelo Tito** (`animacion/tito.py`: guardapolvo, antiparras, bigote, reloj de
  bolsillo dorado; `tito_svg(pose)` / `tito_cara_svg()`), que interrumpe 1-3 veces con la escena
  congelada en gris; (d) toda empresa o persona se presenta en pocas palabras la primera vez, en orden
  problema → idea → qué pasó → final sorpresa; (e) escenas con sentido: cada objeto con su `soporte`
  real (piso, mesa, estante, pared, mano), nada aparece ni cae de la nada (solo íconos en el aire, solo
  billetes o monedas llueven); (f) **viaje en el tiempo** cuando la historia cambia de época (≥ 10
  años): Tito levanta el reloj, remolino, el año contando hacia atrás, el pasado en sepia, y al revés al
  volver (1,25 s); (g) subtítulos chicos (60 px) en una franja semitransparente abajo que no pisa a los
  personajes; SFX sintetizados (`animacion/sfx.py`), música baja. Remotion no hizo falta (SVG alcanzó).
  Nerf nuevo: 40,9 s, render 343 s en la Pi, Claude US$ 0,37 (4 intentos de guion: el chequeo es
  exigente, US$ 0,20-0,40 por video). **Chats:** Pequeña Historia (`efemerides.chat`,
  `historias_fb.chat`) y Así Nació (`animacion.chat` vacío) van al privado de Santi; el grupo "Rots
  clips" queda solo para Rots (apagado). Sigue flojo: personajes siempre de frente, esquinas negras en
  el remolino, pausas del pasado en color, la voz de Tito es la del narrador. 1267 tests OK.
- v0.95.0 (2026-11-14, tarde) — **Por qué el 14/11 no salió nada y el feedback de los ejemplos.**
  (1) La madrugada corrió bien sin Rots (04:00 tecnología y Latinoamérica). Tecnología: la mejor,
  Netscape 6, 7,25 (< 7,5). Latinoamérica: La Pola (8,5) y Túpac Katari pasaron el puntaje pero el
  control del 70 % las frenó (68 % y 62 %): en las frases centrales solo valían fotos de época y el
  resto eran tarjetas. Ahora (`ESCENAS_EN_CENTRALES`) las centrales buscan también 2 escenas de
  Pexels y el modelo puede poner una **escena ilustrativa** ("un preso leyendo papeles": lo que pidió
  Santi) si no hay foto real, sin confundir sobre lo central (nada de una cara que pase por el
  protagonista, ni otro lugar, ni nada moderno); responde `escena` (obligatorio) y una escena no sale
  por `de_epoca` ni `seguro`. (2) El gancho con la foto MÁS llamativa (una cara humana clara del
  protagonista si hay), no la más oficial. (3) El mapa con zoom llega al lugar justo cuando la voz lo
  dice (`momento_de_palabra`, `insertar_tramo`, `mapa_zoom(llegada=)`). (4) Humor suave en los guiones
  cuando la historia lo permite, nunca en muertes, ejecuciones, tragedias ni temas sensibles. (5)
  **Canal de marcas animadas conectado y APAGADO** (`animacion.activo: false`, `animacion/marcas.py`,
  `marcas.yaml` con 457 marcas y 824 pares marca-ángulo verificados en es.wikipedia, tabla
  `animacion_videos`: un ángulo nunca se repite y una marca no vuelve en 7 días; Sonnet puntúa 8
  candidatos en marca conocida, dato sorprendente, giro y humor, pasan ≥ 8; guion validado contra el
  artículo; `_animacion_tick` desde las 07:00, fuera de 03:45-06:00, manda a Telegram y no sube nada).
  Ejemplos mandados a Santi: Nerf (8,25, 40,5 s, render 252 s, Claude US$ 0,087) y Monopoly (9,25,
  45,4 s, 283 s, US$ 0,098). (6) Diseño de retención y alcance en `docs/diseno-retencion-alcance.md`
  (Instagram, TikTok, final en loop, música con tensión y efectos, grupos de Facebook): sin programar.
  Los de hoy se armaron a mano con el estilo nuevo forzado en memoria (el interruptor sigue apagado).
  1092 tests OK.
- v0.94.0 (2026-11-14) — **Rots apagado, Pequeña Historia sin aprobar y con estilo nuevo (los dos
  APAGADOS hasta que Santi apruebe), ElevenLabs preparado, base de animación y nicho** (pedido de
  Santi en dos partes: investigación + mejoras con diseño y ejemplos antes de activar). (1) **Rots
  APAGADO** (`publicacion.rots: false`): `cmd_diario` no corre (ni la de las 03:30 ni el timer de
  las 05:00), sin "pegó", modo en vivo, reintento de clips ni /ya; Pequeña Historia ya no lo espera
  (`_rots_listo(settings)`). /buscar a mano sigue. Los tests de Rots usan el fixture `rots_prendido`.
  (2) **Sin aprobar** (`efemerides.sin_aprobar`, apagado): las 3 diarias se arman en el mismo turno
  (`_efe_auto` → `_efe_armar(auto=True)`), se programan con `_subir` ANTES de mandarse y llegan con
  "🤖 Se publica sola" y ❌ Cancelar; /efemeride e /historia a mano siguen con ✅. (3) **Estilo nuevo**
  (`efemerides.estilo_nuevo`, apagado): el gancho como montaje de hasta 3 imágenes con golpe de zoom
  y whoosh (`plan_rapido(montaje=True)`, movimiento "golpe"; con video en la frase 1, el video), el
  mapa a pantalla completa acercándose al lugar en la de Latinoamérica (`graficos.mapa_zoom`, tramo
  `MAPA` al empezar la 2.ª frase; si el artículo es de una persona, las coordenadas del lugar), el
  gancho entrando palabra por palabra con rebote (`gancho_animado`, un solo evento con `\t` por
  palabra), subtítulos de 100 px con borde 9, 2-3 palabras y la activa con un saltito (`REBOTE`), y
  hasta 6 frases buscando video (`frases_video`: gancho, acción y lo que se nombra al pasar en Pexels;
  `recortar_videos` para no pasar las 100 imágenes de Claude). (4) **ElevenLabs preparado**
  (`elevenlabs.py`): solo con `ELEVENLABS_API_KEY` en el .env y `efemerides.elevenlabs_voz`; si falla,
  la voz de siempre; CLI `voces-elevenlabs [--muestra <id>]`. (5) **Arreglo en producción:** el gancho
  escrito no hacía salto de línea (WrapStyle 2) y desde el 12/11 salía cortado a los costados
  (`lineas_gancho`, 18 letras por línea). (6) **Base de animación** (`clips_bot/animacion/`, sin
  conectar al bot): personajes y escenas SVG por código, línea de tiempo en JSON, cairosvg →
  ffmpeg; en la Pi 45 s de video en ~170 s (0,12 s por cuadro, 1 proceso; el cuello es x264), pico
  84 °C. (7) **Nicho** (`docs/nicho-animacion/informe.md`, 5.692 unidades de la API): top 5 =
  origen de las palabras, origen de marcas, economía con historias, cuerpo humano, mitología.
  **Ejemplo de La Pola** con el estilo nuevo (en la Pi): propuesta 562 s, video 390-503 s, Claude
  US$ 0,36. Encontrado armándolo: la misma foto de Commons entraba dos veces al pool ("Archivo:" y
  "File:"; `clave_archivo`), y el montaje toma la mejor foto de las frases siguientes si la del
  gancho tiene pocas. 1043 tests OK.
- v0.93.0 (2026-11-13) — **Final que paga, puntaje de tecnología y costo real de Claude** (Santi,
  después de ver los guiones del 14/11). (1) **Segunda revisión del final** (`ef.final_que_paga`,
  `SISTEMA_PAGO`, dentro de `escribir_guion`, `revisar_final=True`, en los 3 videos): el mismo
  cliente (Claude) mira si la última o la anteúltima frase responde la pregunta del gancho (en La
  Pola el gancho prometía el billete y el final hablaba del Día de la Mujer); si no, reescribe solo
  las dos últimas y se vuelve a validar todo; si lo nuevo no valida (o Claude no responde), queda el
  guion como estaba. (2) **Puntaje de la de tecnología** (`ef.elegir(notas=)`, `CRITERIOS_TEC` marca,
  sorpresa, consecuencia y final, 1-10; `PUNTAJE_TEC_MIN` 7,5; ejemplo de 10: el error que le hizo
  perder a Netscape la guerra de los navegadores): pasan las de 7,5 o más, de mejor a peor; si
  ninguna, `SinTema` (no sale y se avisa); el puntaje va en la aprobación ("💻 TECNOLOGÍA (solo
  YouTube) ⭐ …", `_encabezado_tec`, `Propuesta.local`). (3) **Costo real de Claude**
  (`claude.resumen_costo` / `texto_costo` por tarea desde `gemini_uso`; `costo()` reconoce los
  modelos con versión, antes un Haiku con versión se cobraba como Sonnet); `_costo_claude_tick`
  manda el del día pedido en `bot_estado.costo_claude_pedido` apenas termina ese día; CLI
  `costo-claude [--dia]`. Pedido cargado: el 14/11. Probado con el guion real de La Pola: la primera
  pasada no ponía el billete porque la revisión veía solo los primeros 8.000 caracteres del artículo
  y el billete está en "Homenajes"; con el artículo entero (20.000) la anteúltima quedó "Su valentía
  la hizo heroína y estuvo en el billete de 10 000 pesos." 949 tests OK.
- v0.92.0 (2026-11-13) — **Guiones que retienen y texto con Claude** (dos pedidos de Santi). (1)
  **Segunda frase con intriga** (`SISTEMA_GUION` y el de Latinoamérica): sin "En <año>, en <lugar>,";
  el año (y el lugar en Latinoamérica) se dicen en la 3.ª o 4.ª (`validar_guion`, `validar_lugar`),
  y en pantalla desde la 2.ª hasta que empieza la 3.ª (`anio_contando(hasta=)`,
  `graficos.lugar_en_pantalla`, estilo `Lugar`). (2) **Estructura** gancho → tensión → giro → pago:
  el guion devuelve `pregunta_gancho`, `frase_tension`, `frase_giro`, `frase_pago`
  (`errores_estructura`: tensión desde la 3.ª, en orden, el pago en la última o la anteúltima); la
  pregunta sale en el mensaje de aprobación. (3) **Latinoamérica 30-40 s** (`ef.a_corto(segundos,
  palabras, frases)`, 70-90 palabras pedidas, 65-95 validadas, voz hasta 40 s: `LATAM_PALABRAS`,
  `LATAM_MAX_S`, `Guion.max_s`); tecnología sigue en 20-30. (4) **Puntaje de las historias**
  (`locales.elegir`: Sonnet da `persona`, `peligro`, `giro`, `emocion` 1-10, Nacozari como 10;
  `proponer` deja solo las de promedio ≥ `PUNTAJE_MIN` 8, ordenadas por puntaje con el calendario
  primero; si ninguna, NarrarError → "hoy sale 1 de 2" / "no hay propuesta"). El encabezado de la
  aprobación pasa a "🌎 LATINOAMÉRICA (YouTube y Facebook)" con el puntaje (decía "SOLO FACEBOOK").
  (5) **Texto con Claude** (`claude.ConRespaldo`, `claude.para_texto`, `textos.motor: claude`,
  `process.cliente_textos`): textos de Rots y chequeo visual con Sonnet, desempate con Haiku, y la
  de tecnología (elegir, guion, ✏️ y acortar: `ef.proponer(texto=)`, `rehacer_guion(texto=)`,
  `_texto_efemeride`) con Sonnet; Gemini de respaldo si Claude falla, y para audio. (6) Encontrado
  armando la vista previa del 14/11: las dos únicas de 8 o más eran LA MISMA historia (La Pola como
  nacimiento y como fusilamiento, mismo artículo) y habrían salido las dos: ahora tampoco se repite
  el artículo del hecho en el día (`ph_latam` guarda `articulo`). 946 tests OK.
- v0.91.0 (2026-11-12) — **Todo en Telegram antes de las 05:30** (Santi). Los timers (05:00 clips,
  06:00 efeméride) no se pueden mover sin la contraseña de Santi (sudo solo permite `restart` de
  los servicios), así que la **escucha arma la madrugada** (`_madrugada_tick`): a
  `publicacion.hora_rots` (03:30) lanza la corrida de Rots con `sudo -n systemctl restart
  clips-bot.service` (sin esperarla) si el turno está libre; apenas termina (`DIARIO_FIN`), la de
  tecnología (`efemerides.hora_propuesta` 04:00, con el turno, `efemeride_del_dia`); y después las 2
  de Latinoamérica (`historias_fb.hora` 04:00, `_fb_tick` espera a Rots y a la de tecnología, o
  hasta las 05:30). "Pegó" pasa a la 01:30 (termina a las 03:00 como mucho). Los timers de 05:00 y
  06:00 quedan de **respaldo**: `cmd_diario` no corre si la de hoy terminó o está andando
  (`_ya_corrio_hoy`) y `efemeride-diaria` no corre si ya se propuso (`EFE_DIA`). Los horarios de
  publicación no cambian. La fecha de la historia es la del día en Argentina (a las 04:00 AR ya es
  el día nuevo también en UTC). OJO: la cuota gratis de Gemini se renueva a las 05:00 AR; a las
  03:30-04:30 queda lo que sobró del día anterior (la principal suele estar sin flash: la segunda
  clave y flash-lite), así que los textos de Rots y de la de tecnología pueden salir con el modelo
  de respaldo, y si no hay nada, el reintento de siempre en una hora. 940 tests OK.
- v0.90.0 (2026-11-12) — **Nicho y cantidad de Pequeña Historia** (§1). (1) **2 historias de
  Latinoamérica por día** (`historias_fb.por_dia`): `_fb_tick` propone hasta 2 con el mismo turno;
  `locales.proponer(excluir, evitar_paises)` saltea lo ya propuesto ese día (`bot_estado.ph_latam:<día>`)
  y deja al final los de un país que ya salió (`otro_pais_primero`, también después de Sonnet); si
  la segunda no sale, "hoy sale 1 de 2 (no relleno)". 📤 las sube a Facebook (a la mañana del país,
  `separar_de_otras` 4 h) y, nuevo, a YouTube (`historias_fb.youtube`). (2) **La efeméride es la de
  tecnología e internet** (`efemerides.tema`, `ef.TEMAS`, `elegir(tema=)`: si ninguno es del tema,
  lista vacía → `ef.SinTema`, aviso sin reintentos), en el **formato corto** (`efemerides.corto`,
  `ef.SISTEMA_GUION_CORTO` = `ef.a_corto(SISTEMA_GUION)`, que también arma el corto de Facebook) y
  **solo en YouTube** (`facebook.efemeride: false`). (3) **YouTube a 4 h** (`hora_ph_youtube`,
  `efemerides.horas_youtube` 11:00/15:30/20:00, `separacion_youtube_h` 4): el primer horario libre
  que no pasó; `_programar_subida` ya no frena la de YouTube porque haya una de Facebook del mismo
  clip. (4) **Voces** (`voces.py`, `_voces_tick`): las de hoy (día de California) por clave, la
  principal sumando las de Lo Encontré (`~/bot-videos/data/bot2.db`, `tts_uso:<día>`: comparten la
  GEMINI_API_KEY, comparado por huella); aviso a Santi al llegar a `tts_aviso` (8) de `tts_tope` (10,
  el que asume Lo Encontré; Google no lo publica). (5) **Seguimiento** (`medicion_ph`): a los 14 días
  (26/11) contra los 10 Shorts anteriores: % que se queda **calibrado con Studio** (Nacozari 63,9 /
  Beatles 61,6 / Capilla 28,4 contra 56,1 / 50,3 / 28,2 de `engagedViews/views`; recta por mínimos
  cuadrados, ±3 puntos; filtrar solo el feed de Shorts no cambia nada: 56,3 / 50,9 / 27,9), vistas,
  **segundo empujón** (un día con ≥ 25 % del primero), % de vistas de suscriptores (lo más parecido
  a "vuelven": la API no tiene `viewerType`; hoy 12 de 12.691 vistas son de suscriptores) y
  tecnología contra Latinoamérica. **Costo medido por día:** Claude ≈ US$0,20-0,25 por historia
  (elegir 0,007 + guion ~0,12 + fotos ~0,07-0,14) y ≈ 0,07-0,14 por la de tecnología (solo las
  fotos) → ~US$0,55-0,65 por día; voces 3 de PH (las 2 de Latinoamérica por la segunda clave) + las
  de Lo Encontré (0-4) en la principal; Pi ~13-15 min por video (propuesta 6-9 + video 6-7). 937 tests OK.
- v0.89.0 (2026-11-12) — **Gancho primero en todo Pequeña Historia** (Santi, con el diagnóstico de
  YouTube: 13 Shorts, cada uno ~1.150-1.290 vistas el primer día y casi nada después, 94-98 % del
  feed de Shorts, `engagedViews/views` 41-56 % (Capilla Sixtina 28 %), 0-2,7 compartidos cada
  1.000; y en Facebook la mayoría se iba en el 0:04). (1) **Guion:** la PRIMERA frase es el gancho
  (lo más sorprendente, ≤ 14 palabras, sin el año, sin "Un día como hoy", "¿Sabías que…?" ni "Hoy
  te cuento") y la SEGUNDA arranca con "En <año>," (en Facebook "En <año>, en <lugar>,"), en
  `SISTEMA_GUION`, el hablado, `SISTEMA_GUION_LOCAL` y el corto; `validar_guion` lo exige en los dos
  formatos, `validar_lugar` mira las dos primeras frases, `acortar_guion` mantiene el "En <año>,".
  (2) **Arranque del video:** `narrar.sacar_silencio_inicial` (la voz arranca en el cuadro 1, deja
  0,02 s); `graficos.gancho_en_pantalla` (la primera frase escrita en grande, amarilla, arriba,
  desde el cuadro 0 sin fundido de entrada, hasta que empieza la segunda frase); el año contando
  pasa a la segunda frase (`anio_contando(inicio=)`) y las palabras clave después; karaoke en los
  dos formatos; la portada (`PORTADA_S` 0,8 s) muestra el gancho. (3) **La primera foto es la más
  impactante:** el elector de fotos devuelve `impactantes` y la primera que sirve para la frase 1 va
  primera (`elegir_fotos`). (4) **Interruptores PRENDIDOS:** `efemerides.imagen_frase: true` y
  `historias_fb.formato_corto: true` (con `render.edicion_rots: true` de antes). (5) **Medición**
  (`medicion_ph.py`, `_medicion_ph_tick` desde las 09:00, una vez por día): Facebook = el segundo en
  que la retención (`post_video_retention_graph`) baja del 50 %, reproducciones y tiempo medio;
  YouTube = % que se queda (`engagedViews/views`) y vistas; en `bot_estado.ph_medicion`; el
  **19/11** le llega a Santi antes contra después (medianas) y video por video; CLI `medicion-ph
  [--enviar]`. El cierre no se tocó. `tests/test_gancho_primero.py`. 929 tests OK.
- v0.88.0 (2026-11-11) — **Feedback del ejemplo nuevo** (Santi: "mejoró mucho"; le gustaron el
  karaoke, la info, las fotos y la tarjeta de una palabra tipo "2022"). (1) **Ninguna foto en más de
  2 cortes** del corto (`plan_rapido`: cada corte cuenta, aunque sea la misma foto con otro
  movimiento; el acta de Cartagena salía en 3 cortes y 5,9 s seguidos al principio): si no queda
  otra, una **tarjeta** (`fabrica_tarjetas`: la clave de la frase, el año, otra clave; base que
  rota) y el 70 % se mide sobre el corto tal cual sale. Las tarjetas vuelven a llevar el año si la
  frase no tiene clave. (2) **Frases sin foto propia → segunda búsqueda** (con la edición nueva):
  en Cartagena la frase 1 solo tenía una vista actual de la ciudad (afuera por época), la 3 pedía
  una bandera española y la 8 una bandera ondeando (ninguna foto); ahora eso, o un corto que
  repetiría fotos, dispara la segunda búsqueda (Commons en general sin la regla de época, Pexels
  para lo que se nombra al pasar) antes que la tarjeta. (3) **Ficción** (efeméride e historia de
  Facebook): NO hechos que pasan dentro de una ficción (`motivo_evento`/`locales.motivo`: "trama de
  una ficción", `_TRAMA`, y en los prompts de elegir); cultura pop solo desde la vida real
  (estreno, lanzamiento, creador, cómo se hizo, impacto, récords); el chequeo del guion la frena
  (`_TRAMA_GUION` "en la serie, Ash…" y `cuenta_trama`). (4) **Voz:** muestras de Fenrir más calmo
  y Achird, Sadaltager y Charon con energía media (`gemini-2.5-flash-preview-tts` + instrucción);
  la de Fenrir salió cortada la primera vez (20,5 de 32 s) y se rehízo. Se aplica cuando Santi
  elija. 921 tests OK.
- v0.87.1 (2026-11-11) — Las fotos que no cumplen la regla fija 1 (menos de 6 distintas, una más
  de 6 s seguidos) ahora también pasan por la segunda búsqueda con Claude antes del hecho siguiente
  (`FotosNoAlcanzan`; el Ash Ketchum del ejemplo se la salteaba). 918 tests OK.
- v0.87.0 (2026-11-11) — **Feedback de Santi sobre Cartagena y Ash Ketchum.** Cartagena (historia
  de Facebook) aprobada. (1) **Ficción** (`SISTEMA_GUION`, vale para la historia de Facebook): series,
  animé, juegos, películas → lo real primero ("el animé de Pokémon cerró la historia de Ash después
  de 25 años") y el personaje como personaje, nunca como si existiera. (2) **Karaoke también en la
  efeméride de YouTube** (con el año contando y las claves de siempre). (3) **Corto: ninguna foto
  más de 4 s seguida** aunque el corte quede de menos de 2,5 s, y **la del gancho hasta 2,5 s**
  (`FOTO_MAX_S`, `GANCHO_MAX_S`, `plan_rapido`, `seguidos_max`): si seguiría la misma, va otra de la
  frase o una del tema general; antes un tramo de 4,1 s quedaba entero. (4) **El ruido del final:**
  era de Gemini TTS (la voz termina, ~0,2 s de silencio y un golpe de -5 dB de 0,14 s, en los dos
  ejemplos); `narrar.limpiar_cola` lo pasa a silencio sin cambiar el largo. (5) **Voz:** probado
  cómo darle tono sin que lo lea: con `gemini-3.8-flash-tts` la instrucción en el texto (en inglés o
  castellano) se lee en voz alta, `systemInstruction` da 400 y una etiqueta [energetic] hace que
  improvise ("Es increíble."); con **`gemini-2.5-flash-preview-tts` y "Say in an energetic, warm
  and natural storytelling voice…: <texto>" sigue el tono SIN leerlo** (Whisper lo confirmó en las
  4 pruebas). Muestras de Fenrir, Puck y Sadachbia con el guion de Cartagena mandadas a Santi; NO
  cambia la voz hasta que elija (`hablar` ya pega la instrucción que termina en ":"). (6)
  **Horarios de Facebook:** la historia a las 08:30 del país de la historia (`hora_historia_fb`,
  `HUSOS_FB` con horario de verano: México 11:30 AR, Colombia y Perú 10:30, Venezuela 09:30,
  Argentina y Chile 08:30; sin país claro 11:00 AR); la efeméride a las 19:00 AR
  (`facebook.hora_efemeride`, antes 12:00); al menos 4 h entre las dos (`separar_de_otras`, sin
  salir del día). 917 tests OK.
- v0.86.0 (2026-11-11) — **Control de calidad de las fotos y calendario de fechas** (pedidos 9 y 10
  de Santi). (1) **70 % de fotos reales** (`efemerides.UMBRAL_FOTOS_REALES`, vale para la efeméride
  y la historia de Facebook, prendida o no la edición nueva): con el plan estimado, si menos del
  70 % del tiempo va con fotos o videos reales (no tarjetas), `FotosInsuficientes`;
  `fotos_con_control` hace una SEGUNDA búsqueda siempre con Claude (`_elector_fotos(reintento=True)`):
  Commons con el título de cada artículo del hecho, sin la regla de época, y en las frases centrales
  vale el retrato del protagonista, el lugar, un monumento o el documento o dibujo del hecho
  (`TIPOS_DEL_HECHO`: la patente). Si tampoco, el hecho siguiente; el de respaldo (menos de 4
  fotos) solo si igual pasa el 70 % (`respaldo_sirve`); si ninguno, `SinFotosReales` → aviso por
  Telegram, SIN video y sin los reintentos de las 07:00/10:00 (`ErrorDefinitivo`). `hacer_video`
  lo vuelve a medir con los tiempos reales de la voz. Visto en el ejemplo del refrigerador de
  Einstein (10/11): ~27 de 37 s con «PATENTE»/«HELADERA» sobre la misma llama difuminada, y la
  palabra cortada a los costados: la tarjeta ahora achica la letra hasta que entre. (2)
  **Calendario** (`calendario.py`): 90 días de fechas de Latinoamérica con su fuente (celebraciones
  con país de la página de cada día de es.wikipedia, el anexo de Venezuela y las fundaciones de
  ciudades), en `bot_estado.calendario_conmemoraciones`; la escucha suma los días que faltan (3 por
  vuelta) y cada lunes desde `historias_fb.calendario_hora` (08:00) le manda a Santi la lista de la
  semana. CLI `calendario [--enviar]`. (3) **Historia de Facebook: el calendario primero**
  (`locales.buenos`/`elegir`): las fechas que se recuerdan hoy (conmemoración, fundación o
  `conmemora` de Haiku) van antes que cualquier otro hecho aunque Haiku no las vea como historia
  humana, y entre ellas México, Colombia, Argentina, Perú, Chile y Venezuela; Sonnet las ve con
  ★ CALENDARIO y el código las pone primero aunque no lo respete. (4) **El día exacto:**
  `_subir_facebook` no sube una historia (ni la efeméride) de un día que ya pasó.
  `tests/test_calidad_calendario.py`. 910 tests OK.
- v0.85.0 (2026-11-10) — **Feedback de Santi sobre los 3 ejemplos.** (1) **Rots: aprobado y
  PRENDIDO** (`render.edicion_rots: true`). (2) Pequeña Historia (sigue APAGADO hasta que apruebe
  los ejemplos nuevos): **Claude (Sonnet) elige y verifica las fotos** (`claude.ClaudeClient.json`
  acepta imágenes, hasta 100 por pedido; `_elector_fotos`, va con `efemerides.imagen_frase`) y
  Gemini queda de respaldo si Claude falla. El guion marca cada frase `central` (cuenta el hecho:
  solo fotos reales del hecho o del lugar, nada de stock ni de "objeto": el pueblo inundado, ESE
  pueblo) o al pasar (un muro, Pokémon, un tren: foto genérica de Commons o Pexels, sin regla de
  época ni de anacronismo, `sin_epoca`); por frase central hasta 3 del hecho, por frase al pasar
  1 del hecho + 2 del objeto en Commons + 2 de Pexels (pool hasta 56). Sin tarjetas con un texto
  que no tiene que ver (`texto_tarjeta(solo_clave)`: solo una clave de ESA frase, nunca el año
  suelto): la frase sin foto alarga la anterior y, con la regla prendida, pasarse de 6 s por eso
  es un aviso y no un error. Historia corta: cortes de **2,5-4 s** (antes 1,5-2,5) y ninguna foto
  más de 2 veces (`plan_rapido(max_apariciones)`; seguir la misma foto con otro movimiento es la
  misma aparición). 894 tests OK.
- v0.84.0 (2026-11-10) — **Edición nueva, programada y APAGADA** (propuesta aprobada por Santi;
  los ejemplos se arman en la Pi con los interruptores prendidos solo en memoria, sin tocar los
  timers). (1) **Imagen = lo que se dice** (`efemerides.imagen_frase`, efeméride de YouTube y su
  Reel + historia de Facebook): el guion trae `objeto` por frase (la cosa genérica, sin año); por
  frase se buscan hasta 2 fotos del hecho o el lugar (Commons y las otras fuentes de archivo), 1 del
  objeto en Commons y 1 del objeto en Pexels (`FOTOS_*_FRASE`, pool hasta 52); Gemini ve de dónde
  sale cada una y el orden de preferencia (`ORDEN_FOTOS`) y dice por foto `anacronismo`: una de
  Pexels en una frase del pasado sale salvo que confirme false. La tarjeta, como antes, al final.
  En este modo no corre la regla (j) (stock primero desde 2000): Pexels va último. (2) **Historia
  de Facebook corta** (`historias_fb.formato_corto`): `locales.SISTEMA_GUION_CORTO` (50-70
  palabras, el GANCHO primero sin fecha, "En <año>, en <lugar>," en la segunda: `validar_guion(corto)`
  y `validar_lugar(corto)`), voz hasta 30 s (`CORTO_MAX_S`), `plan_rapido` (cortes de 1,5-2,5 s que
  alternan entre las fotos de ESA frase y, si hay una sola, la misma con otro movimiento), efecto
  "mov" (`filtro_movimiento`: acercarse/alejarse/paneo sobre el cuadro armado al doble), karaoke
  dorado y sin el año grande al principio; whoosh solo al cambiar de frase. La efeméride de YouTube
  mantiene largo, arranque y formato. (3) **Rots** (`render.edicion_rots`, `edicion.py`): sin el
  principio y el final muertos ni pausas de más de 0,6 s (salvo ruido fuerte: risa o grito), 15-35
  s (si sobra, el bloque con el pico de volumen), cortado ANTES del layout y con los tiempos de las
  palabras mapeados (no se vuelve a transcribir); zoom también en las risas (`zooms.planear(extra)`);
  en la misma llamada de textos `frase_inicio` (≤ 6 palabras, los primeros 2 s en lugar del título)
  y `pregunta` (≤ 12, 2 s finales con el último cuadro congelado, `render(congelar_s)`, y arriba de
  la descripción); karaoke amarillo (`subtitles.escribir_ass_karaoke`); un momento que otro canal
  ya subió pasa a ×0,5 en la selección (`pego.peso_copiado`, con los Shorts que ya encuentra "pegó":
  sin búsquedas nuevas). `tests/test_edicion_nueva.py`. 887 tests OK.
- v0.83.0 (2026-11-10) — (1) Prueba manual vs API cancelada (`prueba_manual_desde: ""`).
  (2) **Rots se sube solo** (`publicacion.subir_solo`): la entrega diaria, antes de mandarse, se
  programa en su horario. (3) La efeméride en Facebook a las 12:00 (`facebook.hora_efemeride`) y
  registrada con `reel: efemeride` junto a las historias (`reel: historia`) para el 24/11.
  `tests/test_subida_diaria.py`. 870 tests OK.
- v0.82.0 (2026-11-10) — **Hashtags, tags y categoría de Rots como los subidos a mano** (§1): la
  descripción termina con `#Shorts #<streamer> #<plataforma> [#tema]` antes del crédito, sin tags,
  categoría 22 (era 20). El clip de la prueba manual lleva la misma descripción. CLI `hashtags-rots`
  para los ya subidos. `tests/test_hashtags_youtube.py`. 865 tests OK. Al corregir los ya subidos, un clip de Kick con "twitch.tv/<login>" en el crédito (los procesados antes del 29/10) pasa a kick.com.
- v0.81.0 (2026-11-10) — **Prueba manual vs API en Rots** (§1, `prueba_manual.py`): del 11 al 17/11,
  1 clip por día de la entrega diaria va "📱 SUBILO VOS" (sin 📤, la descripción con los hashtags
  en un bloque), rotando la posición; el 18/11 el informe del % del feed de Shorts, a mano contra
  API. `tests/test_prueba_manual.py`. 855 tests OK.
- docs (2026-11-10) — Content ID en Rots (Santi, Studio): 3 reclamos, los 3 de Auronplay sobre sus
  directos, públicos y sin efecto en la visibilidad; Auron se sigue subiendo, marcado como
  "reclama" en los análisis y con menos prioridad para monetizar (§1).
- v0.79.2 (2026-11-09) — Sor Juana no entraba el 12/11 (el nacimiento enlaza "Juana Inés de la
  Cruz" y el Día Nacional del Libro, "Sor Juana Inés de la Cruz"): `locales.homenajeado` compara
  sin "Sor/San/…", tildes ni paréntesis. Un hecho se puede fijar por día
  (`historias_fb_hecho:<día>`): el 12/11 queda fijado a Sor Juana (Newbery no va, pedido de Santi).
  835 tests OK.
- v0.79.1 (2026-11-09) — Con un hecho elegido a mano, Haiku clasifica el día entero y no lo puede
  descartar (la primera prueba de Epecuén falló así). **Prueba real en la Pi:** "Villa Epecuén: el
  pueblo que tapó el lago", 10 frases, 99 palabras, el lugar en título, primera frase y
  #VillaEpecuen, 8 fotos (bañistas de 1938, costanera de 1980, ruinas de 2009, Pablo Novak) y 4
  tarjetas donde no había foto de época. 833 tests OK.
- v0.79.0 (2026-11-09) — **Pequeña Historia para Facebook** (§3d): `locales.py`, `claude.py`,
  `/historia`, CLI `historia-fb`, `_fb_tick` a las 06:30 en la escucha, voz por la segunda clave
  (`voz_efemeride(segunda_primero=True)`), subida solo a Facebook a las 19:00 y registro del tipo
  de historia. `anthropic>=2.7` en requirements; `ANTHROPIC_API_KEY` copiada al .env de clips en la
  Pi (la misma de ~/bot-videos; no está en la compu). Los tests no hablan con Claude
  (`conftest._sin_claude`). **Token de Facebook canjeado:** el de usuario con `read_insights`
  estaba pegado en FACEBOOK_PAGE_TOKEN (no había FB_USER_TOKEN); se canjeó ahí mismo por uno de
  PÁGINA que no vence (huella ab2e94551f81, compu y Pi). **Conteo de un mes (10/11 → 09/12, Haiku):**
  4,3 historias buenas por día, 1,1 fuertes (interés ≥ 7), 0,6 con conmemoración; días sin ninguna
  buena: 21/11 y 29/11; sin ninguna fuerte: 10 de 30.
- v0.78.0 (2026-11-09) — **Relleno de fotos sin la foto de otra frase** (regla de Santi, a partir
  de los billetes de rupias de Android): en `ilustrar.asignar`, `completar_distintas` y `tramos`,
  una frase sin foto propia solo usa las `generales` (las del artículo del hecho) o alarga la de la
  frase anterior; las frases con fotos propias siguen igual. En efemérides, si con eso un tramo
  pasa de 6 s, la frase vacía va con la tarjeta. `tests/test_relleno_fotos.py` con el caso de los
  billetes. Nacozari anotado en §1 como caso de referencia de Facebook (orgánico).
- docs (2026-11-09) — §10 reescrito con el estado real de la Pi, lo que espera respuesta de Santi
  (diseño del algoritmo, foto del HTC Dream, análisis del Reel de Facebook, voces) y los problemas
  vistos sin arreglar (403 de miniaturas en Pequeña Historia, el relleno de fotos de la regla k).
- v0.77.0 (2026-11-06) — **Dos fallas del 5/11.** (1) **/ya no andaba nunca**: armaba los args con
  `max_procesar=None` y `_diario` comparaba `procesados >= None` apenas había un candidato
  (TypeError; falló igual el 30/10 dos veces y el 5/11 a las 07:03). No tenía que ver con las
  estadísticas ni la retención. Ahora `MAX_PROCESAR` (6) es el tope por defecto en `_diario`, en /ya
  y en el CLI. `tests/test_ya_tope.py`. (2) **El video de Pequeña Historia de Android llegó sin
  botones**: Telegram rechazó el mensaje de los textos ("message is too long", más de 4096
  caracteres) porque el autor de una foto de Commons (la consola OUYA) traía el CSS de Wikipedia
  (`.mw-parser-output .hlist …`) y la descripción se infló. Arreglos: `efemerides.sin_html` saca los
  bloques `<style>`/`<script>` enteros; `telegram.mandar_con_botones` parte un mensaje largo
  (`partir_html`, cerrando y reabriendo `<pre>`/`<b>`/`<i>`/`<code>`), pone los botones en el último
  pedazo y VERIFICA que hayan quedado (`reply_markup` de la respuesta): si no, `editMessageReplyMarkup`;
  si tampoco, un mensaje corto solo con los botones. `send_message` devuelve el mensaje.
  `tests/test_botones_siempre.py`. La foto de "inversores" de ese video (billetes de rupias de
  Pexels): Gemini no encontró ninguna foto para esa frase y el relleno repitió la que había elegido
  para "10.000 dólares en efectivo" (marcada "NO es de la época"); se reemplazó a mano por una de
  Commons y el video se reenvió.
- docs (2026-11-01) — **Portadas e ilustraciones con IA para Pequeña Historia: EN PAUSA** (Santi). El
  diseño (portada cinematográfica con título serif dorado, hasta 2 ilustraciones "Recreación" por
  video, `containsSyntheticMedia` en YouTube, costo ~US$4–7/mes con Flash) quedó en
  `docs/portadas-ia.md` para retomarlo. Nada programado ni pago activado; siguen vigentes "Sin IA
  generativa" (§1) y "nada de IA, dibujos ni recreaciones" en Pequeña Historia.
- v0.76.0 (2026-11-01) — **/buscar "viejos" = lo que más pegó en otros canales, cortado del stream**
  (pedido de Santi; antes eran los clips más vistos de hace más de 30 días). `_buscar_viejos`: por
  streamer, search.list por vistas de los Shorts de OTROS canales publicados entre `pego.viejos_dias`
  (60) y `pego.dias` (7) días atrás (`pego.candidatos_viejos`), sin los que no pegaron, los compilados,
  los que nombran a otros, los de canales propios, los que ya busqué en el VOD o ya subí
  (`pego.ya_subido`) y los publicados antes del VOD más viejo que todavía existe. **Medido en la Pi:**
  Kick devuelve los VODs del último mes (Davo, Spreen, Coscu y La Cobra: el más viejo del 3-4/10);
  Twitch daba 20 (Auron hasta el 23/09) y ahora pide 100. Para cada Short, de más visto a menos, el
  embudo de "pegó" (`pego.vod_de_un_short`, sacado de `buscar_en_vod_del_dia`, que ahora lo usa
  también): si aparece, corta el tramo, lo procesa con todos los filtros y lo manda como cualquier
  clip; si ese momento del stream ya salió por otro Short (±60 s, `ya_subido_cerca`), no lo repite.
  Tope `pego.viejos_tope_min` (30); el resumen dice qué pasó con cada Short. Sin `YOUTUBE_API_KEY`
  no anda (la búsqueda con yt-dlp solo da "esta semana"). Botón: "Viejos (lo que pegó, 1-2 meses)".
  `tests/test_viejos_pego.py`.
  **Probado en la Pi con datos reales (solo la búsqueda):** Davo → YouTube 46 Shorts, 25 no pegaron / no
  lo nombran, 5 de antes del VOD más viejo (04/10), 3 ya buscados, 6 compilados, 6 nombran a otros
  (Edul, La Cobra) → quedaba 1, subido por el canal de Gastón Edul: ahora también se saltea un Short
  subido por el canal de otra persona conocida ("es del canal de …"). Auron (Twitch, VODs desde el
  02/09) → 16 candidatos; entre ellos una película india ("Auron Mein Kahan Dum Tha"): el nombre
  coincide, el embudo no la va a encontrar pero gasta 2-4 min.
- v0.75.0 (2026-11-01) — **Clips aburridos** (pedido de Santi). (1) En la llamada de textos, campo nuevo
  `momento` (el remate, la reacción fuerte o lo que pasa, en una frase; vacío si no hay) y el prompt del
  puntaje exige un momento concreto: sin él, 5 como mucho (lo hace cumplir el código:
  `textos.puntaje_con_momento`, menos de 3 palabras = no hay). (2) `textos.puntaje_min` 6 → 7. **La
  semana anterior (21 clips con puntaje, Pi):** corte 6 → 15 pasan, corte 7 → 12 (1,7 por día; el resto
  del cupo de 3 sale con relleno); de los 18 entregados, 11 llegan a 7. El efecto del `momento` no se
  puede medir hacia atrás sin volver a gastar Gemini. Dato: el puntaje viejo casi no separaba los votos
  (puntaje 8: 10 👍 y 7 👎; puntaje 6: 7 👍 y 6 👎). (3) Ejemplos del puntaje: además de los votos 👍/👎,
  los Shorts del canal con más vistas y con más % visto entero (`textos.mejores_del_canal`, tabla
  `metricas`; hoy 41 medidos). (4) `seleccion.peso_momento` 0,5 → 1,0: 3 personas que clipearon el
  mismo momento → ×3 (antes ×2). `tests/test_momento.py`.
- v0.74.0 (2026-11-01) — **Brunenger seguía saliendo en los diarios** (Santi: "no puedo sacarlo"). En la
  Pi estaba bien movido a la carpeta "Extra" (sin diarios) desde el 29/10 14:49, y desde ahí la corrida ya
  no buscaba clips nuevos suyos; pero los que ya estaban PROCESADOS de antes quedaban en la pila de
  `output/ready/` y la selección elegía de ahí sin mirar la carpeta: salió uno el 30/10, otro el 31/10 y
  otro el 1/11 (procesados el 25-29/10). Ahora `ejecutar_seleccion` saca de la pila a los streamers que
  hoy no están en los diarios (`_fuera_de_diarios`; los que no son streamers no se tocan). Y en
  /streamers, por streamer, **"📅 En diarios: sí/no"** (`st:dd`), que le gana a la carpeta
  (`registro.en_diarios`, `bot_estado.diarios_streamer`); el modo en vivo sigue mirando la carpeta.
  `tests/test_diarios_streamer.py`.
- v0.73.0 (2026-11-01) — **🔥 SUBIR YA se publica ya** (pedido de Santi). Un clip que salió de una alerta
  del modo en vivo (`db.es_de_envivo`: `envivo_alertas` entregada con ese clip) se sube con 📤 PÚBLICO al
  instante (`youtube.subir(publico=True)`, `_subir_publico_ya`), sin programarlo para el próximo horario;
  queda `publicada` en `subidas` y el botón dice "✅ Publicado". Con partido en pantalla sigue yendo
  privado sin fecha. `Cliente.publicar_ya` (videos.update a público) para pasar uno ya programado.
  `tests/test_envivo_publico.py`.
- v0.72.0 (2026-11-01) — **Prueba de voz menos IA en Pequeña Historia** (Santi: "todavía suena a IA"),
  todo APAGADO hasta que elija: (1) `efemerides.guion_hablado`: `SISTEMA_GUION_HABLADO`, escrito para
  ser dicho (frases de largo variado, 1-2 muletillas, puntos suspensivos, números redondeados como se
  dicen). La validación de "nada que no esté en el artículo" acepta redondeos SOLO con la palabra que
  los marca y según cuál es (`redondeo_valido`): "casi X" = el real un poco abajo (85-100 %), "más de X"
  = arriba hasta ×1,5, "menos de" = 67-100 %, "unos/cerca de" = ±15 %, contra los números del artículo
  (coma decimal incluida: 3,10 m) o los años desde el hecho. Vale también con el prompt de siempre
  (sin "casi/más de" el número tiene que estar tal cual, como antes). Encontrado en la prueba: la
  validación vieja tiraba "más de tres metros" (3,10 m) y "más de mil kilos" (1.356 kg) del Gigante de
  Cardiff; y "quinientos" no se reconocía como número. (2) `efemerides.voz_natural`: pausas entre
  frases a un largo al azar según cómo termina (punto 0,30-0,60 s, ?/! 0,40-0,70, … 0,55-0,85; solo
  alarga, siempre igual para el mismo guion, sin pasarse del tope) y EQ suave de locutor
  (`EQ_LOCUTOR`: filtros y compresor, sin tocar tono ni velocidad); los subtítulos y los cortes de
  foto se corren con las pausas. Muestras A (guion de siempre), B (guion hablado) y B+ (B con pausas y
  EQ) del Gigante de Cardiff mandadas a Santi por Telegram. ElevenLabs (C): falta la clave. También:
  el test de la corrida diaria fallaba en la Pi porque el timer aparte de la efeméride YA está
  instalado (Santi corrió `instalar.sh`); ahora prueba los dos casos. 789 tests OK.
- v0.71.1 (2026-10-30) — **Primera subida real con 📤** (Santi, 09:29 AR): `clip_01M5ZV59PA5XWE4NS6HTHM4V1F`
  → `5WJiIU4kDgI` en Rots, privado con `publishAt` 13:00 AR, procesado y sin restricciones (la Pi le
  avisa a Santi a las 13:05 si pasó a público). La pista del embudo de "pegó" baja video + audio (el
  formato 18 ya no venía y la imagen nunca se puntuaba; ver v0.69.0). 781 tests OK.
- v0.71.0 (2026-10-30) — **Subida a YouTube prendida, tests aislados y tope de tiempo** (pedido de
  Santi). (1) `youtube_upload_enabled: true` (la prueba pública de v0.70.0: público, procesado y sin
  restricciones a los 0, 10 y 60 min). Al prenderla, la suite se colgó en el 27 %. (2) `conftest.py`:
  en TODOS los tests, `requests.Session.request` corta googleapis.com, youtube.com,
  accounts.google.com y facebook.com (`SalidaProhibida`, al instante), `youtube.ruta_token` apunta a
  una carpeta vacía y las credenciales de Facebook vienen vacías; con `CLIPS_REGISTRO_SALIDAS` se
  anota qué test lo intentó. Auditoría (una corrida con los tokens reales al alcance, la subida
  prendida y la red cortada): **0 intentos**; y nada nuevo en los canales (Rots: lo último es la
  prueba; Pequeña Historia: 5/10) ni en la página de Facebook (las efemérides diarias del 23 al
  28/10). La suite pasó de 3,5-6 min a ~100 s. El cuelgue del 27 % no se reprodujo. (3) `red.py`:
  `SesionConTope`, tope TOTAL por pedido (120 s; 900 s el video) además del timeout de requests, que
  es entre bytes; la usan `youtube.Cliente`, el OAuth y la búsqueda de "pegó". Un tope vencido es
  `TiempoAgotado` (un `requests.Timeout`) y donde se atrapaba `YouTubeError` ahora también los
  errores de red. `tests/test_red_tope.py`. 780 tests OK.
- v0.70.1 (2026-10-29) — **Pequeña Historia conectada a YouTube** (`youtube-auth pequena_historia`,
  aceptado por Santi): canal «PequeÑahistoria» `UC-L0R7qXCpzHy14r_DFOleA`. Token en
  `config/youtube_token_pequena_historia.json` de la compu y de la Pi (chmod 600, fuera de git,
  huellas iguales); verificado desde la Pi con `mi_canal()`. La subida sigue gobernada por
  `youtube_upload_enabled`.
- v0.70.0 (2026-10-29) — **Partido en pantalla como experimento** (pedido de Santi; §3 paso 4): ya no
  se descarta, avisa en el mensaje (`process.AVISO_PARTIDO`), con la subida prendida va PRIVADO y SIN
  fecha (`youtube.metadatos(publicar=None)`, `_subir_privado_a_revisar`, estado `privada` en
  `subidas`) con el link a Studio para revisar las Verificaciones, y un /reclamo sobre uno vuelve a
  descartar todos (`registro.excluir_partidos`) sin excluir al streamer. **Crédito de Kick:** los
  clips de Kick salían con "twitch.tv/davooxeneize" y Gemini escribía "reacciona en Twitch" (visto en
  el video de la prueba de subida pública): `textos.credito` y el prompt usan la plataforma real.
  `tests/test_partido_experimento.py`. **Prueba de subida pública** (el mail de cierre de la
  auditoría: "los videos subidos por la API no quedan privados automáticamente"):
  `clip_01M5ZYC0HH21XTPYWQ1RN3BSS3` ("Davo se cansó de escuchar a Gastón 😂", textos corregidos a
  Kick) subido PÚBLICO a Rots por `videos.insert` el 30/10 00:48 UTC → `y5TBZ5OwxoI`, respuesta
  completa en `data/prueba_publica_y5TBZ5OwxoI.json` y en `subidas`; chequeos a los 10 y 60 min en
  `data/prueba_{10,60}min.json`.
- v0.69.0 (2026-10-29) — **"Pegó": el original se busca en el VOD con un embudo** (`vod_embudo.py`,
  diseño aprobado por Santi). Medido antes: de 18 Shorts de Davo buscados en el VOD entero aparecieron
  3, cada VOD nuevo costaba 10-40 min de audio en la Pi y 2 búsquedas se cortaron por tiempo. Los 3
  originales se publicaron 8, 10 y 17 min después del momento, con el stream en vivo; los clips de
  la comunidad de Kick no traen posición (`vod_starts_at` = 0) y los más cercanos estaban a 10,6 y
  24 min. Embudo: VODs de 7 días antes (`pego.vod_dias_antes`), puntaje por en vivo a la hora de
  publicado + texto + imagen (UNA llamada a Gemini: 3 cuadros del Short contra miniatura y 2 cuadros
  de cada VOD), los 2 mejores; hasta 3 ventanas (la hora: 45 min antes de publicado; clips con título
  parecido a lo que se dice en el Short, Whisper; pico de chat en Twitch) ±10 min; audio SOLO de las
  ventanas; el VOD entero solo si sobra tiempo del tope (`pego.vod_respaldo`). Antes de buscar, los
  compilados (título que empieza con TOP, mejores momentos) y los que nombran a otros
  (`pego.otros_nombres` + los otros streamers cargados; los hashtags no cuentan) no se buscan y salen
  en el resumen con el motivo. **Medición en la Pi (6 Shorts reales de Davo, sin el respaldo):** los
  3 con original conocido → 3/3 encontrados en el minuto correcto (76,8 / 105,2 / 107,0; 0,97-0,99),
  los 3 por la ventana de la hora, en 226, 264 y 115 s (pista 2-4 s, Whisper 34-63 s, listar VODs y
  clips 25-27 s, ventana de audio 37-201 s); el sistema anterior tardó 70 min (QfN, 4 VODs enteros)
  y 29 min (R4Wx) según los logs (el de 3LhkA ya rotó). Los otros 3 (PZ4rdImHudw, pBQojLfdMsk,
  q5UJArZYOs8) → 0/3 en 76-111 s: ninguno se publicó con Davo en vivo, ningún clip de la comunidad
  se parecía y Kick no tiene chat grabado, así que no hubo ventanas; el sistema anterior, con los
  VODs enteros de 3 días, tampoco los había encontrado. Encontrado al medir: YouTube ya no da el
  formato 18 y la pista bajaba solo el audio (sin cuadros, la imagen nunca se puntuó); ahora video
  ≤ 480p + audio unidos (`bv*[height<=480]+ba`): probado con R4Wx, Gemini dio 10/10 al VOD correcto
  y 5/10 al otro.
- v0.68.1 (2026-10-29) — **Telegram: los cortes de conexión se reintentan solos** (pedido de Santi).
  `TelegramClient._llamar` (todo lo que manda el bot) y la bajada de `get_file`: ante
  `ConnectionError` (RemoteDisconnected, "Connection aborted") o timeout, 2 reintentos esperando 3 y
  6 s (`ESPERAS_REINTENTO_S`), con el archivo rebobinado para que se mande entero; recién si fallan
  los 3 intentos es `TelegramError` (y ahí avisa lo de siempre). Un error que CONTESTA Telegram (400,
  403…) no se reintenta. `alerta.sh`: `curl --retry 2 --retry-delay 5 --retry-connrefused`. OJO: si
  el corte fue DESPUÉS de que Telegram recibió el mensaje, el reintento lo puede mandar dos veces.
  `tests/test_telegram_reintentos.py`. 762 tests OK.
- v0.68.0 (2026-10-29) — **La corrida del 29/10 murió por timeout buscando fotos de la efeméride.**
  Del log: clips de 05:02 a 05:45 (3 procesados, 856/586/1106 s; 2 con re-render por cara al
  borde), entrega 05:45 (**2 de 3**: dos de los 3 procesados eran de Brunenger y el tope es 1 por
  streamer; el 28/10 salió 1 por lo mismo), efeméride de 05:45 hasta que systemd la mató a las
  06:30 (TimeoutStartSec 90 min): 3 hechos, y en cada frase Openverse colgado (timeout de 30 s) y
  Smithsonian con 429 (la DEMO_KEY compartida; pasaba desde el 25/10). Arreglos: (1) **la
  efeméride con su propio servicio y timer** (`clips-bot-efemeride.service/.timer`, 06:00 AR,
  TimeoutStartSec 75 min, `python -m clips_bot efemeride-diaria`, log `efemeride.log`): espera el
  turno pesado hasta 30 min y, si los clips siguen, la deja para los reintentos de la escucha
  (07:00/10:00) sin pisarlos. `diario` la deja de hacer apenas existe
  `/etc/systemd/system/clips-bot-efemeride.timer`; hasta que Santi corra `sudo bash
  ~/clips/deploy/instalar.sh`, sigue al final de `diario` (después de la entrega, como antes).
  `correr.sh` recibe el comando (`diario` reintenta una vez; la efeméride no). (2) **Topes de
  fotos** (`fuentes_fotos.Corrida`): 10 s por pedido; una fuente que falla 2 veces se saltea el
  resto de la propuesta (los 3 hechos); búsqueda de fotos y videos de cada hecho con tope de
  `efemerides.tope_fotos_min` (10): vencido, sigue con lo que bajó. (3) **Smithsonian solo con
  clave propia** (`SMITHSONIAN_API_KEY`, gratis en https://api.data.gov/signup/): sin clave se
  saltea. (4) Preset: se queda `medium` — la parte de clips de los últimos 8 días fue de 21 a 47
  min (2-4 clips, 234-1106 s cada uno), y sin la efeméride adentro le sobran ≥ 43 de los 90 min.
  Lo que más pesa son los re-renders (un clip con re-render tarda el doble). 758 tests OK.
- v0.67.1 (2026-10-25) — **Título quemado sin cuadraditos.** En el clip de Auron
  «¡Que todo el mundo vea la selfie que me enviaste!» 📸 el 📸 salía como un cuadradito vacío: Arial
  no tiene emojis. `subtitles.titulo_quemable` (lo usa `escribir_titulo_ass`, también para el nombre
  del streamer) saca emojis y pictogramas, banderas, tonos de piel, selectores de variación (U+FE0F),
  ZWJ y keycaps, y las comillas que envuelven el título ENTERO: las «» venían del título de Gemini
  (una cita), no las agregaba el ASS; las comillas internas se quedan. El título del json (YouTube y
  Telegram) no cambia. `tests/test_titulo_quemado.py`. 750 tests OK en la Pi (en un worktree de
  Windows sin `.env` fallan 2 de `test_pego_0200` y
  `test_multipov_evento::test_el_angulo_vacio_se_rescata_con_fit_blur`, igual que antes del cambio).
- v0.67.0 (2026-10-25) — **El clip de Auron mal cortado** ("Auron expone la foto tras ser
  traicionado"): arriba la cara de un chico de una foto en pantalla, subtítulos dobles y la pantalla
  cortada a la izquierda. Causa de la cámara, medida: Haar veía la cara de Auron a pantalla completa
  (primera escena, 12 % del ancho) y la del chico de la foto (segunda escena, 2,7 %) en el mismo
  lugar, y contaban como UNA cara estable al 90 %; la webcam real (arriba a la derecha) Haar la vio
  en 2 de 20 cuadros. Arreglos: (1) misma cara = mismo lugar Y tamaño parecido; split solo si la
  cara está en ≥ 80 % del clip; recuadro de bordes fijos (`recuadro_fijo`); `facecam` por streamer
  (lista en orden de prioridad, streamers.yaml + /streamers → 📷 Webcam, con un cuadro de su último
  clip con los recuadros dibujados). Auron: dos, medidas con los bordes fijos de 12 clips — juegos
  [0,006 0,378 0,180 0,300] (Minecraft y Among Us) y Just Chatting [0,806 0,022 0,172 0,265]. En los
  Minecraft arriba a la derecha está la webcam de la INVITADA con cara en 90 %: por eso gana el
  orden y no la presencia (probado: con "la de más presencia" elegía a la invitada). Haar dentro del
  recuadro agrandado, con perfil: la cara de Auron pasó de 0-70 % a 95-100 % de los cuadros.
  (2) Subtítulos: los 12 últimos clips de Auron traen karaoke quemado → `subtitulos_propios: true`;
  y para todos, OCR en la franja de abajo (12 de Auron: 11 dan 3-8 de 8 cuadros, uno de Among Us
  da 1; 8 de otros streamers sin subtítulos: 0 de 8 los ocho; corte 2). (3) Split: abajo el cuadro
  entero. (4) Chequeo visual con Gemini (`revision.py`). Los 12 de Auron con la decisión nueva: 5
  Minecraft → split con SU webcam (antes 3 fit_blur, 2 split), el menú con webcam grande → split
  por el marco fijo, el roto y 3 a pantalla completa sin webcam fija → fit_blur, 2 a pantalla
  completa siguen en split como antes. 748 tests OK.
- v0.66.0 (2026-10-21) — **Fotos de Pequeña Historia, reglas nuevas** (la de bitcoin del 21/10
  traía una app con error, una planilla de frase semilla, un gráfico en picada cuando el guion dice
  que subió y una captura con texto en otro alfabeto). Ver §1 (f)-(k). Calibrado del OCR sobre las 40
  fotos del pool de bitcoin (fracción de la imagen con cajas de palabras de tesseract, eng, psm 11,
  conf ≥ 60): la app 8,5 %, documentos 12,9-15,2 %, placas en filipino 8,3-11,4 %, diagrama 8,4 %;
  la foto real con más texto (un congreso con carteles) 6,0 % → corte 7 %. La planilla (2 %) y los
  gráficos (2-5 %) no los ve el OCR: los agarra el `tipo` de Gemini. `GeminiClient.json(modelo=)`
  pide SOLO ese modelo (la caché va por modelo). `Fuentes.stock` (Pexels → Unsplash);
  `PEXELS_API_KEY` cargada por Santi y copiada a la Pi (huellas comparadas). Encontrado en la
  primera prueba: el principal sin cuota hacía que el cliente no insistiera 15 min y frenaba también
  al de respaldo; un pedido de UN modelo puntual ya no prende esa pausa. 733 tests OK.
- v0.65.0 (2026-10-20) — **Facebook: por qué el público no ve los Reels, y la portada.**
  (1) Por la API los 8 Reels están `published: true`, `ready`/`complete`, privacidad `EVERYONE`
  ("Público"), sin revisión ni restricción; la página está publicada (`is_published: true`), sin
  restricciones de país ni de edad. Lo que falla es la APP de Meta que publica ("clips-bot", la de
  FB_APP_ID): no tiene URL de política de privacidad ni categoría, requisitos para pasar a modo
  Live, así que está en MODO DESARROLLO, donde lo que publica solo lo ven quienes tienen un rol en la
  app (solo Santi, administrador). Eso explica "No reels yet" desde otra cuenta y el anuncio con 0
  alcance. El modo no se cambia por la API: Santi lo tiene que pasar a Live en el panel de la app.
  (2) **Portada con el año final** (la del Al Capone mostraba "1880" a mitad de la cuenta):
  `graficos.PORTADA_S` = 1,9 s (cuenta hasta 1,4 s, saltito hasta 1,66, fundido desde 2,15; sin
  gráficos, el cartel del año dura 2 s), `media.portada` (JPEG vertical 720x1280), y al subir una
  efeméride: Facebook `POST /{video}/thumbnails` con `is_preferred` y YouTube `thumbnails.set`
  (cuando se active la subida; si falla, la subida sigue). También la miniatura de Telegram de las
  efemérides. Aplicado a los 8 Reels ya publicados (success y verificado: la portada preferida y la
  `picture` del Reel del Al Capone muestran 1931). 723 tests OK.
- v0.64.0 (2026-10-20) — **Videos más livianos** (Santi: "tardan mucho en cargar en Telegram").
  Medido: 44 entregados en 10 días, mediana 9 MB, máx. 28 MB (antes hasta 37), video a 2,4 Mbps de
  mediana y picos de 5,2. Faststart ya estaba en todos (44/44) y `sendVideo` ya mandaba
  `supports_streaming=true`. Subida de la Pi: ~110 Mbps a Cloudflare; a Telegram ~5 MB/s (37 MB en
  8,0 s): el cuello es la descarga en el celular. Comparado con VMAF (modelo de celular) y SSIM
  contra una referencia crf 10, con el render real (fit_blur, zooms, subtítulos y título) de los 3
  clips más pesados: `medium` + crf 22 + tope 3500 kbps = −20 a −26 % de peso con −0,1/−0,6 de VMAF
  (crf 23-26 con veryfast: −35/−55 % pero −2,5 a −11 de VMAF; veryfast/faster/fast al tope 3500:
  −1,6 a −3). En la Pi el render tarda +63 % (58 s de clip: 359 → 585 s). Antes/después del mismo
  clip mandado al privado de Santi (37,0 → 26,9 MB). `tests/test_peso_videos.py` fija los ajustes,
  el faststart en todo render final y el streaming. 717 tests OK.
- v0.63.2 (2026-10-09) — Segundo screencast (oculto) con la búsqueda pública: https://youtu.be/g78FhNRCGuw
  (/lang en + /publicos davooxeneize). Su captura completa el paso 6 del PDF; los dos links van en el
  encabezado del PDF y en el mail. PDF final: 7 páginas, 8 capturas.
- v0.63.1 (2026-10-09) — PDF de la auditoría con las capturas sacadas del screencast
  (zlLOnuSHzQc, bajado en la Pi): /demo, Upload, Studio "Programado", /subidas, Cancel, Studio después
  de cancelar y /metricas refresh (`docs/auditoria-demo/capturas/`, las de Telegram recortadas al chat
  del bot para no mostrar otros chats). **La grabación NO tiene /publicos** (termina en `/buscar
  davooxeneize` con el menú "¿de cuándo?"): el paso 6 del PDF queda esperando una captura de Santi; el
  mail ya no dice que el video muestra la búsqueda pública.
- v0.63.0 (2026-10-09) — **Las respuestas de YouTube se guardan.** Los dos videos de /demo
  (`bocYs7_5N3I` 22:33 y `4JaPlvbWgZ0` 23:00 del 08/10) no están en Studio. Investigado: subieron
  al canal correcto (el token de la Pi es Roty, `UCz0-X39ylB_BAO_yFCLMS8w`); YouTube los aceptó al
  subir (el bot solo guarda el id si no hubo error); ❌ es `videos.update` (en el código no existe
  ningún `videos.delete`) y solo se usó en el segundo, pero desaparecieron los dos; hoy `videos.list`
  con el token del dueño devuelve 0 resultados (un rechazo se seguiría viendo con su motivo) → los
  sacaron DESPUÉS de subirlos, YouTube o desde la cuenta, no el bot. El motivo no se puede saber: no
  se había guardado la respuesta de la API. Ahora: (1) `Cliente.subir` guarda la respuesta COMPLETA de
  `videos.insert` (`subidas.respuesta` + log); (2) ❌ (`_cancelar_youtube`) guarda la de
  `videos.update` aunque falle (`subidas.respuesta_cancelar`); (3) la escucha, 2 minutos después de
  cada subida a YouTube de las últimas 24 h, pide `videos.list` (status, processingDetails) y guarda
  existe/uploadStatus/failureReason/rejectionReason/privacy/publishAt (`subidas.chequeo`); si no
  existe o quedó rechazado/fallido, avisa a Santi. En el mail y el PDF ya no se dice que el video de
  prueba "sigue privado": se describe lo que muestra la grabación (subido, programado, cancelado).
  714 tests OK.
- v0.62.2 (2026-10-08) — **Demo grabada y vuelta a la normalidad.** Screencast (oculto):
  https://youtu.be/zlLOnuSHzQc, ya en el borrador del mail y en el PDF. Bot en castellano
  (`idioma` = es), `youtube_upload_enabled: false`, la excepción solo para `demo_*`. Revisión para el
  09/10: settings en la Pi OK (título 3 s, zooms ×1,35, videos en efemérides, Laomedeia, atempo
  ×1,1, Facebook prendido); zooms y picos aparecen en los clips reales (1-3 por clip); los Reels de
  Facebook del 05 y 06/10 salieron publicados (en la DB seguían "programada": marcados
  "publicada" a mano; el bot no pasa solo un Reel programado a publicado). La efeméride del 08/10 no
  salió (el TimeoutExpired, arreglado en v0.61.0); propuesta de prueba del 09/10 en la Pi, sin
  Telegram: OK (Google compra YouTube, 2006; la frase de acción sin video libre de época → foto).
  Los dos videos de prueba de /demo (`bocYs7_5N3I`, `4JaPlvbWgZ0`) no aparecen ni en
  `videos.list` ni en los uploads del canal: hay que mirarlos en Studio.
- v0.62.1 (2026-10-08) — **Un comando cortado por un reinicio se repetía solo.** La escucha guardaba
  el offset de Telegram DESPUÉS de atender los mensajes: al reiniciarla para frenar el `/buscar
  davooxeneize pego x1` colgado, lo volvió a leer y arrancó de nuevo (22:41:54). Ahora el offset se
  guarda apenas llegan los mensajes, antes de atenderlos: un comando cortado se pierde en vez de
  repetirse. El repetido se frenó salteando ese mensaje (offset +1) y reiniciando. 709 tests OK.
- v0.62.0 (2026-10-08) — **`/publicos <streamer>`** para la demo de la auditoría: `/buscar davooxeneize
  pego x1` se quedó muchos minutos mientras Santi grababa (compara el audio de cada Short contra hasta
  60 clips bajados de Kick); se frenó reiniciando la escucha (el turno pesado se soltó solo).
  `/publicos` hace SOLO `search.list` + `videos.list` (101 unidades de la API key), filtra los Shorts
  que lo nombran (sin mínimo de vistas, los más vistos primero, hasta 10) y contesta al toque con
  título, canal, vistas y link, en el idioma de `/lang`. No baja ni compara nada, ni toma el turno
  pesado. El PDF y el orden de grabación usan `/publicos` en el paso 6. 709 tests OK.
- v0.61.1 (2026-10-08) — **Excepción "Universal Newsreel"** en la lista negra (Santi: los
  noticieros de Universal de 1929–1967 están en dominio público vía el Archivo Nacional de EE.UU.).
  Por item (`es_universal_newsreel`): colección `universal_newsreels` de archive.org (o "Universal
  Newsreel" en título/descripción/temas) Y fecha entre 1929 y 1967 (sin fecha, no) → para ese item
  "Universal" no cuenta (sus metadatos dicen además publisher "Universal Studios"). En texto suelto,
  "Universal Newsreel" escrito así no cuenta como Universal. El resto de Universal y las otras marcas
  siguen bloqueados igual. Probado con los metadatos reales: "New Moon" (1957) y "Florida" (1960)
  vuelven a pasar. 708 tests OK.
- v0.61.0 (2026-10-08) — **Videos de archive.org en efemérides.** La de hoy (reintento de las
  07:00) cayó con `TimeoutExpired`: `sacar_frames` sobre
  `archive.org/download/disneys-animal-kingdom-full-opening-day-broadcast/…` (el `subprocess.run`
  con timeout no lo atrapaba nadie). Arreglos (`videos_libres.py`): (1) todo ffmpeg/ffprobe sobre un
  video remoto va por `_ejecutar` (tope + UN reintento: cuadros 60 s, tramo 180 s, probe 45 s); un
  video que no baja ni un cuadro se saltea entero, `bajar_tramo` baja a archivo local y si no llega
  da RuntimeError → esa frase vuelve a su foto; `buscar_videos` atrapa lo que quede. (2) archive.org:
  solo items cuyos METADATOS (`licenseurl` o `rights`, `licencia_archive`) dicen explícitamente
  dominio público, CC0 o CC BY (nada de NC/ND/SA); si no lo dicen, afuera. (3) Lista negra
  `MARCAS_PROHIBIDAS` (Disney, Pixar, Warner, Universal, Paramount, Fox, Sony, DreamWorks, Marvel,
  Nintendo) en TODAS las fuentes de video (título, autor, links; en archive.org también colección,
  temas, descripción, editor). **Revisión de lo que ya salió:** 6 videos en 4 efemérides; todos con
  licencia libre en sus metadatos, pero **dos son noticieros de Universal** (Universal Newsreel, que
  archive.org marca como dominio público): "New Moon. Reds Launch First Space Satellite, 1957/10/07"
  en la del 04/10 (Sputnik) y "Florida, 1960/10/06" en la del 05/10. El de Disney estaba marcado
  "Public Domain Mark" por quien lo subió: solo la lista negra lo frena. 706 tests OK.
- v0.60.0 (2026-10-08) — **Demo para la auditoría de YouTube** (YouTube pidió "an English
  screencast or step-by-step script… upload, schedule, manage, analytics, public searches"; plazo 7
  días hábiles). (1) `/lang en|es` (`idioma.py`, `L(es, en)`, en `bot_estado.idioma`, la escucha lo
  relee en cada vuelta): en inglés el mensaje del clip (Title/Description/…, recordatorio), los
  botones 📤/🚫/❌, las respuestas de la subida, `/subidas`, la cancelación, `/metricas`, la búsqueda
  🔥 y /demo. (2) `/demo`: un video de prueba propio (barras de color + cartel + tono; nada de
  terceros, `video_demo`) con el mensaje de siempre; «📤» lo sube a Rots con `videos.insert`,
  privado y con `publishAt` MAÑANA a 13:00 aunque `youtube_upload_enabled` esté apagado (solo los
  `demo_*`); queda en `subidas`, `/subidas` lo lista y ❌ usa `videos.update`. El clip demo queda
  `entregado` (nunca `procesado`: no entra a las 05:00) y `metricas.entregados` lo ignora.
  (3) `/metricas refresh`: pide las métricas en el momento (channels.list + playlistItems.list +
  Analytics reports.query). (4) `/buscar <x> pego x1` muestra los Shorts PÚBLICOS encontrados
  (`Recuento.publicos`, `pego.texto_publicos`: título, canal, vistas, link). (5) En
  `docs/auditoria-demo/`: el PDF "Clips Bot – API usage walkthrough" (6 pasos, un lugar por
  captura y el método de la API en cada uno; sale de `walkthrough.html` impreso con Edge), el
  borrador del mail en inglés (`respuesta-email.md`) y el orden de grabación (`orden-grabacion.md`).
  NO probado contra YouTube (la subida la hace Santi al grabar): tests con cliente falso. 701 tests OK.
- v0.59.0 (2026-10-04) — **Facebook prendido y la voz sin degradar.** (1) Facebook: con la app
  nueva de Santi, el token de usuario se canjeó por uno largo y de ahí salió el de la página
  "Pequeña historia" (tipo PAGE, no vence, pages_manage_posts + pages_read_engagement +
  pages_show_list). FACEBOOK_PAGE_ID y FACEBOOK_PAGE_TOKEN en el .env de la compu y de la Pi
  (huellas comparadas, sin mostrarlos); FB_USER_TOKEN borrado de los dos. Reel de prueba publicado
  desde la Pi (9 s, "ready/complete") y borrado. `facebook.activo: true`: el 📤 de la efeméride
  sube también a Facebook. (2) **La voz del 04/10 (Sputnik) sonaba horrible**: salió con Piper
  (Gemini TTS dio timeout) y medido paso a paso, `voz.wav` ya venía a 22 kHz y cortada a 9,8 kHz por
  el +1,5 semitonos (rubberband) sobre los 22 kHz de Piper; no hubo atempo. Arreglos: nada de
  cambiar el tono (`subir_tono`, `voz.semitonos` y `piper_semitonos` afuera; un test prohíbe
  rubberband/asetrate); la voz pasa a 48 kHz UNA vez con soxr (precisión 28) apenas se sintetiza
  (`narrar.a_48k`) y todos los pasos siguen a 48 kHz; duración: atempo hasta ×1,1
  (`tts_acelerar_max` 1,25 → 1,1, en `hacer_video`) y, si ni así entra, se ACORTA EL GUION
  (`acortar_guion`: Gemini, mismas frases, todo respaldado por el artículo) y se vuelve a
  sintetizar. (3) Un timeout suelto de Gemini TTS se reintenta una vez antes de caer en Piper. La del
  04/10 se rehízo con Laomedeia (34,8 s, sin atempo): voz a 48 kHz, el video final con contenido
  hasta 16,6 kHz (antes 9,8). 693 tests OK.
- v0.58.1 (2026-10-04) — Un /reclamo sobre un clip del 412 excluye SOLO el 412 (Santi: no a Davo
  ni a La Cobra); el streamer sigue en las corridas. Un reclamo común sigue excluyendo al streamer.
  685 tests OK.
- v0.58.0 (2026-10-04) — **Picos, 412, el stream y el gameplay** (pedidos de Santi).
  (1) Picos de volumen como DATO en la línea 📊 ("2 picos", `Resultado.picos_volumen`, de
  `zooms.picos` sobre todos los clips con audio): no tocan la selección (un test lo exige).
  (2) **El 412 como experimento**: `registro.PROGRAMAS_EXPERIMENTO = ("412",)`; al combinar, esa
  marca sale de `palabras_programa` y pasa a `Streamer.programa_aviso` → el clip ya no se descarta
  por `programa_terceros`, lleva "⚠️ 412 (stream del programa: revisalo con más cuidado)" en el
  mensaje (diario, catálogo, /buscar viejos, en vivo). "ANALIZAMOS" sigue descartando. El detector de
  partido en pantalla no cambia. Un /reclamo sobre un clip con ese aviso vuelve a excluir TODO el
  412 (`bot_estado.programas_excluidos`); desde v0.58.1, sin excluir al streamer.
  (3) **"Pegó" busca en el stream**: los `vod_por_dia` (2) Shorts sin original que más pegaron, en
  los VODs de Kick (como antes) y ahora también de Twitch (Helix /videos type=archive; audio con la
  variante "audio_only" de yt-dlp) de los 3 días antes de publicado. Si aparece, se corta el tramo
  (lo que dura el Short ± 1,5 s, tope 59 s; la variante más alta hasta 1080p, `vod.cortar`) y se
  procesa como clip NORMAL con todos los filtros (`Descarga.de_streamer`: no es un aporte), con el
  dato de "pegó"; queda `procesado` y compite en la entrega de las 05:00. Stream del 412: con el
  experimento se procesa con el aviso; si está re-excluido, no se procesa. En los dos casos el
  resumen dice "⚠️ Pegó, pero es del 412" (nunca en silencio). Columnas nuevas en `pegados`:
  `vod_programa`, `vod_clip_id`, `vod_resultado`. `vod_tope_min` 25 → 75. Probado en la Pi con VODs
  reales: Davo (Kick, 2 VODs de 6,3 y 8,3 h) y Auron (Twitch, 4,2 h): audio y corte de 20 s en
  1080p en 4-6 s.
  (4) **🎮 Versión con gameplay** (`gameplay.py`, opcional, nunca por defecto): botón debajo de los
  clips de charla (`camara.categorias_charla`) si hay videos en `gameplay/` (fuera de git; en la Pi,
  `~/clips/gameplay/`, vacía todavía). Arma OTRA versión: el clip arriba (1080x960, recortado hacia
  las caras; si no entran, el clip entero sobre su fondo difuminado) y un tramo al azar del gameplay
  abajo, sin audio del juego; subtítulos y título del original. Va por el turno pesado y la cola.
  683 tests OK.
- v0.57.0 (2026-10-04) — **Zoom de reacción y título corto** (Santi, después de las 2 muestras).
  (1) "Punch in" PRENDIDO por defecto (`render.zoom_picos: true`): en los picos de volumen la imagen
  salta a la cara en 0,1 s a ×1,35 (`zoom_max`; o lo máximo que deje entera la zona de todas las
  caras), se queda 0,8 s y vuelve en 0,3 s; máx. 3 por clip y 6 s entre uno y otro (antes: suave,
  ×1,12, 1 cada 20 s). Arranca 0,1 s antes del pico. (2) El título grande se ve solo los primeros
  `render.titulo_segundos` (3) y se va con un fundido de `titulo_fundido_s` (0,3 s, `ad` del ASS).
  670 tests OK.
- v0.56.0 (2026-10-04) — **Feedback de las muestras, por defecto** (Santi). (1) Pequeña Historia:
  `efemerides.videos: true` todos los días (aprobó la muestra del Apolo 11), con las mismas reglas:
  2-3 frases con video, revisado por Gemini, nada de IA, dibujos ni recreaciones. (2) Clips de Rots:
  formato por defecto = la muestra 3 (fit_blur: el video entero y atrás el mismo difuminado, con
  `render.titulo_arriba: true`); el recorte que sigue la cara (muestra 2, `camara.seguir_cara`) queda
  apagado. De la muestra 2 solo unos **zooms** (`zooms.py`, `render.zoom_picos`, APAGADO hasta que
  Santi apruebe 2 clips de prueba): en los picos de volumen (RMS ≥ 1,6× la mediana y el p90; un
  clip parejo no lleva), 1 cada 20 s y máx. 3, separados 8 s; subida 0,3 s, quieto 1 s, bajada
  0,6 s (coseno); hasta ×1,12 hacia las caras, bajado hasta que la zona de TODAS las caras (con el
  margen de `parallax.zona_caras`) entre; si no entra ni con ×1,06, sin zooms. Con zoompan sobre el
  frente agrandado al doble (a tamaño normal tiembla). Decidido por Claude: el split (facecam +
  juego) sigue para los juegos; los zooms solo en fit_blur. Probado en la compu: render 23 s para
  un clip de 24 s, la cara entera en el pico. 669 tests OK.
- v0.55.1 (2026-10-04) — Métricas: "database is locked" en la primera actualización real (la
  escritura quedaba abierta mientras se pedía a YouTube). Ahora se pide todo primero y se escribe
  junto al final; `db.connect` espera 30 s. En la Pi: 24 actualizados, 0 borrados, conclusiones
  guardadas. Política de privacidad reescrita: actualización antes de 30 días, borrado solo si el
  video no existe o se revoca, conclusiones guardadas siempre, y los datos públicos de Shorts de
  otros canales (pegó) borrados a los 30 días.
- v0.55.0 (2026-10-04) — **Regla de los 30 días de YouTube, actualizando y sin borrar** (Santi: "no
  quiero que se borren las métricas"). `metricas.actualizar` (05:00): pide la lista COMPLETA de
  videos del canal; borra los datos de un video SOLO si ya no está en el canal; vuelve a pedir las
  estadísticas de los Shorts nuevos, de los de los últimos 60 días (todos los días) y de TODOS los que
  no se actualizan hace `REFRESCO_DIAS` (25), con las vistas de toda la vida del video (antes: solo los
  últimos 60 días y con las vistas de esa ventana; los viejos no se actualizaban nunca). Si se revoca
  el acceso (Google contesta `invalid_grant`), `borrar_por_revocacion` borra las métricas y los ids de
  subida de ese canal. Lo que el bot concluye (mediana, n y log2 por streamer, duración, layout y
  cámara) se guarda SIEMPRE en `bot_estado.metricas_conclusiones` y los pesos salen de ahí si no hay
  métricas. Datos de Shorts de OTROS canales (los de "pegó": título, canal y vistas públicos) se
  borran a los 30 días (`pego.purgar_viejos`, en la vuelta de las 02:00). Comando nuevo
  **`/metricas [n]`**: vistas, % visto, % que llega al final y duración vista de los últimos Shorts
  medidos (de la DB, sin gastar cuota). 658 tests OK.
- v0.54.1 (2026-10-04) — **Búsqueda en el VOD prendida** (Santi): `pego.vod: true`, `vod_por_dia: 1`
  — solo el Short sin original que más pegó en las últimas 24 h, dentro de la vuelta de las 02:00,
  después de la búsqueda normal y con su propio tope (`vod_tope_min` 25). Solo Kick (el VOD de Twitch
  va por otro camino, no está). Si aparece, el resumen "🔥 Pegó en otros canales" lleva el link al
  VOD y el minuto. 653 tests OK.
- v0.54.0 (2026-10-04) — **Fotos quietas en Pequeña Historia** (pedido de Santi: "el movimiento sale
  de los cortes, los videos y los gráficos"). `efemerides.efecto_fotos: fija` (opciones fija | zoom |
  parallax): `parallax.cuadro_fijo` arma UN cuadro con el mismo encuadre (al menos 72 % del alto,
  caras enteras con margen) sobre el fondo borroso, y se repite lo que dura el tramo (`-tune
  stillimage`: más rápido que cualquiera de los dos efectos). El parallax y el zoom quedan en el
  código por si se vuelven a pedir. 651 tests OK.
- v0.53.0 (2026-10-02) — **Más fuentes de fotos** (`fuentes_fotos.py`). Por frase: Commons con la
  búsqueda tal cual y después cada vez más general (`videos_libres.consultas`), más
  `incategory:"PD-AR-Photo"` si el hecho es argentino (`es_argentino`); si Commons no junta 4, en
  orden: Openverse (CC0/CC BY/dominio público; incluye Flickr y museos) → Smithsonian Open Access
  (CC0; `SMITHSONIAN_API_KEY`, si no la DEMO_KEY pública) → Europeana (reutilización abierta;
  `EUROPEANA_API_KEY`, si no `api2demo`) → Flickr (`FLICKR_API_KEY`) → NASA (espacio) → Pexels y
  Unsplash solo para frases de hoy (`PEXELS_API_KEY`, `UNSPLASH_ACCESS_KEY`). Autor y licencia en
  los créditos ("Fotos:"), bajadas con tope de 15 MB y achicadas a 1280 (caché en
  `data/cache_wiki/otras/`). **Afuera, probado desde la compu y la Pi:** Library of Congress
  (verificación anti-bots de Cloudflare) y Gallica (403): no se esquivan. La Hemeroteca de la BNE no
  tiene API de imágenes: Caras y Caretas entra por lo que está en Commons. **Fotos chicas de la
  época:** una foto FECHADA hasta 10 años después del hecho pasa desde 500 px (`MIN_ANCHO_EPOCA`;
  antes 800 para todo): con Onzari (02/10/1924) Commons daba 2 fotos y ahora 6 de 1923-1926,
  incluidas "Gol olimpico 1924" y "Gol olímpico de Onzari". Medido sin Gemini en 4 búsquedas del
  gol olímpico: 2/2/0/0 candidatas antes, 6/5/5/5 de Commons ahora (+4 de Openverse donde faltaba).
  Si un hecho no junta 4 buenas entre todas, pasa al siguiente (como antes). 649 tests OK.
- v0.52.1 (2026-10-02) — **Caras siempre enteras** en Pequeña Historia. Antes de recortar o hacer
  zoom se detectan TODAS las caras de la foto (`parallax.caras`) y la zona con margen (0,9 caras
  arriba de la cabeza, 0,4 a los costados, 0,35 abajo; `zona_caras`) tiene que quedar a la vista
  incluso con el zoom del parallax (`encuadre`): si no entra con la foto al 72 % del alto, la foto se
  achica hasta que entre (antes una foto más chica que una cara cortada). El zoom se hace alrededor
  de las caras. Videos: el recorte se centra en las caras del cuadro elegido y, si no entran, el
  video va entero (`videos_libres.encuadre_video`, `filtro_video(cx, entero)`). Probado a ojo con un
  retrato (estatua de Champollion) y una foto grupal: ninguna cara cortada. 643 tests OK.
- v0.52.0 (2026-10-02) — **Imágenes de Pequeña Historia más estrictas** (regla fija 1, §1). (1)
  Relevancia dura: Gemini confirma `seguro` (requerido) de que la primera foto de cada frase muestra
  lo que dice la frase o el tema directo del hecho; si no, sale (en la de 4chan entró una página
  militar de Facebook). (2) Capturas de páginas web, redes o foros (`_CAPTURA`, por nombre y
  epígrafe) solo son candidatas de frases que hablan de una página (`_HABLA_DE_WEB`). (3) Cada
  frase busca otra cosa: dos `mostrar` iguales (sin el año ni el orden de las palabras) no pasan la
  validación del guion. (4) Ninguna imagen aparece más de `ilustrar.MAX_APARICIONES` (2) veces (en la
  del gol olímpico del 02/10 se repitieron 2 fotos en todo el video): `tramos` cambia a otra no
  gastada y, si no alcanza, `PocasFotos` → el hecho siguiente, como con menos de 4. 640 tests OK.
- v0.51.0 (2026-10-02) — **Cuota de Gemini.** (1) **Medición por función**: cada llamada anota en
  `gemini_uso` (día AR, función que llamó —sale sola del stack, ej. `textos.generar`,
  `efemerides.elegir_fotos`—, modelo, clave, tokens de entrada y salida, y si salió de la caché);
  `/gemini [días]` muestra llamadas y tokens por función y por día. Antes de esto, del log de la
  Pi: 1/10 = 23 llamadas de texto + 1 de voz (14 flash-lite, 7 flash con la principal, 1 con la
  segunda), 2/10 = 17 (7 lite, 6 flash principal, 4 flash segunda); sin desglose por función.
  (2) **Imágenes ≤ 384 px** en el cliente (`gemini.achicar`, vale para todo: clips, /narrar,
  /serie, efemérides); `frames_jpeg` 384 px; **3 frames por clip** (`frames_para_puntaje` 4 → 3).
  (3) **Caché de 7 días** de respuestas a pedidos IDÉNTICOS (`data/cache_gemini/`, clave = modelo +
  sistema + prompt + schema + temperatura + imágenes + audio): reintentos de la misma efeméride o el
  mismo desempate no gastan cuota. (4) "Puntuar solo a los 6 mejores" ya se cumplía: la corrida
  procesa como máximo `max_procesar` (6) en orden de score por señales gratis, y Gemini corre solo
  en los que pasan los filtros gratis. Juntar más llamadas: no hay más para juntar sin perder la
  validación (clips: 1 por clip; efemérides: elegir + guion + fotos por hecho, que van en orden).
  (5) La segunda clave anda (misma huella en la compu y en la Pi; 5 usos OK el 1 y 2/10). 635 tests OK.
- v0.50.2 (2026-10-02) — **Botones contestados al toque.** Los que disparan algo que tarda
  (`_PESADOS`: aprobar/rehacer voz/🎬/🔁 de efemérides, series, guiones, pasos, pedidos, la cantidad de
  /buscar, buscar desde /streamers, ❌ Cancelar subida) se contestan con "⏳ Un momento…" apenas
  llegan, antes del trabajo; 📤 contesta "📤 Subiendo…" antes de subir (con todo apagado, el cartel
  de la auditoría, como antes). `answer_callback` ignora en silencio "query is too old" / "query ID
  is invalid" (ya contestado o vencido), igual que `edit_message` con "message is not modified". Un
  botón de alguien sin permiso ahora se contesta ("No tenés acceso"), no queda girando. 631 tests OK.
- v0.50.1 (2026-10-02) — **Los apodos de Telegram se SUMAN a los de fábrica.** El 1/10 a las 14:32
  Tommy le puso a Davo "Puerro, David quint, davito, puerrul" desde /streamers y, como los de la DB
  reemplazaban a los del YAML, se perdieron "Davo" y "Davo Xeneize": desde esa vuelta 🔥 daba "0 lo
  nombran de verdad" (antes 21). Ahora `registro.combinar` une YAML + DB; "-" borra solo los de
  Telegram. El menú lo explica. 629 tests OK.
- v0.50.0 (2026-10-02) — **Accesos sin tocar el .env.** `/permitir` (respondiendo a un mensaje
  de la persona, o con su id) y `/sacar_acceso` (respondiendo, con el id, o a secas: lista con
  botones `acc:x:<id>`), solo para Santi (`DUENO` = 8668060171); quedan en `bot_estado.accesos`
  ({sumados, sacados}) y `_permitidos()` = TELEGRAM_ALLOWED_USERS + sumados − sacados (a Santi no lo
  saca nadie), leído en cada vuelta de la escucha. `comandos()` trae `responde_a`. Sumado Micheal
  Lanlin (`8988378175`, el del grupo Rots clips que el 30/09 mandó /streamers y tocó botones sin
  permiso; no hubo otro intento sin permiso en los logs) a TELEGRAM_ALLOWED_USERS en la compu y en
  la Pi. La ayuda de /subidas ya no dice que el 👍 programa. 629 tests OK.
- v0.49.1 (2026-09-30) — "Pegó" busca en el VOD de Kick los 2 Shorts sin original con más vistas del
  día (`pego.vod`, APAGADO; `vod_por_dia` 2, `vod_tope_min` 25; columnas `vod_url`, `vod_segundo`,
  `vod_intentado` en `pegados`; el resumen dice "salió del VOD: acá, en el h:mm:ss"). **Medido en la
  Pi** con "DAVO es del MADRID?" (438.737 vistas): un VOD de 8,3 h → bajar el audio de la variante
  160p + huella 584 s (51× tiempo real), buscar 6,7 s; coincidencia 0,17 (no estaba en ese VOD; el
  otro VOD de esos días no se midió). Cada VOD se guarda: el segundo Short de los mismos días sale casi
  gratis. Muestras del 30/09: efeméride con parallax y gráficos, video 384 s en la Pi (antes 432; el
  render 240 s contra 323); 3 clips con el formato nuevo (2 cayeron en fit_blur por no tener una sola
  persona estable, 1 en "sigue").
- v0.49.0 (2026-09-30) — **Facebook para Pequeña Historia** (APAGADO: `facebook.activo`, hasta que
  Santi complete `docs/facebook.md`). `facebook.py`: Reels Publishing API de Meta en tres pasos
  (`video_reels` start → rupload con el archivo → finish PUBLISHED o SCHEDULED a la misma hora que
  YouTube; si ya pasó, ya; nunca al día siguiente). Mismo "📤 Subir" de la efeméride: se sube a
  Facebook aunque la subida a YouTube esté apagada (el aviso dice las dos cosas). ❌ Cancelar borra
  el Reel programado también. Tabla `subidas`, canal "facebook" (estados programada/publicada/error).
  Credenciales: `FACEBOOK_PAGE_ID` y `FACEBOOK_PAGE_TOKEN` (token de página de larga duración, "no
  vence") en el .env. Sin revisión de Meta: página y app propias, app en modo desarrollo.
  `facebook.version` v23.0 (la guía dice cómo ver la del Explorer). 625 tests OK.
- v0.48.0 (2026-09-30) — **La subida, separada del voto.** 👍/👎 solo votan (antes el 👍 de un
  clip lo programaba en Rots) y el ✅ de la efeméride solo arma el video (antes también lo
  programaba). Debajo de cada clip de streamer y de cada efeméride terminada, una fila aparte:
  "📤 Subir" / "🚫 No subir" (`telegram.fila_subida`, `sub:u|n|x|r|i:<clip_id>`). 📤 programa en su
  horario (clips: el sugerido; efemérides: `hora_publicacion`) y el botón pasa a "📤 Programado
  para las HH:MM" con "❌ Cancelar"; con la subida apagada, 📤 contesta en un cartel "La subida a
  YouTube todavía está apagada (esperando la auditoría)". El estado sale de la DB (`subidas` y
  `no_subir:<clip_id>` en bot_estado), así votar no borra la fila. Los videos propios (/editar,
  /narrar, /serie) no llevan fila: no tienen canal fijo. 620 tests OK.
- v0.47.0 (2026-09-30) — **Formato de los clips de Rots** (APAGADO hasta que Santi vea 3
  muestras: `camara.seguir_cara`, `render.titulo_arriba`). (1) Layout nuevo **"sigue"**: en charla
  o IRL (`camara.categorias_charla`) con UNA persona (o una cara grande), un recorte 9:16 que se
  mueve con la cara (`layout.trayectoria`: 24 cuadros, cara más grande, interpolada y suavizada;
  crop con x/y en función de t, lineal entre puntos), del alto justo para que la persona (≈3,3
  alturas de cara) ocupe al menos `persona_min` (60 %) del alto, nunca menos del 45 % del cuadro
  original. fit_blur queda para 2+ personas o sin cara; `layout_forzado` se respeta. (2) **Título
  grande** (`subtitles.escribir_titulo_ass`: letra gruesa blanca con borde negro, 2 líneas como
  máximo bajando la letra 84→70→60) y el streamer chiquito encima; arriba, o en el split centrado
  en la línea cámara/juego para no taparle la cara. Va en su propio `titulo.ass`, así sale aunque
  el streamer tenga `subtitulos_propios`. 614 tests OK.
- v0.46.0 (2026-09-30) — **Pequeña Historia más dinámica** (pedido de Santi). (1) Ningún video
  entra sin que Gemini mire sus 3 cuadros con la frase y la época: también el del botón 🎬 sobre
  una frase sin video (`revisar_video`, una llamada; antes elegía el primero sin mirar); nada de
  dibujos animados, ilustraciones ni recreaciones salvo que la frase hable de eso. (2) Fotos con
  **parallax 3D** (`parallax.py`, sin modelos: GrabCut separa la figura de la cara o del centro,
  el hueco se rellena con inpaint, dos capas a distinta velocidad; figura llena de contorno
  exterior, porque GrabCut dejaba la boca de un retrato como fondo). Medido en Windows: 5,5 s por
  foto de 5 s contra 7,3 s del zoom de antes (la mezcla en float tardaba 75 ms por cuadro;
  `cv2.blendLinear`, 12). (3) Fotos y videos horizontales ocupan al menos el **72 % del alto**
  (`parallax.caja`, `ALTO_MIN`), recortando los costados hacia la cara o el centro. (4)
  `graficos.py`: el año **contando** al principio (en vez de quieto), **mapa** con el punto
  (coordenadas del artículo + NASA Blue Marble de Commons, dominio público, en la segunda frase),
  **palabras clave grandes** cuando la voz las dice (`claves` en el guion, misma llamada; solo
  palabras que están en el guion) y un **whoosh** sintetizado en cada cambio, mezclado antes de las
  reglas de audio. Interruptores `efemerides.parallax` y `efemerides.graficos` (prendidos).
  609 tests OK.
- v0.45.0 (2026-09-30) — **Voz y claves.** (1) El mensaje del video de la efeméride dice qué voz
  salió: "Voz: Laomedeia" o "Voz: Piper (respaldo, sin cuota | Gemini no respondió)" (el motivo
  viaja en el motor, `piper:…|motivo`); con Piper, botón "🔁 Rehacer con Laomedeia" (`efe:voz`, la
  misma cola que ✅; la propuesta se guarda hasta que salga con Laomedeia). (2) La clave del amigo
  (`GEMINI_API_KEY_2`, formato nuevo de Google: 53 caracteres, empieza con "AQ.", no "AIza") ANDA
  igual que una de AI Studio (200 por encabezado y por URL). La del 29/09 era OTRA (daba 401 desde
  la Pi y desde Windows); Santi la cambió en el .env de Windows y se copió a la Pi el 30/09 (huellas
  comparadas, sin mostrarlas). OJO: la escucha tiene que reiniciarse para leer un .env nuevo
  (`load_dotenv` no pisa lo ya cargado). Además, el bot marcaba una clave inválida PARA SIEMPRE:
  ahora la marca vale solo ese día (`gemini_clave_invalida` = {huella, día del Pacífico}).
  (3) `vod.py` + `audio_huella.coincidencia_rapida` (FFT, igual resultado que la lenta, 13× más
  rápida; 7 h de VOD en ~1 s en Windows): sin conectar hasta medir con un Short de Davo.
- v0.44.0 (2026-09-30) — **La corrida del 30/09 no entregó nada**: "pegó" (dentro de la corrida,
  antes de procesar) tardó 90 min y systemd la mató por `TimeoutStartSec`. Ahora: (1) "pegó" corre
  APARTE, en la escucha a las 02:00 (`_pego_tick`, `pego.hora`/`pego.tope_min` 15, con el turno
  pesado; en la escucha y no en un timer nuevo porque instalar una unidad pide sudo), con tope
  TOTAL real (`pego.SinTiempo`: lo que quedó a medias no se anota) y rotando el streamer por el que
  arranca (`pego_siguiente` en bot_estado; si no, Davo se come los 15 min todos los días);
  la corrida de las 05:00 solo usa lo ya encontrado (`buscar_ahora=False`). (2) Orden fijo de la
  corrida: PRIMERO los clips (candidatos, procesado, entrega); después, cada extra aparte y sin
  poder tumbarla: métricas, el resumen "🔥 Pegó en otros canales" (título, vistas y link de los
  Shorts sin original desde el resumen anterior, `pego_resumen_desde`) y la efeméride. Las
  métricas pasan a después de la entrega: la selección usa las del día anterior. /buscar 🔥 también
  con el tope. (3) `alerta.sh` ahora mira la respuesta de Telegram (curl daba bien aunque Telegram
  rechazara) y reintenta en texto plano; la de 06:32 del 30/09 corrió, y la prueba a mano llegó.
  595 tests OK.
- v0.43.0 (2026-09-29) — **Videos en Pequeña Historia** (pedido de Santi; §3c 5b), APAGADO
  (`efemerides.videos: false`) hasta que apruebe una muestra. Fuentes medidas con el Sputnik: Commons
  y archive.org tienen el noticiero "New Moon" de 1957 (dominio público, 45 s); NASA da material de
  2005 (afuera por época). Sin llamadas nuevas a Gemini: `accion` va en el guion y la elección del
  video (3 cuadros por candidato, hasta 4 por frase) en la de las fotos. Pexels/Pixabay necesitan
  `PEXELS_API_KEY` / `PIXABAY_API_KEY` (sin clave, se saltean). OJO: el efecto de las fotos es un
  zoom suave hacia la cara (no parallax); no se tocó. CLI: `efemeride --videos` para la muestra.
  Decidido por Claude: el stock solo se busca si no hay filmación de archivo; un 🎬 sobre una frase
  sin video busca en el momento sin Gemini (el primero de archivo, cuadro del medio) y lo mira Santi
  en la hoja. 585 tests OK.
  **Primera muestra (Sputnik, en la Pi): 0 videos.** Las frases de acción buscaban "R-7 rocket
  launch pad" y eso no trae nada en ninguna fuente. Ahora `videos_libres.consultas` prueba de la
  puntual a la general (acortando, de a pares de palabras y al final el tema del artículo) hasta
  juntar 4 de la época: "rocket launch" en archive.org (1955-1967) trae primero el noticiero de 1957.
- v0.42.0 (2026-09-29) — **Segunda clave de Gemini** (`GEMINI_API_KEY_2`, pedido de Santi):
  siempre la principal; la segunda SOLO si la principal da 429 de cuota del día, y recién después
  de las dos el modelo de respaldo (orden: flash/principal → flash/segunda → lite/principal →
  lite/segunda). Un 429 que no es de cuota o un 5xx no cambian de clave (el modelo está caído,
  otra clave no lo arregla). El cliente recuerda qué clave quedó sin cuota hasta la medianoche del
  Pacífico. El log dice qué clave usó cada llamada ("Gemini X con la clave principal/segunda").
  La primera vez del día que se usa la segunda, aviso a TELEGRAM_CHAT_ID (`gemini_segunda_dia` en
  bot_estado). Si la segunda es inválida, se ignora, se avisa una vez y se guarda su huella
  (sha256, 12 caracteres, nunca la clave) en `gemini_clave_invalida`: si se cambia en el .env,
  se vuelve a probar. La voz de Pequeña Historia (`hablar_con_claves`) hace lo mismo. 573 tests OK.
- v0.41.0 (2026-09-29) — **🔥 con Davo no daba nada.** Medido en la Pi: la búsqueda
  "davooxeneize" traía 25 Shorts (21 de ≤ 61 s, 21 con 5.000+ vistas, 16 "lo nombraban"), pero
  los 3 más vistos que se comparaban eran memes de fútbol de MordoTv con `#davooxeneize` de relleno
  (600-720 mil vistas), no Davo: no coincidieron con sus 15 clips. Los Shorts de verdad dicen
  "DAVO". Cambios: (1) **apodos** por streamer (`apodos` en el YAML; editables en /streamers →
  🏷 Apodos, tabla `apodos`, que manda): una búsqueda por streamer con todos los nombres unidos por
  `|` (OR de YouTube), 50 resultados; (2) un nombre que está SOLO como hashtag no cuenta
  (`pego.nombra`); (3) originales de los días cercanos al Short (`dias_antes` 3 antes → 12 h
  después) y hasta `max_originales` 60 (antes 15 de 7 días); Kick trae 300 por vistas de la
  semana/mes y filtra por fecha (en orden cronológico no se puede: Davo hace ~500 clips por día);
  la huella de cada clip se guarda en `data/pego_tmp/huellas/` (un mes) y se baja una vez; corta
  apenas uno pasa 0,70; `por_streamer` 3 → 5 Shorts nuevos; (4) **los que pegaron sin original
  se avisan** con link, vistas, contra cuántos clips se comparó y "No encontré el original" (en
  /buscar 🔥 y en la corrida diaria, a los destinos); (5) /buscar 🔥 manda el paso por paso
  (`pego.Recuento`). En `pegados`: columna `comparados` y la mejor coincidencia aunque no pase.
  564 tests OK.
- v0.40.2 (2026-09-29) — **Conectado el canal Rots («Roty», `UCz0-X39ylB_BAO_yFCLMS8w`)** con
  `youtube-auth rots` (subida + yt-analytics.readonly). Token y `client_secret.json` copiados a la
  Pi (`config/`, chmod 600, fuera de git). Verificado en la Pi: `mi_canal()` responde y
  `actualizar_metricas()` leyó métricas de 21 clips (emparejados por título). `YOUTUBE_API_KEY`
  copiada al .env de la Pi: la búsqueda de 🔥 pegó usa la API (probado: 25 resultados). La subida
  sigue APAGADA hasta la auditoría. Pequeña Historia todavía sin conectar. Después Santi pasó la
  app de OAuth a *En producción* y se rehízo `youtube-auth rots` (token nuevo en la Pi, verificado):
  ya no vence a los 7 días.
- v0.40.1 (2026-09-29) — Prendidas por Santi después de la medición: `seleccion.peso_chat` 0 → 0,5,
  `textos.ejemplos_gusto` 0 → 3, `pego.activo` → true y `pego.min_vistas` 10.000 → 5.000 (esa
  semana nada llegaba a 10.000). La API key de YouTube la carga Santi en el .env de la Pi
  (`YOUTUBE_API_KEY`); sin ella, la búsqueda sigue con yt-dlp. 549 tests OK.
- v0.40.0 (2026-09-29) — **/buscar y /streamers con botones:** período (7 días, 30 días, viejos de
  más de 30 días hasta 3 años, 🔥 lo que pegó en otros canales) y cantidad (1, 3, 5); pedido a medio
  preguntar en `bot_estado` (`bu:<token>`, botones `bu:p` / `bu:c`). Si el comando trae todo, o
  palabras, no pregunta. "Viejos": Twitch por fechas, Kick los 100 más vistos de siempre, con los
  filtros de siempre menos antigüedad y vistas. "🔥": solo los originales que pegaron; busca aunque
  `pego.activo` esté apagado (lo pide Santi a mano). 549 tests OK.
- v0.39.0 (2026-09-29) — **Tu gusto en el puntaje:** en la llamada de textos (la del `puntaje`),
  los últimos `textos.ejemplos_gusto` clips que Santi votó 👍 y 👎, con su título y lo primero que
  se dice (tapado), como ejemplo de cómo juzga (`textos.ejemplos_de_gusto`, `texto_gusto`). Hoy hay
  4 👍 y 2 👎. **Subido con 0 (sin ejemplos)** hasta que Santi vea la medición. 535 tests OK.
- v0.38.0 (2026-09-29) — **Picos de chat** (`chat.py`, solo Twitch con VOD): mensajes/s del chat
  en el momento del clip ÷ el ritmo normal de ese stream (mediana de 5 ventanas repartidas por el
  VOD, una vez por VOD), del GraphQL interno de Twitch sin login. Medido 2026-09-29: sin login el
  cursor devuelve páginas VACÍAS, así que cada pedido es una página (~50 mensajes; en Auron ~12 s)
  y el ritmo sale de 3 páginas por ventana; la primera versión contaba mal y daba ~1,2 msg/s para
  todo. Con eso, 12 clips reales de Auron: picos de ×0,45 a ×7,2, sin relación con las vistas (el
  más visto, 20.032, tuvo ×1,38). Factor 1 + peso × log2(pico)/2 (×4 = todo el peso, nunca resta),
  en el orden de candidatos de Twitch (los mejores 2 × n_candidatos) y en la selección; "chat ×N"
  en la línea 📊. Con peso 0,5 el orden de esos 12 cambia mucho ("SOY TONI KROOS" 12° → 4°,
  "DROPS ACTIVOS" 2° → 7°). **Subido con `peso_chat: 0`** (ni se mide) hasta que Santi decida.
  532 tests OK.
- v0.37.0 (2026-09-29) — **Lo que pega en otros canales** (`pego.py`, `audio_huella.py`): una vez
  por día y en /buscar, Shorts de OTROS canales que nombran a cada streamer (título, o canal aunque
  esté pegado: "SpreenClips"), ≤ 61 s, ≥ `pego.min_vistas`, tope `busquedas_por_dia` (API de
  YouTube con YOUTUBE_API_KEY; si no, yt-dlp). Para cada uno, el audio contra los clips originales
  de los 7 días anteriores; el que pasa `pego.umbral` (0,55) entra primero como candidato, con
  bonus `pego.peso` en la selección y "🔥 Pegó en otro canal: X vistas" en el mensaje. El video
  ajeno solo se usa para comparar y se borra. Calibrado en la Pi con clips reales de Spreen (un
  pedazo recomprimido con ruido o tono: 0,70-0,95 contra su clip, ≤ 0,39 contra otros). Un Short
  real de otro canal (Axor, 1802 vistas) no coincidió con ninguno de los 15 clips de esos días.
  Encontrado: el yt-dlp de Windows (2025.06) ya no baja de YouTube ("The page needs to be
  reloaded"); el de la Pi (2026.08) sí. **Subido APAGADO** (`pego.activo: false`) hasta que Santi
  vea la medición. `tests/conftest.py`: ningún test sale a YouTube (uno tardaba 64 s). 527 tests OK.
- v0.36.0 (2026-09-29) — **Métricas del canal** (§4b, `metricas.py`): permiso nuevo
  `yt-analytics.readonly`; `youtube.Cliente.mis_videos / metricas / pct_entero`; tabla `metricas`;
  la corrida diaria las lee si hay token; la selección pesa streamer y tipo de clip con n ≥ 15.
  Hoy no hay token (la conexión con YouTube no se hizo) ni Shorts medidos: el peso no mueve nada
  todavía y no se pudo mostrar su efecto en el orden. Guía actualizada: habilitar YouTube
  Analytics API y sumar el permiso en la pantalla de consentimiento. También: GitHub Pages para la
  pantalla de consentimiento (https://s-fitti848.github.io/ y /privacidad.html, repo
  `S-Fitti848.github.io`, fuera de este repo). 520 tests OK.
- v0.35.0 (2026-09-29) — Efemérides: si un hecho no llega a 4 fotos de época, `fotos_para_guion`
  levanta `PocasFotos` (con el pool y el guion ya armados) y `proponer` pasa al hecho siguiente;
  solo si ninguno llega usa el que más fotos tenga, con el aviso "Ningún hecho de hoy llegó a 4
  fotos de la época" (`Guion.sin_alternativa`). Con ✏️ se queda con el mismo hecho aunque tenga
  pocas. `MAX_GUIONES` 2 → 3 (decidido por Claude: con la regla nueva se pasa más seguido al
  siguiente; son 2 llamadas más de Gemini en el peor caso). 515 tests OK.
- v0.34.0 (2026-09-29) — **Datos personales en textos** (pedido de Santi, a partir de un clip real de
  Davo titulado "si davo es +54 11 3396-6858"): `pantalla.datos_en_texto` para texto escrito
  (mails, teléfonos con prefijo internacional o con contexto, tarjetas con contexto, direcciones
  con calle y número) descarta en candidatos (título del clip y del stream) y en `procesar` (URL
  manual y en vivo); lo que va a Gemini sale tapado (`tapar_datos`) y lo que devuelve (título y
  descripción) se valida y se regenera si trae un dato. Encontrado en el camino: `parsear` no le
  pasaba el `contexto` a `validar`, así que el chequeo de nombres del título contra la
  transcripción (§3 paso 7, desde v0.18) NUNCA corrió en la entrega; arreglado. 513 tests OK.
- v0.33.0 (2026-09-29) — **Davo y el fútbol:** las palabras de fútbol salen de `es_costream`
  (no descartan en ningún camino: diario, /buscar, URL manual, en vivo) y pasan a ser un aviso
  en el mensaje de los streamers con `detectar_marcador` (viaja en `Clip.aviso` → json →
  `enviar_clip`, en la misma línea del 📊). Descarta solo el partido real en pantalla (marcador de
  TV o cancha, sin cambios). El "412" sigue afuera. Además, el umbral de vistas relativas se
  calcula SIN los clips de programas de terceros ni co-streams (no son su contenido). **Davo, sus
  51 clips de los últimos 7 días (Kick, medido 2026-09-29):** 23 del 412, 11 de más de 60 s, 11
  hablan de fútbol. Antes pasaban 13; solo con el cambio del fútbol pasarían 15; con todo
  (fútbol + 30 % de vistas sobre sus 28 clips propios: umbral 25, mediana 22) pasan 5. Los dos
  que liberó el fútbol quedan abajo del 30 %. Con los del 412 adentro el umbral era 36 y pasaban
  3. La detección de partido en pantalla no entra en esa cuenta (corre al procesar). 496 tests OK.
- v0.32.0 (2026-09-29) — **Clips malos** (pedido de Santi): (a) vistas relativas: por streamer,
  solo el 30 % superior de SUS vistas (7 días en recientes; histórico en catálogo, paginado de a
  100 y guardado una semana: vegetta777 = 1095 clips, umbral 328, mediana 171, así que su
  `min_vistas` de 500 ya era más estricto); (b) `puntaje_min` 5 → 6; (c) en cada clip, una
  línea `📊 1.240 vistas (×3,1 su mediana) · 3 creadores distintos · Gemini 7/10`
  (`telegram.por_que`, la mediana viaja de candidatos al json del clip). **La semana pasada con
  las reglas nuevas** (43 entregados del 22 al 29/09, umbral con la ventana de hoy): 29 pasan
  vistas, 37 pasan puntaje ≥ 6, **25 pasan las dos** (58 %). Decidido por Claude: /buscar con
  palabras no filtra por vistas (el que busca algo puntual lo quiere igual); el default de
  `Filtros.vistas_top` es 0 y el 0,30 está en settings.yaml (un test lo exige). 493 tests OK.
- v0.31.0 (2026-09-29) — **Fotos de época** (regla fija, §1): en la efeméride del 29/09 (choque de
  dos Avro Anson, 1940) apareció un avión de 2008. Medido con las 10 fotos que usó ese video:
  9 eran de 1971 a 2017 según `DateTimeOriginal` de Commons (Avro Anson de exhibición, un
  Sukhoi de 2010). Ahora: `Foto.anio` sale de esa fecha (`anio_de`); `mostrar` lleva época y
  lugar (validado en las frases del pasado); frases con `presente`; las fotos de más de 10 años
  después del hecho no son candidatas de las frases del pasado; Gemini ve los años y confirma
  `de_epoca`; la reserva pone primero las fotos del artículo (repetidas antes que modernas); la
  hoja y el texto de aprobación muestran el año de cada foto. Decidido por Claude: la época le
  gana a la cantidad (el mínimo de 6 distintas baja a las que haya de época, piso 3, con aviso);
  `mostrar` pasa de 2-5 a 3-7 palabras (el año y el lugar no entraban). 487 tests OK.
- v0.30.1 (2026-09-28) — Pedido de Santi después de las pruebas de Fleming: (1) mínimo del guion
  de efemérides 85 → 70 palabras ("~30 s está bien para un Short"; con la regla de claridad,
  flash-lite quedaba en 68-82 y la efeméride entera fallaba), se le siguen pidiendo 80-100;
  el aviso de reintento dice cuántas palabras faltan y qué agregar. (2) Falso positivo de
  nombres: "…Volvió" se tomaba por nombre propio; ahora puntos suspensivos, paréntesis y
  comillas «» “” también abren oración (vale para los títulos de los clips también). (3)
  `/efemeride [día/mes] [tema]`: con tema, solo los hechos de esa fecha que lo mencionan. Y el
  error de la propuesta dice qué falló de cada hecho (antes decía "no llegó a 6 fotos" aunque
  el que falló era el guion). La de Fleming NO se rehízo: la prueba real es la del 29/09.
  475 tests OK.
- v0.30.0 (2026-09-28) — **Tres reglas fijas para todos los videos** (§1, decisión permanente de
  Santi), cada una una sola vez en el código compartido y con `tests/test_reglas_fijas.py`:
  (1) fotos que muestran lo que se dice (`ilustrar.py`; en efemérides: guion con `mostrar` por
  frase → búsqueda en el artículo y en Commons por palabras y categoría → Gemini elige por frase en
  una llamada; mínimo 6 distintas, máximo 6 s seguidos, sin repetir salvo que no haya otra; hoja
  con cada foto al lado de su frase); (2) guiones que se entienden (`reglas.REGLAS_CLARIDAD` en los
  prompts de efemérides, /narrar y /serie; efemérides pide además `idea_clave`); (3) audio limpio
  (`media.cola_audio` en renderizar, narrar.mezclar, armar_resumen, multi-POV y efemérides: fade
  in 0,1 s, fade out 0,5 s, largo exacto del video sin `-shortest`; crossfade de 0,04 s en las
  uniones sin correr la sincronía; `chequear_audio` en `enviar_clip` avisa picos > −3 dB en el
  último segundo o audio y video desparejos). Probado con ffmpeg real: resumen de 3 tramos y
  mezcla con voz, audio = video al milisegundo; un final a −0,2 dB dispara el aviso. Encontrado
  probando la búsqueda real: Commons sirve miniaturas desde `thumb.wikimedia.org`, que no tenía la
  pausa de 2 s entre descargas (solo `upload.`); ahora la tienen las dos. Decidido por Claude: el
  crossfade se hace estirando cada tramo d/2 hacia la unión (un acrossfade común acorta el audio
  y lo desfasa del video); efemérides pasa a 2 llamadas por evento (guion + fotos: +1 por día);
  `--hecho` en el CLI para rehacer un hecho puntual.
  **Lo que encontró la primera prueba real (Fleming en la Pi):** (a) el chequeo de audio avisó que
  el audio duraba 26,75 s y el video 35,37 s: con la entrada `concat` de los tramos, ffmpeg 7.1
  cortaba el audio del mismo filtro (con cualquier otra entrada daba exacto). Ahora el audio de la
  efeméride se termina en un paso aparte (`media.preparar_audio`) y se pega sin filtros. (b) El
  guion salió claro ("el hongo mataba a las bacterias… por eso servía para curar infecciones"),
  pero 2 de 8 fotos no tenían nada que ver (una postal de Hamburgo, una máquina de
  radioisótopos): búsquedas genéricas ("microscope view", "medical research") y flash-lite
  eligiendo la primera candidata sin mirar. Arreglos: el prompt pide la COSA puntual con
  ejemplos de qué no; cada frase puede elegir cualquier foto del pool (antes solo las de su
  búsqueda); Gemini dice qué se ve en la que eligió (`se_ve`); y la reserva solo usa fotos que
  Gemini puso para alguna frase, nunca resultados que nadie miró (en 🔁 sí, porque la mira Santi).
  462 tests OK.
- v0.29.0 (2026-09-28) — **Mezcla diaria revisada con lo que rinde** (pedido de Santi: Davoo,
  Auron, Coscu, Coker y Spreen rinden; Minecraft y el Dedsafío no). Carpeta Dedsafío sin diarios
  ni en vivo (en la Pi ya estaba así, tocado por Telegram; ahora también de fábrica). Carpeta
  nueva **Famosos** (diarios y en vivo) con `auronplay` en el YAML (Twitch, 100 clips en 7 d,
  verificado con `registro.resolver`). Mezcla `argentinos: 2` + `famosos: 1`, sin cupo del
  evento. Multi-POV APAGADO. Peso por votos: el score se multiplica por
  1 + 0,5 × (👍 − 👎) / (👍 + 👎 + 3) de los votos de Santi a los clips del streamer (hoy: coker
  y spreen con 1 👍 cada uno → ×1,125). Arreglado de paso: el relleno no respetaba el tope por
  streamer (podía salir un segundo clip del mismo). Decisión anotada en §1: nada de videos largos
  con voz de IA; si se hacen, con la voz grabada de Santi. Decidido por Claude: Auron con cupo
  propio (en el fallback competía contra las vistas absolutas del catálogo de Vegetta, otra
  escala, y no entraba nunca); `previa` 3 y `peso` 0,5 para que pocos votos muevan poco.
  431 tests OK.
- v0.28.4 (2026-09-28) — **Gemini caído = falla pasajera.** La prueba a mano de la efeméride
  (16:33) no salió: el principal sin cuota y flash-lite con 503 "high demand" en todos los
  reintentos (10/20/30/40 s se quemaban en 2 minutos). Ahora (`gemini.py`): un 5xx, un 429 que no
  es de cuota o un timeout se reintentan 3 veces con 30, 60 y 120 s; después, el otro modelo con
  las mismas esperas (sin cuota se salta directo al otro). Si todo falla, `GeminiError.pasajero`.
  Con eso: la efeméride suma un intento en una hora (con las fotos en caché) en vez de avisar; y
  la entrega diaria de clips, si queda corta porque hay clips sin textos por Gemini caído, manda lo
  que tiene y agenda los que faltan en una hora (`bot_estado.clips_reintento`,
  `_clips_reintento_tick` en la escucha: elige SOLO los que faltan). Los dos, hasta
  `textos.reintento_hasta` (22:00); pasado eso, el aviso de siempre. Un /ya no agenda: contesta
  ahí. Decidido por Claude: (1) el tope de las 22:00 (una efeméride tiene que salir ese día); (2)
  después de una falla pasajera completa, el mismo cliente no insiste por 15 min
  (`PAUSA_CAIDO_S`): con Gemini caído una llamada puede tardar ~19 min, y con 15 clips la corrida
  diaria tenía la Pi ocupada horas; (3) el 429 de Wikimedia NO cuenta como pasajero (para eso
  están las 07:00 y 10:00). /narrar y /serie usan el mismo cliente: con Gemini caído tardan más en
  contestar que antes. 420 tests OK.
- v0.28.3 (2026-09-28) — **La efeméride de las 05:00 falló con un 429 de upload.wikimedia.org.**
  Causa (del log de la Pi): la foto que dio 429 era un ORIGINAL (un Bundesarchiv), no una
  miniatura: con `iiurlwidth=1280`, si la foto no es más ancha que eso la API devuelve el original.
  Arreglos: (1) User-Agent según la política de Wikimedia (`config.user_agent()`: nombre/versión,
  link al repo y `WIKIMEDIA_CONTACTO` del .env) en efemérides y música; (2) solo miniaturas
  (1280 → 960 → la foto no se usa, descarte `sin miniatura`), bajadas solo de las que pasaron
  licencia y epígrafe, 2 s entre descargas, Retry-After hasta 120 s; (3) caché en
  `data/cache_wiki/`; (4) `bajar_fotos`: la foto que falla se saltea y la siguiente ocupa su lugar
  (también en 🔁 con la reserva), pero 3 × 429 seguidos cortan; (5) reintentos a las 07:00 y 10:00
  desde la escucha (`_efe_reintento_tick`), y recién después del último, el aviso. 404 tests OK.
- v0.28.2 (2026-09-28) — Costo de Gemini (docs/costo-gemini.md): ~30 llamadas de texto por día
  (medido en la Pi: 11-15 clips/día con textos, más lo nuevo) + 1 de voz; pagando el principal,
  ≈ US$4/mes hasta dic. 2026 y ≈ US$8/mes desde 2027 (precios oficiales del 28/09; doble margen
  en el doc). Nada pago activado.
- v0.28.1 (2026-09-28) — **Subida automática a YouTube, preparada y APAGADA**
  (`youtube_upload_enabled: false`). `clips_bot/youtube.py` sin librerías de Google: OAuth de app
  de escritorio con redirección a 127.0.0.1 (`python -m clips_bot youtube-auth rots|
  pequena_historia`, en la compu con navegador; tokens en `config/youtube_token_<canal>.json`, fuera
  de git), upload reanudable en privado con `publishAt`, cancelar = privado sin fecha. Dos canales
  de la misma cuenta: Rots (clips, categoría 20) y Pequeña Historia (efemérides, 27). Al aprobar se
  programa sola: ✅ de una efeméride → ese mismo día a `efemerides.hora_publicacion` (12:00) o en
  30 min si ya pasó, nunca después de las 23:55 (decidido por Claude: "un día como hoy" no puede
  salir mañana; el test lo encontró corriendo en la Pi a las 23:32, cuando "30 min" daba
  00:02 del día siguiente); 👍 de un clip
  de streamer → su horario sugerido o el siguiente libre (decidido por Claude: el 👍 es la
  "aprobación" de un clip; los videos propios de /editar, /narrar y /serie no se suben solos,
  porque no tienen canal fijo). `/subidas` lista y cancela; tabla `subidas`. Guía para no
  programadores: `docs/auditoria-youtube.md` (proyecto, pantalla de consentimiento, credencial,
  conectar canales, formulario de auditoría campo por campo). Revisado en la doc oficial:
  `videos.insert` cuesta 1 unidad de un balde aparte de 100 por día (antes 1600 de 10.000; §1
  corregido); la restricción a privado de los proyectos sin auditar sigue. OJO: con la app de OAuth
  en modo *Prueba*, Google vence el permiso cada 7 días: hay que pasarla a *En producción*. NO
  probado contra YouTube (sin credenciales): tests con sesión falsa. 391 tests OK.
- v0.28.0 (2026-09-28) — **Carpetas de streamers.** Cada `grupo` es una carpeta (tabla
  `carpetas`) con dos interruptores: `en_vivo` (el modo en vivo SOLO vigila esas carpetas) y
  `diarios` (la corrida de las 05:00 y /ya solo usan esas). De fábrica: Argentinos en vivo sí;
  Dedsafío y Catálogo en vivo no; diarios todas. En /streamers, adentro de una carpeta: "🔴 En
  vivo: sí/no" y "📅 Diarios: sí/no"; en cada streamer "📦 Mover a otra carpeta" (con "➕ Carpeta
  nueva"); una carpeta vacía muestra "🗑 Borrar carpeta". /agregar sin carpeta pregunta con
  botones (con "➕ Carpeta nueva") después del ✅. Mover un streamer del YAML es una acción nueva
  (`registro.MOVER`), no un ALTA: con ALTA, /quitar solo borraba la anotación y el streamer volvía
  a su carpeta. Decidido por Claude: una carpeta que no está en `seleccion.mezcla` (las creadas por
  Telegram) compite por el cupo del catálogo (fallback) y se le procesa al menos un clip; sin eso
  nunca entraba en la entrega diaria. Las carpetas nuevas arrancan sin en vivo y con diarios.
  379 tests OK.
- v0.27.4 (2026-09-28) — Pequeña Historia en la corrida de las 05:00: `efemeride_del_dia` completa
  la música, propone la de hoy y manda la aprobación; con ✅ se arma. Decidido por Claude: va a los
  destinos de la entrega diaria (hoy el grupo Rots clips) salvo que se ponga `efemerides.chat`
  (para el privado de Santi: "8668060171"); si falla, avisa y la corrida de clips no se entera;
  con `--simular` no propone. También: la mezcla de música pasó a mono (en estéreo la voz perdía
  3 dB: -17,7 → -20,6; ahora -17,6). 367 tests OK.
- v0.27.3 (2026-09-28) — **Gemini TTS lee en voz alta la instrucción de tono.** Encontrado en la
  prueba real de la voz nueva (Rosetta con Laomedeia, en la Pi): los primeros 10 s eran "Leé esto
  en español rioplatense, como alguien entusiasmado…" y el guion arrancaba a los 10,4 s. La
  muestra C del 27/09 (la que eligió Santi) TAMBIÉN empezaba así. Probado (4 llamadas):
  instrucción larga → leída; en inglés ("Say enthusiastically…") → traducida y leída; corta
  ("Say cheerfully:") → leída; como `systemInstruction` → 400 "Developer instruction is not
  enabled for this model". Decidido por Claude: sin instrucción (`efemerides.tts_instruccion: ""`);
  el entusiasmo sale de la voz Laomedeia y del guion con ¿? y ¡!. Red de seguridad
  (`narrar.recortar_inicio`): si la voz dice algo antes de las 3 primeras palabras del guion, se
  corta ahí. Velocidad real de Gemini sin la instrucción: ~2,3 palabras/s (no 1,9): 85-105
  palabras son ~37-46 s. La prueba dio 46,6 s tras acelerar ×1,25, video 417 s en la Pi. 362 tests OK.
- v0.27.2 (2026-09-28) — Música automática para Pequeña Historia (`clips_bot/musica.py`,
  `docs/musica.md`). `musica/` entera fuera de git. `musica/youtube/` (los 10 temas de la
  Biblioteca de YouTube que dejó Santi, copiados a la Pi por scp) tiene prioridad; `musica/kevin/`
  (Kevin MacLeod, CC BY 4.0: catálogo `pieces.json`, 839 de 1443 pasan) y `musica/openverse/`
  (solo CC0 y CC BY) se llenan solos hasta 10 por fuente (`python -m clips_bot musica --llenar`),
  con autor, licencia y link en `musica/biblioteca.json`. Filtros: 1-4 min, ≤ 15 MB, sin voces.
  Por video: tono del guion (Gemini lo da en la misma llamada: alegre/epico/misterioso/curioso/
  emotivo) contra las etiquetas del tema, sin repetir en 5 videos, sin los vetados. /reclamo sobre
  un video de efemérides veta su tema (no excluye a nadie). Decidido por Claude: afuera también
  CC BY-SA (el share-alike podría alcanzar al video entero); de youtube/ se saltea lo que dice
  "feat." (canciones con voz: "Shining (feat. …)"); en Openverse "sin voces" = etiqueta o título
  "instrumental" y ninguna etiqueta de voz. Encontrado: Openverse devuelve 403 (Cloudflare) si el
  User-Agent tiene una tilde ("efemérides"); los UA quedaron en ASCII. 358 tests OK.
- v0.27.1 (2026-09-28) — Voz de Pequeña Historia: Gemini TTS (Laomedeia, la muestra C) con la
  instrucción de sonar entusiasmado; si falla o no hay cuota, Piper daniela ajustada (0,88 /
  noise 0,8 / noise_w 1,0 / +1,5 st, la muestra A). Todo en `efemerides.*` de settings. Como
  Gemini da UN audio para todo el guion, los cortes de foto por frase salen de alinear Whisper
  contra el guion (`narrar.alinear_a_guion`, difflib); si pasa de 45 s se acelera con atempo hasta
  ×1,25. La alineación también arregla lo pendiente de los subtítulos: ahora llevan el TEXTO del
  guion y de Whisper solo los tiempos, en efemérides, /serie y /narrar ("Jean-François" entero,
  "propio" y no "propia"). Guion de 85-105 palabras (Gemini a 1,9 palabras/s MEDIDO: 45 s con la
  aceleración; con el respaldo de Piper queda en ~28-33 s). Decidido por Claude: el rango (sale
  de la voz principal) y subir también noise_scale (el pedido decía "más variación de
  entonación", que en Piper es sobre todo noise_scale). 341 tests OK.
- v0.27.0 (2026-09-28) — El canal de efemérides pasa a llamarse **"Pequeña Historia"** (antes
  "Pasó Hoy") en todos lados: ayuda, mensajes, prompts, títulos, User-Agent y este archivo
  (también las entradas viejas del changelog, para que se pueda buscar por un solo nombre).
- v0.26.1 (2026-09-27) — "La voz de efemérides suena triste y plana". Voz ajustable desde
  settings (`voz.length_scale`, `noise_scale`, `noise_w_scale`, `semitonos` con rubberband), por
  defecto igual que siempre; vale para /narrar, /serie y efemérides. Guion de efemérides: frases de
  ≤ 14 palabras, al menos una pregunta y una exclamación, cierre con gancho (? o !). Música de
  fondo para Pequeña Historia: `musica/` (audios fuera de git, créditos en `musica/creditos.json`), una
  pista al azar por video al 12 % con ducking (sidechaincompress) y fundido final; vacía = sin
  música. OJO: contradice §1 "sin música agregada" (pedido explícito de Santi para este canal).
  Muestras mandadas por Telegram con el guion de la Rosetta, MEDIDAS en la Pi:
  0 daniela actual 42,2 s de voz (129 s de síntesis) · A daniela 0,88 + noise_w 1,0 + 1,5 st:
  40,3 s (140 s): la pausa entre frases no se achica con length_scale · C Gemini TTS
  (Laomedeia, "entusiasmado"): 60,8 s (21 s) — el mismo guion se pasa de 60 s: habría que
  escribirlo ~30 % más corto, y gasta cuota · D es_MX-claude-high con los ajustes de A: 50,2 s
  (27 s: 5× más rápido de sintetizar que daniela). La B (A + música) espera la música. Falta que
  Santi elija. 337 tests OK.
- v0.26.0 (2026-09-27) — Pequeña Historia (§3c): `/efemeride [día/mes]` y el CLI `efemeride`, con
  aprobación ✅ / ✏️ / 🔁 foto N. Todavía NO en la corrida diaria. Probado de punta a punta con el
  27/09 real: en la Pi salió "El día que se descifró la piedra de Rosetta", 42,0 s, 12 fotos por
  frase, año 2 s, subtítulos por palabra (voz 102 s, subtítulos 125 s, video 382 s: ~10 min en
  total, el zoom sobre la foto 4× es lo caro). Todo lo que dice el guion está en el artículo
  (verificado a mano, incluido "la pieza más visitada"). Lo que salió de probar con datos reales:
  (1) el artículo del hecho lo elige Gemini (el primero de la lista era el país); (2) imágenes duras
  fuera por epígrafe; (3) "mil millones" de la memoria de Gemini → chequeo de números con letras;
  (4) Piper habla a 3,1 palabras/s MEDIDO, no 2,5: el rango pasó a 105-135 palabras y
  `narrar.PALABRAS_POR_SEGUNDO` también (los guiones de /narrar y /serie salían ~20 % cortos);
  (5) ranking de 8 y no de 3: con 3, ese día no había video (Google: Gemini descartó con razón 5
  de 8 fotos; Vorónezh y E=mc² tenían 1-2 fotos libres); (6) Wikimedia da 429 si se le pega
  seguido: pausa entre llamadas, Retry-After y miniaturas de 1280 (ancho estándar); (7) el autor
  de las fotos CC BY-SA a veces está en `Attribution` o `Credit` y no en `Artist`; sin autor, una
  foto que exige atribución no se usa. Con el modelo de fallback (flash-lite, el principal sin
  cuota ese día) el descarte visual varió entre corridas (Google: 5, 2 y 6 de 8) y el título salió
  sin tildes. 334 tests OK.
- v0.25.1 (2026-09-27) — Un video SIN pista de audio (no silencioso: sin stream) hacía reventar
  faster-whisper (IndexError adentro de PyAV). Lo tapaba el filtro de silencio (100 %), que desde
  v0.24.2 no corre para /editar ni /narrar: ahora, sin pista de audio, no se llama a Whisper.
  Probado con un mp4 sin audio de verdad: en Windows por `procesar` real, y en la Pi el camino de la
  voz entero (Piper 3,5 s de voz en 14 s, Whisper sobre la voz 21 s, render 37 s, final 1080x1920
  de 15 s con solo la voz). **Desplegado** en la Pi (`942bc0b`): hasta ahí seguía en `d226073`
  porque nada de lo de hoy estaba pusheado (ver Trampas). Visto de paso: los subtítulos palabra por
  palabra salen de Whisper escuchando la voz y pueden diferir del guion aprobado ("propia" por
  "propio"); pendiente alinearlos al texto del guion. 289 tests OK (también en la Pi).
- v0.25.0 (2026-09-27) — `/serie <link o video> [cc: <link>] [partes N] [sin audio]` (N de 2 a 5,
  default 3; el original tiene que durar N × 45 s). Escenas (las de /narrar, pidiendo 12 × N) →
  Gemini divide en N etapas en orden y elige 8-10 momentos por etapa (validado: exactamente N, sin
  superponerse, momentos dentro de su etapa; un reintento con los errores) → hoja con una fila de
  miniaturas por parte + una línea por etapa, ✅/✏️ → un resumen de 40-55 s por etapa procesado como
  video propio (OCR, tono, textos; si una parte se descarta, no se arma la serie) → los N guiones en
  UNA llamada, con título de serie, gancho, y los que no son el último cierran nombrando la parte
  siguiente (se valida mirando el cierre; si no, reintenta), ✅/✏️ (+ ✅ Aprobar sin audio si hay
  música) → voz, subtítulos palabra por palabra, "Parte X/N" arriba 3 s, original al 15 % → las N
  juntas, "Título (Parte k)" (se recorta la base, nunca el número; ≤ 59) y horarios 13:00 / 18:00 /
  21:30 (con más partes, al día siguiente). Las dos aprobaciones pesadas van por la cola de
  siempre. Gemini: 1 (división) + N (textos) + 1 (guiones). Probado a mano el render de una parte
  (cartel y subtítulos por palabra con libass) y la hoja; con Gemini y Piper reales, NO. 288 tests OK.
- v0.24.2 (2026-09-27) — `/editar` y `/narrar` ya no descartan por "casi todo silencio" ni "pocas
  palabras" (se miden y se guardan igual): son filtros de clips de streamers, y un video de proceso
  sin nadie hablando es justo lo que se quiere narrar. Una transcripción lenta en un video propio
  sigue sin subtítulos del original en vez de tirarse. Opción `sin audio` (en el comando, abajo del
  video o antes de mandarlo): en /narrar el original sale de la mezcla y queda solo la voz; en
  /editar el mp4 sale mudo. Aviso de música: el audio del video va a Gemini en la MISMA llamada del
  guion (no gasta cuota aparte) y devuelve `musica` (ninguna / de_fondo / cancion + cuál, si la
  reconoce); si hay, el mensaje del guion lo dice y suma **✅ Aprobar sin audio**. NO calibrado:
  cuánto acierta Gemini con la música no se midió (no se gastó cuota en pruebas). Arreglados en el
  camino, los dos encontrados probando: (1) `del modelo` doble en `procesar` tras una transcripción
  lenta que seguía (antes solo con --forzar; con el cambio habría roto cada aporte lento); (2) sin
  audio de fondo, `mezclar` cortaba el video al largo de la voz (40 s → 30 s): ahora la voz se
  rellena con `apad`. Y los tokens de los botones que eran todos dígitos con un 0 adelante se
  rompían al pasarlos a número (`parse_callback` devuelve ahora también `crudos`). 264 tests OK.
- v0.24.1 (2026-09-27) — Modo en vivo con umbral relativo al ritmo de cada canal:
  `max(4, 15 × ritmo de la última hora sin el momento)`. Simulado vuelta por vuelta sobre 72 h
  reales: 4,7 alertas/día (antes ~27), sin tocar el tope. `max_paginas_kick` 5 → 8 (spreen y davoo
  llegan a ~150 clips/h). 248 tests OK.
- v0.24.0 (2026-09-27) — `/narrar` con videos de más de 90 s: cortes de escena con ffmpeg
  (`select=gt(scene,0.3)`, a 320 px), escenas normalizadas a 12-40 (se funden las cortas, se parte
  un plano secuencia), un frame por escena a Gemini que elige 8-10 pasos en orden (validado: rango,
  orden, sin repetir; un reintento con los errores), 4-5 s por paso centrados en la escena (8 → 40 s,
  10 → 48 s), hoja de miniaturas numeradas + una línea por paso con ✅/✏️, y recién con ✅ se corta
  (una pasada de ffmpeg, re-encodeando) y sigue el camino de siempre: procesar → guion → voz.
  Probado a mano con un video sintético de 120 s: 11 de 14 cortes detectados (los que faltan son
  colores de luminancia parecida), resumen de 40,0 s y 48,0 s exactos, con audio, 4 s de ffmpeg.
  `cc: <link>` en /editar y /narrar (en el comando, abajo del video o solo antes de mandarlo): crédito
  "Video original: canal – link, licencia CC BY", el canal sale del link con yt-dlp sin bajarlo, y
  avisa si YouTube informa una licencia que no es CC. Sin `cc:`, un video propio ya no sale con
  "twitch.tv/" pelado en el crédito: queda "(completar autor)". **Arreglado: los botones de
  /ayuda, /destinos, ➕ más y ✅ del guion no llegaban a la escucha** (`callbacks` filtraba por
  st/add; ahora una sola lista, `telegram.PREFIJOS_BOTONES`, que usa también `menu.parse_callback`).
  243 tests OK.
- v0.23.0 (2026-09-27) — Modo en vivo (`/envivo on|off`, §3b): detección dentro de la escucha,
  Twitch en lote cada 5 min y Kick cada 2, momento = 3 creadores distintos, procesado con prioridad
  sobre la cola, "🔥 SUBIR YA" al chat que lo prendió, tope 3/h, y los tiempos de cada tramo en
  `envivo_alertas`. Replay de 72 h reales: con 3 creadores son ~27 alertas/día (ver tabla en §3b).
  `procesar(permitir_fecha=True)`, `enviar_clip(encabezado=...)`. 217 tests OK.
- v0.22.0 (2026-09-27) — Modos `/editar` y `/narrar` (video propio: archivo de Telegram o link con
  yt-dlp). `/ayuda` por secciones con botones. Cantidad por pedido (`xN`, tope 6), `/cantidad`, y
  los botones `➕ N más` / `🔁 Reemplazar`, que usan primero lo ya procesado sin gastar Gemini.
  Destinos separados: lo que se pide por comando se contesta donde se pidió, lo diario va a la
  lista de `/destinos`. `/streamers`, `/agregar`, `/quitar`, `/aca`. Sudoers acotado. 196 tests OK.
- v0.0.0 (2026-09-21) — Documento inicial. Sin código.
- v0.0.1 (2026-09-21) — Publicación manual vía Telegram + módulo de métricas §4b.
- v0.0.2 (2026-09-21) — Upload automático a YouTube Shorts por API; revisado después.
- v0.0.3 (2026-09-21) — Confirmado: sin auditoría los uploads por API quedan bloqueados privados
  para siempre. Todo se sube a mano hasta la auditoría.
- v0.1.0 (2026-09-21) — Esqueleto del repo + cliente Twitch Helix + comando `candidatos`. 6 tests OK.
- v0.2.0 (2026-09-21) — Pasos 3–6: `procesar <url>` (yt-dlp, filtros de audio, faster-whisper,
  layout con OpenCV, render 9:16 con subtítulos). ffmpeg 9.0.2 + faster-whisper 1.2.1. 19 tests OK.
- v0.3.0 (2026-09-21) — `subtitulos_propios`; filtro de co-streams; paso 7 Gemini con validación
  estricta; paso 8 selección; entrega por Telegram. 61 tests OK.
- v0.3.1 (2026-09-21) — Gemini `gemini-3.6-flash` (2.5-flash dio 404), reintentos ante 503.
- v0.3.2 (2026-09-21) — Telegram configurado (@Clipsito_bot). Primer envío real OK.
- v0.3.3 (2026-09-21) — Subtítulos al 80 % del alto y fuente 74→64; cámara con 50 px menos al pie +
  separador negro. 63 tests OK.
- v0.3.4 (2026-09-21) — Telegram mostraba el video angosto: faltaban width/height en sendVideo (el
  mp4 estaba bien). Cámara 40 % / juego 60 %. 65 tests OK.
- v0.4.0 (2026-09-22) — Dos fuentes: reciente (velocidad × mismo momento) y catálogo (cursor de
  Helix por streamer en la DB). Mezcla por cupos con fallback. `depende_de_fecha`. 83 tests OK.
- v0.4.1 (2026-09-22) — Primera corrida con credenciales de Twitch: `veggeta` no tiene clips (es
  `vegetta777`); dedsafio como canal propio no rinde. Los umbrales iniciales estaban altos.
- v0.5.0 (2026-09-22) — Fuente reciente revisada con datos reales: ventana 7 días, mínimo 24 h de
  antigüedad, `min_vistas` 0, sin umbral de velocidad, y score = duplicados × log de vistas.
  Catálogo desde 7 días. 84 tests OK.
- v0.6.0 (2026-09-22) — `duracion_max_s` 60; `empate_pct` por fuente; comando `diario [--simular]`;
  la entrega rechaza streamers sin permiso.
- v0.6.1 (2026-09-22) — Primera `diario --simular` real (flujo completo OK). `candidatos` ya no
  mueve el cursor; `textos.reintentos` 1 → 3 y prompt más explícito con los hashtags. 87 tests OK.
- v0.7.0 (2026-09-22) — Política: streamers por experimento, recordatorio fijo de subir en privado y
  chequear copyright, exclusión automática ante un reclamo (`/reclamo <id>`, `atender-telegram`,
  tabla `streamer_estado`). Kick como segunda plataforma. Mezcla por GRUPO. Palabras de fútbol y
  marcador deportivo por streamer. 104 tests OK.
- v0.8.0 (2026-09-22) — Dedsafío: 54 de 62 participantes resueltos y cargados en `evento_dedsafio`.
  Grupo evento con filtros propios y agrupación de "mismo momento" entre streamers por hora real
  (±2 min). Short multi-POV secuencial (hasta 3 ángulos, ±4 s del pico de reacción, cartel con el
  nombre, orden de menos a más visto, crédito a todos) + comando `multipov`. Gemini: 429 por cuota
  ya no se reintenta. 120 tests OK.
- v0.8.1 (2026-09-22) — CLAUDE.md reconstruido desde el transcript después de que un script de
  parche lo rompiera (37 MB de texto repetido, sin backup).
- v0.9.0 (2026-09-22) — `git init` + repo con commit por cambio. Gemini: free tier medido en ~20
  requests/día, fallback automático a `gemini-3.5-flash-lite` ante 429 por cuota, reintentos 3 → 2 y
  `textos_pendientes` para no perder el render. Fútbol: segunda señal por fracción de verde-césped
  (calibrada con 8 clips reales; agarra el caso que el marcador no veía). 122 tests OK.
- v0.21.0 (2026-09-25) — `/streamers` con navegación por botones, `/agregar` con confirmación y
  `/quitar`, guardando en la DB y combinando con el YAML al cargar. Arreglado el crash de `/buscar`
  en Twitch y blindada la escucha: un comando que explota avisa y no tumba el servicio ni queda en
  loop en la cola. `alerta.sh` reescrito (tenía retornos de carro reales adentro). 185 tests OK.
- v0.20.0 (2026-09-24) — Multi-POV prendido A PRUEBA con la verificación de "mismo hecho": dos 👎
  dentro de 14 días y el bot lo apaga solo (interruptor en la DB, no en el YAML). Prueba arrancada
  en la Pi: 2026-09-25 02:03 → 2026-10-09 02:03. 178 tests OK.
- v0.19.0 (2026-09-24) — Filtro de tono (`tono_sensible`, descarte duro) y puntaje de calidad
  (1–10, corte provisorio 5) en la MISMA llamada de textos, con 4 frames del clip. Relleno marcado
  para llenar el cupo solo con lo que falló únicamente por calidad, aviso de "0 clips hoy", botones
  👍/👎 con el voto y el puntaje en la DB, y verificación de "mismo hecho" para el multi-POV
  (superposición léxica + Gemini, las dos), probada con 5 grupos reales. 175 tests OK.
- v0.18.0 (2026-09-24) — Multi-POV APAGADO hasta tener verificación de "mismo hecho" (la
  agrupación usa la hora de creación del clip, no la del hecho). Título validado contra la
  transcripción. `/ya`, `/buscar` con varios streamers repartiendo el tope, y `/ayuda` con un
  ejemplo por comando. `subtitulos_propios` en rivers_gg, arigameplays y gamstergaming. La corrida
  automática de las 05:02 por systemd salió `success` (27 min de reloj, 46 min de CPU): el sandbox
  de la unidad quedó verificado. 171 tests OK.
- v0.17.1 (2026-09-23) — SIGTERM se maneja como una salida normal para que corran los `finally`:
  sin eso, un `systemctl stop` en medio de una corrida dejaba el turno pesado tomado y el `/buscar`
  siguiente quedaba en cola hasta que venciera (3 h). Encontrado probando el corte, no leyendo. En
  Windows el test no sirve (no hay SIGTERM real): se verificó en la Pi.
- v0.17.0 (2026-09-23) — Modo escucha: `atender-telegram --escuchar` con long polling y su propio
  servicio (`clips-bot-telegram`, `Restart=always`, misma prioridad baja), así `/buscar` anda en el
  momento y no recién en la corrida del día siguiente. Turno de "trabajo pesado" en la DB que toman
  `diario` y cada búsqueda: nunca hay dos clips procesándose a la vez. Si llega un `/buscar` durante
  la corrida diaria, contesta "en cola" y arranca solo al terminar; al revés, `diario` espera hasta
  20 min a una búsqueda y después arranca igual (el día no se saltea). `MAX_BUSQUEDAS` pasa a ser el
  tope de la COLA, porque la ejecución ahora la serializa el turno. 163 tests OK.
- v0.16.0 (2026-09-23) — Comando `/buscar <streamer> [palabras] [días]` por Telegram, solo para
  usuarios permitidos: búsqueda a mano con todos los filtros, aviso previo con la cantidad de
  candidatos, hasta 3 clips por búsqueda y 2 búsquedas simultáneas (turno en la DB, no en memoria,
  porque puede haber dos procesos). El envío de un clip se extrajo a `enviar_clip`, compartido con
  `seleccionar`. 157 tests OK.
- v0.15.0 (2026-09-23) — Primer benchmark REAL en la Pi. `small` se queda (entra cómodo y `base`
  pierde calidad visible). Tope de tiempo en la transcripción (`transcripcion_lenta`) por el clip
  que se iba a 28× la duración. Hallazgo de hardware: la Pi no tiene undervoltage sino
  **throttling térmico** (84,7 °C, `throttled=0xe0008` bajo Whisper sostenido). 152 tests OK.
- v0.14.0 (2026-09-23) — Multi-POV: cada ángulo tiene que mostrar algo en su tramo (medido frame
  por frame, no por promedio: el de PattyMeza daba 56 % de frames en negro y el brillo promedio
  0,22 no lo delataba). Rescate con fit_blur → reemplazo por otro canal del momento → si no, no se
  arma. OCR en `spa+eng` (encuentra un teléfono que `eng` solo no leía, sin falsos positivos
  nuevos; cuesta 1,5–2×). Comando `benchmark` y carpeta `deploy/` con el servicio systemd, el timer
  de las 05:00 AR, la alerta por Telegram y logrotate. 151 tests OK.
- v0.13.1 (2026-09-23) — Segunda entrega real de 3 (Spreen y Vegetta rehechos con fit_blur + el
  multi-POV de PattyMeza/Hasvik/aldo_geo). `TELEGRAM_ALLOWED_USERS` cargado. Primera corrida con
  todo el filtrado nuevo: **28 descartes por `programa_terceros`**, y el filtro de césped agarró un
  clip de fútbol de coker (55 % en 4 de 12 frames). La capa de pantalla corrió en los 5 clips
  procesados (3–11 s cada uno) sin ningún falso positivo. Gemini se quedó sin cuota del modelo
  principal y siguió con el fallback, que además devolvió 503 varias veces: el camino de respaldo
  funcionó. Los clips que ya estaban en `ready/` no pasaron por el filtro nuevo, así que se
  revisaron a mano: salió uno de Davoo (stream "…ANALIZAMOS").
- v0.13.0 (2026-09-23) — `layout_forzado` por streamer (coker: `fit_blur`, hace podcast
  multicámara) y regla automática: si en la zona del "juego" hay caras, no hay juego → fit_blur
  (calibrada sobre los 11 clips que daban split; hizo falta un mínimo de ancho de cara porque Haar
  ve caras en los skins de Minecraft). Capa nueva `pantalla.py`: OCR con tesseract sobre 8 frames,
  descarta por mails / pago / dirección, y los números solo con palabra de contexto (medido: sin eso,
  3 falsos positivos y 0 aciertos sobre 26 clips; con eso, 1 acierto y 0 falsos positivos).
  `palabras_programa` también en davooxeneize. 147 tests OK.
- v0.12.0 (2026-09-23) — `palabras_programa` por streamer: marca de un programa de terceros en el
  TÍTULO DEL STREAM → descarta todo ese stream con motivo `programa_terceros`. Para que ande en Kick
  se trae el título del stream, que el clip no incluye (`/videos` del canal). Cargado en lacobraaa
  con "412" y "ANALIZAMOS": medido, saca 55 de sus 100 clips de la semana. Los comandos de Telegram
  pasan a aceptarse solo de `TELEGRAM_ALLOWED_USERS` (por usuario, no por chat: en un grupo cualquier
  miembro podría mandar /reclamo); sin la variable no se obedece nada. 136 tests OK.
- v0.11.0 (2026-09-23) — Layout `fit_blur` (16:9 entero sobre fondo borroso) en lugar del recorte
  central, que sacó dos Shorts mal: un panel de La Cobra donde el crop agarró la pared del medio y
  cortó a los dos que hablaban, y un Minecraft de Vegetta sin cámara donde cortó el chat, el
  minimapa y la hotbar. Reglas nuevas: `caras_estables` (busca varias caras, no una),
  `camara.margen_borde` 0,15 y chequeo de caras cortadas DESPUÉS del render con re-render
  automático. Los dos clips rehechos: los dos daban 0 caras estables (presencia 35 % y 5 %, bajo el
  umbral de 40 %), así que con la regla vieja caían en el recorte central. 133 tests OK.
- v0.10.0 (2026-09-22) — Primera entrega REAL: 3 Shorts por Telegram (1 del Dedsafío con ×3
  duplicados + 2 de catálogo). Grupo `argentinos` (8 de Kick) y mezcla 2 argentinos + 1 evento con
  fallback a catálogo. Las palabras de fútbol pasan a aplicarse solo a streamers con
  `detectar_marcador` (medido: 6 de 12 descartes del evento eran falsos positivos de "final").
  Arreglados dos bugs de orden: Twitch pisaba los candidatos de Kick, y el filtro del evento corría
  después del corte al top N. 126 tests OK.

---

## 10. DÓNDE ESTAMOS (leer primero en una sesión nueva)

**Snapshot del 2026-11-14 (noche).** El bot corre solo en la Raspberry con DOS canales activos:
**Pequeña Historia** (3 videos por día: 1 de tecnología solo en YouTube + 2 de Latinoamérica en YouTube y
Facebook) y **Así Nació** (canal de marcas animadas, 1 por día, prendido desde el 15/11). **Rots está
APAGADO.** La escucha de Telegram (24/7) arma todo; los timers de 05:00 y 06:00 quedan de respaldo.
Todo lo de Pequeña Historia y Así Nació va al **privado de Santi** (`8668060171`); el grupo "Rots
clips" queda sin uso mientras Rots siga apagado.

### Horarios (hora AR)

| hora | qué | dónde |
|---|---|---|
| ~~01:30~~ / ~~03:30~~ | "pegó" y la corrida de Rots — APAGADOS (`publicacion.rots: false`) | `_pego_tick`, `_madrugada_tick` |
| 04:00 | propuesta de tecnología (puntaje ≥ 7,5) | `_madrugada_tick` → `efemeride_del_dia` |
| después (desde 04:00) | 2 propuestas de Latinoamérica (puntaje ≥ 8, sin repetir país ni artículo) | `_fb_tick` |
| 05:30 | tope de "todo en Telegram" (`LISTO_DESDE`) | |
| 05:00 / 06:00 | timers de respaldo (no hacen nada si ya se hizo) | systemd |
| **07:00** | **Así Nació: arma los 2 videos del día** de a uno (nunca 03:45-06:00), los programa y los manda al privado con ❌ Cancelar; si uno falla, reintento en 1 h hasta las 22:00 | `_animacion_tick` |
| 08:30 del país (11:00 AR sin país) | Latinoamérica en Facebook (≥ 4 h entre las dos) | `hora_historia_fb` |
| desde 09:00 | medición de Pequeña Historia + análisis pedido de un Short + propuesta de mezcla | `_medicion_ph_tick` → `_analisis_y_mezcla` |
| 11:00 / 20:00 | Pequeña Historia en YouTube, SOLO tecnología desde el 23/11 (2 por día; el segundo, de la reserva) | `efemerides.horas_youtube`, `_tec_del_dia_tick` |
| 06:30-22:00 | reposición de la reserva de tecnología (de a uno, hasta 3) | `_reserva_tec_tick` |
| lunes 10:15 | qué temas rinden (tecnología en YouTube, Latinoamérica en Facebook) | `_temas_semana_tick` |
| **13:00 / 20:00** | **Así Nació se publica** en YouTube (@asinacio.oficial) y en su página de Facebook | `animacion.horas_publicacion` |
| lunes 08:00 | lista de fechas de la semana a Santi | `_calendario_tick` |
| al terminar el día pedido | costo real de Claude a Santi | `_costo_claude_tick` |

### Qué está prendido (settings.yaml)

| | |
|---|---|
| Rots | **APAGADO desde 2026-11-14** (`publicacion.rots: false`; código y canal intactos; /buscar a mano sigue). Al prenderlo vuelve con `render.edicion_rots`, `publicacion.subir_solo`, `textos.motor: claude`, etc. |
| Pequeña Historia | 3 por día: `efemerides.tema: tecnologia` + `corto` (20-30 s, solo YouTube) y `historias_fb.por_dia: 2` (30-40 s, YouTube + Facebook); `imagen_frase`, `formato_corto`, `videos`; gancho primero, intriga en la 2.ª, año/lugar en la 3.ª-4.ª, revisión del final; **escenas ilustrativas también en las frases centrales** (`ESCENAS_EN_CENTRALES`); humor suave cuando se puede; mapa sincronizado con la voz (solo con `estilo_nuevo`); `efemerides.chat` / `historias_fb.chat` = privado de Santi |
| Así Nació | `animacion.activo / subir / facebook / reglas_v3: true`, `uso_manos: true` (desde el 17/11: uso con las manos, inspiración, contar billetes, caja, apretón, firma), `hora: 07:00`, `horas_publicacion: [13:00, 20:00]` (2 por día, marcas distintas), `max_tokens: 32000`, `reintentos_guion: 8`, `candidatos: 14`, motor actual (SVG → cairosvg); reglas permanentes de v0.96.0 a v0.98.0 (acción, gancho en cadena, Tito con pausa en gris, viaje en el tiempo en sepia, composición verificada, revisión visual, ritmo 32-38 s con voz ×1,065, subtítulos arriba) |
| Claude | Sonnet elige, puntúa, escribe guiones, revisa el final, elige fotos y revisa los cuadros de Así Nació; Haiku clasifica y chequea; Gemini SOLO voces y audio (y de respaldo) |
| subidas | YouTube: Pequeña Historia, Así Nació (y Rots, apagado); Facebook: página de Pequeña Historia y página de Así Nació. La app de Meta (clips-bot) estaba en modo desarrollo en octubre: si sigue así, el público no ve los Reels (pasarla a Live es de Santi) |
| apagado | Rots; `efemerides.sin_aprobar` (espera el OK de Santi; `estilo_nuevo` PRENDIDO el 15/11); ElevenLabs (sin clave ni voz); multi-POV; prueba manual vs API; portadas con IA |

### Estado real de la Pi (verificado el 2026-11-15, 03:20)

| | |
|---|---|
| commit | v1.05.0, desplegado (estilo visual nuevo de Así Nació, primer filtro de fotos con Haiku, informe de costo por origen, `estilo_nuevo` de Pequeña Historia prendido). Así Nació con 1 proceso de dibujo. Subtítulos virales de Así Nació PRENDIDOS (`animacion.subtitulos_virales: true`, aprobados el 14/11). |
| ventilador | Fan SHIM (GPIO 18) controlado por `ventilador.service` de usuario (55/48 °C, siempre en renders); x264 con 3 hilos; pausa para enfriar entre renders (65 °C, máx. 10 min) |
| timers y escucha | `clips-bot.timer`, `clips-bot-efemeride.timer`, `clips-bot-telegram` activos |
| Así Nació | `animacion_dia` = 2026-11-14 (marcado a mano): el primer video real sale el **15/11** (arma 07:00, publica 19:00) |
| pedidos pendientes en `bot_estado` | `analisis_video_pedido` = `UH4XoZ0rMuE` (el Short de Intel: el análisis le llega a Santi apenas Analytics tenga sus datos); `mezcla_propuesta` sin setear (se manda una vez cuando tecnología ≥ 1,3× Latinoamérica con ≥ 4 y ≥ 6 videos de 3 días) |
| claves (.env de compu y Pi) | `ANTHROPIC_API_KEY` (solo Pi); `FACEBOOK_PAGE_TOKEN` (Pequeña Historia, huella ab2e94551f81); `ASINACIO_FACEBOOK_PAGE_ID` / `_TOKEN` (página «Asinacio.oficial» `1533484406504022`, huella 16d7443e4bb0, no vence); `GEMINI_API_KEY_2`; `FB_APP_ID` / `FB_APP_SECRET`; `ELEVENLABS_API_KEY` (huella 47fff12ec9c8, compu y Pi) |
| tokens de YouTube | `config/youtube_token_{rots,pequena_historia,animacion}.json` (compu y Pi, fuera de git). Así Nació = canal «Asinacio.oficial» `UCPUKDAf5NJbdINUC2Rka69A` |
| Remotion | Node 24 del sistema en la Pi; el prototipo se probó en `~/remotion_prueba` (fuera de `~/clips`); en el repo, `remotion/` (sin `node_modules`) y `clips_bot/animacion_remotion/` |
| chats | Santi (`8668060171`, `DUENO`): todo; grupo "Rots clips" (`-5453399767`): sin uso con Rots apagado |
| música | `musica/` fuera de git |

### Lo que se hizo en la última sesión (2026-11-14, v0.94.0 a v1.04.0)

- **Rots apagado** y Pequeña Historia al privado; **por qué el 14/11 no salió nada a la madrugada**
  (tecnología 7,25 < 7,5; La Pola y Túpac Katari frenadas por el control del 70 %) → escenas
  ilustrativas en las frases centrales; los de ese día se armaron a mano.
- **Pequeña Historia:** gancho escrito con salto de línea (desde el 12/11 salía cortado, ya arreglado
  en producción), pool sin fotos duplicadas (Archivo:/File:), montaje del gancho, mapa con zoom que llega
  cuando se dice el lugar, gancho y subtítulos animados (todo eso con `estilo_nuevo`, APAGADO),
  publicación sin aprobar (`sin_aprobar`, APAGADA), ElevenLabs preparado, humor suave.
- **Investigación de nicho** (`docs/nicho-animacion/informe.md`) → Santi eligió **origen de marcas** →
  canal **Así Nació** con el **Abuelo Tito** de locutor: catálogo de 457 marcas, rotación, guion con
  Claude, reglas permanentes, revisión visual, conectado a YouTube y a Facebook, **prendido**.
- **Remotion:** skill oficial instalada (`.claude/skills/remotion-best-practices`, fuera de git),
  licencia gratis para una persona, prototipo con dibujos con volumen y perspectiva (Nerf: 8-10 min de
  render en la Pi contra 5 del motor actual). **NO en producción.**
- **Subtítulos virales de Así Nació** (aprobados por Santi y PRENDIDOS, v1.03.0): 1-3 palabras, Montserrat
  Black (OFL, `assets/fuentes/`) dibujada como trazos, pop sincronizado, claves en amarillo/rojo con
  temblor, emojis dibujados (💥💰😱🤣) cada 4,5 s como mínimo; en los dos motores.
- **Imágenes de los canales:** perfil de Tito con fondo celeste (elegido); banners de YouTube rehechos
  con todo dentro de 1300x350 (Pequeña Historia, 2 opciones; Así Nació como escena del taller, 2
  opciones + portadas de Facebook, sin el portal: `output/canales/`).
- **Intel:** el Short "El procesador barato de Intel que salió mal" (13/11) hizo 3.220 vistas (los
  demás ~1.200). Analytics todavía no tenía sus datos (llega solo). Lo que se ve: marca conocida +
  "salió mal" (único con ese ángulo), primera imagen un primer plano del producto, 29 s.
- **Calor de la Pi** (v1.02.0): nunca faltó corriente, sí frenadas por calor. Control del Fan SHIM
  (`ventilador.service`, 55/48 °C, siempre prendido en renders), pausa para enfriar entre renders
  (65 °C, máx. 10 min) y x264 con 3 hilos: ffmpeg frena 17 % del tiempo (antes 35 %), pero el pico
  sigue en ~86 °C. Santi va a poner disipadores: medir de nuevo cuando avise.
- **Así Nació con 1 proceso de dibujo** (v1.04.0): 134 s contra 157 con 2 en el demo de 35 s.

### Decisiones de Santi vigentes (además de §1)

- Nada de imágenes generadas con IA en ningún video; una foto mala se reemplaza por otra real
  (Commons/Wikipedia o stock con licencia), nunca por IA. Nada pago activado sin que lo diga.
- Antes de programar algo de algoritmo o formato: **diseño corto primero y esperar su OK**; si hace
  falta volver a autorizar YouTube/Meta (permisos nuevos), avisar ANTES.
- No tocar el turno de render compartido salvo que lo pida.
- Mensajes míos por Telegram empiezan con "🔧 Claude Code:". Todo a su privado.
- Así Nació: dibujos propios, sin logos reales; Tito es el locutor fijo y la cara del canal.
- **Pruebas del motor de Así Nació (Santi, 2026-11-16, para ahorrar):** nunca un video entero para probar: solo las
  escenas que cambiaron, con un guion y una voz ya hechos (sin guion nuevo de Claude ni voz de ElevenLabs), y a Santi una
  hoja de cuadros (6-10 por escena) o un clip corto de esas escenas. El video completo, solo aprobado y antes de prenderlo
  para todos. (Cada Tupper completo costaba ~US$ 1,3 de Claude, ~450 créditos y 8-9 min de render.)

### Esperando respuesta de Santi (NO programar sin su OK)

- **Latinoamérica con el tema ampliado (15/11):** sigue en 1,21 de 7+ por día. Proponer: un criterio de
  "sorpresa" en lugar de "peligro" para las curiosidades (cambia el puntaje: decisión de Santi).
- **Latinoamérica (conteo del 15/11):** aun con las fuentes nuevas, 6 de 14 días no tienen ninguna historia de
  7 o más. Opciones para proponerle: bajar el piso a 6,5 en esos días, sumar la página del día en inglés, o
  dejar que Haiku pase más candidatas a Sonnet (hoy marca "humana" muy pocas: 7-35 de ~100).
- **Presupuesto:** con todo lo de hoy, la estimación es ~US$ 2,5 por día (≈ US$ 75 por mes), cerca del tope de
  80. El aviso llega al 75 % (US$ 60) en el mes.

- **Así Nació, estilo visual nuevo (15/11):** el render en la Pi pasó de 134 a 512 s por video (pico 84 °C,
  igual que antes). Si Santi lo quiere más rápido: sacar los degradés de los personajes (−~120 ms por
  cuadro) o el contorno doble (−~65 ms). Medir el costo real de las fotos con el informe diario (el
  primero llega el 16/11 a las 09:00) y confirmar la estimación de ahorro.

- **Calor:** Santi va a comprar **disipadores para el chip** (debajo del Fan SHIM). **Cuando avise que los
  puso, medir de nuevo** con el mismo render de prueba del 14/11 (antes: ffmpeg pico 86,2 °C, 1.434 MHz de
  media, frenada 17 %; animación pico 86,2 °C, frenada 33 %) y comparar. Otra opción si no alcanza:
  `arm_boost=0` (1,5 GHz; necesita su sudo y reiniciar).
- **Lo Encontré no respeta la pausa para enfriar entre renders** (usa su propio `src/bot/turno.py`, que
  lee y escribe el mismo turno pero sin mirar la temperatura ni `fin_trabajo_pesado`). Pendiente para
  **arreglarlo en el chat de bot-videos** (este repo no lo toca): que antes de tomar el turno espere si
  la CPU está arriba de 65 °C en los 10 min que siguen al último render, igual que `db.tomar_turno` de
  clips, y que al soltarlo anote `fin_trabajo_pesado`.
- **Remotion sí o no** para Así Nació. Si sí: conectar `marcas.armar_video` a Remotion detrás de un
  interruptor (motor actual de respaldo), revisión visual sobre sus cuadros, `npm ci` en
  `~/clips/remotion`, render de 10-12 min (cabe desde las 07:00), redibujar `juego_mesa`,
  `hamburguesa`, `auto`, `consola` y el fondo del globo en el estilo nuevo.
- **Banner de Así Nació:** opción 1 o 2 del taller sin portal (`output/canales/banners_taller/asinacio_v3_*`).
  **Banner y perfil de Pequeña Historia:** opción 1 o 2 (`output/canales/banners_yt/`, `output/canales/ph/`).
- **Pequeña Historia:** `efemerides.sin_aprobar` (sigue apagado; `estilo_nuevo` lo prendió Santi el 15/11).
- **Mezcla 2 tecnología + 1 Latinoamérica en YouTube:** la propuesta llega sola si los datos lo
  justifican; cambiarla recién con su OK.
- **Retención y alcance** (`docs/diseno-retencion-alcance.md`): Instagram (volver a autorizar con el
  permiso de Instagram: avisar antes), TikTok (app + auditoría), final en loop (cambia la regla fija 3
  de audio), música con tensión y efectos, links de búsqueda de grupos de Facebook.
- **App de Meta en modo Live** (lo hace Santi, docs/facebook-asi-nacio.md): sin eso el público puede no
  ver los Reels de las dos páginas.
- **Fuentes web:** Santi eligió la opción C (todo Haiku) el 16/11 y empezar por Latinoamérica (v1.17.0, en
  prueba desde el 17/11, ver §1). Si la prueba queda andando: lo mismo para tecnología y Así Nació (sitios de
  las marcas y empresas), con su propio tope.
- **Voz de Pequeña Historia** (v0.88.0): muestras de Fenrir más calmo, Achird, Sadaltager y Charon;
  falta que elija (`efemerides.tts_modelo: gemini-2.5-flash-preview-tts`, `tts_instruccion`, `tts_voz`).
- **Descripciones de los canales** (propuestas el 2026-11-12): las cambia Santi.
- **Fechas con datos que llegan solos:** el análisis de Intel (apenas Analytics lo tenga); **24/11** la
  comparación de Facebook; **26/11** `medicion_ph` (los nuevos contra los 10 anteriores, tecnología
  contra Latinoamérica). Con esos datos: horarios de Facebook y cortes de puntaje (8 y 7,5).
- **Diseño del algoritmo** (2026-11-05: `/analisis`, ponderación 40/40/20, `/stats_fb`), **foto del
  HTC Dream** en el video de Android, **más fuentes de historias** de Latinoamérica (días sin historia
  buena): siguen sin respuesta.
- **Cuota de voces:** Lo Encontré comparte la GEMINI_API_KEY principal (tope ~10 por día, aviso en 8);
  Pequeña Historia usa 3 por día y Así Nació 1 más. El repo bot-videos no se toca.

### Problemas vistos y no arreglados

- **`thumbnails.set` da 403 en Pequeña Historia** (06/11, la de Arcane): "doesn't have permissions to
  upload and set custom video thumbnails". Probablemente el canal no está verificado (YouTube pide
  verificar con el teléfono para miniaturas propias). La subida sigue igual, sin portada. Lo
  resuelve Santi en youtube.com/verify.
- **El relleno de fotos (regla k) repite una foto sin mirar si va con la frase nueva**: así salieron
  los billetes de rupias en "inversores". Además `de_epoca`/`seguro`/`contradice` solo sacan la
  PRIMERA foto del ranking de cada frase. Arreglo posible (solo propuesta, la regla es de Santi):
  que el relleno use solo fotos que Gemini marcó como válidas para ESA frase, y si no hay, tarjeta.

### Pendiente de antes, sin fecha

- Probar `/narrar` y `/serie` con un video real de proceso.
- **Modo recortar**: pedido el 2026-09-24 y nunca especificado: preguntar qué es.
- Listas de streamers por persona: postergado por Santi el 2026-09-27.
- `gameplay/` en la Pi sigue vacía (el botón 🎮 no aparece hasta que haya videos).
- Capa `librosa` del filtro de música (§4); Kick en el catálogo; links de TikTok/IG/FB → `posts`.
- Decidir si se paga Gemini (docs/costo-gemini.md).
- (Otro repo, bot-videos) el audio con la voz original de la persona en ✂️ Recortar y 🔁 Rearmar:
  Santi lo pidió y lo cortó antes de empezar; no hacerlo salvo que lo vuelva a pedir.

### Trampas que ya nos mordieron

- **La Pi hace `git pull` desde GitHub: un commit sin `git push` no existe para ella.** El
  2026-09-27 hubo 7 commits sin pushear; Santi hizo pull y reinició, la Pi siguió en `d226073`, y
  /narrar le contestó "casi todo silencio" con un filtro que ya estaba sacado. Después de commitear
  algo que tiene que llegar a la Pi: `git push`, y verificar con
  `ssh santi@192.168.50.12 'cd ~/clips && git log --oneline -1'` (en la LAN; por Tailscale,
  100.67.132.95). Nada pesado andando antes de reiniciar la escucha: `db.hay_trabajo_pesado`.

- **Nunca escribas `\r` ni `\n` en un archivo de shell desde un script intermedio.** `alerta.sh`
  terminó con DOS retornos de carro reales adentro: uno partía un comentario en dos y la segunda
  mitad se ejecutaba como comando, y el otro hacía que `tr` borrara también los saltos de línea del
  `.env`, que quedaba en una sola línea. La alerta estuvo rota un día entero por lo mismo que venía
  a arreglar. Verificá siempre con `p.read_bytes().count(b"\r") == 0` antes de commitear.
- **El `.gitattributes` fuerza LF** en `*.sh`, `*.service`, `*.timer` y el sudoers. Con CRLF, Linux
  falla con `bad interpreter: ^M` y systemd no parsea la unidad.
- **La escucha hay que reiniciarla después de cada deploy**, si no sigue con el código viejo:
  `sudo systemctl restart clips-bot-telegram` (ya no pide contraseña).
- **Si el servicio entra en crash-loop**, systemd pega contra el `StartLimitBurst` y NO vuelve a
  arrancar: `systemctl restart` contesta "Start request repeated too quickly" y hace falta
  `sudo systemctl reset-failed clips-bot-telegram` primero. La alerta ya trae ese comando.
- **La cuota de Gemini se agota casi todos los días** (~20 requests del free tier). El fallback a
  flash-lite funciona y se ve en el log constantemente. No gastar cuota en pruebas: para probar
  algo, usá los clips ya procesados de `output/ready/`, que ya tienen textos.
- **Los filtros nuevos no se aplican retroactivamente** a lo que ya está en `output/ready/`. Cuando
  se agrega un filtro hay que revisar a mano lo que quedó de antes (ya pasó dos veces).
- **Medir antes de decidir.** Todo lo que salió bien en este proyecto salió de medir sobre clips
  reales: el umbral de césped, el de caras en la zona del juego, la superposición léxica, el
  puntaje con y sin imagen. Todo lo que salió mal salió de suponer.
