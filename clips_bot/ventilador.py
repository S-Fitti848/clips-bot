"""Control del ventilador Pimoroni Fan SHIM (GPIO 18) en la Pi (Santi, 2026-11-14).

Prende desde PRENDE_C (55 °C) y apaga recién por debajo de APAGA_C (48 °C): la histéresis evita que
prenda y apague a cada rato. Además queda SIEMPRE prendido mientras hay un render: el turno pesado
compartido (clips, Así Nació y Lo Encontré lo usan; `db.hay_trabajo_pesado`). El pin se maneja con
`pinctrl` (el usuario está en el grupo `gpio`: no hace falta sudo).

Corre como servicio de usuario (`deploy/ventilador.service`, con linger: arranca solo con la Pi). Si
el servicio se detiene, el pin queda en ALTO (ventilador prendido): ante la duda, mejor prendido.

`python -m clips_bot.ventilador [--una-vez]`."""

from __future__ import annotations

import argparse
import logging
import subprocess
import time
from pathlib import Path

PIN = 18
PRENDE_C = 55.0
APAGA_C = 48.0
INTERVALO_S = 3.0
TERMICO = Path("/sys/class/thermal/thermal_zone0/temp")
DB = Path("/home/santi/clips/data/clips.db")

log = logging.getLogger("ventilador")


def temperatura(ruta: Path = TERMICO) -> float | None:
    try:
        return int(ruta.read_text().strip()) / 1000
    except (OSError, ValueError):
        return None


def decidir(prendido: bool, temp: float | None, render: bool) -> bool:
    """El estado que tiene que tener el ventilador. Sin temperatura (no se pudo leer), prendido."""
    if render or temp is None:
        return True
    if temp >= PRENDE_C:
        return True
    if temp < APAGA_C:
        return False
    return prendido          # entre 48 y 55 °C se queda como está (histéresis)


def poner(prendido: bool, pinctrl: str = "pinctrl") -> None:
    subprocess.run([pinctrl, "set", str(PIN), "op", "dh" if prendido else "dl"], check=True, timeout=10)


def hay_render(db_path: Path = DB) -> bool:
    try:
        from . import db

        conn = db.connect(db_path)
        try:
            return db.hay_trabajo_pesado(conn, 3 * 3600) is not None
        finally:
            conn.close()
    except Exception as e:      # la base ocupada o rota: ante la duda, como si hubiera render
        log.warning("no pude leer el turno pesado: %s", e)
        return True


def bucle(una_vez: bool = False) -> None:
    prendido = None
    while True:
        temp, render = temperatura(), hay_render()
        quiero = decidir(bool(prendido), temp, render)
        if quiero != prendido:
            poner(quiero)
            log.info("ventilador %s (%.1f °C%s)", "PRENDIDO" if quiero else "apagado",
                     temp if temp is not None else -1, ", render" if render else "")
            prendido = quiero
        if una_vez:
            return
        time.sleep(INTERVALO_S)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Control del Fan SHIM (GPIO 18).")
    ap.add_argument("--una-vez", action="store_true", help="decide y sale (para probar)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    bucle(a.una_vez)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
