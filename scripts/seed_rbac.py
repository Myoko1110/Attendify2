"""Seed minimal RBAC data.

- Creates default roles/permissions.
- Optionally assigns a role to a member by email.

Usage:
  python scripts/seed_rbac.py
  python scripts/seed_rbac.py --member-email you@example.com --role admin

DB URL is taken from DATABASE_URL env var; otherwise uses the same default as alembic.ini.

Exit codes:
  0: success
  1: failure
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path
from uuid import uuid4
import io

# Force UTF-8 for stdout/stderr to avoid UnicodeEncodeError on terminals with ASCII locale
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

# Hint for DB driver / child processes
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PGCLIENTENCODING", "utf8")

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.database.models import (
    Member,
    MemberRole,
    PermissionImplies,
    RBACPermission,
    RBACRole,
    RolePermission,
)
from app.rbac_constants import DEFAULT_ROLES, PERMISSIONS, PERMISSION_IMPLIES

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"


def get_url() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_DB_URL


def upsert_permission(db: Session, key: str, description: str) -> RBACPermission:
    p = db.execute(select(RBACPermission).where(RBACPermission.key == key)).scalar_one_or_none()
    if p:
        if p.description != description:
            p.description = description
        return p
    p = RBACPermission(id=uuid4(), key=key, description=description)
    db.add(p)
    # ensure IDs ready for relationship inserts
    db.flush()
    return p


def upsert_role(db: Session, key: str, display_name: str, description: str) -> RBACRole:
    r = db.execute(select(RBACRole).where(RBACRole.key == key)).scalar_one_or_none()
    if r:
        r.display_name = display_name
        r.description = description
        return r
    r = RBACRole(id=uuid4(), key=key, display_name=display_name, description=description)
    db.add(r)
    db.flush()
    return r


def ensure_role_permission(db: Session, role: RBACRole, perm: RBACPermission) -> None:
    exists = db.execute(
        select(RolePermission)
        .where(RolePermission.role_id == role.id)
        .where(RolePermission.permission_id == perm.id)
    ).scalar_one_or_none()
    if exists:
        return
    db.add(RolePermission(role_id=role.id, permission_id=perm.id))


def ensure_member_role(db: Session, member: Member, role: RBACRole) -> None:
    exists = db.execute(
        select(MemberRole)
        .where(MemberRole.member_id == member.id)
        .where(MemberRole.role_id == role.id)
    ).scalar_one_or_none()
    if exists:
        return
    db.add(MemberRole(member_id=member.id, role_id=role.id))


def ensure_permission_implies(db: Session, parent: RBACPermission, child: RBACPermission) -> None:
    exists = db.execute(
        select(PermissionImplies)
        .where(PermissionImplies.parent_permission_id == parent.id)
        .where(PermissionImplies.child_permission_id == child.id)
    ).scalar_one_or_none()
    if exists:
        return
    db.add(PermissionImplies(parent_permission_id=parent.id, child_permission_id=child.id))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--member-email", default=None)
    ap.add_argument("--role", default="admin")
    args = ap.parse_args()

    url = get_url()
    print(f"[seed_rbac] url={url}")

    eng = create_engine(url)

    with eng.connect() as c:
        try:
            # Ensure PostgreSQL client encoding is UTF8 to avoid UnicodeEncodeError from driver
            c.execute(text("SET client_encoding TO 'UTF8'"))
        except Exception:
            # If the server doesn't allow this or it fails, ignore and continue
            pass
        c.execute(text("select 1"))

    with Session(eng) as db:
        perm_map: dict[str, RBACPermission] = {}
        for p in PERMISSIONS:
            perm_map[p.key] = upsert_permission(db, p.key, p.description)

        # ensure implied permission keys also exist
        for parent_key, child_key in PERMISSION_IMPLIES:
            if parent_key not in perm_map:
                perm_map[parent_key] = upsert_permission(db, parent_key, "")
            if child_key not in perm_map:
                perm_map[child_key] = upsert_permission(db, child_key, "")

        role_map: dict[str, RBACRole] = {}
        for rdef in DEFAULT_ROLES:
            r = upsert_role(db, rdef.key, rdef.display_name, rdef.description)
            role_map[rdef.key] = r
            for pkey in rdef.permission_keys:
                ensure_role_permission(db, r, perm_map[pkey])

        # permission implication edges (optional: table might not exist yet in older DB)
        try:
            for parent_key, child_key in PERMISSION_IMPLIES:
                parent = perm_map[parent_key]
                child = perm_map[child_key]
                ensure_permission_implies(db, parent, child)
        except ProgrammingError:
            print("[seed_rbac] permission_implies table missing; skip implication seeding")

        if args.member_email:
            member = db.execute(select(Member).where(Member.email == args.member_email)).scalar_one_or_none()
            if not member:
                raise SystemExit(f"Member not found: {args.member_email}")
            role = role_map.get(args.role) or db.execute(select(RBACRole).where(RBACRole.key == args.role)).scalar_one_or_none()
            if not role:
                raise SystemExit(f"Role not found: {args.role}")
            ensure_member_role(db, member, role)
            print(f"[seed_rbac] assigned role '{role.key}' to member {member.email}")

        db.commit()

    print("[seed_rbac] seeded RBAC")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
