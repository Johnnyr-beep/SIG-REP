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
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.application.services.agro_presupuesto_mensual_service import (
    AgroPresupuestoMensualService,
)
from app.application.services.periodos import obtener_o_crear_periodo
from app.core.errors import ErrorPeriodoCerrado, ErrorValidacion
from app.infrastructure.models.agro_presupuesto_mensual import (
    AgroPptoMensualDetalle,
    AgroPptoMensualEjecutivo,
    AgroPptoMensualServicio,
)
from app.schemas.agro import (
    DetalleMensualEntrada,
    MapeoMensualEntrada,
    PresupuestoEjecutivoMensualEntrada,
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


def test_captura_directa_puede_iniciar_sin_ingesta_ni_periodo_previo(
    estructura: None,
    sesion: Session,
) -> None:
    periodo_nuevo = "2027-01"
    svc = _servicio(sesion)

    resumen_vacio = svc.resumen(periodo_nuevo)
    guardado = svc.guardar_resumen_ejecutivo(
        periodo_nuevo,
        PresupuestoEjecutivoMensualEntrada(
            gerencia_comercial=Decimal("100"),
            oficina=Decimal("200"),
            servicios=Decimal("300"),
            negocios_especiales=Decimal("400"),
        ),
    )

    assert resumen_vacio.resumen_ejecutivo.total_ppto_anual == Decimal("0")
    assert guardado.gran_total == Decimal("600")
    assert guardado.total_ppto_anual == Decimal("1000")


def test_api_guarda_presupuesto_ejecutivo_sin_ingesta(
    cliente_http: TestClient,
    analista: dict[str, str],
) -> None:
    respuesta = cliente_http.put(
        "/api/v1/agro/presupuesto-mensual/ejecutivo",
        params={"periodo": "2027-02"},
        headers=analista,
        json={
            "gerencia_comercial": "100",
            "oficina": "200",
            "servicios": "300",
            "negocios_especiales": "400",
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    resultado = respuesta.json()
    assert Decimal(resultado["gran_total"]) == Decimal("600")
    assert Decimal(resultado["total_ppto_anual"]) == Decimal("1000")


def test_resumen_ejecutivo_aplica_las_particiones_de_la_imagen(
    estructura: None,
    sesion: Session,
) -> None:
    svc = _servicio(sesion)
    comercial = [
        ("GERENCIA", "GERENCIA COMERCIAL", "A", "100"),
        ("BELKIS", "BELKIS", "Z", "200"),
        ("INVERSIONES SERRANO", "INVERSIONES SERRANO", "F", "300"),
    ]
    for clave, etiqueta, categoria, monto in comercial:
        svc.guardar_detalle(
            PERIODO,
            DetalleMensualEntrada(
                bloque="commercial",
                vendedor_clave=clave,
                vendedor_etiqueta=etiqueta,
                cliente_clave=f"CLIENTE-{clave}",
                categoria=categoria,
                monto=Decimal(monto),
                kilos=Decimal("0"),
            ),
        )
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="agro_distribucion",
            cliente_clave="CLIENTE-AGRO",
            monto=Decimal("400"),
            kilos=Decimal("0"),
        ),
    )
    svc.guardar_servicio(
        PERIODO,
        ServicioMensualEntrada(monto=Decimal("500"), kilos=Decimal("0")),
    )
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="nacional",
            cliente_clave="CLIENTE-ESPECIAL",
            cliente_etiqueta="Almacenes Éxito",
            monto=Decimal("600"),
            kilos=Decimal("0"),
        ),
    )
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="nacional",
            cliente_clave="OTRO-CLIENTE",
            cliente_etiqueta="Otro cliente",
            monto=Decimal("700"),
            kilos=Decimal("0"),
        ),
    )
    svc.guardar_detalle(
        PERIODO_OTRO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="GERENCIA",
            cliente_clave="CLIENTE-SEP",
            categoria="A",
            monto=Decimal("10"),
            kilos=Decimal("0"),
        ),
    )
    svc.guardar_detalle(
        PERIODO_OTRO,
        DetalleMensualEntrada(
            bloque="nacional",
            cliente_clave="SODEXO",
            monto=Decimal("20"),
            kilos=Decimal("0"),
        ),
    )

    ejecutivo = svc.resumen(PERIODO).resumen_ejecutivo

    assert ejecutivo.gerencia_comercial == Decimal("100")
    assert ejecutivo.oficina == Decimal("900")
    assert ejecutivo.distribucion == Decimal("1000")
    assert ejecutivo.servicios == Decimal("500")
    assert ejecutivo.gran_total == Decimal("1500")
    assert ejecutivo.negocios_especiales == Decimal("600")
    assert ejecutivo.total_ppto_anual == Decimal("2130")
    assert ejecutivo.meses_con_presupuesto == 2


