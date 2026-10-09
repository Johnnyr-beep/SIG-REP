from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.infrastructure import precalentador_inventario as precalentador
from app.infrastructure.fuentes.inventario_siesa import InventarioPdvCrudo


@pytest.fixture(autouse=True)
def limpiar_snapshot() -> None:
    precalentador.limpiar_cache_inventario()
    yield
    precalentador.limpiar_cache_inventario()


def test_precarga_y_get_reutilizan_el_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = InventarioPdvCrudo(
        columnas=("CO_Codigo", "Item_Referencia"),
        filas=({"CO_Codigo": "402", "Item_Referencia": "3203"},),
    )
    llamadas = 0

    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            nonlocal llamadas
            llamadas += 1
            return snapshot

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(precalentador, "FuenteInventarioPdvSiesa", FuenteFalsa)

    asyncio.run(precalentador._precalentar_una_vez())

    assert precalentador.obtener_inventario_pdv() is snapshot
    assert llamadas == 1


def test_precarga_inicial_antes_de_aceptar_peticiones(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = InventarioPdvCrudo(columnas=("CO_Codigo",), filas=({"CO_Codigo": "402"},))

    class FuenteFalsa:
        def leer(self) -> InventarioPdvCrudo:
            return snapshot

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(
        precalentador,
        "obtener_settings",
        lambda: SimpleNamespace(siesa_token=SecretStr("token-de-prueba")),
    )
    monkeypatch.setattr(precalentador, "FuenteInventarioPdvSiesa", FuenteFalsa)

    asyncio.run(precalentador.precalentar_inventario_al_iniciar())

    assert precalentador.obtener_inventario_pdv() is snapshot


def test_fallo_de_refresco_conserva_el_ultimo_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = InventarioPdvCrudo(columnas=("CO_Codigo",), filas=({"CO_Codigo": "402"},))

    class FuenteBuena:
        def leer(self) -> InventarioPdvCrudo:
            return snapshot

        def cerrar(self) -> None:
            return None

    class FuenteFalla:
        def leer(self) -> InventarioPdvCrudo:
            raise RuntimeError("SIESA no disponible")

        def cerrar(self) -> None:
            return None

    monkeypatch.setattr(precalentador, "FuenteInventarioPdvSiesa", FuenteBuena)
    asyncio.run(precalentador._precalentar_una_vez())
    monkeypatch.setattr(precalentador, "FuenteInventarioPdvSiesa", FuenteFalla)

    asyncio.run(precalentador._precalentar_una_vez())

    assert precalentador.obtener_inventario_pdv() is snapshot


def test_iniciar_precalentador_sin_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import obtener_settings

    monkeypatch.delenv("SIGREP_SIESA_TOKEN", raising=False)
    obtener_settings.cache_clear()
    try:
        assert precalentador.iniciar_precalentador_inventario() is None
    finally:
        obtener_settings.cache_clear()
