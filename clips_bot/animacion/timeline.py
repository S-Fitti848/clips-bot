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

PROPS_ANIMABLES = ("x", "y", "escala", "rotacion", "opacidad", "mirada", "estirar", "cabeza")
# "cara" de un personaje: (cejas, boca, apertura de la boca)
CARAS = {"feliz": ("arriba", "sonrisa", 0.0), "enojado": ("enojo", "cerrada", 0.0),
         "sorprendido": ("arriba", "o", 0.7), "triste": ("triste", "cerrada", 0.0),
         "risa": ("arriba", "a", 0.55), "grito": ("enojo", "a", 0.8)}
# Ciclos (2026-11-14): pasos por segundo de cada pierna, cuánto rebota el cuerpo, cuánto se balancean
# los brazos (en contrafase con las piernas), cuánto se doblan los codos y cuánto se inclina la cabeza.
CICLOS = {"caminar": (1.7, 16.0, 24.0, 18.0, 3.0), "correr": (2.8, 30.0, 40.0, 75.0, 4.0)}
GRIS_PAUSA = "#4a4f5c"
TIPOS_ELEMENTO = ("personaje", "prop", "gancho", "texto", "tito", "contador")
TRANSICIONES = ("corte", "fundido", "zoom", "barrido", "iris")
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
                "opacidad": float(d.get("opacidad", 1.0)), "mirada": float(d.get("mirada", 0)),
                "estirar": float(d.get("estirar", 1.0)), "cabeza": float(d.get("cabeza", 0))}
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
        fijo = bool(d.get("fijo", tipo in ("gancho", "texto", "contador")))
        el = cls(tipo, d, Pista(claves), base, desde, hasta, fijo)
        if tipo == "tito":   # la mascota de "Así Nació" (tito.py): poses en vez de gestos
            from . import tito as _tito

            for ps in d.get("poses", []):
                if ps.get("pose") not in _tito.POSES:
                    raise ErrorGuion(f"{donde}: pose {ps.get('pose')!r} de Tito desconocida "
                                     f"(hay {', '.join(_tito.POSES)})")
            rnd = random.Random(zlib.crc32(json.dumps(d, sort_keys=True, default=str).encode()))
            t = rnd.uniform(0.6, 1.6)
            while t < dur_escena + 2:
                el.parpadeos.append(t)
                t += rnd.uniform(2.0, 4.0)
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
        sombra = ""
        if self.tipo == "personaje":
            est, dy = self._estado(t, apertura, cuadro, v["mirada"], v["cabeza"])
            contenido = self._pj.svg(est)
            # sombra de contacto en el piso (2026-11-15, "sombras en el piso"): se queda en el piso y se
            # achica y aclara cuando salta
            alto = max(0.0, -dy)
            k = max(0.35, 1 - alto / 420)
            sombra = (f'<ellipse cx="{round(v["x"], 1)}" cy="{round(v["y"] + 6, 1)}" '
                      f'rx="{round(150 * v["escala"] * k, 1)}" ry="{round(30 * v["escala"] * k, 1)}" '
                      f'fill="{P.SOMBRA_TINTE}" opacity="{round(0.28 * k * min(1.0, v["opacidad"]), 3)}"/>')
            v["y"] += dy
        elif self.tipo == "prop":
            params = {k: val for k, val in self.datos.items()
                      if k in ("texto", "color", "encendida", "rota", "forma")}
            contenido = esc.prop(self.datos["nombre"], **params)
        elif self.tipo == "gancho":
            # el gancho se ubica con su propio x/y (centro de la línea): sin traslado extra
            contenido = tx.gancho(self.datos["texto"], tl, self.datos.get("modo", "palabras"),
                                  y=v["y"], tam=int(self.datos.get("tam", 104)), x=v["x"],
                                  color=self.datos.get("color", P.TEXTO_GANCHO))
            return g(g(contenido, -v["x"], -v["y"]), v["x"], v["y"], escala=v["escala"],
                     rot=v["rotacion"], opacidad=v["opacidad"])
        elif self.tipo == "tito":
            from . import tito as _tito

            pose = "saluda"
            for ps in sorted(self.datos.get("poses", []), key=lambda x: float(x.get("t", 0))):
                if float(ps.get("t", 0)) <= tl:
                    pose = ps["pose"]
            habla = bool(self.datos.get("habla", False)) and apertura > 0
            parp = max([1 - abs(t - tp) / 0.09 for tp in self.parpadeos if abs(t - tp) < 0.09] or [0.0])
            giro = float(self.datos.get("giro_aguja", 0.0))     # grados por segundo (viaje en el tiempo)
            contenido = _tito.tito_svg(pose, apertura=apertura if habla else 0.0, parpadeo=parp,
                                       aguja=(giro * tl) % 360 if giro else 40.0,
                                       respiracion=math.sin(2 * math.pi * t / 3.2),
                                       inclinacion=2.5 * math.sin(2 * math.pi * t / 4.1) if habla else 0.0)
        elif self.tipo == "contador":
            # un año que cuenta (viaje en el tiempo): de "de" a "a" en "dur" segundos
            a, b = float(self.datos.get("de", 2026)), float(self.datos.get("a", 1900))
            u = curva("salida")(recortar(tl / max(0.05, float(self.datos.get("dur", 0.8)))))
            tam = int(self.datos.get("tam", 200))
            contenido = texto_con_borde(str(int(round(a + (b - a) * u))), 0, tam * 0.35, tam,
                                        color=self.datos.get("color", P.TEXTO_GANCHO))
        else:   # texto suelto
            tam = int(self.datos.get("tam", 96))
            contenido = texto_con_borde(str(self.datos["texto"]), 0, tam * 0.35, tam,
                                        color=self.datos.get("color", P.TEXTO))
        st = max(0.5, min(1.5, v["estirar"]))
        if abs(st - 1) > 1e-3:   # squash & stretch desde los pies: más alto = más angosto
            return sombra + g(contenido, v["x"], v["y"], v["escala"] * (1 + (1 - st) * 0.5), v["rotacion"],
                              v["opacidad"], escala_y=v["escala"] * st)
        return sombra + g(contenido, v["x"], v["y"], v["escala"], v["rotacion"], v["opacidad"])

    def _ciclo(self, t: float):
        """(tipo, fase, peso 0..1, sentido) del ciclo de caminata/carrera activo en `t`, o None. El peso
        entra y sale en 0,15 s: nada de saltos de pose."""
        for c in self.datos.get("ciclos", []):
            t0, t1 = float(c["t0"]), float(c["t1"])
            if t0 - 0.15 <= t < t1 + 0.15:
                peso = recortar((t - t0 + 0.15) / 0.3) * recortar((t1 + 0.15 - t) / 0.3)
                pasos = CICLOS.get(c.get("tipo"), CICLOS["caminar"])[0]
                return c.get("tipo", "caminar"), 2 * math.pi * pasos * max(0.0, t - t0), peso, \
                    float(c.get("sentido", 0))
        return None

    def _estado(self, t: float, apertura: float, cuadro: int, mirada: float,
                cabeza: float = 0.0) -> tuple[per.Estado, float]:
        gestos = sorted(self.datos.get("gestos", []), key=lambda x: float(x.get("t", 0)))
        previo, actual, t_cambio = "reposo", "reposo", -10.0
        for gs in gestos:
            if float(gs.get("t", 0)) <= t:
                previo, actual, t_cambio = actual, gs["gesto"], float(gs.get("t", 0))
        u = curva("suave")(recortar((t - t_cambio) / 0.3))
        e = per.mezclar_brazos(per.estado_de_gesto(previo), per.estado_de_gesto(actual), u)
        e.respiracion = math.sin(2 * math.pi * t / 3.2)
        e.mirada = mirada
        dy = 0.0
        ciclo = self._ciclo(t)
        if ciclo:
            tipo, fase, peso, sentido = ciclo
            _, rebote, brazo, codo, incl = CICLOS.get(tipo, CICLOS["caminar"])
            s = math.sin(fase)
            # piernas alternadas, el cuerpo sube en cada paso, los brazos en contrafase
            e.pierna_izq, e.pierna_der = peso * max(0.0, s), peso * max(0.0, -s)
            dy = -peso * rebote * abs(s)
            bi = (14 + brazo * s, 12 + codo + 10 * max(0.0, s))
            bd = (14 - brazo * s, 12 + codo + 10 * max(0.0, -s))
            e.brazo_izq = tuple(a + (b - a) * peso for a, b in zip(e.brazo_izq, bi))
            e.brazo_der = tuple(a + (b - a) * peso for a, b in zip(e.brazo_der, bd))
            if sentido:
                e.mirada = sentido
                if peso > 0.5:     # de costado: se da vuelta, de perfil hacia donde camina
                    e.perfil = 1 if sentido > 0 else -1
                    e.zancada = s
                    e.corre = tipo == "correr"
        # la expresión cambia con la acción: "caras" = [{t, cara}] (la última que ya empezó)
        caras = sorted(self.datos.get("caras", []), key=lambda x: float(x.get("t", 0)))
        cara_t = next((c["cara"] for c in reversed(caras) if float(c.get("t", 0)) <= t), None)
        parp = 0.0
        for tp in self.parpadeos:
            d = abs(t - tp)
            if d < 0.09:
                parp = 1 - d / 0.09
                break
        e.parpadeo = parp
        # Cara (canal de marcas, 2026-11-14): la expresión de quien no habla ("cara": feliz,
        # enojado, sorprendido, triste); las cejas del gesto mandan solo si no hay cara.
        cara = cara_t or self.datos.get("cara")
        if cara in CARAS:
            cejas, boca, ap = CARAS[cara]
            e.cejas, e.boca, e.apertura = cejas, boca, ap
        habla = self.datos.get("habla", False)
        if isinstance(habla, list):   # tramos [inicio, fin] locales
            habla = any(a <= t < b for a, b in habla)
        if habla:
            e.apertura = apertura
            e.boca = vocal(cuadro, apertura)
        e.inclinacion = (2.5 * math.sin(2 * math.pi * t / 4.1) if habla and apertura > 0 else 0.0) + cabeza
        if ciclo:
            e.inclinacion += ciclo[2] * CICLOS.get(ciclo[0], CICLOS["caminar"])[4] * math.sin(ciclo[1])
        e.agachar = recortar((1.0 - self.pista.valor("estirar", t, 1.0)) / 0.18)   # al agacharse, rodillas
        return e, dy


