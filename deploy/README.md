# Deploy en la Raspberry Pi 4

La Pi ya corre el bot de trading. **Nada de acá lo toca**: son unidades de systemd con otro nombre
(`clips-bot*`), otro `WorkingDirectory` y sus propias cachés. `instalar.sh` se niega a escribir si
encuentra una unidad `clips-bot*` que no reconoce como suya.

## 1. Preparar la Pi

```bash
sudo apt update
sudo apt install -y ffmpeg tesseract-ocr tesseract-ocr-spa
git clone <repo> ~/clips && cd ~/clips
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env     # TWITCH_*, GEMINI_API_KEY, TELEGRAM_*
```

`tesseract-ocr-spa` es para `pantalla.idioma: spa+eng`. Si no lo instalás, tesseract falla, la capa
de datos en pantalla se saltea sola (con warning) y la corrida sigue — pero perdés ese filtro.
Alternativa: dejar `pantalla.idioma: eng` en `config/settings.yaml`.

## 2. Medir ANTES de poner el timer

El pipeline se calibró en Windows con 8 hilos. La Pi es aarch64 y tiene undervoltage confirmado,
así que los números no se trasladan. Antes de automatizar nada:

```bash
# copiar 2 o 3 mp4 a output/raw/ (o correr `procesar <url>` una vez) y después:
.venv/bin/python -m clips_bot benchmark --clips 3 --modelos small,base
```

Mide OCR, Whisper (carga + transcripción) por modelo, detección de cámara y render, y dice si entra
en el tope de 5 min por clip. Deja un `.srt` por modelo en `output/benchmark/` para comparar la
calidad del texto a ojo, y un `benchmark.json` con la máquina y los tiempos.

Referencia Windows (8 hilos, clips de 17–22 s, `spa+eng`, preset `medium`): 40–76 s por clip, o sea
1,8–4,5× la duración del clip.

**Medido en esta Pi el 2026-09-23** (Pi 4 Rev 1.4, 8 GB, Debian 13, 4 núcleos):

| | cargar modelo | 60 s de video | 22 s de video |
|---|---|---|---|
| `small` | 59 s (la 1ª vez baja 467 MB) | 42 s (0,70×) | 34 s (1,53×) |
| `base` | 21 s | 58 s (0,97×) | 12 s (0,57×) |

`small` entra cómodo, así que **se queda `small`**: `base` es más rápido pero pierde calidad visible
(se come los signos de pregunta e inventa palabras — "no es manera hue" donde `small` pone "no hay
manera"). Los `.srt` de los dos están en `output/benchmark/` si lo querés ver vos.

Dos cosas que sí aparecieron midiendo:

- **Un clip de 17 s tardó 483 s con `small`** (28× la duración). No es el modelo: con `base` fueron
  198 s, y con `beam_size=1` y/o `condition_on_previous_text=False` da 27–37× igual. Es un audio de
  gritos sin habla clara donde el decoder entra en loop, y lo que sale es "no no no no". Por eso
  ahora hay un tope de tiempo por clip (`subtitulos.timeout_factor`, 8× la duración) que lo corta y
  lo descarta con motivo `transcripcion_lenta`.
- **La Pi throttlea por temperatura, no por voltaje.** `get_throttled` arranca en `0x0` (sin
  undervoltage), pero con Whisper sostenido llega a 84,7 °C y pasa a `0xe0008`: límite blando de
  temperatura activo y frecuencia ya capada. Con disipador o ventilador estos números mejoran.
  La unidad ya va con `Nice=10` y CPU de baja prioridad para no calentar de más ni pelearle al
  bot de trading.

Otra palanca, si hiciera falta: `render.x264_preset` a `veryfast`, que en ARM ahorra mucho más de lo
que cuesta en calidad.

## 3. Instalar

```bash
sudo ./deploy/instalar.sh --dry-run    # ver qué haría
sudo ./deploy/instalar.sh
```

Qué deja:

| Archivo | Para qué |
|---|---|
| `/etc/systemd/system/clips-bot.service` | la corrida (`Type=oneshot`, `Nice=10`, CPU de baja prioridad) |
| `/etc/systemd/system/clips-bot.timer` | 05:00 AR todos los días, `Persistent=true` |
| `/etc/systemd/system/clips-bot-telegram.service` | la escucha de Telegram, siempre andando |
| `/etc/systemd/system/clips-bot-alerta@.service` | el aviso por Telegram cuando falla |
| `/etc/logrotate.d/clips-bot` | rota `/var/log/clips-bot/*.log`, 14 días o 20 MB |

**Escucha de Telegram.** `clips-bot-telegram.service` es el único que corre siempre: hace long
polling para que `/buscar` ande en el momento y no recién en la corrida del día siguiente. Vuelve
solo si se cae (`Restart=always`), y si se reinicia 5 veces en 5 minutos para y manda la alerta —
eso ya no es una caída pasajera. Con `--sin-escucha` el instalador lo saltea y queda solo el timer.

**Nunca hay dos cosas pesadas a la vez.** `diario` y cada `/buscar` toman el mismo turno en la DB
(no en memoria: son procesos distintos). Si llega un `/buscar` mientras corre la corrida diaria, el
bot contesta *"En cola (1º), arranco cuando termine la corrida diaria"* y lo larga solo cuando se
libera. Al revés también: la corrida de las 05:00 espera hasta 20 minutos a una búsqueda que esté
andando y después arranca igual, porque el día no se puede saltear.

**Horario.** El timer dice `05:00 America/Argentina/Buenos_Aires`. La zona horaria dentro de
`OnCalendar=` existe desde systemd 252 (Raspberry Pi OS Bookworm la tiene). Si la Pi tuviera una
versión más vieja, el instalador la detecta y deja `08:00 UTC`, que es lo mismo: Argentina es UTC−3
todo el año, no tiene horario de verano.

**Reintento.** `correr.sh` reintenta una vez a los 10 min: la causa más común de falla es una API
que no contestó. Recién si falla el segundo intento salta la alerta. El reintento va en el script y
no en `Restart=` porque con `Type=oneshot` systemd no reinicia como uno espera.

**Logs.** `correr.sh` manda la salida a journald **y** al archivo plano con `tee`, así que están en
los dos lados: `journalctl -u clips-bot` para buscar, `/var/log/clips-bot/diario.log` para leer una
corrida entera de arriba a abajo.

## 4. Comprobar

```bash
systemctl list-timers clips-bot.timer                  # próxima corrida
sudo systemctl start clips-bot.service                 # correrlo ahora
journalctl -u clips-bot -f                             # verlo en vivo
sudo systemctl start clips-bot-alerta@prueba.service   # probar el aviso de Telegram
sudo logrotate -d /etc/logrotate.d/clips-bot           # probar la rotación, sin aplicar
systemctl status clips-bot-telegram                    # la escucha
journalctl -u clips-bot-telegram -f                    # ver los comandos que van llegando
```

Para probar la cola a mano: `sudo systemctl start clips-bot.service` y, mientras corre, mandale un
`/buscar` al bot — tiene que contestar que quedó en cola y arrancar cuando la corrida termine.

## 5. Sacarlo

```bash
sudo systemctl disable --now clips-bot.timer clips-bot-telegram.service
sudo rm /etc/systemd/system/clips-bot{.service,.timer,-telegram.service}
sudo rm /etc/systemd/system/clips-bot-alerta@.service
sudo rm /etc/logrotate.d/clips-bot
sudo systemctl daemon-reload
```
