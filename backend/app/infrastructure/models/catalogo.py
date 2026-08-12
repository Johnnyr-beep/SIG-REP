"""Categorías gerenciales y su mapeo desde las categorías crudas de SIESA (§3.1)."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.infrastructure.models.mixins import TimestampMixin


class Categoria(Base, TimestampMixin):
    """Una de las ocho categorías de negocio.

    No todos los puntos de venta manejan las ocho: LA43 y ALAMEDA no tienen
    ASADERO. El presupuesto por categoría es opcional y su ausencia no es un
    error.
    """

    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    orden: Mapped[int] = mapped_column(default=0, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    mapeos: Mapped[list[MapeoCategoria]] = relationship(back_populates="categoria")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Categoria {self.nombre}>"


class MapeoCategoria(Base, TimestampMixin):
    """Traducción de la categoría cruda de SIESA a la categoría de negocio.

    Es **una tabla**, no un `dict` en el código: SIESA añade categorías y el
    negocio las reclasifica sin esperar un despliegue (§3.1).

    El mapeo es por **texto exacto**. Existen dos códigos `0006` con distinta
    ortografía —`QUESO Y LACTEOS` y `QUESOS Y LACTEOS`— y ambos están sembrados
    como filas separadas. Normalizar el texto para «arreglarlo» aquí sería
    esconder un problema de origen que el negocio necesita ver.
    """

    __tablename__ = "mapeo_categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto_siesa: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id"), nullable=False, index=True
    )

    categoria: Mapped[Categoria] = relationship(back_populates="mapeos", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<MapeoCategoria {self.texto_siesa!r}>"
