"""Calendario de días hábiles por zona y período (§3.2).

Este servicio resuelve la pregunta de la que cuelga todo el reporte: ¿cuántos
días hábiles tiene el mes en esta zona y cuántos van corridos al corte?
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.periodos import fecha_corte_efectiva, obtener_o_crear_periodo
from app.core.config import obtener_settings
from app.core.errors import ErrorNoEncontrado
from app.domain.calendario import derivar_dias_trabajados
from app.domain.indicadores import ideal
from app.infrastructure.models.organizacion import Zona
from app.infrastructure.models.periodo import CalendarioZona, Periodo
from app.schemas.calendario import CalendarioSalida


@dataclass(frozen=True, slots=True)
class DiasZona:
    """Los dos números de una zona al corte, ya resueltos.

    `derivado` distingue lo que calculó el sistema de lo que escribió el
    usuario. La pantalla lo muestra porque no es lo mismo un ideal derivado de
    una regla proporcional que uno que alguien afirmó a mano.
    """

    zona_id: int
    dias_habiles: Decimal
    dias_trabajados: Decimal | None
    derivado: bool


class CalendarioService:
    """Lectura y parametrización del calendario."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion
        self._settings = obtener_settings()

    # ── Consulta ──────────────────────────────────────────────────────────────

    def dias_por_zona(self, periodo: Periodo, fecha_corte: date) -> dict[int, DiasZona]:
        """Días hábiles y trabajados de cada zona con calendario en el período.

        Las zonas sin fila de calendario **no aparecen**: sus puntos de venta
        salen con `H` y `T` vacíos, semáforo `SIN_PRESUPUESTO` y los
        indicadores que dependen del calendario en `null`. Rellenar con un
        valor por defecto silencioso sería inventar la vara de medir.
        """
        filas = self._sesion.execute(
            select(CalendarioZona).where(CalendarioZona.periodo_id == periodo.id)
        ).scalars()

        resultado: dict[int, DiasZona] = {}
        for fila in filas:
            explicito = fila.dias_trabajados is not None
            trabajados = (
                fila.dias_trabajados
                if explicito
                else derivar_dias_trabajados(
                    fila.dias_habiles, periodo.anio, periodo.mes, fecha_corte
                )
            )
            resultado[fila.zona_id] = DiasZona(
                zona_id=fila.zona_id,
                dias_habiles=fila.dias_habiles,
                dias_trabajados=trabajados,
                derivado=not explicito,
            )
        return resultado

    def listar(self, codigo_periodo: str, hasta: date | None = None) -> list[CalendarioSalida]:
        """Calendario de todas las zonas activas del período."""
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        corte = fecha_corte_efectiva(periodo, hasta)
        dias = self.dias_por_zona(periodo, corte)

        zonas = self._sesion.execute(
            select(Zona).where(Zona.activa.is_(True)).order_by(Zona.nombre)
        ).scalars()

        salida: list[CalendarioSalida] = []
        for zona in zonas:
            datos = dias.get(zona.id)
            if datos is None:
                continue
            salida.append(
                CalendarioSalida(
                    zona_id=zona.id,
                    zona=zona.nombre,
                    dias_habiles=datos.dias_habiles,
                    dias_trabajados=datos.dias_trabajados,
                    ideal=ideal(datos.dias_trabajados, datos.dias_habiles),
                    fecha_corte=corte,
                    derivado=datos.derivado,
                )
            )
        return salida

    # ── Parametrización ───────────────────────────────────────────────────────

    def actualizar(
        self,
        zona_id: int,
        codigo_periodo: str,
        dias_habiles: Decimal,
        dias_trabajados: Decimal | None,
        *,
        usuario_id: int | None = None,
        hasta: date | None = None,
    ) -> CalendarioSalida:
        """Fija los días de una zona.

        `dias_trabajados = None` devuelve la zona al cálculo derivado. El
        calendario **no** se bloquea con el cierre de período: cerrar congela el
        presupuesto (§7), y corregir a posteriori los días hábiles de un mes ya
        cerrado es justamente lo que permite recalcular un ideal mal puesto sin
        tocar un solo peso de presupuesto.
        """
        zona = self._sesion.get(Zona, zona_id)
        if zona is None:
            raise ErrorNoEncontrado(f"No existe la zona {zona_id}.")

        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        corte = fecha_corte_efectiva(periodo, hasta)

        fila = self._sesion.execute(
            select(CalendarioZona).where(
                CalendarioZona.periodo_id == periodo.id,
                CalendarioZona.zona_id == zona_id,
            )
        ).scalar_one_or_none()

        if fila is None:
            fila = CalendarioZona(periodo_id=periodo.id, zona_id=zona_id)
            self._sesion.add(fila)

        fila.dias_habiles = dias_habiles
        fila.dias_trabajados = dias_trabajados
        fila.fecha_corte = corte if dias_trabajados is not None else None
        fila.actualizado_por_id = usuario_id
        self._sesion.flush()

        efectivos = (
            dias_trabajados
            if dias_trabajados is not None
            else derivar_dias_trabajados(dias_habiles, periodo.anio, periodo.mes, corte)
        )
        return CalendarioSalida(
            zona_id=zona.id,
            zona=zona.nombre,
            dias_habiles=dias_habiles,
            dias_trabajados=efectivos,
            ideal=ideal(efectivos, dias_habiles),
            fecha_corte=corte,
            derivado=dias_trabajados is None,
        )
