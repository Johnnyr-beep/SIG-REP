from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.api.v1 import inventario as api_inventario
from app.infrastructure.fuentes.inventario_siesa import (
    PARAMETROS_INVENTARIO_PDV,
    RUTA_INVENTARIO_PDV,
    FuenteInventarioPdvSiesa,
    InventarioPdvCrudo,
)
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa, ErrorFuenteSiesa
from tests.conftest import PUNTO_AJENO, PUNTO_PROPIO


def configuracion() -> ConfiguracionSiesa:
    return ConfiguracionSiesa(
        url_base="https://siesa.pruebas.local",
        token=SecretStr("token-solo-de-prueba"),
        companias=(4, 6, 7),
        reintentos=1,
        espera_reintento_seg=0,
    )


def test_descarga_todas_las_paginas_json_del_inventario_pdv() -> None:
    peticiones: list[httpx.Request] = []
    fila_malambo = {
        "Compania": 4,
        "CO_Codigo": "402",
        "CO_Descripcion": "PDV MALAMBO",
        "Bodega_Codigo": "40201",
        "Bodega_Descripcion": "PDV MALAMBO VITRINA",
        "Item_Codigo": 3665,
        "Item_Referencia": "3203",
        "Item_Descripcion": "CANUTA DE RES POR KILO",
        "UM": "KG",
        "Cant_Existencia": 2.2,
        "Cant_Comprometida": 0,
    }
    fila_otro_producto = {**fila_malambo, "Item_Codigo": 3666, "Item_Referencia": "3204"}

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        offset = int(peticion.url.params["offset"])
        if offset == 0:
            return httpx.Response(
                200,
                json={
                    "total": 2,
                    "limit": 5000,
                    "offset": 0,
                    "count": 1,
                    "has_more": True,
                    "next_offset": 5000,
                    "data": [fila_malambo],
                },
            )
        return httpx.Response(
            200,
            json={
                "total": 2,
                "limit": 5000,
                "offset": offset,
                "count": 1,
                "has_more": False,
                "next_offset": None,
                "data": [fila_otro_producto],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        fuente = FuenteInventarioPdvSiesa(configuracion=configuracion(), sesion_http=cliente)
        resultado = fuente.leer()

    assert len(peticiones) == 2
    assert [peticion.url.path for peticion in peticiones] == [RUTA_INVENTARIO_PDV] * 2
    assert [peticion.url.params["offset"] for peticion in peticiones] == ["0", "5000"]
    for peticion in peticiones:
        assert peticion.url.params["limit"] == PARAMETROS_INVENTARIO_PDV["limit"]
        assert "token" not in peticion.url.params
        assert peticion.headers["Authorization"] == "token-solo-de-prueba"
    assert resultado.columnas == (
        "Compania",
        "CO_Codigo",
        "CO_Descripcion",
        "Bodega_Codigo",
        "Bodega_Descripcion",
        "Item_Codigo",
        "Item_Referencia",
        "Item_Descripcion",
        "UM",
        "Cant_Existencia",
        "Cant_Comprometida",
    )
    assert len(resultado.filas) == 2
    assert resultado.filas[0] == {
        "Compania": "4",
        "CO_Codigo": "402",
        "CO_Descripcion": "PDV MALAMBO",
        "Bodega_Codigo": "40201",
        "Bodega_Descripcion": "PDV MALAMBO VITRINA",
        "Item_Codigo": "3665",
        "Item_Referencia": "3203",
        "Item_Descripcion": "CANUTA DE RES POR KILO",
        "UM": "KG",
        "Cant_Existencia": "2.2",
        "Cant_Comprometida": "0",
    }


def test_inventario_preserva_campos_vacios_como_null() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "has_more": False,
                "next_offset": None,
                "data": [{"cia": 4, "id_co": 402, "referencia": None}],
            },
        )
    )
    with httpx.Client(transport=transport) as cliente:
        resultado = FuenteInventarioPdvSiesa(
            configuracion=configuracion(), sesion_http=cliente
        ).leer()

    assert resultado.filas[0]["referencia"] is None


def test_inventario_rechaza_respuesta_json_invalida() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text=""))
    with httpx.Client(transport=transport) as cliente:
        fuente = FuenteInventarioPdvSiesa(configuracion=configuracion(), sesion_http=cliente)

        with pytest.raises(ErrorFuenteSiesa, match=r"JSON.*no es válida"):
            fuente.leer()


