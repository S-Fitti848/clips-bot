"""El Abuelo Tito, la mascota y locutor fijo de "Así Nació" (elegido por Santi el 2026-11-14).

Inventor jubilado: pelado con pelos locos blancos a los costados, antiparras de soldador en la frente,
bigote blanco de manubrio, guardapolvo blanco con chaleco y moño, y un RELOJ DE BOLSILLO antiguo,
grande y dorado, con cadena: con él viaja en el tiempo (gira la perilla y la historia se va al pasado).

Uso:
    tito_svg(pose="saluda")          # cuerpo entero, origen en el piso entre los pies, ~1000 px de alto
    tito_svg("senala", apertura=0.6) # con la boca abierta (la línea de tiempo la mueve con la voz)
    tito_svg("reloj", aguja=120)     # levantando el reloj; `aguja` gira las agujas (grados)
    tito_cara_svg()                  # solo la cabeza, centrada en (0, 0), para la foto de perfil
    documento_png(...)               # (en render.py: rasterizar) para el avatar y el banner

Poses: "saluda" (mano arriba), "senala" (señala a la derecha de la pantalla), "reloj" (levanta el
reloj al lado de la cabeza). Mismo estilo que la animación (paleta.py: contorno grueso, colores planos).
"""
from __future__ import annotations

import math

from . import paleta as P
from .svg import camino, circulo, elipse, g, linea_gruesa, n, rect, trazo

POSES = ("saluda", "senala", "reloj")
FINO = P.TRAZO_FINO
PIEL = P.PIEL[0]
CANAS = "#eef1f6"
GUARDAPOLVO = "#fbfbf6"
CHALECO = "#7a4b2a"
PANTALON = "#4a4a58"
ORO = "#e8b53a"
ORO_OSCURO = "#b07d1c"
R_CABEZA = 122
CABEZA_Y = -705          # centro de la cabeza respecto del piso
HOMBRO_Y = -548


# ---- piezas ------------------------------------------------------------------------------------

def reloj(aguja: float = 0.0, r: float = 58) -> str:
    """El reloj de bolsillo, centrado en (0, 0): caja dorada, tapa abierta atrás, esfera crema con
    12 marcas, dos agujas (giran con `aguja`) y la corona arriba."""
    marcas = "".join(
        f'<path d="M{n(math.sin(math.radians(a)) * r * 0.62)} {n(-math.cos(math.radians(a)) * r * 0.62)} '
        f'L{n(math.sin(math.radians(a)) * r * 0.74)} {n(-math.cos(math.radians(a)) * r * 0.74)}" '
        f'{trazo(ancho=4 if a % 90 else 7)}/>' for a in range(0, 360, 30))

    def manecilla(ang: float, largo: float, ancho: float) -> str:
        x, y = math.sin(math.radians(ang)) * largo, -math.cos(math.radians(ang)) * largo
        return f'<path d="M0 0 L{n(x)} {n(y)}" {trazo(ancho=ancho)}/>'

    return (rect(-12, -r - 30, 24, 22, ORO_OSCURO, r=6, ancho=FINO)        # corona
            + circulo(0, -r - 36, 12, ORO, ancho=FINO)                    # aro
            + circulo(0, 0, r, ORO)
            + circulo(0, 0, r * 0.8, "#fff6dc", ancho=FINO)
            + marcas
            + manecilla(aguja * 12, r * 0.45, 8) + manecilla(aguja, r * 0.62, 5)
            + circulo(0, 0, 7, P.CONTORNO, borde=False)
            + camino(f"M{n(-r * 0.55)} {n(-r * 0.45)} Q{n(-r * 0.62)} {n(-r * 0.05)} {n(-r * 0.5)} {n(r * 0.2)}",
                     ancho=6, color="#ffffff"))


def _cadena(x0: float, y0: float, x1: float, y1: float, caida: float = 70) -> str:
    """La cadena dorada del reloj: una curva colgando entre dos puntos, punteada."""
    mx, my = (x0 + x1) / 2, max(y0, y1) + caida
    d = f"M{n(x0)} {n(y0)} Q{n(mx)} {n(my)} {n(x1)} {n(y1)}"
    return (f'<path d="{d}" fill="none" stroke="{P.CONTORNO}" stroke-width="13" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="{ORO}" stroke-width="7" stroke-dasharray="9 5" '
            f'stroke-linecap="round"/>')


def _nube(circulos: list[tuple[float, float, float]], color: str) -> str:
    """Un mechón de pelo prolijo: varios círculos con UN solo contorno (primero los bordes, después
    los rellenos encima, así no se ven las líneas de adentro)."""
    bordes = "".join(circulo(x, y, r + P.TRAZO / 2, P.CONTORNO, borde=False) for x, y, r in circulos)
    rellenos = "".join(circulo(x, y, r - P.TRAZO / 2, color, borde=False) for x, y, r in circulos)
    return bordes + rellenos


