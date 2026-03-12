"""add generation_roles and permission_implies

Revision ID: b1a2c3d4e5f6
Revises: 8f7e2cc9a9e2
Create Date: 2026-03-08

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b1a2c3d4e5f6"
down_revision = "8f7e2cc9a9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generation_roles",
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("generation", "role_id"),
        sa.UniqueConstraint("generation", "role_id"),
    )

    op.create_table(
        "permission_implies",
        sa.Column("parent_permission_id", sa.Uuid(), nullable=False),
        sa.Column("child_permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["parent_permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("parent_permission_id", "child_permission_id"),
        sa.UniqueConstraint("parent_permission_id", "child_permission_id"),
    )


def downgrade() -> None:
    op.drop_table("permission_implies")
    op.drop_table("generation_roles")
