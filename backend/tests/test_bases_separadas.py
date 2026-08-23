"""Con dos bases, un token de carnes no puede leer agropecuaria. Ni queriendo.

Es la prueba que da sentido a toda la separación. Las demás comprueban que las
consultas están bien escritas; esta comprueba que **aunque estuvieran mal**, la
conexión por la que tendrían que pasar no existe.

El ataque que se fija aquí es concreto y evidente en cuanto se ve: la unidad
viaja en una cabecera para que el inicio de sesión sepa contra qué base
autenticar. Si esa cabecera siguiera mandando después, cualquiera con un token
legítimo de carnes leería agropecuaria añadiendo una línea a su petición. Por eso
el orden es token primero, cabecera solo cuando no hay token.

Las pruebas montan dos bases SQLite de verdad, con **usuarios distintos en cada
una**, que es lo que ocurre en producción desde que las bases se separan.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import obtener_settings
from app.core.db import Base, fabrica_de, motor_de, reiniciar_motores, urls_por_unidad
from app.core.security import decodificar_token, hashear_password
from app.infrastructure.models.usuario import Usuario
from app.main import app
from tests.conftest import CLAVE

CABECERA = "X-SIGREP-Unidad"


def _crear_usuario(unidad: str, nombre: str) -> None:
    with fabrica_de(unidad)() as sesion:  # type: ignore[arg-type]
        sesion.add(
            Usuario(
                usuario=nombre,
                nombre=nombre.title(),
                email=f"{nombre}@pruebas.local",
                password_hash=hashear_password(CLAVE),
                rol="ADMIN",
                activo=True,
                debe_cambiar_password=False,
            )
        )
        sesion.commit()


@pytest.fixture
def dos_bases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Dos bases distintas, cada una con **su propio** usuario.

    Que los usuarios sean distintos no es un detalle de la prueba: es la
    consecuencia real de separar las bases. La tabla de cuentas se duplica, y el
    `admin` de una compañía no existe en la otra.
    """
    carnes = tmp_path / "carnes.db"
    agro = tmp_path / "agro.db"

    monkeypatch.setenv("SIGREP_DB_URL_OVERRIDE", f"sqlite:///{carnes}")
    monkeypatch.setenv("SIGREP_DB_URL_AGRO", f"sqlite:///{agro}")
    obtener_settings.cache_clear()
    reiniciar_motores()

    for unidad in ("carnes", "agropecuaria"):
        Base.metadata.create_all(motor_de(unidad))  # type: ignore[arg-type]

    _crear_usuario("carnes", "jefe_carnes")
    _crear_usuario("agropecuaria", "jefe_agro")

    with TestClient(app) as cliente:
        yield cliente

    reiniciar_motores()
    obtener_settings.cache_clear()


def _entrar(cliente: TestClient, usuario: str, unidad: str) -> tuple[int, dict]:
    respuesta = cliente.post(
        "/api/v1/auth/acceso",
        json={"usuario": usuario, "clave": CLAVE},
        headers={CABECERA: unidad},
    )
    return respuesta.status_code, respuesta.json()


# ── Que las bases son de verdad dos ───────────────────────────────────────────


def test_cada_unidad_apunta_a_una_direccion_distinta(dos_bases: TestClient) -> None:
    urls = urls_por_unidad()

    assert urls["carnes"] != urls["agropecuaria"]
    assert obtener_settings().bases_separadas is True


def test_sin_la_variable_las_dos_comparten_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """El estado anterior a la separación sigue siendo válido y explícito.

    Permite desplegar este código antes de crear la segunda base, y volver atrás
    borrando una variable en vez de revirtiendo un despliegue.
    """
    monkeypatch.delenv("SIGREP_DB_URL_AGRO", raising=False)
    obtener_settings.cache_clear()
    try:
        urls = urls_por_unidad()
        assert urls["carnes"] == urls["agropecuaria"]
        assert obtener_settings().bases_separadas is False
    finally:
        obtener_settings.cache_clear()


# ── El acceso va contra la base que dice la cabecera ──────────────────────────


def test_cada_usuario_entra_solo_por_su_unidad(dos_bases: TestClient) -> None:
    """El de carnes no existe en agropecuaria, y al revés. Son bases distintas."""
    assert _entrar(dos_bases, "jefe_carnes", "carnes")[0] == 200
    assert _entrar(dos_bases, "jefe_agro", "agropecuaria")[0] == 200

    assert _entrar(dos_bases, "jefe_carnes", "agropecuaria")[0] == 401
    assert _entrar(dos_bases, "jefe_agro", "carnes")[0] == 401


def test_el_token_nace_sellado_con_su_unidad(dos_bases: TestClient) -> None:
    """Sellado y firmado: el cliente no puede reescribirlo."""
    _, cuerpo = _entrar(dos_bases, "jefe_agro", "agropecuaria")
    datos = decodificar_token(cuerpo["token_acceso"])

    assert datos.unidad == "agropecuaria"
    assert datos.usuario == "jefe_agro"


# ── El ataque: la cabecera no manda cuando hay token ──────────────────────────


