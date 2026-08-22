"""Restablecer la clave del `admin`, que antes no se podia.

La clave provisional se imprime una sola vez y no se guarda en ninguna parte:
ni en el registro ni en la base, donde solo queda su huella Argon2id. Perderla
dejaba una sola salida, borrar la cuenta a mano en la base, y eso en produccion
lo hace alguien con prisa a las diez de la noche.

`--forzar-clave` no es el comportamiento normal a proposito: restablece una
cuenta que existe, asi que quien lo ejecute por costumbre en el servidor
equivocado deja fuera a quien estuviera dentro.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.infrastructure.models.usuario import Usuario
from app.infrastructure.semilla import crear_administrador


def _admin(sesion: Session) -> Usuario:
    return sesion.query(Usuario).filter_by(usuario="admin").one()


def test_sin_forzar_una_segunda_pasada_no_toca_la_cuenta(sesion: Session) -> None:
    """Es la proteccion de siempre: sembrar dos veces no cierra a nadie fuera."""
    primero = crear_administrador(sesion)
    assert primero is not None
    sesion.flush()

    assert crear_administrador(sesion) is None
    assert _admin(sesion).password_hash == primero[0].password_hash


def test_forzar_cambia_la_clave_y_devuelve_la_nueva(sesion: Session) -> None:
    creado = crear_administrador(sesion)
    assert creado is not None
    huella_vieja = _admin(sesion).password_hash
    sesion.flush()

    restablecido = crear_administrador(sesion, forzar=True)

    assert restablecido is not None
    assert restablecido[1] != creado[1]
    assert _admin(sesion).password_hash != huella_vieja


def test_forzar_desbloquea_la_cuenta(sesion: Session) -> None:
    """Quien pierde la clave suele haberla probado hasta bloquearse.

    Cambiarsela sin desbloquear dejaria la sesion igual de cerrada, con una causa
    nueva que buscar y ninguna pista de que hay dos.
    """
    assert crear_administrador(sesion) is not None
    admin = _admin(sesion)
    admin.intentos_fallidos = 9
    admin.activo = False
    sesion.flush()

    assert crear_administrador(sesion, forzar=True) is not None

    admin = _admin(sesion)
    assert admin.intentos_fallidos == 0
    assert admin.bloqueado_hasta is None
    assert admin.activo is True


def test_la_clave_restablecida_hay_que_cambiarla_al_entrar(sesion: Session) -> None:
    """Una clave que viajo por una terminal no puede quedarse como definitiva."""
    assert crear_administrador(sesion) is not None
    admin = _admin(sesion)
    admin.debe_cambiar_password = False
    sesion.flush()

    assert crear_administrador(sesion, forzar=True) is not None
    assert _admin(sesion).debe_cambiar_password is True


def test_una_clave_dada_a_mano_pasa_por_la_politica(sesion: Session) -> None:
    """Restablecer no es una puerta trasera, y menos la de la cuenta que reparte
    los permisos."""
    import pytest

    from app.core.errors import ErrorValidacion

    assert crear_administrador(sesion) is not None
    sesion.flush()

    with pytest.raises(ErrorValidacion):
        crear_administrador(sesion, "123", forzar=True)
