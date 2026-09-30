from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.infrastructure.fuentes.agro_tat import FuenteVentasTat
from app.infrastructure.models.agro_tat import AgroTatCorrida, AgroTatVenta
from app.schemas.agro_tat import AgroTatIngestaSalida, AgroTatResumen, AgroTatVentaSalida


class AgroTatService:
    def __init__(self, sesion: Session) -> None:
        self.sesion = sesion

    def listar(
        self,
        desde: date,
        hasta: date,
        tipo_comercial: str | None,
        limite: int | None,
        offset: int,
        fuente: FuenteVentasTat | None = None,
    ) -> AgroTatResumen:
        origen_propio = fuente is None
        origen = fuente or FuenteVentasTat()
        try:
            todas = list(origen.obtener_ventas(desde, hasta))
        finally:
            if origen_propio:
                origen.cerrar()

        tipos_comerciales = sorted(
            {fila.tipo_comercial for fila in todas if fila.tipo_comercial is not None}
        )
        filtradas = [
            fila
            for fila in todas
            if tipo_comercial is None or fila.tipo_comercial == tipo_comercial
        ]
        pagina = filtradas[offset:] if limite is None else filtradas[offset : offset + limite]
        total_cantidad = sum((fila.cantidad_inv for fila in filtradas), Decimal(0)).quantize(
            Decimal("0.001")
        )
        total_subtotal = sum((fila.valor_subtotal for fila in filtradas), Decimal(0)).quantize(
            Decimal("0.01")
        )
        return AgroTatResumen(
            filas=[AgroTatVentaSalida.model_validate(fila) for fila in pagina],
            total_cantidad=total_cantidad,
            total_subtotal=total_subtotal,
            tipos_comerciales=tipos_comerciales,
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
