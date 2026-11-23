#!/usr/bin/env bash
# Modo escucha de Telegram: lo ejecuta clips-bot-telegram.service.
# Igual que correr.sh, deja el log en journald Y en el archivo plano que rota logrotate.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${CLIPS_BOT_LOG_DIR:-/var/log/clips-bot}"
LOG="$LOG_DIR/telegram.log"

mkdir -p "$LOG_DIR" 2>/dev/null || true
echo "=== $(date -Is) arranca el modo escucha" | tee -a "$LOG"

# sed tapa claves y tokens (Santi, 2026-11-23). Sin `exec` para que el tee siga vivo; pipefail conserva el código de python para el Restart=.
"$DIR/.venv/bin/python" -m clips_bot atender-telegram --escuchar 2>&1 | sed -u -E 's/(access_token|token|key)=[^&[:space:]"]+/\1=***/g; s#/bot[0-9]+:[A-Za-z0-9_-]+#/bot***#g; s/EAA[A-Za-z0-9]{20,}/***/g; s/AIza[0-9A-Za-z_-]{30,}/***/g; s/sk-ant-[A-Za-z0-9_-]+/***/g' | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
