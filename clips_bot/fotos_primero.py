"""Fotos primero, guion después (Santi, 2026-11-25: "que los videos salgan bien al primer intento").

La semana del 18 al 25/11 solo 2 de 24 videos de Pequeña Historia pasaron el estándar y casi todas las caídas fueron por
fotos: el guion se escribía primero y después se buscaban fotos para frases que no tenían ninguna (PH-02 en 17 de 24,
borrosas en 9, de otra época en 8). Ahora, ANTES de pedir el guion:

1. Se juntan las fotos libres de la historia (las del artículo, Commons con el título en castellano y en inglés, y las
   otras fuentes libres), se bajan y el código saca las chicas, las borrosas y las con mucho texto.
2. Haiku describe cada una en UN pedido: qué se ve, si es nítida, de qué época es lo que muestra, si es de ESTA
   historia y lo de siempre (dura, político, retrato de quién). Se queda solo con las nítidas, de la época, de la
   historia y sin problemas.
3. Con menos de MINIMO (8), la historia no se usa: no se gasta el guion.
4. Sonnet escribe el guion con esa lista delante (`contexto`): cada frase tiene que poder mostrarse con una de esas fotos.
5. Haiku (solo texto) dice qué fotos van con cada frase, y de ahí sigue el armado de siempre (`ilustrar`, tarjetas,
   control del 70 %); la revisión del video terminado no cambia.

Interruptor: `efemerides.fotos_primero` (tecnología, la reserva y Latinoamérica).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

MINIMO = 8              # Santi, 2026-11-25: 8 fotos buenas como mínimo (avisar antes de bajarlo)
MAX_CANDIDATAS = 24     # las que se bajan y se le muestran a Haiku (un pedido)
POR_FRASE = 3
DESCRIPCION_V = 1
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache_claude" / "fotos_primero"
TIPOS_MALOS = {"captura", "documento", "grafico", "mapa", "logo", "diagrama", "planilla"}

SISTEMA = """Mirás fotos para un video corto de historia ("Pequeña Historia"). De cada foto decís, en castellano:
- se_ve: qué se ve, concreto, en una línea ("una Game Boy gris en una mano", "Gunpei Yokoi sonriendo en 1990").
- nitida: true si se ve nítida y con buena calidad en un celular; false si está borrosa, pixelada, muy oscura, es un
  recorte de diario ilegible o una miniatura agrandada.
- epoca: de qué año o década es lo que se VE ("1989", "años 80", "actual"); anio: el año aproximado (0 si no se sabe).
- de_epoca: true si lo que se ve corresponde a la época de la historia que te paso (un producto de ese año fotografiado
  hoy en un museo SÍ cuenta; una calle de hoy, un modelo nuevo o gente de hoy en una historia de 1970, NO).
- de_la_historia: true si muestra a la persona, el objeto, el lugar o algo directo de ESTA historia; false si es de otra
  cosa (otro producto, otra ciudad, otra persona) o algo genérico que no se puede atar a la historia.
- tipo: foto | captura | documento | grafico | mapa | logo | ilustracion.
- texto_otro_idioma: true si tiene texto visible en un idioma que no es castellano ni inglés.
- dura: true si muestra muertos o heridos. politico: true si es un político o un acto de gobierno. retrato: true si es
  el retrato de una persona. quien: el nombre de la persona si se sabe por la foto o su epígrafe, o "".
