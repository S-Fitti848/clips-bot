"""Personajes en SVG con partes animables.

Coordenadas locales: (0, 0) es el piso entre los pies; el personaje mide ~680 px a escala 1 y
mira al frente. "der"/"izq" son los lados de la PANTALLA (no del personaje).

Un personaje se dibuja con un `Estado` (qué hace en ese cuadro): parpadeo, boca, cejas, ángulos
de los brazos y respiración. Los gestos (`GESTOS`) son ángulos de brazos con nombre; la línea de
tiempo interpola entre gestos, así un "señalar" no aparece de golpe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from . import paleta as P
from .svg import camino, circulo, elipse, g, linea_gruesa, n, trazo

BLANCO_SUCIO = "#f2ece0"

# ---- estado de un cuadro ------------------------------------------------------


@dataclass
class Estado:
    parpadeo: float = 0.0          # 0 abiertos, 1 cerrados
    boca: str = "cerrada"          # cerrada | a | e | o | sonrisa
    apertura: float = 0.0          # 0..1, cuánto se abre la boca (sale de la voz)
    cejas: str = "normal"          # normal | arriba | enojo | triste
    brazo_izq: tuple[float, float] = (12.0, 10.0)   # (hombro, codo) en grados, 0 = colgando
    brazo_der: tuple[float, float] = (12.0, 10.0)
    respiracion: float = 0.0       # -1..1 (seno)
    mirada: float = 0.0            # -1 izquierda .. 1 derecha
    inclinacion: float = 0.0       # grados de la cabeza


# Gestos: ángulos (hombro, codo) de cada brazo. Hombro 0 = colgando, 90 = horizontal hacia afuera,
# 180 = arriba. Codo: cuánto más gira el antebrazo (positivo = hacia arriba/adentro).
GESTOS: dict[str, dict] = {
    "reposo": {"izq": (12, 10), "der": (12, 10)},
    "senalar": {"izq": (12, 10), "der": (115, -5), "cejas": "arriba"},
    "senalar_izq": {"izq": (115, -5), "der": (12, 10), "cejas": "arriba"},
    "encogerse": {"izq": (55, 95), "der": (55, 95), "cejas": "triste"},
    "sorpresa": {"izq": (150, 20), "der": (150, 20), "cejas": "arriba"},
    "saludar": {"izq": (12, 10), "der": (140, 35)},
    "pensar": {"izq": (12, 10), "der": (10, 205), "cejas": "enojo"},
    "explicar": {"izq": (40, 70), "der": (40, 70)},
}


def estado_de_gesto(nombre: str, base: Estado | None = None) -> Estado:
    gs = GESTOS.get(nombre, GESTOS["reposo"])
    e = base or Estado()
    return replace(e, brazo_izq=tuple(gs["izq"]), brazo_der=tuple(gs["der"]),
                   cejas=gs.get("cejas", "normal"))


def mezclar_brazos(a: Estado, b: Estado, t: float) -> Estado:
    """Interpola los brazos de `a` hacia `b` (t de 0 a 1). Las cejas cambian a la mitad."""
    def lerp2(p, q):
        return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
    return replace(a, brazo_izq=lerp2(a.brazo_izq, b.brazo_izq),
                   brazo_der=lerp2(a.brazo_der, b.brazo_der),
                   cejas=b.cejas if t >= 0.5 else a.cejas)


# ---- el personaje -------------------------------------------------------------


@dataclass
class Personaje:
    nombre: str = "narrador"
    piel: str = P.PIEL[0]
    pelo: str = P.PELO[0]
    peinado: str = "jopo"          # jopo | corto | largo | rulos | pelado
    sombrero: str = "ninguno"      # ninguno | gorra | galera
    color_sombrero: str = P.ROJO
    ropa: str = P.TURQUESA
    pantalon: str = "#34405e"
    anteojos: bool = False
    bigote: bool = False
    cachetes: bool = True
    alto_cuerpo: float = 1.0       # 0.85 = más bajo/compacto

    R_CABEZA = 118
    LARGO_BRAZO = 112
    LARGO_ANTEBRAZO = 104
    ANCHO_BRAZO = 30

    def svg(self, e: Estado | None = None) -> str:
        e = e or Estado()
        k = self.alto_cuerpo
        resp = 1 + 0.014 * e.respiracion           # el torso "respira" (alto del torso)
        piso_torso = -150 * k
        tope_torso = piso_torso - 270 * k * resp
        cy_cabeza = tope_torso - self.R_CABEZA + 22
        hombro_y = tope_torso + 38
        return "".join([
            self._piernas(piso_torso),
            self._torso(piso_torso, tope_torso),
            self._brazo(-1, hombro_y, *e.brazo_izq),
            self._brazo(1, hombro_y, *e.brazo_der),
            g(self._cabeza(e), 0, cy_cabeza, rot=e.inclinacion),
        ])

    # -- partes --
    def _piernas(self, piso_torso: float) -> str:
        p = []
        for s in (-1, 1):
            x = s * 42
            p.append(linea_gruesa([(x, piso_torso + 10), (x, -28)], self.pantalon, 44))
            # zapato: del talón (adentro) a la punta (afuera)
            p.append(camino(f"M{n(x - s * 30)} 0 Q{n(x - s * 30)} -46 {n(x + s * 6)} -46 "
                            f"Q{n(x + s * 50)} -46 {n(x + s * 52)} 0 Z", "#2a2a33",
                            ancho=P.TRAZO_FINO + 2))
        return "".join(p)

    def _torso(self, piso: float, tope: float) -> str:
        w_ab, w_ar = 118, 98
        d = (f"M{-w_ab} {n(piso)} L{w_ab} {n(piso)} "
             f"Q{w_ab + 6} {n(tope + 40)} {w_ar} {n(tope + 10)} "
             f"Q{w_ar - 10} {n(tope)} 0 {n(tope)} "
             f"Q{-w_ar + 10} {n(tope)} {-w_ar} {n(tope + 10)} "
             f"Q{-w_ab - 6} {n(tope + 40)} {-w_ab} {n(piso)} Z")
        cuello = (f'<path d="M-30 {n(tope + 2)} Q0 {n(tope + 34)} 30 {n(tope + 2)}" '
                  f'fill="{BLANCO_SUCIO}" {trazo(ancho=P.TRAZO_FINO)}/>')
        return camino(d, self.ropa) + cuello

    def _brazo(self, lado: int, hombro_y: float, hombro: float, codo: float) -> str:
        x0 = lado * 92
        a1 = math.radians(hombro)
        a2 = math.radians(hombro + codo)
        x1 = x0 + lado * math.sin(a1) * self.LARGO_BRAZO
        y1 = hombro_y + math.cos(a1) * self.LARGO_BRAZO
        x2 = x1 + lado * math.sin(a2) * self.LARGO_ANTEBRAZO
        y2 = y1 + math.cos(a2) * self.LARGO_ANTEBRAZO
        return (linea_gruesa([(x0, hombro_y), (x1, y1), (x2, y2)], self.ropa, self.ANCHO_BRAZO)
                + circulo(x2, y2, 24, self.piel))

    def _cabeza(self, e: Estado) -> str:
        R = self.R_CABEZA
        p = []
        if self.peinado == "largo":   # pelo de atrás, debajo de la cara
            p.append(camino(f"M{-R - 14} -10 Q{-R - 24} {R + 70} {-R + 30} {R + 60} L{R - 30} "
                            f"{R + 60} Q{R + 24} {R + 70} {R + 14} -10 Z", self.pelo))
        for s in (-1, 1):             # orejas
            p.append(circulo(s * (R - 4), 12, 26, self.piel))
        p.append(circulo(0, 0, R, self.piel))
        p.append(self._pelo())
        if self.cachetes:
            for s in (-1, 1):
                p.append(f'<ellipse cx="{s * 66}" cy="38" rx="22" ry="13" fill="{P.ROSA}" '
                         f'opacity="0.45"/>')
        p.append(self._ojos(e))
        p.append(self._cejas(e.cejas))
        if self.anteojos:
            p.append(self._anteojos())
        if self.bigote:
            p.append(camino("M-44 44 Q-22 26 0 40 Q22 26 44 44 Q22 58 0 48 Q-22 58 -44 44 Z",
                            self.pelo, ancho=P.TRAZO_FINO))
        p.append(self._boca(e))
        p.append(self._sombrero())
        return "".join(p)

    def _pelo(self) -> str:
        R = self.R_CABEZA
        c = self.pelo
        if self.peinado == "pelado":
            return ""
        if self.peinado == "rulos":
            bolas = [(-80, -70), (-40, -100), (0, -110), (40, -100), (80, -70), (-104, -26),
                     (104, -26)]
            return "".join(circulo(x, y, 40, c) for x, y in bolas)
        if self.peinado == "jopo":
            return camino(f"M{-R + 4} -20 Q{-R} {-R - 10} -10 {-R - 30} Q60 {-R - 62} "
                          f"{R - 10} {-R + 4} Q{R + 6} -60 {R - 6} -22 Q60 -70 10 -64 "
                          f"Q-50 -62 {-R + 4} -20 Z", c)
        # corto / largo (la parte de arriba)
        return camino(f"M{-R + 2} -14 Q{-R + 6} {-R - 14} 0 {-R - 12} Q{R - 6} {-R - 14} "
                      f"{R - 2} -14 Q50 -64 0 -60 Q-50 -64 {-R + 2} -14 Z", c)

    def _ojos(self, e: Estado) -> str:
        p = []
        cierre = max(0.0, min(1.0, e.parpadeo))
        for s in (-1, 1):
            cx, cy = s * 42, -8
            if cierre > 0.85:   # cerrado: una rayita curva
                p.append(camino(f"M{cx - 20} {cy} Q{cx} {cy + 10} {cx + 20} {cy}",
                                ancho=P.TRAZO_FINO + 1))
                continue
            ry = 26 * (1 - cierre)
            p.append(elipse(cx, cy, 20, ry, P.BLANCO, ancho=P.TRAZO_FINO))
            pr = min(11, ry * 0.6)
            p.append(circulo(cx + 6 * e.mirada, cy + 3, pr, P.CONTORNO, borde=False))
            p.append(circulo(cx + 6 * e.mirada + 4, cy - 2, pr * 0.35, P.BLANCO, borde=False))
        return "".join(p)

    def _cejas(self, tipo: str) -> str:
        dy, rot = {"normal": (0, 0), "arriba": (-16, -6), "enojo": (2, 14),
                   "triste": (-6, -16)}.get(tipo, (0, 0))
        return "".join(g(f'<path d="M-20 0 L20 0" {trazo(ancho=11)}/>', s * 42, -50 + dy,
                         rot=s * rot) for s in (-1, 1))

    def _anteojos(self) -> str:
        return (f'<g fill="none" {trazo(ancho=P.TRAZO_FINO + 1)}>'
                '<circle cx="-42" cy="-8" r="32"/><circle cx="42" cy="-8" r="32"/>'
                '<path d="M-10 -10 Q0 -18 10 -10"/></g>')

    def _boca(self, e: Estado) -> str:
        y = 58
        ap = max(0.0, min(1.0, e.apertura))
        if e.boca in ("cerrada", "sonrisa") or ap < 0.08:
            ancho, curva = (30, 14) if e.boca == "cerrada" else (40, 26)
            return camino(f"M{-ancho} {y - 4} Q0 {y + curva} {ancho} {y - 4}")
        rx, ry = {"a": (32, 8 + 30 * ap), "e": (40, 6 + 16 * ap),
                  "o": (16 + 6 * ap, 10 + 24 * ap)}.get(e.boca, (30, 8 + 26 * ap))
        cy = y + ry * 0.35
        interior = elipse(0, cy, rx, ry, "#5a1e2a", ancho=P.TRAZO_FINO + 1)
        lengua = ""
        if ry > 16:
            lengua = elipse(0, cy + ry * 0.5, rx * 0.55, ry * 0.35, "#ff7a8a", borde=False)
        return interior + lengua

    def _sombrero(self) -> str:
        R = self.R_CABEZA
        c = self.color_sombrero
        if self.sombrero == "gorra":
            return (camino(f"M{-R + 4} -40 Q{-R + 10} {-R - 30} 0 {-R - 30} Q{R - 10} {-R - 30} "
                           f"{R - 4} -40 Z", c)
                    + camino(f"M{R - 30} -44 Q{R + 70} -46 {R + 74} -30 Q{R + 20} -24 "
                             f"{R - 30} -30 Z", c))
        if self.sombrero == "galera":
            return (camino(f"M-80 {-R + 10} L-74 {-R - 120} L74 {-R - 120} L80 {-R + 10} Z", c)
                    + f'<rect x="-78" y="{-R - 20}" width="156" height="24" fill="{P.ROJO}" '
                      f'{trazo(ancho=P.TRAZO_FINO)}/>'
                    + elipse(0, -R + 12, 130, 22, c))
        return ""


# ---- elenco -------------------------------------------------------------------

ELENCO: dict[str, Personaje] = {
    "narrador": Personaje("narrador", piel=P.PIEL[0], pelo=P.PELO[1], peinado="jopo",
                          ropa=P.TURQUESA, anteojos=True),
    "vecina": Personaje("vecina", piel=P.PIEL[1], pelo=P.PELO[0], peinado="rulos",
                        ropa=P.ROSA, pantalon="#5b3b6e", alto_cuerpo=0.92),
    "abuelo": Personaje("abuelo", piel=P.PIEL[0], pelo=P.PELO[4], peinado="pelado",
                        sombrero="galera", color_sombrero="#2b2b33", ropa=P.VIOLETA,
                        bigote=True, alto_cuerpo=0.9),
    "pibe": Personaje("pibe", piel=P.PIEL[2], pelo=P.PELO[3], peinado="corto", sombrero="gorra",
                      color_sombrero=P.ROJO, ropa=P.AMARILLO, alto_cuerpo=0.85),
}


def personaje(nombre: str, **cambios) -> Personaje:
    """Del elenco, con cambios paramétricos: `personaje('pibe', ropa='#00aa88')`. Un nombre que no
    está en el elenco arranca del narrador."""
    base = ELENCO.get(nombre, ELENCO["narrador"])
    return replace(base, **cambios) if cambios else base
