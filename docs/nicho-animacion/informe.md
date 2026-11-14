# Nicho para un canal nuevo de Shorts animados en español

**Fecha:** 2026-11-14 · **Fuente de los números:** YouTube Data API v3 (nada de la web) · **Cuota gastada:** 5.692 unidades (56 búsquedas × 100 + 92 pedidos de detalle × 1).

Todo lo que dice "dato" sale de la API y está en `raw/`. Todo lo que dice **(juicio)** es opinión mía y está separado.

---

## 1. Método

**Búsqueda.** Por nicho, 2 llamadas a `search.list`: una en castellano y una en inglés, con `type=video`, `videoDuration=short` (menos de 4 min), `order=viewCount`, `publishedAfter=2026-05-14` (6 meses), `relevanceLanguage=es|en`, `maxResults=50`. Después `videos.list` (vistas, duración, título) y `channels.list` (suscriptores) de todos los resultados. Las palabras buscadas están en la segunda tabla y en `medir.py`.

**Filtros aplicados a cada resultado** (en este orden; cuántos cayó cada filtro está en `resultados.json`, campo `descartes`):
1. **Duración ≤ 180 s** (el largo máximo de un Short hoy). `videoDuration=short` trae hasta 4 min.
2. **Idioma por el título**, no por `relevanceLanguage` (que trae cualquier cosa): cuenta palabras típicas de cada idioma y tildes/ñ; descarta títulos con más de 20 % de letras no latinas (hindi, tamil…) y los que tienen marcas de portugués. Si empata, usa el idioma que declara el video.
3. **Tema por el título** (`tema.py`): cada nicho tiene una o dos listas de palabras y el título tiene que tener al menos una de cada lista (ej. comidas: "origen/invento/historia de…" **y** "pizza/helado/…"). Es estricto a propósito: un término genérico como "historia de la comida" traía dramas animados de un nene sin comida.

**Qué se mide por nicho e idioma** (sobre los videos que pasan los 3 filtros):
- máximo de vistas, **mediana del top 20** (la mediana y no el promedio, para que un viral solo no lo infle), cuántos pasan 100.000 vistas;
- cuántos canales distintos, cuántos con ≥ 1 M de suscriptores, cuánto del top 20 se lleva el canal más fuerte (concentración);
- **canales chicos que la rompen:** videos de ≥ 100.000 vistas hechos por canales de < 10.000 suscriptores (y, aparte, de < 100.000).

**Fórmula del puntaje (0-100).** Cada componente se normaliza de 0 a 1 entre los 28 nichos (mínimo → 0, máximo → 1):

```
Demanda    = 0,5 · norm(log10 mediana top20 ES) + 0,5 · norm(log10 mediana top20 EN)
Apertura   = 0,5 · norm(% de los videos ES ≥100k que son de canales <100k subs)
           + 0,5 · norm(log2(1 + videos ES ≥100k de canales <10k subs))
Brecha     = norm(log10 mediana EN − log10 mediana ES)
Saturación = norm(canales ES ≥1M subs + 10 · concentración del canal más fuerte)

Puntaje = 100 · (0,40 · Demanda + 0,30 · Apertura + 0,15 · Brecha + 0,15 · (1 − Saturación))
```

**Regla para el top 5:** quedan afuera los nichos cuya precisión del tema (de los 10 primeros resultados en castellano, cuántos son de verdad del tema, mirado a ojo) es menor a 5/10, porque sus números miden otra cosa.

**Robustez:** probé 3 juegos de pesos más (demanda 0,6; apertura 0,45; sin brecha). `origen_palabras`, `origen_marcas` y `cuerpo_humano` quedan en el top 5 en los 4; `economia_historias` en 3 de 4; `mitologia` y `misterios` se alternan el 5.° lugar (están empatados: 53,8 contra 53,7).

---

## 2. Tabla de los 28 nichos (datos)

Ordenada por puntaje. "ES válidos" = resultados en castellano que pasan los 3 filtros (de 50 como mucho). La última columna es juicio (la precisión, mirada a ojo).

