import datetime

from app.database import async_session, cruds
from app.utils import determine_attendance_status_utc

# NOTE: このテストは本番の DB に依存するため、通常はテスト用 DB を準備する必要があります。
# ここでは基本的な呼び出しが例外を投げないことを確認するサモル的テストを用意します。


async def test_auto_insert_runs_without_exception():
    date = datetime.date.today()
    async with async_session() as db:
        # 実行して例外が出ないことを確認
        res = await cruds.auto_insert_daily_attendances(db, date)
        assert isinstance(res, list)


def test_determine_attendance_status_utc_cases():
    start_time = datetime.time(9, 0)
    end_time = datetime.time(14, 0)

    cases = [
        (datetime.datetime(2026, 4, 19, 0, 0, tzinfo=datetime.timezone.utc), None, "出席"),
        (datetime.datetime(2026, 4, 19, 0, 30, tzinfo=datetime.timezone.utc), None, "早退"),
        (datetime.datetime(2026, 4, 19, 14, 30, tzinfo=datetime.timezone.utc), None, "遅刻"),
        (datetime.datetime(2026, 4, 19, 6, 0, tzinfo=datetime.timezone.utc), "遅刻", "遅早"),
        (datetime.datetime(2026, 4, 19, 14, 30, tzinfo=datetime.timezone.utc), "早退", "遅早"),
    ]

    for now_utc, existing_status, expected in cases:
        assert determine_attendance_status_utc(
            now_utc=now_utc,
            start_time=start_time,
            end_time=end_time,
            existing_status=existing_status,
        ) == expected
