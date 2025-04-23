import datetime

from fastapi import APIRouter, Depends, Query

from app import schemas
from app.database import db, models
from app.dependencies import get_valid_session

router = APIRouter(prefix="/schedule", tags=["Schedule"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="予定を取得",
    description="予定を取得します。",
)
async def get_schedule() -> list[schemas.Schedule]:
    return [schemas.Schedule.create(a) for a in await db.get_schedules()]


@router.post(
    "",
    summary="予定を登録",
    description="予定を登録します。すでに存在する場合は更新されます。",
)
async def post_schedule(s: schemas.Schedule = Query()) -> schemas.ScheduleOperationalResult:
    await db.add_schedule(models.Schedule(date=s.date, type=s.type))
    return schemas.ScheduleOperationalResult(result=True, date=s.date)


@router.delete(
    "/{date}",
    summary="予定を削除",
    description="予定を削除します。予定が存在しない場合でもエラーを返しません。",
)
async def delete_schedule(date: datetime.date) -> schemas.ScheduleOperationalResult:
    await db.remove_schedule(date)
    return schemas.ScheduleOperationalResult(result=True, date=date)
