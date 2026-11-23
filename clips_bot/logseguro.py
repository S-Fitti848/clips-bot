"""Nunca una clave ni un token en los logs (Santi, 2026-11-23).

El error del resumen de 24 h de Facebook escribía la URL entera, con `access_token=EAA…` de la página, cada 30 min; y
los cortes de Telegram dejaban `/bot<id>:<token>/getUpdates`. `tapar` reemplaza todo lo que parece una clave por `***`
y `instalar` le pone un formateador que tapa a todos los handlers del logger raíz (mensaje, argumentos y traceback).
"""
from __future__ import annotations

import logging
import re

TAPA = "***"

_PATRONES = (
    # parámetros de URL o de formulario con nombre de secreto
    (re.compile(r"(?i)\b(access_token|refresh_token|id_token|token|api_key|apikey|key|client_secret|secret|"
                r"password|signature|sig)=([^&\s\"'<>]+)"), r"\1=" + TAPA),
    (re.compile(r"/bot\d+:[A-Za-z0-9_-]+"), "/bot" + TAPA),                      # Telegram
    (re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{30,}"), TAPA),                       # token de Telegram suelto
    (re.compile(r"\bEAA[A-Za-z0-9]{20,}"), TAPA),                                 # Facebook / Meta
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), TAPA),                              # Google API key
    (re.compile(r"\bAQ\.[A-Za-z0-9_-]{30,}"), TAPA),                              # Google API key nueva
    (re.compile(r"\bya29\.[A-Za-z0-9._-]+"), TAPA),                               # Google OAuth
    (re.compile(r"\b1//[A-Za-z0-9_-]{30,}"), TAPA),                               # Google refresh token
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]+"), TAPA),                               # Anthropic
    (re.compile(r"\bsk_[A-Fa-f0-9]{30,}"), TAPA),                                 # ElevenLabs
    (re.compile(r"(?i)\b(Bearer|Authorization:?)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 " + TAPA),
    (re.compile(r"(?i)(\"?(?:x-goog-api-key|xi-api-key|x-api-key)\"?\s*[:=]\s*\"?)[^\s\"',}]+"), r"\1" + TAPA),
)


def tapar(texto: str) -> str:
    if not texto:
        return texto
    for patron, reemplazo in _PATRONES:
        texto = patron.sub(reemplazo, texto)
    return texto


class Formateador(logging.Formatter):
    """El formateador de siempre, pero lo que sale (con el traceback incluido) pasa por `tapar`."""

    def __init__(self, base: logging.Formatter | None = None):
        super().__init__()
        self.base = base or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return tapar(self.base.format(record))


def instalar(logger: logging.Logger | None = None) -> None:
    """Pone el formateador que tapa en todos los handlers (llamar después de basicConfig)."""
    logger = logger or logging.getLogger()
    for h in logger.handlers:
        if not isinstance(h.formatter, Formateador):
            h.setFormatter(Formateador(h.formatter))
