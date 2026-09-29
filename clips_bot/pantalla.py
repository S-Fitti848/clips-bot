"""§3: datos personales en pantalla (OCR, sin LLM).

Por qué existe: el 2026-09-23 casi se publica un clip de hasvik donde la categoría decía Minecraft
(así que pasó el filtro del evento) pero lo que se veía era su navegador en un checkout, con nombre,
mail y dirección postal de un tercero. Nada en el pipeline miraba QUÉ hay en pantalla.

Cómo: tesseract sobre 6-8 frames muestreados, y después regex + listas de palabras sobre el texto.
Sin LLM: es barato, corre offline y no depende de cuota. Los falsos positivos se aceptan (§4, misma
política que el filtro de música): tirar un clip bueno sale mucho más barato que publicar el mail o
la dirección de alguien.

Límites conocidos:
  - tesseract lee mal el texto chico o sobre fondo con textura (chat de Twitch, HUD de un juego).
    Eso juega a favor acá: lo que nos importa (un formulario, un checkout) es texto grande y limpio.
  - El modelo `spa` no siempre está instalado; con `eng` alcanza porque las señales son mails,
    números y palabras que se escriben casi igual, y todo se compara sin tildes.
  - Si tesseract no está instalado, la capa se saltea con un warning (no corta la corrida).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MOTIVO = "datos_en_pantalla"

# Un mail es la señal más limpia: casi no hay falsos positivos y es lo más sensible que se publica.
RE_MAIL = re.compile(r"[a-z0-9._%+-]{2,}@[a-z0-9.-]{2,}\.[a-z]{2,}", re.I)
# Teléfonos: 9+ dígitos seguidos, o con prefijo internacional y separadores. Los relojes y las
# coordenadas de un juego no llegan a esa cantidad de dígitos juntos.
RE_TELEFONO = re.compile(r"(?:\+\d{1,3}[\s.\-()]{0,3})?(?:\d[\s.\-()]{0,2}){8,14}\d")
# Tarjetas: 13-19 dígitos en grupos.
RE_TARJETA = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")


@dataclass(frozen=True)
class Hallazgo:
    tipo: str     # mail | telefono | tarjeta | pago | direccion
    muestra: str  # el texto que disparó, recortado (para revisar por qué se descartó)


@dataclass(frozen=True)
class Pantalla:
    """`motivo` vacío = no dispara nada. Se guarda siempre, dispare o no, para poder calibrar."""
    motivo: str = ""
    hallazgos: tuple[Hallazgo, ...] = ()
    frames_leidos: int = 0
    caracteres: int = 0  # cuánto texto leyó tesseract en total (0 = no leyó nada, sospechá del OCR)
    salteado: str = ""   # por qué no corrió (tesseract ausente, capa apagada)

    @property
    def hay(self) -> bool:
        return bool(self.motivo)

    def a_dict(self) -> dict:
        return {"motivo": self.motivo, "frames_leidos": self.frames_leidos,
                "caracteres": self.caracteres, "salteado": self.salteado,
                "hallazgos": [{"tipo": h.tipo, "muestra": h.muestra} for h in self.hallazgos]}


class OcrNoDisponible(RuntimeError):
    pass


def find_tesseract() -> str:
    """TESSERACT_CMD → PATH → instalaciones típicas de Windows."""
    exe = "tesseract" + (".exe" if os.name == "nt" else "")
    if d := os.getenv("TESSERACT_CMD"):
        if Path(d).exists():
            return d
    if p := shutil.which("tesseract"):
        return p
    if os.name == "nt":
        candidatos = [
            Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / exe,
            Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / exe,
            Path(os.getenv("USERPROFILE", "")) / exe,
        ]
        for p in candidatos:
            if p.exists():
                return str(p)
    raise OcrNoDisponible(
        "No encuentro tesseract. Windows: winget install UB-Mannheim.TesseractOCR · "
        "Pi/Debian: sudo apt install tesseract-ocr · o definí TESSERACT_CMD con la ruta del binario."
    )


def _normalizar(texto: str) -> str:
    """minúsculas, sin tildes, todo lo que no es letra/número → espacio (igual que en candidates)."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip() + " "


