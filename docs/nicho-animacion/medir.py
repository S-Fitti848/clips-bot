"""Investigación de nichos para un canal de Shorts animado en español.

Uso: python medir.py buscar   -> hace las búsquedas que falten (cachea todo en raw/)
     python medir.py analizar -> arma resultados.json sin gastar cuota

La clave se lee del .env del bot y nunca se imprime ni se guarda.
"""
import json
import hashlib
import math
import re
import statistics
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

AQUI = Path(__file__).resolve().parent
RAW = AQUI / "raw"
RAW.mkdir(exist_ok=True)
ENV = AQUI.parent.parent / ".env"
API = "https://www.googleapis.com/youtube/v3"
DESDE = "2026-05-14T00:00:00Z"  # hace 6 meses (hoy 2026-11-14)
MAX_S = 180  # duración máxima para contar como Short

# nicho: (busqueda_es, busqueda_en, palabras del tema es, palabras del tema en)
NICHOS = {
    "origen_palabras": ("origen de las palabras", "etymology",
                        ["palabra", "origen", "etimolog", "significa", "viene de"],
                        ["word", "etymolog", "origin", "means", "comes from"]),
    "origen_frases": ("origen de la frase", "origin of the phrase",
                      ["frase", "expresi", "dicho", "origen", "por qué decimos"],
                      ["phrase", "saying", "expression", "origin", "why we say"]),
    "inventos_accidente": ("inventos por accidente", "invented by accident",
                           ["invent", "accident", "por error", "casualidad", "descubr"],
                           ["invent", "accident", "mistake", "discover"]),
    "errores_fortunas": ("error que costó millones", "mistake that cost millions",
                         ["error", "millones", "perdi", "costó", "fortuna"],
                         ["mistake", "million", "billion", "cost", "lost", "error"]),
    "leyes_absurdas": ("leyes absurdas", "weird laws",
                       ["ley", "ilegal", "prohib", "legal"],
                       ["law", "illegal", "banned", "legal"]),
    "juicios_absurdos": ("demandas absurdas", "ridiculous lawsuit",
                         ["demand", "juicio", "tribunal", "juez", "abogad"],
                         ["lawsuit", "sued", "court", "judge", "lawyer", "sue"]),
    "fronteras_raras": ("fronteras más raras del mundo", "weird borders",
                        ["frontera", "país", "enclave", "límite", "territorio", "mapa"],
                        ["border", "country", "enclave", "territory", "map"]),
    "paises_diminutos": ("micronaciones", "micronation",
                         ["micronaci", "país", "pequeño", "independ", "nación"],
                         ["micronation", "country", "smallest", "nation", "independ"]),
    "historia_comidas": ("historia de la comida", "food history",
                         ["comida", "origen", "historia", "plato", "invent", "receta"],
                         ["food", "origin", "history", "dish", "invented", "recipe"]),
    "origen_marcas": ("historia de la marca", "brand origin story",
                      ["marca", "empresa", "historia", "fundó", "logo", "origen"],
                      ["brand", "company", "history", "founded", "logo", "origin"]),
    "oficios_perdidos": ("oficios que desaparecieron", "jobs that no longer exist",
                         ["oficio", "trabajo", "profesi", "desapareci", "antiguo"],
                         ["job", "profession", "no longer", "disappear", "old", "occupation"]),
    "animales_raros": ("animales extraños", "weird animals",
                       ["animal", "especie", "criatura", "raro", "extraño"],
                       ["animal", "species", "creature", "weird", "strange"]),
    "economia_historias": ("economía explicada", "economics explained",
                           ["econom", "dinero", "inflaci", "precio", "banco", "mercado"],
                           ["econom", "money", "inflation", "price", "bank", "market"]),
    "estafas_historicas": ("estafas más grandes de la historia", "biggest scams in history",
                           ["estafa", "fraude", "engañ", "estafador", "timo"],
                           ["scam", "fraud", "con", "scammer", "ponzi", "hoax"]),
    "apuestas_historicas": ("apuestas más locas de la historia", "craziest bets in history",
                            ["apuesta", "apost", "casino", "ganó"],
                            ["bet", "wager", "gambl", "casino"]),
    "por_que_asi": ("la verdadera razón por la que", "the real reason why",
                    ["por qué", "razón", "motivo", "verdadera"],
                    ["why", "reason", "real"]),
    "misterios": ("misterios sin resolver", "unsolved mysteries",
                  ["misterio", "enigma", "inexplicable", "sin resolver", "desapareci"],
                  ["mystery", "unsolved", "unexplained", "disappear", "enigma"]),
    "leyendas_urbanas": ("leyendas urbanas", "urban legends",
                         ["leyenda", "mito", "cuento", "aparici"],
                         ["legend", "myth", "folklore", "tale"]),
    "mitologia": ("mitología", "mythology",
                  ["mitolog", "dios", "diosa", "mito", "zeus", "nórdic", "griega"],
                  ["mytholog", "god", "goddess", "myth", "zeus", "norse", "greek"]),
    "cuerpo_humano": ("cuerpo humano datos curiosos", "human body facts",
                      ["cuerpo", "cerebro", "corazón", "humano", "piel", "órgano"],
                      ["body", "brain", "heart", "human", "skin", "organ"]),
    "sesgos_psicologia": ("sesgo cognitivo", "cognitive bias",
                          ["sesgo", "psicolog", "efecto", "mente", "cerebro"],
                          ["bias", "psycholog", "effect", "mind", "brain"]),
    "filosofia": ("filosofía explicada", "philosophy explained",
                  ["filosof", "sócrates", "platón", "nietzsche", "estoic", "pensamiento"],
                  ["philosoph", "socrates", "plato", "nietzsche", "stoic"]),
    "supersticiones": ("origen de las supersticiones", "origin of superstitions",
                       ["supersti", "mala suerte", "buena suerte", "origen", "creencia"],
                       ["supersti", "bad luck", "good luck", "origin", "belief"]),
    "medicina_rara": ("medicina antigua", "weird medical history",
                      ["medicina", "médico", "tratamiento", "cura", "enfermedad", "antigua"],
                      ["medic", "doctor", "treatment", "cure", "disease", "surgery"]),
    "robos_famosos": ("robos más famosos de la historia", "greatest heist in history",
                      ["robo", "ladr", "atraco", "robaron", "botín"],
                      ["heist", "robbery", "thief", "stole", "stolen", "robbed"]),
    "errores_traduccion": ("errores de traducción", "translation mistakes",
                           ["traducci", "tradu", "idioma", "significa"],
                           ["translat", "language", "lost in", "means"]),
    "historia_juguetes": ("historia de los juguetes", "toy history",
                          ["juguete", "juego", "muñec", "invent", "historia"],
                          ["toy", "game", "doll", "invent", "history"]),
    "que_pasaria_si": ("qué pasaría si", "what would happen if",
                       ["qué pasaría", "que pasaria", "si "],
                       ["what would happen", "what if", "if "]),
}


