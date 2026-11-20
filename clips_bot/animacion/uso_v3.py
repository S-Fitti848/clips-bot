"""Así Nació, pedidos de Santi del 2026-11-16 (con reglas_v3):

1. USO REAL CON LAS MANOS, paso a paso (`escena_uso`): las manos agarran el producto y lo usan como se usa de verdad
   (Tupper: agarrar, levantar la tapa, guardar comida, cerrar y apretar hasta que cierra hermético; Play-Doh: amasar y
   moldear; cubo: girar las caras). Las manos SIEMPRE tocan el objeto: cada paso las pone sobre la parte que mueven.
   El producto va por partes (cuerpo, tapa y lo que se guarda), dibujadas una vez y guardadas.
5. LA INSPIRACIÓN, animada (`escena_inspiracion`): cuando la historia dice que algo inspiró al producto, la pieza sale
   de lo que la inspiró, se da vuelta, vuela y encastra en el producto (la tapa de la lata de pintura sobre el Tupper),
   con un clic y destellos, en la frase donde la voz lo explica: que se entienda sin la voz.
"""
from __future__ import annotations

import math
import random

from . import acciones as ac
from . import paleta as P

PASOS = ("agarrar", "abrir_tapa", "meter", "cerrar_tapa", "apretar", "amasar", "moldear", "girar", "apilar")
CON_TAPA = {"abrir_tapa", "meter", "cerrar_tapa", "apretar"}
X0, Y0 = 540, 1180            # el producto, de cerca, en el centro
SEP_TRATO = 190               # en el apretón, cada persona a esta distancia del medio (cerca, del otro lado de la mesa)
ESCALA = 1.9                  # los dibujos miden ~200 px: el producto ocupa ~380 px
SEP_MANO = 345                # las manos, a los costados del cuerpo
# Agarre humano (Santi, 2026-11-19, después del Lego: "nada de manos de madera gigantes ni pinzas de robot"): la mano
# llega de costado, casi acostada, con los dedos apoyados sobre la cara del objeto y doblados a medias.
GIRO_AGARRE = 62
Y_AGARRE = 110              # la muñeca, abajo del medio del objeto: los dedos tocan su costado
AGARRE = 0.55
ESCALA_MANO = 1.3
PASO_MIN_S = 0.55


def manga_de_epoca(spec: dict) -> str:
    """La manga de la escena: la que dice el guion o una de la época (tweed marrón antes de 1940, azul después)."""
    m = str((spec.get("uso") or {}).get("manga") or "")
    if m.startswith("#"):
        return m
    anio = int(spec.get("anio_escena") or 0)
    return "#6b5440" if anio and anio < 1940 else "#3d4f7a"


def _el(nombre: str, x: float, y: float, **kw) -> dict:
    return {"tipo": "prop", "nombre": nombre, "x": round(x, 1), "y": round(y, 1), **kw}


def _k(t, **kw) -> dict:
    return {"t": round(t, 3), **kw}


def pasos_validos(pasos, partes: dict) -> list[str]:
    """Los pasos que se pueden mostrar (los de tapa, solo si hay cuerpo y tapa dibujados)."""
    out = [p for p in pasos or [] if p in PASOS]
    if not (partes.get("cuerpo") and partes.get("tapa")):
        out = [p for p in out if p not in CON_TAPA]
    if not out:
        out = ["agarrar", "girar"]
    if out[0] != "agarrar":
        out = ["agarrar"] + out
    return out[:6]


