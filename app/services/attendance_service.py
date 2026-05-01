from datetime import date
import logging

from app.database import async_session, cruds

logger = logging.getLogger(__name__)


async def auto_insert_daily_attendances():
    """APScheduler から呼ばれるジョブ関数。

    APScheduler の job 呼び出しは sync/async の両方サポートされますが、AsyncIOScheduler は
    非同期関数を await してくれるため async 関数にしてあります。
    """
    today = date.today()
    print(f"auto_insert_daily_attendances called for date={today}")
    async with async_session() as db:
        try:
            inserted = await cruds.auto_insert_daily_attendances(db, today)
            print(inserted)
            print(f"auto_insert_daily_attendances inserted={len(inserted)} for date={today}")
        except Exception:
            logger.exception("auto_insert_daily_attendances failed for date=%s", today)
