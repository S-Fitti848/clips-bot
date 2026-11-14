"""Escenas de ACCIÓN para "Así Nació" (Santi, 2026-11-14: "dos personajes hablando no engancha":
mostrar, no contar).

Un guion describe cada escena en alto nivel (quién hace qué, qué objeto rebota o se rompe y dónde está
apoyado, qué hace la cámara) y este módulo lo traduce a la línea de tiempo de la base (`timeline`):
keyframes densos, gestos que se alternan (caminar = paso_a/paso_b), pedazos que salen volando con
gravedad, la DESTRUCCIÓN EN CADENA del gancho (la pelota rompe la tele, rebota, tira la lámpara, cae el
cuadro), sacudones de cámara en los golpes y la lista de efectos de sonido (SFX) con su segundo exacto.

Reglas de Santi para las escenas (2026-11-14, "escenas con sentido"): cada objeto está donde estaría en
la vida real (la lámpara de pie al lado del sillón, la tele sobre una mesa, el cuadro en la pared, el
jarrón en un estante) y nada aparece de la nada: lo que cae, cae de algún lado.

También: la pausa con la mascota (el Abuelo Tito, `tito.py`) y el VIAJE EN EL TIEMPO (Tito levanta el
reloj, la escena se va en remolino, el año cuenta hacia atrás y la imagen pasa a sepia).

Todo determinista (misma escena = mismo dibujo).
"""
from __future__ import annotations

import math
import random

from . import paleta as P

FPS_FISICA = 15            # keyframes por segundo en las trayectorias (el resto lo interpola)
G = 3600.0                 # gravedad en px/s² (a 1080 de ancho, se ve "de dibujo animado")
PISO = 1640                # donde pisan los personajes (más arriba que antes: abajo van los subtítulos)
PISO_PARED = 1420          # la línea del piso contra la pared: ahí se apoyan los muebles y cae lo que cae
POS = {"izquierda": 250, "centro": 540, "derecha": 830, "afuera_izq": -300, "afuera_der": 1380}
LADOS = ("izquierda", "centro", "derecha")

# rol → (personaje del elenco, cambios, escala)
ROLES = {
    "nene": ("nene", {}, 0.95),
    "nena": ("nene", {"peinado": "largo", "pelo": P.PELO[2], "ropa": P.ROSA}, 0.95),
    "mama": ("mama", {}, 0.85),
    "papa": ("narrador", {"anteojos": False, "bigote": True, "ropa": P.AZUL, "peinado": "corto"}, 0.85),
    "abuela": ("vecina", {"pelo": P.PELO[4], "ropa": P.VIOLETA}, 0.82),
    "fundador": ("abuelo", {}, 0.85),
    "inventor": ("abuelo", {"anteojos": True, "ropa": P.BLANCO, "sombrero": "ninguno",
                            "peinado": "rulos", "pelo": P.PELO[4]}, 0.85),
    "empresario": ("narrador", {"ropa": P.GRIS_OSCURO, "anteojos": False, "bigote": True,
                                "sombrero": "galera", "color_sombrero": "#2b2b33"}, 0.85),
    "rival": ("narrador", {"ropa": P.ROJO, "peinado": "corto", "bigote": True, "anteojos": False,
                           "pelo": P.PELO[3]}, 0.85),
    "cliente": ("vecina", {}, 0.82),
    "joven": ("pibe", {}, 0.88),
    "vendedor": ("pibe", {"ropa": P.TURQUESA, "sombrero": "ninguno"}, 0.88),
    "publicista": ("vecina", {"ropa": P.VIOLETA, "anteojos": True, "peinado": "largo"}, 0.82),
}

# Acciones de un personaje. Las de MOVIMIENTO son las que hacen que una escena no sea "estática".
ACCIONES = ("caminar", "correr", "saltar", "caerse", "retar", "martillar", "tirar", "atrapar",
            "festejar", "asustarse", "pensar", "entrar", "salir", "senalar", "quieto")
MOVIMIENTO = {"caminar", "correr", "saltar", "caerse", "retar", "martillar", "tirar", "atrapar",
              "festejar", "asustarse", "entrar", "salir"}
CARAS = ("feliz", "enojado", "sorprendido", "triste", "normal")

# Efectos de un objeto. Los DINÁMICOS cuentan como acción.
EFECTOS = ("aparece", "rebota", "cae_y_se_rompe", "se_rompe", "vuela", "gira", "crece", "llueve",
           "quieto")
DINAMICOS = {"rebota", "cae_y_se_rompe", "se_rompe", "vuela", "gira", "crece", "llueve"}
CAMARAS = ("fija", "acercar", "alejar", "paneo", "sacudon")
SFX = ("golpe", "vidrio", "whoosh", "boing", "pop", "tac", "ding", "viaje")

