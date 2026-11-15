"""Así Nació más visual (Santi, 2026-11-15; regla para todos los videos, detrás de `animacion.visual_plus`).

Sobre un guion ya validado, Haiku propone por escena (barato, una llamada):
- un rótulo tipo noticiero con año y lugar ("1974 · Budapest");
- un dato con un número gigante ("4 MILLONES" / "de cubos vendidos") si la frase dice un número;
- una tarjeta de cita (texto, nombre y cargo) SOLO si la cita está literal en el artículo;
- un cartel tipo cómic para el golpe ("¡QUEBRÓ!", "¡ÉXITO!");
- el momento del día (día, atardecer, noche, interior), que cambia la luz;
- el lugar de Wikipedia del primer rótulo, para el mapa con pin que hace zoom.
El código revisa todo contra el texto (años y números que no están en la frase, citas que no están en el
artículo: afuera) y la línea de tiempo lo dibuja (acciones.py, escenas.py)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

MOMENTOS = ("dia", "atardecer", "noche", "interior")
TITO_CADA_S = 9.0          # Tito reacciona en una esquina cada 8-10 s
MAPA_S = 1.4               # la escena del mapa con el pin

SISTEMA = """Sumás elementos visuales a las escenas de un video animado corto sobre el origen de una marca.
Para CADA escena (mismo orden, con su número) decí:
- `rotulo_anio` (el año que muestra la escena si la frase o el texto lo dicen; 0 si no) y `rotulo_lugar` (la
  ciudad o el país donde pasa, corto; vacío si no se sabe): sale como rótulo de noticiero "1974 · Budapest";
  ponelo solo cuando cambia el año o el lugar, no en todas las escenas;
- `dato_numero` y `dato_texto`: si la frase dice un número importante (ventas, años, precio), el número
  como se dice ("4 MILLONES", "1.000", "100 AÑOS") y 2 a 4 palabras de qué es ("cubos vendidos"); si no, vacío;
- `cita_texto`, `cita_nombre`, `cita_cargo`: SOLO si el TEXTO trae una frase textual entre comillas de alguien
  de la historia que encaja en esa escena (copiada tal cual); si no, todo vacío;
- `cartel`: 1 o 2 palabras de cómic en mayúsculas con signos para el golpe de la escena ("¡QUEBRÓ!",
  "¡ÉXITO!", "¡BOOM!", "¡NO!"), solo en 2 o 3 escenas fuertes; si no, vacío;
