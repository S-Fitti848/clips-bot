"""Hashtags de Rots (2026-11-10): los Shorts subidos por la API salían sin ningún hashtag en la
descripción, con tags y en la categoría 20; los subidos a mano (los que salían en el feed) tenían
"<texto>\n\n#Shorts #streamer #tema\n\nClip de X — url", sin tags y en la 22."""
from types import SimpleNamespace

import clips_bot.__main__ as m
from clips_bot import db, youtube
from clips_bot.textos import descripcion_youtube, hashtags_youtube

CHARLA = ("Just Chatting", "IRL")
CRED = "Clip de auronplay — twitch.tv/auronplay"


def _meta(**extra):
    base = {"clip_id": "c1", "streamer": "auronplay", "plataforma": "twitch", "categoria": "Minecraft",
            "salida": "x.mp4",
            "textos": {"titulo": "Auron se ríe", "descripcion": f"Auron se ríe en Minecraft.\n\n{CRED}",
                       "credito": CRED, "hashtags": ["#Shorts射", "#Auronplay", "#Humor"]}}
    base.update(extra)
    return base


def test_streamer_plataforma_tema_y_shorts():
    assert hashtags_youtube(_meta(), CHARLA) == ["#Shorts", "#auronplay", "#twitch", "#minecraft"]
    assert hashtags_youtube(_meta(streamer="davooxeneize", plataforma="kick", categoria="Rocket League"),
                            CHARLA) == ["#Shorts", "#davooxeneize", "#kick", "#rocketleague"]
    # un juego con subtítulo: solo el nombre
    assert hashtags_youtube(_meta(categoria="Age of Empires II: Definitive Edition"), CHARLA)[-1] \
        == "#ageofempiresii"


def test_charla_sin_tema_o_futbol():
    assert hashtags_youtube(_meta(categoria="Just Chatting"), CHARLA) == ["#Shorts", "#auronplay", "#twitch"]
    por_gemini = _meta(streamer="lacobraaa", plataforma="kick", categoria="Just Chatting",
                       textos={**_meta()["textos"], "hashtags": ["#Shorts", "#Fútbol", "#Boca"]})
    assert hashtags_youtube(por_gemini, CHARLA) == ["#Shorts", "#lacobraaa", "#kick", "#futbol"]
    # el aviso de fútbol sale del título del STREAM: solo no alcanza (el corpiño de La Cobra)
    solo_aviso = _meta(categoria="Just Chatting", textos={**_meta()["textos"], "hashtags": ["#Humor"]},
                       aviso="⚽ habla de fútbol (Boca): no se descarta por eso; mirá que no se vea el partido")
    assert hashtags_youtube(solo_aviso, CHARLA) == ["#Shorts", "#auronplay", "#twitch"]


def test_entre_3_y_5_y_sin_repetir():
    for meta in (_meta(), _meta(categoria="Just Chatting"), _meta(categoria="Twitch")):
        h = hashtags_youtube(meta, CHARLA)
        assert 3 <= len(h) <= 5 and len(set(h)) == len(h) and h[0] == "#Shorts"


def test_descripcion_con_el_formato_de_los_subidos_a_mano():
    assert descripcion_youtube(_meta(), CHARLA) == (
        f"Auron se ríe en Minecraft.\n\n#Shorts #auronplay #twitch #minecraft\n\n{CRED}")
    # si la descripción ya traía hashtags al final, no quedan dos líneas
    viejo = _meta(textos={**_meta()["textos"],
                          "descripcion": f"Texto.\n\n#Shorts #Auron\n\n{CRED}"})
    assert descripcion_youtube(viejo, CHARLA).count("#Shorts") == 1


def test_subida_a_rots_sin_tags_categoria_22(monkeypatch, tmp_path):
    subidas = []

    class Cliente:
        respuesta_subida = {}

        def __init__(self, canal):
            pass

        def subir(self, video, titulo, desc, tags, publicar, categoria, publico=False):
            subidas.append((desc, tags, categoria))
            return "vid1"

    monkeypatch.setattr(youtube, "Cliente", Cliente)
    monkeypatch.setattr(m, "_portada_de", lambda meta: None)
    conn = db.connect(tmp_path / "t.db")
    s = m.load_settings()
    m._programar_subida(conn, s, _meta(), "rots", "13:00")
    desc, tags, cat = subidas[0]
    assert "#Shorts #auronplay #twitch #minecraft" in desc and tags == [] and cat == "22"
    cuerpo = youtube.metadatos("t", desc, tags, None, cat)
    assert cuerpo["snippet"]["tags"] == [] and cuerpo["snippet"]["categoryId"] == "22"


