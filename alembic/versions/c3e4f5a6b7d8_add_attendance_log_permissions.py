"""add attendance_log permissions

Revision ID: c3e4f5a6b7d8
Revises: b1a2c3d4e5f6
Create Date: 2026-03-18

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from uuid import uuid4

# revision identifiers, used by Alembic.
revision = "c3e4f5a6b7d8"
down_revision = "b1a2c3d4e5f6"
branch_labels = None
depends_on = None

PERMS = [
    ("attendance-log:read", "出席ログの読み込み"),
    ("attendance-log:write", "出席ログの操作"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Insert permissions if missing
    for key, desc in PERMS:
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, key, description, created_at)"
                " SELECT :id, :key, :desc, now() WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE key = :key)"
            ),
            {"id": str(uuid4()), "key": key, "desc": desc},
        )

    # Assign to admin role if exists
    row = conn.execute(sa.text("SELECT id FROM roles WHERE key = :k"), {"k": "admin"}).fetchone()
    if row:
        role_id = row[0]
        for key, _ in PERMS:
            pid_row = conn.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).fetchone()
            if not pid_row:
                continue
            perm_id = pid_row[0]
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id)"
                    " SELECT :rid, :pid WHERE NOT EXISTS (SELECT 1 FROM role_permissions WHERE role_id = :rid AND permission_id = :pid)"
                ),
                {"rid": role_id, "pid": perm_id},
            )


def downgrade() -> None:
    conn = op.get_bind()

    # remove role_permissions and permissions for these keys
    for key, _ in PERMS:
        pid_row = conn.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).fetchone()
        if not pid_row:
            continue
        perm_id = pid_row[0]
        conn.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"), {"pid": perm_id})
        conn.execute(sa.text("DELETE FROM permissions WHERE id = :pid"), {"pid": perm_id})
