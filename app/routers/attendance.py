import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Form
from sqlalchemy.exc import IntegrityError

from app import schemas
from app.abc.api_error import APIErrorCode
from app.abc.part import Part
from app.database import db, models
from app.dependencies import get_valid_session

router = APIRouter(prefix="/attendance", tags=["Attendance"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="出欠情報を取得",
    description="出欠情報を取得します。",
)
async def get_attendances(part: Part = None, generation: int = None, date: datetime.date = None) -> list[schemas.Attendance]:
    return [schemas.Attendance.create(a) for a in await db.get_attendances(part=part, generation=generation, date=date)]


@router.post(
    "",
    summary="出欠情報を登録",
    description="出欠情報を登録します。出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
)
async def post_attendance(a: schemas.AttendancesParams = Form()) -> schemas.AttendanceOperationalResult:
    attendance = models.Attendance(date=a.date, member_id=a.member_id, attendance=a.attendance)

    try:
        attendance_id = await db.add_attendance(attendance)
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")

    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)


@router.post(
    "s",
    summary="出欠情報を登録",
    description="出欠情報を登録します。出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
)
async def post_attendances(attendances: list[schemas.AttendancesParams]) -> schemas.AttendancesOperationalResult:
    attendance_list = [models.Attendance(date=a.date, member_id=a.member_id, attendance=a.attendance) for a in attendances]

    try:
        await db.add_attendances(attendance_list)
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")

    return schemas.AttendancesOperationalResult(result=True)


@router.delete(
    "/{attendance_id}",
    summary="出欠情報を削除",
    description="出欠情報を削除します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def delete_attendance(attendance_id: UUID) -> schemas.AttendanceOperationalResult:
    await db.remove_attendance(attendance_id)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)


@router.patch(
    "/{attendance_id}",
    summary="出欠情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_attendance(attendance_id: UUID, attendance: str) -> schemas.AttendanceOperationalResult:
    await db.update_attendance(attendance_id, attendance)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)
