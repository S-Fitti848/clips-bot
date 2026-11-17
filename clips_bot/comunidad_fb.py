"""Pequeña Historia en Facebook: publicaciones de comunidad (Santi, 2026-11-16). Una por día, además de los Reels:
una foto de época (personaje, lugar o hecho de Latinoamérica) con una pregunta grande que pide opinión o recuerdos
("¿Qué personaje de la historia de tu país merece una película?", "¿Sabías esta historia? Contame de dónde sos").
Sin voz ni render: la imagen se arma con PIL y se programa para las 13:00 AR. Apagado (`historias_fb.comunidad`)
hasta que Santi apruebe los ejemplos. Los comentarios y compartidos van en el resumen de 24 h (stats_fb).

La foto sale del artículo de la historia de Latinoamérica del día (las mismas reglas de siempre: licencia libre,
de época, sin cosas duras), con su autor y licencia en el texto.
"""
from __future__ import annotations

import json
import logging
import textwrap
from datetime import datetime, timedelta
from pathlib import Path

import requests

log = logging.getLogger(__name__)

ANCHO, ALTO = 1080, 1350          # 4:5, lo que mejor ocupa el feed de Facebook
FUENTE = Path(__file__).resolve().parent.parent / "assets" / "fuentes" / "Montserrat-Black.ttf"
CANAL = "facebook_comunidad"

SISTEMA = """Escribís una publicación de COMUNIDAD para la página de Facebook "Pequeña Historia" (historias reales de
Latinoamérica). Va una foto de época con una PREGUNTA grande que invite a comentar: pedí opinión o recuerdos de la
gente, ligada a ESTA historia y a su país ("¿Qué personaje de la historia de tu país merece una película?", "¿Sabías
esta historia? Contame de dónde sos", "¿Tu abuelo te contó algo de esto?"). Castellano latinoamericano, cálido, tuteo.
- `pregunta`: 6 a 12 palabras, termina en "?". Que se pueda contestar en un comentario.
- `texto`: el posteo, 2 a 4 frases cortas: lo esencial de la historia con UN dato concreto (solo lo que dice el texto
  que te paso) y la invitación a comentar. Sin hashtags ni links.
Respondé solo el JSON."""
SCHEMA = {"type": "OBJECT", "properties": {"pregunta": {"type": "STRING"}, "texto": {"type": "STRING"}},
          "required": ["pregunta", "texto"]}


def escribir(cliente, historia: dict, se_ve: str = "") -> dict:
    """{pregunta, texto} para la historia ({titulo, texto, lugar, pais, anio}). `se_ve`: lo que muestra la foto ya
    verificada; el texto habla de ESO (Santi, 2026-11-17: primero la foto, después el texto)."""
    prompt = (f"Historia ({historia.get('anio')}, {historia.get('lugar')}, {historia.get('pais')}): "
              f"{historia.get('titulo')}\n{historia.get('texto')}"
              + (f"\n\nLA FOTO MUESTRA: {se_ve}. El texto y la pregunta hablan de lo que se ve en la foto (la persona, "
                 "el lugar o el hecho), ligado a la historia; nada que la foto contradiga." if se_ve else ""))
    errores = []
    for _ in range(3):
        d = json.loads(cliente.json(SISTEMA, prompt + ("\n\nCorregí: " + "; ".join(errores) if errores else ""),
                                    SCHEMA, 0.7))
        p = str(d.get("pregunta") or "").strip()
        errores = []
        if not p.endswith("?") or not 4 <= len(p.split()) <= 13:
            errores.append("la pregunta va de 6 a 12 palabras y termina en ?")
        if not str(d.get("texto") or "").strip():
            errores.append("falta el texto")
        if not errores:
            return {"pregunta": p, "texto": str(d["texto"]).strip()}
    raise ValueError("; ".join(errores))


def _fuente(tam: int):
    from PIL import ImageFont

    return ImageFont.truetype(str(FUENTE), tam)


def lineas_que_entran(texto: str, ancho_max: int, tam: int) -> list[str]:
    f = _fuente(tam)
    for ancho_chars in range(22, 7, -1):
        lineas = textwrap.wrap(texto, ancho_chars)
        if all(f.getlength(x) <= ancho_max for x in lineas):
            return lineas
    return textwrap.wrap(texto, 8)


