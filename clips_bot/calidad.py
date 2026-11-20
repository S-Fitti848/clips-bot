"""El estándar de calidad de Así Nació y Pequeña Historia (Santi, 2026-11-16; ESTANDAR_CALIDAD.md).

- `reglas(canal)`: las reglas del documento (se relee si cambia: una regla nueva entra sin tocar código).
- `para_prompt(canal)`: las reglas de revisión, para el pedido a Claude; `SCHEMA_REGLAS`: lo que responde.
- `fallas_de(respuesta, canal)`: las que no cumplió (solo ids conocidos).
- `texto_estandar(...)`: la línea del mensaje ("📏 Estándar 17/19 · ❌ AN-05 …").
- `anotar(...)` / `resumen_semana(...)`: la tabla `calidad_fallas` y el resumen de los lunes.
- `revisar_ph(...)`: la revisión de Pequeña Historia sobre la hoja de fotos, con el cambio de foto como arreglo.
"""
from __future__ import annotations

import html
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)

DOC = ROOT / "ESTANDAR_CALIDAD.md"
CANALES = {"asinacio": "AN", "pequena_historia": "PH"}
NOMBRE_CANAL = {"asinacio": "Así Nació", "pequena_historia": "Pequeña Historia"}
_RE = re.compile(r"^- \*\*((AN|PH)-\d+)\*\* · (revisión|código)(?: · arreglo: (\w+))? — (.+)$")


@dataclass(frozen=True)
class Regla:
    id: str
    tipo: str          # "revisión" | "código"
    arreglo: str
    texto: str

    @property
    def titulo(self) -> str:
        """Lo que va antes de los dos puntos (en mayúsculas en el documento): GANCHO, NADA FLOTANDO…"""
        t = self.texto.split(":", 1)[0]
        return t.capitalize() if len(t) <= 60 else t[:60]


_cache: dict = {}


def reglas(canal: str, doc: Path | None = None) -> list[Regla]:
    doc = doc or DOC
    try:
        mt = doc.stat().st_mtime
    except OSError:
        return []
    clave = (str(doc), mt)
    if _cache.get("clave") != clave:
        todas = []
        for linea in doc.read_text(encoding="utf-8").splitlines():
            m = _RE.match(linea.strip())
            if m:
                todas.append((m.group(2), Regla(m.group(1), m.group(3), m.group(4) or "otro", m.group(5).strip())))
        _cache.update(clave=clave, todas=todas)
    pre = CANALES.get(canal, canal)
    return [r for p_, r in _cache["todas"] if p_ == pre]


def de_revision(canal: str) -> list[Regla]:
    return [r for r in reglas(canal) if r.tipo == "revisión"]


def por_id(canal: str) -> dict[str, Regla]:
    return {r.id: r for r in reglas(canal)}


SCHEMA_REGLAS = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "STRING"}, "cumple": {"type": "BOOLEAN"}, "cuadro": {"type": "INTEGER"}, "que": {"type": "STRING"}},
    "required": ["id", "cumple", "cuadro", "que"]}}


def para_prompt(canal: str, unidad: str = "cuadro") -> str:
    rs = de_revision(canal)
    if not rs:
        return ""
    lista = "\n".join(f"- {r.id}: {r.texto}" for r in rs)
    return (f"\n\nESTÁNDAR DE CALIDAD DEL CANAL (Santi, 2026-11-16). Puntuá el video contra CADA una de estas reglas: en "
            f"`reglas`, una entrada por regla con su `id`, `cumple` (true/false) y, si no cumple, el `{unidad}` donde "
            f"mejor se ve (si no hay uno, 0) y `que` (concreto: qué se ve y qué tendría que verse). Sé exigente pero "
            f"no inventes: si se cumple, true.\n{lista}")


def fallas_de(lista, canal: str) -> list[dict]:
    """Las reglas que no cumplió (las de ids que no están en el documento se ignoran)."""
    ids = {r.id for r in de_revision(canal)}
    out, vistos = [], set()
    for x in lista or []:
        if not isinstance(x, dict):
            continue
        rid = str(x.get("id") or "").strip().upper()
        if rid in ids and rid not in vistos and x.get("cumple") is False:
            vistos.add(rid)
            out.append({"id": rid, "cuadro": int(x.get("cuadro") or 0), "que": str(x.get("que") or "")[:240]})
    return out