| # | Nicho | Puntaje | ES válidos | ES máx | ES mediana top 20 | ES ≥100k | ES canales | ES canales ≥1M subs | ES chicos (<10k) con ≥100k | ES <100k subs con ≥100k | Concentración (1 canal) | EN máx | EN mediana top 20 | EN ≥100k | Precisión ES (top 10, a ojo) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | origen_palabras | 63.8 | 45 | 5.990.708 | 21.537 | 5 | 36 | 0 | 2 | 5 | 70 % | 20.170.317 | 549.095 | 26 | 9/10 |
| 2 | por_que_asi | 62.4 | 37 | 9.296.556 | 1.094.214 | 37 | 36 | 8 | 4 | 14 | 22 % | 42.231.886 | 5.887.156 | 29 | 3/10 |
| 3 | origen_marcas | 60.3 | 39 | 6.859.790 | 397.514 | 17 | 26 | 1 | 4 | 7 | 34 % | 10.041.067 | 433.078 | 17 | 8/10 |
| 4 | economia_historias | 58.9 | 31 | 220.638 | 9.473 | 2 | 29 | 0 | 2 | 2 | 23 % | 1.312.336 | 33.700 | 4 | 7/10 |
| 5 | cuerpo_humano | 57.9 | 41 | 7.913.464 | 2.086.119 | 16 | 21 | 2 | 2 | 5 | 72 % | 38.389.544 | 6.333.083 | 15 | 10/10 |
| 6 | mitologia | 53.8 | 30 | 828.631 | 46.805 | 6 | 25 | 4 | 1 | 1 | 27 % | 6.544.084 | 2.520.382 | 16 | 7/10 |
| 7 | misterios | 53.7 | 46 | 4.808.858 | 214.115 | 15 | 21 | 4 | 1 | 11 | 48 % | 8.280.172 | 791.341 | 26 | 6/10 |
| 8 | historia_juguetes | 51.8 | 31 | 2.354.671 | 79.831 | 10 | 26 | 7 | 0 | 2 | 40 % | 34.618.151 | 27.394.234 | 2 | 3/10 |
| 9 | animales_raros | 46.0 | 31 | 18.988.051 | 4.084.738 | 29 | 16 | 6 | 0 | 7 | 21 % | 138.396.294 | 4.377.395 | 31 | 9/10 |
| 10 | historia_comidas | 44.1 | 9 | 5.313.081 | 66.751 | 4 | 8 | 1 | 0 | 0 | 74 % | 14.954.687 | 3.818.981 | 15 | 3/9 |
| 11 | filosofia | 43.3 | 15 | 8.039 | 1.279 | 0 | 15 | 0 | 0 | 0 | 21 % | 39.275.138 | 227.662 | 17 | 7/10 |
| 12 | inventos_accidente | 42.7 | 33 | 5.025.310 | 27.107 | 4 | 32 | 2 | 2 | 2 | 81 % | 19.680.347 | 60.501 | 6 | 10/10 |
| 13 | que_pasaria_si | 40.7 | 48 | 19.015.262 | 8.198.377 | 48 | 28 | 10 | 0 | 6 | 19 % | 57.035.548 | 6.913.688 | 24 | 7/10 |
| 14 | fronteras_raras | 39.1 | 48 | 4.595.453 | 7.800 | 4 | 42 | 0 | 1 | 1 | 64 % | 16.510.179 | 38.263 | 8 | 10/10 |
| 15 | estafas_historicas | 38.6 | 24 | 15.796 | 686 | 0 | 19 | 0 | 0 | 0 | 56 % | 23.026.870 | 212.200 | 14 | 10/10 |
| 16 | leyes_absurdas | 37.9 | 35 | 2.085.414 | 55.810 | 7 | 31 | 2 | 0 | 2 | 41 % | 3.987.272 | 145.326 | 11 | 7/10 |
| 17 | errores_fortunas | 33.5 | 38 | 771.731 | 26.467 | 3 | 38 | 2 | 0 | 0 | 37 % | 4.718.427 | 111.100 | 11 | 5/10 |
| 18 | leyendas_urbanas | 32.7 | 45 | 11.659.829 | 71.638 | 7 | 36 | 2 | 0 | 0 | 82 % | 9.542.485 | 451.686 | 23 | 9/10 |
| 19 | paises_diminutos | 32.6 | 42 | 18.481 | 1.522 | 0 | 21 | 0 | 0 | 0 | 28 % | 344.738 | 22.840 | 1 | 6/10 |
| 20 | sesgos_psicologia | 32.4 | 30 | 1.716 | 1.310 | 0 | 28 | 0 | 0 | 0 | 7 % | 667.362 | 11.132 | 1 | 9/10 |
| 21 | origen_frases | 29.7 | 44 | 305.906 | 32.552 | 5 | 42 | 3 | 0 | 1 | 23 % | 1.044.121 | 20.152 | 3 | 10/10 (pero 6 son '¿Y si sí?') |
| 22 | medicina_rara | 28.9 | 45 | 923.883 | 3.548 | 2 | 42 | 1 | 0 | 2 | 69 % | 438.853 | 1.546 | 1 | 7/10 |
| 23 | robos_famosos | 27.4 | 26 | 27.863 | 1.080 | 0 | 26 | 0 | 0 | 0 | 43 % | 11.165.258 | 10.260 | 3 | 10/10 |
| 24 | oficios_perdidos | 27.3 | 5 | 11.925 | 395 | 0 | 5 | 0 | 0 | 0 | 91 % | 696.834 | 39.134 | 3 | 5/5 |
| 25 | errores_traduccion | 22.6 | 24 | 196.739 | 532 | 1 | 21 | 0 | 0 | 0 | 93 % | 1.134.035 | 14.374 | 4 | 6/10 |
| 26 | juicios_absurdos | 19.3 | 3 | 1.036 | 1.019 | 0 | 1 | 0 | 0 | 0 | 100 % | 8.175.529 | 9.031 | 2 | 3/3 |
| 27 | supersticiones | 16.3 | 15 | 11.995 | 218 | 0 | 11 | 0 | 0 | 0 | 84 % | 54.225 | 2.086 | 0 | 10/10 |
| 28 | apuestas_historicas | 12.3 | 1 | 29 | 29 | 0 | 1 | 0 | 0 | 0 | 100 % | 723.010 | 988 | 2 | 0/1 |

