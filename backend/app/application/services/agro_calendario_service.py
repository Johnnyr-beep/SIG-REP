"""Calendario de días hábiles por centro de operación (§3.2 aplicado a agro).

Resuelve la pregunta de la que cuelga todo el reporte: ¿cuántos días hábiles
tiene el mes en este centro y cuántos van corridos al corte?

La diferencia con carnes es la unidad. Allí son dieciséis puntos de venta
repartidos en zonas, y la zona existe porque varios puntos comparten calendario.
Aquí son **dos centros de operación** —301 Planta y 302 Montería— y no hay nada
que agrupar: el centro *es* la unidad de calendario. Inventar una tabla de zonas
con dos filas de una fila cada una sería la clase de simetría con carnes que no
aporta nada y hay que mantener para siempre.

Lo que sí se reutiliza tal cual, porque es puro y está probado, es
`app.domain.calendario`: `derivar_dias_trabajados` reparte los días hábiles en
proporción a los días transcurridos, y una sobreescritura del usuario manda
sobre la derivación porque el negocio sabe cosas que el calendario no.

**Un centro sin fila de calendario no aparece con días por defecto.** Sale con
`H` y `T` vacíos, semáforo `SIN_PRESUPUESTO` y los indicadores que dependen del
calendario en `null`. Rellenar con un valor silencioso sería inventar la vara de
medir, y todo el sistema existe para que la vara se vea.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.periodos import fecha_corte_efectiva, obtener_o_crear_periodo
from app.core.errors import ErrorNoEncontrado
from app.domain.calendario import derivar_dias_trabajados
from app.domain.indicadores import ideal
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_presupuesto import AgroCalendario
from app.infrastructure.models.agro_vocabulario import TipoDimension, normalizar_clave
from app.infrastructure.models.periodo import Periodo
from app.schemas.agro import CalendarioAgroSalida


@dataclass(frozen=True, slots=True)
class DiasCentro:
    """Los dos números de un centro al corte, ya resueltos.

    `derivado` distingue lo que calculó el sistema de lo que escribió el
    usuario. La pantalla lo muestra porque no es lo mismo un ideal derivado de
    una regla proporcional que uno que alguien afirmó a mano.
    """

    centro_id: int
    dias_habiles: Decimal
    dias_trabajados: Decimal | None
    derivado: bool


class AgroCalendarioService:
    """Lectura y parametrización del calendario agropecuario."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion

    # ── Consulta ──────────────────────────────────────────────────────────────

    def dias_por_centro(self, periodo: Periodo, fecha_corte: date) -> dict[int, DiasCentro]:
        """Días hábiles y trabajados de cada centro con calendario en el período."""
        filas = self._sesion.execute(
            select(AgroCalendario).where(AgroCalendario.periodo_id == periodo.id)
        ).scalars()

        resultado: dict[int, DiasCentro] = {}
        for fila in filas:
            explicito = fila.dias_trabajados is not None
            trabajados = (
                fila.dias_trabajados
                if explicito
                else derivar_dias_trabajados(
                    fila.dias_habiles, periodo.anio, periodo.mes, fecha_corte
                )
            )
            resultado[fila.centro_id] = DiasCentro(
                centro_id=fila.centro_id,
                dias_habiles=fila.dias_habiles,
                dias_trabajados=trabajados,
                derivado=not explicito,
            )
        return resultado

    def listar(self, codigo_periodo: str, hasta: date | None = None) -> list[CalendarioAgroSalida]:
        """Calendario de los centros que tienen fila en el período."""
        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        corte = fecha_corte_efectiva(periodo, hasta)
        dias = self.dias_por_centro(periodo, corte)

        centros = self._centros()
        salida: list[CalendarioAgroSalida] = []
        for centro in sorted(centros.values(), key=lambda c: c.clave):
            datos = dias.get(centro.id)
            if datos is None:
                continue
            salida.append(
                CalendarioAgroSalida(
                    centro=centro.clave,
                    nombre=centro.nombre,
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
        codigo_centro: str,
        codigo_periodo: str,
        dias_habiles: Decimal,
        dias_trabajados: Decimal | None,
        *,
        usuario_id: int | None = None,
        hasta: date | None = None,
    ) -> CalendarioAgroSalida:
        """Fija los días de un centro.

        `dias_trabajados = None` devuelve el centro al cálculo derivado. El
        calendario **no** se bloquea con el cierre de período: cerrar congela el
        presupuesto (§7), y corregir a posteriori los días hábiles de un mes ya
        cerrado es justamente lo que permite recalcular un ideal mal puesto sin
        tocar un solo peso de presupuesto.

        El centro tiene que existir en el catálogo, y ahí no hay forma de
        evitarlo: el calendario se cuelga de una fila concreta de
        `agro_dimensiones` y el catálogo lo puebla la ingesta. Parametrizar el
        calendario de un centro que nunca facturó no tiene sentido —no tendría
        venta que medir— y el mensaje lo dice en lugar de crear una fila
        fantasma.
        """
        clave = normalizar_clave(TipoDimension.CENTRO_OPERACION, codigo_centro)
        centro = self._sesion.execute(
            select(AgroDimension).where(
                AgroDimension.tipo == TipoDimension.CENTRO_OPERACION.value,
                AgroDimension.clave == clave,
            )
        ).scalar_one_or_none()
        if centro is None:
            raise ErrorNoEncontrado(
                f"No existe el centro de operación {codigo_centro!r} en el catálogo "
                "agropecuario. Los centros los da de alta la ingesta con la primera venta "
                "que traen; ejecute la carga del rango antes de parametrizar su calendario."
            )

        periodo = obtener_o_crear_periodo(self._sesion, codigo_periodo)
        corte = fecha_corte_efectiva(periodo, hasta)

        fila = self._sesion.execute(
            select(AgroCalendario).where(
                AgroCalendario.periodo_id == periodo.id,
                AgroCalendario.centro_id == centro.id,
            )
        ).scalar_one_or_none()

        if fila is None:
            fila = AgroCalendario(periodo_id=periodo.id, centro_id=centro.id)
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
        return CalendarioAgroSalida(
            centro=centro.clave,
            nombre=centro.nombre,
            dias_habiles=dias_habiles,
            dias_trabajados=efectivos,
            ideal=ideal(efectivos, dias_habiles),
            fecha_corte=corte,
            derivado=dias_trabajados is None,
        )

    # ── Interno ───────────────────────────────────────────────────────────────

    def _centros(self) -> dict[int, AgroDimension]:
        return {
            centro.id: centro
            for centro in self._sesion.execute(
                select(AgroDimension).where(
                    AgroDimension.tipo == TipoDimension.CENTRO_OPERACION.value
                )
            ).scalars()
        }
