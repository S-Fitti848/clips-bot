"""Fuentes extra de las historias de Facebook (pedido de Santi, 2026-11-10: que ningún día quede sin
una historia fuerte). Sin red: una Wikipedia falsa que contesta según el pedido, con textos copiados
de la forma de los reales."""

from datetime import date

from clips_bot import locales

DIA_12 = """== Acontecimientos ==
* [[1922]]: en [[Lima]] (Perú) se inaugura algo.
== Nacimientos ==
* [[1651]]: [[Juana Inés de la Cruz]], escritora novohispana (f. 1695).
== Celebraciones ==
* [[Día Mundial contra la Neumonía]].<br><small>Se conmemora desde 2009.</small>
* {{ARG}}:
** [[Ejército Argentino]]: Día de las Tropas de Monte.
* {{ECU}}:
** Independencia de [[Ambato]].<br><small>Conmemora la proclamación de la independencia de esta ciudad ecuatoriana, ocurrida el 12 de noviembre de 1820, durante el proceso de emancipación.<ref>{{Cita web |url=https://ambato.gob.ec/}}</ref></small>
* {{MEX}}:
** Día Nacional del Libro.<br><small>Instituido por decreto presidencial en 1979 para conmemorar el nacimiento de [[Sor Juana Inés de la Cruz]], ocurrido en 1651.</small>
** Día de la Cartera y el Cartero.<br><small>Conmemoración establecida en 1931 durante la presidencia de [[Pascual Ortiz Rubio]].</small>
* {{ALB}}:
** [[Día de la Liberación]], ocurrida el 12 de noviembre de 1944.
== Véase también ==
"""

ANEXO_VE = """== Noviembre ==
*2 de noviembre: [[Conmemoración de los Fieles Difuntos|día de los fieles difuntos]].
*12 de noviembre: natalicio del General [[José Antonio Anzoátegui]].
*29 de noviembre: natalicio de [[Andrés Bello]].
"""

BUSQUEDA = {
    '"fundada el 12 de noviembre"': [
        ("Rocha (Uruguay)", "Nuestra Señora de los Remedios de Rocha (fundada el 12 de noviembre de 1793 por Rafael Pérez del Puerto"),
        ("Universidad Viña del Mar", "Fue fundada el 12 de noviembre de 1988 por el ingeniero"),
        ("Bolsa de Belgrado", "La Bolsa de Belgrado en Serbia fue fundada el 12 de noviembre de 1894")],
    '"fundado el 12 de noviembre"': [
        ("Ariquemes", "La tribu se encuentra actualmente extinta. El municipio fue fundado el 12 de noviembre de 1977."),
        ("Club Atlético Central Norte (Tucumán)", "equipo de fútbol argentino que fue fundado el 12 de noviembre de 1911")],
    '"el 12 de noviembre de" vecinos': [
        ("Villa Soldati (Buenos Aires)", "El barrio se fundó el 12 de noviembre de 1908, cuando los vecinos")],
}
INTROS = {
    "Rocha (Uruguay)": "Rocha es una ciudad del sureste de Uruguay, capital del departamento de Rocha.",
    "Universidad Viña del Mar": "La Universidad Viña del Mar es una universidad privada de Chile.",
    "Bolsa de Belgrado": "La Bolsa de Belgrado es la bolsa de valores de Serbia.",
    "Ariquemes": "Ariquemes es un municipio brasileño del estado de Rondonia, en Brasil.",
    "Club Atlético Central Norte (Tucumán)": "El Club Atlético Central Norte es un club de fútbol de la ciudad de San Miguel de Tucumán, Argentina.",
    "Villa Soldati (Buenos Aires)": "Villa Soldati es un barrio de la Ciudad de Buenos Aires, Argentina.",
}
TEXTOS = {
    "Ambato": "Ambato es una ciudad de Ecuador.\n== Historia ==\nEl 12 de noviembre de 1820 los vecinos de Ambato se levantaron contra la corona y proclamaron su independencia en la plaza. Otra cosa pasó en 1949.",
    "Villa Soldati (Buenos Aires)": "Villa Soldati es un barrio. El 12 de noviembre de 1908 los vecinos, encabezados por José Soldati, lotearon las tierras de la familia y armaron la primera escuela.",
    "Rocha (Uruguay)": "Rocha es una ciudad de Uruguay. La villa fue fundada el 12 de noviembre de 1793 por Rafael Pérez del Puerto con familias asturianas y gallegas.",
}


class Wiki:
    def __init__(self, falla=()):
        self.falla = set(falla)
        self.pedidos = []

    def _get(self, url, params=None):
        p = params or {}
        self.pedidos.append(p)
        if p.get("list") == "search":
            if "search" in self.falla:
                raise RuntimeError("429")
            hits = BUSQUEDA.get(p["srsearch"], [])
            return {"query": {"search": [{"title": t, "snippet": f"<span>{s}</span>"} for t, s in hits]}}
        if p.get("prop") == "extracts":
            return {"query": {"pages": {str(i): {"title": t, "extract": INTROS.get(t, "")}
                                        for i, t in enumerate(p["titles"].split("|"))}}}
        if p.get("page", "").startswith("Anexo:"):
            if "anexos" in self.falla:
                raise RuntimeError("429")
            return {"parse": {"wikitext": ANEXO_VE if "Venezuela" in p["page"] else ""}}
        return {"parse": {"wikitext": DIA_12}}

    def texto(self, lang, titulo):
        return TEXTOS.get(titulo, "")


