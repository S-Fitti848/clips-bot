# Facebook para Así Nació: cómo conectarlo

Con esto, el video diario de Así Nació sale también como **Reel en la página de Facebook de Así Nació**,
a la misma hora que en YouTube (19:00 AR), y el ❌ Cancelar lo frena en los dos lados.

Se usa la **misma app de Meta** que ya publica en Pequeña Historia (`clips-bot`): no hay que crear otra.
Tiempo: unos 5 minutos.

## Lo que hacés vos

1. Tenés que ser **administrador** de la página de Así Nació en Facebook (si la página no existe:
   facebook.com/pages/create → nombre **Así Nació**, categoría *Entretenimiento* o *Sitio web*).
2. Entrá a **developers.facebook.com/tools/explorer** (con tu cuenta de Facebook).
3. A la derecha:
   - **Meta App**: elegí **clips-bot** (la misma de Pequeña Historia).
   - **User or Page**: **User Token**.
   - **Permissions**: agregá estos (escribiendo el nombre en el buscador):
     `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_metadata`,
     `read_insights` y, si aparece, `publish_video`.
4. Tocá **Generate Access Token**. Se abre una ventana de Facebook: **elegí la página Así Nació**
   (podés dejar también Pequeña Historia tildada, no molesta) y aceptá todos los permisos.
5. Copiá el token que quedó arriba de todo en el Explorer (un texto largo que empieza con `EAA…`).
6. En tu compu, abrí el archivo **`.env`** de la carpeta `clips` (con el Bloc de notas) y agregá al
   final una línea:

   ```
   FB_USER_TOKEN=el_token_que_copiaste
   ```

   Guardá. **No pegues el token en ningún chat** (tampoco en el de Claude): es como una contraseña.
7. Decile a Claude: *"Cargué FB_USER_TOKEN en el .env para Así Nació"*.

## Lo que hace Claude (sin mostrar el token en ningún lado)

1. Canjea tu token por uno de larga duración (con el ID y el secreto de la app, que ya están en el
   `.env`) y, de ahí, saca el **token de la página Así Nació**, que **no vence**.
2. Guarda `ASINACIO_FACEBOOK_PAGE_ID` y `ASINACIO_FACEBOOK_PAGE_TOKEN` en el `.env` de la compu y de
   la Pi (compara las huellas, no los valores) y **borra** `FB_USER_TOKEN`.
3. Prende `animacion.facebook` y, con tu OK, prueba con un Reel corto que borra enseguida.

## Ojo: la app está en "modo desarrollo"

En octubre se vio que los Reels que publica la app en modo desarrollo **no los ve el público** (solo
quien tiene un rol en la app). Si eso sigue así, el Reel de Así Nació tampoco se va a ver. Pasarla a
**modo Live** se hace en developers.facebook.com → la app **clips-bot** → arriba, el interruptor
**Modo de la app: Desarrollo → Live**; para eso Meta pide una **URL de política de privacidad**
(sirve la que ya está: https://s-fitti848.github.io/privacidad.html) y una **categoría** de la app.
