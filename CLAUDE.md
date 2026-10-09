# Clips Bot — Project Context

**Snapshot:** 2026-10-09 | **Versión:** v0.63.2 | **Modo:** Fase 2: corriendo solo en la Pi (timer 05:00 + escucha de Telegram 24/7)

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
- **Videos largos: NO por ahora (decisión de Santi, 2026-09-28).** No quiere videos largos con voz
  de IA. Si más adelante se hacen, van con SU voz grabada, no con Gemini TTS ni Piper.
- **Sin música agregada en los clips.** Cualquier música es riesgo de Content ID. Si el clip trae
  música de fondo del stream, se descarta (detección: ver §4). EXCEPCIÓN pedida por Santi
  (2026-09-27): Pequeña Historia lleva música de fondo con licencia verificada (docs/musica.md).
- **Volumen: 3 uploads/día** de clips + 1 de Pequeña Historia. Cuota (doc oficial, revisada
  2026-09-28): `videos.insert` cuesta 1 unidad de un balde aparte, *Video Uploads*, con 100 por día;
  ya no son 1600 de las 10.000 unidades generales. La cuota no es un límite para este volumen.
- **Publicación: TODO MANUAL hasta la auditoría de YouTube (decisión 2026-09-21, revisada).**
  CONFIRMADO: los videos subidos por API desde un proyecto sin auditar quedan bloqueados como
  privados de forma permanente (no se pueden publicar desde Studio ni apelar). Por eso, hasta
  aprobar la auditoría, el bot NO sube nada: entrega por Telegram el mp4 + título + descripción +
  hashtags y Santi sube a mano a YouTube Shorts, TikTok, Instagram Reels y Facebook Reels
  (~5–7 min/día). Esto también evita la auditoría de TikTok y la revisión de Meta.
  Con la auditoría aprobada se activa YouTube automático: `videos.insert` privado + `publishAt`
  escalonado (ej. 13:00/18:00/21:30 AR). Preparado desde v0.28.1 (apagado): ver
  docs/auditoria-youtube.md. TikTok/IG/FB siguen manuales.
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
4. Transmisión deportiva (streamers con `detectar_marcador`) → descarta con DOS señales: marcador de
   TV en una esquina de arriba, o fracción de verde-césped alta en ≥ 2 de 12 frames (una cancha llena
   la pantalla). Después, filtros de audio: casi todo silencio, o muy pocas palabras por segundo.
4b. **Datos en pantalla (OCR, sin LLM).** tesseract sobre 8 frames; descarta con motivo
   `datos_en_pantalla` si aparece un mail, una palabra de pago (checkout, subtotal, CVV…) o de
   dirección (shipping, código postal…). Los NÚMEROS (teléfono, tarjeta) solo cuentan si en el mismo
   frame hay una palabra de contexto (tel, contacto, DNI): sin eso daba 3 falsos positivos y ningún
   acierto sobre 26 clips. Si tesseract no está instalado la capa se saltea y la corrida sigue.
5. Layout, tres opciones (el recorte central "a ver qué sale" se eliminó el 2026-09-23):
   - **split** — facecam clara (una cara chica y estable): cámara arriba 40 % (1080x762) + línea
     negra de 6 px + juego abajo 60 % (1080x1152).
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
6. Whisper → SRT → quemar subtítulos (fuente 64, bloque centrado al 80 % del alto, 2 líneas máx).
   Si el streamer tiene `subtitulos_propios: true` (ya trae subtítulos en vivo), no se queman; el
   SRT se guarda igual (título + pista de subtítulos en YouTube).
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
clips_bot/envivo.py      modo en vivo (§3b): quién está al aire, momentos por creadores distintos,
                         alertas en la DB (no repetir, tope, vencer) y el resumen de tiempos
tests/                   549 tests sin red ni video (conftest.py: nada sale a YouTube) (test_reglas_fijas.py: las 3 reglas de §1)
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

**Snapshot del 2026-09-28 (madrugada).** El bot corre solo en la Raspberry: timer a las 05:00 AR
(clips + la propuesta de Pequeña Historia) y la escucha de Telegram 24/7 (comandos y modo en vivo).

### Estado real de la Pi (verificado el 2026-09-28 ~00:00)

| | |
|---|---|
| commit | el último de `main` (v0.28.2, `4293b2a`); 391 tests OK en la Pi; escucha reiniciada |
| `clips-bot.timer` | activo, próxima 05:00 AR (clips y después la efeméride) |
| `clips-bot-telegram` | activo; modo en vivo PRENDIDO por Santi en el grupo el 27/09 |
| carpetas | Argentinos y Famosos (en vivo sí, diarios sí), Catálogo (en vivo no, diarios sí), Dedsafío (en vivo no, diarios no): el modo en vivo vigila 9 de 64 |
| música de Pequeña Historia | 29 temas en `musica/` (9 de la Biblioteca de YouTube de Santi, 10 Kevin MacLeod, 10 Openverse), 157 MB, fuera de git |
| subida a YouTube | APAGADA (`youtube_upload_enabled: false`); Rots conectado (token en la Pi, app de OAuth en producción: no vence; métricas andando desde el 2026-09-29); Pequeña Historia sin conectar |
| sudoers | instalado (`/etc/sudoers.d/clips-bot`) |
| destinos de la entrega diaria (y de la propuesta de efeméride) | el grupo **Rots clips** (`-5453399767`) |
| chats conocidos | Rots clips (grupo), Santiago Fittipaldi (`8668060171`) y Tommy Bildo (privados) |
| `cantidad_diaria` | 3 |
| multi-POV | APAGADO desde el 2026-09-28 (`multipov.activo: false`) |

