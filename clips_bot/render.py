"""§3 pasos 5–6: armar el 9:16 y quemar subtítulos en una sola pasada de ffmpeg.

Tres layouts (los elige `layout.decidir_layout`):
  split     facecam clara: cámara arriba, juego abajo. Recorta, pero recorta bien porque sabe dónde
            está cada cosa.
  fullcam   una sola cara grande y centrada: recorte 9:16 centrado en la cara.
  fit_blur  todo lo demás. El 16:9 entero, escalado a 1080 de ancho y centrado, sobre el mismo video
            ampliado y borroso llenando el 9:16. No recorta NADA: es lo único seguro cuando hay dos
            personas separadas, o cuando lo importante está en los bordes (chat, HUD, marcador).
            Los subtítulos quedan en la franja de abajo, fuera del video.
"""

from __future__ import annotations

from pathlib import Path

from . import zooms
from .config import Render
from .layout import Layout
from .media import cola_audio, find_bin, probe, run

SUBS_ARCHIVO = "subs.ass"
TITULO_ARCHIVO = "titulo.ass"


def filtro(layout: Layout, render: Render, con_subs: bool, con_titulo: bool = False) -> str:
    W, H = render.ancho, render.alto
    escalar = "scale={w}:{h}:flags=lanczos,setsar=1"
    final = f"fps={render.fps}" + (f",ass={SUBS_ARCHIVO}" if con_subs else "") \
        + (f",ass={TITULO_ARCHIVO}" if con_titulo else "")
    if layout.tipo == "sigue":
        # Charla o IRL: el recorte 9:16 se mueve con la cara (layout.ffmpeg_crop_movil).
        return f"[0:v]{layout.ffmpeg_crop_movil()},{escalar.format(w=W, h=H)},{final}[v]"

    if layout.tipo == "split":
        assert layout.camara is not None
        hc = render.alto_camara
        sep = render.separador_px
        pad = f",pad={W}:{hc}:0:0:black" if sep > 0 else ""  # línea negra entre cámara y juego
        return (
            "[0:v]split=2[c][g];"
            f"[c]{layout.camara.ffmpeg_crop()},{escalar.format(w=W, h=hc - sep)}{pad}[cam];"
            f"[g]{layout.principal.ffmpeg_crop()},{escalar.format(w=W, h=H - hc)}[juego];"
            f"[cam][juego]vstack=inputs=2,{final}[v]"
        )
    if layout.tipo == "fit_blur":
        # Fondo: el mismo video agrandado hasta tapar los 1080x1920 y desenfocado.
        # Frente: el 16:9 entero a 1080 de ancho, centrado. No se recorta nada.
        # Con zooms (zooms.py): unos pocos acercamientos suaves en los picos de volumen, hacia las caras.
        frente = f"scale={W}:-2:flags=lanczos,setsar=1"
        if layout.zooms:
            p = layout.principal
            h = int(round(W * p.h / p.w / 2)) * 2
            frente = zooms.filtro_frente(W, h, render.fps, list(layout.zooms), layout.zoom, *layout.zoom_centro)
        return (
            "[0:v]split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma={render.blur_sigma}[fondo];"
            f"[fg]{frente}[frente];"
            f"[fondo][frente]overlay=0:(H-h)/2,{final}[v]"
        )
    return f"[0:v]{layout.principal.ffmpeg_crop()},{escalar.format(w=W, h=H)},{final}[v]"


def renderizar(entrada: Path, salida: Path, layout: Layout, render: Render, dir_subs: Path | None,
               dir_titulo: Path | None = None) -> None:
    """dir_subs: carpeta que contiene subs.ass (ffmpeg corre ahí para no pelear con el escapado
    de rutas de Windows dentro del filtro). None = sin subtítulos. `dir_titulo`: la carpeta con
    titulo.ass (el título grande); es la misma carpeta de trabajo que la de los subtítulos."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    grafo, audio = filtro(layout, render, dir_subs is not None, dir_titulo is not None), []
    info = probe(entrada)
    if info.tiene_audio:   # audio limpio (media.cola_audio): fundidos y termina con el video
        dur = min(info.duracion, render.duracion_max_s) if info.duracion else render.duracion_max_s
        grafo += f";[0:a]{cola_audio(dur)}[a]"
        audio = ["-map", "[a]"]
    args = [
        find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(entrada.resolve()),
        "-t", str(render.duracion_max_s),
        "-filter_complex", grafo,
        "-map", "[v]", *audio,
        "-c:v", "libx264", "-preset", render.x264_preset, "-crf", str(render.crf), "-pix_fmt", "yuv420p",
        "-maxrate", f"{render.maxrate_kbps}k", "-bufsize", f"{2 * render.maxrate_kbps}k",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(salida.resolve()),
    ]
    run(args, cwd=dir_subs or dir_titulo)
