from __future__ import annotations

import sys
from contextlib import nullcontext

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure import semilla
from app.infrastructure.models.organizacion import PuntoVenta


def test_semilla_grupo_carga_y_completa_descripciones_siesa(sesion: Session, monkeypatch) -> None:
    punto_existente = PuntoVenta(
        codigo_co="402",
        nombre="MALAMBO",
        descripcion_siesa=None,
        activo=True,
        presupuestado=True,
    )
    sesion.add(punto_existente)
    sesion.flush()

    monkeypatch.setattr(semilla, "configurar_logging", lambda _entorno: None)
    monkeypatch.setattr(semilla, "sesion_ambito", lambda _unidad: nullcontext(sesion))
    monkeypatch.setattr(sys, "argv", ["semilla", "--unidad", "grupo-santacruz"])

    semilla.main()

    puntos = sesion.scalars(select(PuntoVenta)).all()
    por_codigo = {punto.codigo_co: punto for punto in puntos}
    assert por_codigo["402"].descripcion_siesa == "PDV MALAMBO"
    assert por_codigo["603"].descripcion_siesa == "CONCORD"
    assert len(puntos) == len(semilla.PUNTOS_VENTA) + 1
