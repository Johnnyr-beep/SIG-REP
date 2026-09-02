"""Agregación de reportes: alcance, cuadre, días ponderados y comparabilidad.

Ocho defectos confirmados en revisión —fuga de datos por alcance, venta que se
evapora al desactivar un catálogo, consolidado que no cuadra con sus grupos,
ideal mal ponderado, ideal que cambia con la medida, días redondeados antes de
proyectar, crecimiento entre universos distintos y participación sobre el
top-N— tienen aquí su prueba de regresión. Las pruebas de `tests/revision/`
demuestran el defecto con el escenario que lo destapó; estas fijan la regla para
que no vuelva.

Los números están puestos a mano y son verificables con una calculadora: si
alguna falla, el mensaje tiene que dejar claro **cuál** de las ocho reglas se
rompió, no solo que dos decimales no coinciden.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.domain import indicadores as ind
from app.domain.enums import AgrupacionClientes, Medida
from app.domain.semaforo import UmbralesSemaforo
from app.infrastructure.models.organizacion import Grupo, PuntoVenta
from app.infrastructure.models.periodo import CalendarioZona
from app.infrastructure.models.venta import Cliente, VentaLinea
from app.schemas.reportes import RespuestaTablero
from tests.conftest import (
    PERIODO,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_periodo,
    id_punto_venta,
)

D = Decimal
UMBRALES = UmbralesSemaforo()
CORTE = date(2026, 8, 15)


# ── Ayudas ────────────────────────────────────────────────────────────────────


def _fijar_dias(sesion: Session, nombre_zona: str, habiles: str, trabajados: str) -> None:
    """Fija a mano el calendario de una zona, como hace el negocio en pantalla."""
    from app.infrastructure.models.organizacion import Zona

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


def _ids(sesion: Session, *codigos: str) -> list[int]:
    return [id_punto_venta(sesion, codigo) for codigo in codigos]


def _tablero(
    sesion: Session,
    *,
    alcance: list[int] | None = None,
    grupo: str | None = None,
    medida: Medida = Medida.VALOR,
) -> RespuestaTablero:
    """El tablero del período de pruebas, con el corte fijo en el día 15."""
    return ReportesService(sesion).tablero(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, alcance=alcance, grupo=grupo, medida=medida)
    )


# ── §4 Dominio: ideal agregado, días exactos y venta comparable ───────────────


def test_el_ideal_agregado_sustituye_a_t_sobre_h() -> None:
    """En un corte multizona el ideal no es `T / H`, y manda `ideal_agregado`.

    `T / H` = 11 / 28.05 = 0.3922 sería la media de los días; la media de los
    ideales ponderada por presupuesto es 0.3991. Son varas distintas y la
    segunda es la que corresponde: la venta esperada al corte es `Σ(P_i·ideal_i)`.
    """
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("4000000000"),
            costo=D(0),
            presupuesto=D("10000000000"),
            dias_habiles=D("28.05"),
            dias_trabajados=D("11.00"),
            ideal_agregado=D("0.3991228070175438596491228070"),
        ),
        UMBRALES,
    )

    assert resultado.ideal == D("0.3991"), "el ideal agregado no llegó al resultado"
    assert resultado.brecha == D("0.4000") - D("0.3991")


def test_sin_ideal_agregado_el_ideal_sigue_siendo_t_sobre_h() -> None:
    """Una fila de una sola zona no tiene nada que corregir: `ideal = T / H`."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("100000000"),
            costo=D(0),
            presupuesto=D("400000000"),
            dias_habiles=D("27.5"),
            dias_trabajados=D("7.5"),
        ),
        UMBRALES,
    )

    assert resultado.ideal == D("0.2727")


def test_los_dias_se_publican_redondeados_pero_proyectan_exactos() -> None:
    """El redondeo de `H` y `T` es de publicación, nunca de cálculo.

    `H = 26.66666666675` y `T = 14.0184` entran exactos: la proyección se calcula
    con ellos y solo después se publican con dos decimales. Proyectar con los
    valores ya cuantizados desviaría el cierre de mes en millones.
    """
    habiles = D("26.66666666675")
    trabajados = D("14.01842991316629563175601974")
    venta = D("3300000000")

    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=venta,
            costo=D(0),
            presupuesto=D("10000000000"),
            dias_habiles=habiles,
            dias_trabajados=trabajados,
        ),
        UMBRALES,
    )

    assert resultado.dias_habiles == D("26.67"), "H se publica con dos decimales"
    assert resultado.dias_trabajados == D("14.02")
    assert resultado.proyeccion == ((venta / trabajados) * habiles).quantize(D("0.01")), (
        "la proyección se calculó sobre días ya redondeados"
    )
    assert resultado.venta_diaria_requerida == (
        (D("10000000000") - venta) / (habiles - trabajados)
    ).quantize(D("0.01"))


