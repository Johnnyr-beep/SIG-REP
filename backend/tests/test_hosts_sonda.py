"""`hosts_efectivos` siempre admite el bucle local.

Esta suite existe por un fallo real de producción, y por eso vale la pena
contarlo aquí: con la lista de hosts restringida al dominio público, la sonda
del contenedor —`curl http://127.0.0.1:8000/api/v1/salud`, cabecera
`Host: 127.0.0.1:8000`— recibía **400** de `TrustedHostMiddleware`. Docker
marcaba el contenedor como no sano, Swarm lo reiniciaba sin parar y nginx
devolvía 502 al mundo.

Lo cruel del diagnóstico es que todo lo demás funcionaba: la base migraba,
Uvicorn arrancaba y el único rastro era una línea de log que parecía inocente.
Cuanto mejor se configuraban los hosts, más seguro fallaba.
"""

from __future__ import annotations

import pytest

from app.core.config import HOSTS_SONDA, Settings

CLAVE = "clave-de-pruebas-suficientemente-larga-1234567890"


def _settings(**extra: object) -> Settings:
    return Settings(secret_key=CLAVE, **extra)  # type: ignore[arg-type]


@pytest.mark.parametrize("sonda", HOSTS_SONDA)
def test_el_bucle_local_siempre_esta_permitido(sonda: str) -> None:
    """Con hosts declarados explícitamente, la sonda sigue entrando."""
    hosts = _settings(hosts_permitidos=["sigrep.grupo-santacruz.com"]).hosts_efectivos
    assert sonda in hosts


@pytest.mark.parametrize("sonda", HOSTS_SONDA)
def test_tambien_cuando_los_hosts_se_derivan_del_cors(sonda: str) -> None:
    hosts = _settings(cors_origenes=["https://sigrep.grupo-santacruz.com"]).hosts_efectivos
    assert sonda in hosts


def test_el_dominio_declarado_va_primero() -> None:
    """El orden importa solo para que el log de arranque se lea bien."""
    hosts = _settings(hosts_permitidos=["sigrep.grupo-santacruz.com"]).hosts_efectivos
    assert hosts[0] == "sigrep.grupo-santacruz.com"


def test_no_se_repiten_si_alguien_los_declara_a_mano() -> None:
    hosts = _settings(hosts_permitidos=["localhost", "sigrep.grupo-santacruz.com"]).hosts_efectivos
    assert hosts.count("localhost") == 1


def test_sin_nada_declarado_se_admite_todo() -> None:
    """Último recurso: una lista vacía dejaría la API rechazando todo."""
    assert _settings().hosts_efectivos == ["*"]
