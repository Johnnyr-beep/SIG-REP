"""Pruebas del presupuesto mensual configurable de la unidad Agropecuaria.

Este módulo es **distinto** del presupuesto por dimensiones. Aquí hay cuatro
bloques independientes —commercial, agro_distribucion, servicio, nacional— y el
total mensual **es la suma de los cuatro**. En el presupuesto por dimensiones,
las cuatro descomposiciones describen el mismo dinero y no se suman.

Las pruebas cubren:

1. El total mensual suma los cuatro bloques.
2. Los bloques de agro_distribucion y nacional fijan el vendedor automáticamente.
3. El bloque de servicio es un solo valor mensual.
4. Las restricciones de unicidad impiden duplicados.
5. El bloqueo por período cerrado funciona.
6. Las validaciones de categoría (A–F) solo aplican al bloque comercial.
7. El presupuesto por dimensiones no se ve afectado.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.application.services.agro_presupuesto_mensual_service import (
    AgroPresupuestoMensualService,
)
from app.application.services.periodos import obtener_o_crear_periodo
from app.core.errors import ErrorPeriodoCerrado, ErrorValidacion
from app.infrastructure.models.agro_presupuesto_mensual import (
    AgroPptoMensualDetalle,
    AgroPptoMensualServicio,
)
from app.schemas.agro import (
    DetalleMensualEntrada,
    MapeoMensualEntrada,
    ServicioMensualEntrada,
)
from tests.conftest import PERIODO

PERIODO_OTRO = "2026-09"


def _servicio(sesion: Session) -> AgroPresupuestoMensualService:
    return AgroPresupuestoMensualService(sesion)


# ── Resumen y suma de bloques ─────────────────────────────────────────────────


def test_el_total_mensual_suma_los_cuatro_bloques(
    estructura: None,
    sesion: Session,
) -> None:
    """El total mensual es la suma de los cuatro bloques independientes."""
    svc = _servicio(sesion)

    # Comercial: un vendedor con categoría A
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="LEON",
            cliente_clave="CLIENTE-1",
            categoria="A",
            monto=Decimal("1000000"),
            kilos=Decimal("500"),
        ),
    )

    # Agro distribución: vendedor fijo AGROPECUARIA
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="agro_distribucion",
            cliente_clave="CLIENTE-2",
            monto=Decimal("2000000"),
            kilos=Decimal("300"),
        ),
    )

    # Nacional: vendedor fijo JUAN SIERRA
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="nacional",
            cliente_clave="EXITO",
            monto=Decimal("3000000"),
            kilos=Decimal("200"),
        ),
    )

    # Servicio: un solo valor mensual
    svc.guardar_servicio(
        PERIODO,
        ServicioMensualEntrada(monto=Decimal("500000"), kilos=Decimal("0")),
    )

    resumen = svc.resumen(PERIODO)

    assert resumen.total_monto == Decimal("6500000")
    assert resumen.total_kilos == Decimal("1000")

    # Cada bloque con su total
    bloques = {b.bloque: b for b in resumen.bloques}
    assert bloques["commercial"].total_monto == Decimal("1000000")
    assert bloques["agro_distribucion"].total_monto == Decimal("2000000")
    assert bloques["nacional"].total_monto == Decimal("3000000")
    assert bloques["servicio"].total_monto == Decimal("500000")


def test_resumen_con_periodo_vacio_devuelve_ceros(
    estructura: None,
    sesion: Session,
) -> None:
    """Un período sin capturar devuelve ceros, no error."""
    resumen = _servicio(sesion).resumen(PERIODO)
    assert resumen.total_monto == Decimal("0")
    assert resumen.total_kilos == Decimal("0")
    assert len(resumen.bloques) == 4


# ── Vendedor fijo en agro_distribucion y nacional ─────────────────────────────


def test_agro_distribucion_fija_vendedor_agropecuaria(
    estructura: None,
    sesion: Session,
) -> None:
    """El bloque agro_distribucion asigna el vendedor AGROPECUARIA automáticamente."""
    salida = _servicio(sesion).guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="agro_distribucion",
            cliente_clave="CLIENTE-AGRO",
            monto=Decimal("100000"),
            kilos=Decimal("0"),
        ),
    )
    assert salida.vendedor_clave == "AGROPECUARIA"


def test_nacional_fija_vendedor_juan_sierra(
    estructura: None,
    sesion: Session,
) -> None:
    """El bloque nacional asigna el vendedor JUAN SIERRA automáticamente."""
    salida = _servicio(sesion).guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="nacional",
            cliente_clave="EXITO",
            monto=Decimal("200000"),
            kilos=Decimal("0"),
        ),
    )
    assert salida.vendedor_clave == "JUAN SIERRA"


def test_commercial_requiere_vendedor(
    estructura: None,
    sesion: Session,
) -> None:
    """El bloque comercial exige un vendedor en cada fila."""
    with pytest.raises(ErrorValidacion, match="requiere un vendedor"):
        _servicio(sesion).guardar_detalle(
            PERIODO,
            DetalleMensualEntrada(
                bloque="commercial",
                cliente_clave="CLIENTE-X",
                categoria="A",
                monto=Decimal("100000"),
                kilos=Decimal("0"),
            ),
        )


# ── Categorías A–F ───────────────────────────────────────────────────────────


def test_commercial_requiere_categoria(
    estructura: None,
    sesion: Session,
) -> None:
    """El bloque comercial exige una categoría A–F en cada fila."""
    with pytest.raises(ErrorValidacion, match="requiere una categor"):
        _servicio(sesion).guardar_detalle(
            PERIODO,
            DetalleMensualEntrada(
                bloque="commercial",
                vendedor_clave="LEON",
                cliente_clave="CLIENTE-X",
                monto=Decimal("100000"),
                kilos=Decimal("0"),
            ),
        )


def test_agro_distribucion_no_admite_categoria(
    estructura: None,
    sesion: Session,
) -> None:
    """Solo el bloque comercial usa categorías A–F."""
    with pytest.raises(ErrorValidacion, match="no admite categor"):
        _servicio(sesion).guardar_detalle(
            PERIODO,
            DetalleMensualEntrada(
                bloque="agro_distribucion",
                cliente_clave="CLIENTE-X",
                categoria="A",
                monto=Decimal("100000"),
                kilos=Decimal("0"),
            ),
        )


# ── Bloque de servicio ───────────────────────────────────────────────────────


def test_servicio_es_un_solo_valor_mensual(
    estructura: None,
    sesion: Session,
) -> None:
    """El bloque de servicio guarda un solo importe por período."""
    svc = _servicio(sesion)
    salida = svc.guardar_servicio(
        PERIODO,
        ServicioMensualEntrada(monto=Decimal("800000"), kilos=Decimal("0")),
    )
    assert salida.monto == Decimal("800000")

    # Actualizar el mismo período reemplaza, no duplica
    salida2 = svc.guardar_servicio(
        PERIODO,
        ServicioMensualEntrada(monto=Decimal("900000"), kilos=Decimal("0")),
    )
    assert salida2.monto == Decimal("900000")

    # Solo una fila en la tabla
    filas = sesion.query(AgroPptoMensualServicio).all()
    assert len(filas) == 1


def test_servicio_no_admite_detalle(
    estructura: None,
    sesion: Session,
) -> None:
    """El bloque de servicio no se captura por filas de detalle.

    El esquema Pydantic ya rechaza `servicio` en `DetalleMensualEntrada` con su
    patrón `^(commercial|agro_distribucion|nacional)$`, así que la validación
    ocurre en la frontera HTTP antes de llegar al servicio.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="bloque"):
        DetalleMensualEntrada(
            bloque="servicio",
            monto=Decimal("100000"),
            kilos=Decimal("0"),
        )


