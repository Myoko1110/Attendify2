from fastapi import APIRouter, Depends, Form
from sqlalchemy.exc import IntegrityError

from app.abc.api_error import APIErrorCode
from app.database import db
from app.dependencies import get_valid_session
from app.schemas import *

router = APIRouter(prefix="/member", tags=["Member"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="部員を取得",
    description="部員を取得します。",
)
async def get_members(part: Part = None, generation: int = None) -> list[Member]:
    return [Member.create(a) for a in await db.get_members(part=part, generation=generation)]


@router.get(
    "/self",
    summary="自分自身を取得",
    description="自分自身を取得します。",
)
async def get_self(session: Session = Depends(get_valid_session)) -> Member:
    return session.member


@router.post(
    "",
    summary="部員を登録",
    description="部員を登録します。",
)
async def post_member(m: MemberParams = Form()) -> Member:
    try:
        member = models.Member(part=m.part, generation=m.generation, name=m.name, name_kana=m.name_kana, email=m.email, role=m.role)
        return await db.add_member(member)
    except IntegrityError as e:
        raise APIErrorCode.ALREADY_EXISTS_MEMBER_EMAIL.of(f"Already exists member email: {e.code}")


@router.post(
    "s",
    summary="部員を登録",
    description="部員を登録します。",
)
async def post_members(members: list[MemberParams]) -> MembersOperationalResult:
    member_list = [models.Member(part=m.part, generation=m.generation, name=m.name, name_kana=m.name_kana, email=m.email, role=m.role) for m in members]
    await db.add_members(member_list)
    return MembersOperationalResult(result=True)


@router.delete(
    "/{member_id}",
    summary="部員を削除",
    description="部員を削除します。部員が存在しない場合でもエラーを返しません。",
)
async def delete_member(member_id: UUID) -> MembersOperationalResult:
    await db.remove_member(member_id)
    return MembersOperationalResult(result=True)


@router.patch(
    "/{member_id}",
    summary="部員情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_member(member_id: UUID, m: MemberParamsOptional) -> MembersOperationalResult:
    await db.update_member(member_id, m)
    return MembersOperationalResult(result=True)
