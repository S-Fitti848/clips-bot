"""Gráficos animados de Pequeña Historia (pedido 2026-09-30), sin nada generado por IA:

- el AÑO contando al principio (de unas décadas antes hasta el año del hecho, y queda);
- un MAPA con un punto en el lugar del hecho (coordenadas del artículo de Wikipedia, sobre el
  mapa "Blue Marble" de la NASA, dominio público), unos segundos en la segunda frase;
- las PALABRAS CLAVE grandes cuando la voz las dice (las marca Gemini en el guion, misma llamada);
- un "whoosh" suave en cada cambio de foto o video (sintetizado con ffmpeg: nada que bajar).

El año y las palabras van en el mismo .ass de los subtítulos; el mapa, como una imagen encima
en el render final; el whoosh, mezclado en el audio ANTES de las reglas fijas de audio (§1).
"""

from __future__ import annotations

import logging
import math
import subprocess
import unicodedata
from pathlib import Path

from .media import find_bin

log = logging.getLogger(__name__)

MAPA_BASE = "File:Blue Marble 2002.png"     # NASA, dominio público, equirrectangular
MAPA_CREDITO = "Mapa: NASA Blue Marble (dominio público)"
CONTAR_S, AÑO_HASTA_S = 1.4, 2.4
CLAVE_S = 1.1


def _t(s: float) -> str:
    s = max(0.0, s)
    h, r = divmod(s, 3600)
    m, r = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{r:05.2f}"


