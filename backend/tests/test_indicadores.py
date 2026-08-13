"""Los indicadores de §4: funciones puras, sin base de datos.

Es la suite que más importa. Aquí viven las reglas que el Excel actual tiene
mal, y cada caso borde de esta lista es un número que hoy alguien podría estar
leyendo equivocado en una reunión de gerencia.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain import indicadores as ind
from app.domain.enums import Semaforo
from app.domain.semaforo import UmbralesSemaforo, evaluar_semaforo

D = Decimal
UMBRALES = UmbralesSemaforo()


# ── División protegida: la regla que gobierna todo el módulo ──────────────────


@pytest.mark.parametrize(
    ("numerador", "denominador"),
    [
        (D(10), D(0)),  # denominador cero
        (None, D(10)),  # falta el numerador
        (D(10), None),  # falta el denominador
        (None, None),
    ],
)
def test_dividir_devuelve_none_y_nunca_explota(
    numerador: Decimal | None, denominador: Decimal | None
) -> None:
    assert ind.dividir(numerador, denominador) is None


def test_dividir_no_devuelve_cero_cuando_no_se_puede_calcular() -> None:
    """`None` y `0` son afirmaciones distintas.

    `0` dice «vendió nada»; `None` dice «no se puede calcular». Confundirlas es
    el defecto que hoy tiene el Excel.
    """
    resultado = ind.dividir(D(10), D(0))
    assert resultado is not ind.CERO
    assert resultado is None


# ── §4.1 Cumplimiento ─────────────────────────────────────────────────────────


def test_cumplimiento_replica_el_dato_real_de_malambo() -> None:
    """PPTO 618 882 592 y venta 181 285 044 → 29.29 % (fila real del Excel)."""
    resultado = ind.cumplimiento(D("181285044"), D("618882592"))
    assert resultado is not None
    assert ind.redondear_porcentaje(resultado) == D("0.2929")


def test_cumplimiento_sin_presupuesto_es_none() -> None:
    """432 EVENTOS BUCARAMANGA vende y no está presupuestado (§3.1)."""
    assert ind.cumplimiento(D("5000000"), None) is None


def test_ideal_admite_media_jornada() -> None:
    """7.5 días trabajados sobre 27.5 hábiles = 27.27 %, el `IDEAL` del Excel."""
    resultado = ind.ideal(D("7.5"), D("27.5"))
    assert resultado is not None
    assert ind.redondear_porcentaje(resultado) == D("0.2727")


def test_brecha_es_none_si_falta_cualquiera_de_los_dos() -> None:
    assert ind.brecha(D("0.30"), None) is None
    assert ind.brecha(None, D("0.27")) is None


def test_brecha_positiva_cuando_va_por_encima_del_ideal() -> None:
    assert ind.brecha(D("0.30"), D("0.27")) == D("0.03")


# ── §4.2 Proyección y venta diaria requerida ──────────────────────────────────


def test_venta_diaria_promedio_es_none_el_primer_dia_del_mes() -> None:
    """Con `T = 0` no hay promedio. Decir «vende 0 al día» sería falso."""
    assert ind.venta_diaria_promedio(D("1000"), D(0)) is None


def test_proyeccion_es_el_ritmo_actual_extendido_al_mes() -> None:
    promedio = ind.venta_diaria_promedio(D("181285044"), D("7.5"))
    assert promedio is not None
    resultado = ind.proyeccion(promedio, D("27.5"))
    assert resultado is not None
    assert ind.redondear(resultado, 2) == D("664711828.00")


def test_venta_diaria_requerida_reparte_el_faltante() -> None:
    """(P − V) / (H − T): 20 días quedan, 437 597 548 por vender."""
    resultado = ind.venta_diaria_requerida(D("618882592"), D("181285044"), D("27.5"), D("7.5"))
    assert resultado is not None
    assert ind.redondear(resultado, 2) == D("21879877.40")


def test_venta_diaria_requerida_es_cero_si_ya_cumplio() -> None:
    """`V ≥ P` se evalúa antes que nada: no queda nada por vender."""
    assert ind.venta_diaria_requerida(D("100"), D("150"), D("27.5"), D("7.5")) == ind.CERO


def test_venta_diaria_requerida_es_cero_incluso_con_el_mes_terminado() -> None:
    """Cumplir el presupuesto es cierto aunque ya no queden días hábiles."""
    assert ind.venta_diaria_requerida(D("100"), D("150"), D("27.5"), D("27.5")) == ind.CERO


def test_venta_diaria_requerida_es_none_si_no_quedan_dias() -> None:
    """`H = T` con presupuesto sin cubrir: no hay entre cuántos días repartir."""
    assert ind.venta_diaria_requerida(D("618882592"), D("100"), D("27.5"), D("27.5")) is None


def test_venta_diaria_requerida_es_none_con_calendario_incoherente() -> None:
    """`H < T` es un calendario mal parametrizado.

    Un requerido negativo sería peor que un vacío: se leería como «puede dejar
    de vender», que es exactamente lo contrario de lo que pasa.
    """
    assert ind.venta_diaria_requerida(D("618882592"), D("100"), D("20"), D("27.5")) is None


# ── §4.3 Crecimiento ──────────────────────────────────────────────────────────


def test_crecimiento_contra_el_anio_anterior() -> None:
    resultado = ind.crecimiento(D("946010421"), D("2742973374.7087736"))
    assert resultado is not None
    assert ind.redondear_porcentaje(resultado) == D("-0.6551")


def test_crecimiento_sin_historia_es_none_no_cero() -> None:
    """Sin 2025 cargado el indicador viaja vacío (§4.3).

    Un `0 %` afirmaría que se vendió lo mismo que el año pasado, y eso no es lo
    que sabemos cuando simplemente no hay dato.
    """
    assert ind.crecimiento(D("946010421"), None) is None
    assert ind.crecimiento(D("946010421"), D(0)) is None


# ── §4.4 Margen ───────────────────────────────────────────────────────────────


def test_margen_se_pondera_sobre_los_totales() -> None:
    """Dos líneas de tamaño muy distinto: 1000 al 50 % y 9000 al 10 %.

    El promedio simple de los porcentajes daría 30 %. El ponderado da 14 %, que
    es el único número cierto. Por eso §4.4 prohíbe promediar el `MARGEN` que
    envía SIESA línea a línea.
    """
    venta = D("10000")
    costo = D("500") + D("8100")  # 50 % de 1000 + 90 % de 9000
    resultado = ind.margen_porcentaje(venta, costo)
    assert resultado is not None
    assert ind.redondear_porcentaje(resultado) == D("0.1400")


def test_margen_es_none_sin_venta() -> None:
    assert ind.margen_porcentaje(D(0), D(0)) is None


def test_margen_es_none_si_alguna_linea_del_conjunto_no_tiene_costo() -> None:
    """§4.4: sin el costo de una sola línea, el conjunto no tiene margen.

    Es el caso de PEREIRA, cuyo endpoint no entrega el costo. Con la columna
    sumada tal cual —las líneas sin costo aportando cero— el resultado sería
    `1.0000`, un 100 % de margen que nadie ha ganado. La afirmación correcta es
    «no se puede calcular»: `None`, y la pantalla pinta «—».
    """
    assert ind.margen_valor(D("10000"), D("6000"), costo_completo=False) is None
    assert ind.margen_porcentaje(D("10000"), D("6000"), costo_completo=False) is None
    # Y no se calcula sobre «las líneas que sí tienen costo»: eso daría 0.4000,
    # un porcentaje que parece completo y no lo es.
    assert ind.margen_porcentaje(D("10000"), D("6000")) == D("0.4")


def test_un_costo_declarado_en_cero_si_da_margen() -> None:
    """`0` es un dato; su ausencia es otra cosa. Solo la segunda anula el margen."""
    assert ind.margen_porcentaje(D("10000"), D(0)) == D(1)
    assert ind.margen_valor(D("10000"), D(0)) == D("10000")


def test_la_fila_pierde_el_margen_pero_no_el_resto_de_indicadores() -> None:
    """El costo incompleto se lleva el margen y **nada más** (§4.4).

    Cumplimiento, ideal, proyección y crecimiento no dependen del costo: para un
    punto de venta sin costo en el origen tienen que seguir publicándose.
    """
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("500000"),
            costo=D(0),
            costo_completo=False,
            presupuesto=D("1000000"),
            venta_anio_anterior=D("400000"),
            dias_habiles=D("27.5"),
            dias_trabajados=D("7.5"),
        ),
        UMBRALES,
    )

    assert resultado.margen_valor is None
    assert resultado.margen_porcentaje is None
    assert resultado.cumplimiento == D("0.5000")
    assert resultado.ideal == D("0.2727")
    assert resultado.proyeccion == D("1833333.33")
    assert resultado.crecimiento == D("0.2500")
    assert resultado.semaforo is Semaforo.VERDE


# ── Semáforo (§4.1) ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cumplimiento", "ideal", "esperado"),
    [
        (D("0.30"), D("0.27"), Semaforo.VERDE),  # por encima
        (D("0.27"), D("0.27"), Semaforo.VERDE),  # justo en el ideal
        (D("0.25"), D("0.27"), Semaforo.AMARILLO),  # entre el 90 % y el ideal
        (D("0.243"), D("0.27"), Semaforo.AMARILLO),  # exactamente el 90 %
        (D("0.20"), D("0.27"), Semaforo.ROJO),  # bajo el 90 %
        (D("0"), D("0.27"), Semaforo.ROJO),  # no vendió nada
    ],
)
def test_semaforo(cumplimiento: Decimal, ideal: Decimal, esperado: Semaforo) -> None:
    assert evaluar_semaforo(cumplimiento, ideal, UMBRALES) is esperado


def test_semaforo_sin_presupuesto_no_inventa_color() -> None:
    """Sin presupuesto no hay cumplimiento; sin calendario no hay ideal."""
    assert evaluar_semaforo(None, D("0.27"), UMBRALES) is Semaforo.SIN_PRESUPUESTO
    assert evaluar_semaforo(D("0.30"), None, UMBRALES) is Semaforo.SIN_PRESUPUESTO


def test_umbrales_rechazan_un_factor_imposible() -> None:
    with pytest.raises(ValueError, match="fracción del ideal"):
        UmbralesSemaforo(factor_amarillo=D("1.5"))


def test_umbrales_configurables_cambian_el_color() -> None:
    """Los umbrales son parámetro del sistema, no constante del código (§4.1)."""
    estricto = UmbralesSemaforo(factor_amarillo=D("0.99"))
    assert evaluar_semaforo(D("0.25"), D("0.27"), UMBRALES) is Semaforo.AMARILLO
    assert evaluar_semaforo(D("0.25"), D("0.27"), estricto) is Semaforo.ROJO


# ── Fila completa ─────────────────────────────────────────────────────────────


def test_fila_completa_con_los_datos_reales_de_malambo() -> None:
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("181285044"),
            costo=D("127500000"),
            presupuesto=D("618882592"),
            dias_habiles=D("27.5"),
            dias_trabajados=D("7.5"),
        ),
        UMBRALES,
    )

    assert resultado.cumplimiento == D("0.2929")
    assert resultado.ideal == D("0.2727")
    assert resultado.brecha == D("0.0202")
    assert resultado.semaforo is Semaforo.VERDE
    assert resultado.proyeccion == D("664711828.00")
    assert resultado.venta_diaria_requerida == D("21879877.40")
    # Sin historia cargada, el crecimiento va vacío, no en cero.
    assert resultado.crecimiento is None
    # Los parámetros del cálculo viajan con el resultado para poder verificarlo
    # a mano (§4.2).
    assert resultado.dias_habiles == D("27.5")
    assert resultado.dias_trabajados == D("7.5")


def test_fila_de_punto_sin_presupuesto_no_rompe_nada() -> None:
    """432 EVENTOS BUCARAMANGA: vende, no tiene presupuesto, y no descuadra."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("5000000"),
            costo=D("3000000"),
            presupuesto=None,
            dias_habiles=D("28"),
            dias_trabajados=D("9"),
        ),
        UMBRALES,
    )

    assert resultado.venta == D("5000000.00")
    assert resultado.presupuesto is None
    assert resultado.cumplimiento is None
    assert resultado.venta_diaria_requerida is None
    assert resultado.semaforo is Semaforo.SIN_PRESUPUESTO
    # El margen sí se puede calcular: no depende del presupuesto.
    assert resultado.margen_porcentaje == D("0.4000")


