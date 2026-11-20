"""Biblioteca BASE de Así Nació (Santi, 2026-11-20: "reusar escenas cuando sirven y crear nuevas solo cuando hace
falta").

10 escenas armadas y probadas una por una contra el estándar, que el guion usa POR DEFECTO cambiando el producto (en
su versión de esa época: `fiel.de_la_escena`), los personajes según el rol y el año (`acciones.vestir`), la
decoración (el fondo y el año) y los textos:

    gancho (escena 1, automático: gancho_v3) · taller_inventor · fabrica_produce · vender_tienda · apreton_manos ·
    crisis · exito_multitud · producto_en_uso · lanzamiento · cierre_tito

El apretón ya estaba (uso_v3); la fábrica y la tienda se rehicieron acá (la gente grande, la línea o el mostrador
adelante) y pisan a las de escenas_lib. Cada constructor recibe lo mismo que los de `escenas_lib` y devuelve
{elementos, fondo, camara, sfx, actores} (+ multitud, momento, fondo_fijo). Cada una trae su cámara: plano medio de la
gente → de cerca a lo que importa."""

from __future__ import annotations

from . import acciones as ac

# las 10 de la biblioteca base, en el orden en que suelen aparecer en una historia (para el guion y la hoja)
BASE = ("gancho", "taller_inventor", "fabrica_produce", "vender_tienda", "apreton_manos", "crisis", "exito_multitud",
        "producto_en_uso", "lanzamiento", "cierre_tito")

DESCRIPCION = {
    "taller_inventor": ("el inventor o fundador trabaja en su taller o laboratorio detrás de su mesa, con el producto "
                        "(o lo que hacían entonces) en las manos, y le llega la idea (inventar, probar, empezar, el "
                        "primer prototipo)", ("lejos", "cerca"), "taller"),
    "crisis": ("de noche en la oficina: alguien se agarra la cabeza detrás del escritorio con el papel de las ventas "
               "y el gráfico que cae (quiebra, deudas, fracaso, nadie compraba, un problema)", ("cerca",), "oficina"),
    "exito_multitud": ("una multitud en la calle, los de adelante con el producto en las manos festejando (éxito, "
                       "furor, todos lo querían, millones lo usan)", ("lejos",), "ciudad"),
    "producto_en_uso": ("dos personas usan el producto de verdad en el lugar donde se usa (la casa, la cocina, la "
                        "cancha): lo que hace el producto y para qué sirve", ("cerca", "lejos"), "casa"),
    "lanzamiento": ("la presentación o la publicidad: alguien presenta el producto sobre un pedestal en un escenario, "
                    "con flashes y la gente aplaudiendo (salió a la venta, el lanzamiento, el anuncio, la publicidad)",
                    ("lejos",), "escenario"),
    "cierre_tito": ("el cierre: el Abuelo Tito en su taller saluda al lado del producto (la última frase, el remate)",
                    ("frente",), "taller"),
    # las dos de antes, rehechas (la descripción para el guion es la misma idea)
    "fabrica_produce": ("la línea de producción: obreros detrás de la cinta con el producto que avanza uno tras otro "
                        "(fabricar en serie, producir, la fábrica)", ("lejos", "cerca"), "fabrica"),
    "vender_tienda": ("la tienda o el almacén: el vendedor detrás del mostrador con el producto y la caja registradora, "
                      "una clienta que paga (vender, salir a la venta, la primera venta)", ("lejos", "cerca"), "tienda"),
}

MEDIO = 1.7                       # el zoom del plano medio de la gente de pie
Y_CABEZA = ac.PISO - 430          # más o menos la cabeza de un adulto de pie
Y_MEDIO = 1355                    # el centro del plano medio (con MEDIO se ve de y 790 al piso)


def _el(nombre, x, y, **kw) -> dict:
    return {"tipo": "prop", "nombre": nombre, "x": round(x, 1), "y": round(y, 1), **kw}


def _rol(spec: dict, k: int, defecto: str, genero: str = "", edad: str = "") -> dict:
    actores = spec.get("actores") or []
    a = actores[k] if k < len(actores) else {}
    return {"rol": a.get("rol") or defecto, "genero": a.get("genero") or genero, "edad": a.get("edad") or edad}


