from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.abc.api_error import APIErrorCode
from app.database import cruds, get_db
from app.dependencies import require_permission
from app.schemas.rbac import (
    GenerationRoleAssign,
    GenerationRole,
    MemberRoleAssign,
    MemberRolesSchema,
    PermissionImpliesEdgeSchema,
    PermissionSchema,
    ResultSchema,
    RoleCreate,
    RolePermissionAssign,
    RoleSchema,
    RoleUpdate,
)

router = APIRouter(
    prefix="/rbac",
    tags=["RBAC"],
)


@router.get("/permissions", response_model=list[PermissionSchema])
async def list_permissions(db: AsyncSession = Depends(get_db)):
    return await cruds.rbac_list_permissions(db)


@router.get("/roles", response_model=list[RoleSchema])
async def list_roles(db: AsyncSession = Depends(get_db)):
    return await cruds.rbac_list_roles(db)


@router.post("/roles", response_model=RoleSchema, status_code=201, dependencies=[Depends(require_permission("rbac:manage"))],)
async def create_role(payload: RoleCreate, db: AsyncSession = Depends(get_db)):
    role = await cruds.rbac_create_role(db, key=payload.key, display_name=payload.display_name, description=payload.description)
    return role


@router.patch("/roles/{role_key}", response_model=RoleSchema, dependencies=[Depends(require_permission("rbac:manage"))],)
async def update_role(role_key: str, payload: RoleUpdate, db: AsyncSession = Depends(get_db)):
    role = await cruds.rbac_update_role(db, role_key, display_name=payload.display_name, description=payload.description)
    if role is None:
        raise APIErrorCode.ROLE_NOT_FOUND.of(f"Role '{role_key}' not found", 404)
    return role


@router.delete("/roles/{role_key}", response_model=ResultSchema, dependencies=[Depends(require_permission("rbac:manage"))],)
async def delete_role(role_key: str, db: AsyncSession = Depends(get_db)):
    deleted = await cruds.rbac_delete_role(db, role_key)
    if not deleted:
        raise APIErrorCode.ROLE_NOT_FOUND.of(f"Role '{role_key}' not found", 404)
    return ResultSchema(result=True)


@router.get("/roles/{role_key}/permissions", response_model=list[PermissionSchema])
async def get_role_permissions(role_key: str, db: AsyncSession = Depends(get_db)):
    role = await cruds.rbac_get_role_permissions(db, role_key)
    if role is None:
        raise APIErrorCode.ROLE_NOT_FOUND.of(f"Role '{role_key}' not found", 404)
    return sorted(role.permissions, key=lambda p: p.key)


@router.put("/roles/{role_key}/permissions", response_model=list[PermissionSchema], dependencies=[Depends(require_permission("rbac:manage"))],)
async def put_role_permissions(role_key: str, payload: RolePermissionAssign, db: AsyncSession = Depends(get_db)):
    try:
        role = await cruds.rbac_replace_role_permissions(db, role_key, permission_keys=payload.permission_keys)
    except ValueError as e:
        raise APIErrorCode.AUTHENTICATION_FAILED.of(str(e), 400)
    if role is None:
        raise APIErrorCode.ROLE_NOT_FOUND.of(f"Role '{role_key}' not found", 404)
    return sorted(role.permissions, key=lambda p: p.key)


@router.get("/generations/{generation}/roles", response_model=GenerationRole)
async def get_generation_roles(generation: int, db: AsyncSession = Depends(get_db)):
    keys = await cruds.rbac_get_generation_role_keys(db, generation)
    return GenerationRole(generation=generation, role_keys=keys)


@router.get("/generations/roles", response_model=list[GenerationRole])
async def get_generations_roles(
    generations: list[int] | None = Query(default=None, description="対象generationを複数指定。未指定なら全generationを返す"),
    db: AsyncSession = Depends(get_db),
):
    by_gen = await cruds.rbac_get_generations_role_keys(db, generations=generations)
    items = [
        {"generation": gen, "role_keys": keys}
        for gen, keys in sorted(by_gen.items(), key=lambda x: x[0])
    ]
    return items


@router.put("/generations/{generation}/roles", response_model=ResultSchema, dependencies=[Depends(require_permission("rbac:manage"))],)
async def put_generation_roles(generation: int, payload: GenerationRoleAssign, db: AsyncSession = Depends(get_db)):
    try:
        await cruds.rbac_replace_generation_roles(db, generation, role_keys=payload.role_keys)
    except ValueError as e:
        raise APIErrorCode.AUTHENTICATION_FAILED.of(str(e), 400)

    await db.commit()
    return ResultSchema(result=True)


@router.put("/generations/roles", response_model=ResultSchema, dependencies=[Depends(require_permission("rbac:manage"))],)
async def put_generations_roles(payload: list[GenerationRole], db: AsyncSession = Depends(get_db)):
    try:
        await cruds.rbac_replace_generations_roles_bulk(
            db,
            items=payload,
        )
    except ValueError as e:
        raise APIErrorCode.AUTHENTICATION_FAILED.of(str(e), 400)

    await db.commit()
    return ResultSchema(result=True)


@router.get("/permissions/implies", response_model=list[PermissionImpliesEdgeSchema])
async def get_permission_implies(
    parent_keys: list[str] | None = Query(default=None, description="親permissionを複数指定。未指定なら全エッジを返す"),
    db: AsyncSession = Depends(get_db),
):
    rows = await cruds.rbac_get_permission_implies_edges(db, parent_keys=parent_keys)
    edges = [PermissionImpliesEdgeSchema(parent_key=p, child_key=c) for p, c in rows]
    return edges


@router.get("/members/{member_id}/roles", response_model=MemberRolesSchema)
async def get_member_roles(member_id: UUID, db: AsyncSession = Depends(get_db)):
    keys = await cruds.rbac_get_member_role_keys(db, member_id)
    return MemberRolesSchema(member_id=member_id, role_keys=keys)


@router.put("/members/{member_id}/roles", response_model=ResultSchema, dependencies=[Depends(require_permission("rbac:manage"))],)
async def put_member_roles(member_id: UUID, payload: MemberRoleAssign, db: AsyncSession = Depends(get_db)):
    try:
        await cruds.rbac_replace_member_roles(db, member_id, role_keys=payload.role_keys)
    except ValueError as e:
        raise APIErrorCode.AUTHENTICATION_FAILED.of(str(e), 400)

    await db.commit()
    return ResultSchema(result=True)
