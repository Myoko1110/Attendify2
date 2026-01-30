from uuid import UUID, uuid4  # noqa: F401

from fastapi import APIRouter, Body, Depends, Form
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.dependencies import get_valid_session
from app.schemas import *
from app.database import models

router = APIRouter(prefix="/member", tags=["Member"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="部員を取得",
    description="部員を取得します。",
    response_model=list[MemberDetailSchema],
)
async def get_members(
    part: Part = None,
    generation: int = None,
    include_groups: bool = False,
    include_weekly_participation: bool = False,
    include_status_periods: bool = False,
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

    schemas: list[MemberDetailSchema] = []

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

        schemas.append(MemberDetailSchema(**data))

    return schemas


@router.get(
    "/self",
    summary="自分自身を取得",
    description="自分自身を取得します。",
    response_model=Member,
)
async def get_self(session: models.Session = Depends(get_valid_session)) -> Member:
    return session.member


@router.post(
    "",
    summary="部員を登録",
    description="部員を登録します。",
    response_model=Member,
)
async def post_member(m: MemberParams = Form(), db: AsyncSession = Depends(get_db)):
    try:
        member = models.Member(**m.model_dump())
        return await cruds.add_member(db, member)
    except IntegrityError as e:
        raise APIErrorCode.ALREADY_EXISTS_MEMBER_EMAIL.of(f"Already exists member email: {e.code}")


@router.post(
    "s",
    summary="部員を登録",
    description="部員を登録します。",
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
)
async def delete_member(member_id: UUID,
                        db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.remove_member(db, member_id)
    return MembersOperationalResult(result=True)


@router.patch(
    "/{member_id}",
    summary="部員情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_member(member_id: UUID, m: MemberParamsOptional,
                       db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_member(db, member_id, m)
    return MembersOperationalResult(result=True)


@router.patch(
    "/competition/{is_competition_member}",
    summary="部員のコンクールメンバー情報を更新",
)
async def patch_competition_members(is_competition_member: bool, member_ids: list[UUID] = Body,
                                    db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_members_competition(db, member_ids, is_competition_member)
    return MembersOperationalResult(result=True)


@router.patch(
    "/retired/{is_temporarily_retired}",
    summary="部員のコンクールメンバー情報を更新",
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
)
async def get_membership_statuses(member_id: UUID, db: AsyncSession = Depends(get_db)):
    return await cruds.get_membership_status_periods(db, member_id)


@router.post(
    "/{member_id}/status",
    summary="部員の活動状態を登録",
    description="部員の活動状態を登録します。",
    response_model=MembershipStatusPeriod,
)
async def post_membership_status_period(member_id: UUID, params: MembershipStatusPeriodParams,
                                        db: AsyncSession = Depends(get_db)):
    status_period = models.MembershipStatusPeriod(**params.model_dump(), member_id=member_id)
    return await cruds.add_membership_status_period(db, status_period)


@router.delete(
    "/statuses/{status_period_id}",
    summary="部員の活動状態を削除",
    description="部員の活動状態を削除します。",
)
async def delete_membership_status_period(status_period_id: UUID,
                                          db: AsyncSession = Depends(get_db)):
    await cruds.remove_membership_status_period(db, status_period_id)
    return dict(result=True)


@router.patch(
    "/statuses/{status_period_id}",
    summary="部員の活動状態を更新",
    description="部員の活動状態を更新します。",
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
)
async def get_member_groups(member_id: UUID, db: AsyncSession = Depends(get_db)):
    return await cruds.get_member_groups(db, member_id)


@router.post(
    "/statuses",
    summary="複数人の活動状態を一括登録",
    description="複数の部員に対して同じ活動状態を一度に登録します。",
    response_model=list[MembershipStatusPeriod],
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
