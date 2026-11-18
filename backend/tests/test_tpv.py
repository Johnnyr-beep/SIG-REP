from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.application.services.tpv_service import RegistroTpv, resumir_tpv
from app.infrastructure.fuentes.tpv import leer_paginas_tpv


def test_solo_acumula_dias_con_todas_las_cajas_cerradas_y_pdvs_visibles() -> None:
    def fila(dia: int, codigo: str, caja: str, estado: str) -> RegistroTpv:
        return RegistroTpv.model_validate(
            {
                "Compania": 4,
                "CO": codigo,
                "Fecha": f"2026-11-{dia:02}T00:00:00",
                "TPV": caja,
                "Estado": estado,
            }
        )

    respuesta = resumir_tpv(
        [
            fila(1, " 42 ", "TPV1", "Cerrado"),
            fila(1, "042", "TPV2", "Cerrado"),
            fila(2, "042", "TPV1", "Cerrado"),
            fila(2, "042", "TPV2", "Abierto"),
            fila(2, "999", "TPV3", "Abierto"),
            fila(5, "042", "TPV1", "Cerrado"),
        ],
        {"042": "PDV visible"},
        date(2026, 11, 1),
        date(2026, 11, 3),
    )

    (punto,) = respuesta.puntos
    assert punto.fecha_acumulada == date(2026, 11, 1)
    assert punto.dias_acumulados == 1
    assert punto.dias_sin_acumulacion == 2
    assert punto.dias_sin_registros == 1
    (abierta,) = respuesta.abiertas
    assert abierta.tpv == "TPV2"
    assert abierta.fecha == date(2026, 11, 2)


def test_lee_todas_las_paginas_por_compania_sin_filtrar_estado() -> None:
    llamadas = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        consulta = peticion.url.params
        compania, offset = int(consulta["cia"]), int(consulta["offset"])
        llamadas.append((compania, offset))
        assert consulta["fecha_inicio"] == "2026-11-01"
        assert consulta["fecha_fin"] == "2026-11-03"
        assert "estado" not in consulta
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "Compania": compania,
                        "CO": "402",
                        "Fecha": "2026-11-01T00:00:00",
                        "TPV": "TPV1",
                        "Estado": "Abierto" if offset else "Cerrado",
                    }
                ],
                "has_more": compania == 4 and offset == 0,
                "next_offset": 1 if offset == 0 else None,
            },
        )

    with httpx.Client(
        base_url="https://siesa.test", transport=httpx.MockTransport(responder)
    ) as cliente:
        registros = leer_paginas_tpv(cliente, (4, 6), date(2026, 11, 1), date(2026, 11, 3))

    assert llamadas == [(4, 0), (4, 1), (6, 0)]
    assert [registro.estado for registro in registros] == ["Cerrado", "Abierto", "Cerrado"]


def test_costos_tpv_respeta_alcance_por_http(
    cliente_http: TestClient, jefe_pdv: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fuente(*_argumentos: object) -> list[RegistroTpv]:
        return [
            RegistroTpv.model_validate(
                {
                    "Compania": 4,
                    "CO": codigo,
                    "Fecha": "2026-08-01T00:00:00",
                    "TPV": "TPV1",
                    "Estado": "Abierto",
                }
            )
            for codigo in ("402", "413")
        ]

    monkeypatch.setattr("app.api.v1.reportes.consultar_registros_tpv", fuente)
    ruta = "/api/v1/reportes/costos/tpv?periodo=2026-08"
    respuesta = cliente_http.get(ruta, headers=jefe_pdv)
    assert respuesta.status_code == 200
    assert [fila["codigo_co"] for fila in respuesta.json()["puntos"]] == ["402"]
    assert [fila["codigo_co"] for fila in respuesta.json()["abiertas"]] == ["402"]

    sin_acceso = cliente_http.get(f"{ruta}&punto_venta=413", headers=jefe_pdv)
    assert sin_acceso.status_code == 200
    assert sin_acceso.json()["puntos"] == sin_acceso.json()["abiertas"] == []