# ---- escenas y video ---------------------------------------------------------------


@dataclass
class Escena:
    duracion: float
    fondo: tuple                    # ("cielo", semilla) | ("color", "#hex")
    camara: Pista
    transicion: tuple[str, float]   # (tipo, duración)
    elementos: list[Elemento]
    # Pausa (canal de marcas, 2026-11-14): la escena ANTERIOR queda congelada en su último cuadro y
    # en gris, con el "⏸" arriba; encima, en color, van los elementos de esta (la mascota que comenta).
    congela: bool = False
    # Viaje en el tiempo (2026-11-14): tono sepia de la escena (0 = color, 1 = sepia), de `tono[0]` al
    # empezar a `tono[1]` al terminar; y en una pausa, `girar` = la escena congelada se va en remolino
    # con la cámara de la pausa (sin el gris).
    tono: tuple[float, float] = (0.0, 0.0)
    girar: bool = False

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
        congela = bool(d.get("congela", False))
        elementos = []
        for k, e in enumerate(d.get("elementos", [])):
            if congela:      # sobre la escena congelada todo va en coordenadas de pantalla
                e = {**e, "fijo": True}
            elementos.append(Elemento.desde_dict(e, f"{donde}, elemento {k + 1}", dur))
        tono = d.get("tono", 0.0)
        tono = (float(tono[0]), float(tono[1])) if isinstance(tono, (list, tuple)) else (float(tono), float(tono))
        return cls(dur, fondo, Pista(d.get("camara", [])), (tr.get("tipo", "corte"), tdur),
                   elementos, congela, tono, bool(d.get("girar", False)))

    def tono_en(self, t: float) -> float:
        a, b = self.tono
        return round(a + (b - a) * curva("suave")(recortar(t / self.duracion)), 3) if a != b else a

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
    tono: float = 0.0                  # sepia (0..1) de la imagen, sin tocar los subtítulos


