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
ESCALA = 1.9                  # los dibujos miden ~200 px: el producto ocupa ~380 px
SEP_MANO = 230                # las manos, a los costados del cuerpo
PASO_MIN_S = 0.55


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
    izq = [_k(0, x=X0 - SEP_MANO - 260, y=Y0 + 330, rotacion=24, fase=0.0)]   # las manos entran desde abajo
    der = [_k(0, x=X0 + SEP_MANO + 260, y=Y0 + 330, rotacion=-24, fase=0.0)]
    sfx: list[tuple[float, str]] = []
    extra: list[dict] = []
    t = 0.0
    tapa_abierta = False
    for paso in pasos:
        a, b = t, min(dur, t + tramo)
        m = a + (b - a) * 0.5
        if paso == "agarrar":          # las dos manos llegan al cuerpo y los dedos se cierran sobre él
            izq += [_k(a + 0.35 * (b - a), x=X0 - SEP_MANO, y=Y0 + 60, rotacion=28, fase=0.0, easing="salida"),
                    _k(b, x=X0 - SEP_MANO + 30, y=Y0 + 50, rotacion=32, fase=1.0, easing="suave")]
            der += [_k(a + 0.35 * (b - a), x=X0 + SEP_MANO, y=Y0 + 60, rotacion=-28, fase=0.0, easing="salida"),
                    _k(b, x=X0 + SEP_MANO - 30, y=Y0 + 50, rotacion=-32, fase=1.0, easing="suave")]
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
                izq.append(_k(t1, x=X0 - SEP_MANO + 70, y=Y0 + 20, rotacion=30, fase=1.0, easing="suave"))
                der.append(_k(t1, x=X0 + SEP_MANO - 70, y=Y0 + 20, rotacion=-30, fase=1.0, easing="suave"))
            sfx.append((round(m, 3), "boing"))
        elif paso == "girar":          # gira de a cuartos de vuelta, con las manos que lo giran
            for k_ in range(3):
                t1 = a + (b - a) * (k_ + 1) / 3
                kc.append(_k(t1, rotacion=90 * (k_ + 1), fase=min(1.0, (k_ + 1) / 3), easing="salida"))
                sfx.append((round(t1 - 0.08, 3), "tac"))
            izq.append(_k(b, x=X0 - SEP_MANO + 20, y=Y0 + 40, rotacion=36, fase=1.0, easing="suave"))
            der.append(_k(b, x=X0 + SEP_MANO - 20, y=Y0 + 40, rotacion=-36, fase=1.0, easing="suave"))
        elif paso == "apilar":         # otros iguales se apilan encima, uno por uno
            for k_ in range(3):
                t1 = a + (b - a) * k_ / 3
                extra.append(_el(cuerpo if not tapa else prota or cuerpo, X0, Y0 - 520, escala=ESCALA * 0.9,
                                 desde=round(t1, 3), color=True,
                                 keyframes=[_k(t1, y=Y0 - 520), _k(t1 + 0.25, y=Y0 - 150 * (k_ + 1), easing="entrada")]))
                sfx.append((round(t1 + 0.25, 3), "tac"))
        t = b
    # de cerca, apoyado en una mesa (nada flotando en el medio del cuarto)
    els = [_el("mesa", X0, Y0 + 100 * ESCALA, escala=3.4, decorado=True),
           _el(cuerpo, X0, Y0, escala=ESCALA, color=True, keyframes=sorted(kc, key=lambda k: k["t"]))]
    if tapa:
        els.append(_el(tapa, X0, y_tapa, escala=ESCALA, color=True, keyframes=sorted(kt, key=lambda k: k["t"])))
    els += extra
    color_manga = manga or "#3d4f7a"
    for lado, kf in ((-1, izq), (1, der)):
        els.append(_el("mano", kf[0]["x"], kf[0]["y"], escala=1.05, forma=lado, manga=color_manga, fase=0.0, detalle=True,
                       keyframes=sorted(kf, key=lambda k: k["t"])))
    cam = [_k(0, zoom=1.0), _k(dur, zoom=1.06, easing="suave")]
    return {"elementos": els, "fondo": None, "camara": cam, "sfx": sorted(sfx), "actores": []}


def escena_inspiracion(dur: float, fuente: str, pieza: str, producto: str, seed: int = 0) -> dict:
    """Lo que inspiró al producto a la izquierda y el producto a la derecha: la pieza sale de la fuente, se da vuelta,
    vuela en arco y encastra en el producto con un clic, destellos y una flecha que une los dos."""
    rnd = random.Random(seed)
    xf, xp, y = 290, 790, 1180
    t_sale, t_gira, t_llega = dur * 0.12, dur * 0.42, dur * 0.68
    y_pieza_f, y_pieza_p = y - 150, y - 120
    kp = [_k(0, x=xf, y=y_pieza_f, rotacion=0, escala=1.3),
          _k(t_sale, x=xf, y=y_pieza_f - 160, rotacion=0, escala=1.35, easing="salida"),      # se levanta
          _k(t_gira, x=(xf + xp) / 2, y=y - 520, rotacion=180, escala=1.45, easing="suave"),  # se da vuelta en el aire
          _k(t_llega, x=xp, y=y_pieza_p, rotacion=180, escala=1.3, easing="entrada"),         # baja sobre el producto
          _k(t_llega + 0.1, escala=1.18, easing="lineal"), _k(t_llega + 0.25, escala=1.3, easing="rebote")]
    linea = ac.estela(kp[1:4], t_sale, t_llega)
    els = [_el(fuente, xf, y, escala=1.6, color=True),
           _el(producto, xp, y, escala=1.6, color=True,
               keyframes=[_k(t_llega, escala=1.6), _k(t_llega + 0.12, escala=1.5),
                          _k(t_llega + 0.3, escala=1.65, easing="rebote"), _k(dur, escala=1.65)])]
    if linea:
        els.append(linea)
    els.append(_el(pieza, xf, y_pieza_f, color=True, keyframes=kp))
    els.append(_el("flecha", (xf + xp) / 2, y + 260, escala=0.9, desde=round(t_llega, 3), entrada="rebote"))
    els += ac.destellos(t_llega + 0.02, rnd, (xp, y_pieza_p), n_=5)
    sfx = [(round(t_sale, 3), "whoosh"), (round(t_llega, 3), "tac"), (round(t_llega + 0.15, 3), "ding")]
    cam = [_k(0, zoom=1.0), _k(t_llega, zoom=1.06, easing="suave"),
           _k(t_llega + 0.02, zoom=1.22, x=(xp - 540) * 0.4, y=(y_pieza_p - 960) * 0.3, easing="escalon"),
           _k(dur, zoom=1.28, x=(xp - 540) * 0.4, y=(y_pieza_p - 960) * 0.3, easing="suave")]
    return {"elementos": els, "fondo": None, "camara": cam, "sfx": sorted(sfx), "actores": []}
