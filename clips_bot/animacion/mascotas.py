"""Las 4 opciones de mascota/locutor del canal "Así Nació" (Santi, 2026-11-14: "bien diferentes entre
sí, con personalidad, que encajen con el humor y que se reconozcan en chiquito"). Mismo estilo que la
animación (paleta.py: contorno grueso violeta oscuro, colores planos). Cuando Santi elija una, esa es
la del locutor de los videos, la foto de perfil y el banner.

Cada mascota es una función `svg(pose)` que devuelve un grupo con el origen en el piso, al medio de
los pies, de ~1000 px de alto; `cara()` es solo la cabeza centrada en (0, 0), para el avatar.
Poses: "saluda" (un brazo arriba) o "senala" (señala hacia la derecha)."""

from __future__ import annotations

from . import paleta as P
from .svg import camino, circulo, elipse, g, linea_gruesa, n, rect, trazo

FINO = P.TRAZO_FINO


def _ojo(cx: float, cy: float, r: float = 20, guino: bool = False, mira: float = 0.3) -> str:
    if guino:
        return camino(f"M{n(cx - r)} {n(cy + 2)} Q{n(cx)} {n(cy - r * 0.7)} {n(cx + r)} {n(cy + 2)}",
                      ancho=FINO + 3)
    return (elipse(cx, cy, r, r * 1.25, P.BLANCO, ancho=FINO)
            + circulo(cx + r * 0.35 * mira, cy + 3, r * 0.55, P.CONTORNO, borde=False)
            + circulo(cx + r * 0.35 * mira + r * 0.2, cy - r * 0.15, r * 0.2, P.BLANCO, borde=False))


def _brazo(x0: float, y0: float, puntos: list[tuple[float, float]], color: str, mano: str,
           ancho: float = 34) -> str:
    pts = [(x0, y0)] + puntos
    x, y = pts[-1]
    return linea_gruesa(pts, color, ancho) + circulo(x, y, 26, mano)


def _pose_brazos(pose: str, hx: float, hy: float, color: str, mano: str) -> str:
    """Brazos para un torso con hombros en (±hx, hy). saluda: el derecho arriba; senala: el derecho
    estirado hacia la derecha y un poco arriba (para señalar el nombre del canal)."""
    izq = _brazo(-hx, hy, [(-hx - 60, hy + 110), (-hx - 30, hy + 220)], color, mano)
    if pose == "senala":
        der = _brazo(hx, hy, [(hx + 120, hy - 40), (hx + 240, hy - 90)], color, mano)
        # el dedo índice
        der += camino(f"M{n(hx + 252)} {n(hy - 104)} L{n(hx + 300)} {n(hy - 128)}", ancho=26) + \
            camino(f"M{n(hx + 252)} {n(hy - 104)} L{n(hx + 300)} {n(hy - 128)}", ancho=12, color=mano)
    else:
        der = _brazo(hx, hy, [(hx + 90, hy - 90), (hx + 120, hy - 210)], color, mano)
    return izq + der


def _piernas(sep: float, alto: float, color: str, zapato: str = "#2a2a33") -> str:
    p = []
    for s in (-1, 1):
        x = s * sep
        p.append(linea_gruesa([(x, -alto), (x, -30)], color, 46))
        p.append(camino(f"M{n(x - s * 30)} 0 Q{n(x - s * 30)} -48 {n(x + s * 8)} -48 "
                        f"Q{n(x + s * 56)} -48 {n(x + s * 58)} 0 Z", zapato, ancho=FINO + 2))
    return "".join(p)


# ---- A: Don Benito, vendedor de antes --------------------------------------------------------

