"""Entorno de migraciones Alembic."""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

# Importar el paquete registra todas las tablas en Base.metadata; sin esto el
# autogenerate produciría una migración vacía.
import app.infrastructure.models  # noqa: F401
from alembic import context
from app.core.config import obtener_settings
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", obtener_settings().database_url)

target_metadata = Base.metadata


def ejecutar_offline() -> None:
    """Genera el SQL sin conectarse (útil para revisión previa por el DBA)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_online() -> None:
    """Aplica las migraciones contra la base configurada."""
    conectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with conectable.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    ejecutar_offline()
else:
    ejecutar_online()
