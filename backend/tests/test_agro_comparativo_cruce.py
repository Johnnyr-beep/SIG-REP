from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.agro_reportes_service import AgroReportesService, FiltrosAgro
from app.application.services.periodos import obtener_o_crear_periodo
from app.domain.enums import Medida
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import TipoDimension

D = Decimal


def _dimension(sesion: Session, tipo: TipoDimension, clave: str) -> AgroDimension:
    fila = AgroDimension(tipo=tipo.value, clave=clave, nombre=clave)
    sesion.add(fila)
    sesion.flush()
    return fila


def test_comparativo_diario_limita_pareja_centro_y_excluye_impuestos(sesion: Session) -> None:
    periodo_actual = obtener_o_crear_periodo(sesion, "2026-08")
    periodo_anterior = obtener_o_crear_periodo(sesion, "2026-07")
    centro = _dimension(sesion, TipoDimension.CENTRO_OPERACION, "301")
    otro_centro = _dimension(sesion, TipoDimension.CENTRO_OPERACION, "302")
    vendedor = _dimension(sesion, TipoDimension.VENDEDOR, "V1")
    cliente = _dimension(sesion, TipoDimension.CLIENTE, "C1")
    otro_vendedor = _dimension(sesion, TipoDimension.VENDEDOR, "V2")
    otro_cliente = _dimension(sesion, TipoDimension.CLIENTE, "C2")
    tipo_item = _dimension(sesion, TipoDimension.TIPO_ITEM, "BIENES")
    especie = _dimension(sesion, TipoDimension.ESPECIE, "RES")
    comercial = _dimension(sesion, TipoDimension.TIPO_COMERCIAL, "CORTE")
    grupo = _dimension(sesion, TipoDimension.GRUPO, "G1")
    producto = _dimension(sesion, TipoDimension.ITEM, "P1")

    def agregar(
        dia: date,
        mes: str,
        monto: str,
        *,
        id_vendedor: AgroDimension = vendedor,
        id_cliente: AgroDimension = cliente,
        id_centro: AgroDimension = centro,
        impuesto: bool = False,
    ) -> None:
        periodo = periodo_actual if mes == "2026-08" else periodo_anterior
        sesion.add(
            AgroVentaLinea(
                periodo_id=periodo.id,
                fecha=dia,
                centro_id=id_centro.id,
                tipo_item_id=tipo_item.id,
                especie_id=especie.id,
                tipo_comercial_id=comercial.id,
                grupo_id=grupo.id,
                vendedor_id=id_vendedor.id,
                cliente_id=id_cliente.id,
                item_id=producto.id,
                es_impuesto=impuesto,
                cantidad_inv=D("1"),
                kilos_total=D(monto),
                valor_bruto=D(monto),
                descuentos=D("0"),
                valor_subtotal=D(monto),
                total_neto=D(monto),
                total_costo=D("0"),
                utilidad_bruta=D(monto),
                lineas_facturadas=1,
            )
        )

    agregar(date(2026, 8, 1), "2026-08", "100")
    agregar(date(2026, 8, 2), "2026-08", "200")
    agregar(date(2026, 7, 1), "2026-07", "80")
    agregar(date(2026, 7, 3), "2026-07", "30")
    agregar(date(2026, 8, 1), "2026-08", "900", id_vendedor=otro_vendedor)
    agregar(date(2026, 8, 1), "2026-08", "800", id_cliente=otro_cliente)
    agregar(date(2026, 8, 1), "2026-08", "700", id_centro=otro_centro)
    agregar(date(2026, 8, 1), "2026-08", "600", impuesto=True)
    sesion.flush()

    respuesta = AgroReportesService(sesion).comparativo_cruce_diario(
        FiltrosAgro(
            periodo="2026-08",
            desde=date(2026, 8, 1),
            hasta=date(2026, 8, 3),
            centros=("301",),
            medida=Medida.VALOR,
        ),
        "V1",
        "C1",
    )

    assert [punto.fecha for punto in respuesta.dias] == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]
    assert [punto.fecha_anterior for punto in respuesta.dias] == [
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]
    assert [punto.venta_actual for punto in respuesta.dias] == [D("100"), D("200"), None]
    assert [punto.venta_anterior for punto in respuesta.dias] == [D("80"), None, D("30")]