# ── Unicidad ─────────────────────────────────────────────────────────────────


def test_detalle_duplicado_se_actualiza_no_se_duplica(
    estructura: None,
    sesion: Session,
) -> None:
    """Guardar la misma combinación (bloque, cliente, vendedor, categoría) reemplaza."""
    svc = _servicio(sesion)
    datos = DetalleMensualEntrada(
        bloque="commercial",
        vendedor_clave="LEON",
        cliente_clave="CLIENTE-1",
        categoria="A",
        monto=Decimal("100000"),
        kilos=Decimal("0"),
    )
    svc.guardar_detalle(PERIODO, datos)
    datos2 = DetalleMensualEntrada(
        bloque="commercial",
        vendedor_clave="LEON",
        cliente_clave="CLIENTE-1",
        categoria="A",
        monto=Decimal("200000"),
        kilos=Decimal("0"),
    )
    svc.guardar_detalle(PERIODO, datos2)

    filas = sesion.query(AgroPptoMensualDetalle).all()
    assert len(filas) == 1
    assert Decimal(filas[0].monto) == Decimal("200000")


# ── Período cerrado ───────────────────────────────────────────────────────────


def test_periodo_cerrado_bloquea_detalle(
    estructura: None,
    sesion: Session,
) -> None:
    """Un período cerrado no admite cambios de presupuesto mensual."""
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    periodo.cerrado = True
    sesion.commit()

    with pytest.raises(ErrorPeriodoCerrado):
        _servicio(sesion).guardar_detalle(
            PERIODO,
            DetalleMensualEntrada(
                bloque="commercial",
                vendedor_clave="LEON",
                cliente_clave="CLIENTE-1",
                categoria="A",
                monto=Decimal("100000"),
                kilos=Decimal("0"),
            ),
        )


