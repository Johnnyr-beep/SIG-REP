"""Leer el libro de presupuesto tal como lo arma el negocio.

Las tres trampas de ese formato, cada una con su prueba: los subtotales que no
se pueden cargar como si fueran miembros, el nombre que no es la clave, y el
total del propio libro como red de seguridad.
"""

from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import Workbook

from app.application.services import agro_presupuesto_tabla as tabla

CATALOGO = {
    "AFRICANO FRIAS ZULMA ESTER": "22641887",
    "MORA KATIA MARGARITA": "1042421513",
    "GUTIERREZ BOLIVAR LEON FELIPE": "98601901",
}


def _libro(filas: list[tuple[object, object, object]]) -> bytes:
    """Un libro con la forma de la tabla dinamica: nombre, kilos y pesos."""
    lb = Workbook()
    h = lb.active
    assert h is not None
    h.append(["VENDEDORES", " PPT EN KILO", "VENDEDORES", "PPT EN $"])
    for nombre, kilos, monto in filas:
        h.append([nombre, kilos, nombre, monto])
    memoria = io.BytesIO()
    lb.save(memoria)
    return memoria.getvalue()


def test_los_subtotales_no_se_cargan_como_miembros() -> None:
    """Cargarlos meteria el presupuesto dos veces: por vendedor y por su canal."""
    datos = _libro(
        [
            ("TAT", 30, 300),
            ("MORA KATIA MARGARITA", 10, 100),
            ("AFRICANO FRIAS ZULMA ESTER", 20, 200),
        ]
    )

    r = tabla.leer(datos, CATALOGO)

    assert r is not None
    assert [m.nombre for m in r.metas] == [
        "MORA KATIA MARGARITA",
        "AFRICANO FRIAS ZULMA ESTER",
    ]
    assert "TAT" in r.omitidas
    assert sum(m.kilos for m in r.metas) == Decimal(30)


def test_un_subtotal_se_reconoce_por_ser_una_suma_no_por_su_nombre() -> None:
    """La lista de canales cambia; un nombre escrito dentro del codigo, no.

    Con los canales en una lista fija, el dia que aparezca uno nuevo se cargaria
    como si fuera un vendedor y duplicaria su presupuesto en silencio.
    """
    datos = _libro(
        [
            ("CANAL RECIEN INVENTADO", 30, 300),
            ("MORA KATIA MARGARITA", 10, 100),
            ("AFRICANO FRIAS ZULMA ESTER", 20, 200),
        ]
    )

    r = tabla.leer(datos, CATALOGO)

    assert r is not None
    assert "CANAL RECIEN INVENTADO" in r.omitidas
    assert r.sin_resolver == []


def test_un_nombre_que_no_cuadra_como_suma_se_reporta() -> None:
    """No es un subtotal ni un vendedor conocido: alguien tiene que mirarlo."""
    datos = _libro(
        [
            ("PEREZ QUIEN SABE", 999, 999),
            ("MORA KATIA MARGARITA", 10, 100),
        ]
    )

    r = tabla.leer(datos, CATALOGO)

    assert r is not None
    assert "PEREZ QUIEN SABE" in r.sin_resolver
    assert [m.nombre for m in r.metas] == ["MORA KATIA MARGARITA"]


def test_la_meta_se_guarda_bajo_la_clave_del_origen_y_no_bajo_el_nombre() -> None:
    """Es lo que hace que la meta cruce con la venta.

    Guardada bajo el nombre, quedaria colgada de una clave que ninguna venta usa
    y el cumplimiento de esa persona saldria cero para siempre sin fallar nada.
    """
    r = tabla.leer(_libro([("MORA KATIA MARGARITA", 10, 100)]), CATALOGO)

    assert r is not None
    assert r.metas[0].clave == "1042421513"


def test_el_nombre_se_compara_sin_tildes_ni_espacios_de_mas() -> None:
    """En el libro real hay `MORA  KATIA MARGARITA`, con dos espacios."""
    r = tabla.leer(_libro([("  mora   katía  margarita ", 10, 100)]), CATALOGO)

    assert r is not None
    assert r.metas[0].clave == "1042421513"


def test_el_total_del_libro_viaja_para_poder_contrastarlo() -> None:
    """Es lo que detecta que algo se quedo fuera sin que nadie lo note."""
    datos = _libro(
        [
            ("MORA KATIA MARGARITA", 10, 100),
            ("AFRICANO FRIAS ZULMA ESTER", 20, 200),
            ("Total general", 30, 300),
        ]
    )

    r = tabla.leer(datos, CATALOGO)

    assert r is not None
    assert r.total_libro_kilos == Decimal(30)
    assert r.total_libro_monto == Decimal(300)


def test_una_hoja_sin_columna_de_vendedores_no_es_este_formato() -> None:
    """La hoja de datos crudos trae los mismos dos encabezados.

    Leerla sumaria el presupuesto una vez por cada linea de factura. Lo que
    distingue a la tabla es la columna `VENDEDORES` junto a las cifras.
    """
    lb = Workbook()
    h = lb.active
    assert h is not None
    h.append(["Nombre vendedor", "GRUPO", " PPT EN KILO", "PPT EN $"])
    h.append(["MORA KATIA MARGARITA", "A", 10, 100])
    memoria = io.BytesIO()
    lb.save(memoria)

    assert tabla.leer(memoria.getvalue(), CATALOGO) is None