def test_conmemoraciones_con_el_anio_del_hecho_son_candidatas():
    todos, conm, homen = locales.leer_dia(Wiki(), date(2026, 11, 12))
    cel = [c for c in todos if c.seccion == "celebracion"]
    por_pagina = {c.paginas[0]: c for c in cel}
    assert por_pagina["Ambato"].anio == 1820 and por_pagina["Ambato"].texto.startswith("Ecuador: ")
    assert por_pagina["Sor Juana Inés de la Cruz"].anio == 1651      # no 1979 (el decreto)
    assert "Pascual Ortiz Rubio" not in por_pagina                     # sin año del hecho: no
    assert "Día de la Liberación" not in por_pagina                     # Albania: no es de acá
    assert "Ejército Argentino" not in por_pagina
    assert all("<" not in c.texto for c in cel)
    assert any(x.startswith("México: Día Nacional del Libro") for x in conm)


def test_anio_celebracion():
    d = date(2026, 11, 12)
    assert locales.anio_celebracion("ocurrida el 12 de noviembre de 1820", d) == 1820
    assert locales.anio_celebracion("Instituido en 1979 para conmemorar el nacimiento, ocurrido en 1651", d) == 1651
    assert locales.anio_celebracion("Conmemoración establecida en 1931", d) is None


def test_la_celebracion_pasa_el_filtro_como_un_acontecimiento():
    todos, _, homen = locales.leer_dia(Wiki(), date(2026, 11, 12))
    ok, _ = locales.filtrar(todos, date(2026, 11, 10), homen)
    assert any(c.seccion == "celebracion" and c.paginas[0] == "Ambato" for c in ok)


def test_anexo_por_pais_homenajea_a_la_persona():
    conm, homen = locales.leer_anexos(Wiki(), date(2026, 11, 12))
    assert conm == ["Venezuela: natalicio del General José Antonio Anzoátegui."]
    assert homen == {"José Antonio Anzoátegui"}


def test_fundaciones_solo_pueblos_y_ciudades_de_latinoamerica():
    f = locales.buscar_fundaciones(Wiki(), date(2026, 11, 12))
    assert {c.paginas[0]: c.anio for c in f} == {"Rocha (Uruguay)": 1793, "Ariquemes": 1977}
    assert all(c.seccion == "fundacion" for c in f)
    assert "Rafael Pérez del Puerto" in f[0].texto and "Uruguay" in f[0].texto


def test_es_lugar_latino():
    assert locales.es_lugar_latino("Ariquemes es un municipio brasileño del estado de Rondonia, en Brasil.")
    assert not locales.es_lugar_latino("El Club Atlético es un club de fútbol de la ciudad de Salta, Argentina.")
    assert not locales.es_lugar_latino("Caudiel es un municipio de la provincia de Castellón, España.")


def test_historia_de_cada_ciudad_saca_lo_que_paso_hoy():
    h = locales.historia_de_ciudades(Wiki(), date(2026, 11, 12), ["Ambato"])
    ambato = [c for c in h if c.paginas == ["Ambato"]]
    assert len(ambato) == 1 and ambato[0].anio == 1820 and "vecinos de Ambato" in ambato[0].texto
    assert not any("1949" in c.texto for c in h)


def test_leer_todo_junta_las_fuentes_sin_repetir():
    avisos = []
    todos, conm, homen = locales.leer_todo(Wiki(), date(2026, 11, 12), avisos.append)
    secciones = {c.seccion for c in todos}
    assert {"acontecimientos", "celebracion", "fundacion", "historia_ciudad"} <= secciones
    # Rocha: la fundación (buscador) y la oración de su historia son el mismo hecho → uno solo
    assert sum(1 for c in todos if c.paginas[0] == "Rocha (Uruguay)" and c.anio == 1793) == 1
    # Ambato: la conmemoración y la oración de su historia, también
    assert sum(1 for c in todos if c.paginas[0] == "Ambato" and c.anio == 1820) == 1
    assert any(c.seccion == "historia_ciudad" and "José Soldati" in c.texto for c in todos)
    assert "José Antonio Anzoátegui" in homen
    assert any("fuentes extra" in a for a in avisos)


def test_una_fuente_caida_no_frena_el_dia():
    avisos = []
    todos, _, _ = locales.leer_todo(Wiki(falla={"search", "anexos"}), date(2026, 11, 12), avisos.append)
    assert any(c.seccion == "acontecimientos" for c in todos)
    assert any("fundaciones: no salió" in a for a in avisos)
    assert any("anexos de efemérides: no salió" in a for a in avisos)