def _norm(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", t or "") if not unicodedata.combining(c))
    return "".join(c for c in t.lower() if c.isalnum())


def estilos(W: int, H: int, fuente: str) -> list[str]:
    return [f"Style: Anio,{fuente},230,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,"
            f"0,0,1,10,4,8,40,40,{int(H * 0.16)},1",
            f"Style: Clave,{fuente},150,&H0000E1FF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,"
            f"0,0,1,10,4,8,40,40,{int(H * 0.17)},1"]


def anio_contando(anio: int, desde: int | None = None, pasos: int = 18) -> list[str]:
    """El año corriendo de `desde` (unas décadas antes) hasta `anio` en CONTAR_S, frenando al final,
    y quieto hasta AÑO_HASTA_S."""
    desde = desde if desde is not None else max(0, anio - 60)
    ev = []
    for k in range(pasos):
        x = (k + 1) / pasos
        valor = round(desde + (anio - desde) * (1 - (1 - x) ** 3))
        a, b = CONTAR_S * k / pasos, CONTAR_S * (k + 1) / pasos
        ev.append(f"Dialogue: 2,{_t(a)},{_t(b)},Anio,,0,0,0,,{valor}")
    ev.append(f"Dialogue: 2,{_t(CONTAR_S)},{_t(AÑO_HASTA_S)},Anio,,0,0,0,,"
              f"{{\\t(0,120,\\fscx112\\fscy112)\\t(120,260,\\fscx100\\fscy100)\\fad(0,250)}}{anio}")
    return ev


def claves_en_tiempo(palabras: list, claves: list[str], desde_s: float = AÑO_HASTA_S) -> list[str]:
    """Cada palabra clave, grande, en el momento en que la voz la dice (la primera vez, después
    del año). `palabras`: las del guion con su tiempo (subtitles.Palabra)."""
    buscadas = {_norm(c): c for c in claves if _norm(c)}
    ev, usadas, ultimo_fin = [], set(), 0.0
    for p in palabras:
        k = _norm(p.texto)
        if k in buscadas and k not in usadas and p.inicio >= desde_s and p.inicio >= ultimo_fin:
            usadas.add(k)
            fin = p.inicio + CLAVE_S
            ultimo_fin = fin
            texto = p.texto.strip(" ,.;:¡!¿?\"'«»").upper()
            ev.append(f"Dialogue: 2,{_t(p.inicio)},{_t(fin)},Clave,,0,0,0,,"
                      f"{{\\fscx60\\fscy60\\t(0,140,\\fscx112\\fscy112)\\t(140,260,\\fscx100\\fscy100)"
                      f"\\fad(60,200)}}{texto}")
    return ev


def agregar_al_ass(ass: Path, estilos_nuevos: list[str], eventos: list[str]) -> None:
    """Suma estilos y eventos a un .ass ya escrito (el de los subtítulos)."""
    t = ass.read_text(encoding="utf-8")
    if estilos_nuevos:
        t = t.replace("\n\n[Events]", "\n" + "\n".join(estilos_nuevos) + "\n\n[Events]", 1)
    ass.write_text(t.rstrip("\n") + "\n" + "\n".join(eventos) + "\n", encoding="utf-8")


def sacar_cartel(ass: Path) -> None:
    """El año quieto de antes (estilo Cartel) sale: ahora lo cuenta `anio_contando`."""
    lineas = [l for l in ass.read_text(encoding="utf-8").splitlines() if ",Cartel," not in l]
    ass.write_text("\n".join(lineas) + "\n", encoding="utf-8")


# ---- el mapa ------------------------------------------------------------------------------------

def mapa(base: Path, lat: float, lon: float, salida: Path, ancho: int = 560, alto: int = 360,
         span_lon: float = 70.0) -> Path:
    """Un recuadro del mapa (equirrectangular) centrado en (lat, lon) con un punto rojo y su aro."""
    from PIL import Image, ImageDraw

    im = Image.open(base).convert("RGB")
    W, H = im.size
    px, py = (lon + 180) / 360 * W, (90 - lat) / 180 * H
    cw = span_lon / 360 * W
    ch = cw * alto / ancho
    x0 = min(max(px - cw / 2, 0), W - cw)
    y0 = min(max(py - ch / 2, 0), H - ch)
    recorte = im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((ancho, alto), Image.LANCZOS)
    d = ImageDraw.Draw(recorte)
    cx, cy = (px - x0) / cw * ancho, (py - y0) / ch * alto
    for r, color, grosor in ((26, (255, 255, 255), 4), (14, (230, 30, 30), 0)):
        caja = (cx - r, cy - r, cx + r, cy + r)
        d.ellipse(caja, outline=color, width=grosor) if grosor else d.ellipse(caja, fill=color)
    marco = Image.new("RGB", (ancho + 12, alto + 12), (255, 255, 255))
    marco.paste(recorte, (6, 6))
    salida.parent.mkdir(parents=True, exist_ok=True)
    marco.save(salida)
    return salida


def filtro_mapa(entrada: int, desde: float, hasta: float, W: int, H: int) -> str:
    """El recuadro del mapa arriba al centro, con fundido, entre `desde` y `hasta` (segundos)."""
    return (f"[{entrada}:v]format=rgba,fade=t=in:st={desde:.2f}:d=0.3:alpha=1,"
            f"fade=t=out:st={max(desde, hasta - 0.3):.2f}:d=0.3:alpha=1[mapa];"
            f"[base][mapa]overlay=(W-w)/2:{int(H * 0.09)}:enable='between(t,{desde:.2f},{hasta:.2f})'")


# ---- el whoosh ----------------------------------------------------------------------------------

def whoosh(salida: Path, dur: float = 0.45) -> Path:
    """Un "whoosh" suave: ruido rosa filtrado, con subida y bajada. Sintetizado, sin archivos."""
    if salida.exists():
        return salida
    salida.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"anoisesrc=d={dur}:c=pink:a=0.7:r=48000",
                    "-af", f"highpass=f=500,lowpass=f=4500,afade=t=in:d={dur * 0.55:.2f},"
                           f"afade=t=out:st={dur * 0.55:.2f}:d={dur * 0.45:.2f},volume=0.9",
                    "-ac", "1", str(salida)], check=True, capture_output=True)
    return salida


def mezclar_whoosh(audio: Path, cortes: list[float], w: Path, salida: Path, volumen: float = 0.22) -> Path:
    """El audio (voz + música) con un whoosh centrado en cada corte (segundos)."""
    cortes = [c for c in cortes if c > 0.3]
    if not cortes:
        return audio
    n = len(cortes)
    ramas = [f"[1:a]asplit={n}" + "".join(f"[w{i}]" for i in range(n)) + ";"]
    for i, c in enumerate(cortes):
        ms = max(0, int((c - 0.22) * 1000))
        ramas.append(f"[w{i}]adelay={ms}|{ms},volume={volumen}[d{i}];")
    mezcla = "[0:a]" + "".join(f"[d{i}]" for i in range(n)) + \
        f"amix=inputs={n + 1}:duration=first:normalize=0[a]"
    subprocess.run([find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio),
                    "-i", str(w), "-filter_complex", "".join(ramas) + mezcla, "-map", "[a]",
                    str(salida)], check=True, capture_output=True)
    return salida


def distancia_ok(lat: float, lon: float) -> bool:
    return -85 <= lat <= 85 and -180 <= lon <= 180 and not (math.isnan(lat) or math.isnan(lon))
