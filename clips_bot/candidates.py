"""Pasos 1–2 del pipeline: pedir clips a Twitch y filtrarlos a candidatos, de dos fuentes.

  reciente  clips de las últimas `ventana_horas` con al menos `antiguedad_min_h`, un clip por momento,
            por score = duplicados × log de vistas.
  catalogo  clips viejos (por vistas absolutas), avanzando con un cursor por streamer en la DB.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from . import db
from .config import Catalogo, Evento, Filtros, Kick, Seleccion, Streamer
from .kick import KickClient, KickError, a_clip
from .seleccion import score_reciente
from .twitch import TwitchClient, TwitchError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Clip:
    id: str
    url: str
    broadcaster_login: str
    broadcaster_name: str
    title: str
    view_count: int
    duration: float
    language: str
    created_at: datetime
    game_id: str
    game_name: str
    vod_offset: int | None
    video_id: str = ""
    stream_title: str = ""
    fuente: str = "reciente"
    # Creadores DISTINTOS que clipearon el mismo momento (este incluido). Si el mismo usuario
    # clipeó tres veces la misma muerte, cuenta 1: la señal es cuánta gente lo consideró clipeable.
    clips_mismo_momento: int = 1
    plataforma: str = "twitch"
    grupo: str = ""  # cupo en el que compite (seleccion.mezcla)
    creator_id: str = ""  # quién hizo el clip (no el streamer)
    creadores: tuple[str, ...] = ()  # creadores DISTINTOS del mismo momento

    @classmethod
    def from_helix(cls, d: dict, login: str, game_name: str = "", stream_title: str = "",
                   fuente: str = "reciente", plataforma: str = "twitch", grupo: str = "") -> "Clip":
        return cls(
            id=d["id"],
            url=d["url"],
            broadcaster_login=login,
            broadcaster_name=d.get("broadcaster_name") or login,
            title=d.get("title") or "",
            view_count=int(d.get("view_count") or 0),
            duration=float(d.get("duration") or 0),
            language=(d.get("language") or "").lower(),
            created_at=datetime.fromisoformat(d["created_at"].replace("Z", "+00:00")),
            game_id=d.get("game_id") or "",
            game_name=game_name,
            vod_offset=d.get("vod_offset"),
            creator_id=str(d.get("creator_id") or d.get("creator_name") or ""),
            video_id=d.get("video_id") or "",
            stream_title=stream_title,
            fuente=fuente,
            plataforma=plataforma,
            grupo=grupo,
        )


MOTIVO_COSTREAM = "costream"
MOTIVO_PROGRAMA = "programa_terceros"
MOTIVO_SIN_PALABRAS = "sin las palabras buscadas"
MOTIVO_FUERA_EVENTO = "fuera del evento (categoría, título o fecha)"
MOTIVO_MUY_NUEVO = "muy nuevo (no llegó a antiguedad_min_h; se reevalúa mañana)"


def _normalizar(texto: str) -> str:
    """minúsculas, sin tildes, todo lo que no es letra/número → espacio. 'Co-Stream' → 'co stream'."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " " + re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip() + " "


def es_costream(textos: list[str], categoria: str, filtros: Filtros, con_deportes: bool = False) -> bool:
    """Co-stream o evento: palabra de la lista (completa) en algún título, o categoría de eventos.

    `con_deportes` suma las palabras de fútbol, y va SOLO para los streamers con detectar_marcador:
    aplicadas a todos, "final" y "partido" tiran clips de juego sanos (medido 2026-09-22).
    """
    if categoria.strip().lower() in {c.lower() for c in filtros.categorias_costream}:
        return True
    normalizados = [_normalizar(t) for t in textos if t]
    palabras = filtros.palabras_costream + (filtros.palabras_deportes if con_deportes else ())
    for palabra in palabras:
        p = _normalizar(palabra)
        if p.strip() and any(p in t for t in normalizados):
            return True
    return False


def tiene_palabras(clip: Clip, palabras: tuple[str, ...]) -> bool:
    """Alguna de las palabras aparece en el título del clip o en el del stream (palabra completa,
    sin tildes ni mayúsculas). Sin palabras pedidas, pasan todos."""
    if not palabras:
        return True
    texto = _normalizar(clip.title) + _normalizar(clip.stream_title)
    return any(_normalizar(p) in texto for p in palabras if p.strip())


