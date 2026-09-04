from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domain.enums import Rol
from app.infrastructure.models.usuario import UsuarioPermiso
from tests.conftest import _crear_usuario, autenticar


def _consulta_agro(sesion: Session, cliente_http: TestClient, *permisos: str) -> dict[str, str]:
    usuario = _crear_usuario(sesion, "consulta_agro", Rol.CONSULTA)
    sesion.add_all(UsuarioPermiso(usuario_id=usuario.id, codigo=codigo) for codigo in permisos)
    sesion.commit()
    return autenticar(cliente_http, "consulta_agro")


def test_consulta_agro_tat_no_puede_abrir_resumen(
    cliente_http: TestClient, sesion: Session
) -> None:
    cabeceras = _consulta_agro(sesion, cliente_http, "PERMISO_AGRO_CONSULTAR_TAT")

    tat = cliente_http.get(
        "/api/v1/agro/tat?fecha_inicio=2026-08-01&fecha_fin=2026-08-31", headers=cabeceras
    )
    resumen = cliente_http.get("/api/v1/agro/resumen?por=centro_operacion", headers=cabeceras)

    assert tat.status_code == 200, tat.text
    assert resumen.status_code == 403


def test_consulta_agro_resumen_rechaza_filtro_centro_sin_permiso(
    cliente_http: TestClient, sesion: Session
) -> None:
    cabeceras = _consulta_agro(sesion, cliente_http, "PERMISO_AGRO_CONSULTAR_RESUMEN")

    respuesta = cliente_http.get(
        "/api/v1/agro/resumen?periodo=2026-08&por=centro_operacion&centro=301",
        headers=cabeceras,
    )

    assert respuesta.status_code == 403


def test_exportacion_agro_requiere_permiso_de_descarga(
    cliente_http: TestClient, sesion: Session
) -> None:
    cabeceras = _consulta_agro(sesion, cliente_http, "PERMISO_AGRO_CONSULTAR_RESUMEN")

    respuesta = cliente_http.get(
        "/api/v1/agro/exportar/resumen?periodo=2026-08&por=centro_operacion", headers=cabeceras
    )

    assert respuesta.status_code == 403
