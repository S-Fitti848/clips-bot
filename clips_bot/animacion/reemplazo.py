"""Así Nació: una escena que sigue sin pasar el estándar después de las 2 vueltas de corrección se reemplaza por una
de la BIBLIOTECA DE ESCENAS APROBADAS (Santi, 2026-11-16).

- La biblioteca (`data/animacion/escenas_estandar.json`) guarda las escenas que pasaron el estándar en un video
  (`guardar_aprobadas`), con el objeto protagonista como variable.
- `reemplazar` prueba candidatas de OTROS videos, adaptadas a esa frase (`adaptar`: mismo protagonista, los
  personajes de esa escena, el mismo lugar, época y luz), sin pedir dibujos nuevos; cada candidata la mira Haiku con 3
  cuadros (`chequear`), no la revisión completa.
- Empalme (`empalmar`): se arma la línea de tiempo entera con la escena nueva, pero en el video solo se cambia el
  tramo de ESA escena (misma duración, misma transición): las demás escenas, la voz, los subtítulos y los efectos de
  sonido de afuera quedan idénticos. El render del video es uno solo, al final.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from datetime import date
from pathlib import Path

from clips_bot.config import DATA_DIR

log = logging.getLogger(__name__)

BIBLIOTECA = DATA_DIR / "animacion" / "escenas_estandar.json"
MAX_GUARDADAS = 300
MAX_CANDIDATAS = 4
TOPE_CORRECCIONES_USD = 0.50      # Santi, 2026-11-16: si las correcciones de un video pasan de esto, se frena y avisa
OBJETO = "{objeto}"
# las de uso e inspiración dependen de las partes dibujadas de SU producto: no se pasan a otro
NO_REUSABLES = {"uso_manos", "inspiracion"}
CONTINUIDAD = ("frase", "parte", "fondo", "anio_escena", "viaje_a_anio", "vuelve_al_presente", "decorado", "claves",
               "emoji", "texto_pantalla")


def cargar(ruta: Path | None = None) -> list[dict]:
    ruta = ruta or BIBLIOTECA
    try:
        return list(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def _protagonista(d: dict) -> str:
    from .marcas import prop_real

    return prop_real(d.get("protagonista") or {})


def escenas_que_pasaron(datos: dict, claves: list, problemas: list[dict]) -> set[int]:
    """Las frases (índice del guion) que se revisaron en la última mirada y no tienen ningún problema."""
    malos = {int(p.get("cuadro") or 0) for p in problemas}
    out, todas = set(), {}
    for n, (_t, i, _q) in enumerate(claves, 1):
        e = datos["escenas"][i]
        k = e.get("frase")
        if not isinstance(k, int) or e.get("gancho_v3") or e.get("girar"):
            continue
        todas.setdefault(k, True)
        if n in malos:
            todas[k] = False
    out = {k for k, ok in todas.items() if ok}
    return out


def guardar_aprobadas(d: dict, frases_ok: set[int], video: str, marca: str, ruta: Path | None = None) -> int:
    """Suma a la biblioteca las escenas de este video que pasaron el estándar (el protagonista como variable)."""
    ruta = ruta or BIBLIOTECA
    prota = _protagonista(d)
    lib = [x for x in cargar(ruta) if x.get("video") != video]
    n = 0
    for k in sorted(frases_ok):
        if k == 0 or k >= len(d.get("escenas") or []):
            continue
        spec = copy.deepcopy(d["escenas"][k])
        if spec.get("accion_escena") in NO_REUSABLES:
            continue
        for o in spec.get("objetos") or []:
            if (o.get("dibujo") or o.get("prop")) == prota or o.get("prop") == prota:
                o["prop"], o["dibujo"] = OBJETO, ""
        lib.append({"video": video, "marca": marca, "fecha": date.today().isoformat(), "k": k,
                    "parte": spec.get("parte"), "accion_escena": spec.get("accion_escena") or "libre",
                    "plano": spec.get("plano") or "", "frase": str(spec.get("frase") or ""), "spec": spec})
        n += 1
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(lib[-MAX_GUARDADAS:], ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as err:
        log.warning("biblioteca de escenas aprobadas: no pude guardar (%s)", err)
    return n


def _palabras(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-záéíóúñ]{4,}", (t or "").lower())}


def candidatas(lib: list[dict], actual: dict, video: str, marca: str, maximo: int = MAX_CANDIDATAS) -> list[dict]:
    """De otros videos, distintas de la acción que falló, primero las de la misma parte del relato y las que más se
    parecen a la frase."""
    pal = _palabras(str(actual.get("frase") or ""))
    vistas, out = set(), []
    for x in sorted(lib, key=lambda x: (-(x.get("parte") == actual.get("parte")) * 3
                                         - len(pal & _palabras(x.get("frase") or "")), x.get("fecha", "")),
                    ):
        if x.get("video") == video or x.get("marca") == marca or x.get("accion_escena") in NO_REUSABLES:
            continue
        firma = (x.get("accion_escena"), x.get("plano"), x.get("marca"))
        if ((x.get("accion_escena") or "libre") == (actual.get("accion_escena") or "libre")
                and (x.get("plano") or "") == (actual.get("plano") or "")):     # la que falló, no
            continue
        if firma in vistas:
            continue
        vistas.add(firma)
        out.append(x)
        if len(out) >= maximo:
            break
    return out


def adaptar(cand: dict, d: dict, k: int) -> dict | None:
    """La escena aprobada con lo de ESTA frase: el texto, el lugar, la época, la luz, el decorado y los viajes de la
    escena vieja; el protagonista de este video; los personajes de esta escena (o de las vecinas). None si necesita un
    dibujo que no está (no se piden dibujos nuevos)."""
    from . import escenas as esc

    actual = d["escenas"][k]
    nuevo = copy.deepcopy(cand["spec"])
    for clave in CONTINUIDAD:
        if clave in actual:
            nuevo[clave] = copy.deepcopy(actual[clave])
        else:
            nuevo.pop(clave, None)
    nuevo.pop("dibujo_nuevo", None)
    nuevo.pop("accion_nueva", None)
    prota = _protagonista(d)
    objetos = []
    for o in nuevo.get("objetos") or []:
        if o.get("prop") == OBJETO:
            objetos.append({**o, "prop": prota, "dibujo": ""})
        elif o.get("prop") and o.get("prop") != "dibujo_nuevo" and esc.es_prop(str(o["prop"])):
            objetos.append(o)
    if not prota or not esc.es_prop(prota):
        return None
    nuevo["objetos"] = objetos
    gente = list(actual.get("actores") or [])
    if not gente:   # los personajes de las escenas vecinas (los mismos del video)
        for j in (k - 1, k + 1):
            if 0 <= j < len(d["escenas"]) and d["escenas"][j].get("actores"):
                gente = list(d["escenas"][j]["actores"])
                break
    apr = list(nuevo.get("actores") or [])
    if apr:
        n = min(len(apr), len(gente)) if gente else 0
        nuevo["actores"] = [{**apr[i], **{c: gente[i][c] for c in ("rol", "genero", "edad", "persona_real")
                                          if c in gente[i]}} for i in range(n)]
    return nuevo


def tramos(datos: dict, k: int) -> list[tuple[int, float, float]]:
    """(índice, desde, hasta) de las escenas de la línea de tiempo que son la acción de la frase k (sin el gancho, el
    viaje en el tiempo, el mapa ni la pausa de Tito)."""
    t, out = 0.0, []
    for i, e in enumerate(datos["escenas"]):
        dur = float(e["duracion"])
        if e.get("frase") == k and not e.get("gancho_v3") and not e.get("girar") and not e.get("congela"):
            out.append((i, t, t + dur))
        t += dur
    return out


def empalmar(viejo: dict, sfx_viejo: list, nuevo: dict, sfx_nuevo: list, k: int):
    """El video viejo con SOLO el tramo de la frase k tomado del nuevo. None si los tramos no coinciden en cantidad o
    en duración (el empalme correría la voz)."""
    a, b = tramos(viejo, k), tramos(nuevo, k)
    if not a or len(a) != len(b):
        return None
    if any(abs((x[2] - x[1]) - (y[2] - y[1])) > 1e-3 or abs(x[1] - y[1]) > 1e-3 for x, y in zip(a, b)):
        return None
    out = copy.deepcopy(viejo)
    sfx = list(sfx_viejo)
    for (i, t0, t1), (j, _, _) in zip(a, b):
        escena = copy.deepcopy(nuevo["escenas"][j])
        if "transicion" in viejo["escenas"][i]:          # el empalme con la escena de antes, como estaba
            escena["transicion"] = copy.deepcopy(viejo["escenas"][i]["transicion"])
        else:
            escena.pop("transicion", None)
        out["escenas"][i] = escena
        sfx = [s for s in sfx if not (t0 <= s[0] < t1)] + [s for s in sfx_nuevo if t0 <= s[0] < t1]
    return out, sorted(sfx)


SISTEMA_HAIKU = """Mirás 3 cuadros de UNA escena de un video animado corto (dibujos planos) y decís si pasa el estándar del
canal para lo que dice la voz en ese momento. Sé exigente: si algo de la lista no se cumple, `cumple` = false y en `que`
decí qué se ve mal."""
SCHEMA_HAIKU = {"type": "OBJECT", "properties": {"cumple": {"type": "BOOLEAN"}, "que": {"type": "STRING"}},
                "required": ["cumple", "que"]}
REGLAS_ESCENA = ("AN-02", "AN-03", "AN-05", "AN-06", "AN-07")


def chequear(haiku, datos: dict, k: int, frase: str, ids: list[str], carpeta: Path, n: int,
             capturar=None) -> tuple[bool, str]:
    """Haiku mira 3 cuadros de la escena k (no la revisión completa)."""
    from clips_bot import calidad

    from . import render as rd
    from .marcas import _jpeg_512
    from .timeline import Video

    tr = tramos(datos, k)
    if not tr or haiku is None:
        return False, "sin escena o sin Haiku"
    t0, t1 = tr[0][1], tr[-1][2]
    video = Video.desde_dict({**datos, "audio": None})
    imagenes = []
    for j, f in enumerate((0.2, 0.5, 0.8)):
        png = carpeta / f"reemplazo_{k + 1}_{n}_{j}.png"
        t = t0 + (t1 - t0) * f
        if capturar:
            capturar(datos, t, png)
        else:
            rd.cuadro_png(video, min(video.total_cuadros - 1, int(t * video.fps)), png, escala=0.35)
        imagenes.append(_jpeg_512(png))
    reglas_ = calidad.por_id("asinacio")
    lista = "\n".join(f"- {r}: {reglas_[r].texto}" for r in dict.fromkeys(list(ids) + list(REGLAS_ESCENA))
                      if r in reglas_)
    try:
        r = json.loads(haiku.json(SISTEMA_HAIKU, f"La voz dice: «{frase}»\n\nReglas:\n{lista}", SCHEMA_HAIKU, 0.1,
                                  imagenes=imagenes))
    except Exception as err:  # noqa: BLE001
        return False, f"Haiku no respondió ({str(err)[:80]})"
    return bool(r.get("cumple")), str(r.get("que") or "")[:200]


def reemplazar(haiku, d: dict, datos: dict, sfx: list, k: int, ids: list[str], armar, video: str, marca: str,
               carpeta: Path, sigue=lambda: True, avisar=log.info, capturar=None, lib: list[dict] | None = None):
    """Prueba candidatas de la biblioteca para la frase k. (datos, sfx, d, texto) con la primera que pase, o None.
    `armar(d)` → (datos, sfx) de la línea de tiempo entera; `sigue()` False = se pasó el tope de costo."""
    lib = cargar() if lib is None else lib
    actual = d["escenas"][k]
    for n, cand in enumerate(candidatas(lib, actual, video, marca), 1):
        if not sigue():
            avisar("reemplazo de escenas: frené por el tope de costo")
            break
        nuevo_spec = adaptar(cand, d, k)
        if nuevo_spec is None:
            continue
        d2 = copy.deepcopy(d)
        d2["escenas"][k] = nuevo_spec
        # cada video único (Santi, 2026-11-17): una escena de la biblioteca no puede pasar el tope de un tercio de
        # escenas repetidas de los últimos 10 videos (si el video ya estaba pasado, por lo menos no lo empeora)
        from . import marcas as _m

        prev = _m.ESCENAS_PREVIAS
        antes, despues = len(_m.repetidas(d, prev)), len(_m.repetidas(d2, prev))
        if despues > _m.tope_repetidas(d2) and despues > antes:
            avisar(f"reemplazo escena {k + 1}: la candidata {n} repite escenas de más ({_m.firma_escena(nuevo_spec)})")
            continue
        prota = _m.prop_real(d.get("protagonista") or {})
        if _m.firma_completa(nuevo_spec, prota) in {f for v in _m.COMPLETAS_PREVIAS[-_m.VIDEOS_UNICOS:] for f in v}:
            avisar(f"reemplazo escena {k + 1}: la candidata {n} quedaría igual a una escena de otro video")
            continue
        try:
            datos2, sfx2 = armar(d2)
        except Exception as err:  # noqa: BLE001 — una candidata que no se arma se saltea
            avisar(f"reemplazo escena {k + 1}: la candidata {n} no se arma ({str(err)[:100]})")
            continue
        unido = empalmar(datos, sfx, datos2, sfx2, k)
        if unido is None:
            avisar(f"reemplazo escena {k + 1}: la candidata {n} no empalma (otra duración)")
            continue
        ok, que = chequear(haiku, unido[0], k, str(actual.get("frase") or ""), ids, carpeta, n, capturar)
        avisar(f"reemplazo escena {k + 1}: candidata {n} ({cand.get('marca')}, {cand.get('accion_escena')}) → "
               f"{'pasa' if ok else 'no pasa'}: {que[:100]}")
        if ok:
            d["escenas"][k] = nuevo_spec
            return unido[0], unido[1], d, (f"escena {k + 1}: reemplazada por una aprobada de {cand.get('marca')} "
                                           f"({cand.get('accion_escena')}{', ' + cand['plano'] if cand.get('plano') else ''})")
    return None