def benito_cara(guino: bool = False) -> str:
    R = 150
    piel = P.PIEL[0]
    p = [circulo(-R + 4, 16, 30, piel), circulo(R - 4, 16, 30, piel), circulo(0, 0, R, piel)]
    for s in (-1, 1):   # cachetes
        p.append(f'<ellipse cx="{s * 92}" cy="48" rx="30" ry="18" fill="{P.ROSA}" opacity="0.55"/>')
    p.append(_ojo(-50, -14, 22, mira=0.2))
    p.append(_ojo(50, -14, 22, guino=guino, mira=0.2))
    for s in (-1, 1):   # cejas gruesas
        p.append(g(f'<path d="M-26 0 Q0 -14 26 0" fill="none" {trazo(ancho=14)}/>', s * 50, -60))
    p.append(elipse(0, 30, 24, 20, "#f0a585", ancho=FINO))     # nariz
    # el bigote de manubrio: lo que lo hace reconocible en chiquito
    p.append(camino("M0 52 Q-40 34 -86 50 Q-130 66 -128 30 Q-150 66 -108 84 Q-60 98 0 70 "
                    "Q60 98 108 84 Q150 66 128 30 Q130 66 86 50 Q40 34 0 52 Z", "#3b2a20", ancho=FINO + 1))
    p.append(camino("M-34 96 Q0 122 34 96", ancho=FINO + 2))  # sonrisa debajo del bigote
    # canotier de paja con cinta roja
    p.append(elipse(0, -R + 26, 190, 30, "#e8c46a"))
    p.append(camino(f"M-112 {-R + 26} L-104 {-R - 66} Q0 {-R - 82} 104 {-R - 66} L112 {-R + 26} Z",
                    "#e8c46a"))
    p.append(rect(-110, -R - 14, 220, 34, P.ROJO, ancho=FINO))
    p.append(f'<path d="M-90 {-R - 50} L90 {-R - 50}" stroke="#c9a24a" stroke-width="6"/>')
    return "".join(p)


def benito(pose: str = "saluda") -> str:
    p = [_piernas(46, 170, "#3b3550")]
    # torso redondo: camisa blanca, chaleco a rayas, moñito
    torso = camino("M-140 -150 Q-160 -340 -100 -430 L100 -430 Q160 -340 140 -150 Z", BLANCO_CAMISA)
    rayas = "".join(f'<path d="M{x} -425 L{x} -155" stroke="{P.ROJO}" stroke-width="16"/>'
                    for x in range(-120, 130, 40))
    chaleco = (f'<clipPath id="cb"><path d="M-140 -150 Q-160 -340 -100 -430 L-30 -430 L0 -330 L30 -430 '
               f'L100 -430 Q160 -340 140 -150 Z"/></clipPath><g clip-path="url(#cb)">'
               f'<rect x="-170" y="-440" width="340" height="300" fill="{P.BLANCO}"/>{rayas}</g>')
    p += [torso, chaleco,
          camino("M-140 -150 Q-160 -340 -100 -430 L-30 -430 L0 -330 L30 -430 L100 -430 Q160 -340 140 -150 Z"),
          camino("M-36 -420 L0 -400 L-36 -380 Z M36 -420 L0 -400 L36 -380 Z", P.ROJO, ancho=FINO),
          circulo(0, -400, 10, P.ROJO, ancho=FINO),
          "".join(circulo(0, y, 7, P.AMARILLO, ancho=4) for y in (-300, -250, -200))]
    p.append(_pose_brazos(pose, 118, -400, BLANCO_CAMISA, P.PIEL[0]))
    p.append(g(benito_cara(guino=pose == "senala"), 0, -580))
    return "".join(p)


BLANCO_CAMISA = "#fbf6ec"


# ---- B: Lu, la investigadora --------------------------------------------------------------------

