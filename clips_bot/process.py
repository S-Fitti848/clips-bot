"""Pasos 3–7 del pipeline para un clip:
descargar → co-stream → filtros de audio → transcripción → textos (Gemini, descarta si depende de la
fecha) → layout → render.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import db
from . import layout as lay
from . import subtitles as sub
from . import textos as tx
from . import deportes
from . import pantalla as pant
from .candidates import MOTIVO_COSTREAM, aviso_futbol, es_costream
from .config import DB_PATH, OUTPUT_DIR, Settings, Streamer
from .download import descargar
from .gemini import GeminiClient, GeminiError
from .media import fraccion_silencio, frames_jpeg, probe
from .render import renderizar

log = logging.getLogger(__name__)

RAW_DIR = OUTPUT_DIR / "raw"
READY_DIR = OUTPUT_DIR / "ready"
WORK_DIR = OUTPUT_DIR / "work"
DEBUG_DIR = OUTPUT_DIR / "debug"


@dataclass
class Resultado:
    clip_id: str = ""
    streamer: str = ""
    canal: str = ""
    url: str = ""
    titulo_twitch: str = ""
    categoria: str = ""
    vistas: int = 0
    creado: str | None = None  # ISO UTC
    fuente: str = "reciente"  # reciente | catalogo
    grupo: str = ""  # cupo en el que compite (seleccion.mezcla)
    plataforma: str = "twitch"
    clips_mismo_momento: int = 1
    mediana_vistas: int = 0  # del streamer en la ventana: para el "por qué" del mensaje
    aviso: str = ""  # algo para mirar sin descartar (ej. habla de fútbol): sale en el mensaje
    marcador_deportivo: dict | None = None
    pantalla: dict | None = None  # OCR: datos personales / pantalla de pago
    duracion_s: float = 0.0
    silencio: float = 0.0
    palabras: int = 0
    palabras_por_s: float = 0.0
    transcripcion: str = ""
    layout: str = ""
    layout_forzado: str = ""  # el de streamers.yaml, si el streamer lo tiene fijado
    presencia_cara: float = 0.0
    rerender_fit_blur: str = ""  # motivo, si el chequeo post-render detectó una cara cortada
    subtitulos_quemados: bool = True
    textos: dict | None = None
    textos_pendientes: bool = False  # el render está hecho; `seleccionar` reintenta los textos
    puntaje: int = 0        # 1 a 10 de Gemini: se entiende solo + tiene remate
    relleno: bool = False   # no llegó al corte de calidad: solo se usa si falta para llenar el día
    descartado: str | None = None
    salida: str | None = None
    raw: str | None = None  # el mp4 original, para re-renderizar (/narrar)
    tiempos: dict[str, float] = field(default_factory=dict)


class Cronometro:
    def __init__(self, res: Resultado, avisar):
        self.res = res
        self.avisar = avisar

    @contextmanager
    def etapa(self, nombre: str):
        self.avisar(f"→ {nombre}…")
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self.res.tiempos[nombre] = round(dt, 2)
            self.avisar(f"  {nombre}: {dt:.1f} s")


def fuente_por_antiguedad(creado: datetime | None, cfg: Settings, ahora: datetime | None = None) -> str:
    """Para URLs pegadas a mano: catálogo si el clip tiene al menos antiguedad_min_dias."""
    if creado is None:
        return "reciente"
    ahora = ahora or datetime.now(timezone.utc)
    return "catalogo" if (ahora - creado).days >= cfg.catalogo.antiguedad_min_dias else "reciente"


def procesar(url: str, cfg: Settings, streamers: list[Streamer], forzar: bool = False,
             gemini: GeminiClient | None = None, avisar=print, *, fuente: str | None = None,
             clips_mismo_momento: int = 1, grupo: str | None = None,
             descarga=None, permitir_fecha: bool = False, mediana_vistas: int = 0,
             aviso: str = "") -> Resultado:
    """fuente/clips_mismo_momento vienen de `candidatos` en la corrida diaria; por URL manual la
    fuente se deduce de la antigüedad y el momento queda en 1 (sin VOD no se puede agrupar).

    `descarga`: un video que ya está bajado (los modos /editar y /narrar). Esos no son clips de un
    streamer, así que se saltean los filtros que son POR CANAL — co-stream, palabras de fútbol,
    marcador deportivo — que sin streamer no significan nada y solo tirarían videos buenos. Los
    filtros de seguridad (datos en pantalla, tono) y los de calidad corren igual.

    `permitir_fecha`: el modo en vivo. `depende_de_fecha` existe para no publicar mañana algo que
    solo tenía sentido hoy; un clip que se sube en el momento es justo lo contrario. No es un filtro
    de seguridad ni de tono, así que ahí se anota y no se descarta.
    """
    res = Resultado(url=url, clips_mismo_momento=clips_mismo_momento, mediana_vistas=mediana_vistas,
                    aviso=aviso)
    crono = Cronometro(res, avisar)
    fa = cfg.filtro_audio
    aporte = descarga is not None

    if aporte:
        d = descarga
    else:
        with crono.etapa("descarga"):
            d = descargar(url, RAW_DIR)
    res.clip_id, res.streamer, res.canal, res.titulo_twitch = d.clip_id, d.streamer, d.canal, d.titulo
    res.categoria, res.vistas = d.categoria, d.vistas
    res.creado = d.creado.isoformat() if d.creado else None
    res.fuente = fuente or fuente_por_antiguedad(d.creado, cfg)
    res.plataforma = d.plataforma
    info = probe(d.path)
    res.duracion_s = round(info.duracion, 2)
    avisar(f"  {d.canal} · {d.titulo!r} · [{d.categoria or '?'}] · {d.vistas} vistas · "
           f"{info.ancho}x{info.alto} · {info.duracion:.1f} s · fuente {res.fuente}")

    streamer = next((s for s in streamers if s.login == d.streamer), None)
    res.subtitulos_quemados = not (streamer and streamer.subtitulos_propios)
    res.grupo = grupo or (streamer.grupo_de(res.fuente) if streamer else res.fuente)

    def descartar(motivo: str, registro: str) -> bool:
        """True si hay que cortar acá. Con --forzar se avisa y se sigue (y no se marca en la DB)."""
        avisar(f"  ⚠ {motivo}" + (" (sigo por --forzar)" if forzar else ""))
        if forzar:
            return False
        res.descartado = motivo
        _registrar(res, "descartado", registro)
        return True

    # §3 paso 2 (versión URL manual): co-stream / evento por título o categoría.
    # No corre para un aporte: sin streamer, "co-stream" no quiere decir nada.
    if not aporte and es_costream([d.titulo], d.categoria, cfg.filtros) and descartar(
        f"co-stream o evento (título {d.titulo!r}, categoría {d.categoria!r})", MOTIVO_COSTREAM
    ):
        return _cerrar(res)

    # Marcador de transmisión deportiva (solo para los streamers marcados). Va antes de Whisper:
    # es lo más barato de descartar. Hablar de fútbol NO descarta (2026-09-29): es solo un aviso
    # (por URL manual o en vivo, sale del título del clip); lo que descarta es VER el partido.
    if streamer and streamer.detectar_marcador:
        res.aviso = res.aviso or aviso_futbol([d.titulo], cfg.filtros)
        m = cfg.marcador
        with crono.etapa("transmisión deportiva"):
            deporte = deportes.detectar_deporte(d.path, m.frames_muestra, m.quietud_min, m.bordes_min,
                                                m.cesped_min, m.cesped_frames_min)
        res.marcador_deportivo = deporte.a_dict()  # se guarda SIEMPRE, dispare o no: sirve para calibrar
        avisar(f"  deporte: césped máx {deporte.cesped_max:.0%} en {deporte.frames_con_cesped} frames, "
               f"marcador {'sí' if deporte.marcador.hay else 'no'}")
        if deporte.hay and descartar(f"transmisión deportiva: {deporte.motivo}", "transmisión deportiva"):
            return _cerrar(res)

    # Datos personales en pantalla (OCR). Va antes de Whisper: es más barato (3-9 s) y es un
    # descarte duro. Se guarda SIEMPRE, dispare o no, igual que el marcador deportivo.
    with crono.etapa("datos en pantalla"):
        vista = pant.detectar_datos(d.path, cfg.pantalla)
    res.pantalla = vista.a_dict()
    if vista.salteado:
        avisar(f"  ⚠ OCR salteado: {vista.salteado}")
    else:
        avisar(f"  pantalla: {vista.caracteres} caracteres leídos en {vista.frames_leidos} frames, "
               f"{len(vista.hallazgos)} hallazgo(s)")
    if vista.hay and descartar(vista.motivo, pant.MOTIVO):
        return _cerrar(res)

    # §3 paso 4: capas baratas del filtro de audio. (Capa librosa de §4: pendiente.)
    with crono.etapa("silencio"):
        res.silencio = round(
            fraccion_silencio(d.path, info.duracion, fa.silencio_db, fa.silencio_min_s) if info.tiene_audio else 1.0, 3
        )
    # Silencio y pocas palabras son filtros de CLIPS DE STREAMERS (un clip sin habla es gameplay
    # puro o música del stream). Un video propio de /editar o /narrar suele ser un proceso sin
    # nadie hablando, justo lo que se quiere narrar (decisión 2026-09-27): se miden y se guardan,
    # pero no descartan. La música de esos videos se avisa en /narrar y se resuelve con `sin audio`.
    if (not aporte and res.silencio > fa.max_silencio
            and descartar(f"casi todo silencio ({res.silencio:.0%})", "silencio")):
        return _cerrar(res)

    if not info.tiene_audio:
        # Sin pista de audio (no silencioso: SIN stream) faster-whisper revienta adentro de PyAV
        # con IndexError (probado 2026-09-27 con un mp4 sin audio de verdad). No hay nada que
        # transcribir: el video sigue sin palabras, y en /narrar queda solo la voz.
        avisar("  sin pista de audio: no hay nada que transcribir")
        palabras = []
    else:
        palabras = _transcribir(res, d, info, cfg, crono, descartar, aporte, avisar)
        if palabras is None:
            return _cerrar(res)
    res.palabras = len(palabras)
    res.palabras_por_s = round(len(palabras) / info.duracion, 2) if info.duracion else 0.0
    res.transcripcion = " ".join(p.texto for p in palabras)
    avisar(f"  {res.palabras} palabras ({res.palabras_por_s}/s)")
    if not aporte and res.palabras_por_s < fa.min_palabras_por_s and descartar(
        f"pocas palabras ({res.palabras_por_s}/s < {fa.min_palabras_por_s}): probable música o gameplay puro",
        "pocas palabras",
    ):
        return _cerrar(res)

    # §3 paso 7, antes del render: si el clip depende de la fecha se descarta sin gastar el render.
    # Si Gemini falla, se sigue: `seleccionar` genera los textos que falten (y ahí también descarta).
    if gemini:
        try:
            with crono.etapa("gemini: textos"):
                imgs = frames_jpeg(d.path, cfg.textos.frames_para_puntaje) \
                    if cfg.textos.frames_para_puntaje else None
                res.textos = generar_textos(gemini, cfg, asdict(res), imagenes=imgs).to_dict()
            avisar(f"  título: {res.textos['titulo']}")
        except (GeminiError, tx.TextosError) as e:
            avisar(f"  ⚠ textos: {e}")
            res.textos_pendientes = True
        if res.textos and res.textos["depende_de_fecha"] and permitir_fecha:
            avisar("  depende de la fecha, pero es para subir ya: sigue")
        elif res.textos and res.textos["depende_de_fecha"] and descartar(
            "depende de la fecha (referencia a algo puntual de ese día)", tx.MOTIVO_FECHA
        ):
            return _cerrar(res)
        # Tono: descarte duro, sin excepciones y sin relleno. Es el único filtro de contenido que
        # mira de QUÉ trata el clip; existe porque el 2026-09-24 casi se publica el memorial de una
        # mascota muerta con un emoji de risa en el título.
        if res.textos and res.textos.get("sensible") and descartar(
            "tono sensible (muerte, duelo, enfermedad, violencia real o salud mental)",
            tx.MOTIVO_SENSIBLE
        ):
            return _cerrar(res)
        # Calidad: NO es un descarte. El clip se renderiza igual y queda marcado como relleno, para
        # usarlo solo si la corrida no llega a 3 con los que sí pasaron.
        if res.textos:
            res.puntaje = int(res.textos.get("puntaje") or 0)
            res.relleno = 0 < res.puntaje < cfg.textos.puntaje_min
            if res.relleno:
                avisar(f"  puntaje {res.puntaje} < {cfg.textos.puntaje_min}: queda como RELLENO")
    else:
        res.textos_pendientes = True
        avisar("  (sin GEMINI_API_KEY: textos pendientes)")

    work = WORK_DIR / d.clip_id
    work.mkdir(parents=True, exist_ok=True)
    subs = sub.armar_subtitulos(palabras, cfg.subtitulos)
    sub.escribir_srt(subs, work / "subs.srt")  # siempre: sirve para el título y como pista en YouTube
    sub.escribir_ass(subs, work / "subs.ass", cfg.subtitulos, cfg.render)
    if not res.subtitulos_quemados:
        avisar(f"  {d.streamer} tiene subtitulos_propios: no se queman los nuestros (el .srt se guarda igual)")

    forzado = streamer.layout_forzado if streamer else ""
    with crono.etapa("detectar cámara"):
        W, H, frames, imagenes = lay.detectar_caras(d.path, cfg.camara.frames_muestra)
        layout = lay.decidir_layout(W, H, frames, cfg.camara, cfg.render, forzado=forzado)
        if imagenes:
            lay.guardar_debug(imagenes[len(imagenes) // 2], layout, DEBUG_DIR / f"{d.clip_id}_layout.jpg")
    res.layout, res.presencia_cara = layout.tipo, round(layout.presencia, 2)
    res.layout_forzado = forzado
    avisar(f"  layout {layout.tipo}" + (f" (forzado en streamers.yaml)" if forzado else "")
           + f" (cara estable en {layout.presencia:.0%} de los frames)")

    quemar = bool(subs) and res.subtitulos_quemados
    salida = READY_DIR / f"{d.clip_id}.mp4"
    with crono.etapa("render 9:16" + (" + subtítulos" if quemar else "")):
        renderizar(d.path, salida, layout, cfg.render, work if quemar else None)

    # Chequeo post-render: si el recorte partió una cara, se rehace con fit_blur (que no recorta).
    # Atrapa lo que la decisión previa no vio, ej. la persona que se corre a un costado a mitad del clip.
    # Con layout_forzado no se toca: si alguien pidió ese layout a mano, se respeta.
    if layout.tipo != "fit_blur" and not forzado:
        with crono.etapa("chequeo de caras cortadas"):
            cortada, detalle = lay.cara_cortada_en_render(salida)
        if cortada:
            avisar(f"  ⚠ {detalle} → re-render con fit_blur")
            res.rerender_fit_blur = detalle
            layout = lay.layout_fit_blur(W, H, cfg.render, layout.presencia, layout.cara)
            res.layout = layout.tipo
            with crono.etapa("re-render fit_blur"):
                renderizar(d.path, salida, layout, cfg.render, work if quemar else None)

    shutil.copyfile(work / "subs.srt", READY_DIR / f"{d.clip_id}.srt")
    res.salida = str(salida)
    res.raw = str(d.path)

    _registrar(res, "procesado", tx.MOTIVO_SIN_REMATE if res.relleno else None)
    return _cerrar(res)


def _transcribir(res: Resultado, d, info, cfg: Settings, crono: Cronometro, descartar, aporte: bool,
                 avisar) -> list | None:
    """Whisper con su tope de tiempo. None = el clip quedó descartado (el que llama corta ahí)."""
    with crono.etapa("whisper: cargar modelo"):
        modelo = sub.cargar_modelo(cfg.subtitulos)
    try:
        with crono.etapa("whisper: transcribir"):
            return sub.transcribir(modelo, d.path, cfg.subtitulos, info.duracion)
    except sub.TranscripcionLenta as e:
        if aporte:
            # El tope de tiempo se respeta igual (cuida la Pi); solo que el video sigue sin
            # subtítulos del original en vez de tirarse.
            avisar(f"  ⚠ {e}: sigo sin subtítulos del audio original")
            return []
        # Con --forzar `descartar` devuelve False y el clip sigue sin palabras. (Antes había un
        # `del modelo` doble acá que en ese caso tiraba UnboundLocalError.)
        return None if descartar(str(e), "transcripcion_lenta") else []
    finally:
        del modelo


def generar_textos(gemini: GeminiClient, cfg: Settings, meta: dict,
                   imagenes: list[bytes] | None = None) -> tx.TextosClip:
    return tx.generar(
        gemini, cfg.textos, canal=meta["canal"] or meta["streamer"], login=meta["streamer"],
        categoria=meta["categoria"], titulo_twitch=meta["titulo_twitch"], duracion=meta["duracion_s"],
        transcripcion=meta["transcripcion"], fecha=(meta.get("creado") or "")[:10] or None,
        imagenes=imagenes,
    )


def _registrar(res: Resultado, estado: str, motivo: str | None) -> None:
    conn = db.connect(DB_PATH)
    try:
        db.registrar_clip(
            conn, res.clip_id, res.streamer, estado, motivo, title=res.titulo_twitch, game_name=res.categoria,
            duration_s=res.duracion_s, view_count=res.vistas, created_at=res.creado, url=res.url,
        )
    finally:
        conn.close()


def _cerrar(res: Resultado) -> Resultado:
    res.tiempos["total"] = round(sum(v for k, v in res.tiempos.items() if k != "total"), 2)
    if res.clip_id:
        # Solo lo publicable va a ready/; los descartes dejan su json en work/ para revisar.
        destino = READY_DIR / f"{res.clip_id}.json" if res.salida else WORK_DIR / res.clip_id / "resultado.json"
        guardar_meta(destino, asdict(res))
    return res


def guardar_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
