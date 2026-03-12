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

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"

REQUIRED_PERMISSION_KEYS = [
    "dashboard:read",
    "dashboard:write",
    "rbac:manage",
    "attendance:export",
    "member:write",
]


def main() -> int:
    url = os.getenv("DATABASE_URL") or DEFAULT_DB_URL
    eng = create_engine(url)

    with eng.begin() as c:
        # Ensure permissions table exists
        c.execute(text("select 1 from permissions limit 1"))

        existing = set(
            r[0]
            for r in c.execute(text("select key from permissions")).fetchall()
        )

        missing = [k for k in REQUIRED_PERMISSION_KEYS if k not in existing]
        if not missing:
            return 0

        for k in missing:
            c.execute(
                text("insert into permissions (id, key, description, created_at) values (:id, :k, '', now())"),
                {"id": str(uuid4()), "k": k},
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