Respondé SOLO el JSON pedido, una entrada por foto, con su número."""

SCHEMA = {
    "type": "object",
    "properties": {"fotos": {"type": "array", "items": {"type": "object", "properties": {
        "foto": {"type": "integer"}, "se_ve": {"type": "string"}, "nitida": {"type": "boolean"},
        "epoca": {"type": "string"}, "anio": {"type": "integer"}, "de_epoca": {"type": "boolean"},
        "de_la_historia": {"type": "boolean"}, "tipo": {"type": "string"},
        "texto_otro_idioma": {"type": "boolean"}, "dura": {"type": "boolean"}, "politico": {"type": "boolean"},
        "retrato": {"type": "boolean"}, "quien": {"type": "string"}},
        "required": ["foto", "se_ve", "nitida", "epoca", "de_epoca", "de_la_historia", "tipo"]}}},
    "required": ["fotos"],
}

SISTEMA_ASIGNAR = """Te paso las frases de un guion y las fotos que hay (con lo que muestra cada una). Para cada frase,
decí las fotos (hasta 3, la mejor primero) que muestran LO QUE DICE ESA FRASE. Si ninguna lo muestra, la lista vacía:
no pongas una foto que no tiene que ver. Para la frase 1 (el gancho), la más impactante primero."""

SCHEMA_ASIGNAR = {
    "type": "object",
    "properties": {"frases": {"type": "array", "items": {"type": "object", "properties": {
        "frase": {"type": "integer"}, "fotos": {"type": "array", "items": {"type": "integer"}}},
        "required": ["frase", "fotos"]}}},
    "required": ["frases"],
}


class FotosPrevias(Exception):
    """La historia no tiene MINIMO fotos buenas: no se escribe el guion."""

    def __init__(self, buenas: int, motivos: dict, costo_usd: float = 0.0):
        self.buenas, self.motivos = buenas, motivos
        super().__init__(f"solo {buenas} fotos buenas antes del guion (mínimo {MINIMO}; "
                         + ", ".join(f"{k} {v}" for k, v in sorted(motivos.items(), key=lambda kv: -kv[1])[:4]) + ")")


@dataclass
class Banco:
    pool: list                                  # Foto, bajadas (el pool del video empieza con estas)
    buenas: list[int]                           # índices del pool que pasaron
    desc: dict[int, dict] = field(default_factory=dict)
    motivos: dict = field(default_factory=dict)
    haiku: object = None                        # para `asignar`

    def contexto(self) -> str:
        lineas = [f"F{n}: {self.desc[k].get('se_ve', '')} ({self.desc[k].get('epoca') or 'sin fecha'})"
                  for n, k in enumerate(self.buenas, 1)]
        return ("\n\nFOTOS QUE HAY PARA ESTE VIDEO (Santi, 2026-11-25: el guion se escribe A PARTIR de las fotos). "
                "Cada frase tiene que poder mostrarse con una de estas fotos: no escribas frases sobre cosas que no se "
                "ven en ninguna (si un dato importante no tiene foto, contalo en la misma frase que algo que sí la "
                "tiene). El gancho, con lo que muestra la foto más impactante.\n" + "\n".join(lineas))


def _sumar(lista: list, nuevas, vistas: set) -> None:
    from .efemerides import clave_archivo

    for f in nuevas:
        k = clave_archivo(f.archivo)
        if k not in vistas:
            vistas.add(k)
            lista.append(f)


def candidatas(wiki, e, fotos_articulo: list, fuentes=None, avisar=log.info) -> list:
    """Las fotos libres de la historia, sin Claude: artículo, Commons (título en castellano y en inglés) y las otras
    fuentes libres (Openverse, Smithsonian, Europeana, Flickr, Internet Archive; nada de stock)."""
    from . import efemerides as ef
    from . import fuentes_fotos

    out, vistas = [], set()
    _sumar(out, fotos_articulo, vistas)
    nombres = [re.sub(r"\s*\(.*?\)", "", e.paginas[0].replace("_", " ")).strip()]
    try:
        en = wiki.en_ingles(e.paginas[0]) if e.lang == "es" else None
    except Exception:  # noqa: BLE001
        en = None
    if en:
        nombres.append(re.sub(r"\s*\(.*?\)", "", en.replace("_", " ")).strip())
    nombres = list(dict.fromkeys(nombres))
    for q in nombres + [f"{n} {e.anio}" for n in nombres]:
        if len(out) >= MAX_CANDIDATAS:
            break
        try:
            nuevas, _ = ef.filtrar_infos(wiki, "commons", wiki.buscar_commons(q, cuantas=12), f"Commons: {q}", e.anio)
        except Exception as err:  # noqa: BLE001 — una fuente caída no frena
            avisar(f"    fotos primero: Commons «{q}» falló ({str(err)[:80]})")
            continue
        _sumar(out, nuevas, vistas)
    if len(out) < MAX_CANDIDATAS:
        otras = fuentes or fuentes_fotos.Fuentes()
        try:
            halladas = otras.buscar(nombres, False, False, MAX_CANDIDATAS - len(out), avisar)
        except Exception as err:  # noqa: BLE001
            avisar(f"    fotos primero: otras fuentes fallaron ({str(err)[:80]})")
            halladas = []
        _sumar(out, [ef._foto_de(h, nombres[0]) for h in halladas], vistas)
    return out[:MAX_CANDIDATAS]


def _huella(ruta) -> str:
    import hashlib

    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()[:24]


def describir(haiku, pool: list, historia: str, anio: int, avisar=log.info) -> dict[int, dict]:
    """{índice: descripción}. Las ya descriptas (misma imagen y misma historia) salen de la caché."""
    from . import efemerides as ef
    from .narrar import NarrarError

    out: dict[int, dict] = {}
    faltan: list[int] = []
    clave_h = re.sub(r"\W+", "", historia.lower())[:40]
    for k, f in enumerate(pool):
        try:
            x = json.loads((CACHE / f"{_huella(f.ruta)}_{clave_h}.json").read_text(encoding="utf-8"))
            if x.get("v") == DESCRIPCION_V:
                out[k] = x
                continue
        except (OSError, ValueError):
            pass
        faltan.append(k)
    if faltan:
        imagenes = [ef._jpeg_chico(Path(pool[k].ruta), 384) for k in faltan]
        lista = "\n".join(f"foto {j}: {pool[k].archivo.replace('File:', '')[:90]} — {pool[k].epigrafe[:120]}"
                          + (f" (fechada {pool[k].anio})" if pool[k].anio else "")
                          for j, k in enumerate(faltan, 1))
        try:
            d = json.loads(haiku.json(SISTEMA, f"LA HISTORIA ({anio}): {historia[:600]}\n\nSon {len(faltan)} fotos, "
                                               f"numeradas de 1 a {len(faltan)}. Epígrafe de cada una:\n{lista}",
                                      SCHEMA, imagenes=imagenes))
        except Exception as err:  # noqa: BLE001
            raise NarrarError(f"no pude describir las fotos ({str(err)[:120]})") from err
        por_num = {x.get("foto"): x for x in d.get("fotos") or [] if isinstance(x, dict)}
        for j, k in enumerate(faltan, 1):
            x = por_num.get(j)
            if not x:
                continue
            x = dict(x, v=DESCRIPCION_V)
            out[k] = x
            try:
                CACHE.mkdir(parents=True, exist_ok=True)
                (CACHE / f"{_huella(pool[k].ruta)}_{clave_h}.json").write_text(json.dumps(x, ensure_ascii=False),
                                                                               encoding="utf-8")
            except OSError:
                pass
    avisar(f"    fotos primero: {len(pool) - len(faltan)} ya descriptas, {len(faltan)} nuevas (Haiku)")
    return out


def motivo(desc: dict | None, historia: str) -> str | None:
    """Por qué una foto descripta no sirve, o None."""
    from .efemerides import motivo_persona

    if not desc:
        return "sin describir"
    if desc.get("nitida") is False:
        return "borrosa"
    if desc.get("de_epoca") is False:
        return "de otra época"
    if desc.get("de_la_historia") is False:
        return "no es de la historia"
    if str(desc.get("tipo") or "foto").lower() in TIPOS_MALOS:
        return f"es un {desc.get('tipo')}"
    if desc.get("texto_otro_idioma"):
        return "texto en otro idioma"
    if desc.get("dura"):
        return "muertos o heridos"
    return motivo_persona(desc, historia) and "persona que la historia no nombra"


def juntar(wiki, haiku, e, fotos_articulo: list, carpeta: Path, historia: str, avisar=log.info,
           fuentes=None, minimo: int = MINIMO) -> Banco:
    """Pasos 1-3: las fotos buenas de la historia, o FotosPrevias."""
    from . import efemerides as ef

    cands = candidatas(wiki, e, fotos_articulo, fuentes, avisar)
    bajadas, _ = ef.bajar_fotos(wiki, cands, carpeta, f"{e.anio}_fp", len(cands), avisar)
    motivos: dict = {}
    pool = []
    for f in bajadas:       # el código primero (gratis): chicas, borrosas y con mucho texto
        m = ef.motivo_calidad(f.ruta)
        if m is None and ef.fraccion_texto(Path(f.ruta)) > ef.UMBRAL_TEXTO_OCR:
            m = "mucho texto"
        if m:
            k = m.split(" (")[0]
            motivos[k] = motivos.get(k, 0) + 1
            continue
        pool.append(f)
    avisar(f"  fotos primero: {len(cands)} candidatas, {len(bajadas)} bajadas, {len(pool)} pasan el código {motivos}")
    if len(pool) < minimo:
        raise FotosPrevias(len(pool), motivos)
    desc = describir(haiku, pool, historia, e.anio, avisar)
    buenas = []
    for k in range(len(pool)):
        m = motivo(desc.get(k), historia)
        if m:
            motivos[m] = motivos.get(m, 0) + 1
            avisar(f"    F{k + 1} afuera ({m}): {(desc.get(k) or {}).get('se_ve', '')[:70]}")
        else:
            buenas.append(k)
    avisar(f"  fotos primero: {len(buenas)} buenas de {len(pool)} {motivos}")
    if len(buenas) < minimo:
        raise FotosPrevias(len(buenas), motivos)
    return Banco(pool, buenas, desc, motivos, haiku)


def asignar(haiku, frases: list[str], banco: Banco, avisar=log.info) -> list[list[int]]:
    """Paso 5: por frase, los índices del pool (hasta POR_FRASE) que muestran lo que dice (Haiku, solo texto)."""
    fotos = "\n".join(f"F{n}: {banco.desc[k].get('se_ve', '')} ({banco.desc[k].get('epoca') or 'sin fecha'})"
                      for n, k in enumerate(banco.buenas, 1))
    texto = "\n".join(f"frase {i}: {f}" for i, f in enumerate(frases, 1))
    d = json.loads(haiku.json(SISTEMA_ASIGNAR, f"FRASES:\n{texto}\n\nFOTOS:\n{fotos}\n\nRespondé con el número de "
                                               "foto sin la F.", SCHEMA_ASIGNAR))
    por = {x.get("frase"): x.get("fotos") or [] for x in d.get("frases") or [] if isinstance(x, dict)}
    out = []
    for i in range(1, len(frases) + 1):
        ids = [n for n in por.get(i, []) if isinstance(n, int) and 1 <= n <= len(banco.buenas)]
        out.append(list(dict.fromkeys(banco.buenas[n - 1] for n in ids))[:POR_FRASE])
    avisar("    fotos primero, por frase: " + " | ".join(f"{i + 1}:{[banco.buenas.index(k) + 1 for k in r]}"
                                                       for i, r in enumerate(out)))
    return out