def lu_cara(guino: bool = False) -> str:
    R = 145
    piel = P.PIEL[1]
    pelo = "#2b1d2e"
    p = [circulo(0, -R - 20, 58, pelo),                          # rodete
         camino(f"M{-R - 10} 0 Q{-R - 20} {R + 30} {-R + 40} {R + 24} L{R - 40} {R + 24} "
                f"Q{R + 20} {R + 30} {R + 10} 0 Z", pelo),        # pelo de atrás (carré)
         circulo(-R + 4, 14, 26, piel), circulo(R - 4, 14, 26, piel), circulo(0, 0, R, piel)]
    for s in (-1, 1):
        p.append(f'<ellipse cx="{s * 84}" cy="52" rx="24" ry="14" fill="{P.ROSA}" opacity="0.5"/>')
    for x, y in ((-70, 46), (-56, 58), (-84, 60), (70, 46), (56, 58), (84, 60)):   # pecas
        p.append(circulo(x, y, 4, "#b8734a", borde=False))
    # flequillo recto
    p.append(camino(f"M{-R + 2} -6 Q{-R + 6} {-R - 20} 0 {-R - 16} Q{R - 6} {-R - 20} {R - 2} -6 "
                    f"L{R - 20} -40 L-{R - 20} -40 Z", pelo))
    p.append(_ojo(-48, 4, 20, mira=0.6))
    p.append(_ojo(48, 4, 20, guino=guino, mira=0.6))
    # anteojos grandes, rojos: la marca de ella en chiquito
    p.append(f'<g fill="none" {trazo(P.ROJO, 13)}><circle cx="-50" cy="4" r="44"/>'
             f'<circle cx="50" cy="4" r="44"/><path d="M-8 0 Q0 -10 8 0"/></g>')
    p.append(f'<g fill="none" {trazo(ancho=4)}><circle cx="-50" cy="4" r="51"/>'
             f'<circle cx="50" cy="4" r="51"/></g>')
    p.append(camino("M-40 82 Q0 112 40 82 Q0 98 -40 82 Z", "#5a1e2a", ancho=FINO))   # sonrisa abierta
    # lápiz detrás de la oreja
    p.append(g(rect(-12, -70, 24, 140, P.AMARILLO, ancho=FINO) +
               camino("M-12 70 L0 100 L12 70 Z", "#f6c9a0", ancho=FINO), R - 4, -40, rot=30))
    return "".join(p)


def lu(pose: str = "saluda") -> str:
    p = [_piernas(40, 160, "#34405e", zapato=P.BLANCO)]
    p.append(camino("M-120 -150 Q-128 -340 -96 -410 Q0 -440 96 -410 Q128 -340 120 -150 Z", P.VIOLETA))
    p.append(camino("M-60 -410 Q0 -360 60 -410", ancho=FINO + 2))                       # capucha
    p.append(rect(-60, -260, 120, 60, "#7444d8", r=20, ancho=FINO))                      # bolsillo
    # la libreta en la mano izquierda
    p.append(_pose_brazos(pose, 100, -390, P.VIOLETA, P.PIEL[1]))
    p.append(g(rect(-56, -74, 112, 148, P.TURQUESA, r=8) +
               "".join(f'<path d="M-36 {y} L36 {y}" stroke="{P.BLANCO}" stroke-width="7"/>'
                       for y in (-34, -6, 22)) +
               "".join(circulo(-56, y, 8, P.GRIS, ancho=4) for y in (-50, -10, 30)),
               -190, -170, rot=-12))
    p.append(g(lu_cara(guino=pose == "senala"), 0, -560))
    return "".join(p)


# ---- C: Lampi, la lamparita ---------------------------------------------------------------------

