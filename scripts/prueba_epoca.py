"""Calibración de la época de fotos_primero (Santi, 2026-11-25): solo el paso de fotos (Haiku) sobre las 6 historias de
la prueba, sin guion ni video. CLIPS_CLAUDE_REAL=1 PYTHONPATH=. .venv/bin/python scripts/prueba_epoca.py"""
from __future__ import annotations

import json

from clips_bot import banco as banco_mod, claude, db
from clips_bot import efemerides as ef
from clips_bot import fotos_primero as fp
from clips_bot.config import DB_PATH, OUTPUT_DIR, load_settings
import clips_bot.__main__ as m

NOKIA = {"lang": "es", "anio": 1865, "articulo": "Nokia", "paginas": ["Nokia"],
         "texto": "1865 a orillas del río Nokianvirta, en Finlandia, Fredrik Idestam funda un molino de papel: el "
                  "origen de Nokia, que hizo papel, botas de goma y cables antes de los celulares."}


def main() -> None:
    conn = db.connect(DB_PATH)
    haiku = m._puntuador(load_settings())
    wiki = ef.Wiki()
    tec = {x["articulo"]: x for x in banco_mod.leer(conn, "tecnologia")}
    latam = {x["articulo"]: x for x in banco_mod.leer(conn, "latam")}
    historias = [tec.get("Microsoft"), tec.get("Walkman"), NOKIA] + [latam.get(a) for a in (
        "Ciudad de Santa Fe (Argentina)", "Estación Concordia Central", "CYL", "Tabasco (México)")]
    fila0 = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM gemini_uso").fetchone()[0]
    out = []
    for it in historias:
        if not it:
            continue
        e = ef.Evento(it.get("lang", "es"), int(it["anio"]), it["texto"], list(it["paginas"]))
        fotos, _ = ef.fotos_del_evento(wiki, e)
        fuente = ef.texto_fuente(wiki, e)
        lugar = (it.get("clasif") or {}).get("lugar", "")
        carpeta = OUTPUT_DIR / "prueba_epoca" / it["articulo"].replace("/", "_")
        print(f"== {it['anio']} {it['articulo']}", flush=True)
        try:
            b = fp.juntar(wiki, haiku, e, fotos, carpeta, f"{lugar}: {it['texto']} {fuente[:900]}", print)
            out.append((it["articulo"], len(b.buenas), b.motivos))
        except fp.FotosPrevias as err:
            out.append((it["articulo"], err.buenas, err.motivos))
    costo = sum(claude.costo(mo, e_ or 0, s or 0) for mo, e_, s in conn.execute(
        "SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND rowid > ?", (fila0,)))
    for a, n, mot in out:
        print(f"RESULTADO {a}: {n} buenas {'✅' if n >= fp.MINIMO else '❌'} {mot}")
    print(f"COSTO US$ {costo:.3f}")


if __name__ == "__main__":
    main()