def texto_estandar(canal: str, fallas: list[dict], corregidas: list[str] | None = None,
                   codigo: list[str] | None = None, revisado: bool = True) -> str:
    """La parte del mensaje: cuántas reglas de revisión cumplió, cuáles no (y por qué), lo que se corrigió solo y
    lo que no cumplió de las reglas que chequea el código."""
    rs = de_revision(canal)
    ids = por_id(canal)
    partes = []
    if revisado and rs:
        ok = len(rs) - len(fallas)
        partes.append(f"📏 <b>Estándar de calidad</b>: {ok}/{len(rs)}" + (" ✅" if not fallas else ""))
        for f in fallas:
            r = ids.get(f["id"])
            partes.append(f"❌ {f['id']} {html.escape(r.titulo if r else '')}: {html.escape(f.get('que') or '')}")
    elif rs:
        partes.append("📏 <b>Estándar de calidad</b>: la revisión no respondió (no se puntuó)")
    if corregidas:
        partes.append("🔧 corregido solo: " + ", ".join(corregidas))
    for c in codigo or []:
        partes.append(f"❌ {html.escape(c)}")
    return "\n".join(partes)


# ---- puntaje mínimo para publicarse solo (Santi, 2026-11-17) -------------------------------------
# Debajo de esto, después de las correcciones, el video NO se programa: le llega a Santi con ✅ Publicar igual /
# ❌ Cancelar, y si no responde no sale. El aviso solo alcanza con 1 o 2 reglas sin cumplir.
# Mínimo para publicarse sola (Santi, 2026-11-17): como mucho 2 reglas de revisión sin cumplir (era 12/14 en Así Nació
# y 7/9 en Pequeña Historia); así sumar reglas nuevas no cambia la vara.
# Así Nació 15/19 (Santi, 2026-11-20: la vara de la prueba de las 5 marcas): 4 reglas de revisión sin cumplir como mucho
MAX_FALLAS = {"asinacio": 4, "pequena_historia": 2}


def minimo(canal: str) -> int:
    return max(0, len(de_revision(canal)) - MAX_FALLAS.get(canal, 99))


def puntaje(canal: str, fallas: list[dict]) -> tuple[int, int]:
    total = len(de_revision(canal))
    return max(0, total - len({f.get("id") for f in fallas})), total


# Reglas que frenan el video aunque el resto se cumpla (Santi, 2026-11-17, el Short de Colón): una sola sin cumplir
# en la revisión del video terminado y no se publica solo.
TARJETA_EXENTA = {"PH-02", "PH-12"}
BLOQUEANTES = {"pequena_historia": {"PH-02", "PH-10", "PH-11", "PH-12", "PH-13"}}


def bloqueantes(canal: str, fallas: list[dict]) -> list[dict]:
    return [f for f in fallas if f.get("id") in BLOQUEANTES.get(canal, set())]


def retener(canal: str, fallas: list[dict], revisado: bool) -> bool:
    """True si el video no puede publicarse solo (la revisión respondió y quedó debajo del mínimo, o falló una regla
    que bloquea)."""
    if not revisado:
        return False
    if bloqueantes(canal, fallas):
        return True
    ok, total = puntaje(canal, fallas)
    return bool(total) and ok < minimo(canal)


def texto_retenido(canal: str, fallas: list[dict]) -> str:
    ok, total = puntaje(canal, fallas)
    bl = bloqueantes(canal, fallas)
    if bl:
        return (f"🚫 <b>NO se publica sola</b>: no cumple {', '.join(f['id'] for f in bl)} (reglas que frenan el "
                f"video; detalle abajo). ✅ Publicar igual la programa en su horario; si no respondés, no sale.")
    return (f"⏸ <b>NO se publica sola</b>: el estándar de calidad dio {ok}/{total} (mínimo "
            f"{minimo(canal)}). ✅ Publicar igual la programa en su horario; si no respondés, no sale.")


