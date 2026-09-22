"""`iniciar_precalentador_financiero_en_vivo`: arranca sin token, no revienta.

Mismo patrón que `test_documentos_diarios.py` para `programador_documentos`:
sin `SIGREP_SIESA_TOKEN` el bucle ni se crea, en vez de fallar en el primer
recalentamiento.
"""

from __future__ import annotations


def test_iniciar_precalentador_sin_token(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import obtener_settings
    from app.infrastructure.precalentador_financiero import (
        iniciar_precalentador_financiero_en_vivo,
    )

    monkeypatch.delenv("SIGREP_SIESA_TOKEN", raising=False)
    obtener_settings.cache_clear()
    try:
        assert iniciar_precalentador_financiero_en_vivo() is None
    finally:
        obtener_settings.cache_clear()


def test_intervalo_menor_al_ttl_de_la_cache() -> None:
    """El recalentamiento debe llegar antes de que venza la caché de 10 minutos,

    o hay una ventana donde la caché ya expiró y nadie la ha vuelto a llenar.
    """
    from app.infrastructure.fuentes.financiero_siesa import _TTL_CACHE_SEG
    from app.infrastructure.precalentador_financiero import INTERVALO_MINUTOS

    assert INTERVALO_MINUTOS * 60 < _TTL_CACHE_SEG
