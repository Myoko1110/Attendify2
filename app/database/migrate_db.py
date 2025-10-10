from pathlib import Path

from sqlalchemy import URL, create_engine

from app.database import Base

DB_URL = URL.create(
    drivername="mysql+pymysql",
    database=Path("./attendify.db").as_posix(),
    query=dict(
        charset="utf8mb4",
    ),
)
engine = create_engine(DB_URL, echo=True)


def migrate_database():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    migrate_database()
