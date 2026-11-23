"""Qué temas rinden más (Santi, 2026-11-23): en tecnología (YouTube), marcas, inventos, empresas, internet y
videojuegos; en Latinoamérica (Facebook), fútbol, ídolos de antes, curiosidades, historias humanas y próceres o
fundaciones. Los lunes se comparan las vistas por tema y los que andan mejor suben en el orden de elección (un bonus al
ORDEN, nunca al puntaje mínimo).

Sin modelo: el tema sale de palabras del título y del texto (y del `tipo` que ya da Haiku en Latinoamérica), así se
puede medir también lo que salió antes. Los datos son los de `medicion_ph` (vistas de YouTube y reproducciones de
Facebook, que se miden solas cada mañana) y el registro de los Reels (`historias_fb_registro`)."""
from __future__ import annotations

import json
import math
import re
import unicodedata

from . import db

PESOS = "temas_pesos"            # bot_estado: {"tec": {subtema: bonus}, "latam": {grupo: bonus}, "dia": ...}
SUBTEMAS_TEC = ("videojuegos", "internet", "empresas", "marcas", "inventos")
NOMBRE_TEC = {"videojuegos": "videojuegos", "internet": "internet", "empresas": "empresas", "marcas": "marcas",
              "inventos": "inventos"}
GRUPOS_LATAM = ("futbol", "idolo", "curiosidad", "humana", "procer")
NOMBRE_LATAM = {"futbol": "fútbol", "idolo": "ídolos de antes", "curiosidad": "curiosidades",
                "humana": "historias humanas", "procer": "próceres y fundaciones"}
# Lo que Santi pidió para Facebook (2026-11-23), aunque los números todavía no alcancen: base del orden.
BASE_LATAM = {"futbol": 1.0, "idolo": 0.6, "curiosidad": 0.6, "humana": 0.0, "procer": -1.0}
MAX_BONUS = 0.75
MIN_N = 2


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _hay(texto: str, palabras: tuple) -> bool:
    return any(re.search(rf"\b{re.escape(p)}", texto) for p in palabras)


_JUEGOS = ("videojuego", "juego", "consola", "nintendo", "playstation", "xbox", "sega", "atari", "game boy", "gameboy",
           "minecraft", "half-life", "pac-man", "pacman", "tetris", "mario", "zelda", "pokemon", "steam", "arcade",
           "video game", "game ")
_INTERNET = ("internet", "web", "navegador", "browser", "arpanet", "google", "buscador", "correo electronico", "e-mail",
             "email", "sitio", "red social", "redes sociales", "facebook", "youtube", "twitter", "wikipedia", "hacke",
             "hacker", "virus", "netscape", "yahoo", "omegle", "dominio", "online", "en linea", "chat")
_EMPRESAS = ("empresa", "compania", "fundo ", "fundaron", "quiebra", "quebro", "compro ", "compra de", "adquiri",
             "acciones", "fusion", "startup", "garaje", "socios", "company", "founded", "bankrupt")
_MARCAS = ("iphone", "ipod", "ipad", "walkman", "windows", "macintosh", "android", "blackberry", "nokia", "smartphone",
           "celular", "telefono", "kindle", "intel", "ibm", "microsoft", "apple", "sony", "samsung", "motorola",
           "procesador", "chip", "lanzo", "lanzamiento", "presento")


def subtema_tec(texto: str) -> str:
    """videojuegos > internet > empresas > marcas > inventos (lo que no es de los otros: el primer X, una patente)."""
    t = _norm(texto) + " "
    if _hay(t, _JUEGOS):
        return "videojuegos"
    if _hay(t, _INTERNET):
        return "internet"
    if _hay(t, _EMPRESAS):
        return "empresas"
    if _hay(t, _MARCAS):
        return "marcas"
    return "inventos"


_FUTBOL = ("futbol", "gol", "club", "campeon", "mundial", "copa ", "seleccion", "arquero", "hincha", "estadio",
           "racing", "boca", "river", "colon", "chapecoense", "libertadores", "penal", "delantero", "goleador")
_PROCER = ("insurgente", "independencia", "batalla", "sitio ", "sitio a", "fusil", "general", "revuelta", "revolucion",
           "conquistador", "virrey", "corona", "realista", "caudillo", "presidente", "mando mexico", "decreto",
           "fundad", "fundacion", "nacio de", "distrito", "cambio de nombre")
_CURIOSAS = {"lugar_curioso", "invento", "costumbre", "record", "misterio", "dato_sorprendente"}


def grupo_latam(tipo: str | None, texto: str = "") -> str:
    """El grupo de una historia de Latinoamérica: por el `tipo` de Haiku y, si no alcanza, por las palabras."""
    tipo = str(tipo or "")
    t = _norm(texto) + " "
    if tipo == "futbol" or _hay(t, _FUTBOL):
        return "futbol"
    if tipo == "idolo":
        return "idolo"
    if tipo in ("procer", "fundacion"):
        return "procer"
    if tipo in _CURIOSAS:
        return "curiosidad"
    if _hay(t, _PROCER) and tipo in ("heroe_de_pueblo", "momento_emotivo", "otro", ""):
        return "procer"
    return "humana"


