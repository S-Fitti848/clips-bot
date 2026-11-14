"""Línea de tiempo: un video descripto con DATOS (dict/JSON) → la descripción de cada cuadro.

Formato (todo en segundos; los tiempos de una escena son locales a esa escena):

    {
      "fps": 30,
      "audio": "voz.wav",                       # opcional: la boca de quien "habla" sigue la voz
      "subtitulos": [{"texto": "Hola a todos", "inicio": 0.3, "fin": 1.4}, ...],
      "escenas": [
        {
          "duracion": 5,
          "fondo": {"tipo": "ciudad", "semilla": 2},   # cielo | ciudad | oficina | globo  (o "color")
          "transicion": {"tipo": "zoom", "duracion": 0.4},  # corte | fundido | zoom | barrido
          "camara": [{"t": 0, "zoom": 1}, {"t": 5, "zoom": 1.12, "y": -40, "easing": "suave"}],
          "elementos": [
            {"tipo": "personaje", "nombre": "narrador", "x": 540, "y": 1700, "escala": 1.1,
             "habla": true, "entrada": "abajo",
             "gestos": [{"t": 0, "gesto": "saludar"}, {"t": 2, "gesto": "senalar"}]},
            {"tipo": "prop", "nombre": "moneda", "x": 820, "y": 900, "entrada": "rebote",
             "keyframes": [{"t": 1, "rotacion": 0}, {"t": 3, "rotacion": 360, "easing": "lineal"}]},
            {"tipo": "gancho", "texto": "¿Sabías esto?", "modo": "palabras", "y": 360},
            {"tipo": "texto", "texto": "1999", "x": 540, "y": 700, "tam": 140}
          ]
        }
      ]
    }

Propiedades animables con keyframes: x, y, escala, rotacion, opacidad (y "mirada" en personajes).
Cada keyframe dice cómo se LLEGA a él (`easing`, por defecto "suave"). Antes del primero vale el
primero; después del último, el último. Las transiciones se comen el arranque de la escena nueva:
la anterior sigue andando por debajo mientras dura. El largo total = suma de las duraciones.
"""
from __future__ import annotations

import json
import math
import random
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from . import escenas as esc
from . import paleta as P
from . import personajes as per
from . import texto as tx
from .audio import vocal
from .easing import curva, recortar
from .svg import g, texto_con_borde

PROPS_ANIMABLES = ("x", "y", "escala", "rotacion", "opacidad", "mirada")
TIPOS_ELEMENTO = ("personaje", "prop", "gancho", "texto")
TRANSICIONES = ("corte", "fundido", "zoom", "barrido")
ENTRADAS = ("rebote", "izquierda", "derecha", "abajo", "arriba", "fundido")


class ErrorGuion(ValueError):
    """La descripción del video no es válida (dice qué y dónde)."""


# ---- pistas de keyframes ------------------------------------------------------


@dataclass
class Pista:
    """Keyframes de varias propiedades. `valor(prop, t, defecto)` interpola con el easing del
    keyframe de llegada."""
    claves: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.claves = sorted(self.claves, key=lambda k: float(k.get("t", 0)))
        self._por_prop: dict[str, list[tuple[float, float, str | None]]] = {}
        for k in self.claves:
            for prop, v in k.items():
                if prop in ("t", "easing"):
                    continue
                self._por_prop.setdefault(prop, []).append(
                    (float(k.get("t", 0)), float(v), k.get("easing")))

    def valor(self, prop: str, t: float, defecto: float) -> float:
        ks = self._por_prop.get(prop)
        if not ks:
            return defecto
        if t <= ks[0][0]:
            return ks[0][1]
        for (t0, v0, _), (t1, v1, ez) in zip(ks, ks[1:]):
            if t < t1:
                u = recortar((t - t0) / (t1 - t0)) if t1 > t0 else 1.0
                return v0 + (v1 - v0) * curva(ez)(u)
        return ks[-1][1]


def claves_de_entrada(tipo: str, base: dict, desde: float, dur: float = 0.5) -> list[dict]:
    """Keyframes automáticos para una entrada con nombre (así un guion no tiene que escribirlos)."""
    x, y, e = base["x"], base["y"], base["escala"]
    t0, t1 = desde, desde + dur
    if tipo == "rebote":
        return [{"t": t0, "escala": 0.0}, {"t": t1, "escala": e, "easing": "rebote"}]
    if tipo == "fundido":
        return [{"t": t0, "opacidad": 0.0}, {"t": t1, "opacidad": 1.0, "easing": "suave"}]
    dx, dy = {"izquierda": (-900, 0), "derecha": (900, 0), "abajo": (0, 1100),
              "arriba": (0, -900)}[tipo]
    return [{"t": t0, "x": x + dx, "y": y + dy},
            {"t": t1, "x": x, "y": y, "easing": "salida"}]