### Hecho y andando en producción

- Pipeline completo de clips (§3) con todos los filtros: co-stream, programas de terceros, deportes,
  datos en pantalla (OCR), tono sensible, calidad con puntaje, duración, idioma, música por audio.
- Layout `split` / `fullcam` / `fit_blur` con chequeo post-render, y `layout_forzado` por streamer.
- Entrega por Telegram con 👍/👎 por persona, relleno marcado y aviso de "0 clips hoy".
- Comandos: `/ya`, `/buscar`, `/streamers` (carpetas con interruptores), `/agregar` (pregunta la
  carpeta), `/quitar`, `/cantidad`, `/reclamo`, `/destinos`, `/aca`, `/ayuda`, `/editar`,
  `/narrar`, `/serie`, `/efemeride`, `/envivo`, `/subidas`.
- Modo en vivo con umbral relativo (§3b), solo sobre carpetas con 🔴 En vivo.
- Pequeña Historia (§3c): propuesta diaria a las 05:00 con aprobación ✅/✏️/🔁, voz de Gemini TTS
  (Laomedeia) con respaldo de Piper, música con ducking elegida por tono, créditos automáticos.
- Turno de trabajo pesado + cola: nunca hay dos clips procesándose a la vez, y un comando que
  explota avisa sin tumbar el servicio.
- Deploy: systemd, logrotate, alerta por Telegram con `OnFailure`, sudoers acotado.

### A medias (el código está, la prueba real no)

- **La efeméride automática de las 05:00** nunca corrió sola todavía (la primera es la del 28/09).
- **La voz de Gemini con el recorte de lo leído antes del guion**: el recorte está probado con
  tests; la voz sin instrucción se probó en la Pi con una frase, no con un video entero.
- **La subida a YouTube**: Rots ya está conectado y las métricas se leen, pero nunca se subió nada
  (apagada hasta la auditoría). Pequeña Historia sin `youtube-auth` todavía.
- **`/narrar` y `/serie` con videos reales de proceso** (hasta ahora, sintéticos y Gemini falso).
- **La mezcla nueva (2 argentinos + 1 Auron, votos) nunca corrió de verdad**: la primera es la
  del 05:00 del 2026-09-29.

### Pendiente, en orden

1. **Mirar la primera efeméride automática.** La de las 05:00 del 2026-09-28 falló (429 de
   Wikimedia, arreglado en v0.28.3 y corrida a mano ese día). Falta ver: que ✅ arme el video con
   la voz de Gemini (¿arranca limpio, sin leer nada antes?) y con música, y que no tape la voz; y
   que un reintento de las 07:00/10:00 ande solo cuando pase de verdad.
2. **Modo en vivo:** ahora vigila solo Argentinos (8 canales). Las 4,7 alertas/día simuladas eran
   con los 63: van a ser menos. Mirar `/envivo` en unos días.
3. **Probar `/narrar` y `/serie` con un video real de proceso** (pasos, etapas, aviso de música,
   `sin audio`, tiempos en la Pi).
4. **Auditoría de YouTube** (docs/auditoria-youtube.md): proyecto, credencial, conectar los dos
   canales, formulario. Recién con la aprobación, `youtube_upload_enabled: true`.
5. **Decidir si se paga Gemini** (≈ US$4/mes hasta dic. 2026; docs/costo-gemini.md).
6. **Modo recortar**: pedido el 2026-09-24 y nunca especificado: preguntar qué es.
7. **Revisión del corte de calidad (lo del "9 de 10").** El corte está en `textos.puntaje_min: 5`,
   puesto a mano. El trato es elegirlo con datos: el puntaje desde el cual Santi vota más 👍 que 👎
   (`db.votos_por_puntaje`). Arrancó el 2026-09-24, así que a partir del **2026-10-08** hay que
   mirarlo. Con 2 votos todavía no alcanza para nada. Los mismos votos ahora también pesan en la
   selección por streamer: cuantos más vote Santi, mejor elige.
8. **Métricas de YouTube (§4b) → vistas en el peso por streamer.** El lugar ya está
   (`seleccion.factores_votos`); falta leer las métricas.
9. **Listas de streamers por persona.** Pedido y después postergado explícitamente por Santi el
   2026-09-27 ("las listas por persona no las hagas por ahora"). El diseño pensado: una corrida de
   candidatos compartida, selección POR destino, y procesado deduplicado; el grupo usa la unión.

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
