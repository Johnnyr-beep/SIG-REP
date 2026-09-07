"""Aislamiento de la instancia corporativa Grupo Santacruz."""

from fastapi import Request

from app.core.deps import unidad_de_peticion


def test_cabecera_corporativa_resuelve_la_unidad_del_grupo() -> None:
    peticion = Request(
        {
            "type": "http",
            "headers": [(b"x-sigrep-unidad", b"grupo-santacruz")],
        }
    )

    assert unidad_de_peticion(peticion) == "grupo-santacruz"
