# Portadas e ilustraciones con IA para Pequeña Historia — EN PAUSA

**Estado (2026-11-01):** diseño propuesto, **en pausa por decisión de Santi**. No hay nada
programado ni pago activado. Este archivo es para retomarlo más adelante.

Pedido original de Santi: sumar el estilo de un canal de historia que pega mucho: portada
cinematográfica con IA, ilustraciones con IA en las frases sin foto buena, aviso de contenido
sintético al subir, y una muestra antes de dejarlo por defecto.

---

## Antes de retomar: lo que hay que decidir

1. **Choca con dos reglas vigentes.** CLAUDE.md §1: "Sin IA generativa: Gemini solo para texto".
   Y en Pequeña Historia (v0.56.0, 2026-10-04): "nada de IA, dibujos ni recreaciones". La
   propuesta es cambiarlas SOLO para Pequeña Historia (portada con IA siempre + como mucho 2
   ilustraciones marcadas por video). Los clips de Rots siguen sin IA.
2. **Pago en Google.** Los modelos de imágenes de Gemini no tendrían plan gratis: hay que activar
   la facturación en el proyecto de la clave de Gemini, o cargar una clave aparte solo para
   imágenes (`GEMINI_API_KEY_IMAGENES`).
3. **Imágenes realistas de personas reales.** Una imagen de una persona histórica real hecha con IA
   no se puede presentar como verdadera en un canal de historia: por eso el aviso va en tres lugares
   (YouTube, descripción y "Recreación" en pantalla).
4. **Abiertas:** ¿modelo Flash o Pro? ¿"Recreación" también en el primer cuadro, o portada limpia?
   ¿Fuente Cinzel u otra serif?

---

## 1. Portada con IA

- **Escena:** en la MISMA llamada del guion (sin llamadas nuevas de texto), Gemini agrega
  `escena_portada` (personaje o escena principal, con ropa, lugar y época, solo con lo que dice el
  artículo), `titulo_portada` (2 a 5 palabras), `lugar` y el año a mostrar ("44 A. C.").
- **Imagen:** el modelo de imágenes de Gemini la genera con un estilo fijo: vertical 9:16,
  cinematográfica, luz dorada, mucho detalle, fiel a la época y al lugar del artículo, sin letras
  ni logos.
- **Revisión:** Gemini mira la imagen terminada (una llamada con visión) y la rechaza si tiene
  texto metido, anacronismos evidentes, manos o caras deformes, o algo duro. Si la rechaza, se
  genera una vez más.
- **Título:** lo arma el código (PIL), no la IA, para que el estilo sea siempre igual: título
  grande en serif dorada con borde y sombra, abajo la línea chica "ROMA · 44 A. C.", y un degradé
  oscuro para que se lea. En la Pi solo hay DejaVu Serif: propuesta, bajar **Cinzel** (licencia
  libre OFL) a una carpeta de fuentes del repo.
- **Dónde va:** primer cuadro del video (~1 s, con la voz ya arrancando; reemplaza al "año
  contando" del principio) y portada en YouTube (`thumbnails.set`) y en Facebook
  (`/{video}/thumbnails` con `is_preferred`), en lugar de la que hoy sale de un cuadro del video
  (`media.portada`, `graficos.PORTADA_S`).
- **Aprobación:** la portada aparece en la hoja de aprobación, con un botón **🔁 Portada** para
  generar otra.

## 2. Ilustraciones con IA

- **Cuándo:** solo en las frases que hoy quedan sin foto buena de la época (donde ahora se repite
  una foto o va la tarjeta). **Como mucho 2 por video.**
- **Orden de preferencia:** foto real de época → ilustración IA → repetir una buena → tarjeta.
  Esto cambia la regla fija 1 (k) de CLAUDE.md §1: necesita el OK explícito de Santi.
- **Cómo se ven:** mismo estilo que la portada, zoom lento (las fotos reales siguen quietas, como
  pide `efemerides.efecto_fotos: fija`) y **"Recreación"** chiquito en una esquina.
- **No cuentan como fotos reales:** la regla "con menos de 4 fotos reales de época
  (`ilustrar.MIN_FOTOS_ABSOLUTO`), se pasa al hecho siguiente" sigue igual, para que la IA no tape
  la falta de material.
- **En la hoja:** cada una marcada con "IA".

## 3. Aviso de contenido sintético

- **YouTube:** `status.containsSyntheticMedia: true` en toda efeméride con imágenes de IA (siempre,
  porque la portada lo es). Existe en la Data API desde octubre de 2024 y se puede poner en
  `videos.insert` y `videos.update` (`youtube.metadatos`).
- **Descripción:** una línea "Portada e ilustraciones recreadas con IA."
- **Facebook:** no se encontró un campo documentado para marcar IA en Reels por la Graph API. Para
  Instagram existe `is_ai_generated` en el contenedor; para Facebook solo un pedido de usuarios que
  menciona `video_labels: ["LABELED_AI_GENERATED"]`, sin documentación oficial. Plan: la línea en
  la descripción, y probar ese campo con un Reel de prueba (y borrarlo) antes de confiar en él.

## 4. Costo (estimado; confirmar con la primera llamada real)

Google no publica en un lugar claro el precio por imagen; los blogs no coinciden entre sí.

| | Por imagen | Por video (portada + 2 ilustraciones, con algún reintento: 3 a 6 imágenes) | Por mes (31 videos) |
|---|---|---|---|
| Modelo Flash de imágenes | ~US$0,04 | US$0,12–0,23 | ~US$4–7 |
| Modelo Pro de imágenes | ~US$0,13 | US$0,40–0,80 | ~US$12–25 |

La revisión con Gemini de cada imagen agrega menos de un centavo. Propuesta: arrancar con Flash y
pasar a Pro solo si la calidad no alcanza. (Para comparar: el texto de Gemini, si se paga, sale
≈ US$4–8/mes según `docs/costo-gemini.md`.)

## 5. Cómo se probaría

- Todo detrás de un interruptor apagado (`efemerides.ia`) hasta que Santi apruebe una muestra.
- Muestra: con la efeméride de un día real, en la Pi: propuesta, portada, ilustraciones y el
  video terminado, mandado al privado de Santi (no al grupo) y sin subir nada.
- Tests sin red, como siempre (el conftest ya corta YouTube y Facebook; habría que cortar también
  el endpoint de imágenes de Gemini).

## Fuentes consultadas (2026-11-01)

- YouTube Data API, historial de cambios: https://developers.google.com/youtube/v3/revision_history
- YouTube Data API, recurso videos: https://developers.google.com/youtube/data/reference/rest/v3/videos
- Precios de imágenes de Gemini (blogs, sin confirmar):
  https://blog.laozhang.ai/en/posts/gemini-3-pro-image-api-pricing ,
  https://blog.laozhang.ai/en/posts/gemini-image-cheapest-api-2026 ,
  https://www.developersdigest.tech/models/image-generation/google-gemini-api
- Meta: changelog de Instagram Platform (`is_ai_generated`):
  https://developers.secure.facebook.com/documentation/instagram-platform/changelog ;
  pedido de usuarios sobre Facebook:
  https://zernio.featurebase.app/p/feature-request-ai-generated-content-disclosure-for-facebook-and-pinterest
