"""Biblioteca de escenas de acción (Santi, 2026-11-15: "lo que se ve no coincide con lo que dice la voz").

Cada escena de la biblioteca muestra UNA acción concreta (armar algo en una mesa, vender en una tienda, una
fábrica produciendo, una reunión, cargar un barco, un contador de ventas que sube, estantes que se llenan, el
objeto que gira y se transforma, algo que despega) con sus PLANOS (desde arriba, primer plano de manos, de
lejos, de espaldas, de cerca, de frente) y se reusa en todos los videos cambiando el objeto y los personajes.
El objeto protagonista se MUEVE con efectos (gira, se resuelve, avanza en una cinta, vuela al barco, se apila).

Las acciones que no están se crean como receta (la escena del guion con el objeto y los roles como
variables) y quedan guardadas en `data/animacion/escenas_lib.json` para reusarlas (`guardar_receta`)."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from clips_bot.config import DATA_DIR

from . import acciones as ac
from . import paleta as P

RECETAS = DATA_DIR / "animacion" / "escenas_lib.json"

# acción → (descripción para el guion, planos que tiene, fondo por defecto)
ACCIONES = {
    "armar_mesa": ("alguien arma o construye el objeto con las manos sobre una mesa (armar, ensamblar, inventar, "
                   "probar piezas)", ("arriba", "manos", "lejos", "espaldas"), "taller"),
    "vender_tienda": ("una tienda con gente comprando el objeto y un vendedor (vender, salir a la venta, lanzamiento)",
                      ("lejos", "cerca"), "tienda"),
    "fabrica_produce": ("una fábrica produciendo: una cinta saca el objeto uno tras otro (fabricar en serie, producir)",
                        ("lejos", "cerca"), "fabrica"),
    "reunion": ("una reunión de 2 o 3 personas alrededor del objeto (un trato, comprar la empresa, una idea)",
                ("lejos", "espaldas"), "oficina"),
    "cargar_barco": ("cajas con el objeto que se cargan en un barco (exportar, llegar a otro país)", ("lejos",), "puerto"),
    "contador_ventas": ("un contador de ventas que sube y una pila del objeto que crece (vendió millones, récord)",
                        ("frente",), "escenario"),
    "estantes_llenan": ("estantes de una tienda que se llenan con el objeto (llegó a todas las tiendas, furor)",
                        ("lejos",), "tienda"),
    "objeto_gira": ("el objeto grande en el centro girando y transformándose (presentar el objeto, el momento clave, "
                    "se resuelve)", ("cerca",), "escenario"),
    "despega": ("el objeto despega o sale volando con humo y fuego (un lanzamiento, explotar de fama, viajar lejos)",
                ("lejos",), "cielo"),
    # Santi, 2026-11-16 (uso_v3.py): el producto usado de verdad por dos manos, paso a paso, y la inspiración animada
    "uso_manos": ("dos manos de cerca usan el producto como se usa de verdad, paso a paso (guardar comida y cerrar la "
                  "tapa, amasar, girar las caras)", ("manos",), None),
    "inspiracion": ("lo que inspiró al producto y el producto, lado a lado: la pieza pasa de uno al otro y encastra "
                    "(la frase que cuenta de dónde salió la idea)", ("cerca",), None),
    # la PLATA con acciones reales (Santi, 2026-11-16: nada de monedas con $ gigantes en las manos)
    "contar_billetes": ("dos manos cuentan billetes sobre una mesa, pasándolos de una pila a otra (ganancias, ventas, "
                        "ahorros, pagos)", ("manos",), None),
    "abrir_caja": ("una mano aprieta la tecla de la caja registradora, se abre el cajón y saca un billete (las primeras "
                   "ventas, la plata que entra)", ("manos",), None),
    "apreton_manos": ("dos manos se dan un apretón para cerrar un trato (un acuerdo, una compra, una sociedad, pactar "
                      "con los acreedores)", ("manos",), None),
    "firmar": ("una mano firma un contrato o un cheque con lapicera mientras la otra sostiene el papel (comprar una "
               "empresa, una deuda, un contrato, una patente)", ("manos",), None),
}
# Las de los pedidos del 16/11: solo se ofrecen al guion con `animacion.uso_manos` (las prende marcas.armar_video)
# la biblioteca BASE (Santi, 2026-11-20): las escenas nuevas de plantillas.py, probadas una por una
from . import plantillas as _pl  # noqa: E402

ACCIONES.update(_pl.DESCRIPCION)
CON_CAMARA = _pl.CON_CAMARA
ACCIONES_V4 = {"uso_manos", "inspiracion", "contar_billetes", "abrir_caja", "apreton_manos", "firmar"}
CON_V4 = False
LIBRE = "libre"
PLANOS = ("arriba", "manos", "lejos", "espaldas", "cerca", "frente")
SIN_DECO = {"mesa_arriba"}

# Como mucho UNA escena de solo manos por video (las 5 marcas del 20/11: firmar, contar billetes y armar desde arriba
# en el mismo video y la revisión decía "solo manos, sin gente, no se entiende sin la voz"). Se queda la de uso (el
# producto en uso); las demás pasan a su versión con gente, sin pedirle nada a Claude.
# firmar ya NO es de solo manos: es una persona firmando en su escritorio (biblioteca base, 2026-11-20); antes la
# regla de "una sola de manos" la cambiaba por una reunión de dos personas paradas (Pepsi)
SOLO_MANOS = {"uso_manos", "contar_billetes", "abrir_caja"}
CON_GENTE = {"contar_billetes": ("reunion", "lejos"),
             "abrir_caja": ("vender_tienda", "cerca"), "uso_manos": ("armar_mesa", "lejos"),
             "armar_mesa": ("armar_mesa", "lejos")}


def solo_manos(e: dict) -> bool:
    acc = str(e.get("accion_escena") or "")
    return acc in SOLO_MANOS or (acc == "armar_mesa" and str(e.get("plano") or "") in ("arriba", "manos"))


def una_de_manos(escenas: list[dict], maximo: int = 1) -> list[dict]:
    idx = [i for i, e in enumerate(escenas) if solo_manos(e)]
    quedan = set(sorted(idx, key=lambda i: (escenas[i].get("accion_escena") != "uso_manos", i))[:maximo])
    out = []
    for i, e in enumerate(escenas):
        if i in idx and i not in quedan:
            acc, plano = CON_GENTE.get(str(e.get("accion_escena") or ""), ("armar_mesa", "lejos"))
            e = {**e, "accion_escena": acc, "plano": plano}
        out.append(e)
    return out       # fondos propios de la biblioteca (no los elige el guion)


def recetas() -> dict:
    try:
        return json.loads(RECETAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_receta(nombre: str, descripcion: str, spec: dict) -> None:
    """Una acción nueva (la escena del guion, con {objeto} y {rol} como variables), para reusarla."""
    todas = recetas()
    if nombre in todas or nombre in ACCIONES:
        return
    plantilla = json.loads(json.dumps({k: spec.get(k) for k in ("fondo", "actores", "objetos", "multitud", "camara")}))
    todas[nombre] = {"descripcion": descripcion, "spec": plantilla}
    RECETAS.parent.mkdir(parents=True, exist_ok=True)
    RECETAS.write_text(json.dumps(todas, ensure_ascii=False, indent=1), encoding="utf-8")


def todas_las_acciones() -> dict[str, str]:
    """{acción: descripción} de la biblioteca (las de código y las guardadas)."""
    out = {k: v[0] for k, v in ACCIONES.items() if CON_V4 or k not in ACCIONES_V4}
    out.update({k: v.get("descripcion", "") for k, v in recetas().items()})
    return out


def _rol(spec: dict, k: int, defecto: str) -> dict:
    actores = spec.get("actores") or []
    a = actores[k] if k < len(actores) else {}
    return {"rol": a.get("rol") or defecto, "genero": a.get("genero") or "", "edad": a.get("edad") or "",
            "cara": a.get("cara") or "normal"}


def _objeto(spec: dict, protagonista: str) -> str:
    """El objeto de la escena: el protagonista si está; si no, el primero que no es un ícono ni un gráfico (en el Lego
    de 2015 la pila del contador era de gráficos, 2026-11-19)."""
    props = [str(o.get("prop") or "") for o in spec.get("objetos") or []]
    if protagonista and (protagonista in props or not props):
        return protagonista
    for p_ in props:
        if p_ and p_ not in ac.ICONOS:
            return p_
    return protagonista or "caja"


def construir(accion: str, plano: str, spec: dict, dur: float, i: int, protagonista: str = "") -> dict | None:
    """(elementos, fondo, camara, sfx, actores) de una acción de la biblioteca; None si no está (va lo de siempre)."""
    if accion in recetas() and accion not in ACCIONES:
        return None          # las recetas guardadas se arman como una escena del guion (ver aplicar_receta)
    if accion not in ACCIONES:
        return None
    rnd = random.Random(i * 31 + len(accion))
    planos = ACCIONES[accion][1]
    plano = plano if plano in planos else planos[0]
    obj = _objeto(spec, protagonista)
    f = globals()[f"_{accion}"]
    return f(plano, spec, dur, i, obj, rnd)


def aplicar_receta(accion: str, spec: dict, protagonista: str = "") -> dict:
    """La escena del guion con la receta guardada de esa acción (el objeto y los roles del guion encima)."""
    r = recetas().get(accion)
    if not r:
        return spec
    base = json.loads(json.dumps(r["spec"]))
    obj = _objeto(spec, protagonista)
    for o in base.get("objetos") or []:
        if o.get("prop") == "{objeto}":
            o["prop"] = obj
    for k, a in enumerate(base.get("actores") or []):
        if k < len(spec.get("actores") or []):
            a.update({c: spec["actores"][k][c] for c in ("rol", "genero", "edad", "persona_real") if c in spec["actores"][k]})
    return {**spec, **{k: v for k, v in base.items() if v}}


# ---- las acciones --------------------------------------------------------------------------------------
def _el(nombre, x, y, **kw) -> dict:
    return {"tipo": "prop", "nombre": nombre, "x": round(x, 1), "y": round(y, 1), **kw}


def _actor(e: "ac.Escena", a: dict, accion: str, x: float, k: int = 0, espaldas: bool = False) -> None:
    e.actor(a["rol"], accion, "centro", None, a["cara"], k, x0=x, x1=x, genero=a["genero"], edad=a["edad"])
    if espaldas:
        e.elementos[-1]["espaldas"] = True


def _armar_mesa(plano, spec, dur, i, obj, rnd):
    sfx = []
    if plano in ("arriba", "manos"):
        # desde arriba: la mesa de madera llena el cuadro, el objeto en el centro girando y armándose, y las
        # dos manos trabajando sobre él
        # manos humanas con el detalle de siempre que AGARRAN el objeto apoyado en la mesa (Santi, 2026-11-19: nada de
        # manos de madera gigantes con el objeto flotando): lo giran apenas, sin levantarlo
        from . import uso_v3 as _u

        z = 1.0 if plano == "arriba" else 1.2
        els = [_el(obj, 540, 1080, escala=2.0, fase=0.0,
                   keyframes=[{"t": 0, "rotacion": -5, "fase": 0.0}, {"t": dur, "rotacion": 5, "fase": 1.0, "easing": "suave"}])]
        for lado in (-1, 1):
            kf, t, x0 = [], 0.0, 540 + lado * _u.SEP_MANO
            while t < dur:
                ang = t * 4.0 + (0 if lado < 0 else math.pi)
                kf.append({"t": round(t, 2), "x": round(x0 + 12 * math.cos(ang), 1),
                           "y": round(1080 + _u.Y_AGARRE + 10 * math.sin(ang), 1), "rotacion": -lado * _u.GIRO_AGARRE,
                           "fase": _u.AGARRE, "easing": "suave"})
                t += 0.3
            els.append(_el("mano", x0, 1080 + _u.Y_AGARRE, escala=_u.ESCALA_MANO, forma=lado, detalle=True, fase=_u.AGARRE,
                           manga=_u.manga_de_epoca(spec), keyframes=kf))
        t = 0.3
        while t < dur:
            sfx.append((round(t, 2), "tac"))
            t += 0.55
        cam = [{"t": 0, "zoom": z}, {"t": dur, "zoom": z + 0.08, "easing": "suave"}]
        return {"elementos": els, "fondo": "mesa_arriba", "camara": cam, "sfx": sfx, "actores": []}
    e = ac.Escena(dur, semilla=i)
    a = _rol(spec, 0, "inventor")
    _actor(e, a, "fabricar", 540, espaldas=(plano == "espaldas"))
    q = e.elementos[-1]
    esc_ = float(q.get("escala", 0.74))
    e.elementos.append(_el(obj, 540, ac.PISO - 360 * esc_, escala=0.7, fase=0.0, en_mano=True,
                           keyframes=[{"t": 0, "rotacion": 0, "fase": 0.0},
                                      {"t": dur, "rotacion": 360, "fase": 1.0, "easing": "lineal"}]))
    return {"elementos": e.elementos, "fondo": None, "camara": None, "sfx": e.sfx, "actores": e.actores}


def _uso_manos(plano, spec, dur, i, obj, rnd):
    from . import uso_v3

    u = spec.get("uso") or {}
    return uso_v3.escena_uso(dur, obj, u.get("partes") or {}, u.get("pasos") or [], u.get("manga") or "", seed=i)


def _inspiracion(plano, spec, dur, i, obj, rnd):
    from . import uso_v3

    ins = spec.get("inspiracion") or {}
    if not (ins.get("fuente") and ins.get("pieza")):
        return _objeto_gira(plano, spec, dur, i, obj, rnd)
    return uso_v3.escena_inspiracion(dur, ins["fuente"], ins["pieza"], ins.get("producto") or obj, seed=i,
                                     resultado=ins.get("resultado") or "", acompana=ins.get("acompana") or "")


def _plata(tipo):
    def f(plano, spec, dur, i, obj, rnd):
        from . import uso_v3

        return uso_v3.escena_plata(tipo, dur, (spec.get("uso") or {}).get("manga") or "", seed=i, spec=spec)
    return f


_contar_billetes, _abrir_caja, _apreton_manos, _firmar = (_plata(t) for t in
                                                          ("contar_billetes", "abrir_caja", "apreton_manos", "firmar"))


def _vender_tienda(plano, spec, dur, i, obj, rnd):
    e = ac.Escena(dur, semilla=i)
    v = _rol(spec, 0, "vendedor")
    _actor(e, v, "vender", 860)
    els = list(e.elementos)
    els.append(_el("mostrador", 840, ac.PISO - 120, escala=1.0))
    # dos clientes que entran caminando, sin pisarse: el primero va más lejos (más cerca del mostrador)
    clientes = [_rol(spec, 1, "cliente"), _rol(spec, 2, "joven")]
    destinos = ((-260, 440), (-560, 170))
    for k, (c, (x0, x1)) in enumerate(zip(clientes, destinos)):
        e2 = ac.Escena(dur, semilla=i + k)
        e2.actor(c["rol"], "caminar", "afuera_izq", None, "feliz", 0, x0=x0, x1=x1, genero=c["genero"], edad=c["edad"])
        els += e2.elementos
    # cada cliente se lleva uno: el objeto aparece sobre el mostrador y vuela a su mano
    sfx = list(e.sfx)
    for k in range(3):
        t0 = round(0.6 + k * min(0.7, dur / 4), 2)
        x_dest = destinos[k % 2][1]
        els.append(_el(obj, 840, ac.PISO - 330, escala=0.55, desde=t0, hasta=round(t0 + 0.6, 2),
                       keyframes=[{"t": t0, "escala": 0.1}, {"t": t0 + 0.2, "escala": 0.55, "easing": "rebote"},
                                  {"t": t0 + 0.6, "x": x_dest, "y": ac.PISO - 420, "easing": "entrada"}]))
        els.append(_el("moneda", 840, ac.PISO - 520, escala=0.5, desde=t0, hasta=round(t0 + 0.5, 2),
                       keyframes=[{"t": t0, "y": ac.PISO - 520}, {"t": t0 + 0.5, "y": ac.PISO - 640, "opacidad": 0.0}]))
        sfx.append((t0, "caja_registradora" if k == 0 else "pop"))
    cam = [{"t": 0, "zoom": 1.0 if plano == "lejos" else 1.25}, {"t": dur, "zoom": 1.08 if plano == "lejos" else 1.32,
                                                              "easing": "suave"}]
    return {"elementos": els, "fondo": "tienda", "camara": cam, "sfx": sfx, "actores": e.actores, "multitud": True}


def _fabrica_produce(plano, spec, dur, i, obj, rnd):
    e = ac.Escena(dur, semilla=i)
    for k, (x, defecto) in enumerate(((180, "obrero"), (900, "obrera"))):
        _actor(e, _rol(spec, k, defecto), "fabricar", x, k)
    els = list(e.elementos)
    y = 1940 * 0.66 - 70          # sobre la cinta del fondo de la fábrica
    n_ = 7
    for k in range(n_):
        t0 = round(k * dur / n_, 2)
        els.append(_el(obj, -120, y, escala=0.55, fase=1.0, desde=t0,
                       keyframes=[{"t": t0, "x": -120}, {"t": t0 + dur * 0.85, "x": 1200, "easing": "lineal"}]))
    sfx = [(0.0, "maquina")] + [(round(k * dur / n_ + 0.1, 2), "tac") for k in range(n_)]
    cam = [{"t": 0, "zoom": 1.0 if plano == "lejos" else 1.3}, {"t": dur, "zoom": 1.06 if plano == "lejos" else 1.36,
                                                              "x": 40, "easing": "suave"}]
    return {"elementos": els, "fondo": "fabrica", "camara": cam, "sfx": e.sfx + sfx, "actores": e.actores}


def _reunion(plano, spec, dur, i, obj, rnd):
    e = ac.Escena(dur, semilla=i)
    # Nada de gente parada (Santi, 2026-11-15): uno le da el objeto al otro, que lo agarra y lo prueba.
    for k, (x, accion, defecto) in enumerate(((240, "vender", "inventor"), (840, "usar", "empresario"))):
        _actor(e, _rol(spec, k, defecto), accion, x, k, espaldas=(plano == "espaldas" and k == 0))
    els = list(e.elementos)
    medio = min(dur * 0.55, dur - 0.3)
    els.append(_el(obj, 330, 1060, escala=0.9, fase=0.0, desde=0.1,
                   keyframes=[{"t": 0.1, "x": 330, "y": 1060, "rotacion": 0, "fase": 0.0},
                              {"t": medio, "x": 760, "y": 1000, "rotacion": 200, "fase": 0.3, "easing": "suave"},
                              {"t": dur, "x": 760, "y": 1000, "rotacion": 380, "fase": 1.0, "easing": "suave"}]))
    return {"elementos": els, "fondo": "oficina", "camara": None, "sfx": e.sfx + [(0.3, "pop")], "actores": e.actores}


def _cargar_barco(plano, spec, dur, i, obj, rnd):
    els, sfx = [], []
    n_ = 5
    for k in range(n_):
        t0 = round(0.2 + k * (dur - 0.6) / n_, 2)
        x0, y0, x1, y1 = 960, 1500, 420 + k * 60, 960
        kf = []
        for j in range(9):
            u = j / 8
            kf.append({"t": round(t0 + u * 0.8, 3), "x": round(x0 + (x1 - x0) * u, 1),
                       "y": round(y0 + (y1 - y0) * u - 260 * math.sin(math.pi * u), 1), "easing": "lineal"})
        els.append(_el("caja", x0, y0, escala=0.5, desde=t0, keyframes=kf, texto=""))
        els.append(_el(obj, x1, y1 - 70, escala=0.32, desde=round(t0 + 0.8, 2), entrada="rebote"))
        sfx.append((round(t0 + 0.8, 2), "tac"))
    e = ac.Escena(dur, semilla=i)
    _actor(e, _rol(spec, 0, "marinero"), "senalar", 820)
    return {"elementos": els + e.elementos, "fondo": "puerto", "camara": [{"t": 0, "zoom": 1.0}, {"t": dur, "zoom": 1.08, "x": -40,
                                                                                         "easing": "suave"}],
            "sfx": sfx + e.sfx, "actores": e.actores}


def numero_de_ventas(frase: str) -> int | None:
    """El número más grande de la frase que no es un año ("vendió 100.000" → 100000); None si no hay."""
    import re as _re

    nums = []
    for m in _re.finditer(r"(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:\s+(millones|millón|mil)\b)?", frase):
        txt = m.group(1)
        v = int(_re.sub(r"\D", "", txt))
        if m.group(2):
            v *= 1000 if m.group(2) == "mil" else 10 ** 6
            txt += " " + m.group(2)
        es_anio = len(txt) == 4 and txt.isdigit() and 1500 <= v <= 2100
        if not es_anio and 0 < v < 10 ** 10:
            nums.append(v)
    return max(nums) if nums else None


def _contador_ventas(plano, spec, dur, i, obj, rnd):
    import re as _re

    hasta = numero_de_ventas(str(spec.get("frase") or ""))
    # Sin un número en la frase no hay contador (nada de cifras inventadas): solo la pila que crece.
    # llega a la cifra a la mitad de la escena: un cuadro a mitad de cuenta mostraba "190196" con la voz diciendo
    # "200 000" (las 5 marcas del 20/11)
    els = ([{"tipo": "contador", "de": 0, "a": hasta, "dur": max(0.6, min(1.3, dur * 0.45)), "desde": 0.15, "x": 540, "y": 640,
             "tam": 170 if hasta < 10 ** 7 else 130, "entrada": "rebote"}] if hasta else [])
    for k in range(12):          # la pila del objeto que crece
        t0 = round(0.2 + k * (dur - 0.5) / 12, 2)
        x = 540 + ((k % 4) - 1.5) * 120
        y = ac.PISO - 90 - (k // 4) * 110
        els.append(_el(obj, x, y, escala=0.45, fase=1.0, desde=t0, entrada="rebote"))
    return {"elementos": els, "fondo": "escenario", "camara": [{"t": 0, "zoom": 1.0}, {"t": dur, "zoom": 1.12, "easing": "suave"}],
            "sfx": [(round(0.2 + k * (dur - 0.5) / 12, 2), "pop") for k in range(0, 12, 2)], "actores": []}


def _estantes_llenan(plano, spec, dur, i, obj, rnd):
    els, sfx, k = [], [], 0
    for fila in range(4):
        ye = 300 + fila * 270 + 200          # las tablas de las estanterías del fondo de la tienda
        for col in range(6):
            x = 100 + col * 90 + (520 if col >= 3 else 0)
            t0 = round(0.1 + k * (dur - 0.4) / 24, 2)
            els.append(_el(obj, x, ye - 45, escala=0.36, fase=1.0, desde=t0, entrada="rebote"))
            if k % 4 == 0:
                sfx.append((t0, "pop"))
            k += 1
    return {"elementos": els, "fondo": "tienda", "camara": [{"t": 0, "zoom": 1.0}, {"t": dur, "zoom": 1.1, "easing": "suave"}],
            "sfx": sfx, "actores": []}


def _objeto_gira(plano, spec, dur, i, obj, rnd):
    # apoyado en una mesa y girando apenas, nunca flotando en el aire (Santi, 2026-11-19: nada flota)
    els = [_el("mesa", 540, 1300, escala=3.4, decorado=True, en_medio=True),
           _el(obj, 540, 1180, escala=1.9, fase=0.0, color=True,
               keyframes=[{"t": 0, "rotacion": -6, "escala": 1.75, "fase": 0.0},
                          {"t": dur * 0.85, "rotacion": 6, "escala": 1.95, "fase": 1.0, "easing": "suave"},
                          {"t": dur, "rotacion": 6, "escala": 1.95, "fase": 1.0}])]
    els += ac.destellos(max(0.2, dur * 0.8), rnd, (540, 1080))
    return {"elementos": els, "fondo": "escenario", "camara": [{"t": 0, "zoom": 1.0}, {"t": dur, "zoom": 1.15, "easing": "suave"}],
            "sfx": [(round(dur * 0.8, 2), "ding")], "actores": []}


def _despega(plano, spec, dur, i, obj, rnd):
    t0, t1 = 0.25, max(0.8, dur - 0.2)
    kf, humo = [], []
    for j in range(13):
        u = j / 12
        x = 540 + 260 * math.sin(u * math.pi * 1.2)
        y = 1650 - 1250 * (u ** 1.6)
        kf.append({"t": round(t0 + u * (t1 - t0), 3), "x": round(x, 1), "y": round(y, 1),
                   "rotacion": round(20 * math.cos(u * math.pi * 1.2), 1), "easing": "lineal"})
        if j % 2 == 0:
            humo += ac.polvo(x, y + 120, t0 + u * (t1 - t0), rnd, 2, "#e8e8e8")
    els = humo + [_el("fuego", 540, 1770, escala=0.9, desde=t0, keyframes=[{**k, "y": k["y"] + 120} for k in kf]),
                  _el(obj, 540, 1650, escala=0.9, desde=0.0, keyframes=[{"t": 0, "x": 540, "y": 1650}] + kf)]
    lin = ac.estela(kf, t0, t1)
    if lin:
        els.insert(0, lin)
    return {"elementos": els, "fondo": "cielo", "camara": [{"t": 0, "zoom": 1.0}, {"t": dur, "zoom": 1.1, "easing": "suave"}],
            "sfx": [(t0, "cohete")], "actores": []}


# la biblioteca base pisa a las versiones viejas de la fábrica y la tienda (Santi, 2026-11-20)
globals().update({f"_{k}": f for k, f in _pl.CONSTRUCTORES.items()})
