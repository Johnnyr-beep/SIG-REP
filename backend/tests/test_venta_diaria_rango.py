"""Venta diaria: fila de totales y corte por rango de fechas.

Dos cosas que el negocio pedía y que hoy se hacían a mano o no se hacían:

1. **La fila de totales.** Hoy alguien suma las columnas con la calculadora. La
   fila viaja en un campo propio —`totales`—, no como una fila más del arreglo,
   y cuadra con la suma de sus filas *por construcción*.
2. **El rango `desde`/`hasta`.** Con una trampa que es la razón de que estas
   pruebas existan: **el presupuesto es mensual** (§3.3). Un rango del 25 de
   julio al 5 de agosto tiene dos líneas de referencia distintas y las dos son
   correctas; publicar una sola sería medir los días de julio contra el
   presupuesto de agosto.

Los números están puestos a mano para que se puedan comprobar con una
calculadora, y elegidos para que ninguna suma parcial coincida con otra.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.reportes_service import (
    MAX_DIAS_RANGO,
    ErrorRangoExcesivo,
    ErrorRangoInvertido,
    FiltrosReporte,
    ReportesService,
)
from app.infrastructure.models.organizacion import Zona
from app.infrastructure.models.periodo import CalendarioZona
from app.infrastructure.models.presupuesto import Presupuesto
from app.infrastructure.models.venta import VentaLinea
from app.infrastructure.semilla import sembrar_calendario
from app.schemas.reportes import RespuestaVentaDiaria
from tests.conftest import (
    PERIODO,
    PUNTO_PROPIO,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_periodo,
    id_punto_venta,
)

D = Decimal
CORTE = date(2026, 8, 15)
JULIO = "2026-07"


# ── Ayudas ────────────────────────────────────────────────────────────────────


def _fijar_calendario(
    sesion: Session, habiles: str, trabajados: str, periodo: str = PERIODO
) -> None:
    """Mismo calendario en todas las zonas: hace predecible el diario."""
    for calendario in sesion.scalars(
        select(CalendarioZona).where(CalendarioZona.periodo_id == id_periodo(sesion, periodo))
    ).all():
        calendario.dias_habiles = D(habiles)
        calendario.dias_trabajados = D(trabajados)
    sesion.commit()


def _abrir_julio(sesion: Session) -> None:
    """Abre 2026-07 con su calendario, como haría la parametrización."""
    sembrar_calendario(sesion, JULIO)
    sesion.commit()


def _presupuesto_en(sesion: Session, periodo: str, codigo_co: str, monto: str) -> None:
    sesion.add(
        Presupuesto(
            periodo_id=id_periodo(sesion, periodo),
            punto_venta_id=id_punto_venta(sesion, codigo_co),
            categoria_id=id_categoria(sesion, "RES"),
            monto=D(monto),
            kilos=D(0),
        )
    )
    sesion.commit()


def _venta_en(sesion: Session, periodo: str, codigo_co: str, fecha: date, valor: str) -> None:
    sesion.add(
        VentaLinea(
            periodo_id=id_periodo(sesion, periodo),
            fecha=fecha,
            punto_venta_id=id_punto_venta(sesion, codigo_co),
            categoria_id=id_categoria(sesion, "RES"),
            valor_subtotal=D(valor),
            costo_promedio=D(0),
            cantidad_inv=D(0),
        )
    )
    sesion.commit()


def _reporte(
    sesion: Session,
    *,
    puntos_venta: tuple[str, ...] | None = None,
    alcance: list[int] | None = None,
    desde: date | None = None,
    hasta: date = CORTE,
) -> RespuestaVentaDiaria:
    """El reporte de venta diaria del período de pruebas, con corte fijo."""
    return ReportesService(sesion).venta_diaria(
        FiltrosReporte(
            periodo=PERIODO,
            hasta=hasta,
            desde=desde,
            puntos_venta=puntos_venta,
            alcance=alcance,
        )
    )


# ── La fila de totales ────────────────────────────────────────────────────────


def test_la_fila_de_totales_cuadra_con_la_suma_de_sus_filas(
    sesion: Session, estructura: None
) -> None:
    """Columna a columna y en el total del período. Es toda la promesa."""
    _fijar_calendario(sesion, "25", "10")
    dar_venta(sesion, "402", "RES", 1, "40000")
    dar_venta(sesion, "402", "RES", 2, "60000")
    dar_venta(sesion, "405", "RES", 2, "15000")
    dar_venta(sesion, "603", "RES", 3, "5000")

    respuesta = _reporte(sesion)
    totales = respuesta.totales

    assert totales.valores[0] == D("40000.00"), "día 1: solo MALAMBO"
    assert totales.valores[1] == D("75000.00"), "día 2: 60 000 + 15 000"
    assert totales.valores[2] == D("5000.00"), "día 3: solo CONCORDE"
    assert totales.total == D("120000.00")

    # Y la comprobación que de verdad importa: cuadra columna a columna con las
    # filas que tiene encima, sin excepción y sin depender de los números de
    # arriba. Un día sin ninguna venta vale `None` en la fila de totales, igual
    # que en las filas: es «no hay dato», no «sumó cero».
    for indice, _fecha in enumerate(respuesta.fechas):
        presentes = [f.valores[indice] for f in respuesta.filas if f.valores[indice] is not None]
        esperado = sum(presentes, start=D(0)) if presentes else None
        assert totales.valores[indice] == esperado
    assert totales.total == sum(D(f.total) for f in respuesta.filas)


def test_un_dia_sin_venta_en_ningun_punto_es_vacio_y_no_cero(
    sesion: Session, estructura: None
) -> None:
    """«Vendió cero» y «no hay dato» son afirmaciones distintas (§7)."""
    _fijar_calendario(sesion, "25", "10")
    dar_venta(sesion, "402", "RES", 2, "60000")

    totales = _reporte(sesion).totales

    assert totales.valores[0] is None, "el día 1 no tuvo venta registrada"
    assert totales.valores[1] == D("60000.00")


def test_la_fila_de_totales_respeta_el_filtro_de_puntos_de_venta(
    sesion: Session, estructura: None
) -> None:
    """«Si se piden tres puntos, el total es el de esos tres»."""
    _fijar_calendario(sesion, "25", "10")
    for codigo, valor in (
        ("402", "100000"),
        ("405", "200000"),
        ("603", "400000"),
        ("413", "800000"),
    ):
        dar_venta(sesion, codigo, "RES", 5, valor)

    assert _reporte(sesion).totales.total == D("1500000.00")
    assert _reporte(sesion, puntos_venta=("402", "405", "603")).totales.total == D("700000.00")
    assert _reporte(sesion, puntos_venta=("402",)).totales.total == D("100000.00")


def test_la_fila_de_totales_respeta_el_alcance_del_usuario(
    sesion: Session, estructura: None
) -> None:
    """Un total no es un resumen inocente: es la suma de datos con dueño."""
    _fijar_calendario(sesion, "25", "10")
    dar_venta(sesion, PUNTO_PROPIO, "RES", 5, "100000")
    dar_venta(sesion, "413", "RES", 5, "800000")

    alcance = [id_punto_venta(sesion, PUNTO_PROPIO)]
    assert _reporte(sesion, alcance=alcance).totales.total == D("100000.00")
    assert _reporte(sesion, alcance=alcance, puntos_venta=("413",)).totales.total == D("0.00")


def test_el_presupuesto_diario_total_es_la_suma_de_las_referencias(
    sesion: Session, estructura: None
) -> None:
    """`Σ (P_i / H_i)`, no el presupuesto agregado partido por los días.

    Dos zonas con calendarios distintos: 1 000 000 / 25 = 40 000 y
    900 000 / 30 = 30 000. La referencia del total es 70 000. Dividir el
    presupuesto agregado (1 900 000) entre unos días ponderados daría otro
    número y la fila no cuadraría con las que tiene encima.
    """
    zona_malambo = sesion.scalars(select(Zona).where(Zona.nombre == "MALAMBO")).one()
    for calendario in sesion.scalars(select(CalendarioZona)).all():
        calendario.dias_habiles = D("25") if calendario.zona_id == zona_malambo.id else D("30")
        calendario.dias_trabajados = D("10")
    sesion.commit()

    dar_presupuesto(sesion, "402", "RES", "1000000")  # zona MALAMBO, H = 25
    dar_presupuesto(sesion, "405", "RES", "900000")  # otra zona, H = 30

    respuesta = _reporte(sesion)

    assert respuesta.presupuesto_diario_por_pdv["402"] == D("40000.00")
    assert respuesta.presupuesto_diario_por_pdv["405"] == D("30000.00")
    assert respuesta.totales.presupuesto_diario == D("70000.00")


def test_sin_ningun_presupuesto_la_referencia_del_total_es_vacia(
    sesion: Session, estructura: None
) -> None:
    """Ni cero ni una raya inventada: «—» (§7)."""
    _fijar_calendario(sesion, "25", "10")
    dar_venta(sesion, "402", "RES", 5, "100000")

    assert _reporte(sesion).totales.presupuesto_diario is None


def test_un_punto_presupuestado_sin_dias_habiles_deja_el_total_en_vacio(
    sesion: Session, estructura: None
) -> None:
    """Sumar solo el resto publicaría una referencia baja con pinta de completa.

    Se borra el calendario de la zona de 405: su término `P / H` es
    incalculable. El total no puede seguir adelante sin él, igual que el margen
    no sigue adelante sin el costo de una línea (§4.4).
    """
    _fijar_calendario(sesion, "25", "10")
    dar_presupuesto(sesion, "402", "RES", "1000000")
    dar_presupuesto(sesion, "405", "RES", "900000")

    zona_405 = sesion.scalars(
        select(Zona).where(Zona.nombre == "LA 70 / LA 43 / SIMON / LA GRANJA")
    ).one()
    for calendario in sesion.scalars(
        select(CalendarioZona).where(CalendarioZona.zona_id == zona_405.id)
    ).all():
        sesion.delete(calendario)
    sesion.commit()

    respuesta = _reporte(sesion)

    assert respuesta.presupuesto_diario_por_pdv["402"] == D("40000.00")
    assert respuesta.presupuesto_diario_por_pdv["405"] is None
    assert respuesta.totales.presupuesto_diario is None


def test_por_http_la_fila_de_totales_viaja_en_su_propio_campo(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """No como una fila más de `filas`: la pantalla no la distingue por nombre."""
    _fijar_calendario(sesion, "25", "10")
    dar_presupuesto(sesion, "402", "RES", "1000000")
    dar_venta(sesion, "402", "RES", 1, "40000")
    dar_venta(sesion, "405", "RES", 1, "10000")

    cuerpo = cliente_http.get(
        f"/api/v1/reportes/venta-diaria?periodo={PERIODO}&hasta=2026-08-15", headers=gerente
    ).json()

    assert "TOTAL" not in [f["punto_venta"] for f in cuerpo["filas"]]
    assert cuerpo["totales"]["valores"][0] == "50000.00"
    assert cuerpo["totales"]["total"] == "50000.00"
    assert cuerpo["totales"]["presupuesto_diario"] == "40000.00"
    # Los importes viajan como texto, la fila de totales incluida.
    assert isinstance(cuerpo["totales"]["total"], str)


# ── El rango de fechas ────────────────────────────────────────────────────────


def test_sin_desde_el_reporte_es_exactamente_el_de_siempre(
    sesion: Session, estructura: None
) -> None:
    """La compatibilidad hacia atrás, escrita como prueba."""
    _fijar_calendario(sesion, "25", "10")
    dar_venta(sesion, "402", "RES", 1, "40000")

    respuesta = _reporte(sesion)

    assert respuesta.desde == date(2026, 8, 1)
    assert respuesta.hasta == CORTE
    assert respuesta.fecha_corte == CORTE
    assert respuesta.periodos == [PERIODO]
    assert len(respuesta.fechas) == 15
    assert respuesta.presupuesto_diario_por_periodo[PERIODO] == respuesta.presupuesto_diario_por_pdv


def test_un_rango_dentro_del_mes_recorta_las_columnas(sesion: Session, estructura: None) -> None:
    _fijar_calendario(sesion, "25", "10")
    dar_venta(sesion, "402", "RES", 1, "40000")
    dar_venta(sesion, "402", "RES", 5, "60000")
    dar_venta(sesion, "402", "RES", 9, "90000")

    respuesta = _reporte(sesion, desde=date(2026, 8, 5), hasta=date(2026, 8, 9))

    assert respuesta.fechas == [date(2026, 8, dia) for dia in range(5, 10)]
    assert respuesta.totales.valores[0] == D("60000.00")
    assert respuesta.totales.valores[4] == D("90000.00")
    # El día 1 queda fuera del rango y su venta no entra en el total.
    assert respuesta.totales.total == D("150000.00")


def test_un_rango_que_cruza_meses_trae_los_dias_de_los_dos(
    sesion: Session, estructura: None
) -> None:
    """Del 25 de julio al 5 de agosto: siete días de julio y cinco de agosto."""
    _abrir_julio(sesion)
    _fijar_calendario(sesion, "25", "10")
    _fijar_calendario(sesion, "25", "25", periodo=JULIO)
    _venta_en(sesion, JULIO, "402", date(2026, 7, 26), "100000")
    _venta_en(sesion, PERIODO, "402", date(2026, 8, 2), "200000")

    respuesta = _reporte(sesion, desde=date(2026, 7, 25), hasta=date(2026, 8, 5))

    assert len(respuesta.fechas) == 12
    assert respuesta.fechas[0] == date(2026, 7, 25)
    assert respuesta.fechas[-1] == date(2026, 8, 5)
    assert respuesta.periodos == [JULIO, PERIODO]

    fila = next(f for f in respuesta.filas if f.punto_venta == "402")
    assert fila.valores[1] == D("100000.00"), "26 de julio"
    assert fila.valores[8] == D("200000.00"), "2 de agosto"
    assert fila.total == D("300000.00")
    assert respuesta.totales.total == D("300000.00")


def test_el_rango_que_cruza_meses_toma_el_presupuesto_de_cada_periodo(
    sesion: Session, estructura: None
) -> None:
    """**La prueba que da sentido a todo esto.**

    Julio: 1 000 000 sobre 25 días hábiles = 40 000 diarios.
    Agosto: 1 500 000 sobre 25 días hábiles = 60 000 diarios.

    Son dos referencias distintas y las dos son correctas. Publicar una sola
    mediría los días de julio contra el presupuesto de agosto, que es
    exactamente el error que §3.3 impide: el presupuesto es **mensual**.
    """
    _abrir_julio(sesion)
    _fijar_calendario(sesion, "25", "10")
    _fijar_calendario(sesion, "25", "25", periodo=JULIO)
    _presupuesto_en(sesion, JULIO, "402", "1000000")
    _presupuesto_en(sesion, PERIODO, "402", "1500000")

    respuesta = _reporte(sesion, desde=date(2026, 7, 25), hasta=date(2026, 8, 5))

    assert respuesta.presupuesto_diario_por_periodo[JULIO]["402"] == D("40000.00")
    assert respuesta.presupuesto_diario_por_periodo[PERIODO]["402"] == D("60000.00")
    assert respuesta.totales.presupuesto_diario_por_periodo[JULIO] == D("40000.00")
    assert respuesta.totales.presupuesto_diario_por_periodo[PERIODO] == D("60000.00")
    # `presupuesto_diario_por_pdv` es el del período de la petición, y el
    # contrato promete que equivale a su entrada en el mapa por período.
    assert respuesta.presupuesto_diario_por_pdv["402"] == D("60000.00")
    assert respuesta.presupuesto_diario_por_pdv == respuesta.presupuesto_diario_por_periodo[PERIODO]


def test_los_dias_habiles_distintos_de_cada_mes_dan_referencias_distintas(
    sesion: Session, estructura: None
) -> None:
    """Aunque el presupuesto no cambie, el calendario sí: julio no es agosto."""
    _abrir_julio(sesion)
    _fijar_calendario(sesion, "30", "10")
    _fijar_calendario(sesion, "24", "24", periodo=JULIO)
    _presupuesto_en(sesion, JULIO, "402", "1200000")
    _presupuesto_en(sesion, PERIODO, "402", "1200000")

    respuesta = _reporte(sesion, desde=date(2026, 7, 25), hasta=date(2026, 8, 5))

    assert respuesta.presupuesto_diario_por_periodo[JULIO]["402"] == D("50000.00")  # /24
    assert respuesta.presupuesto_diario_por_periodo[PERIODO]["402"] == D("40000.00")  # /30


def test_un_periodo_del_rango_que_no_esta_abierto_no_inventa_referencia(
    sesion: Session, estructura: None
) -> None:
    """Sin período no hay presupuesto ni calendario: «—», no un cero cómodo."""
    _fijar_calendario(sesion, "25", "10")
    _presupuesto_en(sesion, PERIODO, "402", "1500000")

    respuesta = _reporte(sesion, desde=date(2026, 7, 25), hasta=date(2026, 8, 5))

    assert respuesta.periodos == [JULIO, PERIODO]
    assert respuesta.presupuesto_diario_por_periodo[JULIO]["402"] is None
    assert respuesta.totales.presupuesto_diario_por_periodo[JULIO] is None
    assert respuesta.presupuesto_diario_por_periodo[PERIODO]["402"] == D("60000.00")


# ── Los rechazos ──────────────────────────────────────────────────────────────


def test_un_rango_invertido_se_rechaza_con_su_motivo(sesion: Session, estructura: None) -> None:
    """No devuelve una tabla vacía que parezca «no hubo ventas»."""
    with pytest.raises(ErrorRangoInvertido) as error:
        _reporte(sesion, desde=date(2026, 8, 10), hasta=date(2026, 8, 5))

    assert "invertido" in str(error.value).lower()


def test_un_rango_excesivo_se_rechaza_diciendo_cual_es_el_tope(
    sesion: Session, estructura: None
) -> None:
    """Un error que no dice el límite obliga a adivinarlo a reintentos."""
    with pytest.raises(ErrorRangoExcesivo) as error:
        _reporte(sesion, desde=date(2026, 1, 1), hasta=date(2026, 12, 31))

    assert str(MAX_DIAS_RANGO) in str(error.value)
    assert error.value.detalles["maximo_dias"] == MAX_DIAS_RANGO
    assert error.value.detalles["dias_solicitados"] == 365


def test_el_rango_de_exactamente_el_tope_se_admite(sesion: Session, estructura: None) -> None:
    """El límite es inclusivo: 92 días entran, 93 no. Un `off by one` aquí
    convierte el tope documentado en otro distinto.
    """
    _fijar_calendario(sesion, "25", "10")
    desde = date(2026, 8, 15)
    respuesta = _reporte(sesion, desde=desde, hasta=date(2026, 11, 14))  # 92 días

    assert len(respuesta.fechas) == MAX_DIAS_RANGO

    with pytest.raises(ErrorRangoExcesivo):
        _reporte(sesion, desde=desde, hasta=date(2026, 11, 15))  # 93


def test_por_http_el_rango_invertido_devuelve_422_con_codigo_propio(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    """El frontend necesita distinguirlo de «el período no existe»."""
    respuesta = cliente_http.get(
        f"/api/v1/reportes/venta-diaria?periodo={PERIODO}&desde=2026-08-10&hasta=2026-08-05",
        headers=gerente,
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "rango_invertido"


def test_por_http_el_rango_excesivo_devuelve_422_con_el_tope(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    respuesta = cliente_http.get(
        f"/api/v1/reportes/venta-diaria?periodo={PERIODO}&desde=2025-01-01&hasta=2026-12-31",
        headers=gerente,
    )

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "rango_excesivo"
    assert cuerpo["detalles"]["maximo_dias"] == MAX_DIAS_RANGO


def test_por_http_el_rango_llega_hasta_la_exportacion(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """Exportar un rango que la pantalla no puede exportar sería otra verdad."""
    _abrir_julio(sesion)
    _fijar_calendario(sesion, "25", "10")
    _venta_en(sesion, JULIO, "402", date(2026, 7, 26), "100000")

    respuesta = cliente_http.get(
        f"/api/v1/reportes/venta-diaria/exportar?periodo={PERIODO}"
        "&desde=2026-07-25&hasta=2026-08-05",
        headers=gerente,
    )

    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"PK\x03\x04")