# ---- registro y resumen semanal -----------------------------------------------------------------

def _tabla(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS calidad_fallas (dia TEXT, canal TEXT, video TEXT, regla TEXT, que TEXT, "
                 "corregida INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE IF NOT EXISTS calidad_videos (dia TEXT, canal TEXT, video TEXT, revisado INTEGER, "
                 "PRIMARY KEY (canal, video))")


def anotar(conn, canal: str, video: str, fallas: list[dict], corregidas: list[str] | None = None,
           codigo: list[tuple[str, str]] | None = None, revisado: bool = True, dia: str | None = None) -> None:
    """Un video revisado: sus fallas finales, las que se corrigieron solas y las de código ((id, qué))."""
    if conn is None:
        return
    try:
        _tabla(conn)
        dia = dia or date.today().isoformat()
        conn.execute("DELETE FROM calidad_fallas WHERE canal = ? AND video = ?", (canal, video))
        conn.execute("INSERT OR REPLACE INTO calidad_videos VALUES (?, ?, ?, ?)", (dia, canal, video, int(revisado)))
        filas = [(dia, canal, video, f["id"], f.get("que") or "", 0) for f in fallas]
        filas += [(dia, canal, video, rid, "", 1) for rid in corregidas or []]
        filas += [(dia, canal, video, rid, que, 0) for rid, que in codigo or []]
        conn.executemany("INSERT INTO calidad_fallas VALUES (?, ?, ?, ?, ?, ?)", filas)
        conn.commit()
    except Exception as err:  # noqa: BLE001 — anotar nunca frena un video
        log.warning("calidad: no pude anotar %s/%s (%s)", canal, video, err)


def resumen_semana(conn, desde: str, hasta: str) -> str:
    """Las reglas que más fallaron entre `desde` (incluido) y `hasta` (excluido), por canal: cuántas veces quedaron
    sin cumplir en el video publicado, cuántas se corrigieron solas y un ejemplo."""
    _tabla(conn)
    partes = [f"📏 <b>Estándar de calidad, semana {desde[8:10]}/{desde[5:7]} a "
              f"{(date.fromisoformat(hasta) - timedelta(days=1)):%d/%m}</b>"]
    for canal, nombre in NOMBRE_CANAL.items():
        n = conn.execute("SELECT COUNT(*) FROM calidad_videos WHERE canal = ? AND dia >= ? AND dia < ?",
                         (canal, desde, hasta)).fetchone()[0]
        partes.append(f"\n<b>{nombre}</b>: {n} videos revisados")
        if not n:
            continue
        filas = conn.execute("SELECT regla, que, corregida FROM calidad_fallas WHERE canal = ? AND dia >= ? AND dia < ?",
                             (canal, desde, hasta)).fetchall()
        quedaron = Counter(r for r, _, c in filas if not c)
        corregidas = Counter(r for r, _, c in filas if c)
        if not quedaron and not corregidas:
            partes.append("✅ ninguna regla falló")
            continue
        ids = por_id(canal)
        for rid in sorted(set(quedaron) | set(corregidas), key=lambda x: (-quedaron[x], -corregidas[x], x))[:6]:
            ej = next((q for r, q, c in filas if r == rid and not c and q), "")
            reg = ids.get(rid)
            partes.append(f"• {rid} {html.escape(reg.titulo if reg else '')}: quedó sin cumplir en {quedaron[rid]} de {n}"
                          + (f", corregida sola {corregidas[rid]} vez/veces" if corregidas[rid] else "")
                          + (f"\n   ej.: {html.escape(ej[:160])}" if ej else ""))
    partes.append("\nLo que más falla es lo primero a mejorar en el motor.")
    return "\n".join(partes)


# ---- Pequeña Historia: la revisión sobre la hoja de fotos -----------------------------------------

SISTEMA_PH = """Revisás un video corto de "Pequeña Historia" (historia real narrada con fotos) ANTES de publicarlo. Te paso
la HOJA: cada frase del guion con la foto (o las fotos, numeradas) que se ve mientras se dice, y el año de cada foto si
se sabe. Las fotos son reales de archivo; juzgalas con las reglas del canal. No inventes problemas."""

SCHEMA_PH = {"type": "OBJECT", "properties": {"reglas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "STRING"}, "cumple": {"type": "BOOLEAN"}, "frase": {"type": "INTEGER"},
    "foto": {"type": "INTEGER"}, "que": {"type": "STRING"}},
    "required": ["id", "cumple", "frase", "foto", "que"]}}}, "required": ["reglas"]}


