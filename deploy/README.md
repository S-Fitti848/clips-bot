# Deploy en la Raspberry Pi 4

La Pi ya corre el bot de trading. **Nada de acá lo toca**: son unidades de systemd con otro nombre
(`clips-bot*`), otro `WorkingDirectory` y sus propias cachés. `instalar.sh` se niega a escribir si
encuentra una unidad `clips-bot*` que no reconoce como suya.

## 1. Preparar la Pi

```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv tesseract-ocr tesseract-ocr-spa logrotate
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

**Si `small` no entra en 5 min:** pasar a `base` en `config/settings.yaml` (`subtitulos.modelo`), y
comparar los dos `.srt` del mismo clip antes de decidir — el número de palabras no alcanza para
juzgar, hay que leerlos. Otra palanca, más barata que cambiar de modelo: `render.x264_preset` a
`veryfast`, que en ARM ahorra mucho más de lo que cuesta en calidad.

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
| `/etc/systemd/system/clips-bot-alerta@.service` | el aviso por Telegram cuando falla |
| `/etc/logrotate.d/clips-bot` | rota `/var/log/clips-bot/diario.log`, 14 días o 20 MB |

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
```

## 5. Sacarlo

```bash
sudo systemctl disable --now clips-bot.timer
sudo rm /etc/systemd/system/clips-bot{.service,.timer} /etc/systemd/system/clips-bot-alerta@.service
sudo rm /etc/logrotate.d/clips-bot
sudo systemctl daemon-reload
```
