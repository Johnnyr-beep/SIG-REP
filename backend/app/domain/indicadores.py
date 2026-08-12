"""Los indicadores del reporte gerencial (§4 de la especificación).

Funciones puras sobre `Decimal`. Sin base de datos, sin ORM, sin HTTP.

Tres reglas gobiernan todo este módulo:

1. **Ninguna división explota y ninguna devuelve cero.** Si el denominador es
   cero o falta un dato, el resultado es `None` y la interfaz pinta «—». Un `0`
   en un cumplimiento significa «vendió nada», que es una afirmación distinta de
   «no se puede calcular», y confundirlas es exactamente el defecto que tiene
   hoy el Excel.
2. **Los porcentajes no se promedian.** Se recalculan sobre los totales (§7).
   Por eso aquí no existe ninguna función que reciba una lista de porcentajes.
   El `ideal` de un corte multizona es la única excepción aparente, y no lo es:
   no se promedia el ideal de nadie, se recalcula como
   `venta esperada / presupuesto` = `Σ(P_i × ideal_i) / Σ P_i`, que es la misma
   regla aplicada al único total que tiene sentido aquí. Ver
   `calcular_indicadores`.
3. **No se replican las fórmulas del libro vigente.** El «Hallazgo del Excel
   actual» de §4.2 documenta que sus divisores están desalineados entre hojas.
   Estas son las fórmulas de la especificación, y el reporte publica `H` y `T`
   junto al resultado para que cualquiera pueda rehacer el cálculo a mano.

Nomenclatura de §4:

    P = presupuesto del mes      V = venta acumulada al corte
    H = días hábiles del mes     T = días trabajados al corte
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import Semaforo
from app.domain.semaforo import UmbralesSemaforo, evaluar_semaforo

#: Los porcentajes viajan como fracción decimal con cuatro cifras
#: (`"0.2885"` = 28.85 %), según `docs/API.md`.
DECIMALES_PORCENTAJE = 4

#: `H` y `T` se **publican** con dos decimales (`"27.50"`, `"7.50"`). El
#: calendario admite medias jornadas (§3.2) y un agregado multizona da un
#: promedio ponderado con cola infinita; dos cifras es lo que la pantalla puede
#: mostrar sin mentir. El redondeo es de publicación: los cálculos que dependen
#: de `H` y `T` usan el valor exacto que entra en `InsumosIndicadores`.
DECIMALES_DIAS = 2

CERO = Decimal("0")


# ── Utilidades de cálculo protegido ───────────────────────────────────────────


def dividir(numerador: Decimal | None, denominador: Decimal | None) -> Decimal | None:
    """División protegida: `None` si falta un dato o el denominador es cero.

    Es la única forma de dividir en todo el dominio. Nunca lanza y nunca
    devuelve cero por defecto.
    """
    if numerador is None or denominador is None or denominador == CERO:
        return None
    return numerador / denominador


def redondear(valor: Decimal | None, decimales: int) -> Decimal | None:
    """Cuantiza a la escala indicada propagando `None`.

    Se usa solo al armar la respuesta: los cálculos intermedios trabajan con la
    precisión completa de `Decimal` para no arrastrar error de redondeo.
    """
    if valor is None:
        return None
    return valor.quantize(Decimal(1).scaleb(-decimales))


def redondear_porcentaje(valor: Decimal | None) -> Decimal | None:
    """Cuantiza un porcentaje a las 4 cifras que exige el contrato."""
    return redondear(valor, DECIMALES_PORCENTAJE)


def redondear_no_nulo(valor: Decimal, decimales: int) -> Decimal:
    """Variante para valores que nunca son `None` (la venta, siempre sumable).

    Existe para no tener que escribir `redondear(x, 2) or CERO`, que además de
    feo pierde la escala: `Decimal("0.00") or CERO` devuelve `Decimal("0")` y el
    contrato quedaría emitiendo `"0"` donde promete `"0.00"`.
    """
    return valor.quantize(Decimal(1).scaleb(-decimales))


# ── §4.1 Cumplimiento ─────────────────────────────────────────────────────────


def cumplimiento(venta: Decimal | None, presupuesto: Decimal | None) -> Decimal | None:
    """`V / P` — qué fracción del presupuesto se lleva vendida.

    `None` cuando el punto de venta no está presupuestado; es el caso de
    432 EVENTOS BUCARAMANGA, que vende y no descuadra el consolidado.
    """
    return dividir(venta, presupuesto)


def ideal(dias_trabajados: Decimal | None, dias_habiles: Decimal | None) -> Decimal | None:
    """`T / H` — el cumplimiento que *debería* llevarse hoy."""
    return dividir(dias_trabajados, dias_habiles)


def brecha(valor_cumplimiento: Decimal | None, valor_ideal: Decimal | None) -> Decimal | None:
    """`cumplimiento − ideal`. Positiva es verde; `None` si falta cualquiera."""
    if valor_cumplimiento is None or valor_ideal is None:
        return None
    return valor_cumplimiento - valor_ideal


# ── §4.2 Venta diaria y proyección ────────────────────────────────────────────


def venta_diaria_promedio(venta: Decimal | None, dias_trabajados: Decimal | None) -> Decimal | None:
    """`V / T` — ritmo de venta observado al corte.

    `None` el primer día del mes, cuando `T = 0`: todavía no hay promedio que
    calcular y decir «vende 0 al día» sería falso.
    """
    return dividir(venta, dias_trabajados)


def proyeccion(
    valor_venta_diaria_promedio: Decimal | None, dias_habiles: Decimal | None
) -> Decimal | None:
    """`venta_diaria_promedio × H` — cierre de mes al ritmo actual."""
    if valor_venta_diaria_promedio is None or dias_habiles is None:
        return None
    return valor_venta_diaria_promedio * dias_habiles


def cumplimiento_proyectado(
    valor_proyeccion: Decimal | None, presupuesto: Decimal | None
) -> Decimal | None:
    """`proyeccion / P` — a dónde llega el mes si nada cambia."""
    return dividir(valor_proyeccion, presupuesto)


def venta_diaria_requerida(
    presupuesto: Decimal | None,
    venta: Decimal | None,
    dias_habiles: Decimal | None,
    dias_trabajados: Decimal | None,
) -> Decimal | None:
    """`(P − V) / (H − T)` — lo que hay que vender cada día que queda.

    Es el número accionable del reporte, y es justamente el que el Excel actual
    no tiene bien. Reglas de §4.2, en este orden:

    - `V ≥ P` → `0`. El presupuesto ya está cubierto; no queda nada por vender.
      Se evalúa **antes** que el resto porque es una afirmación cierta aunque el
      mes ya haya terminado.
    - `H ≤ T` → `None`. No quedan días hábiles entre los que repartir el
      faltante; la interfaz pinta «—». Se incluye `H < T` —un calendario
      incoherente— porque un requerido negativo sería peor que un vacío.
    - En cualquier otro caso, el faltante repartido entre los días restantes.
    """
    if presupuesto is None or venta is None or dias_habiles is None or dias_trabajados is None:
        return None
    if venta >= presupuesto:
        return CERO
    if dias_habiles <= dias_trabajados:
        return None
    return (presupuesto - venta) / (dias_habiles - dias_trabajados)


# ── §4.3 Crecimiento ──────────────────────────────────────────────────────────


def crecimiento(
    venta_actual: Decimal | None, venta_anio_anterior: Decimal | None
) -> Decimal | None:
    """`V_actual / V_año_anterior − 1`.

    Sin historia cargada el indicador viaja vacío, nunca en cero: un `0 %` de
    crecimiento afirma que se vendió lo mismo que el año pasado, y eso no es lo
    que sabemos cuando simplemente no hay dato de 2025.
    """
    razon = dividir(venta_actual, venta_anio_anterior)
    if razon is None:
        return None
    return razon - Decimal(1)


# ── §4.4 Margen ───────────────────────────────────────────────────────────────


def margen_valor(venta: Decimal | None, costo: Decimal | None) -> Decimal | None:
    """`Σ valor_subtotal − Σ costo_promedio`."""
    if venta is None or costo is None:
        return None
    return venta - costo


def margen_porcentaje(venta: Decimal | None, costo: Decimal | None) -> Decimal | None:
    """`margen_valor / Σ valor_subtotal`, **ponderado sobre los totales**.

    Nunca se promedia el porcentaje `MARGEN` que envía SIESA línea a línea:
    promediar porcentajes de líneas de distinto tamaño da un número falso. Ese
    campo se conserva solo para conciliación (§4.4).
    """
    return dividir(margen_valor(venta, costo), venta)


# ── Armado de la fila completa ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class InsumosIndicadores:
    """Los agregados crudos de un corte, ya sumados sobre el detalle.

    Casi todo es opcional porque un punto de venta puede no tener presupuesto
    (§3.1) y un período puede no tener calendario cargado.

    `venta` y `presupuesto` van en la medida del reporte —pesos o kilos—,
    mientras que `venta_valor` y `costo` van **siempre en pesos**: el margen es
    un concepto monetario y calcularlo sobre kilos daría un número sin
    significado. Cuando la medida es `valor`, `venta_valor` sobra y se toma de
    `venta`.

    `dias_habiles` y `dias_trabajados` llegan **sin redondear**. En una fila de
    un solo punto de venta son los del calendario de su zona; en un agregado
    multizona son promedios ponderados con cola decimal larga, y quien los
    redondee antes de proyectar mete el error que documenta §4.2. Se redondean
    al publicar, no al calcular.

    Los dos campos opcionales de abajo existen porque un agregado de varias
    zonas o de varios puntos de venta no se comporta como la suma ingenua de sus
    hijos; ambos son `None` en una fila simple, donde no hay nada que corregir.
    """

    venta: Decimal
    costo: Decimal
    presupuesto: Decimal | None = None
    venta_anio_anterior: Decimal | None = None
    dias_habiles: Decimal | None = None
    dias_trabajados: Decimal | None = None
    venta_valor: Decimal | None = None
    #: Venta **comparable**: la de los puntos de venta que tienen dato del año
    #: anterior. Se usa solo para el crecimiento (§4.3), nunca para el
    #: cumplimiento. Es el *same-store sales* del comercio: comparar 2026 con
    #: 2025 exige que los dos lados hablen del mismo universo de puntos, o dos
    #: puntos nuevos publican un crecimiento inventado. `None` = todo comparable.
    venta_comparable: Decimal | None = None
    #: `ideal` ya ponderado por presupuesto para un agregado multizona. Cuando
    #: viene, sustituye a `T / H`. Ver `calcular_indicadores`.
    ideal_agregado: Decimal | None = None

    @property
    def base_margen(self) -> Decimal:
        """Venta en pesos contra la que se pondera el margen."""
        return self.venta if self.venta_valor is None else self.venta_valor

    @property
    def base_crecimiento(self) -> Decimal:
        """Venta contra la que se mide el crecimiento del año anterior."""
        return self.venta if self.venta_comparable is None else self.venta_comparable


@dataclass(frozen=True, slots=True)
class ResultadoIndicadores:
    """Los once números de una fila del reporte, ya cuantizados.

    Es el contenido de `FilaIndicadores` en `docs/API.md`, sin depender de
    Pydantic: el dominio no conoce la capa de transporte.
    """

    presupuesto: Decimal | None
    venta: Decimal
    cumplimiento: Decimal | None
    ideal: Decimal | None
    brecha: Decimal | None
    semaforo: Semaforo
    proyeccion: Decimal | None
    cumplimiento_proyectado: Decimal | None
    venta_diaria_promedio: Decimal | None
    venta_diaria_requerida: Decimal | None
    venta_anio_anterior: Decimal | None
    crecimiento: Decimal | None
    margen_valor: Decimal | None
    margen_porcentaje: Decimal | None
    dias_habiles: Decimal | None
    dias_trabajados: Decimal | None


def calcular_indicadores(
    insumos: InsumosIndicadores,
    umbrales: UmbralesSemaforo,
    *,
    decimales_medida: int = 2,
) -> ResultadoIndicadores:
    """Arma la fila completa a partir de los agregados de un corte.

    Función pura: mismos insumos, mismo resultado. Los porcentajes se cuantizan
    a 4 cifras y las magnitudes a la escala de la medida (2 para pesos, 3 para
    kilos), que es lo que exige el contrato de la API.

    Los cálculos intermedios usan la precisión completa de `Decimal`: la
    proyección se deriva del promedio diario **sin redondear**, y `H` y `T`
    entran exactos y se redondean solo al asignarlos al resultado. Redondear
    antes de multiplicar por `H` mete un error de hasta 28 pesos por punto de
    venta y luego nadie entiende por qué el consolidado no cuadra con la suma.

    **`ideal` en un agregado no es `T / H`.** En una fila de una sola zona sí, y
    es lo que se calcula. Pero cuando el corte abarca varias zonas con
    calendarios distintos, la venta esperada al corte es `Σ(P_i × ideal_i)` y el
    presupuesto es `Σ P_i`, de modo que el ideal del agregado es
    `Σ(P_i × ideal_i) / Σ P_i` —la media de los ideales ponderada por
    presupuesto—, que **no** coincide con el cociente de las medias `T / H`
    (desigualdad de Jensen: `ideal` es un cociente, y la media de cocientes no
    es el cociente de las medias). Ese valor lo calcula quien conoce los pesos
    —el servicio de reportes— y llega aquí en `ideal_agregado`, mientras que `H`
    y `T` conservan su significado propio: los días hábiles y trabajados medios
    del corte, que son los que proyectan la venta y los que dejan `H − T` como
    número de días para la venta diaria requerida.
    """
    valor_cumplimiento = cumplimiento(insumos.venta, insumos.presupuesto)
    valor_ideal = (
        insumos.ideal_agregado
        if insumos.ideal_agregado is not None
        else ideal(insumos.dias_trabajados, insumos.dias_habiles)
    )
    promedio_diario = venta_diaria_promedio(insumos.venta, insumos.dias_trabajados)
    valor_proyeccion = proyeccion(promedio_diario, insumos.dias_habiles)

    return ResultadoIndicadores(
        presupuesto=redondear(insumos.presupuesto, decimales_medida),
        venta=redondear_no_nulo(insumos.venta, decimales_medida),
        cumplimiento=redondear_porcentaje(valor_cumplimiento),
        ideal=redondear_porcentaje(valor_ideal),
        brecha=redondear_porcentaje(brecha(valor_cumplimiento, valor_ideal)),
        semaforo=evaluar_semaforo(valor_cumplimiento, valor_ideal, umbrales),
        proyeccion=redondear(valor_proyeccion, decimales_medida),
        cumplimiento_proyectado=redondear_porcentaje(
            cumplimiento_proyectado(valor_proyeccion, insumos.presupuesto)
        ),
        venta_diaria_promedio=redondear(promedio_diario, decimales_medida),
        venta_diaria_requerida=redondear(
            venta_diaria_requerida(
                insumos.presupuesto,
                insumos.venta,
                insumos.dias_habiles,
                insumos.dias_trabajados,
            ),
            decimales_medida,
        ),
        venta_anio_anterior=redondear(insumos.venta_anio_anterior, decimales_medida),
        # Contra la venta **comparable**, no contra la venta total: los dos
        # lados del crecimiento tienen que hablar del mismo universo de puntos.
        crecimiento=redondear_porcentaje(
            crecimiento(insumos.base_crecimiento, insumos.venta_anio_anterior)
        ),
        # El margen siempre es dinero: 2 decimales, y ponderado sobre la venta
        # en pesos aunque el reporte se esté mirando en kilos.
        margen_valor=redondear(margen_valor(insumos.base_margen, insumos.costo), 2),
        margen_porcentaje=redondear_porcentaje(
            margen_porcentaje(insumos.base_margen, insumos.costo)
        ),
        # Aquí, y solo aquí, se redondean los días: el cálculo de arriba usó los
        # valores exactos.
        dias_habiles=redondear(insumos.dias_habiles, DECIMALES_DIAS),
        dias_trabajados=redondear(insumos.dias_trabajados, DECIMALES_DIAS),
    )
