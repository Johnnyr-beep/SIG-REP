"""Reglas del cubo comercial: medidas, filtros y protección contra impuestos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.application.services.agro_reportes_service import AgroReportesService, FiltrosAgro
from app.application.services.periodos import obtener_o_crear_periodo
from app.domain.enums import Medida
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import TipoDimension
from tests.conftest import PERIODO

D = Decimal
ANIO, MES = (int(parte) for parte in PERIODO.split("-"))


def _miembro(sesion: Session, tipo: TipoDimension, clave: str) -> AgroDimension:
    miembro = AgroDimension(tipo=tipo.value, clave=clave, nombre=clave.replace("_", " "))
    sesion.add(miembro)
    sesion.flush()
    return miembro


@pytest.fixture
def venta_cubo(sesion: Session) -> Session:
    """Dos combinaciones vendibles y una fila de impuesto que nunca debe entrar."""
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    dimensiones = {
        tipo: _miembro(sesion, tipo, tipo.value)
        for tipo in TipoDimension
        if tipo not in {TipoDimension.TIPO_COMERCIAL, TipoDimension.GRUPO}
    }
    cortes = _miembro(sesion, TipoDimension.TIPO_COMERCIAL, "CORTES")
    canales = _miembro(sesion, TipoDimension.TIPO_COMERCIAL, "CANALES")
    grupo_a = _miembro(sesion, TipoDimension.GRUPO, "A")
    grupo_b = _miembro(sesion, TipoDimension.GRUPO, "B")

    def agregar(
        tipo_comercial: AgroDimension,
        grupo: AgroDimension,
        *,
        neto: str,
        costo: str | None,
        utilidad: str | None,
        impuesto: bool = False,
    ) -> None:
        sesion.add(
            AgroVentaLinea(
                periodo_id=periodo.id,
                fecha=date(ANIO, MES, 5),
                centro_id=dimensiones[TipoDimension.CENTRO_OPERACION].id,
                tipo_item_id=dimensiones[TipoDimension.TIPO_ITEM].id,
                especie_id=dimensiones[TipoDimension.ESPECIE].id,
                tipo_comercial_id=tipo_comercial.id,
                grupo_id=grupo.id,
                vendedor_id=dimensiones[TipoDimension.VENDEDOR].id,
                cliente_id=dimensiones[TipoDimension.CLIENTE].id,
                item_id=dimensiones[TipoDimension.ITEM].id,
                valor_bruto=D(neto) + D("10"),
                descuentos=D("10"),
                valor_subtotal=D(neto),
                total_neto=D(neto),
                total_costo=D(costo) if costo is not None else None,
                utilidad_bruta=D(utilidad) if utilidad is not None else None,
                kilos_total=D("2"),
                cantidad_inv=D("3"),
                lineas_facturadas=2,
                es_impuesto=impuesto,
            )
        )

    agregar(cortes, grupo_a, neto="100", costo="60", utilidad="40")
    agregar(cortes, grupo_a, neto="50", costo=None, utilidad=None)
    agregar(canales, grupo_b, neto="80", costo="30", utilidad="50")
    agregar(cortes, grupo_a, neto="999", costo="1", utilidad="998", impuesto=True)
    sesion.flush()
    return sesion


def _cubo(sesion: Session, centros: tuple[str, ...] | None = None):
    return AgroReportesService(sesion).cubo(
        FiltrosAgro(
            periodo=PERIODO,
            hasta=date(ANIO, MES, 20),
            centros=centros,
            medida=Medida.VALOR,
        ),
        [TipoDimension.TIPO_COMERCIAL, TipoDimension.GRUPO],
    )


def test_el_cubo_agrega_todas_las_medidas_y_excluye_impuesto(venta_cubo: Session) -> None:
    respuesta = _cubo(venta_cubo)

    assert respuesta.total.total_neto == D("230.00")
    assert respuesta.total.valor_bruto == D("260.00")
    assert respuesta.total.valor_subtotal == D("230.00")
    assert respuesta.total.cantidad_inv == D("9.000")
    assert respuesta.total.kilos_total == D("6.000")
    assert respuesta.total.lineas_facturadas == 6
    assert respuesta.total.total_costo is None
    assert respuesta.total.utilidad_bruta is None
    assert [fila.nombres for fila in respuesta.filas] == [
        ["CORTES", "A"],
        ["CANALES", "B"],
    ]


def test_el_cubo_deja_vacia_medida_incompleta_sin_ocultar_la_venta(venta_cubo: Session) -> None:
    respuesta = _cubo(venta_cubo)
    cortes = respuesta.filas[0]

    assert cortes.total_neto == D("150.00")
    assert cortes.total_costo is None
    assert cortes.utilidad_bruta is None