# ---- elementos ------------------------------------------------------------------


@dataclass
class Elemento:
    tipo: str
    datos: dict
    pista: Pista
    base: dict
    desde: float = 0.0
    hasta: float = math.inf
    fijo: bool = False             # True = no lo mueve la cámara (textos en pantalla)
    parpadeos: list[float] = field(default_factory=list)

    @classmethod
    def desde_dict(cls, d: dict, donde: str, dur_escena: float) -> "Elemento":
        tipo = d.get("tipo")
        if tipo not in TIPOS_ELEMENTO:
            raise ErrorGuion(f"{donde}: tipo {tipo!r} desconocido (hay {', '.join(TIPOS_ELEMENTO)})")
        if tipo == "prop" and d.get("nombre") not in esc.PROPS:
            raise ErrorGuion(f"{donde}: prop {d.get('nombre')!r} desconocido "
                             f"(hay {', '.join(sorted(esc.PROPS))})")
        if tipo in ("gancho", "texto") and not str(d.get("texto", "")).strip():
            raise ErrorGuion(f"{donde}: {tipo} sin texto")
        base = {"x": float(d.get("x", P.ANCHO / 2)), "y": float(d.get("y", P.ALTO / 2)),
                "escala": float(d.get("escala", 1.0)), "rotacion": float(d.get("rotacion", 0)),
                "opacidad": float(d.get("opacidad", 1.0)), "mirada": float(d.get("mirada", 0))}
        desde = float(d.get("desde", 0.0))
        hasta = float(d.get("hasta", math.inf))
        claves = list(d.get("keyframes", []))
        for k in claves:
            malas = set(k) - set(PROPS_ANIMABLES) - {"t", "easing"}
            if malas:
                raise ErrorGuion(f"{donde}: keyframe con propiedades desconocidas {sorted(malas)}")
            if k.get("easing"):
                try:
                    curva(k["easing"])
                except ValueError as e:
                    raise ErrorGuion(f"{donde}: {e}") from None
        if d.get("entrada"):
            if d["entrada"] not in ENTRADAS:
                raise ErrorGuion(f"{donde}: entrada {d['entrada']!r} desconocida "
                                 f"(hay {', '.join(ENTRADAS)})")
            claves = claves_de_entrada(d["entrada"], base, desde) + claves
        if d.get("salida") == "fundido" and hasta < math.inf:
            claves += [{"t": hasta - 0.35, "opacidad": 1.0}, {"t": hasta, "opacidad": 0.0}]
        fijo = bool(d.get("fijo", tipo in ("gancho", "texto")))
        el = cls(tipo, d, Pista(claves), base, desde, hasta, fijo)
        if tipo == "personaje":
            for gs in d.get("gestos", []):
                if gs.get("gesto") not in per.GESTOS:
                    raise ErrorGuion(f"{donde}: gesto {gs.get('gesto')!r} desconocido "
                                     f"(hay {', '.join(per.GESTOS)})")
            rnd = random.Random(zlib.crc32(json.dumps(d, sort_keys=True, default=str).encode()))
            t = rnd.uniform(0.6, 2.0)
            while t < dur_escena + 2:
                el.parpadeos.append(t)
                t += rnd.uniform(2.2, 4.6)
            el._pj = per.personaje(d.get("nombre", "narrador"), **d.get("cambios", {}))
        return el

    def visible(self, t: float) -> bool:
        return self.desde <= t < self.hasta

    def svg(self, t: float, apertura: float, cuadro: int) -> str:
        v = {k: self.pista.valor(k, t, self.base[k]) for k in PROPS_ANIMABLES}
        if v["opacidad"] <= 0.001 or v["escala"] <= 0.001:
            return ""
        tl = t - self.desde
        if self.tipo == "personaje":
            contenido = self._pj.svg(self._estado(t, apertura, cuadro, v["mirada"]))
        elif self.tipo == "prop":
            params = {k: val for k, val in self.datos.items() if k in ("texto", "color", "encendida")}
            contenido = esc.prop(self.datos["nombre"], **params)
        elif self.tipo == "gancho":
            # el gancho se ubica con su propio x/y (centro de la línea): sin traslado extra
            contenido = tx.gancho(self.datos["texto"], tl, self.datos.get("modo", "palabras"),
                                  y=v["y"], tam=int(self.datos.get("tam", 104)), x=v["x"],
                                  color=self.datos.get("color", P.TEXTO_GANCHO))
            return g(g(contenido, -v["x"], -v["y"]), v["x"], v["y"], escala=v["escala"],
                     rot=v["rotacion"], opacidad=v["opacidad"])
        else:   # texto suelto
            tam = int(self.datos.get("tam", 96))
            contenido = texto_con_borde(str(self.datos["texto"]), 0, tam * 0.35, tam,
                                        color=self.datos.get("color", P.TEXTO))
        return g(contenido, v["x"], v["y"], v["escala"], v["rotacion"], v["opacidad"])

    def _estado(self, t: float, apertura: float, cuadro: int, mirada: float) -> per.Estado:
        gestos = sorted(self.datos.get("gestos", []), key=lambda x: float(x.get("t", 0)))
        previo, actual, t_cambio = "reposo", "reposo", -10.0
        for gs in gestos:
            if float(gs.get("t", 0)) <= t:
                previo, actual, t_cambio = actual, gs["gesto"], float(gs.get("t", 0))
        u = curva("suave")(recortar((t - t_cambio) / 0.3))
        e = per.mezclar_brazos(per.estado_de_gesto(previo), per.estado_de_gesto(actual), u)
        e.respiracion = math.sin(2 * math.pi * t / 3.2)
        e.mirada = mirada
        parp = 0.0
        for tp in self.parpadeos:
            d = abs(t - tp)
            if d < 0.09:
                parp = 1 - d / 0.09
                break
        e.parpadeo = parp
        habla = self.datos.get("habla", False)
        if isinstance(habla, list):   # tramos [inicio, fin] locales
            habla = any(a <= t < b for a, b in habla)
        if habla:
            e.apertura = apertura
            e.boca = vocal(cuadro, apertura)
        e.inclinacion = 2.5 * math.sin(2 * math.pi * t / 4.1) if habla and apertura > 0 else 0.0
        return e


