"""Modo en vivo (/envivo on|off): encontrar un momento mientras el stream sigue al aire.

Cada vuelta:
  1. Quién está en vivo: Twitch en lote (/streams, cada `intervalo_twitch_s`); Kick canal por canal
     (/channels/{slug}, cada `intervalo_kick_s`, con la pausa de siempre entre llamadas).
  2. De los que están en vivo, los clips de los últimos `ventana_min` minutos.
  3. Momentos: clips del MISMO canal a ±`ventana_vod_s` de vod_offset (Twitch, si lo informa) o a
     ±`ventana_real_s` de hora de creación. Si `min_creadores` personas distintas clipearon el mismo
     momento, se anota una alerta y el mejor clip que pase los filtros se procesa al toque.

Lo que NO se hace acá: procesar ni mandar. Eso va en __main__ (turno pesado, Telegram), para que
esto se pueda probar sin red, sin video y sin bot.

Medido 2026-09-27 (ver settings.yaml → envivo): Twitch NO da vod_offset mientras el stream está al
aire, así que casi siempre se agrupa por hora de creación.
"""

from __future__ import annotations

import logging
import sqlite3
import statistics
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from . import db
from .candidates import Clip, creadores_de, motivo_descarte
from .config import EnVivo, Filtros, Streamer
from .kick import KickClient, KickError, a_clip
from .twitch import TwitchClient, TwitchError

log = logging.getLogger(__name__)

MOTIVO_MISMO_MOMENTO = "mismo momento (ya salió en vivo)"


