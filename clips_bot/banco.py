"""Bancos de reserva (Santi, 2026-11-15: "nunca un día sin video").

Historias que NO dependen de la fecha (curiosidades, personajes, lugares; inventos y empresas de
tecnología; marcas de Así Nació), puntuadas de antemano con PUNTAJE_BANCO (8) o más. Se usan cuando la
mejor candidata del día queda debajo del piso absoluto (6) o cuando no hay candidatas. Cada banco tiene
al menos OBJETIVO (20) y se repone solo cuando baja de MINIMO (10).

Se guardan en bot_estado (`banco:<canal>`, una lista JSON). Se llenan cosechando otros días del año (los
que están lejos de hoy, así una historia de fecha no sale cerca de su aniversario): Wikipedia de ese día,
la misma clasificación y el mismo puntaje con Haiku que en producción; quedan solo las de 8 o más que no
son conmemoraciones ni fundaciones (esas sí dependen de la fecha).
"""
from __future__ import annotations

import json
import logging
import random
import time
from datetime import date, timedelta

from . import db

log = logging.getLogger(__name__)

CANALES = ("latam", "tecnologia", "asinacio")
NOMBRES = {"latam": "Latinoamérica", "tecnologia": "tecnología", "asinacio": "Así Nació"}
PUNTAJE_BANCO = 8.0
PISO_ABSOLUTO = 6.0     # debajo de esto, la mejor del día no sale: va una del banco
MINIMO = 10
OBJETIVO = 20
# Santi, 2026-11-25: el banco de tecnología es la fuente normal y "no tiene que bajar nunca de 15": empieza a llenar
# debajo de 20 (deja margen para los ~3 que se usan por día entre el video y la reserva) y sigue hasta 25
MINIMOS = {"tecnologia": 20}
OBJETIVOS = {"tecnologia": 25}
LEJOS_DIAS = 100        # se cosechan días a más de 100 días de hoy (lejos de su aniversario)
CLAVE = "banco:{}"
LLENANDO = "banco_llenando:{}"
CURSOR = "banco_cursor:{}"


# ---- guardar y leer ------------------------------------------------------------------------------

def leer(conn, canal: str) -> list[dict]:
    try:
        return json.loads(db.get_valor(conn, CLAVE.format(canal)) or "[]")
    except ValueError:
        return []


def guardar(conn, canal: str, items: list[dict]) -> None:
    db.set_valor(conn, CLAVE.format(canal), json.dumps(items, ensure_ascii=False))


def agregar(conn, canal: str, nuevos: list[dict]) -> int:
    """Suma los que no estaban (por `id`). Devuelve cuántos sumó."""
    items = leer(conn, canal)
    ids = {x.get("id") for x in items}
    malas = sin_fotos(conn, canal)
    sumados = []
    for x in nuevos:
        if _art(x.get("articulo") or (x.get("paginas") or [""])[0]) in malas:
            continue
        if x.get("id") and x["id"] not in ids and float(x.get("puntaje") or 0) >= minimo_banco(canal):
            ids.add(x["id"])
            sumados.append(x)
    if sumados:
        guardar(conn, canal, items + sumados)
    return len(sumados)


def minimo_banco(canal: str) -> float:
    """Tecnología: el mismo mínimo que el video del día para marcas, empresas y videojuegos (7,5; Santi, 2026-11-24:
    con 8 el banco sumó 2 historias en 60 días). Los demás bancos, PUNTAJE_BANCO (8)."""
    if canal == "tecnologia":
        from . import efemerides as ef

        return ef.PUNTAJE_TEC_MIN
    return PUNTAJE_BANCO


SIN_FOTOS = "sin_fotos:{}"     # bot_estado: {articulo: {"dia", "motivo"}} — historias que fallaron por fotos


def _art(x) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", str(x or "").replace("_", " ")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def sin_fotos(conn, canal: str) -> set[str]:
    """Los artículos que ya fallaron por fotos en ese canal (Santi, 2026-11-23: "marcá las que fallaron por fotos
    para no repetirlas"). No vencen: las fotos de Commons de un artículo cambian muy poco."""
    try:
        return set(json.loads(db.get_valor(conn, SIN_FOTOS.format(canal)) or "{}"))
    except ValueError:
        return set()


