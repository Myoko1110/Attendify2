import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.database import cruds, get_db
from app.database.attendance_export_cruds import get_attendances_in_range, get_pre_attendances_in_range
from app.dependencies import get_valid_session
from app.services.attendance_excel import MemberLite, build_attendance_xlsx_bytes

router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"],
    dependencies=[Depends(get_valid_session)],
)


@router.get(
    "/export/excel",
    summary="出欠表をExcelでエクスポート",
    description="フロントエンドの出欠表と同様の形式でExcel(xlsx)を生成して返します。",
)
async def export_attendance_excel(
    both_sheets: bool = Query(True, description="trueなら確定出欠と事前出欠を別シートで出力"),
    display_mode: str = Query("actual", pattern="^(actual|pre)$"),
    months: list[str] | None = Query(None, description="対象月(YYYY-MM)。未指定なら全月"),
    expand_months: list[str] | None = Query(None, description="展開する月(YYYY-MM)。未指定なら全月展開"),
    grades: list[int] | None = Query(None, description="generation（学年）フィルタ"),
    group_ids: list[str] | None = Query(None, description="グループIDフィルタ"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    # ---- fetch data (Postgres via SQLAlchemy) ----
    schedules = await cruds.get_schedules(db)
    schedule_dates = [s.date for s in schedules]

    # members (include groups for filtering)
    members = await cruds.get_members(db, include_groups=True)

    # filter members like frontend behavior
    filtered_members = []
    for m in members:
        if getattr(m.part, "value", str(m.part)) == "advisor":
            continue
        if grades and m.generation not in set(grades):
            continue
        if group_ids:
            mg_ids = {str(g.id) for g in getattr(m, "groups", [])}
            if not any(gid in mg_ids for gid in group_ids):
                continue
        filtered_members.append(m)

    # months set -> used to reduce DB load
    target_months = months
    if not target_months:
        # derive from schedules
        month_set: list[str] = []
        for s in schedules:
            mk = f"{s.date.year:04d}-{s.date.month:02d}"
            if mk not in month_set:
                month_set.append(mk)
        target_months = month_set

    # ---- bulk fetch attendances by date-range ----
    # schedules から対象範囲を決める（余計な月を引くより高速・単純）
    if schedule_dates:
        start = min(schedule_dates)
        end = max(schedule_dates)
    else:
        start = datetime.date.today()
        end = start

    member_id_set = {m.id for m in filtered_members}

    actual_rows = [a for a in await get_attendances_in_range(db, start=start, end=end) if a.member_id in member_id_set]
    pre_rows = [p for p in await get_pre_attendances_in_range(db, start=start, end=end) if p.member_id in member_id_set]

    # convert members
    member_lites: list[MemberLite] = [
        MemberLite(
            id=str(m.id),
            part_value=getattr(m.part, "value", str(m.part)),
            part_en_short=getattr(getattr(m.part, "detail", None), "enShort", getattr(m.part, "value", str(m.part))),
            generation=int(m.generation),
            name=str(m.name),
            name_kana=str(m.name_kana),
        )
        for m in filtered_members
    ]

    actual_map: dict[tuple[str, datetime.date], str] = {}
    for a in actual_rows:
        if a.member_id is None:
            continue
        actual_map[(str(a.member_id), a.date)] = a.attendance

    pre_map: dict[tuple[str, datetime.date], str] = {}
    for p in pre_rows:
        if p.member_id is None:
            continue
        pre_map[(str(p.member_id), p.date)] = p.attendance

    xlsx_bytes = build_attendance_xlsx_bytes(
        schedules=schedule_dates,
        members=member_lites,
        actual_map=actual_map,
        pre_map=pre_map,
        months=target_months,
        expand_months=set(expand_months) if expand_months else None,
        both_sheets=both_sheets,
        display_mode=display_mode,
    )

    bytes_io = BytesIO(xlsx_bytes)
    bytes_io.seek(0)
    filename = f"attendance_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"

    return StreamingResponse(
        bytes_io,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
