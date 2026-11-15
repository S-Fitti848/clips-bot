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
- en `cambios`, cada {item} que cambies, ENTERO y con su número (`indice`, desde 1, y `nuevo` false);
  un {item} nuevo solo si falta: `nuevo` true e `indice` = después de qué número va (0 = al principio);
- en `sacar`, los números de los que sobran;
- en `campos`, solo los campos generales que haya que tocar: `campo` y su `valor` en JSON (si ninguno, vacío).
No cambies lo que está bien. Todas las reglas de arriba siguen valiendo."""


def sin_enums(s):
    """Una copia del schema sin `enum` (los valores los valida después el código)."""
    if isinstance(s, dict):
        return {k: sin_enums(v) for k, v in s.items() if k != "enum"}
    if isinstance(s, list):
        return [sin_enums(x) for x in s]
    return s


def schema_parche(schema: dict, lista: str) -> dict:
    """El schema de la respuesta: cambios / agregar / sacar / campos, sacado del schema del guion."""
    # Sin enums (2026-11-15): con ellos la gramática de Claude pasaba su tope en Así Nació. Lo que vuelve
    # se valida igual con las reglas del guion.
    item = sin_enums(schema["properties"][lista]["items"])
    generales = {k: sin_enums(v) for k, v in schema["properties"].items() if k != lista}
    return {
        "type": "OBJECT",
        "properties": {
            # Una sola lista (2026-11-15): con el {item} dos veces (cambios y agregar) la gramática de Claude
            # pasaba su tope con las escenas de Así Nació ("compiled grammar is too large").
            "cambios": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "indice": {"type": "INTEGER"}, "nuevo": {"type": "BOOLEAN"}, "item": item},
                "required": ["indice", "nuevo", "item"]}},
            "sacar": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            # campos generales como lista (2026-11-15): un objeto con todos opcionales pasaba el tope de la
            # gramática. `valor` es el JSON del campo (texto, número, lista u objeto).
            "campos": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "campo": {"type": "STRING", "enum": list(generales)}, "valor": {"type": "STRING"}},
                "required": ["campo", "valor"]}},
        },
        "required": ["cambios", "sacar", "campos"],
    }


def aplicar(d: dict, parche: dict, lista: str) -> dict:
    """El guion con el parche aplicado (sin tocar el original)."""
    out = copy.deepcopy(d)
    items = list(out.get(lista) or [])
    agregados = [{"despues_de": c.get("indice"), "item": c.get("item")}
                 for c in parche.get("cambios") or [] if c.get("nuevo")]
    for c in parche.get("cambios") or []:
        if c.get("nuevo"):
            continue
        k = c.get("indice")
        if isinstance(k, int) and 1 <= k <= len(items) and isinstance(c.get("item"), dict):
            items[k - 1] = c["item"]
    sacar = {k for k in parche.get("sacar") or [] if isinstance(k, int)}
    nuevos: dict[int, list] = {}
    for a in list(parche.get("agregar") or []) + agregados:
        k = a.get("despues_de")
        if isinstance(k, int) and isinstance(a.get("item"), dict):
            nuevos.setdefault(max(0, min(k, len(items))), []).append(a["item"])
    armado = list(nuevos.get(0, []))
    for k, it in enumerate(items, 1):
        if k not in sacar:
            armado.append(it)
        armado += nuevos.get(k, [])
    out[lista] = armado
    campos = parche.get("campos") or {}
    if isinstance(campos, list):
        lista_campos = {}
        for c in campos:
            if not isinstance(c, dict) or not c.get("campo"):
                continue
            v = c.get("valor")
            try:
                v = json.loads(v) if isinstance(v, str) else v
            except ValueError:
                pass
            lista_campos[c["campo"]] = v
        campos = lista_campos
    for k, v in campos.items():
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
             sorted(c.get("campo", "") if isinstance(c, dict) else c for c in (parche.get("campos") or [])))
    return aplicar(d, parche, lista)