def _persona(e: "ac.Escena", a: dict, accion: str, x: float, cara: str, k: int) -> dict:
    e.actor(a["rol"], accion, "centro", None, cara, k, x0=x, x1=x, genero=a["genero"], edad=a["edad"])
    return e.elementos[-1]


def _mesa(x: float = 540, escala: float = 0.72) -> dict:
    """La mesa DELANTE de la gente (sin `decorado`, que la mandaba atrás), más baja que las manos: con la mesa de
    tamaño normal la tapa quedaba encima de las manos y tapaba lo que tenían (el papel de la crisis, 2026-11-20)."""
    return _el("mesa", x, ac.PISO - 226 * escala, escala=escala, en_medio=True)


def esc_de(obj: str, alto_px: float) -> float:
    """La escala para que `obj` mida `alto_px` de alto (los dibujos guardados vienen en una caja de ~300 px; los de
    código tienen su caja en acciones.CAJAS): la botella fiel salía diminuta en la mano con la escala de la genérica."""
    c = ac.CAJAS.get(obj)
    alto = (c[2] - c[1]) if c else 300.0
    return round(alto_px / max(80.0, alto), 3)


def _en_mano(e: "ac.Escena", obj: str, quien: int | None = None, alto_px: float = 190) -> None:
    """El producto en las manos del personaje `quien` (o del primero libre), a todo color, a la altura de la panza y
    más chico: nunca tapando la cara (Coca-Cola, 2026-11-20)."""
    if quien is not None:
        for k, a in enumerate(e.actores):
            if k != quien:
                a["_l"] = a.get("lleva")
                a["lleva"] = a.get("lleva") or "_"
    n = len(e.elementos)
    e.objeto(obj, "quieto", "centro", soporte="mano")
    for el in e.elementos[n:]:
        if el.get("en_mano"):
            el["escala"] = esc_de(obj, alto_px)
            el["color"] = True
    if quien is not None:
        for k, a in enumerate(e.actores):
            if k != quien:
                a["lleva"] = a.pop("_l")
                if not a["lleva"]:
                    a.pop("lleva")


def _cam(dur: float, *focos: tuple[float, float, float]) -> list[dict]:
    """La cámara propia de la escena (no la de gancho_v3.planos): un plano por foco (x, y, zoom), en partes iguales,
    con un zoom lento adentro de cada uno, sin salirse nunca del cuadro."""
    from . import gancho_v3 as gv

    tramos = []
    for x, y, z in focos:
        mx, my = 540 / z, 960 / z
        x, y = min(max(x, mx), 1080 - mx), min(max(y, my), 1920 - my)
        tramos.append((z, z * 1.04, x - 540, y - 960, 0.0))
    return gv.camara_cortes(dur, tramos)


def _de_perfil(e: "ac.Escena", k: int, lado: int, a: str, b: str, dur: float, paso: float = 0.4) -> tuple[float, float]:
    """El personaje k de perfil QUIETO (lado 1 = mira a la derecha) alternando los gestos a y b (los "p_..." de
    personajes), sin lo que el rol le pone en las manos. Devuelve dónde queda su mano de adelante con el gesto a
    (coordenadas de la escena), para poner ahí lo que agarra (biblioteca base, 2026-11-20: de frente se leían "parados
    mirando a cámara sin hacer nada")."""
    from dataclasses import replace as _r

    from . import personajes as per

    el = e.actores[k]
    el["perfil"] = lado
    gestos, t, j = [{"t": 0, "gesto": a}], 0.2, 0
    while t < dur:
        gestos.append({"t": round(t, 3), "gesto": b if j % 2 == 0 else a})
        t += paso
        j += 1
    el["gestos"] = gestos
    for clave in ("objeto_rol", "manos"):
        el.pop(clave, None)
    el["lleva"] = el.get("lleva") or "_"
    pj = per.ELENCO.get(el["nombre"], per.ELENCO["narrador"])
    alto = (el.get("cambios") or {}).get("alto_cuerpo")
    if alto:
        pj = _r(pj, alto_cuerpo=float(alto))
    lx, ly = pj.mano_perfil(*per.GESTOS[a]["der"])
    esc = float(el.get("escala", 0.74))
    return float(el["x"]) + lado * esc * lx, ac.PISO + esc * ly


