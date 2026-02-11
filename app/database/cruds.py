import calendar
import datetime
import secrets
from typing import Sequence
from uuid import UUID

from sqlalchemy import between, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from app import utils
from app.abc.part import Part
from app.database.models import Attendance, AttendanceRate, Group, Member, MemberGroup, \
    MembershipStatus, \
    MembershipStatusPeriod, PreAttendance, PreCheck, Schedule, Session, WeeklyParticipation
from app.schemas import MemberParamsOptional, MembershipStatusPeriodParams, \
    WeeklyParticipationParams


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
        start = datetime.date.fromisoformat(f"{month}-01")
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = datetime.date(start.year, start.month, last_day)
        stmt = stmt.where(between(Attendance.date, start, end))

    result = await db.execute(stmt)
    return [r for r in result.scalars().all()]


async def add_attendance(db: AsyncSession, attendance: Attendance,
                         overwrite: bool = False) -> Attendance:
    # 既存動作 (overwrite=False)
    if not overwrite:
        db.add(attendance)
        await db.commit()
        await db.refresh(attendance, ["member"])
        return attendance

    # overwrite=True の場合は upsert を行う
    stmt = insert(Attendance).values(
        date=attendance.date,
        member_id=attendance.member_id,
        attendance=attendance.attendance,
        created_at=utils.now(),
        updated_at=utils.now(),
    )

    # 重複キー (date, member_id) があれば attendance と updated_at を上書きする
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "member_id"],
        set_=dict(
            attendance=stmt.excluded.attendance,
            updated_at=utils.now(),
        )
    )

    await db.execute(stmt)
    await db.commit()

    # upsert 後の行を取得して member をロードして返す
    q = select(Attendance).where(
        Attendance.date == attendance.date,
        Attendance.member_id == attendance.member_id,
    ).options(selectinload(Attendance.member))
    res = await db.execute(q)
    return res.scalar_one()


async def add_attendances(db: AsyncSession, attendances: list[Attendance], overwrite: bool = False):
    # 既存動作 (overwrite=False)
    if not overwrite:
        db.add_all(attendances)
        await db.commit()
        # refresh each instance so that DB-generated fields (id 等) が反映される
        for a in attendances:
            await db.refresh(a)
        return attendances

    # overwrite=True の場合はバルク upsert を行う
    if not attendances:
        return []

    values = [
        dict(
            date=a.date,
            member_id=a.member_id,
            attendance=a.attendance,
            created_at=utils.now(),
            updated_at=utils.now(),
        )
        for a in attendances
    ]

    stmt = insert(Attendance).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "member_id"],
        set_=dict(
            attendance=stmt.excluded.attendance,
            updated_at=utils.now(),
        )
    )

    await db.execute(stmt)
    await db.commit()

    # upsert の結果を各レコードごとに取得して返す（member を含めて取得）
    inserted: list[Attendance] = []
    for a in attendances:
        q = select(Attendance).where(
            Attendance.date == a.date,
            Attendance.member_id == a.member_id,
        ).options(selectinload(Attendance.member))
        res = await db.execute(q)
        ar = res.scalar_one_or_none()
        if ar is not None:
            inserted.append(ar)
    return inserted


async def remove_attendance(db: AsyncSession, attendance_id: UUID):
    await db.execute(delete(Attendance).where(Attendance.id == attendance_id))
    await db.commit()


async def remove_attendances(db: AsyncSession, attendance_ids: list[UUID]):
    """指定した出欠IDのリストを一括で削除する。attendance_ids が空なら何もしない。

    単一削除のループではなく、IN 条件で一度の DB 操作で削除を行う。
    この実装では PostgreSQL の RETURNING を利用して、削除した行の id と date を
    1 回の DB 呼び出しで取得して返します。
    """
    if not attendance_ids:
        return []

    stmt = delete(Attendance).where(Attendance.id.in_(attendance_ids)).returning(Attendance.id,
                                                                                 Attendance.date)
    result = await db.execute(stmt)
    rows = result.all()
    await db.commit()
    # rows は sqlalchemy.engine.Row のリスト。各要素は (id, date)
    return rows


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
    await db.commit()


async def add_attendance_rates(db: AsyncSession, attendance_rates: list[AttendanceRate]):
    if not attendance_rates:
        return []

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

    # 実行してコミット
    await db.execute(stmt)
    await db.commit()


