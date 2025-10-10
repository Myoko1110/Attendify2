import datetime

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.database import cruds, get_db, models
from app.dependencies import get_valid_session

router = APIRouter(prefix="/schedule", tags=["Schedule"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="予定を取得",
    description="予定を取得します。",
    response_model=list[schemas.Schedule],
)
async def get_schedule(db: AsyncSession = Depends(get_db)):
    return [a for a in await cruds.get_schedules(db)]


@router.post(
    "",
    summary="予定を登録",
    description="予定を登録します。すでに存在する場合は更新されます。",
)
async def post_schedule(s: schemas.Schedule = Body(), db: AsyncSession = Depends(get_db)) -> schemas.ScheduleOperationalResult:
    await cruds.add_schedule(db, models.Schedule(**s.model_dump()))
    return schemas.ScheduleOperationalResult(result=True, date=s.date)


@router.delete(
    "/{date}",
    summary="予定を削除",
    description="予定を削除します。予定が存在しない場合でもエラーを返しません。",
)
async def delete_schedule(date: datetime.date, db: AsyncSession = Depends(get_db)) -> schemas.ScheduleOperationalResult:
    await cruds.remove_schedule(db, date)
    return schemas.ScheduleOperationalResult(result=True, date=date)
