# Retención y alcance de Pequeña Historia — diseño (2026-11-14, para el OK de Santi)

Nada de esto está programado. Cada punto dice qué hace falta, qué cuesta y qué riesgo tiene.

## 1. Reels también en Instagram

**Cómo:** la API de Instagram (Graph API, la misma app de Meta que ya publica en la página) sube un
Reel en dos pasos: se crea un "contenedor" con `media_type=REELS` en `/{ig-user-id}/media` (con
subida reanudable directa del archivo desde la Pi, `rupload.facebook.com`, sin necesitar una URL
pública), se espera a que su `status_code` sea `FINISHED` y se publica con `/{ig-user-id}/media_publish`.
Meta deja chequear el cupo con `content_publishing_limit`.

**Qué hace falta (de Santi):**
- La cuenta de Instagram tiene que ser **profesional** (Business o Creator) y estar vinculada a la
  página (ya lo está).
- **Volver a autorizar** el token de la página sumando el permiso de publicar en Instagram
  (`instagram_content_publish` / `instagram_business_content_publish`) — **aviso antes**, como quedó
  acordado. El token actual no lo tiene.
- La app de Meta sigue en **modo desarrollo**: hay que confirmar si lo publicado así se ve público en
  Instagram (en Facebook NO se veía para el público). Lo pruebo con un Reel de prueba y lo borro.

**Diseño:** el mismo 📤 de Pequeña Historia (o la publicación sola) sube también a Instagram, a la misma
hora que Facebook; queda en `subidas` con canal `instagram`; ❌ Cancelar lo borra. Interruptor
`instagram.activo` apagado hasta probar.

## 2. TikTok automático: qué hace falta

- Registrar una app en **TikTok for Developers** con el producto *Content Posting API* y el permiso
  `video.publish` (revisión de la app).
- **Además**, una **auditoría aparte** de la Content Posting API: hasta pasarla, lo que se sube por la
  API queda **privado (solo yo)**, y si la cuenta es pública la API la rechaza (error
  `unaudited_client_can_only_post_to_private_accounts`). Sin auditar, hasta 5 usuarios por día y con
  la cuenta en privado. Terceros hablan de 2 a 6 semanas para la auditoría (no es un dato oficial).
- La auditoría revisa el uso y que la app muestre al usuario una pantalla de publicación con ciertos
  elementos (título, privacidad, avisos): para un bot que publica solo, hay que armar esa parte o
  justificarla.
- Mi recomendación: por ahora TikTok a mano (el bot ya manda el mp4 y los textos); pedir la app y la
  auditoría en paralelo si TikTok rinde.

## 3. Final en loop

El guion termina con una frase que **empalma con la primera**: la última frase deja la idea a mitad y
la primera la completa al volver a empezar (ej.: final "…y por eso todavía hoy, cada 14 de noviembre,
se acuerdan de" → arranque "Una mujer joven que espió a los españoles…"). Cambios:
- Prompt del guion: regla nueva + campo `empalme` (true/false); la revisión del final (`final_que_paga`)
  chequea que el final pague el gancho Y empalme.
- Video: sin fundido a negro ni silencio al final (hoy el audio tiene fade out de 0,5 s, regla fija 3:
  hay que **cambiar la regla fija** para este formato, por eso pido OK); el último cuadro igual al
  primero (misma foto) para que el corte no se note.
- Riesgo: la frase cortada suena rara si alguien mira una sola vez. Se mide con el % que llega al final
  y las vistas repetidas (YouTube da `averageViewPercentage` > 100 % cuando hay repeticiones).

## 4. Música con tensión y efectos de sonido

- **Música:** la biblioteca ya tiene etiquetas por tono (alegre/épico/misterioso/curioso/emotivo).
  Sumo "tensión" y elijo temas de licencia libre ya verificada (Biblioteca de YouTube, Kevin MacLeod
  CC BY, Openverse CC0/CC BY; nunca NC/ND/SA), con crédito en la descripción. El guion ya marca el
  tono: las de peligro y giro piden "tensión". Sube un poco el volumen de la música en la tensión y
  baja en el pago.
- **Efectos:** sintetizados con ffmpeg (como el whoosh actual: sin licencias): un golpe grave suave en
  la frase del giro (`frase_giro`, que el guion ya marca) y un "riser" corto que termina en el pago
  (`frase_pago`). Volumen bajo, nunca encima de la voz.
- Costo: nada extra (sin llamadas nuevas a Claude). Render: +5-10 s por video.

## 5. Grupos de Facebook del lugar, para compartir a mano

- La API de Facebook **no permite buscar grupos** (Meta lo cerró en 2018) ni publicar en grupos
  ajenos. Un modelo inventando nombres de grupos tampoco sirve (pueden no existir).
- **Diseño:** cuando la historia es de un lugar concreto, con el video te llega un mensaje con 2-3
  **links de búsqueda de grupos** ya armados (`facebook.com/search/groups/?q=<lugar>`,
  `<lugar> historia`, `<región> recuerdos`), que abrís desde el celu con tu cuenta y elegís los que
  sean públicos y activos. Compartir es manual (es lo que pediste).
- Opcional más adelante: guardar los grupos que elijas por lugar (`/grupo Bogotá <link>`) para que la
  próxima historia del mismo lugar ya traiga los links directos.

## 6. Humor (ya programado, va con todo)

Pequeña Historia: un toque de humor o ironía suave cuando la historia lo permite, nunca en muertes,
ejecuciones, tragedias, guerras ni temas sensibles (regla en el prompt del guion, 2026-11-14).
