"""Fotos que muestran lo que se dice: regla fija para todo video narrado con fotos (decisión de
Santi, 2026-09-28). Hoy lo usa Pequeña Historia; cualquier narración con fotos pasa por acá.

1. Por cada frase del guion, Gemini anota qué mostrar ("petri dish bacteria", "Penicillium mold").
2. El bot busca candidatas (en el artículo y en Commons, por categoría y por palabras, con los
   filtros de siempre) y Gemini ordena, en UNA llamada, las que sirven para cada frase.
3. Acá, sin Gemini:
   - `asignar`: una foto por frase, la mejor que todavía no salió; repetir solo si no hay otra.
   - `tramos`: ninguna foto más de MAX_TRAMO_S seguidos. Una frase larga se parte y la segunda
     parte lleva otra foto de su lista; dos frases seguidas con la misma foto cuentan juntas.
   - `errores_plan`: mínimo MIN_FOTOS_DISTINTAS fotos distintas y ningún tramo largo.
"""

from __future__ import annotations

import math

MIN_FOTOS_DISTINTAS = 6
# La época le gana a la cantidad (2026-09-29): si no hay 6 fotos de la época del hecho, el mínimo
# baja a las que haya (repitiendo las del artículo), pero con menos de MIN_FOTOS_ABSOLUTO el hecho
# NO se usa y se pasa al siguiente del día (pedido de Santi: "que pase al siguiente hecho en vez de
# repetir fotos"). Solo si ninguno llega se usa el que más tenga, con aviso, y nunca con menos de
# MIN_FOTOS_RESPALDO (con una sola foto no se puede cumplir lo de 6 s seguidos).
MIN_FOTOS_ABSOLUTO = 4
MIN_FOTOS_RESPALDO = 2
MAX_TRAMO_S = 6.0
RANKING_MAX = 3          # fotos que Gemini ordena por frase
# Una misma imagen no aparece más de esto en todo el video (2026-10-02: en la del gol olímpico se
# repitieron 2 fotos por todo el video). Una aparición = cada vez que vuelve a verse.
MAX_APARICIONES = 2


def apariciones(plan: list[tuple[int, int, float]]) -> dict[int, int]:
    """{foto: cuántas veces aparece}: dos tramos seguidos con la misma foto son una sola aparición."""
    out: dict[int, int] = {}
    previa = None
    for _, f, _ in plan:
        if f != previa:
            out[f] = out.get(f, 0) + 1
        previa = f
    return out


def asignar(rankings: list[list[int]], pool: list[int]) -> list[int]:
    """La foto de cada frase. `rankings[i]`: las que sirven para la frase i, de mejor a peor.
    `pool`: las que se pueden usar si una frase no tiene ninguna (las fotos del hecho).

    Orden de preferencia: la mejor de su lista que no salió todavía → una del pool que no salió →
    repetir la de su lista que salió hace más tiempo (y no es la de la frase anterior)."""
    ultimo_uso: dict[int, int] = {}
    out: list[int] = []
    for i, rk in enumerate(rankings):
        elegida = next((f for f in rk if f not in ultimo_uso), None)
        if elegida is None and not rk:
            elegida = next((f for f in pool if f not in ultimo_uso), None)
        if elegida is None:
            opciones = rk or pool
            if not opciones:
                raise ValueError(f"la frase {i + 1} no tiene ninguna foto posible")
            distintas = [f for f in opciones if not out or f != out[-1]] or opciones
            elegida = min(distintas, key=lambda f: ultimo_uso.get(f, -1))
        ultimo_uso[elegida] = i
        out.append(elegida)
    return out


def completar_distintas(fotos: list[int], rankings: list[list[int]], pool: list[int],
                        minimo: int = MIN_FOTOS_DISTINTAS) -> list[int]:
    """Si hay menos de `minimo` fotos distintas, cambia las repeticiones por fotos que todavía no
    salieron: primero las que Gemini puso para esa frase, después las del pool."""
    fotos = list(fotos)
    vistas: set[int] = set()
    for i, f in enumerate(fotos):
        if len(set(fotos)) >= minimo:
            break
        if f in vistas:
            nueva = next((x for x in rankings[i] + pool if x not in fotos), None)
            if nueva is not None:
                fotos[i] = nueva
        vistas.add(fotos[i])
    return fotos


def _otra(ranking: list[int], pool: list[int], evitar: int | None, ya: set[int]) -> int | None:
    """Otra foto para seguir la misma frase: nueva de su lista → nueva del pool → cualquiera de su
    lista distinta de `evitar` → cualquiera del pool distinta de `evitar`."""
    for opciones in ([f for f in ranking if f not in ya], [f for f in pool if f not in ya],
                     [f for f in ranking if f != evitar], [f for f in pool if f != evitar]):
        if opciones:
            return opciones[0]
    return None


def tramos(fotos: list[int], duraciones: list[float], rankings: list[list[int]],
           pool: list[int], max_s: float = MAX_TRAMO_S,
           max_apariciones: int = MAX_APARICIONES) -> list[tuple[int, int, float]]:
    """(frase, foto, segundos) en orden. Ninguna foto se ve más de `max_s` seguidos ni aparece más
    de `max_apariciones` veces (si hay otra que la reemplace)."""
    out: list[tuple[int, int, float]] = []
    ya = set(fotos)
    veces: dict[int, int] = {}

    def gastada(g: int) -> bool:
        return veces.get(g, 0) >= max_apariciones
    for i, (f, dur) in enumerate(zip(fotos, duraciones)):
        partes = max(1, math.ceil(dur / max_s - 1e-9))
        seg = dur / partes
        rk = rankings[i] if i < len(rankings) else []
        for k in range(partes):
            foto = f if k == 0 else None
            previa = out[-1][1] if out else None
            corrido = 0.0
            for _, g, s in reversed(out):
                if g != previa:
                    break
                corrido += s
            if foto is None or (foto == previa and corrido + seg > max_s + 1e-6):
                foto = _otra(rk, pool, previa, ya) if previa is not None else f
                if foto is None:
                    foto = f
            if foto != previa and gastada(foto):
                # Ya apareció las veces permitidas: otra de su lista o del pool que no esté gastada.
                otra = next((g for g in rk + pool if g != previa and not gastada(g)), None)
                foto = otra if otra is not None else foto
            if foto != previa:
                veces[foto] = veces.get(foto, 0) + 1
            ya.add(foto)
            out.append((i, foto, seg))
    return out


def errores_plan(plan: list[tuple[int, int, float]], minimo: int = MIN_FOTOS_DISTINTAS,
                 max_s: float = MAX_TRAMO_S, max_apariciones: int = MAX_APARICIONES) -> list[str]:
    """Lo que no cumple la regla, en castellano (vacío = cumple)."""
    errores = []
    de_mas = {f: n for f, n in apariciones(plan).items() if n > max_apariciones}
    if de_mas:
        errores.append("fotos que aparecen más de " + str(max_apariciones) + " veces: "
                       + ", ".join(f"la {f + 1} ({n})" for f, n in sorted(de_mas.items())))
    distintas = len({f for _, f, _ in plan})
    if distintas < minimo:
        errores.append(f"hay {distintas} fotos distintas: tienen que ser al menos {minimo}")
    corrido, previa = 0.0, None
    for _, f, s in plan:
        corrido = corrido + s if f == previa else s
        previa = f
        if corrido > max_s + 1e-6:
            errores.append(f"la foto {f + 1} se ve {corrido:.1f} s seguidos (máximo {max_s:.0f} s)")
            break
    return errores
