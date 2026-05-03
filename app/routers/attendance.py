import datetime
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.abc.api_error import APIErrorCode
from app.abc.part import Part
from app.database import async_session, cruds, get_db, models
from app.dependencies import get_valid_session, require_permission
from app.utils import Attendances

# uvicorn の既定ハンドラ/フォーマッタを使って出力形式を統一する
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/attendance", tags=["Attendance"],
                   dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="出欠情報を取得",
    description="出欠情報を取得します。",
    response_model=list[schemas.Attendance],
    dependencies=[Depends(require_permission("attendance:read"))],
)
async def get_attendances(part: Part = None, generation: int = None, date: datetime.date = None,
                          month: str = None, db: AsyncSession = Depends(get_db)):
    return await cruds.get_attendances(db, part=part, generation=generation, date=date, month=month)


@router.post(
    "",
    summary="出欠情報を登録",
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
    response_model=schemas.Attendance,
    dependencies=[Depends(require_permission("attendance:write"))],
)
async def post_attendance(
        background_tasks: BackgroundTasks,
        a: schemas.AttendancesParams = Form(),
        db: AsyncSession = Depends(get_db),
        overwrite: bool = Query(False, description="重複があった場合に上書きする")
):
    attendance_params = models.Attendance(**a.model_dump())
    try:
        attendance = await cruds.add_attendance(db, attendance_params, overwrite=overwrite)

        # 単発登録でも月再構築ロジックに統一してズレを防ぐ
        updated_month = attendance.date.strftime("%Y-%m")
        background_tasks.add_task(recalculate_attendance_rates_bulk, updated_month)

        await db.refresh(attendance, ["member"])
        return attendance
    except IntegrityError:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")


async def recalculate_attendance_rates(updated_month: str, attendance: models.Attendance):
    # 互換のため残す: 旧呼び出し経路も月再構築ロジックへ委譲する
    logger.info(
        f"recalculate_attendance_rates delegated to bulk month={updated_month} "
        f"attendance_id={getattr(attendance, 'id', None)}"
    )
    await recalculate_attendance_rates_bulk(updated_month)


@router.post(
    "s",
    summary="出欠情報を登録",
    description="出欠情報を登録します。すでに出欠情報（同じ部員・日にち）が存在する場合はエラーを返します。",
    dependencies=[Depends(require_permission("attendance:write"))],
)
async def post_attendances(
        attendances: list[schemas.AttendancesParams],
        background_tasks: BackgroundTasks,
        db: AsyncSession = Depends(get_db),
        overwrite: bool = Query(False,
                                description="重複があった場合に上書きする")) -> schemas.AttendancesOperationalResult:
    attendance_list = [models.Attendance(**a.model_dump()) for a in attendances]

    if not attendance_list:
        return schemas.AttendancesOperationalResult(result=True)

    try:
        inserted = await cruds.add_attendances(db, attendance_list, overwrite=overwrite)
    except IntegrityError as e:
        raise APIErrorCode.ALREADY_EXISTS_ATTENDANCE.of("Already exists attendance")

    # バルク登録された出欠の月ごとに出席率再計算をバックグラウンドで行う
    try:
        months = sorted({a.date.strftime("%Y-%m") for a in inserted if a is not None})
        logger.info(f"post_attendances: inserted_count={len(inserted)} months={months}")
        for m in months:
            logger.info(f"post_attendances: scheduling recalc for month={m}")
            background_tasks.add_task(recalculate_attendance_rates_bulk, m)
    except Exception:
        # バックグラウンドタスクの登録に失敗しても主処理は成功させる
        pass

    return schemas.AttendancesOperationalResult(result=True)


async def recalculate_attendance_rates_bulk(updated_month: str):
    """バルク登録または複数レコード変更時に、指定した月について出席率を再計算して DB に保存する。

    単一登録用の recalculate_attendance_rates と異なり、該当月の全出欠（member=True）を取得して
    全体・パート・各部員ごとの出席率を計算する。
    """
    async with async_session() as db:
        # メンバーをロードした上で当月の出欠を取得
        attendances = await cruds.get_attendances(db, member=True)
        schedules = await cruds.get_schedules(db)
        months = sorted(set(schedule.date.strftime("%Y-%m") for schedule in schedules))
        dates = sorted(set(schedule.date for schedule in schedules))

        logger.info(f"recalculate_attendance_rates_bulk({updated_month}): "
                    f"total_attendances={len(attendances)} schedule_months={months} schedule_dates={dates}")

        # 月内の削除/上書きで対象外になった member 行が残らないよう、対象月を再構築する。
        await cruds.clear_attendance_rates_by_month(db, updated_month)

        if updated_month not in months:
            # その月にスケジュールが無ければ、既存レートを消した状態で終了。
            logger.warning(f"skip {updated_month}: no schedule found")
            return

        all_attendances = Attendances(
            *[a for a in attendances if a.date.strftime(
                "%Y-%m") == updated_month and a.member is not None and a.date in dates]
        )

        logger.info(f"filtered attendances for {updated_month}: {len(all_attendances)} records")

        attendance_rates: list[models.AttendanceRate] = []

        # 全体
        attendance_rates.append(
            models.AttendanceRate(target_type="all", month=updated_month,
                                  rate=all_attendances.calc(False), actual=False))
        attendance_rates.append(
            models.AttendanceRate(target_type="all", month=updated_month,
                                  rate=all_attendances.calc(True), actual=True))

        # パートごと
        for part in Part:
            part_attendances = all_attendances.filter_by_part(part)
            attendance_rates.append(
                models.AttendanceRate(target_type="part", target_id=part.value, month=updated_month,
                                      rate=part_attendances.calc(False), actual=False))
            attendance_rates.append(
                models.AttendanceRate(target_type="part", target_id=part.value, month=updated_month,
                                      rate=part_attendances.calc(True), actual=True))

        # 部員ごと
        for member in set(a.member for a in all_attendances if a.member is not None):
            member_attendances = all_attendances.filter_by_member(member)
            attendance_rates.append(
                models.AttendanceRate(target_type="member", target_id=str(member.id),
                                      month=updated_month,
                                      rate=member_attendances.calc(False), actual=False))
            attendance_rates.append(
                models.AttendanceRate(target_type="member", target_id=str(member.id),
                                      month=updated_month,
                                      rate=member_attendances.calc(True), actual=True))

        await cruds.add_attendance_rates(db, attendance_rates)
        await db.commit()

        logger.info(f"saved {len(attendance_rates)} attendance rate records for {updated_month}: "
                    f"all_rates={[(r.target_type, r.actual, r.rate) for r in attendance_rates if r.target_type == 'all']}")