def test_un_token_de_carnes_no_lee_agropecuaria_aunque_mande_la_cabecera(
    dos_bases: TestClient,
) -> None:
    """**La prueba central de toda la separación.**

    Con un token válido de carnes y la cabecera de agropecuaria, la petición
    tiene que resolverse contra carnes. Si la cabecera ganara, cualquiera con
    credenciales legítimas de una compañía leería las cifras de la otra
    añadiendo una línea a su petición.
    """
    _, cuerpo = _entrar(dos_bases, "jefe_carnes", "carnes")
    autorizacion = {"Authorization": f"Bearer {cuerpo['token_acceso']}"}

    perfil = dos_bases.get(
        "/api/v1/auth/yo",
        headers={**autorizacion, CABECERA: "agropecuaria"},
    )

    assert perfil.status_code == 200
    # Resolvió contra carnes: en la base de agropecuaria ese usuario no existe,
    # así que verlo devuelto es la prueba de que no se cambió de base.
    assert perfil.json()["usuario"] == "jefe_carnes"


def test_el_token_de_agropecuaria_tampoco_se_desvia_a_carnes(dos_bases: TestClient) -> None:
    """La regla vale en las dos direcciones; no es una defensa de una sola cara."""
    _, cuerpo = _entrar(dos_bases, "jefe_agro", "agropecuaria")

    perfil = dos_bases.get(
        "/api/v1/auth/yo",
        headers={"Authorization": f"Bearer {cuerpo['token_acceso']}", CABECERA: "carnes"},
    )

    assert perfil.status_code == 200
    assert perfil.json()["usuario"] == "jefe_agro"


def test_sin_cabecera_ni_token_se_atiende_a_carnes(dos_bases: TestClient) -> None:
    """Una sonda o un balanceador no saben de unidades, y no tienen por qué."""
    respuesta = dos_bases.post(
        "/api/v1/auth/acceso", json={"usuario": "jefe_carnes", "clave": CLAVE}
    )

    assert respuesta.status_code == 200


def test_una_cabecera_inventada_no_abre_ninguna_puerta(dos_bases: TestClient) -> None:
    """Un valor desconocido cae a carnes, no a «la última que se pidió»."""
    respuesta = dos_bases.post(
        "/api/v1/auth/acceso",
        json={"usuario": "jefe_agro", "clave": CLAVE},
        headers={CABECERA: "../agropecuaria"},
    )

    assert respuesta.status_code == 401


# ── Renovar no cambia de compañía ─────────────────────────────────────────────


def test_refrescar_conserva_la_unidad_del_token_presentado(dos_bases: TestClient) -> None:
    """La unidad sale del refresco, no de la petición.

    Si saliera de la cabecera, un refresco de carnes serviría para obtener un
    acceso a agropecuaria: la separación se rompería en la renovación, que es
    justo donde nadie mira.
    """
    _, cuerpo = _entrar(dos_bases, "jefe_agro", "agropecuaria")

    renovado = dos_bases.post(
        "/api/v1/auth/refrescar",
        json={"token_refresco": cuerpo["token_refresco"]},
        headers={CABECERA: "carnes"},
    )

    assert renovado.status_code == 200
    assert decodificar_token(renovado.json()["token_acceso"]).unidad == "agropecuaria"


def test_refrescar_busca_al_usuario_en_la_base_de_su_unidad(dos_bases: TestClient) -> None:
    """Y no solo sella bien la unidad: **lee la base correcta**.

    Comprobar solo el sello es lo que dejó pasar el fallo. El refresco viaja en
    el cuerpo, así que la dependencia de sesión no lo veía y abría la de carnes;
    allí el `id` 1 es `jefe_carnes` y no `jefe_agro`, de modo que la renovación
    salía a nombre del usuario de la otra compañía con el sello correcto encima.
    """
    _, cuerpo = _entrar(dos_bases, "jefe_agro", "agropecuaria")

    renovado = dos_bases.post(
        "/api/v1/auth/refrescar", json={"token_refresco": cuerpo["token_refresco"]}
    )

    assert renovado.status_code == 200
    assert decodificar_token(renovado.json()["token_acceso"]).usuario == "jefe_agro"


def test_desactivar_una_cuenta_le_cierra_la_renovacion(dos_bases: TestClient) -> None:
    """Y se comprueba en **su** base, que es donde alguien la desactiva.

    Con la comprobación hecha contra carnes, desactivar a `jefe_agro` en su
    compañía no le cerraba nada: seguía renovando mientras el usuario que ocupa
    ese mismo `id` en la otra base siguiera activo.
    """
    _, cuerpo = _entrar(dos_bases, "jefe_agro", "agropecuaria")

    sesion: Session
    with fabrica_de("agropecuaria")() as sesion:  # type: ignore[arg-type]
        sesion.query(Usuario).filter_by(usuario="jefe_agro").one().activo = False
        sesion.commit()

    renovado = dos_bases.post(
        "/api/v1/auth/refrescar", json={"token_refresco": cuerpo["token_refresco"]}
    )

    assert renovado.status_code == 401


# ── Los datos tampoco se ven entre sí ─────────────────────────────────────────


def test_lo_escrito_en_una_base_no_aparece_en_la_otra(dos_bases: TestClient) -> None:
    """La comprobación de fondo, sin pasar por HTTP: son dos archivos distintos."""

    def usuarios(unidad: str) -> set[str]:
        sesion: Session
        with fabrica_de(unidad)() as sesion:  # type: ignore[arg-type]
            return {u.usuario for u in sesion.query(Usuario).all()}

    assert usuarios("carnes") == {"jefe_carnes"}
    assert usuarios("agropecuaria") == {"jefe_agro"}