def _hoja_ph(p, carpeta: Path, nombre: str) -> Path:
    from . import efemerides as ef

    g = ef.Guion.de_dict(p.guion)
    plan = ef.plan_de(p)
    videos = {i: ef.Video.de_dict(v) for i, v in ((int(k), v) for k, v in g.videos.items())}
    return ef.hoja_de_guion([ef.Foto.de_dict(f) for f in p.fotos], ef.filas_de_hoja(plan, g.frases),
                            carpeta / nombre, videos=videos)


def _preguntar_ph(cliente, p, hoja: Path) -> list[dict]:
    from . import efemerides as ef

    g = ef.Guion.de_dict(p.guion)
    texto = "\n".join(f"Frase {i + 1}: {f}" for i, f in enumerate(g.frases))
    prompt = (f"Título: {g.titulo}\nAño del hecho: {ef.Evento(**p.evento).anio}\n\nEl guion:\n{texto}"
              + para_prompt("pequena_historia", "frase").replace("`frase` donde", "`frase` (desde 1) donde")
              + "\nEn las reglas de fotos, `foto` = el número de la foto que no sirve (el de la hoja; si no, 0).")
    r = json.loads(cliente.json(SISTEMA_PH, prompt, SCHEMA_PH, 0.2, imagenes=[hoja.read_bytes()]))
    out = []
    for x in fallas_de(r.get("reglas"), "pequena_historia"):
        orig = next((y for y in r.get("reglas") or [] if str(y.get("id") or "").upper() == x["id"]), {})
        out.append({**x, "frase": int(orig.get("frase") or 0), "foto": int(orig.get("foto") or 0)})
    return out


def revisar_ph(cliente, p, carpeta: Path, wiki=None, avisar=log.info):
    """(propuesta, fallas finales, corregidas, revisado). Claude mira la hoja (foto + frase) contra el estándar; las
    fotos que no pasan se cambian por la siguiente que sirve para esa frase (`ef.cambiar_foto`) y se vuelve a mirar
    una vez. Lo del guion no se reescribe acá (ya lo validó el código): se avisa."""
    from . import efemerides as ef

    if cliente is None:
        return p, [], [], False
    try:
        fallas = _preguntar_ph(cliente, p, _hoja_ph(p, carpeta, "calidad_hoja_1.jpg"))
    except Exception as err:  # noqa: BLE001 — la revisión es una red: si no responde, el video sale igual
        avisar(f"estándar de calidad: la revisión no respondió ({str(err)[:120]})")
        return p, [], [], False
    reglas_ = por_id("pequena_historia")
    a_cambiar = []
    for f in fallas:
        if reglas_.get(f["id"]) and reglas_[f["id"]].arreglo == "cambiar_foto":
            usadas = ef.numeros_usados(p)
            n = f["foto"] if f["foto"] in usadas else 0
            if not n and f["frase"]:
                plan = ef.plan_de(p)
                n = next((k + 1 for j, k, _ in plan if j == f["frase"] - 1 and k != ef.VIDEO), 0)
            if n and n not in a_cambiar:
                a_cambiar.append(n)
    if not a_cambiar:
        return p, fallas, [], True
    hechos = []
    for n in a_cambiar[:4]:
        try:
            nueva = ef.cambiar_foto(p, n, wiki or ef.Wiki(), carpeta)
        except Exception as err:  # noqa: BLE001
            avisar(f"estándar de calidad: no pude cambiar la foto {n} ({str(err)[:100]})")
            nueva = None
        if nueva is not None:
            hechos.append(n)
    if not hechos:
        return p, fallas, [], True
    avisar(f"estándar de calidad: cambié las fotos {hechos} ({', '.join(f['id'] for f in fallas)})")
    try:
        finales = _preguntar_ph(cliente, p, _hoja_ph(p, carpeta, "calidad_hoja_2.jpg"))
    except Exception as err:  # noqa: BLE001
        avisar(f"estándar de calidad: la segunda revisión no respondió ({str(err)[:120]})")
        finales = [f for f in fallas if reglas_.get(f["id"]) and reglas_[f["id"]].arreglo != "cambiar_foto"]
    corregidas = sorted({f["id"] for f in fallas} - {f["id"] for f in finales})
    return p, finales, corregidas, True