class SinCuota(Exception):
    pass


def clave():
    k = dotenv_values(ENV).get("YOUTUBE_API_KEY")
    if not k:
        raise SystemExit("falta YOUTUBE_API_KEY")
    return k


GASTO = AQUI / "raw" / "_gasto.json"


def sumar_gasto(u):
    g = json.loads(GASTO.read_text()) if GASTO.exists() else {"unidades": 0}
    g["unidades"] += u
    GASTO.write_text(json.dumps(g))


def pedir(endpoint, params, costo):
    p = dict(params)
    p["key"] = clave()
    r = requests.get(f"{API}/{endpoint}", params=p, timeout=30)
    sumar_gasto(costo)
    if r.status_code != 200:
        try:
            razon = r.json()["error"]["errors"][0]["reason"]
        except Exception:
            razon = f"http {r.status_code}"
        if razon in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise SinCuota(razon)
        raise RuntimeError(f"{endpoint}: {razon}")
    return r.json()


def buscar():
    for nombre, (q_es, q_en, *_r) in NICHOS.items():
        for lang, q in (("es", q_es), ("en", q_en)):
            f = RAW / f"search_{nombre}_{lang}.json"
            if f.exists():
                continue
            d = pedir("search", {
                "part": "snippet", "q": q, "type": "video", "videoDuration": "short",
                "order": "viewCount", "publishedAfter": DESDE, "relevanceLanguage": lang,
                "maxResults": 50}, 100)
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            print(f"busqueda ok {nombre} {lang}: {len(d.get('items', []))}", flush=True)
    detalles()


def lotes(ids, n=50):
    ids = sorted(set(ids))
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


