"""Pedidos HTTP con tope de tiempo TOTAL (2026-10-30, Santi: "que nunca más quede colgado horas").

El `timeout` de requests es entre bytes, no total: un servidor que manda de a poco, o un socket que
queda medio abierto, puede tener un pedido andando horas sin que salte. `SesionConTope` corre cada
pedido en un hilo y, si pasa el tope, levanta `TiempoAgotado` y sigue (el hilo queda suelto y muere
solo cuando el socket se cierra). Lo usan todos los clientes de YouTube.
"""

from __future__ import annotations

import threading

import requests

TOPE_S = 120          # cualquier pedido común (listar, renovar el token, consultar estado)
TOPE_SUBIDA_S = 900   # el PUT/POST del video entero (20-40 MB desde la Pi)
TIMEOUT_REQUESTS = (10, 60)   # (conexión, entre bytes) si quien llama no dice otro


class TiempoAgotado(requests.Timeout):
    """El pedido pasó el tope total. Es un `requests.Timeout`: quien ya los atrapa, sigue igual."""


class SesionConTope(requests.Session):
    def __init__(self, tope_s: float = TOPE_S, tope_subida_s: float = TOPE_SUBIDA_S):
        super().__init__()
        self.tope_s = tope_s
        self.tope_subida_s = tope_subida_s

    def request(self, method, url, *args, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT_REQUESTS)
        con_archivo = kwargs.get("data") is not None and not isinstance(kwargs.get("data"), (dict, str, bytes))
        tope = self.tope_subida_s if (method.upper() == "PUT" or con_archivo) else self.tope_s
        resultado: dict = {}

        def correr():
            try:
                resultado["r"] = super(SesionConTope, self).request(method, url, *args, **kwargs)
            except BaseException as e:   # se relanza en el hilo de quien llamó
                resultado["e"] = e

        hilo = threading.Thread(target=correr, daemon=True)
        hilo.start()
        hilo.join(tope)
        if hilo.is_alive():
            raise TiempoAgotado(f"{method} {str(url)[:80]}: no terminó en {tope:.0f} s (tope total)")
        if "e" in resultado:
            raise resultado["e"]
        return resultado["r"]
