from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.api.v1 import reportes
from app.application.services import canales_facturados_service
from app.core.config import Settings
from app.infrastructure.fuentes.ventas_canal_siesa import (
    ConfiguracionVentasCanal,
    RegistroVentaCanal,
    consultar_ventas_por_canal,
)
from app.schemas.reportes import RespuestaCanalesFacturados


def test_consultar_ventas_por_canal_sigue_todas_las_paginas() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        assert peticion.url.params["periodo_inicio"] == "202609"
        assert peticion.url.params["periodo_fin"] == "202609"
        assert peticion.url.params.get_list("cia") == ["4"]
        assert peticion.headers["Authorization"] == "token-de-prueba"
        if peticion.url.params["offset"] == "0":
            return httpx.Response(
                200,
                json={
                    "data": [{"Canal": "HORECA", "Venta_Neta": 100}],
                    "has_more": True,
                    "next_offset": 1,
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"Canal": "HORECA", "Venta_Neta": 25},
                    {"Canal": None, "Venta_Neta": 5},
                ],
                "has_more": False,
            },
        )

    configuracion = ConfiguracionVentasCanal(
        url_base="https://siesa.pruebas.local",
        token=SecretStr("1-token-de-prueba"),
    )
    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        filas = consultar_ventas_por_canal(
            "202609",
            (4,),
            configuracion=configuracion,
            cliente=cliente,
        )

    assert len(peticiones) == 2
    assert filas == [
        RegistroVentaCanal(canal="HORECA", venta_neta=Decimal("100")),
        RegistroVentaCanal(canal="HORECA", venta_neta=Decimal("25")),
        RegistroVentaCanal(canal="SIN CLASE", venta_neta=Decimal("5")),
    ]


def test_ventas_facturadas_por_canal_agrega_y_calcula_participacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        canales_facturados_service,
        "consultar_ventas_por_canal",
        lambda *_args, **_kwargs: [
            RegistroVentaCanal("HORECA", Decimal("100")),
            RegistroVentaCanal("HORECA", Decimal("25")),
            RegistroVentaCanal("SIN CLASE", Decimal("25")),
        ],
    )
    settings = Settings(siesa_token=SecretStr("token-de-prueba"))

    respuesta = canales_facturados_service.ventas_facturadas_por_canal(
        "2026-09", (4,), settings=settings
    )

    assert respuesta.total_venta == Decimal("150.00")
    assert [(fila.canal, fila.venta, fila.participacion) for fila in respuesta.filas] == [
        ("HORECA", Decimal("125.00"), Decimal("0.833333")),
        ("SIN CLASE", Decimal("25.00"), Decimal("0.166667")),
    ]


def test_api_ventas_facturadas_por_canal_y_alcance_pdv(
    cliente_http: httpx.Client,
    gerente: dict[str, str],
    jefe_pdv: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llamadas: list[tuple[str, tuple[int, ...]]] = []

    def falso_servicio(periodo: str, companias: tuple[int, ...], *, settings: Settings):
        llamadas.append((periodo, companias))
        return RespuestaCanalesFacturados(
            periodo=periodo,
            total_venta="100.00",
            filas=[{"canal": "HORECA", "venta": "100.00", "participacion": "1.000000"}],
        )

    monkeypatch.setattr(reportes, "ventas_facturadas_por_canal", falso_servicio)
    ruta = "/api/v1/reportes/clientes/canales-facturados?periodo=2026-09"

    respuesta = cliente_http.get(ruta, headers=gerente)
    assert respuesta.status_code == 200
    assert respuesta.json()["filas"][0]["canal"] == "HORECA"
    assert llamadas and llamadas[0][0] == "2026-09"

    restringida = cliente_http.get(ruta, headers=jefe_pdv)
    assert restringida.status_code == 403