def escena_uso(dur: float, prota: str, partes: dict, pasos: list[str], manga: str = "", seed: int = 0) -> dict:
    """(elementos, fondo, camara, sfx, actores) de la secuencia de uso: el producto de cerca y dos manos que lo usan
    paso a paso. `partes` = {"cuerpo", "tapa", "contenido"} (nombres de dibujos; vacíos si no hay)."""
    rnd = random.Random(seed)
    pasos = pasos_validos(pasos, partes)
    cuerpo = partes.get("cuerpo") or prota or "caja"
    tapa, contenido = partes.get("tapa") or "", partes.get("contenido") or ""
    tramo = max(PASO_MIN_S, dur / len(pasos))
    y_tapa = Y0 - 120 * ESCALA * 0.55            # la tapa apoyada arriba del cuerpo
    kc = [_k(0, x=X0, y=Y0, escala=ESCALA, rotacion=0, fase=0.0)]          # cuerpo (o el producto entero)
    kt = [_k(0, x=X0, y=y_tapa, escala=ESCALA, rotacion=0)]                # tapa
    izq = [_k(0, x=X0 - SEP_MANO - 300, y=Y0 + 200, rotacion=GIRO_AGARRE - 15, fase=0.0)]   # entran de costado
    der = [_k(0, x=X0 + SEP_MANO + 300, y=Y0 + 200, rotacion=-GIRO_AGARRE + 15, fase=0.0)]
    sfx: list[tuple[float, str]] = []
    extra: list[dict] = []
    t = 0.0
    tapa_abierta = False
    for paso in pasos:
        a, b = t, min(dur, t + tramo)
        m = a + (b - a) * 0.5
        if paso == "agarrar":          # las dos manos llegan al cuerpo y los dedos se cierran sobre él
            izq += [_k(a + 0.35 * (b - a), x=X0 - SEP_MANO - 40, y=Y0 + Y_AGARRE + 20, rotacion=GIRO_AGARRE - 10, fase=0.0,
                       easing="salida"),
                    _k(b, x=X0 - SEP_MANO, y=Y0 + Y_AGARRE, rotacion=GIRO_AGARRE, fase=AGARRE, easing="suave")]
            der += [_k(a + 0.35 * (b - a), x=X0 + SEP_MANO + 40, y=Y0 + Y_AGARRE + 20, rotacion=-GIRO_AGARRE + 10, fase=0.0,
                       easing="salida"),
                    _k(b, x=X0 + SEP_MANO, y=Y0 + Y_AGARRE, rotacion=-GIRO_AGARRE, fase=AGARRE, easing="suave")]
            sfx.append((round(a + 0.35 * (b - a), 3), "tac"))
        elif paso == "abrir_tapa":     # la izquierda sostiene el cuerpo; la derecha levanta la tapa y la corre
            kt += [_k(a, x=X0, y=y_tapa, rotacion=0), _k(m, x=X0 + 40, y=y_tapa - 230, rotacion=-14, easing="salida"),
                   _k(b, x=X0 + 250, y=y_tapa - 150, rotacion=-24, easing="suave")]
            der += [_k(a, x=X0 + 120, y=y_tapa + 40, rotacion=-40, fase=1.0, easing="suave"),
                    _k(m, x=X0 + 160, y=y_tapa - 190, rotacion=-40, fase=1.0, easing="salida"),
                    _k(b, x=X0 + 370, y=y_tapa - 110, rotacion=-48, fase=1.0, easing="suave")]
            sfx.append((round(a + 0.1, 3), "pop"))
            tapa_abierta = True
        elif paso == "meter" and contenido:     # la comida baja adentro del cuerpo, empujada por la mano
            extra.append(_el(contenido, X0 - 30, Y0 - 520, escala=ESCALA * 0.55, desde=round(a, 3),
                             keyframes=[_k(a, y=Y0 - 520, escala=ESCALA * 0.55, opacidad=1.0),
                                        _k(m, y=Y0 - 60, escala=ESCALA * 0.5, easing="entrada"),
                                        _k(b, y=Y0 + 10, escala=ESCALA * 0.42, opacidad=0.0, easing="suave")]))
            izq += [_k(a, x=X0 - 120, y=Y0 - 420, rotacion=20, fase=1.0, easing="suave"),
                    _k(m, x=X0 - 120, y=Y0 - 40, rotacion=12, fase=1.0, easing="entrada"),
                    _k(b, x=X0 - SEP_MANO + 30, y=Y0 + 50, rotacion=32, fase=1.0, easing="suave")]
            sfx.append((round(m, 3), "pop"))
        elif paso == "cerrar_tapa" and tapa_abierta:   # la tapa vuelve encima del cuerpo, con la mano
            kt += [_k(a, x=X0 + 250, y=y_tapa - 150, rotacion=-24), _k(m, x=X0 + 30, y=y_tapa - 120, rotacion=-6,
                                                                       easing="salida"),
                   _k(b, x=X0, y=y_tapa, rotacion=0, easing="entrada")]
            der += [_k(a, x=X0 + 370, y=y_tapa - 110, rotacion=-48, fase=1.0),
                    _k(b, x=X0 + 130, y=y_tapa - 10, rotacion=-30, fase=1.0, easing="entrada")]
            sfx.append((round(b - 0.05, 3), "tac"))
            tapa_abierta = False
        elif paso == "apretar":        # las dos manos aprietan la tapa hasta el clic: hermético
            for k_ in range(2):
                tp = a + (b - a) * (0.25 + 0.4 * k_)
                kt += [_k(tp, escala=ESCALA, y=y_tapa), _k(tp + 0.1, escala=ESCALA * 0.96, y=y_tapa + 12),
                       _k(tp + 0.22, escala=ESCALA, y=y_tapa, easing="rebote")]
            izq += [_k(a, x=X0 - 110, y=y_tapa + 10, rotacion=34, fase=0.2, easing="suave"),
                    _k(b, x=X0 - 110, y=y_tapa + 22, rotacion=34, fase=0.3)]
            der += [_k(a, x=X0 + 110, y=y_tapa + 10, rotacion=-34, fase=0.2, easing="suave"),
                    _k(b, x=X0 + 110, y=y_tapa + 22, rotacion=-34, fase=0.3)]
            sfx += [(round(a + (b - a) * 0.35, 3), "tac"), (round(b - 0.1, 3), "ding")]
            extra += ac.destellos(b - 0.25, rnd, (X0, y_tapa), n_=3)
        elif paso in ("amasar", "moldear"):   # el producto se aplasta y se estira entre las manos
            n_ = 3 if paso == "amasar" else 2
            for k_ in range(n_):
                t1 = a + (b - a) * (k_ + 0.5) / n_
                ancho = 1.25 if paso == "amasar" else 1.4 - 0.25 * k_
                kc += [_k(t1, escala=ESCALA * ancho, rotacion=rnd.uniform(-8, 8), easing="suave"),
                       _k(min(b, t1 + (b - a) / (2 * n_)), escala=ESCALA * 0.92, rotacion=0, easing="suave")]
                izq.append(_k(t1, x=X0 - SEP_MANO + 40, y=Y0 + Y_AGARRE, rotacion=GIRO_AGARRE, fase=AGARRE, easing="suave"))
                der.append(_k(t1, x=X0 + SEP_MANO - 40, y=Y0 + Y_AGARRE, rotacion=-GIRO_AGARRE, fase=AGARRE, easing="suave"))
            sfx.append((round(m, 3), "boing"))
        elif paso == "girar":          # gira de a cuartos de vuelta, con las manos que lo giran
            for k_ in range(3):
                t1 = a + (b - a) * (k_ + 1) / 3
                kc.append(_k(t1, rotacion=90 * (k_ + 1), fase=min(1.0, (k_ + 1) / 3), easing="salida"))
                sfx.append((round(t1 - 0.08, 3), "tac"))
            izq.append(_k(b, x=X0 - SEP_MANO, y=Y0 + Y_AGARRE, rotacion=GIRO_AGARRE, fase=AGARRE, easing="suave"))
            der.append(_k(b, x=X0 + SEP_MANO, y=Y0 + Y_AGARRE, rotacion=-GIRO_AGARRE, fase=AGARRE, easing="suave"))
        elif paso == "apilar":         # otros iguales se apilan encima, uno por uno
            for k_ in range(3):
                t1 = a + (b - a) * k_ / 3
                extra.append(_el(cuerpo if not tapa else prota or cuerpo, X0, Y0 - 520, escala=ESCALA * 0.9,
                                 desde=round(t1, 3), color=True,
                                 keyframes=[_k(t1, y=Y0 - 520), _k(t1 + 0.25, y=Y0 - 150 * (k_ + 1), easing="entrada")]))
                sfx.append((round(t1 + 0.25, 3), "tac"))
        t = b
    # de cerca, apoyado en una mesa (nada flotando en el medio del cuarto)
    els = [_el("mesa", X0, Y0 + 62 * ESCALA, escala=3.4, decorado=True, en_medio=True),
           _el(cuerpo, X0, Y0, escala=ESCALA, color=True, keyframes=sorted(kc, key=lambda k: k["t"]))]
    if tapa:
        els.append(_el(tapa, X0, y_tapa, escala=ESCALA, color=True, keyframes=sorted(kt, key=lambda k: k["t"])))
    els += extra
    color_manga = manga or "#3d4f7a"
    for lado, kf in ((-1, izq), (1, der)):
        els.append(_el("mano", kf[0]["x"], kf[0]["y"], escala=ESCALA_MANO, forma=lado, manga=color_manga, fase=0.0,
                       detalle=True,
                       keyframes=sorted(kf, key=lambda k: k["t"])))
    cam = [_k(0, zoom=1.0), _k(dur, zoom=1.06, easing="suave")]
    return {"elementos": els, "fondo": None, "camara": cam, "sfx": sorted(sfx), "actores": []}


