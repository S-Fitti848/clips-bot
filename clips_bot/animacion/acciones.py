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
PISO = 1830                # donde pisan los personajes (2026-11-14: los subtítulos pasaron ARRIBA; abajo
                           # los personajes quedan por delante de los muebles, que van contra la pared)
BANDA_SUBTITULOS = 300     # nada de la escena sube de acá (y < 300): ahí van los subtítulos
Y_TEXTO_PANTALLA = 430
PISO_PARED = 1420          # la línea del piso contra la pared: ahí se apoyan los muebles y cae lo que cae
POS = {"izquierda": 250, "centro": 540, "derecha": 830, "afuera_izq": -300, "afuera_der": 1380}
LADOS = ("izquierda", "centro", "derecha")

# rol → (personaje del elenco, cambios, escala)
ROLES = {
    "nene": ("nene", {}, 0.8),
    "nena": ("nene", {"peinado": "largo", "pelo": P.PELO[2], "ropa": P.ROSA}, 0.8),
    "mama": ("mama", {}, 0.74),
    "papa": ("narrador", {"anteojos": False, "bigote": True, "ropa": P.AZUL, "peinado": "corto"}, 0.74),
    "abuela": ("vecina", {"pelo": P.PELO[4], "ropa": P.VIOLETA}, 0.72),
    "fundador": ("abuelo", {}, 0.74),
    "inventor": ("narrador", {"anteojos": True, "ropa": P.BLANCO, "sombrero": "ninguno",
                              "peinado": "jopo", "pelo": P.PELO[0], "bigote": True}, 0.74),
    "empresario": ("narrador", {"ropa": P.GRIS_OSCURO, "anteojos": False, "bigote": True,
                                "sombrero": "galera", "color_sombrero": "#2b2b33"}, 0.74),
    "rival": ("narrador", {"ropa": P.ROJO, "peinado": "corto", "bigote": True, "anteojos": False,
                           "pelo": P.PELO[3]}, 0.74),
    "cliente": ("vecina", {}, 0.72),
    "joven": ("pibe", {}, 0.76),
    "vendedor": ("pibe", {"ropa": P.TURQUESA, "sombrero": "ninguno"}, 0.76),
    "publicista": ("vecina", {"ropa": P.VIOLETA, "anteojos": True, "peinado": "largo"}, 0.72),
    # Variedad según la historia y la época (Santi, 2026-11-15: "no siempre los mismos dos chicos")
    "obrero": ("narrador", {"ropa": "#3d6fb6", "pantalon": "#2c3e66", "sombrero": "gorra",
                            "color_sombrero": P.AMARILLO, "anteojos": False, "peinado": "corto"}, 0.74),
    "obrera": ("vecina", {"ropa": "#3d6fb6", "pantalon": "#2c3e66", "peinado": "largo"}, 0.72),
    "cientifica": ("mama", {"ropa": P.BLANCO, "anteojos": True, "peinado": "rulos", "pelo": P.PELO[3]}, 0.74),
    "medico": ("narrador", {"ropa": P.BLANCO, "anteojos": True, "bigote": False, "peinado": "corto",
                            "pantalon": "#5b6170"}, 0.74),
    "enfermera": ("mama", {"ropa": "#9fd8d0", "pantalon": "#9fd8d0", "peinado": "largo", "pelo": P.PELO[0]}, 0.74),
    "granjero": ("narrador", {"ropa": "#c0603b", "pantalon": "#3a5a8c", "sombrero": "gorra",
                              "color_sombrero": "#c9a24a", "anteojos": False, "bigote": True}, 0.74),
    "marinero": ("pibe", {"ropa": "#1d3557", "sombrero": "gorra", "color_sombrero": P.BLANCO}, 0.76),
    "cocinero": ("narrador", {"ropa": P.BLANCO, "sombrero": "galera", "color_sombrero": P.BLANCO,
                              "anteojos": False, "bigote": True}, 0.74),
    "deportista": ("pibe", {"ropa": P.ROJO, "sombrero": "ninguno", "pantalon": P.BLANCO}, 0.76),
    "estudiante": ("pibe", {"ropa": P.VERDE, "sombrero": "ninguno", "anteojos": True}, 0.76),
    "inventora": ("mama", {"ropa": P.BLANCO, "anteojos": True, "peinado": "rulos", "pelo": P.PELO[4]}, 0.74),
    # Personajes según quién es y su rol (Santi, 2026-11-17): los empleados del negocio y los que reparten
    "cajero": ("narrador", {"ropa": P.BLANCO, "anteojos": False, "peinado": "corto"}, 0.74),
    "cajera": ("mama", {"ropa": P.BLANCO, "peinado": "largo"}, 0.74),
    "vendedora": ("vecina", {"ropa": P.BLANCO, "peinado": "largo"}, 0.72),
    "repartidor": ("pibe", {"ropa": "#b7a58a", "sombrero": "boina", "color_sombrero": "#5a5048"}, 0.76),
}
NINOS = {"nene", "nena"}

# Personajes fieles (Santi, 2026-11-15: "Ernő Rubik es un hombre y salió como una señora"): el género y la
# edad mandan sobre el dibujo base del rol; el rol pone la ropa y los accesorios.
GENEROS = ("hombre", "mujer")
EDADES = ("chico", "joven", "adulto", "mayor")
BASE = {("hombre", "chico"): ("nene", 0.8), ("mujer", "chico"): ("nene", 0.8),
        ("hombre", "joven"): ("pibe", 0.76), ("mujer", "joven"): ("vecina", 0.72),
        ("hombre", "adulto"): ("narrador", 0.74), ("mujer", "adulto"): ("mama", 0.74),
        ("hombre", "mayor"): ("abuelo", 0.72), ("mujer", "mayor"): ("vecina", 0.72)}


CLARO = "#f4f1e8"     # lona o algodón claro: delantales, guardapolvos


def vestir(rol: str, anio: int, genero: str) -> dict:
    """La ropa de cada uno según su ROL y la ÉPOCA de la escena (Santi, 2026-11-17: "los obreros con mameluco o
    delantal y gorra de fábrica, los cajeros con uniforme, los clientes con ropa de calle de la época, los
    empresarios de traje, los científicos con guardapolvo"). Piezas de la biblioteca (`Personaje.vestuario`) que se
    combinan; devuelve los cambios que van encima de los del rol."""
    a = anio if anio and anio < 2026 else 2026
    m = genero == "mujer"
    v: dict = {}
    if rol in ("obrero", "obrera", "repartidor", "granjero"):
        if rol == "granjero":
            v = {"vestuario": "mameluco", "color_vestuario": "#3a5a8c", "pantalon": "#3a5a8c", "ropa": "#c0603b",
                 "sombrero": "boina" if a < 1950 else "gorra", "color_sombrero": "#8d6e63"}
        elif a < 1940:     # el obrero de antes: camisa, delantal de lona y gorra plana; la obrera, falda y cofia
            v = {"vestuario": "delantal", "color_vestuario": CLARO, "ropa": "#b7a58a", "pantalon": "#4a4036",
                 "sombrero": "boina", "color_sombrero": "#5a5048"}
        else:              # de 1940 en adelante: mameluco azul y gorra
            v = {"vestuario": "mameluco", "color_vestuario": "#3d6fb6", "pantalon": "#3d6fb6", "ropa": "#d9dde6",
                 "sombrero": "gorra", "color_sombrero": "#3d6fb6"}
        if m:
            v.update({"sombrero": "cofia", "color_sombrero": CLARO})
            if a < 1950:
                v.update({"vestuario": v["vestuario"] + "+falda_larga", "pantalon": "#5b4a6e", "ropa": "#9fb3c8"})
    elif rol in ("cajero", "cajera", "vendedor", "vendedora"):
        v = {"vestuario": "uniforme", "color_vestuario": "#2f5d50", "ropa": P.BLANCO, "sombrero": "ninguno"}
        if m and a < 1960:
            v.update({"vestuario": "uniforme+falda_larga", "pantalon": "#2f3e46"})
    elif rol in ("empresario", "fundador"):
        v = {"vestuario": "traje", "ropa": "#2f2f3a", "pantalon": "#2f2f3a",
             "sombrero": "galera" if a < 1915 else "bombin" if a < 1950 else "ninguno", "color_sombrero": "#2b2b33"}
        if not m and a < 1940:
            v["bigote"] = True
    elif rol in ("inventor", "inventora", "cientifica", "medico"):
        v = {"vestuario": "guardapolvo", "color_vestuario": CLARO}
    elif rol == "cocinero":
        v = {"vestuario": "delantal", "color_vestuario": CLARO}
    elif rol in ("cliente", "papa", "mama", "abuela", "joven", "rival", "publicista"):
        if a < 1950:       # ropa de calle de la época: saco y sombrero ellos, falda larga ellas
            v = ({"vestuario": "falda_larga", "pantalon": "#6d4c6e", "ropa": "#c9a0b4"} if m else
                 {"vestuario": "calle", "ropa": "#5b4636", "pantalon": "#3b3330",
                  "sombrero": "bombin" if a < 1935 else "ninguno", "color_sombrero": "#2b2b33"})
        elif a < 1975 and not m:
            v = {"vestuario": "calle", "ropa": "#6b5b4b"}
    if m:
        v.pop("bigote", None)
    return v


def genero_de(nombre: str, cambios: dict, genero: str = "") -> str:
    if genero in GENEROS:
        return genero
    return "mujer" if nombre in ("mama", "vecina") or (nombre == "nene" and cambios.get("peinado") == "largo") else "hombre"


# Lo que tiene en las manos cada rol cuando trabaja (Santi, 2026-11-17: "todos hacen algo según su rol"; nadie con
# las manos juntas o vacías mirando a cámara). "{prota}" = el producto de la historia.
TRABAJO_ROL = {"obrero": "caja", "obrera": "{prota}", "repartidor": "caja", "granjero": "caja",
               "cajero": "billete", "cajera": "billete", "vendedor": "{prota}", "vendedora": "{prota}",
               "cliente": "{prota}", "cocinero": "{prota}"}
QUE_HACE_ROL = {"obrero": "carga cajas", "obrera": "empaca el producto", "repartidor": "carga cajas",
                "granjero": "carga la cosecha", "cajero": "cobra", "cajera": "cobra", "vendedor": "ofrece el producto",
                "vendedora": "ofrece el producto", "cliente": "elige y compra", "cocinero": "cocina"}


