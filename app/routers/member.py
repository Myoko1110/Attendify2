from uuid import UUID

from fastapi import APIRouter, Form

from app import schemas
from app.abc.part import Part
from app.abc.role import Role
from app.database import db, models
from app.schemas import MemberOperationalResult

router = APIRouter(prefix="/member", tags=["Member"])


@router.get(
    "s/",
    summary="部員を取得",
    description="部員を取得します。",
)
async def get_members(part: Part = None, generation: int = None) -> list[schemas.Member]:
    return [schemas.Member.create(a) for a in await db.get_members(part=part, generation=generation)]


@router.post(
    "/",
    summary="部員を登録",
    description="部員を登録します。",
)
async def post_attendance(part: Part = Form(), generation: int = Form(), name: str = Form(), name_kana: str = Form(), email: str = Form(), role: Role = Form()) -> MemberOperationalResult:
    member = models.Member(part=part, generation=generation, name=name, name_kana=name_kana, email=email, role=role)
    member_id = await db.add_member(member)
    return schemas.MemberOperationalResult(result=True, member_id=member_id)
