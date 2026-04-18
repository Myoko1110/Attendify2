"""add start_time and end_time columns to schedules

Revision ID: a1b2c3d4e5f6
Revises: f4e5d6c7b8a9
Create Date: 2026-03-18

"""

from __future__ import annotations

from alembic import op  # type: ignore
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f4e5d6c7b8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Use PostgreSQL's IF NOT EXISTS to avoid errors if columns already exist
    conn.execute(
        sa.text(
            "ALTER TABLE schedules ADD COLUMN IF NOT EXISTS start_time TIMESTAMP WITH TIME ZONE NULL;"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE schedules ADD COLUMN IF NOT EXISTS end_time TIMESTAMP WITH TIME ZONE NULL;"
        )

    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE schedules DROP COLUMN IF EXISTS start_time;"))
    conn.execute(sa.text("ALTER TABLE schedules DROP COLUMN IF EXISTS end_time;"))