async def get_members(db: AsyncSession, *, part: Part = None, generation: int = None,
                      include_groups: bool = False, include_weekly_participation: bool = False,
                      include_status_periods: bool = False) \
        -> Sequence[Member]:
    stmt = select(Member)

    if part is not None:
        stmt = stmt.where(Member.part == part)

    if generation is not None:
        stmt = stmt.where(Member.generation == generation)

    if include_groups:
        stmt = stmt.options(selectinload(Member.groups))

    if include_weekly_participation:
        stmt = stmt.options(selectinload(Member.weekly_participations))

    if include_status_periods:
        stmt = stmt.options(
            selectinload(Member.membership_status_periods)
            .selectinload(MembershipStatusPeriod.status)
        )

    result = await db.execute(stmt)

    return result.scalars().all()


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
    for m in members:
        await db.refresh(m)
    return members


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
                                   groups=schedule.groups, exclude_groups=schedule.exclude_groups,
                                   generations=schedule.generations).on_conflict_do_update(
        index_elements=["date"],
        set_={
            "type": schedule.type,
            "groups": schedule.groups,
            "exclude_groups": schedule.exclude_groups,
            "generations": schedule.generations,
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


async def get_weekly_participation(db: AsyncSession, member_id: UUID):
    stmt = select(WeeklyParticipation).where(WeeklyParticipation.member_id == member_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def upsert_weekly_participation(db: AsyncSession,
                                      member_id: UUID,
                                      params: WeeklyParticipationParams):
    stmt = insert(WeeklyParticipation).values(
        member_id=member_id,
        weekday=params.weekday,
        default_attendance=params.default_attendance,
        is_active=params.is_active,
    ).on_conflict_do_update(
        index_elements=["member_id", "weekday"],
        set_=dict(
            is_active=params.is_active,
            default_attendance=params.default_attendance,
        )
    ).returning(WeeklyParticipation)
    await db.execute(stmt)
    await db.commit()


async def get_membership_statuses(db: AsyncSession):
    result = await db.execute(select(MembershipStatus))
    return result.scalars().all()


async def add_membership_status(db: AsyncSession, status: MembershipStatus):
    db.add(status)
    await db.commit()
    await db.refresh(status)
    return status


async def remove_membership_status(db: AsyncSession, status_id: UUID):
    await db.execute(delete(MembershipStatus).where(MembershipStatus.id == status_id))
    await db.commit()


async def update_membership_status(db: AsyncSession, status_id: UUID, display_name: str | None,
                                   is_attendance_target: bool | None,
                                   default_attendance: str | None):
    stmt = update(MembershipStatus).where(MembershipStatus.id == status_id)

    if display_name is not None:
        stmt = stmt.values(display_name=display_name)
    if is_attendance_target is not None:
        stmt = stmt.values(is_attendance_target=is_attendance_target)
    if default_attendance is not None:
        stmt = stmt.values(default_attendance=default_attendance)

    await db.execute(stmt)
    await db.commit()


async def get_membership_status_periods(db: AsyncSession, member_id: UUID):
    stmt = select(MembershipStatusPeriod).where(
        MembershipStatusPeriod.member_id == member_id
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def add_membership_status_period(db: AsyncSession, status_period: MembershipStatusPeriod):
    db.add(status_period)
    await db.commit()
    await db.refresh(status_period)
    return status_period


async def remove_membership_status_period(db: AsyncSession, status_period_id: UUID):
    await db.execute(
        delete(MembershipStatusPeriod).where(
            MembershipStatusPeriod.id == status_period_id
        )
    )
    await db.commit()


async def update_membership_status_period(db: AsyncSession, status_period_id: UUID,
                                          params: MembershipStatusPeriodParams
                                          ):
    stmt = update(MembershipStatusPeriod).where(
        MembershipStatusPeriod.id == status_period_id
    )

    if params.start_date is not None:
        stmt = stmt.values(start_date=params.start_date)
    if params.end_date is not None:
        stmt = stmt.values(end_date=params.end_date)
    if params.status_id is not None:
        stmt = stmt.values(status_id=params.status_id)

    await db.execute(stmt)
    await db.commit()


async def add_membership_status_periods(db: AsyncSession,
                                        status_periods: list[MembershipStatusPeriod]):
    if not status_periods:
        return []

    # 事前に id を集める（models の default=uuid4 によりインスタンスに id がある想定）
    ids = [sp.id for sp in status_periods]

    db.add_all(status_periods)
    await db.commit()

    # まとめて取得して関連を selectinload で事前ロードする
    stmt = select(MembershipStatusPeriod).where(MembershipStatusPeriod.id.in_(ids)).options(
        selectinload(MembershipStatusPeriod.status),
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_groups(db: AsyncSession):
    result = await db.execute(select(Group))
    return result.scalars().all()


async def add_group(db: AsyncSession, group: Group):
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


async def remove_group(db: AsyncSession, group_id: UUID):
    await db.execute(delete(Group).where(Group.id == group_id))
    await db.commit()


async def update_group(db: AsyncSession, group_id: UUID, display_name: str):
    await db.execute(
        update(Group).where(Group.id == group_id).values(display_name=display_name)
    )
    await db.commit()


async def get_member_groups(db: AsyncSession, member_id: UUID):
    stmt = select(MemberGroup).where(MemberGroup.member_id == member_id).options(
        selectinload(MemberGroup.group))
    result = await db.execute(stmt)
    return [i.group for i in result.scalars().all()]


async def add_member_group(db: AsyncSession, member_group: MemberGroup):
    db.add(member_group)
    await db.commit()
    await db.refresh(member_group)
    return member_group


async def add_members_group(db: AsyncSession, member_groups: list[MemberGroup]):
    db.add_all(member_groups)
    await db.commit()
    for mg in member_groups:
        await db.refresh(mg)
    return member_groups


async def get_group_members(db: AsyncSession, group_id: UUID):
    stmt = (select(MemberGroup).where(MemberGroup.group_id == group_id)
            .options(selectinload(MemberGroup.member)))
    result = await db.execute(stmt)
    return [i.member for i in result.scalars().all()]


async def remove_group_member(db: AsyncSession, group_id: UUID, member_id: UUID):
    await db.execute(
        delete(MemberGroup).where(
            MemberGroup.group_id == group_id,
            MemberGroup.member_id == member_id,
        )
    )
    await db.commit()


async def remove_group_members(db: AsyncSession, group_id: UUID, member_ids: list[UUID]):
    await db.execute(
        delete(MemberGroup).where(
            MemberGroup.group_id == group_id,
            MemberGroup.member_id.in_(member_ids),
        )
    )
    await db.commit()


async def get_pre_attendances(db: AsyncSession, *, member_id: UUID | None, month: str | None,
                              pre_check_id: str | None) -> \
        Sequence[PreAttendance]:
    stmt = select(PreAttendance)

    if member_id is not None:
        stmt = stmt.where(PreAttendance.member_id == member_id)
    if month is not None:
        start = datetime.date.fromisoformat(f"{month}-01")
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = datetime.date(start.year, start.month, last_day)
        stmt = stmt.where(between(PreAttendance.date, start, end))
    if pre_check_id is not None:
        stmt = stmt.where(PreAttendance.pre_check_id == pre_check_id)

    result = await db.execute(stmt)
    return result.scalars().all()


async def add_pre_attendances(db: AsyncSession, pre_attendances: list[PreAttendance],
                              overwrite: bool = False):
    if not pre_attendances:
        return []

    if not overwrite:
        # add_all to persist each PreAttendance instance
        db.add_all(pre_attendances)
        await db.commit()

        # refresh to populate DB-generated fields (id 等)
        for p in pre_attendances:
            await db.refresh(p)
        return pre_attendances

    # overwrite=True の場合はバルク upsert を行う
    values = [
        dict(
            date=p.date,
            member_id=p.member_id,
            attendance=p.attendance,
            reason=p.reason,
            pre_check_id=p.pre_check_id,
        )
        for p in pre_attendances
    ]

    stmt = insert(PreAttendance).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "member_id"],
        set_=dict(
            attendance=stmt.excluded.attendance,
            reason=stmt.excluded.reason,
            pre_check_id=stmt.excluded.pre_check_id,
            updated_at=utils.now(),
        )
    )

    await db.execute(stmt)
    await db.commit()

    # upsert の結果を各レコードごとに取得して返す
    inserted: list[PreAttendance] = []
    for p in pre_attendances:
        q = select(PreAttendance).where(
            PreAttendance.date == p.date,
            PreAttendance.member_id == p.member_id,
        )
        res = await db.execute(q)
        pr = res.scalar_one_or_none()
        if pr is not None:
            inserted.append(pr)
    return inserted


async def remove_pre_attendance(db: AsyncSession, pre_attendance_id: UUID):
    await db.execute(delete(PreAttendance).where(PreAttendance.id == pre_attendance_id))
    await db.commit()


async def bulk_remove_pre_attendances(db: AsyncSession, pre_attendance_ids: list[UUID]):
    await db.execute(delete(PreAttendance).where(PreAttendance.id.in_(pre_attendance_ids)))
    await db.commit()


async def update_pre_attendance(db: AsyncSession, pre_attendance_id: UUID, attendance: str):
    await db.execute(
        update(PreAttendance).where(PreAttendance.id == pre_attendance_id).values(
            attendance=attendance)
    )
    await db.commit()


async def get_pre_checks(db: AsyncSession) -> Sequence[PreAttendance]:
    stmt = select(PreCheck)

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_pre_check_by_id(db: AsyncSession, pre_check_id: str) -> PreCheck | None:
    stmt = select(PreCheck).where(PreCheck.id == pre_check_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def add_pre_check(db: AsyncSession, pre_checks: PreCheck):
    db.add(pre_checks)
    await db.commit()
    await db.refresh(pre_checks)
    return pre_checks


async def remove_pre_check(db: AsyncSession, pre_check_id: str):
    await db.execute(delete(PreCheck).where(PreCheck.id == pre_check_id))
    await db.commit()


async def update_pre_check(db: AsyncSession, pre_check_id: str,
                           start_date: datetime.date, end_date: datetime.date, description: str,
                           edit_deadline_days: int):
    await db.execute(
        update(PreCheck).where(PreCheck.id == pre_check_id).values(
            start_date=start_date, end_date=end_date, description=description,
            edit_deadline_days=edit_deadline_days)
    )
    await db.commit()
    pre_check = await get_pre_check_by_id(db, pre_check_id)

    return pre_check
