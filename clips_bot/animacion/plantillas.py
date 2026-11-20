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
    "taller_inventor": ("el origen: el inventor o fundador trabaja concentrado en SU lugar, que sale de su oficio "
                        "(químico o científico: laboratorio con frascos y tubos; artesano o inventor: taller; empresario: "
                        "oficina escribiendo el plan), con el producto (o lo que hacían entonces) en las manos, y le "
                        "llega la idea (inventar, probar, empezar, el primer prototipo)", ("lejos", "cerca"), "taller"),
    "crisis": ("de noche en la oficina: alguien se agarra la cabeza detrás del escritorio con el papel de las ventas "
               "y el gráfico que cae (quiebra, deudas, fracaso, nadie compraba, un problema)", ("cerca",), "oficina"),
    "exito_multitud": ("el éxito que se entiende de un vistazo: el protagonista salta de felicidad en la tienda, al lado el "
                       "gráfico de ventas que sube y el cartel de ¡AGOTADO! (éxito, furor, todos lo querían, millones lo "
                       "usan, se agotó)", ("lejos",), "tienda"),
    "producto_en_uso": ("una o dos personas usan el producto de verdad en el lugar donde se usa (la casa, la cocina, la "
                        "cancha): una bebida se toma (la botella a la boca), una comida se come; lo que hace el "
                        "producto y para qué sirve", ("cerca", "lejos"), "casa"),
    "lanzamiento": ("la presentación o la publicidad: alguien presenta el producto sobre un pedestal en un escenario, "
                    "con flashes de fotos (salió a la venta, el lanzamiento, el anuncio, la publicidad)",
                    ("lejos",), "escenario"),
    "cierre_tito": ("el cierre: el Abuelo Tito en su taller señala el producto (la última frase, el remate)",
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
        tramos.append((z, z * 1.09, x - 540, y - 960, 0.0))     # un acercamiento que se nota (Santi, 2026-11-20)
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


def _agarrado(obj: str, xy: tuple[float, float], alto_px: float = 170, quien: dict | None = None, **kw) -> dict:
    """El producto en la mano de alguien de perfil (en_mano: así nadie le agrega otro en el pecho). Con `quien` (el
    actor que lo agarra) los dedos se cierran ENCIMA del objeto (`agarre`: acciones.escena_accion agrega los dedos con
    su piel después del objeto; Santi, 2026-11-20)."""
    el = _el(obj, xy[0], xy[1] - 10, escala=esc_de(obj, alto_px), color=True, en_mano=True, **kw)
    if quien is not None:
        quien["_sostiene"] = True
        el["agarre"] = {"piel": _pj(quien).piel, "lado": int(quien.get("perfil") or 1),
                        "escala": round(float(quien.get("escala", 0.74)) * 1.15, 3)}
    return el


# ---- las escenas -----------------------------------------------------------------------------------------------
import re as _re  # noqa: E402

# El lugar del origen sale de quién es el protagonista (Santi, 2026-11-20): químico o científico en el laboratorio
# (frascos, tubos, pizarrón), artesano o inventor en el taller, empresario en la oficina.
_LAB = _re.compile(r"qu[ií]mic|farmac|cient[ií]fic|m[ée]dic|bioqu|laborator|enfermer|bot[aá]nic|f[ií]sic", _re.I)
_OFICINA = _re.compile(r"empresari|banquer|comerciant|ejecutiv|abogad|contador|publicist|vendedor|fundador de una empresa",
                       _re.I)


def lugar_de_oficio(spec: dict) -> str:
    """laboratorio | oficina | taller según el oficio del protagonista (el del guion, su rol o el lugar pedido)."""
    gente = spec.get("actores") or []
    texto = " ".join([str(spec.get("_oficio") or ""), str(spec.get("oficio") or ""),
                      str((gente[0] if gente else {}).get("rol") or "")])
    fondo = str(spec.get("fondo") or "")
    if _LAB.search(texto) or fondo in ("laboratorio", "hospital"):
        return "laboratorio"
    if _OFICINA.search(texto) or fondo == "oficina":
        return "oficina"
    return "taller"


def _taller_inventor(plano, spec, dur, i, obj, rnd):
    """El origen: el protagonista de perfil en SU lugar de trabajo, con el producto (o lo de esa época) en las manos y
    concentrado; a la mitad le llega la idea (la lamparita). El lugar sale del oficio: laboratorio (frascos, tubos y el
    pizarrón del fondo), oficina (escribe el plan en el escritorio) o taller (planos en la mesa)."""
    e = ac.Escena(dur, semilla=i)
    lugar = lugar_de_oficio(spec)
    defecto = {"laboratorio": "cientifica", "oficina": "empresario"}.get(lugar, "inventor")
    _persona(e, _rol(spec, 0, defecto), "fabricar", 360, "concentrado", 0)
    els_extra = []
    if lugar == "oficina":      # escribe el plan: la lapicera en la mano, el papel en el escritorio, el producto al lado
        mano = _de_perfil(e, 0, 1, "p_escribir_a", "p_escribir_b", dur, 0.22)
        els_extra += [_mesa(mano[0] + 30), _el("papel_firma", mano[0] + 10, ac.PISO - 226 * 0.72 - 8, escala=0.6, forma=1),
                      _agarrado("lapicera", mano, 90, quien=e.actores[0]),
                      _el(obj, mano[0] + 190, ac.PISO - 226 * 0.72 - 70, escala=esc_de(obj, 150), color=True)]
    else:
        mano = _de_perfil(e, 0, 1, "p_sostener_a", "p_sostener_b", dur)
        els_extra += [_mesa(mano[0] + 40),
                      _agarrado(obj, mano, quien=e.actores[0], keyframes=[{"t": 0, "rotacion": -8},
                                                                         {"t": dur, "rotacion": 8, "easing": "suave"}])]
        y_mesa = ac.PISO - 226 * 0.72
        if lugar == "laboratorio":
            # MEZCLA (Pepsi, 2026-11-20: "no se ve la acción de mezclar"): vuelca el matraz sobre el producto que está
            # en la mesa, con el chorro de color; los tubos al lado
            els_extra.pop()                           # el producto no va en la mano: va en la mesa, recibiendo
            mano = _de_perfil(e, 0, 1, "p_verter", "p_verter", dur, 9.0)
            # la boca del matraz inclinado 100° (178 px de alto a escala 130/200) cae sobre el producto
            boca = (mano[0] + 114, mano[1] - 10 + 20)
            alto_p = 110
            arriba_p = y_mesa - alto_p
            els_extra += [_el(obj, boca[0] + 6, y_mesa - alto_p / 2, escala=esc_de(obj, alto_p), color=True),
                          _agarrado("frasco", mano, 130, quien=e.actores[0],
                                    keyframes=[{"t": 0, "rotacion": 20}, {"t": 0.6, "rotacion": 100, "easing": "suave"}]),
                          _el("chorro", boca[0], boca[1], escala=round(max(0.2, (arriba_p - boca[1]) / 140), 3),
                              desde=0.65, color="#7fd36b"),
                          _el("tubos", mano[0] + 320, y_mesa, escala=0.5)]
        else:
            els_extra.append(_el("papel_firma", mano[0] + 150, ac.PISO - 160, escala=0.6, forma=1))
    dos = len(spec.get("actores") or []) > 1
    if dos:
        _persona(e, _rol(spec, 1, "obrero"), "trabajar", 840, "concentrado", 1)
        _de_perfil(e, 1, -1, "p_dar", "p_dar_b", dur, 0.5)
    els = list(e.elementos) + els_extra
    t_idea = round(dur * 0.45, 2)
    els.append(_el("lamparita", 360, Y_CABEZA - 230, escala=0.55, desde=t_idea,
                   keyframes=[{"t": t_idea, "escala": 0.15}, {"t": t_idea + 0.25, "escala": 0.55, "easing": "rebote"}]))
    els += ac.destellos(t_idea + 0.1, rnd, (360, Y_CABEZA - 230), n_=3)
    return {"elementos": els, "fondo": lugar,
            "camara": _cam(dur, (560 if dos else 470, Y_MEDIO, MEDIO), (mano[0], mano[1] - 60, 2.3)),
            "sfx": [(0.3, "tac"), (0.9, "tac"), (t_idea, "ding")] + e.sfx, "actores": e.actores}


def _fabrica_produce(plano, spec, dur, i, obj, rnd):
    """La línea de producción: la cinta adelante (de su época) con el producto que avanza uno tras otro, y dos obreros
    de perfil, enfrentados, con las manos sobre la cinta trabajando el producto. Las máquinas son las del fondo."""
    e = ac.Escena(dur, semilla=i)
    manos = []
    for k, (x, defecto, gen) in enumerate(((260, "obrero", "hombre"), (640, "obrera", "mujer"))):
        _persona(e, _rol(spec, k, defecto, gen), "trabajar", x, "concentrado", k)
        manos.append(_de_perfil(e, k, 1, "p_cinta_a", "p_cinta_b", dur, 0.35))   # los dos para el mismo lado: la línea
    els = list(e.elementos) + [_agarrado(obj, m, 120, quien=e.actores[k]) for k, m in enumerate(manos)]
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
            _agarrado(obj, medio, 170, quien=e.actores[0])]
    t_c = round(dur * 0.55, 2)
    return {"elementos": els, "fondo": "tienda",
            "camara": _cam(dur, (570, Y_MEDIO, 1.6), (medio[0], medio[1] - 80, 2.1)),
            "sfx": e.sfx + [(t_c, "caja_registradora")], "actores": e.actores}


