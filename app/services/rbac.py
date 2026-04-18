from __future__ import annotations

from collections import deque
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    GenerationRole,
    Member,
    MemberRole,
    PermissionImplies,
    RBACPermission,
    RBACRole,
    RolePermission,
)


async def _role_ids_for_member(db: AsyncSession, member_id: UUID) -> set[UUID]:
    # member's generation
    member = await db.get(Member, member_id)
    if not member:
        return set()

    role_ids: set[UUID] = set()

    # personal roles
    rows = (await db.execute(select(MemberRole.role_id).where(MemberRole.member_id == member_id))).all()
    role_ids.update(r[0] for r in rows)

    # generation roles
    rows = (
        await db.execute(select(GenerationRole.role_id).where(GenerationRole.generation == member.generation))
    ).all()
    role_ids.update(r[0] for r in rows)

    # default role: always granted to every member if the role exists in DB
    default_role = (await db.execute(select(RBACRole).where(RBACRole.key == "default"))).scalar_one_or_none()
    if default_role:
        role_ids.add(default_role.id)

    return role_ids


async def effective_permission_keys_for_member(db: AsyncSession, member_id: UUID) -> set[str]:
    role_ids = await _role_ids_for_member(db, member_id)
    if not role_ids:
        return set()

    perm_ids = set(
        r[0]
        for r in (
            await db.execute(select(RolePermission.permission_id).where(RolePermission.role_id.in_(role_ids)))
        ).all()
    )

    if not perm_ids:
        return set()

    # Expand via implication edges (transitive closure)
    edges = (
        await db.execute(
            select(PermissionImplies.parent_permission_id, PermissionImplies.child_permission_id)
        )
    ).all()

    children_map: dict[UUID, set[UUID]] = {}
    for parent_id, child_id in edges:
        children_map.setdefault(parent_id, set()).add(child_id)

    q: deque[UUID] = deque(perm_ids)
    while q:
        p = q.popleft()
        for child in children_map.get(p, ()):  # type: ignore[arg-type]
            if child not in perm_ids:
                perm_ids.add(child)
                q.append(child)

    keys = set(
        r[0]
        for r in (
            await db.execute(select(RBACPermission.key).where(RBACPermission.id.in_(perm_ids)))
        ).all()
    )
    return keys


def has_permission(permission_keys: Iterable[str], required: str) -> bool:
    return required in set(permission_keys)


async def generation_role_keys_for_generation(db: AsyncSession, generation: int) -> list[str]:
    rows = (
        await db.execute(
            select(RBACRole.key)
            .join(GenerationRole, GenerationRole.role_id == RBACRole.id)
            .where(GenerationRole.generation == generation)
            .order_by(RBACRole.key)
        )
    ).all()
    return [r[0] for r in rows]


async def member_role_keys_for_member(db: AsyncSession, member_id: UUID) -> list[str]:
    rows = (
        await db.execute(
            select(RBACRole.key)
            .join(MemberRole, MemberRole.role_id == RBACRole.id)
            .where(MemberRole.member_id == member_id)
            .order_by(RBACRole.key)
        )
    ).all()
    return [r[0] for r in rows]


async def effective_role_keys_for_member(db: AsyncSession, member_id: UUID) -> list[str]:
    member = await db.get(Member, member_id)
    if not member:
        return []

    gen_keys = await generation_role_keys_for_generation(db, int(member.generation))
    mem_keys = await member_role_keys_for_member(db, member_id)
    all_keys: set[str] = set(gen_keys) | set(mem_keys)

    # default role: always granted to every member if the role exists in DB
    default_role = (await db.execute(select(RBACRole).where(RBACRole.key == "default"))).scalar_one_or_none()
    if default_role:
        all_keys.add(default_role.key)

    return sorted(all_keys)


# backwards compatible alias
async def role_keys_for_generation(db: AsyncSession, generation: int) -> list[str]:
    return await generation_role_keys_for_generation(db, generation)