# ---- Pequeña Historia: la revisión del video TERMINADO (Santi, 2026-11-17) -------------------------------------
# En Colón la revisión miró la hoja de antes de la voz (una foto por frase, en miniatura) y el video salió con fotos
# que nadie había mirado (los cortes del formato corto) y con un año contando que mostraba 1993 y 2020. Ahora, con el
# video armado, Claude mira UN cuadro de cada corte, en grande, con su frase al lado.
REGLAS_VIDEO_PH = ("PH-02", "PH-03", "PH-04", "PH-05", "PH-06", "PH-10", "PH-11", "PH-12", "PH-13")

SISTEMA_VIDEO_PH = """Revisás un video corto de "Pequeña Historia" YA TERMINADO, antes de publicarlo. Te paso UNA imagen con
un cuadro de cada corte del video, en orden y numerados (el número amarillo k es el corte k), con la frase que la voz dice en ese momento, y los datos
reales de la historia (año y lugar). Mirá cada cuadro de verdad: quién aparece, qué se ve, si se ve nítido, y qué dicen
los textos escritos en pantalla (el año, el lugar). Sé estricto con las personas: un político, un funcionario o un acto
de gobierno, o el retrato de alguien que la historia no nombra, NO cumple. No inventes problemas: si se cumple, true."""

SCHEMA_VIDEO_PH = {"type": "OBJECT", "properties": {"reglas": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "id": {"type": "STRING"}, "cumple": {"type": "BOOLEAN"}, "corte": {"type": "INTEGER"}, "que": {"type": "STRING"}},
    "required": ["id", "cumple", "corte", "que"]}}}, "required": ["reglas"]}


def cuadros_de_cortes(video: Path, cortes: list[dict], carpeta: Path, ancho: int = 480) -> list[Path]:
    """Un cuadro del medio de cada corte del video terminado."""
    import subprocess

    from .media import find_bin

    carpeta.mkdir(parents=True, exist_ok=True)
    out = []
    for k, c in enumerate(cortes):
        t = float(c["inicio"]) + float(c["dur"]) / 2
        destino = carpeta / f"corte_{k + 1:02d}.jpg"
        subprocess.run([find_bin("ffmpeg"), "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v",
                        "1", "-vf", f"scale={ancho}:-2", "-q:v", "4", str(destino)], check=True, timeout=60)
        out.append(destino)
    return out