def test_fila_sin_calendario_cargado() -> None:
    """Sin días hábiles no hay ideal ni proyección, pero sí cumplimiento."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(venta=D("100"), costo=D("60"), presupuesto=D("400")),
        UMBRALES,
    )

    assert resultado.cumplimiento == D("0.2500")
    assert resultado.ideal is None
    assert resultado.brecha is None
    assert resultado.proyeccion is None
    assert resultado.venta_diaria_promedio is None
    assert resultado.semaforo is Semaforo.SIN_PRESUPUESTO


def test_la_proyeccion_no_arrastra_error_de_redondeo() -> None:
    """El promedio diario se multiplica por `H` **sin redondear** antes.

    Redondear el promedio antes de extenderlo al mes mete un error de hasta
    28 pesos por punto de venta, y luego nadie entiende por qué el consolidado
    no cuadra con la suma de sus filas.
    """
    insumos = ind.InsumosIndicadores(
        venta=D("100"), costo=D(0), presupuesto=D("1000"), dias_habiles=D(3), dias_trabajados=D(3)
    )
    resultado = ind.calcular_indicadores(insumos, UMBRALES)
    # 100/3 = 33.333... × 3 = 100 exacto. Redondeando el promedio a 33.33 daría
    # 99.99 y la proyección no cuadraría con la venta ya realizada.
    assert resultado.proyeccion == D("100.00")


def test_venta_en_cero_se_reporta_con_la_escala_del_contrato() -> None:
    """PEREIRA/EMBUTIDOS tiene venta 0 en el archivo real: debe salir `0.00`."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D(0),
            costo=D(0),
            presupuesto=D("83882933.47"),
            dias_habiles=D("27.5"),
            dias_trabajados=D("7.5"),
        ),
        UMBRALES,
    )
    assert str(resultado.venta) == "0.00"
    assert resultado.cumplimiento == D("0.0000")
    assert resultado.semaforo is Semaforo.ROJO


def test_kilos_usan_tres_decimales_y_el_margen_sigue_en_pesos() -> None:
    """En modo kilos el margen se pondera sobre la venta en pesos (§4.5)."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("64857.0689"),  # kilos vendidos
            costo=D("120000000"),
            presupuesto=D("194475.894"),
            venta_valor=D("181285044"),  # la venta en pesos, para el margen
            dias_habiles=D("27.5"),
            dias_trabajados=D("7.5"),
        ),
        UMBRALES,
        decimales_medida=3,
    )
    assert str(resultado.venta) == "64857.069"
    assert resultado.margen_porcentaje == D("0.3381")
