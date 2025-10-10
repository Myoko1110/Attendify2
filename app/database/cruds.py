import datetime
import secrets
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from app import utils
from app.abc.part import Part
from app.database.models import Attendance, AttendanceRate, Member, Schedule, Session
from app.schemas import MemberParamsOptional


def generate_token():
    return secrets.token_urlsafe(256)


async def get_attendances(db: AsyncSession, *, part: Part = None, generation: int = None,
                          date: datetime.date = None, month: str = None, member: bool = False) -> \
        list[Attendance]:
    stmt = select(Attendance)

    if not member:
        stmt = stmt.options(noload(Attendance.member))

    if date is not None:
        stmt = stmt.where(Attendance.date == date)

    if part is not None:
        stmt = stmt.where(Member.part == part)

    if generation is not None:
        stmt = stmt.where(Member.generation == generation)

    if month is not None:
        stmt = stmt.where(func.strftime("%Y-%m", Attendance.date) == month)

    result = await db.execute(stmt)
    return [r for r in result.scalars().all()]


async def add_attendance(db: AsyncSession, attendance: Attendance) -> Attendance:
    db.add(attendance)
    await db.commit()
    await db.refresh(attendance, ["member"])
    return attendance


async def add_attendances(db: AsyncSession, attendances: list[Attendance]):
    db.add_all(attendances)
    await db.commit()


async def remove_attendance(db: AsyncSession, attendance_id: UUID):
    await db.execute(delete(Attendance).where(Attendance.id == attendance_id))
    await db.commit()


async def update_attendance(db: AsyncSession, attendance_id: UUID, attendance: str):
    await db.execute(
        update(Attendance).where(Attendance.id == attendance_id).values(
            attendance=attendance)
    )
    await db.commit()


async def get_attendance_rates(db: AsyncSession) -> list[AttendanceRate]:
    stmt = select(AttendanceRate)

    result = await db.execute(stmt)
    return [r[0] for r in result.all()]


async def clear_attendance_rates(db: AsyncSession):
    await db.execute(delete(AttendanceRate))


async def add_attendance_rates(db: AsyncSession, attendance_rates: list[AttendanceRate]):
    stmt = insert(AttendanceRate).values([
        dict(
            target_type=x.target_type,
            target_id=x.target_id,
            month=x.month,
            actual=x.actual,
            rate=x.rate,
        )
        for x in attendance_rates
    ])

    stmt = stmt.on_conflict_do_update(
        index_elements=["target_id", "month", "actual"],
        set_=dict(
            rate=stmt.excluded.rate,
        )
    )

    await db.execute(stmt)


async def get_members(db: AsyncSession, *, part: Part = None, generation: int = None) -> list[
    Member]:
    stmt = select(Member)

    if part is not None:
        stmt = stmt.where(Member.part == part)

    if generation is not None:
        stmt = stmt.where(Member.generation == generation)

    result = await db.execute(stmt)
    return [r[0] for r in result.all()]


async def get_member_by_email(db: AsyncSession, email: str) -> Member | None:
    stmt = select(Member).where(Member.email == email)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_session_by_valid_token(db: AsyncSession, token: str) -> Session | None:
    stmt = select(Session).where(Session.token == token).options(selectinload(Session.member))
    result = await db.execute(stmt)

    session = result.scalar_one_or_none()
    if not session:
        return None

    if session.created_at + datetime.timedelta(days=30) < utils.now():
        return None
    return session


async def add_member(db: AsyncSession, member: Member) -> Member:
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def add_members(db: AsyncSession, members: list[Member]):
    db.add_all(members)
    await db.commit()


async def remove_member(db: AsyncSession, member_id: UUID):
    await db.execute(delete(Member).where(Member.id == member_id))
    await db.commit()


async def update_member(db: AsyncSession, member_id: UUID, m: MemberParamsOptional):
    stmt = update(Member).where(Member.id == member_id)

    if m.part is not None:
        stmt = stmt.values(part=m.part)
    if m.generation is not None:
        stmt = stmt.values(generation=m.generation)
    if m.name is not None:
        stmt = stmt.values(name=m.name)
    if m.name_kana is not None:
        stmt = stmt.values(name_kana=m.name_kana)
    if m.email is not None:
        stmt = stmt.values(email=m.email)
    if m.role is not None:
        stmt = stmt.values(role=m.role)
    if m.lecture_day is not None:
        stmt = stmt.values(lecture_day=m.lecture_day)
    if m.is_competition_member is not None:
        stmt = stmt.values(is_competition_member=m.is_competition_member)

    await db.execute(stmt)
    await db.commit()


async def update_members_competition(db: AsyncSession, member_ids: list[UUID],
                                     is_competition_member: bool):
    stmt = update(Member).where(Member.id.in_(member_ids)).values(
        is_competition_member=is_competition_member)
    await db.execute(stmt)
    await db.commit()


async def get_schedules(db: AsyncSession) -> list[Schedule]:
    result = await db.execute(select(Schedule))
    return [r[0] for r in result.all()]


async def add_schedule(db: AsyncSession, schedule: Schedule):
    stmt = insert(Schedule).values(date=schedule.date, type=schedule.type,
                                   target=schedule.target).on_conflict_do_update(
        index_elements=["date"],
        set_={
            "type": schedule.type,
            "target": schedule.target,
        },
    )
    await db.execute(stmt)
    await db.commit()


async def remove_schedule(db: AsyncSession, date: datetime.date):
    await db.execute(delete(Schedule).where(Schedule.date == date))
    await db.commit()


async def create_session(db: AsyncSession, member: Member) -> str:
    token = generate_token()
    session = Session(
        token=token,
        member_id=member.id,
    )

    db.add(session)
    await db.commit()
    return token


async def remove_session(db: AsyncSession, token: str):
    await db.execute(delete(Session).where(Session.token == token))
    await db.commit()