def es_programa_de_terceros(stream_title: str, palabras: tuple[str, ...]) -> bool:
    """Marca de un programa con formato propio en el TÍTULO DEL STREAM.

    Mira solo el título del stream a propósito: el del clip casi nunca lo nombra (el clip de La Cobra
    del 2026-09-22 se llamaba "El peor golpe en vivo" y el stream era "412 con LA COBRA, DAVOOXENEIZE,
    AGUSNETA... PROGRAMA"). Con una marca, TODO ese stream queda afuera, aunque el momento clipeado
    no tenga nada del programa.
    """
    if not stream_title:
        return False
    normalizado = _normalizar(stream_title)
    return any(_normalizar(p) in normalizado for p in palabras if p.strip())


def es_del_evento(clip: Clip, cfg: Evento) -> bool:
    """Categoría del evento (ej. Minecraft) o palabra del evento en el título, dentro del período."""
    if cfg.desde and clip.created_at.date().isoformat() < cfg.desde:
        return False
    if cfg.hasta and clip.created_at.date().isoformat() > cfg.hasta:
        return False
    if clip.game_name.strip().lower() in {c.lower() for c in cfg.categorias}:
        return True
    texto = _normalizar(clip.title) + _normalizar(clip.stream_title)
    return any(_normalizar(p) in texto for p in cfg.palabras if p.strip())


def agrupar_evento(clips: list[Clip], ventana_s: float) -> list[list[Clip]]:
    """Agrupa clips de DISTINTOS streamers por hora real (±ventana): en un evento con decenas de
    canales, una muerte grande la clipea gente en varios canales casi al mismo tiempo."""
    grupos: list[list[Clip]] = []
    libres = sorted(clips, key=lambda c: c.view_count, reverse=True)
    while libres:
        ancla = libres.pop(0)
        cerca = [c for c in libres if abs((c.created_at - ancla.created_at).total_seconds()) <= ventana_s]
        grupos.append([ancla] + cerca)
        libres = [c for c in libres if c not in cerca]
    return grupos


def consolidar_evento(res: "Resultado", cfg: Evento, peso_momento: float,
                      n_candidatos: int = 8) -> "Resultado":
    """Sobre los candidatos del grupo "evento": junta los de la misma hora real entre streamers
    (sumando los creadores distintos) y recién ahí corta al top N.

    Importante: le llegan TODOS los clips del evento que pasaron los filtros, no los 8 mejores. Si
    se corta antes, con 52 canales es casi imposible que 3 de los 8 sean del mismo momento y el
    multi-POV no se dispara nunca (medido 2026-09-22: 15 momentos con 3+ canales en el día, y
    ninguno llegaba a consolidarse)."""
    evento = [c for c in res.candidatos if (c.grupo or "") == "evento"]
    resto = [c for c in res.candidatos if (c.grupo or "") != "evento"]
    if not evento:
        return res

    del_evento = []
    for c in evento:
        if es_del_evento(c, cfg):
            del_evento.append(c)
        else:
            res.descartes[MOTIVO_FUERA_EVENTO] += 1

    elegidos = []
    for grupo in agrupar_evento(del_evento, cfg.ventana_entre_streamers_s):
        # Unión de los creadores de cada clip del grupo: el mismo usuario en dos canales cuenta 1.
        creadores = tuple(sorted({x for c in grupo for x in (c.creadores or (c.creator_id or c.id,))}))
        elegidos.append(replace(grupo[0], clips_mismo_momento=len(creadores), creadores=creadores))
        res.descartes["mismo momento (entre streamers del evento)"] += len(grupo) - 1
        if len({c.broadcaster_login for c in grupo}) >= 3:
            # 3+ canales clipearon el mismo momento: da para un Short multi-POV (§ multipov)
            res.grupos_evento.append(grupo)

    def sc(c: Clip) -> float:
        return score_reciente(c.view_count, c.clips_mismo_momento, peso_momento)

    elegidos.sort(key=sc, reverse=True)
    res.descartes["fuera del top N"] += max(len(elegidos) - n_candidatos, 0)
    res.candidatos = sorted(resto + elegidos[:n_candidatos], key=sc, reverse=True)
    return res


