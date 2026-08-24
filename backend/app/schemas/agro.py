"""Esquemas de la unidad Agropecuaria — el contrato de `/api/v1/agro`.

Las convenciones son las mismas que las del resto de SIGREP y no se repiten
aquí: los importes y las cantidades viajan como `string`, los porcentajes como
fracción decimal (`"0.2885"` = 28.85 %) y todo indicador indefinido viaja como
`null` para pintarse «—», nunca como `0`. Ver `app/schemas/common.py`.

Lo que sí es propio de este módulo, y es lo que hay que entender antes de
tocarlo, son dos formas deliberadas:

**1. El presupuesto se publica agrupado por dimensión, nunca en una lista
plana.** `RespuestaPresupuestoAgro` es una lista de `PresupuestoDimensionSalida`,
cada una con **su** total, y no existe ningún campo con «el total del
presupuesto». No es un olvido: las cuatro dimensiones —vendedor, centro de
operación, especie y tipo comercial— son cuatro repartos del mismo dinero, y un
total global solo podría salir de sumarlos, que da el doble de la meta real. Una
pantalla que necesite el presupuesto de la compañía elige una dimensión; las
cuatro dan la misma cifra cuando la captura está bien, y cuando no, eso es
justamente lo que publica `CuadrePresupuestoSalida`.

**2. `IndicadoresAgro` es un solo bloque, reutilizado en todos los ejes.** Igual
que `FilaIndicadores` en carnes: un esquema, un tipo en el frontend y un
componente de fila. Los campos que dependen del presupuesto viajan vacíos en los
ejes que no lo tienen —cliente, grupo y tipo de ítem no se presupuestan— y eso
es información, no un hueco: dicen que ahí no hay meta contra la que medir.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import Medida, Semaforo
from app.infrastructure.models.agro_vocabulario import (
    DimensionPresupuesto,
    EjeCruce,
    EjeResumen,
)
from app.schemas.common import DecimalStr, EsquemaBase

# ── Catálogo de dimensiones ───────────────────────────────────────────────────


class MiembroDimensionSalida(EsquemaBase):
    """Un miembro del catálogo: `clave` para cruzar, `nombre` para pintar."""

    tipo: str
    clave: str
    nombre: str
    activo: bool = True


class FilaVentaComercialAgro(EsquemaBase):
    """Venta por tipo comercial y especie, sin sumar dimensiones distintas."""

    tipo_comercial: str
    especie: str
    venta_valor: DecimalStr
    kilos: DecimalStr


class RespuestaVentasComercialesAgro(EsquemaBase):
    periodo: str
    fecha_corte: date
    filas: list[FilaVentaComercialAgro]


# ── Presupuesto ───────────────────────────────────────────────────────────────


class PresupuestoAgroSalida(EsquemaBase):
    """La meta de un miembro dentro de una dimensión."""

    dimension: str
    clave: str
    nombre: str
    monto: DecimalStr
    kilos: DecimalStr


class PresupuestoDimensionSalida(EsquemaBase):
    """El presupuesto del período **visto por una dimensión**, con su total.

    `total_monto` es el presupuesto **de la compañía** repartido por esta
    dimensión, no el de un trozo. Por eso no hay ningún total por encima de
    este: sumar los de dos dimensiones contaría el mismo dinero dos veces.
    """

    dimension: str
    etiqueta: str
    #: `False` cuando nadie ha capturado nada en esta dimensión. No es lo mismo
    #: que un presupuesto de cero: aquel es una afirmación del negocio y este es
    #: la ausencia de la parametrización.
    definido: bool
    total_monto: DecimalStr
    total_kilos: DecimalStr
    filas: list[PresupuestoAgroSalida] = Field(default_factory=list)


class PresupuestoAgroEntrada(BaseModel):
    """Alta o modificación de una meta.

    `dimension` es obligatoria y tipada: sin ella no se sabe en cuál de los
    cuatro repartos va la cifra, y ponerla en el que no es descuadra los dos.

    `motivo` es obligatorio y no admite una palabra suelta: todo cambio de
    presupuesto queda con autor, fecha y motivo (§7), y «ajuste» no sirve para
    evaluar a nadie seis meses después.
    """

    periodo: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", examples=["2026-08"])
    dimension: DimensionPresupuesto
    clave: str = Field(min_length=1, max_length=60, examples=["301", "V-07"])
    etiqueta: str | None = Field(default=None, max_length=200)
    monto: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    kilos: Decimal = Field(ge=0, max_digits=18, decimal_places=3)
    motivo: str = Field(min_length=5, max_length=400)


class CuadreDimension(EsquemaBase):
    """El total de una dimensión, para contrastarlo con las demás."""

    dimension: str
    etiqueta: str
    total_monto: DecimalStr
    total_kilos: DecimalStr


class CuadrePresupuestoSalida(EsquemaBase):
    """¿Las cuatro descomposiciones dan el mismo total?

    Es la comprobación que hace visible un error de captura que de otro modo no
    se vería: si el presupuesto por vendedor suma distinto que el presupuesto
    por especie, uno de los dos repartos está mal, porque los dos describen el
    mismo dinero.

    **El sistema no lo corrige.** Repartir la diferencia sería inventarse la
    meta de alguien. La publica —aquí y dentro de `parametros_calculo` de cada
    reporte— y quien la capturó la arregla.
    """

    periodo: str
    cuadra: bool
    #: Diferencia entre el total más alto y el más bajo de las dimensiones
    #: capturadas. Cero cuando cuadra.
    diferencia_monto: DecimalStr
    diferencia_kilos: DecimalStr
    mensaje: str
    dimensiones: list[CuadreDimension] = Field(default_factory=list)


class HistorialAgroSalida(EsquemaBase):
    cuando: datetime
    quien: str | None = None
    dimension: str
    clave: str
    campo: str
    valor_anterior: DecimalStr | None = None
    valor_nuevo: DecimalStr | None = None
    motivo: str


class ErrorFilaAgro(BaseModel):
    fila: int
    motivo: str


class ResultadoCargaAgro(BaseModel):
    """Resultado de la carga masiva, con el cuadre recién calculado.

    El cuadre viaja aquí a propósito: el momento de ver que las cuatro
    descomposiciones no dan lo mismo es justo después de subirlas, cuando quien
    lo hizo todavía tiene el archivo abierto.
    """

    aceptadas: int
    rechazadas: int
    errores: list[ErrorFilaAgro] = Field(default_factory=list)
    cuadre: CuadrePresupuestoSalida


# ── Calendario ────────────────────────────────────────────────────────────────


class CalendarioAgroSalida(EsquemaBase):
    """Días hábiles y trabajados de un centro de operación en un período.

    La unidad de calendario de agropecuaria es el **centro de operación** —301
    Planta y 302 Montería—, no una zona: son dos y pueden abrir días distintos.
    Los días admiten media jornada, así que son decimales (`"27.5"`).
    """

    centro: str = Field(description="Código de centro de operación (`CO_Id`)")
    nombre: str
    dias_habiles: DecimalStr
    dias_trabajados: DecimalStr | None = None
    ideal: DecimalStr | None = None
    fecha_corte: date | None = None
    #: `True` si los días trabajados los derivó el sistema de la fecha de corte;
    #: `False` si los escribió el usuario, cuya afirmación manda.
    derivado: bool = True


class CalendarioAgroEntrada(BaseModel):
    """`dias_trabajados` nulo significa **derivado** de la fecha de corte."""

    dias_habiles: Decimal = Field(gt=0, le=31, max_digits=5, decimal_places=2)
    dias_trabajados: Decimal | None = Field(default=None, ge=0, le=31, max_digits=5)


# ── Indicadores y reportes ────────────────────────────────────────────────────


class IndicadoresAgro(EsquemaBase):
    """El bloque de indicadores de una fila, sea cual sea el eje.

    Un solo esquema reutilizado en los siete ejes de resumen, en los dos cruces
    y en el consolidado, por la misma razón que `FilaIndicadores` en carnes: un
    tipo en el frontend y un componente de fila. Si un eje necesita un campo
    propio, se añade aquí como opcional; duplicar el esquema es cómo se empieza
    a divergir.

    **Las filas de `TipoItem = IMPUESTO` no están en ninguno de estos números.**
    El impuesto se ingiere y se guarda marcado —para poder conciliar con el
    origen— y se excluye de todo total, de todo porcentaje y de toda comparación
    contra presupuesto: no es venta, es recaudo a nombre de terceros. Lo que sí
    se publica, aparte, es cuánto se excluyó: ver `ConciliacionAgro`.

    Los campos que dependen del presupuesto viajan **vacíos** en los ejes que no
    se presupuestan —cliente, grupo y tipo de ítem—. No es un hueco por cargar:
    es que ahí no hay meta contra la que medir.
    """

    #: La venta en la medida del reporte (pesos o kilos). Es `TotalNeto` cuando
    #: la medida es `valor`; ver el supuesto marcado en `agro_venta.py`.
    venta: DecimalStr
    #: La venta **siempre en pesos**, aunque el reporte se esté mirando en
    #: kilos: el margen y la participación son conceptos monetarios.
    venta_valor: DecimalStr
    kilos: DecimalStr
    cantidad: DecimalStr
    #: `LineasFacturadas`. **Líneas, no documentos ni tickets.** Una venta de
    #: ocho productos son ocho líneas y **un** documento, y la fuente no entrega
    #: el documento. No se aproxima y no se renombra.
    lineas_facturadas: int
    #: Fracción de la venta total del corte que representa esta fila.
    participacion: DecimalStr | None = None

    margen_valor: DecimalStr | None = None
    margen_porcentaje: DecimalStr | None = None

    presupuesto: DecimalStr | None = None
    cumplimiento: DecimalStr | None = None
    ideal: DecimalStr | None = None
    brecha: DecimalStr | None = None
    semaforo: Semaforo = Semaforo.SIN_PRESUPUESTO
    proyeccion: DecimalStr | None = None
    cumplimiento_proyectado: DecimalStr | None = None
    venta_diaria_promedio: DecimalStr | None = None
    venta_diaria_requerida: DecimalStr | None = None
    dias_habiles: DecimalStr | None = None
    dias_trabajados: DecimalStr | None = None


class FilaResumenAgro(IndicadoresAgro):
    """Una fila del reporte de resumen: el miembro y sus indicadores."""

    clave: str
    nombre: str
    #: El último día **dentro del corte** en que este miembro tuvo venta.
    #:
    #: Se llama `ultima_venta` y no `ultima_compra` aunque en el eje de cliente
    #: la pantalla lo rotule así: el sistema mide ventas, y el mismo campo en el
    #: eje de vendedor o de centro no describe la compra de nadie.
    #:
    #: **Está acotado al corte, no es la última venta histórica.** Filtrar por
    #: julio y leer «12 de julio» significa que ese fue su último día *en julio*;
    #: puede haber comprado en agosto. Un campo que a veces mirara fuera del
    #: rango y a veces no sería imposible de interpretar.
    ultima_venta: date | None = None


class ConciliacionAgro(EsquemaBase):
    """Lo que se dejó fuera de los totales, y por qué.

    Existe para que la cifra del reporte se pueda conciliar con el origen sin
    tener que adivinar la diferencia. `impuesto_*` es la venta que trae la
    fuente con `TipoItem = IMPUESTO` y que **no** suma en ningún indicador: no
    es venta, es recaudo a nombre de terceros. Está guardada y marcada, no
    descartada, para que nadie crea que se perdieron filas.
    """

    impuesto_valor: DecimalStr
    impuesto_kilos: DecimalStr
    #: Suma de `LineasFacturadas` de las filas de impuesto: **líneas, no filas**.
    #: No tiene por qué coincidir con el campo `impuesto` de la corrida, que
    #: cuenta filas del origen —una fila puede traer varias líneas facturadas—.
    #: En una carga real de siete días fueron 170 filas y 180 líneas. Se dice
    #: aquí porque quien concilie contra el ERP va a ver los dos números juntos
    #: y, sin esta nota, va a leer la diferencia como diez filas perdidas.
    impuesto_lineas: int
    nota: str = Field(
        default=(
            "TipoItem = IMPUESTO se ingiere y se guarda marcado, y se excluye de todo total, "
            "porcentaje y comparación contra presupuesto: no es venta, es recaudo a nombre "
            "de terceros. Sumado a la venta publicada da el total bruto del origen."
        )
    )


class ParametrosCalculoAgro(EsquemaBase):
    """De dónde sale cada número (§4.2), y qué se dejó fuera.

    Va en toda respuesta de reporte para que la pantalla pueda mostrar la
    fórmula y sus parámetros al lado del resultado. Un número sin origen es
    exactamente el problema que SIGREP viene a resolver.

    `cuadre` viaja aquí **en todos los reportes**, y no solo en la pantalla de
    presupuesto, porque un descuadre entre descomposiciones invalida la lectura
    de cualquiera de ellas y quien mire un cumplimiento tiene derecho a saberlo
    sin ir a buscarlo a otra pantalla.
    """

    fecha_corte: date
    dias_habiles: DecimalStr | None = None
    dias_trabajados: DecimalStr | None = None
    umbrales: dict[str, str]
    dimension_presupuesto: str | None = None
    cuadre: CuadrePresupuestoSalida | None = None
    conciliacion: ConciliacionAgro
    formulas: dict[str, str] = Field(
        default_factory=lambda: dict(_FORMULAS),
        description="Las fórmulas tal como están escritas en la especificación",
    )


_FORMULAS: dict[str, str] = {
    "venta": "suma(TotalNeto) de las lineas con TipoItem distinto de IMPUESTO",
    "cumplimiento": "V / P, **dentro de una sola dimension de presupuesto**",
    "ideal": "centro de operacion: T / H · resto: suma(P_i x ideal_i) / suma(P_i) por centro",
    "brecha": "cumplimiento - ideal",
    "venta_diaria_promedio": "V / T",
    "proyeccion": "venta_diaria_promedio * H",
    "cumplimiento_proyectado": "proyeccion / P",
    "venta_diaria_requerida": "(P - V) / (H - T); 0 si V >= P; indefinido si H = T",
    "margen_valor": (
        "suma(TotalNeto) - suma(TotalCosto); indefinido si alguna linea no tiene costo"
    ),
    "margen_porcentaje": (
        "margen_valor / suma(TotalNeto); indefinido si alguna linea no tiene costo"
    ),
    "participacion": "venta de la fila / venta total del corte, recalculada sobre totales",
    "presupuesto": (
        "cuatro descomposiciones del MISMO total (vendedor, centro de operacion, especie, "
        "tipo comercial). NO se suman entre si: sumarlas daria el doble de la meta"
    ),
}


class RespuestaResumenAgro(EsquemaBase):
    """`GET /agro/reportes/resumen` — la venta por cualquiera de los siete ejes."""

    periodo: str
    fecha_corte: date
    medida: Medida
    por: EjeResumen
    consolidado: IndicadoresAgro
    filas: list[FilaResumenAgro]
    parametros_calculo: ParametrosCalculoAgro


class FilaCruceAgro(IndicadoresAgro):
    """Una fila de un cruce: las claves de sus dos o tres ejes.

    `claves` y `nombres` viajan como listas alineadas con `ejes` en lugar de
    como campos con nombre fijo, y es deliberado: los dos cruces tienen distinto
    número de ejes y con campos fijos el de dos tendría uno vacío. La pantalla
    recorre `ejes` y pinta una columna por cada uno.
    """

    claves: list[str]
    nombres: list[str]


class RespuestaCruceAgro(EsquemaBase):
    """`GET /agro/reportes/cruce` — vendedor × cliente y vendedor × cliente × producto.

    **Los cruces cuadran con el total.** La suma de sus filas es exactamente la
    venta del corte, porque las tres dimensiones son obligatorias en la línea:
    lo que llega sin vendedor, sin cliente o sin producto entra con su miembro
    visible (`SIN VENDEDOR`, `SIN CLIENTE`, `SIN PRODUCTO`) y sigue sumando.
    Un cruce que descartara los nulos publicaría menos venta que el resumen y
    nadie sabría por qué.

    `truncado` avisa de que la respuesta trae solo las primeras `limite` filas
    por venta. El **consolidado no se trunca**: es el total del corte entero, no
    el de las filas publicadas, para que la participación siga siendo cierta.
    """

    periodo: str
    fecha_corte: date
    medida: Medida
    por: EjeCruce
    ejes: list[str]
    consolidado: IndicadoresAgro
    filas: list[FilaCruceAgro]
    truncado: bool = False
    limite: int
    parametros_calculo: ParametrosCalculoAgro


class FilaVentaDiariaAgro(EsquemaBase):
    """Una fila del reporte de venta diaria: un centro de operación."""

    centro: str
    nombre: str
    #: Un valor por fecha, en el mismo orden que `fechas`. `null` en los días
    #: sin venta registrada, que no es lo mismo que un día con venta cero.
    valores: list[DecimalStr | None]
    total: DecimalStr


class TotalesVentaDiariaAgro(EsquemaBase):
    """La fila de totales, en un campo propio y no como una fila más.

    Mezclada entre las filas, la pantalla tendría que reconocerla por su nombre,
    y esa clase de convención se rompe el día que alguien bautice así un centro.
    Cuadra con la suma de `filas` por construcción: se acumula sobre los mismos
    valores que se publican.
    """

    valores: list[DecimalStr | None]
    total: DecimalStr
    #: `Σ (P_i / H_i)` sobre los centros: la suma de las líneas de referencia de
    #: las filas, no el presupuesto agregado partido por unos días ponderados.
    #: `null` si ningún centro tiene presupuesto, y también si alguno lo tiene y
    #: no tiene días hábiles: ahí el término es incalculable y sumar solo el
    #: resto publicaría una referencia más baja que la real con pinta de
    #: completa (§7).
    presupuesto_diario: DecimalStr | None = None


class RespuestaVentaDiariaAgro(EsquemaBase):
    """`GET /agro/reportes/venta-diaria` — la serie por día, por centro."""

    periodo: str
    fecha_corte: date
    desde: date
    hasta: date
    medida: Medida
    fechas: list[date]
    #: Presupuesto diario derivado por centro: `presupuesto_mensual / H`. Sale
    #: de la dimensión `centro_operacion`, que es la única que reparte la meta
    #: por la unidad que tiene calendario.
    presupuesto_diario_por_centro: dict[str, DecimalStr | None] = Field(default_factory=dict)
    filas: list[FilaVentaDiariaAgro]
    totales: TotalesVentaDiariaAgro
    parametros_calculo: ParametrosCalculoAgro


# ── Ingesta ───────────────────────────────────────────────────────────────────


class SolicitudIngestaAgro(BaseModel):
    """Rango a cargar. **Los dos extremos se incluyen.**"""

    desde: date
    hasta: date

    @model_validator(mode="after")
    def _rango_coherente(self) -> SolicitudIngestaAgro:
        if self.hasta < self.desde:
            raise ValueError("La fecha final no puede ser anterior a la inicial.")
        return self


class CorridaAgroSalida(EsquemaBase):
    id: int
    cuando: datetime
    quien: str | None = None
    fuente: str
    desde: date | None = None
    hasta: date | None = None
    estado: str
    filas_leidas: int
    aceptadas: int
    rechazadas: int
    #: Filas de impuesto cargadas. Van **dentro** de `aceptadas` —se guardan— y
    #: se cuentan aparte porque son las que no van a aparecer en ningún total.
    #: Sin este número, conciliar la corrida contra el origen daría una
    #: diferencia sin explicación.
    impuesto: int = 0
    duracion_ms: int | None = None


class RechazoAgroSalida(EsquemaBase):
    fila: int | None = None
    campo: str | None = None
    valor: str | None = None
    motivo: str = Field(description="Por qué no se pudo aceptar la fila")
