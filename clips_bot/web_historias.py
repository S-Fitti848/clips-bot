"""Historias de la web para Latinoamérica (Santi, 2026-11-16, opción C: "las efemérides de Wikipedia no
alcanzan"; ese día las candidatas sacaron 1,8, 2,5 y 3,5).

Dos pasos, los dos con Haiku y la búsqueda web de la API de Anthropic (`web_search` / `web_fetch`; Haiku
no tiene las versiones con filtro dinámico, van las básicas):

1. `buscar`: historias curiosas y reales de diarios, sitios de historia, museos y archivos de cada país,
   en lo posible de esta fecha, con los links donde aparecen. Entran como candidatas junto a las de
   Wikipedia y se puntúan igual (8 o más).
2. `verificar`: antes de escribir el guion de CUALQUIER historia de Latinoamérica (de la web o de
   Wikipedia), cada dato (nombres, año, lugar, cifras) tiene que estar en al menos DOS fuentes
   independientes (sitios distintos; Wikipedia cuenta como una sola). El guion se escribe solo con el
   texto de los datos verificados; los links quedan en la bitácora y en la propuesta.

Costo: cada búsqueda vale US$ 0,01 (se anota en gemini_uso como el "modelo" `web_search`, una unidad por
búsqueda, para que entre en /costos y en el informe diario); los tokens de Haiku, como siempre. La prueba
de un día real la mide `__main__._web_latam_tick` y, si se pasa de lo estimado, la apaga sola.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .gemini import _llamador

log = logging.getLogger(__name__)

HAIKU = "claude-haiku-5-5"
HERRAMIENTA_BUSCAR = "web_search_20250305"
HERRAMIENTA_LEER = "web_fetch_20250910"
MODELO_BUSQUEDA = "web_search"          # la fila de costo de las búsquedas en gemini_uso (1 unidad = 1 búsqueda)
BUSQUEDAS_DESCUBRIR = 10      # 2026-11-18: 8 → 10 (más historias que lleguen a 8)
BUSQUEDAS_VERIFICAR = 4
LECTURAS_VERIFICAR = 3
MIN_FUENTES = 2
MIN_DATOS = 3                            # una historia verificada tiene al menos 3 datos con 2 fuentes
MAX_VUELTAS = 4                          # pause_turn: cuántas veces se deja seguir al servidor
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")


class WebError(Exception):
    """La búsqueda web no anduvo (la API, la red o una respuesta sin JSON). Quien llama sigue sin ella."""


@dataclass
class Verificacion:
    ok: bool
    datos: list[dict] = field(default_factory=list)      # [{"dato", "fuentes": [url, ...]}] con 2+ sitios
    texto: str = ""                                       # lo que se le pasa al guion: solo lo verificado
    motivo: str = ""
    links: list[str] = field(default_factory=list)


def dominio(url: str) -> str:
    """El sitio de un link, sin www. ni subdominios de idioma de Wikipedia (es.wikipedia.org = wikipedia.org)."""
    h = (urlparse(str(url or "")).hostname or "").lower()
    h = re.sub(r"^www\d?\.", "", h)
    partes = h.split(".")
    if "wikipedia" in partes or "wikimedia" in partes:
        return "wikipedia.org"
    return h


def sacar_json(texto: str) -> dict:
    """El último objeto JSON del texto (en un bloque ```json o suelto)."""
    bloques = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", texto, flags=re.S)
    candidatos = bloques[::-1] or []
    if not candidatos:
        i, j = texto.find("{"), texto.rfind("}")
        if i >= 0 and j > i:
            candidatos = [texto[i:j + 1]]
    for c in candidatos:
        try:
            d = json.loads(c)
            if isinstance(d, dict):
                return d
        except ValueError:
            continue
    raise WebError("la respuesta no trajo el JSON pedido")


class ClienteWeb:
    """Haiku con las herramientas de búsqueda del servidor. `uso(funcion, modelo, clave, entrada, salida, cache)`
    como el de claude.ClaudeClient (gemini.registrar_uso)."""

    def __init__(self, api_key: str = "", modelo: str = HAIKU, cliente=None, uso=None, timeout: float = 300):
        if cliente is None:
            import anthropic

            cliente = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self._c, self.modelo, self.uso = cliente, modelo, uso

    def pedir(self, sistema: str, prompt: str, busquedas: int, lecturas: int = 0,
              max_tokens: int = 16000) -> tuple[str, list[str]]:
        """(texto final, links que aparecieron en los resultados). Anota tokens y búsquedas."""
        import anthropic

        from .claude import ClaudeError, prueba_sin_claude

        try:
            prueba_sin_claude()
        except ClaudeError as e:
            raise WebError(str(e)) from e
        funcion = _llamador()
        herramientas = [{"type": HERRAMIENTA_BUSCAR, "name": "web_search", "max_uses": busquedas}]
        if lecturas:
            herramientas.append({"type": HERRAMIENTA_LEER, "name": "web_fetch", "max_uses": lecturas})
        mensajes: list = [{"role": "user", "content": prompt}]
        entrada = salida = n_busq = 0
        links: list[str] = []
        try:
            for _ in range(MAX_VUELTAS):
                r = self._c.messages.create(model=self.modelo, max_tokens=max_tokens, system=sistema,
                                            tools=herramientas, messages=mensajes)
                entrada += r.usage.input_tokens
                salida += r.usage.output_tokens
                stu = getattr(r.usage, "server_tool_use", None)
                n_busq += int(getattr(stu, "web_search_requests", 0) or 0) if stu else 0
                links += _links_de(r.content)
                if r.stop_reason != "pause_turn":
                    break
                mensajes.append({"role": "assistant", "content": r.content})
        except anthropic.APIError as e:
            raise WebError(f"búsqueda web ({self.modelo}): {e}") from e
        finally:
            if self.uso and (entrada or salida or n_busq):
                self.uso(funcion, self.modelo, "claude", entrada, salida, False)
                if n_busq:
                    self.uso(funcion, MODELO_BUSQUEDA, "claude", n_busq, 0, False)
        log.info("búsqueda web para %s: %d búsquedas, %d + %d tokens", funcion, n_busq, entrada, salida)
        if r.stop_reason in ("refusal", "max_tokens"):
            raise WebError(f"búsqueda web: la respuesta terminó con {r.stop_reason}")
        texto = "\n".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return texto, list(dict.fromkeys(links))


def json_de(cliente: "ClienteWeb", texto: str, sistema: str) -> dict:
    """El JSON de la respuesta; si no lo trajo (Santi, 2026-11-18: 2 de 5 verificaciones se cayeron así), se le pide
    al mismo modelo, SIN herramientas, que pase su respuesta al formato pedido (no busca de nuevo)."""
    try:
        return sacar_json(texto)
    except WebError:
        pass
    try:
        r = cliente._c.messages.create(
            model=cliente.modelo, max_tokens=8000,
            system="Pasás una respuesta al formato JSON que se pidió. No agregues datos que no estén en la respuesta.",
            messages=[{"role": "user", "content": "EL FORMATO PEDIDO:\n" + sistema[-1500:] + "\n\nLA RESPUESTA:\n"
                       + texto[-12000:] + "\n\nDevolvé SOLO el bloque ```json."}])
        if cliente.uso:
            cliente.uso(_llamador(), cliente.modelo, "claude", r.usage.input_tokens, r.usage.output_tokens, False)
        return sacar_json("\n".join(b.text for b in r.content if getattr(b, "type", "") == "text"))
    except WebError:
        raise
    except Exception as e:  # noqa: BLE001
        raise WebError(f"la respuesta no trajo el JSON pedido ({str(e)[:100]})") from e


def _links_de(contenido) -> list[str]:
    out = []
    for b in contenido or []:
        t = getattr(b, "type", "")
        if t == "web_search_tool_result":
            for x in getattr(b, "content", None) or []:
                if getattr(x, "url", None):
                    out.append(x.url)
        elif t == "web_fetch_tool_result":
            c = getattr(b, "content", None)
            if getattr(c, "url", None):
                out.append(c.url)
        elif t == "text":
            for cit in getattr(b, "citations", None) or []:
                if getattr(cit, "url", None):
                    out.append(cit.url)
    return out


# ---- 1. descubrir ------------------------------------------------------------------------------------

SISTEMA_BUSCAR = """Buscás en la web historias CURIOSAS Y REALES de Latinoamérica para "Pequeña Historia", un
canal de videos cortos (40 s). El modelo es el maquinista Jesús García, que en 1907 alejó de Nacozari un tren
con dinamita encendida y salvó al pueblo: gente concreta que hace algo notable en un lugar con nombre, o un
lugar insólito, un invento de la región, una costumbre, un récord, un misterio o un dato que haga decir
"no puede ser". También ídolos latinoamericanos de antes (época de oro del cine mexicano y argentino, cantantes,
actores, deportistas), contados como una historia real de su vida con un giro y emoción.
LO QUE MÁS RINDE (Santi, 2026-11-23, medido en Facebook): el FÚTBOL (clubes que salen campeones después de años,
partidos históricos, ídolos, arqueros, hinchadas, mundiales), los ídolos de antes y las curiosidades. Buscá
primero eso. Próceres, conquistadores, batallas, revueltas y fundaciones de ciudades rinden lo peor: solo si no hay otra.

Dónde buscar: diarios de cada país (sus secciones de historia y de "un día como hoy" / efemérides), sitios
de historia, museos, archivos nacionales, bibliotecas, sitios de gobiernos locales y blogs especializados.
Wikipedia sirve como UNA fuente más, no como la única. Buscá en varios países: primero México, Colombia,
Argentina, Perú, Chile y Venezuela, y también el resto de Latinoamérica.

Preferí hechos que pasaron un día como el que te paso (su aniversario); si no hay buenos, historias que no
dependen de la fecha. Nada de: tragedias solas (muertes, desastres o crímenes sin un acto heroico o algo
luminoso), política partidaria, guerras desde 1945, ni lo que pasa dentro de una ficción (la cultura pop,
solo desde la vida real). Solo hechos reales con año.

Al final respondé SOLO con un bloque ```json con esta forma:
{"historias": [{"texto": "qué pasó, 2-3 oraciones con nombres, año y lugar", "anio": 1907,
  "fecha": "07/11" (día/mes del hecho, o "" si no se sabe), "lugar": "pueblo o ciudad", "region": "",
  "pais": "México", "tipo": "heroe_de_pueblo|gente_comun|anecdota|momento_emotivo|lugar_curioso|invento|
  costumbre|record|misterio|dato_sorprendente|idolo|futbol|procer|otro", "articulo_wikipedia": "título exacto del artículo de
  es.wikipedia del hecho o del protagonista, o vacío", "articulo_lugar": "título exacto del artículo de
  es.wikipedia del lugar, o vacío", "interes": 1-10, "fuentes": ["url", "url"]}]}
Entre 8 y 12 historias, de países distintos si se puede, cada una con los links donde la leíste.
Cada historia se puntúa después del 1 al 10 en PERSONA (alguien concreto con nombre), PELIGRO o SORPRESA, GIRO y
EMOCIÓN, y solo salen las de 8 o más (Nacozari = 10): traé solo las que llegarían a eso. Nada de fundaciones de pueblos
contadas como un trámite, cambios de nombre ni efemérides administrativas: lo que buscamos es lo que se cuenta en una
sobremesa."""


def buscar(cliente: ClienteWeb, dia, evitar: list[str] | None = None,
           busquedas: int = BUSQUEDAS_DESCUBRIR, tema: str = "") -> list[dict]:
    """Las historias que encontró (dicts del JSON), con al menos un link y año. Con `tema` (el banco, Santi
    2026-11-25): historias de ese tema que no dependen de la fecha."""
    fecha = f"{dia.day} de {MESES[dia.month - 1]}"
    prompt = (f"La fecha de hoy es el {fecha}. Buscá historias de Latinoamérica que pasaron un {fecha} "
              "(cualquier año) y, si faltan, historias curiosas que no dependen de la fecha.")
    if tema:
        prompt = (f"Buscá historias de Latinoamérica sobre {tema} que NO dependen de la fecha (se pueden contar "
                  "cualquier día). Cada una con el título exacto de su artículo de es.wikipedia (sin eso no sirve).")
    if evitar:
        prompt += "\nNo repitas estas, que ya salieron: " + " | ".join(x[:120] for x in evitar)
    texto, links = cliente.pedir(SISTEMA_BUSCAR, prompt, busquedas=busquedas)
    out = []
    for h in json_de(cliente, texto, SISTEMA_BUSCAR).get("historias") or []:
        try:
            anio = int(h.get("anio"))
        except (TypeError, ValueError):
            continue
        fuentes = [u for u in h.get("fuentes") or [] if str(u).startswith("http")]
        if not str(h.get("texto") or "").strip() or not fuentes or not str(h.get("lugar") or h.get("pais") or "").strip():
            continue
        h["anio"], h["fuentes"] = anio, fuentes
        out.append(h)
    log.info("búsqueda web: %d historias (%d links en los resultados)", len(out), len(links))
    return out


def es_del_dia(h: dict, dia) -> bool:
    return str(h.get("fecha") or "").strip() == f"{dia.day:02d}/{dia.month:02d}" or \
        str(h.get("fecha") or "").strip() == f"{dia.day}/{dia.month}"


# ---- 2. verificar ------------------------------------------------------------------------------------

SISTEMA_VERIFICAR = """Verificás una historia antes de que se cuente en un video. Buscá y leé fuentes en la web
(diarios, sitios de historia, museos, archivos, sitios oficiales; Wikipedia vale como UNA sola fuente) y
confirmá CADA dato que haría falta para contarla: los nombres de las personas y de los lugares, el año, la
fecha si se dice, las cifras y lo que pasó. Un dato está verificado si lo dicen al menos DOS fuentes de
SITIOS DISTINTOS que no se copien entre sí. Si una fuente contradice a otra, ese dato no está verificado.

Al final respondé SOLO con un bloque ```json:
{"datos": [{"dato": "una oración con el dato", "fuentes": ["url de un sitio", "url de otro sitio"]}],
 "resumen": "la historia contada en 250-400 palabras en castellano con SOLO los datos verificados, con todos
  los nombres, años, lugares y cifras escritos igual que en los datos",
 "es_real": true, "problema": "vacío, o por qué no se pudo verificar o qué está mal"}"""


def es_tecnica(err: Exception) -> bool:
    """La respuesta cortada o sin el JSON pedido (no dice nada de si la historia es real)."""
    t = str(err)
    return "max_tokens" in t or "JSON" in t or "SIN ACCESO" in t


# Santi, 2026-11-28: la verificación contestó "no tengo acceso web en esta conversación" y la historia quedó como "no
# verificada". Eso es una falla técnica (el modelo no usó la búsqueda), no un veredicto sobre la historia.
_SIN_ACCESO = re.compile(r"(no tengo|sin) acceso (a la )?web|no (pude|puedo) (abrir|acceder|leer|navegar)"
                         r"|no (tengo|cuento con) (herramientas|la herramienta) de b[uú]squeda|cannot (browse|access)",
                         re.I)


def sin_acceso(d: dict) -> bool:
    return bool(_SIN_ACCESO.search(f"{d.get('problema') or ''} {d.get('resumen') or ''}"))


def verificar(cliente: ClienteWeb, texto: str, anio: int, lugar: str, pais: str,
              pistas: list[str] | None = None) -> Verificacion:
    """Cada dato con 2+ fuentes de sitios distintos (lo revisa el código, no solo el modelo)."""
    prompt = (f"Historia ({anio}, {lugar}, {pais}): {texto}\n"
              + ("Links donde apareció: " + " ".join(pistas[:6]) if pistas else ""))
    # Santi, 2026-11-25: 4 de 15 verificaciones de la semana se cayeron por la respuesta cortada (max_tokens) o sin
    # JSON: eso es una falla técnica, no de la historia. Se reintenta una vez, con el doble de lugar para responder.
    for intento in range(2):
        try:
            salida, links = cliente.pedir(SISTEMA_VERIFICAR, prompt, busquedas=BUSQUEDAS_VERIFICAR,
                                          lecturas=LECTURAS_VERIFICAR, max_tokens=16000 * (intento + 1))
            d = json_de(cliente, salida, SISTEMA_VERIFICAR)
            if sin_acceso(d):
                raise WebError(f"SIN ACCESO: la verificación dijo que no pudo buscar ({str(d.get('problema'))[:120]})")
            break
        except WebError as err:
            if intento or not es_tecnica(err):
                raise
            log.info("verificación: %s; la reintento una vez", err)
    buenos, malos = [], 0
    for x in d.get("datos") or []:
        fuentes = [u for u in x.get("fuentes") or [] if str(u).startswith("http")]
        if str(x.get("dato") or "").strip() and len({dominio(u) for u in fuentes}) >= MIN_FUENTES:
            buenos.append({"dato": str(x["dato"]).strip(), "fuentes": fuentes})
        else:
            malos += 1
    todos_links = list(dict.fromkeys([u for x in buenos for u in x["fuentes"]] + links))
    if d.get("es_real") is False:
        return Verificacion(False, buenos, motivo=str(d.get("problema") or "no es real")[:300], links=todos_links)
    if len(buenos) < MIN_DATOS:
        return Verificacion(False, buenos, links=todos_links,
                            motivo=(f"solo {len(buenos)} datos con {MIN_FUENTES} fuentes de sitios distintos"
                                    f" ({malos} sin confirmar)" + (f": {d.get('problema')}" if d.get("problema") else ""))[:300])
    resumen = str(d.get("resumen") or "").strip()
    texto_final = resumen + "\n\nDatos verificados (cada uno en 2 o más fuentes):\n" + \
        "\n".join(f"- {x['dato']}" for x in buenos)
    return Verificacion(True, buenos, texto_final, links=todos_links)


def cliente_web() -> ClienteWeb | None:
    """Con ANTHROPIC_API_KEY del .env; None si no está."""
    from .config import env
    from .gemini import registrar_uso

    clave = env("ANTHROPIC_API_KEY", requerido=False)
    if not clave:
        return None
    return ClienteWeb(clave, uso=registrar_uso)
