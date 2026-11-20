"""Así Nació, reglas del 2026-11-16 (Santi; detrás de `animacion.reglas_v3` hasta que apruebe el Tupper):

GANCHO (primeros 3 s): una imagen sorprendente o imposible con el producto (explota, gigante, se multiplica, vuela,
una multitud se pelea por él), con colores fuertes (rayos de cómic) y mucho movimiento; 2 o 3 cortes de ~1 s, con
un golpe en cada corte; texto grande arriba (3 a 5 palabras); más detalle que el resto (fondo completo, destellos,
polvo, líneas de movimiento). El guion trae 3 opciones (`ganchos`) y la revisión visual elige la más llamativa.

RESTO: ninguna toma dura más de 3 s y cada frase tiene al menos 2 planos (de lejos → de cerca a las manos y el
objeto), siempre con movimiento (zoom lento).
"""
from __future__ import annotations

import math
import random

from . import acciones as ac
from . import paleta as P

TIPOS = ("explota", "gigante", "multiplica", "vuela", "multitud")
TOMA_MAX_S = 3.0
EFECTOS = {"polvo", "lineas_mov", "destello", "primer_plano", "rayos", "rotulo", "dato", "cita", "cartel_comic",
           "tito_reaccion", "pedazo", "reloj_gigante"}
Y_OBJETO = 1150
MUEBLES = {"mesa", "estante", "mostrador", "ventana", "cuadro", "lampara"}
Y_MANOS_MIN = 1150          # un objeto más arriba que esto está flotando: el primer plano no va ahí
ZOOM_CERCA = (1.55, 1.65)   # el primer plano de las manos (más cerrado cortaba las caras)
Y_TEXTO_GANCHO = 600        # el texto del gancho, lejos de los subtítulos de arriba (2026-11-16)
Y_ROTULO = 420              # el rótulo, debajo de los subtítulos (antes 330: quedaba pegado)


def _corte(t: float, zoom: float, x: float = 0.0, y: float = 0.0, rot: float = 0.0) -> list[dict]:
    """Un corte seco a la cámara (zoom, x, y) en `t`."""
    mx, my = 540 * (1 - 1 / zoom), 960 * (1 - 1 / zoom)
    x, y = max(-mx, min(mx, x)), max(-my, min(my, y))
    return [{"t": round(t, 3), "zoom": round(zoom, 3), "x": round(x, 1), "y": round(y, 1), "rotacion": rot,
             "easing": "escalon"}]


def camara_cortes(dur: float, tramos: list[tuple[float, float, float, float, float]]) -> list[dict]:
    """tramos = [(zoom inicial, zoom final, x, y, rotación)] repartidos parejo en `dur`, con cortes secos entre ellos
    y un zoom lento adentro de cada uno (nada queda quieto)."""
    n = len(tramos)
    kf = []
    for j, (z0, z1, x, y, rot) in enumerate(tramos):
        t0, t1 = dur * j / n, dur * (j + 1) / n
        if j == 0:
            kf.append({"t": 0, "zoom": z0, "x": x, "y": y, "rotacion": rot})
        else:
            kf += _corte(t0, z0, x, y, rot)
        mx, my = 540 * (1 - 1 / z1), 960 * (1 - 1 / z1)
        kf.append({"t": round(max(t0 + 0.02, t1 - 0.02), 3), "zoom": z1, "x": round(max(-mx, min(mx, x)), 1),
                   "y": round(max(-my, min(my, y)), 1), "rotacion": rot, "easing": "suave"})
    return kf


