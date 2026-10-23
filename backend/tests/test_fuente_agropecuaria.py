from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import SecretStr

from app.infrastructure.fuentes.agropecuaria import ConfiguracionAgro, FuenteVentaAgropecuaria


def fuente() -> FuenteVentaAgropecuaria:
    configuracion = ConfiguracionAgro(
        url_base="https://siesa.pruebas.local",
        token=SecretStr("token-solo-de-prueba"),
        reintentos=1,
        espera_reintento_seg=0,
    )
    return FuenteVentaAgropecuaria(configuracion=configuracion)


def registro(**sobrescribir: str) -> dict[str, str]:
    fila = {
        "fecha": "2026-10-01",
        "co_id": "301",
        "tipoitem": "0001 - BIENES",
        "cantidadinv": "2",
        "kilostotal": "2",
        "valorbruto": "1000",
        "descuentos": "0",
        "valorsubtotal": "1000",
        "totalneto": "1000",
        "utilidadbruta": "400",
    }
    fila.update(sobrescribir)
    return fila


def linea_agro(fila: dict[str, str]) -> Decimal | None:
    linea = fuente()._formar_linea(fila, date(2026, 10, 1), date(2026, 10, 31))
    assert linea is not None
    return linea.total_costo


def test_reconstruye_costo_desde_total_neto_y_utilidad_bruta() -> None:
    assert linea_agro(registro()) == Decimal("600.00")


def test_utilidad_bruta_define_costo_aunque_total_costo_discrepe() -> None:
    assert linea_agro(registro(totalcosto="100")) == Decimal("600.00")


def test_total_costo_explicito_se_usa_si_falta_utilidad_bruta() -> None:
    assert linea_agro(registro(totalcosto="0", utilidadbruta="")) == Decimal("0.00")


def test_costo_sigue_desconocido_si_faltan_total_costo_y_utilidad() -> None:
    assert linea_agro(registro(utilidadbruta="")) is None