def _ojo(cx: float, cy: float, parpadeo: float, mira: float, guino: bool) -> str:
    if guino or parpadeo > 0.85:
        return camino(f"M{n(cx - 20)} {n(cy + 4)} Q{n(cx)} {n(cy - 12)} {n(cx + 20)} {n(cy + 4)}", ancho=FINO + 3)
    ry = 27 * (1 - max(0.0, parpadeo))
    return (elipse(cx, cy, 22, ry, P.BLANCO, ancho=FINO)
            + circulo(cx + 7 * mira, cy + 4, min(12, ry * 0.5), P.CONTORNO, borde=False)
            + circulo(cx + 7 * mira + 4, cy - 1, min(4.5, ry * 0.2), P.BLANCO, borde=False))


def cabeza(apertura: float = 0.0, parpadeo: float = 0.0, mira: float = 0.25, guino: bool = False,
           sonrisa: bool = True) -> str:
    """La cabeza centrada en (0, 0)."""
    R = R_CABEZA
    p = []
    # pelos locos: dos nubes prolijas a los costados y tres mechones parados arriba
    for s in (-1, 1):
        p.append(_nube([(s * 118, -30, 46), (s * 150, 12, 44), (s * 128, 54, 38), (s * 96, -64, 30)], CANAS))
    for x, ang in ((-34, -24), (4, 6), (40, 30)):
        p.append(g(camino("M-9 0 Q-22 -46 0 -78 Q4 -40 12 0 Z", CANAS, ancho=FINO), x, -R + 12, rot=ang))
    p += [circulo(-R + 6, 14, 26, PIEL), circulo(R - 6, 14, 26, PIEL), circulo(0, 0, R, PIEL)]
    for s in (-1, 1):
        p.append(f'<ellipse cx="{s * 74}" cy="34" rx="24" ry="14" fill="{P.ROSA}" opacity="0.5"/>')
    # antiparras de soldador en la frente: correa de cuero + dos lentes de bronce con vidrio verde
    p.append(camino(f"M{-R + 4} -66 Q0 -92 {R - 4} -66 L{R - 2} -44 Q0 -70 {-R + 2} -44 Z", "#6b4a2e", ancho=FINO))
    for s in (-1, 1):
        p.append(circulo(s * 44, -64, 33, "#c98a3a", ancho=FINO + 1))
        p.append(circulo(s * 44, -64, 22, "#5fd1a8", ancho=FINO))
        p.append(circulo(s * 44 - 7, -71, 6, P.BLANCO, borde=False))
    p.append(rect(-12, -70, 24, 12, "#6b4a2e", r=4, ancho=4))
    # cejas blancas peludas
    for s in (-1, 1):
        p.append(g(camino("M-26 6 Q0 -16 26 6 Q0 -2 -26 6 Z", CANAS, ancho=FINO), s * 44, -28))
    p.append(_ojo(-44, 4, parpadeo, mira, False))
    p.append(_ojo(44, 4, parpadeo, mira, guino))
    # boca (abajo del bigote): cerrada sonriendo, o abierta según la voz
    ap = max(0.0, min(1.0, apertura))
    if ap < 0.08:
        p.append(camino("M-26 74 Q0 94 26 74" if sonrisa else "M-22 80 Q0 86 22 80", ancho=FINO + 2))
    else:
        p.append(elipse(0, 78 + 8 * ap, 26, 6 + 20 * ap, "#5a1e2a", ancho=FINO + 1))
        if ap > 0.4:
            p.append(elipse(0, 86 + 12 * ap, 14, 6 * ap, "#ff7a8a", borde=False))
    # nariz y bigote de manubrio
    p.append(elipse(0, 30, 23, 19, "#f0a585", ancho=FINO))
    p.append(camino("M0 48 Q-26 38 -58 50 Q-86 58 -96 40 Q-100 70 -66 76 Q-30 80 0 62 "
                    "Q30 80 66 76 Q100 70 96 40 Q86 58 58 50 Q26 38 0 48 Z", CANAS, ancho=FINO + 1))
    return "".join(p)


def _brazo(x0: float, y0: float, puntos: list[tuple[float, float]]) -> str:
    pts = [(x0, y0)] + puntos
    x, y = pts[-1]
    return linea_gruesa(pts, GUARDAPOLVO, 40) + circulo(x, y, 25, PIEL)


