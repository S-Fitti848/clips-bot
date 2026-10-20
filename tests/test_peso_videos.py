"""Peso de los videos que manda el bot (2026-10-20: "tardan en cargar en Telegram")."""
import re
from pathlib import Path

from clips_bot.config import load_settings

RAIZ = Path(__file__).resolve().parent.parent


def test_ajustes_medidos_con_vmaf():
    r = load_settings().render
    assert (r.x264_preset, r.crf, r.maxrate_kbps) == ("medium", 22, 3500)
    assert 59 * r.maxrate_kbps / 8 / 1000 < 30          # un clip de 59 s no pasa de ~26 MB


def test_todo_render_final_lleva_faststart():
    # los que salen hacia Telegram: clips, multi-POV, efemérides, gameplay
    for archivo in ("render.py", "multipov.py", "efemerides.py", "gameplay.py"):
        texto = (RAIZ / "clips_bot" / archivo).read_text(encoding="utf-8")
        assert "+faststart" in texto, archivo


def test_send_video_pide_streaming():
    texto = (RAIZ / "clips_bot" / "telegram.py").read_text(encoding="utf-8")
    assert re.search(r'"supports_streaming":\s*"true"', texto)
