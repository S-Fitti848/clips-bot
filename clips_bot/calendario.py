"""Calendario de fechas de Latinoamérica para la historia de Facebook (pedido de Santi, 2026-11-11).

Los próximos 90 días: aniversarios de fundación de ciudades y pueblos, días nacionales, días de
héroes locales, fiestas patronales y conmemoraciones (como el Día del Ferrocarrilero en México).
Primero México, Colombia, Argentina, Perú, Chile y Venezuela.

Fuentes, siempre con su link (nada inventado):
- la sección de celebraciones de la página de cada día de Wikipedia en español ("20 de noviembre"):
  las líneas con un país de Latinoamérica;
- el anexo de efemérides de Venezuela (el único de un país latinoamericano en es.wikipedia);
- los pueblos y ciudades fundados ese día (el buscador de es.wikipedia, solo artículos que son un
  lugar de Latinoamérica: `locales.buscar_fundaciones`).

Se guarda en bot_estado (`calendario_conmemoraciones`); la escucha suma los días que faltan y cada
lunes le manda a Santi la lista de la semana. La historia de Facebook de cada día usa las mismas
fuentes en vivo y les da prioridad (`locales.buenos`)."""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import date, timedelta
from urllib.parse import quote

from . import db
from . import efemerides as ef
from . import locales

log = logging.getLogger(__name__)

CLAVE = "calendario_conmemoraciones"   # bot_estado: {"dias": {iso: {"generado": iso, "entradas": [...]}}}
DIAS = 90
REFRESCAR_DIAS = 14     # un día ya armado se vuelve a leer si tiene más de esto (Wikipedia cambia)
MAX_POR_DIA = 8         # en el mensaje de la semana, por día
FUNDACION_ANIOS_MIN = 50   # una "fundación" de 2009 es un barrio nuevo (visto el 11/11): afuera

BANDERAS = {"México": "🇲🇽", "Colombia": "🇨🇴", "Argentina": "🇦🇷", "Perú": "🇵🇪", "Chile": "🇨🇱",
            "Venezuela": "🇻🇪", "Uruguay": "🇺🇾", "Paraguay": "🇵🇾", "Bolivia": "🇧🇴", "Ecuador": "🇪🇨",
            "Cuba": "🇨🇺", "Brasil": "🇧🇷", "Guatemala": "🇬🇹", "Honduras": "🇭🇳", "Nicaragua": "🇳🇮",
            "Costa Rica": "🇨🇷", "Panamá": "🇵🇦", "El Salvador": "🇸🇻", "Puerto Rico": "🇵🇷",
            "República Dominicana": "🇩🇴"}
DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")

# Para el país de una fundación (sale de la intro del artículo): nombre o gentilicio.
_PAISES_RE = [(p, re.compile(rx, re.I)) for p, rx in (
    ("México", r"m[eé]xic"), ("Colombia", r"colombi"), ("Argentina", r"argentin"),
    ("Perú", r"\bper[uú]\b|peruan"), ("Chile", r"\bchile"), ("Venezuela", r"venezol|venezuel"),
    ("Uruguay", r"urugua"), ("Paraguay", r"paragua"), ("Bolivia", r"bolivi"), ("Ecuador", r"ecuator"),
    ("Cuba", r"\bcuba"), ("Brasil", r"brasil"), ("Guatemala", r"guatemal"), ("Honduras", r"hondure|honduras"),
    ("Nicaragua", r"nicarag"), ("Costa Rica", r"costa ?rica|costarric"), ("Panamá", r"panam"),
    ("El Salvador", r"salvador"), ("Puerto Rico", r"puerto ?ric|puertorriq"),
    ("República Dominicana", r"dominican"))]


def url_wiki(titulo: str) -> str:
    return "https://es.wikipedia.org/wiki/" + quote(titulo.replace(" ", "_"))


def pais_de(texto: str) -> str | None:
    """El primer país de Latinoamérica que nombra el texto (por posición, no por la lista)."""
    hallados = [(m.start(), p) for p, rx in _PAISES_RE for m in [rx.search(texto)] if m]
    return min(hallados)[1] if hallados else None