# ---- escenas y video ---------------------------------------------------------------


@dataclass
class Escena:
    duracion: float
    fondo: tuple                    # ("cielo", semilla) | ("color", "#hex")
    camara: Pista
    transicion: tuple[str, float]   # (tipo, duración)
    elementos: list[Elemento]

    @classmethod
    def desde_dict(cls, d: dict, i: int) -> "Escena":
        donde = f"escena {i + 1}"
        try:
            dur = float(d["duracion"])
        except (KeyError, TypeError, ValueError):
            raise ErrorGuion(f"{donde}: falta 'duracion' (segundos)") from None
        if dur <= 0:
            raise ErrorGuion(f"{donde}: duración {dur} ≤ 0")
        f = d.get("fondo", {"tipo": "cielo"})
        if isinstance(f, str):
            f = {"tipo": f}
        if f.get("tipo") == "color":
            fondo = ("color", f.get("color", P.BLANCO))
        elif f.get("tipo") in esc.FONDOS:
            fondo = (f["tipo"], int(f.get("semilla", 1)))
        else:
            raise ErrorGuion(f"{donde}: fondo {f.get('tipo')!r} desconocido "
                             f"(hay color, {', '.join(sorted(esc.FONDOS))})")
        tr = d.get("transicion", {"tipo": "corte"})
        if isinstance(tr, str):
            tr = {"tipo": tr}
        if tr.get("tipo", "corte") not in TRANSICIONES:
            raise ErrorGuion(f"{donde}: transición {tr.get('tipo')!r} desconocida "
                             f"(hay {', '.join(TRANSICIONES)})")
        tdur = 0.0 if tr.get("tipo", "corte") == "corte" else float(tr.get("duracion", 0.4))
        tdur = min(tdur, dur * 0.5)
        elementos = [Elemento.desde_dict(e, f"{donde}, elemento {k + 1}", dur)
                     for k, e in enumerate(d.get("elementos", []))]
        return cls(dur, fondo, Pista(d.get("camara", [])), (tr.get("tipo", "corte"), tdur),
                   elementos)

    def camara_en(self, t: float) -> tuple[float, float, float, float]:
        """(zoom, dx, dy, rotación) de la cámara a los `t` segundos de la escena."""
        z = max(1.0, self.camara.valor("zoom", t, 1.0))   # nunca se ve afuera del fondo
        # la corrida se limita a lo que deja el zoom: el encuadre no se sale del dibujo
        mx, my = P.ANCHO / 2 * (1 - 1 / z), P.ALTO / 2 * (1 - 1 / z)
        dx = min(mx, max(-mx, self.camara.valor("x", t, 0.0)))
        dy = min(my, max(-my, self.camara.valor("y", t, 0.0)))
        rot = self.camara.valor("rotacion", t, 0.0) if z > 1.0 else 0.0
        return (round(z, 4), round(dx, 1), round(dy, 1), round(rot, 2))


