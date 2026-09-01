"""La serie anual: doce meses en una respuesta, y el total que no promedia.

Es el único reporte agropecuario que cruza de período, y cruzar trae dos riesgos
que no existen cuando se mide dentro de un mes. Los dos se fijan aquí:

**1. El corte tiene que aplicarse una sola vez y al año entero.** Un corte por
mes mal resuelto recorta también los meses ya cerrados, y entonces el año que
sale por pantalla es más bajo que el año real sin que nada falle.

**2. El total del año no es el promedio de los doce cumplimientos.** Promediarlos
le da el mismo peso a un enero de mil millones que a un diciembre de cien, y el
número resultante no es el cumplimiento de nada (§7). El total recalcula sobre
las sumas, igual que cualquier otro nivel del sistema.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.application.services.agro_presupuesto_service import AgroPresupuestoService
from app.application.services.agro_reportes_service import AgroReportesService
from app.application.services.periodos import obtener_o_crear_periodo
from app.infrastructure.models.agro_dimensiones import AgroDimension
from app.infrastructure.models.agro_presupuesto import AgroCalendario
from app.infrastructure.models.agro_venta import AgroVentaLinea
from app.infrastructure.models.agro_vocabulario import (
    DimensionPresupuesto,
    EjeResumen,
    TipoDimension,
)

D = Decimal

ANIO = 2026
PLANTA, MONTERIA = "301", "302"

#: El corte cae dentro de agosto a propósito: junio y julio quedan cerrados y
#: agosto a medias. Es la única forma de que la prueba distinga «se aplicó el
#: corte al año entero» de «se aplicó el corte a cada mes».
CORTE = date(ANIO, 8, 20)

#: Las metas **cambian de mes a mes** y no por adorno: con la misma meta los tres
#: meses, el promedio de los cumplimientos coincide con el cumplimiento de las
#: sumas y la prueba del total pasaría sin comprobar nada.
METAS_PLANTA = {6: "1000", 7: "2000", 8: "4000"}
KILOS_PLANTA = {6: "10", 7: "20", 8: "40"}

#: Dimensiones que la línea exige y que esta prueba no mira. `agro_venta_lineas`
#: las tiene todas obligatorias para que ningún cruce pueda perder una fila.
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
def anio_con_tres_meses(sesion: Session) -> Session:
    """Junio, julio y agosto de 2026, con meta en los tres.

    Planta vende lo mismo los tres meses —mil— contra metas que suben, así que
    sus tres cumplimientos son 100 %, 50 % y 25 %. Montería tiene meta y **no
    vende nada**: es la fila que un reporte que solo mire la venta perdería.

    Se añaden dos filas que no deben aparecer: una de impuesto en junio y una
    venta de agosto **posterior al corte**.
    """
    accesorias = {tipo: _miembro(sesion, tipo, "SIN_DATO", "SIN DATO") for tipo in _ACCESORIAS}
    planta = _miembro(sesion, TipoDimension.CENTRO_OPERACION, PLANTA, "PLANTA")
    monteria = _miembro(sesion, TipoDimension.CENTRO_OPERACION, MONTERIA, "MONTERIA")
    presupuesto = AgroPresupuestoService(sesion)

    def vender(
        periodo_id: int,
        centro: AgroDimension,
        cuando: date,
        neto: str,
        kilos: str,
        *,
        impuesto: bool = False,
    ) -> None:
        sesion.add(
            AgroVentaLinea(
                periodo_id=periodo_id,
                fecha=cuando,
                centro_id=centro.id,
                tipo_item_id=accesorias[TipoDimension.TIPO_ITEM].id,
                especie_id=accesorias[TipoDimension.ESPECIE].id,
                tipo_comercial_id=accesorias[TipoDimension.TIPO_COMERCIAL].id,
                grupo_id=accesorias[TipoDimension.GRUPO].id,
                vendedor_id=accesorias[TipoDimension.VENDEDOR].id,
                cliente_id=accesorias[TipoDimension.CLIENTE].id,
                item_id=accesorias[TipoDimension.ITEM].id,
                valor_bruto=D(neto),
                descuentos=D("0"),
                valor_subtotal=D(neto),
                total_neto=D(neto),
                total_costo=D("0"),
                kilos_total=D(kilos),
                cantidad_inv=D("1"),
                lineas_facturadas=1,
                es_impuesto=impuesto,
            )
        )

    for mes in (6, 7, 8):
        codigo = f"{ANIO}-{mes:02d}"
        periodo = obtener_o_crear_periodo(sesion, codigo)
        vender(periodo.id, planta, date(ANIO, mes, 5), "1000", "5")
        presupuesto.guardar(
            codigo_periodo=codigo,
            dimension=DimensionPresupuesto.CENTRO_OPERACION,
            clave=PLANTA,
            monto=D(METAS_PLANTA[mes]),
            kilos=D(KILOS_PLANTA[mes]),
            motivo="Meta inicial de la prueba",
        )
        presupuesto.guardar(
            codigo_periodo=codigo,
            dimension=DimensionPresupuesto.CENTRO_OPERACION,
            clave=MONTERIA,
            monto=D("500"),
            kilos=D("5"),
            motivo="Meta inicial de la prueba",
        )

    junio = obtener_o_crear_periodo(sesion, f"{ANIO}-06")
    agosto = obtener_o_crear_periodo(sesion, f"{ANIO}-08")
    vender(junio.id, planta, date(ANIO, 6, 9), "99999", "999", impuesto=True)
    vender(agosto.id, planta, date(ANIO, 8, 25), "88888", "888")

    sesion.flush()
    assert monteria.id is not None
    return sesion


def _serie(sesion: Session, centros: tuple[str, ...] | None = None):
    return AgroReportesService(sesion).serie_mensual(
        ANIO, EjeResumen.CENTRO_OPERACION, centros=centros, hasta=CORTE
    )


def _fila(respuesta, clave: str):
    return next(fila for fila in respuesta.filas if fila.clave == clave)


def test_la_serie_publica_los_doce_meses_aunque_solo_existan_tres(
    anio_con_tres_meses: Session,
) -> None:
    """Doce columnas siempre, y `abierto` diciendo cuáles existen.

    Una rejilla anual que unos años trae doce columnas y otros ocho se lee como
    una rejilla rota. Los meses sin período salen en cero **y marcados**, que es
    otra cosa que un mes abierto sin venta.
    """
    respuesta = _serie(anio_con_tres_meses)

    assert respuesta.periodos == [f"{ANIO}-{mes:02d}" for mes in range(1, 13)]

    planta = _fila(respuesta, PLANTA)
    assert len(planta.meses) == 12
    assert [mes.mes for mes in planta.meses] == list(range(1, 13))
    assert [mes.abierto for mes in planta.meses] == [
        False, False, False, False, False, True, True, True, False, False, False, False
    ]  # fmt: skip

    enero = planta.meses[0]
    assert enero.venta_valor == D("0.00")
    assert enero.presupuesto is None
    assert enero.cumplimiento is None


def test_el_corte_deja_completos_los_meses_cerrados_y_recorta_el_mes_en_curso(
    anio_con_tres_meses: Session,
) -> None:
    """El corte se aplica al año, una vez.

    Junio y julio salen completos aunque el corte esté en agosto; la venta del
    25 de agosto, posterior al corte, no entra. Si el corte se aplicara mes a
    mes con la fecha global sin saturar, junio y julio saldrían vacíos.
    """
    planta = _fila(_serie(anio_con_tres_meses), PLANTA)

    assert planta.meses[5].venta_valor == D("1000.00")
    assert planta.meses[6].venta_valor == D("1000.00")
    assert planta.meses[7].venta_valor == D("1000.00")
    assert planta.total.venta_valor == D("3000.00")


def test_el_impuesto_no_entra_en_ningun_mes(anio_con_tres_meses: Session) -> None:
    """La regla 1 del servicio, también cuando la consulta abarca doce meses.

    La agregación anual no pasa por `_filtros_base` —su `WHERE` es de un solo
    período— y por eso hay que fijar aquí que no se le olvidó el impuesto: son
    99.999 pesos de recaudo de terceros esperando a colarse como venta de junio.
    """
    planta = _fila(_serie(anio_con_tres_meses), PLANTA)

    assert planta.meses[5].venta_valor == D("1000.00")
    assert planta.meses[5].kilos == D("5.000")


def test_el_total_del_anio_recalcula_el_cumplimiento_sobre_las_sumas(
    anio_con_tres_meses: Session,
) -> None:
    """`Σ V / Σ P`, no el promedio de los doce cumplimientos.

    Los tres meses cumplen 100 %, 50 % y 25 %, cuyo promedio es 58,33 %. El
    cumplimiento del año es 3.000 / 7.000 = 42,86 %. Quince puntos de diferencia
    entre el número correcto y el que sale de promediar ratios.
    """
    planta = _fila(_serie(anio_con_tres_meses), PLANTA)

    assert planta.meses[5].cumplimiento == D("1.0000")
    assert planta.meses[6].cumplimiento == D("0.5000")
    assert planta.meses[7].cumplimiento == D("0.2500")

    assert planta.total.mes == 0
    assert planta.total.periodo == str(ANIO)
    assert planta.total.presupuesto == D("7000.00")
    assert planta.total.cumplimiento == D("0.4286")


def test_la_serie_publica_pesos_y_kilos_en_la_misma_respuesta(
    anio_con_tres_meses: Session,
) -> None:
    """Las dos medidas juntas, para no casar dos listas de doce por índice."""
    planta = _fila(_serie(anio_con_tres_meses), PLANTA)

    assert planta.total.venta_valor == D("3000.00")
    assert planta.total.kilos == D("15.000")
    assert planta.total.presupuesto_kilos == D("70.000")
    # 15 / 70 = 0,2143. Distinto del cumplimiento en pesos: un mes puede cumplir
    # en pesos y no en kilos, y eso es justo lo que la gerencia mira.
    assert planta.total.cumplimiento_kilos == D("0.2143")
    assert planta.total.cumplimiento == D("0.4286")


def test_un_centro_presupuestado_sin_venta_sigue_siendo_fila(
    anio_con_tres_meses: Session,
) -> None:
    """El peor caso del reporte no puede ser el que desaparece.

    Montería tiene meta los tres meses y no vendió nada. Una fila armada solo
    con los miembros que aparecen en la venta la dejaría fuera justo cuando hay
    que mirarla.
    """
    monteria = _fila(_serie(anio_con_tres_meses), MONTERIA)

    assert monteria.total.venta_valor == D("0.00")
    assert monteria.total.presupuesto == D("1500.00")
    assert monteria.total.cumplimiento == D("0.0000")


def test_el_consolidado_suma_la_venta_y_la_meta_de_los_dos_centros(
    anio_con_tres_meses: Session,
) -> None:
    """El total del año: 3.000 vendidos contra 8.500 de meta."""
    respuesta = _serie(anio_con_tres_meses)

    assert respuesta.totales.total.venta_valor == D("3000.00")
    assert respuesta.totales.total.presupuesto == D("8500.00")
    assert respuesta.totales.total.cumplimiento == D("0.3529")
    assert respuesta.totales.total.diferencia == D("-5500.00")


def test_el_filtro_de_centro_recorta_tambien_la_meta_del_consolidado(
    anio_con_tres_meses: Session,
) -> None:
    """Misma regla que en el resumen: el filtro estrecha el denominador.

    Con Planta a la vista, la meta del consolidado tiene que ser la de Planta
    —7.000— y no la de los dos centros. Sumando la de Montería, el cumplimiento
    del año caería de 42,86 % a 35,29 % por un filtro de pantalla.
    """
    respuesta = _serie(anio_con_tres_meses, (PLANTA,))

    assert [fila.clave for fila in respuesta.filas] == [PLANTA]
    assert respuesta.totales.total.presupuesto == D("7000.00")
    assert respuesta.totales.total.cumplimiento == D("0.4286")


def test_un_mes_abierto_sin_meta_deja_vacia_la_del_anio(
    anio_con_tres_meses: Session, sesion: Session
) -> None:
    """Sumar solo los meses con meta publicaría un año más barato que el real.

    Con mayo abierto y sin presupuesto, el año de Planta ya no tiene meta
    completa. Sumar los tres meses que sí la tienen daría 7.000 con pinta de ser
    el año entero, y un cumplimiento del 42,86 % contra una meta que le falta un
    mes. Vacío dice lo que pasa; el 42,86 % lo esconde.
    """
    obtener_o_crear_periodo(sesion, f"{ANIO}-05")
    sesion.flush()

    planta = _fila(_serie(anio_con_tres_meses), PLANTA)

    assert planta.meses[4].abierto is True
    assert planta.meses[4].presupuesto is None
    # Los meses que sí tienen meta la conservan: lo que se rinde es el año.
    assert planta.meses[5].presupuesto == D("1000.00")
    assert planta.total.venta_valor == D("3000.00")
    assert planta.total.presupuesto is None
    assert planta.total.cumplimiento is None


def test_sin_calendario_no_hay_proyeccion_y_con_el_si(
    anio_con_tres_meses: Session, sesion: Session
) -> None:
    """La proyección depende del calendario, y el año la exige en cada mes.

    Sin días hábiles no hay `H` con el que proyectar y la columna sale vacía, que
    es cierto. Cargando el calendario de los tres meses aparece. Un año al que
    le falte el calendario de un mes abierto tampoco proyecta: sumar solo los
    meses con `H` daría un año más corto con pinta de completo.
    """
    planta = _fila(_serie(anio_con_tres_meses), PLANTA)
    assert planta.meses[7].proyeccion is None
    assert planta.total.proyeccion is None

    centro = sesion.execute(
        AgroDimension.__table__.select().where(AgroDimension.clave == PLANTA)
    ).one()
    for mes in (6, 7, 8):
        periodo = obtener_o_crear_periodo(sesion, f"{ANIO}-{mes:02d}")
        sesion.add(AgroCalendario(periodo_id=periodo.id, centro_id=centro.id, dias_habiles=D("20")))
    sesion.flush()

    planta = _fila(_serie(anio_con_tres_meses), PLANTA)
    assert planta.meses[7].proyeccion is not None
    assert planta.total.proyeccion is not None