def marcar_sin_fotos(conn, canal: str, articulo: str, motivo: str, hoy: date | None = None) -> None:
    try:
        d = json.loads(db.get_valor(conn, SIN_FOTOS.format(canal)) or "{}")
    except ValueError:
        d = {}
    d[_art(articulo)] = {"dia": (hoy or _hoy_ar()).isoformat(), "motivo": str(motivo)[:160]}
    db.set_valor(conn, SIN_FOTOS.format(canal), json.dumps(d, ensure_ascii=False))
    # sale del banco (sin contarlo como uso): no se vuelve a intentar
    guardar(conn, canal, [x for x in leer(conn, canal)
                          if _art(x.get("articulo") or (x.get("paginas") or [""])[0]) != _art(articulo)])


def quitar(conn, canal: str, id_: str | None) -> None:
    """Sale del banco SIN contarlo como uso (la reserva de tecnología arma sus videos desde acá: Santi, 2026-11-23;
    eso no es "el día no tuvo nada")."""
    if id_:
        guardar(conn, canal, [x for x in leer(conn, canal) if x.get("id") != id_])


def sacar(conn, canal: str, id_: str | None, hoy: date | None = None) -> None:
    """La historia ya se usó: sale del banco (nunca se repite) y queda anotado el uso (USOS)."""
    if not id_:
        return
    items = leer(conn, canal)
    quedan = [x for x in items if x.get("id") != id_]
    if len(quedan) != len(items):
        guardar(conn, canal, quedan)
    anotar_uso(conn, canal, id_, hoy)


# ---- cuántas veces se usa (Santi, 2026-11-16: "el banco es la excepción") ---------------------------

USOS = "banco_usos"              # bot_estado: [{"canal", "dia", "id"}], los usos de los últimos 60 días
AVISO_USOS = "banco_usos_aviso"  # bot_estado, banco_usos_aviso:<canal>:<lunes>: ya se avisó esa semana
TOPE_SEMANA = 2                  # más de 2 usos por semana en un canal = su búsqueda necesita arreglo


def _usos(conn) -> list[dict]:
    try:
        return json.loads(db.get_valor(conn, USOS) or "[]")
    except ValueError:
        return []


def anotar_uso(conn, canal: str, id_: str, hoy: date | None = None) -> None:
    hoy = hoy or _hoy_ar()
    desde = (hoy - timedelta(days=60)).isoformat()
    usos = [u for u in _usos(conn) if u.get("dia", "") >= desde]
    usos.append({"canal": canal, "dia": hoy.isoformat(), "id": id_})
    db.set_valor(conn, USOS, json.dumps(usos, ensure_ascii=False))


def _hoy_ar() -> date:
    from datetime import datetime, timezone

    return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def usos_semana(conn, hoy: date | None = None) -> dict[str, int]:
    """{canal: usos} de la semana de `hoy` (lunes a domingo)."""
    lunes = lunes_de(hoy or _hoy_ar())
    fin = lunes + timedelta(days=6)
    out = {c: 0 for c in CANALES}
    for u in _usos(conn):
        if lunes.isoformat() <= u.get("dia", "") <= fin.isoformat() and u.get("canal") in out:
            out[u["canal"]] += 1
    return out


def texto_usos(conn, hoy: date | None = None) -> str:
    hoy = hoy or _hoy_ar()
    este, anterior = usos_semana(conn, hoy), usos_semana(conn, lunes_de(hoy) - timedelta(days=1))
    partes = []
    for c in CANALES:
        marca = " ⚠️" if este[c] > TOPE_SEMANA else ""
        partes.append(f"{NOMBRES[c]} {este[c]}{marca} (la anterior {anterior[c]})")
    return (f"<b>Banco de reserva</b>, usos esta semana (desde el lunes {lunes_de(hoy):%d/%m}; tope "
            f"{TOPE_SEMANA}): " + " · ".join(partes) + f"\nQuedan: {resumen(conn)}.")


