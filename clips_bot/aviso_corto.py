"""Mensajes cortos de cada video (Santi, 2026-11-20: "tienen demasiado texto y no los leo").

A Telegram va SOLO el video con: título, hashtags y una línea de resumen ("✅ 11/13 · US$ 0,31 · sale 11:00"). Si
necesita aprobación, ✅ / ❌ y una línea con el motivo principal. Todo el detalle (reglas que fallaron, correcciones,
puntajes, fotos, textos para copiar) se guarda en `bot_estado` (`detalle:<clip_id>`) y sale con el botón "📋 Detalle"
o con /detalle. Los avisos e informes: como mucho 3 líneas (`recortar`); el resto, también detrás de 📋.
"""

from __future__ import annotations

import html
import re
import secrets

DETALLE = "detalle:"          # bot_estado: el detalle completo de un video o de un aviso (HTML)
ULTIMO = "detalle_ultimo"     # bot_estado: el último guardado (para /detalle a secas)
MAX_LINEAS = 3
DB = None                     # la base donde se guarda el detalle de los avisos (None = la del bot; los tests la cambian)


def plata(usd: float | None) -> str:
    return f"US$ {float(usd or 0):.2f}".replace(".", ",")


def resumen(ok: int | None, total: int | None, costo: float | None, hora: str = "",
            retenido: bool = False, etiqueta: str = "") -> str:
    """✅ 11/13 · US$ 0,31 · sale 11:00 (⏸ si espera el OK). `etiqueta` adelante ("💻 Tecnología"): Santi, 2026-11-23,
    no se dio cuenta de que le había llegado el de tecnología porque el mensaje corto no decía cuál era."""
    partes = [etiqueta] if etiqueta else []
    if total:
        partes.append(f"{'⏸' if retenido else '✅'} {ok}/{total}")
    elif retenido:
        partes.append("⏸")
    if costo is not None:
        partes.append(plata(costo))
    if retenido:
        partes.append("espera tu OK")
    elif hora:
        partes.append(f"sale {hora}")
    return " · ".join(partes)


def motivo_retenido(canal: str, fallas: list[dict], bajo: bool) -> str:
    """La razón principal, en una línea."""
    from . import calidad

    if bajo:
        bl = calidad.bloqueantes(canal, fallas)
        f = (bl or fallas or [None])[0]
        if f:
            r = calidad.por_id(canal).get(f.get("id"))
            que = (r.titulo if r else "") or f.get("que") or ""
            return f"Motivo: {f.get('id')} {que}".strip()[:150]
        ok, total = calidad.puntaje(canal, fallas)
        return f"Motivo: estándar {ok}/{total} (mínimo {calidad.minimo(canal)})"
    return "Motivo: Pequeña Historia no se publica sola"


def caption(titulo: str, hashtags: list[str] | str, linea: str, motivo: str = "") -> str:
    tags = hashtags if isinstance(hashtags, str) else " ".join(hashtags or [])
    return "\n".join(x for x in (titulo, tags, linea, motivo) if x)[:1024]


def boton(clave: str) -> dict:
    return {"text": "📋 Detalle", "callback_data": f"det:{clave}"[:64]}


def guardar(conn, clave: str, detalle_html: str) -> None:
    from . import db

    db.set_valor(conn, DETALLE + clave, detalle_html)
    db.set_valor(conn, ULTIMO, clave)


def leer(conn, clave: str = "") -> str | None:
    from . import db

    clave = clave or db.get_valor(conn, ULTIMO) or ""
    return db.get_valor(conn, DETALLE + clave) if clave else None


def con_detalle(teclado: dict | None, clave: str) -> dict:
    filas = [list(f) for f in (teclado or {}).get("inline_keyboard") or []]
    filas.append([boton(clave)])
    return {"inline_keyboard": filas}


def recortar(texto: str, maximo: int = MAX_LINEAS) -> tuple[str, str]:
    """(las primeras `maximo` líneas con contenido, el resto). Sin resto, el resto es ""."""
    lineas = [x for x in texto.split("\n") if x.strip()]
    if len(lineas) <= maximo:
        return "\n".join(lineas), ""
    corto = "\n".join(lineas[:maximo])
    # que no quede una etiqueta abierta (<pre>, <b>…) en el corte
    for tag in ("pre", "code", "b", "i"):
        if corto.count(f"<{tag}>") > corto.count(f"</{tag}>"):
            corto += f"</{tag}>"
    return corto, texto


def mandar_aviso(tg, chat, conn, texto: str, teclado: dict | None = None) -> dict:
    """Un aviso o informe de 3 líneas como mucho; si es más largo, el resto va detrás de 📋 Detalle."""
    corto, todo = recortar(texto)
    if todo and conn is not None:
        clave = "a" + secrets.token_hex(4)
        guardar(conn, clave, todo)
        teclado = con_detalle(teclado, clave)
    return tg.send_message(chat, corto, teclado=teclado) if teclado else tg.send_message(chat, corto)


def plano(texto_html: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", texto_html or ""))
