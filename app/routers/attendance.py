import datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Form
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.abc.api_error import APIErrorCode
from app.abc.part import Part
from app.database import async_session, cruds, get_db, models
from app.dependencies import get_valid_session
from app.utils import Attendances

router = APIRouter(prefix="/attendance", tags=["Attendance"],
                   dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="出欠情報を取得",
    description="出欠情報を取得します。",
    response_model=list[schemas.Attendance],
)
async def get_attendances(part: Part = None, generation: int = None, date: datetime.date = None,
                          month: str = None, db: AsyncSession = Depends(get_db)):
    return [a for a in
            await cruds.get_attendances(db, part=part, generation=generation, date=date,
                                        month=month)]


@router.post(
    "",
    summary="出欠情報を登録",
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
    response_model=schemas.Attendance,
)
async def post_attendance(
    a: schemas.AttendancesParams = Form(),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    attendance_params = models.Attendance(**a.model_dump())
    try:
        attendance = await cruds.add_attendance(db, attendance_params)

        # 出欠率の再計算処理をバックグラウンドタスクに移動
        updated_month = attendance.date.strftime("%Y-%m")
        background_tasks.add_task(recalculate_attendance_rates, updated_month, attendance)

        await db.refresh(attendance, ["member"])
        return attendance
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")


async def recalculate_attendance_rates(updated_month: str, attendance: models.Attendance):
    async with async_session() as db:
        all_attendances = Attendances(*(await cruds.get_attendances(db, month=updated_month)))

        attendance_rates = [
            models.AttendanceRate(target_type="all", month=updated_month,
                                  rate=all_attendances.calc(False), actual=False),
            models.AttendanceRate(target_type="all", month=updated_month,
                                  rate=all_attendances.calc(True), actual=True),
        ]

        part_attendances = all_attendances.filter_by_part(attendance.member.part)
        attendance_rates.append(
            models.AttendanceRate(target_type="part", target_id=attendance.member.part.value,
                                  month=updated_month,
                                  rate=part_attendances.calc(False), actual=False))
        attendance_rates.append(
            models.AttendanceRate(target_type="part", target_id=attendance.member.part.value,
                                  month=updated_month,
                                  rate=part_attendances.calc(True), actual=True))

        member_attendances = all_attendances.filter_by_member(attendance.member)
        attendance_rates.append(
            models.AttendanceRate(target_type="member", target_id=str(attendance.member.id),
                                  month=updated_month, rate=member_attendances.calc(False),
                                  actual=False))
        attendance_rates.append(
            models.AttendanceRate(target_type="member", target_id=str(attendance.member.id),
                                  month=updated_month, rate=member_attendances.calc(True),
                                  actual=True))

        await cruds.add_attendance_rates(db, attendance_rates)
        await db.commit()


@router.post(
    "s",
    summary="出欠情報を登録",
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
)
async def post_attendances(
        attendances: list[schemas.AttendancesParams],
        db: AsyncSession = Depends(get_db)) -> schemas.AttendancesOperationalResult:
    attendance_list = [models.Attendance(**a.model_dump()) for a in attendances]

    try:
        await cruds.add_attendances(db, attendance_list)
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")

    return schemas.AttendancesOperationalResult(result=True)


@router.delete(
    "/{attendance_id}",
    summary="出欠情報を削除",
    description="出欠情報を削除します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def delete_attendance(attendance_id: UUID, db: AsyncSession = Depends(
    get_db)) -> schemas.AttendanceOperationalResult:
    await cruds.remove_attendance(db, attendance_id)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)


@router.patch(
    "/{attendance_id}",
    summary="出欠情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_attendance(attendance_id: UUID,
                           attendance: str, db: AsyncSession = Depends(
            get_db)) -> schemas.AttendanceOperationalResult:
    await cruds.update_attendance(db, attendance_id, attendance)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)


@router.get(
    "/rate",
    summary="出欠率を取得",
    description="出欠率を取得します。出欠率は全体、パートごと、部員ごとに取得できます。",
    response_model=list[schemas.AttendanceRate],
)
async def get_attendance_rates(db: AsyncSession = Depends(get_db)):
    return await cruds.get_attendance_rates(db)


@router.post(
    "/rate/recalc",
    summary="出欠情報を再計算",
    description="出欠情報を再計算します。",
)
async def recalc_attendance(
        db: AsyncSession = Depends(get_db)) -> schemas.AttendancesOperationalResult:
    attendances = await cruds.get_attendances(db, member=True)
    schedules = await cruds.get_schedules(db)
    months = sorted(set(schedule.date.strftime("%Y-%m") for schedule in schedules))
    dates = sorted(set(schedule.date for schedule in schedules))

    attendance_rates: list[models.AttendanceRate] = []

    for month in months:
        all_attendances = Attendances(
            *[a for a in attendances if a.date.strftime("%Y-%m") == month and a.member is not None and a.date in dates])
        attendance_rates.append(
            models.AttendanceRate(target_type="all", month=month, rate=all_attendances.calc(False),
                                  actual=False))
        attendance_rates.append(
            models.AttendanceRate(target_type="all", month=month, rate=all_attendances.calc(True),
                                  actual=True))

        for part in Part:
            part_attendances = all_attendances.filter_by_part(part)
            attendance_rates.append(
                models.AttendanceRate(target_type="part", target_id=part.value, month=month,
                                      rate=part_attendances.calc(False), actual=False))
            attendance_rates.append(
                models.AttendanceRate(target_type="part", target_id=part.value, month=month,
                                      rate=part_attendances.calc(True), actual=True))

        for member in set(a.member for a in all_attendances):
            member_attendances = all_attendances.filter_by_member(member)
            attendance_rates.append(
                models.AttendanceRate(target_type="member", target_id=str(member.id), month=month,
                                      rate=member_attendances.calc(False), actual=False))
            attendance_rates.append(
                models.AttendanceRate(target_type="member", target_id=str(member.id), month=month,
                                      rate=member_attendances.calc(True), actual=True))

    await cruds.clear_attendance_rates(db)
    await cruds.add_attendance_rates(db, attendance_rates)
    await db.commit()

    return schemas.AttendancesOperationalResult(result=True)
