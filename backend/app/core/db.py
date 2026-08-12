"""Motor y sesiones de base de datos. Portado de GSC ONE."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import obtener_settings


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos ORM."""


def _crear_engine() -> Engine:
    settings = obtener_settings()
    url = settings.database_url

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


engine: Engine = _crear_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def obtener_sesion() -> Generator[Session, None, None]:
    """Dependencia FastAPI: una sesión por petición, con rollback ante error."""
    sesion = SessionLocal()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


@contextmanager
def sesion_ambito() -> Iterator[Session]:
    """Sesión transaccional para jobs y scripts fuera del ciclo HTTP."""
    sesion = SessionLocal()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
