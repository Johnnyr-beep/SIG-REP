from fastapi.testclient import TestClient


def test_numero_empleados_es_editable_y_aparece_en_cumplimiento(
    cliente_http: TestClient, gerente: dict[str, str]
) -> None:
    puntos = cliente_http.get("/api/v1/catalogos/puntos-venta", headers=gerente).json()
    malambo = next(punto for punto in puntos if punto["codigo_co"] == "402")

    guardado = cliente_http.put(
        "/api/v1/presupuesto/empleados",
        headers=gerente,
        json={"punto_venta_id": malambo["id"], "numero_empleados": 8},
    )
    assert guardado.status_code == 200
    assert guardado.json()["numero_empleados"] == 8

    respuesta = cliente_http.get(
        "/api/v1/reportes/cumplimiento",
        params={"periodo": "2026-08"},
        headers=gerente,
    )
    assert respuesta.status_code == 200
    filas = {fila["punto_venta"]: fila for fila in respuesta.json()["filas"]}
    assert filas["402"]["numero_empleados"] == 8
    assert filas["413"]["numero_empleados"] is None


def test_empleados_respeta_el_alcance_del_analista(
    cliente_http: TestClient,
    analista_con_alcance: dict[str, str],
    jefe_pdv: dict[str, str],
) -> None:
    puntos = cliente_http.get("/api/v1/catalogos/puntos-venta", headers=analista_con_alcance).json()
    la93 = next(punto for punto in puntos if punto["codigo_co"] == "413")

    lectura_analista = cliente_http.get(
        "/api/v1/presupuesto/empleados",
        params={"punto_venta": "413"},
        headers=analista_con_alcance,
    )
    lectura_jefe = cliente_http.get(
        "/api/v1/presupuesto/empleados",
        params={"punto_venta": "413"},
        headers=jefe_pdv,
    )
    guardado = cliente_http.put(
        "/api/v1/presupuesto/empleados",
        headers=analista_con_alcance,
        json={"punto_venta_id": la93["id"], "numero_empleados": 12},
    )

    assert lectura_analista.status_code == 200
    assert lectura_jefe.status_code == 403
    assert guardado.status_code == 403
