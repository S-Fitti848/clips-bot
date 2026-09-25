"""Altas y bajas de streamers hechas por Telegram, guardadas en la DB.

Por qué no en `config/streamers.yaml`: el YAML está en git y lo editamos a mano. Si el bot también
escribiera ahí, cada alta por Telegram sería un conflicto al próximo `git pull` en la Pi. Entonces
el YAML sigue siendo la lista "de autor" y la DB guarda las diferencias; al cargar se combinan.

Regla de precedencia: la DB gana. Una baja saca a alguien aunque esté en el YAML, y un alta lo
agrega o le cambia el grupo. Así se puede corregir algo desde el teléfono sin tocar el repo.
"""

from __future__ import annotations

import sqlite3

from .config import PLATAFORMAS, Streamer

ALTA, BAJA = "alta", "baja"


def guardar(conn: sqlite3.Connection, login: str, accion: str, quien: str,
            plataforma: str = "twitch", grupo: str = "argentinos") -> None:
    """Anota un alta o una baja. La última acción sobre un login es la que vale."""
    if accion not in (ALTA, BAJA):
        raise ValueError(f"accion {accion!r}")
    if plataforma not in PLATAFORMAS:
        raise ValueError(f"plataforma {plataforma!r}")
    conn.execute(
        """INSERT INTO streamers_extra (login, accion, plataforma, grupo, quien, ts)
           VALUES (?, ?, ?, ?, ?, datetime('now'))
           ON CONFLICT(login) DO UPDATE SET
               accion = excluded.accion, plataforma = excluded.plataforma,
               grupo = excluded.grupo, quien = excluded.quien, ts = excluded.ts""",
        (login.lower(), accion, plataforma, grupo, str(quien)),
    )
    conn.commit()


def olvidar(conn: sqlite3.Connection, login: str) -> None:
    """Saca la anotación: el streamer vuelve a valer lo que diga el YAML (o a no existir)."""
    conn.execute("DELETE FROM streamers_extra WHERE login = ?", (login.lower(),))
    conn.commit()


def anotados(conn: sqlite3.Connection) -> dict[str, dict]:
    """{login: {accion, plataforma, grupo, quien, ts}} de todo lo tocado por Telegram."""
    filas = conn.execute(
        "SELECT login, accion, plataforma, grupo, quien, ts FROM streamers_extra").fetchall()
    return {f[0]: {"accion": f[1], "plataforma": f[2], "grupo": f[3], "quien": f[4], "ts": f[5]}
            for f in filas}


def combinar(del_yaml: list[Streamer], conn: sqlite3.Connection) -> list[Streamer]:
    """La lista efectiva: el YAML más las altas de la DB, menos las bajas.

    Los agregados por Telegram entran con `permiso.experimento`, que es la política vigente (§1):
    nadie se suma sin permiso citado o sin marcar que es un experimento.
    """
    extra = anotados(conn)
    out = [s for s in del_yaml if extra.get(s.login, {}).get("accion") != BAJA]
    por_login = {s.login for s in out}
    for login, d in sorted(extra.items()):
        if d["accion"] != ALTA or login in por_login:
            continue
        out.append(Streamer(login=login, plataforma=d["plataforma"], fuentes=("reciente",),
                            grupo=d["grupo"], experimento=True))
    return out


def por_grupo(streamers: list[Streamer]) -> dict[str, list[Streamer]]:
    """Agrupados como los muestra /streamers, con el grupo efectivo de cada uno."""
    out: dict[str, list[Streamer]] = {}
    for s in streamers:
        out.setdefault(s.grupo or s.grupo_de("reciente"), []).append(s)
    for lista in out.values():
        lista.sort(key=lambda s: s.login)
    return dict(sorted(out.items(), key=lambda kv: (-len(kv[1]), kv[0])))


# ---- resolver un alta -------------------------------------------------------
# Antes de sumar a alguien hay que saber tres cosas: que el canal exista, que sea EL canal (no un
# slug libre con 9 seguidores, que ya pasó con Momo y Luquitas) y que tenga clips de la última
# semana. Sin clips recientes no aporta nada y solo gasta llamadas todos los días.

from dataclasses import dataclass, field  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


@dataclass
class Candidato:
    login: str
    plataforma: str
    nombre: str = ""
    seguidores: int | None = None   # Kick lo da; Twitch ya no con app token
    clips_7d: int = 0
    extra: str = ""

    def resumen(self) -> str:
        partes = [f"<b>{self.nombre or self.login}</b> (<code>{self.login}</code>) en {self.plataforma}"]
        if self.seguidores is not None:
            partes.append(f"{self.seguidores:,} seguidores".replace(",", "."))
        partes.append(f"{self.clips_7d} clips en 7 días")
        if self.extra:
            partes.append(self.extra)
        return " · ".join(partes)


