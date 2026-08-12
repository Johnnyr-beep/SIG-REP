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
    # anterior. Comparar la venta de todos contra la de unos pocos publicaría un
    # crecimiento inventado. `V` y `V_anio_anterior` se publican completos.
    "crecimiento": "V_comparable / V_anio_anterior - 1 (solo puntos con historia)",
    "margen_valor": "suma(valor_subtotal) - suma(costo_promedio)",
    "margen_porcentaje": "margen_valor / suma(valor_subtotal)",
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


class RespuestaVentaDiaria(BaseModel):
    """`GET /reportes/venta-diaria` — el equivalente vivo de `Hoja1`."""

    periodo: str
    fecha_corte: date
    medida: Medida
    fechas: list[date]
    #: Presupuesto diario derivado por punto de venta, la línea de referencia
    #: del gráfico: `presupuesto_mensual / dias_habiles(zona)`.
    presupuesto_diario_por_pdv: dict[str, DecimalStr | None]
    filas: list[FilaVentaDiaria]
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
