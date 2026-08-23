"""El filtro `centro` tiene que llegar tambien al denominador del cumplimiento.

Es el mismo control que en carnes fija `test_reportes_filtro_multipdv`, y la
pregunta que hay que hacerle es la misma: cuando la pantalla se filtra a un
centro, ¿contra que meta se esta midiendo la venta que se ensena?

Si el filtro recorta la venta pero no el presupuesto, el consolidado compara la
venta de un centro contra la meta de todos. El numero que sale no es un error
visible: es un cumplimiento mas bajo, con toda la pinta de ser cierto, que
ademas **se contradice con la fila que tiene justo debajo** —esa si sale bien—.
Nadie mira dos veces un cumplimiento bajo en agosto.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.application.services.agro_presupuesto_service import AgroPresupuestoService
from app.application.services.agro_reportes_service import AgroReportesService, FiltrosAgro
from app.application.services.periodos import obtener_o_crear_periodo
from app.domain.enums import Medida, Semaforo
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import (
    DimensionPresupuesto,
    EjeResumen,
    TipoDimension,
)
from tests.conftest import PERIODO

ANIO, MES = (int(parte) for parte in PERIODO.split("-"))

#: Los dos centros reales de la unidad, con la desproporcion real entre ellos:
#: Planta presupuesta cuatro veces lo de Monteria. Esa desproporcion es la que
#: hace visible el fallo —con dos centros iguales, el error se nota la mitad—.
PLANTA, MONTERIA = "301", "302"

#: Dimensiones que la linea de venta exige y que esta prueba no mira. Se crean
#: una vez y se reutilizan: `agro_venta_lineas` las tiene todas obligatorias a
#: proposito, para que ningun cruce pueda perder una fila.
_ACCESORIAS = (
    TipoDimension.TIPO_ITEM,
    TipoDimension.ESPECIE,
    TipoDimension.TIPO_COMERCIAL,
    TipoDimension.GRUPO,
    TipoDimension.VENDEDOR,
    TipoDimension.CLIENTE,
    TipoDimension.ITEM,
)


def _miembro(sesion: Session, tipo: TipoDimension, clave: str, nombre: str) -> AgroDimension:
    fila = AgroDimension(tipo=tipo.value, clave=clave, nombre=nombre)
    sesion.add(fila)
    sesion.flush()
    return fila


@pytest.fixture
def dos_centros(sesion: Session) -> Session:
    """Planta y Monteria, cada uno con su meta y su venta.

    Planta va al 50 % de su meta y Monteria al 40 %: dos cumplimientos distintos
    y los dos distintos del que saldria de mezclar las metas, para que ninguna
    asercion pueda pasar por casualidad.
    """
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    accesorias = {tipo: _miembro(sesion, tipo, "SIN_DATO", "SIN DATO") for tipo in _ACCESORIAS}

    presupuesto = AgroPresupuestoService(sesion)
    for clave, nombre, meta, venta in (
        (PLANTA, "PLANTA", "2000", "1000"),
        (MONTERIA, "MONTERIA", "500", "200"),
    ):
        centro = _miembro(sesion, TipoDimension.CENTRO_OPERACION, clave, nombre)
        sesion.add(
            AgroVentaLinea(
                periodo_id=periodo.id,
                fecha=date(ANIO, MES, 5),
                centro_id=centro.id,
                tipo_item_id=accesorias[TipoDimension.TIPO_ITEM].id,
                especie_id=accesorias[TipoDimension.ESPECIE].id,
                tipo_comercial_id=accesorias[TipoDimension.TIPO_COMERCIAL].id,
                grupo_id=accesorias[TipoDimension.GRUPO].id,
                vendedor_id=accesorias[TipoDimension.VENDEDOR].id,
                cliente_id=accesorias[TipoDimension.CLIENTE].id,
                item_id=accesorias[TipoDimension.ITEM].id,
                valor_bruto=Decimal(venta),
                descuentos=Decimal("0"),
                valor_subtotal=Decimal(venta),
                total_neto=Decimal(venta),
                total_costo=Decimal("0"),
                kilos_total=Decimal("10"),
                cantidad_inv=Decimal("10"),
                lineas_facturadas=1,
                es_impuesto=False,
            )
        )
        presupuesto.guardar(
            codigo_periodo=PERIODO,
            dimension=DimensionPresupuesto.CENTRO_OPERACION,
            clave=clave,
            monto=Decimal(meta),
            kilos=Decimal("100"),
            motivo="Meta inicial de la prueba",
        )
    sesion.flush()
    return sesion


def _resumen(sesion: Session, centros: tuple[str, ...] | None):
    filtros = FiltrosAgro(
        periodo=PERIODO,
        hasta=date(ANIO, MES, 28),
        centros=centros,
        medida=Medida.VALOR,
    )
    return AgroReportesService(sesion).resumen(filtros, EjeResumen.CENTRO_OPERACION)


def test_el_presupuesto_del_consolidado_se_limita_a_los_centros_pedidos(
    dos_centros: Session,
) -> None:
    """El denominador manda.

    Sumando la meta de Monteria, el cumplimiento de Planta sale 1000/2500 = 40 %
    en lugar de 1000/2000 = 50 %. Diez puntos de cumplimiento inventados por un
    filtro de pantalla.
    """
    respuesta = _resumen(dos_centros, (PLANTA,))

    assert respuesta.consolidado.venta == Decimal("1000.00")
    assert respuesta.consolidado.presupuesto == Decimal("2000.00")
    assert respuesta.consolidado.cumplimiento == Decimal("0.5000")


def test_el_consolidado_filtrado_no_se_contradice_con_su_unica_fila(
    dos_centros: Session,
) -> None:
    """Con un solo centro a la vista, el total **es** esa fila.

    Que difirieran era el sintoma visible del fallo, y el que hace que alguien
    lo acabe notando: la misma pantalla publicando dos cumplimientos distintos
    para la misma venta.
    """
    respuesta = _resumen(dos_centros, (MONTERIA,))

    assert len(respuesta.filas) == 1
    assert respuesta.consolidado.presupuesto == respuesta.filas[0].presupuesto
    assert respuesta.consolidado.cumplimiento == respuesta.filas[0].cumplimiento


def test_sin_filtro_el_consolidado_sigue_siendo_el_de_la_compania(dos_centros: Session) -> None:
    """La parte que nadie mira: que lo de siempre siga funcionando igual."""
    respuesta = _resumen(dos_centros, None)

    assert respuesta.consolidado.venta == Decimal("1200.00")
    assert respuesta.consolidado.presupuesto == Decimal("2500.00")


def test_un_centro_sin_meta_deja_el_cumplimiento_vacio_y_no_en_cero(
    dos_centros: Session, sesion: Session
) -> None:
    """Filtrar a un centro sin presupuesto no es «cumplio el 0 %».

    Es «no hay vara»: cumplimiento vacio y semaforo `SIN_PRESUPUESTO`. Publicar
    cero afirmaria que existe una meta y que no se vendio nada contra ella, que
    son dos afirmaciones y las dos falsas.
    """
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    _miembro(sesion, TipoDimension.CENTRO_OPERACION, "303", "SINCELEJO")
    sesion.flush()
    assert periodo is not None

    respuesta = _resumen(dos_centros, ("303",))

    assert respuesta.consolidado.presupuesto is None
    assert respuesta.consolidado.cumplimiento is None
    assert respuesta.consolidado.semaforo is Semaforo.SIN_PRESUPUESTO


def test_pedir_un_centro_que_no_existe_no_ensancha_el_presupuesto(dos_centros: Session) -> None:
    """El filtro estrecha, nunca ensancha.

    Un codigo inventado tiene que dejar la pantalla vacia, no caerse al «todos»
    y publicar el presupuesto entero de la compania sin venta contra la que
    medirlo.
    """
    respuesta = _resumen(dos_centros, ("999",))

    assert respuesta.filas == []
    assert respuesta.consolidado.venta == Decimal("0.00")
    assert respuesta.consolidado.presupuesto is None