def _arriba(e: "ac.Escena", k: int, dur: float, gesto: str = "senalar") -> tuple[float, float]:
    """El personaje k de frente muestra el producto con el brazo estirado (festeja con él). Devuelve dónde va."""
    from . import personajes as per

    el = e.actores[k]
    el["gestos"] = [{"t": 0, "gesto": gesto}]
    for clave in ("objeto_rol", "manos"):
        el.pop(clave, None)
    el["lleva"] = el.get("lleva") or "_"
    pj = per.ELENCO.get(el["nombre"], per.ELENCO["narrador"])
    brazo = pj.brazos(per.estado_de_gesto(gesto))[1]
    esc = float(el.get("escala", 0.74))
    return float(el["x"]) + esc * brazo[-1][0], ac.PISO + esc * brazo[-1][1] - 30


def _agarrado(obj: str, xy: tuple[float, float], alto_px: float = 170, **kw) -> dict:
    """El producto en la mano de alguien de perfil (en_mano: así nadie le agrega otro en el pecho)."""
    return _el(obj, xy[0], xy[1] - 10, escala=esc_de(obj, alto_px), color=True, en_mano=True, **kw)


# ---- las escenas -----------------------------------------------------------------------------------------------
def _taller_inventor(plano, spec, dur, i, obj, rnd):
    """De perfil en su mesa de trabajo, con el producto en las manos trabajándolo; papeles con planos en la mesa; a la
    mitad, la lamparita de la idea arriba de la cabeza. Un ayudante enfrente si el guion trae dos."""
    e = ac.Escena(dur, semilla=i)
    lab = str(spec.get("fondo") or "") in ("laboratorio", "hospital")
    _persona(e, _rol(spec, 0, "cientifica" if lab else "inventor"), "fabricar", 360, "normal", 0)
    mano = _de_perfil(e, 0, 1, "p_sostener_a", "p_sostener_b", dur)
    dos = len(spec.get("actores") or []) > 1
    if dos:
        _persona(e, _rol(spec, 1, "obrero"), "trabajar", 800, "feliz", 1)
        _de_perfil(e, 1, -1, "p_dar", "p_dar_b", dur, 0.5)
    els = list(e.elementos)
    els += [_mesa(mano[0] + 40), _agarrado(obj, mano, keyframes=[{"t": 0, "rotacion": -8},
                                                                  {"t": dur, "rotacion": 8, "easing": "suave"}]),
            _el("papel_firma", mano[0] + 150, ac.PISO - 160, escala=0.6, forma=1)]
    t_idea = round(dur * 0.45, 2)
    els.append(_el("lamparita", 360, Y_CABEZA - 230, escala=0.55, desde=t_idea,
                   keyframes=[{"t": t_idea, "escala": 0.15}, {"t": t_idea + 0.25, "escala": 0.55, "easing": "rebote"}]))
    els += ac.destellos(t_idea + 0.1, rnd, (360, Y_CABEZA - 230), n_=3)
    return {"elementos": els, "fondo": "laboratorio" if lab else "taller",
            "camara": _cam(dur, (560 if dos else 470, Y_MEDIO, MEDIO), (mano[0], mano[1] - 60, 2.3)),
            "sfx": [(0.3, "tac"), (0.9, "tac"), (t_idea, "ding")] + e.sfx, "actores": e.actores}


