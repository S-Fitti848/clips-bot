"""Corregir SOLO lo que falla de un guion (Santi, 2026-11-15: "cuando la validación rechace una frase o escena,
no reescribas el guion entero: pedile a Claude que corrija solo esa frase o escena, con el resto como contexto").

Vale para Así Nació (las escenas) y Pequeña Historia (las frases). El modelo devuelve solo los cambios: los
ítems de la lista que reescribe (enteros, con su número), los que agrega o saca, y los campos generales que
toque. Así la respuesta es corta (barata) y lo que estaba bien no se rompe. Quien llama vuelve a validar y,
si la corrección puntual falla CORRECCIONES_MAX veces seguidas, reescribe el guion entero como antes."""

from __future__ import annotations

import copy
import json
import logging

log = logging.getLogger(__name__)

CORRECCIONES_MAX = 3

INSTRUCCION = """

CORRECCIÓN PUNTUAL. Te paso un guion que NO pasó la revisión y la lista de errores. Corregí SOLO lo que
falla, con el resto del guion como contexto (que siga encajando con lo de antes y lo de después):
- en `cambios`, cada {item} que cambies, ENTERO y con su número (`indice`, desde 1);
- en `agregar`, un {item} nuevo solo si falta (después de qué número va: `despues_de`, 0 = al principio);
- en `sacar`, los números de los que sobran;
- en `campos`, solo los campos generales que haya que tocar (si ninguno, vacío).
No cambies lo que está bien. Todas las reglas de arriba siguen valiendo."""


def schema_parche(schema: dict, lista: str) -> dict:
    """El schema de la respuesta: cambios / agregar / sacar / campos, sacado del schema del guion."""
    item = schema["properties"][lista]["items"]
    generales = {k: v for k, v in schema["properties"].items() if k != lista}
    return {
        "type": "OBJECT",
        "properties": {
            "cambios": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "indice": {"type": "INTEGER"}, "item": item}, "required": ["indice", "item"]}},
            "agregar": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "despues_de": {"type": "INTEGER"}, "item": item}, "required": ["despues_de", "item"]}},
            "sacar": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            "campos": {"type": "OBJECT", "properties": generales, "required": []},
        },
        "required": ["cambios", "agregar", "sacar", "campos"],
    }


def aplicar(d: dict, parche: dict, lista: str) -> dict:
    """El guion con el parche aplicado (sin tocar el original)."""
    out = copy.deepcopy(d)
    items = list(out.get(lista) or [])
    for c in parche.get("cambios") or []:
        k = c.get("indice")
        if isinstance(k, int) and 1 <= k <= len(items) and isinstance(c.get("item"), dict):
            items[k - 1] = c["item"]
    sacar = {k for k in parche.get("sacar") or [] if isinstance(k, int)}
    nuevos: dict[int, list] = {}
    for a in parche.get("agregar") or []:
        k = a.get("despues_de")
        if isinstance(k, int) and isinstance(a.get("item"), dict):
            nuevos.setdefault(max(0, min(k, len(items))), []).append(a["item"])
    armado = list(nuevos.get(0, []))
    for k, it in enumerate(items, 1):
        if k not in sacar:
            armado.append(it)
        armado += nuevos.get(k, [])
    out[lista] = armado
    for k, v in (parche.get("campos") or {}).items():
        if v not in (None, "", [], {}):
            out[k] = v
    return out


def corregir(cliente, sistema: str, pedido: str, d: dict, errores: list[str], schema: dict, lista: str,
             item: str = "escena") -> dict:
    """Un pedido de corrección puntual. Devuelve el guion corregido (todavía sin validar)."""
    prompt = (pedido + "\n\nEL GUION (" + lista + " numeradas desde 1):\n"
              + json.dumps(d, ensure_ascii=False) + "\n\nERRORES:\n- " + "\n- ".join(errores))
    parche = json.loads(cliente.json(sistema + INSTRUCCION.replace("{item}", item), prompt,
                                     schema_parche(schema, lista), 0.4))
    if lista in parche and "cambios" not in parche:     # devolvió el guion entero: se usa tal cual
        return parche
    log.info("corrección puntual: %d cambios, %d nuevos, %d afuera, campos %s",
             len(parche.get("cambios") or []), len(parche.get("agregar") or []), len(parche.get("sacar") or []),
             sorted((parche.get("campos") or {}).keys()))
    return aplicar(d, parche, lista)
