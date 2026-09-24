#!/usr/bin/env bash
# Instala el servicio y el timer del clips-bot en la Raspberry.
#
# NO TOCA EL BOT DE TRADING: solo crea/activa unidades que empiezan con "clips-bot", y antes de
# hacer nada verifica que ninguna de esas unidades ya exista con otro dueño. Si algo no cuadra,
# corta sin escribir.
#
#   sudo ./deploy/instalar.sh            instala y activa el timer y la escucha de Telegram
#   sudo ./deploy/instalar.sh --dry-run  muestra lo que haría, sin escribir
#   sudo ./deploy/instalar.sh --sin-escucha   solo el timer diario (sin clips-bot-telegram)
set -euo pipefail

DRY=0
ESCUCHA=1
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --sin-escucha) ESCUCHA=0 ;;
    *) echo "Opción desconocida: $a"; exit 1 ;;
  esac
done

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USUARIO="${SUDO_USER:-$(id -un)}"
LOG_DIR=/var/log/clips-bot
UNIDADES=(clips-bot.service clips-bot.timer clips-bot-alerta@.service clips-bot-telegram.service)

decir() { printf '  %s\n' "$*"; }
hacer() { if [ "$DRY" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }

echo "Proyecto:  $DIR"
echo "Usuario:   $USUARIO"
echo "systemd:   $(systemctl --version | head -1)"

# --- comprobaciones previas ---------------------------------------------------
[ -x "$DIR/.venv/bin/python" ] || { echo "ERROR: falta $DIR/.venv (creá el venv e instalá requirements.txt)"; exit 1; }
[ -f "$DIR/.env" ] || { echo "ERROR: falta $DIR/.env (TWITCH_*, GEMINI_API_KEY, TELEGRAM_*)"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ERROR: falta ffmpeg (sudo apt install ffmpeg)"; exit 1; }
command -v tesseract >/dev/null || decir "AVISO: no hay tesseract; la capa de datos en pantalla se saltea (sudo apt install tesseract-ocr tesseract-ocr-spa)"
tesseract --list-langs 2>/dev/null | grep -qx spa || decir "AVISO: falta el idioma spa (sudo apt install tesseract-ocr-spa); poné pantalla.idioma: eng si no lo vas a instalar"

# Que no estemos pisando unidades de otro proyecto (el bot de trading vive en sus propias unidades).
for u in "${UNIDADES[@]}"; do
  ruta="/etc/systemd/system/$u"
  if [ -e "$ruta" ] && ! grep -q "Clips Bot\|clips_bot\|clips-bot" "$ruta" 2>/dev/null; then
    echo "ERROR: $ruta ya existe y no parece del clips-bot. No toco nada."; exit 1
  fi
done
otras="$(systemctl list-units --type=service --all --no-legend 'clips-bot*' 2>/dev/null | wc -l)"
decir "unidades clips-bot ya presentes: $otras (las de trading no se tocan)"

# --- 05:00 AR -----------------------------------------------------------------
# La zona horaria dentro de OnCalendar existe desde systemd 252. Si es más vieja, se usa UTC:
# Argentina es UTC-3 todo el año (no hay horario de verano), así que 05:00 AR = 08:00 UTC.
VER="$(systemctl --version | head -1 | awk '{print $2}' | tr -cd '0-9')"
TIMER_TMP="$(mktemp)"
if [ "${VER:-0}" -ge 252 ]; then
  cp "$DIR/deploy/clips-bot.timer" "$TIMER_TMP"
  decir "systemd $VER: uso la zona horaria dentro de OnCalendar"
else
  sed 's|^OnCalendar=.*|OnCalendar=*-*-* 08:00:00 UTC  # = 05:00 AR (systemd viejo, sin zonas)|' \
    "$DIR/deploy/clips-bot.timer" > "$TIMER_TMP"
  decir "systemd $VER (< 252): uso 08:00 UTC, que es 05:00 AR"
fi

# --- escribir -----------------------------------------------------------------
hacer "install -d -m 0755 -o '$USUARIO' -g '$USUARIO' '$LOG_DIR'"
UNIDADES_A_ESCRIBIR=(clips-bot.service clips-bot-alerta@.service)
[ "$ESCUCHA" = 1 ] && UNIDADES_A_ESCRIBIR+=(clips-bot-telegram.service)
for u in "${UNIDADES_A_ESCRIBIR[@]}"; do
  hacer "sed -e 's|__DIR__|$DIR|g' -e 's|__USUARIO__|$USUARIO|g' '$DIR/deploy/$u' > '/etc/systemd/system/$u'"
done
hacer "install -m 0644 '$TIMER_TMP' /etc/systemd/system/clips-bot.timer"
hacer "sed 's|__USUARIO__|$USUARIO|g' '$DIR/deploy/logrotate-clips-bot' > /etc/logrotate.d/clips-bot"
hacer "chmod +x '$DIR/deploy/correr.sh' '$DIR/deploy/alerta.sh' '$DIR/deploy/escuchar.sh'"
hacer "systemctl daemon-reload"
hacer "systemctl enable --now clips-bot.timer"
if [ "$ESCUCHA" = 1 ]; then
  hacer "systemctl enable --now clips-bot-telegram.service"
else
  decir "sin modo escucha (--sin-escucha): /buscar se atiende recién en la corrida diaria"
fi
rm -f "$TIMER_TMP"

echo
echo "Listo. Comprobaciones:"
echo "  systemctl list-timers clips-bot.timer        # próxima corrida"
echo "  systemctl status clips-bot-telegram          # la escucha de Telegram"
echo "  journalctl -u clips-bot-telegram -f          # ver los comandos que llegan"
echo "  sudo systemctl start clips-bot.service       # correrlo ahora a mano"
echo "  journalctl -u clips-bot -f                   # ver la corrida en vivo"
echo "  sudo logrotate -d /etc/logrotate.d/clips-bot # probar la rotación (sin aplicar)"
echo "  sudo systemctl start clips-bot-alerta@prueba.service   # probar el aviso de Telegram"
