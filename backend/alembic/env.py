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


def _migrar(unidad: str, url: str) -> None:
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
        print(f"[alembic] {unidad}: al dia.")
    finally:
        conectable.dispose()


def ejecutar_online() -> None:
    """Aplica las migraciones a cada base. La principal es la que puede parar todo.

    La distincion importa y es deliberada. Si falla la base de carnes, el sistema
    entero deja de tener sentido y el arranque **debe** parar: sin ella no hay
    nada que servir. Si falla la de agropecuaria, en cambio, tumbar el
    contenedor dejaria sin servicio a una compania que funciona por culpa de otra
    que ni siquiera tiene datos todavia, y por algo tan tonto como un caracter
    mal escrito en una variable de entorno.

    Asi que la secundaria falla **ruidosamente y sin parar el arranque**: carnes
    sigue en pie, agropecuaria no responde, y el motivo esta en el registro con
    todas sus letras en lugar de en un contenedor que se reinicia en bucle.
    """
    destinos = _destinos()

    principal = destinos.pop("carnes", None)
    if principal is not None:
        print("[alembic] Migrando la base de carnes…")
        _migrar("carnes", principal)

    for unidad, url in destinos.items():
        print(f"[alembic] Migrando la base de {unidad}…")
        try:
            _migrar(unidad, url)
        except Exception as error:
            print(f"[alembic] ERROR: no se pudo migrar la base de {unidad}: {error}")
            print(f"[alembic] La aplicacion arranca igual y {unidad} no va a responder.")
            print("[alembic] Revise SIGREP_DB_URL_AGRO: usuario, servidor y nombre de base.")
            print("[alembic] Carnes no esta afectada.")


if context.is_offline_mode():
    ejecutar_offline()
else:
    ejecutar_online()
