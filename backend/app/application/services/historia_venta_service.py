"""Captura manual de venta histórica de carnes."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.periodos import buscar_periodo, obtener_o_crear_periodo
from app.core.errors import ErrorAutorizacion, ErrorNoEncontrado
from app.infrastructure.models.historia_venta import HistoriaVentaManual
from app.infrastructure.models.organizacion import PuntoVenta
from app.infrastructure.models.usuario import Usuario
from app.schemas.presupuesto import HistoriaVentaSalida


class HistoriaVentaService:
    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    def listar(
        self, codigo_periodo: str, alcance: list[int] | None = None
    ) -> list[HistoriaVentaSalida]:
        periodo = buscar_periodo(self._sesion, codigo_periodo)
        if periodo is None:
            return []
        consulta = (
            select(HistoriaVentaManual)
            .where(HistoriaVentaManual.periodo_id == periodo.id)
            .order_by(HistoriaVentaManual.punto_venta_id)
        )
        if alcance is not None:
            consulta = consulta.where(HistoriaVentaManual.punto_venta_id.in_(alcance or [-1]))
        autores: dict[int | None, str] = {}
        for usuario_id, nombre in self._sesion.execute(select(Usuario.id, Usuario.usuario)):
            autores[usuario_id] = nombre
        return [
            HistoriaVentaSalida(
                periodo=periodo.codigo,
                punto_venta_id=fila.punto_venta_id,
                punto_venta=fila.punto_venta.codigo_co,
                nombre=fila.punto_venta.nombre,
                monto=fila.monto,
                kilos=fila.kilos,
                motivo=fila.motivo,
                actualizado_en=fila.actualizado_en,
                actualizado_por=autores.get(fila.actualizado_por_id),
            )
            for fila in self._sesion.scalars(consulta)
        ]

    def guardar(
        self,
        *,
        codigo_periodo: str,
        punto_venta_id: int,
        monto: Decimal,
        kilos: Decimal,
        motivo: str,
        usuario: Usuario,
        alcance: list[int] | None = None,
    ) -> HistoriaVentaSalida:
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        punto = self._sesion.get(PuntoVenta, punto_venta_id)
        if punto is None:
            raise ErrorNoEncontrado(f"No existe el punto de venta {punto_venta_id}.")
        if alcance is not None and punto.id not in alcance:
            raise ErrorAutorizacion(
                f"No tiene permiso para parametrizar el punto de venta {punto.codigo_co}."
            )

        fila = self._sesion.scalar(
            select(HistoriaVentaManual).where(
                HistoriaVentaManual.periodo_id == periodo.id,
                HistoriaVentaManual.punto_venta_id == punto.id,
            )
        )
        if fila is None:
            fila = HistoriaVentaManual(
                periodo_id=periodo.id,
                punto_venta_id=punto.id,
                monto=monto,
                kilos=kilos,
                motivo=motivo,
                actualizado_por_id=usuario.id,
            )
            self._sesion.add(fila)
        else:
            fila.monto = monto
            fila.kilos = kilos
            fila.motivo = motivo
            fila.actualizado_por_id = usuario.id
        self._sesion.flush()

        return HistoriaVentaSalida(
            periodo=periodo.codigo,
            punto_venta_id=punto.id,
            punto_venta=punto.codigo_co,
            nombre=punto.nombre,
            monto=fila.monto,
            kilos=fila.kilos,
            motivo=fila.motivo,
            actualizado_en=fila.actualizado_en,
            actualizado_por=usuario.usuario,
        )
