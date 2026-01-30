from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import cruds, get_db, models
from app.dependencies import get_valid_session
from app.schemas import MembershipStatus, MembershipStatusParams

router = APIRouter(prefix="/membership_status", tags=["MembershipStatus"],
                   dependencies=[Depends(get_valid_session)])


@router.get(
    "es",
    summary="活動状態マスタを取得",
    description="活動状態マスタを取得します。",
    response_model=list[MembershipStatus],
)
async def get_membership_statuses(db: AsyncSession = Depends(get_db)):
    return await cruds.get_membership_statuses(db)


@router.post(
    "",
    summary="活動状態マスタを作成",
    description="新しい活動状態マスタを作成します。",
    response_model=MembershipStatus,
)
async def post_membership_status(
    params: MembershipStatusParams,
    db: AsyncSession = Depends(get_db),
):
    ms = models.MembershipStatus(**params.model_dump())
    return await cruds.add_membership_status(db, ms)


@router.delete(
    "/{membership_status_id}",
    summary="活動状態マスタを削除",
    description="指定したIDの活動状態マスタを削除します。",
)
async def delete_membership_status(
    membership_status_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await cruds.remove_membership_status(db, membership_status_id)
    return dict(result=True)
