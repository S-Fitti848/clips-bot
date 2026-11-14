"""Render: cada cuadro SVG → raster → ffmpeg (libx264, yuv420p, faststart).

Cómo se ahorra trabajo (la Pi se calienta, ver CLAUDE.md §2):
- El FONDO es estático: se rasteriza UNA vez por proceso y por fondo, y la cámara se le aplica
  como transformación afín de PIL (mucho más barata que volver a dibujar 200 edificios).
- Solo lo que se mueve (personajes, props, textos) se rasteriza cada cuadro, con fondo
  transparente, y se compone arriba.
- Si un cuadro es igual al anterior (misma descripción), no se vuelve a dibujar.
- Varios procesos con tope (`procesos`), con una ventana de cuadros en vuelo acotada: si ffmpeg va
  más lento, no se acumulan cuadros en memoria (cada uno son 6 MB).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import escenas as esc
from . import paleta as P
from .easing import salida, suave
from .svg import documento, fuente
from .timeline import CapaEscena, Cuadro, Video

# ---- rasterizadores -----------------------------------------------------------


class Rasterizador:
    nombre = "?"

    def rgba(self, svg: str, w: int, h: int):
        """SVG completo (con <svg>) → PIL.Image RGBA de w x h."""
        raise NotImplementedError


class Resvg(Rasterizador):
    """resvg (Rust) por `resvg-py`: devuelve PNG, así que hay un decode por cuadro. Sin fuentes del
    sistema (solo la del canal): si no, escanea todas las fuentes en CADA llamada."""
    nombre = "resvg"

    def __init__(self):
        import resvg_py

        self._r = resvg_py
        archivo, _ = fuente()
        self._fuentes = [archivo] if archivo else None

    def rgba(self, svg, w, h):
        from PIL import Image

        png = self._r.svg_to_bytes(svg_string=svg, skip_system_fonts=bool(self._fuentes),
                                   font_files=self._fuentes)
        if not isinstance(png, (bytes, bytearray)):
            png = bytes(png)
        return Image.open(io.BytesIO(png)).convert("RGBA")


class Cairo(Rasterizador):
    """cairosvg dibujando DIRECTO en una superficie de cairo en memoria (sin codificar PNG).
    Es "nativo": el render compone todo en cairo (fondo cacheado + cámara con la matriz de cairo
    + el SVG dibujado encima en la misma superficie) y le pasa a ffmpeg los píxeles BGRA tal cual.
    Medido en la Pi (2026-11-14): el frente en 0,066 s contra 0,44 s de resvg-py, que paga
    codificar y decodificar un PNG de 1080x1920 en cada llamada."""
    nombre = "cairosvg"
    nativo = True

    def __init__(self):
        import cairocffi
        from cairosvg.parser import Tree
        from cairosvg.surface import PNGSurface

        class _Sobre(PNGSurface):
            """Dibuja sobre una superficie que ya existe (con el fondo pintado) en vez de crear
            una nueva: así no hay una capa transparente que después haya que mezclar."""
            destino = None

            def _create_surface(self, width, height):
                d = type(self).destino
                return d, d.get_width(), d.get_height()

        self._cairo, self._Tree, self._Sobre = cairocffi, Tree, _Sobre

    def superficie(self, w: int, h: int):
        return self._cairo.ImageSurface(self._cairo.FORMAT_ARGB32, w, h)

    def dibujar_en(self, svg: str, sup) -> None:
        self._Sobre.destino = sup
        try:
            self._Sobre(self._Tree(bytestring=svg.encode("utf-8")), None, 96)
        finally:
            self._Sobre.destino = None

    def rgba(self, svg, w, h):
        from PIL import Image

        sup = self.superficie(w, h)
        self.dibujar_en(svg, sup)
        sup.flush()
        return Image.frombuffer("RGBA", (w, h), bytes(sup.get_data()), "raw", "BGRa",
                                sup.get_stride(), 1)


class RsvgConvert(Rasterizador):
    """El binario `rsvg-convert` (librsvg), un proceso por cuadro."""
    nombre = "rsvg-convert"

    def __init__(self):
        self._bin = shutil.which("rsvg-convert")
        if not self._bin:
            raise RuntimeError("no está rsvg-convert")

    def rgba(self, svg, w, h):
        from PIL import Image

        r = subprocess.run([self._bin, "-w", str(w), "-h", str(h), "-f", "png"],
                           input=svg.encode("utf-8"), capture_output=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode(errors="replace")[-400:])
        return Image.open(io.BytesIO(r.stdout)).convert("RGBA")


RASTERIZADORES = {"resvg": Resvg, "cairosvg": Cairo, "rsvg-convert": RsvgConvert}
ORDEN_AUTO = ("cairosvg", "resvg", "rsvg-convert")   # el más rápido en la Pi primero (ver bench)


def disponibles() -> list[str]:
    out = []
    for nombre in ORDEN_AUTO:
        try:
            RASTERIZADORES[nombre]()
            out.append(nombre)
        except Exception:
            pass
    return out


def crear(nombre: str = "auto") -> Rasterizador:
    if nombre != "auto":
        return RASTERIZADORES[nombre]()
    for n in ORDEN_AUTO:
        try:
            return RASTERIZADORES[n]()
        except Exception:
            continue
    raise RuntimeError("No hay ningún rasterizador de SVG: pip install resvg-py (o cairosvg)")


# ---- composición de un cuadro (corre en los procesos) -----------------------------

_W = {"r": None, "w": 0, "h": 0, "fondos": {}, "cache_fondo": True}


def _iniciar(nombre: str, w: int, h: int, cache_fondo: bool):
    _W["r"] = crear(nombre)
    _W["w"], _W["h"] = w, h
    _W["fondos"] = {}
    _W["cache_fondo"] = cache_fondo


def _doc(cuerpo: str) -> str:
    """Documento a la resolución de salida, con el viewBox siempre en 1080x1920."""
    return documento(cuerpo).replace(f'width="{P.ANCHO}" height="{P.ALTO}"',
                                     f'width="{_W["w"]}" height="{_W["h"]}"', 1)


def _svg_fondo(fondo: tuple) -> str:
    if fondo[0] == "color":
        return f'<rect width="{P.ANCHO}" height="{P.ALTO}" fill="{fondo[1]}"/>'
    return esc.fondo(fondo[0], fondo[1])


def _fondo(fondo: tuple):
    img = _W["fondos"].get(fondo)
    if img is None:
        img = _W["r"].rgba(_doc(_svg_fondo(fondo)), _W["w"], _W["h"])
        _W["fondos"][fondo] = img
    return img


def _svg_camara(cuerpo: str, camara: tuple) -> str:
    z, dx, dy, rot = camara
    if (z, dx, dy, rot) == (1.0, 0.0, 0.0, 0.0) or not cuerpo:
        return cuerpo
    cx, cy = P.ANCHO / 2, P.ALTO / 2
    rot_s = f" rotate({rot})" if rot else ""
    return (f'<g transform="translate({cx} {cy}){rot_s} scale({z}) '
            f'translate({-cx - dx} {-cy - dy})">{cuerpo}</g>')


def coeficientes_camara(camara: tuple, w: int, h: int) -> tuple:
    """Afín inversa (salida → entrada) para PIL, en píxeles de salida: la misma cámara que
    `_svg_camara` (zoom y rotación alrededor del centro, corrida dx/dy en px de 1080)."""
    import math

    z, dx, dy, rot = camara
    k = w / P.ANCHO
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    cx, cy = w / 2, h / 2
    a, b = c / z, s / z
    d, e = -s / z, c / z
    return (a, b, cx + dx * k - (a * cx + b * cy), d, e, cy + dy * k - (d * cx + e * cy))


def _capa(capa: CapaEscena, encima: str = ""):
    """Una escena rasterizada. `encima` (subtítulos) va en la MISMA llamada al rasterizador:
    cada llamada tiene un costo fijo alto (pixmap de 1080x1920 + PNG), medido en Windows con
    resvg: 0,13 s por una capa de subtítulos sola."""
    from PIL import Image

    w, h = _W["w"], _W["h"]
    if not _W["cache_fondo"]:   # todo junto en un solo SVG (para comparar)
        cuerpo = (_svg_camara(_svg_fondo(capa.fondo) + capa.frente, capa.camara) + capa.fijo
                  + encima)
        return _W["r"].rgba(_doc(cuerpo), w, h)
    base = _fondo(capa.fondo)
    if capa.camara != (1.0, 0.0, 0.0, 0.0):
        base = base.transform((w, h), Image.AFFINE, coeficientes_camara(capa.camara, w, h),
                              resample=Image.BILINEAR)
    else:
        base = base.copy()
    cuerpo = _svg_camara(capa.frente, capa.camara) + capa.fijo + encima
    if cuerpo:
        base.alpha_composite(_W["r"].rgba(_doc(cuerpo), w, h))
    return base


def _zoom(img, z: float):
    from PIL import Image

    w, h = img.size
    cw, ch = w / z, h / z
    caja = ((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)
    return img.resize((w, h), Image.BILINEAR, box=caja)


def _transicion(sale, entra, tipo: str, u: float):
    from PIL import Image, ImageDraw

    if tipo == "fundido":
        return Image.blend(sale, entra, suave(u))
    if tipo == "zoom":   # la que sale se acerca rápido, la que entra llega desde cerca
        if u < 0.5:
            return _zoom(sale, 1 + 0.8 * suave(u / 0.5))
        return _zoom(entra, 1.8 - 0.8 * salida((u - 0.5) / 0.5))
    if tipo == "barrido":   # empuja de derecha a izquierda, con una franja de color en el borde
        w, h = sale.size
        x = int(round(w * (1 - salida(u))))
        out = Image.new("RGBA", (w, h))
        out.paste(sale, (x - w, 0))
        out.paste(entra, (x, 0))
        banda = max(4, w // 45)
        ImageDraw.Draw(out).rectangle([x - banda, 0, x, h], fill=P.AMARILLO)
        return out
    return entra


# -- composición nativa (cairo) --

def _fondo_cairo(fondo: tuple):
    sup = _W["fondos"].get(fondo)
    if sup is None:
        sup = _W["r"].superficie(_W["w"], _W["h"])
        _W["r"].dibujar_en(_doc(_svg_fondo(fondo)), sup)
        _W["fondos"][fondo] = sup
    return sup


def _matriz_camara(ctx, camara: tuple, w: int, h: int) -> None:
    """La misma cámara que `_svg_camara`, en píxeles de salida, sobre un contexto de cairo."""
    import math

    z, dx, dy, rot = camara
    k = w / P.ANCHO
    ctx.translate(w / 2, h / 2)
    if rot:
        ctx.rotate(math.radians(rot))
    ctx.scale(z, z)
    ctx.translate(-w / 2 - dx * k, -h / 2 - dy * k)


def _capa_cairo(capa: CapaEscena, encima: str = ""):
    r, w, h = _W["r"], _W["w"], _W["h"]
    sup = r.superficie(w, h)
    if not _W["cache_fondo"]:
        cuerpo = (_svg_camara(_svg_fondo(capa.fondo) + capa.frente, capa.camara) + capa.fijo
                  + encima)
        r.dibujar_en(_doc(cuerpo), sup)
        return sup
    ctx = r._cairo.Context(sup)
    if capa.camara != (1.0, 0.0, 0.0, 0.0):
        _matriz_camara(ctx, capa.camara, w, h)
    ctx.set_source_surface(_fondo_cairo(capa.fondo), 0, 0)
    ctx.get_source().set_filter(r._cairo.FILTER_BILINEAR)
    ctx.paint()
    cuerpo = _svg_camara(capa.frente, capa.camara) + capa.fijo + encima
    if cuerpo:
        r.dibujar_en(_doc(cuerpo), sup)
    return sup


def _transicion_cairo(sale, entra, tipo: str, u: float):
    r, w, h = _W["r"], _W["w"], _W["h"]
    cairo = r._cairo
    if tipo == "fundido":
        ctx = cairo.Context(sale)
        ctx.set_source_surface(entra, 0, 0)
        ctx.paint_with_alpha(suave(u))
        return sale
    out = r.superficie(w, h)
    ctx = cairo.Context(out)
    if tipo == "zoom":
        if u < 0.5:
            img, z = sale, 1 + 0.8 * suave(u / 0.5)
        else:
            img, z = entra, 1.8 - 0.8 * salida((u - 0.5) / 0.5)
        ctx.translate(w / 2, h / 2)
        ctx.scale(z, z)
        ctx.translate(-w / 2, -h / 2)
        ctx.set_source_surface(img, 0, 0)
        ctx.get_source().set_filter(cairo.FILTER_BILINEAR)
        ctx.paint()
        return out
    if tipo == "barrido":
        x = int(round(w * (1 - salida(u))))
        ctx.set_source_surface(sale, x - w, 0)
        ctx.paint()
        ctx.set_source_surface(entra, x, 0)
        ctx.paint()
        banda = max(4, w // 45)
        ctx.set_source_rgb(1.0, 0.82, 0.25)
        ctx.rectangle(x - banda, 0, banda, h)
        ctx.fill()
        return out
    return entra


def _componer_cairo(cuadro: Cuadro) -> bytes:
    if cuadro.b is not None and cuadro.transicion:
        sup = _transicion_cairo(_capa_cairo(cuadro.b), _capa_cairo(cuadro.a),
                                *cuadro.transicion)
        if cuadro.encima:
            _W["r"].dibujar_en(_doc(cuadro.encima), sup)
    else:
        sup = _capa_cairo(cuadro.a, cuadro.encima)
    sup.flush()
    return bytes(sup.get_data())   # BGRA (ARGB32 de cairo en little-endian), stride = 4 * w


def formato_pixel(nombre: str) -> str:
    """Cómo le llegan los píxeles a ffmpeg según el rasterizador."""
    return "bgra" if getattr(RASTERIZADORES.get(nombre), "nativo", False) else "rgb24"


def componer(cuadro: Cuadro) -> tuple[bytes, float]:
    """Cuadro → bytes crudos (`formato_pixel`) y los segundos que tardó, para medir."""
    t0 = time.perf_counter()
    if getattr(_W["r"], "nativo", False):
        return _componer_cairo(cuadro), time.perf_counter() - t0
    if cuadro.b is not None and cuadro.transicion:
        img = _transicion(_capa(cuadro.b), _capa(cuadro.a), *cuadro.transicion)
        if cuadro.encima:   # los subtítulos no participan de la transición
            img.alpha_composite(_W["r"].rgba(_doc(cuadro.encima), _W["w"], _W["h"]))
    else:
        img = _capa(cuadro.a, cuadro.encima)
    return img.convert("RGB").tobytes(), time.perf_counter() - t0


# ---- temperatura (Pi) -------------------------------------------------------------


def temperatura() -> float | None:
    try:
        r = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=5)
        return float(r.stdout.strip().split("=")[1].split("'")[0])
    except Exception:
        try:
            return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
        except Exception:
            return None


def throttled() -> str | None:
    try:
        r = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip().split("=")[1]
    except Exception:
        return None


class _Termometro(threading.Thread):
    def __init__(self, cada_s: float = 5.0):
        super().__init__(daemon=True)
        self.cada_s, self.muestras, self._fin = cada_s, [], threading.Event()

    def run(self):
        while not self._fin.is_set():
            t = temperatura()
            if t is not None:
                self.muestras.append(t)
            self._fin.wait(self.cada_s)

    def parar(self):
        self._fin.set()


# ---- render completo ---------------------------------------------------------------


@dataclass
class Resultado:
    salida: Path
    cuadros: int
    repetidos: int
    segundos: float
    rasterizador: str
    procesos: int
    s_por_cuadro_raster: float           # tiempo de composición promedio en un proceso
    s_armado_svg: float                  # describir los cuadros (proceso principal)
    temp_antes: float | None = None
    temp_max: float | None = None
    temp_despues: float | None = None
    throttled_antes: str | None = None
    throttled_despues: str | None = None
    peso_mb: float = 0.0
    extra: dict = field(default_factory=dict)

    def resumen(self) -> str:
        lineas = [f"{self.salida.name}: {self.cuadros} cuadros ({self.repetidos} repetidos) en "
                  f"{self.segundos:.1f} s -> {self.segundos / max(1, self.cuadros):.3f} s/cuadro de "
                  f"reloj; {self.peso_mb:.2f} MB",
                  f"  {self.rasterizador}, {self.procesos} procesos: componer "
                  f"{self.s_por_cuadro_raster:.3f} s/cuadro por proceso; describir "
                  f"{self.s_armado_svg:.1f} s en total"]
        if self.temp_antes is not None:
            lineas.append(f"  temperatura: {self.temp_antes} -> máx {self.temp_max} -> "
                          f"{self.temp_despues} °C · throttled {self.throttled_antes} -> "
                          f"{self.throttled_despues}")
        return "\n".join(lineas)


def comando_ffmpeg(video: Video, salida: Path, w: int, h: int, crf: int, preset: str,
                   hilos: int | None, pix_fmt: str = "rgb24") -> list[str]:
    from clips_bot.media import cola_audio, find_bin

    args = [find_bin("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", pix_fmt, "-s", f"{w}x{h}", "-r", str(video.fps),
            "-i", "-"]
    if video.audio:
        args += ["-i", video.audio, "-map", "0:v", "-map", "1:a",
                 "-af", cola_audio(video.total_cuadros / video.fps),
                 "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    args += ["-c:v", "libx264", "-preset", preset, "-tune", "animation", "-crf", str(crf),
             "-pix_fmt", "yuv420p", "-maxrate", "3500k", "-bufsize", "7000k",
             "-movflags", "+faststart"]
    if hilos:
        args += ["-threads", str(hilos)]
    return args + [str(salida)]


def renderizar(video: Video, salida: Path, rasterizador: str = "auto", procesos: int = 2,
               escala: float = 1.0, crf: int = 22, preset: str = "medium",
               hilos_x264: int | None = None, cache_fondo: bool = True,
               max_cuadros: int | None = None, progreso=None) -> Resultado:
    """Renderiza el video a mp4. `escala` < 1 para pruebas (0.25 = 270x480). `procesos` = cuántos
    procesos rasterizan (en la Pi, 2-3: el x264 también usa CPU y todo calienta)."""
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    w = int(round(P.ANCHO * escala / 2)) * 2
    h = int(round(P.ALTO * escala / 2)) * 2
    nombre = crear(rasterizador).nombre
    total = video.total_cuadros if max_cuadros is None else min(max_cuadros, video.total_cuadros)

    termo = _Termometro()
    temp_antes, thr_antes = temperatura(), throttled()
    if temp_antes is not None:
        termo.start()
    t_inicio = time.perf_counter()
    ff = subprocess.Popen(comando_ffmpeg(video, salida, w, h, crf, preset, hilos_x264,
                                         formato_pixel(nombre)),
                          stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t_svg, t_comp, n_comp, repetidos = 0.0, 0.0, 0, 0
    try:
        if procesos <= 1:
            _iniciar(nombre, w, h, cache_fondo)
            previo, previo_bytes = None, b""
            for i in range(total):
                a = time.perf_counter()
                c = video.cuadro(i)
                t_svg += time.perf_counter() - a
                if c == previo:
                    repetidos += 1
                else:
                    previo_bytes, dt = componer(c)
                    t_comp += dt
                    n_comp += 1
                    previo = c
                ff.stdin.write(previo_bytes)
                if progreso:
                    progreso(i + 1, total)
        else:
            ventana = deque()   # (futuro | bytes) en orden
            previo = None
            with ProcessPoolExecutor(procesos, initializer=_iniciar,
                                     initargs=(nombre, w, h, cache_fondo)) as ex:
                def vaciar(hasta: int):
                    nonlocal t_comp, n_comp
                    while len(ventana) > hasta:
                        item = ventana.popleft()
                        if isinstance(item, tuple):   # ("rep", futuro del cuadro igual anterior)
                            datos = item[1].result()[0]
                        else:
                            datos, dt = item.result()
                            t_comp += dt
                            n_comp += 1
                        ff.stdin.write(datos)

                ultimo = None
                for i in range(total):
                    a = time.perf_counter()
                    c = video.cuadro(i)
                    t_svg += time.perf_counter() - a
                    if c == previo and ultimo is not None:
                        repetidos += 1
                        ventana.append(("rep", ultimo))
                    else:
                        ultimo = ex.submit(componer, c)
                        ventana.append(ultimo)
                        previo = c
                    vaciar(procesos * 3)
                    if progreso:
                        progreso(i + 1, total)
                vaciar(0)
        ff.stdin.close()
        err = ff.stderr.read().decode(errors="replace")
        if ff.wait(timeout=600) != 0:
            raise RuntimeError(f"ffmpeg falló:\n{err[-1500:]}")
    except BaseException:
        ff.kill()
        raise
    finally:
        termo.parar()
    seg = time.perf_counter() - t_inicio
    return Resultado(
        salida=salida, cuadros=total, repetidos=repetidos, segundos=seg, rasterizador=nombre,
        procesos=max(1, procesos), s_por_cuadro_raster=t_comp / max(1, n_comp),
        s_armado_svg=t_svg, temp_antes=temp_antes,
        temp_max=max(termo.muestras) if termo.muestras else temp_antes,
        temp_despues=temperatura(), throttled_antes=thr_antes, throttled_despues=throttled(),
        peso_mb=salida.stat().st_size / 1e6 if salida.exists() else 0.0)


def cuadro_png(video: Video, i: int, destino: Path, rasterizador: str = "auto",
               escala: float = 1.0) -> Path:
    """Un cuadro suelto a PNG (para mirar sin armar el video)."""
    from PIL import Image

    w = int(round(P.ANCHO * escala / 2)) * 2
    h = int(round(P.ALTO * escala / 2)) * 2
    nombre = crear(rasterizador).nombre
    _iniciar(nombre, w, h, True)
    datos, _ = componer(video.cuadro(i))
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if formato_pixel(nombre) == "bgra":
        img = Image.frombytes("RGBA", (w, h), datos, "raw", "BGRA").convert("RGB")
    else:
        img = Image.frombytes("RGB", (w, h), datos)
    img.save(destino)
    return destino


def hilos_x264_defecto() -> int | None:
    """En la Pi (4 núcleos) x264 con todos los hilos compite con los rasterizadores: 2."""
    return 2 if (os.cpu_count() or 8) <= 4 else None
