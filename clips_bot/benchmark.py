"""Cuánto tarda un clip completo en esta máquina, etapa por etapa.

Existe para el deploy en la Raspberry Pi 4 (aarch64, con undervoltage confirmado): antes de poner
el timer hay que saber si un clip entra en tiempo, y si `faster-whisper small` es viable en ARM o
hay que bajar a `base`. Con `--modelos small,base` transcribe con los dos y deja los .srt al lado
para comparar la calidad a ojo, que es lo único que importa acá (no hay ground truth).

No descarga nada: usa los mp4 que ya están en output/raw/. Así el número no depende de la red.
"""

from __future__ import annotations

import json
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import layout as lay
from . import pantalla as pant
from . import subtitles as sub
from .config import Settings
from .media import probe
from .render import renderizar

LIMITE_S = 300.0  # 5 min por clip: arriba de esto no da para la corrida diaria


@dataclass
class Medicion:
    clip_id: str
    duracion_s: float = 0.0
    etapas: dict[str, float] = field(default_factory=dict)
    layout: str = ""
    palabras: dict[str, int] = field(default_factory=dict)  # por modelo de Whisper

    @property
    def total(self) -> float:
        return sum(self.etapas.values())

    def por_segundo(self) -> float:
        """Segundos de proceso por segundo de video: el número que se compara entre máquinas."""
        return self.total / self.duracion_s if self.duracion_s else 0.0


def _cronometrar(etapas: dict[str, float], nombre: str):
    class _Ctx:
        def __enter__(self):
            self.t0 = time.perf_counter()
            return self

        def __exit__(self, *_):
            etapas[nombre] = round(time.perf_counter() - self.t0, 2)
            return False

    return _Ctx()


def medir_clip(raw: Path, cfg: Settings, modelos: list[str], destino: Path,
               avisar=print) -> Medicion:
    """Corre las etapas caras sobre un mp4 ya descargado. Deja un .srt por modelo en `destino`."""
    from dataclasses import replace

    info = probe(raw)
    m = Medicion(clip_id=raw.stem, duracion_s=round(info.duracion, 2))
    destino.mkdir(parents=True, exist_ok=True)

    with _cronometrar(m.etapas, "ocr"):
        vista = pant.detectar_datos(raw, cfg.pantalla)
    if vista.salteado:
        avisar(f"    ocr salteado: {vista.salteado}")

    palabras_ref = None
    for modelo in modelos:
        cfg_subs = replace(cfg.subtitulos, modelo=modelo)
        with _cronometrar(m.etapas, f"w:{modelo} cargar"):
            wm = sub.cargar_modelo(cfg_subs)
        with _cronometrar(m.etapas, f"w:{modelo} transcr"):
            palabras = sub.transcribir(wm, raw, cfg_subs)
        del wm
        m.palabras[modelo] = len(palabras)
        subs = sub.armar_subtitulos(palabras, cfg_subs)
        sub.escribir_srt(subs, destino / f"{raw.stem}.{modelo}.srt")
        if palabras_ref is None:
            palabras_ref = palabras

    with _cronometrar(m.etapas, "detectar cámara"):
        W, H, frames, _ = lay.detectar_caras(raw, cfg.camara.frames_muestra)
        layout = lay.decidir_layout(W, H, frames, cfg.camara, cfg.render)
    m.layout = layout.tipo

    subs_dir = destino / raw.stem
    subs_dir.mkdir(parents=True, exist_ok=True)
    sub.escribir_ass(sub.armar_subtitulos(palabras_ref or [], cfg.subtitulos),
                     subs_dir / "subs.ass", cfg.subtitulos, cfg.render)
    with _cronometrar(m.etapas, "render"):
        renderizar(raw, destino / f"{raw.stem}.bench.mp4", layout, cfg.render, subs_dir)
    return m


def maquina() -> dict:
    """Para poder comparar la corrida de la Pi con la de Windows en el mismo json."""
    import os

    datos = {"plataforma": platform.platform(), "maquina": platform.machine(),
             "python": platform.python_version(), "cpus": os.cpu_count()}
    modelo = Path("/proc/device-tree/model")
    if modelo.exists():  # en la Pi dice "Raspberry Pi 4 Model B Rev 1.5"
        datos["modelo"] = modelo.read_text(errors="ignore").strip("\x00\n")
    return datos


def informe(mediciones: list[Medicion], modelos: list[str], limite_s: float = LIMITE_S) -> str:
    """Tabla + veredicto. `limite_s` es el tope por clip que hace viable la corrida diaria."""
    if not mediciones:
        return "No hay clips para medir (poné mp4 en output/raw/)."
    etapas: list[str] = []
    for m in mediciones:
        for e in m.etapas:
            if e not in etapas:
                etapas.append(e)
    lineas = [f"{'clip':26} {'dur':>6} " + " ".join(f"{e[:15]:>15}" for e in etapas) + f" {'TOTAL':>8} {'x dur':>6}"]
    for m in mediciones:
        fila = f"{m.clip_id[:26]:26} {m.duracion_s:>5.0f}s " + " ".join(
            f"{m.etapas.get(e, 0):>15.1f}" for e in etapas)
        lineas.append(fila + f" {m.total:>7.0f}s {m.por_segundo():>5.1f}x")

    # El total real de una corrida usa UN solo modelo de Whisper: el de más tiempo es el peor caso.
    def total_con(modelo: str, m: Medicion) -> float:
        otros = sum(v for k, v in m.etapas.items() if not k.startswith("w:"))
        return otros + sum(v for k, v in m.etapas.items() if k.startswith(f"w:{modelo} "))

    lineas.append("")
    for modelo in modelos:
        totales = sorted(total_con(modelo, m) for m in mediciones)
        peor, mediana = totales[-1], totales[len(totales) // 2]
        veredicto = "ENTRA" if peor <= limite_s else f"NO ENTRA (tope {limite_s:.0f}s)"
        lineas.append(f"whisper {modelo:<6} por clip: mediana {mediana:.0f}s · peor {peor:.0f}s → {veredicto}")
        lineas.append(f"{'':21}3 clips/día ≈ {3 * mediana / 60:.0f} min de corrida")
    if len(modelos) > 1:
        lineas.append("")
        lineas.append("Palabras transcriptas por clip (más no es mejor, pero una caída grande avisa):")
        for m in mediciones:
            lineas.append(f"  {m.clip_id[:30]:30} " + "  ".join(
                f"{mo}: {m.palabras.get(mo, 0):>4}" for mo in modelos))
        lineas.append("Los .srt de cada modelo quedaron al lado para comparar el texto.")
    return "\n".join(lineas)


def guardar(mediciones: list[Medicion], modelos: list[str], destino: Path) -> Path:
    datos = {"maquina": maquina(), "modelos": modelos,
             "clips": [{"clip_id": m.clip_id, "duracion_s": m.duracion_s, "layout": m.layout,
                        "etapas": m.etapas, "palabras": m.palabras, "total_s": round(m.total, 2)}
                       for m in mediciones]}
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino
