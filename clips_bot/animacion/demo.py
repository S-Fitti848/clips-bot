"""Video de muestra (~45 s): narrador hablando, secundarios, 4 fondos, props, gancho, subtítulos,
cámara y las 4 transiciones. Todo armado como DATOS (el mismo dict que podría escribir un modelo).

    python -m clips_bot.animacion.demo --salida output/animacion/demo.mp4 [--segundos 45]
        [--rasterizador auto|resvg|cairosvg|rsvg-convert] [--procesos 2] [--escala 1]
        [--sin-piper] [--png 30,400] [--json guion.json]

Voz: Piper si está (ANIM_VOZ o ~/clips/voces/es_AR-daniela-high.onnx); si no, un "bla bla"
sintético con los mismos tiempos, para ver la boca y tener audio.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import audio as au
from . import render as rd
from .timeline import Video

N = "narrador"

# (frase que se dice, escena sin duración ni subtítulos)
GUION: list[tuple[str, dict]] = [
    ("¿Sabés por qué las monedas tienen rayitas en el borde?", {
        "fondo": {"tipo": "cielo", "semilla": 1},
        "camara": [{"t": 0, "zoom": 1.0}, {"t": 6, "zoom": 1.08, "y": 40, "easing": "suave"}],
        "elementos": [
            {"tipo": "personaje", "nombre": N, "x": 540, "y": 1780, "escala": 1.15, "habla": True,
             "entrada": "abajo", "gestos": [{"t": 0, "gesto": "saludar"},
                                            {"t": 1.6, "gesto": "explicar"}]},
            {"tipo": "gancho", "texto": "¿Por qué las monedas tienen rayitas?", "y": 380,
             "modo": "palabras"},
        ]}),
    ("Hace siglos, las monedas eran de oro y plata de verdad.", {
        "fondo": {"tipo": "ciudad", "semilla": 2},
        "transicion": {"tipo": "zoom", "duracion": 0.45},
        "elementos": [
            {"tipo": "personaje", "nombre": N, "x": 330, "y": 1760, "habla": True,
             "gestos": [{"t": 0.3, "gesto": "senalar"}]},
            {"tipo": "prop", "nombre": "moneda", "x": 790, "y": 760, "escala": 1.3,
             "entrada": "rebote", "desde": 0.4,
             "keyframes": [{"t": 0.9, "rotacion": 0},
                           {"t": 6, "rotacion": 40, "easing": "suave"}]},
            {"tipo": "texto", "texto": "ORO", "x": 790, "y": 1000, "tam": 110,
             "color": "#ffd23f", "entrada": "rebote", "desde": 1.2},
        ]}),
    ("Y había gente que limaba un poquito del borde para quedarse con el metal.", {
        "fondo": {"tipo": "oficina", "semilla": 3},
        "transicion": {"tipo": "barrido", "duracion": 0.4},
        "elementos": [
            {"tipo": "personaje", "nombre": "abuelo", "x": 760, "y": 1790, "escala": 1.0,
             "entrada": "derecha", "gestos": [{"t": 0.8, "gesto": "pensar"}],
             "keyframes": [{"t": 0.5, "mirada": 0}, {"t": 1.5, "mirada": -1}]},
            {"tipo": "personaje", "nombre": N, "x": 290, "y": 1790, "escala": 0.95,
             "habla": True, "gestos": [{"t": 0, "gesto": "senalar"},
                                       {"t": 2.5, "gesto": "encogerse"}],
             "keyframes": [{"t": 0, "mirada": 1}]},
            {"tipo": "prop", "nombre": "pregunta", "x": 900, "y": 820, "entrada": "rebote",
             "desde": 1.0, "keyframes": [{"t": 1.5, "rotacion": -8},
                                         {"t": 3, "rotacion": 8}, {"t": 4.5, "rotacion": -8}]},
        ]}),
    ("Pasaba en todo el mundo, y las monedas valían cada vez menos.", {
        "fondo": {"tipo": "globo", "semilla": 4},
        "transicion": {"tipo": "fundido", "duracion": 0.5},
        "camara": [{"t": 0, "zoom": 1.12}, {"t": 5.5, "zoom": 1.0, "easing": "suave"}],
        "elementos": [
            {"tipo": "personaje", "nombre": N, "x": 540, "y": 1860, "escala": 0.9, "habla": True,
             "gestos": [{"t": 0, "gesto": "explicar"}, {"t": 2.5, "gesto": "encogerse"}]},
            {"tipo": "prop", "nombre": "flecha", "x": 860, "y": 1260, "rotacion": 90,
             "entrada": "fundido", "desde": 2.0,
             "keyframes": [{"t": 2.0, "y": 1180}, {"t": 3.5, "y": 1300, "easing": "rebote"}]},
        ]}),
    ("Entonces a alguien se le ocurrió una idea brillante.", {
        "fondo": {"tipo": "cielo", "semilla": 5},
        "transicion": {"tipo": "zoom", "duracion": 0.45},
        "elementos": [
            {"tipo": "personaje", "nombre": N, "x": 540, "y": 1780, "escala": 1.1, "habla": True,
             "gestos": [{"t": 0, "gesto": "pensar"}, {"t": 1.4, "gesto": "sorpresa"}]},
            {"tipo": "prop", "nombre": "lamparita", "x": 540, "y": 560, "escala": 1.4,
             "entrada": "rebote", "desde": 1.3},
        ]}),
    ("Ponerles rayitas en el borde: si faltaba una, se notaba al toque.", {
        "fondo": {"tipo": "ciudad", "semilla": 6},
        "transicion": {"tipo": "barrido", "duracion": 0.4},
        "camara": [{"t": 0, "zoom": 1.0}, {"t": 3, "zoom": 1.1, "x": 120, "easing": "suave"},
                   {"t": 6, "zoom": 1.0, "x": 0, "easing": "suave"}],
        "elementos": [
            {"tipo": "prop", "nombre": "cartel", "texto": "RAYITAS", "x": 540, "y": 700,
             "escala": 1.2, "entrada": "arriba"},
            {"tipo": "personaje", "nombre": "vecina", "x": 830, "y": 1800, "escala": 0.9,
             "entrada": "derecha", "desde": 0.6, "gestos": [{"t": 1.5, "gesto": "sorpresa"}]},
            {"tipo": "personaje", "nombre": "pibe", "x": 560, "y": 1840, "escala": 0.85,
             "entrada": "abajo", "desde": 1.0, "gestos": [{"t": 2.0, "gesto": "saludar"}]},
            {"tipo": "personaje", "nombre": N, "x": 250, "y": 1780, "escala": 0.95,
             "habla": True, "gestos": [{"t": 0, "gesto": "explicar"},
                                       {"t": 2.2, "gesto": "senalar"}]},
        ]}),
    ("Hoy ya no son de oro, pero las rayitas quedaron.", {
        "fondo": {"tipo": "oficina", "semilla": 7},
        "transicion": {"tipo": "fundido", "duracion": 0.4},
        "elementos": [
            {"tipo": "prop", "nombre": "moneda", "x": 760, "y": 900, "escala": 1.6,
             "entrada": "rebote", "keyframes": [{"t": 0.5, "rotacion": 0},
                                                {"t": 5, "rotacion": -30}]},
            {"tipo": "prop", "nombre": "exclamacion", "x": 930, "y": 640, "escala": 0.6,
             "entrada": "rebote", "desde": 1.8},
            {"tipo": "personaje", "nombre": N, "x": 330, "y": 1790, "habla": True,
             "gestos": [{"t": 0, "gesto": "encogerse"}, {"t": 2.0, "gesto": "senalar"}]},
        ]}),
    ("Y ahora, cada vez que veas una, te vas a acordar. ¡Seguinos para más!", {
        "fondo": {"tipo": "cielo", "semilla": 8},
        "transicion": {"tipo": "zoom", "duracion": 0.45},
        "camara": [{"t": 0, "zoom": 1.1}, {"t": 6, "zoom": 1.0, "easing": "suave"}],
        "elementos": [
            {"tipo": "personaje", "nombre": N, "x": 540, "y": 1780, "escala": 1.15, "habla": True,
             "gestos": [{"t": 0, "gesto": "explicar"}, {"t": 2.6, "gesto": "saludar"}]},
            {"tipo": "gancho", "texto": "¡Seguinos!", "y": 420, "modo": "rebote", "tam": 150,
             "desde": 2.6},
        ]}),
]

PAUSA_S = 0.45
INICIO_S = 0.3


def armar(segundos: float, carpeta: Path, usar_piper: bool = True) -> tuple[dict, str]:
    """El dict del video + la voz (wav en `carpeta`). Devuelve también qué voz se usó."""
    carpeta.mkdir(parents=True, exist_ok=True)
    frases = [f for f, _ in GUION]
    modelo = au.modelo_piper() if usar_piper else None
    wav = carpeta / "voz.wav"
    if modelo:
        wav, tiempos = au.piper_frases(frases, modelo, wav, pausa_s=PAUSA_S, inicio_s=INICIO_S)
        motor = f"piper ({modelo.name})"
    else:
        # tiempos estimados (~2,6 palabras/s) y escalados para llegar a `segundos`
        largos = [len(f.split()) / 2.6 for f in frases]
        esc = (segundos - INICIO_S - PAUSA_S * len(frases)) / sum(largos)
        tiempos, t = [], INICIO_S
        for d in largos:
            tiempos.append((t, t + d * esc))
            t += d * esc + PAUSA_S
        motor = "sintética"
    # cada escena va del arranque de su frase al arranque de la siguiente
    cortes = [0.0] + [tiempos[i + 1][0] - 0.15 for i in range(len(tiempos) - 1)]
    fin = max(segundos, tiempos[-1][1] + 1.2)
    escenas = []
    for i, (_, esc_d) in enumerate(GUION):
        dur = (cortes[i + 1] if i + 1 < len(cortes) else fin) - cortes[i]
        escenas.append({**esc_d, "duracion": round(dur, 3)})
    if not modelo:
        au.voz_de_prueba(wav, tiempos, fin)
    subs = [{"texto": f, "inicio": round(a, 3), "fin": round(b, 3)}
            for f, (a, b) in zip(frases, tiempos)]
    return {"fps": 30, "audio": str(wav), "subtitulos": subs, "escenas": escenas}, motor


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--segundos", type=float, default=45)
    ap.add_argument("--rasterizador", default="auto")
    ap.add_argument("--procesos", type=int, default=2)
    ap.add_argument("--escala", type=float, default=1.0)
    ap.add_argument("--crf", type=int, default=22)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--hilos-x264", type=int, default=None)
    ap.add_argument("--sin-cache-fondo", action="store_true")
    ap.add_argument("--sin-piper", action="store_true")
    ap.add_argument("--png", default="", help="índices de cuadros para guardar como PNG")
    ap.add_argument("--json", default="", help="guardar el guion (dict) acá")
    a = ap.parse_args(argv)

    salida = Path(a.salida)
    carpeta = salida.with_suffix("")
    carpeta = carpeta.parent / (carpeta.name + "_trabajo")
    t0 = time.perf_counter()
    datos, motor = armar(a.segundos, carpeta, not a.sin_piper)
    print(f"voz: {motor} ({time.perf_counter() - t0:.1f} s)", flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    video = Video.desde_dict(datos)
    print(f"{len(video.escenas)} escenas, {video.duracion:.1f} s, {video.total_cuadros} cuadros",
          flush=True)
    for idx in [int(x) for x in a.png.split(",") if x.strip()]:
        rd.cuadro_png(video, idx, salida.parent / f"{salida.stem}_cuadro{idx:04d}.png",
                      a.rasterizador, a.escala)

    ultimo = [0.0]

    def progreso(i, total):
        if time.perf_counter() - ultimo[0] > 15 or i == total:
            ultimo[0] = time.perf_counter()
            print(f"  {i}/{total} cuadros ({time.perf_counter() - t0:.0f} s)", flush=True)

    hilos = a.hilos_x264 if a.hilos_x264 is not None else rd.hilos_x264_defecto()
    r = rd.renderizar(video, salida, a.rasterizador, a.procesos, a.escala, a.crf, a.preset,
                      hilos, not a.sin_cache_fondo, progreso=progreso)
    print(r.resumen(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