def avisos_pendientes(conn, hoy: date | None = None) -> list[str]:
    """Los avisos de esta semana que todavía no se mandaron (una vez por canal y semana); los marca."""
    hoy = hoy or _hoy_ar()
    lunes = lunes_de(hoy).isoformat()
    out = []
    for c, n in usos_semana(conn, hoy).items():
        clave = f"{AVISO_USOS}:{c}:{lunes}"
        if n > TOPE_SEMANA and not db.get_valor(conn, clave):
            db.set_valor(conn, clave, "1")
            out.append(f"🔧 Claude Code: {NOMBRES[c]} ya usó el banco de reserva {n} veces esta semana "
                       f"(tope {TOPE_SEMANA}): la búsqueda de historias de ese canal necesita arreglo.")
    return out


def hay_que_reponer(conn, canal: str) -> bool:
    """Con menos de MINIMO (MINIMOS) empieza a llenar y sigue hasta OBJETIVO (OBJETIVOS; entonces para)."""
    n = len(leer(conn, canal))
    clave = LLENANDO.format(canal)
    if n < MINIMOS.get(canal, MINIMO):
        db.set_valor(conn, clave, "1")
    elif n >= OBJETIVOS.get(canal, OBJETIVO):
        db.borrar_valor(conn, clave)
    return db.get_valor(conn, clave) == "1"


def proximo_dia(conn, canal: str, hoy: date) -> date:
    """El próximo día del año a cosechar: desde hoy + LEJOS_DIAS, de a uno; da la vuelta al año."""
    raw = db.get_valor(conn, CURSOR.format(canal))
    try:
        dia = date.fromisoformat(raw) if raw else hoy + timedelta(days=LEJOS_DIAS)
    except ValueError:
        dia = hoy + timedelta(days=LEJOS_DIAS)
    if dia < hoy + timedelta(days=LEJOS_DIAS) or dia > hoy + timedelta(days=365 - 30):
        dia = hoy + timedelta(days=LEJOS_DIAS)
    db.set_valor(conn, CURSOR.format(canal), (dia + timedelta(days=1)).isoformat())
    return dia


def resumen(conn) -> str:
    return " · ".join(f"{NOMBRES[c]} {len(leer(conn, c))}" for c in CANALES)


# ---- cosechar ------------------------------------------------------------------------------------

def cosechar_latam(wiki, haiku, puntuador, dia: date, avisar=log.info) -> list[dict]:
    """Historias de Latinoamérica de `dia` que no dependen de la fecha, con 8 o más."""
    from . import locales

    todos, conmemoraciones, homenajeados = locales.leer_todo(wiki, dia, avisar)
    cands, _ = locales.filtrar(todos, date.today(), homenajeados)
    if not cands:
        return []
    locales.clasificar(haiku, cands, conmemoraciones)
    lista = [c for c in locales.buenos(cands)
             if c.seccion != "fundacion" and not locales.en_calendario(c) and not c.clasif.get("conmemora")]
    if not lista:
        return []
    out = []
    for c, art, lug in locales.elegir(puntuador, lista[:locales.A_PUNTUAR], cuantos=locales.A_PUNTUAR):
        if c.clasif.get("puntaje", 0) < PUNTAJE_BANCO or not str(c.clasif.get("lugar") or "").strip():
            continue
        out.append({"id": f"latam:{art}", "texto": c.texto, "anio": c.anio, "paginas": c.paginas,
                    "articulo": art, "articulo_lugar": lug, "puntaje": c.clasif.get("puntaje"),
                    "clasif": {k: c.clasif.get(k) for k in ("lugar", "region", "pais", "tipo", "puntajes")},
                    "de_dia": dia.isoformat()})
    return out


# Santi, 2026-11-25: el banco de Latinoamérica por tema, con la búsqueda web de Haiku (con Wikipedia sumaba 1 cada ~40 min)
TEMAS_BANCO_LATAM = (
    "FÚTBOL: clubes que salieron campeones después de años, partidos históricos, ídolos, arqueros, hinchadas, mundiales",
    "MÚSICA: cómo nació una canción, un género (tango, cumbia, bolero, ranchera, samba) o un disco que hizo historia",
    "ÍDOLOS DE ANTES: la época de oro del cine mexicano y argentino, cantantes, actores y deportistas, con un giro real",
    "INVENTOS LATINOS: inventos y descubrimientos de Latinoamérica (el bolígrafo, el colectivo, la huella digital…)",
    "CURIOSIDADES E HISTORIAS HUMANAS SORPRENDENTES: lugares insólitos, récords, misterios, gente común que hizo algo "
    "increíble",
)


