"""Versión con gameplay abajo (pedido de Santi, 2026-10-04). OPCIONAL, nunca por defecto: debajo de
los clips de charla sale el botón "🎮 Versión con gameplay", que arma OTRA versión con el streamer
arriba y un tramo al azar de un video de `gameplay/` abajo (videos que graba Santi; la carpeta está
fuera de git). Sin audio del juego: solo el del clip.

Arriba: el clip a pantalla completa en su mitad (1080x960), recortado hacia las caras; si las caras
(con margen) no entran en ese recorte, el clip entero escalado sobre su mismo fondo difuminado, como
el fit_blur. Abajo: el gameplay recortado al centro. Subtítulos y título, los del clip.
"""

from __future__ import annotations

import random
from pathlib import Path

from .media import cola_audio, find_bin, probe, run

CARPETA = Path("gameplay")
EXTENSIONES = (".mp4", ".mov", ".mkv", ".webm")


def videos(carpeta: Path = CARPETA) -> list[Path]:
    if not carpeta.is_dir():
        return []
    return sorted(p for p in carpeta.iterdir() if p.suffix.lower() in EXTENSIONES)


def es_charla(meta: dict, categorias_charla: tuple) -> bool:
    return (meta.get("categoria") or "") in categorias_charla


def disponible(meta: dict, categorias_charla: tuple, carpeta: Path = CARPETA) -> bool:
    """El botón sale solo en clips de charla de un streamer, con el original guardado y gameplay."""
    return (bool(meta.get("streamer")) and not meta.get("efemeride") and es_charla(meta, categorias_charla)
            and bool(meta.get("raw")) and bool(videos(carpeta)))


def elegir_tramo(lista: list[Path], duracion: float, rng=random) -> tuple[Path, float]:
    """Un video al azar que alcance, y un inicio al azar dentro de él."""
    largos = [(p, probe(p).duracion or 0) for p in lista]
    sirven = [(p, d) for p, d in largos if d >= duracion + 1] or [max(largos, key=lambda x: x[1])]
    p, d = rng.choice(sirven)
    return p, round(rng.uniform(0, max(d - duracion, 0)), 2)


def filtro(W: int, H: int, ancho: int, alto: int, zona: tuple | None, blur_sigma: float,
           con_subs: bool, con_titulo: bool, fps: int) -> str:
    """[0:v] = clip, [1:v] = gameplay. Mitad de arriba el streamer, mitad de abajo el juego."""
    mitad = H // 2
    ratio = W / mitad
    vis_w = alto * ratio                     # el recorte de arriba usa todo el alto del clip
    cabe = vis_w <= ancho and (zona is None or (zona[2] - zona[0]) * ancho <= vis_w)
    if cabe:
        cx = ((zona[0] + zona[2]) / 2 * ancho) if zona else ancho / 2
        x = int(min(max(cx - vis_w / 2, 0), ancho - vis_w)) // 2 * 2
        arriba = (f"[0:v]crop={int(vis_w) // 2 * 2}:{alto // 2 * 2}:{x}:0,"
                  f"scale={W}:{mitad}:flags=lanczos,setsar=1[arriba]")
    else:   # las caras no entran: el clip entero sobre su fondo difuminado (sin cortar a nadie)
        arriba = (f"[0:v]split=2[a1][a2];[a1]scale={W}:{mitad}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{mitad},gblur=sigma={blur_sigma}[afondo];"
                  f"[a2]scale={W}:{mitad}:force_original_aspect_ratio=decrease,setsar=1[afrente];"
                  f"[afondo][afrente]overlay=(W-w)/2:(H-h)/2[arriba]")
    abajo = (f"[1:v]scale={W}:{H - mitad}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H - mitad},setsar=1[abajo]")
    final = f"fps={fps}" + (",ass=subs.ass" if con_subs else "") + (",ass=titulo.ass" if con_titulo else "")
    return f"{arriba};{abajo};[arriba][abajo]vstack=inputs=2,{final}[v]"


def renderizar(clip: Path, juego: Path, inicio_juego: float, salida: Path, render, zona: tuple | None,
               dir_trabajo: Path | None, con_subs: bool, con_titulo: bool) -> Path:
    info = probe(clip)
    dur = min(info.duracion or render.duracion_max_s, render.duracion_max_s)
    grafo = filtro(render.ancho, render.alto, info.ancho, info.alto, zona, render.blur_sigma,
                   con_subs, con_titulo, render.fps)
    audio = []
    if info.tiene_audio:    # solo el audio del clip: el del juego no entra nunca
        grafo += f";[0:a]{cola_audio(dur)}[a]"
        audio = ["-map", "[a]"]
    salida.parent.mkdir(parents=True, exist_ok=True)
    run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(clip.resolve()),
         "-ss", f"{inicio_juego:.2f}", "-i", str(juego.resolve()),
         "-t", f"{dur:.2f}", "-filter_complex", grafo, "-map", "[v]", *audio,
         "-c:v", "libx264", "-preset", render.x264_preset, "-crf", str(render.crf), "-pix_fmt", "yuv420p",
         "-maxrate", f"{render.maxrate_kbps}k", "-bufsize", f"{2 * render.maxrate_kbps}k",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(salida.resolve())],
        cwd=dir_trabajo if (con_subs or con_titulo) else None)
    return salida
