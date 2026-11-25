"""Santi, 2026-11-25: el git pull trajo `fotos_primero` y la escucha vieja (código viejo en memoria) se cayó al releer
settings.yaml. Un proceso andando sigue con la última configuración buena; al arrancar, el error sale igual."""
from __future__ import annotations

import shutil

import pytest

from clips_bot import config


def test_una_clave_nueva_no_tumba_un_proceso_andando(tmp_path):
    ruta = tmp_path / "settings.yaml"
    shutil.copy(config.CONFIG_DIR / "settings.yaml", ruta)
    buena = config.load_settings(ruta)
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("efemerides:\n", "efemerides:\n  clave_del_futuro: 1\n", 1),
                    encoding="utf-8")
    assert config.load_settings(ruta) is buena
    config._ULTIMA_BUENA.clear()
    with pytest.raises(config.ConfigError):        # al arrancar, sin última buena: sale (y frena el despliegue)
        config.load_settings(ruta)


def test_el_despliegue_prueba_antes_de_actualizar():
    s = (config.CONFIG_DIR.parent / "deploy" / "desplegar.sh").read_text(encoding="utf-8")
    assert s.index("chequeo-arranque ") < s.index("git merge")
    assert not any(linea.startswith("git pull") for linea in s.splitlines())
    assert b"\r" not in (config.CONFIG_DIR.parent / "deploy" / "desplegar.sh").read_bytes()
