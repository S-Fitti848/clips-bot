"""PROTOTIPO: el render de "Así Nació" con Remotion (Santi, 2026-11-14). NO está en producción.

La línea de tiempo sigue saliendo del motor actual (`clips_bot.animacion`: guion, escenas, acciones,
chequeos de composición, viajes en el tiempo, pausas de Tito). Acá solo cambia el DIBUJO y el render:

    exportar.py  timeline.Video → datos por cuadro (posiciones, poses, caras, cámara, transiciones)
    render.py    esos datos → el proyecto Node de `remotion/` (React + SVG en Chrome headless) → mp4
                 y después el audio del motor actual (voz + música + SFX) pegado con ffmpeg
    prueba.py    la medición en la Pi (un video sintético de 35 s) y el Nerf para comparar

El estilo nuevo (volumen, contornos de grosor variable, escenarios con profundidad) está en
`remotion/src/`. Mientras Santi no apruebe la comparación, Así Nació sigue con el motor actual.
"""
