import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, BackgroundTasks
from fastapi.params import Form
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, utils
from app.abc.api_error import APIErrorCode
from app.abc.attendance_log_type import AttendanceLogType
from app.database import cruds, get_db, models
from app.dependencies import get_valid_session, require_permission
from app.routers.attendance import recalculate_attendance_rates_bulk
from app.schemas import AttendanceLogWithAttendance, Session
from app.utils import JST

router = APIRouter(prefix="/attendance-log", tags=["AttendanceLog"],
                   dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="出席ログを取得",
    description="出席ログを取得します。",
    response_model=list[schemas.AttendanceLog],
    dependencies=[Depends(require_permission("attendance-log:read"))],
)
async def get_attendance_logs(member_id: UUID = None, terminal_member_id: UUID = None,
                              start: datetime.datetime = None, end: datetime.datetime = None,
                              limit: int = Query(None, ge=1), offset: int = Query(None, ge=0),
                              db: AsyncSession = Depends(get_db)):
    return await cruds.get_attendance_logs(db, member_id=member_id,
                                           terminal_member_id=terminal_member_id,
                                           start=start, end=end, limit=limit, offset=offset)


@router.get(
    "/{attendance_log_id}",
    summary="出席ログを取得(単体)",
    description="1件の出席ログを取得します。",
    response_model=schemas.AttendanceLog,
    dependencies=[Depends(require_permission("attendance-log:read"))],
)
async def get_attendance_log(attendance_log_id: UUID, db: AsyncSession = Depends(get_db)):
    return await cruds.get_attendance_log_by_id(db, attendance_log_id)


def _is_before(time_point: datetime.datetime, boundary: datetime.datetime) -> bool:
    return time_point < boundary


def _is_attendance_unique_violation(exc: IntegrityError) -> bool:
    """attendances(date, member_id) の一意制約違反かどうかを判定する。"""
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False

    msg = str(orig)
    return (
            "attendances_date_member_id_key" in msg
            or ("attendances" in msg and "date" in msg and "member_id" in msg)
    )