def cuerpo(pose: str, aguja: float = 0.0, respiracion: float = 0.0) -> tuple[str, str]:
    """(lo de atrás de la cabeza, lo de adelante): piernas, guardapolvo, brazos y el reloj."""
    resp = 1 + 0.012 * respiracion
    p = []
    for s in (-1, 1):   # piernas y zapatos marrones
        x = s * 40
        p.append(linea_gruesa([(x, -200), (x, -30)], PANTALON, 44))
        p.append(camino(f"M{n(x - s * 30)} 0 Q{n(x - s * 30)} -46 {n(x + s * 8)} -46 "
                        f"Q{n(x + s * 58)} -46 {n(x + s * 60)} 0 Z", "#5b3a22", ancho=FINO + 2))
    top = HOMBRO_Y * resp
    # guardapolvo largo (corte A), abierto adelante
    p.append(camino(f"M-112 {n(top)} Q-150 -380 -168 -176 Q-84 -160 0 -170 Q84 -160 168 -176 "
                    f"Q150 -380 112 {n(top)} Q0 {n(top - 26)} -112 {n(top)} Z", GUARDAPOLVO))
    # chaleco marrón y camisa entre las solapas
    p.append(camino(f"M-56 {n(top - 6)} L-46 -300 L0 -270 L46 -300 L56 {n(top - 6)} Z", CHALECO, ancho=FINO))
    p.append(camino(f"M-30 {n(top - 10)} L0 -470 L30 {n(top - 10)} Z", "#bfe3ff", ancho=FINO))
    for y in (-420, -370, -320):
        p.append(circulo(0, y, 6, ORO_OSCURO, ancho=3))
    # solapas
    for s in (-1, 1):
        p.append(camino(f"M{s * 58} {n(top - 4)} L{s * 30} -430 L{s * 70} -460 L{s * 96} {n(top + 6)} Z",
                        GUARDAPOLVO, ancho=FINO))
    p.append(f'<path d="M-50 -296 L-56 -176 M50 -296 L56 -176" {trazo(ancho=FINO)}/>')
    # bolsillo con lapiceras (a la derecha de la pantalla)
    p.append(rect(74, -330, 60, 56, GUARDAPOLVO, r=6, ancho=FINO))
    for k, c in enumerate((P.ROJO, P.AZUL)):
        p.append(rect(84 + k * 22, -356, 12, 40, c, r=4, ancho=3))
    # moño rojo
    p.append(camino(f"M0 {n(top - 4)} L-34 {n(top - 22)} L-34 {n(top + 18)} Z", P.ROJO, ancho=FINO))
    p.append(camino(f"M0 {n(top - 4)} L34 {n(top - 22)} L34 {n(top + 18)} Z", P.ROJO, ancho=FINO))
    p.append(circulo(0, top - 4, 10, P.ROJO, ancho=FINO))
    bolsillo_reloj = (-36, -330)     # de donde sale la cadena (bolsillo del chaleco)
    adelante = []
    hx, hy = 108, top + 14
    if pose == "reloj":
        # brazo derecho (de la pantalla) arriba con el reloj al lado de la cabeza; el otro en la cintura
        adelante.append(_brazo(-hx, hy, [(-190, -430), (-128, -350)]))
        adelante.append(_brazo(hx, hy, [(205, -620), (238, -760)]))
        rx, ry = 248, -842
        adelante.append(_cadena(bolsillo_reloj[0], bolsillo_reloj[1], rx - 10, ry + 50, caida=160))
        adelante.append(g(reloj(aguja, 70), rx, ry, rot=8))
        adelante.append(circulo(238, -760, 25, PIEL))      # la mano por delante de la cadena
    else:
        # el reloj colgando de la mano izquierda (de la pantalla), con la cadena al chaleco
        adelante.append(_brazo(-hx, hy, [(-176, -420), (-168, -300)]))
        adelante.append(_cadena(bolsillo_reloj[0], bolsillo_reloj[1], -168, -300, caida=40))
        adelante.append(_cadena(-168, -300, -168, -206, caida=0))
        adelante.append(g(reloj(aguja, 52), -168, -150, rot=-6))
        if pose == "senala":
            adelante.append(_brazo(hx, hy, [(220, -560), (330, -606)]))
            adelante.append(camino("M342 -612 L392 -634", ancho=26)
                            + camino("M342 -612 L392 -634", ancho=12, color=PIEL))
        else:   # saluda
            adelante.append(_brazo(hx, hy, [(196, -640), (214, -768)]))
    return "".join(p), "".join(adelante)


def tito_svg(pose: str = "saluda", apertura: float = 0.0, parpadeo: float = 0.0, aguja: float = 0.0,
             respiracion: float = 0.0, mira: float = 0.25, guino: bool = False, inclinacion: float = 0.0) -> str:
    """Tito de cuerpo entero (origen en el piso, entre los pies; ~1000 px de alto)."""
    atras, adelante = cuerpo(pose if pose in POSES else "saluda", aguja, respiracion)
    return atras + g(cabeza(apertura, parpadeo, mira, guino), 0, CABEZA_Y, rot=inclinacion) + adelante


def tito_cara_svg(guino: bool = False, apertura: float = 0.0) -> str:
    """Solo la cabeza, centrada en (0, 0) (~370 px de ancho con el pelo): para la foto de perfil."""
    return cabeza(apertura=apertura, guino=guino)


def documento(contenido: str, ancho: int, alto: int, fondo: str | None = None) -> str:
    from .svg import documento as doc

    return doc(contenido, ancho, alto, fondo)
