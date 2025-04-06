from uuid import UUID

from fastapi import APIRouter, Depends, Form

from app import schemas
from app.abc.part import Part
from app.database import db, models
from app.dependencies import get_valid_session
from app.schemas import MemberOperationalResult, MemberParams, MemberParamsOptional, \
    MembersOperationalResult

router = APIRouter(prefix="/member", tags=["Member"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="部員を取得",
    description="部員を取得します。",
)
async def get_members(part: Part = None, generation: int = None) -> list[schemas.Member]:
    return [schemas.Member.create(a) for a in await db.get_members(part=part, generation=generation)]


@router.post(
    "",
    summary="部員を登録",
    description="部員を登録します。",
)
async def post_member(m: MemberParams = Form()) -> MemberOperationalResult:
    member = models.Member(part=m.part, generation=m.generation, name=m.name, name_kana=m.name_kana, email=m.email, role=m.role)
    member_id = await db.add_member(member)
    return schemas.MemberOperationalResult(result=True, member_id=member_id)


@router.post(
    "s",
    summary="部員を登録",
    description="部員を登録します。",
)
async def post_members(members: list[schemas.MemberParams]) -> schemas.MembersOperationalResult:
    member_list = [models.Member(part=m.part, generation=m.generation, name=m.name, name_kana=m.name_kana, email=m.email, role=m.role) for m in members]
    await db.add_members(member_list)
    return schemas.MembersOperationalResult(result=True)


@router.delete(
    "/{member_id}",
    summary="部員を削除",
    description="部員を削除します。部員が存在しない場合でもエラーを返しません。",
)
async def delete_attendance(member_id: UUID) -> MembersOperationalResult:
    await db.remove_member(member_id)
    return schemas.MembersOperationalResult(result=True)


@router.patch(
    "/{member_id}",
    summary="部員情報を更新",
    description="出欠情報を更新します。出欠情報が存在しない場合でもエラーを返しません。",
)
async def patch_attendance(member_id: UUID, m: MemberParamsOptional) -> MembersOperationalResult:
    await db.update_attendance(member_id, m)
    return schemas.MembersOperationalResult(result=True)
