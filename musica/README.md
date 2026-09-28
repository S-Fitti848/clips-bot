# Música de fondo de Pasó Hoy

El bot elige una pista al azar de esta carpeta por cada video de efemérides y la mezcla al 12 %
(`efemerides.musica_volumen` en `config/settings.yaml`), bajándola cuando habla la voz. Qué pista
usó queda en el json del video (`efemeride.musica`). Con la carpeta vacía, no hay música.

Los audios NO van a git (pesan; como `voces/`). Sí van este README y `creditos.json`.

## Reglas

- Solo música con licencia verificada que permita uso comercial y en YouTube.
- Cada pista va en `creditos.json`: `{"archivo.mp3": "Tema – Autor – licencia – link"}`. Si la
  licencia pide atribución, ese texto sale en la descripción ("Música: …"). Si no la pide, igual se
  anota (con el link) para saber de dónde salió.
- Ojo con Content ID: §1 de CLAUDE.md dice "sin música agregada". Esto es una excepción pedida por
  Santi para Pasó Hoy (2026-09-27). Si un video recibe un reclamo por la música, sacar esa pista.
