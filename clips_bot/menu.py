"""Los teclados de /streamers y /agregar, y el parseo de lo que vuelve al apretar un botón.

Telegram limita el `callback_data` de cada botón a **64 bytes**, así que acá no viajan logins: viaja
`st:s:2:37` (grupo 2, streamer 37). Los índices son posiciones en la lista ordenada que arma
`registro.por_grupo`, y como el mensaje se re-dibuja en cada paso, alcanzan: si la lista cambió,
el siguiente toque ya trabaja sobre la nueva.
"""

from __future__ import annotations

POR_PAGINA = 12      # 6 filas de 2
COLUMNAS = 2
LIMITE_CALLBACK = 64  # bytes, lo que acepta Telegram

# Los emojis de cada grupo conocido; el resto cae en 📦.
ICONOS = {"evento": "🎮", "argentinos": "🇦🇷", "catalogo": "📚"}
NOMBRES = {"evento": "Dedsafío", "argentinos": "Argentinos", "catalogo": "Catálogo"}


def _cb(*partes) -> str:
    dato = ":".join(str(p) for p in partes)
    assert len(dato.encode()) <= LIMITE_CALLBACK, f"callback_data de {len(dato)} bytes: {dato}"
    return dato


def etiqueta_grupo(grupo: str, n: int, etiqueta: str = "") -> str:
    nombre = etiqueta or NOMBRES.get(grupo, grupo.replace("_", " ").capitalize())
    return f"{ICONOS.get(grupo, '📦')} {nombre} ({n})"


def teclado_grupos(grupos: dict[str, list], etiquetas: dict[str, str] | None = None) -> dict:
    """Primer nivel: un botón por carpeta, uno por fila."""
    etiquetas = etiquetas or {}
    filas = [[{"text": etiqueta_grupo(g, len(l), etiquetas.get(g, "")),
               "callback_data": _cb("st", "g", i, 0)}]
             for i, (g, l) in enumerate(grupos.items())]
    return {"inline_keyboard": filas}


def _si_no(v: bool) -> str:
    return "sí" if v else "no"


def teclado_streamers(gi: int, streamers: list, pagina: int, excluidos: dict,
                      carpeta: dict | None = None) -> dict:
    """Segundo nivel: los streamers de la carpeta, de a 2 por fila y 12 por página, y arriba los
    dos interruptores de la carpeta. Si está vacía, el botón para borrarla."""
    desde = pagina * POR_PAGINA
    visibles = streamers[desde:desde + POR_PAGINA]
    filas, fila = [], []
    if carpeta is not None:
        filas.append([
            {"text": f"🔴 En vivo: {_si_no(carpeta['en_vivo'])}", "callback_data": _cb("st", "v", gi)},
            {"text": f"📅 Diarios: {_si_no(carpeta['diarios'])}", "callback_data": _cb("st", "d", gi)},
        ])
        if not streamers:
            filas.append([{"text": "🗑 Borrar carpeta", "callback_data": _cb("st", "del", gi)}])
    for k, s in enumerate(visibles):
        i = desde + k
        if s.login in excluidos:
            # Los excluidos se ven pero no se tocan: el callback es un "no pasa nada" explícito.
            fila.append({"text": f"🚫 {s.login}", "callback_data": _cb("st", "x", i)})
        else:
            fila.append({"text": s.login, "callback_data": _cb("st", "s", gi, i)})
        if len(fila) == COLUMNAS:
            filas.append(fila)
            fila = []
    if fila:
        filas.append(fila)

    nav = []
    if pagina > 0:
        nav.append({"text": "◀️", "callback_data": _cb("st", "g", gi, pagina - 1)})
    if desde + POR_PAGINA < len(streamers):
        nav.append({"text": "▶️", "callback_data": _cb("st", "g", gi, pagina + 1)})
    if nav:
        filas.append(nav)
    filas.append([{"text": "⬅️ Volver", "callback_data": _cb("st", "r")}])
    return {"inline_keyboard": filas}


def teclado_streamer(gi: int, si: int, pagina: int, apodos: tuple = ()) -> dict:
    """Tercer nivel: qué hacer con ese streamer. El período va directo; después, la cantidad."""
    etiqueta = ", ".join(apodos) or "ninguno"
    etiqueta = etiqueta if len(etiqueta) <= 28 else etiqueta[:27] + "…"
    return {"inline_keyboard": [
        [{"text": "Últimos 7 días", "callback_data": _cb("st", "b", gi, si, "7")},
         {"text": "Últimos 30 días", "callback_data": _cb("st", "b", gi, si, "30")}],
        [{"text": "Viejos (más de 30 días)", "callback_data": _cb("st", "b", gi, si, "viejos")}],
        [{"text": "🔥 Lo que pegó en otros canales", "callback_data": _cb("st", "b", gi, si, "pego")}],
        [{"text": "🔎 Con palabra…", "callback_data": _cb("st", "w", gi, si)}],
        [{"text": f"🏷 Apodos: {etiqueta}", "callback_data": _cb("st", "ap", gi, si)}],
        [{"text": "📦 Mover a otra carpeta", "callback_data": _cb("st", "m", gi, si)}],
        [{"text": "⬅️ Volver", "callback_data": _cb("st", "g", gi, pagina)}],
    ]}


