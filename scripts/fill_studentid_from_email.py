"""Fill members.studentid from the first 8 digits of email.

This script updates only members whose email starts with 8 digits.
It skips rows when the first 8 characters are not all digits.

Usage:
  python scripts/fill_studentid_from_email.py

Environment:
  DATABASE_URL (optional)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"

FIRST_EIGHT_DIGITS = re.compile(r"^(\d{8})")


def main() -> int:
    url = os.getenv("DATABASE_URL") or DEFAULT_DB_URL
    eng = create_engine(url)

    with eng.begin() as c:
        rows = c.execute(
            text(
                "SELECT id, email, studentid "
                "FROM members "
                "WHERE email IS NOT NULL AND email <> ''"
            )
        ).fetchall()

        updated = 0
        skipped = 0

        for member_id, email, studentid in rows:
            if studentid is not None:
                skipped += 1
                continue

            if not isinstance(email, str):
                skipped += 1
                continue

            m = FIRST_EIGHT_DIGITS.match(email)
            if not m:
                skipped += 1
                continue

            c.execute(
                text("UPDATE members SET studentid = :studentid WHERE id = :id"),
                {"studentid": int(m.group(1)), "id": member_id},
            )
            updated += 1

    print(f"updated={updated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
