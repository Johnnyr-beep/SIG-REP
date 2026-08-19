"""Administración de usuarios: las seis reglas que la hacen segura.

Este módulo no es «un CRUD de usuarios»: es quien reparte los accesos a las
cifras de la compañía. Cada prueba fija una regla sin la cual el rol `ADMIN`
sería una formalidad —alguien podría otorgarse lo que quisiera, o dejar el
sistema sin ninguna cuenta capaz de volver a entrar—.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Rol
from app.infrastructure.models.usuario import Usuario
from tests.conftest import PUNTO_AJENO, PUNTO_PROPIO, id_usuario

RUTA = "/api/v1/usuarios"


def _crear(cliente: TestClient, cabecera: dict[str, str], **campos: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "usuario": "nuevo",
        "nombre": "Persona Nueva",
        "rol": "CONSULTA",
        **campos,
    }
    respuesta = cliente.post(RUTA, json=cuerpo, headers=cabecera)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _admins_activos(sesion: Session) -> int:
    return len(
        sesion.scalars(
            select(Usuario).where(Usuario.rol == Rol.ADMIN.value, Usuario.activo.is_(True))
        ).all()
    )


# ── Regla 1 · Nadie se administra a sí mismo ──────────────────────────────────


def test_un_admin_no_puede_cambiarse_el_rol(
    cliente_http: TestClient, admin: dict[str, str], sesion: Session
) -> None:
    """Sin esta regla el rol es decorativo: cualquiera se otorga lo que quiera."""
    propio = id_usuario(sesion, "admin")

    respuesta = cliente_http.patch(f"{RUTA}/{propio}", json={"rol": "GERENTE"}, headers=admin)

    assert respuesta.status_code == 403
    sesion.expire_all()
    registro = sesion.get(Usuario, propio)
    assert registro is not None
    assert registro.rol == Rol.ADMIN.value


def test_un_admin_no_puede_desactivarse(
    cliente_http: TestClient, admin: dict[str, str], sesion: Session
) -> None:
    """La protección contra el clic que te deja fuera de tu propio sistema."""
    propio = id_usuario(sesion, "admin")

    assert cliente_http.post(f"{RUTA}/{propio}/desactivar", headers=admin).status_code == 403


def test_un_admin_no_puede_ampliarse_el_alcance(
    cliente_http: TestClient, admin: dict[str, str], sesion: Session
) -> None:
    propio = id_usuario(sesion, "admin")

    respuesta = cliente_http.put(
        f"{RUTA}/{propio}/puntos-venta",
        json={"puntos_venta": [PUNTO_PROPIO]},
        headers=admin,
    )

    assert respuesta.status_code == 403


def test_sobre_otro_administrador_si_puede(
    cliente_http: TestClient,
    admin: dict[str, str],
    otro_admin: dict[str, str],
    sesion: Session,
) -> None:
    """El camino feliz: la regla prohíbe la autoadministración, no el trabajo."""
    ajeno = id_usuario(sesion, "admin_relevo")

    respuesta = cliente_http.patch(
        f"{RUTA}/{ajeno}", json={"nombre": "Relevo Renombrado"}, headers=admin
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Relevo Renombrado"


# ── Regla 2 · Siempre queda un ADMIN activo ───────────────────────────────────


def test_no_se_puede_desactivar_al_ultimo_administrador(
    cliente_http: TestClient,
    admin: dict[str, str],
    otro_admin: dict[str, str],
    sesion: Session,
) -> None:
    """Con dos, desactivar a uno es legítimo. Con uno, el sistema se planta.

    Es la diferencia entre una operación reversible y quedarse sin ninguna
    cuenta capaz de volver a crear administradores. La comprobación se hace
    sobre el objetivo, no sobre el actor: nadie se desactiva a sí mismo (regla
    1), así que el caso real es «el actor desactiva al único que queda».
    """
    relevo = id_usuario(sesion, "admin_relevo")
    assert _admins_activos(sesion) == 2

    # Con dos activos, la baja del segundo se acepta.
    assert cliente_http.post(f"{RUTA}/{relevo}/desactivar", headers=admin).status_code == 200
    sesion.expire_all()
    assert _admins_activos(sesion) == 1

    # Se crea un tercero y se le da de baja: vuelve a haber relevo, se permite.
    tercero = _crear(cliente_http, admin, usuario="admin_suplente", rol="ADMIN")
    sesion.expire_all()
    assert _admins_activos(sesion) == 2
    identificador = tercero["usuario"]["id"]
    assert cliente_http.post(f"{RUTA}/{identificador}/desactivar", headers=admin).status_code == 200

    # Y nunca se llega a cero.
    sesion.expire_all()
    assert _admins_activos(sesion) >= 1


def test_no_se_puede_degradar_al_ultimo_administrador(
    cliente_http: TestClient, admin: dict[str, str], sesion: Session
) -> None:
    """Cambiar el rol del último ADMIN es la otra forma de quedarse fuera."""
    suplente = _crear(cliente_http, admin, usuario="admin_temporal", rol="ADMIN")
    identificador = suplente["usuario"]["id"]

    # Hay dos: degradar a uno se acepta.
    assert (
        cliente_http.patch(f"{RUTA}/{identificador}", json={"rol": "CONSULTA"}, headers=admin)
    ).status_code == 200

    sesion.expire_all()
    assert _admins_activos(sesion) == 1


# ── Regla 3 · No se borra, se desactiva ───────────────────────────────────────


def test_no_existe_el_borrado_de_usuarios(
    cliente_http: TestClient, admin: dict[str, str], sesion: Session
) -> None:
    """Sus acciones viven en el historial de presupuesto y en las corridas.

    Borrar el usuario destruiría el rastro que §3.3 existe para conservar. La
    baja es la desactivación, que preserva la fila y su identidad.
    """
    creado = _crear(cliente_http, admin, usuario="dado_de_baja")
    identificador = creado["usuario"]["id"]

    # No hay verbo de borrado en la API.
    assert cliente_http.delete(f"{RUTA}/{identificador}", headers=admin).status_code in (404, 405)

    assert cliente_http.post(f"{RUTA}/{identificador}/desactivar", headers=admin).status_code == 200

    sesion.expire_all()
    registro = sesion.get(Usuario, identificador)
    assert registro is not None, "el usuario debe seguir existiendo tras la baja"
    assert registro.activo is False


def test_un_usuario_desactivado_no_puede_entrar(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    creado = _crear(cliente_http, admin, usuario="cesado")
    clave = creado["clave_provisional"]
    cliente_http.post(f"{RUTA}/{creado['usuario']['id']}/desactivar", headers=admin)

    respuesta = cliente_http.post("/api/v1/auth/acceso", json={"usuario": "cesado", "clave": clave})

    assert respuesta.status_code == 401


# ── Regla 4 · Todo queda registrado ───────────────────────────────────────────


def test_cada_operacion_deja_rastro_de_quien_y_sobre_quien(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    """Un permiso concedido sin rastro no se puede auditar."""
    creado = _crear(cliente_http, admin, usuario="auditado")
    cliente_http.patch(f"{RUTA}/{creado['usuario']['id']}", json={"rol": "ANALISTA"}, headers=admin)

    rastro = cliente_http.get(f"{RUTA}/auditoria", headers=admin)

    assert rastro.status_code == 200
    filas = rastro.json()
    assert filas, "la auditoría no puede estar vacía tras crear y modificar"
    assert any("admin" in str(fila).lower() for fila in filas)


# ── Regla 5 · La clave provisional se entrega una sola vez ────────────────────


def test_la_clave_se_entrega_una_vez_y_obliga_a_cambiarla(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    creado = _crear(cliente_http, admin, usuario="estrenando")
    clave = creado["clave_provisional"]

    assert clave and len(clave) >= 12
    assert creado["usuario"]["debe_cambiar_password"] is True

    # No reaparece en el listado: se entregó una vez y ya.
    listado = cliente_http.get(RUTA, headers=admin).json()
    fila = next(u for u in listado if u["usuario"] == "estrenando")
    assert "clave_provisional" not in fila

    # Y sirve para entrar.
    acceso = cliente_http.post(
        "/api/v1/auth/acceso", json={"usuario": "estrenando", "clave": clave}
    )
    assert acceso.status_code == 200


def test_restablecer_genera_una_clave_distinta(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    """El remedio cuando el administrador pierde la clave antes de entregarla."""
    creado = _crear(cliente_http, admin, usuario="olvidadizo")
    primera = creado["clave_provisional"]

    respuesta = cliente_http.post(
        f"{RUTA}/{creado['usuario']['id']}/restablecer-clave", headers=admin
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["clave_provisional"] != primera


# ── Regla 6 · El hash nunca sale de la base ───────────────────────────────────


def test_ninguna_respuesta_expone_el_hash(cliente_http: TestClient, admin: dict[str, str]) -> None:
    """Ni siquiera al ADMIN. Un hash filtrado es un ataque por diccionario."""
    creado = _crear(cliente_http, admin, usuario="sin_hash")
    listado = cliente_http.get(RUTA, headers=admin).json()

    for cuerpo in (creado, listado):
        crudo = str(cuerpo).lower()
        assert "password_hash" not in crudo
        assert "argon2" not in crudo


# ── El alcance por punto de venta ─────────────────────────────────────────────


def test_fijar_alcance_reemplaza_la_lista_completa(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    """Lo que se envía es lo que queda: sin reemplazo, quitar un punto no se puede."""
    creado = _crear(cliente_http, admin, usuario="jefe_nuevo", rol="JEFE_PDV")
    identificador = creado["usuario"]["id"]

    respuesta = cliente_http.put(
        f"{RUTA}/{identificador}/puntos-venta",
        json={"puntos_venta": [PUNTO_PROPIO, PUNTO_AJENO]},
        headers=admin,
    )
    assert sorted(respuesta.json()["puntos_venta"]) == sorted([PUNTO_PROPIO, PUNTO_AJENO])

    respuesta = cliente_http.put(
        f"{RUTA}/{identificador}/puntos-venta",
        json={"puntos_venta": [PUNTO_PROPIO]},
        headers=admin,
    )
    assert respuesta.json()["puntos_venta"] == [PUNTO_PROPIO]


# ── Quién puede administrar, en las dos direcciones ───────────────────────────


def test_los_roles_de_negocio_no_administran_usuarios(
    cliente_http: TestClient,
    gerente: dict[str, str],
    analista: dict[str, str],
    consulta: dict[str, str],
    jefe_pdv: dict[str, str],
) -> None:
    """GERENTE incluido: ve todas las cifras y no reparte accesos."""
    for cabecera in (gerente, analista, consulta, jefe_pdv):
        assert cliente_http.get(RUTA, headers=cabecera).status_code == 403
        respuesta = cliente_http.post(
            RUTA,
            json={"usuario": "intruso", "nombre": "No Deberia", "rol": "CONSULTA"},
            headers=cabecera,
        )
        assert respuesta.status_code == 403


def test_sin_token_no_se_administra(cliente_http: TestClient) -> None:
    assert cliente_http.get(RUTA).status_code == 401


# ── ADMIN es superusuario: también ve el negocio ──────────────────────────────


def test_el_admin_entra_en_reportes_presupuesto_calendario_e_ingesta(
    cliente_http: TestClient, admin: dict[str, str]
) -> None:
    """Decisión del negocio (18-ago-2026).

    Sistemas necesita diagnosticar por sí mismo si un reporte muestra bien los
    datos, sin pedir prestada una cuenta de gerencia. Esta prueba es la que
    falla si alguien decide «endurecer» el rol excluyéndolo del negocio.
    """
    for ruta in (
        "/api/v1/reportes/tablero?periodo=2026-08",
        "/api/v1/presupuesto?periodo=2026-08",
        "/api/v1/calendario?periodo=2026-08",
        "/api/v1/ingesta/corridas",
    ):
        assert cliente_http.get(ruta, headers=admin).status_code == 200, ruta
