"""Bitácora de las cargas de venta agropecuaria (§5).

Tablas propias y no las de carnes, por dos motivos que se refuerzan:

1. **`agro_venta_lineas.corrida_id` tiene que apuntar a algún sitio**, y
   apuntarlo a `corridas_ingesta` mezclaría en una misma tabla las corridas de
   dos unidades de negocio que corren en instancias distintas y contra fuentes
   distintas.
2. **La pantalla de ingesta de carnes no debe llenarse de corridas
   agropecuarias.** `GET /ingesta/corridas` responde «¿está cargado el mes?»;
   con las dos unidades en la misma tabla, respondería que sí cuando lo que
   está cargado es lo de la otra.

Lo que sí se reutiliza tal cual es `BitacoraIngesta`
(`app/application/services/bitacora_ingesta.py`): agrega las anotaciones por
(campo, motivo, valor) con su recuento y no sabe nada de qué tabla las va a
guardar. Y `EstadoCorrida`, que es el mismo ciclo de vida.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.domain.enums import EstadoCorrida
from app.infrastructure.models.mixins import UtcDateTime, ahora_utc


class AgroCorridaIngesta(Base):
    """Una ejecución de carga de venta agropecuaria, exitosa o no."""

    __tablename__ = "agro_corridas_ingesta"
    __table_args__ = (Index("ix_agro_corridas_cuando", "cuando"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cuando: Mapped[datetime] = mapped_column(UtcDateTime, default=ahora_utc, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    #: Hoy siempre `agropecuaria`. Se guarda como columna, y no se da por
    #: supuesto, para que el día que exista una carga por archivo la bitácora
    #: distinga de dónde vino cada corrida.
    fuente: Mapped[str] = mapped_column(String(20), nullable=False, default="agropecuaria")
    desde: Mapped[date | None] = mapped_column()
    hasta: Mapped[date | None] = mapped_column()
    estado: Mapped[str] = mapped_column(
        String(30), nullable=False, default=EstadoCorrida.EN_CURSO.value
    )

    filas_leidas: Mapped[int] = mapped_column(default=0, nullable=False)
    aceptadas: Mapped[int] = mapped_column(default=0, nullable=False)
    rechazadas: Mapped[int] = mapped_column(default=0, nullable=False)
    #: Filas de `TipoItem = IMPUESTO` cargadas en esta corrida. Van dentro de
    #: `aceptadas` —se guardan— y se cuentan aparte porque son las que **no**
    #: van a aparecer en ningún total: sin este número, quien concilie la
    #: corrida contra el origen vería una diferencia sin explicación.
    impuesto: Mapped[int] = mapped_column(default=0, nullable=False)
    duracion_ms: Mapped[int | None] = mapped_column()

    #: Endpoint consultado, sin el token. Ayuda a contestar «¿de dónde salió
    #: este número?» seis meses después.
    origen: Mapped[str | None] = mapped_column(String(300))
    mensaje: Mapped[str | None] = mapped_column(Text)

    rechazos: Mapped[list[AgroRechazoIngesta]] = relationship(
        back_populates="corrida", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AgroCorridaIngesta {self.id} {self.estado}>"


class AgroRechazoIngesta(Base):
    """Una fila que la ingesta agropecuaria no pudo aceptar, con su motivo.

    Rechazar en silencio es peor que fallar: el consolidado sale cuadrado y
    nadie se entera de que faltan tres días de un centro de operación.
    """

    __tablename__ = "agro_rechazos_ingesta"
    __table_args__ = (Index("ix_agro_rechazos_corrida", "corrida_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    corrida_id: Mapped[int] = mapped_column(
        ForeignKey("agro_corridas_ingesta.id", ondelete="CASCADE"), nullable=False
    )
    #: Número de fila en el origen.
    fila: Mapped[int | None] = mapped_column()
    campo: Mapped[str | None] = mapped_column(String(60))
    #: Valor ofensivo, truncado. Se guarda como texto porque justamente el
    #: problema suele ser que no tenía el tipo que decía tener.
    valor: Mapped[str | None] = mapped_column(String(300))
    motivo: Mapped[str] = mapped_column(String(300), nullable=False)

    corrida: Mapped[AgroCorridaIngesta] = relationship(back_populates="rechazos")
