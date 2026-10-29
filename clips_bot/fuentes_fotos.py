"""Más fuentes de fotos para Pequeña Historia (pedido 2026-10-02), además del artículo y Commons.

En orden: Commons con búsquedas que se van achicando (y, si el hecho es argentino, también las fotos
`PD-AR-Photo` y las de Caras y Caretas que ya están en Commons) → Openverse (CC0, CC BY y dominio
público; incluye Flickr, museos y bibliotecas) → Smithsonian Open Access (CC0) → Europeana
(reutilización abierta) → Flickr (CC BY y dominio público, si hay FLICKR_API_KEY) → NASA (temas de
espacio) → Pexels y Unsplash (solo para frases que hablan de HOY: son fotos modernas).

Siempre con autor y licencia para los créditos, ≥ 800 px de ancho, sin los epígrafes prohibidos de
siempre (mapas, banderas, logos, imágenes duras) y con la regla de época de las fotos (lo decide
`efemerides.fotos_para_guion` con el año, y Gemini confirma `de_epoca`).

Probado el 2026-10-02 desde la compu y la Pi: la Library of Congress responde con una verificación
anti-bots de Cloudflare y Gallica (BnF) con 403: quedan afuera (no se esquiva ningún bloqueo). La
Hemeroteca Digital de la BNE no tiene una API para buscar imágenes: lo de Caras y Caretas que está
en dominio público y subido a Commons entra por Commons.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path

import requests

from .config import env, user_agent

log = logging.getLogger(__name__)

POR_FUENTE = 4
MIN_ANCHO = 800
PAUSA_S = 1.0
MAX_BYTES = 15 * 1024 * 1024
ANCHO_LOCAL = 1280      # lo que se guarda (como las miniaturas de Commons)
_ARGENTINO = re.compile(r"argentin|buenos aires|rosario|c[oó]rdoba|mendoza|la plata|boca juniors|"
                        r"river plate|per[oó]n|malvinas|rioplatense", re.I)


# ---- límites por corrida (2026-10-29: la corrida murió por timeout buscando fotos) ------------------
#
# Openverse no contestaba (timeout de 30 s, varias veces por frase) y Smithsonian daba 429 con la
# clave de prueba, en cada frase de cada hecho: la búsqueda de fotos pasó de 45 min. Ahora cada
# pedido tiene TIMEOUT_S, una fuente que falla MAX_FALLAS veces se saltea el resto de la corrida, y
# la búsqueda de un hecho tiene un tope total (efemerides.tope_fotos_min) después del cual se sigue
# con lo que haya.

TIMEOUT_S = 10
MAX_FALLAS = 2


class Corrida:
    """Las fallas por fuente de una corrida (una propuesta, con sus hechos) y el tope de tiempo de
    la búsqueda en curso."""

    def __init__(self, reloj=time.monotonic):
        self.fallas: dict[str, int] = {}
        self.hasta: float | None = None
        self._reloj = reloj

    def salteada(self, fuente: str) -> bool:
        return self.fallas.get(fuente, 0) >= MAX_FALLAS

    def fallo(self, fuente: str) -> int:
        self.fallas[fuente] = self.fallas.get(fuente, 0) + 1
        return self.fallas[fuente]

    def con_tope(self, segundos: float | None) -> None:
        self.hasta = self._reloj() + segundos if segundos else None

    def vencida(self) -> bool:
        return self.hasta is not None and self._reloj() >= self.hasta


CORRIDA = Corrida()


def nueva_corrida() -> Corrida:
    """Al empezar una propuesta: las fallas de ayer (o de otra propuesta) no cuentan."""
    global CORRIDA
    CORRIDA = Corrida()
    return CORRIDA


def es_argentino(texto: str) -> bool:
    return bool(_ARGENTINO.search(texto or ""))


def _anio(texto) -> int | None:
    m = re.search(r"(?<!\d)(1[4-9]\d\d|20\d\d)(?!\d)", str(texto or ""))
    return int(m.group(1)) if m else None


class Fuentes:
    def __init__(self, session: requests.Session | None = None, timeout: float = TIMEOUT_S, sleep=time.sleep):
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = user_agent()
        self.timeout = timeout
        self._sleep = sleep

    def _json(self, url: str, **kw) -> dict:
        self._sleep(PAUSA_S)
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r.json()

    # ---- cada fuente: dicts con archivo, url, ancho, alto, licencia, autor, epigrafe, pagina, anio

    def openverse(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        d = self._json("https://api.openverse.org/v1/images/", params={
            "q": q, "license": "cc0,by,pdm", "page_size": n * 3, "mature": "false"})
        out = []
        for r in d.get("results") or []:
            if int(r.get("width") or 0) < MIN_ANCHO or r.get("mature"):
                continue
            lic = {"cc0": "CC0", "pdm": "Dominio público", "by": "CC BY"}.get(r.get("license"), "")
            if not lic:
                continue
            if r.get("license") == "by" and r.get("license_version"):
                lic += f" {r['license_version']}"
            out.append({"archivo": f"openverse:{r['id']}", "url": r.get("url") or "", "ancho": int(r["width"]),
                        "alto": int(r.get("height") or 0), "licencia": lic,
                        "autor": r.get("creator") or ("" if lic.startswith(("CC0", "Dominio")) else ""),
                        "epigrafe": f"{r.get('title') or ''} ({r.get('source') or 'Openverse'})",
                        "pagina": r.get("foreign_landing_url") or r.get("detail_url") or "",
                        "anio": _anio(r.get("title"))})
        return out[:n]

    def smithsonian(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        # Solo con clave propia (gratis en https://api.data.gov/signup/): la DEMO_KEY compartida
        # daba 429 en todas las frases (2026-10-25 al 29).
        clave = env("SMITHSONIAN_API_KEY", requerido=False)
        if not clave:
            return []
        d = self._json("https://api.si.edu/openaccess/api/v1.0/search", params={
            "q": f"{q} AND online_media_type:Images", "rows": n * 3, "api_key": clave})
        out = []
        for row in (d.get("response") or {}).get("rows") or []:
            cont = row.get("content") or {}
            medios = ((cont.get("descriptiveNonRepeating") or {}).get("online_media") or {}).get("media") or []
            img = next((m for m in medios if m.get("type") == "Images" and m.get("usage", {}).get("access") == "CC0"), None)
            if not img:
                continue
            url = img.get("content") or ""
            fecha = (cont.get("indexedStructured") or {}).get("date") or []
            out.append({"archivo": f"si:{row.get('id')}", "url": url, "ancho": MIN_ANCHO, "alto": 0,
                        "licencia": "CC0", "autor": "Smithsonian Institution",
                        "epigrafe": str(row.get("title") or "")[:160],
                        "pagina": (cont.get("descriptiveNonRepeating") or {}).get("record_link") or "",
                        "anio": _anio(" ".join(fecha) if isinstance(fecha, list) else fecha)})
        return out[:n]

    def europeana(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        clave = env("EUROPEANA_API_KEY", requerido=False) or "api2demo"
        d = self._json("https://api.europeana.eu/record/v2/search.json", params={
            "query": q, "wskey": clave, "rows": n * 3, "media": "true", "reusability": "open",
            "qf": "TYPE:IMAGE", "profile": "rich"})
        out = []
        for it in d.get("items") or []:
            derecho = " ".join(it.get("rights") or [])
            lic = ("CC0" if "zero" in derecho else "Dominio público" if "publicdomain/mark" in derecho
                   else "CC BY" if "/licenses/by/" in derecho else "")
            url = (it.get("edmIsShownBy") or [""])[0]
            if not lic or not url:
                continue
            out.append({"archivo": f"europeana:{it.get('id')}", "url": url, "ancho": MIN_ANCHO, "alto": 0,
                        "licencia": lic, "autor": ", ".join((it.get("dcCreator") or [])[:2])
                        or ", ".join((it.get("dataProvider") or [])[:1]),
                        "epigrafe": " ".join(it.get("title") or [])[:160],
                        "pagina": it.get("guid") or "", "anio": _anio(" ".join(it.get("year") or []))})
        return out[:n]

    def flickr(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        clave = env("FLICKR_API_KEY", requerido=False)
        if not clave:
            return []
        d = self._json("https://api.flickr.com/services/rest/", params={
            "method": "flickr.photos.search", "api_key": clave, "text": q, "license": "4,9,10",
            "extras": "url_l,owner_name,date_taken,license", "per_page": n * 3, "format": "json",
            "nojsoncallback": 1, "sort": "relevance", "content_type": 1})
        lic = {"4": "CC BY 2.0", "9": "CC0", "10": "Dominio público"}
        out = []
        for p in (d.get("photos") or {}).get("photo") or []:
            if not p.get("url_l") or int(p.get("width_l") or 0) < MIN_ANCHO:
                continue
            out.append({"archivo": f"flickr:{p['id']}", "url": p["url_l"], "ancho": int(p["width_l"]),
                        "alto": int(p.get("height_l") or 0), "licencia": lic.get(str(p.get("license")), ""),
                        "autor": p.get("ownername") or "", "epigrafe": p.get("title") or "",
                        "pagina": f"https://www.flickr.com/photos/{p.get('owner')}/{p['id']}",
                        "anio": _anio(p.get("datetaken"))})
        return out[:n]

    def nasa(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        d = self._json("https://images-api.nasa.gov/search", params={"q": q, "media_type": "image"})
        out = []
        for it in (d.get("collection") or {}).get("items", [])[:n * 2]:
            dd = (it.get("data") or [{}])[0]
            enlace = next((l["href"] for l in it.get("links") or [] if l.get("rel") == "preview"), "")
            if not enlace:
                continue
            nid = dd.get("nasa_id", "")
            url = enlace.replace("~thumb", "~medium")
            out.append({"archivo": f"nasa:{nid}", "url": url, "ancho": MIN_ANCHO, "alto": 0,
                        "licencia": "NASA (dominio público)", "autor": dd.get("center") or "NASA",
                        "epigrafe": dd.get("title") or "", "pagina": f"https://images.nasa.gov/details/{nid}",
                        "anio": _anio(dd.get("date_created"))})
        return out[:n]

    def pexels(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        clave = env("PEXELS_API_KEY", requerido=False)
        if not clave:
            return []
        d = self._json("https://api.pexels.com/v1/search", params={"query": q, "per_page": n},
                       headers={"Authorization": clave})
        return [{"archivo": f"pexels:{p['id']}", "url": (p.get("src") or {}).get("large2x") or "",
                 "ancho": int(p.get("width") or 0), "alto": int(p.get("height") or 0),
                 "licencia": "Licencia de Pexels", "autor": p.get("photographer") or "Pexels",
                 "epigrafe": p.get("alt") or "", "pagina": p.get("url") or "", "anio": None}
                for p in d.get("photos") or []][:n]

    def unsplash(self, q: str, n: int = POR_FUENTE) -> list[dict]:
        clave = env("UNSPLASH_ACCESS_KEY", requerido=False)
        if not clave:
            return []
        d = self._json("https://api.unsplash.com/search/photos", params={"query": q, "per_page": n},
                       headers={"Authorization": f"Client-ID {clave}"})
        return [{"archivo": f"unsplash:{p['id']}", "url": (p.get("urls") or {}).get("regular") or "",
                 "ancho": int(p.get("width") or 0), "alto": int(p.get("height") or 0),
                 "licencia": "Licencia de Unsplash", "autor": (p.get("user") or {}).get("name") or "Unsplash",
                 "epigrafe": p.get("alt_description") or p.get("description") or "",
                 "pagina": (p.get("links") or {}).get("html") or "", "anio": None}
                for p in d.get("results") or []][:n]

    def stock(self, consultas: list[str], cuantas: int, avisar=log.info) -> list[dict]:
        """Fotos de stock (Pexels, Unsplash) para los temas modernos, ANTES que Commons: para un
        hecho de 2021 Commons trae capturas de apps y planillas (2026-10-21, la de bitcoin)."""
        from .efemerides import _NO_FOTO

        out, vistos = [], set()
        for nombre, f in (("pexels", self.pexels), ("unsplash", self.unsplash)):
            for q in consultas[:2]:
                if len(out) >= cuantas or CORRIDA.vencida():
                    return out[:cuantas]
                if CORRIDA.salteada(nombre):
                    break
                try:
                    halladas = f(q)
                except (requests.RequestException, ValueError, KeyError) as e:
                    self._fallo(nombre, q, e, avisar)
                    break
                for h in halladas:
                    if h["archivo"] in vistos or not h["url"] or _NO_FOTO.search(h["epigrafe"]):
                        continue
                    vistos.add(h["archivo"])
                    out.append({**h, "fuente": nombre})
                if halladas:
                    break
        return out[:cuantas]

    @staticmethod
    def _fallo(nombre: str, q: str, e: Exception, avisar) -> None:
        n = CORRIDA.fallo(nombre)
        avisar(f"    fotos: {nombre} «{q}» falló ({str(e)[:80]})"
               + (f" → la salteo el resto de la corrida ({n} fallas)" if n >= MAX_FALLAS else ""))

    # ---- todas, en orden -------------------------------------------------------------------

    def buscar(self, consultas: list[str], presente: bool, de_espacio: bool, cuantas: int,
               avisar=log.info) -> list[dict]:
        """Hasta `cuantas` candidatas de las fuentes que no son Commons, en orden, probando las
        consultas de la más puntual a la más general."""
        from .efemerides import _NO_FOTO

        fuentes = [("openverse", self.openverse), ("smithsonian", self.smithsonian),
                   ("europeana", self.europeana), ("flickr", self.flickr)]
        if de_espacio:
            fuentes.append(("nasa", self.nasa))
        if presente:   # fotos modernas: solo para lo que habla de hoy
            fuentes += [("pexels", self.pexels), ("unsplash", self.unsplash)]
        out, vistos = [], set()
        for nombre, f in fuentes:
            for q in consultas[:3]:
                if len(out) >= cuantas or CORRIDA.vencida():
                    return out[:cuantas]
                if CORRIDA.salteada(nombre):
                    break
                try:
                    halladas = f(q)
                except (requests.RequestException, ValueError, KeyError) as e:
                    self._fallo(nombre, q, e, avisar)
                    break
                for h in halladas:
                    if (h["archivo"] in vistos or not h["url"] or not h["licencia"]
                            or _NO_FOTO.search(h["epigrafe"])):
                        continue
                    vistos.add(h["archivo"])
                    out.append({**h, "fuente": nombre})
                if halladas:
                    break
        return out[:cuantas]


def bajar(url: str, destino: Path, cache: Path | None, session: requests.Session | None = None,
          sleep=time.sleep) -> Path:
    """Baja una foto de cualquier fuente (con tope de tamaño), la deja en JPEG de ≤ ANCHO_LOCAL px
    de ancho y la guarda en la caché (la misma foto no se baja dos veces)."""
    import io

    from PIL import Image

    destino.parent.mkdir(parents=True, exist_ok=True)
    guardada = cache / (hashlib.sha1(url.encode()).hexdigest() + ".jpg") if cache else None
    if guardada and guardada.exists() and guardada.stat().st_size > 0:
        destino.write_bytes(guardada.read_bytes())
        return destino
    s = session or requests.Session()
    sleep(PAUSA_S)
    r = s.get(url, timeout=60, stream=True, headers={"User-Agent": user_agent()})
    r.raise_for_status()
    datos = b""
    for trozo in r.iter_content(65536):
        datos += trozo
        if len(datos) > MAX_BYTES:
            raise ValueError("la foto pesa demasiado")
    with Image.open(io.BytesIO(datos)) as im:
        im = im.convert("RGB")
        if im.width < MIN_ANCHO:
            raise ValueError(f"menos de {MIN_ANCHO} px de ancho")
        if im.width > ANCHO_LOCAL:
            im = im.resize((ANCHO_LOCAL, int(im.height * ANCHO_LOCAL / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    destino.write_bytes(buf.getvalue())
    if guardada:
        guardada.parent.mkdir(parents=True, exist_ok=True)
        guardada.write_bytes(buf.getvalue())
    return destino