def test_error_http_no_refleja_cuerpo_ni_token() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text="token-filtrado"))
    with httpx.Client(transport=transport) as cliente:
        fuente = FuenteInventarioPdvSiesa(configuracion=configuracion(), sesion_http=cliente)

        with pytest.raises(ErrorFuenteSiesa) as error:
            fuente.leer()

    assert "token-filtrado" not in str(error.value)
    assert "token-solo-de-prueba" not in str(error.value)


def test_api_inventario_filtra_por_alcance_de_jefe_pdv(
    cliente_http: httpx.Client,
    estructura: None,
    jefe_pdv: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            return InventarioPdvCrudo(
                columnas=(
                    "COMPAÑÍA",
                    "PDV CODIGO",
                    "PDV DESCRIPCION",
                    "ITEM REFERENCIA",
                    "CANT EXISTENCIA",
                ),
                filas=(
                    {
                        "COMPAÑÍA": "4",
                        "PDV CODIGO": "TPV402001",
                        "PDV DESCRIPCION": "PDV MALAMBO",
                        "ITEM REFERENCIA": "A",
                        "CANT EXISTENCIA": "2",
                    },
                    {
                        "COMPAÑÍA": "4",
                        "PDV CODIGO": "TPV413001",
                        "PDV DESCRIPCION": "PDV LA 93",
                        "ITEM REFERENCIA": "B",
                        "CANT EXISTENCIA": "8",
                    },
                ),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_inventario, "FuenteInventarioPdvSiesa", FuenteFalsa)

    respuesta = cliente_http.get("/api/v1/inventario/pdv", headers=jefe_pdv)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["filas"][0]["referencia"] == "A"
    assert cuerpo["filas"][0]["existencia"] == "2"
    assert "punto_venta_codigo" not in cuerpo["filas"][0]


def test_api_inventario_consolida_lineas_del_mismo_pdv(
    cliente_http: httpx.Client,
    estructura: None,
    admin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            return InventarioPdvCrudo(
                columnas=(
                    "cia",
                    "PDV Codigo",
                    "PUNTO DE VENTA",
                    "tpv",
                    "Item Codigo",
                    "Item Referencia",
                    "Item Descripcion",
                    "UM",
                    "CostoPromedio",
                    "Cant Existencia",
                    "Cant Comprometida",
                ),
                filas=(
                    {
                        "cia": "4",
                        "PDV Codigo": PUNTO_PROPIO,
                        "PUNTO DE VENTA": "MALAMBO",
                        "tpv": "T1",
                        "Item Codigo": "2529",
                        "Item Referencia": "10039",
                        "Item Descripcion": "COSTILLA CORRIENTE",
                        "UM": "KG",
                        "CostoPromedio": "23403.2800",
                        "Cant Existencia": "1.234,50",
                        "Cant Comprometida": "2",
                    },
                    {
                        "cia": "4",
                        "PDV Codigo": PUNTO_PROPIO,
                        "PUNTO DE VENTA": "MALAMBO",
                        "tpv": "T2",
                        "Item Codigo": "2530",
                        "Item Referencia": "10040",
                        "Item Descripcion": "COSTILLA ESPECIAL",
                        "UM": "KG",
                        "CostoPromedio": "100.0000",
                        "Cant Existencia": "5",
                        "Cant Comprometida": "1",
                    },
                    {
                        "cia": "4",
                        "PDV Codigo": PUNTO_AJENO,
                        "PUNTO DE VENTA": "LA93",
                        "tpv": "T3",
                        "Item Codigo": "2529",
                        "Item Referencia": "10039",
                        "Item Descripcion": "COSTILLA CORRIENTE",
                        "UM": "KG",
                        "CostoPromedio": "23403.2800",
                        "Cant Existencia": "3",
                        "Cant Comprometida": "0",
                    },
                ),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_inventario, "FuenteInventarioPdvSiesa", FuenteFalsa)

    respuesta = cliente_http.get("/api/v1/inventario/pdv", headers=admin)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 3
    assert cuerpo["columnas"] == [
        "punto_venta",
        "codigo_producto",
        "referencia",
        "producto",
        "unidad",
        "existencia",
        "comprometida",
        "CostoPromedio",
    ]
    costillas = [fila for fila in cuerpo["filas"] if fila["referencia"] == "10039"]
    assert len(costillas) == 2
    por_pdv = {fila["punto_venta"]: fila for fila in costillas}
    malambo = por_pdv["MALAMBO"]
    la93 = por_pdv["LA93"]
    for fila in costillas:
        assert fila["codigo_producto"] == "2529"
        assert fila["producto"] == "COSTILLA CORRIENTE"
        assert fila["unidad"] == "KG"
        assert fila["datos"]["CostoPromedio"] == "23403.2800"
        assert "tpv" not in fila["datos"]
        assert "punto_venta_codigo" not in fila
    assert malambo["existencia"] == "1234.50"
    assert malambo["comprometida"] == "2"
    assert la93["existencia"] == "3"
    assert la93["comprometida"] == "0"


def test_api_mapea_bodega_de_malambo_al_punto_de_venta(
    cliente_http: httpx.Client,
    estructura: None,
    admin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            return InventarioPdvCrudo(
                columnas=(
                    "Compania",
                    "CO_Codigo",
                    "CO_Descripcion",
                    "Bodega_Codigo",
                    "Bodega_Descripcion",
                    "Item_Codigo",
                    "Item_Referencia",
                    "Item_Descripcion",
                    "UM",
                    "Cant_Existencia",
                    "Cant_Comprometida",
                    "Cant_Pend_Entrar",
                    "Cant_Pend_Salir",
                    "Costo_Prom_Unit",
                    "Costo_Prom_Total",
                    "Fecha_Ult_Entrada",
                    "Fecha_Ult_Salida",
                ),
                filas=(
                    {
                        "Compania": "4",
                        "CO_Codigo": "402",
                        "CO_Descripcion": "PDV MALAMBO",
                        "Bodega_Codigo": "40201",
                        "Bodega_Descripcion": "PDV MALAMBO VITRINA",
                        "Item_Codigo": "3665",
                        "Item_Referencia": "3203",
                        "Item_Descripcion": "CANUTA DE RES POR KILO",
                        "UM": "KG",
                        "Cant_Existencia": "2.2",
                        "Cant_Comprometida": "0",
                        "Cant_Pend_Entrar": "0",
                        "Cant_Pend_Salir": "0",
                        "Costo_Prom_Unit": "6000",
                        "Costo_Prom_Total": "13200",
                        "Fecha_Ult_Entrada": "2026-10-03T00:00:00",
                        "Fecha_Ult_Salida": "2026-09-30T00:00:00",
                    },
                ),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_inventario, "FuenteInventarioPdvSiesa", FuenteFalsa)
    respuesta = cliente_http.get("/api/v1/inventario/pdv", headers=admin)

    assert respuesta.status_code == 200, respuesta.text
    fila = respuesta.json()["filas"][0]
    assert fila["punto_venta"] == "MALAMBO"
    assert fila["codigo_producto"] == "3665"
    assert fila["referencia"] == "3203"
    assert fila["producto"] == "CANUTA DE RES POR KILO"
    assert fila["existencia"] == "2.2"
    assert fila["comprometida"] == "0"
    assert "Bodega_Codigo" not in fila["datos"]


def test_api_inventario_no_abre_datos_a_jefe_sin_alcance(
    cliente_http: httpx.Client,
    estructura: None,
    jefe_sin_alcance: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            return InventarioPdvCrudo(
                columnas=("id_co", "referencia", "existencia"),
                filas=({"id_co": PUNTO_PROPIO, "referencia": "A", "existencia": "2"},),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_inventario, "FuenteInventarioPdvSiesa", FuenteFalsa)

    respuesta = cliente_http.get("/api/v1/inventario/pdv", headers=jefe_sin_alcance)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["filas"] == []


def test_api_inventario_falla_cerrado_si_csv_no_identifica_el_pdv(
    cliente_http: httpx.Client,
    estructura: None,
    jefe_pdv: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            return InventarioPdvCrudo(
                columnas=("referencia", "existencia"),
                filas=({"referencia": "A", "existencia": "2"},),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_inventario, "FuenteInventarioPdvSiesa", FuenteFalsa)

    respuesta = cliente_http.get("/api/v1/inventario/pdv", headers=jefe_pdv)

    assert respuesta.status_code == 502
    assert "no se puede aplicar el alcance" in respuesta.json()["detalle"]