def mosaico(cuadros: list[Path], destino: Path, ancho: int = 216, columnas: int = 5) -> Path:
    """Capa 5 (Santi, 2026-11-18): todos los cortes en UNA imagen, numerados, para un solo pedido."""
    from PIL import Image, ImageDraw, ImageFont

    ims = [Image.open(c).convert("RGB") for c in cuadros]
    alto = max(int(im.height * ancho / im.width) for im in ims)
    filas = (len(ims) + columnas - 1) // columnas
    hoja = Image.new("RGB", (columnas * ancho, filas * alto), "black")
    dr = ImageDraw.Draw(hoja)
    try:
        fnt = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    except OSError:
        fnt = ImageFont.load_default()
    for k, im in enumerate(ims):
        x, y = (k % columnas) * ancho, (k // columnas) * alto
        hoja.paste(im.resize((ancho, int(im.height * ancho / im.width))), (x, y))
        dr.rectangle((x, y, x + 40, y + 32), fill="black")
        dr.text((x + 5, y + 2), str(k + 1), fill="yellow", font=fnt)
    destino.parent.mkdir(parents=True, exist_ok=True)
    hoja.save(destino, quality=85)
    return destino


def revisar_video_ph(cliente, meta: dict, avisar=log.info) -> tuple[list[dict], bool]:
    """(fallas, revisado) del video terminado contra las reglas de fotos y de rótulos (REGLAS_VIDEO_PH)."""
    ef_ = meta.get("efemeride") or {}
    cortes = ef_.get("cortes") or []
    if cliente is None or not cortes:
        return [], False
    video = Path(meta["salida"])
    try:
        cuadros = cuadros_de_cortes(video, cortes, video.parent / "revision_final")
    except Exception as err:  # noqa: BLE001
        avisar(f"revisión del video terminado: no pude sacar los cuadros ({str(err)[:120]})")
        return [], False
    frases = ef_.get("guion") or []
    lineas = []
    for k, c in enumerate(cortes, 1):
        i = int(c.get("frase", 0))
        frase = frases[i] if 0 <= i < len(frases) else ""
        lineas.append(f"Corte {k} ({c.get('tipo')}, {c.get('inicio')} s): frase {i + 1}: {frase}")
    local = ef_.get("local") or {}
    ids = por_id("pequena_historia")
    reglas_txt = "\n".join(f"- {r.id}: {r.texto}" for r in de_revision("pequena_historia"))
    prompt = (f"DATOS REALES: el hecho es de {ef_.get('anio')}"
              + (f", en {local.get('lugar')} ({local.get('pais')})" if local.get("lugar") else "")
              + f". {ef_.get('evento', '')[:400]}\n\nLOS CORTES:\n" + "\n".join(lineas)
              + "\n\nPuntuá el video contra CADA regla: en `reglas`, una entrada por regla con su `id`, `cumple` "
                "(true/false) y, si no cumple, el `corte` donde se ve (desde 1) y `que` (concreto: qué se ve y qué "
                f"tendría que verse).\n{reglas_txt}")
    try:
        imgs = [mosaico(cuadros, video.parent / "revision_final" / "mosaico.jpg").read_bytes()]
        r = json.loads(cliente.json(SISTEMA_VIDEO_PH, prompt, SCHEMA_VIDEO_PH, 0.1, imagenes=imgs))
    except Exception as err:  # noqa: BLE001
        avisar(f"revisión del video terminado: no respondió ({str(err)[:120]})")
        return [], False
    validos = {r.id for r in de_revision("pequena_historia")}
    out, vistos = [], set()
    for x in r.get("reglas") or []:
        rid = str(x.get("id") or "").strip().upper()
        if rid in validos and rid not in vistos and x.get("cumple") is False:
            vistos.add(rid)
            k = int(x.get("corte") or 0)
            seg = f" (corte {k}, {cortes[k - 1]['inicio']} s)" if 1 <= k <= len(cortes) else ""
            out.append({"id": rid, "cuadro": k, "que": (str(x.get("que") or "") + seg)[:260]})
    avisar(f"revisión del video terminado: {len(cortes)} cortes, fallan {[f['id'] for f in out] or 'ninguna'}")
    return out, True


# las reglas que se arreglan cambiando la foto de un corte (Santi, 2026-11-18)
REGLAS_FOTO = ("PH-02", "PH-03", "PH-04", "PH-05", "PH-06", "PH-10", "PH-11", "PH-12")
VUELTAS_REEMPLAZO = 2


def revisar_y_reemplazar(revisor, salida: Path, plan: list, g, cortes: list[dict], e, local: dict, armar,
                         tarjeta_nueva, avisar=log.info) -> dict:
    """El mosaico de todo el video (un pedido); por cada corte con una foto mal, la siguiente finalista de su frase
    que todavía no falló, o una tarjeta; se rehace SOLO ese tramo y se revisa SOLO ese corte (un pedido con esos
    cuadros). Devuelve {fallas, revisado, reemplazos, salida}. Las fallas que quedan son las que no tuvieron arreglo."""
    from . import efemerides as ef

    meta = {"salida": str(salida), "efemeride": {"cortes": cortes, "guion": list(g.frases), "anio": e.anio,
                                                 "evento": e.texto, "local": local}}
    fallas, revisado = revisar_video_ph(revisor, meta, avisar)
    out = {"fallas": fallas, "revisado": revisado, "reemplazos": [], "salida": str(salida)}
    if not revisado:
        return out
    malas: set[int] = set()
    con_tarjeta: set[int] = set()   # cortes que ya pasaron a tarjeta: no se juzgan como foto
    rk = g.rankings()
    for _vuelta in range(VUELTAS_REEMPLAZO):
        de_foto = [f for f in fallas if f["id"] in REGLAS_FOTO and 1 <= int(f.get("cuadro") or 0) <= len(plan)]
        if not de_foto:
            break
        cambiados: dict[int, str] = {}
        for f in de_foto:
            k = int(f["cuadro"]) - 1
            if k in cambiados:
                continue
            i, vieja, s_ = plan[k]
            if vieja not in (ef.VIDEO, ef.MAPA):
                malas.add(vieja)
            usadas = {x for _, x, _ in plan}
            nueva = next((x for x in (rk[i] if i < len(rk) else []) if x not in malas and x not in usadas
                          and x not in (ef.VIDEO, ef.MAPA)), None)
            como = "la siguiente finalista"
            if nueva is None:
                nueva = tarjeta_nueva(i)
                como = "una tarjeta de texto"
            if nueva is None:
                continue
            if como == "una tarjeta de texto":
                con_tarjeta.add(k)
            else:
                con_tarjeta.discard(k)
            plan[k] = (i, nueva, s_)
            cambiados[k] = f"corte {k + 1} ({f['id']}): {como}"
        if not cambiados:
            break
        salida = armar(set(cambiados))
        out["salida"] = str(salida)
        out["reemplazos"] += list(cambiados.values())
        avisar("revisión final: reemplacé " + "; ".join(cambiados.values()))
        nuevos = ef.cortes_de(plan, _Prop(cortes, plan))
        for k in cambiados:
            cortes[k] = nuevos[k] if k < len(nuevos) else cortes[k]
        sub = {"salida": str(salida), "efemeride": {**meta["efemeride"],
                                                    "cortes": [cortes[k] for k in sorted(cambiados)]}}
        nuevas, ok = revisar_video_ph(revisor, sub, avisar)
        orden = sorted(cambiados)
        nuevas = [{**x, "cuadro": orden[x["cuadro"] - 1] + 1} for x in nuevas
                  if 1 <= int(x.get("cuadro") or 0) <= len(orden) and x["id"] in REGLAS_FOTO] if ok else []
        fallas = [x for x in fallas if not (x["id"] in REGLAS_FOTO and int(x.get("cuadro") or 0) - 1 in cambiados)]
        fallas += nuevas
    # Santi, 2026-11-20 (Windows 1.0): una tarjeta con la clave de su frase es el último recurso de la regla (k); su
    # fondo difuminado a propósito no es una "foto borrosa" (PH-12) ni una foto de otra cosa (PH-02).
    fallas = [x for x in fallas if not (x["id"] in TARJETA_EXENTA and int(x.get("cuadro") or 0) - 1 in con_tarjeta)]
    out["fallas"] = fallas
    return out


class _Prop:
    """Lo mínimo que necesita `cortes_de` (los archivos de las fotos ya están en los cortes)."""

    def __init__(self, cortes, plan):
        self.fotos = []


def juntar_fallas(antes: list[dict], final: list[dict]) -> list[dict]:
    """Las fallas de la revisión de la hoja más las del video terminado (la del video manda en sus reglas)."""
    # la del video terminado es la revisión (capa 5): manda en todas las reglas
    return list(final)


def semana_anterior(hoy: date) -> tuple[str, str]:
    """(lunes anterior, este lunes) en ISO, para el resumen de los lunes."""
    lunes = hoy - timedelta(days=hoy.weekday())
    return (lunes - timedelta(days=7)).isoformat(), lunes.isoformat()


def hoy_ar() -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat()
