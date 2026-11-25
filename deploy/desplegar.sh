#!/usr/bin/env bash
# Deploy en la Pi. Uso: bash ~/clips/deploy/desplegar.sh
#
# Santi, 2026-11-25 (el ConfigError de fotos_primero): antes el script hacía `git pull` y DESPUÉS esperaba hasta 30 min
# a que no hubiera trabajo pesado para reiniciar: en ese rato la escucha vieja (código viejo en memoria) releía el
# settings.yaml nuevo y se caía con "Clave desconocida". Ahora:
#   1. el código nuevo se prueba en una COPIA aparte (git worktree) con el .env de esta máquina: `chequeo-arranque`
#      (carga settings.yaml y streamers.yaml, importa todos los módulos) y los tests; si falla, no se toca nada;
#   2. se espera a que no haya trabajo pesado (hasta 30 min) SIN haber actualizado todavía;
#   3. recién ahí se actualiza y se reinicia en el mismo momento;
#   4. si la escucha no queda andando, vuelve al commit anterior y la reinicia.
set -euo pipefail
cd ~/clips
PY=.venv/bin/python
antes=$(git rev-parse HEAD)
git fetch -q
nuevo=$(git rev-parse origin/main)
if [ "$antes" = "$nuevo" ]; then
  echo "ya está en $(git log --oneline -1)"
  exit 0
fi
echo "de $(git log --oneline -1 "$antes")"
echo "a  $(git log --oneline -1 "$nuevo")"

copia=$(mktemp -d /tmp/clips_deploy.XXXXXX)
limpiar() { git worktree remove --force "$copia" >/dev/null 2>&1 || rm -rf "$copia"; }
trap limpiar EXIT
git worktree add -q --detach "$copia" "$nuevo"
cp .env "$copia/.env"
for f in config/*.json; do [ -e "$f" ] && cp "$f" "$copia/config/"; done
( cd "$copia" && PYTHONPATH=. "$OLDPWD/$PY" -m clips_bot chequeo-arranque ) || {
  echo "CHEQUEO FALLÓ: el código nuevo no arranca con la configuración de la Pi. No despliego."; exit 1; }
( cd "$copia" && PYTHONPATH=. "$OLDPWD/$PY" -m pytest -q -x 2>&1 | tail -1 ) | tee /tmp/clips_deploy_tests.txt
grep -q " passed" /tmp/clips_deploy_tests.txt && ! grep -qE "failed|error" /tmp/clips_deploy_tests.txt || {
  echo "TESTS FALLARON en la copia. No despliego."; exit 1; }

pesado() {
  $PY -c "
from clips_bot import db
from clips_bot.config import DB_PATH
print(db.hay_trabajo_pesado(db.connect(DB_PATH)) or '')"
}
for _ in $(seq 1 90); do
  P=$(pesado)
  [ -z "$P" ] && break
  echo "pesado: $P (espero; todavía no actualicé nada)"
  sleep 20
done
P=$(pesado)
if [ -n "$P" ]; then
  echo "pesado: $P: NO despliego (sigue el código de antes, intacto)"
  exit 1
fi

git merge -q --ff-only "$nuevo"
sudo systemctl restart clips-bot-telegram
sleep 15
if [ "$(systemctl is-active clips-bot-telegram)" != "active" ] || \
   journalctl -u clips-bot-telegram --since "-20s" --no-pager | grep -qE "ConfigError|Traceback"; then
  echo "LA ESCUCHA NO ARRANCÓ BIEN: vuelvo a $antes"
  git reset -q --hard "$antes"
  sudo systemctl restart clips-bot-telegram
  echo "escucha: $(systemctl is-active clips-bot-telegram) (código de antes)"
  exit 1
fi
echo "desplegado $(git log --oneline -1); escucha: active"
