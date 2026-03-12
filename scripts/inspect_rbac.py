"""Inspect RBAC tables.

Usage:
  python scripts/inspect_rbac.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"

url = os.getenv("DATABASE_URL") or DEFAULT_DB_URL
print(f"[inspect_rbac] url={url}")

eng = create_engine(url)
with eng.connect() as c:
    roles = c.execute(text("select key, display_name from roles order by key")).fetchall()
    perms = c.execute(text("select key from permissions order by key")).fetchall()
    rp = c.execute(text("select count(*) from role_permissions")).scalar()
    mr = c.execute(text("select count(*) from member_roles")).scalar()

print("roles=", roles)
print("permissions=", perms)
print("role_permissions_count=", rp)
print("member_roles_count=", mr)
