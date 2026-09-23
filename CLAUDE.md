# Clips Bot — Project Context

**Snapshot:** 2026-09-23 | **Versión:** v0.15.0 | **Modo:** Fase 1 andando: primera entrega real hecha (3 Shorts por Telegram)

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
- **Sin música agregada.** Cualquier música es riesgo de Content ID. Si el clip trae música de
  fondo del stream, se descarta (detección: ver §4).
- **Volumen: 3 uploads/día** (3 × 1600 = 4800 unidades de las 10.000 diarias de cuota).
- **Publicación: TODO MANUAL hasta la auditoría de YouTube (decisión 2026-09-21, revisada).**
  CONFIRMADO: los videos subidos por API desde un proyecto sin auditar quedan bloqueados como
  privados de forma permanente (no se pueden publicar desde Studio ni apelar). Por eso, hasta
  aprobar la auditoría, el bot NO sube nada: entrega por Telegram el mp4 + título + descripción +
  hashtags y Santi sube a mano a YouTube Shorts, TikTok, Instagram Reels y Facebook Reels
  (~5–7 min/día). Esto también evita la auditoría de TikTok y la revisión de Meta.
  Con la auditoría aprobada se activa YouTube automático: `videos.insert` privado + `publishAt`
  escalonado (ej. 13:00/18:00/21:30 AR); cuota confirmada 1600/upload → 3 × 1600 = 4800 de las
  10.000 diarias. TikTok/IG/FB siguen manuales.
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
| Scheduler | systemd timer (1 corrida/día, ej. 05:00 AR) | + watchdog simple |

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
     3 personas clipearon compite con uno de 500 vistas sin duplicados. `min_vistas` 0, sin umbral.
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
   motivo `costream`. Las palabras de fútbol (gol, Boca, River, partido, Mundial…) son por Davoo.
   **Programas de terceros** (`palabras_programa` por streamer, motivo `programa_terceros`): marca
   de un programa con formato propio en el TÍTULO DEL STREAM, no en el del clip. Si dispara, queda
   afuera TODO ese stream. En Kick el clip no trae el título del stream: sale de
   `/api/v2/channels/{slug}/videos` (una llamada por canal, `{livestream_id: session_title}`); si
   esa llamada falla, los clips quedan sin título de stream y la corrida sigue.
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
7b. **Multi-POV (grupo evento).** Si 3+ canales clipearon el mismo momento y se procesaron 3, se
   arma ADEMÁS un Short secuencial: hasta 3 ángulos, cada uno ±4 s alrededor de su pico de reacción
   (volumen RMS + densidad de palabras del .srt), cartel con el nombre del streamer arriba durante
   su tramo, orden de menos a más visto (el final es el ángulo más fuerte) y crédito a todos en la
   descripción. Sin pantalla dividida. Se parte de los mp4 verticales ya renderizados.
   **Cada ángulo tiene que MOSTRAR algo en su tramo**: se cuenta cuántos frames del tramo son un
   rectángulo casi negro (`multipov.frames_vacios_max`, más de un tercio = no sirve). Si un ángulo
   no pasa: (1) se rehace con fit_blur, que muestra el 16:9 entero; (2) si tampoco alcanza, se
   reemplaza por otro canal del mismo momento (se procesan hasta 2 más); (3) si no se llega a
   `min_angulos`, no se arma el multi-POV.
8. Elegir con cupos por GRUPO (`seleccion.mezcla`, default 1 kick_reciente + 1 evento + 1 catálogo).
   Cada grupo compite solo en su cupo; lo que un grupo no llena pasa al grupo `catalogo`, y si a ese
   le sobra vuelve a repartirse. Tope 2 por streamer entre todos. Empate en el corte → Gemini
   (`empate_pct` por fuente: 3 % recientes, porque el score es logarítmico; 10 % catálogo).
9. YouTube (SOLO con la auditoría aprobada; flag `youtube_upload_enabled`, default false):
   `videos.insert` privado con `publishAt` en el slot correspondiente. Guardar `video_id` en
   `clips.db` (tabla `posts`). Reintento con backoff; si falla 3 veces, alerta y se manda igual.
