"""Qué unidades ofrece la instancia, y por qué esa lista no es decorativa.

El selector de marca es lo primero que ve alguien, antes incluso del acceso, y
puede ofrecer una unidad que esta instancia no sirve. Que la elección lleve a
unas pantallas vacías es peor que no ofrecerla: el usuario no tiene forma de
distinguir «no hay datos cargados» de «esta no es su aplicación». Por eso la
lista viaja desde el servidor, que es el único que sabe la respuesta.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings


def _settings(unidad: str) -> Settings:
    return Settings(secret_key="c" * 40, unidad=unidad)  # type: ignore[arg-type]


def test_por_omision_sirve_las_dos_unidades_con_modulo() -> None:
    """Carnes y agropecuaria comparten base: hoy la instancia sirve las dos."""
    assert _settings("todas").unidades_disponibles == ["carnes", "agropecuaria"]


def test_carnes_frias_no_se_ofrece_porque_no_tiene_modulo() -> None:
    """Es una marca sin backend. Ofrecerla llevaría a las pantallas de carnes."""
    assert "carnes-frias" not in _settings("todas").unidades_disponibles


@pytest.mark.parametrize("unidad", ["carnes", "agropecuaria"])
def test_fijada_a_una_unidad_no_ofrece_las_demas(unidad: str) -> None:
    """El día que una unidad se lleve a su propio despliegue, con su propia base.

    Ahí sí es cierto que elegir la otra marca no mostraría nada, y la instancia
    deja de ofrecerla en vez de dejar que alguien lo descubra por su cuenta.
    """
    assert _settings(unidad).unidades_disponibles == [unidad]


def test_la_sonda_publica_la_unidad_sin_pedir_sesion(cliente_http: TestClient) -> None:
    """Público a propósito: el selector va antes del acceso (§6)."""
    cuerpo = cliente_http.get("/api/v1/salud").json()

    assert cuerpo["unidad"] == "todas"
    assert cuerpo["unidades"] == ["carnes", "agropecuaria"]
