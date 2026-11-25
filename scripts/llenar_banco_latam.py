"""Llena el banco de Latinoamérica por tema con la búsqueda web de Haiku (Santi, 2026-11-25). Producción (no prueba)."""
import logging
import sys
from datetime import date
from pathlib import Path

from clips_bot import banco, db, gemini as gemini_mod
from clips_bot.__main__ import DB_PATH, _puntuador
from clips_bot.web_historias import cliente_web
from clips_bot.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
settings = load_settings()
conn = db.connect(DB_PATH)
tope = float(sys.argv[1]) if len(sys.argv) > 1 else 0.70
with gemini_mod.origen(gemini_mod.PRODUCCION):
    from clips_bot import presupuesto

    antes = presupuesto.gasto_hoy(conn, date.today().isoformat())
    punt, web = _puntuador(settings), cliente_web()
    for tema in banco.TEMAS_BANCO_LATAM:
        if presupuesto.gasto_hoy(conn, date.today().isoformat()) - antes > tope:
            print("tope de gasto de la cosecha")
            break
        nuevos = banco.cosechar_latam_web(conn, web, punt, tema, date.today(), print)
        n = banco.agregar(conn, "latam", nuevos)
        print(f"== {tema[:20]}: +{n} (banco {len(banco.leer(conn, 'latam'))})", flush=True)
    print(f"gasto: US$ {presupuesto.gasto_hoy(conn, date.today().isoformat()) - antes:.2f}")
