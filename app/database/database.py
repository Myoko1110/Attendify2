import asyncio
import secrets
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import URL, delete, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, \
    create_async_engine
from sqlalchemy.orm import selectinload

from app.database.models import *


class AttendifyDatabase:
    def __init__(self, db_dir: Path, db_filename="attendify.db"):
        self.db_path = db_dir / db_filename
        self.engine = None  # type: AsyncEngine | None
        self._commit_lock = asyncio.Lock()

    async def connect(self):
        if self.engine:
            return

        url = URL.create(
            drivername="sqlite+aiosqlite",
            database=self.db_path.as_posix(),
            query=dict(
                charset="utf8mb4",
            ),
        )

        self.engine = create_async_engine(url, echo=False)

        async with self.engine.begin() as conn:  # type: AsyncConnection
            print("table creating...")
            await conn.run_sync(Base.metadata.create_all)
            print("table created")

    async def close(self):
        if self.engine is None:
            return

        await self.engine.dispose()
        self.engine = None

    def session(self) -> AsyncSession:
        return async_sessionmaker(autoflush=True, bind=self.engine)()

    @classmethod
    def generate_token(cls):
        return secrets.token_urlsafe(256)

    async def get_attendances(self, *, part: Part = None, generation: int = None,
                              date: datetime.date = None) -> list[Attendance]:
        async with self.session() as db:
            stmt = select(Attendance).options(selectinload(Attendance.member))

            if date is not None:
                stmt = stmt.where(Attendance.date == date)

            if part is not None:
                stmt = stmt.where(Member.part == part)

            if generation is not None:
                stmt = stmt.where(Member.generation == generation)

            result = await db.execute(stmt)
            return [r for r in result.scalars().all()]

    async def add_attendance(self, attendance: Attendance) -> list[UUID]:
        async with self._commit_lock:
            async with self.session() as db:
                db.add(attendance)
                await db.flush()
                await db.refresh(attendance)
                attendance_id = attendance.id
                await db.commit()
                return attendance_id

    async def add_attendances(self, attendances: list[Attendance]):
        async with self._commit_lock:
            async with self.session() as db:
                db.add_all(attendances)
                await db.commit()

    async def remove_attendance(self, attendance_id: UUID):
        async with self._commit_lock:
            async with self.session() as db:
                await db.execute(delete(Attendance).where(Attendance.id == attendance_id))
                await db.commit()

    async def update_attendance(self, attendance_id: UUID, attendance: str):
        async with self._commit_lock:
            async with self.session() as db:
                await db.execute(
                    update(Attendance).where(Attendance.id == attendance_id).values(attendance=attendance)
                )
                await db.commit()

    async def get_members(self, *, part: Part = None, generation: int = None) -> list[Member]:
        async with self.session() as db:
            stmt = select(Member)

            if part is not None:
                stmt = stmt.where(Member.part == part)

            if generation is not None:
                stmt = stmt.where(Member.generation == generation)

            result = await db.execute(stmt)
            return [r for r in result.scalars().all()]

    async def add_member(self, member: Member) -> list[UUID]:
        async with self._commit_lock:
            async with self.session() as db:
                db.add(member)
                await db.flush()
                await db.refresh(member)
                member_id = member.id
                await db.commit()
                return member_id
