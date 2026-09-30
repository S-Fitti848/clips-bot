# Facebook para Pequeña Historia: cómo conectarlo

Con esto, cuando toques **📤 Subir** debajo de una efeméride terminada, el bot sube el video como
**Reel a la página de Facebook** de Pequeña Historia (además de programarlo en YouTube cuando esa
subida esté prendida). Sale a la misma hora que en YouTube (`hora_publicacion`, 12:00); si esa hora
ya pasó, se publica en el momento. Nunca al día siguiente: es "un día como hoy".

No hace falta que Meta revise nada: es **tu** página y **tu** app, y la app queda en "modo
desarrollo", que para el administrador anda completo.

Tiempo: unos 20 minutos. Necesitás una cuenta de Facebook (la tuya).

---

## 1. La página

Si ya existe la página de Pequeña Historia, saltá al paso 2.

1. Entrá a **facebook.com/pages/create**.
2. Nombre: **Pequeña Historia**. Categoría: algo como *Sitio web de educación* o *Medios/noticias*.
3. Crear. Poné una foto de perfil y una portada (se pueden cambiar después).

## 2. La app en Meta for Developers

1. Entrá a **developers.facebook.com** con tu cuenta. Si es la primera vez, te pide registrarte
   como desarrollador: aceptá y confirmá el mail o el teléfono.
2. Arriba: **Mis apps → Crear app**.
3. Te pregunta el **caso de uso**: elegí el que diga algo como **"Administrar todo en tu página"**
   (en inglés, *Manage everything on your Page*). Si no aparece, elegí **Otro** y después tipo
   **Empresa** (*Business*).
4. Nombre de la app: **Pequeña Historia Bot** (no puede decir "Facebook"). Mail de contacto: el tuyo.
5. Si te pregunta por un "portfolio comercial" (*Business portfolio*), podés dejarlo sin elegir.
6. Crear. Te puede pedir la contraseña de Facebook.

La app queda en **modo desarrollo**: está bien así, **no la pases a "en vivo"** (para eso Meta sí
pediría revisión, y no hace falta).

## 3. Los permisos y el token (en el Graph API Explorer)

1. Entrá a **developers.facebook.com/tools/explorer**.
2. A la derecha:
   - **Meta App**: elegí *Pequeña Historia Bot*.
   - **User or Page**: *User Token* (por ahora).
   - **Permissions**: agregá estos cinco (escribiendo el nombre en el buscador):
     - `pages_show_list`
     - `pages_read_engagement`
     - `pages_manage_posts`
     - `pages_manage_metadata`
     - `publish_video` (si no aparece, seguí sin él)
3. Tocá **Generate Access Token**. Se abre una ventana de Facebook: **elegí la página Pequeña
   Historia** (solo esa) y aceptá todos los permisos.
4. Anotá también, arriba a la izquierda del Explorer, la **versión** (por ejemplo `v23.0`): si es
   distinta de la que está en `config/settings.yaml` → `facebook.version`, avisale a Claude.

## 4. El token de larga duración (el que no vence)

El token del paso 3 dura una hora. Hay que cambiarlo por uno que no venza:

1. Copiá el token que quedó en el Explorer (el texto largo arriba de todo).
2. Entrá a **developers.facebook.com/tools/debug/accesstoken**, pegalo y tocá **Debug**.
3. Abajo, tocá **Extend Access Token** (Extender token de acceso). Te da un token nuevo: ese dura
   60 días. Copialo.
4. Volvé al **Explorer**, pegá ese token nuevo en el campo **Access Token** (arriba), y en la barra
   de consulta escribí:

   ```
   me/accounts
   ```

   y tocá **Submit**.
5. En la respuesta aparece tu página. Anotá dos cosas de ella:
   - `id` → el **ID de la página** (solo números).
   - `access_token` → el **token de la página**. Este es el que sirve: un token de página sacado
     de un token de usuario de larga duración **no vence**.
6. Para confirmarlo: pegá el token de la página en el **Access Token Debugger** (paso 4.2) y fijate
   que diga **Expira: Nunca** (*Expires: Never*) y que tipo diga **Page**.

⚠️ Ese token es como una contraseña de la página: **no lo pegues en ningún chat** (tampoco en el de
Claude), ni en capturas, ni en git.

## 5. Cargarlo en el bot

1. En tu compu, abrí el archivo **`.env`** del bot (en la carpeta `clips`) y agregá al final:

   ```
   FACEBOOK_PAGE_ID=el id de la página
   FACEBOOK_PAGE_TOKEN=el token de la página
   ```

2. Guardá y decile a Claude: *"Cargué FACEBOOK_PAGE_ID y FACEBOOK_PAGE_TOKEN en el .env: copialos a
   la Pi, prendé Facebook y probalo"*. Claude los copia a la Pi sin mostrarlos, pone
   `facebook.activo: true` y prueba con un video de muestra.

## Si algo falla

- **"Invalid OAuth access token" o "Session has expired"**: el token no es el de la página o venció.
  Repetí el paso 4 (el `access_token` que sale de `me/accounts`, no el del Explorer).
- **"(#200) The user hasn't authorized the application to perform this action"**: falta un permiso
  del paso 3. Generá el token de nuevo con los cinco permisos y repetí el paso 4.
- **"(#100) ... video_reels"** o algo de la versión: la versión de la Graph API cambió; decile a
  Claude cuál muestra el Explorer.
- **El Reel no aparece**: los Reels programados se ven en **Meta Business Suite → Contenido →
  Programado**. Los publicados, en la pestaña **Reels** de la página.
- **Cambiaste la contraseña de Facebook**: eso invalida los tokens. Repetí los pasos 3 y 4.

## Cancelar un Reel programado

Debajo de la efeméride, después de 📤, aparece **❌ Cancelar**: borra el Reel programado en Facebook
y cancela el de YouTube.
