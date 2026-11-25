"""Prueba de "fotos primero" (Santi, 2026-11-25): 3 historias con el sistema nuevo, dentro del tope de pruebas de
US$ 1, armadas y revisadas como la reserva (sin mandar nada). Una de tecnología del banco, una de Latinoamérica y una
de las que fallaron esta semana (Nokia). Correr en la Pi con CLIPS_CLAUDE_REAL=1 (Santi lo pidió con el tope de US$ 1):

    CLIPS_CLAUDE_REAL=1 PYTHONPATH=. .venv/bin/python scripts/prueba_fotos_primero.py [tec|latam|nokia ...]

Cada historia toma el turno pesado (respeta la pausa para enfriar entre renders) y lo suelta al terminar. El resultado
queda en output/prueba_fotos_primero/resultado.json.
"""
from __future__ import annotations

import json
import secrets
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import clips_bot.__main__ as m
from clips_bot import banco as banco_mod, bitacora, claude, db
from clips_bot import efemerides as ef
from clips_bot import locales
from clips_bot.config import OUTPUT_DIR, env, load_settings
from clips_bot.telegram import TelegramClient

AR = ZoneInfo("America/Argentina/Buenos_Aires")
SALIDA = OUTPUT_DIR / "prueba_fotos_primero"
NOKIA = {"id": "tec:Nokia", "lang": "es", "anio": 1865, "articulo": "Nokia", "paginas": ["Nokia"], "puntaje": 8.25,
         "subtema": "marcas",
         "texto": "1865 a orillas del río Nokianvirta, en Finlandia, Fredrik Idestam funda un molino de papel: el "
                  "origen de Nokia, que hizo papel, botas de goma y cables antes de los celulares."}


def esperar_turno(conn) -> None:
    while not db.tomar_turno(conn, db.RECURSO_PESADO, "prueba:fotos_primero", maximo=1,
                             vencimiento_s=m.VENCIMIENTO_PESADO_S):
        print("esperando el turno pesado / la pausa para enfriar…", flush=True)
        time.sleep(60)


def armar(conn, tg, settings, cual: str) -> dict:
    hoy = datetime.now(AR).date()
    gemini = m._gemini(settings)
    cfg = settings.efemerides
    token = secrets.token_hex(3)
    carpeta = SALIDA / f"{cual}_{token}"
    bitacora.abrir(conn, token, "pequena_historia", "prueba_fotos_primero")
    t0 = time.time()
    fila0 = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM gemini_uso").fetchone()[0]
    comun = dict(avisar=print, videos=False, tope_fotos_s=cfg.tope_fotos_min * 60, imagen_frase=cfg.imagen_frase,
                 elector=m._elector_fotos(settings), elector_reintento=m._elector_fotos(settings, reintento=True),
                 mas_video=cfg.estilo_nuevo, puntuador=m._puntuador(settings), fotos_primero=True)
    try:
        if cual == "latam":  # noqa: SIM114
            sonnet, haiku = m._claude_textos(settings)
            ya = m._latam_del_dia(conn, hoy)
            p = locales.proponer(ef.Wiki(), sonnet, haiku, gemini, hoy, carpeta,
                                 corto=settings.historias_fb.formato_corto,
                                 excluir={v for x in ya for v in (x.get("texto"), x.get("articulo")) if v},
                                 evitar_paises={x["pais"] for x in ya if x.get("pais")}, web=None,
                                 banco=banco_mod.leer(conn, "latam"), solo_banco=True, **comun)
        else:
            if cual == "nokia":
                item = NOKIA
            else:      # "tec" = el primero del banco; "tec:Walkman" = ese artículo
                nombre = cual.split(":", 1)[1] if ":" in cual else ""
                banco_t = banco_mod.leer(conn, "tecnologia")
                item = next((x for x in banco_t if x.get("articulo") == nombre), banco_t[0])
            p = ef.proponer(ef.Wiki(), gemini, hoy, carpeta, tema="tecnologia", corto=cfg.corto,
                            texto=m._texto_efemeride(settings, gemini), banco=[item], solo_banco=True,
                            max_guiones=1, piso_fotos=0.60, **comun)
    except Exception as e:  # noqa: BLE001
        bitacora.cerrar(conn, "fallido")
        return {"cual": cual, "error": f"propuesta: {str(e)[:300]}", "costo": costo_desde(conn, fila0)}
    estado = {"propuesta": p.__dict__, "carpeta": str(carpeta), "chat_id": ""}
    db.set_valor(conn, f"efe:{token}", json.dumps(estado, ensure_ascii=False))
    r = m._efe_armar(conn, tg, None, token, settings, auto=True, reserva=True)
    db.borrar_valor(conn, f"efe:{token}")
    if not isinstance(r, dict):
        bitacora.cerrar(conn, "fallido")
        return {"cual": cual, "error": f"video: {str(r)[:300]}", "costo": costo_desde(conn, fila0)}
    from clips_bot import calidad

    ok, total = calidad.puntaje("pequena_historia", r["fallas"])
    pasa = r["revisado"] and not calidad.retener("pequena_historia", r["fallas"], True) \
        and (r.get("fotos_pct") or 0) >= ef.UMBRAL_FOTOS_REALES - 1e-9
    bitacora.cerrar(conn, "descartado")
    meta = json.loads(open(r["meta"], encoding="utf-8").read())
    return {"cual": cual, "titulo": r.get("titulo"), "pasa": bool(pasa), "estandar": f"{ok}/{total}",
            "fallas": [f.get("id") for f in r["fallas"]], "fotos_pct": r.get("fotos_pct"),
            "video": meta.get("salida") or meta.get("video") or "", "meta": r["meta"], "clip_id": r["clip_id"],
            "costo": costo_desde(conn, fila0), "minutos": round((time.time() - t0) / 60, 1)}


def costo_desde(conn, fila0: int) -> float:
    return round(sum(claude.costo(mo, e or 0, s or 0) for mo, e, s in conn.execute(
        "SELECT modelo, entrada, salida FROM gemini_uso WHERE clave = 'claude' AND rowid > ?", (fila0,))), 3)


def main() -> None:
    settings = load_settings()
    conn = db.connect(m.DB_PATH)
    tg = TelegramClient(env("TELEGRAM_BOT_TOKEN"))
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / "resultado.json"
    resultados = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
    for cual in sys.argv[1:] or ["tec", "latam", "nokia"]:
        gastado = claude.gasto_pruebas_hoy(conn) if hasattr(claude, "gasto_pruebas_hoy") else 0
        print(f"== {cual} (pruebas de hoy: US$ {gastado:.2f})", flush=True)
        esperar_turno(conn)
        try:
            r = armar(conn, tg, settings, cual)
        finally:
            db.soltar_turno(conn, db.RECURSO_PESADO, "prueba:fotos_primero")
        print(json.dumps(r, ensure_ascii=False), flush=True)
        resultados.append(r)
        ruta.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