def escena_inspiracion(dur: float, fuente: str, pieza: str, producto: str, seed: int = 0, resultado: str = "",
                       acompana: str = "") -> dict:
    """Lo que inspiró al producto a la izquierda (con lo que lo hace reconocible al lado: `acompana`, el pincel de la
    lata) y el producto a la derecha, SIN su parte (el Tupper sin tapa). La pieza sale de la fuente, se da vuelta, vuela,
    cae sobre el producto y se TRANSFORMA en su parte (`resultado`: la tapa de pintura se vuelve la tapa blanca del
    Tupper), con un clic, destellos y una flecha (Santi, 2026-11-16: "que se entienda sin la voz")."""
    rnd = random.Random(seed)
    xf, xp, y = 290, 790, 1180
    esc_ = 1.6
    t_sale, t_gira, t_llega = dur * 0.12, dur * 0.4, dur * 0.62
    t_trans = min(dur - 0.35, t_llega + 0.15)
    y_pieza_f, y_pieza_p = y - 150, y - 120 * esc_ * 0.55
    kp = [_k(0, x=xf, y=y_pieza_f, rotacion=0, escala=1.3, opacidad=1.0),
          _k(t_sale, x=xf, y=y_pieza_f - 160, rotacion=0, escala=1.35, easing="salida"),      # se levanta
          _k(t_gira, x=(xf + xp) / 2, y=y - 520, rotacion=180, escala=1.45, easing="suave"),  # se da vuelta en el aire
          _k(t_llega, x=xp, y=y_pieza_p, rotacion=180, escala=1.3, easing="entrada"),         # cae sobre el producto
          _k(t_llega + 0.1, escala=1.18, easing="lineal")]
    if resultado:      # se transforma: la pieza se apaga mientras aparece la parte del producto en el mismo lugar
        kp += [_k(t_trans, escala=1.25, opacidad=1.0), _k(t_trans + 0.3, escala=1.5, opacidad=0.0, easing="salida")]
    else:
        kp.append(_k(t_llega + 0.25, escala=1.3, easing="rebote"))
    linea = ac.estela(kp[1:4], t_sale, t_llega)
    els = [_el(fuente, xf, y, escala=esc_, color=True)]
    if acompana:
        els.append(_el(acompana, xf + 175, y + 70, escala=1.0, rotacion=24, color=True))
    els.append(_el(producto, xp, y, escala=esc_, color=True,
                   keyframes=[_k(t_llega, escala=esc_), _k(t_llega + 0.12, escala=esc_ * 0.94),
                              _k(t_llega + 0.3, escala=esc_ * 1.03, easing="rebote"), _k(dur, escala=esc_ * 1.03)]))
    if resultado:
        els.append(_el(resultado, xp, y_pieza_p, escala=esc_, color=True, desde=round(t_trans, 3),
                       keyframes=[_k(t_trans, escala=esc_ * 0.8, opacidad=0.0),
                                  _k(t_trans + 0.3, escala=esc_ * 1.03, opacidad=1.0, easing="rebote")]))
    if linea:
        els.append(linea)
    els.append(_el(pieza, xf, y_pieza_f, color=True, keyframes=kp))
    els.append(_el("flecha", (xf + xp) / 2, y + 260, escala=0.9, desde=round(t_llega, 3), entrada="rebote"))
    els += ac.destellos(t_trans if resultado else t_llega + 0.02, rnd, (xp, y_pieza_p), n_=6)
    sfx = [(round(t_sale, 3), "whoosh"), (round(t_llega, 3), "tac"), (round(t_trans + 0.1, 3), "ding")]
    cam = [_k(0, zoom=1.0), _k(t_llega, zoom=1.06, easing="suave"),
           _k(t_llega + 0.02, zoom=1.22, x=(xp - 540) * 0.6, y=(y_pieza_p - 960) * 0.3, easing="escalon"),
           _k(dur, zoom=1.3, x=(xp - 540) * 0.6, y=(y_pieza_p - 960) * 0.3, easing="suave")]
    return {"elementos": els, "fondo": None, "camara": cam, "sfx": sorted(sfx), "actores": []}