def _crisis(plano, spec, dur, i, obj, rnd):
    """De noche, en la oficina: una persona detrás del escritorio se agarra la cabeza; sobre el escritorio el papel de
    las ventas y el producto olvidado; al lado de la cabeza, el gráfico que se viene abajo."""
    e = ac.Escena(dur, semilla=i)
    # mira el papel de las ventas que tiene en las manos (con las manos en la nuca se leía "relajado", 2026-11-20)
    _persona(e, _rol(spec, 0, "empresario"), "usar", 420, "devastado", 0)
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
    """El ÉXITO que se entiende en 1 segundo (Santi, 2026-11-20: "no una multitud genérica"): en la tienda, el
    protagonista salta de felicidad con los brazos arriba; al lado, el gráfico de ventas que SUBE y el cartel de
    ¡AGOTADO! sobre el mostrador vacío con la caja registradora sonando. Sin gente de relleno atrás."""
    e = ac.Escena(dur, semilla=i)
    _persona(e, _rol(spec, 0, "fundador"), "festejar", 270, "euforico", 0)
    el = e.actores[0]
    for clave in ("objeto_rol", "manos"):
        el.pop(clave, None)
    el["gestos"] = [{"t": 0, "gesto": "festejar"}]
    y_m = ac.PISO - 120
    t_g = 0.25
    els = list(e.elementos)
    els += [_el("mostrador", 760, y_m, escala=1.0, en_medio=True),
            _el("caja_registradora", 870, y_m - 150, escala=0.7, keyframes=[{"t": 0, "fase": 0.0},
                                                                             {"t": dur * 0.5, "fase": 1.0}], fase=0.0),
            _el(obj, 715, y_m - 140, escala=esc_de(obj, 150), color=True),       # la última que queda
            _el("grafico_sube", 640, Y_CABEZA - 170, escala=0.7, desde=t_g,
                keyframes=[{"t": t_g, "escala": 0.2}, {"t": t_g + 0.35, "escala": 0.7, "easing": "rebote"}]),
            _el("cartel_comic", 505, Y_CABEZA + 95, escala=0.45, texto="¡AGOTADO!", desde=round(dur * 0.4, 2),
                keyframes=[{"t": round(dur * 0.4, 2), "escala": 0.2},
                           {"t": round(dur * 0.4, 2) + 0.25, "escala": 0.45, "easing": "rebote"}])]
    for t in (0.4, dur * 0.6):
        els += ac.destellos(t, rnd, (300, Y_CABEZA - 120), n_=4)
    return {"elementos": els, "fondo": "tienda:vacia", "fondo_fijo": True,
            "camara": _cam(dur, (470, Y_MEDIO - 80, 1.45), (440, Y_MEDIO - 40, 1.6)),
            "sfx": e.sfx + [(0.1, "aplausos"), (round(dur * 0.5, 2), "caja_registradora")], "actores": e.actores}