def _muestra(texto: str, n: int = 40) -> str:
    limpio = " ".join(texto.split())
    return limpio[:n] + ("…" if len(limpio) > n else "")


def buscar(texto: str, palabras_pago: tuple[str, ...], palabras_direccion: tuple[str, ...],
           buscar_telefonos: bool = True, palabras_contexto: tuple[str, ...] = ()) -> list[Hallazgo]:
    """Todos los hallazgos de un texto. Devuelve la lista entera para poder mirar los falsos positivos.

    Los mails y las palabras de pago/dirección valen solos. Los NÚMEROS (teléfono, tarjeta) solo
    cuentan si además hay una palabra de contexto en ese mismo frame: medido 2026-09-23 sobre 26
    clips reales, el regex de teléfono solo (9+ dígitos) daba 3 falsos positivos y 0 aciertos —
    era el contador de dinero de Vegetta ("17.764.293.15"), un id de Minecraft y un timer. Un
    número que importa está etiquetado; el HUD de un juego no lo está.
    """
    out: list[Hallazgo] = []
    normalizado = _normalizar(texto)
    for m in RE_MAIL.findall(texto):
        out.append(Hallazgo("mail", _muestra(m)))
    hay_contexto = any(_normalizar(p) in normalizado for p in palabras_contexto if p.strip())
    if hay_contexto:
        for regex, tipo in ((RE_TARJETA, "tarjeta"), (RE_TELEFONO, "telefono")):
            if tipo == "telefono" and not buscar_telefonos:
                continue
            for m in regex.findall(texto):
                digitos = sum(c.isdigit() for c in m)
                if digitos >= (13 if tipo == "tarjeta" else 9):
                    out.append(Hallazgo(tipo, _muestra(m)))
    for palabras, tipo in ((palabras_pago, "pago"), (palabras_direccion, "direccion")):
        for p in palabras:
            if p.strip() and _normalizar(p) in normalizado:
                out.append(Hallazgo(tipo, p))
    return out


# ---- textos escritos: títulos y descripciones (2026-09-29) -----------------------------------
# Un clip real de Kick se titulaba "si davo es +54 11 3396-6858": el OCR mira la pantalla, no los
# títulos. En un texto escrito las reglas son otras: un teléfono con prefijo internacional se
# reconoce solo (en la pantalla, un contador de un juego no lleva "+54"), y las palabras sueltas de
# dirección del OCR ("calle", "piso") en un título son falsos positivos seguros ("en la calle").

MOTIVO_TITULO = "datos personales en el título"
TAPADO = "[dato personal]"
# Con prefijo internacional: "+54 11 3396-6858", "+1 (555) 123-4567".
RE_TEL_ESCRITO = re.compile(r"\+\d{1,3}[\s.\-()]*(?:\d[\s.\-()]{0,2}){7,13}\d")
# Calle/avenida + nombre + número: "Av. Corrientes 1234", "calle Falsa 123".
RE_DIRECCION = re.compile(
    r"\b(?:calle|av(?:enida)?\.?|pasaje|bv\.?|boulevard|diagonal)\s+"
    r"[A-Za-zÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ .]{1,30}?\s\d{2,5}\b", re.I)
DIRECCION_ESCRITA = ("codigo postal", "direccion de envio", "shipping address", "zip code", "ship to")
CONTEXTO_ESCRITO = ("tel", "telefono", "phone", "celular", "cel", "whatsapp", "wsp", "wpp",
                    "contacto", "llamame", "llamen", "escribime", "dni", "cbu", "alias")