# Dónde se apoya cada cosa ("escenas con sentido"). Los ÍCONOS (un signo de pregunta, una lamparita
# de idea, un gráfico) pueden aparecer en el aire: son de dibujo animado, no objetos de la casa.
SOPORTES = ("piso", "mesa", "estante", "pared", "mano", "aire")
ICONOS = {"pregunta", "exclamacion", "lamparita", "idea_fallida", "flecha", "cartel", "grafico_sube",
          "grafico_baja", "calendario", "nube", "corona"}
LLUEVEN = {"billete", "moneda"}
SOPORTE_NATURAL = {"lampara": "piso", "tele": "mesa", "cuadro": "pared", "ventana": "pared",
                   "jarron": "estante", "botella": "mesa", "lata": "mesa", "caja": "mesa", "trofeo": "estante",
                   "celular": "mesa", "control": "mesa", "pelota": "piso", "zapatilla": "piso",
                   "reloj_bolsillo": "mano", "martillo": "mano", "camion": "piso", "engranaje": "piso",
                   "bolsa_plata": "piso", "megafono": "mano", "cohete": "piso"}
# Lo que solo tiene sentido en un lugar.
SOPORTE_OBLIGADO = {"cuadro": {"pared"}, "ventana": {"pared"}, "lampara": {"piso", "mesa"},
                    "tele": {"mesa", "piso"}}
# del origen del dibujo a la base (para apoyarlo justo arriba de la mesa o del piso)
ALTO_BASE = {"pelota": 70, "lampara": 187, "botella": 230, "lata": 150, "caja": 170, "jarron": 120,
             "tele": 130, "trofeo": 150, "celular": 180, "zapatilla": 104, "control": 130, "camion": 86,
             "engranaje": 120, "bolsa_plata": 160, "cohete": 60, "moneda": 110, "billete": 85}
Y_MESA = PISO_PARED - 226          # la tapa de la mesita
Y_ESTANTE = 820                    # la tabla del estante
Y_PARED = 640                      # el centro de lo que cuelga en la pared
Y_AIRE = 1000
ROMPIBLES_VIDRIO = {"ventana", "lampara", "botella", "lamparita", "celular", "jarron", "tele"}
COLOR_PEDAZOS = {"ventana": "#9fe3ff", "lampara": P.AMARILLO, "botella": "#9fe3ff", "tele": "#5b6b7a",
                 "lamparita": "#fff3b0", "jarron": P.TURQUESA, "celular": "#9fe3ff", "cuadro": P.MADERA}
CON_VERSION_ROTA = {"tele", "ventana"}


def _x(lado: str | None, defecto: str = "centro") -> float:
    return float(POS.get(lado or defecto, POS[defecto]))


def soporte_de(prop: str, soporte: str | None) -> str:
    if soporte in SOPORTES and soporte not in ("", None):
        if prop in SOPORTE_OBLIGADO and soporte not in SOPORTE_OBLIGADO[prop]:
            return sorted(SOPORTE_OBLIGADO[prop])[0] if prop != "lampara" else "piso"
        return soporte
    return "aire" if prop in ICONOS else SOPORTE_NATURAL.get(prop, "mesa")


def ubicar(prop: str, soporte: str, donde: str, fondo: str = "") -> tuple[float, float]:
    """(x, y) del centro del dibujo, apoyado donde corresponde."""
    x = _x(donde if donde in LADOS else "centro")
    if prop == "lampara" and soporte == "piso" and fondo == "casa" and donde != "izquierda":
        x = 470.0                       # la lámpara de pie, al lado del sillón
    base = ALTO_BASE.get(prop, 120)
    if soporte == "piso":
        return x, PISO_PARED - base
    if soporte == "mesa":
        return x, Y_MESA - base
    if soporte == "estante":
        return x, Y_ESTANTE - base * 0.75
    if soporte == "pared":
        return x, Y_PARED
    return x, Y_AIRE


def y_objeto(prop: str) -> float:
    return ubicar(prop, soporte_de(prop, None), "centro")[1]


def _alternar(a: str, b: str, t0: float, t1: float, paso: float) -> list[dict]:
    out, t, k = [], t0, 0
    while t < t1:
        out.append({"t": round(t, 3), "gesto": a if k % 2 == 0 else b})
        t += paso
        k += 1
    return out


def _bob(y: float, t0: float, t1: float, alto: float, paso: float) -> list[dict]:
    out, t, k = [], t0, 0
    while t < t1:
        out.append({"t": round(t, 3), "y": y - (alto if k % 2 else 0), "easing": "suave"})
        t += paso
        k += 1
    out.append({"t": round(t1, 3), "y": y, "easing": "suave"})
    return out


def _arco(x0, y0, x1, y1, t0, dur, alto, giro=0.0) -> list[dict]:
    pts = []
    n = max(2, int(dur * FPS_FISICA))
    for i in range(n + 1):
        u = i / n
        pts.append({"t": round(t0 + u * dur, 3), "x": round(x0 + (x1 - x0) * u, 1),
                    "y": round(y0 + (y1 - y0) * u - alto * math.sin(math.pi * u), 1),
                    "rotacion": round(giro * u, 1), "easing": "lineal"})
    return pts