# lo que se usa llevándoselo a la boca (una bebida o una comida): en uso, se toma o se come
_SE_TOMA = _re.compile(r"bebid|gaseos|refresc|cerveza|vino|caf[eé]|\bt[eé]\b|jugo|leche|agua|tomar|tom[oa]ba", _re.I)
_SE_COME = _re.compile(r"comid|aliment|golosin|chocolat|galle|snack|helad|caramel|hamburgues|pizza|cereal|comer|com[ií]a",
                       _re.I)
_LUGAR_USO = {"cocina", "casa", "estadio", "playa", "campo", "oficina", "hospital", "laboratorio", "escuela"}


def _pj(el: dict):
    """El personaje de un actor (con sus cambios: piel, alto)."""
    from . import personajes as per

    cambios = {k: v for k, v in (el.get("cambios") or {}).items() if k in per.Personaje.__dataclass_fields__}
    return per.personaje(el["nombre"], **cambios)


def _a_la_boca(e, k: int, obj: str, dur: float, comer: bool) -> list[dict]:
    """El ciclo COMPLETO de tomar o comer (Santi, 2026-11-20): el producto en el pecho → sube a la boca (la botella se
    inclina hacia la boca y la cabeza va para atrás; un bocado: la boca se abre) → baja; y otra vez. El producto sigue
    a la mano cuadro a cuadro (sus keyframes salen de los mismos gestos)."""
    from . import personajes as per

    el = e.actores[k]
    pj = _pj(el)
    lado = int(el.get("perfil") or 1)
    esc = float(el.get("escala", 0.74))
    abajo, arriba = ("p_comer_b", "p_comer_a") if comer else ("p_sostener_a", "p_tomar_alto")

    def pos(g):
        lx, ly = pj.mano_perfil(*per.GESTOS[g]["der"])
        return float(el["x"]) + lado * esc * lx, ac.PISO + esc * ly

    # tiempos: abajo 0 → sube 0,5 → arriba hasta 1,6 → baja 2,0 → abajo hasta 2,6 → sube… (ciclo de 2,6 s)
    gestos, kf, t = [], [], 0.0
    (xa, ya), (xb, yb) = pos(abajo), pos(arriba)
    if not comer:     # el pico de la botella en la boca: el cuerpo de la botella queda afuera, arriba
        xb, yb = xb + 20 * lado, yb - 15
    rot_a, rot_b = -8 * lado, (-128 if not comer else -30) * lado
    # el gesto tarda 0,3 s en llegar (timeline): sube de 0,2 a 0,5, queda arriba, baja de 1,7 a 2,0
    while t < dur:
        gestos += [{"t": round(t, 3), "gesto": abajo}, {"t": round(t + 0.2, 3), "gesto": arriba},
                   {"t": round(t + 1.7, 3), "gesto": abajo}]
        for dt, (x, y), r in ((0.0, (xa, ya), rot_a), (0.2, (xa, ya), rot_a), (0.5, (xb, yb), rot_b),
                              (1.7, (xb, yb), rot_b), (2.0, (xa, ya), rot_a)):
            kf.append({"t": round(t + dt, 3), "x": round(x, 1), "y": round(y - 10, 1), "rotacion": r, "easing": "suave"})
        t += 2.6
    gestos = [g_ for g_ in gestos if g_["t"] <= dur]
    el["gestos"] = gestos
    x0, y0 = xa, ya
    return [_agarrado(obj, (x0, y0), 120 if comer else 160, quien=el, keyframes=kf, a_la_boca=True)]


