"""rastro de administracion de usuarios

El modulo de administracion de usuarios anade el rol ADMIN y la tabla
`usuario_auditoria`, que guarda quien administro que cuenta, que cambio y
cuando. Es el equivalente de `presupuesto_historial` para los permisos: «un
permiso concedido sin rastro no se puede auditar».

Que hace y que **no** hace esta revision:

- Crea `usuario_auditoria`. Es la unica tabla nueva.
- **No toca `usuarios`.** El rol nuevo no necesita migracion: `usuarios.rol` es
  un `VARCHAR(20)` sin restriccion CHECK ni tipo ENUM del motor, asi que
  `'ADMIN'` cabe tal cual. Se comprobo contra `0001`: la columna se declaro
  deliberadamente como cadena para que anadir un rol no exija migrar datos
  historicos.
- **No crea ningun usuario.** El primer ADMIN lo crea
  `python -m app.infrastructure.semilla --administrador`, que imprime su clave
  provisional una sola vez. Sembrar una cuenta desde una migracion significaria
  o una clave fija en el repositorio o una clave generada que nadie ve.

Las dos claves ajenas a `usuarios` —la cuenta administrada y quien la
administro— son **anulables**, igual que en `presupuesto_historial` y por el
mismo motivo: el rastro tiene que sobrevivir a lo que historia. Las columnas
`usuario` y `actor` guardan ademas el nombre de acceso desnormalizado, de modo
que la fila se lee entera sin ningun `JOIN` y sigue diciendo la verdad aunque
manana alguien renombre la cuenta.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

import app.infrastructure.models.mixins
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuario_auditoria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("usuario", sa.String(length=50), nullable=False),
        sa.Column("accion", sa.String(length=30), nullable=False),
        sa.Column("campo", sa.String(length=40), nullable=True),
        sa.Column("valor_anterior", sa.String(length=200), nullable=True),
        sa.Column("valor_nuevo", sa.String(length=200), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=50), nullable=False),
        sa.Column("ip_origen", sa.String(length=45), nullable=True),
        sa.Column(
            "cuando", app.infrastructure.models.mixins.UtcDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_usuario_auditoria_actor_id"), "usuario_auditoria", ["actor_id"], unique=False
    )
    op.create_index(
        op.f("ix_usuario_auditoria_usuario_id"), "usuario_auditoria", ["usuario_id"], unique=False
    )
    # Sirve la consulta de la pantalla: el rastro de **una** cuenta, del cambio
    # mas reciente al mas antiguo.
    op.create_index(
        "ix_auditoria_usuario_cuando", "usuario_auditoria", ["usuario_id", "cuando"], unique=False
    )


def downgrade() -> None:
    """Bajar **borra el rastro de auditoria**, y no hay forma de que no lo haga.

    Se deja escrito aqui porque es la clase de perdida que no se nota hasta que
    alguien pregunta quien concedio un permiso: si esta base ya lleva
    administracion de usuarios en produccion, exporte `usuario_auditoria` antes
    de ejecutar este `downgrade`. Ninguna otra revision de SIGREP destruye
    historia al bajar; esta si, porque la tabla entera es historia.
    """
    op.drop_index("ix_auditoria_usuario_cuando", table_name="usuario_auditoria")
    op.drop_index(op.f("ix_usuario_auditoria_usuario_id"), table_name="usuario_auditoria")
    op.drop_index(op.f("ix_usuario_auditoria_actor_id"), table_name="usuario_auditoria")
    op.drop_table("usuario_auditoria")
