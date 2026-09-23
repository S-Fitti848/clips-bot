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
import json
import logging
import sys
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
            meta = o.meta
            ruta_json = READY_DIR / f"{o.clip_id}.json"
            horario = horarios[i - 1] if i <= len(horarios) else None
            video = Path(meta["salida"])
            info = probe(video)  # dimensiones reales del archivo: sin esto Telegram lo muestra angosto
            thumb = miniatura(video, video.with_suffix(".thumb.jpg"))
            tg.send_video(chat_id, video, f"#{i} · {meta['streamer']} · {meta['textos']['titulo']}",
                          width=info.ancho, height=info.alto, duration=round(info.duracion), thumbnail=thumb)
            tg.send_message(chat_id, mensaje_textos(i, meta["streamer"], o.clip_id, horario, meta["textos"]))
            if not meta.get("subtitulos_quemados", True):  # el .srt va como pista de subtítulos en YouTube
                tg.send_document(chat_id, READY_DIR / f"{o.clip_id}.srt",
                                 "Subtítulos para cargar como pista en YouTube")
            meta["entregado"] = {"fecha": datetime.now(timezone.utc).isoformat(), "orden": i, "horario": horario}
            guardar_meta(ruta_json, meta)
            db.set_estado(conn, o.clip_id, "entregado")
            print(f"  enviado #{i}: {o.clip_id}")
    finally:
        conn.close()
    return 0


def cmd_diario(args: argparse.Namespace) -> int:
    """Corrida diaria completa: candidatos → procesar lo necesario → elegir → entregar."""
    from .process import procesar

    settings = load_settings()
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
    angulos = list(por_canal.values())[:3]
    if len(angulos) < 3:
        return 0

    print(f"\n=== Multi-POV: {len(angulos)} canales clipearon el mismo momento")
    ids, procesados = [], 0
    for c in angulos:
        print(f"\n--- [multipov] {c.url}")
        try:
            r = procesar(c.url, settings, streamers, gemini=gemini, fuente="reciente",
                         clips_mismo_momento=c.clips_mismo_momento, grupo="evento")
        except (DescargaError, MediaError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            continue
        procesados += 1
        if r.descartado:
            print(f"  → DESCARTADO: {r.descartado}")
        else:
            ids.append(r.clip_id)
    if len(ids) < 3:
        print(f"  quedaron {len(ids)} ángulos usables: no alcanza para el multi-POV")
        return procesados

    meta = armar_multipov(settings, ids, gemini)
    if meta:
        conn = db.connect(DB_PATH)
        try:
            for cid in ids:
                db.set_estado(conn, cid, "usado_multipov")
        finally:
            conn.close()
    return procesados


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

    angulos = multipov.ordenar(multipov.preparar(metas, READY_DIR))
    por_id = {m["clip_id"]: m for m in metas}
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
            elif c["comando"] in ("/ayuda", "/start", "/help"):
                respuesta = ("Comandos:\n/reclamo &lt;id del clip&gt; — marcá que ese video recibió un "
                             "reclamo o strike. Excluyo al streamer de las próximas corridas.")
            else:
                respuesta = f"No conozco {c['comando']}. Probá /ayuda."
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
    atender_telegram(load_settings())
    return 0


def READY_DIR_CLI() -> Path:
    from .process import READY_DIR

    return READY_DIR


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

    pa = sub.add_parser("atender-telegram", help="procesar los comandos que le mandaste al bot (/reclamo)")
    pa.set_defaults(func=cmd_atender_telegram)

    pt = sub.add_parser("telegram-chat-id", help="listar chats que le escribieron al bot (getUpdates)")
    pt.set_defaults(func=cmd_telegram_chat_id)

    args = p.parse_args(argv)
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
