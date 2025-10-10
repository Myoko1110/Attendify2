from fastapi import APIRouter, Depends, Form, Body
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.dependencies import get_valid_session
from app.schemas import *

router = APIRouter(prefix="/member", tags=["Member"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="部員を取得",
    description="部員を取得します。",
    response_model=list[Member],
)
async def get_members(part: Part = None, generation: int = None, db: AsyncSession = Depends(get_db)):
    return [a for a in await cruds.get_members(db, part=part, generation=generation)]


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
async def post_members(members: list[MemberParams], db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    member_list = [models.Member(**m.model_dump()) for m in members]
    await cruds.add_members(db, member_list)
    return MembersOperationalResult(result=True)


@router.delete(
    "/{member_id}",
    summary="部員を削除",
    description="部員を削除します。部員が存在しない場合でもエラーを返しません。",
)
async def delete_member(member_id: UUID, db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.remove_member(db, member_id)
    return MembersOperationalResult(result=True)


@router.patch(
    "/{member_id}",
    summary="部員情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_member(member_id: UUID, m: MemberParamsOptional, db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_member(db, member_id, m)
    return MembersOperationalResult(result=True)


@router.patch(
    "/competition/{is_competition_member}",
    summary="部員のコンクールメンバー情報を更新",
)
async def patch_competition_members(is_competition_member: bool, member_ids: list[UUID] = Body, db: AsyncSession = Depends(get_db)) -> MembersOperationalResult:
    await cruds.update_members_competition(db, member_ids, is_competition_member)
    return MembersOperationalResult(result=True)