def _fabrica_produce(plano, spec, dur, i, obj, rnd):
    """La línea de producción: la cinta adelante (de su época) con el producto que avanza uno tras otro, y dos obreros
    de perfil, enfrentados, con las manos sobre la cinta trabajando el producto. Las máquinas son las del fondo."""
    e = ac.Escena(dur, semilla=i)
    manos = []
    for k, (x, defecto, gen) in enumerate(((260, "obrero", "hombre"), (640, "obrera", "mujer"))):
        _persona(e, _rol(spec, k, defecto, gen), "trabajar", x, "normal", k)
        manos.append(_de_perfil(e, k, 1, "p_cinta_a", "p_cinta_b", dur, 0.35))   # los dos para el mismo lado: la línea
    els = list(e.elementos) + [_agarrado(obj, m, 120) for m in manos]
    anio = int(spec.get("anio_escena") or 2026)
    els.append({"tipo": "prop", "nombre": "cinta_frente", "x": 540, "y": ac.Y_CINTA, "linea": True,
                "forma": 1 if anio < 1940 else 0})
    n_ = 5
    for k in range(n_):
        t0 = round(-dur + k * 2 * dur / n_, 2)      # ya hay producto en la cinta desde el primer cuadro
        els.append({"tipo": "prop", "nombre": obj, "x": -140, "y": ac.Y_CINTA - 40, "escala": esc_de(obj, 120),
                    "linea": True, "color": True,
                    "keyframes": [{"t": t0, "x": -140}, {"t": t0 + 2 * dur, "x": 1220, "easing": "lineal"}]})
    sfx = [(0.0, "maquina")] + [(round(0.4 + k * dur / 4, 2), "tac") for k in range(4)]
    return {"elementos": els, "fondo": "fabrica",
            "camara": _cam(dur, (540, Y_MEDIO, 1.55), (540, ac.Y_CINTA - 120, 2.2)), "sfx": sfx + e.sfx,
            "actores": e.actores}


def _vender_tienda(plano, spec, dur, i, obj, rnd):
    """El almacén o la tienda: el vendedor detrás del mostrador le da el producto a una clienta (los dos de perfil,
    enfrentados, las manos en el producto), la caja registradora y más producto sobre el mostrador. Sin billetes: con
    un billete en la mano se leía como un "$" en el pecho (2026-11-20)."""
    e = ac.Escena(dur, semilla=i)
    _persona(e, _rol(spec, 0, "vendedor", "hombre"), "vender", 780, "feliz", 0)
    m_v = _de_perfil(e, 0, -1, "p_dar", "p_dar", dur)
    _persona(e, _rol(spec, 1, "cliente", "mujer"), "comprar", 450, "feliz", 1)
    m_c = _de_perfil(e, 1, 1, "p_dar", "p_dar", dur)
    e.actores[1]["x"] = round(float(e.actores[1]["x"]) + (m_v[0] - 18 - m_c[0]), 1)     # la mano justo en el producto
    m_c = (m_v[0] - 18, m_c[1])
    els = list(e.elementos)
    y_m = ac.PISO - 120
    medio = (m_v[0] - 9, (m_v[1] + m_c[1]) / 2)
    els += [_el("mostrador", 840, y_m, escala=1.0, en_medio=True),
            _el("caja_registradora", 950, y_m - 150, escala=0.7),
            _el(obj, 790, y_m - 140, escala=esc_de(obj, 140), color=True),
            _agarrado(obj, medio, 170)]
    t_c = round(dur * 0.55, 2)
    return {"elementos": els, "fondo": "tienda",
            "camara": _cam(dur, (570, Y_MEDIO, 1.6), (medio[0], medio[1] - 80, 2.1)),
            "sfx": e.sfx + [(t_c, "caja_registradora")], "actores": e.actores}


def _crisis(plano, spec, dur, i, obj, rnd):
    """De noche, en la oficina: una persona detrás del escritorio se agarra la cabeza; sobre el escritorio el papel de
    las ventas y el producto olvidado; al lado de la cabeza, el gráfico que se viene abajo."""
    e = ac.Escena(dur, semilla=i)
    # mira el papel de las ventas que tiene en las manos (con las manos en la nuca se leía "relajado", 2026-11-20)
    _persona(e, _rol(spec, 0, "empresario"), "usar", 420, "triste", 0)
    mano = _de_perfil(e, 0, 1, "p_sostener_a", "p_sostener_b", dur, 0.7)
    els = list(e.elementos) + [_el("papel_firma", mano[0] + 10, mano[1] - 20, escala=0.7, forma=1, en_mano=True,
                                   rotacion=-70)]
    els += [_mesa(540), _el(obj, 610, ac.PISO - 163 - 75, escala=esc_de(obj, 150), color=True)]
    t_g = 0.3
    els.append(_el("grafico_baja", 790, Y_CABEZA - 60, escala=0.75, desde=t_g,
                   keyframes=[{"t": t_g, "escala": 0.2}, {"t": t_g + 0.3, "escala": 0.75, "easing": "rebote"}]))
    return {"elementos": els, "fondo": "oficina", "momento": "noche",
            "camara": _cam(dur, (560, Y_MEDIO, MEDIO), (560, Y_CABEZA + 40, 2.2)),
            "sfx": [(t_g, "boing")] + e.sfx, "actores": e.actores}


