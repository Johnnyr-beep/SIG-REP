from __future__ import annotations

from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.api.v1 import financiero as api_financiero
from app.core.deps import unidad_de_peticion
from app.infrastructure.fuentes.cxp_proveedores_siesa import (
    COMPANIAS_CXP_PROVEEDORES,
    RUTA_CXP_PROVEEDORES,
    CxpProveedoresCrudo,
    FuenteCxpProveedoresSiesa,
)
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa


def test_descarga_saldos_cxp_con_companias_y_token_en_header() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(
            200,
            text=(
                "compania,auxiliar,proveedor,nit,total,total_corriente,total_vencido\n"
                "3,1330050103,PROVEEDOR DE PRUEBA,900123456,-2000000,-2000000,0\n"
            ),
        )

    configuracion = ConfiguracionSiesa(
        url_base="https://siesa.pruebas.local",
        token=SecretStr("token-solo-de-prueba"),
        companias=COMPANIAS_CXP_PROVEEDORES,
        reintentos=1,
        espera_reintento_seg=0,
    )
    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        resultado = FuenteCxpProveedoresSiesa(
            configuracion=configuracion,
            sesion_http=cliente,
        ).leer(fecha_corte=date(2026, 10, 19))

    assert len(peticiones) == 1
    peticion = peticiones[0]
    assert peticion.url.path == RUTA_CXP_PROVEEDORES
    assert peticion.url.params.get_list("compania") == ["3", "4", "6", "7"]
    assert peticion.url.params["fecha_corte"] == "2026-10-19"
    assert peticion.url.params["format"] == "csv"
    assert "token" not in peticion.url.params
    assert peticion.headers["Authorization"] == "token-solo-de-prueba"
    assert resultado.columnas == (
        "compania",
        "auxiliar",
        "proveedor",
        "nit",
        "total",
        "total_corriente",
        "total_vencido",
    )
    assert resultado.filas[0]["auxiliar"] == "1330050103"
    assert resultado.filas[0]["proveedor"] == "PROVEEDOR DE PRUEBA"


def test_api_cxp_proveedores_requiere_acceso_financiero_de_grupo(
    cliente_http: httpx.Client,
    admin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ruta = "/api/v1/financiero/cxp-proveedores?fecha_corte=2026-10-19"
    assert cliente_http.get(ruta).status_code == 401
    assert cliente_http.get(ruta, headers=admin).status_code == 403

    monkeypatch.setitem(
        cliente_http.app.dependency_overrides,
        unidad_de_peticion,
        lambda: "grupo-santacruz",
    )

    class FuenteFalsa:
        def leer(self, fecha_corte: date | None = None) -> CxpProveedoresCrudo:
            assert fecha_corte == date(2026, 10, 19)
            return CxpProveedoresCrudo(
                columnas=("compania", "proveedor", "total_vencido"),
                filas=(
                    {
                        "compania": "3",
                        "proveedor": "PROVEEDOR DE PRUEBA",
                        "total_vencido": "500",
                    },
                ),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_financiero, "FuenteCxpProveedoresSiesa", lambda: FuenteFalsa())
    respuesta = cliente_http.get(ruta, headers=admin)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "fecha_corte": "2026-10-19",
        "columnas": ["compania", "proveedor", "total_vencido"],
        "filas": [{"compania": "3", "proveedor": "PROVEEDOR DE PRUEBA", "total_vencido": "500"}],
        "total": 1,
    }