@dataclass(frozen=True)
class CapaEscena:
    """Lo que hace falta para rasterizar una escena en un cuadro (comparable: si dos cuadros
    seguidos son iguales, el segundo no se vuelve a dibujar)."""
    fondo: tuple
    camara: tuple
    frente: str        # SVG (cuerpo, sin <svg>) afectado por la cámara
    fijo: str          # SVG en coordenadas de pantalla


@dataclass(frozen=True)
class Cuadro:
    a: CapaEscena
    b: CapaEscena | None = None        # escena que sale (durante una transición)
    transicion: tuple | None = None    # (tipo, u 0..1)
    encima: str = ""                   # subtítulos


@dataclass
class Video:
    escenas: list[Escena]
    fps: int = P.FPS
    ancho: int = P.ANCHO
    alto: int = P.ALTO
    audio: str | None = None
    subtitulos: list[list[tx.Palabra]] = field(default_factory=list)
    envolvente: list[float] = field(default_factory=list)

    @classmethod
    def desde_dict(cls, d: dict, base: Path | None = None) -> "Video":
        if not d.get("escenas"):
            raise ErrorGuion("el video no tiene escenas")
        escenas = [Escena.desde_dict(e, i) for i, e in enumerate(d["escenas"])]
        v = cls(escenas, fps=int(d.get("fps", P.FPS)))
        if d.get("audio"):
            ruta = Path(d["audio"])
            if base and not ruta.is_absolute():
                ruta = base / ruta
            if not ruta.is_file():
                raise ErrorGuion(f"no existe el audio {ruta}")
            from .audio import envolvente

            v.audio = str(ruta)
            v.envolvente = envolvente(ruta, v.fps)
        palabras: list[tx.Palabra] = []
        for s in d.get("subtitulos", []):
            if "palabras" in s:   # tiempos por palabra (ej. de Whisper)
                palabras += [tx.Palabra(p["texto"], float(p["inicio"]), float(p["fin"]))
                             for p in s["palabras"]]
            else:
                palabras += tx.palabras_de_texto(s["texto"], float(s["inicio"]), float(s["fin"]))
        v.subtitulos = tx.agrupar(palabras)
        return v

    @classmethod
    def desde_json(cls, ruta: Path) -> "Video":
        return cls.desde_dict(json.loads(Path(ruta).read_text(encoding="utf-8")), ruta.parent)

    @property
    def duracion(self) -> float:
        return sum(e.duracion for e in self.escenas)

    @property
    def total_cuadros(self) -> int:
        return int(round(self.duracion * self.fps))

    def _capa(self, escena: Escena, t: float, cuadro: int) -> CapaEscena:
        ap = self.envolvente[cuadro] if cuadro < len(self.envolvente) else 0.0
        frente, fijo = [], []
        for el in escena.elementos:
            if el.visible(t):
                (fijo if el.fijo else frente).append(el.svg(t, ap, cuadro))
        return CapaEscena(escena.fondo, escena.camara_en(t), "".join(frente), "".join(fijo))

    def cuadro(self, i: int) -> Cuadro:
        t = i / self.fps
        inicio = 0.0
        for k, e in enumerate(self.escenas):
            if t < inicio + e.duracion or k == len(self.escenas) - 1:
                tl = t - inicio
                a = self._capa(e, tl, i)
                b, trans = None, None
                tipo, tdur = e.transicion
                if k > 0 and tdur > 0 and tl < tdur:
                    prev = self.escenas[k - 1]
                    b = self._capa(prev, prev.duracion + tl, i)
                    trans = (tipo, round(tl / tdur, 4))
                encima = tx.subtitulo(self.subtitulos, t) if self.subtitulos else ""
                return Cuadro(a, b, trans, encima)
            inicio += e.duracion
        raise IndexError(i)