def _exito_multitud(plano, spec, dur, i, obj, rnd):
    """En la calle, tres personas adelante con el producto en las manos festejando, y la multitud atrás aplaudiendo;
    destellos y aplausos."""
    e = ac.Escena(dur, semilla=i)
    gente = [(_rol(spec, 0, "joven", "mujer"), 220), (_rol(spec, 1, "cliente", "hombre"), 460),
             (_rol(spec, 2, "joven", "hombre"), 880)]
    for k, (a, x) in enumerate(gente):
        _persona(e, a, "usar" if k == 1 else "festejar", x, "feliz", k)
    for k, lado in ((0, 1), (2, -1)):
        _de_perfil(e, k, lado, "p_aplaudir_a", "p_aplaudir_b", dur, 0.2)
    arriba = _arriba(e, 1, dur)
    els = list(e.elementos) + [_agarrado(obj, arriba, 230, keyframes=[{"t": 0, "rotacion": -8},
                                                                       {"t": dur, "rotacion": 8, "easing": "suave"}])]
    for t in (0.4, dur * 0.6):
        els += ac.destellos(t, rnd, (540, Y_CABEZA - 80), n_=4)
    return {"elementos": els, "fondo": "ciudad", "camara": _cam(dur, (540, Y_MEDIO - 60, 1.4), (540, Y_MEDIO, MEDIO)),
            "sfx": e.sfx + [(0.1, "aplausos")], "actores": e.actores, "multitud": True}


import re as _re  # noqa: E402

# lo que se usa llevándoselo a la boca (una bebida o una comida): en uso, se toma o se come
_SE_TOMA = _re.compile(r"bebid|gaseos|refresc|cerveza|vino|caf[eé]|\bt[eé]\b|jugo|leche|agua|comid|aliment|golosin|"
                       r"chocolat|galle|snack|helad|caramel|hamburgues|pizza|cereal|tomar|tom[oa]ba", _re.I)
_LUGAR_USO = {"cocina", "casa", "estadio", "playa", "campo", "oficina", "hospital", "laboratorio", "escuela"}


def _producto_en_uso(plano, spec, dur, i, obj, rnd):
    """Dos personas de perfil, enfrentadas, usando el producto donde se usa: una lo tiene en las manos y lo usa, la
    otra le muestra el suyo."""
    e = ac.Escena(dur, semilla=i)
    fondo = str(spec.get("fondo") or "")
    fondo = fondo if fondo in _LUGAR_USO else "casa"
    _persona(e, _rol(spec, 0, "joven", "mujer"), "usar", 360, "feliz", 0)
    boca = bool(_SE_TOMA.search(str(spec.get("_categoria") or "") + " " + str(spec.get("frase") or "")))
    m1 = _de_perfil(e, 0, 1, *(("p_tomar_a", "p_tomar_b") if boca else ("p_sostener_a", "p_sostener_b")), dur, 0.6)
    _persona(e, _rol(spec, 1, "joven", "hombre"), "usar", 740, "sorprendido", 1)
    m2 = _de_perfil(e, 1, -1, "p_dar", "p_dar_b", dur, 0.5)
    els = list(e.elementos)
    els += [_agarrado(obj, m1, keyframes=[{"t": 0, "rotacion": -125 if boca else -10},
                                          {"t": dur, "rotacion": -110 if boca else 10, "easing": "suave"}]),
            _agarrado(obj, m2, 150)]
    if fondo in ("cocina", "casa", "oficina"):
        els.append(_mesa(550, 0.62))
    els += ac.destellos(dur * 0.5, rnd, (550, Y_CABEZA), n_=3)
    return {"elementos": els, "fondo": fondo, "camara": _cam(dur, (550, Y_MEDIO, MEDIO), (m1[0] + 60, m1[1] - 90, 2.2)),
            "sfx": e.sfx + [(round(dur * 0.5, 2), "ding")], "actores": e.actores}


