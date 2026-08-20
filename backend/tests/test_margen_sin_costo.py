"""§4.4 · Un conjunto con alguna línea sin costo no tiene margen: publica «—».

409 PEREIRA —el segundo punto de venta de la compañía— registra en el módulo de
POS que solo sirve `GET /ventas/pos-vendedor-detalle`, y ese endpoint **no
entrega el costo**: llega vacío en el 100 % de sus filas. Mientras
`venta_lineas.costo_promedio` fue `NOT NULL`, esas líneas entraban en cero y la
fórmula de §4.4 publicaba

    margen = (Σ subtotal − 0) / Σ subtotal = 100 %

Un 100 % de margen no es una cifra alta: es una cifra **falsa**, y va a la
pantalla donde alguien toma decisiones. La regla del dominio es la misma de §4 y
§7: lo que no se puede calcular es `None` y la interfaz pinta «—».

La regla se aplica al **conjunto entero**: si cualquier línea del agregado
carece de costo, el margen de ese agregado es `None`. Calcularlo sobre «las
líneas que sí tienen costo» daría un porcentaje que parece completo y no lo es,
que es la peor de las dos opciones. La consecuencia —el consolidado de la
compañía pierde el margen mientras PEREIRA no traiga costo— es deliberada: no se
puede calcular, y que se vea es lo que crea la presión para que la API lo
entregue.

Lo que **no** cambia: cumplimiento, ideal, brecha, proyección, venta diaria y
crecimiento no dependen del costo y siguen funcionando para PEREIRA con toda
normalidad. Perder el margen no puede convertirse en perder el punto de venta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.domain.enums import AgrupacionClientes, Semaforo
from app.infrastructure.models.organizacion import Zona
from app.infrastructure.models.periodo import CalendarioZona
from app.infrastructure.models.venta import VentaLinea
from app.schemas.reportes import FilaPuntoVenta, RespuestaTablero
from tests.conftest import (
    PERIODO,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_periodo,
    id_punto_venta,
)

D = Decimal
CORTE = date(2026, 8, 15)

#: PEREIRA: el punto sin costo en el origen. MALAMBO: uno cualquiera con costo.
SIN_COSTO = "409"
CON_COSTO = "402"


# ── Ayudas ────────────────────────────────────────────────────────────────────


def _fijar_dias(sesion: Session, nombre_zona: str, habiles: str, trabajados: str) -> None:
    zona = sesion.scalars(select(Zona).where(Zona.nombre == nombre_zona)).one()
    fila = sesion.scalars(
        select(CalendarioZona).where(
            CalendarioZona.periodo_id == id_periodo(sesion),
            CalendarioZona.zona_id == zona.id,
        )
    ).one()
    fila.dias_habiles = D(habiles)
    fila.dias_trabajados = D(trabajados)
    sesion.commit()


def _fila(sesion: Session, codigo_co: str) -> FilaPuntoVenta:
    """La fila del reporte de cumplimiento de un punto de venta."""
    respuesta = ReportesService(sesion).cumplimiento(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, puntos_venta=(codigo_co,))
    )
    assert len(respuesta.filas) == 1
    return respuesta.filas[0]


def _tablero(sesion: Session, *codigos: str) -> RespuestaTablero:
    """El tablero limitado a los puntos de venta indicados."""
    alcance = [id_punto_venta(sesion, codigo) for codigo in codigos]
    return ReportesService(sesion).tablero(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, alcance=alcance)
    )


def _escenario_pereira(sesion: Session) -> None:
    """PEREIRA vendiendo medio presupuesto, con el costo que la API no manda."""
    _fijar_dias(sesion, "PEREIRA", "27.5", "7.5")
    dar_presupuesto(sesion, SIN_COSTO, "RES", "1000000")
    dar_venta(sesion, SIN_COSTO, "RES", 5, valor="500000", costo=None)


# ── La regla ──────────────────────────────────────────────────────────────────


def test_una_linea_sin_costo_deja_el_margen_en_none_y_no_en_uno(
    sesion: Session, estructura: None
) -> None:
    """El defecto exacto: PEREIRA publicando 100 % de margen.

    Con `costo_promedio` nulo, `Σ costo` vale cero y la fórmula de §4.4 daba
    `500000 / 500000 = 1.0000`. Tiene que dar «—».
    """
    _escenario_pereira(sesion)

    fila = _fila(sesion, SIN_COSTO)

    assert fila.margen_porcentaje != D("1.0000"), (
        "PEREIRA está publicando 100 % de margen: el costo que la API no manda "
        "se está sumando como cero"
    )
    assert fila.margen_porcentaje is None
    assert fila.margen_valor is None


def test_la_linea_sin_costo_se_persiste_nula_no_en_cero(sesion: Session, estructura: None) -> None:
    """`NULL` y `0` son afirmaciones distintas y la base tiene que distinguirlas."""
    _escenario_pereira(sesion)

    linea = sesion.scalars(
        select(VentaLinea).where(VentaLinea.punto_venta_id == id_punto_venta(sesion, SIN_COSTO))
    ).one()

    assert linea.costo_promedio is None, "un costo que no existe no es un costo de cero"


def test_el_resto_de_indicadores_de_pereira_se_siguen_calculando(
    sesion: Session, estructura: None
) -> None:
    """Perder el margen no puede ser perder el punto de venta.

    Ninguno de estos indicadores depende del costo: `P = 1 000 000`,
    `V = 500 000`, `H = 27.5`, `T = 7.5`, y 400 000 vendidos en agosto de 2025.
    """
    _escenario_pereira(sesion)
    _venta_anio_anterior(sesion, SIN_COSTO, "400000")

    fila = _fila(sesion, SIN_COSTO)

    assert fila.cumplimiento == D("0.5000")
    assert fila.ideal == D("0.2727"), "7.5 / 27.5"
    assert fila.brecha == D("0.5000") - D("0.2727")
    assert fila.semaforo is Semaforo.VERDE
    assert fila.venta_diaria_promedio == D("66666.67"), "500 000 / 7.5"
    assert fila.proyeccion == D("1833333.33"), "el promedio diario exacto x 27.5"
    assert fila.cumplimiento_proyectado == D("1.8333")
    assert fila.venta_diaria_requerida == D("25000.00"), "(1 000 000 - 500 000) / 20 días"
    assert fila.crecimiento == D("0.2500"), "500 000 contra 400 000 del año anterior"
    assert fila.venta == D("500000.00"), "la venta se carga entera; no se descarta nada"


def test_un_conjunto_con_el_costo_completo_da_el_margen_de_siempre(
    sesion: Session, estructura: None
) -> None:
    """La regla no toca el caso normal: 10 000 vendidos con 6 000 de costo."""
    dar_presupuesto(sesion, CON_COSTO, "RES", "20000")
    dar_venta(sesion, CON_COSTO, "RES", 5, valor="6000", costo="3600")
    dar_venta(sesion, CON_COSTO, "RES", 6, valor="4000", costo="2400")

    fila = _fila(sesion, CON_COSTO)

    assert fila.margen_valor == D("4000.00")
    assert fila.margen_porcentaje == D("0.4000")


def test_un_costo_de_cero_declarado_sigue_dando_margen(sesion: Session, estructura: None) -> None:
    """`0` es un dato y `NULL` es su ausencia; solo el segundo anula el margen.

    Sin esta distinción, la corrección se comería el margen de cualquier venta
    regalada o de cualquier ajuste a costo cero, que sí son calculables.
    """
    dar_presupuesto(sesion, CON_COSTO, "RES", "20000")
    dar_venta(sesion, CON_COSTO, "RES", 5, valor="10000", costo="0")

    assert _fila(sesion, CON_COSTO).margen_porcentaje == D("1.0000")


def test_una_sola_linea_sin_costo_anula_el_margen_de_todo_el_conjunto(
    sesion: Session, estructura: None
) -> None:
    """No se calcula el margen «sobre las líneas que sí tienen costo».

    Ese cálculo daría `0.4000` —un número que parece completo y no lo es—
    ignorando 90 000 de venta cuyo costo nadie conoce. La regla es al revés:
    cualquier línea sin costo deja el conjunto sin margen.
    """
    dar_presupuesto(sesion, CON_COSTO, "RES", "200000")
    dar_venta(sesion, CON_COSTO, "RES", 5, valor="10000", costo="6000")
    dar_venta(sesion, CON_COSTO, "RES", 6, valor="90000", costo=None)

    fila = _fila(sesion, CON_COSTO)

    assert fila.margen_porcentaje != D("0.4000"), (
        "se está publicando el margen de las líneas con costo como si fuera el del conjunto"
    )
    assert fila.margen_porcentaje is None
    assert fila.venta == D("100000.00"), "la venta sin costo sigue contando como venta"


def test_el_consolidado_pierde_el_margen_mientras_pereira_no_traiga_costo(
    sesion: Session, estructura: None
) -> None:
    """Consecuencia deliberada de la regla, y la que crea la presión sobre la API.

    El consolidado de la compañía incluye a PEREIRA: si PEREIRA no tiene costo,
    el margen de la compañía no se puede calcular. Lo que **no** se pierde es
    nada más: la venta, el presupuesto y el cumplimiento del consolidado siguen
    completos, y el margen del resto de los puntos sigue publicándose.
    """
    dar_presupuesto(sesion, CON_COSTO, "RES", "20000")
    dar_venta(sesion, CON_COSTO, "RES", 5, valor="10000", costo="6000")
    _escenario_pereira(sesion)

    con_pereira = _tablero(sesion, CON_COSTO, SIN_COSTO).consolidado
    sin_pereira = _tablero(sesion, CON_COSTO).consolidado

    assert con_pereira.margen_porcentaje is None, "el margen de la compañía no es calculable"
    assert con_pereira.venta == D("510000.00"), "la venta consolidada no pierde nada"
    assert con_pereira.cumplimiento == D("0.5000"), "510 000 / 1 020 000"

    assert sin_pereira.margen_porcentaje == D("0.4000"), (
        "sin PEREIRA dentro, el margen del resto de la compañía se calcula igual que siempre"
    )


def test_el_grupo_sin_pereira_conserva_su_margen(sesion: Session, estructura: None) -> None:
    """El contagio llega hasta donde llega el conjunto, ni una fila más.

    PEREIRA es del GRUPO 2 y MALAMBO del GRUPO 1: el tablero publica el margen
    del 1 y deja en «—» el del 2.
    """
    dar_presupuesto(sesion, CON_COSTO, "RES", "20000")
    dar_venta(sesion, CON_COSTO, "RES", 5, valor="10000", costo="6000")
    _escenario_pereira(sesion)

    por_grupo = {g.codigo: g for g in _tablero(sesion, CON_COSTO, SIN_COSTO).grupos}

    assert por_grupo["001"].margen_porcentaje == D("0.4000"), "el grupo de MALAMBO calcula igual"
    assert por_grupo["002"].margen_porcentaje is None, "el grupo de PEREIRA, no"


def test_el_reporte_de_clientes_tampoco_inventa_el_margen(
    sesion: Session, estructura: None
) -> None:
    """La regla vale en todas las pantallas, no solo en el cumplimiento."""
    dar_presupuesto(sesion, SIN_COSTO, "RES", "1000000")
    dar_venta(sesion, SIN_COSTO, "RES", 5, valor="500000", costo=None)

    respuesta = ReportesService(sesion).clientes(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, alcance=[id_punto_venta(sesion, SIN_COSTO)]),
        AgrupacionClientes.CLIENTE,
    )

    assert len(respuesta.filas) == 1
    assert respuesta.filas[0].margen_porcentaje is None
    assert respuesta.filas[0].venta == D("500000.00")


# ── Ayuda: historia del año anterior ──────────────────────────────────────────


def _venta_anio_anterior(sesion: Session, codigo_co: str, valor: str) -> None:
    from app.application.services.periodos import obtener_o_crear_periodo

    periodo = obtener_o_crear_periodo(sesion, "2025-08")
    sesion.add(
        VentaLinea(
            periodo_id=periodo.id,
            fecha=date(2025, 8, 5),
            punto_venta_id=id_punto_venta(sesion, codigo_co),
            categoria_id=id_categoria(sesion, "RES"),
            valor_subtotal=D(valor),
            costo_promedio=D(0),
            cantidad_inv=D(0),
        )
    )
    sesion.commit()