def teclado_periodo(token: str) -> dict:
    """/buscar sin período: de cuándo (el pedido queda guardado en bot_estado con `token`)."""
    from .telegram import PERIODOS_BUSCAR

    return {"inline_keyboard": [[{"text": texto, "callback_data": _cb("bu", "p", token, clave)}]
                                for clave, texto in PERIODOS_BUSCAR]}


def teclado_cantidad(token: str) -> dict:
    """Cuántos videos: 1, 3 o 5."""
    from .telegram import CANTIDADES_BUSCAR

    return {"inline_keyboard": [[{"text": str(n), "callback_data": _cb("bu", "c", token, n)}
                                 for n in CANTIDADES_BUSCAR]]}


def teclado_mover(gi: int, si: int, carpetas: list[tuple[str, str]]) -> dict:
    """A qué carpeta lo paso. `carpetas`: [(nombre, etiqueta)] en el orden del menú; la actual
    (gi) no aparece."""
    filas = [[{"text": f"{ICONOS.get(n, '📦')} {e}", "callback_data": _cb("st", "mv", gi, si, ci)}]
             for ci, (n, e) in enumerate(carpetas) if ci != gi]
    filas.append([{"text": "➕ Carpeta nueva", "callback_data": _cb("st", "mn", gi, si)}])
    filas.append([{"text": "⬅️ Volver", "callback_data": _cb("st", "s", gi, si)}])
    return {"inline_keyboard": filas}


def teclado_carpetas_alta(token: str, carpetas: list[tuple[str, str]]) -> dict:
    """/agregar: en qué carpeta va. Un botón por carpeta y "➕ Carpeta nueva"."""
    filas = [[{"text": f"{ICONOS.get(n, '📦')} {e}", "callback_data": _cb("add", "c", token, ci)}]
             for ci, (n, e) in enumerate(carpetas)]
    filas.append([{"text": "➕ Carpeta nueva", "callback_data": _cb("add", "cn", token)}])
    filas.append([{"text": "❌ No agregar", "callback_data": _cb("add", "n", token)}])
    return {"inline_keyboard": filas}


def teclado_confirmar(token: str) -> dict:
    """Los ✅/❌ de un alta. `token` es corto a propósito: el login no siempre entra en 64 bytes."""
    return {"inline_keyboard": [[
        {"text": "✅ Agregar", "callback_data": _cb("add", "y", token)},
        {"text": "❌ No", "callback_data": _cb("add", "n", token)},
    ]]}


def teclado_opciones(token_base: str, opciones: list) -> dict:
    """Cuando el nombre es ambiguo: un botón por candidato, más un ❌."""
    filas = [[{"text": f"{o.login} · {o.plataforma}"
                       + (f" · {o.clips_7d} clips" if o.clips_7d else " · sin clips"),
               "callback_data": _cb("add", "o", token_base, i)}]
             for i, o in enumerate(opciones)]
    filas.append([{"text": "❌ Ninguno", "callback_data": _cb("add", "n", token_base)}])
    return {"inline_keyboard": filas}


def teclado_destinos(chats: list[dict], faltan: list[dict]) -> dict:
    """Un botón por chat conocido, con ✅/⬜ según reciba o no la entrega de las 05:00.

    `faltan` son los permitidos que nunca le escribieron al bot: se muestran apagados y sin acción,
    porque Telegram NO deja que un bot escriba primero. Sin esto el destino fallaría callado.
    """
    filas = []
    for i, c in enumerate(chats):
        icono = "👥" if c["tipo"] in ("group", "supergroup") else "👤"
        marca = "✅" if c["activo"] else "⬜"
        nombre = c["nombre"] or c["chat_id"]
        filas.append([{"text": f"{marca} {icono} {nombre}",
                       "callback_data": _cb("dst", "t", i)}])
    for f in faltan:
        filas.append([{"text": f"🚫 👤 {f['nombre']} — falta su /start",
                       "callback_data": _cb("dst", "x")}])
    filas.append([{"text": "🔄 Actualizar", "callback_data": _cb("dst", "r")}])
    return {"inline_keyboard": filas}


def parse_callback(data: str) -> dict | None:
    """`st:s:2:37` → {'menu': 'st', 'accion': 's', 'args': [2, 37]}. None si no es de los nuestros."""
    from .telegram import PREFIJOS_BOTONES   # una sola lista: dos listas separadas ya se despegaron

    partes = data.split(":")
    if len(partes) < 2 or partes[0] not in PREFIJOS_BOTONES:
        return None
    args = []
    for p in partes[2:]:
        args.append(int(p) if p.lstrip("-").isdigit() else p)
    # `crudos`: los mismos, como texto. Los tokens hex de los botones (secrets.token_hex) a veces
    # son todos dígitos: "012345" pasado a int es 12345, y el botón buscaba un pedido que no existe.
    return {"menu": partes[0], "accion": partes[1], "args": args, "crudos": partes[2:]}
