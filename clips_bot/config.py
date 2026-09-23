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
    margen_s: float = 4.0
    max_angulos: int = 3
    min_angulos: int = 3
    frames_muestra: int = 10
    frames_vacios_max: float = 0.34   # más de un tercio del tramo en negro → el ángulo no sirve
    luma_negro: float = 0.08          # un píxel por debajo de esto cuenta como negro
    pixeles_negros_min: float = 0.90  # y un frame es "vacío" con esta fracción de píxeles negros


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


FUENTES = ("reciente", "catalogo")


@dataclass(frozen=True)
class Seleccion:
    mezcla: dict = field(default_factory=lambda: {"kick_reciente": 1, "evento": 1, "catalogo": 1})
    peso_momento: float = 0.5
    max_por_streamer: int = 1
    empate_pct: dict = field(default_factory=lambda: {"reciente": 0.03, "catalogo": 0.10})

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
    multipov: MultiPov = MultiPov()
    textos: Textos = Textos()
    seleccion: Seleccion = Seleccion()
    publicacion: Publicacion = Publicacion()
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
                             "empate_pct": {f: pct.get(f, 0.0) for f in FUENTES}})
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
        multipov=_seccion(MultiPov, raw, "multipov", path),
        textos=_seccion(Textos, raw, "textos", path),
        seleccion=seleccion,
        publicacion=_seccion(Publicacion, raw, "publicacion", path),
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
                )
            )
    return out


def env(nombre: str, requerido: bool = True) -> str:
    load_dotenv(ROOT / ".env")
    valor = os.getenv(nombre, "").strip()
    if requerido and not valor:
        raise ConfigError(f"Falta {nombre} en .env (ver .env.example)")
    return valor


def load_twitch_creds() -> TwitchCreds:
    load_dotenv(ROOT / ".env")
    cid = os.getenv("TWITCH_CLIENT_ID", "").strip()
    secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise ConfigError("Faltan TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET en .env (ver .env.example)")
    return TwitchCreds(cid, secret)
