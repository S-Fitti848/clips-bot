#!/usr/bin/env bash
# Aviso por Telegram de que una unidad falló. Lo dispara OnFailure=clips-bot-alerta@%n.service
# Usa el mismo bot y el mismo chat que la entrega diaria: lee TELEGRAM_* del .env del proyecto.
set -uo pipefail

UNIDAD="${1:-clips-bot.service}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1090
if [ -f "$DIR/.env" ]; then
  set -a; . "$DIR/.env"; set +a
fi
: "${TELEGRAM_BOT_TOKEN:?falta TELEGRAM_BOT_TOKEN en $DIR/.env}"
: "${TELEGRAM_CHAT_ID:?falta TELEGRAM_CHAT_ID en $DIR/.env}"

ESTADO="$(systemctl show "$UNIDAD" -p Result --value 2>/dev/null || echo desconocido)"
COLAS="$(journalctl -u "$UNIDAD" -n 25 --no-pager -o cat 2>/dev/null | tail -c 2500)"

TEXTO="$(printf '⚠️ <b>%s</b> falló (%s) en la Pi.\n\nÚltimas líneas:\n<pre>%s</pre>\n\nPara ver todo:\n<pre>journalctl -u %s -n 200 --no-pager</pre>' \
  "$UNIDAD" "$ESTADO" "$(printf '%s' "$COLAS" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')" "$UNIDAD")"

curl -sS --max-time 30 -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "parse_mode=HTML" \
  --data-urlencode "text=${TEXTO}" >/dev/null
