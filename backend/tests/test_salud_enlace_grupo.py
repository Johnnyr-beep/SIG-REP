"""Contrato de navegación hacia la instancia corporativa aislada."""

from app.api.v1.salud import EstadoSalud


def test_salud_publica_enlace_corporativo_sin_exponer_conexion() -> None:
    respuesta = EstadoSalud(
        estado="operativo",
        unidad="todas",
        unidades=["carnes", "agropecuaria"],
        url_grupo_santacruz="https://grupo.grupo-santacruz.com",
        version="pruebas",
        base_datos="disponible",
    )

    cuerpo = respuesta.model_dump()

    assert cuerpo["url_grupo_santacruz"] == "https://grupo.grupo-santacruz.com"
    assert "db_url_grupo_santacruz" not in cuerpo
