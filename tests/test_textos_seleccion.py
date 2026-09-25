import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from clips_bot.candidates import es_costream
from clips_bot.config import Filtros, Seleccion, Textos
from clips_bot.gemini import GeminiClient, GeminiError
from clips_bot.seleccion import Opcion, seleccionar, validar_orden
from clips_bot.telegram import TelegramClient, TelegramError, chats, mensaje_textos, resolver_chat_id
from clips_bot.textos import SCHEMA, TextosError, generar, parsear, validar

CFG = Textos()
VALIDO = {
    "titulo": "No puede creer lo que le pasó en la última ronda",
    "descripcion": "El streamer pierde una partida ganada por un error insólito.",
    "hashtags": ["#Shorts", "#elxokas", "#WoW"],
    "gancho": "reaccion",
    "depende_de_fecha": False,
    "sensible": False,
    "puntaje": 7,
}


# ---- formato de textos (paso 7) ------------------------------------------------


def test_valido_pasa_y_agrega_credito():
    t, errores = parsear(json.dumps(VALIDO), CFG, "elxokas", "elxokas")
    assert errores == []
    assert t.titulo == VALIDO["titulo"]
    assert t.credito == "Clip de elxokas — twitch.tv/elxokas"
    assert t.descripcion.endswith("\n\nClip de elxokas — twitch.tv/elxokas")
    assert t.hashtags == ("#Shorts", "#elxokas", "#WoW")
    assert set(t.to_dict()) == {"titulo", "descripcion", "hashtags", "gancho", "credito",
                                "depende_de_fecha", "sensible", "puntaje"}
    assert t.depende_de_fecha is False
    assert t.sensible is False and t.puntaje == 7


@pytest.mark.parametrize(
    "cambio, error",
    [
        ({"titulo": "x" * 60}, "máximo 59"),
        ({"titulo": ""}, "titulo tiene que ser"),
        ({"titulo": "Mirá esto #fail"}, "hashtags"),
        ({"titulo": 123}, "titulo tiene que ser"),
        ({"descripcion": "mirá https://x.com"}, "links"),
        ({"descripcion": "texto #tag"}, "hashtags ni links"),
        ({"hashtags": ["#Shorts", "#a"]}, "entre 3 y 5"),
        ({"hashtags": ["#Shorts", "#a", "#b", "#c", "#d", "#e"]}, "entre 3 y 5"),
        ({"hashtags": ["#a", "#b", "#c"]}, "falta #Shorts"),
        ({"hashtags": ["#Shorts", "sin_numeral", "#b"]}, "formato inválido"),
        ({"hashtags": ["#Shorts", "#dos palabras", "#b"]}, "formato inválido"),
        ({"hashtags": ["#Shorts", "#shorts", "#b"]}, "repetidos"),
        ({"hashtags": "#Shorts #a #b"}, "lista"),
        ({"gancho": "otro"}, "gancho"),
        ({"extra": 1}, "no permitidos"),
    ],
)
def test_invalidos(cambio, error):
    data = {**VALIDO, **cambio}
    errores = validar(data, CFG)
    assert any(error in e for e in errores), errores


def test_espacios_alrededor_de_hashtags_se_normalizan():
    t, errores = parsear(json.dumps({**VALIDO, "hashtags": [" #Shorts", "#elxokas ", "#WoW"]}), CFG, "x", "x")
    assert errores == [] and t.hashtags == ("#Shorts", "#elxokas", "#WoW")
    # pero un espacio en el medio sigue siendo inválido
    _, errores = parsear(json.dumps({**VALIDO, "hashtags": ["#Shorts", "#el xokas", "#WoW"]}), CFG, "x", "x")
    assert any("formato inválido" in e for e in errores)


def test_faltan_campos_y_no_json():
    assert any("faltan campos" in e for e in validar({"titulo": "hola"}, CFG))
    assert validar([VALIDO], CFG) == ["la respuesta no es un objeto JSON"]
    t, errores = parsear("```json\n{}```", CFG, "a", "a")
    assert t is None and "no es JSON" in errores[0]


def test_schema_coincide_con_validacion():
    assert set(SCHEMA["required"]) == set(VALIDO)
    assert set(SCHEMA["properties"]) == set(VALIDO)


class FakeGemini:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.prompts = []

    def json(self, sistema, prompt, schema, temperatura=0.7, imagenes=None):
        self.prompts.append(prompt)
        self.imagenes = imagenes
        return self.respuestas.pop(0)


