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
from app.utils import determine_attendance_status_utc

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
    jst_date = now.astimezone(ZoneInfo("Asia/Tokyo")).date()

    # 1. 必要なデータの取得（スケジュールと既存出欠）
    schedule = await cruds.get_schedule(db, jst_date)

    if not schedule:
        raise APIErrorCode.SCHEDULE_NOT_FOUND.of(
            f"Schedule for {jst_date} is not registered.", 404
        )

    if not schedule.start_time or not schedule.end_time:
        raise APIErrorCode.INVALID_SCHEDULE.of(
            "Start/End time is not set for this schedule.", 400
        )

    attendance = await cruds.get_attendance(db, member_id, jst_date)

    # 2. ステータスの判定
    new_status = determine_attendance_status_utc(
        now_utc=now,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        existing_status=attendance.attendance if attendance else None
    )

    # 3. Attendanceレコードの準備 (Upsert)
    if not attendance:
        attendance = models.Attendance(
            member_id=member_id,
            date=jst_date,
            attendance=new_status,
            first_tap_at=now,
        )
        db.add(attendance)
    else:
        attendance.attendance = new_status
        attendance.last_tap_at = now

    # 4. ログの作成と保存
    al = models.AttendanceLog(
        member_id=member_id,
        terminal_member_id=session.member.id,
        timestamp=now
    )
    db.add(al)

    try:
        await db.commit()
        await db.refresh(al)
        # Build schema from SQLAlchemy object attributes and include attendance
        attendance_log = AttendanceLogWithAttendance.model_validate({
            "id": al.id,
            "member_id": al.member_id,
            "timestamp": al.timestamp,
            "terminal_member_id": al.terminal_member_id,
            "member": al.member,
            "attendance": new_status,
        })
        return attendance_log
    except IntegrityError:
        await db.rollback()
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Duplicate request", 409)


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