@dataclass
class Video:
    escenas: list[Escena]
    fps: int = P.FPS
    ancho: int = P.ANCHO
    alto: int = P.ALTO
    audio: str | None = None
    subtitulos: list[list[tx.Palabra]] = field(default_factory=list)
    envolvente: list[float] = field(default_factory=list)
    sub_y: float = 1500.0          # alto de los subtítulos ("subtitulos_y" en el dict)
    sub_tam: int = 92              # tamaño de letra ("subtitulos_tam")
    sub_banda: bool = False        # franja semitransparente detrás ("subtitulos_banda")
    # "viral" (Así Nació, 2026-11-14): 1-3 palabras, Montserrat Black, pop por palabra, claves en color con
    # temblor y emoji (subtitulos_virales.py); "clasico" = el de siempre ("subtitulos_estilo")
    sub_estilo: str = "clasico"

    @classmethod
    def desde_dict(cls, d: dict, base: Path | None = None) -> "Video":
        if not d.get("escenas"):
            raise ErrorGuion("el video no tiene escenas")
        escenas = [Escena.desde_dict(e, i) for i, e in enumerate(d["escenas"])]
        if escenas[0].congela:
            raise ErrorGuion("escena 1: una pausa (congela) necesita una escena antes")
        v = cls(escenas, fps=int(d.get("fps", P.FPS)), sub_y=float(d.get("subtitulos_y", 1500.0)),
                sub_tam=int(d.get("subtitulos_tam", 92)), sub_banda=bool(d.get("subtitulos_banda", False)),
                sub_estilo=str(d.get("subtitulos_estilo") or "clasico"))
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
                palabras += [tx.Palabra(p["texto"], float(p["inicio"]), float(p["fin"]),
                                        bool(p.get("clave", False)), bool(p.get("impacto", False)),
                                        str(p.get("emoji") or ""))
                             for p in s["palabras"]]
            else:
                palabras += tx.palabras_de_texto(s["texto"], float(s["inicio"]), float(s["fin"]))
        if v.sub_estilo == "viral":
            from . import subtitulos_virales as sv

            v.subtitulos = sv.agrupar(palabras)
        else:
            v.subtitulos = tx.agrupar(palabras)
        return v

    def encima(self, t: float) -> str:
        """Los subtítulos del segundo `t` (SVG en coordenadas de pantalla; los usa también Remotion)."""
        if not self.subtitulos:
            return ""
        if self.sub_estilo == "viral":
            from . import subtitulos_virales as sv

            return sv.subtitulo(self.subtitulos, t, y=self.sub_y)
        encima = tx.subtitulo(self.subtitulos, t, y=self.sub_y, tam=self.sub_tam)
        if encima and self.sub_banda:
            alto = self.sub_tam * 1.45
            encima = (f'<rect x="0" y="{round(self.sub_y - alto / 2, 1)}" width="{P.ANCHO}" '
                      f'height="{round(alto, 1)}" fill="#000000" opacity="0.42"/>') + encima
        return encima

    @classmethod
    def desde_json(cls, ruta: Path) -> "Video":
        return cls.desde_dict(json.loads(Path(ruta).read_text(encoding="utf-8")), ruta.parent)

    @property
    def duracion(self) -> float:
        return sum(e.duracion for e in self.escenas)

    @property
    def total_cuadros(self) -> int:
        return int(round(self.duracion * self.fps))

    def _capa(self, escena: Escena, t: float, cuadro: int, apertura: float | None = None) -> CapaEscena:
        ap = (self.envolvente[cuadro] if cuadro < len(self.envolvente) else 0.0)             if apertura is None else apertura
        frente, fijo = [], []
        for el in escena.elementos:
            if el.visible(t):
                (fijo if el.fijo else frente).append(el.svg(t, ap, cuadro))
        return CapaEscena(escena.fondo, escena.camara_en(t), "".join(frente), "".join(fijo))

    def _capa_k(self, k: int, t: float, cuadro: int, apertura: float | None = None) -> CapaEscena:
        """La capa de la escena `k`; si es una pausa, la anterior congelada y en gris + la suya."""
        e = self.escenas[k]
        if not e.congela or k == 0:
            return self._capa(e, t, cuadro, apertura)
        j = k - 1
        while j > 0 and self.escenas[j].congela:
            j -= 1
        prev = self.escenas[j]
        base = self._capa(prev, prev.duracion - 1e-3, cuadro, apertura=0.0)   # nadie habla atrás
        propia = self._capa(e, t, cuadro, apertura)
        if e.girar:     # viaje en el tiempo: la escena congelada se va en remolino, sin gris
            return CapaEscena(base.fondo, e.camara_en(t), base.frente + base.fijo,
                              propia.frente + propia.fijo)
        u = recortar(t / 0.2) * recortar((e.duracion - t) / 0.2)
        gris = (f'<rect width="{P.ANCHO}" height="{P.ALTO}" fill="{GRIS_PAUSA}" '
                f'opacity="{round(0.62 * u, 3)}"/>')
        icono = g(esc.icono_pausa(), 110, 390, opacidad=u) if u > 0.01 else ""
        return CapaEscena(base.fondo, base.camara, base.frente,
                          base.fijo + gris + icono + propia.frente + propia.fijo)

    def cuadro(self, i: int) -> Cuadro:
        t = i / self.fps
        inicio = 0.0
        for k, e in enumerate(self.escenas):
            if t < inicio + e.duracion or k == len(self.escenas) - 1:
                tl = t - inicio
                a = self._capa_k(k, tl, i)
                b, trans = None, None
                tipo, tdur = e.transicion
                if k > 0 and tdur > 0 and tl < tdur:
                    prev = self.escenas[k - 1]
                    b = self._capa_k(k - 1, prev.duracion + tl, i)
                    trans = (tipo, round(tl / tdur, 4))
                return Cuadro(a, b, trans, self.encima(t), e.tono_en(tl))
            inicio += e.duracion
        raise IndexError(i)