def lampi_cara(guino: bool = False, halo: bool = True) -> str:
    p = []
    if halo:
        p.append(f'<circle cx="0" cy="-20" r="230" fill="{P.AMARILLO}" opacity="0.25"/>')
        for k in range(12):
            p.append(g(f'<path d="M0 -255 L0 -300" {trazo(P.AMARILLO, 16)}/>', 0, -20, rot=k * 30))
    # el vidrio (la cara) y la rosca
    p.append(camino("M-170 -40 Q-170 -230 0 -230 Q170 -230 170 -40 Q170 60 90 120 L90 170 "
                    "L-90 170 L-90 120 Q-170 60 -170 -40 Z", "#fff3a6"))
    p.append(f'<path d="M-110 -150 Q-130 -90 -118 -40" fill="none" stroke="{P.BLANCO}" '
             f'stroke-width="18" stroke-linecap="round"/>')                                # brillo
    p.append(rect(-92, 166, 184, 36, P.GRIS, r=10, ancho=FINO))
    p.append(rect(-84, 200, 168, 34, "#c7ccd6", r=10, ancho=FINO))
    p.append(rect(-76, 232, 152, 32, P.GRIS, r=10, ancho=FINO))
    p.append(camino("M-30 264 Q0 300 30 264 Z", P.GRIS_OSCURO, ancho=FINO))
    # el filamento como un rulito arriba (su "pelo")
    p.append(camino("M-40 -120 Q-40 -190 0 -190 Q40 -190 30 -150 Q20 -120 0 -140 Q-14 -160 10 -170",
                    ancho=10, color=P.NARANJA))
    for s in (-1, 1):
        p.append(f'<ellipse cx="{s * 92}" cy="40" rx="26" ry="15" fill="{P.NARANJA}" opacity="0.45"/>')
    p.append(_ojo(-56, -10, 26, mira=-0.2))
    p.append(_ojo(56, -10, 26, guino=guino, mira=-0.2))
    for s in (-1, 1):
        p.append(g(f'<path d="M-24 6 Q0 -10 24 0" fill="none" {trazo(ancho=12)}/>', s * 56, -66,
                   rot=s * 8))
    p.append(camino("M-56 46 Q0 110 56 46 Q0 70 -56 46 Z", "#5a1e2a", ancho=FINO + 1))
    p.append(elipse(0, 70, 22, 10, "#ff7a8a", borde=False))
    return "".join(p)


def lampi(pose: str = "saluda") -> str:
    p = []
    for s in (-1, 1):   # piernitas finas con zapatillas
        x = s * 50
        p.append(linea_gruesa([(x, -200), (x, -36)], P.GRIS_OSCURO, 18))
        p.append(camino(f"M{n(x - s * 34)} 0 Q{n(x - s * 34)} -50 {n(x + s * 6)} -50 Q{n(x + s * 60)} -50 "
                        f"{n(x + s * 62)} 0 Z", P.ROJO, ancho=FINO + 2))
        p.append(f'<path d="M{n(x - s * 20)} -8 L{n(x + s * 50)} -8" stroke="{P.BLANCO}" stroke-width="8"/>')
    cuerpo = g(lampi_cara(guino=pose == "senala"), 0, -480)
    if pose == "senala":
        brazos = (_brazo(-150, -470, [(-230, -400), (-250, -320)], P.GRIS_OSCURO, P.BLANCO, 18)
                  + _brazo(150, -470, [(260, -520), (360, -580)], P.GRIS_OSCURO, P.BLANCO, 18))
    else:
        brazos = (_brazo(-150, -470, [(-230, -400), (-250, -320)], P.GRIS_OSCURO, P.BLANCO, 18)
                  + _brazo(150, -470, [(240, -560), (260, -680)], P.GRIS_OSCURO, P.BLANCO, 18))
    return "".join(p) + brazos + cuerpo


# ---- D: el abuelo Tito, inventor ----------------------------------------------------------------

def tito_cara(guino: bool = False) -> str:
    R = 148
    piel = P.PIEL[0]
    canas = "#e9ecf2"
    p = []
    # pelos locos a los costados (lo pelado arriba)
    for s in (-1, 1):
        p.append(camino(f"M{s * 110} -60 Q{s * 210} -120 {s * 190} -20 Q{s * 250} 0 {s * 180} 50 "
                        f"Q{s * 230} 100 {s * 140} 90 Z", canas))
    p += [circulo(-R + 4, 16, 28, piel), circulo(R - 4, 16, 28, piel), circulo(0, 0, R, piel)]
    for s in (-1, 1):
        p.append(f'<ellipse cx="{s * 86}" cy="50" rx="26" ry="15" fill="{P.ROSA}" opacity="0.5"/>')
    # anteojos de soldador en la frente (bronce, vidrios verdes): su marca
    p.append(rect(-R + 8, -96, 2 * R - 16, 26, "#6b4a2e", r=12, ancho=FINO))
    for s in (-1, 1):
        p.append(circulo(s * 48, -104, 40, "#c98a3a", ancho=FINO + 1))
        p.append(circulo(s * 48, -104, 26, "#5fd1a8", ancho=FINO))
        p.append(circulo(s * 48 - 8, -112, 7, P.BLANCO, borde=False))
    p.append(_ojo(-50, -4, 18, mira=0.4))
    p.append(_ojo(50, -4, 18, guino=guino, mira=0.4))
    for s in (-1, 1):   # cejas blancas peludas
        p.append(g(camino("M-30 6 Q-10 -18 30 -4 Q10 -2 -30 6 Z", canas, ancho=FINO), s * 50, -38))
    p.append(elipse(0, 30, 28, 22, "#f0a585", ancho=FINO))
    p.append(camino("M0 50 Q-50 40 -84 74 Q-40 96 0 70 Q40 96 84 74 Q50 40 0 50 Z", canas, ancho=FINO + 1))
    p.append(camino("M-26 104 Q0 120 26 104", ancho=FINO + 2))
    return "".join(p)