def _generar(cliente):
    return generar(cliente, CFG, canal="Elxokas", login="elxokas", categoria="WoW",
                   titulo_twitch="FOG", duracion=30, transcripcion="hola")


def test_generar_reintenta_con_los_errores():
    malo = json.dumps({**VALIDO, "hashtags": ["#a", "#b", "#c"]})
    cliente = FakeGemini([malo, json.dumps(VALIDO)])
    t = _generar(cliente)
    assert t.titulo == VALIDO["titulo"]
    assert "falta #Shorts" in cliente.prompts[1]


def test_generar_falla_si_nunca_valida():
    cliente = FakeGemini(["{}"] * (1 + CFG.reintentos))
    with pytest.raises(TextosError):
        _generar(cliente)
    assert cliente.respuestas == []  # usó todos los reintentos configurados


def test_generar_insiste_si_gemini_manda_un_solo_hashtag():
    # visto en vivo 2026-09-22: Gemini devolvió 1 hashtag en 2 de 3 clips
    un_hashtag = json.dumps({**VALIDO, "hashtags": ["#Shorts"]})
    cliente = FakeGemini([un_hashtag, un_hashtag, json.dumps(VALIDO)])
    assert _generar(cliente).hashtags == ("#Shorts", "#elxokas", "#WoW")
    assert "entre 3 y 5" in cliente.prompts[-1]


class Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def post(self, url, headers=None, json=None, timeout=None, data=None, files=None):
        self.llamadas.append({"url": url, "headers": headers, "json": json, "data": data, "files": files})
        return self.respuestas.pop(0)


