from pathlib import Path

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.database import models

ASYNC_DB_URL = URL.create(
    drivername="sqlite+aiosqlite",
    database=Path("./attendify.db").as_posix(),
    query=dict(
        charset="utf8mb4",
    ),
)

async_engine = create_async_engine(ASYNC_DB_URL, echo=True)
async_session = async_sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)

Base = declarative_base()


async def get_db():
    async with async_session() as session:
        yield session
