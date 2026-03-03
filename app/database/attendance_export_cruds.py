from __future__ import annotations

import datetime as dt
from sqlalchemy import between, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Attendance, PreAttendance


async def get_attendances_in_range(
    db: AsyncSession,
    *,
    start: dt.date,
    end: dt.date,
) -> list[Attendance]:
    """期間で確定出欠を一括取得する（エクスポートなどで月ごとのループを避ける用）。"""
    res = await db.execute(
        select(Attendance).where(between(Attendance.date, start, end))
    )
    return list(res.scalars().all())


async def get_pre_attendances_in_range(
    db: AsyncSession,
    *,
    start: dt.date,
    end: dt.date,
) -> list[PreAttendance]:
    """期間で事前出欠を一括取得する（monthごとのループを避ける用）。"""
    res = await db.execute(
        select(PreAttendance).where(between(PreAttendance.date, start, end))
    )
    return list(res.scalars().all())