def test_gemini_http_pide_json_y_extrae_texto():
    ok = {"candidates": [{"content": {"parts": [{"text": json.dumps(VALIDO)}]}}]}
    s = FakeSession([Resp(503, {}), Resp(200, ok)])
    c = GeminiClient("KEY", "gemini-x", session=s, sleep=lambda _: None)
    assert json.loads(c.json("sis", "prompt", SCHEMA)) == VALIDO
    llamada = s.llamadas[1]
    assert "gemini-x:generateContent" in llamada["url"]
    assert llamada["headers"]["x-goog-api-key"] == "KEY"
    assert llamada["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_4xx_no_reintenta():
    s = FakeSession([Resp(400, {"error": "bad"})])
    with pytest.raises(GeminiError):
        GeminiClient("K", "m", session=s, sleep=lambda _: None).json("s", "p", SCHEMA)
    assert len(s.llamadas) == 1


# ---- co-stream -----------------------------------------------------------------------

FILTROS = Filtros(
    palabras_costream=("LEC", "co-stream", "costream", "Kings League", "partido", "final"),
    categorias_costream=("Sports", "Special Events"),
)


@pytest.mark.parametrize(
    "titulos, categoria, esperado",
    [
        (["REACCIONANDO A LA LEC"], "League of Legends", True),
        (["Co-Stream Worlds"], "", True),
        (["COSTREAM con amigos"], "", True),
        (["kings league jornada 3"], "", True),
        (["", "Viendo el PARTIDO de hoy"], "Just Chatting", True),  # título del stream
        (["la final más épica"], "", True),  # falso positivo aceptado
        (["Mi colección de cartas"], "Just Chatting", False),  # "lec" dentro de otra palabra
        (["finalmente gané"], "Minecraft", False),
        (["un repartidor"], "", False),
        (["lo que sea"], "Sports", True),
        (["lo que sea"], "League of Legends", False),
    ],
)
def test_es_costream(titulos, categoria, esperado):
    assert es_costream(titulos, categoria, FILTROS, con_deportes=True) is esperado


def test_las_palabras_de_futbol_solo_aplican_a_los_streamers_de_deportes():
    """Medido en los 52 canales del Dedsafío (2026-09-22): con las palabras de fútbol aplicadas a
    todos, 6 de los 12 descartes eran falsos positivos ("Final de Geoware World", "boss final")."""
    f = Filtros(palabras_costream=("LEC", "Worlds"), palabras_deportes=("final", "partido", "gol"))
    juego = ["cinemática del boss final"]
    assert es_costream(juego, "Minecraft", f, con_deportes=False) is False  # streamer normal: pasa
    assert es_costream(juego, "Minecraft", f, con_deportes=True) is True  # Davoo y cía: se descarta
    # las de esports siguen valiendo para todos
    assert es_costream(["REACCIONANDO A LA LEC"], "Minecraft", f, con_deportes=False) is True


# ---- selección (paso 8) --------------------------------------------------------------

AHORA = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


def op(id, streamer, vistas, horas, fuente="reciente", momento=1):
    return Opcion(id, streamer, vistas, AHORA - timedelta(hours=horas), titulo=id, fuente=fuente,
                  clips_mismo_momento=momento)


def solo_recientes(n, empate_pct=0.0, **kw):
    return Seleccion(mezcla={"reciente": n, "catalogo": 0},
                     empate_pct={"reciente": empate_pct, "catalogo": 0.0}, **kw)


def test_tope_por_streamer_en_recientes():
    cfg = solo_recientes(3, max_por_streamer=2, empate_pct=0.0)
    opciones = [
        op("a1", "a", 3000, 30),
        op("a2", "a", 2800, 30),
        op("a3", "a", 2600, 30),  # tercero de "a": queda afuera
        op("b1", "b", 1500, 30),
    ]
    assert [o.clip_id for o in seleccionar(opciones, cfg, AHORA)] == ["a1", "a2", "b1"]


def test_desempate_solo_si_el_empate_cruza_el_corte():
    cfg = solo_recientes(2, max_por_streamer=5, empate_pct=0.10)
    llamados = []

    def invertir(grupo):
        llamados.append([o.clip_id for o in grupo])
        return list(reversed(grupo))

    # scores log: x 4.70, y 4.00, z 3.98, w 3.00. Corte en y; z queda a menos del 10 % → empate.
    opciones = [op("x", "a", 50_000, 30), op("y", "b", 1000, 30), op("z", "c", 950, 30), op("w", "d", 10, 30)]
    assert [o.clip_id for o in seleccionar(opciones, cfg, AHORA, invertir)] == ["x", "z"]
    assert llamados == [["y", "z"]]

    # OJO: 10 % sobre un score logarítmico es ancho (≈ 2,5× en vistas). Acá sí quedan separados.
    llamados.clear()
    sin_empate = [op("x", "a", 50_000, 30), op("y", "b", 1000, 30), op("z", "c", 1, 30)]
    assert [o.clip_id for o in seleccionar(sin_empate, cfg, AHORA, invertir)] == ["x", "y"]
    assert llamados == []


def test_desempate_que_falla_no_rompe():
    cfg = solo_recientes(1, empate_pct=0.5)

    def explota(grupo):
        raise RuntimeError("gemini caído")

    opciones = [op("x", "a", 1000, 0), op("y", "b", 900, 0)]
    assert [o.clip_id for o in seleccionar(opciones, cfg, AHORA, explota)] == ["x"]


def test_validar_orden():
    assert validar_orden('{"orden": ["b", "a"]}', ["a", "b"]) == ["b", "a"]
    for malo in ['{"orden": ["a"]}', '{"orden": ["a", "a"]}', '{"orden": ["a", "c"]}', "no json", "[]"]:
        with pytest.raises(ValueError):
            validar_orden(malo, ["a", "b"])


# ---- Telegram ---------------------------------------------------------------------


def test_chats_y_resolver_chat_id():
    updates = [
        {"message": {"chat": {"id": 111, "type": "private", "first_name": "Santi", "username": "santi"}}},
        {"message": {"chat": {"id": 111, "type": "private", "first_name": "Santi"}}},
        {"my_chat_member": {}},
    ]
    assert chats(updates) == [{"id": "111", "tipo": "private", "nombre": "Santi"}]

    class TG:
        def __init__(self, ups):
            self.ups = ups

        def get_updates(self):
            return self.ups

    assert resolver_chat_id(TG([]), "999") == "999"
    assert resolver_chat_id(TG(updates), "") == "111"
    with pytest.raises(TelegramError):
        resolver_chat_id(TG([]), "")
    dos = updates + [{"message": {"chat": {"id": 222, "type": "private", "first_name": "Otro"}}}]
    with pytest.raises(TelegramError):
        resolver_chat_id(TG(dos), "")


def test_mensaje_textos_escapa_html_y_tiene_bloques():
    textos = {"titulo": "<b>ojo</b> & más", "descripcion": "desc\n\nClip de X — twitch.tv/x",
              "hashtags": ["#Shorts", "#x", "#y"], "credito": "Clip de X — twitch.tv/x"}
    m = mensaje_textos(2, "x", "Slug-1", "18:00", textos)
    assert "&lt;b&gt;ojo&lt;/b&gt; &amp; más" in m
    assert m.count("<pre>") == 4
    assert "sugerido 18:00 AR" in m and "<code>Slug-1</code>" in m
    assert "<pre>#Shorts #x #y</pre>" in m


def test_telegram_rechaza_archivos_grandes(tmp_path: Path):
    grande = tmp_path / "v.mp4"
    with grande.open("wb") as f:
        f.truncate(51 * 1024 * 1024)
    with pytest.raises(TelegramError, match="50 MB"):
        TelegramClient("T", session=FakeSession([])).send_video("1", grande)


def test_send_video_manda_dimensiones_y_miniatura(tmp_path: Path):
    video, thumb = tmp_path / "v.mp4", tmp_path / "v.jpg"
    video.write_bytes(b"x")
    thumb.write_bytes(b"y")
    s = FakeSession([Resp(200, {"ok": True, "result": {}})])
    TelegramClient("T", session=s).send_video("1", video, "cap", width=1080, height=1920, duration=30,
                                             thumbnail=thumb)
    llamada = s.llamadas[0]
    assert llamada["url"].endswith("/sendVideo")
    assert llamada["data"] | {} == {"chat_id": "1", "caption": "cap", "supports_streaming": "true",
                                    "width": "1080", "height": "1920", "duration": "30"}
    assert set(llamada["files"]) == {"video", "thumbnail"}


def test_telegram_error_de_api():
    s = FakeSession([Resp(400, {"ok": False, "error_code": 400, "description": "chat not found"})])
    with pytest.raises(TelegramError, match="chat not found"):
        TelegramClient("T", session=s).send_message("1", "hola")
    assert s.llamadas[0]["data"]["parse_mode"] == "HTML"


# ---- el título contra lo que se dice ------------------------------------------------


def test_nombres_propios_del_titulo():
    from clips_bot.textos import nombres_propios

    # mayúscula en medio de la oración = nombra algo
    assert nombres_propios("Reconoce que no conoce a Zelda") == ["Zelda"]
    assert nombres_propios("¿Podría Luka ganar contra Nani?") == ["Luka", "Nani"]
    # la primera palabra NO se mira: en español va en mayúscula siempre y no dice nada.
    # Es un agujero conocido y a propósito: mirarla haría saltar "Reconoce" como si fuera un nombre.
    assert nombres_propios("Zelda le gana a todos") == []
    assert nombres_propios("no hay manera de que pase esto") == []


def test_un_titulo_que_nombra_algo_que_nadie_dijo_no_vale():
    from clips_bot.config import Textos
    from clips_bot.textos import nombres_sin_respaldo, validar

    def texto(titulo):
        return {"titulo": titulo, "descripcion": "algo pasa en el clip",
                "hashtags": ["#Shorts", "#Uno", "#Dos"], "gancho": "reaccion",
                "depende_de_fecha": False, "sensible": False, "puntaje": 7}

    dicho = "uy no puedo creer lo que hizo el Mario ese"
    assert nombres_sin_respaldo("Se pelea con Mario", dicho) == []
    assert nombres_sin_respaldo("Se pelea con Zelda", dicho) == ["Zelda"]
    # la categoría y el nombre del canal también cuentan como respaldo
    assert nombres_sin_respaldo("Un fail en Minecraft", "que desastre | Minecraft") == []

    errores = validar(texto("Se pelea con Zelda"), Textos(), contexto=dicho)
    assert any("Zelda" in e for e in errores)
    assert validar(texto("Se pelea con Mario"), Textos(), contexto=dicho) == []
    # sin contexto no se chequea nada (ruta vieja, ej. tests o textos regenerados sin transcripción)
    assert validar(texto("Se pelea con Zelda"), Textos()) == []


def test_el_caso_real_de_zelda_NO_lo_agarra_este_chequeo():
    """Honestidad sobre el alcance: en el Short que salió mal, "Zelda" SÍ estaba en la
    transcripción ("en memoria de Zelda", de unos créditos). El título estaba mal porque el
    multi-POV juntó tres momentos sin relación, no porque inventara un nombre."""
    from clips_bot.textos import nombres_sin_respaldo

    real = "Campfire Studios, los constructores, los builders. En memoria de Zelda, el tiempo siempre"
    assert nombres_sin_respaldo("Reconoce que no conoce a Zelda", real) == []
