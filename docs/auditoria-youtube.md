# Subida automática a YouTube: cómo prenderla

Guía para hacer una sola vez, sin saber programar. Son 4 partes:

1. Crear el proyecto en Google Cloud y la credencial (≈ 20 min).
2. Conectar los dos canales al bot (≈ 5 min).
3. Pedir la auditoría de YouTube (≈ 30 min de formulario, después esperar).
4. Prender la subida cuando aprueben (1 minuto).

> **Por qué hay que esperar la auditoría:** YouTube dice que *todos los videos subidos por la API
> desde un proyecto sin verificar quedan restringidos a privados*. Y en este bot tomamos esa
> restricción como permanente: un video subido así no se puede publicar después (§1 de
> CLAUDE.md). Por eso la subida está **apagada** (`youtube_upload_enabled: false`) hasta que
> aprueben. Antes de eso, si querés probar algo, que sea SOLO en un canal descartable.

---

## Parte 1 — Proyecto de Google Cloud y credencial

Todo con la cuenta de Google que maneja los dos canales (Rots y Pequeña Historia).

1. Entrá a **https://console.cloud.google.com**. Si es la primera vez, aceptá los términos.
2. Arriba a la izquierda, en el selector de proyectos → **Proyecto nuevo** → nombre `clips-bot`
   → **Crear**. Asegurate de que quede seleccionado arriba.
3. **Habilitar la API:** menú ☰ → *APIs y servicios* → *Biblioteca* → buscá **YouTube Data API
   v3** → **Habilitar**.
4. **Pantalla de consentimiento** (lo que ves cuando el bot te pide permiso): menú ☰ → *APIs y
   servicios* → *Pantalla de consentimiento de OAuth* (en algunas cuentas se llama *Google Auth
   Platform*).
   - Tipo de usuario: **Externo**.
   - Nombre de la app: `Clips Bot`. Correo de asistencia: el tuyo.
   - Permisos (scopes): agregá `.../auth/youtube.upload` y `.../auth/youtube`.
   - Usuarios de prueba: agregá tu propia cuenta de Google.
   - **Importante:** mientras la app esté en modo *Prueba* (Testing), Google hace vencer el permiso
     **cada 7 días** y habría que volver a conectar los canales todas las semanas. Cuando termines
     de conectar los canales (parte 2), volvé acá y apretá **Publicar app** (pasa a *En
     producción*). Como la usás solo vos, no hace falta la verificación de Google: al conectar vas
     a ver un aviso de "app no verificada" → *Configuración avanzada* → *Ir a Clips Bot*.
5. **La credencial:** menú ☰ → *APIs y servicios* → *Credenciales* → **Crear credenciales** →
   **ID de cliente de OAuth** → tipo **App de escritorio** → nombre `clips-bot` → **Crear** →
   **Descargar JSON**.
6. Renombrá ese archivo a **`client_secret.json`** y ponelo en la carpeta `config/` del bot, en la
   compu de Windows (`C:\Users\nquin\Downloads\code\bots\clips\config\`). **No va a GitHub**
   (el `.gitignore` ya lo excluye).
7. Anotá el **número de proyecto** (menú ☰ → *Información del proyecto*): lo pide el formulario de
   la parte 3.

## Parte 2 — Conectar los dos canales

En la compu de Windows (necesita navegador), en una consola dentro de la carpeta del bot:

```
python -m clips_bot youtube-auth rots
```

Se abre Google. Elegí tu cuenta y, **en la pantalla siguiente, el canal Rots** (no la cuenta
personal: si la cuenta tiene varios canales, Google pregunta cuál). Aceptá los permisos. La consola
dice `Listo: Rots (UC…)` y deja el archivo `config/youtube_token_rots.json`.

Lo mismo para el otro canal:

```
python -m clips_bot youtube-auth pequena_historia
```

Y copiá la credencial y los dos tokens a la Pi:

```
scp config/client_secret.json config/youtube_token_rots.json config/youtube_token_pequena_historia.json santi@192.168.50.12:clips/config/
```

Ya con esto la Pi puede subir, pero **no lo va a hacer** mientras `youtube_upload_enabled` esté
en `false`.

## Parte 3 — La auditoría

Formulario oficial: **"YouTube API Services - Audit and Quota Extension Form"**
→ https://support.google.com/youtube/contact/yt_api_form

La documentación de Google no publica la lista exacta de campos (dice solamente que hay que
completar el formulario y que alguien del equipo de YouTube te contacta). Lo que sigue es lo que
**suelen** preguntar, con respuestas pensadas para este bot. Si un campo no coincide, respondé con
la misma idea.

| Lo que suele preguntar | Qué poner |
|---|---|
| Nombre, mail de contacto, país | los tuyos; Argentina |
| Organización / empresa | tu nombre o el del proyecto ("Rots") si no tenés empresa |
| Número de proyecto de Google Cloud | el de la parte 1, paso 7 |
| Nombre de la app / cliente de la API | Clips Bot |
| ¿Para qué usa la API? | "Herramienta interna para subir y programar videos cortos a MIS dos canales (Rots y Pequeña Historia). Uso `videos.insert` con `publishAt` para programar, y `videos.update` para cancelar una programación. No accedo a datos de otros usuarios ni los guardo." |
| ¿Quiénes la usan? / cantidad de usuarios | una sola persona (el dueño de los canales); no es una app pública |
| ¿Muestra o guarda datos de YouTube? | "Solo guardo el id de cada video que subo y su fecha programada, para poder cancelarla." |
| Métodos de la API que usa | `videos.insert`, `videos.update`, `channels.list` (para confirmar el canal) |
| Cuota que pedís | lo de fábrica alcanza (≈ 3-4 subidas por día, el tope actual es 100). Si hay que poner un número, pedí el mínimo que ofrezca |
| Capturas o video del flujo | grabá la pantalla: el mensaje del bot en Telegram con el video → apretar ✅ → el mensaje "📤 Programado…" → el video en Studio como privado con fecha. Se puede hacer con un canal de prueba |
| Política de privacidad / términos | si piden una URL: una página simple (Google Sites o un Doc público) que diga que la app es de uso personal, que solo sube videos a tus canales y que no recolecta datos de terceros |
| ¿Cumple las Developer Policies y los Términos de YouTube API Services? | Sí. Leelos por arriba antes: https://developers.google.com/youtube/terms/developer-policies |

Cuánto tarda: Google no da un plazo. Contestan por mail; a veces piden más datos o un video.

## Parte 4 — Prender la subida (cuando aprueben)

1. En `config/settings.yaml`, cambiar `youtube_upload_enabled: false` por `true`.
2. Subirlo y actualizar la Pi (lo mismo de siempre):

```
git commit -am "Subida a YouTube prendida" && git push
ssh santi@192.168.50.12 "cd ~/clips && git pull && sudo systemctl restart clips-bot-telegram"
```

Desde ahí:

- **Pequeña Historia:** al apretar ✅ en la efeméride, el video se arma, llega por Telegram y se
  programa solo para ese día a las 12:00 (o en 30 minutos si ya pasó esa hora). Se configura en
  `efemerides.hora_publicacion`.
- **Rots:** al darle 👍 a un clip, se programa en su horario sugerido (13:00, 18:00 o 21:30; si
  está ocupado, el siguiente libre).
- **/subidas** en Telegram lista lo programado y tiene un botón **❌ Cancelar** por video: lo deja
  privado y sin fecha en Studio (no lo borra).
- TikTok, Instagram y Facebook siguen siendo a mano.

Si algo falla al subir, el bot avisa en el chat con el motivo y queda anotado en `/subidas`.
