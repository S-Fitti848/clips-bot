"""Compara los rasterizadores en ESTA máquina con cuadros reales del demo (un solo proceso).

    python -m clips_bot.animacion.bench [--cuadros 30] [--escala 1]

Para cada rasterizador disponible mide, en segundos por cuadro:
  frente   solo lo que se mueve (personajes, props, texto) sobre transparente
  fondo    un fondo entero (lo que se ahorra el caché)
  cuadro   el cuadro completo como lo arma el render (fondo cacheado + cámara + frente + subtítulos)
  sin_cache el cuadro completo dibujando el fondo vectorial cada vez
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

from . import render as rd
from .demo import armar
from .timeline import Video


def medir(nombre: str, video: Video, indices: list[int], escala: float) -> dict:
    w = int(round(1080 * escala / 2)) * 2
    h = int(round(1920 * escala / 2)) * 2
    out = {}
    rd._iniciar(nombre, w, h, True)
    r = rd._W["r"]
    cuadros = [video.cuadro(i) for i in indices]
    # fondo entero (sin caché)
    t = []
    for fondo in sorted({c.a.fondo for c in cuadros}):
        a = time.perf_counter()
        r.rgba(rd._doc(rd._svg_fondo(fondo)), w, h)
        t.append(time.perf_counter() - a)
    out["fondo"] = statistics.mean(t)
    t = []
    for c in cuadros:
        cuerpo = rd._svg_camara(c.a.frente, c.a.camara) + c.a.fijo + c.encima
        a = time.perf_counter()
        r.rgba(rd._doc(cuerpo), w, h)
        t.append(time.perf_counter() - a)
    out["frente"] = statistics.mean(t)
    for c in cuadros[:2]:      # calentar el caché de fondos
        rd.componer(c)
    t = []
    for c in cuadros:
        a = time.perf_counter()
        rd.componer(c)
        t.append(time.perf_counter() - a)
    out["cuadro"] = statistics.mean(t)
    rd._iniciar(nombre, w, h, False)
    t = []
    for c in cuadros:
        a = time.perf_counter()
        rd.componer(c)
        t.append(time.perf_counter() - a)
    out["sin_cache"] = statistics.mean(t)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cuadros", type=int, default=30)
    ap.add_argument("--escala", type=float, default=1.0)
    ap.add_argument("--rasterizadores", default="")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        datos, _ = armar(45, Path(tmp), usar_piper=False)
        video = Video.desde_dict(datos)
    paso = max(1, video.total_cuadros // a.cuadros)
    indices = list(range(5, video.total_cuadros, paso))[: a.cuadros]
    nombres = [x for x in a.rasterizadores.split(",") if x] or rd.disponibles()
    print(f"{len(indices)} cuadros del demo, escala {a.escala}; rasterizadores: {nombres}")
    print(f"{'rasterizador':14} {'frente':>8} {'fondo':>8} {'cuadro':>8} {'sin_cache':>10}  (s/cuadro)")
    for nombre in nombres:
        try:
            m = medir(nombre, video, indices, a.escala)
        except Exception as e:
            print(f"{nombre:14} falló: {e}")
            continue
        temp = rd.temperatura()
        print(f"{nombre:14} {m['frente']:8.3f} {m['fondo']:8.3f} {m['cuadro']:8.3f} "
              f"{m['sin_cache']:10.3f}" + (f"   ({temp} °C)" if temp else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
