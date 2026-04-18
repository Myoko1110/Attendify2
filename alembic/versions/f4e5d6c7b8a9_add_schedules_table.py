"""add schedules table

Revision ID: f4e5d6c7b8a9
Revises: d9c8b7a6e5f4
Create Date: 2026-03-18

"""

from __future__ import annotations

from alembic import op  # type: ignore
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "f4e5d6c7b8a9"
down_revision = "d9c8b7a6e5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='schedules'"
        )
    ).first()
    if exists:
        # table already exists, skip creation
        return

    op.create_table(
        "schedules",
        sa.Column("date", sa.Date(), nullable=False, primary_key=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generations", sa.JSON(), nullable=True),
        sa.Column("groups", sa.JSON(), nullable=True),
        sa.Column("exclude_groups", sa.JSON(), nullable=True),
        sa.Column("is_pre_attendance_target", sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='schedules'"
        )
    ).first()
    if not exists:
        # table doesn't exist, nothing to drop
        return

    op.drop_table("schedules")
