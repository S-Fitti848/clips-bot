#!/usr/bin/env bash
# Deploy en la Pi: git pull, tests y reinicio de la escucha SOLO cuando no hay trabajo pesado
# (espera hasta 30 min a que termine). Antes vivía en /tmp y el sistema lo borró (2026-10-20).
# Uso: bash ~/clips/deploy/desplegar.sh
set -euo pipefail
cd ~/clips
git pull -q
git log --oneline -1
.venv/bin/python -m pytest -q 2>&1 | tail -1
pesado() {
  .venv/bin/python -c "
from clips_bot import db
from clips_bot.config import DB_PATH
print(db.hay_trabajo_pesado(db.connect(DB_PATH)) or '')"
}
for _ in $(seq 1 90); do
  P=$(pesado)
  [ -z "$P" ] && break
  echo "pesado: $P (espero)"
  sleep 20
done
P=$(pesado)
if [ -n "$P" ]; then
  echo "pesado: $P: NO reinicio la escucha"
  exit 1
fi
echo "pesado: None"
sudo systemctl restart clips-bot-telegram
echo "escucha: $(systemctl is-active clips-bot-telegram)"
