"""Esquemas de los reportes — el núcleo del contrato.

`FilaIndicadores` es **un solo esquema**, reutilizado sin variantes en el
consolidado, en el grupo, en el punto de venta y en la categoría. Los niveles
superiores heredan de él y solo añaden su identificación, de modo que el JSON
sale plano tal como lo describe `docs/API.md` y el frontend puede tener un solo
tipo y un solo componente de fila.

Si algún día un nivel necesita un campo propio, se añade a `FilaIndicadores`
como opcional. Duplicar el esquema es cómo se empieza a divergir.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.domain.enums import Medida, Semaforo
from app.schemas.common import DecimalStr, EsquemaBase


class FilaIndicadores(EsquemaBase):
    """Los indicadores de §4 para un corte cualquiera.

    Todo lo indefinido viaja como `null` y la pantalla pinta «—». Nunca `0`:
    «vendió cero» y «no se puede calcular» son afirmaciones distintas.

    `dias_habiles` y `dias_trabajados` viajan **en la propia fila**, no solo en
    `parametros_calculo`, porque en el consolidado y en el grupo son un
    agregado de varias zonas y quien lea el reporte tiene derecho a ver con qué
    `H` y qué `T` se calculó *esa* línea (§4.2).
    """

    presupuesto: DecimalStr | None = None
    venta: DecimalStr
    cumplimiento: DecimalStr | None = None
    ideal: DecimalStr | None = None
    brecha: DecimalStr | None = None
    semaforo: Semaforo
    proyeccion: DecimalStr | None = None
    cumplimiento_proyectado: DecimalStr | None = None
    venta_diaria_promedio: DecimalStr | None = None
    venta_diaria_requerida: DecimalStr | None = None
    venta_anio_anterior: DecimalStr | None = None
    crecimiento: DecimalStr | None = None
    margen_valor: DecimalStr | None = None
    margen_porcentaje: DecimalStr | None = None
    dias_habiles: DecimalStr | None = None
    dias_trabajados: DecimalStr | None = None


class FilaCategoria(FilaIndicadores):
    categoria: str


class FilaPuntoVenta(FilaIndicadores):
    punto_venta: str = Field(description="Código C.O.")
    nombre: str
    categorias: list[FilaCategoria] = Field(default_factory=list)


class FilaGrupo(FilaIndicadores):
    codigo: str
    nombre: str


class PuntoVentaSinPresupuesto(BaseModel):
    """Venta de un punto no presupuestado (432 EVENTOS BUCARAMANGA).

    Se reporta **aparte** y nunca se descarta en silencio (§3.1 y §7): su venta
    es real y el gerente necesita verla, pero mezclarla con el consolidado
    presupuestado distorsionaría el cumplimiento de toda la compañía.
    """

    codigo_co: str
    nombre: str
    venta: DecimalStr
    kilos: DecimalStr


class ParametrosCalculo(BaseModel):
    """De dónde sale cada número (§4.2).

    Va en toda respuesta de reporte para que la pantalla pueda mostrar la
    fórmula y sus parámetros al lado del resultado. Un número sin origen es
    exactamente el problema que SIGREP viene a resolver.
    """

    fecha_corte: date
    dias_habiles: DecimalStr | None = None
    dias_trabajados: DecimalStr | None = None
    umbrales: dict[str, str]
    formulas: dict[str, str] = Field(
        default_factory=lambda: dict(_FORMULAS),
        description="Las fórmulas tal como están escritas en la especificación",
    )


_FORMULAS: dict[str, str] = {
    "cumplimiento": "V / P",
    # En una fila de una sola zona el ideal es `T / H` y se puede rehacer a mano
    # con los días que la propia respuesta publica. En una fila agregada que
    # abarca varias zonas —un grupo, el consolidado— **no lo es**: se pondera el
    # ideal de cada zona por su presupuesto, porque la venta esperada al corte
    # es `Σ(P_i × ideal_i)` y el presupuesto total `Σ P_i`. Promediar los días y
    # dividir después daría otro número, y sería el equivocado.
    # `H` y `T` siguen siendo las medias ponderadas de los días, que es lo que
    # da sentido a `V / T` y a los días que quedan en `H - T`.
    "ideal": "una zona: T / H · agregado: suma(P_i x ideal_i) / suma(P_i)",
    "brecha": "cumplimiento - ideal",
    "venta_diaria_promedio": "V / T",
    "proyeccion": "venta_diaria_promedio * H",
    "cumplimiento_proyectado": "proyeccion / P",
    "venta_diaria_requerida": "(P - V) / (H - T); 0 si V >= P; indefinido si H = T",
    # Solo entran en el cociente los puntos de venta con historia del año
    # anterior. La venta comparable se proyecta al cierre: comparar venta
    # parcial con un mes cerrado publicaría un decrecimiento ficticio.
    "crecimiento": (
        "(proyeccion(V_comparable) - V_anio_anterior) / V_anio_anterior (solo puntos con historia)"
    ),
    # El margen de un conjunto al que le falta el costo de alguna línea es
    # **indefinido**, y no el margen de las líneas que sí lo traen: ese
    # porcentaje parecería completo sin serlo. Hoy le ocurre a 409 PEREIRA —el
    # endpoint de la API que lo sirve no entrega el costo— y, por tanto, a todo
    # agregado que lo contenga, el consolidado de la compañía incluido. La
    # salvedad se publica junto a la fórmula para que quien lea el reporte sepa
    # por qué ve «—» donde antes veía un 100 %.
    "margen_valor": (
        "suma(valor_subtotal) - suma(costo_promedio); indefinido si alguna linea no tiene costo"
    ),
    "margen_porcentaje": (
        "margen_valor / suma(valor_subtotal); indefinido si alguna linea no tiene costo"
    ),
    "presupuesto_diario": "presupuesto_mensual / H",
}


class RespuestaTablero(BaseModel):
    """`GET /reportes/tablero` — la pantalla de la gerencia."""

    periodo: str
    fecha_corte: date
    medida: Medida
    consolidado: FilaIndicadores
    grupos: list[FilaGrupo]
    sin_presupuesto: list[PuntoVentaSinPresupuesto]
    parametros_calculo: ParametrosCalculo


class RespuestaCumplimiento(BaseModel):
    """`GET /reportes/cumplimiento` — la tabla del Excel, viva."""

    periodo: str
    fecha_corte: date
    medida: Medida
    consolidado: FilaIndicadores
    filas: list[FilaPuntoVenta]
    sin_presupuesto: list[PuntoVentaSinPresupuesto]
    parametros_calculo: ParametrosCalculo


class FilaVentaDiaria(BaseModel):
    punto_venta: str
    nombre: str
    #: Un valor por fecha, en el mismo orden que `fechas`. `null` en los días
    #: sin venta registrada, que no es lo mismo que un día con venta cero.
    valores: list[DecimalStr | None]
    total: DecimalStr


class TotalesVentaDiaria(BaseModel):
    """La fila de totales del reporte de venta diaria.

    Va en un **campo propio** y no como una fila más de `filas`, y es
    deliberado: mezclada, la pantalla tendría que reconocerla por su nombre
    —`punto_venta == "TOTAL"`— y esa clase de convención se rompe el día que
    alguien bautice así un punto de venta. Aparte, la pantalla la fija al pie
    de la tabla sin tener que preguntarle nada a nadie.

    Respeta el filtro: si se piden tres puntos de venta, el total es el de esos
    tres. Y cuadra con la suma de `filas` por construcción —se acumula sobre
    los mismos valores que se publican—, no por coincidencia.
    """

    #: Suma por día de las filas incluidas, alineada con `fechas`. `null` en un
    #: día sin venta registrada en **ningún** punto, que no es lo mismo que un
    #: día que sumó cero.
    valores: list[DecimalStr | None]
    #: Suma de los totales de las filas: el total del período o del rango.
    total: DecimalStr
    #: Suma de las líneas de referencia de las filas, `Σ (P_i / H_i)`, en el
    #: período de la petición. `null` si ningún punto tiene presupuesto
    #: parametrizado, o si alguno lo tiene y su zona no tiene días hábiles: ahí
    #: el término es incalculable y sumar solo el resto publicaría una
    #: referencia más baja que la real con pinta de completa (§7).
    presupuesto_diario: DecimalStr | None = None
    #: El mismo total, uno por período. Las mismas claves que
    #: `RespuestaVentaDiaria.presupuesto_diario_por_periodo`.
    presupuesto_diario_por_periodo: dict[str, DecimalStr | None] = Field(default_factory=dict)


class RespuestaVentaDiaria(BaseModel):
    """`GET /reportes/venta-diaria` — el equivalente vivo de `Hoja1`.

    Admite dos modos, y el primero es el de siempre:

    - **Por período.** Sin `desde`, las columnas van del día 1 a la fecha de
      corte del `periodo` pedido. `desde`, `hasta` y `periodos` describen ese
      mismo rango, de modo que la respuesta es autodescriptiva en los dos
      modos y la pantalla no necesita saber cuál se usó.
    - **Por rango.** Con `desde`, las columnas van de `desde` a `hasta`, aunque
      el rango cruce de mes.

    `periodo` sigue siendo el **período de referencia** en los dos modos: de él
    salen `parametros_calculo` y `presupuesto_diario_por_pdv`. Cuando el rango
    cruza meses, la referencia de cada día sale de
    `presupuesto_diario_por_periodo`, porque el presupuesto es mensual (§3.3) y
    un día de julio no se mide contra el presupuesto de agosto.
    """

    periodo: str
    #: Último día publicado. Coincide siempre con `hasta`.
    fecha_corte: date
    #: Primer día publicado. Sin rango, el día 1 del período.
    desde: date
    #: Último día publicado. Sin rango, la fecha de corte del período.
    hasta: date
    medida: Medida
    #: Períodos `YYYY-MM` que el rango toca, en orden, más el de la petición.
    #: Son las claves de `presupuesto_diario_por_periodo`.
    periodos: list[str] = Field(default_factory=list)
    fechas: list[date]
    #: Presupuesto diario derivado por punto de venta, la línea de referencia
    #: del gráfico: `presupuesto_mensual / dias_habiles(zona)`. Es el del
    #: **período de la petición**; equivale a
    #: `presupuesto_diario_por_periodo[periodo]`.
    presupuesto_diario_por_pdv: dict[str, DecimalStr | None]
    #: La misma referencia, un mapa por período:
    #: `{"2026-07": {"402": "..."}, "2026-08": {"402": "..."}}`. Con el rango
    #: dentro de un solo mes tiene una única entrada.
    presupuesto_diario_por_periodo: dict[str, dict[str, DecimalStr | None]] = Field(
        default_factory=dict
    )
    filas: list[FilaVentaDiaria]
    totales: TotalesVentaDiaria
    parametros_calculo: ParametrosCalculo


class FilaClientes(BaseModel):
    clave: str
    nombre: str
    venta: DecimalStr
    kilos: DecimalStr
    margen_porcentaje: DecimalStr | None = None
    #: Fracción de la venta total del corte que representa esta fila.
    participacion: DecimalStr | None = None


class RespuestaClientes(BaseModel):
    """`GET /reportes/clientes` — venta por cliente, vendedor, canal o pago."""

    periodo: str
    fecha_corte: date
    por: str
    filas: list[FilaClientes]
    parametros_calculo: ParametrosCalculo