def _mediana(xs: list[float]) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    m = len(xs) // 2
    return float(xs[m]) if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def _bonus(por_grupo: dict[str, list[float]]) -> dict[str, float]:
    todas = [v for xs in por_grupo.values() for v in xs]
    general = _mediana(todas)
    out = {}
    for g, xs in por_grupo.items():
        if len(xs) < MIN_N or general <= 0:
            out[g] = 0.0
            continue
        out[g] = round(max(-MAX_BONUS, min(MAX_BONUS, 0.5 * math.log2(max(_mediana(xs), 1) / general))), 2)
    return out


def vistas_tec(yt: dict) -> dict[str, list[float]]:
    """{subtema: [vistas]} de los Shorts de tecnología medidos (medicion_ph["yt"]), con más de 2 días."""
    out: dict[str, list[float]] = {}
    for x in (yt or {}).values():
        if x.get("tipo") != "tecnologia" or x.get("vistas") is None:
            continue
        out.setdefault(subtema_tec(x.get("titulo") or x.get("clip_id") or ""), []).append(float(x["vistas"]))
    return out


def vistas_latam(fb: dict, registro: list[dict]) -> tuple[dict[str, list[float]], list[tuple]]:
    """({grupo: [reproducciones]}, [(reproducciones, grupo, título)]) de los Reels de Latinoamérica."""
    reg = {r.get("video_id"): r for r in registro or [] if r.get("reel") == "historia"}
    por: dict[str, list[float]] = {}
    filas = []
    for vid, x in (fb or {}).items():
        r = reg.get(vid)
        if not r or x.get("reproducciones") is None:
            continue
        g = grupo_latam(r.get("tipo"), r.get("titulo") or "")
        por.setdefault(g, []).append(float(x["reproducciones"]))
        filas.append((x["reproducciones"], g, r.get("titulo") or ""))
    return por, sorted(filas, reverse=True)


def calcular(conn) -> dict:
    """Los pesos de hoy, desde las mediciones guardadas; los guarda y los devuelve."""
    from . import medicion_ph as mp

    datos = mp.cargar(conn)
    registro = json.loads(db.get_valor(conn, "historias_fb_registro") or "[]")
    tec = vistas_tec(datos.get("yt") or {})
    lat, _ = vistas_latam(datos.get("fb") or {}, registro)
    b_lat = _bonus(lat)
    pesos = {"tec": _bonus(tec),
             "latam": {g: round(BASE_LATAM.get(g, 0.0) + b_lat.get(g, 0.0), 2) for g in GRUPOS_LATAM},
             "n_tec": {g: len(v) for g, v in tec.items()}, "n_latam": {g: len(v) for g, v in lat.items()},
             "med_tec": {g: _mediana(v) for g, v in tec.items()}, "med_latam": {g: _mediana(v) for g, v in lat.items()}}
    db.set_valor(conn, PESOS, json.dumps(pesos, ensure_ascii=False))
    return pesos


def leer(conn) -> dict:
    try:
        return json.loads(db.get_valor(conn, PESOS) or "{}")
    except ValueError:
        return {}


def pesos_tec(conn) -> dict[str, float]:
    return dict(leer(conn).get("tec") or {})


def pesos_latam(conn) -> dict[str, float]:
    return dict(leer(conn).get("latam") or BASE_LATAM)


def _miles(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".")


def texto_semana(pesos: dict) -> str:
    """3 líneas para Santi: qué rinde en cada canal y qué va primero desde ahora."""
    def fila(med: dict, n: dict, nombres: dict) -> str:
        orden = sorted(med, key=lambda g: -med[g])
        return " · ".join(f"{nombres.get(g, g)} {_miles(med[g])} ({n.get(g, 0)})" for g in orden) or "sin datos"

    tec = fila(pesos.get("med_tec") or {}, pesos.get("n_tec") or {}, NOMBRE_TEC)
    lat = fila(pesos.get("med_latam") or {}, pesos.get("n_latam") or {}, NOMBRE_LATAM)
    primero_t = [NOMBRE_TEC[g] for g, b in sorted((pesos.get("tec") or {}).items(), key=lambda x: -x[1]) if b > 0]
    primero_l = [NOMBRE_LATAM[g] for g, b in sorted((pesos.get("latam") or {}).items(), key=lambda x: -x[1]) if b > 0]
    return (f"🔧 Claude Code: 💻 Tecnología en YouTube (mediana de vistas, videos): {tec}\n"
            f"🌎 Latinoamérica en Facebook (mediana de reproducciones): {lat}\n"
            f"Van primero: {', '.join(primero_t) or 'igual que antes'} (tecnología); "
            f"{', '.join(primero_l) or 'igual que antes'} (Facebook).")
