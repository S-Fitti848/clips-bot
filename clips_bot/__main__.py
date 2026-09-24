"""CLI: python -m clips_bot <comando>

Comandos:
  candidatos   Lista los clips candidatos (recientes y catálogo). No descarga ni sube; guarda en la
               DB los descartados por co-stream. NO mueve el cursor del catálogo salvo --avanzar-cursor.
  procesar     Pasos 3–7 para una o más URLs de clip: descarga, co-stream, filtros de audio,
               subtítulos, textos con Gemini (descarta si depende de la fecha), layout 9:16.
               Deja todo en output/ready/. No sube nada.
  seleccionar  Paso 8: elige los mejores procesados. Con --enviar los manda por Telegram (paso 10).
  diario       Corrida completa (la del timer de systemd): candidatos → procesar lo necesario para
               llenar los cupos → elegir → entregar. Con --simular hace todo menos el envío.
  telegram-chat-id  Lista los chats que le escribieron al bot (getUpdates) para fijar TELEGRAM_CHAT_ID.
  multipov     Arma un Short multi-POV secuencial con clips YA procesados del mismo momento
               (hasta 3 ángulos, ±4 s alrededor del pico de reacción, cartel con el nombre).
  atender-telegram  Lee los comandos que le mandaste al bot. /reclamo <id> marca que un video recibió
               un reclamo o strike y EXCLUYE al streamer de las próximas corridas.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__, db
from .candidates import (MOTIVO_COSTREAM, Resultado, buscar_candidatos, buscar_catalogo, buscar_kick,
                         consolidar_evento)
from .config import DB_PATH, ConfigError, Settings, env, load_settings, load_streamers, load_twitch_creds
from .download import DescargaError
from .gemini import GeminiClient, GeminiError
from .kick import KickClient
from .media import MediaError, miniatura, probe
from .seleccion import score_reciente
from .telegram import TelegramClient, TelegramError
from .textos import TextosError
from .twitch import TwitchClient, TwitchError

log = logging.getLogger(__name__)

AR = timezone(timedelta(hours=-3), "AR")  # Argentina no tiene horario de verano


def _imprimir(res: Resultado, peso: float = 0.5) -> None:
    if res.sin_permiso:
        print(f"Sin permiso (ni cita ni experimento) en streamers.yaml: {', '.join(res.sin_permiso)}")
    if res.excluidos:
        print(f"EXCLUIDOS por reclamo de copyright: {', '.join(res.excluidos)}")
    for f in res.fallos:
        print(f"FALLO (la corrida sigue igual): {f}")
    if res.no_encontrados:
        print(f"No existen en Twitch: {', '.join(res.no_encontrados)}")
    for login, n in res.total_por_streamer.items():
        print(f"  {login}: {n} clips")

    ahora = datetime.now(timezone.utc)
    for titulo, clips, descartes in [
        ("Recientes (score = duplicados × log de vistas)", res.candidatos, res.descartes),
        ("Catálogo (por vistas absolutas)", res.catalogo, res.descartes_catalogo),
    ]:
        print(f"\n{titulo}: {len(clips)}")
        for i, c in enumerate(clips, 1):
            edad_h = (ahora - c.created_at).total_seconds() / 3600
            edad = f"{edad_h / 24:.1f} d" if edad_h >= 48 else f"{edad_h:.0f} h"
            sc = score_reciente(c.view_count, c.clips_mismo_momento, peso) if c.fuente == "reciente" else c.view_count
            print(
                f"{i:>2}. score {sc:>8,.2f}  {c.view_count:>6,} vistas  x{c.clips_mismo_momento} dup  "
                f"{edad:>6}  {c.duration:>4.0f}s  {c.plataforma:<6} {c.broadcaster_login:<12} "
                f"[{c.game_name or '?'}]  {c.title}"
            )
            print(f"    {c.url}")
        if any(descartes.values()):
            print("  Descartes:")
            for motivo, n in descartes.most_common():
                if n:
                    print(f"    {n:>4}  {motivo}")


def buscar_todo(settings: Settings, streamers: list, incluir_sin_permiso: bool,
                guardar_cursor: bool) -> Resultado:
    """Pasos 1–2 de las dos plataformas y las dos fuentes. Si Kick falla, queda anotado en
    res.fallos y la corrida sigue con Twitch."""
    conn = db.connect(DB_PATH)
    try:
        vistos = db.ids_vistos(conn)
        excluidos = db.excluidos(conn)
        res = buscar_kick(KickClient(pausa_s=settings.kick.pausa_s), streamers, settings.filtros, vistos, settings.kick,
                          incluir_sin_permiso=incluir_sin_permiso, seleccion=settings.seleccion,
                          excluidos=excluidos, evento=settings.evento)
        if any(s.plataforma == "twitch" for s in streamers):
            client = TwitchClient(*load_twitch_creds().__dict__.values())
            res = buscar_candidatos(client, streamers, settings.filtros, vistos, res=res,
                                    incluir_sin_permiso=incluir_sin_permiso, seleccion=settings.seleccion,
                                    excluidos=excluidos, evento=settings.evento)
            res = buscar_catalogo(client, streamers, settings.filtros, settings.catalogo, conn, vistos,
                                  incluir_sin_permiso=incluir_sin_permiso, res=res,
                                  guardar_cursor=guardar_cursor, excluidos=excluidos)
        res = consolidar_evento(res, settings.evento, settings.seleccion.peso_momento,
                                settings.filtros.n_candidatos)
        # Co-stream es una propiedad fija del clip: se marca para no volver a evaluarlo.
        for c in res.costream:
            db.registrar_clip(
                conn, c.id, c.broadcaster_login, "descartado", MOTIVO_COSTREAM,
                title=c.title, game_name=c.game_name, duration_s=c.duration, view_count=c.view_count,
                created_at=c.created_at.isoformat(), url=c.url,
            )
    finally:
        conn.close()
    return res


def cmd_candidatos(args: argparse.Namespace) -> int:
    settings = load_settings()
    res = buscar_todo(settings, load_streamers(), args.incluir_sin_permiso, args.avanzar_cursor)

    if not res.total_por_streamer and not res.no_encontrados:
        print("Ningún streamer habilitado. Completá permiso.cita y permiso.fuente en config/streamers.yaml,")
        print("o usá --incluir-sin-permiso solo para probar el listado.")
        return 1

    if args.json:
        out = [
            {**c.__dict__, "created_at": c.created_at.isoformat()}
            for c in res.candidatos + res.catalogo
        ]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _imprimir(res, settings.seleccion.peso_momento)
    return 0


def _gemini(settings: Settings) -> GeminiClient | None:
    key = env("GEMINI_API_KEY", requerido=False)
    return GeminiClient(key, settings.textos.modelo,
                        modelo_fallback=settings.textos.modelo_fallback) if key else None


def cmd_procesar(args: argparse.Namespace) -> int:
    from .process import procesar  # importa faster-whisper/OpenCV solo si hace falta

    settings = load_settings()
    streamers = load_streamers()
    permitidos = {s.login for s in streamers if s.permitido}
    gemini = _gemini(settings)
    codigo = 0
    for url in args.url:
        print(f"\n=== {url}")
        try:
            res = procesar(url, settings, streamers, forzar=args.forzar, gemini=gemini, fuente=args.fuente)
        except (DescargaError, MediaError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            codigo = 2
            continue
        if res.streamer.lower() not in permitidos:
            print(f"\nOJO: {res.streamer} no está en streamers.yaml con permiso cargado. "
                  "Sirve para probar, no para publicar.")
        print("\nTiempos:")
        for etapa, seg in res.tiempos.items():
            print(f"  {etapa:<28} {seg:>7.1f} s")
        if res.descartado:
            print(f"\nDESCARTADO: {res.descartado}")
            codigo = codigo or 3
        else:
            print(f"\nListo: {res.salida}")
    return codigo


def _opciones_pendientes(ready: Path, settings: Settings) -> list:
    """Clips procesados (estado 'procesado' en la DB) con su json en output/ready/."""
    from .process import fuente_por_antiguedad
    from .seleccion import Opcion

    conn = db.connect(DB_PATH)
    try:
        estado = db.estados(conn)
    finally:
        conn.close()
    opciones = []
    for p in sorted(ready.glob("*.json")):
        meta = json.loads(p.read_text(encoding="utf-8"))
        if estado.get(meta.get("clip_id")) != "procesado":
            continue
        creado = datetime.fromisoformat(meta["creado"]) if meta.get("creado") else None
        titulo = (meta.get("textos") or {}).get("titulo") or meta.get("titulo_twitch", "")
        fuente = meta.get("fuente") or fuente_por_antiguedad(creado, settings)  # jsons de antes de v0.4
        opciones.append(Opcion(
            meta["clip_id"], meta["streamer"], int(meta.get("vistas") or 0), creado, titulo,
            meta.get("transcripcion", ""), meta, fuente=fuente, grupo=meta.get("grupo") or fuente,
            clips_mismo_momento=int(meta.get("clips_mismo_momento") or 1),
        ))
    return opciones


def completar_textos(opciones: list, gemini: GeminiClient | None, settings: Settings, ready: Path,
                     marcar_descartado) -> list:
    """Genera los textos que falten (Gemini falló o no había key al procesar) y saca los que
    dependen de la fecha. Los que no se pueden completar quedan afuera de esta selección."""
    from .process import generar_textos, guardar_meta
    from .textos import MOTIVO_FECHA

    listas = []
    for o in opciones:
        meta = o.meta
        # Textos de antes de v0.4 no traen depende_de_fecha: se regeneran para evaluarlo.
        if not meta.get("textos") or "depende_de_fecha" not in meta["textos"]:
            if not gemini:
                print(f"  {o.clip_id}: sin textos (o sin evaluar la fecha) y sin GEMINI_API_KEY → queda afuera")
                continue
            try:
                meta["textos"] = generar_textos(gemini, settings, meta).to_dict()
            except (GeminiError, TextosError) as e:
                print(f"  {o.clip_id}: no se pudieron generar los textos ({e}) → queda afuera")
                continue
            guardar_meta(ready / f"{o.clip_id}.json", meta)
            o.titulo = meta["textos"]["titulo"]
        if meta["textos"].get("depende_de_fecha"):
            print(f"  {o.clip_id}: depende de la fecha → descartado")
            marcar_descartado(o.clip_id, MOTIVO_FECHA)
            continue
        listas.append(o)
    return listas


def cmd_seleccionar(args: argparse.Namespace) -> int:
    settings = load_settings()
    return ejecutar_seleccion(settings, _gemini(settings), enviar=args.enviar, n=args.n)


def ejecutar_seleccion(settings: Settings, gemini: GeminiClient | None, enviar: bool,
                       n: int | None = None) -> int:
    """Paso 8 + paso 10. Sin `enviar` muestra lo que mandaría y no toca Telegram ni la DB."""
    from .process import READY_DIR, guardar_meta
    from .seleccion import desempate_gemini, score, seleccionar
    from .telegram import mensaje_textos, resolver_chat_id

    cfg = settings.seleccion
    ahora = datetime.now(timezone.utc)
    permitidos = {s.login for s in load_streamers() if s.permitido}

    conn = db.connect(DB_PATH)
    try:
        def marcar_descartado(clip_id: str, motivo: str) -> None:
            conn.execute("UPDATE clips SET estado = 'descartado', motivo = ? WHERE clip_id = ?", (motivo, clip_id))
            conn.commit()

        pendientes = _opciones_pendientes(READY_DIR, settings)
        opciones = completar_textos(pendientes, gemini, settings, READY_DIR, marcar_descartado)
    finally:
        conn.close()
    if not opciones:
        print("No hay clips procesados pendientes (estado 'procesado' en la DB con json en output/ready/).")
        return 1
    elegidos = seleccionar(opciones, cfg, ahora, desempate_gemini(gemini) if gemini else None)
    if n:
        elegidos = elegidos[:n]

    cupos = ", ".join(f"{k} {v}" for k, v in cfg.mezcla.items())
    horarios = settings.publicacion.horarios
    print(f"\n{len(opciones)} pendientes → elegidos {len(elegidos)} (cupos: {cupos}):")
    for i, o in enumerate(elegidos, 1):
        edad = f"{(ahora - o.creado).total_seconds() / 3600 / 24:.1f} d" if o.creado else "?"
        horario = horarios[i - 1] if i <= len(horarios) else "?"
        print(f"\n{i}. [{o.grupo_o_fuente()}] score {score(o, ahora, cfg):,.2f}  {o.vistas:,} vistas  "
              f"x{o.clips_mismo_momento} dup  {edad}  {o.streamer}  ({horario} AR)")
        t = o.meta["textos"]
        print(f"   Título:      {t['titulo']}")
        print(f"   Descripción: {t['descripcion'].splitlines()[0]}")
        print(f"   Hashtags:    {' '.join(t['hashtags'])}")
        print(f"   mp4:         {o.meta['salida']}")
    sin_permiso = [o.clip_id for o in elegidos if o.streamer not in permitidos]
    if sin_permiso:
        print(f"\nOJO: {len(sin_permiso)} de los elegidos son de streamers sin permiso cargado en "
              "streamers.yaml. No se pueden publicar.")
    if not enviar:
        print("\n(simulación: no se mandó nada ni se marcó entregado)")
        return 0
    if sin_permiso:
        print("ERROR: no mando clips de streamers sin permiso cargado.", file=sys.stderr)
        return 2

    tg = TelegramClient(env("TELEGRAM_BOT_TOKEN"))
    chat_id = resolver_chat_id(tg, env("TELEGRAM_CHAT_ID", requerido=False))
    conn = db.connect(DB_PATH)
    try:
        for i, o in enumerate(elegidos, 1):
            horario = horarios[i - 1] if i <= len(horarios) else None
            enviar_clip(tg, chat_id, conn, o.clip_id, o.meta, i, horario)
            print(f"  enviado #{i}: {o.clip_id}")
    finally:
        conn.close()
    return 0


def enviar_clip(tg: TelegramClient, chat_id: str, conn, clip_id: str, meta: dict, numero: int,
                horario: str | None) -> None:
    """El mp4 + el mensaje con los textos, y el clip queda `entregado`. §3 paso 10."""
    from .process import READY_DIR, guardar_meta
    from .telegram import mensaje_textos

    video = Path(meta["salida"])
    info = probe(video)  # dimensiones reales del archivo: sin esto Telegram lo muestra angosto
    thumb = miniatura(video, video.with_suffix(".thumb.jpg"))
    tg.send_video(chat_id, video, f"#{numero} · {meta['streamer']} · {meta['textos']['titulo']}",
                  width=info.ancho, height=info.alto, duration=round(info.duracion), thumbnail=thumb)
    tg.send_message(chat_id, mensaje_textos(numero, meta["streamer"], clip_id, horario, meta["textos"]))
    if not meta.get("subtitulos_quemados", True):  # el .srt va como pista de subtítulos en YouTube
        tg.send_document(chat_id, READY_DIR / f"{clip_id}.srt",
                         "Subtítulos para cargar como pista en YouTube")
    meta["entregado"] = {"fecha": datetime.now(timezone.utc).isoformat(), "orden": numero,
                         "horario": horario}
    guardar_meta(READY_DIR / f"{clip_id}.json", meta)
    db.set_estado(conn, clip_id, "entregado")


def cmd_diario(args: argparse.Namespace) -> int:
    """Corrida diaria completa: candidatos → procesar lo necesario → elegir → entregar."""
    settings = load_settings()

    # Turno pesado: si hay un /buscar andando (modo escucha), se espera a que termine en vez de
    # pelearle la CPU a la Pi. Después de ESPERA_DIARIO_S arranca igual: la corrida del día no se
    # saltea por una búsqueda que quedó larga o colgada.
    token = f"diario:{datetime.now(timezone.utc).timestamp():.0f}"
    conn = db.connect(DB_PATH)
    try:
        espera = 0.0
        while not db.tomar_turno(conn, db.RECURSO_PESADO, token, maximo=1,
                                 vencimiento_s=VENCIMIENTO_PESADO_S):
            quien = db.hay_trabajo_pesado(conn, VENCIMIENTO_PESADO_S)
            if espera >= ESPERA_DIARIO_S:
                print(f"  {quien} sigue andando después de {espera / 60:.0f} min: arranco igual")
                db.soltar_turno(conn, db.RECURSO_PESADO, str(quien), VENCIMIENTO_PESADO_S)
                continue
            if espera == 0:
                print(f"  hay {quien} andando; espero hasta {ESPERA_DIARIO_S // 60} min")
            time.sleep(30)
            espera += 30
    finally:
        conn.close()
    try:
        return _diario(args, settings)
    finally:
        conn = db.connect(DB_PATH)
        try:
            db.soltar_turno(conn, db.RECURSO_PESADO, token, VENCIMIENTO_PESADO_S)
        finally:
            conn.close()


def _diario(args: argparse.Namespace, settings: Settings) -> int:
    from .process import procesar

    streamers = load_streamers()
    gemini = _gemini(settings)

    print("=== Comandos pendientes de Telegram")
    try:
        atender_telegram(settings, silencioso=True)
    except (TelegramError, ConfigError) as e:
        print(f"  (no pude leer Telegram: {e})")

    print("\n=== Pasos 1-2: candidatos")
    res = buscar_todo(settings, streamers, args.incluir_sin_permiso, guardar_cursor=True)
    _imprimir(res, settings.seleccion.peso_momento)
    if not res.candidatos and not res.catalogo:
        print("\nSin candidatos: no hay nada que procesar.")
        return 1

    # Pasos 3-7. Se procesa por fuente en orden de score, solo hasta llenar el cupo de esa fuente
    # (más lo que se vaya descartando), para no gastar Whisper y render de más.
    print(f"\n=== Pasos 3-7: procesar (tope {args.max_procesar} clips)")
    procesados = 0
    # Por grupo (no por fuente): cada cupo de la mezcla se llena con sus propios candidatos.
    # Multi-POV: si 3+ canales del evento clipearon el mismo momento, esos 3 clips se procesan y el
    # Short secuencial se queda con el cupo del evento. Uno por día.
    multipov_hecho = procesar_multipov_del_dia(settings, streamers, res, gemini, args.max_procesar)
    procesados += multipov_hecho

    por_grupo: dict[str, list] = {}
    for c in res.candidatos + res.catalogo:
        por_grupo.setdefault(c.grupo or c.fuente, []).append(c)
    for grupo, clips in sorted(por_grupo.items(), key=lambda kv: -settings.seleccion.mezcla.get(kv[0], 0)):
        if grupo == "evento" and multipov_hecho:
            print("\n(el cupo del evento se lo lleva el multi-POV de hoy)")
            continue
        objetivo = max(settings.seleccion.mezcla.get(grupo, 0), 1 if grupo == "catalogo" else 0)
        fuente = clips[0].fuente
        ok = 0
        for c in clips:
            if ok >= objetivo or procesados >= args.max_procesar:
                break
            print(f"\n--- [{grupo}] {c.url}")
            try:
                r = procesar(c.url, settings, streamers, gemini=gemini, fuente=fuente,
                             clips_mismo_momento=c.clips_mismo_momento, grupo=c.grupo)
            except (DescargaError, MediaError) as e:
                print(f"ERROR: {e}", file=sys.stderr)
                continue
            procesados += 1
            ok += 0 if r.descartado else 1
            print(f"  → {'DESCARTADO: ' + r.descartado if r.descartado else 'listo'} "
                  f"({r.tiempos.get('total', 0):.0f} s)")
        if ok < objetivo:
            print(f"  (grupo {grupo}: {ok}/{objetivo} del cupo; lo que falte lo cubre el catálogo)")

    print("\n=== Pasos 8 y 10: elegir y entregar")
    return ejecutar_seleccion(settings, gemini, enviar=not args.simular)


def procesar_multipov_del_dia(settings: Settings, streamers: list, res: Resultado,
                              gemini: GeminiClient | None, tope: int) -> int:
    """Procesa los 3 ángulos del mejor momento del evento y arma el multi-POV. Devuelve cuántos
    clips procesó (0 si no había un momento con 3+ canales distintos).

    Los 3 individuales quedan en estado `usado_multipov`, así no compiten contra el multi-POV en la
    selección: el cupo del evento es uno solo.
    """
    from .process import READY_DIR, procesar

    if not res.grupos_evento or tope < 3:
        return 0
    # el grupo con más canales distintos; a igualdad, el de más vistas
    grupo = max(res.grupos_evento,
                key=lambda g: (len({c.broadcaster_login for c in g}), sum(c.view_count for c in g)))
    por_canal: dict[str, object] = {}
    for c in sorted(grupo, key=lambda c: c.view_count, reverse=True):
        por_canal.setdefault(c.broadcaster_login, c)  # un ángulo por canal
    candidatos = list(por_canal.values())
    n = settings.multipov.max_angulos
    if len(candidatos) < n:
        return 0

    print(f"\n=== Multi-POV: {len(candidatos)} canales clipearon el mismo momento")
    ids, procesados, i = [], 0, 0

    def procesar_siguiente() -> bool:
        """Procesa el próximo candidato del momento. True si quedó usable."""
        nonlocal procesados, i
        c = candidatos[i]
        i += 1
        print(f"\n--- [multipov] {c.url}")
        try:
            r = procesar(c.url, settings, streamers, gemini=gemini, fuente="reciente",
                         clips_mismo_momento=c.clips_mismo_momento, grupo="evento")
        except (DescargaError, MediaError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return False
        procesados += 1
        if r.descartado:
            print(f"  → DESCARTADO: {r.descartado}")
            return False
        ids.append(r.clip_id)
        return True

    while len(ids) < n and i < len(candidatos) and procesados < tope:
        procesar_siguiente()
    if len(ids) < n:
        print(f"  quedaron {len(ids)} ángulos usables: no alcanza para el multi-POV")
        return procesados

    meta = armar_multipov(settings, ids, gemini)
    # Si algún ángulo no mostraba nada en su tramo, se busca reemplazo en el mismo momento.
    # Se prueban hasta 2 canales más: cada uno cuesta una descarga + Whisper + OCR + render.
    for _ in range(2):
        if meta or i >= len(candidatos) or procesados >= tope:
            break
        print("\n  busco un ángulo de reemplazo en el mismo momento")
        if procesar_siguiente():
            meta = armar_multipov(settings, ids, gemini)
    if meta:
        conn = db.connect(DB_PATH)
        try:
            for cid in ids:
                db.set_estado(conn, cid, "usado_multipov")
        finally:
            conn.close()
    return procesados


def _angulos_con_contenido(candidatos: list, por_id: dict, settings: Settings, max_angulos: int,
                           avisar=print) -> list:
    """Se queda con los ángulos cuyo tramo MUESTRA algo, probando de más a menos visto.

    Un ángulo cuyo panel de juego es un rectángulo negro no aporta ningún POV (PattyMeza,
    2026-09-23). El orden de rescate es el de §3 7b: primero rehacerlo con fit_blur (que muestra el
    16:9 entero, sin panel), y si tampoco alcanza, reemplazarlo por el siguiente ángulo del mismo
    momento. Si no se llega al mínimo, el que llama no arma nada.
    """
    from dataclasses import replace as _replace
    from . import layout as lay, multipov
    from .process import RAW_DIR, WORK_DIR
    from .render import renderizar

    cfg, R = settings.multipov, settings.render
    elegidos = []
    for a in candidatos:
        if len(elegidos) >= max_angulos:
            break
        meta = por_id[a.clip_id]
        es_split = meta.get("layout") == "split"
        y0 = R.alto_camara if es_split else 0
        c = multipov.medir_panel(a.video, a.inicio, a.fin, y0, R.alto, cfg.frames_muestra,
                                 cfg.luma_negro, cfg.pixeles_negros_min)
        if not multipov.panel_vacio(c, cfg.frames_vacios_max):
            elegidos.append(a)
            continue
        avisar(f"  {a.streamer}: {c.vacios:.0%} del tramo en negro ({meta.get('layout')})")
        if not es_split:
            avisar(f"    ya no tiene panel que sacar: lo dejo afuera")
            continue
        # Rescate 1: rehacer ese clip con fit_blur (el 16:9 entero) y volver a medir el frame completo.
        alterno = WORK_DIR / f"fitblur_{a.clip_id}.mp4"
        try:
            W, H, frames, _ = lay.detectar_caras(RAW_DIR / f"{a.clip_id}.mp4", settings.camara.frames_muestra)
            subs = WORK_DIR / a.clip_id
            renderizar(RAW_DIR / f"{a.clip_id}.mp4", alterno, lay.layout_fit_blur(W, H, R), R,
                       subs if (subs / "subs.ass").exists() and meta.get("subtitulos_quemados", True) else None)
        except (OSError, RuntimeError) as e:
            avisar(f"    no pude rehacerlo con fit_blur ({e}): lo dejo afuera")
            continue
        c2 = multipov.medir_panel(alterno, a.inicio, a.fin, 0, R.alto, cfg.frames_muestra,
                                  cfg.luma_negro, cfg.pixeles_negros_min)
        if multipov.panel_vacio(c2, cfg.frames_vacios_max):
            avisar(f"    con fit_blur sigue {c2.vacios:.0%} en negro: lo reemplazo")
            continue
        avisar(f"    rehecho con fit_blur: {c2.vacios:.0%} en negro")
        elegidos.append(_replace(a, video=alterno))
    return elegidos


def armar_multipov(settings: Settings, clip_ids: list[str], gemini: GeminiClient | None,
                   avisar=print) -> dict | None:
    """Multi-POV con clips ya procesados. Devuelve el meta del nuevo Short (o None si no se pudo)."""
    from . import multipov
    from .process import READY_DIR, WORK_DIR, generar_textos, guardar_meta
    from .textos import TextosClip

    metas = []
    for cid in clip_ids:
        ruta = READY_DIR / f"{cid}.json"
        if not ruta.exists():
            avisar(f"  {cid}: no está procesado (falta {ruta.name})")
            continue
        meta = json.loads(ruta.read_text(encoding="utf-8"))
        if not meta.get("salida") or not Path(meta["salida"]).exists():
            avisar(f"  {cid}: no tiene mp4 renderizado")
            continue
        metas.append(meta)
    if len(metas) < 2:
        avisar("  hacen falta al menos 2 ángulos procesados")
        return None

    cfg_mp = settings.multipov
    minimo = min(len(metas), cfg_mp.min_angulos)
    por_id = {m["clip_id"]: m for m in metas}
    candidatos = multipov.preparar(metas, READY_DIR, cfg_mp.margen_s)
    candidatos.sort(key=lambda a: a.vistas, reverse=True)  # se prueban de más a menos visto
    angulos = _angulos_con_contenido(candidatos, por_id, settings, cfg_mp.max_angulos, avisar)
    if len(angulos) < minimo:
        avisar(f"  solo {len(angulos)} de {len(candidatos)} ángulos muestran algo en su tramo "
               f"(hacen falta {minimo}): no armo el multi-POV")
        return None
    angulos = sorted(angulos, key=lambda a: a.vistas)  # de menos a más visto: el final es el fuerte
    for a in angulos:
        avisar(f"  {a.streamer:<16} vistas {a.vistas:>6,}  ventana {a.inicio:.1f}–{a.fin:.1f}s")

    ancla = max(angulos, key=lambda a: a.vistas)
    nuevo_id = f"multipov_{ancla.clip_id}"
    salida = READY_DIR / f"{nuevo_id}.mp4"
    multipov.armar(angulos, salida, WORK_DIR / nuevo_id, settings.render, settings.subtitulos)

    # Textos: se parte de los del ángulo más visto (o se generan) y el crédito pasa a ser de todos.
    meta_ancla = por_id[ancla.clip_id]
    textos = meta_ancla.get("textos")
    if (not textos or "depende_de_fecha" not in textos) and gemini:
        try:
            textos = generar_textos(gemini, settings, meta_ancla).to_dict()
        except (GeminiError, TextosError) as e:
            avisar(f"  ⚠ textos: {e}")
            textos = None
    if not textos:
        avisar("  sin textos: los genera `seleccionar` antes de enviar")
    else:
        creditos = [(por_id[a.clip_id].get("canal") or a.streamer,
                     f"{'kick.com' if por_id[a.clip_id].get('plataforma') == 'kick' else 'twitch.tv'}/"
                     f"{por_id[a.clip_id]['streamer']}") for a in angulos]
        credito = multipov.credito_multiple(creditos)
        cuerpo = textos["descripcion"].split("\n\nClip de ")[0]
        textos = {**textos, "credito": credito, "descripcion": f"{cuerpo}\n\n{credito}"}

    meta = {
        "clip_id": nuevo_id, "streamer": meta_ancla["streamer"], "canal": meta_ancla.get("canal", ""),
        "url": meta_ancla.get("url", ""), "titulo_twitch": meta_ancla.get("titulo_twitch", ""),
        "categoria": meta_ancla.get("categoria", ""), "vistas": ancla.vistas,
        "creado": meta_ancla.get("creado"), "duracion_s": round(sum(a.duracion for a in angulos), 2),
        "fuente": "reciente", "grupo": meta_ancla.get("grupo") or "evento",
        "plataforma": meta_ancla.get("plataforma", "twitch"),
        "clips_mismo_momento": len(angulos), "multipov": [a.clip_id for a in angulos],
        "transcripcion": meta_ancla.get("transcripcion", ""), "subtitulos_quemados": True,
        "textos": textos, "salida": str(salida),
    }
    guardar_meta(READY_DIR / f"{nuevo_id}.json", meta)
    conn = db.connect(DB_PATH)
    try:
        db.registrar_clip(conn, nuevo_id, meta["streamer"], "procesado", None,
                          title=meta["titulo_twitch"], duration_s=meta["duracion_s"],
                          view_count=meta["vistas"], created_at=meta["creado"], url=meta["url"])
    finally:
        conn.close()
    avisar(f"  listo: {salida} ({meta['duracion_s']:.0f} s, {len(angulos)} ángulos)")
    return meta


def cmd_multipov(args: argparse.Namespace) -> int:
    settings = load_settings()
    meta = armar_multipov(settings, args.clip_id, _gemini(settings))
    return 0 if meta else 1


def atender_telegram(settings: Settings, silencioso: bool = False) -> int:
    """Procesa los comandos que le mandaste al bot. Hoy: /reclamo <id de clip> → excluye al streamer.

    El offset de getUpdates se guarda en la DB, así cada comando se atiende una sola vez.
    Cuando exista el módulo de métricas (§4b), el mismo camino sirve para excluir automáticamente
    cuando YouTube marque un reclamo: llamar a `db.excluir_streamer` y avisar igual que acá.

    Permiso por USUARIO (TELEGRAM_ALLOWED_USERS), no por chat: con la entrega en un grupo el chat es
    uno solo y cualquier miembro podría excluir un streamer con /reclamo. Sin la variable no se
    obedece ningún comando (falla cerrado): es preferible que /reclamo no ande a que lo use
    cualquiera si el bot termina en otro grupo.
    """
    from .telegram import comandos, usuarios_permitidos

    tg = TelegramClient(env("TELEGRAM_BOT_TOKEN"))
    permitidos = usuarios_permitidos(env("TELEGRAM_ALLOWED_USERS", requerido=False))
    if not permitidos:
        log.warning("TELEGRAM_ALLOWED_USERS vacío: no obedezco ningún comando")
    conn = db.connect(DB_PATH)
    try:
        guardado = db.get_valor(conn, "telegram_offset")
        updates = tg.get_updates(offset=int(guardado) if guardado else None)
        atendidos = 0
        for c in comandos(updates):
            if c["user_id"] not in permitidos:
                quien = f"{c['usuario'] or '?'} (id {c['user_id'] or '?'})"
                log.warning("%s de %s: no está en TELEGRAM_ALLOWED_USERS, lo ignoro", c["comando"], quien)
                if not silencioso:
                    print(f"  {c['comando']} de {quien} → IGNORADO (no autorizado)")
                if not permitidos:
                    # Está mal configurado, no es un intruso: decile cómo arreglarlo, con su id.
                    # Con la lista puesta, a los de afuera no se les contesta nada.
                    tg.send_message(c["chat_id"],
                                    "No tengo <code>TELEGRAM_ALLOWED_USERS</code> configurado, así que no "
                                    f"obedezco comandos. Tu id es <code>{c['user_id']}</code>: ponelo ahí "
                                    "en el .env (con coma si son varios).")
                continue
            if c["comando"] == "/reclamo":
                respuesta = _reclamo(conn, c["args"])
            elif c["comando"] == "/buscar":
                respuesta = _buscar(conn, tg, c["chat_id"], c["args"], settings,
                                    load_streamers(), _gemini(settings))
                if respuesta is OCUPADO:
                    # Sin modo escucha no hay cola: este proceso termina cuando termina la pasada.
                    respuesta = (f"Hay una corrida pesada andando ({db.hay_trabajo_pesado(conn)}). "
                                 "Probá de nuevo cuando termine, o dejá andando "
                                 "<code>clips-bot-telegram</code> para que quede en cola.")
            elif c["comando"] in ("/ayuda", "/start", "/help"):
                respuesta = _ayuda()
            else:
                respuesta = f"No conozco {c['comando']}. Probá /ayuda."
            if respuesta:
                tg.send_message(c["chat_id"], respuesta)
            atendidos += 1
            if not silencioso:
                print(f"  {c['comando']} {' '.join(c['args'])} → respondido")
        if updates:
            db.set_valor(conn, "telegram_offset", str(max(u["update_id"] for u in updates) + 1))
        if atendidos and silencioso:
            print(f"  {atendidos} comando(s) de Telegram atendidos")
        elif not atendidos and not silencioso:
            print("Sin comandos nuevos.")
        return atendidos
    finally:
        conn.close()


MAX_BUSQUEDAS = 2      # búsquedas esperando en la cola del modo escucha
TOPE_BUSCAR = 3        # clips procesados por búsqueda: cada uno es Whisper + OCR + render
VENCIMIENTO_PESADO_S = 3 * 3600   # un turno pesado colgado se suelta solo a las 3 h
ESPERA_DIARIO_S = 20 * 60         # lo que `diario` aguanta a una búsqueda antes de arrancar igual

OCUPADO = object()     # lo devuelve _buscar cuando hay otra cosa pesada andando


def _buscar(conn, tg: TelegramClient, chat_id: str, args: list[str], settings: Settings,
            streamers: list, gemini: GeminiClient | None):
    """/buscar <streamer> [palabras] [días]. Devuelve el mensaje final, None si ya respondió, o
    OCUPADO si hay otra cosa pesada corriendo (el que llama decide si encola).

    Contesta "buscando..." con cuántos candidatos hay ANTES de procesar, porque procesar 3 clips en
    la Pi son varios minutos y si no parece que el bot se colgó.
    """
    from .candidates import MOTIVO_SIN_PALABRAS, buscar_candidatos, buscar_kick
    from .process import READY_DIR, procesar
    from .seleccion import score_reciente
    from .telegram import parse_buscar

    from dataclasses import replace as _replace

    try:
        login, palabras, dias = parse_buscar(args)
    except ValueError as e:
        return str(e)

    st = next((x for x in streamers if x.login == login), None)
    if st is None:
        return (f"No tengo a <code>{login}</code> en streamers.yaml. Los que hay: "
                + ", ".join(sorted(x.login for x in streamers)[:25]) + "...")
    if not st.permitido:
        return f"{login} no tiene permiso cargado en streamers.yaml: no puedo mandar sus clips."
    excluidos = db.excluidos(conn)
    if login in excluidos:
        return f"{login} está EXCLUIDO ({excluidos[login]}). Sacalo a mano si querés volver a usarlo."

    # Turno pesado: procesar clips es lo caro, y no puede haber dos a la vez (ni con `diario`).
    token = f"buscar:{login}:{datetime.now(timezone.utc).timestamp():.0f}"
    if not db.tomar_turno(conn, db.RECURSO_PESADO, token, maximo=1,
                          vencimiento_s=VENCIMIENTO_PESADO_S):
        return OCUPADO
    try:
        # Ventana pedida a mano: sin el mínimo de 24 h de antigüedad (eso es para que un clip junte
        # vistas y duplicados; acá el que busca ya sabe lo que quiere) y con margen de candidatos
        # para que el filtro de palabras tenga con qué trabajar.
        filtros = _replace(settings.filtros, ventana_horas=dias * 24, antiguedad_min_h=0,
                           n_candidatos=max(settings.filtros.n_candidatos, 20))
        vistos = db.ids_vistos(conn)
        if st.plataforma == "kick":
            res = buscar_kick(KickClient(pausa_s=settings.kick.pausa_s), [st], filtros, vistos,
                              settings.kick, seleccion=settings.seleccion, excluidos=excluidos,
                              evento=settings.evento, palabras_titulo=palabras)
        else:
            res = buscar_candidatos(TwitchClient(load_twitch_creds()), [st], filtros, vistos,
                                    seleccion=settings.seleccion, excluidos=excluidos,
                                    evento=settings.evento, palabras_titulo=palabras)

        que = f" con {', '.join(palabras)}" if palabras else ""
        if not res.candidatos:
            return (f"Busqué en {login}{que} de los últimos {dias} días y no quedó ninguno."
                    f"{_resumen_descartes(res)}")
        tg.send_message(chat_id, f"Buscando en <b>{login}</b>{html.escape(que)} de los últimos "
                                 f"{dias} días: <b>{len(res.candidatos)} candidatos</b>. "
                                 f"Proceso los {min(TOPE_BUSCAR, len(res.candidatos))} mejores, "
                                 f"tarda unos minutos.")

        enviados, fallados = 0, []
        for c in res.candidatos[:TOPE_BUSCAR]:
            try:
                r = procesar(c.url, settings, streamers, gemini=gemini, fuente="reciente",
                             clips_mismo_momento=c.clips_mismo_momento, grupo=st.grupo_de("reciente"),
                             avisar=lambda *_: None)
            except (DescargaError, MediaError) as e:
                fallados.append(f"{c.id[:14]}: {e}")
                continue
            if r.descartado:
                res.descartes[r.descartado.split(" (")[0]] += 1
                continue
            meta = json.loads((READY_DIR / f"{r.clip_id}.json").read_text(encoding="utf-8"))
            if not meta.get("textos"):
                fallados.append(f"{r.clip_id[:14]}: sin textos (¿cuota de Gemini?)")
                continue
            enviados += 1
            enviar_clip(tg, chat_id, conn, r.clip_id, meta, enviados, None)

        final = [f"Listo: <b>{enviados}</b> de {len(res.candidatos)} candidatos "
                 f"({login}{que}, {dias} días)."]
        if fallados:
            final.append("No salieron: " + "; ".join(html.escape(f) for f in fallados[:3]))
        final.append(_resumen_descartes(res))
        return "\n".join(x for x in final if x)
    finally:
        db.soltar_turno(conn, db.RECURSO_PESADO, token, VENCIMIENTO_PESADO_S)


def _resumen_descartes(res) -> str:
    """Los motivos de descarte, de mayor a menor. Es la mitad útil de una búsqueda: dice POR QUÉ
    no quedó nada."""
    if not res.descartes:
        return ""
    filas = sorted(res.descartes.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in filas)
    cuerpo = "\n".join(f"{v:>4}  {html.escape(k)}" for k, v in filas if v)
    return f"\nDescartes ({total}):\n<pre>{cuerpo}</pre>"


def escuchar_telegram(settings: Settings, timeout_poll: int = 50) -> int:
    """`atender-telegram --escuchar`: long polling, para que /buscar ande cuando lo mandás y no
    recién en la corrida del día siguiente. Lo corre clips-bot-telegram.service.

    Cola: si hay una corrida pesada andando (`diario` o la búsqueda anterior), la búsqueda no se
    tira, se guarda y arranca sola cuando se libera el turno. Mientras hay algo en la cola el
    polling baja a unos segundos, así no se queda esperando 50 s para reaccionar.
    """
    from .telegram import comandos, usuarios_permitidos

    tg = TelegramClient(env("TELEGRAM_BOT_TOKEN"), timeout=timeout_poll + 30)
    permitidos = usuarios_permitidos(env("TELEGRAM_ALLOWED_USERS", requerido=False))
    if not permitidos:
        log.warning("TELEGRAM_ALLOWED_USERS vacío: no obedezco ningún comando")
    cola: list[dict] = []
    print(f"Escuchando (long polling {timeout_poll}s). Ctrl-C para salir.")
    while True:
        conn = db.connect(DB_PATH)
        try:
            _drenar_cola(conn, tg, cola, settings)
            guardado = db.get_valor(conn, "telegram_offset")
            espera = 5 if cola else timeout_poll
            try:
                updates = tg.get_updates(offset=int(guardado) if guardado else None, timeout=espera)
            except TelegramError as e:
                # Un corte de red no puede matar el servicio: se anota y se reintenta.
                log.warning("getUpdates falló (%s); reintento en 30 s", e)
                time.sleep(30)
                continue
            for c in comandos(updates):
                if c["user_id"] not in permitidos:
                    log.warning("%s de %s (id %s): no autorizado", c["comando"], c["usuario"],
                                c["user_id"])
                    continue
                _despachar(conn, tg, c, settings, cola)
            if updates:
                db.set_valor(conn, "telegram_offset", str(max(u["update_id"] for u in updates) + 1))
        finally:
            conn.close()


def _despachar(conn, tg: TelegramClient, c: dict, settings: Settings, cola: list[dict]) -> None:
    """Un comando del modo escucha. /buscar puede quedar en cola; el resto contesta al toque."""
    print(f"  {c['comando']} {' '.join(c['args'])} de {c['usuario'] or c['user_id']}")
    if c["comando"] == "/buscar":
        if len(cola) >= MAX_BUSQUEDAS:
            tg.send_message(c["chat_id"], f"Ya tengo {len(cola)} búsquedas en cola. Esperá a que "
                                          "salgan esas y probá de nuevo.")
            return
        r = _buscar(conn, tg, c["chat_id"], c["args"], settings, load_streamers(), _gemini(settings))
        if r is OCUPADO:
            cola.append({"chat_id": c["chat_id"], "args": c["args"]})
            quien = db.hay_trabajo_pesado(conn, VENCIMIENTO_PESADO_S) or ""
            que = "la corrida diaria" if quien.startswith("diario") else "la búsqueda anterior"
            tg.send_message(c["chat_id"], f"En cola ({len(cola)}º), arranco cuando termine {que}.")
        elif r:
            tg.send_message(c["chat_id"], r)
        return
    if c["comando"] == "/reclamo":
        respuesta = _reclamo(conn, c["args"])
    elif c["comando"] in ("/ayuda", "/start", "/help"):
        respuesta = _ayuda()
    else:
        respuesta = f"No conozco {c['comando']}. Probá /ayuda."
    tg.send_message(c["chat_id"], respuesta)


def _drenar_cola(conn, tg: TelegramClient, cola: list[dict], settings: Settings) -> None:
    """Arranca las búsquedas que estaban esperando, mientras el turno pesado siga libre."""
    while cola:
        if db.hay_trabajo_pesado(conn, VENCIMIENTO_PESADO_S):
            return
        pedido = cola.pop(0)
        r = _buscar(conn, tg, pedido["chat_id"], pedido["args"], settings, load_streamers(),
                    _gemini(settings))
        if r is OCUPADO:  # alguien tomó el turno entre el chequeo y la llamada
            cola.insert(0, pedido)
            return
        if r:
            tg.send_message(pedido["chat_id"], r)


def _ayuda() -> str:
    return ("Comandos:\n"
            "/reclamo &lt;id del clip&gt; — marcá que ese video recibió un reclamo o strike. "
            "Excluyo al streamer de las próximas corridas.\n"
            "/buscar &lt;streamer&gt; [palabras] [días] — busco en sus clips de los últimos días "
            f"(default 7), proceso los {TOPE_BUSCAR} mejores y te los mando. "
            "Ej: <code>/buscar davooxeneize gol 3</code>")


def _reclamo(conn, args: list[str]) -> str:
    """Marca un reclamo/strike sobre un clip y excluye al streamer."""
    if not args:
        return "Uso: <code>/reclamo &lt;id del clip&gt;</code> (el id va en cada mensaje de entrega)."
    clip_id = args[0]
    fila = db.clip_de(conn, clip_id)
    if not fila:
        return f"No tengo el clip <code>{clip_id}</code> en la base. ¿Copiaste bien el id?"
    streamer, _url = fila
    nuevo = db.excluir_streamer(conn, streamer, f"reclamo de copyright ({' '.join(args[1:]) or 'manual'})", clip_id)
    db.registrar_clip(conn, clip_id, streamer, "descartado", "reclamo")
    if nuevo:
        return (f"Anotado. <b>{streamer} queda EXCLUIDO</b>: no se vuelve a usar en las corridas.\n"
                f"Acordate de sacar el video de YouTube si el reclamo bloquea el contenido.")
    return f"{streamer} ya estaba excluido. Anoté el reclamo sobre <code>{clip_id}</code>."


def cmd_atender_telegram(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.escuchar:
        try:
            escuchar_telegram(settings)
        except KeyboardInterrupt:
            print("\nListo.")
        return 0
    atender_telegram(settings)
    return 0


def READY_DIR_CLI() -> Path:
    from .process import READY_DIR

    return READY_DIR


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Mide las etapas caras sobre los mp4 que ya están en output/raw/. No descarga nada."""
    from . import benchmark as bench
    from .process import OUTPUT_DIR, RAW_DIR

    settings = load_settings()
    modelos = [m.strip() for m in args.modelos.split(",") if m.strip()]
    crudos = sorted(RAW_DIR.glob("*.mp4"), key=lambda p: p.stat().st_size)[: args.clips]
    if not crudos:
        print(f"No hay mp4 en {RAW_DIR}. Corré `procesar <url>` o copiá alguno desde otra máquina.",
              file=sys.stderr)
        return 1
    info = bench.maquina()
    print(f"{info.get('modelo') or info['plataforma']} · {info['maquina']} · {info['cpus']} CPUs · "
          f"Python {info['python']}")
    print(f"Whisper: {', '.join(modelos)} ({settings.subtitulos.compute_type}) · "
          f"OCR: {settings.pantalla.idioma} · x264 preset {settings.render.x264_preset}")
    destino = OUTPUT_DIR / "benchmark"
    mediciones = []
    for raw in crudos:
        print(f"\n--- {raw.name}")
        m = bench.medir_clip(raw, settings, modelos, destino)
        print(f"    {m.layout} · total {m.total:.0f}s ({m.por_segundo():.1f}x la duración)")
        mediciones.append(m)
    print(f"\n" + bench.informe(mediciones, modelos, args.limite_s))
    print(f"\njson: {bench.guardar(mediciones, modelos, destino / 'benchmark.json')}")
    return 0