def motivo_descarte(clip: Clip, filtros: Filtros, vistos: set[str], min_vistas: int | None = None,
                    ahora: datetime | None = None, con_deportes: bool = False,
                    palabras_programa: tuple[str, ...] = (),
                    palabras_titulo: tuple[str, ...] = ()) -> str | None:
    """Devuelve por qué se descarta el clip, o None si pasa. El orden importa solo para el reporte.

    MUY NUEVO no es definitivo: esos clips no se marcan en la DB, así que vuelven a entrar en la
    corrida siguiente, cuando ya juntaron vistas y duplicados."""
    if clip.id in vistos:
        return "ya visto"
    if ahora is not None and (ahora - clip.created_at).total_seconds() / 3600 < filtros.antiguedad_min_h:
        return MOTIVO_MUY_NUEVO
    if clip.duration < filtros.duracion_min_s:
        return "muy corto"
    if clip.duration > filtros.duracion_max_s:
        return "muy largo"
    if clip.language and clip.language != filtros.idioma.lower():  # Kick no informa idioma
        return f"idioma != {filtros.idioma}"
    # Las palabras pedidas a mano (/buscar) se filtran ACÁ, antes del corte al top N. Si se filtrara
    # después, los clips que no tienen las palabras se comerían los lugares (mismo bug que ya pasó
    # dos veces con el evento y con los candidatos de Kick).
    if not tiene_palabras(clip, palabras_titulo):
        return MOTIVO_SIN_PALABRAS
    if es_programa_de_terceros(clip.stream_title, palabras_programa):
        return MOTIVO_PROGRAMA
    if es_costream([clip.title, clip.stream_title], clip.game_name, filtros, con_deportes):
        return MOTIVO_COSTREAM
    excluidas = {c.lower() for c in filtros.categorias_excluidas}
    if clip.game_name.lower() in excluidas:
        return f"categoría excluida ({clip.game_name})"
    if clip.view_count < (filtros.min_vistas if min_vistas is None else min_vistas):
        return "pocas vistas"
    return None


def agrupar_momentos(clips: list[Clip], ventana_s: float) -> list[list[Clip]]:
    """Grupos de clips del mismo momento: mismo streamer, mismo VOD y vod_offset a ±ventana_s del más
    visto del grupo. Sin VOD o sin offset (VOD borrado) el clip queda solo. Cada grupo sale ordenado
    por vistas, de mayor a menor."""
    grupos: list[list[Clip]] = []
    libres = sorted(clips, key=lambda c: c.view_count, reverse=True)
    while libres:
        ancla = libres.pop(0)
        grupo = [ancla]
        if ancla.video_id and ancla.vod_offset is not None:
            mismos = [
                c for c in libres
                if c.broadcaster_login == ancla.broadcaster_login and c.video_id == ancla.video_id
                and c.vod_offset is not None and abs(c.vod_offset - ancla.vod_offset) <= ventana_s
            ]
            grupo += mismos
            libres = [c for c in libres if c not in mismos]
        grupos.append(grupo)
    return grupos


@dataclass
class Resultado:
    candidatos: list[Clip] = field(default_factory=list)  # fuente reciente
    descartes: Counter = field(default_factory=Counter)
    catalogo: list[Clip] = field(default_factory=list)
    descartes_catalogo: Counter = field(default_factory=Counter)
    total_por_streamer: dict[str, int] = field(default_factory=dict)
    no_encontrados: list[str] = field(default_factory=list)
    sin_permiso: list[str] = field(default_factory=list)
    excluidos: list[str] = field(default_factory=list)  # con reclamo de copyright
    grupos_evento: list[list[Clip]] = field(default_factory=list)  # mismo momento entre streamers (3+)
    fallos: list[str] = field(default_factory=list)  # ej. la API de Kick caída
    costream: list[Clip] = field(default_factory=list)  # se guardan en la DB como descartados


def habilitados(streamers: list[Streamer], plataforma: str, fuente: str, res: Resultado,
                incluir_sin_permiso: bool, excluidos: dict[str, str] | None = None) -> list[Streamer]:
    """Streamers de esa plataforma y fuente que pueden usarse: con permiso (cita o experimento) y
    sin exclusión por reclamo de copyright."""
    excluidos = excluidos or {}
    activos = []
    for s in streamers:
        if s.plataforma != plataforma or fuente not in s.fuentes:
            continue
        if s.login in excluidos:
            if s.login not in res.excluidos:
                res.excluidos.append(s.login)
            continue
        if s.permitido or incluir_sin_permiso:
            activos.append(s)
        if not s.permitido and s.login not in res.sin_permiso:
            res.sin_permiso.append(s.login)
    return activos