def cache_lote(tipo, ids, endpoint, part):
    h = hashlib.sha1(",".join(ids).encode()).hexdigest()[:12]
    f = RAW / f"{tipo}_{h}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    d = pedir(endpoint, {"part": part, "id": ",".join(ids), "maxResults": 50}, 1)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def ids_videos():
    out = []
    for f in RAW.glob("search_*.json"):
        for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            out.append(it["id"]["videoId"])
    return out


def cargar_videos():
    vids = {}
    for f in RAW.glob("videos_*.json"):
        for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            vids[it["id"]] = it
    return vids


def cargar_canales():
    ch = {}
    for f in RAW.glob("channels_*.json"):
        for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
            ch[it["id"]] = it
    return ch


def detalles():
    ya = cargar_videos()
    faltan = [v for v in set(ids_videos()) if v not in ya]
    for lote in lotes(faltan):
        cache_lote("videos", lote, "videos", "snippet,statistics,contentDetails")
    vids = cargar_videos()
    canales = {v["snippet"]["channelId"] for v in vids.values()}
    ya_c = cargar_canales()
    for lote in lotes([c for c in canales if c not in ya_c]):
        cache_lote("channels", lote, "channels", "snippet,statistics")
    print("detalles ok", flush=True)


def segundos(iso):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


ES_W = {"el", "la", "los", "las", "de", "del", "que", "por", "para", "en", "un", "una", "es",
        "se", "su", "con", "qué", "por qué", "cómo", "como", "más", "mas", "y", "lo", "al", "no"}
EN_W = {"the", "of", "and", "is", "to", "why", "this", "you", "that", "was", "in", "a", "how",
        "what", "for", "with", "it", "are", "on", "his", "her", "they", "be"}


PT = re.compile(r"\b(não|voc[êe]|uma|tamb[ée]m|isso|muito|como o|venceu|quebrou|tentaram|existem|dinheiro|homem|manter|explicada como)\b|ção|ções|ã")


def idioma(titulo, sn):
    letras = re.findall(r"[^\W\d_]", titulo)
    no_latinas = [c for c in letras if ord(c) > 0x24F]
    if letras and len(no_latinas) / len(letras) > 0.2:
        return "otro"
    if PT.search(titulo.lower()):
        return "pt"
    lang = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "").lower()
    t = titulo.lower()
    pal = re.findall(r"[a-záéíóúñü]+", t)
    es = sum(w in ES_W for w in pal) + 2 * len(re.findall(r"[ñáéíóú¿¡]", t))
    en = sum(w in EN_W for w in pal)
    if es > en:
        return "es"
    if en > es:
        return "en"
    if lang.startswith("es"):
        return "es"
    if lang.startswith("en"):
        return "en"
    return "?"


def del_tema(v, nicho, lang):
    """Estricto: sobre el TÍTULO, todos los grupos de tema.T[nicho] tienen que coincidir."""
    from tema import T
    grupos = T[nicho][0 if lang == "es" else 1]
    t = v["snippet"].get("title", "").lower()
    return all(re.search(g, t) for g in grupos)


def mediana(xs):
    return statistics.median(xs) if xs else 0


