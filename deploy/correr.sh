#!/usr/bin/env bash
# Corre un comando del bot desde systemd: `diario` (clips-bot.service, el default) o
# `efemeride-diaria` (clips-bot-efemeride.service). Hace dos cosas que el .service no puede solo:
#   1. deja el log en journald Y en el archivo plano que rota logrotate (<comando>.log);
#   2. la corrida de clips se reintenta una vez, porque la causa más común de falla es una API que
#      no contestó. La efeméride no: sus reintentos los hace la escucha de Telegram (07:00, 10:00).
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${CLIPS_BOT_LOG_DIR:-/var/log/clips-bot}"
COMANDO="${1:-diario}"
case "$COMANDO" in
  diario) LOG="$LOG_DIR/diario.log"; REINTENTAR=1 ;;
  efemeride-diaria) LOG="$LOG_DIR/efemeride.log"; REINTENTAR=0 ;;
  *) echo "comando desconocido: $COMANDO" >&2; exit 2 ;;
esac
ESPERA_REINTENTO_S="${CLIPS_BOT_REINTENTO_S:-600}"

mkdir -p "$LOG_DIR" 2>/dev/null || true

correr() {
  # tee manda a stdout (lo toma journald) y al archivo; pipefail conserva el código de python.
  "$DIR/.venv/bin/python" -m clips_bot "$COMANDO" 2>&1 | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

echo "=== $(date -Is) $COMANDO (intento 1)" | tee -a "$LOG"
if correr; then
  exit 0
fi
codigo=$?
if [ "$REINTENTAR" != 1 ]; then
  echo "=== $(date -Is) falló con código $codigo" | tee -a "$LOG"
  exit "$codigo"
fi
echo "=== $(date -Is) falló con código $codigo; reintento en ${ESPERA_REINTENTO_S}s" | tee -a "$LOG"
sleep "$ESPERA_REINTENTO_S"
echo "=== $(date -Is) $COMANDO (intento 2)" | tee -a "$LOG"
if correr; then
  exit 0
fi
codigo=$?
echo "=== $(date -Is) falló de nuevo con código $codigo" | tee -a "$LOG"
exit "$codigo"
