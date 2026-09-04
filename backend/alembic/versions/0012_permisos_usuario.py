"""Permisos granulares por usuario.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuario_permisos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "codigo", name="uq_usuario_permiso"),
    )
    op.create_index("ix_usuario_permisos_usuario_id", "usuario_permisos", ["usuario_id"])
    op.create_index("ix_usuario_permisos_codigo", "usuario_permisos", ["codigo"])


def downgrade() -> None:
    op.drop_index("ix_usuario_permisos_codigo", table_name="usuario_permisos")
    op.drop_index("ix_usuario_permisos_usuario_id", table_name="usuario_permisos")
    op.drop_table("usuario_permisos")