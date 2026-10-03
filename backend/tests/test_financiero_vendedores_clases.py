import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.fuentes.agro_vendedores_clases import (
    obtener_vendedores_clases,
    parsear_vendedores_clases,
)
from app.infrastructure.fuentes.agropecuaria import ConfiguracionAgro, ErrorFuenteAgro


def test_parsear_catalogo_normaliza_las_clases_requeridas() -> None:
    contenido = (
        "Codigo_Vendedor,Nombre_Vendedor,Clase_Vendedor\n"
        "01,Ana,CCT\n"
        "02,Beto,MAYORISTA\n"
        "03,Camila,MON\n"
        "04,Diego,Oficina\n"
        "05,Elena,TAT\n"
        "06,Fabi,OTRA\n"
    )

    assert parsear_vendedores_clases(contenido) == {
        "01": "CCT",
        "02": "MAY",
        "03": "MON",
        "04": "OFI",
        "05": "TAT",
    }


def test_catalogo_consulta_cia_tres_y_csv() -> None:
    solicitudes: list[httpx.Request] = []

    def responder(solicitud: httpx.Request) -> httpx.Response:
        solicitudes.append(solicitud)
        return httpx.Response(
            200,
            text="codigo_vendedor,clase\n01,CCT\n",
            request=solicitud,
        )

    cliente = httpx.Client(transport=httpx.MockTransport(responder))
    configuracion = ConfiguracionAgro(
        url_base="https://siesa.test",
        token=SecretStr("token-de-prueba"),
    )

    assert obtener_vendedores_clases(configuracion, cliente) == {"01": "CCT"}
    solicitud = solicitudes[0]
    assert solicitud.url.path == "/ventas/vendedores-clases"
    assert solicitud.url.params["cia"] == "3"
    assert solicitud.url.params["format"] == "csv"


def test_catalogo_falla_si_cambia_el_contrato_de_columnas() -> None:
    with pytest.raises(ErrorFuenteAgro, match="columnas reconocibles"):
        parsear_vendedores_clases("vendedor,segmento\n01,CCT\n")
