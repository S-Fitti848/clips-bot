"""El estándar de calidad de Así Nació y Pequeña Historia (Santi, 2026-11-16; ESTANDAR_CALIDAD.md).

- `reglas(canal)`: las reglas del documento (se relee si cambia: una regla nueva entra sin tocar código).
- `para_prompt(canal)`: las reglas de revisión, para el pedido a Claude; `SCHEMA_REGLAS`: lo que responde.
- `fallas_de(respuesta, canal)`: las que no cumplió (solo ids conocidos).
- `texto_estandar(...)`: la línea del mensaje ("📏 Estándar 12/14 · ❌ AN-05 …").
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
MINIMO_PUBLICAR = {"asinacio": 11, "pequena_historia": 7}


def puntaje(canal: str, fallas: list[dict]) -> tuple[int, int]:
    total = len(de_revision(canal))
    return max(0, total - len({f.get("id") for f in fallas})), total


def retener(canal: str, fallas: list[dict], revisado: bool) -> bool:
    """True si el video no puede publicarse solo (la revisión respondió y quedó debajo del mínimo)."""
    if not revisado:
        return False
    ok, total = puntaje(canal, fallas)
    minimo = MINIMO_PUBLICAR.get(canal, 0)
    return bool(total) and ok < minimo


def texto_retenido(canal: str, fallas: list[dict]) -> str:
    ok, total = puntaje(canal, fallas)
    return (f"⏸ <b>NO se publica sola</b>: el estándar de calidad dio {ok}/{total} (mínimo "
            f"{MINIMO_PUBLICAR.get(canal, 0)}). ✅ Publicar igual la programa en su horario; si no respondés, no sale.")


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


def semana_anterior(hoy: date) -> tuple[str, str]:
    """(lunes anterior, este lunes) en ISO, para el resumen de los lunes."""
    lunes = hoy - timedelta(days=hoy.weekday())
    return (lunes - timedelta(days=7)).isoformat(), lunes.isoformat()


def hoy_ar() -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date().isoformat()