class Escena:
    """Arma UNA escena: elementos, cámara y SFX (segundos locales a la escena)."""

    def __init__(self, dur: float, semilla: int = 0, fondo: str = ""):
        self.dur = dur
        self.fondo = fondo
        self.fondo_el: list[dict] = []        # muebles de apoyo (mesa, estante): atrás de todo
        self.elementos: list[dict] = []
        self.sfx: list[tuple[float, str]] = []
        self.golpes: list[tuple[float, float]] = []   # (segundo, fuerza) para el sacudón de cámara
        self.rnd = random.Random(semilla)
        self.mano: tuple[float, float, float] | None = None   # (x, y, t) de un "tirar"
        self._soportes: set = set()

    # ---- personajes ---------------------------------------------------------------------
    def actor(self, rol: str, accion: str, desde: str = "centro", hacia: str | None = None,
              cara: str = "normal", k: int = 0) -> None:
        nombre, cambios, escala = ROLES.get(rol, ROLES["joven"])
        x0 = _x(desde)
        x1 = _x(hacia, desde) if hacia and hacia in POS else x0
        t0 = round(0.05 + 0.18 * k, 2)
        fin = max(t0 + 0.6, self.dur - 0.1)
        el = {"tipo": "personaje", "nombre": nombre, "cambios": cambios, "x": x0, "y": PISO,
              "escala": escala}
        if cara in ("feliz", "enojado", "sorprendido", "triste"):
            el["cara"] = cara
        kf: list[dict] = []
        gestos: list[dict] = [{"t": 0, "gesto": "reposo"}]
        alto = 680 * escala * per_alto(nombre, cambios)
        sentido = 1 if x1 >= x0 else -1

        if accion in ("caminar", "entrar", "salir"):
            if accion == "entrar":
                x0 = POS["afuera_izq"] if x1 <= 540 else POS["afuera_der"]
                el["x"] = x0
            elif accion == "salir":
                x1 = POS["afuera_der"] if x0 >= 540 else POS["afuera_izq"]
            if abs(x1 - x0) < 60:
                x1 = x0 + (180 if x0 < 540 else -180)
            tw = min(fin - t0, max(1.0, abs(x1 - x0) / 420))
            kf += [{"t": t0, "x": x0}, {"t": t0 + tw, "x": x1, "easing": "lineal"}]
            kf += _bob(PISO, t0, t0 + tw, 14, 0.14)
            gestos += _alternar("paso_a", "paso_b", t0, t0 + tw, 0.25) + [{"t": t0 + tw, "gesto": "reposo"}]
        elif accion == "correr":
            if abs(x1 - x0) < 60:
                x1 = POS["derecha"] if x0 < 540 else POS["izquierda"]
            tw = min(fin - t0, max(0.55, abs(x1 - x0) / 1100))
            kf += [{"t": t0, "x": x0, "rotacion": 0}, {"t": t0 + 0.15, "rotacion": 7 * sentido},
                   {"t": t0 + tw, "x": x1, "easing": "lineal"}, {"t": t0 + tw + 0.2, "rotacion": 0}]
            kf += _bob(PISO, t0, t0 + tw, 26, 0.1)
            gestos += _alternar("correr_a", "correr_b", t0, t0 + tw, 0.16) + [{"t": t0 + tw, "gesto": "reposo"}]
            self.sfx.append((t0, "whoosh"))
        elif accion == "saltar":
            t, saltos = t0 + 0.15, 0
            while t + 0.6 <= fin and saltos < 3:
                kf += [{"t": t, "y": PISO}, {"t": t + 0.28, "y": PISO - 220, "easing": "salida"},
                       {"t": t + 0.56, "y": PISO, "easing": "entrada"}]
                gestos += [{"t": t, "gesto": "festejar"}, {"t": t + 0.5, "gesto": "reposo"}]
                self.sfx.append((t, "boing"))
                t += 0.75
                saltos += 1
        elif accion == "caerse":
            tc = t0 + 0.3
            kf += [{"t": tc, "rotacion": 0, "y": PISO}, {"t": tc + 0.1, "y": PISO - 60, "easing": "salida"},
                   {"t": tc + 0.4, "rotacion": 84 * (1 if x0 < 540 else -1), "y": PISO + 30,
                    "easing": "entrada"}]
            gestos += [{"t": tc, "gesto": "sorpresa"}]
            el["cara"] = "sorprendido"
            self.sfx.append((tc + 0.4, "golpe"))
            self.golpes.append((tc + 0.4, 20))
        elif accion == "retar":
            gestos += _alternar("retar_a", "retar_b", t0, fin, 0.2)
            kf += _bob(PISO, t0, fin, 10, 0.4)
            el.setdefault("cara", "enojado")
        elif accion == "martillar":
            gestos += _alternar("martillo_arriba", "martillo_abajo", t0, fin, 0.22)
            mx, my = x0 + 150 * escala, PISO - alto * 0.62
            mk, t, k2 = [], t0, 0
            while t < fin:
                mk.append({"t": round(t, 3), "rotacion": -40 if k2 % 2 == 0 else 25, "easing": "salida"})
                if k2 % 2:
                    self.sfx.append((t + 0.12, "tac"))
                t += 0.22
                k2 += 1
            self.elementos.append({"tipo": "prop", "nombre": "martillo", "x": mx, "y": my,
                                   "escala": 0.55 * escala, "keyframes": mk})
        elif accion == "tirar":
            gestos += [{"t": t0, "gesto": "lanzar_atras"}, {"t": t0 + 0.35, "gesto": "lanzar"},
                       {"t": t0 + 1.0, "gesto": "reposo"}]
            self.mano = (x0 + 120 * escala * (1 if x0 <= 540 else -1), PISO - alto * 0.72, t0 + 0.4)
            self.sfx.append((t0 + 0.35, "whoosh"))
        elif accion == "atrapar":
            kf += [{"t": t0 + 0.2, "y": PISO}, {"t": t0 + 0.4, "y": PISO - 60, "easing": "salida"},
                   {"t": t0 + 0.6, "y": PISO, "easing": "entrada"}]
            gestos += [{"t": t0 + 0.1, "gesto": "atrapar"}]
        elif accion == "festejar":
            gestos += _alternar("festejar", "sorpresa", t0, fin, 0.3)
            t = t0
            while t + 0.4 <= fin:
                kf += [{"t": t, "y": PISO}, {"t": t + 0.2, "y": PISO - 90, "easing": "salida"},
                       {"t": t + 0.4, "y": PISO, "easing": "entrada"}]
                t += 0.6
            el.setdefault("cara", "feliz")
        elif accion == "asustarse":
            kf += [{"t": t0 + 0.1, "y": PISO}, {"t": t0 + 0.25, "y": PISO - 120, "easing": "salida"},
                   {"t": t0 + 0.45, "y": PISO, "easing": "entrada"}]
            kf += [{"t": t0 + 0.45 + i * 0.07, "rotacion": (4 if i % 2 else -4)} for i in range(6)]
            kf += [{"t": t0 + 0.9, "rotacion": 0}]
            gestos += [{"t": t0 + 0.1, "gesto": "cubrirse"}]
            el["cara"] = "sorprendido"
            self.sfx.append((t0 + 0.1, "boing"))
        elif accion == "pensar":
            gestos += [{"t": t0, "gesto": "pensar"}]
            kf += _bob(PISO, t0, fin, 6, 0.6)
            self.elementos.append({"tipo": "prop", "nombre": "lamparita", "x": x0,
                                   "y": PISO - alto - 130, "escala": 0.65, "entrada": "rebote",
                                   "desde": round(min(fin - 0.3, t0 + 0.7), 2)})
            self.sfx.append((min(fin - 0.3, t0 + 0.7), "ding"))
        elif accion == "senalar":
            gestos += [{"t": t0, "gesto": "senalar" if x0 < 540 else "senalar_izq"}]
            kf += _bob(PISO, t0, fin, 6, 0.5)
        else:   # quieto
            gestos += [{"t": t0, "gesto": "explicar"}]
            kf += _bob(PISO, t0, fin, 5, 0.6)
        el["keyframes"] = sorted(kf, key=lambda q: q["t"])
        el["gestos"] = gestos
        self.elementos.append(el)

    # ---- objetos --------------------------------------------------------------------------
    def _apoyo(self, soporte: str, x: float) -> None:
        """La mesita o el estante debajo de un objeto (una sola vez por lugar)."""
        if soporte not in ("mesa", "estante") or (soporte, x) in self._soportes:
            return
        self._soportes.add((soporte, x))
        self.fondo_el.append({"tipo": "prop", "nombre": soporte, "x": x,
                              "y": Y_MESA if soporte == "mesa" else Y_ESTANTE})

    def _romper(self, prop: str, base: dict, x: float, y: float, t: float, fuerza: float = 14) -> None:
        """El objeto (ya agregado hasta `t` en `base`) se rompe en `t`: su versión rota o se cae, y
        los pedazos, el sonido y un sacudón chico."""
        if prop in CON_VERSION_ROTA:
            self.elementos.append({**base, "x": x, "y": y, "rota": True, "desde": round(t, 3)})
        elif prop == "lampara":       # se cae de costado y se rompe contra el piso
            caida = 0.32
            self.elementos.append({**base, "x": x, "y": y, "desde": round(t, 3), "hasta": round(t + caida, 3),
                                   "keyframes": [{"t": t, "rotacion": 0},
                                                 {"t": t + caida, "rotacion": 82, "x": x + 120,
                                                  "y": PISO_PARED - 60, "easing": "entrada"}]})
            self._pedazos(prop, x + 130, PISO_PARED - 50, t + caida)
            return
        elif prop == "cuadro":        # se descuelga y cae al piso
            caida = math.sqrt(2 * (PISO_PARED - 80 - y) / G) * 1.4
            self.elementos.append({**base, "x": x, "y": y, "desde": round(t, 3),
                                   "keyframes": [{"t": t, "rotacion": 0, "y": y},
                                                 {"t": t + caida, "rotacion": -18, "y": PISO_PARED - 80,
                                                  "easing": "entrada"}]})
            self.sfx.append((round(t, 3), "pop"))
            self.sfx.append((round(t + caida, 3), "golpe"))
            self.golpes.append((t + caida, fuerza))
            return
        self._pedazos(prop, x, y, t, fuerza)

    def objeto(self, prop: str, efecto: str, donde: str = "centro", texto: str = "",
               color: str | None = None, k: int = 0, blanco: tuple[float, float] | None = None,
               soporte: str | None = None) -> float | None:
        """Agrega el objeto (apoyado donde corresponde); devuelve el segundo del impacto/rotura si lo hay."""
        sop = soporte_de(prop, soporte)
        x, y = ubicar(prop, sop, donde, self.fondo)
        self._apoyo(sop, x)
        base = {"tipo": "prop", "nombre": prop, "x": x, "y": y}
        if color:
            base["color"] = color
        if texto:
            base["texto"] = texto[:12]
        te = round(0.35 + 0.2 * k, 2)
        if efecto == "quieto":
            self.elementos.append(base)
            return None
        if efecto == "aparece":
            self.elementos.append({**base, "entrada": "rebote", "desde": te})
            self.sfx.append((te, "pop"))
            return None
        if efecto == "gira":
            self.elementos.append({**base, "keyframes": [{"t": 0, "rotacion": 0},
                                                         {"t": self.dur, "rotacion": 540, "easing": "lineal"}]})
            return None
        if efecto == "crece":
            self.elementos.append({**base, "keyframes": [{"t": te, "escala": 0.2},
                                                         {"t": te + 0.6, "escala": 1.7, "easing": "rebote"}]})
            self.sfx.append((te, "pop"))
            return None
        if efecto == "llueve":
            for i in range(8):
                xi = 80 + i * 130 + self.rnd.uniform(-30, 30)
                ti = te + i * 0.12
                self.elementos.append({**base, "x": xi, "y": -200, "escala": 0.55, "desde": round(ti, 2),
                                       "keyframes": [{"t": ti, "y": -200, "rotacion": 0},
                                                     {"t": ti + 1.4, "y": 2200, "rotacion": 220 * (1 if i % 2 else -1),
                                                      "easing": "entrada"}]})
            return None
        if efecto == "vuela":
            if self.mano:
                ox, oy, tt = self.mano
            else:
                ox, oy, tt = (-150 if x >= 540 else 1230), 900, te
            dx, dy = blanco if blanco else ((1230 if ox < 540 else -150), 700)
            dur = 0.8
            self.elementos.append({**base, "x": ox, "y": oy, "escala": 0.8, "desde": round(tt, 2),
                                   "hasta": round(tt + dur + (0.02 if blanco else 0.6), 2),
                                   "keyframes": _arco(ox, oy, dx, dy, tt, dur, 380, 540)})
            self.sfx.append((tt, "whoosh"))
            return round(tt + dur, 3)
        if efecto == "rebota":
            if self.mano:
                px, py, tt = self.mano
                vx = 520 if px <= 540 else -520
                vy = -700.0
            else:
                px, py, tt, vx, vy = x, y, te, 240.0, -300.0
            pts, t, botes = [], 0.0, 0
            paso = 1 / FPS_FISICA
            piso = PISO_PARED + 120          # rebota en el piso del medio de la habitación
            while tt + t < self.dur - 0.05:
                pts.append({"t": round(tt + t, 3), "x": round(px, 1), "y": round(py, 1),
                            "rotacion": round(t * 300, 1), "easing": "lineal"})
                vy += G * paso
                px += vx * paso
                py += vy * paso
                if px < 80 or px > 1000:
                    vx = -vx
                if py >= piso and vy > 0:
                    py = piso
                    if abs(vy) > 450 and botes < 5:
                        self.sfx.append((tt + t + paso, "boing"))
                        botes += 1
                    vy = -vy * 0.62
                    vx *= 0.85
                t += paso
            self.elementos.append({**base, "x": pts[0]["x"] if pts else x, "y": pts[0]["y"] if pts else y,
                                   "escala": 0.8, "desde": round(tt, 2), "keyframes": pts})
            return None
        if efecto == "cae_y_se_rompe":
            # cae DE SU LUGAR (la mesa, el estante, la pared): nada sale del cielo
            tc = te
            caida = math.sqrt(2 * max(60.0, PISO_PARED - 40 - y) / G) * 1.6
            impacto = round(tc + caida, 3)
            self.elementos.append({**base, "hasta": impacto,
                                   "keyframes": [{"t": tc, "y": y, "rotacion": 0, "x": x},
                                                 {"t": tc + 0.15, "x": x + 25, "rotacion": 12, "easing": "salida"},
                                                 {"t": impacto, "y": PISO_PARED - 40, "rotacion": 40,
                                                  "x": x + 60, "easing": "entrada"}]})
            self._pedazos(prop, x + 60, PISO_PARED - 40, impacto, 18)
            return impacto
        if efecto == "se_rompe":
            tb = round(te + 0.6, 3)
            self.elementos.append({**base, "hasta": tb})
            self._romper(prop, base, x, y, tb)
            return tb
        self.elementos.append(base)
        return None

    def cadena(self, objetivos: list[dict], proyectil: str = "pelota", color: str | None = None) -> list[float]:
        """El efecto dominó del gancho (Santi: "tira la pelota → rompe la tele → rebota y tira la
        lámpara → cae un cuadro"): 2 a 4 cosas, cada una en su lugar, cada golpe con su sonido y un
        sacudón chico. Devuelve los segundos de cada impacto."""
        if self.mano:
            cx, cy, t = self.mano
        else:
            cx, cy, t = -120.0, 900.0, 0.3
            self.sfx.append((t, "whoosh"))
        pts: list[dict] = []
        impactos = []
        tramo = 0.42
        restante = max(1.2, self.dur - t - 0.2)
        if len(objetivos) * tramo > restante:
            tramo = restante / max(1, len(objetivos))
        for k, o in enumerate(objetivos[:4]):
            prop = o.get("prop") or "jarron"
            sop = soporte_de(prop, o.get("soporte"))
            x, y = ubicar(prop, sop, o.get("donde") or LADOS[k % 3], self.fondo)
            self._apoyo(sop, x)
            t_imp = round(t + tramo, 3)
            alto = 300 if k == 0 else 180
            nuevos = _arco(cx, cy, x, y, t, tramo, alto, 360)
            pts += nuevos if not pts else nuevos[1:]
            base = {"tipo": "prop", "nombre": prop, "x": x, "y": y}
            self.elementos.append({**base, "hasta": t_imp})
            self._romper(prop, base, x, y, t_imp, fuerza=12 + 3 * k)
            if prop not in ("cuadro", "lampara"):
                self.sfx.append((t_imp, "golpe"))
            impactos.append(t_imp)
            cx, cy, t = x, y, t_imp
        # después del último golpe la pelota cae al piso y rebota una vez
        fin = min(self.dur - 0.05, t + 0.6)
        if fin > t + 0.1:
            pts += _arco(cx, cy, cx + (120 if cx < 540 else -120), PISO_PARED + 100, t, fin - t, 80, 200)[1:]
            self.sfx.append((round(fin, 3), "boing"))
        if pts:
            el = {"tipo": "prop", "nombre": proyectil, "x": pts[0]["x"], "y": pts[0]["y"], "escala": 0.7,
                  "desde": pts[0]["t"], "keyframes": pts}
            if color:
                el["color"] = color
            self.elementos.append(el)
        return impactos

    def _pedazos(self, prop: str, x: float, y: float, t: float, fuerza: float = 14) -> None:
        c = COLOR_PEDAZOS.get(prop, P.GRIS)
        for i in range(8):
            vx = self.rnd.uniform(-650, 650)
            vy = self.rnd.uniform(-1300, -500)
            pts, px, py, tt = [], x, y, 0.0
            while tt <= 0.9:
                pts.append({"t": round(t + tt, 3), "x": round(px, 1), "y": round(py, 1),
                            "rotacion": round(tt * 700 * (1 if i % 2 else -1), 1),
                            "opacidad": round(max(0.0, 1 - max(0.0, tt - 0.5) / 0.4), 2), "easing": "lineal"})
                vy += G * (1 / FPS_FISICA)
                px += vx / FPS_FISICA
                py = min(PISO_PARED + 40, py + vy / FPS_FISICA)
                tt += 1 / FPS_FISICA
            self.elementos.append({"tipo": "prop", "nombre": "pedazo", "forma": i % 4, "color": c, "x": x,
                                   "y": y, "escala": self.rnd.uniform(0.6, 1.1), "desde": round(t, 3),
                                   "hasta": round(t + 0.95, 3), "keyframes": pts})
        self.sfx.append((round(t, 3), "vidrio" if prop in ROMPIBLES_VIDRIO else "golpe"))
        self.golpes.append((t, fuerza))

    # ---- cámara -----------------------------------------------------------------------------
    def camara(self, tipo: str) -> list[dict]:
        d = self.dur
        golpes = sorted(self.golpes) or ([(d * 0.5, 22)] if tipo == "sacudon" else [])
        z0, z1 = {"acercar": (1.0, 1.14), "alejar": (1.16, 1.02), "paneo": (1.18, 1.18),
                  "sacudon": (1.08, 1.12)}.get(tipo, (1.0, 1.04))
        if golpes:
            z0, z1 = max(z0, 1.06), max(z1, 1.06)
        kf = [{"t": 0, "zoom": z0}, {"t": d, "zoom": z1, "easing": "suave"}]
        if tipo == "paneo":
            kf += [{"t": 0, "x": -70}, {"t": d, "x": 70, "easing": "suave"}]
        ultimo = -1.0
        for tg, fuerza in golpes[:4]:   # sacudón: 0,35 s de corridas cortas que se apagan
            if tg - ultimo < 0.3:
                continue
            ultimo = tg
            for i in range(6):
                a = fuerza * (1 - i / 6)
                kf.append({"t": round(tg + i * 0.05, 3), "x": round(a * (1 if i % 2 else -1), 1),
                           "y": round(a * 0.6 * (1 if i % 3 else -1), 1), "easing": "lineal"})
            kf.append({"t": round(tg + 0.32, 3), "x": 0, "y": 0, "easing": "suave"})
        return kf


