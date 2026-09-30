"""Carga de config (YAML) y secretos (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
DB_PATH = DATA_DIR / "clips.db"


class ConfigError(RuntimeError):
    pass


PLATAFORMAS = ("twitch", "kick")
GRUPO_FALLBACK = "catalogo"  # los cupos que un grupo no llena se los queda este


@dataclass(frozen=True)
class Streamer:
    login: str
    plataforma: str = "twitch"
    fuentes: tuple[str, ...] = ("reciente",)
    grupo: str = ""
    cita: str = ""
    fuente: str = ""
    verificado: str = ""
    experimento: bool = False
    subtitulos_propios: bool = False  # ya trae subtítulos en vivo quemados → no quemar los nuestros
    detectar_marcador: bool = False  # descartar clips con marcador de transmisión deportiva
    # Marcas de programa de terceros en el TÍTULO DEL STREAM (no el del clip): "412", "ANALIZAMOS".
    # Cuando el streamer está transmitiendo un programa con marca propia, todo ese stream queda
    # afuera aunque el clip no diga nada. Es por streamer porque una marca ajena en otro canal no
    # significa lo mismo. Motivo de descarte: programa_terceros.
    palabras_programa: tuple[str, ...] = ()
    # split | fullcam | fit_blur. Vacío = lo decide la detección de caras. Es para los canales cuyo
    # formato la heurística no puede ver (ej. coker: podcast multicámara, donde "el juego" no existe).
    layout_forzado: str = ""
    # Cómo lo nombran los demás, para buscar lo que pegó en otros canales (pego.py): "Davo", no
    # "davooxeneize". El login se busca siempre; esto se suma. Editable desde /streamers (DB).
    apodos: tuple[str, ...] = ()

    @property
    def permitido(self) -> bool:
        """Permiso público citado, o entrada como experimento (política 2026-09-22)."""
        return bool(self.cita.strip() and self.fuente.strip()) or self.experimento

    @property
    def como_entra(self) -> str:
        return "cita" if (self.cita.strip() and self.fuente.strip()) else "experimento"

    def grupo_de(self, fuente: str) -> str:
        return self.grupo or f"{self.plataforma}_{fuente}"


@dataclass(frozen=True)
class Filtros:
    ventana_horas: int = 168
    antiguedad_min_h: float = 24
    idioma: str = "es"
    duracion_min_s: float = 15
    duracion_max_s: float = 60
    min_vistas: int = 0
    n_candidatos: int = 8
    max_clips_por_streamer: int = 100
    categorias_excluidas: tuple[str, ...] = ("Music", "DJs")
    palabras_costream: tuple[str, ...] = ()
    palabras_deportes: tuple[str, ...] = ()  # solo para streamers con detectar_marcador
    categorias_costream: tuple[str, ...] = ()
    ventana_momento_s: float = 60
    # Vistas relativas (2026-09-29): por streamer, solo pasan los clips en esta fracción superior de
    # SUS vistas (7 días en recientes, histórico en catálogo). 0 = apagado; el valor real (0,30)
    # está en settings.yaml, y un test exige que siga ahí.
    vistas_top: float = 0.0


@dataclass(frozen=True)
class Evento:
    """Grupo "evento": un mismo evento transmitido por decenas de streamers a la vez."""
    categorias: tuple[str, ...] = ("Minecraft",)
    palabras: tuple[str, ...] = ("dedsafio", "nights")
    desde: str = ""  # AAAA-MM-DD; vacío = sin piso
    hasta: str = ""  # vacío = sin techo
    ventana_entre_streamers_s: float = 120  # ±2 min de hora real = misma muerte/momento


@dataclass(frozen=True)
class Kick:
    pausa_s: float = 1.0  # entre llamadas: la API interna no documenta su rate limit
    orden: str = "view"  # view = los más vistos (sin esto vienen los últimos subidos)
    ventana: str = "week"  # day | week | month | "" (todos)
    max_clips: int = 60


@dataclass(frozen=True)
class Catalogo:
    antiguedad_min_dias: int = 7
    antiguedad_max_dias: int = 1095
    min_vistas: int = 500
    n_candidatos: int = 4
    por_pagina: int = 20
    max_paginas: int = 3


@dataclass(frozen=True)
class Render:
    ancho: int = 1080
    alto: int = 1920
    fps: int = 30
    duracion_max_s: float = 59
    alto_camara: int = 768
    separador_px: int = 6
    recorte_inferior_camara_px: int = 50
    zoom_sin_camara: float = 1.08
    blur_sigma: float = 30  # fondo del layout fit_blur
    # El título del clip grande arriba y el streamer chiquito encima (2026-09-30). Apagado hasta
    # que Santi vea 3 muestras.
    titulo_arriba: bool = False
    x264_preset: str = "medium"
    crf: int = 20
    maxrate_kbps: int = 5000


@dataclass(frozen=True)
class Camara:
    frames_muestra: int = 20
    min_presencia: float = 0.4
    cara_grande: float = 0.12
    margen_borde: float = 0.15       # cara a menos de esto de un borde del recorte → fit_blur
    # Fracción de frames con una cara (que no es la de la cámara) dentro del recorte del "juego".
    # Por encima de esto no hay juego: es contenido multicámara y el split parte a alguien.
    presencia_juego_max: float = 0.20
    cara_juego_min: float = 0.065     # ancho mínimo (fracción del frame) para contar como persona
    # Charla o IRL con una persona: zoom siguiendo la cara (layout "sigue", 2026-09-30). Apagado
    # hasta que Santi vea 3 muestras.
    seguir_cara: bool = False
    persona_min: float = 0.6          # la persona ocupa al menos esto del alto
    categorias_charla: tuple = ("Just Chatting", "IRL", "Talk Shows & Podcasts", "Travel & Outdoors",
                                "Food & Drink", "Pools, Hot Tubs, and Beaches", "ASMR")


@dataclass(frozen=True)
class Subtitulos:
    modelo: str = "small"
    # Tope de tiempo de pared por clip: max(timeout_min_s, timeout_factor x duración del clip).
    # Medido en la Pi: los clips normales van a 0,7-1,5x y uno patológico se fue a 28x.
    timeout_factor: float = 8.0
    timeout_min_s: float = 60.0
    compute_type: str = "int8"
    cpu_threads: int = 0
    idioma: str = "es"
    fuente: str = "Arial"
    tamano: int = 64
    mayusculas: bool = False
    max_chars_linea: int = 24
    max_lineas: int = 2
    max_duracion_s: float = 3.0
    posicion_y: float = 0.80


@dataclass(frozen=True)
class FiltroAudio:
    max_silencio: float = 0.8
    min_palabras_por_s: float = 0.7
    silencio_db: float = -35
    silencio_min_s: float = 0.5


@dataclass(frozen=True)
class MarcadorDeportivo:
    frames_muestra: int = 12
    quietud_min: float = 0.75  # la región cambia 4 veces menos que el frame entero
    bordes_min: float = 0.05  # 5 % de los píxeles de la región son borde (texto/líneas del gráfico)
    cesped_min: float = 0.45  # fracción de verde-césped en un frame para contarlo como cancha
    cesped_frames_min: int = 2  # cuántos frames así hacen falta para descartar


@dataclass(frozen=True)
class MultiPov:
    """§3 paso 7b. `margen_s`: mitad de la ventana de cada ángulo alrededor de su pico."""
    # Prendido de nuevo el 2026-09-24, ahora con verificación de "mismo hecho" (ver
    # `es_el_mismo_hecho`). Va a prueba: si junta `votos_negativos_max` 👎 dentro de `dias_prueba`,
    # el bot lo apaga solo y avisa. Ese apagado vive en la DB, no acá.
    activo: bool = True
    votos_negativos_max: int = 2
    dias_prueba: int = 14
    margen_s: float = 4.0
    max_angulos: int = 3
    min_angulos: int = 3
    frames_muestra: int = 10
    frames_vacios_max: float = 0.34   # más de un tercio del tramo en negro → el ángulo no sirve
    # Verificación de "mismo hecho": tienen que pasar las DOS, la superposición léxica entre las
    # transcripciones y la pregunta a Gemini. La agrupación por hora de creación sola no alcanza.
    superposicion_min: float = 0.12
    luma_negro: float = 0.08          # un píxel por debajo de esto cuenta como negro
    pixeles_negros_min: float = 0.90  # y un frame es "vacío" con esta fracción de píxeles negros


@dataclass(frozen=True)
class Voz:
    """TTS para el modo /narrar. Piper, local y gratis: ver la comparación en CLAUDE.md §8."""
    motor: str = "piper"
    modelo: str = "voces/es_AR-daniela-high.onnx"
    volumen_original: float = 0.15   # el audio del video queda de fondo, abajo de la voz
    # Ajustes de Piper (los default son los del .onnx.json de daniela). length_scale < 1 = más
    # rápido; noise_scale = variación del audio; noise_w_scale = variación de la duración de
    # los fonemas (el ritmo). `semitonos` sube el tono DESPUÉS de sintetizar (rubberband de ffmpeg:
    # cambia el tono sin cambiar la velocidad).
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w_scale: float = 0.8
    semitonos: float = 0.0


@dataclass(frozen=True)
class PantallaCfg:
    """OCR sobre frames muestreados: datos personales o pantallas de pago (§ pantalla.py)."""
    activo: bool = True
    frames_muestra: int = 8
    idioma: str = "spa+eng"   # si `spa` no está instalado, tesseract falla y la capa se saltea
    buscar_telefonos: bool = True
    palabras_pago: tuple[str, ...] = ()
    # Un teléfono o una tarjeta solo cuentan si en el mismo frame hay una de estas palabras.
    palabras_contexto: tuple[str, ...] = ()
    palabras_direccion: tuple[str, ...] = ()


@dataclass(frozen=True)
class Textos:
    modelo: str = "gemini-3.6-flash"
    modelo_fallback: str = "gemini-3.5-flash-lite"  # cuando se acaba la cuota diaria del principal
    max_titulo: int = 59
    min_hashtags: int = 3
    max_hashtags: int = 5
    max_descripcion: int = 800
    reintentos: int = 2
    # Gemini caído (503 y cía., ya con sus reintentos y el otro modelo): la efeméride y los clips
    # que faltan de la entrega diaria se reintentan solos en este rato, hasta esta hora (AR).
    reintento_pasajero_min: int = 60
    reintento_hasta: str = "22:00"
    # Calidad: puntaje de 1 a 10 (se entiende solo + tiene remate). Abajo del corte el clip no se
    # tira: queda como RELLENO, y solo se usa si la corrida no llega a 3 sin él.
    puntaje_min: int = 6     # 5 → 6 el 2026-09-29 (pedido de Santi: llegaban clips malos)
    # Ejemplos del gusto de Santi en la llamada del puntaje: los últimos N 👍 y N 👎. 0 = sin.
    ejemplos_gusto: int = 0
    frames_para_puntaje: int = 4   # 0 = puntuar solo con la transcripción


@dataclass(frozen=True)
class EfemeridesCfg:
    """Pequeña Historia (§3c). La música sale de `carpeta_musica`, una al azar por video; vacía = sin música."""
    diaria: bool = True               # proponer la efeméride en la corrida de las 05:00
    chat: str = ""                    # a quién mandar la propuesta diaria (ids con coma); vacío = /destinos
    hora_publicacion: str = "12:00"    # AR: a qué hora se publica sola (con la subida prendida)
    # Si la de las 05:00 no sale, la escucha de Telegram reintenta a estas horas (AR) y recién
    # después del último avisa que no hay propuesta.
    reintentos: tuple = ("07:00", "10:00")
    musica: bool = True
    # 2 o 3 frases de acción con video libre (videos_libres.py). Apagado hasta que Santi vea la muestra.
    videos: bool = False
    parallax: bool = True       # fotos con parallax 3D (parallax.py) en vez del zoom
    graficos: bool = True       # año contando, mapa, palabras clave grandes y whoosh (graficos.py)
    carpeta_musica: str = "musica"
    musica_volumen: float = 0.12
    musica_por_fuente: int = 10      # temas que se bajan solos de Kevin MacLeod y de Openverse
    # Voz (decisión 2026-09-28: la muestra C). gemini = Gemini TTS; si falla o no hay cuota, Piper
    # con los ajustes piper_* (la muestra A). piper = directo Piper.
    voz_motor: str = "gemini"
    tts_modelo: str = "gemini-3.8-flash-tts"
    tts_voz: str = "Laomedeia"
    # VACÍA a propósito. Probado en la Pi el 2026-09-28 con gemini-3.8-flash-tts: la instrucción
    # de tono se LEE en voz alta, sea larga ("Leé esto en español rioplatense…": 10 s leídos antes
    # del guion), en inglés ("Say enthusiastically, …": la tradujo y la leyó) o corta ("Say
    # cheerfully:"); y como systemInstruction da 400 ("Developer instruction is not enabled for
    # this model"). El entusiasmo sale de la voz (Laomedeia) y del guion (¿? y ¡!).
    tts_instruccion: str = ""
    # Gemini lee a ~2,3 palabras/s (medido sin la instrucción leída). Si se pasa de esto, se
    # acelera con atempo hasta tts_acelerar_max (más que 1,25 ya se nota).
    tts_max_s: float = 45.0
    tts_acelerar_max: float = 1.25
    piper_length_scale: float = 0.88
    piper_noise_scale: float = 0.8
    piper_noise_w_scale: float = 1.0
    piper_semitonos: float = 1.5


@dataclass(frozen=True)
class Pego:
    """Lo que pega en otros canales → el clip original (pego.py)."""
    activo: bool = True
    busquedas_por_dia: int = 40       # la API cuesta 100 unidades por búsqueda (de 10.000 diarias)
    dias: int = 7                     # Shorts de la última semana
    dias_antes: int = 3               # originales: de 3 días antes de publicado el Short a 12 h después
    min_vistas: int = 10000           # "pegó"
    por_streamer: int = 5             # Shorts NUEVOS que se comparan por streamer y búsqueda
    max_originales: int = 60          # clips del streamer que se comparan por Short (huella en caché)
    umbral: float = 0.55              # audio_huella: calibrado con clips reales (ver pego.py)
    peso: float = 3.0                 # bonus en la selección para un original que pegó
    canales_propios: tuple = ("Rots", "Pequeña Historia")
    # Corre APARTE de la corrida diaria (2026-09-30: dentro de ella tardó 90 min y systemd la mató
    # sin entregar nada): en la escucha, a esta hora, con este tope TOTAL. La de las 05:00 solo usa
    # lo que ya encontró.
    hora: str = "02:00"
    tope_min: int = 15


@dataclass(frozen=True)
class EnVivo:
    """Modo /envivo: detectar un momento mientras el stream sigue al aire (§3 modo en vivo)."""
    intervalo_twitch_s: int = 300     # /streams va en lote: una llamada para todos los de Twitch
    intervalo_kick_s: int = 120       # Kick no tiene lote: una llamada por canal, con kick.pausa_s
    ventana_min: int = 15             # se alertan los momentos de los últimos N minutos
    ventana_base_min: int = 60        # y el ritmo normal del canal se mide sobre la última hora
    min_creadores: int = 4            # creadores DISTINTOS: nunca menos que esto
    factor_base: float = 15.0         # ...y al menos factor × el ritmo normal del canal
    ventana_vod_s: int = 60           # Twitch con vod_offset: mismo VOD a ±N s
    ventana_real_s: int = 90          # Kick, y Twitch sin vod_offset: hora de creación a ±N s
    alertas_por_hora: int = 3         # pendientes + procesando + entregadas en los últimos 60 min
    vencimiento_min: int = 60         # una alerta que esperó turno más que esto ya no es "YA"
    max_paginas_kick: int = 5         # páginas de 20 clips por canal y por vuelta


FUENTES = ("reciente", "catalogo")


@dataclass(frozen=True)
class Seleccion:
    mezcla: dict = field(default_factory=lambda: {"kick_reciente": 1, "evento": 1, "catalogo": 1})
    peso_momento: float = 0.5
    max_por_streamer: int = 1
    empate_pct: dict = field(default_factory=lambda: {"reciente": 0.03, "catalogo": 0.10})
    # Peso por votos 👍/👎 de `votos_de` a los clips de cada streamer (ver settings.yaml).
    peso_votos: float = 0.5
    votos_previa: int = 3
    votos_de: tuple = ()
    # Métricas del canal (§4b, metricas.py): peso por streamer y por tipo de clip (duración, layout,
    # cámara) según la mediana de vistas de lo ya subido. Solo grupos con n ≥ metricas_min_n.
    peso_metricas: float = 0.5
    metricas_min_n: int = 15
    # Picos de chat (chat.py, solo Twitch con VOD): × (1 + peso × log2(pico)/2), pico ×4 = todo el
    # peso. 0 = no se mide (cada clip son ~3 pedidos al chat de Twitch).
    peso_chat: float = 0.0

    @property
    def n(self) -> int:
        return sum(self.mezcla.values())


@dataclass(frozen=True)
class Publicacion:
    horarios: tuple[str, ...] = ("13:00", "18:00", "21:30")


@dataclass(frozen=True)
class Settings:
    filtros: Filtros
    evento: Evento = Evento()
    kick: Kick = Kick()
    catalogo: Catalogo = Catalogo()
    render: Render = Render()
    camara: Camara = Camara()
    subtitulos: Subtitulos = Subtitulos()
    filtro_audio: FiltroAudio = FiltroAudio()
    marcador: MarcadorDeportivo = MarcadorDeportivo()
    pantalla: PantallaCfg = PantallaCfg()
    voz: Voz = Voz()
    multipov: MultiPov = MultiPov()
    textos: Textos = Textos()
    seleccion: Seleccion = Seleccion()
    publicacion: Publicacion = Publicacion()
    envivo: EnVivo = EnVivo()
    pego: Pego = Pego()
    efemerides: EfemeridesCfg = EfemeridesCfg()
    youtube_upload_enabled: bool = False


@dataclass(frozen=True)
class TwitchCreds:
    client_id: str
    client_secret: str


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"No existe {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _seccion(cls, raw: dict, nombre: str, path: Path):
    datos = dict(raw.get(nombre) or {})
    try:
        return cls(**datos)
    except TypeError as e:
        raise ConfigError(f"Clave desconocida en {path} → {nombre}: {e}") from e


def load_settings(path: Path = CONFIG_DIR / "settings.yaml") -> Settings:
    raw = _read_yaml(path)
    for seccion, clave in [
        ("evento", "categorias"),
        ("evento", "palabras"),
        ("candidatos", "categorias_excluidas"),
        ("candidatos", "palabras_costream"),
        ("candidatos", "palabras_deportes"),
        ("candidatos", "categorias_costream"),
        ("publicacion", "horarios"),
    ]:
        if clave in (raw.get(seccion) or {}):
            raw[seccion][clave] = tuple(str(x) for x in raw[seccion][clave] or ())
    filtros = _seccion(Filtros, raw, "candidatos", path)
    if filtros.duracion_min_s >= filtros.duracion_max_s:
        raise ConfigError("duracion_min_s tiene que ser menor que duracion_max_s")
    seleccion = _seccion(Seleccion, raw, "seleccion", path)
    mezcla = {str(k): v for k, v in (seleccion.mezcla or {}).items()}
    if not mezcla or not all(isinstance(v, int) and v >= 0 for v in mezcla.values()):
        raise ConfigError(f"seleccion.mezcla: cupos enteros ≥ 0 por grupo, no {mezcla}")
    pct = {str(k): float(v) for k, v in (seleccion.empate_pct or {}).items()}
    if set(pct) - set(FUENTES) or not all(0 <= v < 1 for v in pct.values()):
        raise ConfigError(f"seleccion.empate_pct: fuentes válidas {FUENTES} con valores entre 0 y 1, no {pct}")
    seleccion = Seleccion(**{**seleccion.__dict__, "mezcla": mezcla,
                             "empate_pct": {f: pct.get(f, 0.0) for f in FUENTES},
                             "votos_de": tuple(str(u) for u in seleccion.votos_de or ())})
    catalogo = _seccion(Catalogo, raw, "catalogo", path)
    if catalogo.antiguedad_min_dias >= catalogo.antiguedad_max_dias:
        raise ConfigError("catalogo.antiguedad_min_dias tiene que ser menor que antiguedad_max_dias")
    return Settings(
        filtros=filtros,
        evento=_seccion(Evento, raw, "evento", path),
        kick=_seccion(Kick, raw, "kick", path),
        catalogo=catalogo,
        render=_seccion(Render, raw, "render", path),
        camara=_seccion(Camara, raw, "camara", path),
        subtitulos=_seccion(Subtitulos, raw, "subtitulos", path),
        filtro_audio=_seccion(FiltroAudio, raw, "filtro_audio", path),
        marcador=_seccion(MarcadorDeportivo, raw, "marcador", path),
        pantalla=_seccion(PantallaCfg, raw, "pantalla", path),
        voz=_seccion(Voz, raw, "voz", path),
        multipov=_seccion(MultiPov, raw, "multipov", path),
        textos=_seccion(Textos, raw, "textos", path),
        seleccion=seleccion,
        publicacion=_seccion(Publicacion, raw, "publicacion", path),
        envivo=_seccion(EnVivo, raw, "envivo", path),
        efemerides=_seccion(EfemeridesCfg, raw, "efemerides", path),
        pego=_seccion(Pego, raw, "pego", path),
        youtube_upload_enabled=bool(raw.get("youtube_upload_enabled", False)),
    )


LAYOUTS = ("split", "fullcam", "fit_blur")


def _layout_forzado(item: dict, login: str) -> str:
    valor = str(item.get("layout_forzado") or "").strip().lower()
    if valor and valor not in LAYOUTS:
        raise ConfigError(f"{login}: layout_forzado {valor!r} (válidos: {LAYOUTS})")
    return valor


def load_streamers(path: Path = CONFIG_DIR / "streamers.yaml") -> list[Streamer]:
    """Lee `streamers` y las secciones `evento_*` (esas van al grupo "evento" por default)."""
    raw = _read_yaml(path)
    out: list[Streamer] = []
    vistos: set[str] = set()
    secciones = [("streamers", "")] + [(k, "evento") for k in raw if str(k).startswith("evento")]
    for seccion, grupo_default in secciones:
        for item in raw.get(seccion) or []:
            login = str(item.get("login", "")).strip().lower()
            if not login:
                raise ConfigError(f"Streamer sin login en {path} → {seccion}")
            if login in vistos:
                raise ConfigError(f"Streamer duplicado en {path}: {login}")
            vistos.add(login)
            plataforma = str(item.get("plataforma") or "twitch").strip().lower()
            if plataforma not in PLATAFORMAS:
                raise ConfigError(f"{login}: plataforma {plataforma!r} (válidas: {PLATAFORMAS})")
            fuentes = tuple(str(f).strip().lower() for f in (item.get("fuentes") or ["reciente"]))
            if set(fuentes) - set(FUENTES):
                raise ConfigError(f"{login}: fuentes {fuentes} (válidas: {FUENTES})")
            permiso = item.get("permiso") or {}
            out.append(
                Streamer(
                    login=login,
                    plataforma=plataforma,
                    fuentes=fuentes,
                    grupo=str(item.get("grupo") or grupo_default),
                    cita=str(permiso.get("cita") or ""),
                    fuente=str(permiso.get("fuente") or ""),
                    verificado=str(permiso.get("verificado") or ""),
                    experimento=bool(permiso.get("experimento", False)),
                    subtitulos_propios=bool(item.get("subtitulos_propios", False)),
                    detectar_marcador=bool(item.get("detectar_marcador", False)),
                    palabras_programa=tuple(
                        str(p).strip() for p in (item.get("palabras_programa") or ()) if str(p).strip()
                    ),
                    layout_forzado=_layout_forzado(item, login),
                    apodos=tuple(str(a).strip() for a in (item.get("apodos") or ()) if str(a).strip()),
                )
            )
    return out


def env(nombre: str, requerido: bool = True) -> str:
    load_dotenv(ROOT / ".env")
    valor = os.getenv(nombre, "").strip()
    if requerido and not valor:
        raise ConfigError(f"Falta {nombre} en .env (ver .env.example)")
    return valor


REPO_URL = "https://github.com/S-Fitti848/clips-bot"


def user_agent() -> str:
    """El User-Agent de todo lo que va a Wikipedia, Commons (upload.wikimedia.org) y a las fuentes
    de música. Formato de la política de Wikimedia: `nombre/versión (contacto) librería/versión`.
    El mail sale de WIKIMEDIA_CONTACTO en .env (no va al repo); sin él queda solo el link.
    Todo en ASCII: Openverse devuelve 403 si el User-Agent tiene una tilde (visto 2026-09-28)."""
    import requests

    mail = env("WIKIMEDIA_CONTACTO", requerido=False)
    contacto = "; ".join(x for x in (REPO_URL, mail) if x)
    return f"PequenaHistoriaBot/0.28 ({contacto}) python-requests/{requests.__version__}"


def load_twitch_creds() -> TwitchCreds:
    load_dotenv(ROOT / ".env")
    cid = os.getenv("TWITCH_CLIENT_ID", "").strip()
    secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise ConfigError("Faltan TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET en .env (ver .env.example)")
    return TwitchCreds(cid, secret)
