"""Revisión: H y T agregados en el consolidado y en el grupo.

Estas pruebas NO son de la aplicación: documentan defectos encontrados en la
revisión. Fallan a propósito contra el comportamiento actual.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.domain.enums import Medida
from app.infrastructure.models.organizacion import PuntoVenta, Zona
from app.infrastructure.models.periodo import CalendarioZona
from tests.conftest import PERIODO, dar_presupuesto, dar_venta, id_periodo


def _fijar_dias(sesion: Session, nombre_zona: str, habiles: str, trabajados: str) -> None:
    zona = sesion.scalars(select(Zona).where(Zona.nombre == nombre_zona)).one()
    fila = sesion.scalars(
        select(CalendarioZona).where(
            CalendarioZona.periodo_id == id_periodo(sesion),
            CalendarioZona.zona_id == zona.id,
        )
    ).one()
    fila.dias_habiles = Decimal(habiles)
    fila.dias_trabajados = Decimal(trabajados)
    sesion.commit()


def test_ideal_consolidado_se_pondera_por_presupuesto_por_dias_no_por_presupuesto(
    sesion: Session, estructura: None
) -> None:
    """El ideal del consolidado no es el ideal ponderado por presupuesto.

    Escenario: dos zonas con calendarios distintos y días trabajados fijados a
    mano por el negocio (el caso que el propio docstring de `actualizar` declara
    como el que manda).

        CARTAGENA (415)  H=24    T=20   ideal = 0.8333   presupuesto 1 000 M
        LA43      (405)  H=28.5  T=10   ideal = 0.3509   presupuesto 9 000 M

    Ponderado por presupuesto, como dice el docstring de `_dias_agregados`:

        (1 000·0.833333 + 9 000·0.350877) / 10 000 = 0.3991

    Lo que el servicio calcula:

        H = (24·1000 + 28.5·9000)/10000 = 28.05
        T = (20·1000 + 10·9000)/10000   = 11.00
        ideal = 11.00 / 28.05            = 0.3922
    """
    _fijar_dias(sesion, "CARTAGENA", "24", "20")
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "10")

    dar_presupuesto(sesion, "415", "RES", "1000000000")
    dar_presupuesto(sesion, "405", "RES", "9000000000")
    dar_venta(sesion, "415", "RES", 15, "500000000")
    dar_venta(sesion, "405", "RES", 15, "3450000000")

    filtros = FiltrosReporte(
        periodo=PERIODO,
        hasta=date(2026, 8, 15),
        alcance=[
            sesion.scalars(select(PuntoVenta.id).where(PuntoVenta.codigo_co == "415")).one(),
            sesion.scalars(select(PuntoVenta.id).where(PuntoVenta.codigo_co == "405")).one(),
        ],
    )
    tablero = ReportesService(sesion).tablero(filtros)
    consolidado = tablero.consolidado

    ideal_ponderado_por_presupuesto = (
        Decimal(1000) * (Decimal(20) / Decimal(24))
        + Decimal(9000) * (Decimal(10) / Decimal("28.5"))
    ) / Decimal(10000)

    print()
    print(f"  H consolidado emitido : {consolidado.dias_habiles}")
    print(f"  T consolidado emitido : {consolidado.dias_trabajados}")
    print(f"  ideal emitido         : {consolidado.ideal}")
    print(f"  ideal ponderado por P : {ideal_ponderado_por_presupuesto:.4f}")
    print(f"  cumplimiento          : {consolidado.cumplimiento}")
    print(f"  semaforo              : {consolidado.semaforo}")

    assert consolidado.ideal == ideal_ponderado_por_presupuesto.quantize(Decimal("0.0001"))


def test_el_ideal_cambia_al_cambiar_de_medida(sesion: Session, estructura: None) -> None:
    """`ideal = T/H` es calendario puro y no debería depender de `medida`.

    Escenario: mismo período, mismo corte, mismos dos puntos de venta. Solo se
    cambia el interruptor pesos/kilos. Los presupuestos en kilos tienen otro
    reparto que los de pesos (LA43 pesa más en pesos, CARTAGENA en kilos), y como
    `_dias_agregados` pondera H y T con el presupuesto **de la medida en curso**,
    el ideal del consolidado cambia de valor.
    """
    _fijar_dias(sesion, "CARTAGENA", "24", "20")
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "10")

    dar_presupuesto(sesion, "415", "RES", "1000000000", kilos="9000")
    dar_presupuesto(sesion, "405", "RES", "9000000000", kilos="1000")
    dar_venta(sesion, "415", "RES", 15, "500000000", kilos="4000")
    dar_venta(sesion, "405", "RES", 15, "3450000000", kilos="400")

    ids = [
        sesion.scalars(select(PuntoVenta.id).where(PuntoVenta.codigo_co == "415")).one(),
        sesion.scalars(select(PuntoVenta.id).where(PuntoVenta.codigo_co == "405")).one(),
    ]
    servicio = ReportesService(sesion)
    en_pesos = servicio.tablero(
        FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15), medida=Medida.VALOR, alcance=ids)
    ).consolidado
    en_kilos = servicio.tablero(
        FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15), medida=Medida.KILOS, alcance=ids)
    ).consolidado

    print()
    print(
        f"  pesos : H={en_pesos.dias_habiles} T={en_pesos.dias_trabajados} "
        f"ideal={en_pesos.ideal} semaforo={en_pesos.semaforo}"
    )
    print(
        f"  kilos : H={en_kilos.dias_habiles} T={en_kilos.dias_trabajados} "
        f"ideal={en_kilos.ideal} semaforo={en_kilos.semaforo}"
    )

    assert en_pesos.ideal == en_kilos.ideal, "el ideal es calendario, no depende de la medida"
    assert en_pesos.dias_habiles == en_kilos.dias_habiles


def test_h_y_t_agregados_se_redondean_antes_de_proyectar(sesion: Session, estructura: None) -> None:
    """`_ponderar` cuantiza H y T a 2 decimales y esos valores ya redondeados
    alimentan la proyección y la venta diaria requerida.

    Escenario: tres zonas con presupuestos que no dan una media exacta.
    """
    _fijar_dias(sesion, "CARTAGENA", "24", "13")
    _fijar_dias(sesion, "LA 70 / LA 43 / SIMON / LA GRANJA", "28.5", "15")
    _fijar_dias(sesion, "BUCARAMANGA Y CENTRO", "27.5", "14")

    dar_presupuesto(sesion, "415", "RES", "3333333333")
    dar_presupuesto(sesion, "405", "RES", "3333333333")
    dar_presupuesto(sesion, "412", "RES", "3333333334")
    dar_venta(sesion, "415", "RES", 15, "1000000000")
    dar_venta(sesion, "405", "RES", 15, "1200000000")
    dar_venta(sesion, "412", "RES", 15, "1100000000")

    ids = [
        sesion.scalars(select(PuntoVenta.id).where(PuntoVenta.codigo_co == c)).one()
        for c in ("415", "405", "412")
    ]
    consolidado = (
        ReportesService(sesion)
        .tablero(FiltrosReporte(periodo=PERIODO, hasta=date(2026, 8, 15), alcance=ids))
        .consolidado
    )

    venta = Decimal("3300000000")
    p = Decimal("3333333333") * 2 + Decimal("3333333334")
    h_exacto = (
        Decimal(24) * Decimal("3333333333")
        + Decimal("28.5") * Decimal("3333333333")
        + Decimal("27.5") * Decimal("3333333334")
    ) / p
    t_exacto = (
        Decimal(13) * Decimal("3333333333")
        + Decimal(15) * Decimal("3333333333")
        + Decimal(14) * Decimal("3333333334")
    ) / p
    proyeccion_exacta = (venta / t_exacto) * h_exacto

    print()
    print(f"  H emitido (2 dec) : {consolidado.dias_habiles}   H exacto : {h_exacto}")
    print(f"  T emitido (2 dec) : {consolidado.dias_trabajados}   T exacto : {t_exacto}")
    print(f"  proyeccion emitida: {consolidado.proyeccion}")
    print(f"  proyeccion exacta : {proyeccion_exacta.quantize(Decimal('0.01'))}")
    print(
        f"  diferencia        : "
        f"{(Decimal(consolidado.proyeccion) - proyeccion_exacta).quantize(Decimal('0.01'))}"
    )

    assert Decimal(consolidado.proyeccion) == proyeccion_exacta.quantize(Decimal("0.01"))