def per_alto(nombre: str, cambios: dict) -> float:
    from . import personajes as per

    return float(cambios.get("alto_cuerpo", per.ELENCO.get(nombre, per.ELENCO["narrador"]).alto_cuerpo))


def es_dinamica(spec: dict) -> bool:
    """¿La escena muestra algo que pasa? (no "dos personajes hablando")."""
    return bool(spec.get("cadena")) or \
        any(a.get("accion") in MOVIMIENTO for a in spec.get("actores") or []) or \
        any(o.get("efecto") in DINAMICOS for o in spec.get("objetos") or [])


def escena_accion(spec: dict, dur: float, i: int, primera: bool = False,
                  tono: float = 0.0) -> tuple[dict, list[tuple[float, str]]]:
    """Una escena del guion → (dict de timeline.Escena, [(segundo local, sfx)])."""
    fondo = spec.get("fondo") or "ciudad"
    e = Escena(dur, semilla=i + 1, fondo=fondo)
    actores = list(spec.get("actores") or [])[:3]
    usados = set()
    for k, a in enumerate(actores):
        desde = a.get("desde") if a.get("desde") in POS else LADOS[k % 3] if len(actores) > 1 else "centro"
        if desde in usados and desde in LADOS:
            desde = next((l for l in LADOS if l not in usados), desde)
        usados.add(desde)
        e.actor(a.get("rol") or "joven", a.get("accion") or "quieto", desde, a.get("hacia"),
                a.get("cara") or "normal", k)
    colores = (P.NARANJA, P.AZUL, P.ROJO, P.VERDE, P.VIOLETA)
    objetos = list(spec.get("objetos") or [])[:3]
    cadena = [o for o in (spec.get("cadena") or []) if o.get("prop")][:4]
    if cadena:
        proy = next((o for o in objetos if o.get("efecto") in ("vuela", "rebota")), None)
        e.cadena(cadena, (proy or {}).get("prop") or "pelota", colores[i % len(colores)])
        objetos = [o for o in objetos if o is not proy]
    rompible = next((o for o in objetos if o.get("efecto") == "se_rompe"), None)
    blanco = None
    if rompible:
        sop = soporte_de(rompible.get("prop") or "", rompible.get("soporte"))
        blanco = ubicar(rompible.get("prop") or "", sop, rompible.get("donde") or "centro", fondo)
    impacto = None
    for k, o in enumerate(objetos):
        if o is rompible:
            continue
        r = e.objeto(o.get("prop") or "pelota", o.get("efecto") or "quieto", o.get("donde") or "centro",
                     str(o.get("texto") or ""), colores[(i + k) % len(colores)], k,
                     blanco if o.get("efecto") == "vuela" else None, o.get("soporte"))
        if o.get("efecto") == "vuela" and r is not None:
            impacto = r
    if rompible is not None:
        if impacto is not None:   # lo rompe lo que voló: la rotura cae justo en el impacto
            e2 = Escena(dur, semilla=i + 7, fondo=fondo)
            e2.objeto(rompible.get("prop") or "ventana", "se_rompe", rompible.get("donde") or "centro",
                      str(rompible.get("texto") or ""), None, 0, soporte=rompible.get("soporte"))
            corr = impacto - 0.95      # en e2 la rotura es en te + 0,6 = 0,95
            for el in e2.elementos:
                for clave in ("desde", "hasta"):
                    if clave in el:
                        el[clave] = round(el[clave] + corr, 3)
                for kf in el.get("keyframes", []):
                    kf["t"] = round(kf["t"] + corr, 3)
            e.elementos += e2.elementos
            e.fondo_el += [m for m in e2.fondo_el if m not in e.fondo_el]
            e.sfx += [(t + corr, s) for t, s in e2.sfx]
            e.golpes += [(t + corr, f) for t, f in e2.golpes]
        else:
            e.objeto(rompible.get("prop") or "ventana", "se_rompe", rompible.get("donde") or "centro",
                     str(rompible.get("texto") or ""), None, len(objetos), soporte=rompible.get("soporte"))
    # orden de dibujo: muebles de apoyo → lo que cuelga o se apoya atrás → personajes → pedazos y proyectiles
    fondo_cosas = {"ventana", "lampara", "cuadro", "tele", "jarron", "botella", "trofeo"}
    e.elementos.sort(key=lambda el: 0 if el.get("nombre") in fondo_cosas and not el.get("keyframes") else
                     1 if el.get("tipo") == "personaje" else 2)
    elementos = e.fondo_el + e.elementos
    texto = str(spec.get("texto_pantalla") or "").strip()
    if texto:
        elementos.append({"tipo": "gancho", "texto": texto, "y": 330, "modo": "palabras" if primera else "rebote",
                          "tam": 100, "desde": 0.0 if primera else 0.2})
    tr = spec.get("transicion") if spec.get("transicion") in ("corte", "fundido", "zoom", "barrido") else "barrido"
    d = {"duracion": dur, "fondo": {"tipo": fondo, "semilla": i + 1},
         "transicion": {"tipo": "corte" if primera else tr, "duracion": 0.25},
         "camara": e.camara(spec.get("camara") or "fija"), "elementos": elementos, "tono": tono}
    sfx = sorted((round(t, 3), s) for t, s in e.sfx if 0 <= t < dur)
    return d, sfx


