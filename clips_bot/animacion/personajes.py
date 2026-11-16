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
from .svg import aclarar, camino, circulo, elipse, g, linea_gruesa, n, oscurecer, trazo

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
    # Piernas (2026-11-14, "se mueven rígidos"): cuánto se levanta cada pie (0..1); la rodilla se
    # dobla hacia afuera y el pie sube. `agachar` (0..1): las dos rodillas dobladas (anticipación).
    pierna_izq: float = 0.0
    pierna_der: float = 0.0
    agachar: float = 0.0
    # De PERFIL al caminar de costado (Santi, 2026-11-14): 1 = mira a la derecha de la pantalla, -1 a la
    # izquierda, 0 = de frente. `zancada` (-1..1) abre las piernas y balancea los brazos en el plano.
    perfil: int = 0
    zancada: float = 0.0
    corre: bool = False
    espaldas: bool = False        # de espaldas: la nuca con el pelo, sin cara ni botones


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
    # Acciones del canal de marcas (2026-11-14): se alternan de a pares (caminar = paso_a/paso_b
    # cada ~0,25 s) y la mezcla de 0,3 s entre gestos hace el balanceo. Ver animacion/acciones.py.
    "paso_a": {"izq": (32, 22), "der": (-14, 14)},
    "paso_b": {"izq": (-14, 14), "der": (32, 22)},
    "correr_a": {"izq": (70, 80), "der": (-30, 70), "cejas": "arriba"},
    "correr_b": {"izq": (-30, 70), "der": (70, 80), "cejas": "arriba"},
    "retar_a": {"izq": (40, 115), "der": (138, 22), "cejas": "enojo"},
    "retar_b": {"izq": (40, 115), "der": (118, 48), "cejas": "enojo"},
    "martillo_arriba": {"izq": (40, 70), "der": (155, 25), "cejas": "enojo"},
    "martillo_abajo": {"izq": (40, 70), "der": (75, 35), "cejas": "enojo"},
    "lanzar_atras": {"izq": (40, 40), "der": (165, 40)},
    "lanzar": {"izq": (30, 20), "der": (95, -25), "cejas": "arriba"},
    "atrapar": {"izq": (100, -15), "der": (100, -15), "cejas": "arriba"},
    "festejar": {"izq": (168, 8), "der": (168, 8), "cejas": "arriba"},
    "cubrirse": {"izq": (150, 120), "der": (150, 120), "cejas": "triste"},
    # Las manos con el objeto adelante (Así Nació, 2026-11-16: "las manos siempre hacen algo con el objeto"): se
    # alternan de a pares (lo agarra, lo abre, lo llena), nunca los brazos abiertos al costado.
    "sostener_a": {"izq": (18, -95), "der": (18, -95)},
    "sostener_b": {"izq": (24, -110), "der": (14, -88)},
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