def _producto_en_uso(plano, spec, dur, i, obj, rnd):
    """Una o dos personas de perfil usando el producto donde se usa. Una bebida se TOMA (la botella sube a la boca,
    inclinada, la cabeza atrás) y una comida se COME; lo demás se usa en las manos."""
    e = ac.Escena(dur, semilla=i)
    fondo = str(spec.get("fondo") or "")
    fondo = fondo if fondo in _LUGAR_USO else "casa"
    texto = str(spec.get("_categoria") or "") + " " + str(spec.get("frase") or "")
    comer = bool(_SE_COME.search(texto)) and not _SE_TOMA.search(texto)
    boca = comer or bool(_SE_TOMA.search(texto))
    _persona(e, _rol(spec, 0, "joven", "mujer"), "usar", 360, "feliz", 0)
    if boca:
        _de_perfil(e, 0, 1, "p_sostener_a", "p_sostener_a", dur, 9.0)
        els_p = _a_la_boca(e, 0, obj, dur, comer)
    else:
        m1 = _de_perfil(e, 0, 1, "p_sostener_a", "p_sostener_b", dur, 0.6)
        els_p = [_agarrado(obj, m1, quien=e.actores[0], keyframes=[{"t": 0, "rotacion": -10},
                                                                   {"t": dur, "rotacion": 10, "easing": "suave"}])]
    _persona(e, _rol(spec, 1, "joven", "hombre"), "usar", 760, "feliz", 1)
    m2 = _de_perfil(e, 1, -1, "p_sostener_a", "p_sostener_b", dur, 0.7)
    els = list(e.elementos) + els_p + [_agarrado(obj, m2, 150, quien=e.actores[1])]
    if fondo in ("cocina", "casa", "oficina"):
        els.append(_mesa(560, 0.62))
    con_x = [k for k in els_p[0].get("keyframes") or [] if "x" in k]
    foco = con_x[2] if len(con_x) > 2 else els_p[0]       # de cerca: la botella en la boca
    return {"elementos": els, "fondo": fondo,
            "camara": _cam(dur, (560, Y_MEDIO, MEDIO), (float(foco["x"]) - 40, float(foco["y"]) - 40, 2.2)),
            "sfx": e.sfx + [(0.6, "pop")], "actores": e.actores}