def entradas_del_dia(wiki: ef.Wiki, dia: date, avisar=log.info) -> list[dict]:
    """Las fechas de Latinoamérica de ese día: {tipo, pais, texto, articulos, anio, fuente}, de mayor a
    menor prioridad (país con más público primero). Si una fuente falla, se avisa y sigue sin ella."""
    out: list[dict] = []
    vistos: set[str] = set()

    def sumar(e: dict) -> None:
        clave = ef._norm(e["texto"])[:80]
        if clave not in vistos:
            vistos.add(clave)
            out.append(e)

    fuente_dia = url_wiki(locales.titulo_dia(dia))
    secs = locales._secciones(locales._wikitexto_dia(wiki, dia))
    for c in locales.celebraciones(secs):
        if not c["pais"]:
            continue
        sumar({"tipo": "conmemoracion", "pais": c["pais"], "texto": c["texto"][:220],
               "articulos": c["enlaces"][:5], "anio": locales.anio_celebracion(c["texto"], dia),
               "fuente": fuente_dia})
    try:
        conm, _ = locales.leer_anexos(wiki, dia)
        for linea in conm:
            origen, _, texto = linea.partition(": ")
            sumar({"tipo": "conmemoracion", "pais": "Venezuela", "texto": texto[:220], "articulos": [],
                   "anio": None, "fuente": url_wiki(f"Anexo:Efemérides en {origen}")})
    except Exception as err:  # noqa: BLE001 — una fuente caída no frena el calendario
        avisar(f"calendario {dia:%d/%m}: anexos no salió ({err})")
    try:
        for c in locales.buscar_fundaciones(wiki, dia):
            if c.anio > dia.year - FUNDACION_ANIOS_MIN:
                continue
            titulo = c.paginas[0]
            sumar({"tipo": "fundacion", "pais": pais_de(c.texto), "texto": f"Aniversario de la fundación de {titulo}",
                   "articulos": [titulo], "anio": c.anio, "fuente": url_wiki(titulo)})
    except Exception as err:  # noqa: BLE001
        avisar(f"calendario {dia:%d/%m}: fundaciones no salió ({err})")
    return sorted(out, key=lambda e: (locales.prioridad_pais(e["pais"]), e["tipo"] != "fundacion"))


def cargar(conn) -> dict:
    try:
        d = json.loads(db.get_valor(conn, CLAVE) or "{}")
    except ValueError:
        d = {}
    d.setdefault("dias", {})
    return d


def actualizar(conn, wiki: ef.Wiki, hoy: date, dias: int = DIAS, max_nuevos: int | None = None,
               avisar=log.info) -> int:
    """Arma los días de [hoy, hoy + dias) que faltan (o que tienen más de REFRESCAR_DIAS), de a uno
    y guardando cada uno (si se corta, lo hecho queda). Borra los que ya pasaron hace más de una
    semana. Devuelve cuántos armó; `max_nuevos` es el tope por llamada (la escucha no se traba)."""
    cal = cargar(conn)
    limite = (hoy - timedelta(days=7)).isoformat()
    cal["dias"] = {k: v for k, v in cal["dias"].items() if k >= limite}
    hechos = 0
    for k in range(dias):
        dia = hoy + timedelta(days=k)
        iso = dia.isoformat()
        ya = cal["dias"].get(iso)
        if ya and ya.get("generado", "") >= (hoy - timedelta(days=REFRESCAR_DIAS)).isoformat():
            continue
        if max_nuevos is not None and hechos >= max_nuevos:
            break
        try:
            entradas = entradas_del_dia(wiki, dia, avisar)
        except ef.WikiError as err:
            avisar(f"calendario {dia:%d/%m}: no salió ({err}); sigo la próxima vez")
            break
        cal["dias"][iso] = {"generado": hoy.isoformat(), "entradas": entradas}
        db.set_valor(conn, CLAVE, json.dumps(cal, ensure_ascii=False))
        hechos += 1
    if not hechos:
        db.set_valor(conn, CLAVE, json.dumps(cal, ensure_ascii=False))
    return hechos


def del_dia(conn, dia: date) -> list[dict]:
    return (cargar(conn)["dias"].get(dia.isoformat()) or {}).get("entradas") or []


def falta(conn, desde: date, dias: int) -> bool:
    cal = cargar(conn)["dias"]
    return any((desde + timedelta(days=k)).isoformat() not in cal for k in range(dias))


def linea(e: dict) -> str:
    bandera = BANDERAS.get(e.get("pais") or "", "🌎")
    pais = html.escape(e.get("pais") or "Latinoamérica")
    texto = html.escape(e["texto"][:160])
    anio = f" ({e['anio']})" if e.get("tipo") == "fundacion" and e.get("anio") else ""
    return f"• {bandera} {pais}: {texto}{anio}"


def texto_semana(conn, lunes: date) -> str:
    """La lista de la semana (lunes a domingo) para Telegram, con el link a la fuente de cada día."""
    partes = [f"📅 <b>Calendario de la semana</b> ({lunes:%d/%m} → {lunes + timedelta(days=6):%d/%m})\n"
              "Fechas de Latinoamérica para la historia de Facebook: ese día van primero, y sale el "
              "día exacto. Prioridad: México, Colombia, Argentina, Perú, Chile y Venezuela."]
    for k in range(7):
        dia = lunes + timedelta(days=k)
        entradas = del_dia(conn, dia)
        cab = f"\n<b>{DIAS_SEMANA[dia.weekday()]} {dia:%d/%m}</b>"
        if not entradas:
            hay = dia.isoformat() in cargar(conn)["dias"]
            partes.append(cab + ("\n• (ninguna fecha de Latinoamérica en las fuentes)" if hay
                                 else "\n• (todavía sin armar)"))
            continue
        lineas = [linea(e) for e in entradas[:MAX_POR_DIA]]
        if len(entradas) > MAX_POR_DIA:
            lineas.append(f"• … y {len(entradas) - MAX_POR_DIA} más")
        fuente = f'<a href="{url_wiki(locales.titulo_dia(dia))}">fuente</a>'
        partes.append(f"{cab} · {fuente}\n" + "\n".join(lineas))
    return "\n".join(partes)
