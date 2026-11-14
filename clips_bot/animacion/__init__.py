"""Animación vectorial para Shorts (1080x1920, 30 fps), dibujada por código.

Nada de IA generativa: personajes, fondos, props y texto son SVG armados en Python con un estilo
único (contorno grueso, colores planos, paleta en `paleta.py`). Un video se describe con datos
(`timeline.Video.desde_dict`), así un guion generado por un modelo de texto lo puede armar sin
tocar código, y `render.renderizar` lo pasa a mp4 (SVG → raster → ffmpeg).

Módulos:
  paleta      colores y grosores, en un solo lugar
  svg         ayudas para armar SVG + la fuente del texto
  personajes  narrador y secundarios con partes animables (ojos, boca, cejas, brazos, respiración)
  escenas     fondos (cielo, ciudad, oficina, globo) y props (cartel, flecha, pregunta, moneda…)
  texto       gancho animado y subtítulos estilo Shorts
  timeline    keyframes con easing, cámara, transiciones, escenas descriptas con dicts/JSON
  audio       envolvente de la voz (para la boca) y voz de prueba
  render      rasterizadores (resvg, cairosvg, rsvg-convert), composición con caché y ffmpeg
  demo        `python -m clips_bot.animacion.demo --salida demo.mp4`
  bench       compara los rasterizadores en la máquina donde corre
"""