def cosechar_latam_web(conn, web, puntuador, tema: str, hoy: date, avisar=log.info) -> list[dict]:
    """Historias de `tema` de la web que no dependen de la fecha, con artículo de Wikipedia (para las fotos) y 8 o más
    con la regla de hoy (rareza incluida)."""
    from . import locales

    ya = {x.get("texto") for x in leer(conn, "latam")} | {x.get("articulo") for x in leer(conn, "latam")}
    cands = [c for c in locales.candidatos_web(web, hoy, ya, avisar, tema=tema)
             if c.paginas and c.paginas[0] != c.clasif.get("lugar")]
    if not cands:
        return []
    out = []
    for c, art, lug in locales.elegir(puntuador, cands, cuantos=len(cands)):
        if c.clasif.get("puntaje", 0) < PUNTAJE_BANCO or art in ya:
            continue
        out.append({"id": f"latam:{art}", "texto": c.texto, "anio": c.anio, "paginas": c.paginas,
                    "articulo": art, "articulo_lugar": lug, "puntaje": c.clasif.get("puntaje"),
                    "clasif": {k: c.clasif.get(k) for k in ("lugar", "region", "pais", "tipo", "puntajes")},
                    "de_dia": "", "origen": "web"})
    return out


REGLA_LATAM = "banco_latam_regla"   # bot_estado: la versión de la regla con la que se revisó el banco de Latinoamérica
VERSION_REGLA_LATAM = "2026-11-25"   # Santi: tema primero, y estaciones/edificios/fundaciones/próceres con rareza


def revisar_latam(conn, puntuador, avisar=log.info) -> tuple[list[dict], list[str]]:
    """Vuelve a puntuar el banco de Latinoamérica con la regla de hoy (rareza: locales.puntaje_de) y saca lo que ya no
    llega a 8. Devuelve (las que quedan, las que salieron con su puntaje nuevo)."""
    from . import locales, temas

    items = leer(conn, "latam")
    cands = [locales.Candidato("banco", int(it["anio"]), it["texto"], list(it["paginas"]),
                               dict(it.get("clasif") or {}, conmemora="")) for it in items]
    if not cands:
        db.set_valor(conn, REGLA_LATAM, VERSION_REGLA_LATAM)
        return [], []
    notas = {id(c): (c, art, lug) for c, art, lug in locales.elegir(puntuador, cands, cuantos=len(cands))}
    quedan, salen = [], []
    for it, c in zip(items, cands):
        g = temas.grupo_latam(c.clasif.get("tipo"), c.texto)
        nombre = f"{c.anio} {c.clasif.get('lugar') or ''}: {c.texto[:60]}"
        if id(c) not in notas:
            salen.append(f"{nombre} (sin puntaje)")
            continue
        p = float(c.clasif.get("puntaje") or 0)
        if p < PUNTAJE_BANCO:
            r = (c.clasif.get("puntajes") or {}).get("rareza")
            salen.append(f"{nombre} ({temas.NOMBRE_LATAM.get(g, g)}, {p:g}" + (f", rareza {r}" if r is not None else "")
                         + ")")
            continue
        quedan.append(dict(it, puntaje=p, clasif=dict(it.get("clasif") or {}, puntajes=c.clasif.get("puntajes"))))
    guardar(conn, "latam", quedan)
    db.set_valor(conn, REGLA_LATAM, VERSION_REGLA_LATAM)
    avisar(f"banco latam revisado: quedan {len(quedan)}, salen {len(salen)}: " + " | ".join(salen))
    return quedan, salen


SUBTEMAS_BANCO_TEC = ("marcas", "empresas", "videojuegos")   # Santi, 2026-11-24: el banco, con marcas y videojuegos
FOTOS_BANCO_MIN = 6     # fotos libres (sin Claude) para entrar al banco; con 4 pasaban y después fallaban (23-24/11)