def cmd_telegram_chat_id(args: argparse.Namespace) -> int:
    from .telegram import chats, usuarios

    updates = TelegramClient(env("TELEGRAM_BOT_TOKEN")).get_updates()
    encontrados = chats(updates)
    if not encontrados:
        print("Nadie le escribió al bot todavía (o ya se consumieron los updates). Mandale un mensaje y reintentá."
              + chr(10) +
              "En un GRUPO, con el modo privacidad de BotFather activado (el default) el bot solo ve los "
              "mensajes que empiezan con / o que lo mencionan: mandá /start en el grupo.")
        return 1
    print("Chats (TELEGRAM_CHAT_ID; los grupos tienen id negativo):")
    for c in encontrados:
        print(f"{c['id']:>16}  {c['tipo']:<10} {c['nombre']}")
    quienes = usuarios(updates)
    if quienes:
        print(chr(10) + "Usuarios (TELEGRAM_ALLOWED_USERS, separados por coma):")
        for u in quienes:
            print(f"{u['id']:>16}  {u['nombre']}")
    print("\nCopiá el id que corresponda a TELEGRAM_CHAT_ID en .env.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clips_bot", description=f"Clips Bot v{__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("candidatos", help="listar clips candidatos (guarda solo los descartes costream)")
    pc.add_argument(
        "--incluir-sin-permiso",
        action="store_true",
        help="incluye streamers sin permiso cargado. SOLO para probar el listado; el pipeline nunca los usa",
    )
    pc.add_argument("--json", action="store_true", help="salida JSON")
    pc.add_argument("--avanzar-cursor", action="store_true",
                    help="guarda el cursor del catálogo (por default listar no lo mueve; `diario` sí)")
    pc.set_defaults(func=cmd_candidatos)

    pp = sub.add_parser("procesar", help="descargar y armar el Short de una o más URLs de clip (sin subir)")
    pp.add_argument("url", nargs="+", help="URL(s) de clips de Twitch")
    pp.add_argument("--forzar", action="store_true",
                    help="seguir aunque disparen los filtros (co-stream, audio, depende de la fecha)")
    pp.add_argument("--fuente", choices=["reciente", "catalogo"],
                    help="default: catalogo si el clip tiene ≥ catalogo.antiguedad_min_dias, si no reciente")
    pp.set_defaults(func=cmd_procesar)

    ps = sub.add_parser("seleccionar", help="elegir los mejores procesados; --enviar los manda por Telegram")
    ps.add_argument("--n", type=int, help="tope total después de la mezcla por cupos (default: la suma de los cupos)")
    ps.add_argument("--enviar", action="store_true", help="mandar los elegidos por Telegram y marcarlos entregados")
    ps.set_defaults(func=cmd_seleccionar)

    pd = sub.add_parser("diario", help="corrida completa: candidatos → procesar → elegir → entregar")
    pd.add_argument("--simular", action="store_true",
                    help="hace todo menos el envío: no manda por Telegram ni marca entregado")
    pd.add_argument("--max-procesar", type=int, default=6, help="tope de clips a procesar (default 6)")
    pd.add_argument("--incluir-sin-permiso", action="store_true",
                    help="incluye streamers sin permiso cargado. Solo para simular: el envío igual los rechaza")
    pd.set_defaults(func=cmd_diario)

    pm = sub.add_parser("multipov", help="armar un Short multi-POV con clips ya procesados del mismo momento")
    pm.add_argument("clip_id", nargs="+", help="ids de clips ya procesados (2 a 3 ángulos)")
    pm.set_defaults(func=cmd_multipov)

    pa = sub.add_parser("atender-telegram", help="procesar los comandos que le mandaste al bot")
    pa.add_argument("--escuchar", action="store_true",
                    help="queda escuchando con long polling en vez de hacer una sola pasada "
                         "(lo usa clips-bot-telegram.service)")
    pa.set_defaults(func=cmd_atender_telegram)

    pt = sub.add_parser("telegram-chat-id", help="listar chats que le escribieron al bot (getUpdates)")
    pt.set_defaults(func=cmd_telegram_chat_id)

    pb = sub.add_parser("benchmark", help="cuánto tarda un clip completo en esta máquina")
    pb.add_argument("--clips", type=int, default=2, help="cuántos mp4 de output/raw/ medir (default 2)")
    pb.add_argument("--modelos", default="small",
                    help="modelos de Whisper separados por coma, ej. small,base (default small)")
    pb.add_argument("--limite-s", type=float, default=300.0, help="tope por clip para el veredicto")
    pb.set_defaults(func=cmd_benchmark)

    args = p.parse_args(argv)
    # SIGTERM (lo que manda systemd al frenar o al vencer TimeoutStartSec) tiene que desarmar la
    # pila como cualquier salida, para que corran los `finally` que sueltan el turno pesado. Sin
    # esto, un `systemctl stop` en medio de una corrida dejaba el turno tomado y el /buscar
    # siguiente quedaba en cola hasta que venciera (3 h). Encontrado probando, no en la doc.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    # Los títulos de clips traen emojis; la consola de Windows por defecto no es UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for ruidoso in ("httpx", "huggingface_hub", "faster_whisper"):
        logging.getLogger(ruidoso).setLevel(logging.DEBUG if args.verbose else logging.WARNING)
    try:
        return args.func(args)
    except (ConfigError, TwitchError, DescargaError, MediaError, GeminiError, TextosError, TelegramError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