def armar_imagen(foto: Path, pregunta: str, credito: str, salida: Path) -> Path:
    """La foto (recortada a 4:5) con un degradé oscuro y la pregunta grande en blanco con borde, más el crédito."""
    from PIL import Image, ImageDraw, ImageOps

    im = ImageOps.fit(Image.open(foto).convert("RGB"), (ANCHO, ALTO), centering=(0.5, 0.35))
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    dib = ImageDraw.Draw(capa)
    for y in range(ALTO // 3, ALTO):         # degradé de abajo: la pregunta se lee sobre cualquier foto
        a = int(215 * ((y - ALTO // 3) / (ALTO - ALTO // 3)) ** 1.2)
        dib.line([(0, y), (ANCHO, y)], fill=(10, 8, 20, a))
    dib.rectangle([0, 0, ANCHO, 120], fill=(10, 8, 20, 120))
    im = Image.alpha_composite(im.convert("RGBA"), capa)
    dib = ImageDraw.Draw(im)
    dib.text((48, 40), "PEQUEÑA HISTORIA", font=_fuente(40), fill=(255, 214, 0), stroke_width=2, stroke_fill="black")
    tam = 96
    while tam > 54:
        lineas = lineas_que_entran(pregunta.upper(), ANCHO - 120, tam)
        if len(lineas) <= 5:
            break
        tam -= 6
    alto_linea = int(tam * 1.12)
    y = ALTO - 120 - alto_linea * len(lineas)
    for ln in lineas:
        w = _fuente(tam).getlength(ln)
        dib.text(((ANCHO - w) / 2, y), ln, font=_fuente(tam), fill="white", stroke_width=max(4, tam // 14),
                 stroke_fill="black")
        y += alto_linea
    dib.text((48, ALTO - 62), credito[:90], font=_fuente(22), fill=(230, 230, 230), stroke_width=2, stroke_fill="black")
    salida.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(salida, "JPEG", quality=90)
    return salida


# ---- la foto la mira Claude contra el texto (Santi, 2026-11-17: la de Colón salió con los presidentes del Mercosur) ----
FOTOS_CANDIDATAS = 6
SISTEMA_FOTO = """Elegís la foto de una publicación de Facebook de "Pequeña Historia" (historias reales de Latinoamérica).
Te paso el texto de la historia y varias fotos numeradas. Por cada foto decí:
- `se_ve`: qué se ve, corto y concreto.
- `coincide`: true SOLO si la foto muestra lo que cuenta el texto: la persona de la historia, el hecho, el objeto, el
  club/la institución, o el LUGAR PUNTUAL donde pasó (el puerto al que llegaron, el estadio, la plaza, la fábrica:
  vale una vista de ese lugar, de la época o no). Una foto de otra cosa del mismo país o ciudad (un paisaje, una
  catedral, otro edificio) NO coincide. Un mapa, un plano, un logo, un escudo, una captura o una imagen con marca de agua o texto sobreimpreso NO
  coinciden nunca.
- `politico`: true si muestra políticos, presidentes, funcionarios o un acto de gobierno (una cumbre, una firma, un
  discurso oficial, una foto protocolar).
- `protagonista`: true si la persona principal de la foto ES de quien trata la historia.
`mejor`: el número de la foto que mejor muestra la historia entre las que coinciden (0 si ninguna sirve)."""
SCHEMA_FOTO = {"type": "OBJECT", "properties": {
    "fotos": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "n": {"type": "INTEGER"}, "se_ve": {"type": "STRING"}, "coincide": {"type": "BOOLEAN"},
        "politico": {"type": "BOOLEAN"}, "protagonista": {"type": "BOOLEAN"}},
        "required": ["n", "se_ve", "coincide", "politico", "protagonista"]}},
    "mejor": {"type": "INTEGER"}}, "required": ["fotos", "mejor"]}


def articulos_de(historia: dict) -> list[str]:
    """Los artículos del tema, sin repetir: el del hecho, el del lugar y las otras páginas que nombra."""
    vistos = [historia.get("articulo"), historia.get("articulo_lugar")] + list(historia.get("paginas") or [])
    return [a for a in dict.fromkeys(str(x or "").strip() for x in vistos) if a][:3]


def fotos_candidatas(wiki, historia: dict, carpeta: Path, n: int = FOTOS_CANDIDATAS) -> list[tuple[Path, str]]:
    """Hasta `n` fotos del tema, con las reglas de siempre, bajadas: las de sus artículos y, si faltan, las de su
    categoría en Commons (Santi, 2026-11-17: "elegí el tema empezando por las fotos"). [(ruta, crédito)]."""
    from . import efemerides as ef

    out: list[tuple[Path, str]] = []
    anio = int(historia.get("anio") or 0)

    def sumar(fotos) -> None:
        bajadas, _ = ef.bajar_fotos(wiki, fotos[: (n - len(out)) * 2], carpeta, f"comunidad_{len(out)}", n - len(out))
        out.extend((Path(f.ruta), f"Foto: {f.autor} · {f.licencia}") for f in bajadas)

    for articulo in articulos_de(historia):
        if len(out) >= n:
            break
        try:
            fotos, _ = ef.fotos_del_evento(wiki, ef.Evento("es", anio, str(historia.get("texto") or ""), [articulo]))
        except ef.WikiError:
            continue
        sumar(fotos)
    principal = next(iter(articulos_de(historia)), "")
    if len(out) < n and principal:
        try:
            fotos, _ = ef.filtrar_infos(wiki, "commons", wiki.buscar_commons(principal), f"Commons: {principal}",
                                        anio or None)
            sumar(fotos)
        except Exception as err:  # noqa: BLE001 — Commons es un extra
            log.info("comunidad: Commons para %s no respondió (%s)", principal, err)
    return out[:n]


TIPOS_CON_FOTOS = ("idolo", "heroe_de_pueblo", "gente_comun", "lugar_curioso", "fundacion", "costumbre", "record")


def temas(historias_dia: list[dict], banco_latam: list[dict], usados: set[str], maximo: int = 6) -> list[dict]:
    """Los temas a probar, en orden: las historias de hoy (van con el Reel del día) y después las del banco de
    Latinoamérica que suelen tener buenas fotos (ídolos, personajes, lugares). Nunca uno ya usado."""
    out = []
    for h in historias_dia:
        out.append({"id": str(h.get("articulo") or h.get("texto") or "")[:80], "texto": h.get("texto"),
                    "anio": int(str(h.get("texto") or "0")[:4]) if str(h.get("texto") or "")[:4].isdigit() else 0,
                    "pais": h.get("pais"), "articulo": h.get("articulo"), "paginas": h.get("paginas") or []})
    prioridad = {t: k for k, t in enumerate(TIPOS_CON_FOTOS)}
    for b in sorted(banco_latam, key=lambda b: (prioridad.get((b.get("clasif") or {}).get("tipo"), 99),
                                                -float(b.get("puntaje") or 0))):
        out.append({"id": str(b.get("id") or b.get("articulo") or "")[:80], "texto": b.get("texto"),
                    "anio": int(b.get("anio") or 0), "pais": (b.get("clasif") or {}).get("pais"),
                    "articulo": b.get("articulo"), "articulo_lugar": b.get("articulo_lugar"),
                    "paginas": b.get("paginas") or []})
    return [t for t in out if t["id"] and t["id"] not in usados][:maximo]


def _jpeg_chico(ruta: Path) -> bytes:
    import io

    from PIL import Image

    im = Image.open(ruta).convert("RGB")
    im.thumbnail((512, 512))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=80)
    return b.getvalue()


def foto_que_coincide(cliente, historia: dict, candidatas: list[tuple[Path, str]]) -> tuple[tuple[Path, str] | None, str]:
    """((ruta, crédito) de la foto que muestra la historia, por qué). Nunca un político ni un acto de gobierno, salvo
    que esa persona sea el protagonista de la historia. (None, motivo) si ninguna sirve."""
    if not candidatas:
        return None, "el artículo no tiene fotos que pasen las reglas"
    if cliente is None:
        return None, "sin Claude no se puede mirar la foto"
    lista = "\n".join(f"Foto {k + 1}" for k in range(len(candidatas)))
    r = json.loads(cliente.json(SISTEMA_FOTO, f"La historia: {historia.get('texto')}\n\n{lista}", SCHEMA_FOTO, 0.1,
                                imagenes=[_jpeg_chico(p) for p, _ in candidatas]))
    validas = {}
    for f in r.get("fotos") or []:
        k = int(f.get("n") or 0)
        if 1 <= k <= len(candidatas) and f.get("coincide") and (not f.get("politico") or f.get("protagonista")):
            validas[k] = str(f.get("se_ve") or "")
    if not validas:
        vistas = "; ".join(f"{int(f.get('n') or 0)}: {str(f.get('se_ve') or '')[:60]}"
                           + (" (político)" if f.get("politico") else "") for f in (r.get("fotos") or [])[:4])
        return None, f"ninguna foto muestra la historia ({vistas})"
    mejor = int(r.get("mejor") or 0)
    k = mejor if mejor in validas else min(validas)
    return candidatas[k - 1], validas[k]


def foto_de_la_historia(wiki, historia: dict, carpeta: Path) -> tuple[Path, str] | None:
    """La foto principal del artículo del hecho (o del lugar), con las reglas de siempre, bajada. (ruta, crédito)."""
    from . import efemerides as ef

    for articulo in [a for a in (historia.get("articulo"), historia.get("articulo_lugar")) if a]:
        e = ef.Evento("es", int(historia.get("anio") or 0), str(historia.get("texto") or ""), [articulo])
        try:
            fotos, _ = ef.fotos_del_evento(wiki, e)
        except ef.WikiError:
            continue
        bajadas, _ = ef.bajar_fotos(wiki, fotos[:4], carpeta, "comunidad", 1)
        if bajadas:
            f = bajadas[0]
            return Path(f.ruta), f"Foto: {f.autor} · {f.licencia}"
    return None


def programar(imagen: Path, mensaje: str, cuando: datetime, version: str, page_id: str, token: str,
              session=None) -> str:
    """La publicación de foto en la página, programada para `cuando` (o ya, si pasó). Devuelve el id del post."""
    from .facebook import GRAPH, _ok

    s = session or requests.Session()
    data = {"message": mensaje, "access_token": token}
    if cuando > datetime.now(cuando.tzinfo) + timedelta(minutes=11):     # Facebook pide al menos 10 min
        data.update(published="false", scheduled_publish_time=str(int(cuando.timestamp())))
    with imagen.open("rb") as f:
        d = _ok(s.post(f"{GRAPH.format(version=version)}/{page_id}/photos", data=data, timeout=120,
                       files={"source": (imagen.name, f, "image/jpeg")}), "comunidad")
    return str(d.get("post_id") or d.get("id") or "")


def mensaje(texto: str, pregunta: str, credito: str) -> str:
    return f"{texto}\n\n👉 {pregunta}\n\n{credito}"
