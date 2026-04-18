from uuid import UUID, uuid4  # noqa: F401

from fastapi import APIRouter, Body, Depends, Form
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.dependencies import get_valid_session, require_permission
from app.schemas import *
from app.database import models
from app.services import rbac

router = APIRouter(prefix="/member", tags=["Member"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="部員を取得",
    description="部員を取得します。",
    response_model=list[MemberDetailSchema],
    dependencies=[Depends(require_permission("member:read"))],
)
async def get_members(
    part: Part = None,
    generation: int = None,
    include_groups: bool = False,
    include_weekly_participation: bool = False,
    include_status_periods: bool = False,
    include_roles: bool = False,
    db: AsyncSession = Depends(get_db),
):
    members = await cruds.get_members(
        db,
        part=part,
        generation=generation,
        include_groups=include_groups,
        include_weekly_participation=include_weekly_participation,
        include_status_periods=include_status_periods,
    )

    if include_weekly_participation:
        for m in members:
            records_dict = {r.weekday: r for r in m.weekly_participations}

            weekly_list = []
            for day in range(7):
                if day in records_dict:
                    rec = records_dict[day]
                    weekly_list.append(
                        models.WeeklyParticipation(
                            id=rec.id,
                            member_id=rec.member_id,
                            weekday=rec.weekday,
                            is_active=rec.is_active,
                            default_attendance=rec.default_attendance,
                        )
                    )
                else:
                    weekly_list.append(
                        models.WeeklyParticipation(
                            id=uuid4(),
                            member_id=m.id,
                            weekday=day,
                            is_active=False,
                        )
                    )
            m.weekly_participations = weekly_list

    # generation -> role keys cache (avoid N+1)
    gen_role_cache: dict[int, list[str]] = {}

    schemas: list[MemberDetailSchema] = []

    # ----- RBAC role info (bulk load to avoid N+1) -----
    role_key_by_id: dict[UUID, str] = {}
    member_role_ids_by_member: dict[UUID, set[UUID]] = {}
    gen_role_ids_by_generation: dict[int, set[UUID]] = {}

    if include_roles and members:
        member_ids = [m.id for m in members]
        generations = sorted({int(m.generation) for m in members})

        # 1) load member_roles in bulk
        rows = (
            await db.execute(
                select(models.MemberRole.member_id, models.MemberRole.role_id)
                .where(models.MemberRole.member_id.in_(member_ids))
            )
        ).all()
        role_ids: set[UUID] = set()
        for mid, rid in rows:
            member_role_ids_by_member.setdefault(mid, set()).add(rid)
            role_ids.add(rid)

        # 2) load generation_roles in bulk
        rows = (
            await db.execute(
                select(models.GenerationRole.generation, models.GenerationRole.role_id)
                .where(models.GenerationRole.generation.in_(generations))
            )
        ).all()
        for gen, rid in rows:
            gen_role_ids_by_generation.setdefault(int(gen), set()).add(rid)
            role_ids.add(rid)

        # 3) load role_id -> key
        if role_ids:
            rrows = (
                await db.execute(
                    select(models.RBACRole.id, models.RBACRole.key).where(models.RBACRole.id.in_(role_ids))
                )
            ).all()
            role_key_by_id = {rid: key for rid, key in rrows}

        # 4) build generation_role_keys cache
        for gen in generations:
            keys = sorted(role_key_by_id.get(rid, "") for rid in gen_role_ids_by_generation.get(gen, set()))
            gen_role_cache[gen] = [k for k in keys if k]

        # 5) bulk load permissions: role_id -> set[permission_id]
        role_permission_rows = (
            await db.execute(
                select(models.RolePermission.role_id, models.RolePermission.permission_id)
                .where(models.RolePermission.role_id.in_(role_ids))
            )
        ).all()
        perm_ids_by_role: dict[UUID, set[UUID]] = {}
        all_perm_ids: set[UUID] = set()
        for rid, pid in role_permission_rows:
            perm_ids_by_role.setdefault(rid, set()).add(pid)
            all_perm_ids.add(pid)

        # 6) load permission implication edges for transitive closure
        imply_rows = (
            await db.execute(
                select(models.PermissionImplies.parent_permission_id, models.PermissionImplies.child_permission_id)
            )
        ).all()
        children_map: dict[UUID, set[UUID]] = {}
        for parent_id, child_id in imply_rows:
            children_map.setdefault(parent_id, set()).add(child_id)

        # 7) load permission_id -> key
        perm_key_by_id: dict[UUID, str] = {}
        if all_perm_ids:
            prows = (
                await db.execute(
                    select(models.RBACPermission.id, models.RBACPermission.key)
                    .where(models.RBACPermission.id.in_(all_perm_ids))
                )
            ).all()
            perm_key_by_id = {pid: key for pid, key in prows}

    for m in members:
        # 基本情報
        data = Member.model_validate(m).model_dump()

        # ★ 常にキーを作る
        data["groups"] = (
            MemberGroupsSchema.model_validate(m).groups
            if include_groups
            else []
        )

        data["weekly_participations"] = (
            MemberWeeklySchema.model_validate(m).weekly_participations
            if include_weekly_participation
            else []
        )

        data["membership_status_periods"] = (
            MembershipStatusPeriodSchema.model_validate(m).membership_status_periods
            if include_status_periods
            else []
        )

        if include_roles:
            gen = int(m.generation)
            data["generation_role_keys"] = gen_role_cache.get(gen, [])

            mem_keys = sorted(
                role_key_by_id.get(rid, "") for rid in member_role_ids_by_member.get(m.id, set())
            )
            mem_keys = [k for k in mem_keys if k]
            data["member_role_keys"] = mem_keys

            effective = sorted(set(data["generation_role_keys"]) | set(mem_keys))
            data["effective_role_keys"] = effective

            # effective_permission_keys (transitive closure)
            member_role_ids = (
                member_role_ids_by_member.get(m.id, set())
                | gen_role_ids_by_generation.get(gen, set())
            )
            base_perm_ids: set[UUID] = set()
            for rid in member_role_ids:
                base_perm_ids |= perm_ids_by_role.get(rid, set())

            # expand via implication
            expanded_perm_ids = set(base_perm_ids)
            from collections import deque
            q: deque[UUID] = deque(expanded_perm_ids)
            while q:
                p = q.popleft()
                for child in children_map.get(p, set()):
                    if child not in expanded_perm_ids:
                        expanded_perm_ids.add(child)
                        q.append(child)

            data["effective_permission_keys"] = sorted(
                perm_key_by_id[pid] for pid in expanded_perm_ids if pid in perm_key_by_id
            )

        schemas.append(MemberDetailSchema(**data))

    return schemas


@router.get(
    "/self",
    summary="自分自身を取得",
    description="自分自身を取得します。",
    response_model=MemberDetailSchema,
)
async def get_self(
    include_groups: bool = False,
    include_weekly_participation: bool = False,
    include_status_periods: bool = False,
    include_roles: bool = False,
    session: models.Session = Depends(get_valid_session),
    db: AsyncSession = Depends(get_db),
) -> MemberDetailSchema:
    member = session.member

    # 追加情報が必要なら、IDで必要な関連だけロードして取り直す（全件取得はしない）
    if include_groups or include_weekly_participation or include_status_periods:
        loaded = await cruds.get_member_by_id(
            db,
            member.id,
            include_groups=include_groups,
            include_weekly_participation=include_weekly_participation,
            include_status_periods=include_status_periods,
        )
        if loaded is not None:
            member = loaded

    if include_weekly_participation:
        records_dict = {r.weekday: r for r in member.weekly_participations}
        weekly_list = []
        for day in range(7):
            if day in records_dict:
                rec = records_dict[day]
                weekly_list.append(
                    models.WeeklyParticipation(
                        id=rec.id,
                        member_id=rec.member_id,
                        weekday=rec.weekday,
                        is_active=rec.is_active,
                        default_attendance=rec.default_attendance,
                    )
                )
            else:
                weekly_list.append(
                    models.WeeklyParticipation(
                        id=uuid4(),
                        member_id=member.id,
                        weekday=day,
                        is_active=False,
                    )
                )
        member.weekly_participations = weekly_list

    data = Member.model_validate(member).model_dump()

    data["groups"] = (
        MemberGroupsSchema.model_validate(member).groups
        if include_groups
        else []
    )

    data["weekly_participations"] = (
        MemberWeeklySchema.model_validate(member).weekly_participations
        if include_weekly_participation
        else []
    )

    data["membership_status_periods"] = (
        MembershipStatusPeriodSchema.model_validate(member).membership_status_periods
        if include_status_periods
        else []
    )

    if include_roles:
        # 表示は member_role_keys のみの予定でも、API的には両方返せるようにする
        data["generation_role_keys"] = await rbac.generation_role_keys_for_generation(db, int(member.generation))
        data["member_role_keys"] = await rbac.member_role_keys_for_member(db, member.id)
        data["effective_role_keys"] = await rbac.effective_role_keys_for_member(db, member.id)
        data["effective_permission_keys"] = sorted(
            await rbac.effective_permission_keys_for_member(db, member.id)
        )

    return MemberDetailSchema(**data)


@router.get(
    "/idm/{felica_idm}",
    summary="FelicaのIDmから部員を取得",
    description="FelicaのIDmから部員を取得します。",
    response_model=MemberDetailSchema | None,
)
async def get_by_felica_idm(
    felica_idm: str,
    include_groups: bool = False,
    include_weekly_participation: bool = False,
    include_status_periods: bool = False,
    db: AsyncSession = Depends(get_db),
) -> MemberDetailSchema | None:
    member = await cruds.get_member_by_felica_idm(db, felica_idm)
    if member is None:
        return None

    # 追加情報が必要なら、必要な関連だけ selectinload するために取り直す
    if include_groups or include_weekly_participation or include_status_periods:
        loaded = await cruds.get_members(
            db,
            include_groups=include_groups,
            include_weekly_participation=include_weekly_participation,
            include_status_periods=include_status_periods,
        )
        # get_members はフィルタなしだと全件取得なので、自分だけに絞る
        member = next((m for m in loaded if m.id == member.id), member)

    if include_weekly_participation:
        records_dict = {r.weekday: r for r in member.weekly_participations}
        weekly_list = []
        for day in range(7):
            if day in records_dict:
                rec = records_dict[day]
                weekly_list.append(
                    models.WeeklyParticipation(
                        id=rec.id,
                        member_id=rec.member_id,
                        weekday=rec.weekday,
                        is_active=rec.is_active,
                        default_attendance=rec.default_attendance,
                    )
                )
            else:
                weekly_list.append(
                    models.WeeklyParticipation(
                        id=uuid4(),
                        member_id=member.id,
                        weekday=day,
                        is_active=False,
                    )
                )
        member.weekly_participations = weekly_list

    data = Member.model_validate(member).model_dump()

    data["groups"] = (
        MemberGroupsSchema.model_validate(member).groups
        if include_groups
        else []
    )

    data["weekly_participations"] = (
        MemberWeeklySchema.model_validate(member).weekly_participations
        if include_weekly_participation
        else []
    )

    data["membership_status_periods"] = (
        MembershipStatusPeriodSchema.model_validate(member).membership_status_periods
        if include_status_periods
        else []
    )

    return MemberDetailSchema(**data)


@router.post(
    "",
    summary="部員を登録",
    description="部員を登録します。",
    response_model=MemberDetailSchema,
    dependencies=[Depends(require_permission("member:write"))],
)
async def post_member(m: MemberParams = Form(), db: AsyncSession = Depends(get_db)):
    try:
        member = models.Member(**m.model_dump())
        result = await cruds.add_member(db, member)

        records_dict = {r.weekday: r for r in result.weekly_participations}

        weekly_list = []
        for day in range(7):
            if day in records_dict:
                rec = records_dict[day]
                weekly_list.append(
                    models.WeeklyParticipation(
                        id=rec.id,
                        member_id=rec.member_id,
                        weekday=rec.weekday,
                        is_active=rec.is_active,
                        default_attendance=rec.default_attendance,
                    )
                )
            else:
                weekly_list.append(
                    models.WeeklyParticipation(
                        id=uuid4(),
                        member_id=result.id,
                        weekday=day,
                        is_active=False,
                    )
                )
        result.weekly_participations = weekly_list

        return result
    except IntegrityError as e:
        raise APIErrorCode.ALREADY_EXISTS_MEMBER_EMAIL.of(f"Already exists member email: {e.code}")


@router.post(
    "s",
    summary="部員を登録",
    description="部員を登録します。",
    dependencies=[Depends(require_permission("member:write"))],
)
async def post_members(members: list[MemberParams],
                       db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    member_list = [models.Member(**m.model_dump()) for m in members]
    await cruds.add_members(db, member_list)
    return MembersOperationalResult(result=True)


@router.delete(
    "/{member_id}",
    summary="部員を削除",
    description="部員を削除します。部員が存在しない場合でもエラーを返しません。",
    dependencies=[Depends(require_permission("member:write"))],
)
async def delete_member(member_id: UUID,
                        db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.remove_member(db, member_id)
    return MembersOperationalResult(result=True)


@router.patch(
    "/{member_id}",
    summary="部員情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
    dependencies=[Depends(require_permission("member:write"))],
)
async def patch_member(member_id: UUID, m: MemberParamsOptional,
                       db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_member(db, member_id, m)
    return MembersOperationalResult(result=True)


@router.patch(
    "/competition/{is_competition_member}",
    summary="部員のコンクールメンバー情報を更新",
    dependencies=[Depends(require_permission("member:write"))],
)
async def patch_competition_members(is_competition_member: bool, member_ids: list[UUID] = Body,
                                    db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_members_competition(db, member_ids, is_competition_member)
    return MembersOperationalResult(result=True)


@router.patch(
    "/retired/{is_temporarily_retired}",
    summary="部員のコンクールメンバー情報を更新",
    dependencies=[Depends(require_permission("member:write"))],
)
async def patch_retired_members(is_temporarily_retired: bool, member_ids: list[UUID] = Body,
                                db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_members_retired(db, member_ids, is_temporarily_retired)
    return MembersOperationalResult(result=True)


@router.get(
    "/{member_id}/weekly_participation",
    summary="部員の曜日ごとの参加情報を取得",
    description="部員の曜日ごとの参加情報（講習の曜日など）を取得します。",
    response_model=list[WeeklyParticipation],
    dependencies=[Depends(require_permission("member:read"))],
)
async def get_weekly_participations(member_id: UUID, db: AsyncSession = Depends(get_db)):
    records = await cruds.get_weekly_participation(db, member_id)
    records_dict = {r.weekday: r for r in records}

    result = []
    for day in range(7):
        if day in records_dict:
            rec = records_dict[day]
            result.append(WeeklyParticipation(
                id=rec.id,
                member_id=rec.member_id,
                weekday=rec.weekday,
                is_active=rec.is_active,
                default_attendance=rec.default_attendance
            ))
        else:
            result.append(WeeklyParticipation(
                id=uuid4(),
                member_id=member_id,
                weekday=day,
                is_active=False,
                default_attendance=None
            ))

    return result


@router.post(
    "/{member_id}/weekly_participation",
    summary="部員の曜日ごとの参加情報を登録／更新",
    description="部員の曜日ごとの参加情報を登録（すでに存在する場合は更新）します。",
    dependencies=[Depends(require_permission("member:write"))],
)
async def post_weekly_participation(member_id: UUID, wp: WeeklyParticipationParams = Form(),
                                    db: AsyncSession = Depends(get_db)):
    await cruds.upsert_weekly_participation(db, member_id, wp)
    return dict(result=True)


@router.get(
    "/{member_id}/statuses",
    summary="部員の活動状態を取得",
    description="部員の活動状態を取得します。",
    response_model=list[MembershipStatusPeriod],
    dependencies=[Depends(require_permission("member:read"))],
)
async def get_membership_statuses(member_id: UUID, db: AsyncSession = Depends(get_db)):
    return await cruds.get_membership_status_periods(db, member_id)


@router.post(
    "/{member_id}/status",
    summary="部員の活動状態を登録",
    description="部員の活動状態を登録します。",
    response_model=MembershipStatusPeriod,
    dependencies=[Depends(require_permission("member:write"))],
)
async def post_membership_status_period(member_id: UUID, params: MembershipStatusPeriodParams,
                                        db: AsyncSession = Depends(get_db)):
    status_period = models.MembershipStatusPeriod(**params.model_dump(), member_id=member_id)
    return await cruds.add_membership_status_period(db, status_period)


@router.delete(
    "/statuses/{status_period_id}",
    summary="部員の活動状態を削除",
    description="部員の活動状態を削除します。",
    dependencies=[Depends(require_permission("member:write"))],
)
async def delete_membership_status_period(status_period_id: UUID,
                                          db: AsyncSession = Depends(get_db)):
    await cruds.remove_membership_status_period(db, status_period_id)
    return dict(result=True)


@router.patch(
    "/statuses/{status_period_id}",
    summary="部員の活動状態を更新",
    description="部員の活動状態を更新します。",
    dependencies=[Depends(require_permission("member:write"))],
)
async def patch_membership_status_period(status_period_id: UUID,
                                         params: MembershipStatusPeriodParams,
                                         db: AsyncSession = Depends(get_db)):
    await cruds.update_membership_status_period(db, status_period_id, params)
    return dict(result=True)


@router.get(
    "/{member_id}/groups",
    summary="部員の所属グループを取得",
    description="部員の所属グループを取得します。",
    response_model=list[Group],
    dependencies=[Depends(require_permission("group:read"))],
)
async def get_member_groups(member_id: UUID, db: AsyncSession = Depends(get_db)):
    return await cruds.get_member_groups(db, member_id)


@router.post(
    "/statuses",
    summary="複数人の活動状態を一括登録",
    description="複数の部員に対して同じ活動状態を一度に登録します。",
    response_model=list[MembershipStatusPeriod],
    dependencies=[Depends(require_permission("member:write"))],
)
async def post_membership_status_periods(member_ids: list[UUID] = Body(...),
                                         status_period: MembershipStatusPeriodParams = Body(...),
                                         db: AsyncSession = Depends(get_db)):
    status_periods = [
        models.MembershipStatusPeriod(
            id=uuid4(),
            member_id=mid,
            status_id=status_period.status_id,
            start_date=status_period.start_date,
            end_date=status_period.end_date,
        )
        for mid in member_ids
    ]

    rows = await cruds.add_membership_status_periods(db, status_periods)
    return rows
