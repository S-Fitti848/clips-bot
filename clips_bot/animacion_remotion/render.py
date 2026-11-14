"""Datos por cuadro → mp4 con Remotion (Chrome headless) → audio del motor actual pegado con ffmpeg.

Mide lo que pide Santi para decidir si sirve en la Pi: tiempo total, segundos por cuadro, temperatura
(antes, máxima y después), `get_throttled` y la memoria usada (mínimo de MemAvailable durante el render).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from clips_bot.animacion.render import temperatura, throttled


def _mem_disponible_mb() -> float | None:
    try:
        for linea in Path("/proc/meminfo").read_text().splitlines():
            if linea.startswith("MemAvailable:"):
                return int(linea.split()[1]) / 1024
    except Exception:
        return None
    return None


class Monitor(threading.Thread):
    """Temperatura, throttling y memoria disponible cada `cada_s` segundos mientras dura el render."""

    def __init__(self, cada_s: float = 5.0):
        super().__init__(daemon=True)
        self.cada_s = cada_s
        self.temps: list[float] = []
        self.mem: list[float] = []
        self.throttled: set[str] = set()
        self._fin = threading.Event()

    def run(self):
        while not self._fin.is_set():
            t = temperatura()
            if t is not None:
                self.temps.append(t)
            m = _mem_disponible_mb()
            if m is not None:
                self.mem.append(m)
            th = throttled()
            if th:
                self.throttled.add(th)
            self._fin.wait(self.cada_s)

    def parar(self):
        self._fin.set()
        self.join(timeout=10)


def npx() -> str:
    return shutil.which("npx") or "npx"


def renderizar(datos: Path, proyecto: Path, salida: Path, audio: Path | None = None, concurrencia: int = 2,
               crf: int = 22, frames: str | None = None, escala: float = 1.0, timeout_s: int = 3600,
               log=print) -> dict:
    """Renderiza `datos` (JSON de exportar.py) con el proyecto Remotion de `proyecto` (con node_modules).
    Devuelve las mediciones. Con `audio`, el mp4 final lleva ese wav (sin cortar: dura lo mismo)."""
    proyecto, salida, datos = Path(proyecto), Path(salida), Path(datos)
    nombre = f"datos_{datos.stem}.json"
    shutil.copyfile(datos, proyecto / "public" / nombre)
    mudo = salida.with_name(salida.stem + "_mudo.mp4")
    cmd = [npx(), "remotion", "render", "src/index.ts", "AsiNacio", str(mudo.resolve()),
           f"--props={json.dumps({'archivo': nombre})}", f"--concurrency={concurrencia}", "--muted",
           "--codec=h264", f"--crf={crf}", "--log=info"]
    if frames:
        cmd.append(f"--frames={frames}")
    if escala != 1.0:
        cmd.append(f"--scale={escala}")
    t_antes, th_antes = temperatura(), throttled()
    mon = Monitor()
    mon.start()
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=proyecto, capture_output=True, text=True, timeout=timeout_s,
                           env={**os.environ, "NODE_OPTIONS": os.environ.get("NODE_OPTIONS", "--max-old-space-size=2048")})
    finally:
        mon.parar()
    dur = time.time() - t0
    if r.returncode != 0:
        raise RuntimeError(f"remotion render falló ({r.returncode}): {(r.stderr or r.stdout)[-3000:]}")
    n = json.loads(datos.read_text(encoding="utf-8"))
    cuadros = len(n["cuadros"])
    if frames:
        a, _, b = frames.partition("-")
        cuadros = int(b or a) - int(a) + 1
    if audio:
        from clips_bot.media import find_bin

        subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mudo),
                        "-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "192k", "-movflags", "+faststart", str(salida)], check=True, timeout=300)
        mudo.unlink(missing_ok=True)
    else:
        mudo.replace(salida)
    out = {"render_s": round(dur, 1), "cuadros": cuadros, "s_por_cuadro": round(dur / max(1, cuadros), 3),
           "concurrencia": concurrencia, "temp_antes": t_antes,
           "temp_max": max(mon.temps) if mon.temps else None,
           "temp_media": round(sum(mon.temps) / len(mon.temps), 1) if mon.temps else None,
           "temp_despues": temperatura(), "throttled_antes": th_antes,
           "throttled_durante": sorted(mon.throttled), "throttled_despues": throttled(),
           "mem_disponible_min_mb": round(min(mon.mem)) if mon.mem else None, "salida": str(salida)}
    log(json.dumps(out, ensure_ascii=False))
    return out
