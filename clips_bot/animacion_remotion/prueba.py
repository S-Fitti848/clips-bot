"""La medición en la Pi y el Nerf con el motor nuevo (prototipo; no toca producción).

    python -m clips_bot.animacion_remotion.prueba medir --proyecto ~/remotion_prueba --salida ~/remotion_prueba/out \
        --concurrencias 2,3 [--segundos 35]
    python -m clips_bot.animacion_remotion.prueba nerf --proyecto ~/remotion_prueba --carpeta ~/remotion_prueba/nerf
    python -m clips_bot.animacion_remotion.prueba rehacer --proyecto ... --carpeta ...   # sin Claude ni voz: reusa
                                                                                        # linea_de_tiempo.json y el audio

Las dos toman el TURNO PESADO del bot (nada de dos renders a la vez) y no corren en las franjas en que
se arman los videos del día (03:45-06:00 Pequeña Historia, 06:55-07:30 Así Nació).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sqlite3
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

from clips_bot.animacion import marcas
from clips_bot.animacion import texto as tx
from clips_bot.animacion.timeline import Video

from . import exportar as ex
from . import render as rr

TOKEN = "remotion:prueba"
VENCE_S = 3 * 3600
FRANJAS = ((dtime(3, 45), dtime(6, 0)), (dtime(6, 55), dtime(7, 30)))

# Un guion con la forma del de marcas.py (Nerf), escrito a mano: para medir sin gastar Claude ni voz.
GUION_PRUEBA = {
    "titulo": "Así nació Nerf", "pregunta_gancho": "¿Por qué una pelota de espuma?",
    "protagonista": {"prop": "pelota_espuma", "que_es": "la pelota de espuma"},
    "escenas": [
        {"frase": "¡Una pelota adentro de casa es un desastre!", "parte": "gancho", "fondo": "casa",
         "actores": [{"rol": "nene", "accion": "tirar", "desde": "izquierda", "hacia": "ninguno", "cara": "feliz"},
                     {"rol": "mama", "accion": "retar", "desde": "derecha", "hacia": "ninguno", "cara": "enojado"}],
         "objetos": [], "cadena": [{"prop": "tele", "soporte": "mesa", "donde": "centro"},
                                   {"prop": "lampara", "soporte": "piso", "donde": "derecha"},
                                   {"prop": "cuadro", "soporte": "pared", "donde": "izquierda"}],
         "camara": "sacudon", "texto_pantalla": "", "transicion": "corte", "viaje_a_anio": 0,
         "vuelve_al_presente": False},
        {"frase": "Las mamás de todo el mundo lo sabían.", "parte": "problema", "fondo": "casa",
         "actores": [{"rol": "mama", "accion": "retar", "desde": "centro", "hacia": "ninguno", "cara": "enojado"}],
         "objetos": [{"prop": "tele", "efecto": "quieto", "donde": "derecha", "soporte": "mesa", "texto": ""}],
         "cadena": [], "camara": "acercar", "texto_pantalla": "", "transicion": "barrido", "viaje_a_anio": 0,
         "vuelve_al_presente": False},
        {"frase": "En 1969, Reyn Guyer, un inventor de juegos de Minnesota, tuvo una idea.", "parte": "idea",
         "fondo": "taller",
         "actores": [{"rol": "inventor", "accion": "pensar", "desde": "centro", "hacia": "ninguno", "cara": "sorprendido"}],
         "objetos": [{"prop": "lamparita", "efecto": "aparece", "donde": "derecha", "soporte": "aire", "texto": ""}],
         "cadena": [], "camara": "acercar", "texto_pantalla": "1969", "transicion": "zoom", "viaje_a_anio": 1969,
         "vuelve_al_presente": False},
        {"frase": "Probó con espuma: blanda, liviana y no rompía nada.", "parte": "que_paso", "fondo": "taller",
         "actores": [{"rol": "inventor", "accion": "martillar", "desde": "izquierda", "hacia": "ninguno", "cara": "feliz"}],
         "objetos": [{"prop": "pelota_espuma", "efecto": "rebota", "donde": "derecha", "soporte": "piso", "texto": ""}],
         "cadena": [], "camara": "paneo", "texto_pantalla": "", "transicion": "fundido", "viaje_a_anio": 0,
         "vuelve_al_presente": False},
        {"frase": "Parker Brothers, la fábrica de juegos, la fabricó en serie.", "parte": "que_paso", "fondo": "fabrica",
         "actores": [{"rol": "joven", "accion": "caminar", "desde": "izquierda", "hacia": "derecha", "cara": "normal"}],
         "objetos": [{"prop": "caja", "efecto": "quieto", "donde": "centro", "soporte": "mesa", "texto": ""}],
         "cadena": [], "camara": "fija", "texto_pantalla": "", "transicion": "barrido", "viaje_a_anio": 0,
         "vuelve_al_presente": False},
        {"frase": "En un año vendieron cuatro millones.", "parte": "giro", "fondo": "tienda",
         "actores": [{"rol": "cliente", "accion": "festejar", "desde": "derecha", "hacia": "ninguno", "cara": "feliz"}],
         "objetos": [{"prop": "pelota_espuma", "efecto": "aparece", "donde": "izquierda", "soporte": "mesa", "texto": ""}],
         "cadena": [], "camara": "alejar", "texto_pantalla": "4 MILLONES", "transicion": "zoom", "viaje_a_anio": 0,
         "vuelve_al_presente": False},
        {"frase": "Hoy los chicos juegan adentro y la tele sobrevive.", "parte": "final", "fondo": "casa",
         "actores": [{"rol": "nene", "accion": "festejar", "desde": "izquierda", "hacia": "ninguno", "cara": "feliz"},
                     {"rol": "nena", "accion": "saltar", "desde": "derecha", "hacia": "ninguno", "cara": "feliz"}],
         "objetos": [{"prop": "pelota_espuma", "efecto": "rebota", "donde": "centro", "soporte": "piso", "texto": ""}],
         "cadena": [], "camara": "acercar", "texto_pantalla": "", "transicion": "fundido", "viaje_a_anio": 0,
         "vuelve_al_presente": True},
        {"frase": "Y la plata llovió para todos.", "parte": "final", "fondo": "ciudad",
         "actores": [{"rol": "empresario", "accion": "caminar", "desde": "izquierda", "hacia": "centro", "cara": "feliz"}],
         "objetos": [{"prop": "billete", "efecto": "llueve", "donde": "centro", "soporte": "aire", "texto": ""}],
         "cadena": [], "camara": "fija", "texto_pantalla": "", "transicion": "barrido", "viaje_a_anio": 0,
         "vuelve_al_presente": False},
    ],
    "locutor": [{"despues_de_frase": 2, "texto": "Spoiler: la tele no sobrevivió."},
                {"despues_de_frase": 5, "texto": "Sí, era una pelota de espuma. Nada más."}],
}


def franja_prohibida(ahora: datetime | None = None) -> bool:
    h = (ahora or datetime.now()).time()
    return any(a <= h < b for a, b in FRANJAS)


def tomar_turno(log=print):
    from clips_bot import db

    if franja_prohibida():
        raise SystemExit("estamos en una franja en la que se arman los videos del día: no corro nada")
    c = db.connect(Path("/home/santi/clips/data/clips.db"))
    while not db.tomar_turno(c, db.RECURSO_PESADO, TOKEN, maximo=1, vencimiento_s=VENCE_S):
        log("turno pesado ocupado: espero 2 min")
        time.sleep(120)
        if franja_prohibida():
            raise SystemExit("llegó una franja prohibida esperando el turno")
    return c


def soltar_turno(c) -> None:
    from clips_bot import db

    db.soltar_turno(c, db.RECURSO_PESADO, TOKEN, VENCE_S)


def video_sintetico(segundos: float = 35.0) -> Video:
    d = GUION_PRUEBA
    segs = marcas.segmentos(d)
    paso = segundos / len(segs)
    inicios = [i * paso for i in range(len(segs))]
    palabras = []
    for (_, _, texto), a in zip(segs, inicios):
        palabras += tx.palabras_de_texto(texto, a + 0.1, a + paso - 0.25)
    datos, _ = marcas.linea_de_tiempo(d, inicios, segundos, palabras, None, presente=2026)
    v = Video.desde_dict(datos)
    # sin voz: una boca que se mueve igual (para que el costo de la cara sea el real)
    v.envolvente = [max(0.0, math.sin(i * 0.9)) * 0.8 for i in range(v.total_cuadros)]
    return v


def cmd_medir(a) -> int:
    salida = Path(a.salida).expanduser()
    salida.mkdir(parents=True, exist_ok=True)
    v = video_sintetico(a.segundos)
    datos = salida / "prueba.json"
    print("exportado:", ex.exportar(v, datos), flush=True)
    c = tomar_turno()
    resultados = []
    try:
        for n in [int(x) for x in a.concurrencias.split(",") if x.strip()]:
            if franja_prohibida():
                print("franja prohibida: corto acá")
                break
            res = rr.renderizar(datos, Path(a.proyecto).expanduser(), salida / f"prueba_c{n}.mp4", concurrencia=n,
                                frames=a.frames or None)
            resultados.append(res)
            time.sleep(a.enfriar)
            res["temp_tras_enfriar"] = rr.temperatura()
    finally:
        soltar_turno(c)
    (salida / "medicion.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resultados, ensure_ascii=False, indent=1))
    return 0


def _renderizar_carpeta(carpeta: Path, proyecto: Path, concurrencia: int) -> dict:
    linea = json.loads((carpeta / "linea_de_tiempo.json").read_text(encoding="utf-8"))
    v = Video.desde_dict(linea["video"], carpeta)
    datos = carpeta / "remotion.json"
    print("exportado:", ex.exportar(v, datos), flush=True)
    audio = carpeta / "audio_final.wav"
    return rr.renderizar(datos, proyecto, carpeta / "nerf_remotion.mp4", audio=audio if audio.exists() else None,
                         concurrencia=concurrencia)


def cmd_nerf(a) -> int:
    """El Nerf entero con el código de producción (guion con Claude, voz, Whisper, revisión visual,
    música + SFX y el render del motor ACTUAL, para comparar) y después el render con Remotion. Sobre una
    COPIA de la base: no queda anotado en la rotación ni en la música usada."""
    from clips_bot import db as _db
    from clips_bot.config import load_settings

    carpeta = Path(a.carpeta).expanduser()
    carpeta.mkdir(parents=True, exist_ok=True)
    copia = carpeta / "clips_copia.db"
    c = tomar_turno()
    try:
        fuente = sqlite3.connect("/home/santi/clips/data/clips.db")
        destino = sqlite3.connect(copia)
        fuente.backup(destino)
        fuente.close()
        destino.close()
        conn = _db.connect(copia)
        nerf = next(m for m in marcas.cargar_catalogo() if m.nombre == "Nerf")
        e = marcas.Elegido(nerf, "origen", {k: 9 for k in marcas.CRITERIOS})
        settings = load_settings()
        t0 = time.time()
        r = marcas.armar_video(conn, settings, carpeta, forzar=e, avisar=lambda s: print(s, flush=True),
                               procesos=settings.animacion.procesos)
        actual = {"render_s": r.render_s, "total_s": r.total_s, "duracion_s": r.duracion_s, "costo_usd": r.costo_usd,
                  "video": r.video, "revision": r.revision, "tiempos": r.tiempos, "titulo": r.titulo,
                  "descripcion": r.descripcion, "musica": r.musica, "credito_musica": r.credito_musica}
        (carpeta / "resultado_actual.json").write_text(json.dumps(actual, ensure_ascii=False, indent=1), encoding="utf-8")
        print("motor actual:", json.dumps(actual, ensure_ascii=False), f"({time.time() - t0:.0f} s)", flush=True)
        if franja_prohibida():
            raise SystemExit("llegó una franja prohibida: el render con Remotion queda para después (rehacer)")
        res = _renderizar_carpeta(carpeta, Path(a.proyecto).expanduser(), a.concurrencia)
    finally:
        soltar_turno(c)
    (carpeta / "resultado_remotion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def cmd_rehacer(a) -> int:
    carpeta = Path(a.carpeta).expanduser()
    c = tomar_turno()
    try:
        res = _renderizar_carpeta(carpeta, Path(a.proyecto).expanduser(), a.concurrencia)
    finally:
        soltar_turno(c)
    (carpeta / "resultado_remotion.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def cmd_exportar(a) -> int:
    """Solo los datos (sin render): para mirar cuadros en Remotion Studio en la compu."""
    if a.linea:
        linea = json.loads(Path(a.linea).read_text(encoding="utf-8"))
        v = Video.desde_dict(linea["video"], Path(a.linea).parent)
    else:
        v = video_sintetico(a.segundos)
    print(ex.exportar(v, Path(a.salida)))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("medir")
    m.add_argument("--proyecto", required=True)
    m.add_argument("--salida", required=True)
    m.add_argument("--concurrencias", default="2")
    m.add_argument("--segundos", type=float, default=35.0)
    m.add_argument("--frames", default="")
    m.add_argument("--enfriar", type=float, default=60.0)
    for nombre in ("nerf", "rehacer"):
        n = sub.add_parser(nombre)
        n.add_argument("--proyecto", required=True)
        n.add_argument("--carpeta", required=True)
        n.add_argument("--concurrencia", type=int, default=3)
    e = sub.add_parser("exportar")
    e.add_argument("--salida", required=True)
    e.add_argument("--linea", default="")
    e.add_argument("--segundos", type=float, default=35.0)
    a = ap.parse_args(argv)
    return {"medir": cmd_medir, "nerf": cmd_nerf, "rehacer": cmd_rehacer, "exportar": cmd_exportar}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
