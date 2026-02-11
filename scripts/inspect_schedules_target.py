"""
Inspect schedules table columns and sample target values.
Usage:
  python scripts/inspect_schedules_target.py --database sqlite:///attendify.db
"""
import argparse
import sqlite3
import json
import os

parser = argparse.ArgumentParser()
parser.add_argument("--database", default="sqlite:///attendify.db")
args = parser.parse_args()

db_url = args.database
if db_url.startswith("sqlite:///"):
    db_path = db_url[len("sqlite:///"):]
else:
    db_path = db_url

if not os.path.exists(db_path):
    print(f"Database file not found: {db_path}")
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("PRAGMA table_info(schedules)")
cols = cur.fetchall()
print("COLUMNS:")
for c in cols:
    print(c)

# find index of target column if present
col_names = [c[1] for c in cols]
print('\nCOLUMN NAMES:', col_names)

if 'target' not in col_names:
    print('\nNo target column found.')
else:
    print('\nSample target values (up to 20):')
    cur.execute('SELECT date, target FROM schedules LIMIT 20')
    rows = cur.fetchall()
    for date, target in rows:
        print('DATE=', date, 'TARGET=', target)

conn.close()
print('\nDone')