def iso(dt: datetime) -> str:
    """Un solo formato para todo lo que se guarda: las alertas se comparan como texto en SQLite."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def desde_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Momento:
    streamer: str
    plataforma: str
    clips: list[Clip]              # de más a menos visto
    creadores: tuple[str, ...]
    momento: datetime              # el primer clip: lo más cerca del hecho que se sabe
    umbral: datetime               # cuando clipeó el N-ésimo creador distinto: desde ahí se podía ver


@dataclass
class Vuelta:
    """Lo que vio una pasada de detección. Se guarda la última para mostrarla en /envivo."""
    vivos: dict[str, str] = field(default_factory=dict)   # login → plataforma
    clips: int = 0
    momentos: list[Momento] = field(default_factory=list)
    fallos: list[str] = field(default_factory=list)


def _cerca(a: Clip, b: Clip, cfg: EnVivo) -> bool:
    if a.video_id and a.video_id == b.video_id and a.vod_offset is not None and b.vod_offset is not None:
        return abs(a.vod_offset - b.vod_offset) <= cfg.ventana_vod_s
    return abs((a.created_at - b.created_at).total_seconds()) <= cfg.ventana_real_s


def _umbral(clips: list[Clip], n: int) -> datetime | None:
    """Hora en que el grupo llegó a `n` creadores distintos, o None si no llega."""
    vistos: set[str] = set()
    for c in sorted(clips, key=lambda c: c.created_at):
        vistos.add(c.creator_id or f"clip:{c.id}")
        if len(vistos) >= n:
            return c.created_at
    return None


def agrupar_en_vivo(clips: list[Clip], cfg: EnVivo) -> list[Momento]:
    """Momentos con al menos `min_creadores` creadores distintos, del más clipeado al menos.

    Por canal, y empezando por el punto más denso: se toma el clip que más creadores distintos tiene
    alrededor, ese grupo sale, y se repite con lo que queda. Así el momento que se alerta primero es
    el más clipeado y no el más visto (en vivo casi todos tienen 0 a 4 vistas: no dicen nada).
    """
    out: list[Momento] = []
    por_canal: dict[str, list[Clip]] = {}
    # Helix puede devolver el mismo clip en dos páginas (pasó en el replay del 2026-09-27).
    for c in {c.id: c for c in clips}.values():
        por_canal.setdefault(c.broadcaster_login, []).append(c)
    for login, del_canal in por_canal.items():
        # Vecinos calculados UNA vez: recalcularlos en cada vuelta era cúbico, y un canal grande de
        # Kick junta 1200 clips en 72 h (el replay de calibración no terminaba).
        vecinos = {c.id: [x for x in del_canal if _cerca(c, x, cfg)] for c in del_canal}
        libres = {c.id: c for c in del_canal}
        while libres:
            def densidad(c: Clip) -> tuple:
                cerca = [x for x in vecinos[c.id] if x.id in libres]
                return (len(creadores_de(cerca)), c.view_count, c.created_at)

            ancla = max(libres.values(), key=densidad)
            grupo = [x for x in vecinos[ancla.id] if x.id in libres]
            for x in grupo:
                del libres[x.id]
            creadores = creadores_de(grupo)
            umbral = _umbral(grupo, cfg.min_creadores)
            if len(creadores) < cfg.min_creadores or umbral is None:
                continue
            grupo.sort(key=lambda c: (c.view_count, c.created_at), reverse=True)
            out.append(Momento(login, ancla.plataforma, grupo, creadores,
                               min(c.created_at for c in grupo), umbral))
    out.sort(key=lambda m: (len(m.creadores), m.umbral), reverse=True)
    return out


def elegir(m: Momento, filtros: Filtros, vistos: set[str],
           streamer: Streamer | None) -> tuple[Clip | None, Counter]:
    """El más visto del momento que pase los filtros de siempre, SIN la espera de 24 h ni el mínimo
    de vistas (un clip en vivo tiene minutos). Devuelve también por qué quedaron afuera los otros."""
    sin_espera = replace(filtros, antiguedad_min_h=0, min_vistas=0)
    descartes: Counter = Counter()
    for c in m.clips:
        motivo = motivo_descarte(c, sin_espera, vistos,
                                 con_deportes=bool(streamer and streamer.detectar_marcador),
                                 palabras_programa=streamer.palabras_programa if streamer else ())
        if motivo is None:
            return c, descartes
        descartes[motivo] += 1
    return None, descartes


# ---- detección ---------------------------------------------------------------------

def _habilitados(streamers: list[Streamer], excluidos: dict[str, str], plataforma: str) -> list[Streamer]:
    """TODOS los de la lista con permiso y sin reclamo, sin importar grupo ni fuente."""
    return [s for s in streamers
            if s.plataforma == plataforma and s.permitido and s.login not in excluidos]


def detectar(streamers: list[Streamer], cfg: EnVivo, excluidos: dict[str, str], *,
             twitch: TwitchClient | None = None, kick: KickClient | None = None,
             ahora: datetime | None = None, max_paginas_kick: int | None = None) -> Vuelta:
    """Una pasada: quién está en vivo, sus clips recientes y los momentos. No escribe nada.

    Si una plataforma falla, queda en `fallos` y la otra sigue (igual que la corrida diaria)."""
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(minutes=cfg.ventana_min)
    v = Vuelta()
    todos: list[Clip] = []

    if twitch is not None:
        tw = _habilitados(streamers, excluidos, "twitch")
        por_login = {s.login: s for s in tw}
        try:
            vivos = twitch.get_streams([s.login for s in tw]) if tw else {}
        except TwitchError as e:
            v.fallos.append(f"twitch/streams: {e}")
            vivos = {}
        for login, st in vivos.items():
            v.vivos[login] = "twitch"
            try:
                crudos = twitch.get_clips(st["user_id"], desde, ahora, 100)
            except TwitchError as e:
                v.fallos.append(f"twitch/{login}: {e}")
                continue
            s = por_login.get(login)
            todos += [Clip.from_helix(d, login, st["juego"], st["titulo"], "reciente", "twitch",
                                      s.grupo_de("reciente") if s else "") for d in crudos]

    if kick is not None:
        for s in _habilitados(streamers, excluidos, "kick"):
            try:
                ls = kick.get_livestream(s.login)
                if not ls:
                    continue
                v.vivos[s.login] = "kick"
                crudos = kick.get_clips_desde(s.login, desde, max_paginas_kick or cfg.max_paginas_kick)
            except KickError as e:
                v.fallos.append(f"kick/{s.login}: {e}")
                continue
            for d in crudos:
                p = a_clip(d, s.login)
                # El título del stream sirve para los filtros (co-stream, programa de terceros)
                # solo si el clip es de ESTE stream y no de uno anterior.
                titulo = ls["titulo"] if p["video_id"] == ls["id"] else ""
                todos.append(Clip.from_helix(p, s.login, p["_game_name"], titulo, "reciente", "kick",
                                             s.grupo_de("reciente")))

    v.clips = len(todos)
    v.momentos = agrupar_en_vivo(todos, cfg)
    return v


# ---- alertas en la DB ---------------------------------------------------------------

def _mismo_momento(m: Momento, a: dict, cfg: EnVivo) -> bool:
    if set(a["clips"]) & {c.id for c in m.clips}:
        return True
    return abs((desde_iso(a["momento"]) - m.momento).total_seconds()) <= cfg.ventana_real_s


def registrar(conn: sqlite3.Connection, vuelta: Vuelta, cfg: EnVivo, filtros: Filtros,
              streamers: list[Streamer], chat_id: str, ahora: datetime | None = None) -> list[dict]:
    """Anota una alerta por momento NUEVO. Devuelve las que se crearon o cambiaron.

    - Nunca dos del mismo momento: el momento sigue apareciendo en las vueltas siguientes mientras
      sus clips estén dentro de la ventana, y se reconoce por clips en común o por la hora.
    - `sin_clip` es la única que se reevalúa: el momento era bueno pero ningún clip pasaba los
      filtros (ej. todos de más de 60 s), y en la vuelta siguiente puede haber uno que sí.
    - Pasado el tope por hora, se anota igual como `tope`: sirve para medir cuánto se pierde.
    """
    ahora = ahora or datetime.now(timezone.utc)
    por_login = {s.login: s for s in streamers}
    recientes = db.alertas(conn, iso(ahora - timedelta(hours=3)))
    vistos = db.ids_vistos(conn)
    cambios = []
    for m in vuelta.momentos:
        previa = next((a for a in recientes
                       if a["streamer"] == m.streamer and _mismo_momento(m, a, cfg)), None)
        if previa and previa["estado"] != "sin_clip":
            continue
        clip, descartes = elegir(m, filtros, vistos, por_login.get(m.streamer))
        ids = sorted({c.id for c in m.clips} | set(previa["clips"] if previa else []))
        if clip is None:
            motivo = ", ".join(f"{k} ×{n}" for k, n in descartes.most_common(3))
            if previa:
                db.actualizar_alerta(conn, previa["id"], clips=ids, creadores=len(m.creadores),
                                     motivo=motivo)
                continue
            aid = db.crear_alerta(conn, streamer=m.streamer, plataforma=m.plataforma, chat_id=chat_id,
                                  estado="sin_clip", clips=ids, creadores=len(m.creadores),
                                  momento=iso(m.momento), umbral=iso(m.umbral), detectado=iso(ahora),
                                  motivo=motivo)
        else:
            en_la_hora = db.alertas(conn, iso(ahora - timedelta(hours=1)),
                                    estados=db.ESTADOS_CON_MENSAJE)
            estado = "tope" if len(en_la_hora) >= cfg.alertas_por_hora else "pendiente"
            motivo = f"tope de {cfg.alertas_por_hora} por hora" if estado == "tope" else None
            if previa:
                # Era sin_clip y ahora hay uno que pasa: la misma fila, con el tiempo de ahora.
                aid = previa["id"]
                db.actualizar_alerta(conn, aid, estado=estado, motivo=motivo, clip_id=clip.id,
                                     url=clip.url, clips=ids, creadores=len(m.creadores),
                                     detectado=iso(ahora))
            else:
                aid = db.crear_alerta(conn, streamer=m.streamer, plataforma=m.plataforma,
                                      chat_id=chat_id, estado=estado, clips=ids,
                                      creadores=len(m.creadores), momento=iso(m.momento),
                                      umbral=iso(m.umbral), detectado=iso(ahora), clip_id=clip.id,
                                      url=clip.url, motivo=motivo)
        recientes = db.alertas(conn, iso(ahora - timedelta(hours=3)))
        cambios.append(next(a for a in recientes if a["id"] == aid))
    return cambios


def vencer(conn: sqlite3.Connection, cfg: EnVivo, ahora: datetime | None = None) -> int:
    """Las pendientes que esperaron turno demasiado ya no son "YA": quedan como `vencida`."""
    ahora = ahora or datetime.now(timezone.utc)
    limite = iso(ahora - timedelta(minutes=cfg.vencimiento_min))
    n = 0
    for a in db.alertas(conn, estados=("pendiente",)):
        if a["detectado"] < limite:
            db.actualizar_alerta(conn, a["id"], estado="vencida",
                                 motivo=f"esperó turno más de {cfg.vencimiento_min} min")
            n += 1
    return n


def siguiente(conn: sqlite3.Connection) -> dict | None:
    """La pendiente a procesar primero: la más clipeada; a igualdad, la más nueva."""
    pend = db.alertas(conn, estados=("pendiente",))
    return max(pend, key=lambda a: (a["creadores"], a["detectado"])) if pend else None


# ---- dónde se pierde el tiempo --------------------------------------------------------

TRAMOS = [
    ("momento → umbral", "momento", "umbral", "lo que tarda la gente en clipear"),
    ("umbral → detectado", "umbral", "detectado", "lo que tarda el bot en verlo"),
    ("detectado → inicio", "detectado", "inicio", "espera de turno"),
    ("inicio → entregado", "inicio", "entregado", "procesar y mandar"),
    ("momento → entregado", "momento", "entregado", "total"),
]


def _min(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return (desde_iso(b) - desde_iso(a)).total_seconds() / 60


def resumen(alertas: list[dict]) -> str:
    """Conteo por estado y mediana de cada tramo (en minutos), solo con las entregadas."""
    if not alertas:
        return "Sin alertas todavía."
    por_estado = Counter(a["estado"] for a in alertas)
    lineas = ["  ".join(f"{e} {por_estado[e]}" for e in db.ESTADOS_ALERTA if por_estado[e])]
    entregadas = [a for a in alertas if a["estado"] == "entregada"]
    if entregadas:
        lineas.append(f"Medianas en {len(entregadas)} entregadas (minutos):")
        for nombre, a, b, que in TRAMOS:
            vals = [x for x in (_min(al[a], al[b]) for al in entregadas) if x is not None]
            if vals:
                lineas.append(f"  {nombre:<20} {statistics.median(vals):>5.1f}  {que}")
    motivos = Counter(a["motivo"] for a in alertas
                      if a["estado"] in ("descartada", "sin_clip") and a["motivo"])
    if motivos:
        lineas.append("Descartes:")
        lineas += [f"  {n:>3}  {m}" for m, n in motivos.most_common(5)]
    return "\n".join(lineas)