def _lanzamiento(plano, spec, dur, i, obj, rnd):
    """En un escenario: el producto grande sobre un pedestal en el medio, girando apenas, quien lo presenta al
    costado señalándolo, flashes de fotos y la gente aplaudiendo atrás."""
    e = ac.Escena(dur, semilla=i)
    _persona(e, _rol(spec, 0, "empresario"), "senalar", 300, "feliz", 0)
    _de_perfil(e, 0, 1, "p_senalar", "p_senalar_b", dur, 0.6)
    els = list(e.elementos)
    y_ped = ac.PISO - 226 * 0.9
    els += [_mesa(640, 0.9),
            _el(obj, 640, y_ped - 130, escala=esc_de(obj, 260), color=True, fase=1.0,
                keyframes=[{"t": 0, "rotacion": -4}, {"t": dur, "rotacion": 4, "easing": "suave"}]),
            # el cartel de la publicidad colgado atrás, con el producto dibujado (con texto salía como un prohibido)
            _el("cartel", 640, ac.PISO_PARED - 230, escala=1.0, color="#f4e2b8"),   # el palo llega al piso
            _el(obj, 640, ac.PISO_PARED - 230 - 55, escala=esc_de(obj, 150), color=True)]
    sfx = []
    for k in range(3):       # flashes de las cámaras
        t = round(0.3 + k * (dur - 0.6) / 3, 2)
        # a la derecha del producto: cerca de la mano del que presenta parecía que tenía algo blanco en la mano
        els += ac.destellos(t, rnd, (760 + rnd.uniform(-40, 120), y_ped - 220), n_=3)
        sfx.append((t, "pop"))
    return {"elementos": els, "fondo": "escenario", "fondo_fijo": True,
            "camara": _cam(dur, (480, Y_MEDIO - 40, 1.5), (640, y_ped - 120, 2.1)),
            "sfx": e.sfx + sfx + [(0.1, "aplausos")], "actores": e.actores, "multitud": True}


def _cierre_tito(plano, spec, dur, i, obj, rnd):
    """Tito en su taller, de hoy, saludando, con el producto sobre su mesa al lado que brilla."""
    tito = {"tipo": "tito", "x": 360, "y": ac.PISO + 20, "escala": 0.7, "habla": True,
            "poses": [{"t": 0, "pose": "senala"}]}
    y_m = ac.PISO - 226 * 0.9
    els = [tito, _mesa(780, 0.9), _el(obj, 780, y_m - 110, escala=esc_de(obj, 220), color=True,
                                     keyframes=[{"t": 0, "rotacion": -5}, {"t": dur, "rotacion": 5, "easing": "suave"}])]
    els += ac.destellos(dur * 0.4, rnd, (780, y_m - 220), n_=4)
    return {"elementos": els, "fondo": "taller", "fondo_fijo": True,
            "camara": _cam(dur, (560, Y_MEDIO - 60, 1.5), (520, Y_MEDIO, MEDIO)),
            "sfx": [(round(dur * 0.4, 2), "ding")], "actores": []}


CONSTRUCTORES = {"taller_inventor": _taller_inventor, "crisis": _crisis, "exito_multitud": _exito_multitud,
                 "producto_en_uso": _producto_en_uso, "lanzamiento": _lanzamiento, "cierre_tito": _cierre_tito,
                 "fabrica_produce": _fabrica_produce, "vender_tienda": _vender_tienda}
CON_CAMARA = set(CONSTRUCTORES)      # traen su cámara: gancho_v3.planos no la pisa
