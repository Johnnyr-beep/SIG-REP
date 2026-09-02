"""El filtro `punto_venta` admite varios códigos, en los cuatro reportes.

`?punto_venta=402,405,603`. Es el mismo control de la misma barra de filtros en
las cuatro pantallas, así que se comprueba en las cuatro: que un reporte lo
entendiera distinto que otro sería exactamente la incoherencia que la lista
viene a evitar.

Las tres preguntas que hay que hacerle a este filtro son:

1. ¿Suma lo que debe cuando se piden varios?
2. ¿Un solo código y la ausencia siguen comportándose **exactamente** como
   antes? Es la parte que nadie mira y la que rompe lo que ya funcionaba.
3. ¿**Estrecha** siempre, y jamás ensancha? Un JEFE_PDV que pida los puntos de
   un compañero tiene que recibir los suyos y ninguno más. La lista es una
   forma de pedir menos, nunca de pedir permiso.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.domain.enums import AgrupacionClientes
from app.infrastructure.models.periodo import CalendarioZona
from app.infrastructure.models.venta import Cliente, VentaLinea
from tests.conftest import (
    PERIODO,
    PUNTO_AJENO,
    PUNTO_PROPIO,
    dar_presupuesto,
    dar_venta,
    id_categoria,
    id_periodo,
    id_punto_venta,
)

D = Decimal
CORTE = date(2026, 8, 15)

#: Los tres del ejemplo del contrato, más uno que se queda fuera.
TRES = ("402", "405", "603")
CUARTO = "413"


def _fijar_calendario(sesion: Session, habiles: str, trabajados: str) -> None:
    for calendario in sesion.scalars(select(CalendarioZona)).all():
        calendario.dias_habiles = D(habiles)
        calendario.dias_trabajados = D(trabajados)
    sesion.commit()


def _escenario(sesion: Session) -> None:
    """Cuatro puntos con presupuesto y venta, todos distintos entre sí.

    Los importes se eligen para que **ninguna suma parcial coincida con otra**:
    si el filtro dejara entrar un punto de más, el número no cuadraría por
    casualidad con el esperado.
    """
    _fijar_calendario(sesion, "25", "10")
    for codigo, presupuesto, venta in (
        ("402", "1000000", "100000"),
        ("405", "2000000", "200000"),
        ("603", "4000000", "400000"),
        (CUARTO, "8000000", "800000"),
    ):
        dar_presupuesto(sesion, codigo, "RES", presupuesto)
        dar_venta(sesion, codigo, "RES", 5, venta, costo="0")


def _tablero(sesion: Session, *codigos: str, alcance: list[int] | None = None) -> Decimal:
    """La venta del consolidado del tablero con ese filtro de puntos."""
    respuesta = ReportesService(sesion).tablero(
        FiltrosReporte(
            periodo=PERIODO,
            hasta=CORTE,
            puntos_venta=tuple(codigos) or None,
            alcance=alcance,
        )
    )
    return D(respuesta.consolidado.venta)


# ── 1. Varios puntos suman lo que deben ───────────────────────────────────────


def test_el_tablero_de_varios_puntos_suma_solo_esos_puntos(
    sesion: Session, estructura: None
) -> None:
    """`402,405,603` = 100 000 + 200 000 + 400 000. LA93 no entra."""
    _escenario(sesion)

    assert _tablero(sesion, *TRES) == D("700000.00")
    assert _tablero(sesion) == D("1500000.00"), "sin filtro entran los cuatro"


def test_el_presupuesto_del_consolidado_tambien_se_limita_a_los_puntos_pedidos(
    sesion: Session, estructura: None
) -> None:
    """El denominador manda: si sumara el presupuesto de LA93, el cumplimiento
    de los tres puntos saldría hundido sin que nadie pudiera ver por qué.
    """
    _escenario(sesion)

    respuesta = ReportesService(sesion).tablero(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, puntos_venta=TRES)
    )
    assert respuesta.consolidado.presupuesto == D("7000000.00")
    # 700 000 / 7 000 000, recalculado sobre los totales y no promediado (§7).
    assert respuesta.consolidado.cumplimiento == D("0.1000")


def test_cumplimiento_devuelve_una_fila_por_punto_pedido(sesion: Session, estructura: None) -> None:
    _escenario(sesion)

    respuesta = ReportesService(sesion).cumplimiento(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, puntos_venta=TRES)
    )
    assert [f.punto_venta for f in respuesta.filas] == ["402", "405", "603"]
    assert respuesta.consolidado.venta == D("700000.00")


def test_venta_diaria_devuelve_una_fila_por_punto_pedido(sesion: Session, estructura: None) -> None:
    _escenario(sesion)

    respuesta = ReportesService(sesion).venta_diaria(
        FiltrosReporte(periodo=PERIODO, hasta=CORTE, puntos_venta=TRES)
    )
    assert [f.punto_venta for f in respuesta.filas] == ["402", "405", "603"]
    assert sorted(respuesta.presupuesto_diario_por_pdv) == ["402", "405", "603"]


def test_clientes_solo_ve_la_venta_de_los_puntos_pedidos(sesion: Session, estructura: None) -> None:
    """Un cliente por punto de venta: el filtro decide cuáles se publican."""
    _fijar_calendario(sesion, "25", "10")
    for indice, codigo in enumerate(("402", "405", "603", CUARTO), start=1):
        cliente = Cliente(nit=f"NIT{indice}", razon_social=f"CLIENTE {indice}")
        sesion.add(cliente)
        sesion.flush()
        sesion.add(
            VentaLinea(
                periodo_id=id_periodo(sesion),
                fecha=date(2026, 8, 5),
                punto_venta_id=id_punto_venta(sesion, codigo),
                categoria_id=id_categoria(sesion, "RES"),
                cliente_id=cliente.id,
                nit_cliente=f"NIT{indice}",
                valor_subtotal=D("100000") * indice,
                costo_promedio=D(0),
                cantidad_inv=D(0),
            )
        )
    sesion.commit()

    filas = (
        ReportesService(sesion)
        .clientes(
            FiltrosReporte(periodo=PERIODO, hasta=CORTE, puntos_venta=TRES),
            AgrupacionClientes.CLIENTE,
        )
        .filas
    )

    assert sorted(f.clave for f in filas) == ["NIT1", "NIT2", "NIT3"]
    # La participación se divide entre la venta del corte **ya filtrado**:
    # 300 000 de 600 000. Con el cuarto punto dentro daría 0.20.
    assert next(f for f in filas if f.clave == "NIT3").participacion == D("0.5000")


# ── 2. Un punto y ninguno siguen igual ────────────────────────────────────────


def test_un_solo_codigo_se_comporta_igual_que_antes(sesion: Session, estructura: None) -> None:
    """La lista de uno es el filtro de siempre, ni más ni menos."""
    _escenario(sesion)

    assert _tablero(sesion, "402") == D("100000.00")
    assert _tablero(sesion, CUARTO) == D("800000.00")


def test_los_espacios_y_los_repetidos_no_cambian_el_resultado(
    sesion: Session, estructura: None
) -> None:
    """Pedir `402,402` no es pedir MALAMBO dos veces."""
    _escenario(sesion)

    assert _tablero(sesion, "402", "402") == D("100000.00")
    assert _tablero(sesion, " 402 ", "405") == D("300000.00")


def test_sin_filtro_el_reporte_es_el_de_toda_la_compania(sesion: Session, estructura: None) -> None:
    _escenario(sesion)

    respuesta = ReportesService(sesion).cumplimiento(FiltrosReporte(periodo=PERIODO, hasta=CORTE))
    # Los quince puntos presupuestados, no solo los cuatro con venta: un punto
    # que aún no vendió no puede desaparecer del denominador.
    assert len(respuesta.filas) == 15
    assert sum(D(f.venta) for f in respuesta.filas) == D("1500000.00")


def test_un_codigo_inexistente_no_trae_nada_y_no_revienta(
    sesion: Session, estructura: None
) -> None:
    """No es un validador de catálogo: sencillamente no casa con ninguna fila."""
    _escenario(sesion)

    assert _tablero(sesion, "999") == D("0.00")
    assert _tablero(sesion, "402", "999") == D("100000.00")


# ── 3. El filtro estrecha; jamás ensancha ─────────────────────────────────────


def test_el_jefe_no_ensancha_su_alcance_pidiendo_puntos_ajenos(
    sesion: Session, estructura: None
) -> None:
    """La regla de seguridad, comprobada en el servicio.

    Alcance sobre MALAMBO (402) y una petición de tres puntos: recibe el suyo y
    **nada más**. Las dos condiciones se cruzan con `AND`.
    """
    _escenario(sesion)
    alcance = [id_punto_venta(sesion, PUNTO_PROPIO)]

    assert _tablero(sesion, "402", "405", "603", alcance=alcance) == D("100000.00")


def test_pedir_solo_puntos_ajenos_devuelve_vacio_y_no_todo(
    sesion: Session, estructura: None
) -> None:
    """El fallo peligroso sería que un filtro sin intersección se ignorara."""
    _escenario(sesion)
    alcance = [id_punto_venta(sesion, PUNTO_PROPIO)]

    assert _tablero(sesion, "405", PUNTO_AJENO, alcance=alcance) == D("0.00")


def test_por_http_el_jefe_pide_tres_puntos_y_recibe_el_suyo(
    cliente_http: TestClient, jefe_pdv: dict[str, str], sesion: Session
) -> None:
    """La misma regla en la frontera, que es donde se aplica el alcance."""
    _escenario(sesion)

    cuerpo = cliente_http.get(
        f"/api/v1/reportes/cumplimiento?periodo={PERIODO}&hasta=2026-08-15"
        f"&punto_venta=402,405,{PUNTO_AJENO}",
        headers=jefe_pdv,
    ).json()

    assert [f["punto_venta"] for f in cuerpo["filas"]] == [PUNTO_PROPIO]
    assert cuerpo["filas"][0]["venta"] == "100000.00"


def test_por_http_la_gerencia_si_recibe_los_tres(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """La otra mitad: sin restricción de alcance, la lista trae los tres."""
    _escenario(sesion)

    cuerpo = cliente_http.get(
        f"/api/v1/reportes/tablero?periodo={PERIODO}&hasta=2026-08-15&punto_venta=402,405,603",
        headers=gerente,
    ).json()

    assert cuerpo["consolidado"]["venta"] == "700000.00"


def test_por_http_el_filtro_vacio_equivale_a_no_enviarlo(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """Una barra de filtros que se vacía no pide el punto de código «»."""
    _escenario(sesion)
    base = f"/api/v1/reportes/tablero?periodo={PERIODO}&hasta=2026-08-15"

    sin_filtro = cliente_http.get(base, headers=gerente).json()
    vacio = cliente_http.get(f"{base}&punto_venta=", headers=gerente).json()
    comas = cliente_http.get(f"{base}&punto_venta=,,", headers=gerente).json()

    assert sin_filtro["consolidado"]["venta"] == "1500000.00"
    assert vacio["consolidado"] == sin_filtro["consolidado"]
    assert comas["consolidado"] == sin_filtro["consolidado"]


def test_el_filtro_de_varios_puntos_llega_a_la_exportacion(
    cliente_http: TestClient, gerente: dict[str, str], sesion: Session
) -> None:
    """Exportar es exportar lo que muestra la pantalla, filtros incluidos."""
    _escenario(sesion)

    respuesta = cliente_http.get(
        f"/api/v1/reportes/cumplimiento/exportar?periodo={PERIODO}"
        f"&hasta=2026-08-15&punto_venta=402,405",
        headers=gerente,
    )

    assert respuesta.status_code == 200
    assert respuesta.content.startswith(b"PK\x03\x04")
