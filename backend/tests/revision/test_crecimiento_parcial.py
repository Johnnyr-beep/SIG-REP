"""Revisión: crecimiento contra el año anterior con historia incompleta (§4.3)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.services.periodos import obtener_o_crear_periodo
from app.application.services.reportes_service import FiltrosReporte, ReportesService
from app.infrastructure.models.venta import VentaLinea
from tests.conftest import PERIODO, dar_presupuesto, dar_venta, id_categoria, id_punto_venta


def _venta_2025(sesion: Session, codigo_co: str, dia: int, valor: str) -> None:
    periodo = obtener_o_crear_periodo(sesion, "2025-08")
    sesion.add(
        VentaLinea(
            periodo_id=periodo.id,
            fecha=date(2025, 8, dia),
            punto_venta_id=id_punto_venta(sesion, codigo_co),
            categoria_id=id_categoria(sesion, "RES"),
            valor_subtotal=Decimal(valor),
            costo_promedio=Decimal("0"),
            cantidad_inv=Decimal("0"),
        )
    )
    sesion.commit()


def test_crecimiento_consolidado_con_historia_parcial(sesion: Session, estructura: None) -> None:
    """Con 2025 cargado solo para parte de los puntos, el crecimiento sale inflado.

    Escenario: MALAMBO y LAGRANJA venden 1 000 M cada uno en agosto de 2026. De
    2025 solo se alcanzó a cargar MALAMBO (1 000 M). El consolidado compara
    2 000 M de 2026 contra 1 000 M de 2025 y publica **+100 % de crecimiento**,
    cuando la venta real por punto no creció nada.

    §4.3: «sin 2025 cargado, el indicador se muestra vacío, nunca en cero». El
    caso de historia *parcial* no está contemplado y es el que va a ocurrir.
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_presupuesto(sesion, "403", "RES", "1000000000")
    dar_venta(sesion, "402", "RES", 5, "1000000000")
    dar_venta(sesion, "403", "RES", 5, "1000000000")
    _venta_2025(sesion, "402", 5, "1000000000")

    ids = [
        sesion.scalars(select(VentaLinea.punto_venta_id).distinct()).all(),
    ]
    assert ids

    consolidado = (
        ReportesService(sesion)
        .tablero(
            FiltrosReporte(
                periodo=PERIODO,
                hasta=date(2026, 8, 15),
                alcance=[id_punto_venta(sesion, "402"), id_punto_venta(sesion, "403")],
            )
        )
        .consolidado
    )

    print()
    print(f"  venta 2026            : {consolidado.venta}")
    print(f"  venta año anterior    : {consolidado.venta_anio_anterior}")
    print(f"  crecimiento publicado : {consolidado.crecimiento}")
    print("  crecimiento real de los puntos con historia: 0.0000")

    assert consolidado.crecimiento == Decimal("0.0000"), (
        "el consolidado compara 2 puntos de 2026 contra 1 punto de 2025"
    )
