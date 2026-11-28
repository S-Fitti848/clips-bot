"""Arma a mano los videos que le faltan al día (Santi, 2026-11-28: "si hay historias en los bancos, armalos ahora para
que salgan hoy"): el segundo de tecnología (reserva, del banco) y las de Latinoamérica que falten. Toma el turno pesado,
corre como producción (Claude y voz reales) y manda cada uno con ✅ Publicar / ❌ Cancelar como siempre.

Uso (en la Pi): PYTHONPATH=. .venv/bin/python scripts/armar_faltantes.py [--tec N] [--latam N]
"""
import argparse
import logging
import sys
from datetime import datetime

import clips_bot.__main__ as m
from clips_bot import db, gemini, reserva_tec
from clips_bot.config import DB_PATH, env, load_settings
from clips_bot.telegram import TelegramClient


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tec", type=int, default=1)
    ap.add_argument("--latam", type=int, default=2)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    gemini.fijar_origen(gemini.PRODUCCION)
    settings = load_settings()
    conn = db.connect(DB_PATH)
    tg = TelegramClient(env("TELEGRAM_BOT_TOKEN"))
    hoy = datetime.now(m.AR).date()
    turno = "manual:faltantes"
    if not db.tomar_turno(conn, db.RECURSO_PESADO, turno, maximo=1, vencimiento_s=m.VENCIMIENTO_PESADO_S):
        print("el turno pesado está ocupado")
        return 1
    try:
        chats_tec = [c.strip() for c in settings.efemerides.chat.split(",") if c.strip()] or db.destinos(conn)
        for intento in range(4):          # hasta que entre uno en la reserva o 4 intentos
            if a.tec <= 0:
                break
            if not reserva_tec.leer(conn):
                err = m._reserva_armar(conn, tg, settings, hoy)
                print("tecnología:", err or "armado")
            item = reserva_tec.sacar_primero(conn)
            if item and m._entregar_de_reserva(conn, tg, chats_tec, settings, item):
                a.tec -= 1
        chats = [c.strip() for c in settings.historias_fb.chat.split(",") if c.strip()] or db.destinos(conn)
        for k in range(a.latam):
            err = m._fb_proponer(conn, tg, chats, hoy, settings, **m._sin_aprobar(settings))
            print("latinoamérica:", err or "propuesta mandada")
            if err:
                break
    finally:
        db.soltar_turno(conn, db.RECURSO_PESADO, turno, m.VENCIMIENTO_PESADO_S)
    return 0


if __name__ == "__main__":
    sys.exit(main())
