"""Historia manual de venta y su uso en el crecimiento interanual."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.application.services.periodos import obtener_o_crear_periodo
from app.infrastructure.models.venta import VentaLinea
from tests.conftest import (
    PERIODO,
    PUNTO_AJENO,
    PUNTO_PROPIO,
    dar_venta,
    id_categoria,
    id_punto_venta,
)


def _guardar(
    cliente: TestClient,
    cabeceras: dict[str, str],
    sesion: Session,
    punto: str = PUNTO_PROPIO,
    monto: str = "1000",
    kilos: str = "100",
):
    return cliente.put(
        "/api/v1/historia-venta",
        headers=cabeceras,
        json={
            "periodo": "2025-08",
            "punto_venta_id": id_punto_venta(sesion, punto),
            "monto": monto,
            "kilos": kilos,
            "motivo": "Carga inicial del histórico",
        },
    )


def test_historia_manual_alimenta_tablero_en_valor_y_kilos(
    cliente_http: TestClient,
    admin: dict[str, str],
    sesion: Session,
) -> None:
    dar_venta(sesion, PUNTO_PROPIO, "RES", 5, "1200", kilos="150")
    respuesta = _guardar(cliente_http, admin, sesion)
    assert respuesta.status_code == 200, respuesta.text

    valor = cliente_http.get(
        "/api/v1/reportes/tablero",
        headers=admin,
        params={"periodo": PERIODO, "punto_venta": PUNTO_PROPIO, "medida": "valor"},
    ).json()["consolidado"]
    kilos = cliente_http.get(
        "/api/v1/reportes/tablero",
        headers=admin,
        params={"periodo": PERIODO, "punto_venta": PUNTO_PROPIO, "medida": "kilos"},
    ).json()["consolidado"]

    assert valor["venta_anio_anterior"] == "1000.00"
    assert valor["crecimiento"] == "0.2000"
    assert kilos["venta_anio_anterior"] == "100.000"
    assert kilos["crecimiento"] == "0.5000"


def test_venta_transaccional_anterior_tiene_precedencia_y_no_se_duplica(
    cliente_http: TestClient,
    admin: dict[str, str],
    sesion: Session,
) -> None:
    dar_venta(sesion, PUNTO_PROPIO, "RES", 5, "1200")
    assert _guardar(cliente_http, admin, sesion, monto="5000").status_code == 200

    anterior = obtener_o_crear_periodo(sesion, "2025-08")
    sesion.add(
        VentaLinea(
            periodo_id=anterior.id,
            fecha=date(2025, 8, 5),
            punto_venta_id=id_punto_venta(sesion, PUNTO_PROPIO),
            categoria_id=id_categoria(sesion, "RES"),
            valor_subtotal=Decimal("1000"),
            costo_promedio=Decimal("0"),
            cantidad_inv=Decimal("0"),
        )
    )
    sesion.commit()

    fila = cliente_http.get(
        "/api/v1/reportes/tablero",
        headers=admin,
        params={"periodo": PERIODO, "punto_venta": PUNTO_PROPIO, "medida": "valor"},
    ).json()["consolidado"]
    assert fila["venta_anio_anterior"] == "1000.00"
    assert fila["crecimiento"] == "0.2000"


def test_historia_respeta_alcance_de_escritura(
    cliente_http: TestClient,
    analista_con_alcance: dict[str, str],
    sesion: Session,
) -> None:
    propia = _guardar(cliente_http, analista_con_alcance, sesion)
    ajena = _guardar(cliente_http, analista_con_alcance, sesion, punto=PUNTO_AJENO)

    assert propia.status_code == 200
    assert ajena.status_code == 403


def test_rol_consulta_no_puede_guardar_historia(
    cliente_http: TestClient,
    consulta: dict[str, str],
    sesion: Session,
) -> None:
    respuesta = _guardar(cliente_http, consulta, sesion)
    assert respuesta.status_code == 403
