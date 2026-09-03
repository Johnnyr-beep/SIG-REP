from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.infrastructure.fuentes.agro_tat import FuenteVentasTat
from app.infrastructure.models.agro_tat import AgroTatCorrida, AgroTatVenta
from app.schemas.agro_tat import AgroTatIngestaSalida, AgroTatResumen, AgroTatVentaSalida


class AgroTatService:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    def listar(self, desde: date, hasta: date, limite: int, offset: int) -> AgroTatResumen:
        filas = list(
            self.sesion.scalars(
                select(AgroTatVenta)
                .where(AgroTatVenta.fecha_documento.between(desde, hasta))
                .order_by(AgroTatVenta.fecha_documento, AgroTatVenta.nro_documento)
                .limit(limite)
                .offset(offset)
            )
        )
        total = self.sesion.execute(
            select(
                func.coalesce(func.sum(AgroTatVenta.cantidad_inv), 0),
                func.coalesce(func.sum(AgroTatVenta.valor_subtotal), 0),
            ).where(AgroTatVenta.fecha_documento.between(desde, hasta))
        ).one()
        return AgroTatResumen(
            filas=[AgroTatVentaSalida.model_validate(fila) for fila in filas],
            total_cantidad=str(total[0]),
            total_subtotal=str(total[1]),
        )

    def ingerir(
        self, desde: date, hasta: date, fuente: FuenteVentasTat | None = None
    ) -> AgroTatIngestaSalida:
        origen = fuente or FuenteVentasTat()
        corrida = AgroTatCorrida(desde=desde, hasta=hasta)
        self.sesion.add(corrida)
        self.sesion.flush()
        filas = list(origen.obtener_ventas(desde, hasta))
        self.sesion.execute(
            delete(AgroTatVenta).where(AgroTatVenta.fecha_documento.between(desde, hasta))
        )
        self.sesion.add_all(
            [
                AgroTatVenta(
                    corrida_id=corrida.id,
                    fecha_documento=fila.fecha_documento,
                    nro_documento=fila.nro_documento,
                    tipo_comercial=fila.tipo_comercial,
                    cliente_factura=fila.cliente_factura,
                    razon_social_cliente=fila.razon_social_cliente,
                    codigo_sucursal=fila.codigo_sucursal,
                    descripcion_sucursal=fila.descripcion_sucursal,
                    direccion_sucursal=fila.direccion_sucursal,
                    cantidad_inv=fila.cantidad_inv,
                    valor_subtotal=fila.valor_subtotal,
                )
                for fila in filas
            ]
        )
        corrida.filas_leidas = len(filas)
        corrida.filas_insertadas = len(filas)
        self.sesion.flush()
        if fuente is None:
            origen.cerrar()
        return AgroTatIngestaSalida(
            corrida_id=corrida.id,
            filas_leidas=len(filas),
            filas_insertadas=len(filas),
        )