def analizar():
    vids = cargar_videos()
    ch = cargar_canales()
    res = {}
    for nombre, (q_es, q_en, pal_es, pal_en) in NICHOS.items():
        res[nombre] = {"q_es": q_es, "q_en": q_en}
        for lang, pal in (("es", pal_es), ("en", pal_en)):
            f = RAW / f"search_{nombre}_{lang}.json"
            if not f.exists():
                res[nombre][lang] = None
                continue
            items = json.loads(f.read_text(encoding="utf-8")).get("items", [])
            filas, motivos = [], {"largo": 0, "idioma": 0, "tema": 0, "sin_datos": 0}
            for it in items:
                v = vids.get(it["id"]["videoId"])
                if not v:
                    motivos["sin_datos"] += 1
                    continue
                dur = segundos(v["contentDetails"].get("duration"))
                if dur is None or dur > MAX_S:
                    motivos["largo"] += 1
                    continue
                sn = v["snippet"]
                if idioma(sn["title"], sn) != lang:
                    motivos["idioma"] += 1
                    continue
                if not del_tema(v, nombre, lang):
                    motivos["tema"] += 1
                    continue
                c = ch.get(sn["channelId"], {})
                cs = c.get("statistics", {})
                subs = None if cs.get("hiddenSubscriberCount") else int(cs.get("subscriberCount", 0))
                filas.append({
                    "id": v["id"], "titulo": sn["title"], "canal": sn["channelTitle"],
                    "canal_id": sn["channelId"], "subs": subs,
                    "vistas": int(v["statistics"].get("viewCount", 0)),
                    "likes": int(v["statistics"].get("likeCount", 0) or 0),
                    "comentarios": int(v["statistics"].get("commentCount", 0) or 0),
                    "dur": dur, "publicado": sn["publishedAt"][:10],
                })
            filas.sort(key=lambda x: -x["vistas"])
            top = filas[:20]
            vistas = [x["vistas"] for x in top]
            canales = {x["canal_id"]: x["subs"] for x in filas}
            grandes = [c for c, s in canales.items() if s and s >= 1_000_000]
            chicos_100k = [x for x in filas if x["vistas"] >= 100_000 and x["subs"] is not None
                           and x["subs"] < 10_000]
            medianos_100k = [x for x in filas if x["vistas"] >= 100_000 and x["subs"] is not None
                             and x["subs"] < 100_000]
            mas_100k = [x for x in filas if x["vistas"] >= 100_000]
            # concentración: % de las vistas del top 20 que se lleva el canal más fuerte
            por_canal = {}
            for x in top:
                por_canal[x["canal"]] = por_canal.get(x["canal"], 0) + x["vistas"]
            conc = (max(por_canal.values()) / sum(vistas)) if vistas and sum(vistas) else 0
            res[nombre][lang] = {
                "resultados_api": len(items), "validos": len(filas), "descartes": motivos,
                "max": max(vistas) if vistas else 0, "mediana_top20": mediana(vistas),
                "n_100k": len(mas_100k), "canales": len(canales),
                "canales_1M": len(grandes),
                "mediana_subs": mediana([s for s in canales.values() if s is not None]),
                "chicos_10k_con_100k": len(chicos_100k),
                "menores_100k_con_100k": len(medianos_100k),
                "concentracion_top_canal": round(conc, 2),
                "top": filas[:8],
                "ejemplos_chicos": chicos_100k[:5],
            }
    puntuar(res)
    (AQUI / "resultados.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("resultados.json listo")


def norm(vals):
    lo, hi = min(vals.values()), max(vals.values())
    return {k: (v - lo) / (hi - lo) if hi > lo else 0.5 for k, v in vals.items()}


def puntuar(res):
    ok = {k: v for k, v in res.items() if v.get("es") and v.get("en")}
    lg = lambda x: math.log10(1 + x)
    dem_es = norm({k: lg(v["es"]["mediana_top20"]) for k, v in ok.items()})
    dem_en = norm({k: lg(v["en"]["mediana_top20"]) for k, v in ok.items()})
    # apertura: videos de >100k en español hechos por canales <100k subs (proporción) y <10k
    ap_prop = norm({k: (v["es"]["menores_100k_con_100k"] / v["es"]["n_100k"]
                        if v["es"]["n_100k"] else 0) for k, v in ok.items()})
    ap_chicos = norm({k: math.log2(1 + v["es"]["chicos_10k_con_100k"]) for k, v in ok.items()})
    brecha = norm({k: lg(v["en"]["mediana_top20"]) - lg(v["es"]["mediana_top20"])
                   for k, v in ok.items()})
    satur = norm({k: v["es"]["canales_1M"] + 10 * v["es"]["concentracion_top_canal"]
                  for k, v in ok.items()})
    for k in ok:
        demanda = 0.5 * dem_es[k] + 0.5 * dem_en[k]
        apertura = 0.5 * ap_prop[k] + 0.5 * ap_chicos[k]
        s = 0.40 * demanda + 0.30 * apertura + 0.15 * brecha[k] + 0.15 * (1 - satur[k])
        res[k]["puntaje"] = {"total": round(100 * s, 1), "demanda": round(demanda, 2),
                             "apertura": round(apertura, 2), "brecha": round(brecha[k], 2),
                             "saturacion": round(satur[k], 2)}


if __name__ == "__main__":
    try:
        if sys.argv[1] == "buscar":
            buscar()
        else:
            analizar()
    except SinCuota as e:
        print(f"CUOTA AGOTADA ({e}): pare. Lo medido quedó en raw/.")
        sys.exit(2)
