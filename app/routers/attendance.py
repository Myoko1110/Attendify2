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
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
)
async def post_attendance(a: schemas.AttendancesParams = Form()) -> schemas.Attendance:
    attendance = models.Attendance(date=a.date, member_id=a.member_id, attendance=a.attendance)

    try:
        attendance = await db.add_attendance(attendance)
    except IntegrityError as e:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")

    return attendance


@router.post(
    "s",
    summary="出欠情報を登録",
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
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


# @router.get(
#     "/rate",
#     summary="出欠率を取得",
#     description="出欠率を取得します。出欠率は全体、パートごと、部員ごとに取得できます。",
# )
# async def get_attendance_rates():
#     rates = await db.get_attendance_rates()
#     return [schemas.AttendanceRate.create(r) for r in rates]
#
#
# @router.post(
#     "/rate/recalc",
#     summary="出欠情報を再計算",
#     description="出欠情報を再計算します。",
# )
# async def recalc_attendance() -> schemas.AttendancesOperationalResult:
#     attendances = Attendances(schemas.Attendance.create(a) for a in await db.get_attendances())
#     schedules = await db.get_schedules()
#
#     rates = []  # type: list[models.AttendanceRate]
#     for actual in (True, False):
#
#         # 全体
#         rates.append(models.AttendanceRate(
#             target_type="all",
#             period_type="all",
#             rate=attendances.calc(actual),
#             actual=actual,
#         ))
#         calculate_attendance_by_date(attendances, schedules, actual=actual, rates=rates, target_type="all")
#
#         # パートごと
#         parts = set(a.member.part for a in attendances)
#         for part in parts:
#             a = Attendances(a for a in attendances if a.member and a.member.part == part)
#             rates.append(models.AttendanceRate(
#                 target_type="part",
#                 target_id=part.value,
#                 period_type="all",
#                 rate=a.calc(actual),
#                 actual=actual,
#             ))
#
#             calculate_attendance_by_date(a, schedules, actual=actual, rates=rates, target_type='part', target=part.value)
#
#         # 部員ごと
#         members = set(a.member_id for a in attendances if a.member_id)
#         for member_id in members:
#             a = Attendances(a for a in attendances if a.member_id == member_id)
#             rates.append(models.AttendanceRate(
#                 target_type='member',
#                 target_id=str(member_id),
#                 period_type='all',
#                 period_value='',
#                 rate=a.calc(actual),
#                 actual=actual,
#             ))
#
#             calculate_attendance_by_date(a, schedules, actual=actual, rates=rates, target_type='member', target=str(member_id))
#
#     await db.clear_attendance_rates()
#     await db.add_attendance_rates(rates)
#     return schemas.AttendancesOperationalResult(result=True)
#
#
# def calculate_attendance_by_date(
#         attendances: list[models.Attendance],
#         schedules: list[models.Schedule],
#         actual: False,
#         rates: list[models.AttendanceRate],
#         target_type: str,
#         target: str | None = None,
# ):
#     for s in schedules:
#         a = Attendances(a for a in attendances if a.date == s.date)
#         rates.append(models.AttendanceRate(
#             target_type=target_type,
#             target_id=target,
#             period_type='date',
#             period_value=s.date.isoformat(),
#             rate=a.calc(actual),
#             actual=actual,
#         ))
#
#     months = set(Month.from_date(s.date) for s in schedules)
#     for month in months:
#         a = Attendances(a for a in attendances if Month.from_date(a.date) == month)
#         rates.append(models.AttendanceRate(
#             target_type=target_type,
#             target_id=target,
#             period_type='month',
#             period_value=str(month),
#             rate=a.calc(actual),
#             actual=actual,
#         ))
#
#