@router.post(
    "",
    summary="出席ログを登録",
    description="出席ログを登録します。",
    response_model=schemas.AttendanceLogWithAttendance,
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def post_attendance_log(member_id: UUID = Body(),
                              session: Session = Depends(get_valid_session),
                              background_tasks: BackgroundTasks = BackgroundTasks(),
                              db: AsyncSession = Depends(get_db)):
    now = utils.now()
    now_jst = now.astimezone(JST)
    today_jst = now_jst.date()

    schedule = await cruds.get_schedule(db, today_jst)
    if not schedule:
        raise APIErrorCode.SCHEDULE_NOT_FOUND.of(
            f"Schedule for {today_jst} is not registered.", 404
        )
    if not schedule.start_time or not schedule.end_time:
        raise APIErrorCode.INVALID_SCHEDULE.of(
            "Start/End time is not set for this schedule.", 400
        )

    start_dt = datetime.datetime.combine(today_jst, schedule.start_time, tzinfo=JST)
    end_dt = datetime.datetime.combine(today_jst, schedule.end_time, tzinfo=JST)

    existing_attendance = await cruds.get_attendance(db, member_id, today_jst)
    if existing_attendance:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Attendance already exists", 409)

    attendance_logs = await cruds.get_attendance_logs(
        member_id=member_id,
        date=today_jst,
        db=db,
    )
    first_tap_log = min(attendance_logs, key=lambda x: x.timestamp) if attendance_logs else None
    first_tap_at = first_tap_log.timestamp.astimezone(JST) if first_tap_log else None

    log_type = AttendanceLogType.IN
    stmt = None

    def _attendance_values(attendance: str, *, first_tap_at: datetime.datetime | None = None,
                           last_tap_at: datetime.datetime | None = None) -> dict:
        return {
            "date": today_jst,
            "member_id": member_id,
            "attendance": attendance,
            "first_tap_at": first_tap_at,
            "last_tap_at": last_tap_at,
        }

    # 1回目なし
    if first_tap_at is None:
        if _is_before(now_jst, start_dt):  # 開始前
            new_status = "出席"
        elif _is_before(now_jst, end_dt):  # 開始後～終了前
            new_status = "遅刻"
        else:  # 終了後
            new_status = "遅刻"
            log_type = AttendanceLogType.OUT
            stmt = insert(models.Attendance).values(
                _attendance_values(new_status, first_tap_at=now)
            )

    # 1回目あり
    else:
        log_type = AttendanceLogType.OUT
        stay_duration = now_jst - first_tap_at
        if stay_duration < datetime.timedelta(minutes=5):
            raise APIErrorCode.DURATION_TOO_SHORT.of(
                "Stay duration is too short (< 5 minutes).", 409
            )

        if _is_before(now_jst, start_dt):  # 開始前
            raise APIErrorCode.INVALID_CHECK_OUT_TIME.of(
                "Second tap before start time is invalid.", 409
            )
        elif _is_before(now_jst, end_dt):  # 開始後～終了前
            new_status = "早退" if _is_before(first_tap_at, start_dt) else "遅早"
            stmt = insert(models.Attendance).values(
                _attendance_values(
                    new_status,
                    first_tap_at=first_tap_log.timestamp,
                    last_tap_at=now,
                )
            )
        else:  # 終了後
            new_status = "出席" if _is_before(first_tap_at, start_dt) else "遅刻"
            stmt = insert(models.Attendance).values(
                _attendance_values(
                    new_status,
                    first_tap_at=first_tap_log.timestamp,
                    last_tap_at=now,
                )
            )

    al = models.AttendanceLog(
        member_id=member_id,
        terminal_member_id=session.member.id,
        timestamp=now,
        type=log_type,
    )
    db.add(al)

    if stmt is not None:
        stmt = stmt.on_conflict_do_update(
            index_elements=["date", "member_id"],
            set_={
                "attendance": stmt.excluded.attendance,
                "is_disabled": False,
                "updated_at": utils.now(),
            },
        )
        await db.execute(stmt)

        background_tasks.add_task(recalculate_attendance_rates_bulk, now.strftime("%Y-%m"))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _is_attendance_unique_violation(exc):
            raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Attendance already exists", 409)
        raise
    await db.refresh(al)
    await db.refresh(al, ["member"])

    attendance_log = AttendanceLogWithAttendance.model_validate({
        "id": al.id,
        "member_id": al.member_id,
        "timestamp": al.timestamp,
        "terminal_member_id": al.terminal_member_id,
        "member": al.member,
        "attendance": new_status,
        "type": log_type,
    })
    return attendance_log


@router.post(
    "s",
    summary="出席ログを一括登録",
    description="複数の出席ログを一括登録します。",
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def post_attendance_logs(member_ids: list[UUID] = Body(...),
                               session: Session = Depends(get_valid_session),
                               db: AsyncSession = Depends(get_db)):
    logs = [models.AttendanceLog(member_id=m, terminal_member_id=session.member.id) for m in
            member_ids]
    try:
        res = await cruds.add_attendance_logs(db, logs)
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Some AttendanceLog entries conflict", 409)
    return res


@router.delete(
    "/{attendance_log_id}",
    summary="出席ログを削除",
    description="出席ログを削除します。存在しない場合でもエラーにしません。",
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def delete_attendance_log(attendance_log_id: UUID, db: AsyncSession = Depends(
    get_db)) -> schemas.AttendanceOperationalResult:
    await cruds.remove_attendance_log(db, attendance_log_id)
    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_log_id)


@router.delete(
    "s",
    summary="出席ログを一括削除",
    description="複数の出席ログを一括削除します。",
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def bulk_delete_attendance_logs(attendance_log_ids: list[UUID] = Body(...),
                                      db: AsyncSession = Depends(
                                          get_db)) -> schemas.AttendancesOperationalResult:
    await cruds.remove_attendance_logs(db, attendance_log_ids)
    return schemas.AttendancesOperationalResult(result=True)


@router.post(
    "/felica",
    summary="出席ログを登録",
    description="出席ログを登録します。",
    response_model=schemas.AttendanceLogWithAttendance,
)
async def post_attendance_log_by_felica_idm(
        felica_idm: Annotated[str, Form()],
        session: Session = Depends(get_valid_session),
        db: AsyncSession = Depends(get_db)
):
    member = await cruds.get_member_by_felica_idm(db, felica_idm)
    if not member:
        raise APIErrorCode.FELICA_NOT_FOUND.of(f"Member not found for Felica IDM", 404)

    return await post_attendance_log(member.id, session, db=db)


@router.post(
    "/studentid",
    summary="出席ログを登録",
    description="出席ログを登録します。",
    response_model=schemas.AttendanceLogWithAttendance,
)
async def post_attendance_log_by_studentid(
        student_id: Annotated[int, Form()],
        session: Session = Depends(get_valid_session),
        db: AsyncSession = Depends(get_db)
):
    member = await cruds.get_member_by_studentid(db, student_id)
    if not member:
        raise APIErrorCode.FELICA_NOT_FOUND.of(f"Member not found for Student ID", 404)

    return await post_attendance_log(member.id, session, db=db)
