"""Entorno de migraciones Alembic. Aplica el esquema a **todas** las bases.

Desde que Agropecuaria puede tener base propia hay una o dos, según lo que diga
la configuración, y `alembic upgrade head` las recorre todas. Sigue siendo un
solo comando a propósito: el arranque del contenedor lo invoca una vez, y quien
migre a mano no tiene que acordarse de repetirlo con otra variable de entorno —
que es exactamente como una de las dos bases se quedaría atrás sin que nadie lo
notara hasta que fallara una consulta.

Las dos llevan el **mismo esquema**, porque son el mismo sistema aplicado a dos
compañías. Lo que las separa es contra qué servidor se abre la conexión, no qué
tablas tienen dentro.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

# Importar el paquete registra todas las tablas en Base.metadata; sin esto el
# autogenerate produciría una migración vacía.
import app.infrastructure.models  # noqa: F401
from alembic import context
from app.core.db import Base, urls_por_unidad

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _destinos() -> dict[str, str]:
    """Las bases a migrar, sin repetir.

    Cuando las dos unidades comparten base —el caso anterior a la separación— la
    dirección es la misma y se migra **una sola vez**. Recorrerla dos veces no
    rompería nada, porque Alembic es idempotente, pero dejaría en el registro dos
    pasadas por la misma base y la ilusión de que hay dos.
    """
    por_url: dict[str, str] = {}
    for unidad, url in urls_por_unidad().items():
        por_url.setdefault(url, unidad)
    return {unidad: url for url, unidad in por_url.items()}


def ejecutar_offline() -> None:
    """Genera el SQL sin conectarse (útil para revisión previa por el DBA).

    Emite el guion de **una** base: son idénticas, así que un solo volcado
    describe las dos y duplicarlo solo daría más que leer.
    """
    url = next(iter(_destinos().values()))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def ejecutar_online() -> None:
    """Aplica las migraciones contra cada base configurada, una tras otra."""
    for unidad, url in _destinos().items():
        print(f"[alembic] Migrando la base de {unidad}…")

        conectable = create_engine(url, poolclass=pool.NullPool)
        try:
            with conectable.connect() as conexion:
                context.configure(
                    connection=conexion,
                    target_metadata=target_metadata,
                    compare_type=True,
                    compare_server_default=True,
                )
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            conectable.dispose()


if context.is_offline_mode():
    ejecutar_offline()
else:
    ejecutar_online()