def tito(pose: str = "saluda") -> str:
    p = [_piernas(42, 150, "#4a4a58")]
    # guardapolvo blanco largo, abierto, con lapiceras en el bolsillo
    p.append(camino("M-136 -110 Q-150 -330 -100 -420 Q0 -440 100 -420 Q150 -330 136 -110 Z", P.BLANCO))
    p.append(camino("M-40 -420 L0 -300 L40 -420 Z", P.AZUL, ancho=FINO))   # camisa
    p.append('<path d="M0 -300 L0 -110" stroke="%s" stroke-width="5"/>' % P.CONTORNO)
    p.append(rect(40, -300, 64, 60, P.BLANCO, r=6, ancho=FINO))
    for k, c in enumerate((P.ROJO, P.AZUL, P.VERDE)):
        p.append(rect(48 + k * 18, -326, 10, 40, c, r=4, ancho=3))
    p.append(_pose_brazos(pose, 112, -400, P.BLANCO, P.PIEL[0]))
    # llave inglesa en la mano izquierda
    p.append(g(rect(-12, -80, 24, 150, P.GRIS, r=10, ancho=FINO) +
               camino("M-34 -80 Q-40 -130 0 -136 Q40 -130 34 -80 L14 -96 L14 -120 L-14 -120 L-14 -96 Z",
                      P.GRIS, ancho=FINO), -142, -150, rot=-20))
    p.append(g(tito_cara(guino=pose == "senala"), 0, -560))
    return "".join(p)


# Santi eligió a Tito (2026-11-14): la versión pulida (reloj de bolsillo en vez de la llave inglesa)
# está en tito.py; acá queda la primera solo como referencia de las 4 opciones.
def tito_pulido(pose: str = "saluda") -> str:
    from .tito import tito_svg

    return tito_svg(pose)


def tito_cara_pulida(guino: bool = False) -> str:
    from .tito import tito_cara_svg

    return tito_cara_svg(guino)


MASCOTAS = {
    "benito": {"nombre": "Don Benito", "cuerpo": benito, "cara": benito_cara, "fondo": P.ROJO,
               "quien": "vendedor de los de antes: bigote de manubrio, canotier y chaleco a rayas. "
                        "Exagerado, cancherito, vende cualquier cosa (hasta la historia)."},
    "lu": {"nombre": "Lu", "cuerpo": lu, "cara": lu_cara, "fondo": P.TURQUESA,
           "quien": "investigadora joven: anteojos rojos gigantes, libreta y lápiz en la oreja. "
                    "Sabelotodo con ironía: 'en realidad…'"},
    "lampi": {"nombre": "Lampi", "cuerpo": lampi, "cara": lampi_cara, "fondo": P.VIOLETA,
              "quien": "una lamparita con cara (la idea hecha personaje): se prende cuando llega la "
                       "idea genial y se apaga cuando algo sale mal."},
    "tito": {"nombre": "Abuelo Tito", "cuerpo": tito_pulido, "cara": tito_cara_pulida, "fondo": P.NARANJA,
             "quien": "inventor jubilado: pelado con pelos locos, antiparras de soldador en la frente "
                      "y guardapolvo. Vio todo, inventó todo… según él."},
}