10. Telegram: por cada clip, el mp4 + un mensaje con `Título:` / `Descripción:` / `Hashtags:` /
    `Crédito:` en bloques copiables, id interno, horario sugerido, el recordatorio fijo
    **"Subir en PRIVADO → esperar Chequeos de copyright en Studio → si sale limpio, publicar"** y el
    `/reclamo <id>` listo para copiar. Santi sube a mano y responde con los links; el bot los asocia
    al clip en `posts` (esa 2ª mitad está pendiente).

### 4b. Módulo de métricas (feedback loop)
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
- [ ] Cuota de Gemini: si el límite que se agotó el 2026-09-22 es diario y de cuánto, o si conviene
      una key paga.
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
- Costo real: Gemini (~$0), API YouTube ($0), electricidad de la Pi. Debe ser ≈ $0.

---

## 8. ESTADO DEL CÓDIGO

Python 3.13, deps en `requirements.txt`. Además, ffmpeg con libass (Windows: `winget install
Gyan.FFmpeg`, ya instalado 9.0.2; Pi: `apt install ffmpeg`). Si la consola no ve ffmpeg en el PATH,
el código lo busca en la instalación de winget o en `FFMPEG_DIR`.

```
config/settings.yaml     candidatos, evento, kick, catalogo, render, camara, subtitulos, filtro_audio,
                         marcador, pantalla, textos, seleccion, publicacion, youtube_upload_enabled
config/streamers.yaml    login, plataforma, fuentes, grupo, permiso (cita/fuente o experimento),
                         subtitulos_propios, detectar_marcador, palabras_programa, layout_forzado
                         + sección evento_dedsafio
.env                     TWITCH_*, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                         TELEGRAM_ALLOWED_USERS (ids que pueden mandar comandos; vacío = ninguno)
clips_bot/config.py      carga YAML + .env; Streamer.permitido = cita o experimento
clips_bot/twitch.py      Helix: token, /users, /search/channels, /clips (paginado o página con
                         cursor), /games, /videos (título del stream)
clips_bot/kick.py        API interna de Kick: clips por canal (sort=view&time=week), a_clip() los aplana,
                         get_session_titles() = títulos de stream por livestream_id (/videos)
clips_bot/candidates.py  pasos 1–2 de las 3 fuentes: filtros, es_costream, agrupar_momentos,
                         agrupar_evento/consolidar_evento, cursor del catálogo
clips_bot/download.py    paso 3: yt-dlp (Twitch y Kick) → output/raw/
clips_bot/media.py       ffmpeg/ffprobe: ubicar binario, probe, fracción de silencio, miniatura
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
deploy/                  systemd (service + timer 05:00 AR + alerta por Telegram), logrotate,
                         instalar.sh y README con el orden del deploy en la Pi
clips_bot/seleccion.py   paso 8: score por fuente, cupos por grupo con fallback, desempate Gemini
clips_bot/telegram.py    paso 10: sendVideo (width/height/duration + miniatura), mensaje con bloques
                         copiables + recordatorio, getUpdates, comandos con user_id y
                         usuarios_permitidos (TELEGRAM_ALLOWED_USERS)
clips_bot/process.py     orquesta 3–7 por clip, tiempos por etapa, registra estado en la DB
clips_bot/db.py          SQLite data/clips.db: clips, posts, catalogo_cursor, streamer_estado
                         (exclusiones), bot_estado (offset de Telegram)
clips_bot/__main__.py    CLI
tests/                   120 tests sin red ni video
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
- `atender-telegram` — procesa `/reclamo <id del clip>`: marca el reclamo, excluye al streamer y
  responde. `diario` lo corre al principio. El offset de getUpdates queda en la DB.
- `telegram-chat-id` — lista los chats de getUpdates y los ids de usuario (TELEGRAM_ALLOWED_USERS).
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

Streamers cargados (2026-09-22). Mezcla diaria: **2 argentinos + 1 evento**, y el catálogo sin cupo
propio como fallback.
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
