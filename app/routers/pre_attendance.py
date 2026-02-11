import datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db, models
from app.dependencies import get_valid_session
from app.schemas import PreCheck, PreCheckParams

router = APIRouter(prefix="/pre-check", tags=["PreCheck"],
                   dependencies=[Depends(get_valid_session)])


@router.get(
    "/attendances",
    summary="事前出欠情報を取得",
    description="出欠情報を取得します。",
    response_model=list[schemas.PreAttendance],
)
async def get_pre_attendances(member_id: UUID = None, month: str = None, pre_check_id: str = None,
                              db: AsyncSession = Depends(get_db)):
    result = await cruds.get_pre_attendances(db, member_id=member_id, month=month,
                                             pre_check_id=pre_check_id)
    return result


@router.post(
    "/attendances",
    summary="事前出欠情報を登録",
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
    response_model=list[schemas.PreAttendance],
)
async def post_pre_attendances(
        pre_attendances: list[schemas.PreAttendanceParams],
        overwrite: bool = False,
        db: AsyncSession = Depends(get_db), ):
    pre_attendance_list = [models.PreAttendance(**a.model_dump()) for a in pre_attendances]

    if not pre_attendance_list:
        return []

    try:
        result = await cruds.add_pre_attendances(db, pre_attendance_list, overwrite)
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists pre-attendance")

    return result


@router.delete(
    "/attendance/{pre_attendance_id}",
    summary="出欠情報を削除",
    description="出欠情報を削除します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def delete_pre_attendance(pre_attendance_id: UUID, db: AsyncSession = Depends(
    get_db)) -> schemas.AttendanceOperationalResult:
    await cruds.remove_pre_attendance(db, pre_attendance_id)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=pre_attendance_id)


@router.delete(
    "/attendances",
    summary="出欠情報を削除"
)
async def bulk_delete_pre_attendances(pre_attendance_ids: list[UUID], db: AsyncSession = Depends(get_db)):
    await cruds.bulk_remove_pre_attendances(db, pre_attendance_ids)
    return dict(result=True)


@router.patch(
    "/attendance/{attendance_id}",
    summary="出欠情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_pre_attendance(pre_attendance_id: UUID,
                               attendance: str,
                               db: AsyncSession = Depends(
                                   get_db)) -> schemas.AttendanceOperationalResult:
    await cruds.update_pre_attendance(db, pre_attendance_id, attendance)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=pre_attendance_id)


@router.get(
    "s",
    summary="事前出欠マスタを取得",
    response_model=list[PreCheck],
)
async def get_pre_checks(db: AsyncSession = Depends(get_db)):
    return await cruds.get_pre_checks(db)


@router.get(
    "/{pre_check_id}",
    summary="事前出欠マスタを取得",
    response_model=PreCheck | None,
)
async def get_pre_check(pre_check_id: str, db: AsyncSession = Depends(get_db)):
    return await cruds.get_pre_check_by_id(db, pre_check_id)


@router.post(
    "",
    summary="事前出欠マスタを登録",
    response_model=PreCheck,
)
async def post_pre_check(pre_check: PreCheckParams, db: AsyncSession = Depends(get_db)):
    result = await cruds.add_pre_check(db, models.PreCheck(**pre_check.model_dump()))
    return result


@router.delete(
    "/{pre_check_id}",
    summary="事前出欠マスタを削除",
)
async def delete_pre_check(pre_check_id: str, db: AsyncSession = Depends(get_db)):
    await cruds.remove_pre_check(db, pre_check_id)
    return dict(result=True)


@router.patch(
    "/{pre_check_id}",
    summary="事前出欠マスタを更新",
    response_model=PreCheck,
)
async def patch_pre_check(pre_check_id: str, start_date: datetime.date = Body(),
                          end_date: datetime.date = Body(), description: str = Body(),
                          edit_deadline_days: int = Body(),
                          db: AsyncSession = Depends(get_db)):
    return await cruds.update_pre_check(db, pre_check_id, start_date, end_date, description,
                                        edit_deadline_days)
