# Orden exacto para grabar la pantalla (demo de la auditoría)

Antes de grabar: Telegram (el chat privado con el bot) y YouTube Studio del canal Roty abiertos en
dos ventanas. Grabá la pantalla entera, en inglés y sin cortes si se puede.

1. **Telegram:** `/lang en` → el bot contesta "Done: the bot now replies in English."
2. **Telegram:** `/demo` → llega el video de prueba con Title / Description / Hashtags y los botones
   "📤 Upload to YouTube" / "🚫 Don't upload". *(Captura 1)*
3. **Telegram:** tocá **📤 Upload to YouTube** → "📤 Uploading…" y después el mensaje "Uploaded with
   videos.insert … scheduled (publishAt) for <mañana> 13:00 …" con el id y el link a Studio. El botón
   pasa a "📤 Scheduled for 13:00" / "❌ Cancel". *(Captura 2)*
4. **YouTube Studio → Contenido:** mostrá el video de prueba como **Privado**; abrilo y mostrá el
   título, la descripción y la visibilidad/programación. *(Captura 3)*
5. **Telegram:** `/subidas` → la lista "Scheduled YouTube uploads" con el video y "❌ Cancel #N".
   *(Captura 4)*
6. **Telegram:** tocá **❌ Cancel #N** → "Schedule #N cancelled with videos.update…". *(Captura 5,
   primera mitad)*
7. **YouTube Studio:** recargá y mostrá que el video sigue privado y sin fecha de publicación.
   *(Captura 5, segunda mitad)*
8. **Telegram:** `/metricas refresh` → "Requesting the latest metrics from YouTube…" y después
   "Your latest Shorts — YouTube Analytics" con vistas, % visto, % al final y duración. *(Captura 6)*
9. **Telegram:** `/publicos davooxeneize` → en segundos, "Public YouTube search (search.list +
   videos.list)…" y la lista de Shorts públicos con canal, vistas y link. *(Captura 7)*
10. **Telegram:** `/lang es` para volver al castellano (fuera de la grabación).

Notas:
- El `/demo` sube aunque la subida esté apagada para todo lo demás: es solo ese video.
- El video de prueba es de barras de color con un cartel: no tiene nada de terceros.
- `/publicos` gasta 101 unidades de la API key (search.list + videos.list); la subida, 1 del balde de subidas.
- NO uses `/buscar … pego` para la demo: compara audio contra decenas de clips y tarda muchos minutos.
- Si querés repetir la toma, mandá `/demo` de nuevo: cada vez es un video nuevo.