def _ids(client: TwitchClient, activos: list[Streamer], res: Resultado) -> dict[str, str]:
    """login → broadcaster_id de los que existen en Twitch."""
    if not activos:
        return {}
    ids = client.get_user_ids([s.login for s in activos])
    for s in activos:
        if s.login not in ids and s.login not in res.no_encontrados:
            res.no_encontrados.append(s.login)
            log.warning("Streamer %s no existe en Twitch", s.login)
    return {s.login: ids[s.login] for s in activos if s.login in ids}


def _motivo(clip: Clip, filtros: Filtros, vistos: set[str], ahora: datetime, evento: Evento,
            con_deportes: bool, palabras_programa: tuple[str, ...] = (),
            palabras_titulo: tuple[str, ...] = ()) -> str | None:
    """Motivo de descarte, con el filtro del evento incluido.

    Los clips del grupo "evento" que no son del evento se descartan ACÁ, antes del corte al top N:
    si no, los clips de otra cosa del mismo streamer se comen los lugares y el cupo del evento queda
    vacío aunque haya clips buenos del evento más abajo (visto en la simulación del 2026-09-22).
    """
    m = motivo_descarte(clip, filtros, vistos, ahora=ahora, con_deportes=con_deportes,
                        palabras_programa=palabras_programa, palabras_titulo=palabras_titulo)
    if m:
        return m
    if (clip.grupo or "") == "evento" and not es_del_evento(clip, evento):
        return MOTIVO_FUERA_EVENTO
    return None


def _mira_deportes(por_login: dict[str, Streamer], login: str) -> bool:
    s = por_login.get(login)
    return bool(s and s.detectar_marcador)


def _programa_de(por_login: dict[str, Streamer], login: str) -> tuple[str, ...]:
    s = por_login.get(login)
    return s.palabras_programa if s else ()


def _a_clips(client: TwitchClient, crudos: list[tuple[str, dict]], fuente: str,
             por_login: dict[str, Streamer]) -> list[Clip]:
    juegos = client.get_game_names(c.get("game_id", "") for _, c in crudos)
    titulos_stream = client.get_video_titles(c.get("video_id", "") for _, c in crudos)
    return [
        Clip.from_helix(d, login, juegos.get(d.get("game_id", ""), ""),
                        titulos_stream.get(d.get("video_id", ""), ""), fuente, "twitch",
                        por_login[login].grupo_de(fuente) if login in por_login else "")
        for login, d in crudos
    ]


def creadores_de(clips: list[Clip]) -> tuple[str, ...]:
    """Creadores distintos de un grupo de clips. Sin creator_id se usa el id del clip (cuenta como
    uno propio), así un dato faltante no infla ni desinfla el bonus."""
    return tuple(sorted({c.creator_id or f"clip:{c.id}" for c in clips}))


def _elegir_por_momento(todos: list[Clip], motivos: dict[str, str | None], filtros: Filtros,
                        res: Resultado, descartes: Counter) -> list[Clip]:
    """Un clip por momento: el más visto que pasó los filtros. El bonus cuenta a los CREADORES
    distintos del grupo (pasen o no sus clips): el mismo usuario clipeando tres veces cuenta 1."""
    pasan: list[Clip] = []
    for grupo in agrupar_momentos(todos, filtros.ventana_momento_s):
        ok = [c for c in grupo if not motivos[c.id]]
        if ok:
            creadores = creadores_de(grupo)
            pasan.append(replace(ok[0], clips_mismo_momento=len(creadores), creadores=creadores))
            descartes["mismo momento"] += len(ok) - 1
    return pasan


