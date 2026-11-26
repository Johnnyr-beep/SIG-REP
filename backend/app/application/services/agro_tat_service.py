from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.fuentes.agro_tat import ErrorFuenteTat, FuenteVentasTat, LineaTat
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
        filas: list[AgroTatVentaSalida] = []
        tipos_comerciales: set[str] = set()
        total_cantidad = Decimal(0)
        total_subtotal = Decimal(0)
        indice_filtrado = 0
        respaldo_local = False
        try:
            try:
                filas_fuente = origen.obtener_ventas(desde, hasta)
                registros = list(filas_fuente)
            except ErrorFuenteTat:
                registros = self._leer_local(desde, hasta)
                if not registros:
                    raise
                respaldo_local = True
        finally:
            if origen_propio:
                origen.cerrar()

        for fila in registros:
            if fila.tipo_comercial is not None:
                tipos_comerciales.add(fila.tipo_comercial)
            if tipo_comercial is not None and fila.tipo_comercial != tipo_comercial:
                continue

            total_cantidad += fila.cantidad_inv
            total_subtotal += fila.valor_subtotal
            dentro_de_pagina = indice_filtrado >= offset and (
                limite is None or indice_filtrado < offset + limite
            )
            if dentro_de_pagina:
                filas.append(AgroTatVentaSalida.model_validate(fila))
            indice_filtrado += 1

        return AgroTatResumen(
            filas=filas,
            total_cantidad=total_cantidad.quantize(Decimal("0.001")),
            total_subtotal=total_subtotal.quantize(Decimal("0.01")),
            tipos_comerciales=sorted(tipos_comerciales),
            respaldo_local=respaldo_local,
        )

    def _leer_local(self, desde: date, hasta: date) -> list[LineaTat]:
        filas = self.sesion.execute(
            select(AgroTatVenta)
            .where(AgroTatVenta.fecha_documento.between(desde, hasta))
            .order_by(AgroTatVenta.fecha_documento, AgroTatVenta.nro_documento)
        ).scalars()
        return [
            LineaTat(
                fecha_documento=fila.fecha_documento,
                hora_documento=fila.hora_documento,
                nro_documento=fila.nro_documento,
                tipo_comercial=fila.tipo_comercial,
                cliente_factura=fila.cliente_factura,
                razon_social_cliente=fila.razon_social_cliente,
                codigo_sucursal=fila.codigo_sucursal,
                descripcion_sucursal=fila.descripcion_sucursal,
                direccion_sucursal=fila.direccion_sucursal,
                cantidad_inv=Decimal(fila.cantidad_inv),
                valor_subtotal=Decimal(fila.valor_subtotal),
            )
            for fila in filas
        ]

    def ingerir(
        self, desde: date, hasta: date, fuente: FuenteVentasTat | None = None
    ) -> AgroTatIngestaSalida:
        origen = fuente or FuenteVentasTat()
        corrida = AgroTatCorrida(desde=desde, hasta=hasta)
        self.sesion.add(corrida)
        self.sesion.flush()
        try:
            filas = list(origen.obtener_ventas(desde, hasta))
        finally:
            if fuente is None:
                origen.cerrar()
        self.sesion.execute(
            delete(AgroTatVenta).where(AgroTatVenta.fecha_documento.between(desde, hasta))
        )
        self.sesion.add_all(
            [
                AgroTatVenta(
                    corrida_id=corrida.id,
                    fecha_documento=fila.fecha_documento,
                    hora_documento=fila.hora_documento,
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
        return AgroTatIngestaSalida(
            corrida_id=corrida.id,
            filas_leidas=len(filas),
            filas_insertadas=len(filas),
        )