def test_el_crecimiento_se_mide_sobre_la_proyeccion_comparable() -> None:
    """Los dos lados de la división hablan del mismo universo y mes completo.

    2 000 M vendidos en 2026, de los cuales 1 000 M vienen de puntos con
    historia; 1 000 M en 2025. El crecimiento de lo comparable es 0 %, no 100 %.
    """
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("2000000000"),
            costo=D(0),
            venta_comparable=D("1000000000"),
            venta_anio_anterior=D("1000000000"),
        ),
        UMBRALES,
    )

    assert resultado.crecimiento is None
    assert resultado.venta == D("2000000000.00"), "la venta publicada no se recorta"


def test_sin_venta_comparable_el_crecimiento_proyecta_la_venta_completa() -> None:
    """Cuando todo el corte es comparable, se proyecta la venta completa."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(
            venta=D("1500000000"),
            costo=D(0),
            venta_anio_anterior=D("1000000000"),
            dias_habiles=D("20"),
            dias_trabajados=D("10"),
        ),
        UMBRALES,
    )

    assert resultado.crecimiento == D("2.0000")


def test_sin_historia_el_crecimiento_es_vacio_y_no_cero() -> None:
    """§4.3: «sin 2025 cargado, el indicador se muestra vacío, nunca en cero»."""
    resultado = ind.calcular_indicadores(
        ind.InsumosIndicadores(venta=D("1500000000"), costo=D(0), venta_anio_anterior=None),
        UMBRALES,
    )

    assert resultado.crecimiento is None


# ── §7 Alcance: el bloque `sin_presupuesto` no es tierra de nadie ─────────────


def test_sin_presupuesto_respeta_el_alcance_del_usuario(sesion: Session, estructura: None) -> None:
    """Un jefe con alcance sobre MALAMBO no recibe la venta de EVENTOS (432)."""
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "100000000")
    dar_venta(sesion, "432", "RES", 5, "777777777")

    tablero = _tablero(sesion, alcance=_ids(sesion, "402"))

    assert tablero.sin_presupuesto == [], (
        "el alcance del usuario también gobierna el bloque sin_presupuesto"
    )


def test_sin_alcance_la_gerencia_si_ve_la_venta_no_presupuestada(
    sesion: Session, estructura: None
) -> None:
    """La otra mitad de la regla: sin restricción de alcance, 432 se publica.

    Filtrar por alcance no puede convertirse en descartar en silencio (§7).
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "100000000")
    dar_venta(sesion, "432", "RES", 5, "777777777")

    tablero = _tablero(sesion)

    assert [f.codigo_co for f in tablero.sin_presupuesto] == ["432"]
    assert tablero.sin_presupuesto[0].venta == D("777777777.00")