def _pos(el: dict, campo: str, t: float, defecto: float) -> float:
    """El valor de `campo` del elemento a los `t` segundos (interpolación lineal entre sus keyframes)."""
    kfs = sorted((float(k["t"]), float(k[campo])) for k in el.get("keyframes") or [] if campo in k)
    base = float(el.get(campo, defecto))
    if not kfs:
        return base
    if t <= kfs[0][0]:
        return kfs[0][1]
    for (t0, v0), (t1, v1) in zip(kfs, kfs[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * ((t - t0) / max(1e-6, t1 - t0))
    return kfs[-1][1]


def foco(esc_d: dict, t: float = 0.0) -> tuple[float, float] | None:
    """Dónde están las MANOS CON EL OBJETO a los `t` segundos (Santi, 2026-11-16: "los primeros planos encuadran las
    manos con el objeto, no caras cortadas"): el objeto en la mano; si no, un objeto apoyado abajo (mesa, piso); si no,
    las manos del primer personaje. Nunca el decorado, los muebles, los efectos ni algo flotando arriba."""
    props = [el for el in esc_d.get("elementos") or [] if el.get("tipo") == "prop" and el.get("nombre") not in EFECTOS
             and el.get("nombre") not in MUEBLES and not el.get("decorado") and not el.get("fijo")]
    en_mano = [el for el in props if el.get("en_mano")]
    if en_mano:
        el = en_mano[0]
        return _pos(el, "x", t, 540), _pos(el, "y", t, 1000)
    abajo = [el for el in props if _pos(el, "y", t, 0) >= Y_MANOS_MIN]
    for el in sorted(abajo, key=lambda el: (el.get("color") is not True, not el.get("lib"))):
        return _pos(el, "x", t, 540), _pos(el, "y", t, 1000)
    for el in esc_d.get("elementos") or []:
        if el.get("tipo") == "personaje" and not el.get("multitud"):
            return _pos(el, "x", t, 540), _pos(el, "y", t, ac.PISO) - 330 * float(el.get("escala", 1))
    return None


def planos(esc_d: dict) -> None:
    """Cada frase con 2 planos o más (de lejos → de cerca a las manos y el objeto), ninguno de más de 3 s, con zoom
    lento adentro de cada uno. Reemplaza la cámara de la escena."""
    dur = float(esc_d["duracion"])
    n = max(2, math.ceil(dur / TOMA_MAX_S)) if dur >= 1.2 else 1
    tramos = []
    for j in range(n):
        t_medio = dur * (j + 0.5) / n
        f = foco(esc_d, t_medio) if j % 2 == 1 else None
        if f is None:
            tramos.append((1.0 + 0.04 * (j % 2), 1.07 + 0.04 * (j % 2), 0.0, 0.0, 0.0))
        else:
            tramos.append((ZOOM_CERCA[0], ZOOM_CERCA[1], f[0] - 540, f[1] - 960, 0.0))
    esc_d["camara"] = camara_cortes(dur, tramos)


def _objeto(prota: str, **kw) -> dict:
    # el mismo tamaño para un dibujo guardado que para uno de código (la botella fiel salía chica, 2026-11-20)
    f = ac.factor_tam(prota)
    if "escala" in kw:
        kw["escala"] = round(kw["escala"] * f, 3)
    for k in kw.get("keyframes") or []:
        if "escala" in k:
            k["escala"] = round(k["escala"] * f, 3)
    return {"tipo": "prop", "nombre": prota, "color": True, **kw}


def escena_gancho(opcion: dict, prota: str, fondo: str, semilla: int, dur: float,
                  seed: int = 0) -> tuple[dict, list[tuple[float, str]]]:
    """El gancho de 2 o 3 cortes de ~1 s: la imagen imposible de `opcion["tipo"]` con el protagonista, rayos de
    colores fuertes, efectos en cada corte y el texto grande arriba."""
    rnd = random.Random(seed)
    tipo = opcion.get("tipo") if opcion.get("tipo") in TIPOS else "gigante"
    texto = " ".join(str(opcion.get("texto") or "").split()[:5]).upper()
    obj = prota or "caja"
    n = 3 if dur >= 2.4 else 2
    cortes = [dur * k / n for k in range(n)]
    els: list[dict] = [{"tipo": "prop", "nombre": "rayos", "x": 540, "y": Y_OBJETO, "escala": 1.0, "opacidad": 0.6,
                        "color": P.AMARILLO,
                        "keyframes": [{"t": 0, "rotacion": 0, "escala": 0.9}, {"t": dur, "rotacion": 50, "escala": 1.15,
                                                                                "easing": "lineal"}]}]
    sfx: list[tuple[float, str]] = []
    fondo_el: list[dict] = []
    if tipo == "gigante":
        els.append(_objeto(obj, x=540, y=Y_OBJETO + 150, escala=0.5,
                           keyframes=[{"t": 0, "escala": 0.5, "rotacion": -6},
                                      {"t": dur * 0.5, "escala": 2.4, "rotacion": 4, "easing": "rebote"},
                                      {"t": dur, "escala": 3.4, "rotacion": -3, "easing": "suave"}]))
        sfx.append((0.05, "boing"))
    elif tipo == "explota":
        kf = [{"t": 0, "escala": 1.3, "rotacion": 0}]
        for c in cortes:
            kf += [{"t": round(c + 0.02, 3), "escala": 1.0}, {"t": round(c + 0.2, 3), "escala": 2.3, "rotacion": rnd.uniform(-12, 12),
                                                               "easing": "rebote"}]
        els.append(_objeto(obj, x=540, y=Y_OBJETO, escala=1.3, keyframes=sorted(kf, key=lambda k: k["t"])))
        for c in cortes:
            for k in range(6):   # pedazos de colores que salen volando
                ang = math.radians(rnd.uniform(0, 360))
                els.append({"tipo": "prop", "nombre": "destello", "x": 540, "y": Y_OBJETO, "escala": 0.3,
                            "color": (P.ROJO, P.AMARILLO, P.AZUL, P.VERDE)[k % 4], "desde": round(c, 3), "hasta": round(c + 0.8, 3),
                            "keyframes": [{"t": c, "x": 540, "y": Y_OBJETO, "escala": 0.3},
                                          {"t": c + 0.75, "x": round(540 + math.cos(ang) * 520, 1),
                                           "y": round(Y_OBJETO + math.sin(ang) * 420, 1), "escala": 0.7,
                                           "rotacion": 200, "easing": "salida"}]})
        sfx.append((0.0, "explosion"))
    elif tipo == "multiplica":
        puestos = [(540, Y_OBJETO)] + [(540 + 300 * math.cos(math.radians(a)), Y_OBJETO + 330 * math.sin(math.radians(a)))
                                       for a in range(0, 360, 45)]
        for k, (x, y) in enumerate(puestos):
            t = round(k * dur / (len(puestos) + 1), 3)
            els.append(_objeto(obj, x=round(x, 1), y=round(max(ac.BANDA_SUBTITULOS + 380, y), 1), escala=0.9 if k else 1.4,
                               desde=t, keyframes=[{"t": t, "escala": 0.05, "rotacion": rnd.uniform(-30, 30)},
                                                   {"t": t + 0.22, "escala": 0.9 if k else 1.4, "rotacion": 0, "easing": "rebote"}]))
            sfx.append((t, "pop"))
    elif tipo == "vuela":
        kf = []
        for j, c in enumerate(cortes):
            de, a = (-200, 1280) if j % 2 == 0 else (1280, -200)
            seg = dur / n
            kf += [{"t": round(c, 3), "x": de, "y": Y_OBJETO + 200, "rotacion": 0},
                   {"t": round(c + seg * 0.5, 3), "x": 540, "y": Y_OBJETO - 250, "rotacion": 180 if j % 2 == 0 else -180,
                    "easing": "salida"},
                   {"t": round(c + seg - 0.02, 3), "x": a, "y": Y_OBJETO + 150, "rotacion": 360 if j % 2 == 0 else -360,
                    "easing": "entrada"}]
        els.append(_objeto(obj, x=-200, y=Y_OBJETO, escala=1.6, keyframes=kf))
        lin = ac.estela(kf, 0.0, dur)
        if lin:
            els.insert(1, lin)
        sfx += [(round(c, 3), "whoosh") for c in cortes]
    else:   # multitud: la gente atrás peleándose por el objeto, que salta arriba de las cabezas
        e = ac.Escena(dur, semilla=semilla, fondo=fondo)
        e.multitud(8)
        fondo_el = e.fondo_el
        kf = []
        t = 0.0
        while t < dur:
            kf += [{"t": round(t, 3), "y": Y_OBJETO - 80, "rotacion": -10},
                   {"t": round(t + 0.25, 3), "y": Y_OBJETO - 300, "rotacion": 10, "easing": "salida"}]
            t += 0.5
        els.append(_objeto(obj, x=540, y=Y_OBJETO - 80, escala=1.5, keyframes=kf))
        sfx.append((0.1, "aplausos"))
    for c in cortes:          # en cada corte: golpe, polvo y destellos (más detalle que el resto del video)
        sfx.append((round(c + 0.02, 3), "golpe"))
        els += ac.polvo(540 + rnd.uniform(-120, 120), Y_OBJETO + 260, c + 0.02, rnd, n_=5)
        els += ac.destellos(c + 0.05, rnd, (540, Y_OBJETO), n_=4)
    if texto:
        els.append({"tipo": "gancho", "texto": texto, "y": Y_TEXTO_GANCHO, "modo": "palabras", "tam": 110, "desde": 0.0})
    tramos = [(1.0, 1.08, 0, 0, 0), (1.55, 1.7, 0, Y_OBJETO - 960, 3), (2.0, 2.15, 0, Y_OBJETO - 960, -4)][:n]
    camara = camara_cortes(dur, tramos)
    for c in cortes[1:]:      # el corte pega: un sacudón corto
        for i in range(4):
            a = 18 * (1 - i / 4)
            camara.append({"t": round(c + 0.03 + i * 0.05, 3), "x": round(a * (1 if i % 2 else -1), 1), "easing": "lineal"})
    camara.sort(key=lambda k: float(k["t"]))
    esc_d = {"duracion": dur, "fondo": {"tipo": fondo, "semilla": semilla}, "transicion": {"tipo": "corte", "duracion": 0.25},
             "camara": camara, "elementos": fondo_el + els, "tono": 0.0, "gancho_v3": tipo}
    return esc_d, sorted((round(t, 3), s) for t, s in sfx if 0 <= t < dur)


def opciones_de(d: dict) -> list[dict]:
    """Las 3 opciones de gancho del guion (tipo válido y 3 a 5 palabras)."""
    out = []
    for o in d.get("ganchos") or []:
        if o.get("tipo") in TIPOS and 3 <= len(str(o.get("texto") or "").split()) <= 5:
            out.append({"tipo": o["tipo"], "texto": str(o["texto"]).strip()})
    return out[:3]


def _palabras(t: str) -> set[str]:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    out, actual = set(), ""
    for ch in t + " ":
        if ch.isalnum():
            actual += ch
        else:
            if len(actual) >= 3 or actual.isdigit():
                out.add(actual)
            actual = ""
    return out


def sin_textos_repetidos(esc_d: dict, frase: str) -> list[str]:
    """Santi, 2026-11-16: ningún texto en pantalla se repite ni se pisa con otro. Lo que ya dice el subtítulo (la voz)
    no va también grande (una cifra, un texto de la escena); un solo texto grande a la vez (el dato le gana al texto
    de la escena); el rótulo (año · lugar) baja para no quedar pegado a los subtítulos. Devuelve lo que sacó."""
    dichas = _palabras(frase)
    for el in esc_d.get("elementos") or []:     # lo que dice el rótulo tampoco se repite en otro texto
        if el.get("tipo") == "prop" and el.get("nombre") == "rotulo":
            dichas |= _palabras(el.get("texto"))
    sacados, quedan, hay_dato = [], [], False
    for el in esc_d.get("elementos") or []:
        nombre = el.get("nombre") if el.get("tipo") == "prop" else el.get("tipo")
        if nombre in ("dato", "gancho"):
            texto = str(el.get("texto") or "").split("|")[0]
            suyas = _palabras(texto)
            if suyas and suyas <= dichas | {p for p in suyas if not p.isdigit() and len(p) < 4}:
                sacados.append(texto)
                continue
            if nombre == "gancho" and hay_dato:
                sacados.append(texto)
                continue
            hay_dato = hay_dato or nombre == "dato"
        if nombre == "rotulo":
            el["y"] = Y_ROTULO
        quedan.append(el)
    # el texto de la escena va después del dato en la lista: si quedó uno de cada uno, sale el de la escena
    if hay_dato:
        textos = [el for el in quedan if el.get("tipo") == "gancho"]
        for el in textos:
            quedan.remove(el)
            sacados.append(str(el.get("texto") or ""))
    esc_d["elementos"] = quedan
    return sacados
