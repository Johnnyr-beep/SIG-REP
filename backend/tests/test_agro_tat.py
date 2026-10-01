from datetime import date, time
from decimal import Decimal

import httpx
from pydantic import SecretStr

from app.infrastructure.fuentes.agro_tat import (
    COLUMNAS_TAT,
    ConfiguracionTat,
    FuenteVentasTat,
    LineaTat,
)


def test_fuente_tat_envia_contrato_real_y_parsea_csv() -> None:
    llamadas: list[httpx.Request] = []
    csv_real = "\ufeff" + ",".join(COLUMNAS_TAT) + "\n"
    csv_real += "2026-09-01,F-10,Minorista,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50\n"

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(200, text=csv_real)

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://test.local")
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("1-secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 1)))

    assert len(filas) == 1
    assert filas[0].codigo_sucursal == "S-1"
    assert filas[0].cantidad_inv == Decimal("4")
    assert filas[0].valor_subtotal == Decimal("1250.50")
    assert llamadas[0].url.path == "/ventas/facturas-agropecuaria-tat"
    assert llamadas[0].url.params["fecha_inicio"] == "2026-09-01"
    assert llamadas[0].url.params["fecha_fin"] == "2026-09-01"
    assert llamadas[0].url.params["cia"] == "3"
    assert llamadas[0].url.params["limit"] == "5000"
    assert llamadas[0].url.params["format"] == "csv"
    assert llamadas[0].headers["Authorization"] == "secreto"


def test_fuente_tat_parsea_hora_en_columna_opcional() -> None:
    llamadas: list[httpx.Request] = []
    encabezado = (*COLUMNAS_TAT, "hora_documento")
    fila = "2026-09-01,F-10,Minorista,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50,08:14:35"

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(200, text=f"{','.join(encabezado)}\n{fila}\n")

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://test.local")
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 1)))

    assert filas[0].hora_documento.isoformat() == "08:14:35"


def test_fuente_tat_extrae_hora_embebida_en_fecha_documento() -> None:
    encabezado = ",".join(COLUMNAS_TAT)
    fila = "2026-09-01T16:42:05,F-10,Minorista,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50"
    cliente = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, text=f"{encabezado}\n{fila}\n")
        ),
        base_url="https://test.local",
    )
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 1)))

    assert filas[0].fecha_documento == date(2026, 9, 1)
    assert filas[0].hora_documento.isoformat() == "16:42:05"


def test_fuente_tat_csv_completo_se_descarga_en_una_solicitud() -> None:
    llamadas: list[httpx.Request] = []
    encabezado = ",".join(COLUMNAS_TAT)
    fila = "2026-09-01,F-10,Minorista,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50"
    csv_completo = "\n".join([encabezado, *([fila] * 5001)]) + "\n"

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        return httpx.Response(200, text=csv_completo)

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://test.local")
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 1)))

    assert len(filas) == 5001
    assert len(llamadas) == 1
    assert llamadas[0].url.params["format"] == "csv"


def test_fuente_tat_consulta_cada_dia_por_separado() -> None:
    llamadas: list[httpx.Request] = []
    encabezado = ",".join(COLUMNAS_TAT)

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append(request)
        fecha = request.url.params["fecha_inicio"]
        fila = f"{fecha},F-10,TAT,C-7,Cliente 7,S-1,Sucursal Norte,Calle 1,4,1250.50"
        return httpx.Response(200, text=f"{encabezado}\n{fila}\n")

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="https://test.local")
    fuente = FuenteVentasTat(
        ConfiguracionTat("https://test.local", SecretStr("secreto")), cliente=cliente
    )

    filas = list(fuente.obtener_ventas(date(2026, 9, 1), date(2026, 9, 3)))

    assert len(filas) == 3
    assert [
        (llamada.url.params["fecha_inicio"], llamada.url.params["fecha_fin"])
        for llamada in llamadas
    ] == [
        ("2026-09-01", "2026-09-01"),
        ("2026-09-02", "2026-09-02"),
        ("2026-09-03", "2026-09-03"),
    ]


def test_listar_tat_lee_fuente_directa_y_filtra_tipo_comercial(
    cliente_http, admin, monkeypatch
) -> None:
    desde = date(2026, 9, 1)
    filas_fuente = [
        LineaTat(
            fecha_documento=desde,
            nro_documento=f"F-{indice:03}",
            tipo_comercial="TAT",
            hora_documento=time(8, 14),
            cliente_factura=None,
            razon_social_cliente="Cliente TAT",
            codigo_sucursal=None,
            descripcion_sucursal="Sucursal",
            direccion_sucursal=None,
            cantidad_inv=Decimal("1"),
            valor_subtotal=Decimal("10.00"),
        )
        for indice in range(101)
    ] + [
        LineaTat(
            fecha_documento=desde,
            nro_documento="F-MINORISTA",
            tipo_comercial="Minorista",
            cliente_factura=None,
            razon_social_cliente="Cliente minorista",
            codigo_sucursal=None,
            descripcion_sucursal="Sucursal",
            direccion_sucursal=None,
            cantidad_inv=Decimal("2"),
            valor_subtotal=Decimal("25.00"),
        )
    ]

    class FuentePrueba:
        def obtener_ventas(self, inicio: date, fin: date) -> list[LineaTat]:
            assert (inicio, fin) == (desde, date(2026, 9, 30))
            return filas_fuente

        def cerrar(self) -> None:
            pass

    monkeypatch.setattr("app.application.services.agro_tat_service.FuenteVentasTat", FuentePrueba)

    parametros = {"fecha_inicio": "2026-09-01", "fecha_fin": "2026-09-30"}
    todas = cliente_http.get("/api/v1/agro/tat", params=parametros, headers=admin)
    assert todas.status_code == 200, todas.text
    assert len(todas.json()["filas"]) == 102
    assert todas.json()["filas"][0]["hora_documento"] == "08:14:00"
    assert todas.json()["tipos_comerciales"] == ["Minorista", "TAT"]

    filtradas = cliente_http.get(
        "/api/v1/agro/tat",
        params={**parametros, "tipo_comercial": "TAT"},
        headers=admin,
    )
    assert filtradas.status_code == 200, filtradas.text
    assert len(filtradas.json()["filas"]) == 101
    assert {fila["tipo_comercial"] for fila in filtradas.json()["filas"]} == {"TAT"}
    assert filtradas.json()["total_cantidad"] == "101.000"
    assert filtradas.json()["total_subtotal"] == "1010.00"