def escena_locutor(dur: float, k: int = 0) -> tuple[dict, list[tuple[float, str]]]:
    """La PAUSA: la escena de atrás congelada y gris, y Tito (la mascota de "Así Nació") entra por el
    costado, comenta (la boca sigue la voz) y se va. Del lado izquierdo señala la escena; del derecho
    saluda y levanta el reloj."""
    izq = k % 2 == 0
    x = 255 if izq else 825
    afuera = -420 if izq else 1500
    poses = ([{"t": 0, "pose": "saluda"}, {"t": 0.6, "pose": "senala"}] if izq else
             [{"t": 0, "pose": "saluda"}, {"t": max(0.7, dur * 0.5), "pose": "reloj"}])
    tito = {"tipo": "tito", "x": x, "y": PISO + 20, "escala": 0.66, "habla": True,
            "entrada": "izquierda" if izq else "derecha",
            "keyframes": [{"t": max(0.6, dur - 0.3), "x": x}, {"t": dur, "x": afuera, "easing": "entrada"}],
            "poses": poses}
    return ({"duracion": dur, "congela": True, "fondo": {"tipo": "color", "color": "#000000"},
             "transicion": {"tipo": "corte"}, "elementos": [tito]},
            [(0.0, "tac"), (0.05, "whoosh")])


