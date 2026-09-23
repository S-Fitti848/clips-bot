"""§3 pasos 5–6: armar el 9:16 y quemar subtítulos en una sola pasada de ffmpeg."""

from __future__ import annotations

from pathlib import Path

from .config import Render
from .layout import Layout
from .media import find_bin, run

SUBS_ARCHIVO = "subs.ass"


def filtro(layout: Layout, render: Render, con_subs: bool) -> str:
    W, H = render.ancho, render.alto
    escalar = "scale={w}:{h}:flags=lanczos,setsar=1"
    final = f"fps={render.fps}" + (f",ass={SUBS_ARCHIVO}" if con_subs else "")

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
    return f"[0:v]{layout.principal.ffmpeg_crop()},{escalar.format(w=W, h=H)},{final}[v]"


def renderizar(entrada: Path, salida: Path, layout: Layout, render: Render, dir_subs: Path | None) -> None:
    """dir_subs: carpeta que contiene subs.ass (ffmpeg corre ahí para no pelear con el escapado
    de rutas de Windows dentro del filtro). None = sin subtítulos."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    args = [
        find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(entrada.resolve()),
        "-t", str(render.duracion_max_s),
        "-filter_complex", filtro(layout, render, dir_subs is not None),
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", render.x264_preset, "-crf", str(render.crf), "-pix_fmt", "yuv420p",
        "-maxrate", f"{render.maxrate_kbps}k", "-bufsize", f"{2 * render.maxrate_kbps}k",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(salida.resolve()),
    ]
    run(args, cwd=dir_subs)
