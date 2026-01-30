from fastapi import APIRouter, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import cruds, get_db
from app.dependencies import get_valid_session
from app.schemas import *

router = APIRouter(prefix="/group", tags=["Group"], dependencies=[Depends(get_valid_session)])


@router.get(
    "s",
    summary="グループを取得",
    description="グループを取得します。",
    response_model=list[Group],
)
async def get_groups(db: AsyncSession = Depends(get_db)):
    return await cruds.get_groups(db)


@router.post(
    "",
    summary="グループを作成",
    description="新しいグループを作成します。",
    response_model=Group,
)
async def create_group(display_name: str = Form(), db: AsyncSession = Depends(get_db)):
    group = models.Group(display_name=display_name)
    return await cruds.add_group(db, group)


@router.delete(
    "/{group_id}",
    summary="グループを削除",
    description="指定したIDのグループを削除します。",
)
async def delete_group(group_id: UUID, db: AsyncSession = Depends(get_db)):
    await cruds.remove_group(db, group_id)
    return dict(result=True)


@router.put(
    "/{group_id}",
    summary="グループ名を更新",
    description="指定したIDのグループ名を更新します。",
)
async def update_group(group_id: UUID, display_name: str = Form(), db: AsyncSession = Depends(get_db)):
    await cruds.update_group(db, group_id, display_name)
    return dict(result=True)

@router.get(
    "/{group_id}/members",
    summary="グループの部員を取得",
    description="指定したIDのグループ名を更新します。",
    response_model=list[Member],
)
async def get_group_members(group_id: UUID, db: AsyncSession = Depends(get_db)):
    return await cruds.get_group_members(db, group_id)


@router.post(
    "/{group_id}/member/{member_id}",
    summary="グループに部員を追加",
    description="指定したIDのグループに部員を追加します。",
)
async def add_member_to_group(
    group_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    member_group = models.MemberGroup(member_id=member_id, group_id=group_id)
    await cruds.add_member_group(db, member_group)
    return dict(result=True)


@router.post(
    "/{group_id}/members",
    summary="グループに部員を追加",
    description="指定したIDのグループに部員を追加します。",
)
async def add_members_to_group(
    group_id: UUID,
    member_ids: list[UUID],
    db: AsyncSession = Depends(get_db),
):
    member_group = [models.MemberGroup(member_id=m_id, group_id=group_id) for m_id in member_ids]
    await cruds.add_members_group(db, member_group)
    return dict(result=True)


@router.delete(
    "/{group_id}/member/{member_id}",
    summary="グループから部員を削除",
    description="指定したIDのグループから部員を削除します。",
)
async def remove_member_from_group(
    group_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await cruds.remove_group_member(db, group_id, member_id)
    return dict(result=True)


@router.delete(
    "/{group_id}/members",
    summary="グループから部員を削除",
    description="指定したIDのグループから部員を削除します。",
)
async def remove_members_from_group(
    group_id: UUID,
    member_ids: list[UUID],
    db: AsyncSession = Depends(get_db),
):
    await cruds.remove_group_members(db, group_id, member_ids)
    return dict(result=True)
