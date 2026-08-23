"""Motores y sesiones de base de datos, **uno por unidad de negocio**.

Carnes Santacruz y Agropecuaria son dos compañías distintas —la 4, la 6 y la 7
por un lado, la 3 por otro—, cada una con su propia API de origen. Que sus
cifras no se mezclen no puede depender de que la próxima consulta esté bien
escrita: depende de que la conexión por la que tendrían que pasar no exista.

De ahí la forma de este módulo. En vez de un motor global hay un registro por
unidad, y la sesión que recibe una petición es la de **su** unidad. Un token de
carnes no puede leer agropecuaria ni escribiendo la ruta a mano: no está
conectado a esa base.

── El estado anterior sigue siendo válido ────────────────────────────────────

Sin `SIGREP_DB_URL_AGRO` las dos unidades comparten base, que es como arrancó el
sistema. El registro devuelve entonces el **mismo motor** para las dos, no dos
motores contra la misma dirección: dos conjuntos de conexiones al mismo sitio
duplicarían el consumo del pool sin separar nada.

Esa compatibilidad no es pereza. Permite desplegar el código antes de crear la
segunda base, y volver atrás borrando una variable de entorno en vez de
revirtiendo un despliegue.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any, Literal

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import obtener_settings

#: Las unidades que tienen datos propios. `carnes-frias` no está: es una marca
#: sin módulo, y darle un motor sería prometer una base que nadie ha creado.
UnidadDatos = Literal["carnes", "agropecuaria"]

UNIDAD_POR_DEFECTO: UnidadDatos = "carnes"


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos ORM.

    Una sola, compartida por las dos unidades **a propósito**: las tablas se
    llaman igual en las dos bases porque son el mismo esquema aplicado dos
    veces. Lo que separa a las compañías es contra qué servidor se abre la
    conexión, no cómo se llaman sus tablas.
    """


def _crear_engine(url: str) -> Engine:
    settings = obtener_settings()

    if url.startswith("sqlite"):
        # Configuración exclusiva de pruebas: una sola conexión compartida.
        engine = create_engine(
            url,
            echo=settings.db_echo,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _activar_foreign_keys(dbapi_conn: Any, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    return create_engine(
        url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seg,
        pool_pre_ping=True,  # descarta conexiones muertas tras un failover
        future=True,
    )


# ── Registro de motores ───────────────────────────────────────────────────────
#
# Perezoso y cacheado **por URL**, no por unidad: cuando las dos comparten base
# —el caso anterior a la separación— tienen que compartir también el pool de
# conexiones, o el consumo se duplica sin que nada quede separado.

_motores: dict[str, Engine] = {}
_fabricas: dict[str, sessionmaker[Session]] = {}


def _fabrica(url: str) -> sessionmaker[Session]:
    if url not in _fabricas:
        _motores[url] = _crear_engine(url)
        _fabricas[url] = sessionmaker(
            bind=_motores[url],
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _fabricas[url]


def motor_de(unidad: UnidadDatos = UNIDAD_POR_DEFECTO) -> Engine:
    """El motor de una unidad. Lo usan las migraciones y las pruebas."""
    url = obtener_settings().url_de_unidad(unidad)
    _fabrica(url)
    return _motores[url]


def fabrica_de(unidad: UnidadDatos = UNIDAD_POR_DEFECTO) -> sessionmaker[Session]:
    return _fabrica(obtener_settings().url_de_unidad(unidad))


def urls_por_unidad() -> dict[str, str]:
    """Qué dirección le toca a cada unidad. Para migrar y para diagnosticar."""
    settings = obtener_settings()
    return {
        "carnes": settings.url_de_unidad("carnes"),
        "agropecuaria": settings.url_de_unidad("agropecuaria"),
    }


def _es_sqlite_en_memoria(url: str) -> bool:
    """Las dos formas de escribirlo: `sqlite://` a secas y `sqlite:///:memory:`."""
    return url in {"sqlite://", "sqlite:///:memory:"}


def reiniciar_motores() -> None:
    """Olvida los motores para que el registro se rehaga. **Solo para pruebas.**

    Los ajustes se cachean y los motores tambien; una prueba que cambie la
    configuracion de base necesita que el registro se rehaga, o seguiria
    hablando con la base de la prueba anterior.

    **Los motores de SQLite en memoria se quedan como estan**, ni se cierran ni
    se olvidan, y esa excepcion es la que hace que esto funcione.

    Una base en memoria vive dentro de su conexion: cerrarla no libera un
    recurso, la borra. Y el `conftest` toma su motor **una vez, al importarse**,
    asi que si aqui se olvidara del registro, la aplicacion crearia otro nuevo a
    la siguiente consulta: el conftest sembraria las tablas en una base y la
    aplicacion preguntaria por otra, vacia.

    Costo una integracion continua en rojo con treinta y un fallos que no se
    reproducian en local, donde la base de pruebas es un archivo y sobrevive
    tanto a que la cierren como a que la olviden.
    """
    for url in list(_motores):
        if _es_sqlite_en_memoria(url):
            continue
        _motores.pop(url).dispose()
        _fabricas.pop(url, None)


def obtener_sesion_de(unidad: UnidadDatos) -> Generator[Session, None, None]:
    """Sesión de la unidad indicada, con commit al salir y rollback si falla."""
    sesion = fabrica_de(unidad)()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


def obtener_sesion() -> Generator[Session, None, None]:
    """La sesión de carnes, para lo que no depende de la petición."""
    yield from obtener_sesion_de(UNIDAD_POR_DEFECTO)


@contextmanager
def sesion_ambito(unidad: UnidadDatos = UNIDAD_POR_DEFECTO) -> Iterator[Session]:
    """Sesión transaccional para jobs y scripts, y para el puñado de endpoints
    que no pueden usar la dependencia.

    `POST /auth/refrescar` es el caso: su unidad va dentro del token de refresco,
    que viaja en el cuerpo, así que la dependencia de sesión —que solo mira las
    cabeceras— resolvería la base equivocada.
    """
    sesion = fabrica_de(unidad)()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


# ── Compatibilidad de nombres ─────────────────────────────────────────────────


def __getattr__(nombre: str) -> Any:
    """`engine` y `SessionLocal` perezosos, apuntando a carnes.

    Los importa media base de código —el conftest, Alembic, los scripts— y
    resolverlos aquí conserva los nombres de siempre. Perezosos y no de módulo
    porque antes se creaban al cargar el archivo, lo que obligaba a tener
    configuración de base válida para **importar** cualquier cosa.
    """
    if nombre == "engine":
        return motor_de()
    if nombre == "SessionLocal":
        return fabrica_de()
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