def aspecto(rol: str, genero: str = "", edad: str = "") -> tuple[str, dict, float]:
    """(personaje base, cambios, escala) del rol, con el género y la edad pedidos (si vienen)."""
    nombre, cambios, escala = ROLES.get(rol, ROLES["joven"])
    if genero not in GENEROS and edad not in EDADES:
        return nombre, cambios, escala
    genero = genero if genero in GENEROS else ("mujer" if nombre in ("mama", "vecina") else "hombre")
    edad = edad if edad in EDADES else ("chico" if rol in NINOS else "adulto")
    nombre, escala = BASE[(genero, edad)]
    cambios = dict(cambios)
    if genero == "mujer":
        cambios.pop("bigote", None)
        if cambios.get("peinado") in (None, "corto", "jopo", "pelado"):
            cambios["peinado"] = "largo"
    else:
        if cambios.get("peinado") in ("largo", "rulos"):
            cambios["peinado"] = "corto"
    if edad == "mayor":
        cambios["pelo"] = P.PELO[4]
    elif cambios.get("pelo") == P.PELO[4]:
        cambios["pelo"] = P.PELO[0]
    if edad == "chico":
        cambios = {k: v for k, v in cambios.items() if k in ("ropa", "pelo", "peinado", "pantalon")}
        cambios["peinado"] = "largo" if genero == "mujer" else "corto"
    return nombre, cambios, escala

# Acciones de un personaje. Las de MOVIMIENTO son las que hacen que una escena no sea "estática".
ACCIONES = ("caminar", "correr", "saltar", "caerse", "retar", "martillar", "tirar", "atrapar",
            "festejar", "asustarse", "pensar", "entrar", "salir", "senalar", "quieto",
            "fabricar", "vender", "usar", "probar")
MOVIMIENTO = {"caminar", "correr", "saltar", "caerse", "retar", "martillar", "tirar", "atrapar",
              "festejar", "asustarse", "entrar", "salir", "fabricar", "vender", "usar", "probar"}
# Acciones de trabajo (2026-11-15: "fabricando, inventando, vendiendo, gente usando el producto"): se
# dibujan con los gestos de otra acción que ya tiene movimiento con peso.
ALIAS_ACCION = {"usar": "atrapar", "probar": "saltar"}
# Reglas_v3 de Así Nació (Santi, 2026-11-16; lo prende marcas.armar_video): usar, probar y fabricar = las manos
# adelante haciendo algo con el objeto (sostener_a/b), y el objeto en las dos manos, delante del cuerpo.
MANOS_V3 = False
SIN_PLATA_SIMBOLO = False   # lo prende marcas con animacion.uso_manos
NO_DECORADO = {"ventana", "puerta", "cuadro", "cortina", "lampara", "estante", "mesa"}   # parte del cuarto, no decorado
CON_MANOS = ("usar", "probar", "fabricar")
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
Y_CINTA = 1650                     # la tapa de la cinta de la línea de producción (a la altura de la cintura)
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


X_MUEBLE = {"izquierda": 175.0, "centro": 905.0, "derecha": 905.0}   # contra la pared, al costado


def ubicar(prop: str, soporte: str, donde: str, fondo: str = "", espejo: bool = False) -> tuple[float, float]:
    """(x, y) del centro del dibujo, apoyado donde corresponde. Las mesas y los estantes van contra
    la pared A LOS COSTADOS (Santi: "una mesita en el medio tapando al inventor"): lo que está arriba
    de una mesa o un estante queda a un costado, nunca en el medio."""
    x = _x(donde if donde in LADOS else "centro")
    if soporte in ("mesa", "estante"):
        x = X_MUEBLE.get(donde, 930.0)
    if prop == "lampara" and soporte == "piso" and fondo == "casa":
        x = 610.0 if espejo else 470.0  # la lámpara de pie, al lado del sillón (de un lado o del otro)
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


def anclar_abajo(kf: list[dict], dur: float) -> list[dict]:
    """La cámara, al acercarse, se queda pegada ABAJO (los personajes pisan en PISO, cerca del borde
    inferior: con el zoom centrado se les cortaban los pies). A cada cuadro clave con zoom se le suma
    la corrida vertical que deja el borde de abajo quieto; a los del sacudón, encima de esa corrida."""
    zooms = sorted((k["t"], k["zoom"]) for k in kf if "zoom" in k)

    def z_en(t: float) -> float:
        if not zooms:
            return 1.0
        if t <= zooms[0][0]:
            return zooms[0][1]
        for (t0, z0), (t1, z1) in zip(zooms, zooms[1:]):
            if t <= t1:
                return z0 + (z1 - z0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1)
        return zooms[-1][1]

    out = []
    for k in kf:
        k = dict(k)
        ancla = 960 * (1 - 1 / max(1.0, z_en(k["t"])))
        if "zoom" in k or "y" in k:
            k["y"] = round(ancla + float(k.get("y", 0)), 1)
        out.append(k)
    return out


# ---- efectos (Santi, 2026-11-15: "partículas cuando algo se rompe (vidrios, polvo), líneas de movimiento
# cuando algo vuela, destellos en el remate") ------------------------------------------------------------
VEL_LINEAS = 900.0     # px/s desde donde se ven las líneas de movimiento (más rápido = más opacas)


def estela(kfs: list[dict], desde: float | None = None, hasta: float | None = None) -> dict | None:
    """Las líneas de movimiento de algo que vuela: un elemento que sigue los mismos puntos, girado hacia
    donde va, y que se ve solo mientras va rápido. None si no hay trayectoria."""
    pts = [k for k in kfs if "x" in k and "y" in k]
    if len(pts) < 2:
        return None
    out = []
    for a, b in zip(pts, pts[1:]):
        dt = max(1e-3, float(b["t"]) - float(a["t"]))
        dx, dy = float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"])
        v = math.hypot(dx, dy) / dt
        op = max(0.0, min(1.0, (v - VEL_LINEAS * 0.5) / VEL_LINEAS))
        out.append({"t": a["t"], "x": a["x"], "y": a["y"], "rotacion": round(math.degrees(math.atan2(dy, dx)), 1),
                    "opacidad": round(op, 2), "easing": "lineal"})
    ult = pts[-1]
    out.append({"t": ult["t"], "x": ult["x"], "y": ult["y"], "opacidad": 0.0, "easing": "lineal"})
    el = {"tipo": "prop", "nombre": "lineas_mov", "x": out[0]["x"], "y": out[0]["y"], "escala": 0.8,
          "desde": round(desde if desde is not None else float(pts[0]["t"]), 3), "keyframes": out}
    if hasta is not None:
        el["hasta"] = round(hasta, 3)
    return el


def polvo(x: float, y: float, t: float, rnd, n_: int = 4, color: str = "#d9c7a8") -> list[dict]:
    """Nubes de polvo que salen del golpe, crecen y se desvanecen (0,7 s)."""
    out = []
    for i in range(n_):
        ang = rnd.uniform(-math.pi, 0)
        dist = rnd.uniform(70, 150)
        out.append({"tipo": "prop", "nombre": "polvo", "color": color, "x": x, "y": y, "escala": 0.3,
                    "desde": round(t, 3), "hasta": round(t + 0.72, 3),
                    "keyframes": [{"t": t, "x": x, "y": y, "escala": 0.3, "opacidad": 0.9},
                                  {"t": t + 0.7, "x": round(x + math.cos(ang) * dist, 1),
                                   "y": round(y + math.sin(ang) * dist * 0.6, 1), "escala": rnd.uniform(1.0, 1.5),
                                   "opacidad": 0.0, "easing": "salida"}]})
    return out


def destellos(t: float, rnd, centro: tuple[float, float] = (540, 1000), n_: int = 4) -> list[dict]:
    """Destellos que brillan alrededor de lo importante (el remate): aparecen con un pop, giran y se van."""
    out = []
    for i in range(n_):
        x = centro[0] + rnd.uniform(-330, 330)
        y = max(BANDA_SUBTITULOS + 120, centro[1] + rnd.uniform(-360, 160))
        ti = t + i * 0.13
        e = rnd.uniform(0.45, 0.8)
        out.append({"tipo": "prop", "nombre": "destello", "x": round(x, 1), "y": round(y, 1),
                    "color": P.AMARILLO if i % 2 == 0 else "#ffffff",
                    "desde": round(ti, 3), "hasta": round(ti + 0.75, 3),
                    "keyframes": [{"t": ti, "escala": 0.05, "rotacion": 0, "opacidad": 1},
                                  {"t": ti + 0.22, "escala": e, "rotacion": 45, "easing": "rebote"},
                                  {"t": ti + 0.75, "escala": 0.05, "rotacion": 120, "opacidad": 0.2,
                                   "easing": "entrada"}]})
    return out