| Nicho | Búsqueda ES | Búsqueda EN | Demanda | Apertura | Brecha | Saturación |
|---|---|---|---|---|---|---|
| origen_palabras | origen de las palabras | etymology | 0.57 | 0.84 | 0.61 | 0.56 |
| por_que_asi | la verdadera razón por la que | the real reason why | 0.84 | 0.69 | 0.38 | 0.85 |
| origen_marcas | historia de la marca | brand origin story | 0.68 | 0.71 | 0.14 | 0.33 |
| economia_historias | economía explicada | economics explained | 0.4 | 0.84 | 0.31 | 0.14 |
| cuerpo_humano | cuerpo humano datos curiosos | human body facts | 0.87 | 0.5 | 0.29 | 0.76 |
| mitologia | mitología | mythology | 0.68 | 0.3 | 0.72 | 0.54 |
| misterios | misterios sin resolver | unsolved mysteries | 0.68 | 0.58 | 0.32 | 0.72 |
| historia_juguetes | historia de los juguetes | toy history | 0.81 | 0.1 | 1.0 | 0.92 |
| animales_raros | animales extraños | weird animals | 0.88 | 0.12 | 0.13 | 0.66 |
| historia_comidas | historia de la comida | food history | 0.71 | 0.0 | 0.73 | 0.69 |
| filosofia | filosofía explicada | philosophy explained | 0.42 | 0.0 | 0.9 | 0.12 |
| inventos_accidente | inventos por accidente | invented by accident | 0.47 | 0.59 | 0.24 | 0.84 |
| que_pasaria_si | qué pasaría si | what would happen if | 0.93 | 0.06 | 0.1 | 1.0 |
| fronteras_raras | fronteras más raras del mundo | weird borders | 0.4 | 0.34 | 0.36 | 0.51 |
| estafas_historicas | estafas más grandes de la historia | biggest scams in history | 0.39 | 0.0 | 0.98 | 0.45 |
| leyes_absurdas | leyes absurdas | weird laws | 0.54 | 0.14 | 0.27 | 0.48 |
| errores_fortunas | error que costó millones | mistake that cost millions | 0.5 | 0.0 | 0.34 | 0.45 |
| leyendas_urbanas | leyendas urbanas | urban legends | 0.61 | 0.0 | 0.4 | 0.85 |
| paises_diminutos | micronaciones | micronation | 0.31 | 0.0 | 0.53 | 0.19 |
| sesgos_psicologia | sesgo cognitivo | cognitive bias | 0.27 | 0.0 | 0.45 | 0.0 |
| origen_frases | origen de la frase | origin of the phrase | 0.43 | 0.1 | 0.05 | 0.41 |
| medicina_rara | medicina antigua | weird medical history | 0.21 | 0.5 | 0.0 | 0.64 |
| robos_famosos | robos más famosos de la historia | greatest heist in history | 0.26 | 0.0 | 0.46 | 0.32 |
| oficios_perdidos | oficios que desaparecieron | jobs that no longer exist | 0.28 | 0.0 | 0.81 | 0.75 |
| errores_traduccion | errores de traducción | translation mistakes | 0.25 | 0.0 | 0.62 | 0.77 |
| juicios_absurdos | demandas absurdas | ridiculous lawsuit | 0.25 | 0.0 | 0.45 | 0.83 |
| supersticiones | origen de las supersticiones | origin of superstitions | 0.12 | 0.0 | 0.46 | 0.69 |
| apuestas_historicas | apuestas más locas de la historia | craziest bets in history | 0.0 | 0.0 | 0.65 | 0.83 |

