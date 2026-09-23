#!/usr/bin/env bash
# Corrida diaria: la ejecuta clips-bot.service. Hace dos cosas que el .service no puede solo:
#   1. deja el log en journald Y en el archivo plano que rota logrotate;
#   2. reintenta una vez, porque la causa más común de falla es una API que no contestó.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${CLIPS_BOT_LOG_DIR:-/var/log/clips-bot}"
LOG="$LOG_DIR/diario.log"
ESPERA_REINTENTO_S="${CLIPS_BOT_REINTENTO_S:-600}"

mkdir -p "$LOG_DIR" 2>/dev/null || true

correr() {
  # tee manda a stdout (lo toma journald) y al archivo; pipefail conserva el código de python.
  "$DIR/.venv/bin/python" -m clips_bot diario 2>&1 | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

echo "=== $(date -Is) corrida diaria (intento 1)" | tee -a "$LOG"
if correr; then
  exit 0
fi
codigo=$?
echo "=== $(date -Is) falló con código $codigo; reintento en ${ESPERA_REINTENTO_S}s" | tee -a "$LOG"
sleep "$ESPERA_REINTENTO_S"
echo "=== $(date -Is) corrida diaria (intento 2)" | tee -a "$LOG"
if correr; then
  exit 0
fi
codigo=$?
echo "=== $(date -Is) falló de nuevo con código $codigo" | tee -a "$LOG"
exit "$codigo"
