"""Freno por calor de la Pi (Santi, 2026-11-24: "se colgó por calor; hasta que resuelva el enfriamiento, que frene si
pasa de 80 °C").

Servicio de usuario que mira la temperatura cada INTERVALO_S. Al llegar a FRENA_C congela (SIGSTOP) todos los ffmpeg
del usuario (los renders de clips y de Lo Encontré: lo que más calienta) y los suelta (SIGCONT) recién al bajar a
SUELTA_C. El render no se pierde: sigue donde quedó. Si el servicio se detiene o se cae, ExecStopPost suelta todo.

Además deja la temperatura de cada minuto en `data/temperatura.log` (el journal de la Pi no sobrevive un corte: así,
si se vuelve a colgar, se sabe a cuánto llegó y qué corría).

`python -m clips_bot.freno_calor [--soltar]`."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

FRENA_C = 80.0
SUELTA_C = 72.0
INTERVALO_S = 2.0
TERMICO = Path("/sys/class/thermal/thermal_zone0/temp")
REGISTRO = Path("/home/santi/clips/data/temperatura.log")
REGISTRO_MAX = 2_000_000            # ~2 MB (unas 2-3 semanas de una línea por minuto); después se rota a .1
PROCESOS = ("ffmpeg",)

log = logging.getLogger("freno_calor")


def temperatura(ruta: Path = TERMICO) -> float | None:
    try:
        return int(ruta.read_text().strip()) / 1000
    except (OSError, ValueError):
        return None


def decidir(frenado: bool, temp: float | None) -> bool:
    """¿Tienen que quedar congelados? Con histéresis: congela desde FRENA_C, suelta debajo de SUELTA_C. Sin lectura de
    temperatura, suelta (no frena a ciegas)."""
    if temp is None:
        return False
    if temp >= FRENA_C:
        return True
    if temp <= SUELTA_C:
        return False
    return frenado


def pids(nombres=PROCESOS) -> list[int]:
    out = []
    for n in nombres:
        r = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", n], capture_output=True, text=True, timeout=10)
        out += [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    return out


def senal(lista: list[int], sig) -> int:
    n = 0
    for p in lista:
        try:
            os.kill(p, sig)
            n += 1
        except (ProcessLookupError, PermissionError):
            pass
    return n


def anotar(linea: str, ruta: Path = REGISTRO) -> None:
    try:
        if ruta.exists() and ruta.stat().st_size > REGISTRO_MAX:
            ruta.replace(ruta.with_suffix(".log.1"))
        with ruta.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def que_corre() -> str:
    """El turno pesado de ahora (quién renderiza), para el registro."""
    try:
        from . import db
        from .config import DB_PATH

        conn = db.connect(DB_PATH)
        try:
            return db.hay_trabajo_pesado(conn, 3 * 3600) or "-"
        finally:
            conn.close()
    except Exception:
        return "?"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--soltar", action="store_true", help="suelta todo lo congelado y sale")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.soltar:
        log.info("soltados %d", senal(pids(), signal.SIGCONT))
        return
    frenado, ultimo_min, maxima = False, "", 0.0
    while True:
        t = temperatura()
        nuevo = decidir(frenado, t)
        if nuevo:
            senal(pids(), signal.SIGSTOP)      # también los que arrancan mientras está frenado
        if nuevo != frenado:
            if not nuevo:
                senal(pids(), signal.SIGCONT)
            msg = f"{'FRENO' if nuevo else 'SUELTO'} a {t:.1f} °C ({que_corre()})"
            log.info(msg)
            anotar(time.strftime("%Y-%m-%d %H:%M:%S ") + msg)
            frenado = nuevo
        maxima = max(maxima, t or 0.0)
        minuto = time.strftime("%Y-%m-%d %H:%M")
        if minuto != ultimo_min:
            if ultimo_min:
                anotar(f"{minuto} {maxima:.1f} {'frenado' if frenado else ''} {que_corre()}".rstrip())
            ultimo_min, maxima = minuto, 0.0
        time.sleep(INTERVALO_S)


if __name__ == "__main__":
    main()