def test_periodo_cerrado_bloquea_servicio(
    estructura: None,
    sesion: Session,
) -> None:
    """Un período cerrado no admite cambios en el bloque de servicio."""
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    periodo.cerrado = True
    sesion.commit()

    with pytest.raises(ErrorPeriodoCerrado):
        _servicio(sesion).guardar_servicio(
            PERIODO,
            ServicioMensualEntrada(monto=Decimal("100000"), kilos=Decimal("0")),
        )


# ── Mapeos ───────────────────────────────────────────────────────────────────


def test_mapeo_commercial_crea_y_lista(
    estructura: None,
    sesion: Session,
) -> None:
    """Crear un mapeo de comercial con categoría y listarlo."""
    svc = _servicio(sesion)
    svc.guardar_mapeo(
        MapeoMensualEntrada(
            bloque="commercial",
            vendedor_clave="LEON",
            cliente_clave="CLIENTE-1",
            categoria="A",
            activo=True,
        )
    )
    mapeos = svc.listar_mapeos("commercial")
    assert len(mapeos) == 1
    assert mapeos[0].bloque == "commercial"
    assert mapeos[0].categoria == "A"
    assert mapeos[0].activo


def test_mapeo_servicio_no_admite_vendedor(
    estructura: None,
    sesion: Session,
) -> None:
    """El mapeo de servicio no lleva vendedor, cliente ni categoría."""
    with pytest.raises(ErrorValidacion, match="no admite vendedor"):
        _servicio(sesion).guardar_mapeo(
            MapeoMensualEntrada(
                bloque="servicio",
                vendedor_clave="ALGUIEN",
            )
        )


def test_mapeo_commercial_requiere_categoria(
    estructura: None,
    sesion: Session,
) -> None:
    """El mapeo de comercial exige categoría."""
    with pytest.raises(ErrorValidacion, match="requiere una categor"):
        _servicio(sesion).guardar_mapeo(
            MapeoMensualEntrada(
                bloque="commercial",
                vendedor_clave="LEON",
                cliente_clave="CLIENTE-1",
            )
        )


# ── No afecta al presupuesto por dimensiones ─────────────────────────────────


def test_presupuesto_por_dimensiones_no_se_ve_afectado(
    estructura: None,
    sesion: Session,
) -> None:
    """El presupuesto mensual no toca las tablas de agro_presupuestos."""
    from app.application.services.agro_presupuesto_service import AgroPresupuestoService
    from app.infrastructure.models.agro_presupuesto import AgroPresupuesto
    from app.infrastructure.models.agro_vocabulario import DimensionPresupuesto

    svc = _servicio(sesion)
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="LEON",
            cliente_clave="CLIENTE-1",
            categoria="A",
            monto=Decimal("1000000"),
            kilos=Decimal("0"),
        ),
    )
    svc.guardar_servicio(
        PERIODO,
        ServicioMensualEntrada(monto=Decimal("500000"), kilos=Decimal("0")),
    )

    # El presupuesto por dimensiones sigue sin tener nada
    filas_dim = sesion.query(AgroPresupuesto).all()
    assert len(filas_dim) == 0

    # Y su servicio sigue funcionando con su propia lógica
    plan = AgroPresupuestoService(sesion).plan(
        obtener_o_crear_periodo(sesion, PERIODO),
        DimensionPresupuesto.VENDEDOR,
    )
    assert not plan.definido
