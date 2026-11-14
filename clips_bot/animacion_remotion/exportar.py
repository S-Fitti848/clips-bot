"""timeline.Video (el motor actual) → datos por cuadro para el proyecto de Remotion (`remotion/`).

Se reusa TODA la lógica del motor actual: keyframes, entradas, ciclos de caminata, gestos, caras,
parpadeos, la boca que sigue la voz, la cámara (con sus sacudones), las pausas de Tito con la escena
congelada, el viaje en el tiempo (remolino + sepia) y las transiciones. Así los chequeos de composición
del motor actual (nadie encima de nadie, nada tapado, la franja de subtítulos libre) siguen valiendo:
el esqueleto de cada personaje y la ubicación de cada cosa son los mismos; lo que cambia es el dibujo.

Formato (JSON):
    {"fps": 30, "ancho": 1080, "alto": 1920, "personajes": [{...campos de Personaje}],
     "legacy": {"clave": "<svg del motor actual>"},      # props que el estilo nuevo todavía no dibuja
     "cuadros": [{"t": s, "tono": 0..1, "a": CAPA, "b": CAPA|null, "tr": [tipo, u]|null, "sub": "<svg>"}]}
    CAPA = {"f": [fondo, semilla] | ["color", "#hex"], "c": [zoom, dx, dy, rot], "fr": [ITEM], "fi": [ITEM],
            "pausa": u|null, "en": [ITEM], "giro": bool}
    ITEM = {"k": "p"|"t"|"o"|"s", "x", "y", "sx", "sy", "r", "o", ...}
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from clips_bot.animacion import escenas as esc
from clips_bot.animacion import timeline as tl
from clips_bot.animacion.easing import recortar

# Lo que el estilo nuevo dibuja (remotion/src/props.tsx y fondos.tsx). El resto va con el SVG del motor
# actual (con sombra y contorno del estilo nuevo encima), así ningún guion se queda sin dibujo.
PROPS_NUEVOS = {"pelota_espuma", "pelota", "tele", "lampara", "cuadro", "jarron", "mesa", "estante", "ventana",
                "pedazo", "lamparita", "idea_fallida", "pregunta", "exclamacion", "moneda", "billete", "martillo",
                "caja", "reloj_bolsillo", "engranaje", "trofeo", "grafico_sube", "bolsa_plata", "cartel",
                "botella", "flecha", "calendario"}
FONDOS_NUEVOS = {"casa", "taller", "oficina", "fabrica", "tienda", "ciudad", "cielo", "escenario"}

CAMPOS_ESTADO = ("parpadeo", "boca", "apertura", "cejas", "brazo_izq", "brazo_der", "respiracion", "mirada",
                 "inclinacion", "pierna_izq", "pierna_der", "agachar", "perfil", "zancada", "corre")


def _r(x: float, k: int = 2) -> float:
    return round(float(x), k)


class Exportador:
    def __init__(self, video: tl.Video):
        self.v = video
        self._pjs: dict[str, int] = {}
        self.personajes: list[dict] = []
        self.legacy: dict[str, str] = {}

    # -- elementos ------------------------------------------------------------------------------
    def _pj(self, el: tl.Elemento) -> int:
        clave = json.dumps([el.datos.get("nombre", "narrador"), el.datos.get("cambios", {})], sort_keys=True)
        if clave not in self._pjs:
            self._pjs[clave] = len(self.personajes)
            self.personajes.append(asdict(el._pj))
        return self._pjs[clave]

    def item(self, el: tl.Elemento, t: float, apertura: float, cuadro: int) -> dict | None:
        """Lo mismo que `Elemento.svg`, pero como datos (el dibujo lo hace Remotion)."""
        v = {k: el.pista.valor(k, t, el.base[k]) for k in tl.PROPS_ANIMABLES}
        if v["opacidad"] <= 0.001 or v["escala"] <= 0.001:
            return None
        if el.tipo in ("gancho", "texto", "contador"):     # texto: el mismo SVG (fuente medida con PIL)
            s = el.svg(t, apertura, cuadro)
            return {"k": "s", "s": s} if s else None
        st = max(0.5, min(1.5, v["estirar"]))
        sx = v["escala"] * (1 + (1 - st) * 0.5) if abs(st - 1) > 1e-3 else v["escala"]
        sy = v["escala"] * st if abs(st - 1) > 1e-3 else v["escala"]
        it = {"x": _r(v["x"], 1), "y": _r(v["y"], 1), "sx": _r(sx, 4), "sy": _r(sy, 4),
              "r": _r(v["rotacion"]), "o": _r(v["opacidad"], 3)}
        # velocidad (px por cuadro) para las estelas de lo que vuela y las líneas de velocidad de quien corre
        dt = 1 / self.v.fps
        if t - dt >= el.desde:
            vx = v["x"] - el.pista.valor("x", t - dt, el.base["x"])
            vy = v["y"] - el.pista.valor("y", t - dt, el.base["y"])
            if math.hypot(vx, vy) > 2:
                it["v"] = [_r(vx, 1), _r(vy, 1)]
        tl_ = t - el.desde
        if el.tipo == "personaje":
            est, dy = el._estado(t, apertura, cuadro, v["mirada"], v["cabeza"])
            it["piso"] = _r(max(v["y"], el.base["y"]), 1)        # dónde va la sombra (no salta con él)
            it["y"] = _r(v["y"] + dy, 1)
            e = asdict(est)
            it.update(k="p", id=self._pj(el), e={c: (list(map(lambda z: _r(z), e[c])) if isinstance(e[c], tuple)
                                                       else _r(e[c], 3) if isinstance(e[c], float) else e[c])
                                                   for c in CAMPOS_ESTADO})
            return it
        if el.tipo == "tito":
            pose = "saluda"
            for ps in sorted(el.datos.get("poses", []), key=lambda x: float(x.get("t", 0))):
                if float(ps.get("t", 0)) <= tl_:
                    pose = ps["pose"]
            habla = bool(el.datos.get("habla", False)) and apertura > 0
            parp = max([1 - abs(t - tp) / 0.09 for tp in el.parpadeos if abs(t - tp) < 0.09] or [0.0])
            giro = float(el.datos.get("giro_aguja", 0.0))
            it.update(k="t", piso=_r(max(v["y"], el.base["y"]), 1), pose=pose, ap=_r(apertura if habla else 0.0, 3),
                      pa=_r(parp, 3), ag=_r((giro * tl_) % 360 if giro else 40.0, 1),
                      re=_r(math.sin(2 * math.pi * t / 3.2), 3),
                      inc=_r(2.5 * math.sin(2 * math.pi * t / 4.1) if habla else 0.0))
            return it
        # prop
        params = {k: val for k, val in el.datos.items() if k in ("texto", "color", "encendida", "rota", "forma")}
        nombre = el.datos["nombre"]
        it.update(k="o", n=nombre, p=params, sop=el.datos.get("soporte", ""))
        if nombre not in PROPS_NUEVOS:
            clave = nombre + json.dumps(params, sort_keys=True)
            if clave not in self.legacy:
                self.legacy[clave] = esc.prop(nombre, **params)
            it["l"] = clave
        return it

    # -- capas ----------------------------------------------------------------------------------
    def _lista(self, escena: tl.Escena, t: float, cuadro: int, apertura: float | None):
        ap = (self.v.envolvente[cuadro] if cuadro < len(self.v.envolvente) else 0.0) if apertura is None else apertura
        fr, fi = [], []
        for el in escena.elementos:
            if el.visible(t):
                it = self.item(el, t, ap, cuadro)
                if it:
                    (fi if el.fijo else fr).append(it)
        return fr, fi

    def _capa(self, escena: tl.Escena, t: float, cuadro: int, apertura: float | None = None) -> dict:
        fr, fi = self._lista(escena, t, cuadro, apertura)
        tipo, semilla = escena.fondo
        if tipo != "color" and tipo not in FONDOS_NUEVOS:
            clave = f"fondo:{tipo}:{semilla}"
            if clave not in self.legacy:
                self.legacy[clave] = esc.fondo(tipo, semilla)
        return {"f": list(escena.fondo), "c": list(escena.camara_en(t)), "fr": fr, "fi": fi,
                "pausa": None, "en": [], "giro": False}

    def _capa_k(self, k: int, t: float, cuadro: int, apertura: float | None = None) -> dict:
        """Igual que `Video._capa_k`: una pausa es la escena anterior congelada (gris) + la de Tito."""
        e = self.v.escenas[k]
        if not e.congela or k == 0:
            return self._capa(e, t, cuadro, apertura)
        j = k - 1
        while j > 0 and self.v.escenas[j].congela:
            j -= 1
        prev = self.v.escenas[j]
        base = self._capa(prev, prev.duracion - 1e-3, cuadro, apertura=0.0)
        fr, fi = self._lista(e, t, cuadro, apertura)
        if e.girar:
            return {**base, "c": list(e.camara_en(t)), "fr": base["fr"] + base["fi"], "fi": fr + fi, "giro": True}
        u = recortar(t / 0.2) * recortar((e.duracion - t) / 0.2)
        return {**base, "pausa": _r(u, 3), "en": fr + fi}

    def cuadro(self, i: int) -> dict:
        v = self.v
        t = i / v.fps
        inicio = 0.0
        for k, e in enumerate(v.escenas):
            if t < inicio + e.duracion or k == len(v.escenas) - 1:
                tl_ = t - inicio
                a = self._capa_k(k, tl_, i)
                b, tr = None, None
                tipo, tdur = e.transicion
                if k > 0 and tdur > 0 and tl_ < tdur:
                    prev = v.escenas[k - 1]
                    b = self._capa_k(k - 1, prev.duracion + tl_, i)
                    tr = [tipo, _r(tl_ / tdur, 4)]
                sub = v.encima(t)       # los MISMOS subtítulos que el motor actual (caminos SVG)
                return {"t": _r(t, 3), "esc": k, "tl": _r(tl_, 3), "tono": e.tono_en(tl_), "a": a, "b": b,
                        "tr": tr, "sub": sub}
            inicio += e.duracion
        raise IndexError(i)

    def todo(self) -> dict:
        cuadros = [self.cuadro(i) for i in range(self.v.total_cuadros)]
        return {"fps": self.v.fps, "ancho": self.v.ancho, "alto": self.v.alto, "duracion": _r(self.v.duracion, 3),
                "personajes": self.personajes, "legacy": self.legacy, "cuadros": cuadros}


def exportar(video: tl.Video, destino: Path) -> dict:
    """Escribe el JSON para Remotion y devuelve un resumen (cuadros, tamaño)."""
    datos = Exportador(video).todo()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"cuadros": len(datos["cuadros"]), "bytes": destino.stat().st_size,
            "props_viejos": sorted({k.split("{")[0] for k in datos["legacy"]})}
