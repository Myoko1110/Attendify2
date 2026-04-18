"""毎日指定時刻に実行するためのスクリプト。

使い方（PowerShell）:
python scripts/auto_insert_daily_attendance.py [YYYY-MM-DD]
引数が無ければ今日の日付で実行。
"""
import asyncio
import datetime
import logging
import sys

from app.database import async_session, cruds

logging.basicConfig(level=logging.INFO)


async def main(date: datetime.date):
    async with async_session() as db:
        try:
            inserted = await cruds.auto_insert_daily_attendances(db, date)
            logging.info("auto_insert_daily_attendances inserted=%d for date=%s", len(inserted), date)
        except Exception:
            logging.exception("Failed to run auto_insert_daily_attendances for date=%s", date)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        date = datetime.date.fromisoformat(sys.argv[1])
    else:
        # default: today in server local timezone
        date = datetime.date.today()
    asyncio.run(main(date))
