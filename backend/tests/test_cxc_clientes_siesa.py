from __future__ import annotations

from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.api.v1 import financiero as api_financiero
from app.core.deps import unidad_de_peticion
from app.infrastructure.fuentes.cxc_clientes_siesa import (
    COMPANIAS_CXC_CLIENTES,
    RUTA_CXC_CLIENTES,
    CxcClientesCrudo,
    FuenteCxcClientesSiesa,
)
from app.infrastructure.fuentes.siesa import ConfiguracionSiesa


def test_descarga_saldos_cxc_cliente_y_antiguedad() -> None:
    peticiones: list[httpx.Request] = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticiones.append(peticion)
        return httpx.Response(
            200,
            text=(
                "compania,clase_tercero,auxiliar,cliente,naturaleza,total,total_corriente,"
                "total_vencido,total_1_30,total_31_60,total_61_90,total_mas_90\n"
                "3,Cliente,1305050101,CLIENTE DE PRUEBA,Debito,1000,400,600,100,200,200,100\n"
            ),
        )

    configuracion = ConfiguracionSiesa(
        url_base="https://siesa.pruebas.local",
        token=SecretStr("token-solo-de-prueba"),
        companias=COMPANIAS_CXC_CLIENTES,
        reintentos=1,
        espera_reintento_seg=0,
    )
    with httpx.Client(transport=httpx.MockTransport(responder)) as cliente:
        resultado = FuenteCxcClientesSiesa(
            configuracion=configuracion,
            sesion_http=cliente,
        ).leer(fecha_corte=date(2026, 10, 19))

    assert len(peticiones) == 1
    peticion = peticiones[0]
    assert peticion.url.path == RUTA_CXC_CLIENTES
    assert peticion.url.params.get_list("compania") == ["3", "4", "6", "7"]
    assert peticion.url.params["fecha_corte"] == "2026-10-19"
    assert peticion.url.params["format"] == "csv"
    assert "token" not in peticion.url.params
    assert peticion.headers["Authorization"] == "token-solo-de-prueba"
    assert resultado.filas[0]["total_1_30"] == "100"
    assert resultado.filas[0]["total_mas_90"] == "100"


def test_api_cxc_clientes_requiere_acceso_financiero_de_grupo(
    cliente_http: httpx.Client,
    admin: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ruta = "/api/v1/financiero/cxc-clientes?fecha_corte=2026-10-19"
    assert cliente_http.get(ruta).status_code == 401
    assert cliente_http.get(ruta, headers=admin).status_code == 403

    monkeypatch.setitem(
        cliente_http.app.dependency_overrides,
        unidad_de_peticion,
        lambda: "grupo-santacruz",
    )

    class FuenteFalsa:
        def leer(self, fecha_corte: date | None = None) -> CxcClientesCrudo:
            assert fecha_corte == date(2026, 10, 19)
            return CxcClientesCrudo(
                columnas=("compania", "clase_tercero", "total_1_30"),
                filas=({"compania": "3", "clase_tercero": "Cliente", "total_1_30": "100"},),
            )

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(api_financiero, "FuenteCxcClientesSiesa", lambda: FuenteFalsa())
    respuesta = cliente_http.get(ruta, headers=admin)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "fecha_corte": "2026-10-19",
        "columnas": ["compania", "clase_tercero", "total_1_30"],
        "filas": [{"compania": "3", "clase_tercero": "Cliente", "total_1_30": "100"}],
        "total": 1,
    }