def buscar_kick(
    client: KickClient,
    streamers: list[Streamer],
    filtros: Filtros,
    vistos: set[str],
    cfg: Kick = Kick(),
    ahora: datetime | None = None,
    incluir_sin_permiso: bool = False,
    seleccion: Seleccion = Seleccion(),
    res: Resultado | None = None,
    excluidos: dict[str, str] | None = None,
    evento: Evento = Evento(),
    palabras_titulo: tuple[str, ...] = (),
) -> Resultado:
    """Fuente reciente de Kick. Si la API interna falla, se anota en res.fallos y la corrida sigue
    con lo de Twitch (no se corta nada)."""
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(hours=filtros.ventana_horas)
    res = res or Resultado()

    todos: list[Clip] = []
    deportes_de: dict[str, bool] = {}  # las palabras de fútbol son por streamer
    programa_de: dict[str, tuple[str, ...]] = {}  # y las marcas de programa también
    for s in habilitados(streamers, "kick", "reciente", res, incluir_sin_permiso, excluidos):
        try:
            crudos = client.get_clips(s.login, cfg.max_clips, cfg.orden, cfg.ventana)
        except KickError as e:
            log.warning("Kick: %s", e)
            res.fallos.append(f"kick/{s.login}: {e}")
            continue
        res.total_por_streamer[f"{s.login} (kick)"] = len(crudos)
        deportes_de[s.login] = s.detectar_marcador
        programa_de[s.login] = s.palabras_programa
        # El clip de Kick no trae el título del stream, solo livestream_id: se resuelve con
        # /videos del canal (una llamada por canal). Sin esto, los filtros que miran el título del
        # stream no existen en Kick.
        titulos = client.get_session_titles(s.login)
        for d in crudos:
            plano = a_clip(d, s.login)
            clip = Clip.from_helix(plano, s.login, plano["_game_name"],
                                   titulos.get(plano["video_id"], ""), "reciente", "kick",
                                   s.grupo_de("reciente"))
            if clip.created_at >= desde:  # la API no filtra por fecha: se hace acá
                todos.append(clip)
            else:
                res.descartes["fuera de la ventana"] += 1

    if not todos:
        return res
    motivos = {c.id: _motivo(c, filtros, vistos, ahora, evento,
                             deportes_de.get(c.broadcaster_login, False),
                             programa_de.get(c.broadcaster_login, ()), palabras_titulo)
               for c in todos}
    for c in todos:
        if motivos[c.id]:
            res.descartes[motivos[c.id]] += 1
            if motivos[c.id] == MOTIVO_COSTREAM:
                res.costream.append(c)

    pasan = _elegir_por_momento(todos, motivos, filtros, res, res.descartes)
    pasan.sort(key=lambda c: score_reciente(c.view_count, c.clips_mismo_momento, seleccion.peso_momento),
               reverse=True)
    nuevos = pasan[: filtros.n_candidatos]
    res.descartes["fuera del top N"] += len(pasan) - len(nuevos)
    res.candidatos = sorted(
        res.candidatos + nuevos,
        key=lambda c: score_reciente(c.view_count, c.clips_mismo_momento, seleccion.peso_momento),
        reverse=True,
    )
    return res


def buscar_candidatos(
    client: TwitchClient,
    streamers: list[Streamer],
    filtros: Filtros,
    vistos: set[str],
    ahora: datetime | None = None,
    incluir_sin_permiso: bool = False,
    seleccion: Seleccion = Seleccion(),
    res: Resultado | None = None,
    excluidos: dict[str, str] | None = None,
    evento: Evento = Evento(),
    palabras_titulo: tuple[str, ...] = (),
) -> Resultado:
    """Fuente reciente de Twitch: filtros → un clip por momento → score → top N."""
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(hours=filtros.ventana_horas)
    res = res or Resultado()

    activos = habilitados(streamers, "twitch", "reciente", res, incluir_sin_permiso, excluidos)
    por_login = {s.login: s for s in activos}
    crudos: list[tuple[str, dict]] = []
    for login, bid in _ids(client, activos, res).items():
        clips = client.get_clips(bid, desde, ahora, filtros.max_clips_por_streamer)
        res.total_por_streamer[login] = len(clips)
        crudos.extend((login, c) for c in clips)
    if not crudos:
        return res

    todos = _a_clips(client, crudos, "reciente", por_login)
    motivos = {c.id: _motivo(c, filtros, vistos, ahora, evento,
                             _mira_deportes(por_login, c.broadcaster_login),
                             _programa_de(por_login, c.broadcaster_login), palabras_titulo)
               for c in todos}
    for c in todos:
        m = motivos[c.id]
        if m:
            res.descartes[m] += 1
            if m == MOTIVO_COSTREAM:
                res.costream.append(c)

    pasan = _elegir_por_momento(todos, motivos, filtros, res, res.descartes)

    def sc(c: Clip) -> float:
        return score_reciente(c.view_count, c.clips_mismo_momento, seleccion.peso_momento)

    pasan.sort(key=sc, reverse=True)
    # Los del evento pasan enteros: los corta consolidar_evento, después de agrupar por momento.
    del_evento = [c for c in pasan if (c.grupo or "") == "evento"]
    otros = [c for c in pasan if (c.grupo or "") != "evento"]
    nuevos = del_evento + otros[: filtros.n_candidatos]
    res.descartes["fuera del top N"] += len(otros) - min(len(otros), filtros.n_candidatos)
    # Se SUMAN a los que ya haya (ej. los de Kick): cada plataforma aporta su top N y después
    # compiten por cupo en la selección. Pisar la lista dejaba a Kick afuera sin que se notara.
    res.candidatos = sorted(res.candidatos + nuevos, key=sc, reverse=True)
    return res


