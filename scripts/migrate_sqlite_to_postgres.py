"""Migrate core data from a legacy SQLite DB into PostgreSQL.

対象:
- テーブル作成
- 部員 (`members`) と予定 (`schedules`) の移行
- RBAC のデフォルトデータ投入（permissions / roles / role_permissions / permission_implies）

移行しないもの:
- それ以外のデータ（attendance, pre_attendance, sessions, groups など）

使い方:
  python scripts/migrate_sqlite_to_postgres.py --sqlite-db attendify.db
  python scripts/migrate_sqlite_to_postgres.py --sqlite-db attendify.db --pg-url postgresql+asyncpg://postgres:.../attendify

注意:
- 既存の PostgreSQL データは基本的に保持し、足りないものだけ追加します。
- 同じ member/email や schedule/date がある場合はスキップします。
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.abc.part import Part
from app.abc.role import Role
from app.abc.schedule_type import ScheduleType
from app.database.models import (
    Base,
    Member,
    PermissionImplies,
    RBACPermission,
    RBACRole,
    RolePermission,
    Schedule,
)
from app.rbac_constants import DEFAULT_ROLES, PERMISSIONS, PERMISSION_IMPLIES

DEFAULT_PG_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite-db", default="attendify.db", help="Legacy SQLite DB file path")
    ap.add_argument("--pg-url", default=os.getenv("DATABASE_URL", DEFAULT_PG_URL), help="PostgreSQL URL")
    ap.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    ap.add_argument("--verbose", action="store_true")
    return ap.parse_args()


def ensure_sqlite_exists(path: str) -> None:
    if not os.path.exists(path):
        raise SystemExit(f"SQLite database file not found: {path}")


def create_tables(pg_engine) -> None:
    Base.metadata.create_all(pg_engine)


def sqlite_connection(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def load_table_names(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cur.fetchall()}


def table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def sqlite_to_dicts(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    cur = conn.execute(f"SELECT * FROM {table_name}")
    return [dict(row) for row in cur.fetchall()]


def parse_json_value(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        try:
            return json.loads(s)
        except Exception:
            return value
    return value


def parse_uuid(value):
    if value is None or value == "":
        return None
    return UUID(str(value))


def parse_enum(enum_cls: type[Enum], value):
    if value is None or isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except Exception:
        return value


def upsert_permission(db: Session, key: str, description: str) -> RBACPermission:
    row = db.execute(select(RBACPermission).where(RBACPermission.key == key)).scalar_one_or_none()
    if row:
        row.description = description
        return row
    row = RBACPermission(id=uuid4(), key=key, description=description)
    db.add(row)
    db.flush()
    return row


def upsert_role(db: Session, key: str, display_name: str, description: str) -> RBACRole:
    row = db.execute(select(RBACRole).where(RBACRole.key == key)).scalar_one_or_none()
    if row:
        row.display_name = display_name
        row.description = description
        return row
    row = RBACRole(id=uuid4(), key=key, display_name=display_name, description=description)
    db.add(row)
    db.flush()
    return row


def ensure_role_permission(db: Session, role: RBACRole, perm: RBACPermission) -> None:
    exists = db.execute(
        select(RolePermission)
        .where(RolePermission.role_id == role.id)
        .where(RolePermission.permission_id == perm.id)
    ).scalar_one_or_none()
    if not exists:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))


def ensure_permission_implies(db: Session, parent: RBACPermission, child: RBACPermission) -> None:
    exists = db.execute(
        select(PermissionImplies)
        .where(PermissionImplies.parent_permission_id == parent.id)
        .where(PermissionImplies.child_permission_id == child.id)
    ).scalar_one_or_none()
    if not exists:
        db.add(PermissionImplies(parent_permission_id=parent.id, child_permission_id=child.id))


def seed_default_rbac(db: Session) -> None:
    perm_map: dict[str, RBACPermission] = {}
    for p in PERMISSIONS:
        perm_map[p.key] = upsert_permission(db, p.key, p.description)

    for parent_key, child_key in PERMISSION_IMPLIES:
        if parent_key not in perm_map:
            perm_map[parent_key] = upsert_permission(db, parent_key, "")
        if child_key not in perm_map:
            perm_map[child_key] = upsert_permission(db, child_key, "")

    for rdef in DEFAULT_ROLES:
        role = upsert_role(db, rdef.key, rdef.display_name, rdef.description)
        for pkey in rdef.permission_keys:
            ensure_role_permission(db, role, perm_map[pkey])

    for parent_key, child_key in PERMISSION_IMPLIES:
        ensure_permission_implies(db, perm_map[parent_key], perm_map[child_key])


def migrate_members(sqlite_conn: sqlite3.Connection, db: Session, verbose: bool) -> tuple[int, int]:
    if "members" not in load_table_names(sqlite_conn):
        return 0, 0

    src_rows = sqlite_to_dicts(sqlite_conn, "members")
    inserted = 0
    skipped = 0

    with db.no_autoflush:
        for row in src_rows:
            email = row.get("email")
            existing = None
            if email:
                existing = db.execute(select(Member).where(Member.email == email)).scalar_one_or_none()
            if not existing and row.get("id"):
                try:
                    existing = db.get(Member, parse_uuid(row.get("id")))
                except Exception:
                    existing = None
            if existing:
                skipped += 1
                continue

            member = Member(
                id=parse_uuid(row.get("id")) or uuid4(),
                part=parse_enum(Part, row.get("part")),
                generation=row.get("generation"),
                name=row.get("name"),
                name_kana=row.get("name_kana"),
                email=email,
                lecture_day=parse_json_value(row.get("lecture_day")) or [],
                is_competition_member=bool(row.get("is_competition_member")),
            )
            db.add(member)
            inserted += 1
            if verbose and inserted <= 10:
                print(f"[members] insert: {member.email or member.name}")

    return inserted, skipped


def migrate_schedules(sqlite_conn: sqlite3.Connection, db: Session, verbose: bool) -> tuple[int, int]:
    if "schedules" not in load_table_names(sqlite_conn):
        return 0, 0

    cols = table_columns(sqlite_conn, "schedules")
    src_rows = sqlite_to_dicts(sqlite_conn, "schedules")
    inserted = 0
    skipped = 0

    with db.no_autoflush:
        for row in src_rows:
            existing = db.get(Schedule, row.get("date")) if row.get("date") else None
            if existing:
                skipped += 1
                continue

            schedule = Schedule(
                date=row.get("date"),
                type=parse_enum(ScheduleType, row.get("type")),
                generations=parse_json_value(row.get("generations")) if "generations" in cols else None,
                groups=parse_json_value(row.get("groups")) if "groups" in cols else None,
                exclude_groups=parse_json_value(row.get("exclude_groups")) if "exclude_groups" in cols else None,
                is_pre_attendance_target=bool(row.get("is_pre_attendance_target", True)),
            )
            db.add(schedule)
            inserted += 1
            if verbose and inserted <= 10:
                print(f"[schedules] insert: {schedule.date}")

    return inserted, skipped


def main() -> int:
    args = parse_args()
    sqlite_path = args.sqlite_db
    ensure_sqlite_exists(sqlite_path)

    print(f"[migrate_sqlite_to_postgres] sqlite={sqlite_path}")
    print(f"[migrate_sqlite_to_postgres] pg={args.pg_url}")

    pg_engine = create_engine(args.pg_url)
    create_tables(pg_engine)

    with sqlite_connection(sqlite_path) as sqlite_conn:
        with Session(pg_engine) as db:
            seed_default_rbac(db)

            member_inserted, member_skipped = migrate_members(sqlite_conn, db, args.verbose)
            schedule_inserted, schedule_skipped = migrate_schedules(sqlite_conn, db, args.verbose)

            print(
                "[migrate_sqlite_to_postgres] preview: "
                f"members insert={member_inserted} skip={member_skipped}, "
                f"schedules insert={schedule_inserted} skip={schedule_skipped}"
            )

            if not args.commit:
                db.rollback()
                print("[migrate_sqlite_to_postgres] dry-run: no changes applied")
                return 0

            db.commit()

    print("[migrate_sqlite_to_postgres] completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
