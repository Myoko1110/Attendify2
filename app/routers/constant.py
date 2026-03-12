from fastapi import APIRouter, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.abc.part import Part
from app.abc.role import Role
from app.database import cruds, get_db
from app.dependencies import get_valid_session, require_permission
from app.schemas.constant import GradesSchema, PartSchema
from app.schemas.constant_rbac import GradesWithRolesSchema, GradeWithRolesSchema
from app.utils import settings

router = APIRouter(prefix="/constant", tags=["Constant"])


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
async def get_grade(
    include_generation_roles: bool = False,
    db: AsyncSession = Depends(get_db),
) -> GradesSchema | GradesWithRolesSchema:
    grades = settings.get("grade", {})

    if not include_generation_roles:
        return grades

    # settings.yml の grade をベースに、generation_roles をマージして返す
    gens = []
    for v in grades.values():
        try:
            gens.append(int(v.get("generation")))
        except Exception:
            continue

    by_gen = await cruds.rbac_get_generations_role_keys(db, generations=sorted(set(gens)))

    out = {}
    for k, v in grades.items():
        gen = int(v.get("generation"))
        out[k] = GradeWithRolesSchema(**v, generation_role_keys=by_gen.get(gen, []))

    return GradesWithRolesSchema(**out)