def _ventana_catalogo(ahora: datetime, cat: Catalogo) -> tuple[datetime, datetime]:
    return ahora - timedelta(days=cat.antiguedad_max_dias), ahora - timedelta(days=cat.antiguedad_min_dias)


def buscar_catalogo(
    client: TwitchClient,
    streamers: list[Streamer],
    filtros: Filtros,
    cat: Catalogo,
    conn: sqlite3.Connection,
    vistos: set[str],
    ahora: datetime | None = None,
    incluir_sin_permiso: bool = False,
    res: Resultado | None = None,
    guardar_cursor: bool = True,
    excluidos: dict[str, str] | None = None,
) -> Resultado:
    """Fuente catálogo. Por streamer: sigue desde el cursor guardado, pagina hasta juntar
    n_candidatos que pasen los filtros (o max_paginas) y guarda el cursor nuevo junto con su ventana.
    Al final, los mejores n_candidatos entre todos los streamers por vistas absolutas."""
    ahora = ahora or datetime.now(timezone.utc)
    res = res or Resultado()
    pasan: list[Clip] = []

    activos = habilitados(streamers, "twitch", "catalogo", res, incluir_sin_permiso, excluidos)
    por_login = {s.login: s for s in activos}
    for login, bid in _ids(client, activos, res).items():
        guardado = db.get_cursor(conn, login)
        if guardado:
            cursor, desde_s, hasta_s = guardado
            desde, hasta = datetime.fromisoformat(desde_s), datetime.fromisoformat(hasta_s)
        else:
            cursor = None
            desde, hasta = _ventana_catalogo(ahora, cat)

        propios: list[Clip] = []
        paginas = 0
        while paginas < cat.max_paginas:
            try:
                page, siguiente = client.get_clips_pagina(bid, desde, hasta, cat.por_pagina, cursor)
            except TwitchError as e:
                if not cursor:
                    raise
                # Cursor vencido o rechazado: ciclo nuevo con la ventana de hoy (no cuenta como página).
                log.warning("Cursor de catálogo de %s rechazado (%s); arranco ciclo nuevo", login, e)
                res.descartes_catalogo["cursor reiniciado"] += 1
                cursor = None
                desde, hasta = _ventana_catalogo(ahora, cat)
                continue
            paginas += 1
            for c in _a_clips(client, [(login, d) for d in page], "catalogo", por_login):
                m = motivo_descarte(c, filtros, vistos, min_vistas=cat.min_vistas,
                                    con_deportes=_mira_deportes(por_login, c.broadcaster_login),
                                    palabras_programa=_programa_de(por_login, c.broadcaster_login))
                if m:
                    res.descartes_catalogo[m] += 1
                    if m == MOTIVO_COSTREAM:
                        res.costream.append(c)
                else:
                    propios.append(c)
            cursor = siguiente
            if not cursor or len(propios) >= cat.n_candidatos:
                break

        # Solo se guarda si la corrida va a consumir estos clips: listar sin procesar no puede
        # quemar la página (si no, los mejores del ciclo se pierden hasta que el ciclo reinicie).
        if guardar_cursor:
            if cursor:
                db.set_cursor(conn, login, cursor, desde.isoformat(), hasta.isoformat())
            else:
                db.borrar_cursor(conn, login)  # ciclo agotado: la próxima arranca con ventana nueva
                res.descartes_catalogo["ciclo agotado"] += 1
        res.total_por_streamer[f"{login} (catálogo)"] = len(propios)
        pasan.extend(propios)

    pasan.sort(key=lambda c: c.view_count, reverse=True)
    res.catalogo = pasan[: cat.n_candidatos]
    res.descartes_catalogo["fuera del top N"] += len(pasan) - len(res.catalogo)
    return res
