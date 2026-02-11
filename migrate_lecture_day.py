"""""
Migration script: move Member.lecture_day (JSON) to WeeklyParticipation rows.
Usage:
  python scripts/migrate_lecture_day.py --dry-run            # default, shows what would change
  python scripts/migrate_lecture_day.py --commit --backup    # perform changes and backup sqlite file if applicable
  python scripts/migrate_lecture_day.py --database sqlite:///attendify.db --commit
"""
import argparse
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Set, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from app.database.models import Member, WeeklyParticipation

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Normalize various weekday representations into 0=Mon ... 6=Sun
JP_MAP = {
    "月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日": 6,
    "月曜": 0, "火曜": 1, "水曜": 2, "木曜": 3, "金曜": 4, "土曜": 5, "日曜": 6,
}
EN_MAP = {
    "mon": 0, "monday": 0,
    "tue": 1, "tues": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thur": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def normalize_weekday(value: Any) -> Optional[int]:
    """Return weekday int 0..6 or None if unrecognizable."""
    if value is None:
        return None
    # integers
    if isinstance(value, int):
        if 0 <= value <= 6:
            return value
        if 1 <= value <= 7:
            return value - 1
        return None

    # strings
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        # numeric string
        if s.isdigit():
            n = int(s)
            if 0 <= n <= 6:
                return n
            if 1 <= n <= 7:
                return n - 1
            return None
        sl = s.lower()
        if sl in EN_MAP:
            return EN_MAP[sl]
        if sl in JP_MAP:
            return JP_MAP[sl]
        # try first 3 letters english
        key3 = sl[:3]
        if key3 in EN_MAP:
            return EN_MAP[key3]
    return None


def extract_weekdays(raw) -> Set[int]:
    """Given raw Member.lecture_day value, return set of valid weekdays (0..6)."""
    result = set()
    if raw is None:
        return result
    # If stored as JSON string
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            # maybe it's a plain string representing a single weekday
            norm = normalize_weekday(raw)
            if norm is not None:
                result.add(norm)
            return result
        raw = parsed

    # Expecting iterable
    if isinstance(raw, (list, tuple, set)):
        for v in raw:
            wd = normalize_weekday(v)
            if wd is not None:
                result.add(wd)
    else:
        # single value
        wd = normalize_weekday(raw)
        if wd is not None:
            result.add(wd)
    return result


def backup_sqlite(database_url: str) -> None:
    """If database_url points to a sqlite file, copy it with .bak timestamp."""
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        path = database_url[len(prefix):]
        p = Path(path)
        if p.exists():
            dest = p.with_suffix(p.suffix + ".bak")
            shutil.copy2(p, dest)
            logger.info("Backed up sqlite file %s -> %s", p, dest)
        else:
            logger.warning("SQLite file %s not found; skipping backup", p)
    else:
        logger.info("Backup only supported for sqlite files; skipping for %s", database_url)


def migrate(session, dry_run: bool = True, default_attendance: Optional[str] = None, is_active_override: Optional[bool] = None) -> dict:
    """Perform migration; if dry_run True, don't modify DB. Returns a summary dict.

    default_attendance: if provided, set this value on created/updated WeeklyParticipation.default_attendance
    is_active_override: if provided (True/False), use this value for created/updated entries; if None, created entries default to True and existing entries keep current is_active unless created.
    """
    members = session.query(Member).all()
    created = 0
    updated = 0
    skipped_invalid = 0
    per_member_actions = []

    for m in members:
        raw = m.lecture_day
        wds = extract_weekdays(raw)
        if not wds:
            continue
        created_for_member = 0
        updated_for_member = 0
        invalid_entries = []
        for wd in sorted(wds):
            existing = session.query(WeeklyParticipation).filter_by(member_id=m.id, weekday=wd).one_or_none()
            if existing:
                # If override flags are provided, update existing rows accordingly
                to_update = False
                if is_active_override is not None and existing.is_active != is_active_override:
                    if not dry_run:
                        existing.is_active = is_active_override
                        session.add(existing)
                    to_update = True
                if default_attendance is not None and existing.default_attendance != default_attendance:
                    if not dry_run:
                        existing.default_attendance = default_attendance
                        session.add(existing)
                    to_update = True
                if to_update:
                    updated += 1
                    updated_for_member += 1
            else:
                # Determine is_active value for new record: override if provided, else True (existing behavior)
                is_active_value = is_active_override if is_active_override is not None else True
                if not dry_run:
                    wp = WeeklyParticipation(member_id=m.id, weekday=wd, is_active=is_active_value, default_attendance=default_attendance)
                    session.add(wp)
                created += 1
                created_for_member += 1

        # After creating/updating participations, clear lecture_day in commit mode
        if not dry_run:
            m.lecture_day = []
            session.add(m)

        per_member_actions.append({
            "member_id": str(m.id),
            "name": m.name,
            "created": created_for_member,
            "updated": updated_for_member,
        })

    summary = {
        "members_scanned": len(members),
        "created": created,
        "updated": updated,
        "skipped_invalid": skipped_invalid,
        "per_member": per_member_actions,
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=os.environ.get("DATABASE_URL", "sqlite:///attendify.db"), help="SQLAlchemy database URL")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--backup", action="store_true", help="Backup sqlite DB file before applying")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--default-attendance", dest="default_attendance", help="Set default_attendance for created/updated WeeklyParticipation entries")
    parser.add_argument("--default-attendance-fallback", dest="default_attendance_fallback", help="Fallback default_attendance used when --default-attendance is not provided; can also be set via DEFAULT_ATTENDANCE_DEFAULT env var")
    parser.add_argument("--is-active", dest="is_active", choices=["true", "false"], help="Set is_active for created/updated WeeklyParticipation entries (true/false). If omitted, created entries default to True and existing entries are unchanged unless this flag is provided.")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if args.backup and args.commit:
        backup_sqlite(args.database)

    engine = create_engine(args.database, future=True)
    Session = sessionmaker(bind=engine, future=True)

    # parse is_active arg into Optional[bool]
    is_active_override: Optional[bool] = None
    if getattr(args, "is_active", None) is not None:
        is_active_override = True if args.is_active.lower() == "true" else False

    # Determine final default_attendance with precedence:
    # 1) --default-attendance (per-run explicit)
    # 2) --default-attendance-fallback (CLI fallback)
    # 3) DEFAULT_ATTENDANCE_DEFAULT environment variable
    default_attendance_arg = getattr(args, "default_attendance", None)
    if default_attendance_arg is not None:
        final_default_attendance = default_attendance_arg
    else:
        final_default_attendance = getattr(args, "default_attendance_fallback", None) or os.environ.get("DEFAULT_ATTENDANCE_DEFAULT")

    with Session() as session:
        try:
            summary = migrate(session, dry_run=not args.commit, default_attendance=final_default_attendance, is_active_override=is_active_override)
            logger.info("Migration scan complete: members=%d created=%d updated=%d", summary["members_scanned"], summary["created"], summary["updated"])
            if args.commit:
                try:
                    session.commit()
                    logger.info("Changes committed.")
                except IntegrityError as e:
                    logger.error("IntegrityError during commit: %s", e)
                    session.rollback()
            else:
                logger.info("Dry-run mode: no changes were committed. Rerun with --commit to apply.")
        except Exception as e:
            logger.exception("Unexpected error during migration: %s", e)


if __name__ == "__main__":
    main()