def test_pequena_historia_no_cambia():
    meta = _meta(textos={"titulo": "t", "descripcion": "d", "hashtags": ["#Historia"]})
    assert m._para_youtube(meta, "pequena_historia") == ("d", ["#Historia"])
    assert m.CATEGORIA["pequena_historia"] == "27"


def test_corregir_publicados(monkeypatch, tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.crear_subida(conn, "c1", "rots", "programada", video_id="V1", publish_at="2026-11-01T16:00:00Z")
    db.crear_subida(conn, "c2", "rots", "programada", video_id="V2", publish_at="2026-11-02T16:00:00Z")
    db.crear_subida(conn, "efe", "pequena_historia", "programada", video_id="VE")
    monkeypatch.setattr(m, "DB_PATH", tmp_path / "t.db")
    metas = {"c1": _meta(), "c2": {}}
    monkeypatch.setattr(m, "_meta_de", lambda cid: metas.get(cid, {}))
    cambios = []

    class Cliente:
        def __init__(self, canal):
            assert canal == "rots"

        def snippet(self, vid):
            # la publicada se corrigió a mano después de subirla: se respeta, no se vuelve al json
            return {"title": "Auron se ríe", "description": "Auron se ríe (corregido).\n\n" + CRED,
                    "categoryId": "20", "tags": ["Shorts", "auronplay"], "defaultLanguage": "es"}

        def cambiar_snippet(self, vid, sn):
            cambios.append((vid, sn))

    monkeypatch.setattr(youtube, "Cliente", Cliente)
    m.cmd_hashtags_rots(SimpleNamespace(aplicar=False))
    assert cambios == []                       # sin --aplicar no toca nada
    m.cmd_hashtags_rots(SimpleNamespace(aplicar=True))
    assert [v for v, _ in cambios] == ["V1"]   # sin json no se toca; Pequeña Historia tampoco
    sn = cambios[0][1]
    assert sn["title"] == "Auron se ríe" and sn["categoryId"] == "22" and sn["tags"] == []
    assert sn["description"] == f"Auron se ríe (corregido).\n\n#Shorts #auronplay #twitch #minecraft\n\n{CRED}"


def test_insertar_hashtags_en_lo_publicado():
    from clips_bot.textos import insertar_hashtags

    h = ["#Shorts", "#coker", "#kick"]
    # crédito de Kick aunque el json dijera otra cosa: se busca la línea "Clip de"
    assert insertar_hashtags("Texto.\n\nClip de coker — kick.com/coker", h, "Clip de coker — twitch.tv/coker") \
        == "Texto.\n\n#Shorts #coker #kick\n\nClip de coker — kick.com/coker"
    # hashtags viejos después del crédito (la prueba pública de oct.): se reemplazan
    assert insertar_hashtags("Texto.\n\nClip de coker — kick.com/coker\n\n#Shorts #Davo #Kick", h) \
        == "Texto.\n\n#Shorts #coker #kick\n\nClip de coker — kick.com/coker"
    # multi-POV
    assert insertar_hashtags("Texto.\n\nClips de:\n· a — twitch.tv/a", h) \
        == "Texto.\n\n#Shorts #coker #kick\n\nClips de:\n· a — twitch.tv/a"
    assert insertar_hashtags("Solo texto.", h) == "Solo texto.\n\n#Shorts #coker #kick"


def test_cambiar_snippet_manda_titulo_y_categoria():
    enviado = {}

    class Sesion:
        def put(self, url, params, headers, data, timeout):
            import json
            enviado.update(json.loads(data))
            return SimpleNamespace(status_code=200, json=lambda: {}, text="", headers={})

    c = youtube.Cliente.__new__(youtube.Cliente)
    c.session, c.canal = Sesion(), "rots"
    c._headers = lambda: {}
    c.cambiar_snippet("V1", {"title": "T", "description": "D", "categoryId": "22", "tags": [],
                             "defaultLanguage": "es", "thumbnails": {}})
    assert enviado == {"id": "V1", "snippet": {"title": "T", "description": "D", "categoryId": "22",
                                               "defaultLanguage": "es"}}
