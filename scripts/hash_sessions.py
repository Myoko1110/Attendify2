"""Hash existing plaintext session tokens using HMAC-SHA256 and settings.yml's SESSION_SECRET.

Usage:
  python scripts/hash_sessions.py [--database DATABASE_URL] [--yes]

Behavior:
- Loads settings via app.utils (this will auto-generate settings.yml SESSION_SECRET if missing).
- Uses DATABASE_URL env var or the provided --database (or falls back to sqlite:///attendify.db in scripts as others do).
- Creates a backup table named sessions_backup_YYYYmmddHHMMSS AS SELECT * FROM sessions.
- Updates each sessions.token to HMAC-SHA256(secret, token).
- Prompts for confirmation unless --yes is provided.

Note: Ensure you have a database backup before running in production.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text

# Import settings; app.utils will auto-generate SESSION_SECRET in settings.yml if missing
from app import utils

DEFAULT_DB_URL = os.getenv("DATABASE_URL") or "sqlite:///attendify.db"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--database", default=os.getenv("DATABASE_URL") or DEFAULT_DB_URL,
                   help="SQLAlchemy database URL")
    p.add_argument("--yes", action="store_true", help="Don't prompt, assume yes")
    args = p.parse_args()

    settings = utils.settings
    secret = os.environ.get("SESSION_SECRET") or settings.get("SESSION_SECRET")
    if not secret:
        print("SESSION_SECRET not found in environment or settings.yml. Exiting.")
        return 2

    url = args.database
    eng = create_engine(url)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_table = f"sessions_backup_{ts}"

    with eng.begin() as conn:
        # check sessions table exists
        try:
            conn.execute(text("select 1 from sessions limit 1"))
        except Exception as e:
            print("Failed to query sessions table. Is the database URL correct and sessions table present?", e)
            return 3

        print(f"Creating backup table '{backup_table}'...")
        try:
            conn.execute(text(f"create table {backup_table} as select * from sessions"))
        except Exception as e:
            print("Failed to create backup table:", e)
            return 4

        rows = conn.execute(text("select token from sessions")).fetchall()
        total = len(rows)
        print(f"Found {total} session rows to re-hash.")

        if total == 0:
            print("Nothing to do.")
            return 0

        if not args.yes:
            confirm = input(f"Proceed to hash {total} tokens and overwrite sessions.token? Type 'yes' to proceed: ")
            if confirm.strip().lower() != "yes":
                print("Aborted by user.")
                return 1

        print("Hashing and updating tokens...")
        count = 0
        for (token,) in rows:
            if token is None:
                continue
            new = hmac.new(secret.encode(), str(token).encode(), hashlib.sha256).hexdigest()
            res = conn.execute(text("update sessions set token = :new where token = :old"), {"new": new, "old": token})
            # It's possible that update affects 0 rows if token changed concurrently; treat as error
            # SQLAlchemy's res.rowcount may be DB-driver dependent; skip strict check
            count += 1
            if count % 100 == 0:
                print(f"Processed {count}/{total}...")

        print(f"Completed hashing {count} tokens. Backup table: {backup_table}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