def _lanzamiento(plano, spec, dur, i, obj, rnd):
    """En un escenario: el producto grande sobre un pedestal en el medio, girando apenas, quien lo presenta al
    costado señalándolo con el índice, y los flashes de las fotos. Sin gente de relleno atrás (2026-11-20)."""
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
            "sfx": e.sfx + sfx + [(0.1, "aplausos")], "actores": e.actores}


def _cierre_tito(plano, spec, dur, i, obj, rnd):
    """Tito en su taller, de hoy, señalando con el índice el producto que brilla sobre su mesa."""
    tito = {"tipo": "tito", "x": 360, "y": ac.PISO + 20, "escala": 0.7, "habla": True,
            "poses": [{"t": 0, "pose": "senala"}]}
    y_m = ac.PISO - 226 * 0.9
    els = [tito, _mesa(780, 0.9), _el(obj, 780, y_m - 110, escala=esc_de(obj, 220), color=True,
                                     keyframes=[{"t": 0, "rotacion": -5}, {"t": dur, "rotacion": 5, "easing": "suave"}])]
    els += ac.destellos(dur * 0.4, rnd, (780, y_m - 220), n_=4)
    return {"elementos": els, "fondo": "taller", "fondo_fijo": True,
            "camara": _cam(dur, (560, Y_MEDIO - 60, 1.5), (600, Y_MEDIO - 20, MEDIO)),
            "sfx": [(round(dur * 0.4, 2), "ding")], "actores": []}


CONSTRUCTORES = {"taller_inventor": _taller_inventor, "crisis": _crisis, "exito_multitud": _exito_multitud,
                 "producto_en_uso": _producto_en_uso, "lanzamiento": _lanzamiento, "cierre_tito": _cierre_tito,
                 "fabrica_produce": _fabrica_produce, "vender_tienda": _vender_tienda}
CON_CAMARA = set(CONSTRUCTORES)      # traen su cámara: gancho_v3.planos no la pisa