@router.delete(
    "/{attendance_id}",
    summary="出欠情報を削除",
    description="出欠情報を削除します。出欠情報が存在しない場合でもエラーを返しません。",
    dependencies=[Depends(require_permission("attendance:write"))],
)
async def delete_attendance(
    attendance_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> schemas.AttendanceOperationalResult:
    # 削除実行（日付を返す）
    deleted_date = await cruds.remove_attendance(db, attendance_id)

    # 削除した出欠の月について再計算タスクを登録
    if deleted_date:
        updated_month = deleted_date.strftime("%Y-%m")
        logger.info(f"delete_attendance: scheduling recalc for month={updated_month}")
        background_tasks.add_task(recalculate_attendance_rates_bulk, updated_month)

    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)


@router.patch(
    "/{attendance_id}",
    summary="出欠情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
    dependencies=[Depends(require_permission("attendance:write"))],
)
async def patch_attendance(
    attendance_id: UUID,
    attendance: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> schemas.AttendanceOperationalResult:
    # 更新実行（日付を返す）
    updated_date = await cruds.update_attendance(db, attendance_id, attendance)
    
    # 更新した出欠の月について再計算タスクを登録
    if updated_date:
        updated_month = updated_date.strftime("%Y-%m")
        logger.info(f"patch_attendance: scheduling recalc for month={updated_month}")
        background_tasks.add_task(recalculate_attendance_rates_bulk, updated_month)
    
    return schemas.AttendanceOperationalResult(result=True, attendance_id=attendance_id)


@router.get(
    "/rate",
    summary="出欠率を取得",
    description="出欠率を取得します。出欠率は全体、パートごと、部員ごとに取得できます。",
    response_model=list[schemas.AttendanceRate],
    dependencies=[Depends(require_permission("attendance:read"))],
)
async def get_attendance_rates(db: AsyncSession = Depends(get_db)):
    return await cruds.get_attendance_rates(db)


@router.post(
    "/rate/recalc",
    summary="出欠情報を再計算",
    description="出欠情報を再計算します。",
    dependencies=[Depends(require_permission("attendance:write"))],
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
            *[a for a in attendances if
              a.date.strftime("%Y-%m") == month and a.member is not None and a.date in dates])
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


@router.delete(
    "s",
    summary="出欠情報を一括削除",
    description="複数の出欠情報を一括で削除します。attendance_ids は削除する出欠の UUID の配列です。",
    dependencies=[Depends(require_permission("attendance:write"))],
)
async def bulk_delete_attendances(attendance_ids: list[UUID],
                                  background_tasks: BackgroundTasks,
                                  db: AsyncSession = Depends(get_db)) -> schemas.AttendancesOperationalResult:
    """attendance_ids に含まれる出欠を一括削除し、該当する月ごとに出席率を再計算するためのバックグラウンドタスクを登録します。

    DB 削除は cruds.remove_attendances で一回の DELETE クエリにまとめて行います。
    """
    if not attendance_ids:
        return schemas.AttendancesOperationalResult(result=True)

    # 削除を一度の DB 操作で行い、削除した行の id と date を cruds.remove_attendances から受け取る
    rows = await cruds.remove_attendances(db, attendance_ids)

    # rows は list[Row(id, date)] なので、それを月に変換して再計算タスクを登録する
    months = sorted({row[1].strftime("%Y-%m") for row in rows if row[1] is not None})
    logger.info(f"bulk_delete_attendances: removed_rows={len(rows)} months={months}")
    for m in months:
        logger.info(f"bulk_delete_attendances: scheduling recalc for month={m}")
        background_tasks.add_task(recalculate_attendance_rates_bulk, m)

    return schemas.AttendancesOperationalResult(result=True)
