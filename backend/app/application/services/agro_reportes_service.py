"""Reportes de la unidad Agropecuaria: resumen, cruces y venta diaria (§4 y §6).

Su trabajo es siempre el mismo en los tres reportes: agregar el detalle de
venta, cruzarlo con el presupuesto de **su** dimensión y con el calendario, y
entregarle al dominio los insumos para que calcule los indicadores. **Aquí no se
calcula ningún indicador a mano**: todos salen de `app.domain.indicadores`, que
es donde están escritos, probados y documentados. Las fórmulas de agropecuaria
son exactamente las mismas que las de carnes —cumplimiento, ideal, brecha,
proyección, venta diaria requerida, margen ponderado— y reescribirlas sería
crear una segunda verdad.

── Las cinco reglas que gobiernan este archivo ───────────────────────────────

**1. El impuesto no suma, nunca.** Toda consulta lleva
`es_impuesto IS FALSE`, y la lleva porque está en `_filtros_base`, que es el
único sitio donde se construye el `WHERE`. Las filas de `TipoItem = IMPUESTO`
están guardadas —para poder conciliar con el origen— y no son venta: son
recaudo a nombre de terceros. Lo excluido se publica aparte, en
`ConciliacionAgro`, para que la diferencia contra el ERP tenga explicación.

**2. El cumplimiento se calcula DENTRO de una dimensión.** El presupuesto llega
como un `PlanPresupuesto` de una sola dimensión y nunca como un número suelto;
ver `agro_presupuesto_service`. Los ejes que no se presupuestan —cliente, grupo,
tipo de ítem— publican venta, kilos y margen, y todo lo que depende de la meta
viaja vacío. Vacío es información: dice que ahí no hay vara.

**3. Los porcentajes se recalculan sobre los totales, jamás se promedian** (§7).
Cada nivel vuelve a llamar a `calcular_indicadores` con sus propias sumas.

**4. Una sola línea sin costo deja al agregado sin margen calculable** (§4.4).
`SUM(total_costo)` ignora los nulos en silencio, así que la suma sola no
distingue «costó 100» de «no sé cuánto costó». `COUNT(*)` frente a
`COUNT(total_costo)` sí, y esa comparación se resuelve en la misma pasada.

**5. Lo que llega vacío se publica, no se descarta.** `SIN GRUPO` es una fila
más del reporte y sale con el 22 % de la venta que le corresponde. Filtrarla
haría que el eje «grupo» sumara menos que el eje «especie» y nadie sabría por
qué.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.application.services.agro_calendario_service import AgroCalendarioService, DiasCentro
from app.application.services.agro_ingesta_service import totales_impuesto
from app.application.services.agro_presupuesto_service import (
    AgroPresupuestoService,
    PlanPresupuesto,
)
from app.application.services.periodos import fecha_corte_efectiva, obtener_periodo
from app.application.services.reportes_service import (
    MAX_DIAS_RANGO,
    ErrorRangoExcesivo,
    ErrorRangoInvertido,
)
from app.core.config import obtener_settings
from app.domain.calendario import presupuesto_diario
from app.domain.enums import Medida
from app.domain.indicadores import (
    InsumosIndicadores,
    calcular_indicadores,
    dividir,
    redondear,
    redondear_no_nulo,
    redondear_porcentaje,
)
from app.domain.semaforo import UmbralesSemaforo
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import (
    DimensionPresupuesto,
    EjeCruce,
    EjeResumen,
    TipoDimension,
    normalizar_clave,
)
from app.infrastructure.models.periodo import Periodo
from app.schemas.agro import (
    ConciliacionAgro,
    FilaCruceAgro,
    FilaCuboAgro,
    FilaResumenAgro,
    FilaVentaComercialAgro,
    FilaVentaDiariaAgro,
    IndicadoresAgro,
    ParametrosCalculoAgro,
    RespuestaCruceAgro,
    RespuestaCuboAgro,
    RespuestaResumenAgro,
    RespuestaVentaDiariaAgro,
    RespuestaVentasComercialesAgro,
    TotalesVentaDiariaAgro,
)

CERO = Decimal("0")

#: Columna de `agro_venta_lineas` que corresponde a cada dimensión. Es el único
#: sitio donde se traduce un eje pedido por la API a una columna de la base: con
#: el mapa en un solo lugar, añadir un eje es una línea y no una cadena de
#: `if` repartida por tres métodos.
COLUMNA_DIMENSION: dict[TipoDimension, InstrumentedAttribute[int]] = {
    TipoDimension.CENTRO_OPERACION: AgroVentaLinea.centro_id,
    TipoDimension.TIPO_ITEM: AgroVentaLinea.tipo_item_id,
    TipoDimension.ESPECIE: AgroVentaLinea.especie_id,
    TipoDimension.TIPO_COMERCIAL: AgroVentaLinea.tipo_comercial_id,
    TipoDimension.GRUPO: AgroVentaLinea.grupo_id,
    TipoDimension.VENDEDOR: AgroVentaLinea.vendedor_id,
    TipoDimension.CLIENTE: AgroVentaLinea.cliente_id,
    TipoDimension.ITEM: AgroVentaLinea.item_id,
}

#: **La venta.** Ver el supuesto marcado en `agro_venta.py`: el negocio no
#: precisó cuál de los cuatro importes de la fuente es «la venta» y se eligió el
#: neto. Cambiarlo es cambiar **esta línea**, y los otros tres importes ya están
#: persistidos por si el negocio decide otra cosa.
COLUMNA_VENTA = AgroVentaLinea.total_neto

#: Las siete columnas con las que se arma un `TotalesAgro` desde un `GROUP BY`.
#:
#: Las dos del medio son el indicador de costo completo: `COUNT(*)` cuenta las
#: líneas del grupo y `COUNT(total_costo)` **no cuenta los nulos**, así que son
#: iguales si y solo si todas las líneas traen costo. Se resuelve en la base y
#: en la misma pasada —una consulta aparte para preguntarlo sería otro barrido—
#: y funciona igual en PostgreSQL, SQL Server y SQLite, que es más de lo que se
#: puede decir de `FILTER (WHERE ...)`.
COLUMNAS_TOTALES = (
    func.sum(COLUMNA_VENTA),
    func.sum(AgroVentaLinea.kilos_total),
    func.sum(AgroVentaLinea.cantidad_inv),
    func.sum(AgroVentaLinea.total_costo),
    func.count(),
    func.count(AgroVentaLinea.total_costo),
    func.sum(AgroVentaLinea.lineas_facturadas),
)


def _dec(valor: object) -> Decimal:
    """Un agregado de la base a `Decimal`. `NULL` es cero al sumar."""
    return Decimal(str(valor)) if valor is not None else Decimal("0")


def _ent(valor: object) -> int:
    """Un conteo de la base a `int`. `NULL` es cero."""
    return int(str(valor)) if valor is not None else 0


#: Que magnitud se pondera al agregar varios centros: dias habiles, dias
#: trabajados o el ideal de cada uno.
type _Magnitud = Callable[[DiasCentro], Decimal | None]


@dataclass
class TotalesAgro:
    """Sumas de un corte. Mutable a propósito: se acumula sobre él."""

    valor: Decimal = CERO
    kilos: Decimal = CERO
    cantidad: Decimal = CERO
    costo: Decimal = CERO
    #: ¿Traen costo **todas** las líneas que se sumaron aquí? Basta una sin
    #: costo para que el conjunto entero deje de tener margen calculable, por
    #: eso se propaga con `and` al agregar (§4.4).
    costo_completo: bool = True
    lineas: int = 0

    def sumar(self, otro: TotalesAgro) -> None:
        self.valor += otro.valor
        self.kilos += otro.kilos
        self.cantidad += otro.cantidad
        self.costo += otro.costo
        self.costo_completo = self.costo_completo and otro.costo_completo
        self.lineas += otro.lineas

    def medida(self, medida: Medida) -> Decimal:
        return self.valor if medida is Medida.VALOR else self.kilos


@dataclass
class TotalesCuboAgro:
    """Sumas de un corte del cubo: todas las medidas que trae la fuente.

    A diferencia de `TotalesAgro`, incluye `valor_bruto` y `valor_subtotal`,
    que el cubo publica como columnas independientes para que la pantalla pueda
    mostrar la cadena `bruto - descuentos = subtotal` del ERP.
    """

    valor_neto: Decimal = CERO
    kilos: Decimal = CERO
    cantidad: Decimal = CERO
    valor_bruto: Decimal = CERO
    valor_subtotal: Decimal = CERO
    costo: Decimal = CERO
    costo_completo: bool = True
    utilidad_bruta: Decimal | None = None
    utilidad_completa: bool = True
    lineas: int = 0

    def sumar(self, otro: TotalesCuboAgro) -> None:
        self.valor_neto += otro.valor_neto
        self.kilos += otro.kilos
        self.cantidad += otro.cantidad
        self.valor_bruto += otro.valor_bruto
        self.valor_subtotal += otro.valor_subtotal
        self.costo += otro.costo
        self.costo_completo = self.costo_completo and otro.costo_completo
        self.lineas += otro.lineas
        self.utilidad_completa = self.utilidad_completa and otro.utilidad_completa
        if otro.utilidad_bruta is not None:
            self.utilidad_bruta = (self.utilidad_bruta or CERO) + otro.utilidad_bruta


def _totales_de(fila: Sequence[object]) -> TotalesAgro:
    """Una fila de `COLUMNAS_TOTALES` a `TotalesAgro`."""
    valor, kilos, cantidad, costo, lineas, con_costo, facturadas = fila
    return TotalesAgro(
        valor=_dec(valor),
        kilos=_dec(kilos),
        cantidad=_dec(cantidad),
        costo=_dec(costo),
        costo_completo=_ent(lineas) == _ent(con_costo),
        lineas=_ent(facturadas),
    )


@dataclass(frozen=True, slots=True)
class FiltrosAgro:
    """Los filtros comunes a los tres reportes agropecuarios."""

    periodo: str
    hasta: date | None = None
    medida: Medida = Medida.VALOR
    #: Códigos de centro de operación pedidos (`301`, `302`). `None` = todos.
    #: **Estrecha, nunca ensancha**: es un filtro de pantalla, no de permisos.
    centros: tuple[str, ...] | None = None
    #: Primer día del rango de la venta diaria. `None` mantiene el modo por
    #: período: del día 1 a la fecha de corte.
    desde: date | None = None


@dataclass
class _Contexto:
    """Todo lo que hace falta para armar cualquier reporte del período."""

    periodo: Periodo
    fecha_corte: date
    medida: Medida
    umbrales: UmbralesSemaforo
    #: Catálogo entero de dimensiones, `{id: fila}`. Son ~900 miembros: caben en
    #: memoria y evitan tres `JOIN` a la misma tabla en el cruce de tres ejes.
    catalogo: dict[int, AgroDimension]
    dias: dict[int, DiasCentro]
    filtros: FiltrosAgro
    #: `id` de los centros pedidos, o `None` si no se filtró.
    centros_pedidos: list[int] | None = None
    _planes: dict[DimensionPresupuesto, PlanPresupuesto] = field(default_factory=dict)


class AgroReportesService:
    """Armado de los reportes gerenciales de la unidad agropecuaria."""

    def __init__(self, sesion: Session) -> None:
        self._sesion = sesion
        self._settings = obtener_settings()
        self._umbrales = UmbralesSemaforo(factor_amarillo=self._settings.factor_semaforo_amarillo)
        self._presupuesto = AgroPresupuestoService(sesion)

    # ── Resumen por cualquiera de los siete ejes ──────────────────────────────

    def resumen(self, filtros: FiltrosAgro, por: EjeResumen) -> RespuestaResumenAgro:
        """Venta, kilos y margen por centro, tipo de ítem, especie, tipo
        comercial, grupo, vendedor o cliente.

        Y, **donde ese eje tenga presupuesto**, cumplimiento, ideal, proyección
        y semáforo. Los tres ejes que no se presupuestan —cliente, grupo y tipo
        de ítem— publican los indicadores de meta vacíos; no es un hueco por
        cargar, es que ahí no hay meta.

        PENDIENTE DE CONFIRMAR CON EL NEGOCIO: con un filtro de centro activo, la
        meta del consolidado se recorta a los centros pedidos —ver
        `_claves_del_filtro`—, pero en los ejes que **no** son el centro sigue
        publicándose la meta entera del miembro. Es lo único que hay: la meta de
        un vendedor no está repartida por centro, así que su cumplimiento
        filtrado a Montería compara la venta de un centro contra la meta de los
        dos y sale por debajo. La alternativa sería vaciar el cumplimiento
        —«aquí no hay vara para lo que estás mirando»—, que es más honesto y
        cambia lo que hoy ve la pantalla; hay que decidirlo, no adivinarlo.
        """
        ctx = self._contexto(filtros)
        dimension = por.dimension_presupuesto
        plan = self._plan(ctx, dimension) if dimension is not None else None

        columna = COLUMNA_DIMENSION[por.tipo]
        agregados = self._agregar(ctx, [columna])
        ultimas = self._ultima_venta(ctx, columna)
        consolidado_totales = TotalesAgro()
        for totales in agregados.values():
            consolidado_totales.sumar(totales)

        habiles_cia, trabajados_cia, ideal_cia = self._dias_compania(ctx)
        base = consolidado_totales.medida(ctx.medida)

        filas: list[FilaResumenAgro] = []
        for llave, totales in agregados.items():
            miembro = ctx.catalogo.get(llave[0])
            clave = miembro.clave if miembro is not None else str(llave[0])
            if por is EjeResumen.CENTRO_OPERACION:
                habiles, trabajados, ideal_fila = self._dias_centro(ctx, llave[0])
            else:
                habiles, trabajados, ideal_fila = habiles_cia, trabajados_cia, ideal_cia
            filas.append(
                FilaResumenAgro(
                    clave=clave,
                    nombre=miembro.nombre if miembro is not None else clave,
                    ultima_venta=ultimas.get(llave[0]),
                    **self._indicadores(
                        ctx,
                        totales,
                        base,
                        presupuesto=self._meta(plan, clave, ctx.medida),
                        dias_habiles=habiles,
                        dias_trabajados=trabajados,
                        ideal_agregado=ideal_fila,
                    ).model_dump(),
                )
            )
        filas.sort(key=lambda f: (-Decimal(f.venta), f.nombre))

        consolidado = self._indicadores(
            ctx,
            consolidado_totales,
            base,
            presupuesto=self._meta_total(plan, ctx.medida, self._claves_del_filtro(ctx, dimension)),
            dias_habiles=habiles_cia,
            dias_trabajados=trabajados_cia,
            ideal_agregado=ideal_cia,
        )
        return RespuestaResumenAgro(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            medida=ctx.medida,
            por=por,
            consolidado=consolidado,
            filas=filas,
            parametros_calculo=self._parametros(ctx, consolidado, dimension),
        )

    def ventas_comerciales(self, filtros: FiltrosAgro) -> RespuestaVentasComercialesAgro:
        """Venta por categoría comercial y especie.

        No mezcla res con cerdo ni convierte las categorías en especies: cada
        fila conserva ambas dimensiones para que la pantalla pueda leer cortes,
        subproductos, sacrificio, desposte y canales por separado.
        """
        ctx = self._contexto(filtros)
        agregados = self._agregar(
            ctx,
            [
                COLUMNA_DIMENSION[TipoDimension.TIPO_COMERCIAL],
                COLUMNA_DIMENSION[TipoDimension.ESPECIE],
            ],
        )
        filas: list[FilaVentaComercialAgro] = []
        for (tipo_id, especie_id), totales in agregados.items():
            tipo = ctx.catalogo.get(tipo_id)
            especie = ctx.catalogo.get(especie_id)
            filas.append(
                FilaVentaComercialAgro(
                    tipo_comercial=tipo.nombre if tipo is not None else str(tipo_id),
                    especie=especie.nombre if especie is not None else str(especie_id),
                    venta_valor=redondear_no_nulo(totales.valor, 2),
                    kilos=redondear_no_nulo(totales.kilos, 3),
                )
            )
        filas.sort(key=lambda fila: (fila.tipo_comercial, fila.especie))
        return RespuestaVentasComercialesAgro(
            periodo=ctx.periodo.codigo, fecha_corte=ctx.fecha_corte, filas=filas
        )

    # ── Cubo dinámico ─────────────────────────────────────────────────────────

    def cubo(
        self, filtros: FiltrosAgro, dimensiones: list[TipoDimension]
    ) -> RespuestaCuboAgro:
        """Venta agregada por N dimensiones, con todas las medidas.

        Replica el «Filtro Cubo» del ERP SIESA: el negocio elige qué
        dimensiones poner en las filas y el cubo agrega la venta por esa
        combinación. A diferencia del resumen (una sola dimensión) y del cruce
        (dos o tres fijas), aquí cualquier combinación de las ocho dimensiones
        es válida.

        **No calcula indicadores**: cumplimiento, ideal, proyección y semáforo
        dependen de una dimensión de presupuesto, y el cubo puede mezclar
        dimensiones que no se presupuestan. Publica las medidas crudas —las que
        trae la fuente— y deja que la pantalla las lea.

        Las filas se ordenan por venta neta descendente. El total refleja el
        corte entero, sin truncar.
        """
        ctx = self._contexto(filtros)
        columnas = [COLUMNA_DIMENSION[dim] for dim in dimensiones]
        agregados = self._agregar_cubo(ctx, columnas)

        filas: list[FilaCuboAgro] = []
        total_cubo = TotalesCuboAgro()
        for llaves, totales in agregados.items():
            total_cubo.sumar(totales)
            miembros = [ctx.catalogo.get(identificador) for identificador in llaves]
            filas.append(
                FilaCuboAgro(
                    claves=[
                        miembro.clave if miembro is not None else str(identificador)
                        for miembro, identificador in zip(miembros, llaves, strict=True)
                    ],
                    nombres=[
                        miembro.nombre if miembro is not None else str(identificador)
                        for miembro, identificador in zip(miembros, llaves, strict=True)
                    ],
                    cantidad_inv=redondear_no_nulo(totales.cantidad, 3),
                    kilos_total=redondear_no_nulo(totales.kilos, 3),
                    valor_bruto=redondear_no_nulo(totales.valor_bruto, 2),
                    valor_subtotal=redondear_no_nulo(totales.valor_subtotal, 2),
                    total_neto=redondear_no_nulo(totales.valor_neto, 2),
                    total_costo=(
                        redondear_no_nulo(totales.costo, 2)
                        if totales.costo_completo
                        else None
                    ),
                    utilidad_bruta=(
                        redondear_no_nulo(totales.utilidad_bruta, 2)
                        if totales.utilidad_completa and totales.utilidad_bruta is not None
                        else None
                    ),
                    lineas_facturadas=totales.lineas,
                )
            )

        filas.sort(key=lambda f: -Decimal(f.total_neto))

        limite = self._settings.max_filas_reporte_agro
        truncado = len(filas) > limite
        return RespuestaCuboAgro(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            dimensiones=[d.value for d in dimensiones],
            filas=filas[:limite],
            total=FilaCuboAgro(
                claves=[],
                nombres=[],
                cantidad_inv=redondear_no_nulo(total_cubo.cantidad, 3),
                kilos_total=redondear_no_nulo(total_cubo.kilos, 3),
                valor_bruto=redondear_no_nulo(total_cubo.valor_bruto, 2),
                valor_subtotal=redondear_no_nulo(total_cubo.valor_subtotal, 2),
                total_neto=redondear_no_nulo(total_cubo.valor_neto, 2),
                total_costo=(
                    redondear_no_nulo(total_cubo.costo, 2)
                    if total_cubo.costo_completo
                    else None
                ),
                utilidad_bruta=(
                    redondear_no_nulo(total_cubo.utilidad_bruta, 2)
                    if total_cubo.utilidad_completa and total_cubo.utilidad_bruta is not None
                    else None
                ),
                lineas_facturadas=total_cubo.lineas,
            ),
            truncado=truncado,
            limite=limite,
        )

    # ── Los dos cruces ────────────────────────────────────────────────────────

    def cruce(self, filtros: FiltrosAgro, por: EjeCruce) -> RespuestaCruceAgro:
        """Vendedor × cliente y vendedor × cliente × producto.

        **Cuadran con el total y eso no es casualidad: es estructural.** Las
        ocho dimensiones son obligatorias en la línea, así que no hay ninguna
        fila que un cruce pueda perder por venir sin vendedor o sin cliente: lo
        que llega vacío entra con su miembro visible (`SIN VENDEDOR`,
        `SIN CLIENTE`, `SIN PRODUCTO`) y sigue sumando. Un cruce que descartara
        los nulos publicaría menos venta que el resumen, y la diferencia sería
        invisible.

        El **consolidado se calcula sobre el corte entero**, no sobre las filas
        publicadas. Con el tope de filas activo, la participación seguiría
        siendo cierta: si se usara la suma del top-N como denominador, las
        participaciones sumarían 100 % por construcción y un cliente que es el
        45 % de la compañía se publicaría como 60 %.
        """
        ctx = self._contexto(filtros)
        columnas = [COLUMNA_DIMENSION[tipo] for tipo in por.tipos]
        limite = self._settings.max_filas_reporte_agro

        agregados = self._agregar(ctx, columnas)
        consolidado_totales = TotalesAgro()
        for totales in agregados.values():
            consolidado_totales.sumar(totales)

        habiles, trabajados, ideal_cia = self._dias_compania(ctx)
        base = consolidado_totales.medida(ctx.medida)

        ordenadas = sorted(agregados.items(), key=lambda par: -par[1].medida(ctx.medida))
        truncado = len(ordenadas) > limite

        filas: list[FilaCruceAgro] = []
        for llaves, totales in ordenadas[:limite]:
            miembros = [ctx.catalogo.get(identificador) for identificador in llaves]
            filas.append(
                FilaCruceAgro(
                    claves=[
                        m.clave if m is not None else str(i)
                        for m, i in zip(miembros, llaves, strict=True)
                    ],
                    nombres=[
                        m.nombre if m is not None else str(i)
                        for m, i in zip(miembros, llaves, strict=True)
                    ],
                    **self._indicadores(
                        ctx,
                        totales,
                        base,
                        presupuesto=None,
                        dias_habiles=habiles,
                        dias_trabajados=trabajados,
                        ideal_agregado=ideal_cia,
                    ).model_dump(),
                )
            )

        consolidado = self._indicadores(
            ctx,
            consolidado_totales,
            base,
            presupuesto=None,
            dias_habiles=habiles,
            dias_trabajados=trabajados,
            ideal_agregado=ideal_cia,
        )
        return RespuestaCruceAgro(
            periodo=ctx.periodo.codigo,
            fecha_corte=ctx.fecha_corte,
            medida=ctx.medida,
            por=por,
            ejes=[tipo.value for tipo in por.tipos],
            consolidado=consolidado,
            filas=filas,
            truncado=truncado,
            limite=limite,
            parametros_calculo=self._parametros(ctx, consolidado, None),
        )

    # ── Venta diaria ──────────────────────────────────────────────────────────

    def venta_diaria(self, filtros: FiltrosAgro) -> RespuestaVentaDiariaAgro:
        """La serie día por día, un centro de operación por fila.

        El rango se valida **antes de tocar la base**, con las mismas dos
        guardas y los **mismos códigos de error** que el reporte de carnes
        —`rango_invertido` y `rango_excesivo`—, y se reutilizan a propósito: es
        el mismo control de la misma barra de filtros y el frontend ya sabe
        tratarlos. Un rango invertido se rechaza en lugar de devolver la tabla
        vacía que saldría de forma natural, porque eso haría pasar un error de
        captura por «no hubo ventas».

        La línea de referencia es `presupuesto_mensual / H` **por centro**, que
        sale de la dimensión `centro_operacion`: es la única de las cuatro que
        reparte la meta por la unidad que tiene calendario. El total es
        `Σ (P_i / H_i)`, la suma de las referencias de las filas, y no el
        presupuesto agregado partido por unos días ponderados: con cualquier
        otra fórmula la fila de totales no cuadraría con las que tiene encima.
        """
        ctx = self._contexto(filtros)
        desde, hasta = self._rango(ctx, filtros)
        fechas = _rango_fechas(desde, hasta)

        consulta = (
            select(AgroVentaLinea.centro_id, AgroVentaLinea.fecha, func.sum(_columna(ctx.medida)))
            .where(*self._filtros_base(ctx, desde=desde, hasta=hasta, por_periodo=False))
            .group_by(AgroVentaLinea.centro_id, AgroVentaLinea.fecha)
        )
        por_dia: dict[int, dict[date, Decimal]] = defaultdict(dict)
        for centro_id, dia, total in self._sesion.execute(consulta):
            por_dia[centro_id][dia] = Decimal(total or 0)

        plan = self._plan(ctx, DimensionPresupuesto.CENTRO_OPERACION)
        decimales = ctx.medida.decimales

        filas: list[FilaVentaDiariaAgro] = []
        suma_dia: list[Decimal | None] = [None] * len(fechas)
        suma_total = CERO
        referencia_total = CERO
        alguno_presupuestado = False
        referencia_completa = True
        referencias: dict[str, Decimal | None] = {}

        for centro in self._centros_visibles(ctx):
            valores = [por_dia.get(centro.id, {}).get(dia) for dia in fechas]
            total = sum((v for v in valores if v is not None), start=CERO)
            filas.append(
                FilaVentaDiariaAgro(
                    centro=centro.clave,
                    nombre=centro.nombre,
                    valores=[redondear(v, decimales) for v in valores],
                    total=redondear_no_nulo(total, decimales),
                )
            )
            # La fila de totales se acumula sobre los mismos valores que se
            # acaban de publicar: así cuadra con la suma de sus filas por
            # construcción y no por coincidencia. Un día sin venta en **ningún**
            # centro sigue siendo `None` —«no hay dato»— y no cero.
            for indice, valor in enumerate(valores):
                if valor is not None:
                    suma_dia[indice] = (suma_dia[indice] or CERO) + valor
            suma_total += total

            meta = self._meta(plan, centro.clave, ctx.medida)
            datos = ctx.dias.get(centro.id)
            diario = presupuesto_diario(meta, datos.dias_habiles if datos else None)
            referencias[centro.clave] = redondear(diario, decimales)
            if meta is None:
                continue
            alguno_presupuestado = True
            if diario is None:
                # El centro tiene meta y su calendario no está parametrizado: el
                # término es incalculable y sumar solo el resto publicaría una
                # referencia más baja que la real con pinta de completa (§7).
                referencia_completa = False
            else:
                referencia_total += diario

        return RespuestaVentaDiariaAgro(
            periodo=ctx.periodo.codigo,
            fecha_corte=hasta,
            desde=desde,
            hasta=hasta,
            medida=ctx.medida,
            fechas=fechas,
            presupuesto_diario_por_centro=referencias,
            filas=filas,
            totales=TotalesVentaDiariaAgro(
                valores=[redondear(v, decimales) for v in suma_dia],
                total=redondear_no_nulo(suma_total, decimales),
                presupuesto_diario=(
                    redondear(referencia_total, decimales)
                    if alguno_presupuestado and referencia_completa
                    else None
                ),
            ),
            parametros_calculo=self._parametros(ctx, None, DimensionPresupuesto.CENTRO_OPERACION),
        )

    # ── Construcción del contexto ─────────────────────────────────────────────

    def _contexto(self, filtros: FiltrosAgro) -> _Contexto:
        periodo = obtener_periodo(self._sesion, filtros.periodo)
        corte = fecha_corte_efectiva(periodo, filtros.hasta)
        catalogo = {fila.id: fila for fila in self._sesion.execute(select(AgroDimension)).scalars()}

        centros_pedidos: list[int] | None = None
        if filtros.centros:
            claves = {
                normalizar_clave(TipoDimension.CENTRO_OPERACION, codigo)
                for codigo in filtros.centros
            }
            centros_pedidos = [
                fila.id
                for fila in catalogo.values()
                if fila.tipo == TipoDimension.CENTRO_OPERACION.value and fila.clave in claves
            ]

        return _Contexto(
            periodo=periodo,
            fecha_corte=corte,
            medida=filtros.medida,
            umbrales=self._umbrales,
            catalogo=catalogo,
            dias=AgroCalendarioService(self._sesion).dias_por_centro(periodo, corte),
            filtros=filtros,
            centros_pedidos=centros_pedidos,
        )

    def _plan(self, ctx: _Contexto, dimension: DimensionPresupuesto) -> PlanPresupuesto:
        """El plan de una dimensión, resuelto una vez por petición.

        Se cachea por dimensión y **nunca se mezclan dos**: el caché es un mapa
        de dimensión a plan, no una bolsa de importes.
        """
        plan = ctx._planes.get(dimension)
        if plan is None:
            plan = self._presupuesto.plan(ctx.periodo, dimension)
            ctx._planes[dimension] = plan
        return plan

    # ── Agregación ────────────────────────────────────────────────────────────

    def _filtros_base(
        self,
        ctx: _Contexto,
        *,
        desde: date | None = None,
        hasta: date | None = None,
        por_periodo: bool = True,
    ) -> list[ColumnElement[bool]]:
        """**El único sitio donde se construye el `WHERE` de la venta.**

        Que sea uno solo es lo que garantiza que ninguna consulta se olvide de
        excluir el impuesto: si el filtro estuviera repetido en cada método, la
        primera copia que se quedara sin él publicaría el recaudo de terceros
        como venta y el total subiría sin que nada fallara.
        """
        criterios: list[ColumnElement[bool]] = [AgroVentaLinea.es_impuesto.is_(False)]
        if por_periodo and ctx.filtros.desde is None:
            criterios.append(AgroVentaLinea.periodo_id == ctx.periodo.id)
            criterios.append(AgroVentaLinea.fecha <= ctx.fecha_corte)
        elif por_periodo:
            desde, hasta = self._rango(ctx, ctx.filtros)
            criterios.append(AgroVentaLinea.fecha >= desde)
            criterios.append(AgroVentaLinea.fecha <= hasta)
        else:
            if desde is not None:
                criterios.append(AgroVentaLinea.fecha >= desde)
            if hasta is not None:
                criterios.append(AgroVentaLinea.fecha <= hasta)
        if ctx.centros_pedidos is not None:
            criterios.append(AgroVentaLinea.centro_id.in_(ctx.centros_pedidos or [-1]))
        return criterios

    def _agregar(
        self, ctx: _Contexto, columnas: Sequence[InstrumentedAttribute[int]]
    ) -> dict[tuple[int, ...], TotalesAgro]:
        """`GROUP BY` sobre las columnas pedidas, con las sumas de `COLUMNAS_TOTALES`."""
        consulta: Select[tuple[object, ...]] = (
            select(*columnas, *COLUMNAS_TOTALES).where(*self._filtros_base(ctx)).group_by(*columnas)
        )
        anchura = len(columnas)
        return {
            tuple(int(v) for v in fila[:anchura]): _totales_de(fila[anchura:])
            for fila in self._sesion.execute(consulta)
        }

    def _agregar_cubo(
        self, ctx: _Contexto, columnas: Sequence[InstrumentedAttribute[int]]
    ) -> dict[tuple[int, ...], TotalesCuboAgro]:
        """Agrupa las medidas del cubo en una sola consulta.

        Los dos conteos de costo y utilidad preservan su semántica de origen:
        si SIESA omitió una de esas medidas en cualquier línea de una
        combinación, la columna completa se publica vacía. Sumar los valores
        presentes la convertiría en una cifra aparentemente precisa pero
        incompleta.
        """
        consulta = (
            select(
                *columnas,
                func.sum(AgroVentaLinea.cantidad_inv),
                func.sum(AgroVentaLinea.kilos_total),
                func.sum(AgroVentaLinea.valor_bruto),
                func.sum(AgroVentaLinea.valor_subtotal),
                func.sum(AgroVentaLinea.total_neto),
                func.sum(AgroVentaLinea.total_costo),
                func.count(),
                func.count(AgroVentaLinea.total_costo),
                func.sum(AgroVentaLinea.utilidad_bruta),
                func.count(AgroVentaLinea.utilidad_bruta),
                func.sum(AgroVentaLinea.lineas_facturadas),
            )
            .where(*self._filtros_base(ctx))
            .group_by(*columnas)
        )
        anchura = len(columnas)
        agregados: dict[tuple[int, ...], TotalesCuboAgro] = {}
        for fila in self._sesion.execute(consulta):
            (
                cantidad,
                kilos,
                bruto,
                subtotal,
                neto,
                costo,
                lineas,
                con_costo,
                utilidad,
                con_utilidad,
                facturadas,
            ) = fila[anchura:]
            agregados[tuple(int(valor) for valor in fila[:anchura])] = TotalesCuboAgro(
                cantidad=_dec(cantidad),
                kilos=_dec(kilos),
                valor_bruto=_dec(bruto),
                valor_subtotal=_dec(subtotal),
                valor_neto=_dec(neto),
                costo=_dec(costo),
                costo_completo=_ent(lineas) == _ent(con_costo),
                utilidad_bruta=_dec(utilidad) if utilidad is not None else None,
                utilidad_completa=_ent(lineas) == _ent(con_utilidad),
                lineas=_ent(facturadas),
            )
        return agregados

    def _ultima_venta(self, ctx: _Contexto, columna: InstrumentedAttribute[int]) -> dict[int, date]:
        """El último día con venta de cada miembro, **dentro del corte**.

        Consulta aparte y no una columna más de `_agregar` porque aquella la
        comparten el resumen y los dos cruces, y un `MAX(fecha)` por cada
        combinación de tres ejes es trabajo que nadie mira. Aquí es una
        agregación sobre la misma tabla ya filtrada: barata y de un solo grano.
        """
        consulta = (
            select(columna, func.max(AgroVentaLinea.fecha))
            .where(*self._filtros_base(ctx))
            .group_by(columna)
        )
        return {int(clave): fecha for clave, fecha in self._sesion.execute(consulta) if fecha}

    # ── Armado de filas ───────────────────────────────────────────────────────

    def _indicadores(
        self,
        ctx: _Contexto,
        totales: TotalesAgro,
        base_participacion: Decimal,
        *,
        presupuesto: Decimal | None,
        dias_habiles: Decimal | None,
        dias_trabajados: Decimal | None,
        ideal_agregado: Decimal | None,
    ) -> IndicadoresAgro:
        """Los indicadores de una fila, calculados **por el dominio**.

        `venta_valor` viaja siempre en pesos aunque el reporte se esté mirando
        en kilos: el margen es un concepto monetario y calcularlo sobre kilos
        daría un número sin significado.

        La `participacion` se divide entre la venta **total del corte**, que
        llega en `base_participacion`, y no entre la suma de las filas
        publicadas: con el top-N como denominador las participaciones sumarían
        100 % por construcción.
        """
        resultado = calcular_indicadores(
            InsumosIndicadores(
                venta=totales.medida(ctx.medida),
                venta_valor=totales.valor,
                costo=totales.costo,
                costo_completo=totales.costo_completo,
                presupuesto=presupuesto,
                dias_habiles=dias_habiles,
                dias_trabajados=dias_trabajados,
                ideal_agregado=ideal_agregado,
            ),
            ctx.umbrales,
            decimales_medida=ctx.medida.decimales,
        )
        return IndicadoresAgro(
            venta=resultado.venta,
            venta_valor=redondear_no_nulo(totales.valor, 2),
            kilos=redondear_no_nulo(totales.kilos, 3),
            cantidad=redondear_no_nulo(totales.cantidad, 3),
            lineas_facturadas=totales.lineas,
            participacion=redondear_porcentaje(
                dividir(totales.medida(ctx.medida), base_participacion)
            ),
            margen_valor=resultado.margen_valor,
            margen_porcentaje=resultado.margen_porcentaje,
            presupuesto=resultado.presupuesto,
            cumplimiento=resultado.cumplimiento,
            ideal=resultado.ideal,
            brecha=resultado.brecha,
            semaforo=resultado.semaforo,
            proyeccion=resultado.proyeccion,
            cumplimiento_proyectado=resultado.cumplimiento_proyectado,
            venta_diaria_promedio=resultado.venta_diaria_promedio,
            venta_diaria_requerida=resultado.venta_diaria_requerida,
            dias_habiles=resultado.dias_habiles,
            dias_trabajados=resultado.dias_trabajados,
        )

    @staticmethod
    def _meta(plan: PlanPresupuesto | None, clave: str, medida: Medida) -> Decimal | None:
        """La meta de un miembro en la medida del reporte, o `None`.

        `None` cuando ese miembro no está presupuestado: el cumplimiento sale
        vacío y el semáforo `SIN_PRESUPUESTO`, nunca en rojo. Vender sin meta no
        es incumplir; es no tener contra qué medir.
        """
        if plan is None:
            return None
        return plan.monto_de(clave) if medida is Medida.VALOR else plan.kilos_de(clave)

    @staticmethod
    def _meta_total(
        plan: PlanPresupuesto | None, medida: Medida, claves: set[str] | None = None
    ) -> Decimal | None:
        """El total de **una** dimensión, restringido a lo que el filtro deja ver.

        Las cuatro dimensiones reparten el mismo total, así que el total de
        cualquiera de ellas es el presupuesto de la compañía. Por eso aquí no
        hay ninguna suma entre dimensiones ni puede haberla: se usa el plan que
        corresponde al eje que se está mirando y punto.

        **`claves` es el denominador del cumplimiento y por eso existe.** Con un
        filtro de centro activo, la venta del consolidado es la de los centros
        pedidos y su meta tiene que ser la de esos mismos centros. Sumando el
        plan entero se comparaba la venta de Montería contra la meta de Montería
        **más la de Planta**, y el cumplimiento salía muy por debajo del real —en
        la fila del centro salía bien y en el consolidado mal, contradiciéndose
        en la misma pantalla—. Es la regla que carnes ya fija en
        `test_el_presupuesto_del_consolidado_tambien_se_limita_a_los_puntos_pedidos`.

        Si ninguno de los miembros pedidos tiene meta el resultado es `None`, no
        cero: no hay vara contra la que medir lo que se está enseñando.
        """
        if plan is None or not plan.definido:
            return None
        if claves is None:
            return plan.total_monto if medida is Medida.VALOR else plan.total_kilos

        metas = [meta for clave, meta in plan.metas.items() if clave in claves]
        if not metas:
            return None
        # Sin lambda: en contexto tipado una funcion anonima sin anotar es una
        # llamada a ciegas, y aqui lo que se suma es dinero.
        if medida is Medida.VALOR:
            return sum((meta.monto for meta in metas), start=CERO)
        return sum((meta.kilos for meta in metas), start=CERO)

    def _claves_del_filtro(
        self, ctx: _Contexto, dimension: DimensionPresupuesto | None
    ) -> set[str] | None:
        """A qué miembros del plan limita el filtro de centro. `None` = a ninguno.

        Solo la dimensión `centro_operacion` se puede recortar, porque es la
        única cuyos miembros **son** los centros que el filtro nombra. La meta de
        un vendedor no está repartida por centro, así que un filtro de centro no
        se puede proyectar sobre ella; ver la nota al respecto en `resumen`.
        """
        if ctx.centros_pedidos is None or dimension is not DimensionPresupuesto.CENTRO_OPERACION:
            return None
        return {centro.clave for centro in self._centros_visibles(ctx)}

    # ── Días hábiles y trabajados ─────────────────────────────────────────────

    def _dias_centro(
        self, ctx: _Contexto, centro_id: int
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """`H`, `T` e `ideal` de un centro. El ideal es `T / H`, sin ponderar."""
        datos = ctx.dias.get(centro_id)
        if datos is None:
            return None, None, None
        return datos.dias_habiles, datos.dias_trabajados, None

    def _dias_compania(
        self, ctx: _Contexto
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """`H`, `T` e `ideal` de la compañía, para los ejes que no son el centro.

        Un vendedor factura en los dos centros, así que su `H` no es el de
        ninguno de ellos: es el de la compañía. Y el de la compañía se pondera
        **por el presupuesto de la dimensión `centro_operacion`**, que es la
        única de las cuatro que reparte la meta por la unidad que tiene
        calendario. Tres decisiones, cada una con su motivo:

        1. **Ponderar y no promediar a secas.** Si Planta presupuesta veinte
           veces más que Montería, la vara de la compañía se parece muchísimo
           más a la de Planta; el promedio simple le pondría una que no le
           corresponde. Sin presupuesto contra el que ponderar queda el promedio
           simple de los centros con calendario, que es lo único que hay.

        2. **Siempre con el presupuesto en pesos**, nunca con el de la medida en
           curso. El calendario no sabe si el usuario está mirando pesos o
           kilos, y ponderar con el de la medida hacía que el `ideal` —que es
           puro calendario— cambiara de valor al pulsar el interruptor
           pesos/kilos, y con él el semáforo.

        3. **`ideal` se pondera aparte, no se deriva de `T / H`.** La venta
           esperada al corte es `Σ(P_i × ideal_i)` y el presupuesto es `Σ P_i`,
           luego `ideal = Σ(P_i × ideal_i) / Σ P_i`. Ese número **no** coincide
           con el cociente de los promedios (desigualdad de Jensen: la media de
           cocientes no es el cociente de las medias). `H` y `T` conservan su
           significado propio —los días medios, que son los que proyectan y los
           que dejan `H − T` como días restantes— y el ideal va aparte.

        Con un solo centro los tres valores son exactamente los suyos, sin
        distorsión alguna.
        """
        plan = self._plan(ctx, DimensionPresupuesto.CENTRO_OPERACION)
        pesos: dict[int, Decimal] = {}
        for centro in self._centros_visibles(ctx):
            monto = plan.monto_de(centro.clave)
            pesos[centro.id] = monto if monto is not None else CERO

        habiles = self._ponderar(ctx, pesos, lambda d: d.dias_habiles)
        trabajados = self._ponderar(ctx, pesos, lambda d: d.dias_trabajados)
        ideal_ponderado = self._ponderar(
            ctx, pesos, lambda d: dividir(d.dias_trabajados, d.dias_habiles)
        )
        return habiles, trabajados, ideal_ponderado

    def _ponderar(
        self,
        ctx: _Contexto,
        pesos: dict[int, Decimal],
        magnitud: _Magnitud,
    ) -> Decimal | None:
        """Media de `magnitud` sobre los centros, ponderada por `pesos`.

        Devuelve **precisión completa**. Redondear aquí sería el defecto: `H` y
        `T` cuantizados alimentarían la proyección y la venta diaria requerida,
        y el error se multiplicaría por miles de millones. El redondeo es de
        publicación y vive en `calcular_indicadores`.
        """
        acumulado = CERO
        peso_total = CERO
        sueltos: list[Decimal] = []

        for centro_id, datos in ctx.dias.items():
            if centro_id not in pesos:
                continue
            valor = magnitud(datos)
            if valor is None:
                continue
            sueltos.append(valor)
            peso = pesos.get(centro_id, CERO)
            acumulado += valor * peso
            peso_total += peso

        if peso_total > CERO:
            return acumulado / peso_total
        if not sueltos:
            return None
        return sum(sueltos, start=CERO) / Decimal(len(sueltos))

    # ── Auxiliares ────────────────────────────────────────────────────────────

    def _centros_visibles(self, ctx: _Contexto) -> list[AgroDimension]:
        """Centros del catálogo que el filtro permite, ordenados por su código."""
        centros = [
            fila
            for fila in ctx.catalogo.values()
            if fila.tipo == TipoDimension.CENTRO_OPERACION.value
        ]
        if ctx.centros_pedidos is not None:
            permitidos = set(ctx.centros_pedidos)
            centros = [fila for fila in centros if fila.id in permitidos]
        return sorted(centros, key=lambda c: c.clave)

    def _rango(self, ctx: _Contexto, filtros: FiltrosAgro) -> tuple[date, date]:
        """El rango de la venta diaria, ya validado.

        Sin `desde` manda el período: del día 1 a la fecha de corte, que es el
        modo de siempre. Con `desde`, `hasta` pasa a ser el último día del rango
        y se toma tal cual, sin recortarlo contra el mes, porque recortarlo
        cortaría en seco el rango que cruza de mes.
        """
        if filtros.desde is None:
            return ctx.periodo.primer_dia, ctx.fecha_corte

        desde = filtros.desde
        hasta = filtros.hasta or date.today()
        if hasta < desde:
            raise ErrorRangoInvertido(
                f"El rango está invertido: «desde» ({desde}) es posterior a «hasta» ({hasta}).",
                detalles={"desde": str(desde), "hasta": str(hasta)},
            )
        dias = (hasta - desde).days + 1
        if dias > MAX_DIAS_RANGO:
            raise ErrorRangoExcesivo(
                f"El rango pedido son {dias} días y el máximo del reporte de venta diaria "
                f"es {MAX_DIAS_RANGO}. Para horizontes mayores use el resumen, que agrega "
                "por período.",
                detalles={"dias_solicitados": dias, "maximo_dias": MAX_DIAS_RANGO},
            )
        return desde, hasta

    def _parametros(
        self,
        ctx: _Contexto,
        fila: IndicadoresAgro | None,
        dimension: DimensionPresupuesto | None,
    ) -> ParametrosCalculoAgro:
        """`parametros_calculo`, con el cuadre y la conciliación dentro.

        El **cuadre** viaja en todos los reportes y no solo en la pantalla de
        presupuesto: un descuadre entre descomposiciones invalida la lectura de
        cualquiera de ellas, y quien mire un cumplimiento tiene derecho a
        enterarse sin ir a buscarlo a otra pantalla.

        La **conciliación** publica lo que se dejó fuera —el impuesto— para que
        la diferencia contra el ERP tenga explicación en lugar de convertirse en
        una búsqueda a ciegas.
        """
        valor, kilos, lineas = totales_impuesto(self._sesion, ctx.periodo.id, ctx.fecha_corte)
        return ParametrosCalculoAgro(
            fecha_corte=ctx.fecha_corte,
            dias_habiles=fila.dias_habiles if fila else None,
            dias_trabajados=fila.dias_trabajados if fila else None,
            umbrales=ctx.umbrales.a_diccionario(),
            dimension_presupuesto=dimension.value if dimension is not None else None,
            cuadre=self._presupuesto.cuadre_salida(ctx.periodo.codigo),
            conciliacion=ConciliacionAgro(
                impuesto_valor=redondear_no_nulo(valor, 2),
                impuesto_kilos=redondear_no_nulo(kilos, 3),
                impuesto_lineas=lineas,
            ),
        )


#: Magnitud derivada del calendario de un centro. Se pondera con la misma
#: máquina —`_ponderar`— sea cual sea, de modo que `H`, `T` e `ideal` de la
#: compañía usan exactamente los mismos pesos.


def _columna(medida: Medida) -> InstrumentedAttribute[Decimal]:
    """La columna que mide el reporte: el neto en pesos o los kilos."""
    return COLUMNA_VENTA if medida is Medida.VALOR else AgroVentaLinea.kilos_total


def _rango_fechas(desde: date, hasta: date) -> list[date]:
    if hasta < desde:
        return []
    return [desde + timedelta(days=n) for n in range((hasta - desde).days + 1)]
