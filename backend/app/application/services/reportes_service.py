"""Reportes: agregación de la venta y armado de `FilaIndicadores` (§4 y §6).

Es el servicio grande. Su trabajo es siempre el mismo en cuatro pantallas
distintas: agregar el detalle de venta, cruzarlo con el presupuesto y el
calendario, y entregarle al dominio los insumos para que calcule los
indicadores. **Aquí no se calcula ningún indicador a mano**: todos salen de
`app.domain.indicadores`, que es donde están probados.

Dos decisiones que conviene tener presentes al leer el código:

- La agregación se hace **en la base**, con `GROUP BY`, no en Python. Son
  ~440 000 filas por mes; traerlas al proceso para sumarlas sería malgastar
  memoria y tiempo en algo que el motor hace mejor.
- Los porcentajes de un nivel superior **se recalculan sobre los totales**,
  nunca se promedian los de sus hijos (§7). Por eso cada nivel vuelve a llamar
  a `calcular_indicadores` con sus propias sumas.
- De la venta no se agrega solo cuánto: también **si el conjunto tiene el costo
  completo**. `SUM(costo_promedio)` ignora los nulos, y una fuente que no
  entrega costo —la de 409 PEREIRA— hacía que el margen saliera al 100 %. Ver
  `Totales.costo_completo` y §4.4.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.application.services.calendario_service import CalendarioService, DiasZona
from app.application.services.periodos import (
    buscar_periodo,
    fecha_corte_efectiva,
    obtener_periodo,
    periodo_anterior,
)
from app.core.config import obtener_settings
from app.domain.calendario import presupuesto_diario
from app.domain.enums import AgrupacionClientes, Medida
from app.domain.indicadores import (
    InsumosIndicadores,
    ResultadoIndicadores,
    calcular_indicadores,
    dividir,
    margen_porcentaje,
    redondear,
    redondear_no_nulo,
    redondear_porcentaje,
)
from app.domain.semaforo import UmbralesSemaforo
from app.infrastructure.models.catalogo import Categoria
from app.infrastructure.models.organizacion import Grupo, PuntoVenta
from app.infrastructure.models.periodo import Periodo
from app.infrastructure.models.presupuesto import Presupuesto
from app.infrastructure.models.venta import Cliente, VentaLinea
from app.schemas.reportes import (
    FilaCategoria,
    FilaClientes,
    FilaGrupo,
    FilaIndicadores,
    FilaPuntoVenta,
    FilaVentaDiaria,
    ParametrosCalculo,
    PuntoVentaSinPresupuesto,
    RespuestaClientes,
    RespuestaCumplimiento,
    RespuestaTablero,
    RespuestaVentaDiaria,
)

CERO = Decimal("0")

#: Clave de agregación del detalle de venta.
ClaveCelda = tuple[int, int]

#: Una magnitud del calendario derivada del par `(H, T)` de un punto de venta.
#: Se pondera con la misma máquina —`_ponderar`— sea cual sea, de modo que `H`,
#: `T` e `ideal` de un agregado usan exactamente los mismos pesos.
_Magnitud = Callable[[Decimal | None, Decimal | None], Decimal | None]


def _magnitud_habiles(habiles: Decimal | None, trabajados: Decimal | None) -> Decimal | None:
    return habiles


def _magnitud_trabajados(habiles: Decimal | None, trabajados: Decimal | None) -> Decimal | None:
    return trabajados


def _magnitud_ideal(habiles: Decimal | None, trabajados: Decimal | None) -> Decimal | None:
    """`ideal_i = T_i / H_i` del punto, antes de ponderar."""
    return dividir(trabajados, habiles)


@dataclass
class Totales:
    """Sumas de un corte. Mutable a propósito: se acumula sobre él."""

    valor: Decimal = CERO
    kilos: Decimal = CERO
    costo: Decimal = CERO
    #: ¿Traen costo **todas** las líneas que se sumaron aquí?
    #:
    #: `SUM(costo_promedio)` ignora los nulos en silencio, así que la suma sola
    #: no distingue «costó 100» de «no sé cuánto costó». La distinción importa:
    #: 409 PEREIRA llega por el único endpoint de la API que no entrega el
    #: costo, y sin este indicador su margen se publicaba como 100 % (§4.4).
    #: Basta una línea sin costo para que el conjunto entero deje de tener
    #: margen calculable, por eso se propaga con `and` al agregar.
    costo_completo: bool = True

    def sumar(self, otro: Totales) -> None:
        self.valor += otro.valor
        self.kilos += otro.kilos
        self.costo += otro.costo
        self.costo_completo = self.costo_completo and otro.costo_completo

    def medida(self, medida: Medida) -> Decimal:
        return self.valor if medida is Medida.VALOR else self.kilos


#: Las cinco columnas con las que se arma un `Totales` desde un `GROUP BY` sobre
#: `venta_lineas`.
#:
#: Las dos últimas son el indicador de costo completo: `COUNT(*)` cuenta las
#: líneas del grupo y `COUNT(costo_promedio)` **no cuenta los nulos**, así que
#: son iguales si y solo si todas las líneas traen costo. Se resuelve en la base
#: y en la misma pasada —una consulta aparte para preguntarlo sería otro barrido
#: de la tabla caliente— y funciona igual en PostgreSQL, SQL Server y SQLite,
#: que es más de lo que se puede decir de `FILTER (WHERE ...)`.
COLUMNAS_TOTALES = (
    func.sum(VentaLinea.valor_subtotal),
    func.sum(VentaLinea.cantidad_inv),
    func.sum(VentaLinea.costo_promedio),
    func.count(),
    func.count(VentaLinea.costo_promedio),
)


def _totales_de(
    valor: Decimal | None,
    kilos: Decimal | None,
    costo: Decimal | None,
    lineas: int | None,
    lineas_con_costo: int | None,
) -> Totales:
    """Una fila de `COLUMNAS_TOTALES` a `Totales`."""
    return Totales(
        valor=Decimal(valor or 0),
        kilos=Decimal(kilos or 0),
        costo=Decimal(costo or 0),
        costo_completo=(lineas or 0) == (lineas_con_costo or 0),
    )


@dataclass
class Presupuestado:
    """Presupuesto de un corte, en las dos medidas."""

    monto: Decimal = CERO
    kilos: Decimal = CERO
    #: Si existe al menos una fila de presupuesto. Un presupuesto de cero
    #: capturado por el negocio no es lo mismo que la ausencia de presupuesto:
    #: el primero da cumplimiento indefinido igual, pero el segundo además
    #: significa que nadie parametrizó todavía.
    definido: bool = False

    def sumar(self, otro: Presupuestado) -> None:
        self.monto += otro.monto
        self.kilos += otro.kilos
        self.definido = self.definido or otro.definido

    def medida(self, medida: Medida) -> Decimal | None:
        if not self.definido:
            return None
        return self.monto if medida is Medida.VALOR else self.kilos


@dataclass(frozen=True, slots=True)
class FiltrosReporte:
    """Los filtros comunes a todos los reportes (`docs/API.md`)."""

    periodo: str
    hasta: date | None = None
    grupo: str | None = None
    punto_venta: str | None = None
    categoria: str | None = None
    medida: Medida = Medida.VALOR
    #: Puntos de venta a los que el usuario tiene alcance. `None` = todos.
    alcance: list[int] | None = None


@dataclass
class _Contexto:
    """Todo lo que hace falta para armar cualquier reporte del período."""

    periodo: Periodo
    fecha_corte: date
    medida: Medida
    umbrales: UmbralesSemaforo
    puntos: dict[int, PuntoVenta]
    categorias: dict[int, Categoria]
    dias: dict[int, DiasZona]
    #: Los filtros de la petición, incluido el **alcance** del usuario. Viajan
    #: enteros porque hay consultas —la venta sin presupuesto— que no salen de
    #: `puntos` y aun así tienen que respetar lo que el usuario puede ver.
    filtros: FiltrosReporte
    #: Categoría del filtro ya resuelta a `id`, o `None` si no se filtró. Se
    #: resuelve una vez y la usan todas las consultas del reporte.
    categoria_id: int | None = None
    venta: dict[ClaveCelda, Totales] = field(default_factory=dict)
    presupuesto: dict[ClaveCelda, Presupuestado] = field(default_factory=dict)
    venta_anterior: dict[ClaveCelda, Totales] = field(default_factory=dict)
    #: Venta de puntos no presupuestados, aparte del consolidado (§3.1).
    venta_sin_presupuesto: dict[int, Totales] = field(default_factory=dict)


class ReportesService:
    """Armado de los reportes gerenciales."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion
        self._settings = obtener_settings()
        self._umbrales = UmbralesSemaforo(factor_amarillo=self._settings.factor_semaforo_amarillo)

    # ── Tablero gerencial ─────────────────────────────────────────────────────

    def tablero(self, filtros: FiltrosReporte) -> RespuestaTablero:
        """Consolidado de compañía y comparativo de los cuatro grupos."""
        ctx = self._construir_contexto(filtros)

        por_pdv = self._totales_por_punto_venta(ctx)
        consolidado = self._fila_agregada(ctx, list(por_pdv))

        grupos: list[FilaGrupo] = []
        for grupo in self._grupos_ordenados():
            ids = [pid for pid, p in ctx.puntos.items() if p.grupo_id == grupo.id]
            if not ids:
                continue
            base = self._fila_agregada(ctx, ids)
            grupos.append(FilaGrupo(codigo=grupo.codigo, nombre=grupo.nombre, **base.model_dump()))

        return RespuestaTablero(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            medida=ctx.medida,
            consolidado=consolidado,
            grupos=grupos,
            sin_presupuesto=self._filas_sin_presupuesto(ctx),
            parametros_calculo=self._parametros(ctx, consolidado),
        )

    # ── Cumplimiento por punto de venta ───────────────────────────────────────

    def cumplimiento(self, filtros: FiltrosReporte) -> RespuestaCumplimiento:
        """La tabla del Excel, viva: un punto por fila, expandible a categorías."""
        ctx = self._construir_contexto(filtros)

        filas: list[FilaPuntoVenta] = []
        for punto in sorted(ctx.puntos.values(), key=lambda p: p.codigo_co):
            base = self._fila_agregada(ctx, [punto.id])
            categorias = [
                FilaCategoria(
                    categoria=ctx.categorias[cat_id].nombre,
                    **self._fila_celda(ctx, punto.id, cat_id).model_dump(),
                )
                for cat_id in self._categorias_con_dato(ctx, punto.id)
            ]
            filas.append(
                FilaPuntoVenta(
                    punto_venta=punto.codigo_co,
                    nombre=punto.nombre,
                    categorias=categorias,
                    **base.model_dump(),
                )
            )

        return RespuestaCumplimiento(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            medida=ctx.medida,
            filas=filas,
            sin_presupuesto=self._filas_sin_presupuesto(ctx),
            parametros_calculo=self._parametros(ctx, self._fila_agregada(ctx, list(ctx.puntos))),
        )

    # ── Venta diaria ──────────────────────────────────────────────────────────

    def venta_diaria(self, filtros: FiltrosReporte) -> RespuestaVentaDiaria:
        """Detalle día por día del mes, con el presupuesto diario derivado."""
        ctx = self._construir_contexto(filtros, cargar_anio_anterior=False)

        fechas = _rango_fechas(ctx.periodo.primer_dia, ctx.fecha_corte)
        columna = (
            VentaLinea.valor_subtotal if ctx.medida is Medida.VALOR else VentaLinea.cantidad_inv
        )
        consulta = (
            select(VentaLinea.punto_venta_id, VentaLinea.fecha, func.sum(columna))
            .where(
                VentaLinea.periodo_id == ctx.periodo.id,
                VentaLinea.fecha <= ctx.fecha_corte,
            )
            .group_by(VentaLinea.punto_venta_id, VentaLinea.fecha)
        )
        consulta = self._aplicar_filtro_puntos(consulta, ctx)
        if ctx.categoria_id is not None:
            consulta = consulta.where(VentaLinea.categoria_id == ctx.categoria_id)

        por_dia: dict[int, dict[date, Decimal]] = defaultdict(dict)
        for punto_id, dia, total in self._sesion.execute(consulta):
            por_dia[punto_id][dia] = Decimal(total or 0)

        decimales = ctx.medida.decimales
        filas: list[FilaVentaDiaria] = []
        diario: dict[str, Decimal | None] = {}
        for punto in sorted(ctx.puntos.values(), key=lambda p: p.codigo_co):
            valores = [por_dia.get(punto.id, {}).get(dia) for dia in fechas]
            total = sum((v for v in valores if v is not None), start=CERO)
            filas.append(
                FilaVentaDiaria(
                    punto_venta=punto.codigo_co,
                    nombre=punto.nombre,
                    valores=[redondear(v, decimales) for v in valores],
                    total=redondear_no_nulo(total, decimales),
                )
            )
            diario[punto.codigo_co] = redondear(
                presupuesto_diario(
                    self._presupuesto_punto(ctx, punto.id).medida(ctx.medida),
                    self._dias_punto(ctx, punto.id)[0],
                ),
                decimales,
            )

        return RespuestaVentaDiaria(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            medida=ctx.medida,
            fechas=fechas,
            presupuesto_diario_por_pdv=diario,
            filas=filas,
            parametros_calculo=self._parametros(ctx, self._fila_agregada(ctx, list(ctx.puntos))),
        )

    # ── Clientes, vendedores y canales ────────────────────────────────────────

    def clientes(self, filtros: FiltrosReporte, por: AgrupacionClientes) -> RespuestaClientes:
        """Venta por cliente, vendedor, canal o condición de pago.

        El reporte por vendedor no existe hoy en el Excel y el negocio
        claramente lo quiere: sale del cruce con el catálogo de clientes (§3.4).

        Dos detalles que el contrato exige y el código no cumplía:

        - El filtro `categoria` aplica aquí como en todos los reportes
          (`docs/API.md`: «Todos aceptan los mismos filtros»). Sin él, pedir los
          clientes de RES devolvía la venta de las ocho categorías.
        - La `participacion` se divide entre la venta **total del corte**, que
          se consulta aparte, no entre la suma de las filas que sobrevivieron al
          `limit`. Con el top-N como denominador las participaciones suman 100 %
          por construcción y un cliente que es el 45 % de la compañía se publica
          como 60 %.
        """
        ctx = self._construir_contexto(filtros, cargar_anio_anterior=False)

        criterios = [
            VentaLinea.periodo_id == ctx.periodo.id,
            VentaLinea.fecha <= ctx.fecha_corte,
            VentaLinea.punto_venta_id.in_(list(ctx.puntos) or [-1]),
        ]
        if ctx.categoria_id is not None:
            criterios.append(VentaLinea.categoria_id == ctx.categoria_id)

        clave, nombre = _columnas_agrupacion(por)
        consulta = (
            select(clave, nombre, *COLUMNAS_TOTALES)
            .join(Cliente, VentaLinea.cliente_id == Cliente.id, isouter=True)
            .where(*criterios)
            .group_by(clave, nombre)
            .order_by(func.sum(VentaLinea.valor_subtotal).desc())
            .limit(self._settings.max_filas_reporte_clientes)
        )

        crudas = list(self._sesion.execute(consulta))
        total_venta = Decimal(
            self._sesion.scalar(select(func.sum(VentaLinea.valor_subtotal)).where(*criterios)) or 0
        )

        filas: list[FilaClientes] = []
        for valor_clave, valor_nombre, venta, kilos, costo, lineas, con_costo in crudas:
            totales = _totales_de(venta, kilos, costo, lineas, con_costo)
            filas.append(
                FilaClientes(
                    clave=str(valor_clave) if valor_clave is not None else "SIN DATO",
                    nombre=str(valor_nombre) if valor_nombre is not None else "SIN DATO",
                    venta=redondear_no_nulo(totales.valor, 2),
                    kilos=redondear_no_nulo(totales.kilos, 3),
                    # La misma regla que en el resto de los reportes: una línea
                    # sin costo deja el grupo sin margen calculable (§4.4).
                    margen_porcentaje=redondear_porcentaje(
                        margen_porcentaje(
                            totales.valor, totales.costo, costo_completo=totales.costo_completo
                        )
                    ),
                    participacion=redondear_porcentaje(dividir(totales.valor, total_venta)),
                )
            )

        return RespuestaClientes(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            por=por.value,
            filas=filas,
            parametros_calculo=self._parametros(ctx, None),
        )

    # ── Construcción del contexto ─────────────────────────────────────────────

    def _construir_contexto(
        self, filtros: FiltrosReporte, *, cargar_anio_anterior: bool = True
    ) -> _Contexto:
        periodo = obtener_periodo(self._sesion, filtros.periodo)
        corte = fecha_corte_efectiva(periodo, filtros.hasta)

        puntos = self._puntos_visibles(filtros)
        categorias = {
            c.id: c
            for c in self._sesion.execute(select(Categoria).order_by(Categoria.orden)).scalars()
        }

        ctx = _Contexto(
            periodo=periodo,
            fecha_corte=corte,
            medida=filtros.medida,
            umbrales=self._umbrales,
            puntos=puntos,
            categorias=categorias,
            dias=CalendarioService(self._sesion).dias_por_zona(periodo, corte),
            filtros=filtros,
            categoria_id=(
                self._categoria_por_nombre(filtros.categoria).id if filtros.categoria else None
            ),
        )

        ctx.venta = self._agregar_venta(periodo, corte, ctx, ctx.categoria_id)
        ctx.presupuesto = self._agregar_presupuesto(periodo, ctx, ctx.categoria_id)
        ctx.venta_sin_presupuesto = self._agregar_venta_sin_presupuesto(ctx)

        if cargar_anio_anterior:
            anterior = buscar_periodo(self._sesion, periodo_anterior(periodo.codigo))
            if anterior is not None:
                ctx.venta_anterior = self._agregar_venta(
                    anterior, _corte_equivalente(anterior, corte), ctx, ctx.categoria_id
                )

        return ctx

    def _consulta_alcance(self, filtros: FiltrosReporte) -> Select[tuple[PuntoVenta]]:
        """Los puntos de venta que esta petición puede mirar, presupuestados o no.

        Es el perímetro del reporte: el filtro de grupo, el de punto de venta y
        —sobre todo— el **alcance del usuario**, que es una regla de seguridad y
        no una preferencia de pantalla. Todo lo que consulte venta parte de
        aquí; ninguna consulta se salta este perímetro.

        No filtra por `activo`. Desactivar un punto de venta es una operación de
        catálogo —se cerró el local—, no una instrucción de borrar del histórico
        la venta que ese punto ya hizo. Si se filtrara, cerrar CONCORDE a mitad
        de mes evaporaría sus 500 millones del reporte del mes, que es
        exactamente lo que §7 prohíbe: «nunca se descarta».
        """
        consulta = select(PuntoVenta)
        if filtros.grupo:
            consulta = consulta.join(Grupo, PuntoVenta.grupo_id == Grupo.id).where(
                Grupo.codigo == filtros.grupo
            )
        if filtros.punto_venta:
            consulta = consulta.where(PuntoVenta.codigo_co == filtros.punto_venta.strip())
        if filtros.alcance is not None:
            consulta = consulta.where(PuntoVenta.id.in_(filtros.alcance or [-1]))
        return consulta

    def _puntos_visibles(self, filtros: FiltrosReporte) -> dict[int, PuntoVenta]:
        """Puntos presupuestados que el filtro y el alcance del usuario permiten.

        Los no presupuestados quedan fuera de esta lista a propósito: su venta
        se reporta en el bloque `sin_presupuesto`, nunca mezclada.
        """
        consulta = self._consulta_alcance(filtros).where(PuntoVenta.presupuestado.is_(True))
        return {p.id: p for p in self._sesion.execute(consulta).scalars()}

    def _agregar_venta(
        self,
        periodo: Periodo,
        corte: date,
        ctx: _Contexto,
        categoria_id: int | None,
    ) -> dict[ClaveCelda, Totales]:
        """La consulta caliente: `GROUP BY punto_venta, categoria`.

        La cubre `ix_venta_periodo_pdv_categoria`, que empieza por `periodo_id`
        —igualdad—, sigue por `fecha` —rango— y termina por las dos claves de
        agrupación.
        """
        consulta = (
            select(VentaLinea.punto_venta_id, VentaLinea.categoria_id, *COLUMNAS_TOTALES)
            .where(VentaLinea.periodo_id == periodo.id, VentaLinea.fecha <= corte)
            .group_by(VentaLinea.punto_venta_id, VentaLinea.categoria_id)
        )
        consulta = self._aplicar_filtro_puntos(consulta, ctx)
        if categoria_id is not None:
            consulta = consulta.where(VentaLinea.categoria_id == categoria_id)

        return {
            (punto_id, cat_id): _totales_de(valor, kilos, costo, lineas, con_costo)
            for punto_id, cat_id, valor, kilos, costo, lineas, con_costo in self._sesion.execute(
                consulta
            )
        }

    def _agregar_presupuesto(
        self, periodo: Periodo, ctx: _Contexto, categoria_id: int | None
    ) -> dict[ClaveCelda, Presupuestado]:
        consulta = select(
            Presupuesto.punto_venta_id,
            Presupuesto.categoria_id,
            Presupuesto.monto,
            Presupuesto.kilos,
        ).where(Presupuesto.periodo_id == periodo.id)
        if ctx.puntos:
            consulta = consulta.where(Presupuesto.punto_venta_id.in_(list(ctx.puntos)))
        if categoria_id is not None:
            consulta = consulta.where(Presupuesto.categoria_id == categoria_id)

        return {
            (punto_id, cat_id): Presupuestado(
                monto=Decimal(monto or 0), kilos=Decimal(kilos or 0), definido=True
            )
            for punto_id, cat_id, monto, kilos in self._sesion.execute(consulta)
        }

    def _agregar_venta_sin_presupuesto(self, ctx: _Contexto) -> dict[int, Totales]:
        """Venta de los puntos del perímetro que no entraron en el consolidado.

        «La venta de un PDV sin presupuesto se reporta aparte, nunca se descarta
        en silencio» (§3.1 y §7). Dos precisiones que el código no tenía:

        - **Respeta el alcance.** Es venta de un punto de venta concreto, no una
          curiosidad del período: un JEFE_PDV con alcance sobre MALAMBO no tiene
          por qué recibir la venta de 432 EVENTOS BUCARAMANGA. Que el bloque se
          llame «informativo» no lo saca del control de acceso.
        - **Se define por diferencia, no por la bandera `presupuestado`.** Aquí
          entra todo punto del perímetro que **no** esté ya en `ctx.puntos`. La
          bandera decía quién *debería* estar presupuestado; la diferencia dice
          quién realmente no entró en el consolidado, que es lo que hay que
          publicar aparte para que la venta ingerida cuadre. Con la bandera, un
          punto presupuestado pero excluido del consolidado por cualquier motivo
          desaparecía por completo del reporte.
        """
        perimetro = {
            p.id for p in self._sesion.execute(self._consulta_alcance(ctx.filtros)).scalars()
        }
        candidatos = perimetro - set(ctx.puntos)
        if not candidatos:
            return {}

        consulta = (
            select(VentaLinea.punto_venta_id, *COLUMNAS_TOTALES)
            .where(
                VentaLinea.periodo_id == ctx.periodo.id,
                VentaLinea.fecha <= ctx.fecha_corte,
                VentaLinea.punto_venta_id.in_(sorted(candidatos)),
            )
            .group_by(VentaLinea.punto_venta_id)
        )
        if ctx.categoria_id is not None:
            consulta = consulta.where(VentaLinea.categoria_id == ctx.categoria_id)
        return {
            punto_id: _totales_de(valor, kilos, costo, lineas, con_costo)
            for punto_id, valor, kilos, costo, lineas, con_costo in self._sesion.execute(consulta)
        }

    def _aplicar_filtro_puntos(self, consulta: Select, ctx: _Contexto) -> Select:  # type: ignore[type-arg]
        """Restringe la consulta a los puntos visibles del contexto."""
        return consulta.where(VentaLinea.punto_venta_id.in_(list(ctx.puntos) or [-1]))

    # ── Armado de filas ───────────────────────────────────────────────────────

    def _totales_por_punto_venta(self, ctx: _Contexto) -> dict[int, Totales]:
        """Colapsa el detalle por celda a un total por punto de venta.

        Incluye **todos** los puntos visibles, también los que aún no tienen
        venta registrada: si se derivaran las claves de `ctx.venta`, un punto
        presupuestado que todavía no ha vendido desaparecería del consolidado y
        su presupuesto dejaría de contar en el denominador. El cumplimiento de
        la compañía saldría inflado justo al principio del mes, que es cuando
        más puntos llevan cero.
        """
        totales: dict[int, Totales] = {punto_id: Totales() for punto_id in ctx.puntos}
        for (punto_id, _categoria_id), parcial in ctx.venta.items():
            totales.setdefault(punto_id, Totales()).sumar(parcial)
        return totales

    def _fila_celda(self, ctx: _Contexto, punto_id: int, categoria_id: int) -> FilaIndicadores:
        """Fila de una celda (punto de venta × categoría)."""
        venta = ctx.venta.get((punto_id, categoria_id), Totales())
        presu = ctx.presupuesto.get((punto_id, categoria_id), Presupuestado())
        anterior = ctx.venta_anterior.get((punto_id, categoria_id))
        habiles, trabajados = self._dias_punto(ctx, punto_id)

        return self._a_fila(
            ctx,
            InsumosIndicadores(
                venta=venta.medida(ctx.medida),
                venta_valor=venta.valor,
                costo=venta.costo,
                costo_completo=venta.costo_completo,
                presupuesto=presu.medida(ctx.medida),
                venta_anio_anterior=anterior.medida(ctx.medida) if anterior else None,
                dias_habiles=habiles,
                dias_trabajados=trabajados,
            ),
        )

    def _fila_agregada(self, ctx: _Contexto, puntos_ids: list[int]) -> FilaIndicadores:
        """Fila de un conjunto de puntos: punto de venta, grupo o consolidado.

        Se suman las magnitudes y **se recalculan** los porcentajes. Promediar
        los porcentajes de los hijos daría otro número, y sería el equivocado.

        El crecimiento se calcula sobre la **venta comparable**: la de los
        puntos de venta que tienen dato del año anterior, en los dos lados de la
        división. Es el *same-store sales* del comercio. Con historia parcial
        —dos puntos vendiendo en 2026 y uno solo cargado de 2025— comparar el
        total contra el parcial publica un +100 % que nadie vivió. La
        restricción es por punto de venta, no por celda: un punto que empezó a
        vender una categoría nueva sí creció, y esa venta cuenta.
        """
        ids = set(puntos_ids)
        venta = Totales()
        comparable = Totales()
        anterior = Totales()
        presu = Presupuestado()
        con_historia = {punto_id for (punto_id, _cat) in ctx.venta_anterior}

        for (punto_id, _cat), totales in ctx.venta.items():
            if punto_id in ids:
                venta.sumar(totales)
                if punto_id in con_historia:
                    comparable.sumar(totales)
        for (punto_id, _cat), totales in ctx.venta_anterior.items():
            if punto_id in ids:
                anterior.sumar(totales)
        for (punto_id, _cat), valores in ctx.presupuesto.items():
            if punto_id in ids:
                presu.sumar(valores)

        hay_anterior = bool(con_historia & ids)
        habiles, trabajados, ideal_ponderado = self._dias_agregados(ctx, puntos_ids)

        return self._a_fila(
            ctx,
            InsumosIndicadores(
                venta=venta.medida(ctx.medida),
                venta_valor=venta.valor,
                costo=venta.costo,
                # Basta una línea sin costo en cualquiera de los puntos del
                # conjunto para que el agregado no tenga margen calculable. En
                # el consolidado de la compañía eso significa, hoy, que PEREIRA
                # deja al consolidado sin margen: es la consecuencia correcta
                # —no se puede calcular— y la que crea la presión para que la
                # API entregue el costo (§4.4).
                costo_completo=venta.costo_completo,
                presupuesto=presu.medida(ctx.medida),
                venta_anio_anterior=anterior.medida(ctx.medida) if hay_anterior else None,
                venta_comparable=comparable.medida(ctx.medida) if hay_anterior else None,
                dias_habiles=habiles,
                dias_trabajados=trabajados,
                ideal_agregado=ideal_ponderado,
            ),
        )

    def _a_fila(self, ctx: _Contexto, insumos: InsumosIndicadores) -> FilaIndicadores:
        resultado: ResultadoIndicadores = calcular_indicadores(
            insumos, ctx.umbrales, decimales_medida=ctx.medida.decimales
        )
        return FilaIndicadores(
            presupuesto=resultado.presupuesto,
            venta=resultado.venta,
            cumplimiento=resultado.cumplimiento,
            ideal=resultado.ideal,
            brecha=resultado.brecha,
            semaforo=resultado.semaforo,
            proyeccion=resultado.proyeccion,
            cumplimiento_proyectado=resultado.cumplimiento_proyectado,
            venta_diaria_promedio=resultado.venta_diaria_promedio,
            venta_diaria_requerida=resultado.venta_diaria_requerida,
            venta_anio_anterior=resultado.venta_anio_anterior,
            crecimiento=resultado.crecimiento,
            margen_valor=resultado.margen_valor,
            margen_porcentaje=resultado.margen_porcentaje,
            dias_habiles=resultado.dias_habiles,
            dias_trabajados=resultado.dias_trabajados,
        )

    def _filas_sin_presupuesto(self, ctx: _Contexto) -> list[PuntoVentaSinPresupuesto]:
        filas: list[PuntoVentaSinPresupuesto] = []
        for punto_id, totales in ctx.venta_sin_presupuesto.items():
            punto = self._sesion.get(PuntoVenta, punto_id)
            if punto is None:  # pragma: no cover - integridad referencial
                continue
            filas.append(
                PuntoVentaSinPresupuesto(
                    codigo_co=punto.codigo_co,
                    nombre=punto.nombre,
                    venta=redondear_no_nulo(totales.valor, 2),
                    kilos=redondear_no_nulo(totales.kilos, 3),
                )
            )
        return sorted(filas, key=lambda f: f.codigo_co)

    # ── Días hábiles y trabajados ─────────────────────────────────────────────

    def _dias_punto(self, ctx: _Contexto, punto_id: int) -> tuple[Decimal | None, Decimal | None]:
        punto = ctx.puntos.get(punto_id)
        if punto is None or punto.zona_id is None:
            return None, None
        datos = ctx.dias.get(punto.zona_id)
        if datos is None:
            return None, None
        return datos.dias_habiles, datos.dias_trabajados

    def _dias_agregados(
        self, ctx: _Contexto, puntos_ids: list[int]
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """`H`, `T` e `ideal` de un conjunto de puntos que abarca varias zonas.

        Los tres se ponderan **por el presupuesto en pesos**, y devuelven la
        precisión completa. Tres decisiones, cada una con su motivo:

        1. **Ponderar por presupuesto y no promediar a secas.** Un grupo con un
           punto de 5 000 millones en una zona de 24 días y otro de 100 millones
           en una de 28.5 se parece muchísimo más a la zona grande; el promedio
           simple le pondría una vara que no le corresponde. Cuando no hay
           presupuesto contra el que ponderar queda el promedio simple de las
           zonas involucradas, que es lo único que hay.
        2. **Siempre en pesos, nunca en la medida en curso.** El calendario no
           sabe si el usuario está mirando pesos o kilos. Ponderar con el
           presupuesto de la medida hacía que el `ideal` —que es `T / H`, puro
           calendario— cambiara de valor al pulsar el interruptor pesos/kilos, y
           con él el semáforo. El presupuesto en pesos es la única vara estable.
        3. **`ideal` se pondera aparte, no se deriva de `T / H`.** La venta
           esperada al corte es `Σ(P_i × ideal_i)` y el presupuesto es `Σ P_i`,
           luego `ideal = Σ(P_i × ideal_i) / Σ P_i`. Ese número **no** coincide
           con el cociente de los promedios: `T / H` da la media de los días,
           que sirve para proyectar y para `H − T`, pero no es la media de los
           ideales. Publicar `T / H` como ideal del consolidado era medir a toda
           la compañía contra una vara que ninguna zona tiene.

        Con un solo punto de venta —o con todos en la misma zona— los tres
        valores son exactamente los de la zona, sin distorsión alguna.
        """
        pesos: dict[int, Decimal] = {}
        for punto_id in puntos_ids:
            # `Medida.VALOR` a propósito: ver punto 2 del docstring.
            peso = self._presupuesto_punto(ctx, punto_id).medida(Medida.VALOR)
            pesos[punto_id] = peso if peso is not None else CERO

        habiles = self._ponderar(ctx, puntos_ids, pesos, _magnitud_habiles)
        trabajados = self._ponderar(ctx, puntos_ids, pesos, _magnitud_trabajados)
        ideal_ponderado = self._ponderar(ctx, puntos_ids, pesos, _magnitud_ideal)
        return habiles, trabajados, ideal_ponderado

    def _ponderar(
        self,
        ctx: _Contexto,
        puntos_ids: list[int],
        pesos: dict[int, Decimal],
        magnitud: _Magnitud,
    ) -> Decimal | None:
        """Media de `magnitud` sobre los puntos, ponderada por `pesos`.

        Devuelve **precisión completa**. Redondear aquí era el defecto: `H` y
        `T` cuantizados a dos decimales alimentaban la proyección y la venta
        diaria requerida, y el error se multiplicaba por miles de millones. El
        redondeo es de publicación y vive en `calcular_indicadores`.
        """
        acumulado = CERO
        peso_total = CERO
        por_zona: dict[int, Decimal] = {}

        for punto_id in puntos_ids:
            valor = magnitud(*self._dias_punto(ctx, punto_id))
            if valor is None:
                continue
            punto = ctx.puntos.get(punto_id)
            if punto is not None and punto.zona_id is not None:
                por_zona[punto.zona_id] = valor
            peso = pesos.get(punto_id, CERO)
            acumulado += valor * peso
            peso_total += peso

        if peso_total > CERO:
            return acumulado / peso_total
        if not por_zona:
            return None
        return sum(por_zona.values(), start=CERO) / Decimal(len(por_zona))

    def _presupuesto_punto(self, ctx: _Contexto, punto_id: int) -> Presupuestado:
        total = Presupuestado()
        for (pid, _cat), valores in ctx.presupuesto.items():
            if pid == punto_id:
                total.sumar(valores)
        return total

    # ── Auxiliares ────────────────────────────────────────────────────────────

    def _categorias_con_dato(self, ctx: _Contexto, punto_id: int) -> list[int]:
        """Categorías con venta o con presupuesto en ese punto.

        No todos los puntos manejan las ocho: LA43 y ALAMEDA no tienen ASADERO
        y su ausencia no es un error (§3.1). Listar las ocho siempre llenaría el
        reporte de ceros que no significan nada.
        """
        ids = {cat for (pid, cat) in ctx.venta if pid == punto_id}
        ids |= {cat for (pid, cat) in ctx.presupuesto if pid == punto_id}
        return sorted(ids, key=lambda c: ctx.categorias[c].orden if c in ctx.categorias else 99)

    def _grupos_ordenados(self) -> list[Grupo]:
        """Todos los grupos, activos o no.

        No se filtra por `activo` por la misma razón que en `_consulta_alcance`,
        y aquí además el filtro descuadraba el tablero: los puntos de un grupo
        desactivado seguían sumando en el consolidado —el consolidado se arma
        desde los puntos de venta, no desde los grupos— pero su fila
        desaparecía del comparativo, y la suma de las filas visibles dejaba de
        dar el total sin que nadie pudiera ver por qué. Los grupos que no tienen
        ningún punto de venta en el corte se omiten más adelante, que es el
        único motivo legítimo para no publicar una fila.
        """
        return list(
            self._sesion.execute(select(Grupo).order_by(Grupo.orden, Grupo.codigo)).scalars()
        )

    def _categoria_por_nombre(self, nombre: str) -> Categoria:
        from app.core.errors import ErrorNoEncontrado

        categoria = self._sesion.execute(
            select(Categoria).where(Categoria.nombre == nombre.strip().upper())
        ).scalar_one_or_none()
        if categoria is None:
            raise ErrorNoEncontrado(f"No existe la categoría {nombre!r}.")
        return categoria

    def _parametros(self, ctx: _Contexto, fila: FilaIndicadores | None) -> ParametrosCalculo:
        return ParametrosCalculo(
            fecha_corte=ctx.fecha_corte,
            dias_habiles=fila.dias_habiles if fila else None,
            dias_trabajados=fila.dias_trabajados if fila else None,
            umbrales=ctx.umbrales.a_diccionario(),
        )


# ── Funciones auxiliares de módulo ────────────────────────────────────────────


def _rango_fechas(desde: date, hasta: date) -> list[date]:
    if hasta < desde:
        return []
    return [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]


def _corte_equivalente(periodo: Periodo, corte: date) -> date:
    """Mismo día del mes en el período del año anterior.

    SUPUESTO: el crecimiento compara lo comparable, es decir la venta del año
    pasado **hasta el mismo día del mes**. Comparar los nueve primeros días de
    agosto de 2026 contra los treinta y uno de agosto de 2025 daría un
    decrecimiento del 70 % que no significaría nada.
    """
    from app.domain.calendario import dias_del_mes

    dia = min(corte.day, dias_del_mes(periodo.anio, periodo.mes))
    return date(periodo.anio, periodo.mes, dia)


def _columnas_agrupacion(por: AgrupacionClientes):  # type: ignore[no-untyped-def]
    """Columnas de clave y nombre para cada eje del reporte de clientes."""
    if por is AgrupacionClientes.CLIENTE:
        return VentaLinea.nit_cliente, Cliente.razon_social
    if por is AgrupacionClientes.VENDEDOR:
        return Cliente.vendedor, Cliente.vendedor
    if por is AgrupacionClientes.CANAL:
        return Cliente.canal, Cliente.canal
    return VentaLinea.condicion_pago, VentaLinea.condicion_pago