**Lectura rápida de la tabla (datos):**
- **Mucha demanda en castellano, pero cerrado:** `que_pasaria_si` (mediana 8,2 M, 48 de 48 pasan 100k, 10 canales de más de 1 M, ningún canal chico), `animales_raros` (mediana 4,4 M, 7 canales de +1 M, ningún chico), `cuerpo_humano` (mediana 2,1 M pero el 72 % del top 20 es de un solo canal, YOSOYBORJAB, 4,47 M de subs).
- **Brecha grande (rinde en inglés, casi no existe en castellano):** `estafas_historicas` (EN mediana 212.200 vs ES 686; en castellano nadie pasó 16.000 vistas), `filosofia` (EN 227.662 vs ES 1.309), `robos_famosos` (EN máx. 11,2 M; ES máx. 27.863), `juicios_absurdos` (EN 8,2 M; ES 3 videos), `oficios_perdidos`, `supersticiones`, `sesgos_psicologia`. Ojo: brecha no es demanda probada en castellano; puede ser que en castellano no funcione, o que nadie lo haya hecho bien.
- **Canales chicos que la rompen en castellano** (los únicos casos, con nombre): Prizm Labs (3.510 subs) 735.257 vistas con "El verdadero origen de gilipollas"; Donnysin (7.280) 4,5 M con la historia del cromo 00 de Panini; GeoHitos (8.250) 2,2 M con "La verdadera razón por la que Corea está dividida" y 570.630 con fronteras de España; Hombre Polilla (3.130) 1,5 M y Cuerpo en 3D (5.570) 761.399 en cuerpo humano; Explicado con Minecraft (2.930) 220.638 y El Billete (3.460) 209.641 en economía; Misterios en el Tiempo 4k (3.000) 637.217 con los Niños Verdes de Woolpit; Curiosidades Flash (3.300) 402.041 con inventos por accidente; Tio Cuper (3.060) 288.375 con Medusa.
- **Zack D. Films** (29,7 M de subs, animación 3D) aparece arriba de todo en inglés en 5 nichos: origen del oso de peluche (20,2 M), Mr. Potato (34,6 M), la caverna de Platón (39,3 M), una leyenda urbana (9,5 M) y un "qué pasaría si" (12,9 M). Es el formato de referencia del género "origen de X, animado".

---

## 3. Top 5 (con datos) y 3 ideas de video por nicho

