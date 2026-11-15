# Registro de videos (formato común entre bots)

Pedido de Santi (2026-11-15): cada bot registra lo suyo con el mismo formato, para comparar costos y tiempos.
`clips` lo escribe en `data/clips.db`; Lo Encontré tiene que escribirlo en su base (`~/bot-videos/data/bot2.db`)
con la MISMA tabla. `/costos` y el resumen de los lunes de `clips` leen las dos.

## Tabla `videos_registro`

```sql
CREATE TABLE IF NOT EXISTS videos_registro (
    id           TEXT PRIMARY KEY,   -- el id del video en ese bot
    bot          TEXT NOT NULL,      -- clips | lo_encontre
    canal        TEXT NOT NULL,      -- asinacio | pequena_historia | lo_encontre
    formato      TEXT NOT NULL,      -- marcas | tecnologia | latinoamerica | producto | 3_cosas | caro_barato | carrusel
    titulo       TEXT DEFAULT '',
    clip_id      TEXT DEFAULT '',
    dia          TEXT NOT NULL,      -- AR, AAAA-MM-DD
    inicio       TEXT NOT NULL,      -- UTC ISO
    fin          TEXT DEFAULT '',
    total_s      REAL DEFAULT 0,     -- suma de las etapas
    estado       TEXT DEFAULT '',    -- armando | propuesto | entregado | programado | publicado | cancelado | fallido
    fallo_paso   TEXT DEFAULT '',
    fallo_motivo TEXT DEFAULT '',
    temp_max     REAL,               -- °C
    frenado      INTEGER DEFAULT 0,  -- 1 si la Pi se frenó por calor en el render (bits 0x2|0x4|0x8 de get_throttled)
    costo_usd    REAL DEFAULT 0,     -- Claude, todos los pasos
    detalle      TEXT DEFAULT '{}'
)
```

`detalle` (JSON):

```json
{
  "etapas": {"busqueda": 40.1, "guion": 95.3, "fotos": 210.0, "voz": 31.2, "whisper": 35.0, "render": 461.0, "subida": 12.4},
  "claude": [{"paso": "guion", "modelo": "claude-sonnet-5-5", "intentos": 1, "entrada": 9000, "salida": 12000, "usd": 0.138, "cache": 0}],
  "voces": {"n": 2, "reintentos": 1, "claves": {"principal": 2}},
  "tramos": [[1200, 1214]],
  "extra": {}
}
```

Nombres de etapa: `busqueda`, `guion`, `fotos`, `dibujos`, `voz`, `whisper`, `revision`, `render`, `subida`.
Nombres de paso de Claude: `elegir` (puntuar y clasificar), `guion`, `correccion`, `fotos`, `revision_visual`,
`final`, `dibujos`, `otros`. En `clips` todo esto lo arma `clips_bot/bitacora.py` (se puede copiar tal cual).