def _oscurecer(color: str, f: float = 0.78) -> str:
    """El mismo color, más oscuro (el brazo y la pierna de atrás, de perfil)."""
    c = color.lstrip("#")
    if len(c) != 6:
        return color
    return "#" + "".join(f"{int(int(c[i:i + 2], 16) * f):02x}" for i in (0, 2, 4))


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
        if e.perfil:
            cuerpo = self._svg_perfil(e)
            return cuerpo if e.perfil > 0 else g(cuerpo, escala=-1, escala_y=1)
        k = self.alto_cuerpo
        resp = 1 + 0.014 * e.respiracion           # el torso "respira" (alto del torso)
        piso_torso = -150 * k
        tope_torso = piso_torso - 270 * k * resp
        cy_cabeza = tope_torso - self.R_CABEZA + 22
        hombro_y = tope_torso + 38
        return "".join([
            self._piernas(piso_torso, e),
            self._torso_espaldas(piso_torso, tope_torso) if e.espaldas else self._torso(piso_torso, tope_torso),
            self._brazo(-1, hombro_y, *e.brazo_izq),
            self._brazo(1, hombro_y, *e.brazo_der),
            g(self._cabeza(e), 0, cy_cabeza, rot=e.inclinacion),
        ])

    # -- geometría (para el chequeo de composición: brazos que atraviesan caras) --
    def cara(self, e: Estado | None = None) -> tuple[float, float, float]:
        """(x, y, radio) de la cabeza en coordenadas locales (sin sombrero)."""
        k = self.alto_cuerpo
        tope = -150 * k - 270 * k
        return (8.0 * (e.perfil if e else 0), tope - self.R_CABEZA + 22, float(self.R_CABEZA))

    def alto_sombrero(self) -> float:
        return {"galera": 150.0, "gorra": 40.0}.get(self.sombrero, 0.0)

    def brazos(self, e: Estado) -> list[list[tuple[float, float]]]:
        """Las dos poligonales hombro → codo → mano, en coordenadas locales."""
        k = self.alto_cuerpo
        tope = -150 * k - 270 * k
        hy = tope + 38
        if e.perfil:
            return [[(x * e.perfil, y) for x, y in pl] for pl in self._brazos_perfil(e, hy)]
        out = []
        for lado, (hombro, codo) in ((-1, e.brazo_izq), (1, e.brazo_der)):
            x0 = lado * 92
            a1, a2 = math.radians(hombro), math.radians(hombro + codo)
            x1, y1 = x0 + lado * math.sin(a1) * self.LARGO_BRAZO, hy + math.cos(a1) * self.LARGO_BRAZO
            out.append([(x0, hy), (x1, y1), (x1 + lado * math.sin(a2) * self.LARGO_ANTEBRAZO,
                                             y1 + math.cos(a2) * self.LARGO_ANTEBRAZO)])
        return out

    # -- de perfil (mirando a la derecha; a la izquierda se espeja) --
    def _brazos_perfil(self, e: Estado, hy: float) -> list[list[tuple[float, float]]]:
        sw = (34 if e.corre else 26) * e.zancada
        codo = 70 if e.corre else 25
        out = []
        for signo in (-1, 1):            # el de atrás primero
            a1 = math.radians(signo * sw)
            x1, y1 = 4 + math.sin(a1) * self.LARGO_BRAZO, hy + math.cos(a1) * self.LARGO_BRAZO
            a2 = a1 + math.radians(codo)
            out.append([(4, hy), (x1, y1), (x1 + math.sin(a2) * self.LARGO_ANTEBRAZO,
                                            y1 + math.cos(a2) * self.LARGO_ANTEBRAZO)])
        return out

    def _svg_perfil(self, e: Estado) -> str:
        k = self.alto_cuerpo
        resp = 1 + 0.014 * e.respiracion
        piso_torso = -150 * k
        tope = piso_torso - 270 * k * resp
        hy = tope + 38
        R = self.R_CABEZA
        cy = tope - R + 22
        p = []
        # piernas en el plano: una adelante y otra atrás, la de atrás con la rodilla doblada
        largo = (-28) - (piso_torso + 10)
        zan = (40 if e.corre else 28) * e.zancada
        piernas = []
        for signo, oscuro in ((-1, True), (1, False)):
            a = math.radians(signo * zan)
            cad = (0.0, piso_torso + 10)
            rod = (cad[0] + math.sin(a) * largo / 2, cad[1] + math.cos(a) * largo / 2)
            dobla = math.radians(-25 * max(0.0, -signo * e.zancada)) if not e.corre else math.radians(-45 * abs(e.zancada))
            pie = (rod[0] + math.sin(a + dobla) * largo / 2, rod[1] + math.cos(a + dobla) * largo / 2)
            color = "#2b3247" if oscuro else self.pantalon
            piernas.append(linea_gruesa([cad, rod, pie], color, 44)
                           + camino(f"M{n(pie[0] - 26)} {n(pie[1] + 26)} Q{n(pie[0] - 26)} {n(pie[1] - 18)} "
                                    f"{n(pie[0] + 6)} {n(pie[1] - 18)} Q{n(pie[0] + 58)} {n(pie[1] - 14)} "
                                    f"{n(pie[0] + 60)} {n(pie[1] + 26)} Z", "#2a2a33", ancho=P.TRAZO_FINO + 2))
        brazos = self._brazos_perfil(e, hy)
        p.append(piernas[0])
        p.append(linea_gruesa(brazos[0], _oscurecer(self.ropa), self.ANCHO_BRAZO)
                 + circulo(*brazos[0][-1], 22, _oscurecer(self.piel)))
        p.append(piernas[1])
        # torso de costado (más angosto, la panza hacia adelante)
        p.append(camino(f"M-56 {n(piso_torso)} L64 {n(piso_torso)} Q78 {n(tope + 60)} 50 {n(tope + 8)} "
                        f"Q0 {n(tope - 6)} -48 {n(tope + 12)} Q-66 {n(tope + 80)} -56 {n(piso_torso)} Z", self.ropa))
        p.append(linea_gruesa(brazos[1], self.ropa, self.ANCHO_BRAZO) + circulo(*brazos[1][-1], 24, self.piel))
        # cabeza de perfil: oreja atrás, nariz adelante, un ojo
        cab = [circulo(-22, 14, 26, self.piel), circulo(8, 0, R, self.piel)]
        cab.append(self._pelo_perfil())
        if self.cachetes:
            cab.append(f'<ellipse cx="52" cy="38" rx="22" ry="13" fill="{P.ROSA}" opacity="0.45"/>')
        ojo_x = 62
        cierre = max(0.0, min(1.0, e.parpadeo))
        if cierre > 0.85:
            cab.append(camino(f"M{ojo_x - 16} -6 Q{ojo_x} 4 {ojo_x + 16} -6", ancho=P.TRAZO_FINO + 1))
        else:
            ry = 24 * (1 - cierre)
            cab.append(elipse(ojo_x, -8, 16, ry, P.BLANCO, ancho=P.TRAZO_FINO))
            cab.append(circulo(ojo_x + 6, -5, min(10, ry * 0.6), P.CONTORNO, borde=False))
        dy_ceja = {"arriba": -16, "enojo": 2, "triste": -6}.get(e.cejas, 0)
        cab.append(g(f'<path d="M-18 0 L18 0" {trazo(ancho=11)}/>', ojo_x, -52 + dy_ceja,
                     rot={"enojo": 14, "triste": -14}.get(e.cejas, 0)))
        if self.anteojos:
            cab.append(f'<circle cx="{ojo_x}" cy="-8" r="30" fill="none" {trazo(ancho=P.TRAZO_FINO + 1)}/>'
                       f'<path d="M{ojo_x - 30} -10 L-10 -14" {trazo(ancho=P.TRAZO_FINO)}/>')
        cab.append(circulo(R + 6, 22, 22, self.piel))                        # nariz
        if self.bigote:
            cab.append(camino(f"M{R - 30} 44 Q{R} 34 {R + 14} 50 Q{R - 6} 62 {R - 30} 52 Z", self.pelo,
                              ancho=P.TRAZO_FINO))
        ap = max(0.0, min(1.0, e.apertura))
        if e.boca in ("cerrada", "sonrisa") or ap < 0.08:
            cab.append(camino(f"M{R - 50} 62 Q{R - 30} {74 if e.boca == 'sonrisa' else 66} {R - 10} 60"))
        else:
            cab.append(elipse(R - 28, 66, 14, 6 + 14 * ap, "#5a1e2a", ancho=P.TRAZO_FINO))
        cab.append(self._sombrero_perfil())
        p.append(g("".join(cab), 0, cy, rot=e.inclinacion))
        return "".join(p)

    def _pelo_perfil(self) -> str:
        R = self.R_CABEZA
        c = self.pelo
        if self.peinado == "pelado":
            return camino(f"M{-R + 4} -10 Q{-R - 10} 40 {-R + 30} 70 Q{-R + 10} 20 {-R + 30} -20 Z", c)
        if self.peinado == "rulos":
            return "".join(circulo(x, y, 40, c) for x, y in ((-70, -80), (-30, -105), (15, -112), (-95, -30), (-100, 25)))
        largo = 120 if self.peinado == "largo" else 40
        return camino(f"M{R - 10} -60 Q{R - 30} {-R - 20} -10 {-R - 10} Q{-R - 20} {-R + 10} {-R - 6} 10 "
                      f"L{-R + 4} {largo} Q{-R + 40} {largo - 30} -40 0 Q0 -50 {R - 10} -60 Z", c)

    def _sombrero_perfil(self) -> str:
        R = self.R_CABEZA
        c = self.color_sombrero
        if self.sombrero == "gorra":
            return (camino(f"M{-R + 4} -40 Q{-R + 10} {-R - 30} 8 {-R - 30} Q{R - 10} {-R - 30} {R - 4} -40 Z", c)
                    + camino(f"M{R - 20} -44 Q{R + 70} -46 {R + 80} -30 Q{R + 20} -24 {R - 20} -30 Z", c))
        if self.sombrero == "galera":
            return (camino(f"M-72 {-R + 10} L-66 {-R - 120} L82 {-R - 120} L88 {-R + 10} Z", c)
                    + f'<rect x="-70" y="{-R - 20}" width="156" height="24" fill="{P.ROJO}" '
                      f'{trazo(ancho=P.TRAZO_FINO)}/>' + elipse(8, -R + 12, 130, 22, c))
        return ""

    # -- partes --
    def _piernas(self, piso_torso: float, e: Estado | None = None) -> str:
        """Cadera → rodilla → pie. Con la pierna levantada (caminar, correr) el pie sube y la rodilla
        sale hacia afuera; agachado, las dos rodillas se abren. Recta = como antes."""
        p = []
        for s in (-1, 1):
            x = s * 42
            lev = 0.0 if e is None else max(0.0, min(1.0, e.pierna_izq if s < 0 else e.pierna_der))
            ag = 0.0 if e is None else max(0.0, min(1.0, e.agachar))
            cadera = (x, piso_torso + 10)
            pie_y = -28 - 70 * lev
            rodilla = (x + s * (26 * lev + 30 * ag), (cadera[1] + pie_y) / 2 - 6 * lev)
            pie = (x + s * 6 * lev, pie_y)
            p.append(linea_gruesa([cadera, rodilla, pie], self.pantalon, 44))
            dy = pie_y + 28
            # zapato: del talón (adentro) a la punta (afuera)
            p.append(camino(f"M{n(x - s * 30)} {n(dy)} Q{n(x - s * 30)} {n(dy - 46)} {n(x + s * 6)} {n(dy - 46)} "
                            f"Q{n(x + s * 50)} {n(dy - 46)} {n(x + s * 52)} {n(dy)} Z", "#2a2a33",
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
        return camino(d, self.ropa) + cuello + self._detalle_ropa(piso, tope)

    def _torso_espaldas(self, piso: float, tope: float) -> str:
        w_ab, w_ar = 118, 98
        d = (f"M{-w_ab} {n(piso)} L{w_ab} {n(piso)} Q{w_ab + 6} {n(tope + 40)} {w_ar} {n(tope + 10)} "
             f"Q{w_ar - 10} {n(tope)} 0 {n(tope)} Q{-w_ar + 10} {n(tope)} {-w_ar} {n(tope + 10)} "
             f"Q{-w_ab - 6} {n(tope + 40)} {-w_ab} {n(piso)} Z")
        return camino(d, self.ropa) + f'<path d="M0 {n(tope + 20)} L0 {n(piso - 10)}" stroke="{oscurecer(self.ropa, 0.25)}" stroke-width="5" opacity="0.6"/>'

    def _detalle_ropa(self, piso: float, tope: float) -> str:
        """Pliegues, botones, bolsillo y costuras (Santi, 2026-11-15: "más detalle en la ropa")."""
        sombra = oscurecer(self.ropa, 0.28)
        luz = aclarar(self.ropa, 0.45)
        alto = piso - tope
        p = []
        # tapeta con botones por el medio
        p.append(f'<path d="M0 {n(tope + 34)} L0 {n(piso - 6)}" fill="none" stroke="{sombra}" stroke-width="5" '
                 f'stroke-linecap="round"/>')
        for k in range(3):
            y = tope + 70 + k * alto * 0.24
            p.append(f'<circle cx="0" cy="{n(y)}" r="9" fill="{luz}" stroke="{P.CONTORNO}" stroke-width="3.5"/>'
                     f'<circle cx="-2" cy="{n(y - 2)}" r="3" fill="#ffffff" opacity="0.7"/>')
        # bolsillo en el pecho, del lado de la luz
        bx, by = -64, tope + 70
        p.append(f'<path d="M{bx - 24} {n(by)} L{bx + 24} {n(by)} L{bx + 22} {n(by + 38)} Q{bx} {n(by + 46)} '
                 f'{bx - 22} {n(by + 38)} Z" fill="{oscurecer(self.ropa, 0.12)}" {trazo(ancho=3.5)}/>'
                 f'<path d="M{bx - 24} {n(by + 9)} L{bx + 24} {n(by + 9)}" stroke="{P.CONTORNO}" '
                 f'stroke-width="3" opacity="0.6"/>')
        # pliegues: en las axilas y en la cintura (lado de la sombra más marcados)
        for s_, op in ((-1, 0.35), (1, 0.6)):
            p.append(f'<path d="M{s_ * 70} {n(tope + 58)} Q{s_ * 52} {n(tope + 96)} {s_ * 66} {n(tope + 132)}" '
                     f'fill="none" stroke="{sombra}" stroke-width="6" stroke-linecap="round" opacity="{op}"/>')
            p.append(f'<path d="M{s_ * 92} {n(piso - 52)} Q{s_ * 70} {n(piso - 34)} {s_ * 82} {n(piso - 10)}" '
                     f'fill="none" stroke="{sombra}" stroke-width="5" stroke-linecap="round" opacity="{op}"/>')
        # cinturón (costura) abajo
        p.append(f'<path d="M-112 {n(piso - 22)} L112 {n(piso - 22)}" stroke="{sombra}" stroke-width="7" '
                 f'opacity="0.55"/>')
        # brillo en el hombro de la luz
        p.append(f'<path d="M-84 {n(tope + 22)} Q-60 {n(tope + 8)} -30 {n(tope + 10)}" fill="none" '
                 f'stroke="{luz}" stroke-width="8" stroke-linecap="round" opacity="0.8"/>')
        return "".join(p)

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
        if e.espaldas:     # la nuca: orejas, la cabeza y el pelo tapando todo
            pelo = self.pelo if self.peinado != "pelado" else self.piel
            return "".join(circulo(s_ * (R - 4), 12, 26, self.piel) for s_ in (-1, 1)) + circulo(0, 0, R, pelo) \
                + self._sombrero()
        p = []
        if self.peinado == "largo":   # pelo de atrás, debajo de la cara
            p.append(camino(f"M{-R - 14} -10 Q{-R - 24} {R + 70} {-R + 30} {R + 60} L{R - 30} "
                            f"{R + 60} Q{R + 24} {R + 70} {R + 14} -10 Z", self.pelo))
        for s in (-1, 1):             # orejas
            p.append(circulo(s * (R - 4), 12, 26, self.piel))
        p.append(circulo(0, 0, R, self.piel))
        # la nariz: un toque de sombra y brillo (volumen en la cara)
        p.append(f'<path d="M6 16 Q16 30 4 36" fill="none" stroke="{oscurecer(self.piel, 0.3)}" stroke-width="6" '
                 f'stroke-linecap="round"/>')
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

    IRIS = "#6b4a2e"

    def _ojos(self, e: Estado) -> str:
        """Ojos expresivos (2026-11-15): iris de color con pupila y dos brillos; sorprendido = más
        grandes y la pupila chica; enojado = el párpado de arriba cae en diagonal; contento (sonrisa) =
        el párpado de abajo sube (ojos que sonríen); triste = el párpado de arriba cae hacia afuera."""
        p = []
        cierre = max(0.0, min(1.0, e.parpadeo))
        sorpresa = e.cejas == "arriba" and e.boca != "sonrisa"
        for s in (-1, 1):
            cx, cy = s * 42, -8
            if cierre > 0.85:   # cerrado: una rayita curva
                p.append(camino(f"M{cx - 20} {cy} Q{cx} {cy + 10} {cx + 20} {cy}",
                                ancho=P.TRAZO_FINO + 1))
                continue
            rx = 23 if sorpresa else 20
            ry = (31 if sorpresa else 26) * (1 - cierre)
            p.append(elipse(cx, cy, rx, ry, "#fffdf6", ancho=P.TRAZO_FINO))
            pr = min(13 if not sorpresa else 9, ry * 0.62)
            ix, iy = cx + 6 * e.mirada, cy + 3
            p.append(circulo(ix, iy, pr * 1.45, self.IRIS, borde=False))
            p.append(circulo(ix, iy, pr * 0.85, P.CONTORNO, borde=False))
            p.append(circulo(ix + 5, iy - 5, max(2.5, pr * 0.42), "#ffffff", borde=False))
            p.append(circulo(ix - 4, iy + 5, max(1.5, pr * 0.2), "#ffffff", borde=False))
            # párpados (del color de la piel, con su línea): la emoción se lee en los ojos
            if e.cejas == "enojo":
                p.append(f'<path d="M{cx - rx - 4} {cy - ry - 4} L{cx + rx + 4} {cy - ry - 4} '
                         f'L{cx + rx + 4} {n(cy - ry * (0.15 if s < 0 else 0.75))} '
                         f'L{cx - rx - 4} {n(cy - ry * (0.75 if s < 0 else 0.15))} Z" fill="{self.piel}"/>'
                         f'<path d="M{cx - rx - 2} {n(cy - ry * (0.75 if s < 0 else 0.15))} '
                         f'L{cx + rx + 2} {n(cy - ry * (0.15 if s < 0 else 0.75))}" {trazo(ancho=P.TRAZO_FINO)}/>')
            elif e.cejas == "triste":
                afuera, adentro = (cx - s * rx, cx + s * rx)
                p.append(f'<path d="M{afuera - s * 4} {cy - ry - 4} L{adentro + s * 4} {cy - ry - 4} '
                         f'L{adentro + s * 4} {n(cy - ry * 0.7)} L{afuera - s * 4} {n(cy - ry * 0.05)} Z" fill="{self.piel}"/>'
                         f'<path d="M{afuera} {n(cy - ry * 0.05)} L{adentro} {n(cy - ry * 0.7)}" {trazo(ancho=P.TRAZO_FINO)}/>')
            if e.boca == "sonrisa" and e.cejas != "enojo":
                p.append(f'<path d="M{cx - rx - 4} {cy + ry + 4} L{cx + rx + 4} {cy + ry + 4} '
                         f'L{cx + rx + 4} {n(cy + ry * 0.3)} Q{cx} {n(cy - ry * 0.05)} {cx - rx - 4} {n(cy + ry * 0.3)} Z" '
                         f'fill="{self.piel}"/><path d="M{cx - rx} {n(cy + ry * 0.32)} Q{cx} {n(cy - ry * 0.02)} '
                         f'{cx + rx} {n(cy + ry * 0.32)}" fill="none" {trazo(ancho=P.TRAZO_FINO - 1)}/>')
        return "".join(p)

    def _cejas(self, tipo: str) -> str:
        """Cejas con forma (gruesas en el medio, finas en las puntas) y más movimiento."""
        # rotación positiva = horaria (y hacia abajo): en el ojo derecho baja la punta de afuera
        dy, rot = {"normal": (0, 0), "arriba": (-22, 0), "enojo": (6, -18),
                   "triste": (-8, 18)}.get(tipo, (0, 0))
        ceja = (f'<path d="M-24 3 Q0 -13 24 3 Q0 -3 -24 3 Z" fill="{self.pelo}" '
                f'stroke="{P.CONTORNO}" stroke-width="5" stroke-linejoin="round"/>')
        return "".join(g(g(ceja, escala=1, escala_y=1) if s > 0 else g(ceja, escala=-1, escala_y=1),
                         s * 42, -50 + dy, rot=s * rot) for s in (-1, 1))

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
        lengua = dientes = ""
        if ry > 16:
            lengua = elipse(0, cy + ry * 0.5, rx * 0.55, ry * 0.35, "#ff7a8a", borde=False)
        if ry > 12 and rx > 22:   # la fila de dientes de arriba
            dientes = (f'<path d="M{n(-rx * 0.62)} {n(cy - ry * 0.72)} Q0 {n(cy - ry * 1.02)} {n(rx * 0.62)} '
                       f'{n(cy - ry * 0.72)} L{n(rx * 0.55)} {n(cy - ry * 0.45)} Q0 {n(cy - ry * 0.62)} '
                       f'{n(-rx * 0.55)} {n(cy - ry * 0.45)} Z" fill="#ffffff"/>')
        return interior + lengua + dientes

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
    # Canal de marcas (2026-11-14): un nene, una mamá y la MASCOTA del canal, el locutor que aparece
    # al costado cuando la escena se congela (gorra amarilla, anteojos y saco naranja: siempre igual).
    "nene": Personaje("nene", piel=P.PIEL[1], pelo=P.PELO[1], peinado="corto", ropa=P.VERDE,
                      pantalon="#3a5a8c", alto_cuerpo=0.75),
    "mama": Personaje("mama", piel=P.PIEL[0], pelo=P.PELO[2], peinado="largo", ropa=P.AZUL,
                      pantalon="#4b3b6e", alto_cuerpo=0.95),
    "locutor": Personaje("locutor", piel=P.PIEL[1], pelo=P.PELO[0], peinado="jopo", sombrero="gorra",
                         color_sombrero=P.AMARILLO, ropa=P.NARANJA, pantalon="#2b2b33",
                         anteojos=True),
}


def personaje(nombre: str, **cambios) -> Personaje:
    """Del elenco, con cambios paramétricos: `personaje('pibe', ropa='#00aa88')`. Un nombre que no
    está en el elenco arranca del narrador."""
    base = ELENCO.get(nombre, ELENCO["narrador"])
    return replace(base, **cambios) if cambios else base
