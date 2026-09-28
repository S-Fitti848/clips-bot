# Música de fondo de Pequeña Historia

La carpeta `musica/` (en la raíz del proyecto, en la Pi) **no va a git**: pesa, y cada máquina la
arma sola. El código está en `clips_bot/musica.py`.

| Carpeta | Qué hay | Quién la llena |
|---|---|---|
| `musica/youtube/` | temas de la Biblioteca de audio de YouTube | Santi, a mano (copiar por scp a la Pi) |
| `musica/kevin/` | Kevin MacLeod (incompetech.com), CC BY 4.0 | el bot |
| `musica/openverse/` | Openverse, **solo CC0 y CC BY** (nada NC, ND ni SA) | el bot |
| `musica/biblioteca.json` | título, autor, licencia, link y etiquetas de lo que bajó el bot | el bot |

## Cómo elige

1. Afuera los temas vetados por `/reclamo` y los usados en los últimos 5 videos.
2. Si hay alguno de `youtube/`, elige entre esos (tienen prioridad).
3. Entre los que quedan, el que mejor coincide con el **tono** del guion (alegre, épico,
   misterioso, curioso o emotivo; lo decide Gemini en la misma llamada del guion).
4. Va al 12 % (`efemerides.musica_volumen`), bajando cuando habla la voz, con un fundido al final.
5. Qué tema usó queda en el json del video (`efemeride.musica`) y el crédito en la descripción.

De `youtube/` se saltean los que tienen "feat." en el nombre: son canciones con voces y tapan la
narración.

## Llenar y revisar

```bash
python -m clips_bot musica            # lista lo que hay, con tono, vetados y recientes
python -m clips_bot musica --llenar   # baja lo que falte (10 por fuente, efemerides.musica_por_fuente)
```

La corrida de las 05:00 también completa lo que falte.

Filtros al bajar: 1 a 4 minutos, hasta 15 MB, sin voces (Kevin: sin voz, vocals ni coro entre los
instrumentos; Openverse: marcado "instrumental" y sin etiquetas de voz).

## Content ID

§1 de CLAUDE.md decía "sin música agregada". Esto es una excepción pedida por Santi para Pequeña
Historia. La Biblioteca de YouTube es lo único garantizado sin reclamos en YouTube; Kevin MacLeod
casi nunca tiene; lo de Openverse (mucho viene de Jamendo) puede tener. Si llega un reclamo:
`/reclamo <id del video>` y ese tema no se vuelve a usar.