def test_captura_ejecutiva_directa_actualiza_y_reemplaza_el_calculo_heredado(
    estructura: None,
    sesion: Session,
) -> None:
    svc = _servicio(sesion)
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="GERENCIA",
            cliente_clave="CLIENTE-LEGADO",
            categoria="A",
            monto=Decimal("100"),
            kilos=Decimal("0"),
        ),
    )
    datos = PresupuestoEjecutivoMensualEntrada(
        gerencia_comercial=Decimal("1000"),
        oficina=Decimal("2000"),
        servicios=Decimal("300"),
        negocios_especiales=Decimal("400"),
    )

    primera = svc.guardar_resumen_ejecutivo(PERIODO, datos)
    actualizada = svc.guardar_resumen_ejecutivo(
        PERIODO,
        datos.model_copy(update={"gerencia_comercial": Decimal("1100")}),
    )

    assert primera.gran_total == Decimal("3300")
    assert actualizada.gerencia_comercial == Decimal("1100")
    assert actualizada.total_ppto_anual == Decimal("3800")
    assert actualizada.meses_con_presupuesto == 1
    assert sesion.query(AgroPptoMensualEjecutivo).count() == 1


def test_periodo_cerrado_bloquea_captura_ejecutiva(
    estructura: None,
    sesion: Session,
) -> None:
    periodo = obtener_o_crear_periodo(sesion, PERIODO)
    periodo.cerrado = True
    sesion.commit()

    with pytest.raises(ErrorPeriodoCerrado):
        _servicio(sesion).guardar_resumen_ejecutivo(
            PERIODO,
            PresupuestoEjecutivoMensualEntrada(
                gerencia_comercial=Decimal("100"),
                oficina=Decimal("200"),
                servicios=Decimal("300"),
                negocios_especiales=Decimal("400"),
            ),
        )


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


def test_commercial_acepta_categoria_z(estructura: None, sesion: Session) -> None:
    salida = _servicio(sesion).guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="LEON",
            cliente_clave="CLIENTE-Z",
            categoria="Z",
            monto=Decimal("100000"),
            kilos=Decimal("0"),
        ),
    )

    assert salida.categoria == "Z"


def test_presupuesto_comercial_se_puede_capturar_sin_ingesta(sesion: Session) -> None:
    salida = _servicio(sesion).guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="VEND-ANTES-INGESTA",
            vendedor_etiqueta="Vendedor presupuestado",
            cliente_clave="CLIENTE-ANTES-INGESTA",
            cliente_etiqueta="Cliente presupuestado",
            categoria="Z",
            monto=Decimal("2500000"),
            kilos=Decimal("0"),
        ),
    )

    assert salida.vendedor_clave == "VEND-ANTES-INGESTA"
    assert salida.vendedor_etiqueta == "Vendedor presupuestado"
    assert salida.cliente_clave == "CLIENTE-ANTES-INGESTA"
    assert salida.cliente_etiqueta == "Cliente presupuestado"
    assert salida.categoria == "Z"
    assert salida.monto == Decimal("2500000")


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


def test_cliente_comercial_no_puede_cambiar_de_vendedor(
    estructura: None,
    sesion: Session,
) -> None:
    """Un cliente conserva su vendedor, pero la categoría puede repetirse."""
    svc = _servicio(sesion)
    svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="LEON",
            cliente_clave="CLIENTE-X",
            categoria="A",
            monto=Decimal("300000"),
            kilos=Decimal("100"),
        ),
    )

    with pytest.raises(ErrorValidacion, match="ya está asignado"):
        svc.guardar_detalle(
            PERIODO,
            DetalleMensualEntrada(
                bloque="commercial",
                vendedor_clave="OTRO-VENDEDOR",
                cliente_clave="CLIENTE-X",
                categoria="A",
                monto=Decimal("300000"),
                kilos=Decimal("100"),
            ),
        )

    salida = svc.guardar_detalle(
        PERIODO,
        DetalleMensualEntrada(
            bloque="commercial",
            vendedor_clave="LEON",
            cliente_clave="CLIENTE-X",
            categoria="B",
            monto=Decimal("300000"),
            kilos=Decimal("100"),
        ),
    )
    assert salida.vendedor_clave == "LEON"


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