VIAJE_S = 1.25


def escena_viaje(dur: float, de: int, a: int, presente: int = 2026) -> tuple[dict, list[tuple[float, str]]]:
    """El VIAJE EN EL TIEMPO (Santi, 2026-11-14): Tito levanta el reloj (las agujas giran a toda
    velocidad), la escena de atrás se va en remolino, el año cuenta de `de` a `a` y la imagen pasa a
    sepia (al pasado) o vuelve al color (al presente). Dura `dur` (~1,25 s)."""
    al_pasado = a < de
    tito = {"tipo": "tito", "x": 830, "y": PISO + 20, "escala": 0.6, "entrada": "derecha",
            "giro_aguja": 1440, "poses": [{"t": 0, "pose": "reloj"}],
            "keyframes": [{"t": max(0.5, dur - 0.2), "x": 830}, {"t": dur, "x": 1500, "easing": "entrada"}]}
    contador = {"tipo": "contador", "de": de, "a": a, "dur": max(0.4, dur - 0.45), "desde": 0.15,
                "x": 540, "y": 760, "tam": 230, "entrada": "rebote"}
    giro = -260 if al_pasado else 260
    camara = [{"t": 0, "zoom": 1.0, "rotacion": 0}, {"t": dur, "zoom": 2.4, "rotacion": giro, "easing": "entrada"}]
    return ({"duracion": dur, "congela": True, "girar": True, "fondo": {"tipo": "color", "color": "#000000"},
             "transicion": {"tipo": "corte"}, "camara": camara, "elementos": [contador, tito],
             "tono": [0.0 if de >= presente else 1.0, 0.0 if a >= presente else 1.0]},
            [(0.0, "viaje")])
