import calendar
import datetime
import secrets
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import between, delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload
from sqlalchemy.orm import aliased

from app import utils
from app.abc.part import Part
from app.database.models import Attendance, AttendanceLog, AttendanceRate, GenerationRole, Group, \
    Member, \
    MemberGroup, MemberRole, MembershipStatus, MembershipStatusPeriod, PermissionImplies, \
    PreAttendance, PreCheck, RBACPermission, RBACRole, RolePermission, Schedule, Session, \
    WeeklyParticipation
from app.schemas import MembershipStatusPeriodParams, \
    WeeklyParticipationParams
from app.schemas.rbac import GenerationRole as GenerationRoleSchema


def generate_token():
    return secrets.token_urlsafe(256)


async def get_attendances(db: AsyncSession, *, part: Part = None, generation: int = None,
                          date: datetime.date = None, month: str = None, member: bool = False,
                          include_disabled: bool = False) -> \
        list[Attendance]:
    stmt = select(Attendance)

    if not member:
        stmt = stmt.options(noload(Attendance.member))
    else:
        stmt = stmt.options(selectinload(Attendance.member))

    if not include_disabled:
        stmt = stmt.where(Attendance.is_disabled.is_(False))

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


async def get_attendance(db: AsyncSession, member_id: UUID, date: datetime.date,
                         include_disabled: bool = False) -> Attendance | None:
    stmt = select(Attendance).where(Attendance.member_id == member_id, Attendance.date == date)
    if not include_disabled:
        stmt = stmt.where(Attendance.is_disabled.is_(False))
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def add_attendance(db: AsyncSession, attendance: Attendance,
                         overwrite: bool = False) -> Attendance:
    # 既存動作 (overwrite=False)
    if not overwrite:
        try:
            db.add(attendance)
            await db.commit()
            await db.refresh(attendance, ["member"])
            return attendance
        except IntegrityError:
            await db.rollback()
            existing = await get_attendance(
                db,
                attendance.member_id,
                attendance.date,
                include_disabled=True,
            )
            if existing is not None and bool(getattr(existing, "is_disabled", False)):
                return await add_attendance(db, attendance, overwrite=True)
            raise

    # overwrite=True の場合は upsert を行う
    stmt = insert(Attendance).values(
        date=attendance.date,
        member_id=attendance.member_id,
        attendance=attendance.attendance,
        is_disabled=False,
        created_at=utils.now(),
        updated_at=utils.now(),
    )

    # 重複キー (date, member_id) があれば attendance と updated_at を上書きする
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "member_id"],
        set_=dict(
            attendance=stmt.excluded.attendance,
            is_disabled=False,
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
        try:
            db.add_all(attendances)
            await db.commit()
            # refresh each instance so that DB-generated fields (id 等) が反映される
            for a in attendances:
                await db.refresh(a)
            return attendances
        except IntegrityError:
            await db.rollback()

            # disabled 行との重複なら upsert 相当にフォールバックする。
            for a in attendances:
                existing = await get_attendance(
                    db,
                    a.member_id,
                    a.date,
                    include_disabled=True,
                )
                if existing is not None and not bool(getattr(existing, "is_disabled", False)):
                    raise

            return await add_attendances(db, attendances, overwrite=True)

    # overwrite=True の場合はバルク upsert を行う
    if not attendances:
        return []

    values = [
        dict(
            date=a.date,
            member_id=a.member_id,
            attendance=a.attendance,
            is_disabled=False,
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
            is_disabled=False,
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
    await db.execute(update(Attendance).where(Attendance.id == attendance_id).values(is_disabled=True))
    await db.commit()


async def remove_attendances(db: AsyncSession, attendance_ids: list[UUID]):
    """指定した出欠IDのリストを一括で論理削除する。attendance_ids が空なら何もしない。"""
    if not attendance_ids:
        return []

    stmt = (
        update(Attendance)
        .where(
            Attendance.id.in_(attendance_ids),
            Attendance.is_disabled.is_(False),
        )
        .values(is_disabled=True)
        .returning(Attendance.id, Attendance.date)
    )
    result = await db.execute(stmt)
    rows = result.all()
    await db.commit()
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


async def clear_attendance_rates_by_month(db: AsyncSession, month: str):
    await db.execute(delete(AttendanceRate).where(AttendanceRate.month == month))
    await db.commit()


async def add_attendance_rates(db: AsyncSession, attendance_rates: list[AttendanceRate]):
    if not attendance_rates:
        return []

    normalized_rates = [
        dict(
            target_type=x.target_type,
            target_id=(None if x.target_type == "all" and x.target_id is None else x.target_id),
            month=x.month,
            actual=x.actual,
            rate=x.rate,
        )
        for x in attendance_rates
    ]

    # 既存データに target_id=NULL の all 行がある場合、以後の集計ズレを防ぐため対象月・actualを掃除する。
    cleanup_keys = {
        (r["month"], r["actual"])
        for r in normalized_rates
        if r["target_type"] == "all"
    }
    for month, actual in cleanup_keys:
        await db.execute(
            delete(AttendanceRate).where(
                AttendanceRate.target_type == "all",
                AttendanceRate.target_id.is_(None),
                AttendanceRate.month == month,
                AttendanceRate.actual == actual,
            )
        )

    stmt = insert(AttendanceRate).values(normalized_rates)

    stmt = stmt.on_conflict_do_update(
        index_elements=["target_type", "target_id", "month", "actual"],
        set_=dict(
            rate=stmt.excluded.rate,
        )
    )

    # 実行してコミット
    await db.execute(stmt)
    await db.commit()


async def get_attendance_logs(db: AsyncSession, *, member_id: UUID | None = None,
                              terminal_member_id: UUID | None = None,
                              date: datetime.date | None = None,
                              start: datetime.datetime | None = None,
                              end: datetime.datetime | None = None,
                              limit: int | None = None, offset: int | None = None) -> Sequence[
    AttendanceLog]:
    stmt = select(AttendanceLog).order_by(AttendanceLog.timestamp.desc())

    if member_id is not None:
        stmt = stmt.where(AttendanceLog.member_id == member_id)

    if terminal_member_id is not None:
        stmt = stmt.where(AttendanceLog.terminal_member_id == terminal_member_id)

    if date is not None:
        start_dt = datetime.datetime.combine(date, datetime.time.min)
        end_dt = datetime.datetime.combine(date, datetime.time.max)
        stmt = stmt.where(between(AttendanceLog.timestamp, start_dt, end_dt))

    if start is not None:
        stmt = stmt.where(AttendanceLog.timestamp >= start)

    if end is not None:
        stmt = stmt.where(AttendanceLog.timestamp <= end)

    if limit is not None:
        stmt = stmt.limit(limit)

    if offset is not None:
        stmt = stmt.offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_attendance_log_by_id(db: AsyncSession, log_id: UUID) -> AttendanceLog | None:
    stmt = select(AttendanceLog).where(AttendanceLog.id == log_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def add_attendance_log(db: AsyncSession, attendance_log: AttendanceLog) -> AttendanceLog:
    db.add(attendance_log)
    await db.commit()
    await db.refresh(attendance_log)
    return attendance_log


async def add_attendance_logs(db: AsyncSession, attendance_logs: list[AttendanceLog]) -> list[
    AttendanceLog]:
    if not attendance_logs:
        return []
    db.add_all(attendance_logs)
    await db.commit()
    for l in attendance_logs:
        await db.refresh(l)
    return attendance_logs


async def remove_attendance_log(db: AsyncSession, log_id: UUID):
    await db.execute(delete(AttendanceLog).where(AttendanceLog.id == log_id))
    await db.commit()


async def remove_attendance_logs(db: AsyncSession, log_ids: list[UUID]):
    if not log_ids:
        return []
    stmt = delete(AttendanceLog).where(AttendanceLog.id.in_(log_ids)).returning(AttendanceLog.id)
    result = await db.execute(stmt)
    rows = result.all()
    await db.commit()
    return rows


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


async def get_member_by_id(
        db: AsyncSession,
        member_id: UUID,
        *,
        include_groups: bool = False,
        include_weekly_participation: bool = False,
        include_status_periods: bool = False,
) -> Member | None:
    """MemberをIDで取得。

    get_self 用。全件取得を避け、必要な関連だけ selectinload する。
    """

    stmt = select(Member).where(Member.id == member_id)

    if include_groups:
        stmt = stmt.options(selectinload(Member.groups))

    if include_weekly_participation:
        stmt = stmt.options(selectinload(Member.weekly_participations))

    if include_status_periods:
        stmt = stmt.options(
            selectinload(Member.membership_status_periods)
            .selectinload(MembershipStatusPeriod.status)
        )

    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_member_by_email(db: AsyncSession, email: str) -> Member | None:
    stmt = select(Member).where(Member.email == email)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_member_by_felica_idm(db: AsyncSession, felica_idm: str) -> Member | None:
    stmt = select(Member).where(Member.felica_idm == felica_idm)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_member_by_studentid(db: AsyncSession, studentid: int) -> Member | None:
    stmt = select(Member).where(Member.studentid == studentid)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def add_member(db: AsyncSession, member: Member) -> Member:
    db.add(member)
    await db.commit()
    await db.refresh(member, ["weekly_participations"])
    return member


async def add_members(db: AsyncSession, members: list[Member]) -> None:
    db.add_all(members)
    await db.commit()


async def update_member(db: AsyncSession, member_id: UUID, params) -> Member | None:
    member = await get_member_by_id(db, member_id)
    if member is None:
        return None
    for field, value in params.model_dump(exclude_unset=True).items():
        setattr(member, field, value)
    await db.commit()
    await db.refresh(member)
    return member


async def remove_member(db: AsyncSession, member_id: UUID) -> None:
    await db.execute(delete(Member).where(Member.id == member_id))
    await db.commit()


async def get_session_by_valid_token(db: AsyncSession, token: str) -> Session | None:
    """有効なセッショントークンから Session を取得（member もロード）。"""
    stmt = select(Session).where(Session.token == token).options(selectinload(Session.member))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        return None
    return session


# ----------------------------
# RBAC CRUDs
# ----------------------------

async def rbac_list_permissions(db: AsyncSession) -> Sequence[Any]:
    return (await db.execute(select(RBACPermission).order_by(RBACPermission.key))).scalars().all()


async def rbac_list_roles(db: AsyncSession) -> Sequence[Any]:
    return (await db.execute(select(RBACRole).order_by(RBACRole.key))).scalars().all()


async def rbac_get_role_permissions(db: AsyncSession, role_key: str) -> RBACRole | None:
    """指定したrole_keyのロールをpermissions付きで返す。存在しない場合はNoneを返す。"""
    result = await db.execute(
        select(RBACRole)
        .where(RBACRole.key == role_key)
        .options(selectinload(RBACRole.permissions))
    )
    return result.scalar_one_or_none()


async def rbac_get_role(db: AsyncSession, role_key: str) -> RBACRole | None:
    result = await db.execute(select(RBACRole).where(RBACRole.key == role_key))
    return result.scalar_one_or_none()


async def rbac_create_role(db: AsyncSession, *, key: str, display_name: str,
                           description: str = "") -> RBACRole:
    role = RBACRole(key=key, display_name=display_name, description=description)
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


async def rbac_update_role(db: AsyncSession, role_key: str, *, display_name: str | None = None,
                           description: str | None = None) -> RBACRole | None:
    role = await rbac_get_role(db, role_key)
    if role is None:
        return None
    if display_name is not None:
        role.display_name = display_name
    if description is not None:
        role.description = description
    await db.commit()
    await db.refresh(role)
    return role


async def rbac_delete_role(db: AsyncSession, role_key: str) -> bool:
    role = await rbac_get_role(db, role_key)
    if role is None:
        return False
    await db.delete(role)
    await db.commit()
    return True


async def rbac_replace_role_permissions(db: AsyncSession, role_key: str, *,
                                        permission_keys: list[str]) -> RBACRole | None:
    """ロールのpermissionをpermission_keysで完全置換する。ロールが存在しない場合はNoneを返す。"""
    role = await rbac_get_role_permissions(db, role_key)
    if role is None:
        return None

    want = set(permission_keys)
    # permission_keysが存在するか確認
    rows = (await db.execute(
        select(RBACPermission.id, RBACPermission.key).where(RBACPermission.key.in_(want))
    )).all()
    key_to_perm = {k: pid for pid, k in rows}

    missing = want - set(key_to_perm.keys())
    if missing:
        raise ValueError(f"Unknown permissions: {sorted(missing)}")

    want_ids = set(key_to_perm.values())
    existing_ids = {p.id for p in role.permissions}

    for pid in existing_ids - want_ids:
        await db.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == pid,
            )
        )

    for pid in want_ids - existing_ids:
        db.add(RolePermission(role_id=role.id, permission_id=pid))

    await db.commit()
    return await rbac_get_role_permissions(db, role_key)


async def rbac_get_generation_role_keys(db: AsyncSession, generation: int) -> list[str]:
    rows = (
        await db.execute(
            select(RBACRole.key)
            .join(GenerationRole, GenerationRole.role_id == RBACRole.id)
            .where(GenerationRole.generation == generation)
            .order_by(RBACRole.key)
        )
    ).all()
    return [r[0] for r in rows]


async def rbac_get_generations_role_keys(
        db: AsyncSession,
        *,
        generations: list[int] | None = None,
) -> dict[int, list[str]]:
    stmt = (
        select(GenerationRole.generation, RBACRole.key)
        .join(RBACRole, RBACRole.id == GenerationRole.role_id)
        .order_by(GenerationRole.generation, RBACRole.key)
    )
    if generations:
        stmt = stmt.where(GenerationRole.generation.in_(generations))

    rows = (await db.execute(stmt)).all()
    out: dict[int, list[str]] = {}
    for gen, key in rows:
        out.setdefault(int(gen), []).append(key)
    return out


async def _rbac_role_ids_by_keys(db: AsyncSession, role_keys: set[str]) -> dict[str, UUID]:
    if not role_keys:
        return {}
    rows = (await db.execute(
        select(RBACRole.id, RBACRole.key).where(RBACRole.key.in_(role_keys)))).all()
    return {k: rid for rid, k in rows}


async def rbac_replace_generation_roles(db: AsyncSession, generation: int, *,
                                        role_keys: list[str]) -> None:
    want = set(role_keys)
    key_to_id = await _rbac_role_ids_by_keys(db, want)

    missing = want - set(key_to_id.keys())
    if missing:
        raise ValueError(f"Unknown roles: {sorted(missing)}")

    want_ids = set(key_to_id.values())
    existing_rows = (await db.execute(
        select(GenerationRole.role_id).where(GenerationRole.generation == generation))).all()
    existing_ids = {r[0] for r in existing_rows}

    for rid in existing_ids - want_ids:
        obj = await db.get(GenerationRole, {"generation": generation, "role_id": rid})
        if obj:
            await db.delete(obj)

    for rid in want_ids - existing_ids:
        db.add(GenerationRole(generation=generation, role_id=rid))


async def rbac_replace_generations_roles_bulk(
        db: AsyncSession,
        *,
        items: list[GenerationRoleSchema],
) -> None:
    """items: [GenerationRolesBulkItemSchema, ...] の各generationを置換。"""

    want_keys: set[str] = set()
    for item in items:
        want_keys.update(item.role_keys)

    key_to_id = await _rbac_role_ids_by_keys(db, want_keys)
    missing = want_keys - set(key_to_id.keys())
    if missing:
        raise ValueError(f"Unknown roles: {sorted(missing)}")

    want_by_gen: dict[int, set[UUID]] = {
        int(item.generation): {key_to_id[k] for k in set(item.role_keys)}
        for item in items
    }

    target_generations = list(want_by_gen.keys())
    if not target_generations:
        return

    existing_rows = (
        await db.execute(
            select(GenerationRole.generation, GenerationRole.role_id)
            .where(GenerationRole.generation.in_(target_generations))
        )
    ).all()

    existing_by_gen: dict[int, set[UUID]] = {}
    for gen, rid in existing_rows:
        existing_by_gen.setdefault(int(gen), set()).add(rid)

    for gen in target_generations:
        want_ids = want_by_gen.get(gen, set())
        existing_ids = existing_by_gen.get(gen, set())

        for rid in existing_ids - want_ids:
            obj = await db.get(GenerationRole, {"generation": gen, "role_id": rid})
            if obj:
                await db.delete(obj)

        for rid in want_ids - existing_ids:
            db.add(GenerationRole(generation=gen, role_id=rid))


async def rbac_get_member_role_keys(db: AsyncSession, member_id: UUID) -> list[str]:
    rows = (
        await db.execute(
            select(RBACRole.key)
            .join(MemberRole, MemberRole.role_id == RBACRole.id)
            .where(MemberRole.member_id == member_id)
            .order_by(RBACRole.key)
        )
    ).all()
    return [r[0] for r in rows]


async def rbac_replace_member_roles(db: AsyncSession, member_id: UUID, *,
                                    role_keys: list[str]) -> None:
    want = set(role_keys)
    key_to_id = await _rbac_role_ids_by_keys(db, want)

    missing = want - set(key_to_id.keys())
    if missing:
        raise ValueError(f"Unknown roles: {sorted(missing)}")

    want_ids = set(key_to_id.values())

    existing_rows = (
        await db.execute(select(MemberRole.role_id).where(MemberRole.member_id == member_id))).all()
    existing_ids = {r[0] for r in existing_rows}

    for rid in existing_ids - want_ids:
        obj = await db.get(MemberRole, {"member_id": member_id, "role_id": rid})
        if obj:
            await db.delete(obj)

    for rid in want_ids - existing_ids:
        db.add(MemberRole(member_id=member_id, role_id=rid))


async def rbac_get_permission_implies_edges(
        db: AsyncSession,
        *,
        parent_keys: list[str] | None = None,
) -> list[tuple[str, str]]:
    parent = aliased(RBACPermission)
    child = aliased(RBACPermission)

    stmt = (
        select(parent.key, child.key)
        .select_from(PermissionImplies)
        .join(parent, parent.id == PermissionImplies.parent_permission_id)
        .join(child, child.id == PermissionImplies.child_permission_id)
        .order_by(parent.key, child.key)
    )
    if parent_keys:
        stmt = stmt.where(parent.key.in_(parent_keys))

    rows = (await db.execute(stmt)).all()
    return [(p, c) for p, c in rows]


async def get_schedules(db: AsyncSession) -> list[Schedule]:
    result = await db.execute(select(Schedule).order_by(Schedule.date))
    return [r[0] for r in result.all()]


async def get_schedule(db: AsyncSession, date: datetime.date) -> Schedule | None:
    result = await db.execute(select(Schedule).where(Schedule.date == date))
    return result.scalar_one_or_none()


async def add_schedule(db: AsyncSession, schedule: Schedule):
    # 後方互換: `is_pre_attendance_target` が直接指定されている場合はそれを優先。
    # それ以外は新フィールド `is_pre_attendance_excluded` を使い、target はその否定として保存する。
    target = getattr(schedule, "is_pre_attendance_target", None)
    if target is None:
        target = not bool(getattr(schedule, "is_pre_attendance_excluded", False))

    stmt = insert(Schedule).values(
        date=schedule.date,
        type=schedule.type,
        groups=schedule.groups,
        exclude_groups=schedule.exclude_groups,
        generations=schedule.generations,
        is_pre_attendance_target=target,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
    ).on_conflict_do_update(
        index_elements=["date"],
        set_={
            "type": schedule.type,
            "groups": schedule.groups,
            "exclude_groups": schedule.exclude_groups,
            "generations": schedule.generations,
            "is_pre_attendance_target": target,
            "start_time": schedule.start_time,
            "end_time": schedule.end_time,
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
                                   default_attendance: str | None,
                                   is_pre_attendance_excluded: bool | None = None):
    stmt = update(MembershipStatus).where(MembershipStatus.id == status_id)

    if display_name is not None:
        stmt = stmt.values(display_name=display_name)
    if is_attendance_target is not None:
        stmt = stmt.values(is_attendance_target=is_attendance_target)
    if default_attendance is not None:
        stmt = stmt.values(default_attendance=default_attendance)
    if is_pre_attendance_excluded is not None:
        # excluded=True -> target=False
        stmt = stmt.values(is_pre_attendance_target=(not bool(is_pre_attendance_excluded)))

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


async def get_pre_attendance(db: AsyncSession, *, member_id: UUID, date: datetime.date) -> PreAttendance | None:
    stmt = select(PreAttendance).where(
        PreAttendance.member_id == member_id,
        PreAttendance.date == date,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_pre_attendances(db: AsyncSession, *, member_id: UUID | None, month: str | None,
                              date: datetime.date | None,
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
    if date is not None:
        stmt = stmt.where(PreAttendance.date == date)

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
                           deadline: datetime.datetime | None,
                           edit_deadline_days: int):
    await db.execute(
        update(PreCheck).where(PreCheck.id == pre_check_id).values(
            start_date=start_date, end_date=end_date, description=description,
            deadline=deadline,
            edit_deadline_days=edit_deadline_days)
    )
    await db.commit()
    pre_check = await get_pre_check_by_id(db, pre_check_id)

    return pre_check


def _auto_attendance_status_from_log(
        log_timestamp: datetime.datetime,
        start_dt: datetime.datetime,
        end_dt: datetime.datetime,
) -> str:
    """attendance_log 1件から自動補完する attendance を決定する。

    返り値:
    - start_time より前: "早退"
    - end_time より前: "遅早"
    - end_time 以後: "遅刻"
    """
    log_time = log_timestamp.astimezone(start_dt.tzinfo)

    if log_time < start_dt:
        return "早退"
    if log_time < end_dt:
        return "遅早"
    return "遅刻"


def _auto_attendance_status_from_log_range(
        first_log_timestamp: datetime.datetime,
        last_log_timestamp: datetime.datetime,
        start_dt: datetime.datetime,
        end_dt: datetime.datetime,
) -> str:
    """attendance_log 複数件から first/last を使って attendance を決定する。"""
    first_time = first_log_timestamp.astimezone(start_dt.tzinfo)
    last_time = last_log_timestamp.astimezone(start_dt.tzinfo)

    # last が end 以降なら在席完了、未満なら途中退席扱い。
    if last_time >= end_dt:
        return "出席" if first_time < start_dt else "遅刻"
    return "早退" if first_time < start_dt else "遅早"


async def auto_insert_daily_attendances(db: AsyncSession, date: datetime.date):
    """指定日の出欠を未登録の部員について自動挿入する。

    ロジック:
    - 指定日の Schedule がなければ何もしない。
    - 既に Attendance レコードが存在する member はスキップ。
    - attendance_log が 1 件ある場合はその時刻で補完する。
      - start_time 前なら '早退'
      - end_time 前なら '遅早'
      - end_time 後なら '遅刻'
    - attendance_log が 2 件以上ある場合は first/min と last/max で補完する。
    - attendance_log がない場合のみ従来の schedule / weekly participation の処理を使う。
    - まとめて cruds.add_attendances に渡して挿入する。

    戻り値: 挿入した Attendance のリスト（cruds.add_attendances の戻り）
    """
    from app.abc.schedule_type import ScheduleType
    # 1. スケジュール取得
    schedule = await get_schedule(db, date)
    if schedule is None:
        return []

    if not schedule.start_time or not schedule.end_time:
        return []

    # 2. 全部員取得（weekly participation をロード）
    members = await get_members(db, include_weekly_participation=True)

    # 3. 既存の出欠を取得して member_id の集合を作る
    existing = await get_attendances(db, date=date, member=True, include_disabled=True)
    existing_member_ids = {a.member_id for a in existing if a.member_id is not None}

    # 4. 当日の attendance_log を member_id ごとにまとめる
    attendance_logs = await get_attendance_logs(db, date=date)
    logs_by_member_id: dict[UUID, list[AttendanceLog]] = {}
    for log in attendance_logs:
        logs_by_member_id.setdefault(log.member_id, []).append(log)

    start_dt = datetime.datetime.combine(date, schedule.start_time, tzinfo=utils.JST)
    end_dt = datetime.datetime.combine(date, schedule.end_time, tzinfo=utils.JST)

    attendances_to_add = []

    weekday = date.weekday()  # 0=Mon

    for m in members:
        # skip if attendance already exists
        if m.id in existing_member_ids:
            continue

        member_logs = logs_by_member_id.get(m.id, [])
        if len(member_logs) == 1:
            status = _auto_attendance_status_from_log(member_logs[0].timestamp, start_dt, end_dt)
        elif len(member_logs) > 1:
            first_log = min(member_logs, key=lambda x: x.timestamp)
            last_log = max(member_logs, key=lambda x: x.timestamp)
            status = _auto_attendance_status_from_log_range(
                first_log.timestamp,
                last_log.timestamp,
                start_dt,
                end_dt,
            )
        else:
            # attendance_log がない場合のみ従来処理を継続する。
            if schedule.type == ScheduleType.WEEKDAY:
                # find weekly participation for this weekday
                wp = None
                for r in getattr(m, "weekly_participations", []):
                    if r.weekday == weekday:
                        wp = r
                        break

                if wp is not None and getattr(wp, "is_active", False):
                    # 週間参加情報の default_attendance が「講習」の場合のみ '講習' を登録し、それ以外は欠席とする
                    da = getattr(wp, "default_attendance", None)
                    status = da if da == "講習" else "欠席"
                else:
                    status = "欠席"
            else:
                status = "欠席"

        attendance = Attendance(
            date=date,
            member_id=m.id,
            attendance=status,
            first_tap_at=first_log.timestamp if first_log else None,
            last_tap_at=last_log.timestamp if last_log else None,
        )
        attendances_to_add.append(attendance)

    if not attendances_to_add:
        return []

    try:
        inserted = await add_attendances(db, attendances_to_add)
        return inserted
    except Exception:
        # 失敗しても処理を止めない。ただしログは残す。
        import logging
        logging.exception("auto_insert_daily_attendances failed for date=%s", date)
        return []
