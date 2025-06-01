from pathlib import Path

import yaml
from fastapi import APIRouter, Depends

from app.abc.part import Part
from app.abc.role import Role
from app.dependencies import get_valid_session
from app.schemas.constant import GradesSchema, PartSchema
from app.utils import load_setting_data, settings

router = APIRouter(prefix="/constant", tags=["Constant"], dependencies=[Depends(get_valid_session)])


@router.get(
    "/part",
    summary="パートを取得",
    description="パートの情報を取得します。",
)
async def get_part() -> dict[Part, PartSchema]:
    return {p: PartSchema.create(p.detail) for p in Part}


@router.get(
    "/role",
    summary="役職を取得",
    description="役職の情報を取得します。",
)
async def get_role() -> dict[Role, str]:
    return {r: r.display_name for r in Role}





@router.get(
    "/grade",
    summary="学年を取得",
    description="学年の情報を取得します。",
)
async def get_grade() -> GradesSchema:
    return settings.get("grade", {})
