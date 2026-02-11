"""
Migrate schedules.target -> generations (only handle items starting with "g:").
Usage:
  python scripts/migrate_schedule_target.py --database sqlite:///attendify.db         # dry-run (no changes)
  python scripts/migrate_schedule_target.py --database sqlite:///attendify.db --commit --backup

Behavior:
- Reads `target` column (assumed JSON list) from `schedules` table.
- Ignores elements like "c:Y" or "c:N".
- For elements that start with "g:", parses the text after ':' as int and collects into `generations` list.
- Adds columns `generations`, `groups`, `exclude_groups` if they do not exist.
- Updates `generations` column with JSON list of ints. Leaves `groups`/`exclude_groups` NULL.
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--database", default=os.environ.get("DATABASE_URL", "sqlite:///attendify.db"))
parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
parser.add_argument("--backup", action="store_true", help="Backup sqlite DB file before applying")
parser.add_argument("--verbose", action="store_true")
args = parser.parse_args()

# normalize db path for sqlite:/// prefixed URL
db_url = args.database
if db_url.startswith("sqlite:///"):
    db_path = db_url[len("sqlite:///"):]
else:
    db_path = db_url

if not os.path.exists(db_path):
    print(f"Database file not found: {db_path}")
    sys.exit(1)


def maybe_backup(path: str) -> None:
    if not args.backup:
        return
    stamp = datetime.now().strftime('%Y%m%d%H%M%S')
    dst = f"{path}.bak.{stamp}"
    shutil.copy2(path, dst)
    print(f"Backup saved to: {dst}")


def ensure_columns(conn: sqlite3.Connection) -> list:
    """Ensure generations/groups/exclude_groups columns exist. Return current column names list."""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(schedules)")
    cols = [r[1] for r in cur.fetchall()]
    to_add = []
    if 'generations' not in cols:
        to_add.append("ALTER TABLE schedules ADD COLUMN generations JSON NULL")
    if 'groups' not in cols:
        to_add.append("ALTER TABLE schedules ADD COLUMN groups JSON NULL")
    if 'exclude_groups' not in cols:
        to_add.append("ALTER TABLE schedules ADD COLUMN exclude_groups JSON NULL")
    if to_add:
        print("Adding missing columns:")
        for stmt in to_add:
            print("  ", stmt)
            if args.commit:
                cur.execute(stmt)
        if args.commit:
            conn.commit()
            print("Columns added.")
        # refresh cols
        cur.execute("PRAGMA table_info(schedules)")
        cols = [r[1] for r in cur.fetchall()]
    else:
        if args.verbose:
            print("All target columns already exist.")
    return cols


def parse_generations(target_raw):
    """Given raw target value from DB, return list[int] of generations (g:NN -> NN).
    If parsing fails or no items, return []"""
    if target_raw is None:
        return []
    # target_raw is usually a JSON string in the DB; sqlite returns TEXT
    try:
        parsed = json.loads(target_raw)
    except Exception:
        # If it's not JSON, try to interpret simple comma-separated or single token
        if isinstance(target_raw, str):
            s = target_raw.strip()
            # try to treat as single token list
            parsed = [s]
        else:
            return []
    if not isinstance(parsed, list):
        return []
    gens = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if item.startswith('g:'):
            rest = item.split(':', 1)[1]
            # try int
            try:
                n = int(rest)
                gens.append(n)
            except Exception:
                # skip non-int
                continue
        else:
            # ignore other prefixes per user instruction
            continue
    # deduplicate and sort
    gens = sorted(set(gens))
    return gens


def migrate():
    maybe_backup(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cols = ensure_columns(conn)
    cur = conn.cursor()

    # build SELECT dynamically depending on whether generations column exists
    select_cols = ['date', 'target']
    if 'generations' in cols:
        select_cols.append('generations')
    select_sql = "SELECT " + ", ".join(select_cols) + " FROM schedules"

    cur.execute(select_sql)
    rows = cur.fetchall()
    total = 0
    updated = 0
    skipped = 0
    changes = []

    for r in rows:
        total += 1
        date = r['date']
        target_raw = r['target']
        existing_generations = r['generations'] if 'generations' in cols else None
        gens = parse_generations(target_raw)
        if not gens:
            skipped += 1
            continue
        gens_json = json.dumps(gens, ensure_ascii=False)
        # If existing generations equals gens_json, skip
        if existing_generations is not None:
            try:
                # existing_generations may be stored as JSON string
                if isinstance(existing_generations, str):
                    if json.loads(existing_generations) == gens:
                        skipped += 1
                        continue
                else:
                    # if sqlite gives a Python object (unlikely), compare
                    if existing_generations == gens:
                        skipped += 1
                        continue
            except Exception:
                # fallback to string comparison
                if str(existing_generations) == gens_json:
                    skipped += 1
                    continue
        changes.append((date, gens_json))

    print(f"Rows scanned: {total}, to-update: {len(changes)}, skipped(no gens or already set): {skipped}")
    if args.verbose and changes:
        for date, gens_json in changes[:50]:
            print(f"  DATE={date} -> generations={gens_json}")
    if not args.commit:
        print("Dry-run mode: no changes applied. Run with --commit to apply changes.")
        conn.close()
        return

    # apply updates
    for date, gens_json in changes:
        cur.execute("UPDATE schedules SET generations = ? WHERE date = ?", (gens_json, date))
        updated += 1
    conn.commit()
    conn.close()
    print(f"Applied updates: {updated}")


if __name__ == '__main__':
    migrate()
