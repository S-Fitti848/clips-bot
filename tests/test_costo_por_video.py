"""Santi, 2026-11-19 (US$ 2,68 en dos videos de Así Nació que no salieron): Sonnet solo para el guion, Haiku para el
resto y las correcciones, caché de prompts, y como mucho 4 pedidos de corrección por video."""
import json
from types import SimpleNamespace

import pytest

from clips_bot import claude, correcciones


def test_sonnet_solo_para_el_guion_de_asi_nacio():
    S, H = claude.SONNET, claude.HAIKU
    assert claude.modelo_para("marcas.escribir_guion", S) == S
    for f in ("marcas.revisar_visual", "director.dirigir", "dibujos.dibujar", "marcas.elegir_gancho",
              "reemplazo.chequear", "marcas.completar_v3"):
        assert claude.modelo_para(f, S) == H, f
    assert claude.modelo_para("correcciones.corregir", S) == H        # todos los canales
    assert claude.modelo_para("efemerides.escribir_guion", S) == S     # Pequeña Historia sigue igual
    assert claude.modelo_para("marcas.escribir_guion", H) == H         # nunca sube


def test_entrada_equivalente_con_cache():
    u = SimpleNamespace(input_tokens=1000, cache_creation_input_tokens=4000, cache_read_input_tokens=20000)
    assert claude.entrada_equivalente(claude.SONNET, u) == 1000 + 5000 + 1000
    assert claude.entrada_equivalente(claude.HAIKU, u) == 1000 + 5000 + 2000


class _Falso:
    def __init__(self):
        self.pedidos = []

    def json(self, sistema, prompt, schema, temperatura=0.7, **kw):
        self.pedidos.append(prompt)
        return json.dumps({"cambios": [], "sacar": [], "campos": []})


def test_tope_de_4_correcciones_por_video():
    correcciones.reiniciar()
    c = _Falso()
    schema = {"type": "OBJECT", "properties": {"escenas": {"type": "ARRAY", "items": {"type": "OBJECT"}}}}
    for _ in range(4):
        correcciones.corregir(c, "s", "p", {"escenas": []}, ["x"], schema, "escenas")
    with pytest.raises(correcciones.TopeCorrecciones):
        correcciones.corregir(c, "s", "p", {"escenas": []}, ["x"], schema, "escenas")
    assert len(c.pedidos) == 4
    correcciones.reiniciar()
    assert correcciones.quedan() == 4


def test_el_sistema_va_con_cache_control():
    visto = {}

    class _Api:
        def create(self, **pedido):
            visto.update(pedido)
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                         cache_creation_input_tokens=0, cache_read_input_tokens=0),
                                   model=pedido["model"], stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text="{}")])

    falso = SimpleNamespace(messages=_Api(), beta=SimpleNamespace(messages=_Api()))
    c = claude.ClaudeClient("x", claude.HAIKU, cliente=falso)
    c.json("REGLAS FIJAS", "pedido", {"type": "OBJECT", "properties": {}})
    assert visto["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert visto["system"][0]["text"] == "REGLAS FIJAS"