@dataclass
class Resolucion:
    """`elegido` si hay uno claro; `opciones` si es ambiguo; `error` si no hay nada."""
    elegido: Candidato | None = None
    opciones: list[Candidato] = field(default_factory=list)
    error: str = ""


def _clips_7d_kick(kick, slug: str) -> int:
    desde = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        crudos = kick.get_clips(slug, 100, "view", "week")
    except Exception:
        return 0
    n = 0
    for d in crudos:
        creado = str(d.get("created_at") or "").replace("Z", "+00:00")
        try:
            if datetime.fromisoformat(creado).astimezone(timezone.utc) >= desde:
                n += 1
        except ValueError:
            continue
    return n


def _clips_7d_twitch(twitch, broadcaster_id: str) -> int:
    ahora = datetime.now(timezone.utc)
    try:
        return len(twitch.get_clips(broadcaster_id, ahora - timedelta(days=7), ahora, 100))
    except Exception:
        return 0


# Si el que coincide exacto tiene pocos clips, el nombre pedido probablemente no sea su handle y
# haya otro canal más conocido con ese nombre. Medido 2026-09-25: "momo" da un canal en Twitch con
# 7 clips que es un gato espacial en inglés, no el Momo argentino. Con clips de sobra (spreen 100,
# elxokas 100, vegetta777 98) no hay duda y no se pregunta nada.
CLIPS_SIN_DUDA = 20


def resolver(login: str, kick, twitch, clips_sin_duda: int = CLIPS_SIN_DUDA) -> Resolucion:
    """Busca el canal en las DOS plataformas y decide con los clips de la última semana.

    NO alcanza con "está en Kick": medido el 2026-09-25, `vegetta777` en Kick es un slug ocupado con
    166 seguidores y 0 clips, mientras el Vegetta de verdad está en Twitch; `momo` en Kick tiene 707
    seguidores y 0 clips. Con "Kick primero" a secas, las dos altas salían mal. Por eso la señal que
    decide es tener clips en 7 días, que además es lo que hace falta para que el bot lo use.

    - un solo candidato con clips → ese
    - varios con clips, o ninguno → se devuelven las opciones y elige la persona
    """
    login = login.strip().lower().lstrip("@")
    if not login:
        return Resolucion(error="Falta el nombre del streamer.")

    candidatos: list[Candidato] = []
    canal = kick.get_canal(login) if kick else None
    if canal and not canal["baneado"]:
        candidatos.append(Candidato(
            login=canal["slug"], plataforma="kick", nombre=canal["nombre"],
            seguidores=canal["seguidores"], clips_7d=_clips_7d_kick(kick, canal["slug"]),
            extra="verificado" if canal["verificado"] else ""))
    if twitch is not None:
        for u in twitch.get_users([login]):
            candidatos.append(Candidato(
                login=u["login"], plataforma="twitch", nombre=u["nombre"],
                clips_7d=_clips_7d_twitch(twitch, u["id"]), extra=u["descripcion"][:60]))

    con_clips = [c for c in candidatos if c.clips_7d > 0]
    if len(con_clips) == 1 and con_clips[0].clips_7d >= clips_sin_duda:
        return Resolucion(elegido=con_clips[0])
    if len(con_clips) == 1 and twitch is not None:
        # Pocos clips: puede no ser el canal que buscaban. Se muestran los parecidos también.
        otros = [Candidato(login=c["login"], plataforma="twitch", nombre=c["nombre"],
                           extra=c["juego"])
                 for c in twitch.search_channels(login, 8) if c["login"] != con_clips[0].login][:5]
        return Resolucion(opciones=con_clips + otros) if otros else Resolucion(elegido=con_clips[0])
    if len(con_clips) > 1:
        return Resolucion(opciones=con_clips)

    # Nadie con clips: si el nombre existe en algún lado, que decida la persona sabiendo que no
    # tiene nada reciente; si no existe en ningún lado, se ofrecen los parecidos de Twitch.
    if candidatos:
        return Resolucion(opciones=candidatos)
    if twitch is None:
        return Resolucion(error=f"No encontré <code>{login}</code> en Kick.")
    parecidos = [c for c in twitch.search_channels(login, 8) if c["login"] != login][:6]
    if not parecidos:
        return Resolucion(error=f"No existe <code>{login}</code> ni en Kick ni en Twitch.")
    return Resolucion(opciones=[Candidato(login=c["login"], plataforma="twitch", nombre=c["nombre"],
                                          extra=c["juego"]) for c in parecidos])