def cosechar_tecnologia(wiki, puntuador, dia: date, avisar=log.info, contar_fotos=None) -> list[dict]:
    """Hechos de tecnología de `dia` con 8 o más (contados como historia, sin la fecha). Desde el 2026-11-24 (Santi:
    "llenalo con historias de marcas y videojuegos, comprobando antes que tengan fotos libres suficientes, sin gastar
    en Claude para el control") solo marcas, empresas y videojuegos (se separan por palabras ANTES de puntuar: Haiku
    no ve los demás) y solo los que tienen FOTOS_BANCO_MIN fotos libres (`efemerides.fotos_libres`, sin Claude)."""
    from . import efemerides as ef
    from . import temas

    todos = wiki.eventos("es", dia) + wiki.eventos("en", dia)
    cands = [e for e in todos if not ef.motivo_evento(e, date.today())
             and temas.subtema_tec(e.texto) in SUBTEMAS_BANCO_TEC]
    if not cands:
        return []
    contar = contar_fotos or (lambda ev: ef.fotos_libres(wiki, ev, FOTOS_BANCO_MIN))
    notas: dict = {}
    out = []
    for i, art in ef.elegir(puntuador, cands, tema="tecnologia", notas=notas):
        n = notas.get(i) or {}
        if n.get("puntaje", 0) < minimo_banco("tecnologia"):
            continue
        e = cands[i]
        paginas = [art] + [x for x in e.paginas if x != art]
        try:
            libres = contar(ef.Evento(e.lang, e.anio, e.texto, paginas))
        except Exception as err:  # noqa: BLE001 — sin poder contar, no entra
            avisar(f"banco tecnología: no pude contar las fotos de {art} ({str(err)[:80]})")
            continue
        if libres < FOTOS_BANCO_MIN:
            avisar(f"banco tecnología: {art} afuera, {libres} fotos libres (mínimo {FOTOS_BANCO_MIN})")
            continue
        out.append({"id": f"tec:{art}", "lang": e.lang, "anio": e.anio, "texto": e.texto,
                    "paginas": paginas, "articulo": art, "subtema": temas.subtema_tec(e.texto),
                    "fotos_libres": libres, "puntaje": n.get("puntaje"),
                    "notas": {k: n.get(k) for k in ef.CRITERIOS_TEC}, "de_dia": dia.isoformat()})
    return out


def cosechar_asinacio(conn, wiki, revisor, hoy: date, n: int = 20, avisar=log.info) -> list[dict]:
    """Marcas y ángulos libres en la rotación, puntuados con Haiku: los de 8 o más."""
    from .animacion import marcas

    catalogo = marcas.cargar_catalogo()
    ya = {x.get("marca") for x in leer(conn, "asinacio")}
    cands = [(m, a) for m, a in marcas.candidatos(conn, catalogo, hoy, n * 2,
                                                  azar=random.Random(time.time()), excluir=ya)][:n]
    textos = []
    for m, a in cands:
        try:
            textos.append((m, a, marcas.extracto(wiki.texto("es", m.wiki_es), a)))
        except Exception as e:
            avisar(f"banco: no pude leer {m.nombre}: {str(e)[:100]}")
    out = []
    for e in marcas.elegir(revisor, textos, PUNTAJE_BANCO):
        out.append({"id": f"{e.marca.nombre}/{e.angulo}", "marca": e.marca.nombre, "angulo": e.angulo,
                    "notas": e.notas, "dato": e.dato, "puntaje": e.promedio})
    return out


def paso(conn, canal: str, hoy: date, wiki, haiku, puntuador, revisor, avisar=log.info) -> int:
    """Una cosecha (un día del año, o una tanda de marcas) del banco `canal`. Devuelve cuántas sumó."""
    if canal == "latam":
        dia = proximo_dia(conn, canal, hoy)
        nuevos = cosechar_latam(wiki, haiku, puntuador, dia, avisar)
    elif canal == "tecnologia":
        dia = proximo_dia(conn, canal, hoy)
        nuevos = cosechar_tecnologia(wiki, puntuador, dia, avisar)
    else:
        nuevos = cosechar_asinacio(conn, wiki, revisor, hoy, avisar=avisar)
    n = agregar(conn, canal, nuevos)
    avisar(f"banco {canal}: +{n} (quedan {len(leer(conn, canal))})")
    return n