class Escena:
    """Arma UNA escena: elementos, cámara y SFX (segundos locales a la escena)."""

    def __init__(self, dur: float, semilla: int = 0, fondo: str = "", espejo: bool = False):
        self.dur = dur
        self.fondo = fondo
        self.espejo = espejo
        self.fondo_el: list[dict] = []        # muebles de apoyo (mesa, estante): atrás de todo
        self.elementos: list[dict] = []
        self.sfx: list[tuple[float, str]] = []
        self.golpes: list[tuple[float, float]] = []   # (segundo, fuerza) para el sacudón de cámara
        self.rnd = random.Random(semilla)
        self.mano: tuple[float, float, float] | None = None   # (x, y, t) de un "tirar"
        self.primer_plano_en: tuple[float, float, float] | None = None   # (t, x, y) de la cara en primer plano
        self.actores: list[dict] = []    # el elemento de cada personaje (para lo que llevan en la mano)
        self.anio = 2026                 # la época de la escena (la ropa de cada rol sale de acá)
        self._soportes: set = set()

    # ---- personajes ---------------------------------------------------------------------
    def actor(self, rol: str, accion: str, desde: str = "centro", hacia: str | None = None,
              cara: str = "normal", k: int = 0, x0: float | None = None, x1: float | None = None,
              genero: str = "", edad: str = "") -> None:
        """Un personaje con su acción. Movimiento con peso (Santi, 2026-11-14: "se mueven rígidos"):
        caminar/correr con el CICLO de la base (piernas que se levantan con la rodilla doblada, brazos
        en contrafase, el cuerpo sube y baja con cada paso, la cabeza se balancea), anticipación y
        squash & stretch en saltos y golpes, la cabeza que se inclina y la cara que cambia con la acción.
        `x0`/`x1` (numéricos) los pone el plan de la escena para que nadie se pise."""
        nombre, cambios, escala = aspecto(rol, genero, edad)
        if edad != "chico" and rol not in NINOS:
            cambios = {**cambios, **vestir(rol, getattr(self, "anio", 2026), genero_de(nombre, cambios, genero))}
        # cada rol hace lo suyo: nadie queda quieto con las manos vacías (Santi, 2026-11-17)
        if accion == "quieto" and rol in TRABAJO_ROL:
            accion = "trabajar"
        accion_pedida = accion
        accion = "manipular" if (MANOS_V3 and accion in CON_MANOS) else ALIAS_ACCION.get(accion, accion)
        x0 = _x(desde) if x0 is None else x0
        x1 = (_x(hacia, desde) if hacia and hacia in POS else x0) if x1 is None else x1
        t0 = round(0.05 + 0.18 * k, 2)
        fin = max(t0 + 0.6, self.dur - 0.1)
        el = {"tipo": "personaje", "nombre": nombre, "cambios": cambios, "x": x0, "y": PISO,
              "escala": escala}
        kf: list[dict] = []
        gestos: list[dict] = [{"t": 0, "gesto": "reposo"}]
        caras: list[dict] = []
        if cara in ("feliz", "enojado", "sorprendido", "triste"):
            caras.append({"t": 0, "cara": cara})
        alto = 680 * escala * per_alto(nombre, cambios)
        sentido = 1 if x1 >= x0 else -1

        def respira(desde_t: float, hasta_t: float, amp: float = 3.0) -> None:
            """Un balanceo suave de la cabeza mientras está en su lugar (nadie queda de piedra)."""
            t, s_ = desde_t, 1
            while t < hasta_t:
                kf.append({"t": round(t, 3), "cabeza": amp * s_, "easing": "suave"})
                t += 0.7
                s_ = -s_

        if accion in ("caminar", "entrar", "salir", "correr"):
            corre = accion == "correr"
            if abs(x1 - x0) < 30:
                x1 = x0          # sin lugar para moverse (lo decidió el plan): camina en el lugar un poco
            vel = 950 if corre else 380
            tw = min(fin - t0, max(0.7 if corre else 1.0, abs(x1 - x0) / vel))
            # arranca y frena con easing (un poco de anticipación: se inclina antes de salir)
            kf += [{"t": t0, "x": x0, "rotacion": 0}, {"t": t0 + 0.12, "rotacion": (8 if corre else 3) * sentido},
                   {"t": t0 + tw, "x": x1, "easing": "suave"}, {"t": t0 + tw + 0.2, "rotacion": 0, "easing": "salida"}]
            el["ciclos"] = [{"t0": t0, "t1": round(t0 + tw, 3), "tipo": "correr" if corre else "caminar",
                             "sentido": sentido if x1 != x0 else 0}]
            if corre:
                self.sfx.append((t0, "whoosh"))
                caras.append({"t": t0, "cara": cara if cara != "normal" else "sorprendido"})
            # al frenar, un saltito de squash
            kf += [{"t": t0 + tw, "estirar": 1.0}, {"t": t0 + tw + 0.08, "estirar": 0.9, "easing": "salida"},
                   {"t": t0 + tw + 0.25, "estirar": 1.0, "easing": "rebote"}]
            respira(t0 + tw + 0.3, fin)
        elif accion == "saltar":
            t, saltos = t0 + 0.1, 0
            caras.append({"t": t0, "cara": "risa"})
            while t + 0.9 <= fin + 0.1 and saltos < 3:
                kf += [{"t": t, "y": PISO, "estirar": 1.0},
                       {"t": t + 0.12, "estirar": 0.82, "y": PISO, "easing": "salida"},        # se agacha
                       {"t": t + 0.32, "y": PISO - 230, "estirar": 1.12, "easing": "salida"},   # se estira al subir
                       {"t": t + 0.44, "estirar": 1.0, "cabeza": -6, "easing": "suave"},
                       {"t": t + 0.62, "y": PISO, "easing": "entrada"},
                       {"t": t + 0.7, "estirar": 0.84, "cabeza": 4, "easing": "salida"},          # aterriza aplastado
                       {"t": t + 0.86, "estirar": 1.0, "cabeza": 0, "easing": "rebote"}]
                gestos += [{"t": t + 0.1, "gesto": "festejar"}, {"t": t + 0.72, "gesto": "explicar"}]
                self.sfx.append((t + 0.14, "boing"))
                t += 0.95
                saltos += 1
        elif accion == "caerse":
            tc = t0 + 0.25
            lado = 1 if x0 < 540 else -1
            caras += [{"t": tc - 0.1, "cara": "sorprendido"}, {"t": tc + 0.7, "cara": "triste"}]
            kf += [{"t": tc - 0.1, "rotacion": 0, "y": PISO, "cabeza": 0},
                   {"t": tc, "rotacion": -8 * lado, "cabeza": -10, "easing": "salida"},          # tambalea
                   {"t": tc + 0.12, "y": PISO - 50, "rotacion": 10 * lado, "easing": "salida"},
                   {"t": tc + 0.45, "rotacion": 84 * lado, "y": PISO + 30, "easing": "entrada"},
                   {"t": tc + 0.5, "estirar": 0.88}, {"t": tc + 0.7, "estirar": 1.0, "easing": "rebote"}]
            gestos += [{"t": tc - 0.1, "gesto": "sorpresa"}]
            self.sfx.append((tc + 0.45, "golpe"))
            self.golpes.append((tc + 0.45, 20))
        elif accion == "retar":
            caras += [{"t": t0, "cara": "enojado"}, {"t": t0 + 0.6, "cara": "grito"}, {"t": t0 + 1.4, "cara": "enojado"}]
            gestos += [{"t": t0, "gesto": "retar_a"}] + _alternar("retar_a", "retar_b", t0 + 0.3, fin, 0.24)
            t, s_ = t0, 1
            while t < fin:   # se inclina hacia adelante y mueve la cabeza con cada sacudida del dedo
                kf.append({"t": round(t, 3), "cabeza": 7 * s_, "estirar": 1.0 + 0.03 * s_, "easing": "suave"})
                t += 0.24
                s_ = -s_
        elif accion == "martillar":
            caras.append({"t": t0, "cara": "enojado"})
            gestos += _alternar("martillo_arriba", "martillo_abajo", t0, fin, 0.26)
            mx, my = x0 + 150 * escala, PISO - alto * 0.62
            mk, t, k2 = [], t0, 0
            while t < fin:
                arriba = k2 % 2 == 0
                mk.append({"t": round(t, 3), "rotacion": -40 if arriba else 25, "easing": "entrada" if not arriba else "salida"})
                kf.append({"t": round(t, 3), "estirar": 1.02 if arriba else 0.95, "cabeza": -3 if arriba else 4,
                           "easing": "suave"})
                if not arriba:
                    self.sfx.append((t + 0.12, "tac"))
                t += 0.26
                k2 += 1
            self.elementos.append({"tipo": "prop", "nombre": "martillo", "x": mx, "y": my,
                                   "escala": 0.55 * escala, "keyframes": mk})
        elif accion == "tirar":
            gestos += [{"t": t0, "gesto": "lanzar_atras"}, {"t": t0 + 0.35, "gesto": "lanzar"},
                       {"t": t0 + 1.0, "gesto": "reposo"}]
            kf += [{"t": t0, "estirar": 1.0, "cabeza": 0}, {"t": t0 + 0.3, "estirar": 0.9, "cabeza": -8, "easing": "salida"},
                   {"t": t0 + 0.42, "estirar": 1.08, "cabeza": 6, "easing": "salida"},
                   {"t": t0 + 0.7, "estirar": 1.0, "cabeza": 0, "easing": "suave"}]
            caras += [{"t": t0, "cara": "feliz"}, {"t": t0 + 0.9, "cara": "sorprendido"}]
            self.mano = (x0 + 120 * escala * (1 if x0 <= 540 else -1), PISO - alto * 0.72, t0 + 0.4)
            self.sfx.append((t0 + 0.35, "whoosh"))
        elif accion == "atrapar":
            kf += [{"t": t0 + 0.1, "y": PISO, "estirar": 1.0}, {"t": t0 + 0.2, "estirar": 0.86, "easing": "salida"},
                   {"t": t0 + 0.4, "y": PISO - 70, "estirar": 1.08, "easing": "salida"},
                   {"t": t0 + 0.6, "y": PISO, "estirar": 0.9, "easing": "entrada"},
                   {"t": t0 + 0.75, "estirar": 1.0, "easing": "rebote"}]
            gestos += [{"t": t0 + 0.15, "gesto": "atrapar"}]
            caras += [{"t": t0, "cara": "sorprendido"}, {"t": t0 + 0.6, "cara": "risa"}]
            respira(t0 + 0.8, fin)
        elif accion == "festejar":
            gestos += _alternar("festejar", "sorpresa", t0, fin, 0.32)
            caras.append({"t": t0, "cara": "risa"})
            t = t0
            while t + 0.5 <= fin:
                kf += [{"t": t, "y": PISO, "estirar": 1.0}, {"t": t + 0.08, "estirar": 0.88, "easing": "salida"},
                       {"t": t + 0.25, "y": PISO - 100, "estirar": 1.08, "cabeza": 5, "easing": "salida"},
                       {"t": t + 0.45, "y": PISO, "estirar": 0.9, "cabeza": -5, "easing": "entrada"},
                       {"t": t + 0.55, "estirar": 1.0, "easing": "rebote"}]
                t += 0.65
        elif accion == "asustarse":
            kf += [{"t": t0, "y": PISO, "estirar": 1.0}, {"t": t0 + 0.1, "estirar": 0.86, "easing": "salida"},
                   {"t": t0 + 0.25, "y": PISO - 130, "estirar": 1.18, "cabeza": -10, "easing": "salida"},
                   {"t": t0 + 0.48, "y": PISO, "estirar": 0.9, "easing": "entrada"},
                   {"t": t0 + 0.62, "estirar": 1.0, "easing": "rebote"}]
            kf += [{"t": round(t0 + 0.62 + i * 0.07, 3), "rotacion": (4 if i % 2 else -4)} for i in range(6)]
            kf += [{"t": round(t0 + 1.05, 3), "rotacion": 0, "cabeza": 0}]
            gestos += [{"t": t0 + 0.1, "gesto": "cubrirse"}]
            caras.append({"t": t0, "cara": "sorprendido"})
            self.sfx.append((t0 + 0.1, "boing"))
        elif accion == "pensar":
            gestos += [{"t": t0, "gesto": "pensar"}]
            ding = round(min(fin - 0.3, t0 + 0.8), 2)
            kf += [{"t": t0, "cabeza": 0}, {"t": t0 + 0.5, "cabeza": 9, "easing": "suave"},
                   {"t": ding, "cabeza": 9}, {"t": ding + 0.15, "cabeza": -4, "estirar": 1.06, "easing": "salida"},
                   {"t": ding + 0.35, "cabeza": 0, "estirar": 1.0, "easing": "rebote"}]
            gestos += [{"t": ding, "gesto": "senalar" if x0 < 540 else "senalar_izq"}]
            caras += [{"t": t0, "cara": "normal"}, {"t": ding, "cara": "risa"}]
            self.elementos.append({"tipo": "prop", "nombre": "lamparita", "x": x0,
                                   "y": PISO - alto - 130, "escala": 0.65, "entrada": "rebote", "desde": ding})
            self.sfx.append((ding, "ding"))
        elif accion == "manipular":   # reglas_v3: las manos adelante haciendo algo con el objeto (agarra, abre, llena)
            caras.append({"t": t0, "cara": "feliz" if accion_pedida != "fabricar" else "normal"})
            gestos += _alternar("sostener_a", "sostener_b", t0, fin, 0.38)
            t, s_ = t0, 1
            while t < fin:   # mira lo que tiene en las manos
                kf.append({"t": round(t, 3), "cabeza": 9 + 3 * s_, "estirar": 1.0 - 0.015 * s_, "easing": "suave"})
                t += 0.38
                s_ = -s_
        elif accion == "trabajar":   # el trabajo de su rol, con lo suyo en las manos (TRABAJO_ROL)
            caras.append({"t": t0, "cara": "feliz" if rol in ("cliente", "vendedor", "vendedora") else "normal"})
            gestos += _alternar("sostener_a", "sostener_b", t0, fin, 0.42)
            t, s_ = t0, 1
            while t < fin:   # mira lo que hace y se mueve con el trabajo (el que carga va y viene un poco)
                q = {"t": round(t, 3), "cabeza": 10 + 3 * s_, "estirar": 1.0 - 0.02 * s_, "easing": "suave"}
                if rol in ("obrero", "repartidor", "granjero"):
                    q["x"] = round(x0 + 22 * s_, 1)
                kf.append(q)
                t += 0.6
                s_ = -s_
        elif accion == "fabricar":   # arma con las manos lo que hace (2026-11-15: nada de martillo genérico)
            caras.append({"t": t0, "cara": "normal"})
            gestos += _alternar("atrapar", "explicar", t0, fin, 0.32)
            t, s_ = t0, 1
            while t < fin:   # mira lo que tiene en las manos y se mueve con el trabajo
                kf.append({"t": round(t, 3), "cabeza": 8 + 3 * s_, "estirar": 1.0 - 0.02 * s_, "easing": "suave"})
                t += 0.32
                s_ = -s_
        elif accion == "vender":   # ofrece con entusiasmo: señala y muestra, rebotando sobre los pies
            caras.append({"t": t0, "cara": "feliz"})
            gestos += _alternar("senalar" if x0 < 540 else "senalar_izq", "explicar", t0, fin, 0.45)
            t, s_ = t0, 1
            while t < fin:
                kf.append({"t": round(t, 3), "estirar": 1.0 + 0.04 * s_, "cabeza": 5 * s_, "easing": "suave"})
                t += 0.3
                s_ = -s_
        elif accion == "senalar":
            gestos += [{"t": t0, "gesto": "senalar" if x0 < 540 else "senalar_izq"}]
            kf += [{"t": t0, "estirar": 1.0}, {"t": t0 + 0.15, "estirar": 1.05, "easing": "salida"},
                   {"t": t0 + 0.35, "estirar": 1.0, "easing": "suave"}]
            respira(t0 + 0.4, fin)
        else:   # quieto: igual respira, se balancea y gesticula
            gestos += [{"t": t0, "gesto": "explicar"}]
            respira(t0, fin, 4.0)
        el["keyframes"] = sorted(kf, key=lambda q: q["t"])
        el["gestos"] = gestos
        if accion in ("manipular", "trabajar"):
            el["manos"] = True       # el objeto "en la mano" va en las dos, adelante (Escena.objeto)
        if accion == "trabajar":
            el["objeto_rol"] = TRABAJO_ROL[rol]
        el["rol"] = rol
        self.actores.append(el)
        if caras:
            el["caras"] = [c for c in caras if c["cara"] != "normal"] or caras
        self.elementos.append(el)

    def multitud(self, n: int = 6) -> None:
        """Gente atrás (2026-11-15: "multitudes"): una fila de personas chicas que festejan, caminan o
        saltan, detrás de los personajes principales y más oscuras (lejos de la luz)."""
        roles = [r for r in ROLES if r not in NINOS]
        self.sfx.append((0.15, "aplausos"))     # la gente que festeja se oye (biblioteca de efectos)
        for k in range(n):
            rol = roles[self.rnd.randrange(len(roles))]
            nombre, cambios, escala = ROLES[rol]
            x = 90 + k * (900 / max(1, n - 1)) + self.rnd.uniform(-25, 25)
            accion = ("festejar", "saltar", "caminar")[k % 3]
            gestos, kf = [{"t": 0, "gesto": "reposo"}], []
            t0, t = 0.1 + 0.07 * k, 0.1 + 0.07 * k
            if accion == "festejar":
                gestos += _alternar("festejar", "sorpresa", t0, self.dur, 0.35)
            while t < self.dur:
                dy = -26 if (accion == "saltar" and int((t - t0) / 0.3) % 2 == 0) else 0
                kf.append({"t": round(t, 3), "y": PISO - 150 + dy, "cabeza": 4 if int(t / 0.35) % 2 else -4,
                           "easing": "suave"})
                t += 0.3
            self.fondo_el.append({"tipo": "personaje", "nombre": nombre, "cambios": cambios, "x": round(x, 1),
                                  "y": PISO - 150, "escala": round(escala * 0.5, 3), "gestos": gestos,
                                  "keyframes": kf, "multitud": True, "opacidad": 0.92})

    # ---- objetos --------------------------------------------------------------------------
    def _apoyo(self, soporte: str, x: float) -> None:
        """La mesita o el estante debajo de un objeto (una sola vez por lugar)."""
        if soporte not in ("mesa", "estante") or (soporte, x) in self._soportes:
            return
        self._soportes.add((soporte, x))
        self.fondo_el.append({"tipo": "prop", "nombre": soporte, "x": x, "mueble": True,
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
        x, y = ubicar(prop, sop, donde, self.fondo, self.espejo)
        self._apoyo(sop, x)
        base = {"tipo": "prop", "nombre": prop, "x": x, "y": y}
        if sop == "mano" and self.actores and efecto in ("quieto", "gira"):
            # en la mano del primero que aparece (o del que lo está manipulando): a la altura de la mano y siguiéndolo
            quien = next((a for a in self.actores if a.get("manos") and not a.get("lleva")
                          and not a.get("objeto_rol")),
                         next((a for a in self.actores if a.get("manos") and not a.get("lleva")), self.actores[0]))
            quien["lleva"] = prop
            esc_ = float(quien.get("escala", 1))
            lado = 1 if float(quien["x"]) <= 540 else -1
            off = 125 * esc_ * lado
            y = PISO - 330 * esc_
            if quien.get("manos"):   # reglas_v3: en las dos manos, delante del cuerpo
                off, y = 0.0, PISO - 300 * esc_
            kx = [{"t": k["t"], "x": round(float(k["x"]) + off, 1), "easing": k.get("easing", "suave")}
                  for k in quien.get("keyframes", []) if "x" in k]
            # lo voluminoso (una caja) se lleva a la altura de la panza y más chico: si no, le tapa la cara
            esc_mano = 0.42 if prop in ("caja", "bolsa_plata", "caja_registradora") else 0.55
            self.elementos.append({**base, "x": float(quien["x"]) + off, "y": y, "escala": esc_mano,
                                   "keyframes": kx, "en_mano": True})
            return None
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
                self.elementos.append({**base, "x": xi, "y": BANDA_SUBTITULOS + 60, "escala": 0.55,
                                       "desde": round(ti, 2),
                                       "keyframes": [{"t": ti, "y": BANDA_SUBTITULOS + 60, "rotacion": 0, "opacidad": 0},
                                                     {"t": ti + 0.15, "opacidad": 1},
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
            arco = _arco(ox, oy, dx, dy, tt, dur, 380, 540)
            lin = estela(arco, tt, tt + dur)
            if lin:
                self.elementos.append(lin)
            self.elementos.append({**base, "x": ox, "y": oy, "escala": 0.8, "desde": round(tt, 2),
                                   "hasta": round(tt + dur + (0.02 if blanco else 0.6), 2),
                                   "keyframes": arco})
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
            lin = estela(pts, tt)
            if lin:
                self.elementos.append(lin)
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
            x, y = ubicar(prop, sop, o.get("donde") or LADOS[k % 3], self.fondo, self.espejo)
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
            lin = estela(pts)
            if lin:
                self.elementos.append(lin)
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
        self.elementos += polvo(x, y, t, self.rnd, 3 if prop in ROMPIBLES_VIDRIO else 5)
        self.sfx.append((round(t, 3), "vidrio" if prop in ROMPIBLES_VIDRIO else "golpe"))
        self.golpes.append((t, fuerza))

    # ---- cámara -----------------------------------------------------------------------------
    def cara_de(self, el: dict, t: float) -> tuple[float, float]:
        """(x, y) en pantalla (sin cámara) de la cara del personaje `el` en el segundo `t`."""
        from . import personajes as per

        x = float(el["x"])
        for k in sorted(el.get("keyframes", []), key=lambda k: float(k["t"])):
            if "x" in k and float(k["t"]) <= t:
                x = float(k["x"])
        pj = per.personaje(el.get("nombre", "narrador"), **(el.get("cambios") or {}))
        _cx, cy, _r = pj.cara()
        return x, PISO + float(el.get("escala", 1)) * cy

    def camara(self, tipo: str, fuerte: bool = False, plano: str | None = None) -> list[dict]:
        """Zoom suave siempre (nada queda quieto), paneo, temblor en los golpes, cambio de plano a la mitad
        y, en los momentos FUERTES (el gancho, el giro, el final, una cara de sorpresa o enojo), un
        PRIMER PLANO de la cara del protagonista justo después del golpe (Santi, 2026-11-15)."""
        d = self.dur
        golpes = sorted(self.golpes) or ([(d * 0.5, 22)] if tipo == "sacudon" else [])
        z0, z1 = {"acercar": (1.0, 1.14), "alejar": (1.16, 1.02), "paneo": (1.18, 1.18),
                  "sacudon": (1.08, 1.12)}.get(tipo, (1.02, 1.09))
        if golpes:
            z0, z1 = max(z0, 1.06), max(z1, 1.06)
        # más movimiento (visuales, 2026-11-15): de cerca, de lejos o desde abajo, rotando entre escenas
        if plano == "cerca":
            z0, z1 = 1.12, 1.38
        elif plano == "lejos":
            z0, z1 = 1.32, 1.02
        kf = [{"t": 0, "zoom": z0}, {"t": d, "zoom": z1, "easing": "suave"}]
        if plano == "contrapicado":   # desde abajo: cerca del piso, mirando hacia arriba, con un leve giro
            kf = [{"t": 0, "zoom": 1.26, "y": 90, "rotacion": -2.5}, {"t": d, "zoom": 1.18, "y": 30, "rotacion": 1.5,
                                                                      "easing": "suave"}]
        if tipo == "paneo":
            kf += [{"t": 0, "x": -70}, {"t": d, "x": 70, "easing": "suave"}]
        # cambio de plano (Santi: "medio lento"): en las escenas de más de 2,6 s, a la mitad la cámara
        # salta a un plano más cerrado sobre el primer personaje (corte seco, sin reiniciar la acción)
        # El plano nuevo encuadra a TODOS los personajes (más cerrado si son pocos o están juntos):
        # nunca corta a uno por la mitad.
        xs = []
        for el in self.actores:
            xs += [float(k["x"]) for k in el.get("keyframes", []) if "x" in k] or [float(el["x"])]
        z_corte = 1.0
        if xs:
            medio = (max(xs) - min(xs)) / 2 + 150
            z_corte = min(1.24, 540 / max(1.0, medio))
        primer = self._primer_plano(golpes, fuerte, z0, z1)
        if primer:
            kf += primer
        elif d > 2.6 and tipo != "paneo" and z_corte >= 1.08 and not any(tg > d * 0.45 for tg, _ in golpes):
            tc = round(d * 0.5, 3)
            dx = (max(xs) + min(xs)) / 2 - 540
            mx = 540 * (1 - 1 / z_corte)
            dx = max(-mx, min(mx, dx))
            kf += [{"t": round(tc - 0.01, 3), "zoom": round(z0 + (z1 - z0) * 0.5, 3), "x": 0},
                   {"t": tc, "zoom": round(z_corte, 3), "x": round(dx, 1), "easing": "escalon"},
                   {"t": d, "zoom": round(z_corte + 0.03, 3), "x": round(dx, 1), "easing": "suave"}]
            kf = [k for k in kf if not (k["t"] == d and k.get("zoom") == z1)]
        ultimo = -1.0
        pp = self.primer_plano_en
        for tg, fuerza in golpes[:4]:   # sacudón: 0,35 s de corridas cortas que se apagan
            if tg - ultimo < 0.3:
                continue
            if pp and pp[0] - 0.33 <= tg <= pp[0] + self.DUR_CARA:   # en el primer plano no se sacude
                continue
            ultimo = tg
            for i in range(6):
                a = fuerza * (1 - i / 6)
                kf.append({"t": round(tg + i * 0.05, 3), "x": round(a * (1 if i % 2 else -1), 1),
                           "y": round(a * 0.6 * (1 if i % 3 else -1), 1),
                           "rotacion": round(0.08 * a * (1 if i % 2 else -1), 2), "easing": "lineal"})
            kf.append({"t": round(tg + 0.32, 3), "x": 0, "y": 0, "rotacion": 0, "easing": "suave"})
        kf = sorted(kf, key=lambda k: float(k["t"]))
        out = anclar_abajo([k for k in kf if not k.get("_cara")], d)
        # el primer plano ya trae su corrida vertical exacta: no se ancla abajo
        out += [{k_: v for k_, v in k.items() if k_ != "_cara"} for k in kf if k.get("_cara")]
        return sorted(out, key=lambda k: float(k["t"]))

    ZOOM_CARA = 1.9
    DUR_CARA = 0.8

    def _primer_plano(self, golpes, fuerte: bool, z0: float, z1: float) -> list[dict]:
        """Corte a un primer plano de la cara (con un empujón suave) y vuelta al plano general."""
        self.primer_plano_en = None
        if not fuerte or not self.actores or self.dur < 1.6:
            return []
        limite = self.dur - self.DUR_CARA - 0.15
        # justo después del último golpe que deja lugar (la reacción); si ninguno deja, lo antes posible
        despues = [tg + 0.36 for tg, _ in golpes if tg + 0.36 <= limite]
        tc = max(despues) if despues else (min(limite, self.dur * 0.42) if not golpes else limite)
        tc = round(tc, 3)
        if tc < 0.3:
            return []
        el = self.actores[0]
        X, Y = self.cara_de(el, tc)
        out = []
        cx, cy = P.ANCHO / 2, P.ALTO / 2
        zs = (self.ZOOM_CARA, self.ZOOM_CARA + 0.08)
        for t_, z in ((tc, zs[0]), (tc + self.DUR_CARA, zs[1])):
            mx, my = cx * (1 - 1 / z), cy * (1 - 1 / z)
            dx = max(-mx, min(mx, X - cx))
            dy = max(-my, min(my, Y - cy - (0.44 * P.ALTO - cy) / z))
            out.append({"t": round(t_, 3), "zoom": round(z, 3), "x": round(dx, 1), "y": round(dy, 1),
                        "rotacion": 0, "easing": "escalon" if t_ == tc else "suave", "_cara": True})
        self.primer_plano_en = (tc, X, Y)
        zm = z0 + (z1 - z0) * (tc / self.dur)
        antes = {"t": round(tc - 0.01, 3), "zoom": round(zm, 3), "x": 0, "rotacion": 0}
        zf = z0 + (z1 - z0) * min(1.0, (tc + self.DUR_CARA + 0.01) / self.dur)
        despues = {"t": round(tc + self.DUR_CARA + 0.01, 3), "zoom": round(zf, 3), "x": 0, "y": 0,
                   "rotacion": 0, "easing": "escalon"}
        return [antes] + out + [despues]


# ---- lugares: nunca un personaje encima de otro (Santi, 2026-11-14) ------------------------------
MARGEN = 30                 # px libres entre dos personajes
ANCHO_MEDIO = 150           # medio ancho de un personaje a escala 1 (torso + brazos levantados)
X_TITO = {"izquierda": 150.0, "derecha": 930.0}     # pegado al borde, para no tapar a nadie
ESCALA_TITO = 0.55
ANCHO_MEDIO_TITO = 175      # Tito a escala 0,55 con el reloj levantado (medido sobre el dibujo)


def medio_ancho(rol: str) -> float:
    return ANCHO_MEDIO * ROLES.get(rol, ROLES["joven"])[2]


def planear(actores: list[dict], reservar: str | None = None) -> list[dict]:
    """Le da a cada actor su lugar (x0 → x1) para que en NINGÚN cuadro dos se pisen: cada uno en su
    carril; quien camina o corre lo hace sin cruzar a los demás (si no hay lugar, el recorrido se
    acorta); quien entra o sale lo hace por el costado libre. `reservar` = el costado donde va a
    aparecer Tito en la pausa que sigue: ahí no termina nadie (si son 3, queda afuera el último)."""
    carriles = [l for l in LADOS if l != reservar]
    actores = list(actores)[:len(carriles)]
    usados: dict[str, dict] = {}
    for a in actores:   # carril de cada uno: el que pidió (si está libre) o el libre más cercano
        quiere = a.get("desde") if a.get("desde") in LADOS else (a.get("hacia") if a.get("hacia") in LADOS else "centro")
        libres = [l for l in carriles if l not in usados]
        lado = quiere if quiere in libres else min(libres, key=lambda l: abs(POS[l] - POS.get(quiere, 540)))
        usados[lado] = a
    plan = []
    obstaculos: list[tuple[float, float, float]] = []   # (desde x, hasta x, medio ancho)
    if reservar in X_TITO:
        obstaculos.append((X_TITO[reservar], X_TITO[reservar], ANCHO_MEDIO_TITO))
    quietos = {l: a for l, a in usados.items() if a.get("accion") not in ("caminar", "correr", "entrar", "salir")}
    moviles = {l: a for l, a in usados.items() if l not in quietos}
    for lado, a in quietos.items():
        x = float(POS[lado])
        plan.append({**a, "x0": x, "x1": x, "carril": lado})
        obstaculos.append((x, x, medio_ancho(a.get("rol"))))
    planeados: dict[str, tuple[float, float, float]] = {}
    for lado, a in moviles.items():
        hw = medio_ancho(a.get("rol"))
        casa = float(POS[lado])
        izq_lim, der_lim = -10_000.0, 10_000.0
        # los otros que se mueven: su recorrido si ya está planeado; si no, su lugar de partida
        otros = [planeados.get(l, (float(POS[l]), float(POS[l]), medio_ancho(o.get("rol"))))
                 for l, o in moviles.items() if l != lado]
        for o0, o1, ohw in obstaculos + otros:
            lo, hi = min(o0, o1), max(o0, o1)
            if hi <= casa:
                izq_lim = max(izq_lim, hi + ohw + hw + MARGEN)
            elif lo >= casa:
                der_lim = min(der_lim, lo - ohw - hw - MARGEN)
        acc = a.get("accion")
        if acc in ("entrar", "salir"):
            afuera_izq, afuera_der = float(POS["afuera_izq"]), float(POS["afuera_der"])
            puede_izq, puede_der = izq_lim <= afuera_izq + 1, der_lim >= afuera_der - 1
            if not (puede_izq or puede_der):     # sin camino libre: camina un poco en su carril
                acc, x0, x1 = "caminar", casa, casa
            else:
                borde = afuera_izq if (puede_izq and (not puede_der or casa <= 540)) else afuera_der
                x0, x1 = (borde, casa) if acc == "entrar" else (casa, borde)
        else:
            destino = float(POS[a["hacia"]]) if a.get("hacia") in POS else casa + (160 if casa <= 540 else -160)
            x0, x1 = casa, max(izq_lim, min(der_lim, destino))
            if izq_lim > der_lim:
                x1 = casa
        plan.append({**a, "accion": acc, "x0": x0, "x1": x1, "carril": lado})
        planeados[lado] = (x0, x1, hw)
    return plan


def superposiciones(esc_d: dict, paso: float = 0.1, margen: float = 0.0) -> list[tuple[float, int, int]]:
    """(segundo, i, j) de cada par de personajes (o Tito) que se pisan en la escena (cajas horizontales
    de medio ancho ANCHO_MEDIO × escala, con `margen`). Vacío = nadie encima de nadie."""
    from .timeline import Elemento

    personas = []
    for k, d in enumerate(esc_d.get("elementos") or []):
        if d.get("tipo") in ("personaje", "tito") and not d.get("multitud"):
            el = Elemento.desde_dict(d, f"elemento {k}", esc_d["duracion"])
            hw = (ANCHO_MEDIO_TITO / ESCALA_TITO if d["tipo"] == "tito" else ANCHO_MEDIO) * float(d.get("escala", 1))
            personas.append((k, el, hw))
    out = []
    t = 0.0
    while t <= esc_d["duracion"]:
        xs = [(k, el.pista.valor("x", t, el.base["x"]), hw) for k, el, hw in personas if el.visible(t)]
        for a in range(len(xs)):
            for b in range(a + 1, len(xs)):
                if abs(xs[a][1] - xs[b][1]) < xs[a][2] + xs[b][2] + margen:
                    out.append((round(t, 2), xs[a][0], xs[b][0]))
        t += paso
    return out


def posiciones_finales(esc_d: dict) -> list[tuple[float, float]]:
    """(x, medio ancho) de cada personaje al final de la escena (lo que queda congelado en la pausa)."""
    from .timeline import Elemento

    out = []
    for k, d in enumerate(esc_d.get("elementos") or []):
        if d.get("tipo") == "personaje" and not d.get("multitud"):     # la gente del fondo no cuenta
            el = Elemento.desde_dict(d, f"elemento {k}", esc_d["duracion"])
            out.append((el.pista.valor("x", esc_d["duracion"], el.base["x"]), ANCHO_MEDIO * float(d.get("escala", 1))))
    return out


# Caja de cada prop a escala 1: (medio ancho, arriba, abajo) respecto de su origen. Medido sobre los
# dibujos de escenas.py (los muebles grandes tienen su caja real: la mesa es 300 × 226).
CAJAS = {"mesa": (150, 0, 226), "estante": (140, 0, 70), "lampara": (110, -150, 187), "tele": (150, -190, 130),
         "cuadro": (130, -150, 90), "ventana": (170, -200, 200), "jarron": (100, -120, 120),
         "botella": (80, -262, 230), "lata": (80, -170, 150), "caja": (140, -180, 170), "pelota": (70, -70, 70),
         "pelota_espuma": (78, -78, 78), "juego_mesa": (170, -90, 90), "hamburguesa": (130, -90, 130),
         "chocolate": (160, -80, 80), "galletitas": (100, -70, 70), "auto": (180, -100, 72),
         "telefono_disco": (120, -90, 60), "radio": (130, -90, 90), "consola": (150, -40, 170),
         "trofeo": (160, -150, 150), "celular": (95, -180, 180), "zapatilla": (180, -90, 104),
         "control": (190, -110, 130), "camion": (200, -110, 86), "cohete": (120, -200, 150),
         "martillo": (70, -90, 160), "lamparita": (90, -200, 140), "grafico_sube": (190, -170, 150),
         "grafico_baja": (190, -170, 150), "cartel": (190, -140, 230), "calendario": (130, -144, 130)}
NO_CHOCAN = {"pedazo", "lamparita", "gancho", "nube", "martillo", "pregunta", "exclamacion", "flecha", "idea_fallida",
             "polvo", "lineas_mov", "destello", "primer_plano", "rotulo", "dato", "cita", "cartel_comic", "tito_reaccion",
             "mano", "mostrador", "fuego"}


def _en_mundo(el, t: float):
    """(x, y, escala, dy, estado) de un personaje en `t` (sin la rotación: un caído no cuenta)."""
    v = {k: el.pista.valor(k, t, el.base[k]) for k in ("x", "y", "escala", "mirada", "cabeza", "rotacion")}
    est, dy = el._estado(t, 0.0, 0, v["mirada"], v["cabeza"])
    return v, dy, est


def _dist_segmento(px, py, a, b) -> float:
    (x1, y1), (x2, y2) = a, b
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + u * dx), py - (y1 + u * dy))


def composicion(esc_d: dict, paso: float = 0.1) -> list[tuple[float, str, int, int]]:
    """Lo que está MAL compuesto en la escena, cuadro a cuadro (Santi, 2026-11-14): (segundo, qué,
    elemento a, elemento b). Qué:
      "brazo_en_cara"   el brazo (o la mano) de un personaje atraviesa la cara de otro;
      "objeto_en_cara"  un objeto quieto (apoyado) queda sobre la cara o el sombrero de alguien;
      "mueble_en_medio" una mesa o un estante en el medio de la escena;
      "franja"          algo de la escena sube a la franja de los subtítulos.
    Vacío = la escena está bien compuesta."""
    from .timeline import Elemento

    dur = esc_d["duracion"]
    personas, cosas = [], []
    for k, d in enumerate(esc_d.get("elementos") or []):
        if d.get("tipo") == "personaje" and not d.get("multitud"):
            personas.append((k, Elemento.desde_dict(d, f"elemento {k}", dur)))
        elif d.get("tipo") == "prop" and not d.get("lib"):
            cosas.append((k, d, Elemento.desde_dict(d, f"elemento {k}", dur)))
        # la mesa del trato o del uso va en el medio a propósito (`en_medio`, 2026-11-16)
        if d.get("tipo") == "prop" and d.get("nombre") in ("mesa", "estante") and 330 < float(d.get("x", 0)) < 750 \
                and not d.get("en_medio"):
            return [(0.0, "mueble_en_medio", k, -1)]
    out, vistos = [], set()
    t = 0.0
    while t <= dur:
        caras, brazos, cuerpos_altos = [], [], []
        for k, el in personas:
            if not el.visible(t):
                continue
            v, dy, est = _en_mundo(el, t)
            if abs(v["rotacion"]) > 40:          # tirado en el piso: no cuenta
                continue
            pj, e_ = el._pj, v["escala"]
            cx, cy, R = pj.cara(est)
            X, Y = v["x"] + e_ * cx, v["y"] + dy + e_ * cy
            caras.append((k, X, Y, R * e_, e_ * pj.alto_sombrero()))
            brazos.append((k, [[(v["x"] + e_ * px, v["y"] + dy + e_ * py) for px, py in pl] for pl in pj.brazos(est)]))
            cuerpos_altos.append((k, Y - R * e_ - e_ * pj.alto_sombrero()))
        for k, pls in brazos:
            for k2, X, Y, R, _ in caras:
                if k2 == k:
                    continue
                if any(_dist_segmento(X, Y, a, b) < R * 0.85 for pl in pls for a, b in zip(pl, pl[1:])):
                    clave = ("brazo_en_cara", k, k2)
                    if clave not in vistos:
                        vistos.add(clave)
                        out.append((round(t, 2), *clave))
        for k, top in cuerpos_altos:
            if top < BANDA_SUBTITULOS and ("franja", k, -1) not in vistos:
                vistos.add(("franja", k, -1))
                out.append((round(t, 2), "franja", k, -1))
        for k, d, el in cosas:
            if not el.visible(t) or d.get("nombre") in NO_CHOCAN:
                continue
            x = el.pista.valor("x", t, el.base["x"])
            y = el.pista.valor("y", t, el.base["y"])
            e_ = el.pista.valor("escala", t, el.base["escala"])
            if el.pista.valor("opacidad", t, 1.0) < 0.2:
                continue
            hw, arriba, abajo = CAJAS.get(d.get("nombre"), (100, -100, 100))
            x0, x1, y0, y1 = x - hw * e_, x + hw * e_, y + arriba * e_, y + abajo * e_
            if y0 < BANDA_SUBTITULOS and ("franja", k, -1) not in vistos:
                vistos.add(("franja", k, -1))
                out.append((round(t, 2), "franja", k, -1))
            quieto = not any(("x" in q or "y" in q) for q in d.get("keyframes", [])) or d.get("en_mano")
            if not quieto or d.get("mueble"):
                continue
            for k2, X, Y, R, som in caras:   # la caja del objeto contra la cara + el sombrero
                cerca_x = max(x0, min(X, x1))
                cerca_y = max(y0, min(Y, y1))
                toca_cara = math.hypot(X - cerca_x, Y - cerca_y) < R * 0.9
                toca_sombrero = som and x0 < X + R * 0.6 and x1 > X - R * 0.6 and y0 < Y - R and y1 > Y - R - som
                if (toca_cara or toca_sombrero) and ("objeto_en_cara", k, k2) not in vistos:
                    vistos.add(("objeto_en_cara", k, k2))
                    out.append((round(t, 2), "objeto_en_cara", k, k2))
        t += paso
    return out


GESTOS_QUE_ALCANZAN = {"senalar", "senalar_izq", "lanzar", "lanzar_atras", "atrapar", "saludar"}


def arreglar_composicion(esc_d: dict, vueltas: int = 3) -> list[tuple[float, str, int, int]]:
    """Corrige lo que marca `composicion` en el lugar: el gesto que mete el brazo en la cara de otro
    pasa a "explicar"; un objeto sobre una cara se sube a un estante (o se saca si no hay dónde); lo
    que sube a la franja de los subtítulos se baja. Devuelve lo que quede mal (vacío = bien)."""
    for _ in range(vueltas):
        malos = composicion(esc_d)
        if not malos:
            return []
        els = esc_d["elementos"]
        sacar = set()
        for _t, que, a, b in malos:
            if que == "brazo_en_cara":
                el = els[a]
                el["gestos"] = [{**gs, "gesto": "explicar"} if gs.get("gesto") in GESTOS_QUE_ALCANZAN else gs
                                for gs in el.get("gestos", [])]
                if all(gs.get("gesto") not in GESTOS_QUE_ALCANZAN for gs in el["gestos"]):
                    # sigue tocando: los brazos quietos al costado del cuerpo
                    el["gestos"] = [{"t": 0, "gesto": "reposo"}]
            elif que == "objeto_en_cara":
                d = els[a]
                if d.get("en_mano") or d.get("y", 0) <= Y_ESTANTE:
                    sacar.add(a)
                else:   # al estante del costado, arriba de las cabezas
                    d["x"] = X_MUEBLE["derecha"] if float(d["x"]) >= 540 else X_MUEBLE["izquierda"]
                    d["y"] = Y_ESTANTE - ALTO_BASE.get(d.get("nombre"), 120) * 0.75
                    els.append({"tipo": "prop", "nombre": "estante", "x": d["x"], "y": Y_ESTANTE, "mueble": True})
            elif que == "franja":
                d = els[a]
                if d.get("tipo") == "prop":
                    d["y"] = max(float(d.get("y", 0)), BANDA_SUBTITULOS + 200)
                    for kf in d.get("keyframes", []):
                        if "y" in kf:
                            kf["y"] = max(float(kf["y"]), BANDA_SUBTITULOS + 200)
            elif que == "mueble_en_medio":
                els[a]["x"] = X_MUEBLE["derecha"]
        if sacar:
            esc_d["elementos"] = [el for i, el in enumerate(els) if i not in sacar]
        # los muebles siempre atrás de todo
        esc_d["elementos"].sort(key=lambda el: 0 if el.get("mueble") else 1)
    return composicion(esc_d)


def per_alto(nombre: str, cambios: dict) -> float:
    from . import personajes as per

    return float(cambios.get("alto_cuerpo", per.ELENCO.get(nombre, per.ELENCO["narrador"]).alto_cuerpo))


def es_dinamica(spec: dict) -> bool:
    """¿La escena muestra algo que pasa? (no "dos personajes hablando")."""
    from . import escenas_lib as _lib

    if (spec.get("accion_escena") or "") in _lib.ACCIONES:     # las de la biblioteca ya traen su acción
        return True
    return bool(spec.get("cadena")) or bool(spec.get("multitud")) or \
        any(a.get("accion") in MOVIMIENTO for a in spec.get("actores") or []) or \
        any(o.get("efecto") in DINAMICOS for o in spec.get("objetos") or [])


LANZABLES = {"pelota", "pelota_espuma", "zapatilla", "lata", "botella", "caja", "hamburguesa", "galletitas",
             "chocolate", "control", "celular", "moneda"}


def semilla_fondo(anio: int, variante: int) -> int:
    """La semilla del fondo: década*100 + variante (1969 → 19600 + v): la decoración de la época y,
    con variante impar, el lugar espejado (otro ángulo)."""
    return (int(anio) // 10) * 100 + int(variante) % 100


TRANSICIONES_OK = ("corte", "fundido", "zoom", "barrido", "iris")


PLANOS = ("cerca", "lejos", "contrapicado")


def elementos_visuales(vis: dict, dur: float, golpes: list[float], primera: bool) -> tuple[list[dict], list]:
    """Los elementos de "más visual" de una escena (fijos, en coordenadas de pantalla) y sus sonidos."""
    els, sfx = [], []
    if vis.get("rotulo"):
        t0 = 0.15
        els.append({"tipo": "prop", "nombre": "rotulo", "texto": vis["rotulo"], "fijo": True, "x": 40, "y": 330,
                    "escala": 1.3,
                    "desde": t0, "hasta": round(min(dur, t0 + 2.4), 2),
                    "keyframes": [{"t": t0, "x": -700}, {"t": t0 + 0.3, "x": 40, "easing": "salida"},
                                  {"t": min(dur, t0 + 2.1), "x": 40}, {"t": min(dur, t0 + 2.4), "x": -700, "easing": "entrada"}]})
        sfx.append((t0, "whoosh"))
    centro = [x for x in ("dato", "cita") if vis.get(x)]
    if centro:
        k = centro[0]
        t0 = round(min(dur * 0.35, max(0.3, dur - 1.6)), 2)
        y = 760 if k == "dato" else 380
        els.append({"tipo": "prop", "nombre": k, "texto": vis[k], "fijo": True, "x": 540, "y": y, "entrada": "rebote",
                    "desde": t0, "hasta": round(min(dur, t0 + 1.9), 2)})
        sfx.append((t0, "pop"))
    if vis.get("cartel"):
        tc = round(golpes[0] if golpes else min(dur * 0.4, max(0.2, dur - 1.0)), 2)
        els.append({"tipo": "prop", "nombre": "cartel_comic", "texto": vis["cartel"], "fijo": True, "x": 760, "y": 640,
                    "rotacion": -8, "desde": tc, "hasta": round(min(dur, tc + 0.9), 2),
                    "keyframes": [{"t": tc, "escala": 0.1}, {"t": tc + 0.18, "escala": 0.7, "easing": "rebote"},
                                  {"t": tc + 0.8, "escala": 0.75}, {"t": tc + 0.9, "escala": 0.05, "easing": "entrada"}]})
        sfx.append((tc, "golpe"))
    return els, sfx


def dejar_lugar_a_tito(elementos: list[dict], lado: str) -> None:
    """En una escena de la biblioteca que sigue con la pausa de Tito: los personajes terminan (en orden, sin
    pisarse) en la parte de la pantalla que Tito no ocupa; si no entran todos, se van los del lado de Tito.
    Cada uno se corre entero (su caminata también), así no cambia cómo se mueve."""
    # los que se van antes del final (el plano medio del apretón) no están cuando entra Tito: no se tocan (correrlos
    # por separado los alejaba de su mesa y sus manos no se juntaban, 2026-11-16)
    pj = [el for el in elementos if el.get("tipo") == "personaje" and not el.get("multitud") and "hasta" not in el]
    if not pj:
        return

    def final(el: dict) -> float:
        xs = [float(k["x"]) for k in sorted(el.get("keyframes", []), key=lambda k: float(k["t"])) if "x" in k]
        return xs[-1] if xs else float(el["x"])

    hw = max(ANCHO_MEDIO * float(el.get("escala", 1)) for el in pj)
    margen = ANCHO_MEDIO_TITO + hw + MARGEN
    lo, hi = (X_TITO["izquierda"] + margen, 1000.0) if lado == "izquierda" else (80.0, X_TITO["derecha"] - margen)
    paso = 2 * hw + MARGEN
    entran = max(1, int((hi - lo) // paso) + 1)
    pj.sort(key=final)
    if len(pj) > entran:
        sacar = pj[:len(pj) - entran] if lado == "izquierda" else pj[entran:]
        ids = {id(el) for el in sacar}
        elementos[:] = [el for el in elementos if id(el) not in ids]
        pj = [el for el in pj if id(el) not in ids]
    finales = [final(el) for el in pj]
    if all(lo <= x <= hi for x in finales) and all(b - a >= paso for a, b in zip(finales, finales[1:])):
        return
    ancho = paso * (len(pj) - 1)
    inicio = lo + max(0.0, (hi - lo - ancho) / 2)
    for k, el in enumerate(pj):
        delta = inicio + k * paso - finales[k]
        el["x"] = round(float(el["x"]) + delta, 1)
        for kf in el.get("keyframes", []):
            if "x" in kf:
                kf["x"] = round(float(kf["x"]) + delta, 1)


def escena_accion(spec: dict, dur: float, i: int, primera: bool = False, tono: float = 0.0,
                  anio: int = 2026, variante: int = 0, reservar: str | None = None,
                  proyectil: str = "pelota", visual: dict | None = None,
                  protagonista: str = "") -> tuple[dict, list[tuple[float, str]]]:
    """Una escena del guion → (dict de timeline.Escena, [(segundo local, sfx)]). `anio` y `variante`
    eligen la decoración del fondo; `reservar` deja libre el costado de Tito si después viene la pausa;
    `proyectil` es lo que se tira en la cadena (el protagonista, si se puede tirar)."""
    from . import escenas as _esc

    from . import escenas_lib as lib_

    fondo = spec.get("fondo") or "ciudad"
    semilla = semilla_fondo(anio, variante)
    # Biblioteca de escenas (Santi, 2026-11-15: "cada frase muestra la acción concreta que dice la voz"): la
    # acción de la escena con su plano; las recetas guardadas se arman como una escena del guion.
    accion_ = str(spec.get("accion_escena") or "")
    if accion_ in lib_.recetas() and accion_ not in lib_.ACCIONES:
        spec = lib_.aplicar_receta(accion_, spec, protagonista)
    hecha = lib_.construir(accion_, str(spec.get("plano") or ""), spec, dur, i, protagonista) \
        if accion_ in lib_.ACCIONES else None
    if hecha and hecha.get("fondo"):
        fondo = hecha["fondo"]
    e = Escena(dur, semilla=i + 1, fondo=fondo, espejo=_esc.espejado(semilla))
    e.anio = int(anio or 2026)
    if spec.get("multitud") or (hecha and hecha.get("multitud")):
        e.multitud()
    if hecha:
        for el in hecha["elementos"]:
            if el.get("tipo") == "prop":
                el["lib"] = True
        if reservar in X_TITO:
            dejar_lugar_a_tito(hecha["elementos"], reservar)
        e.elementos += hecha["elementos"]
        e.sfx += hecha["sfx"]
        e.actores += hecha["actores"]
    for k, a in enumerate(planear([] if hecha else (spec.get("actores") or []), reservar)):
        e.actor(a.get("rol") or "joven", a.get("accion") or "quieto", a["carril"], a.get("hacia"),
                a.get("cara") or "normal", k, x0=a["x0"], x1=a["x1"], genero=a.get("genero") or "",
                edad=a.get("edad") or "")
    colores = (P.NARANJA, P.AZUL, P.ROJO, P.VERDE, P.VIOLETA)
    # Época (Santi, 2026-11-16): ningún objeto aparece antes del año en que existe (el protagonista, siempre).
    def _de_epoca(nombre: str) -> bool:
        return nombre == protagonista or _esc.existe_en(nombre, anio if anio < 2026 else 0)

    if hecha:
        hecha["elementos"] = [el for el in hecha["elementos"]
                              if el.get("tipo") != "prop" or _de_epoca(str(el.get("nombre") or ""))]
        e.elementos = [el for el in e.elementos if el.get("tipo") != "prop" or _de_epoca(str(el.get("nombre") or ""))]
    objetos = [] if hecha else [o for o in list(spec.get("objetos") or [])[:3] if _de_epoca(str(o.get("prop") or ""))
                                # con uso_manos: nada de monedas o bolsas de plata gigantes (Santi, 2026-11-16)
                                and not (SIN_PLATA_SIMBOLO and o.get("prop") in ("moneda", "bolsa_plata"))]
    cadena = [] if hecha else [o for o in (spec.get("cadena") or []) if o.get("prop") and _de_epoca(str(o["prop"]))][:4]
    if cadena:
        proy = next((o for o in objetos if o.get("efecto") in ("vuela", "rebota")), None)
        e.cadena(cadena, (proy or {}).get("prop") or proyectil, colores[i % len(colores)])
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
    # Reglas_v3: quien manipula tiene el producto en las manos (nunca manos vacías ni el objeto flotando al lado)
    if MANOS_V3 and protagonista and any(a.get("manos") and not a.get("objeto_rol") for a in e.actores) \
            and not any(el.get("en_mano") for el in e.elementos):
        e.objeto(protagonista, "quieto", "centro", soporte="mano")
        for el in e.elementos:
            if el.get("en_mano") and el.get("nombre") == protagonista:
                el["color"] = True
    # Lo que tiene en las manos cada uno según su rol (Santi, 2026-11-17): el obrero la caja, el cajero los billetes,
    # el cliente el producto que compra. Nunca manos vacías.
    for a in list(e.actores):
        if a.get("objeto_rol") and not a.get("lleva"):
            prop = str(a["objeto_rol"]).replace("{prota}", protagonista or "caja")
            if not _de_epoca(prop):
                prop = "caja"
            for b in e.actores:      # que lo agarre ÉL (objeto() elige al primero libre sin objeto de rol)
                if b is not a:
                    b["_ocupado"] = b.get("lleva")
                    b["lleva"] = b.get("lleva") or "_"
            a_or = a.pop("objeto_rol")
            e.objeto(prop, "quieto", "centro", soporte="mano")
            a["objeto_rol"] = a_or
            for b in e.actores:
                if b is not a:
                    b["lleva"] = b.pop("_ocupado")
                    if not b["lleva"]:
                        b.pop("lleva")
            if prop == protagonista:
                for el in e.elementos:
                    if el.get("en_mano") and el.get("nombre") == protagonista:
                        el["color"] = True
    # La línea de producción (Santi, 2026-11-17): en la fábrica con obreros, una cinta adelante con el producto que
    # avanza y la gente trabajando en ella; nunca vacía.
    linea = []
    if fondo == "fabrica" and not hecha and any(a.get("rol") in ("obrero", "obrera") for a in e.actores):
        prod = protagonista if protagonista and _de_epoca(protagonista) else "caja"
        linea.append({"tipo": "prop", "nombre": "cinta_frente", "x": 540, "y": Y_CINTA, "linea": True,
                      "forma": 1 if e.anio < 1940 else 0})
        n_ = 6
        for k in range(n_):
            t0 = round(-dur + k * 2 * dur / n_, 2)     # ya hay producto en la cinta desde el primer cuadro
            linea.append({"tipo": "prop", "nombre": prod, "x": -140, "y": Y_CINTA - 46, "escala": 0.4, "linea": True,
                          "color": prod == protagonista or None,
                          "keyframes": [{"t": t0, "x": -140}, {"t": t0 + 2 * dur, "x": 1220, "easing": "lineal"}]})
        e.sfx.append((0.0, "maquina"))
        for el in linea:
            if "color" in el and el["color"] is None:
                el.pop("color")
    # Decorado de contexto (Santi, 2026-11-16, reglas_v3): 1 a 3 objetos de la historia y la época atrás, sobre el
    # estante, la mesa o el piso (nada de mesas vacías). Más chicos y detrás de los personajes.
    interior = fondo in ("casa", "oficina", "taller", "fabrica", "tienda", "laboratorio", "hospital", "cocina")
    # afuera (calle, campo, puerto) el fondo ya trae su contexto (autos, faroles, vidrieras): nada flotando en la vereda
    # lo que es parte del cuarto o va colgado (ventana, puerta, cuadro) ya lo trae el fondo: como decorado quedaba
    # flotando en el medio de la pared (Frisbee, 2026-11-17)
    decorado = [str(x) for x in (spec.get("decorado") or []) if x and _de_epoca(str(x))
                and str(x) not in NO_DECORADO
                and not (SIN_PLATA_SIMBOLO and str(x) in ("moneda", "bolsa_plata"))][:3] if interior else []
    for j, nombre in enumerate(decorado):
        from . import escenas as _esc2

        if not _esc2.es_prop(nombre):
            continue
        antes, antes_f = len(e.elementos), len(e.fondo_el)
        # adentro: estante, mesa y piso (nada de mesas vacías); afuera, solo en el piso (nada de un estante en la calle)
        sop = ("estante", "mesa", "piso")[j]
        e.objeto(nombre, "quieto", ("izquierda", "derecha", "centro")[j], soporte=sop)
        for el in e.elementos[antes:] + e.fondo_el[antes_f:]:
            el["decorado"] = True          # el objeto y el mueble que lo sostiene: la cámara no los encuadra
            if el.get("nombre") == nombre:
                el["escala"] = round(float(el.get("escala", 1.0)) * 0.7, 3)
    # orden de dibujo: muebles de apoyo → lo que cuelga o se apoya atrás → personajes → pedazos y proyectiles
    fondo_cosas = {"ventana", "lampara", "cuadro", "tele", "jarron", "botella", "trofeo"}
    e.elementos.sort(key=lambda el: 0 if (el.get("nombre") in fondo_cosas or el.get("decorado")) and not el.get("keyframes") else
                     1 if el.get("tipo") == "personaje" else 2)
    e.elementos += linea          # la cinta adelante de la gente (les tapa las piernas: trabajan detrás de la línea)
    elementos = e.fondo_el + e.elementos
    texto = str(spec.get("texto_pantalla") or "").strip()
    if texto:
        elementos.append({"tipo": "gancho", "texto": texto, "y": Y_TEXTO_PANTALLA, "modo": "palabras" if primera else "rebote",
                          "tam": 100, "desde": 0.0 if primera else 0.2})
    parte = spec.get("parte") or ""
    remate = parte in ("giro", "final")
    fuerte = parte in ("gancho", "giro", "final") or bool(cadena) or \
        any((a.get("cara") or "") in ("sorprendido", "enojado") for a in spec.get("actores") or [])
    camara = (hecha["camara"] if hecha and hecha.get("camara") else
              e.camara(spec.get("camara") or "fija", fuerte, PLANOS[i % 3] if visual is not None and not hecha else None))
    if remate:   # el remate brilla (Santi, 2026-11-15): alrededor de la cara del primer plano, si lo hay
        pp = getattr(e, "primer_plano_en", None)
        t_d, centro = ((pp[0] + 0.1, (pp[1], pp[2])) if pp else (min(dur * 0.45, max(0.3, dur - 1.0)), (540, 1050)))
        for k, el in enumerate(destellos(t_d, e.rnd, centro)):
            if pp:   # en un anillo alrededor de la cara, nunca encima (nada tapa una cara)
                ang = math.radians(-160 + k * 47 + e.rnd.uniform(-12, 12))
                dist = e.rnd.uniform(175, 235)
                el["x"] = round(centro[0] + math.cos(ang) * dist, 1)
                el["y"] = round(max(BANDA_SUBTITULOS + 120, centro[1] + math.sin(ang) * dist * 0.9), 1)
            elementos.append(el)
        e.sfx.append((round(t_d, 3), "ding"))
    if fondo in ("casa", "oficina", "taller", "fabrica", "tienda", "ciudad", "laboratorio", "hospital",
                 "campo", "puerto") and i % 2 == 0 and not hecha:
        # profundidad: algo cerca de la cámara en una esquina de abajo, con parallax (se corre al revés)
        lado = -1 if (i // 2) % 2 == 0 else 1
        elementos.append({"tipo": "prop", "nombre": "primer_plano", "texto": fondo, "forma": lado * (1 + 2 * (i // 4 % 2)),
                          "x": 0, "y": 0, "keyframes": [{"t": 0, "x": 22 * lado}, {"t": dur, "x": -22 * lado,
                                                                                  "easing": "suave"}]})
    if texto:
        elementos.append(elementos.pop(next(k for k, el in enumerate(elementos) if el.get("tipo") == "gancho")))
    tr = spec.get("transicion") if spec.get("transicion") in TRANSICIONES_OK else "barrido"
    if not primera and parte in ("giro", "final") and tr in ("corte", "barrido"):
        tr = "iris"            # transición con estilo hacia el remate
    if visual is not None and visual.get("rotulo"):   # el rótulo ya dice el año: sin el año suelto en grande
        elementos = [el for el in elementos if not (el.get("tipo") == "gancho" and str(el.get("texto", "")).strip().isdigit())]
    if visual is not None:   # Así Nació más visual (2026-11-15): rótulo, dato, cita, cartel y la luz del momento
        nuevos, fx_v = elementos_visuales(visual, dur, sorted(t for t, _ in e.golpes), primera)
        elementos += nuevos
        e.sfx += fx_v
    if protagonista:   # en el pasado (sepia) el objeto protagonista queda a todo color (Santi, 2026-11-15)
        for el in elementos:
            if el.get("tipo") == "prop" and el.get("nombre") == protagonista:
                el["color"] = True
    d = {"duracion": dur, "fondo": {"tipo": fondo, "semilla": semilla,
                                    **({"momento": visual["momento"]} if visual and visual.get("momento") else {})},
         "transicion": {"tipo": "corte" if primera else tr, "duracion": 0.3 if tr == "iris" else 0.25},
         "camara": camara, "elementos": elementos, "tono": tono}
    sfx = sorted((round(t, 3), s) for t, s in e.sfx if 0 <= t < dur)
    arreglar_composicion(d)
    return d, sfx


def escena_locutor(dur: float, k: int = 0) -> tuple[dict, list[tuple[float, str]]]:
    """La PAUSA: la escena de atrás congelada y gris, y Tito (la mascota de "Así Nació") entra por el
    costado, comenta (la boca sigue la voz) y se va. Del lado izquierdo señala la escena; del derecho
    saluda y levanta el reloj."""
    izq = lado_tito(k) == "izquierda"
    # Al costado y con los brazos hacia arriba (saluda y levanta el reloj): señalando de costado el
    # brazo tapaba al de al lado (visto en el Nerf del 14/11).
    x = X_TITO["izquierda" if izq else "derecha"]
    afuera = -420 if izq else 1500
    poses = [{"t": 0, "pose": "saluda"}, {"t": max(0.7, dur * 0.5), "pose": "reloj"}]
    tito = {"tipo": "tito", "x": x, "y": PISO + 20, "escala": ESCALA_TITO, "habla": True,
            "entrada": "izquierda" if izq else "derecha",
            "keyframes": [{"t": max(0.6, dur - 0.3), "x": x}, {"t": dur, "x": afuera, "easing": "entrada"}],
            "poses": poses}
    return ({"duracion": dur, "congela": True, "fondo": {"tipo": "color", "color": "#000000"},
             "transicion": {"tipo": "corte"}, "elementos": [tito]},
            [(0.0, "tac"), (0.05, "whoosh")])


def lado_tito(k: int) -> str:
    """De qué costado aparece Tito en su pausa número `k` (se alterna)."""
    return "izquierda" if k % 2 == 0 else "derecha"


VIAJE_S = 1.35


def escena_viaje(dur: float, de: int, a: int, presente: int = 2026) -> tuple[dict, list[tuple[float, str]]]:
    """El VIAJE EN EL TIEMPO, marca del canal (Santi, 2026-11-15; siempre igual, 1-1,5 s): un reloj gigante de
    fondo con las agujas girando hacia atrás (hacia adelante al volver), el año bajando rapidísimo como un
    cuentakilómetros, la escena congelada que se retuerce en remolino, el color que se apaga de a poco hasta
    sepia (o vuelve) y un whoosh fuerte. Tito, con su reloj, en una esquina."""
    al_pasado = a < de
    sentido = -1 if al_pasado else 1
    reloj = {"tipo": "prop", "nombre": "reloj_gigante", "forma": sentido, "x": 540, "y": 930, "escala": 1.12,
             "fase": 0.0, "opacidad": 0.0,
             "keyframes": [{"t": 0, "opacidad": 0.0, "escala": 0.8, "fase": 0.0},
                           {"t": 0.22, "opacidad": 0.88, "escala": 1.12, "easing": "salida"},
                           {"t": dur, "opacidad": 0.88, "escala": 1.22, "fase": 1.0, "easing": "lineal"}]}
    contador = {"tipo": "contador", "estilo": "odometro", "de": de, "a": a, "dur": max(0.45, dur - 0.4),
                "desde": 0.12, "x": 540, "y": 930, "tam": 190, "entrada": "rebote"}
    tito = {"tipo": "tito", "x": 870, "y": PISO + 40, "escala": 0.42, "entrada": "derecha",
            "giro_aguja": -1440 if al_pasado else 1440, "poses": [{"t": 0, "pose": "reloj"}],
            "keyframes": [{"t": max(0.5, dur - 0.2), "x": 870}, {"t": dur, "x": 1500, "easing": "entrada"}]}
    giro = -120 if al_pasado else 120
    camara = [{"t": 0, "zoom": 1.0, "rotacion": 0}, {"t": dur, "zoom": 1.7, "rotacion": giro, "easing": "entrada"}]
    return ({"duracion": dur, "congela": True, "girar": True, "remolino": True,
             "fondo": {"tipo": "color", "color": "#000000"},
             "transicion": {"tipo": "corte"}, "camara": camara, "elementos": [reloj, contador, tito],
             "tono": [0.0 if de >= presente else 1.0, 0.0 if a >= presente else 1.0]},
            [(0.0, "viaje")])
