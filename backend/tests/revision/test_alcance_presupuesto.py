"""Revisión: el alcance de JEFE_PDV solo se aplica en `/reportes`."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hashear_password
from app.domain.enums import Rol
from app.infrastructure.models.usuario import Usuario, UsuarioPuntoVenta
from tests.conftest import CLAVE, PERIODO, autenticar, dar_presupuesto, id_punto_venta


def _jefe_de(sesion: Session, cliente_http: TestClient, codigo: str) -> dict[str, str]:
    usuario = Usuario(
        usuario="jefe",
        nombre="Jefe",
        password_hash=hashear_password(CLAVE),
        rol=Rol.JEFE_PDV.value,
        activo=True,
        debe_cambiar_password=False,
    )
    sesion.add(usuario)
    sesion.flush()
    sesion.add(
        UsuarioPuntoVenta(usuario_id=usuario.id, punto_venta_id=id_punto_venta(sesion, codigo))
    )
    sesion.commit()
    return autenticar(cliente_http, "jefe")


def test_jefe_pdv_lee_el_presupuesto_de_toda_la_compania(
    sesion: Session, cliente_http: TestClient
) -> None:
    """`GET /presupuesto` no aplica `alcance_puntos_venta`.

    Escenario: el jefe de MALAMBO (402) pide `/presupuesto?periodo=2026-08` sin
    parámetro `punto_venta`. Recibe el presupuesto de LA 93 y de todos los demás
    puntos: el presupuesto completo de la compañía, que es exactamente el dato
    contra el que se le va a evaluar a él y a sus pares.
    """
    dar_presupuesto(sesion, "402", "RES", "1000000000")
    dar_presupuesto(sesion, "413", "RES", "3500000000")
    dar_presupuesto(sesion, "415", "CERDO", "2200000000")

    cabeceras = _jefe_de(sesion, cliente_http, "402")

    presupuesto = cliente_http.get(
        "/api/v1/presupuesto", params={"periodo": PERIODO}, headers=cabeceras
    ).json()
    historial = cliente_http.get(
        "/api/v1/presupuesto/historial", params={"periodo": PERIODO}, headers=cabeceras
    ).json()
    calendario = cliente_http.get(
        "/api/v1/calendario", params={"periodo": PERIODO}, headers=cabeceras
    ).json()

    print()
    print(f"  /presupuesto devuelve : {[(f['punto_venta'], f['monto']) for f in presupuesto]}")
    print(f"  /presupuesto/historial: {len(historial)} entradas")
    print(f"  /calendario           : {len(calendario)} zonas")

    ajenos = [f for f in presupuesto if f["punto_venta"] != "402"]
    assert ajenos == [], (
        f"el jefe de 402 recibió el presupuesto de {[f['punto_venta'] for f in ajenos]}"
    )
