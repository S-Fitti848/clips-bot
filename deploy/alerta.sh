#!/usr/bin/env bash
# Aviso por Telegram de que una unidad falló. Lo dispara OnFailure=clips-bot-alerta@%n.service
# Usa el mismo bot y el mismo chat que la entrega diaria: lee TELEGRAM_* del .env del proyecto.
set -uo pipefail

UNIDAD="${1:-clips-bot.service}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# El .env puede venir de Windows con finales de línea CRLF. Bash se trae el 
 pegado al valor y
# la URL de la API sale rota ("curl: (3) URL rejected"), sin decir por qué. Python no se entera
# porque convierte los saltos al leer, así que el bot anda y solo se rompe la alerta: justo lo que
# no se prueba nunca. Por eso se saca el 
 acá antes de importar.
# shellcheck disable=SC1090
if [ -f "$DIR/.env" ]; then
  set -a
  . <(tr -d '
' < "$DIR/.env")
  set +a
fi
: "${TELEGRAM_BOT_TOKEN:?falta TELEGRAM_BOT_TOKEN en $DIR/.env}"
: "${TELEGRAM_CHAT_ID:?falta TELEGRAM_CHAT_ID en $DIR/.env}"

ESTADO="$(systemctl show "$UNIDAD" -p Result --value 2>/dev/null || echo desconocido)"
COLAS="$(journalctl -u "$UNIDAD" -n 25 --no-pager -o cat 2>/dev/null | tail -c 2500)"

# Si pegó contra el StartLimit, systemd NO lo vuelve a levantar hasta un reset-failed: sin decirlo,
# uno reinicia y le contesta "Start request repeated too quickly" sin entender por qué.
AYUDA="journalctl -u $UNIDAD -n 200 --no-pager"
if journalctl -u "$UNIDAD" -n 30 --no-pager -o cat 2>/dev/null | grep -q "repeated too quickly"; then
  AYUDA="$AYUDA
sudo systemctl reset-failed $UNIDAD && sudo systemctl start $UNIDAD"
fi

TEXTO="$(printf '⚠️ <b>%s</b> falló (%s) en la Pi.\n\nÚltimas líneas:\n<pre>%s</pre>\n\nPara ver todo:\n<pre>%s</pre>' \
  "$UNIDAD" "$ESTADO" "$(printf '%s' "$COLAS" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')" "$AYUDA")"

curl -sS --max-time 30 -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "parse_mode=HTML" \
  --data-urlencode "text=${TEXTO}" >/dev/null
