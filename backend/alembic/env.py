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
from app.core.config import obtener_settings
from app.core.db import Base, urls_por_unidad

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Tablas que existen en el esquema compartido pero que **solo** deben crearse
#: al migrar la base de una unidad concreta. Hoy solo el libro mayor del
#: tablero financiero, exclusivo de `grupo-santacruz`: las unidades operativas
#: (Carnes, Agropecuaria, Carnes Frias) no deben ganar ni siquiera una tabla
#: vacia por el hecho de compartir `Base`.
TABLAS_EXCLUSIVAS_POR_UNIDAD: dict[str, str] = {
    "movimientos_contables": "grupo-santacruz",
}


def _incluir_objeto_de(unidad: str):
    """Filtro de autogenerate: oculta las tablas exclusivas de otra unidad.

    Sin esto, un `alembic revision --autogenerate` corrido contra Carnes o
    Agropecuaria detectaria «falta movimientos_contables» y propondria
    recrearla ahi: la tabla esta en `Base.metadata` porque el esquema es
    compartido, pero economicamente no le pertenece a esas bases.
    """

    def _incluir(objeto: object, nombre: str, tipo: str, _reflejado: bool, _comparar_con: object) -> bool:
        if tipo == "table" and TABLAS_EXCLUSIVAS_POR_UNIDAD.get(nombre) not in (None, unidad):
            return False
        return True

    return _incluir


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

    Emite el guión de **una** base representativa. Desde que
    `movimientos_contables` es exclusiva de `grupo-santacruz`, el guión ya no
    describe por igual a las cuatro unidades: quién revise este volcado para
    una unidad operativa debe ignorar esa tabla si aparece aquí, y regenerarlo
    apuntando a `grupo-santacruz` si lo que necesita revisar es esa tabla.
    """
    unidad, url = next(iter(_destinos().items()))
    config.attributes["sigrep_unidad"] = unidad
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_incluir_objeto_de(unidad),
    )
    with context.begin_transaction():
        context.run_migrations()


def _migrar(unidad: str, url: str) -> None:
    conectable = create_engine(url, poolclass=pool.NullPool)
    try:
        with conectable.connect() as conexion:
            config.attributes["sigrep_unidad"] = unidad
            context.configure(
                connection=conexion,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                include_object=_incluir_objeto_de(unidad),
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

    unidad_principal = obtener_settings().unidad
    principal = destinos.pop(unidad_principal if unidad_principal != "todas" else "carnes", None)
    if principal is not None:
        print(f"[alembic] Migrando la base de {unidad_principal}…")
        _migrar(unidad_principal, principal)

    for unidad, url in destinos.items():
        print(f"[alembic] Migrando la base de {unidad}…")
        try:
            _migrar(unidad, url)
        except Exception as error:
            print(f"[alembic] ERROR: no se pudo migrar la base de {unidad}: {error}")
            print(f"[alembic] La aplicacion arranca igual y {unidad} no va a responder.")
            print("[alembic] Revise la URL de base configurada para esa unidad.")
            print(f"[alembic] {unidad_principal} no esta afectada.")


if context.is_offline_mode():
    ejecutar_offline()
else:
    ejecutar_online()