### 1. Origen de las palabras (y de los insultos) — 63,8
**Datos:** en castellano 45 válidos, mediana del top 20 **21.537** (demanda baja), 5 pasan 100k, 36 canales distintos y **ninguno de +1 M**. 2 de los 5 videos de +100k son de un canal de 3.510 subs (Prizm Labs: 735.257 y 145.840) y 1 de 20.700 (Alex O'Dogherty, "¿De dónde viene la palabra chumino?", 1,28 M). En inglés la mediana es **549.095** (25 veces más) y 26 pasan 100k. Ojo: el máximo en castellano (5,99 M) es de un video que no es del tema y se coló.
**Qué hacen los de arriba (dato, de los títulos):** casi todos son de España, sobre insultos y palabras "picantes" (gilipollas, chumino, chorizo), con una persona hablando a cámara o placas de texto; ninguno animado entre los de +100k.
**Juicio:** encaja muy bien con animación (la palabra se puede "actuar": el personaje del que viene el nombre, el objeto, la escena de época). Material para un año sobra y con fuente buena (RAE/DLE, Corominas, Etymonline, Wikcionario). Riesgo bajo; el gancho fuerte (insultos, palabras de doble sentido) roza lo grosero.
**Ideas:**
1. **"Boludo era una palabra de guerra."** Gancho: *"Esta palabra la usaban para nombrar soldados… y hoy se la decís a tu amigo."* Distinto: animado, con el soldado gaucho en escena, y en rioplatense, cuando lo que hay es todo de España.
2. **"Por qué 'salario' viene de la sal."** Gancho: *"A los romanos les pagaban con lo mismo que le ponés a las papas fritas… o no."* Distinto: cierra con el giro (la historia de la paga en sal es dudosa) en vez de repetir el mito, que es lo que hacen casi todos.
3. **"Las palabras que usás todos los días y vienen del árabe."** Gancho: *"Si decís 'ojalá', estás nombrando a Dios sin darte cuenta."* Distinto: una sola palabra por video, con el viaje dibujado en un mapa, en vez de listas de 10.

### 2. Historia y origen de marcas — 60,3
**Datos:** en castellano 39 válidos, mediana **397.514**, 17 pasan 100k, 26 canales, **1 solo de +1 M**, concentración 34 %. 4 videos de +100k son de canales de menos de 10.000 subs (el más fuerte: Donnysin, 7.280 subs, 4,5 M con el cromo 00 de Panini). En inglés, mediana 433.078: la brecha es chica (en castellano ya rinde).
**Qué hacen los de arriba (dato):** LuchoBranding (171.000 subs) y Emprendedores exitosos (152.000) suben videos de **171-179 s**, casi el máximo, con tono de historia de superación ("salió caminando de su casa sin saber leer"); CIBERTALES (483.000) cuenta historias de empresas.
**Juicio:** encaja bien con animación (el fundador como personaje). Material enorme y documentado (sitios de las empresas, prensa, libros). **Riesgo real: logos y marcas registradas**: dibujar el producto sí, pero no usar el logo como imagen principal ni dar a entender que es contenido de la marca.
**Ideas:**
1. **"Bagley y la galletita que sobrevivió a todo."** Gancho: *"Esta galletita argentina tiene más años que el tango."* Distinto: marcas latinoamericanas (Bagley, Havanna, Bimbo, Inca Kola) que los de arriba casi no tocan (van a Louis Vuitton, Nike, Converse).
2. **"Por qué la Coca-Cola llevaba cocaína."** Gancho: *"El nombre no es un invento de marketing: es la receta."* Distinto: 40-60 s con un solo dato fuerte, contra los 170-180 s de LuchoBranding.
3. **"La marca que perdió contra un gaucho."** (cualquier caso real de una empresa grande que perdió en un país chico: Inca Kola contra Coca-Cola en Perú). Gancho: *"Es el único país donde Coca-Cola tuvo que comprar a su rival."* Distinto: la historia como una pelea animada, no como una biografía.

### 3. Economía explicada con historias — 58,9
**Datos:** demanda **baja** en los dos idiomas (mediana ES **23.200**, EN **33.700**), 31 válidos en castellano, solo 2 pasan 100k, **ninguno de +1 M**, concentración 21 %. Lo que lo sube es la apertura: los 2 de +100k son de canales chicos (Explicado con Minecraft, 2.930 subs, 220.638; El Billete, 3.460 subs, 209.641, "Por qué imprimir dinero te hace más pobre (explicado con una isla)"). Craftonomista (7.340 subs) mete 3 de 74-81 mil explicando inflación y oferta y demanda en Minecraft.
**Juicio:** la evidencia es fina (2 videos). Pero lo que funciona es justo lo que la animación hace mejor: una economía de juguete (una isla, un servidor de Minecraft) para explicar un concepto. Y para un público argentino, inflación es tema propio. Material infinito (casos históricos: tulipanes, hiperinflación alemana, Zimbabue, el corralito). Riesgo: política (no tomar partido, explicar mecanismos).
**Ideas:**
1. **"Por qué un billete de 100 billones no alcanzaba para un pan."** Gancho: *"En este país, los billetes valían menos que el papel en el que estaban impresos."* Distinto: una isla dibujada que se repite como "universo" de la serie.
2. **"La burbuja de los tulipanes."** Gancho: *"Alguien cambió una casa por una flor… y le pareció buen negocio."* Distinto: historia real con personajes, no la explicación abstracta de los que hacen "economía en 60 segundos".
3. **"Por qué los precios terminan en ,99."** Gancho: *"Ese centavo que te ahorrás tiene más de cien años de historia."* Distinto: conecta la vida cotidiana con el concepto (une con el nicho de "por qué las cosas son así", que como búsqueda no se pudo medir bien).

### 4. Cuerpo humano (datos curiosos) — 57,9
**Datos:** mucha demanda (mediana ES **2.086.119**, EN **6.333.083**), 16 de 41 pasan 100k. Pero muy concentrado: **72 % del top 20 es de un solo canal** (YOSOYBORJAB, 4,47 M de subs, 8 de los 10 primeros). Igual hay 2 canales chicos con +100k: Hombre Polilla (3.130 subs) 1,5 M y Cuerpo en 3D (5.570) 761.399; CURIOMENTE (16.000 subs) mete 7,6 M y 5,1 M con videos de **6 s**.
**Qué hacen los de arriba (dato):** YOSOYBORJAB repite el mismo título ("Cosas raras que puede hacer tu cuerpo") con una persona haciendo la prueba; CURIOMENTE, videos de 6 s; en inglés, animación 3D por dentro del cuerpo (SyncNexis Anatomy 21,1 M, Nature Discovery TV 17,0 M, canales de 44-63 mil subs).
**Juicio:** la animación es una ventaja clara (mostrar lo que pasa adentro, que no se puede filmar). Material para un año con fuentes buenas (MedlinePlus en español, libros de fisiología). **Riesgo: salud** (YouTube es estricto con información médica; nada de consejos, solo cómo funciona) y que se vuelva repetitivo.
**Ideas:**
1. **"Qué le pasa a tu cuerpo cuando contenés un estornudo."** Gancho: *"Ese estornudo que frenaste salió a 160 km/h… para adentro."* Distinto: el viaje animado por adentro (lo que hacen los canales chicos en inglés que llegan a 17-21 M), no una persona haciendo pruebas.
2. **"Por qué se te arruga la piel en el agua."** Gancho: *"No es que la piel absorba agua: tu cerebro la arruga a propósito."* Distinto: un dato contraintuitivo con el porqué, no una lista.
3. **"El hueso que tenías de bebé y ya no tenés."** Gancho: *"Naciste con casi 300 huesos y hoy tenés 206. ¿Adónde se fueron?"* Distinto: pregunta abierta en la primera frase y la respuesta al final (lo que ya funciona en Pequeña Historia).

### 5. Mitología — 53,8 (empatado con misterios, 53,7)
**Datos:** en castellano 30 válidos, mediana **46.805**, 6 pasan 100k, 4 canales de +1 M pero concentración baja (27 %). Un canal de 3.060 subs (Tio Cuper) con 288.375 ("Medusa, la verdad que no te contaron"); NoeslomismoStick (100.000 subs) 673.036 y 277.118 con animación de palitos. En inglés la mediana es **2.520.382**, pero casi todo es mitología hindú (no comparable con lo que se haría en castellano). Fuera del filtro estricto, Beth Cast (4,24 M de subs) tiene 15,8 M con "Las leyendas mitológicas de LATAM están rotísimas".
**Juicio:** encaje perfecto con animación (dioses, monstruos, sin fotos posibles). Material para años (griega, nórdica, egipcia, y la latinoamericana: guaraní, mapuche, azteca, inca, que casi nadie trata y conecta con Pequeña Historia). Fuentes buenas (Grimal, Graves, compilaciones académicas de mitos americanos). Riesgo bajo; con mitos de pueblos originarios, respeto (no burlarse de creencias vivas).
**Ideas:**
1. **"El Pombero: el que te escucha cuando no hay nadie."** Gancho: *"En el norte argentino, si silbás de noche, alguien te contesta."* Distinto: mitología latinoamericana, que en los resultados casi no aparece.
2. **"Por qué Medusa no era un monstruo."** Gancho: *"La castigaron por algo que le hicieron a ella."* Distinto: el giro de la versión original, contado en 45 s (Tio Cuper lo hace en 151 s).
3. **"El dios azteca que pedía que lo comieras."** Gancho: *"Cada año, la gente se comía a este dios… hecho de semillas."* Distinto: ritual real y raro, con el dato histórico verificable (fuentes: Sahagún).

**Misterios (6.º, 53,7) en una línea:** mediana ES **214.115**, 15 pasan 100k, 11 de esos son de canales de < 100.000 subs (la mayor apertura en proporción), pero 4 de los 10 primeros no son del tema (Free Fire, Dragon Ball, humor). Si se lo toma, el caso a imitar es Misterios en el Tiempo 4k (3.000 subs, 637.217 con los Niños Verdes de Woolpit): misterios históricos documentados, no creepypasta.

---

## 4. Lo que no se pudo medir

- **Demanda de búsqueda real** (cuánta gente busca el tema): la API no lo da. Lo que se midió es la **oferta que rinde**: las vistas de lo que ya existe. Un tema con brecha (estafas, robos, filosofía) puede no tener público en castellano; los datos no lo distinguen de "nadie lo hizo bien".
- **El ranking depende de las palabras buscadas.** Un solo término por idioma y por nicho; un canal que hace el tema con otras palabras no aparece. Con más cuota: 3-4 términos por nicho.
- **`order=viewCount` da los 50 más vistos que coinciden**, no una muestra al azar: las medianas son "del top", no del nicho entero.
- **"¿Es un Short?"**: no hay campo en la API. Usé duración ≤ 180 s.
- **Suscriptores de hoy, no de cuando se publicó el video.** Un canal "chico con un viral" puede haber crecido justo por ese viral; los de < 10.000 subs de hoy seguro eran chicos.
- **Cuántos canales lo hacen en total:** solo cuento los que salen entre los 50 resultados.
- **Retención, compartidos, ingresos, RPM:** la API pública no los da para videos ajenos.
- **El origen del tráfico** (feed de Shorts, búsqueda): no se puede ver en videos ajenos.
- **Qué es animado y qué no:** la API no lo dice; lo que digo de formato sale de leer títulos y nombres de canales, y es juicio. Para confirmarlo hay que mirar los videos.
- **"Por qué las cosas son así"**: como búsqueda ("la verdadera razón por la que") trae fútbol, parejas y cine (3/10 del tema); quedó afuera del top 5 por la regla de precisión, no porque el tema sea malo. **"Qué pasaría si"** y **"historia de los juguetes"** tienen el mismo problema en menor medida (juguetes 3/10: Toy Story, Peppa Pig).
- **Idioma:** la detección por título es una heurística; algún título en portugués o en "spanglish" se puede haber colado o caído.
- **Web:** no se usó búsqueda web; todos los canales nombrados salen de la API.
- **Datos crudos y scripts:** `medir.py` (búsqueda y análisis; `python medir.py analizar` rehace todo sin gastar cuota), `tema.py` (palabras del filtro de tema), `raw/` (todas las respuestas de la API), `resultados.json` (números por nicho).