def test_sin_presupuesto_respeta_el_filtro_de_grupo(sesion: Session, estructura: None) -> None:
    """Pedir el tablero del GRUPO 1 no puede traer la venta de un punto ajeno.

    432 EVENTOS BUCARAMANGA no pertenece al GRUPO 1; publicarlo en ese corte
    metería en la pantalla venta que no es de ese grupo.
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "100000000")
    dar_venta(sesion, "432", "RES", 5, "777777777")

    del_grupo_uno = _tablero(sesion, grupo="001")

    assert del_grupo_uno.sin_presupuesto == []


# ── §7 «Nunca se descarta»: desactivar es catálogo, no filtro de reporte ─────


def test_un_punto_desactivado_sigue_sumando_en_el_consolidado(
    sesion: Session, estructura: None
) -> None:
    """Cerrar CONCORDE a mitad de mes no borra del histórico lo que ya vendió."""
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_presupuesto(sesion, "603", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "400000000")
    dar_venta(sesion, "603", "RES", 5, "500000000")

    punto = sesion.scalars(select(PuntoVenta).where(PuntoVenta.codigo_co == "603")).one()
    punto.activo = False
    sesion.commit()

    tablero = _tablero(sesion)

    assert tablero.consolidado.venta == D("900000000.00")
    assert tablero.consolidado.presupuesto == D("2000000000.00"), (
        "si la venta del punto cuenta, su presupuesto también"
    )


def test_un_punto_desactivado_y_no_presupuestado_sigue_en_el_bloque_aparte(
    sesion: Session, estructura: None
) -> None:
    """Desactivar el punto no presupuestado tampoco lo hace desaparecer."""
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "400000000")
    dar_venta(sesion, "432", "RES", 5, "500000000")

    punto = sesion.scalars(select(PuntoVenta).where(PuntoVenta.codigo_co == "432")).one()
    punto.activo = False
    sesion.commit()

    tablero = _tablero(sesion)
    publicado = D(tablero.consolidado.venta) + sum(D(f.venta) for f in tablero.sin_presupuesto)

    assert publicado == D("900000000.00"), "la venta ingerida tiene que aparecer en algún sitio"


def test_un_grupo_desactivado_conserva_su_fila_y_el_tablero_cuadra(
    sesion: Session, estructura: None
) -> None:
    """El consolidado se arma desde los puntos: si el grupo pierde su fila, no cuadra."""
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_presupuesto(sesion, "407", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "400000000")
    dar_venta(sesion, "407", "RES", 5, "600000000")

    grupo = sesion.scalars(select(Grupo).where(Grupo.codigo == "004")).one()
    grupo.activo = False
    sesion.commit()

    tablero = _tablero(sesion)

    assert "004" in [g.codigo for g in tablero.grupos]
    assert sum(D(g.venta) for g in tablero.grupos) == D(tablero.consolidado.venta)
    # Los grupos sin presupuesto parametrizado publican `null`, no cero: son los
    # que no suman nada al denominador de la compañía.
    assert sum(D(g.presupuesto) for g in tablero.grupos if g.presupuesto is not None) == D(
        tablero.consolidado.presupuesto
    )


# ── §4.1 y §4.2 Días e ideal de un corte multizona ───────────────────────────


def test_el_ideal_del_consolidado_es_la_media_ponderada_de_los_ideales(
    sesion: Session, estructura: None
) -> None:
    """`ideal = Σ(P_i × ideal_i) / Σ P_i`, no `T / H`.

        CARTAGENA (415)  H=24    T=20   ideal=0.8333   P=1 000 M
        LA43      (405)  H=28.5  T=10   ideal=0.3509   P=9 000 M

    Media de los ideales: 0.3991. Cociente de las medias (11 / 28.05): 0.3922.
    """
    _fijar_dias(sesion, "CARTAGENA", "24", "20")
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "10")
    dar_presupuesto(sesion, "415", "RES", "1000000000")
    dar_presupuesto(sesion, "405", "RES", "9000000000")
    dar_venta(sesion, "415", "RES", 15, "500000000")

    consolidado = _tablero(sesion, alcance=_ids(sesion, "415", "405")).consolidado

    esperado = (D(1000) * (D(20) / D(24)) + D(9000) * (D(10) / D("28.5"))) / D(10000)
    assert consolidado.ideal == esperado.quantize(D("0.0001"))
    assert consolidado.dias_habiles == D("28.05"), "H sigue siendo la media de los días hábiles"
    assert consolidado.dias_trabajados == D("11.00")


def test_el_ideal_y_los_dias_no_cambian_al_cambiar_de_medida(
    sesion: Session, estructura: None
) -> None:
    """El calendario no sabe si la pantalla está en pesos o en kilos.

    Los presupuestos en kilos tienen el reparto invertido respecto a los de
    pesos. Si `H`, `T` e `ideal` se ponderaran con la medida en curso, el
    semáforo del consolidado cambiaría al pulsar un interruptor de presentación.
    """
    _fijar_dias(sesion, "CARTAGENA", "24", "20")
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "10")
    dar_presupuesto(sesion, "415", "RES", "1000000000", kilos="9000")
    dar_presupuesto(sesion, "405", "RES", "9000000000", kilos="1000")
    dar_venta(sesion, "415", "RES", 15, "500000000", kilos="4000")

    ids = _ids(sesion, "415", "405")
    servicio = ReportesService(sesion)
    pesos = servicio.tablero(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, medida=Medida.VALOR, alcance=ids)
    ).consolidado
    kilos = servicio.tablero(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, medida=Medida.KILOS, alcance=ids)
    ).consolidado

    assert pesos.ideal == kilos.ideal
    assert pesos.dias_habiles == kilos.dias_habiles
    assert pesos.dias_trabajados == kilos.dias_trabajados


def test_un_corte_de_una_sola_zona_no_sufre_ninguna_ponderacion(
    sesion: Session, estructura: None
) -> None:
    """Con todos los puntos en la misma zona, `H`, `T` e `ideal` son los de la zona."""
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "10")
    dar_presupuesto(sesion, "405", "RES", "1000000000")
    dar_presupuesto(sesion, "406", "RES", "4000000000")
    dar_venta(sesion, "405", "RES", 10, "300000000")

    consolidado = _tablero(sesion, alcance=_ids(sesion, "405", "406")).consolidado

    assert consolidado.dias_habiles == D("28.50")
    assert consolidado.dias_trabajados == D("10.00")
    assert consolidado.ideal == (D(10) / D("28.5")).quantize(D("0.0001"))


def test_la_proyeccion_del_consolidado_usa_dias_sin_redondear(
    sesion: Session, estructura: None
) -> None:
    """Tres zonas con presupuestos que no dan una media exacta.

    Con `H` y `T` cuantizados a dos decimales antes de proyectar, el cierre de
    mes de la compañía se desviaba en millones de pesos.
    """
    _fijar_dias(sesion, "CARTAGENA", "24", "13")
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "15")
    _fijar_dias(sesion, "BUCARAMANGA Y CENTRO", "27.5", "14")
    for codigo, presupuesto in (
        ("415", "3333333333"),
        ("405", "3333333333"),
        ("412", "3333333334"),
    ):
        dar_presupuesto(sesion, codigo, "RES", presupuesto)
    dar_venta(sesion, "415", "RES", 15, "1000000000")
    dar_venta(sesion, "405", "RES", 15, "1200000000")
    dar_venta(sesion, "412", "RES", 15, "1100000000")

    consolidado = _tablero(sesion, alcance=_ids(sesion, "415", "405", "412")).consolidado

    total = D("3333333333") * 2 + D("3333333334")
    habiles = (
        D(24) * D("3333333333") + D("28.5") * D("3333333333") + D("27.5") * D("3333333334")
    ) / total
    trabajados = (
        D(13) * D("3333333333") + D(15) * D("3333333333") + D(14) * D("3333333334")
    ) / total

    assert consolidado.proyeccion == ((D("3300000000") / trabajados) * habiles).quantize(D("0.01"))
    assert consolidado.dias_habiles == D("26.67"), "publicado con dos decimales, calculado exacto"


# ── §4.3 Crecimiento comparable ───────────────────────────────────────────────


def _venta_2025(sesion: Session, codigo_co: str, valor: str) -> None:
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


def test_el_crecimiento_consolidado_proyecta_solo_los_puntos_con_historia(
    sesion: Session, estructura: None
) -> None:
    """Historia parcial: MALAMBO tiene historia y LAGRANJA no.

    El consolidado proyecta la venta de MALAMBO al cierre y la compara contra
    2025. LAGRANJA no entra en el numerador: no tiene historia comparable.
    """
    for codigo in ("402", "403"):
        dar_presupuesto(sesion, codigo, "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "1200000000")
    dar_venta(sesion, "403", "RES", 5, "1000000000")
    _venta_2025(sesion, "402", "1000000000")

    consolidado = _tablero(sesion, alcance=_ids(sesion, "402", "403")).consolidado

    assert consolidado.venta == D("2200000000.00"), "la venta publicada es la de todos los puntos"
    assert consolidado.crecimiento == D("1.4835")


def test_sin_ningun_punto_con_historia_el_crecimiento_consolidado_es_vacio(
    sesion: Session, estructura: None
) -> None:
    """Ni 0 % ni un crecimiento inventado: «—» (§4.3 y §7)."""
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "1200000000")
    _venta_2025(sesion, "403", "1000000000")  # historia de un punto fuera del alcance

    consolidado = _tablero(sesion, alcance=_ids(sesion, "402")).consolidado

    assert consolidado.crecimiento is None
    assert consolidado.venta_anio_anterior is None


# ── Reporte de clientes: filtro de categoría y participación ──────────────────


def _cliente_con_venta(sesion: Session, indice: int, importe: str, categoria: str = "RES") -> None:
    cliente = Cliente(nit=f"NIT{indice}", razon_social=f"CLIENTE {indice}")
    sesion.add(cliente)
    sesion.flush()
    sesion.add(
        VentaLinea(
            periodo_id=id_periodo(sesion),
            fecha=date(2026, 8, 5),
            punto_venta_id=id_punto_venta(sesion, "402"),
            categoria_id=id_categoria(sesion, categoria),
            cliente_id=cliente.id,
            nit_cliente=f"NIT{indice}",
            valor_subtotal=D(importe),
            costo_promedio=D(0),
            cantidad_inv=D(0),
        )
    )
    sesion.commit()


def test_el_reporte_de_clientes_aplica_el_filtro_de_categoria(
    sesion: Session, estructura: None
) -> None:
    """`docs/API.md`: «Todos aceptan los mismos filtros … `categoria`»."""
    _cliente_con_venta(sesion, 1, "100000000", "RES")
    _cliente_con_venta(sesion, 2, "900000000", "CERDO")

    filas = (
        ReportesService(sesion)
        .clientes(
            FiltrosReporte(periodo=PERIODO, hasta=CORTE, categoria="RES"),
            AgrupacionClientes.CLIENTE,
        )
        .filas
    )

    assert [f.clave for f in filas] == ["NIT1"]
    assert sum(D(f.venta) for f in filas) == D("100000000.00")
    assert filas[0].participacion == D("1.0000"), (
        "dentro del corte filtrado, ese cliente es el 100 % de la venta de RES"
    )


def test_la_participacion_se_divide_entre_el_total_del_corte(
    sesion: Session, estructura: None
) -> None:
    """Seis clientes, tope de dos filas: 900 de 2 100 es el 42.86 %, no el 60 %.

    Dividir entre las filas ya truncadas hace que las participaciones sumen
    100 % por construcción y exagera a los primeros del ranking.
    """
    for indice, importe in enumerate(["900", "600", "300", "100", "100", "100"]):
        _cliente_con_venta(sesion, indice, f"{importe}000000")

    servicio = ReportesService(sesion)
    servicio._settings = servicio._settings.model_copy(update={"max_filas_reporte_clientes": 2})
    filas = servicio.clientes(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE), AgrupacionClientes.CLIENTE
    ).filas

    assert len(filas) == 2
    assert filas[0].participacion == D("0.4286")
    assert filas[1].participacion == D("0.2857")
    assert sum(D(f.participacion) for f in filas) < D(1), (
        "las participaciones de un top-N no pueden sumar el 100 %"
    )


def test_la_participacion_de_un_corte_vacio_es_none_y_no_cero(
    sesion: Session, estructura: None
) -> None:
    """División por cero: «—», nunca `0` ni un error (§7)."""
    _cliente_con_venta(sesion, 1, "0")

    filas = (
        ReportesService(sesion)
        .clientes(FiltrosReporte(periodo=PERIODO, hasta=CORTE), AgrupacionClientes.CLIENTE)
        .filas
    )

    assert filas[0].participacion is None


@pytest.mark.parametrize("medida", [Medida.VALOR, Medida.KILOS])
def test_el_tablero_cuadra_en_las_dos_medidas(
    sesion: Session, estructura: None, medida: Medida
) -> None:
    """Cuadre de extremo a extremo: consolidado = Σ grupos, en pesos y en kilos."""
    dar_presupuesto(sesion, "402", "RES", "1000000000", kilos="50000")
    dar_presupuesto(sesion, "415", "RES", "2000000000", kilos="30000")
    dar_presupuesto(sesion, "407", "RES", "3000000000", kilos="10000")
    dar_venta(sesion, "402", "RES", 5, "400000000", kilos="20000")
    dar_venta(sesion, "415", "RES", 5, "600000000", kilos="10000")
    dar_venta(sesion, "407", "RES", 5, "900000000", kilos="4000")
    dar_venta(sesion, "432", "RES", 5, "77000000", kilos="1000")

    tablero = ReportesService(sesion).tablero(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, medida=medida)
    )

    assert sum(D(g.venta) for g in tablero.grupos) == D(tablero.consolidado.venta)
    assert sum(D(g.presupuesto) for g in tablero.grupos if g.presupuesto is not None) == D(
        tablero.consolidado.presupuesto
    )
    assert [f.codigo_co for f in tablero.sin_presupuesto] == ["432"]
