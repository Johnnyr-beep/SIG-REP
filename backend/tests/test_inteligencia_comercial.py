"""Señales explicables de compra entre meses de Agropecuaria."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.services.inteligencia_comercial_service import InteligenciaComercialService
from app.application.services.periodos import obtener_o_crear_periodo
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import TipoDimension


def _miembro(sesion: Session, tipo: TipoDimension, clave: str) -> AgroDimension:
    fila = AgroDimension(tipo=tipo.value, clave=clave, nombre=clave)
    sesion.add(fila)
    sesion.flush()
    return fila


def _venta(
    sesion: Session,
    periodo: str,
    cliente: AgroDimension,
    producto: AgroDimension,
    importe: str,
) -> None:
    registro = obtener_o_crear_periodo(sesion, periodo)
    fijo = _miembro(sesion, TipoDimension.CENTRO_OPERACION, f"C-{periodo}-{cliente.id}")
    accesorios = {
        tipo: _miembro(sesion, tipo, f"{tipo.value}-{periodo}-{cliente.id}")
        for tipo in (
            TipoDimension.TIPO_ITEM,
            TipoDimension.ESPECIE,
            TipoDimension.TIPO_COMERCIAL,
            TipoDimension.GRUPO,
            TipoDimension.VENDEDOR,
        )
    }
    sesion.add(
        AgroVentaLinea(
            periodo_id=registro.id,
            fecha=date(registro.anio, registro.mes, 1),
            centro_id=fijo.id,
            tipo_item_id=accesorios[TipoDimension.TIPO_ITEM].id,
            especie_id=accesorios[TipoDimension.ESPECIE].id,
            tipo_comercial_id=accesorios[TipoDimension.TIPO_COMERCIAL].id,
            grupo_id=accesorios[TipoDimension.GRUPO].id,
            vendedor_id=accesorios[TipoDimension.VENDEDOR].id,
            cliente_id=cliente.id,
            item_id=producto.id,
            cantidad_inv=Decimal("1"),
            kilos_total=Decimal("1"),
            valor_bruto=Decimal(importe),
            descuentos=Decimal("0"),
            valor_subtotal=Decimal(importe),
            total_neto=Decimal(importe),
            lineas_facturadas=1,
            es_impuesto=False,
        )
    )


def test_detecta_cliente_suspendido_y_producto_no_solicitado(sesion: Session) -> None:
    cliente = _miembro(sesion, TipoDimension.CLIENTE, "CLIENTE A")
    producto = _miembro(sesion, TipoDimension.ITEM, "PRODUCTO A")
    _venta(sesion, "2026-07", cliente, producto, "100")
    _venta(sesion, "2026-08", _miembro(sesion, TipoDimension.CLIENTE, "CLIENTE B"), producto, "50")
    sesion.flush()

    respuesta = InteligenciaComercialService(sesion).analizar("2026-08")

    assert respuesta.disponible is True
    assert respuesta.alertas[0].tipo == "suspendio"
    assert respuesta.alertas[0].cliente == "CLIENTE A"
    assert respuesta.productos_no_solicitados[0].producto == "PRODUCTO A"
