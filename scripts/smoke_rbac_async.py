"""Quick smoke test for RBAC evaluation (async).

This script:
- Ensures tables exist (via Base.metadata.create_all).
- Seeds RBAC (roles/permissions/implications) using existing seed script.
- Creates a temporary member with a generation.
- Assigns a generation role and checks effective permissions.

Note: Uses DATABASE_URL if set; otherwise uses app.database ASYNC config.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import async_engine, async_session
from app.database.models import Base, GenerationRole, Member, RBACRole
from app.services.rbac import effective_permission_keys_for_member
from app.abc.part import Part


async def main() -> None:
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        # create member
        m = Member(
            id=uuid4(),
            part=Part.FLUTE,
            generation=51,
            name="smoke",
            name_kana="smoke",
            email=None,
            role=None,
            lecture_day=[],
            is_competition_member=False,
        )
        db.add(m)
        await db.commit()

    # We rely on external seeding for roles/permissions. If missing, keys check will be empty.
    async with async_session() as db:
        role = (await db.execute(select(RBACRole).where(RBACRole.key == "grade_viewer"))).scalar_one_or_none()
        if not role:
            raise SystemExit("RBACRole 'grade_viewer' not found. Run: python scripts/seed_rbac.py")

        db.add(GenerationRole(generation=51, role_id=role.id))
        await db.commit()

    async with async_session() as db:
        keys = await effective_permission_keys_for_member(db, m.id)
        print("effective permission keys:", sorted(keys))
        assert "dashboard:access" in keys
        assert "dashboard:read" in keys


if __name__ == "__main__":
    asyncio.run(main())
