"""merge ec35e27338ac and c3e4f5a6b7d8

Revision ID: d9c8b7a6e5f4
Revises: ec35e27338ac, c3e4f5a6b7d8
Create Date: 2026-03-18

This is a merge revision to resolve multiple-heads situation.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d9c8b7a6e5f4"
down_revision = ("ec35e27338ac", "c3e4f5a6b7d8")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # no-op merge revision
    pass


def downgrade() -> None:
    # nothing to downgrade; this revision solely merges branches
    pass
