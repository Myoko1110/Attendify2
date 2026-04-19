"""Ensure permissions exist in DB.

This script is intentionally quiet on success; it exits non-zero on failure.

Usage:
  python scripts/ensure_permissions.py

Environment:
  DATABASE_URL (optional)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

from app.rbac_constants import DEFAULT_ROLES, PERMISSIONS, PERMISSION_IMPLIES

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"


REQUIRED_PERMISSION_KEYS = [p.key for p in PERMISSIONS]


def main() -> int:
    url = os.getenv("DATABASE_URL") or DEFAULT_DB_URL
    eng = create_engine(url)

    with eng.begin() as c:
        # Ensure permissions table exists
        c.execute(text("select 1 from permissions limit 1"))

        existing = {
            r[0]
            for r in c.execute(text("select key from permissions")).fetchall()
        }

        for p in PERMISSIONS:
            if p.key in existing:
                continue
            c.execute(
                text("insert into permissions (id, key, description, created_at) values (:id, :k, :desc, now())"),
                {"id": str(uuid4()), "k": p.key, "desc": p.description},
            )

        # Make sure implied permissions also exist for older DBs that may not have the full catalog yet.
        for parent_key, child_key in PERMISSION_IMPLIES:
            for key in (parent_key, child_key):
                if key in existing:
                    continue
                c.execute(
                    text("insert into permissions (id, key, description, created_at) values (:id, :k, '', now())"),
                    {"id": str(uuid4()), "k": key},
                )
                existing.add(key)

        # Ensure admin gets every permission in the current code-defined catalog.
        admin_role_id = c.execute(text("select id from roles where key = :k"), {"k": "admin"}).scalar_one_or_none()
        if admin_role_id:
            permission_ids = c.execute(
                text("select id, key from permissions where key = any(:keys)"),
                {"keys": REQUIRED_PERMISSION_KEYS},
            ).fetchall()
            perm_id_by_key = {row[1]: row[0] for row in permission_ids}

            for key in REQUIRED_PERMISSION_KEYS:
                perm_id = perm_id_by_key.get(key)
                if not perm_id:
                    continue
                c.execute(
                    text(
                        "insert into role_permissions (role_id, permission_id) "
                        "select :rid, :pid where not exists (select 1 from role_permissions where role_id = :rid and permission_id = :pid)"
                    ),
                    {"rid": admin_role_id, "pid": perm_id},
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
