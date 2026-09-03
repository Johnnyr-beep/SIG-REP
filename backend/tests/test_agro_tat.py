from datetime import date
from decimal import Decimal

import httpx
from pydantic import SecretStr

from app.infrastructure.fuentes.agro_tat import (
    COLUMNAS_TAT,
    ConfiguracionTat,
    FuenteVentasTat,
)


def test_fuente_tat_envia_contrato_real_y_parsea_csv() -> None:
    llamadas: list[httpx.Request] = []
    csv_real = ",".join(COLUMNAS_TAT) + "\n"
    csv_real += "2026-09-01,F-10,Minorista,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50\n"

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(200, text=csv_real)

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://test.local")
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("1-secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 30)))

    assert len(filas) == 1
    assert filas[0].codigo_sucursal == "S-1"
    assert filas[0].cantidad_inv == Decimal("4")
    assert filas[0].valor_subtotal == Decimal("1250.50")
    assert llamadas[0].url.path == "/ventas/facturas-agropecuaria-tat"
    assert llamadas[0].url.params["fecha_inicio"] == "2026-09-01"
    assert llamadas[0].url.params["fecha_fin"] == "2026-09-30"
    assert llamadas[0].url.params["cia"] == "3"
    assert llamadas[0].url.params["limit"] == "5000"
    assert llamadas[0].url.params["offset"] == "0"
    assert llamadas[0].url.params["format"] == "csv"
    assert llamadas[0].headers["Authorization"] == "secreto"


def test_fuente_tat_pagina_hasta_el_final() -> None:
    llamadas: list[httpx.Request] = []
    encabezado = ",".join(COLUMNAS_TAT)
    fila = "2026-09-01,F-10,Minorista,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50"
    pagina_completa = "\n".join([encabezado, *([fila] * 5000)]) + "\n"
    pagina_final = "\n".join([encabezado, fila]) + "\n"

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        cuerpo = pagina_completa if request.url.params["offset"] == "0" else pagina_final
        return httpx.Response(200, text=cuerpo)

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://test.local")
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 30)))

    assert len(filas) == 5001
    assert [llamada.url.params["offset"] for llamada in llamadas] == ["0", "5000"]
