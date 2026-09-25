#!/usr/bin/env bash
# Aviso por Telegram de que una unidad fallo. Lo dispara OnFailure=clips-bot-alerta@%n.service
# Usa el mismo bot y el mismo chat que la entrega diaria: lee TELEGRAM_* del .env del proyecto.
set -uo pipefail

UNIDAD="${1:-clips-bot.service}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# El .env copiado desde Windows viene con finales de linea CRLF. Bash se trae el retorno de carro
# pegado al valor y la URL de la API sale rota ("curl: (3) URL rejected"), sin decir por que.
# Python no se entera porque convierte los saltos al leer, asi que el bot anda y lo unico que se
# rompe es la alerta: justo lo que no se prueba nunca. Por eso se limpia antes de importar.
# OJO: el patron va como $'\r'. Escrito como comillas simples con un retorno de carro adentro, tr
# borraba TAMBIEN los saltos de linea, el .env quedaba en una sola linea y no se cargaba nada.
if [ -f "$DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . <(tr -d $'\r' < "$DIR/.env")
  set +a
fi
: "${TELEGRAM_BOT_TOKEN:?falta TELEGRAM_BOT_TOKEN en $DIR/.env}"
: "${TELEGRAM_CHAT_ID:?falta TELEGRAM_CHAT_ID en $DIR/.env}"

ESTADO="$(systemctl show "$UNIDAD" -p Result --value 2>/dev/null || echo desconocido)"
COLAS="$(journalctl -u "$UNIDAD" -n 25 --no-pager -o cat 2>/dev/null | tail -c 2500)"

# Si pego contra el StartLimit, systemd NO lo vuelve a levantar hasta un reset-failed: sin decirlo,
# uno reinicia y le contesta "Start request repeated too quickly" sin entender por que.
AYUDA="journalctl -u $UNIDAD -n 200 --no-pager"
if journalctl -u "$UNIDAD" -n 30 --no-pager -o cat 2>/dev/null | grep -q "repeated too quickly"; then
  AYUDA="$AYUDA
sudo systemctl reset-failed $UNIDAD && sudo systemctl start $UNIDAD"
fi

ESCAPADO="$(printf '%s' "$COLAS" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g')"
TEXTO="$(printf '\xe2\x9a\xa0\xef\xb8\x8f <b>%s</b> fallo (%s) en la Pi.\n\nUltimas lineas:\n<pre>%s</pre>\n\nPara ver todo:\n<pre>%s</pre>' \
  "$UNIDAD" "$ESTADO" "$ESCAPADO" "$AYUDA")"

curl -sS --max-time 30 -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "parse_mode=HTML" \
  --data-urlencode "text=${TEXTO}" >/dev/null