# ---- la plata con acciones reales (Santi, 2026-11-16: "nada de monedas con $ gigantes en las manos: parece que la
# están lavando") ------------------------------------------------------------------------------------------------
PLATA = ("contar_billetes", "abrir_caja", "apreton_manos", "firmar")


def _manos(izq: list[dict], der: list[dict], manga: str, manga2: str = "") -> list[dict]:
    out = []
    for lado, kf, color in ((-1, izq, manga), (1, der, manga2 or manga)):
        out.append(_el("mano", kf[0]["x"], kf[0]["y"], escala=1.05, forma=lado, manga=color or "#3d4f7a", fase=0.0,
                       detalle=True, rotacion=kf[0].get("rotacion", 0), keyframes=sorted(kf, key=lambda k: k["t"])))
    return out


def escena_plata(tipo: str, dur: float, manga: str = "", seed: int = 0, spec: dict | None = None) -> dict:
    """Una acción de plata que se lee en un segundo: contar billetes, abrir la caja registradora, darse la mano al
    cerrar un trato, firmar un contrato o un cheque."""
    rnd = random.Random(seed)
    els: list[dict] = []
    sfx: list[tuple[float, str]] = []
    mesa = _el("mesa", X0, Y0 + 190, escala=3.4, decorado=True, en_medio=True)
    if tipo == "contar_billetes":      # de una pila a la otra, de a uno, con la mano que lo pasa
        n_ = max(4, min(8, int(dur / 0.4)))
        els.append(mesa)
        der, izq = [_k(0, x=X0 + 380, y=Y0 + 300, rotacion=-20, fase=0.0)], [_k(0, x=X0 - 330, y=Y0 + 120, rotacion=24,
                                                                                fase=1.0)]
        for k_ in range(n_):
            t0 = 0.25 + k_ * (dur - 0.5) / n_
            t1 = t0 + 0.28
            els.append(_el("billete", X0 + 170, Y0 + 40 - 6 * (n_ - k_), escala=0.85, rotacion=rnd.uniform(-6, 6),
                           keyframes=[_k(0, x=X0 + 170), _k(t0, x=X0 + 170, y=Y0 + 40 - 6 * (n_ - k_)),
                                      _k(t1, x=X0 - 170, y=Y0 + 40 - 6 * k_, rotacion=rnd.uniform(-10, 10), easing="salida")]))
            der += [_k(t0, x=X0 + 250, y=Y0 + 110, rotacion=-26, fase=1.0, easing="suave"),
                    _k(t1, x=X0 - 40, y=Y0 + 110, rotacion=-34, fase=1.0, easing="salida"),
                    _k(t1 + 0.1, x=X0 + 250, y=Y0 + 110, rotacion=-26, fase=0.6, easing="suave")]
            sfx.append((round(t1, 3), "tac"))
        els += _manos(izq, der, manga)
    elif tipo == "abrir_caja":         # aprieta la tecla, se abre el cajón con su ruido, saca un billete
        t_tecla, t_abre = dur * 0.2, dur * 0.35
        els.append(mesa)
        els.append(_el("caja_registradora", X0, Y0 - 40, escala=2.0, fase=0.0,
                       keyframes=[_k(0, fase=0.0), _k(t_abre, fase=0.0), _k(t_abre + 0.25, fase=1.0, easing="rebote")]))
        der = [_k(0, x=X0 + 380, y=Y0 + 300, rotacion=-20, fase=0.0),
               _k(t_tecla, x=X0 + 90, y=Y0 + 30, rotacion=-25, fase=0.4, easing="salida"),
               _k(t_tecla + 0.12, y=Y0 + 50, easing="lineal"), _k(t_tecla + 0.24, y=Y0 + 30, easing="lineal")]
        izq = [_k(0, x=X0 - 380, y=Y0 + 320, rotacion=20, fase=0.0),
               _k(t_abre + 0.3, x=X0 - 60, y=Y0 + 300, rotacion=10, fase=0.0, easing="salida"),
               _k(t_abre + 0.6, x=X0 - 60, y=Y0 + 300, rotacion=10, fase=1.0),
               _k(dur, x=X0 - 260, y=Y0 + 230, rotacion=20, fase=1.0, easing="suave")]
        els.append(_el("billete", X0 - 60, Y0 + 280, escala=0.7, desde=round(t_abre + 0.55, 3),
                       keyframes=[_k(t_abre + 0.55, x=X0 - 60, y=Y0 + 280),
                                  _k(dur, x=X0 - 260, y=Y0 + 200, rotacion=-12, easing="suave")]))
        sfx += [(round(t_tecla, 3), "tac"), (round(t_abre, 3), "caja_registradora")]
        els += _manos(izq, der, manga)
    elif tipo == "apreton_manos":
        # Santi, 2026-11-16 ("nunca dos manos solas"; "parece un saludo con el codo"; "puño contra puño"): primero un
        # PLANO MEDIO con las dos personas CERCA, detrás de la mesa con el contrato grande, y las manos que se juntan
        # justo en el medio, encima del contrato (el ángulo de cada brazo se calcula para que lleguen); después el
        # PRIMER PLANO de las manos enganchadas de costado (palma contra palma, los dedos envolviendo la otra mano,
        # los pulgares cruzados arriba) con una sacudida de arriba abajo.
        from . import personajes as per

        t_corte = round(dur * 0.45, 3)
        e_ = ac.Escena(dur, semilla=seed)
        actores = list((spec or {}).get("actores") or [])
        defectos = (("empresario", "hombre"), ("empresaria", "mujer"))
        esc_mesa = 0.9
        y_mesa = ac.PISO - 226 * esc_mesa          # la tapa de la mesa (sus patas llegan al piso)
        y_mano = y_mesa - 58                       # las manos se juntan un poco arriba del contrato
        for k_, (rol_def, gen_def) in enumerate(defectos):
            a_ = actores[k_] if k_ < len(actores) else {}
            x_ = X0 + (SEP_TRATO if k_ else -SEP_TRATO)
            e_.actor(a_.get("rol") or rol_def, "quieto", "centro", None, "feliz", k_, x0=x_, x1=x_,
                     genero=a_.get("genero") or gen_def, edad=a_.get("edad") or "adulto")
        ropas = []
        for k_, el in enumerate(e_.elementos):
            s_ = float(el.get("escala", 0.74))
            alto = float(el.get("cambios", {}).get("alto_cuerpo") or per.ELENCO.get(el.get("nombre"),
                                                                                per.ELENCO["narrador"]).alto_cuerpo)
            hy = -420 * alto + 38                  # el hombro, en coordenadas del personaje
            dx = SEP_TRATO / s_ - 92               # del hombro hasta el medio (hacia el otro)
            dy = (y_mano - ac.PISO) / s_ - hy
            h_, c_ = per.brazo_hacia(dx, dy)
            el["hasta"] = t_corte
            el["gestos"] = [{"t": 0, "gesto": "reposo"},
                            {"t": 0.25, "gesto": f"{'brazo_izq' if k_ else 'brazo_der'}:{h_}:{c_}"}]
            ropas.append(el.get("cambios", {}).get("ropa") or per.ELENCO.get(el.get("nombre"),
                                                                             per.ELENCO["narrador"]).ropa)
        els += e_.elementos
        ropas += ["#3d4f7a", "#5a3d2b"]
        # la mesa y el contrato van DELANTE de los dos (sin `decorado`, que los mandaba detrás de los personajes)
        els += [_el("mesa", X0, y_mesa, escala=esc_mesa, hasta=t_corte, en_medio=True),
                _el("papel_firma", X0, y_mesa + 4, escala=0.9, forma=1, hasta=t_corte),
                # las dos manos ya enganchadas, chicas, donde se tocan (aparecen cuando los brazos llegan)
                _el("apreton", X0, y_mano, escala=0.26, forma=0, manga=ropas[0], color=ropas[1], desde=0.5,
                    hasta=t_corte, keyframes=[_k(0.5, y=y_mano), _k(0.75, y=y_mano - 10, easing="suave"),
                                              _k(1.0, y=y_mano + 8, easing="suave"), _k(t_corte, y=y_mano)])]
        t_toca = t_corte + 0.18
        mano = _el("apreton", X0, Y0, escala=1.35, manga=manga or "#3d4f7a", color="#5a3d2b", desde=t_corte,
                   keyframes=[_k(t_corte, y=Y0, escala=1.3, rotacion=0), _k(t_toca, escala=1.4, easing="salida")])
        n_sac = 3 if dur - t_toca > 1.3 else 2
        paso = min(0.3, (dur - t_toca - 0.2) / n_sac)
        for k_ in range(n_sac):                    # la sacudida: arriba y abajo, con un poco de giro
            ta = t_toca + 0.05 + k_ * paso
            mano["keyframes"] += [_k(ta + paso * 0.5, y=Y0 - 55, rotacion=-4, easing="suave"),
                                  _k(ta + paso, y=Y0 + 40, rotacion=3, easing="suave")]
        mano["keyframes"].append(_k(min(dur, t_toca + 0.05 + n_sac * paso + 0.2), y=Y0, rotacion=0, easing="suave"))
        els.append(mano)
        sfx += [(round(t_toca, 3), "tac"), (round(min(dur - 0.1, t_toca + 0.9), 3), "ding")]
        els += ac.destellos(min(dur - 0.5, t_toca + 0.8), rnd, (X0, Y0 - 200), n_=4)
    else:                              # firmar: la lapicera escribe la firma mientras la otra mano sostiene el papel
        t0, t1 = dur * 0.18, dur * 0.85
        esc_p = 2.1
        els.append(mesa)
        els.append(_el("papel_firma", X0, Y0 - 60, escala=esc_p, fase=0.0,
                       keyframes=[_k(0, fase=0.0), _k(t0, fase=0.0), _k(t1, fase=1.0, easing="lineal")]))
        pts = [(-110, 120), (-30, 100), (40, 120), (120, 100)]
        kp = [_k(0, x=X0 + 420, y=Y0 + 300)]
        for j, (px, py) in enumerate(pts):
            t = t0 + (t1 - t0) * j / (len(pts) - 1)
            kp.append(_k(t, x=X0 + px * esc_p + 40, y=Y0 - 60 + py * esc_p - 120, easing="suave" if j else "salida"))
        els.append(_el("lapicera", X0 + 420, Y0 + 300, escala=1.2, keyframes=kp))
        der = [_k(k["t"], x=k["x"] + 60, y=k["y"] + 150, rotacion=-30, fase=1.0, easing=k.get("easing", "suave"))
               for k in kp]
        izq = [_k(0, x=X0 - 420, y=Y0 + 300, rotacion=30, fase=0.0),
               _k(t0 * 0.8, x=X0 - 300, y=Y0 + 90, rotacion=40, fase=0.4, easing="salida")]
        sfx += [(round(t0, 3), "tac"), (round(t1, 3), "ding")]
        els += _manos(izq, der, manga)
    if tipo == "apreton_manos":    # plano medio de las dos personas → corte seco al primer plano del apretón
        t_c = round(dur * 0.45, 3)
        cam = [_k(0, zoom=1.22, y=190), _k(t_c - 0.02, zoom=1.27, y=190, easing="suave"),
               _k(t_c, zoom=1.35, y=Y0 - 960, easing="escalon"), _k(dur, zoom=1.45, y=Y0 - 960, easing="suave")]
    else:
        cam = [_k(0, zoom=1.0), _k(dur, zoom=1.06, easing="suave")]
    return {"elementos": els, "fondo": None, "camara": cam, "sfx": sorted(sfx), "actores": []}
