import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, Query
from fastapi.params import Form
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas, utils
from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db, models
from app.dependencies import get_valid_session, require_permission
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


@router.post(
    "",
    summary="出席ログを登録",
    description="出席ログを登録します。",
    response_model=schemas.AttendanceLogWithAttendance,
    dependencies=[Depends(require_permission("attendance-log:write"))],
)
async def post_attendance_log(member_id: UUID = Body(),
                              session: Session = Depends(get_valid_session),
                              db: AsyncSession = Depends(get_db)):
    now = utils.now()
    now_jst = now.astimezone(JST)
    today_jst = now_jst.date()
    jst_date = now.astimezone(ZoneInfo("Asia/Tokyo")).date()

    schedule = await cruds.get_schedule(db, jst_date)
    if not schedule:
        raise APIErrorCode.SCHEDULE_NOT_FOUND.of(
            f"Schedule for {jst_date} is not registered.", 404
        )
    if not schedule.start_time or not schedule.end_time:
        raise APIErrorCode.INVALID_SCHEDULE.of(
            "Start/End time is not set for this schedule.", 400
        )

    start_dt = datetime.datetime.combine(today_jst, schedule.start_time).replace(tzinfo=JST)
    end_dt = datetime.datetime.combine(today_jst, schedule.end_time).replace(tzinfo=JST)

    existing_attendance = await cruds.get_attendance(db, member_id, jst_date)
    if existing_attendance:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Attendance already exists", 409)

    attendance_logs = await cruds.get_attendance_logs(
        member_id=member_id,
        date=today_jst,
        limit=1,
        db=db,
    )
    first_tap_at = attendance_logs[0].timestamp.astimezone(JST) if attendance_logs else None

    # 1回目なし
    if first_tap_at is None:
        if _is_before(now_jst, start_dt):
            new_status = "出席"
        elif _is_before(now_jst, end_dt):
            new_status = "遅刻"
        else:
            new_status = "欠席"
    # 1回目あり
    else:
        if _is_before(now_jst, start_dt):
            raise APIErrorCode.INVALID_CHECK_OUT_TIME.of(
                "Second tap before start time is invalid.", 409
            )
        elif _is_before(now_jst, end_dt):
            new_status = "早退" if _is_before(first_tap_at, start_dt) else "遅早"
            attendance = models.Attendance(
                date=today_jst,
                member_id=member_id,
                attendance=new_status,
                first_tap_at=attendance_logs[0].timestamp,
                last_tap_at=now,
            )
            db.add(attendance)
        else:
            new_status = "出席" if _is_before(first_tap_at, start_dt) else "遅刻"
            attendance = models.Attendance(
                date=today_jst,
                member_id=member_id,
                attendance=new_status,
                first_tap_at=attendance_logs[0].timestamp,
                last_tap_at=now,
            )
            db.add(attendance)

    al = models.AttendanceLog(
        member_id=member_id,
        terminal_member_id=session.member.id,
        timestamp=now,
    )
    db.add(al)
    await db.commit()
    await db.refresh(al)

    attendance_log = AttendanceLogWithAttendance.model_validate({
        "id": al.id,
        "member_id": al.member_id,
        "timestamp": al.timestamp,
        "terminal_member_id": al.terminal_member_id,
        "member": al.member,
        "attendance": new_status,
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
        felica_idm: str = Form(),
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
        student_id: int = Form(),
        session: Session = Depends(get_valid_session),
        db: AsyncSession = Depends(get_db)
):
    member = await cruds.get_member_by_studentid(db, student_id)
    if not member:
        raise APIErrorCode.FELICA_NOT_FOUND.of(f"Member not found for Student ID", 404)

    return await post_attendance_log(member.id, session, db=db)
