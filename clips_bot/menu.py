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


def etiqueta_grupo(grupo: str, n: int) -> str:
    return f"{ICONOS.get(grupo, '📦')} {NOMBRES.get(grupo, grupo.capitalize())} ({n})"


def teclado_grupos(grupos: dict[str, list]) -> dict:
    """Primer nivel: un botón por grupo, uno por fila."""
    filas = [[{"text": etiqueta_grupo(g, len(l)), "callback_data": _cb("st", "g", i, 0)}]
             for i, (g, l) in enumerate(grupos.items())]
    return {"inline_keyboard": filas}


def teclado_streamers(gi: int, streamers: list, pagina: int, excluidos: dict) -> dict:
    """Segundo nivel: los streamers del grupo, de a 2 por fila y 12 por página."""
    desde = pagina * POR_PAGINA
    visibles = streamers[desde:desde + POR_PAGINA]
    filas, fila = [], []
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


def teclado_streamer(gi: int, si: int, pagina: int) -> dict:
    """Tercer nivel: qué hacer con ese streamer."""
    return {"inline_keyboard": [
        [{"text": "Últimos 7 días", "callback_data": _cb("st", "b", gi, si, 7)},
         {"text": "Últimos 30 días", "callback_data": _cb("st", "b", gi, si, 30)}],
        [{"text": "🔎 Con palabra…", "callback_data": _cb("st", "w", gi, si)}],
        [{"text": "⬅️ Volver", "callback_data": _cb("st", "g", gi, pagina)}],
    ]}


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


def parse_callback(data: str) -> dict | None:
    """`st:s:2:37` → {'menu': 'st', 'accion': 's', 'args': [2, 37]}. None si no es de los nuestros."""
    partes = data.split(":")
    if len(partes) < 2 or partes[0] not in ("st", "add"):
        return None
    args = []
    for p in partes[2:]:
        args.append(int(p) if p.lstrip("-").isdigit() else p)
    return {"menu": partes[0], "accion": partes[1], "args": args}