def datos_en_texto(texto: str) -> list[Hallazgo]:
    """Datos personales en un texto ESCRITO (título del clip o del stream, título o descripción que
    genera Gemini): mails, teléfonos con prefijo internacional o con palabra de contexto, tarjetas
    con contexto, y direcciones con calle y número."""
    if not texto:
        return []
    out = [Hallazgo("mail", _muestra(m)) for m in RE_MAIL.findall(texto)]
    for m in RE_TEL_ESCRITO.findall(texto):
        if sum(c.isdigit() for c in m) >= 9:
            out.append(Hallazgo("telefono", _muestra(m)))
    normalizado = _normalizar(texto)
    if any(_normalizar(p) in normalizado for p in CONTEXTO_ESCRITO):
        for regex, tipo, minimo in ((RE_TARJETA, "tarjeta", 13), (RE_TELEFONO, "telefono", 9)):
            for m in regex.findall(texto):
                if sum(c.isdigit() for c in m) >= minimo and not any(h.tipo == tipo for h in out):
                    out.append(Hallazgo(tipo, _muestra(m)))
    for m in RE_DIRECCION.finditer(texto):
        out.append(Hallazgo("direccion", _muestra(m.group(0))))
    for p in DIRECCION_ESCRITA:
        if _normalizar(p) in normalizado:
            out.append(Hallazgo("direccion", p))
    return out


def tapar_datos(texto: str) -> str:
    """El texto con los datos personales reemplazados por "[dato personal]". Es lo que va a Gemini
    (título original del clip, transcripción): así no los puede copiar en lo que escribe."""
    if not texto:
        return texto
    salida = RE_MAIL.sub(TAPADO, texto)
    salida = RE_TEL_ESCRITO.sub(lambda m: TAPADO if sum(c.isdigit() for c in m.group(0)) >= 9
                                else m.group(0), salida)
    salida = RE_DIRECCION.sub(TAPADO, salida)
    if any(_normalizar(p) in _normalizar(salida) for p in CONTEXTO_ESCRITO):
        salida = RE_TELEFONO.sub(lambda m: TAPADO if sum(c.isdigit() for c in m.group(0)) >= 9
                                 else m.group(0), salida)
    return salida


def leer_frames(video: Path, n_frames: int, idioma: str = "eng", cmd: str | None = None) -> list[str]:
    """Texto de n_frames muestreados entre el 5 % y el 95 % del clip."""
    import cv2
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = cmd or find_tesseract()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise OcrNoDisponible(f"OpenCV no puede abrir {video}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    textos: list[str] = []
    try:
        for i in range(n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (0.05 + 0.9 * i / max(n_frames - 1, 1))))
            ok, img = cap.read()
            if not ok:
                continue
            gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            try:
                textos.append(pytesseract.image_to_string(gris, lang=idioma))
            except pytesseract.TesseractError as e:  # idioma que no está instalado, etc.
                raise OcrNoDisponible(f"tesseract falló: {e}") from e
    finally:
        cap.release()
    return textos


def detectar_datos(video: Path, cfg, cmd: str | None = None) -> Pantalla:
    """Capa completa. Nunca levanta por falta de tesseract: devuelve Pantalla(salteado=...)."""
    if not cfg.activo:
        return Pantalla(salteado="capa apagada en settings.yaml")
    try:
        textos = leer_frames(video, cfg.frames_muestra, cfg.idioma, cmd)
    except (OcrNoDisponible, ImportError) as e:
        log.warning("OCR salteado: %s", e)
        return Pantalla(salteado=str(e))

    hallazgos: list[Hallazgo] = []
    for t in textos:
        hallazgos += buscar(t, cfg.palabras_pago, cfg.palabras_direccion, cfg.buscar_telefonos,
                            cfg.palabras_contexto)
    # sin repetir: el mismo mail en 8 frames es un hallazgo, no ocho
    unicos: list[Hallazgo] = []
    for h in hallazgos:
        if h not in unicos:
            unicos.append(h)
    tipos = sorted({h.tipo for h in unicos})
    motivo = ""
    if unicos:
        detalle = ", ".join(f"{h.tipo}: {h.muestra}" for h in unicos[:4])
        motivo = f"{'/'.join(tipos)} en pantalla ({detalle})"
    return Pantalla(motivo=motivo, hallazgos=tuple(unicos), frames_leidos=len(textos),
                    caracteres=sum(len(t) for t in textos))