- `momento`: dia, atardecer, noche o interior (cómo es la luz de esa escena);
- `lugar_wiki`: el título del artículo de Wikipedia en español de `rotulo_lugar` (para el mapa), o vacío.
Nada inventado: años, lugares, números y citas salen de la frase o del TEXTO. Respondé solo el JSON."""

SCHEMA = {"type": "OBJECT", "properties": {"escenas": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {
        "n": {"type": "INTEGER"}, "rotulo_anio": {"type": "INTEGER"}, "rotulo_lugar": {"type": "STRING"},
        "dato_numero": {"type": "STRING"}, "dato_texto": {"type": "STRING"},
        "cita_texto": {"type": "STRING"}, "cita_nombre": {"type": "STRING"}, "cita_cargo": {"type": "STRING"},
        "cartel": {"type": "STRING"}, "momento": {"type": "STRING", "enum": list(MOMENTOS)},
        "lugar_wiki": {"type": "STRING"}},
    "required": ["n", "rotulo_anio", "rotulo_lugar", "dato_numero", "dato_texto", "cita_texto", "cita_nombre",
                 "cita_cargo", "cartel", "momento", "lugar_wiki"]}}}, "required": ["escenas"]}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", str(t or ""))


def validar(v: dict, frase: str, fuente: str, guion_txt: str) -> dict:
    """Lo que no está respaldado, afuera (un rótulo sin año del texto, un número que la frase no dice, una cita
    que no está literal en el artículo)."""
    out = {"momento": v.get("momento") if v.get("momento") in MOMENTOS else "dia"}
    anio = int(v.get("rotulo_anio") or 0)
    lugar = str(v.get("rotulo_lugar") or "").strip()[:24]
    if (anio and str(anio) in guion_txt + fuente) or lugar:
        partes = ([str(anio)] if anio and str(anio) in guion_txt + fuente else []) + ([lugar] if lugar else [])
        out["rotulo"] = " · ".join(partes)
    num, txt = str(v.get("dato_numero") or "").strip()[:14], str(v.get("dato_texto") or "").strip()[:28]
    if num and (_digitos(num) and _digitos(num) in _digitos(frase) or _norm(num).split(" ")[0] in _norm(frase)):
        out["dato"] = f"{num.upper()}|{txt}"
    cita = str(v.get("cita_texto") or "").strip()
    if cita and len(cita) <= 160 and _norm(cita) and _norm(cita) in _norm(fuente):
        quien = ", ".join(x for x in (str(v.get("cita_nombre") or "").strip(), str(v.get("cita_cargo") or "").strip()) if x)
        out["cita"] = f"«{cita}»|{quien[:40]}"
    cartel = str(v.get("cartel") or "").strip().upper()
    if cartel and len(cartel.split()) <= 2 and len(cartel) <= 14:
        out["cartel"] = cartel
    if v.get("lugar_wiki"):
        out["lugar_wiki"] = str(v["lugar_wiki"])[:80]
    return out


def enriquecer(haiku, d: dict, fuente: str, wiki=None, avisar=log.info) -> dict:
    """d["visual"] = [{rotulo, dato, cita, cartel, momento, coords?}] por escena (el guion no cambia)."""
    escenas = d.get("escenas") or []
    if haiku is None or not escenas:
        return d
    lista = "\n".join(f"{i}. ({e.get('fondo')}, {e.get('parte')}, año {e.get('anio_escena') or 'hoy'}) {e.get('frase')}"
                      for i, e in enumerate(escenas, 1))
    try:
        r = json.loads(haiku.json(SISTEMA, f"ESCENAS:\n{lista}\n\nTEXTO:\n{fuente[:12000]}", SCHEMA, 0.3))
    except Exception as err:  # noqa: BLE001 — sin esto el video sale igual
        avisar(f"visuales: no respondió ({str(err)[:120]})")
        return d
    por_n = {x.get("n"): x for x in r.get("escenas") or [] if isinstance(x, dict)}
    guion_txt = " ".join(str(e.get("frase") or "") for e in escenas)
    vis = [validar(por_n.get(i, {}), str(e.get("frase") or ""), fuente, guion_txt) for i, e in enumerate(escenas, 1)]
    if wiki is not None:     # el mapa: el primer lugar con coordenadas en Wikipedia
        for v in vis:
            if v.get("lugar_wiki"):
                try:
                    c = wiki.coordenadas("es", v["lugar_wiki"])
                except Exception:  # noqa: BLE001
                    c = None
                if c:
                    v["coords"] = [round(c[0], 3), round(c[1], 3)]
                    break
    d["visual"] = vis
    avisar("visuales: " + "; ".join(f"{i + 1}: " + ", ".join(k for k in v if k not in ("lugar_wiki",))
                                    for i, v in enumerate(vis)))
    return d


# ---- el mapa (fondo cacheado) ----------------------------------------------------------------------------
def codificar(lat: float, lon: float) -> int:
    return int(round((lat + 90) * 100)) * 100000 + int(round((lon + 180) * 100))


def decodificar(semilla: int) -> tuple[float, float]:
    return (semilla // 100000) / 100 - 90, (semilla % 100000) / 100 - 180


MAPA_BASE = None   # se resuelve en mapa_base()
SPAN_LON = 64.0    # grados de longitud que entran en el ancho del cuadro


def mapa_base() -> Path | None:
    from clips_bot.config import DATA_DIR

    ruta = DATA_DIR / "animacion" / "mapa_base.png"
    if ruta.exists():
        return ruta
    try:
        from clips_bot import efemerides as ef

        ruta.parent.mkdir(parents=True, exist_ok=True)
        return ef.Wiki().mapa_base(ruta.parent)
    except Exception as err:  # noqa: BLE001
        log.warning("mapa base: %s", err)
        return None


def recorte(lat: float, lon: float, W: int = 1080, H: int = 1920, base_wh: tuple[int, int] = (2560, 1280)):
    """(x0, y0, cw, ch) del recorte en píxeles del mapa base y (px, py) del pin en el cuadro."""
    bw, bh = base_wh
    px, py = (lon + 180) / 360 * bw, (90 - lat) / 180 * bh
    cw = SPAN_LON / 360 * bw
    ch = cw * H / W
    ch = min(ch, bh)
    x0 = min(max(px - cw / 2, 0), bw - cw)
    y0 = min(max(py - ch / 2, 0), bh - ch)
    return (x0, y0, cw, ch), ((px - x0) / cw * W, (py - y0) / ch * H)


def svg_mapa(semilla: int, W: int = 1080, H: int = 1920) -> str:
    """El fondo del mapa (cacheado: se arma una sola vez por escena): el recorte del mundo con un pin."""
    import base64
    import io

    from PIL import Image

    lat, lon = decodificar(semilla)
    base = mapa_base()
    pin = recorte(lat, lon, W, H)[1]
    fondo = f'<rect width="{W}" height="{H}" fill="#1d3557"/>'
    if base is not None:
        with Image.open(base) as im:
            (x0, y0, cw, ch), pin = recorte(lat, lon, W, H, im.size)
            r = im.convert("RGB").crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W // 2, H // 2))
            buf = io.BytesIO()
            r.save(buf, "JPEG", quality=82)
        fondo = (f'<image width="{W}" height="{H}" preserveAspectRatio="none" '
                 f'href="data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"/>')
    px, py = pin
    return (fondo + f'<rect width="{W}" height="{H}" fill="#0b1d33" opacity="0.18"/>'
            f'<g transform="translate({px:.0f} {py:.0f})">'
            f'<circle r="46" fill="none" stroke="#ffffff" stroke-width="7" opacity="0.8"/>'
            f'<path d="M0 0 C-30 -40 -34 -70 0 -92 C34 -70 30 -40 0 0 Z" fill="#e63946" stroke="#1f1a24" stroke-width="7"/>'
            f'<circle cy="-62" r="13" fill="#ffffff"/></g>')
