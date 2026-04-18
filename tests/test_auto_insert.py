import asyncio
import datetime

import pytest

from app.database import async_session, cruds, models

# NOTE: このテストは本番の DB に依存するため、通常はテスト用 DB を準備する必要があります。
# ここでは基本的な呼び出しが例外を投げないことを確認するサモル的テストを用意します。

@pytest.mark.asyncio
async def test_auto_insert_runs_without_exception():
    date = datetime.date.today()
    async with async_session() as db:
        # 実行して例外が出ないことを確認
        res = await cruds.auto_insert_daily_attendances(db, date)
        assert isinstance(res, list)
