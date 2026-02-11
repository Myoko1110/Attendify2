# sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import text

SQLITE_URL = "sqlite:///./attendify.db"

# postgres
POSTGRES_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sqlite_engine = create_engine(
    SQLITE_URL, connect_args={"check_same_thread": False}
)

postgres_engine = create_engine(POSTGRES_URL)

SQLiteSession = sessionmaker(bind=sqlite_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

from app.database.models import *

Base.metadata.create_all(bind=postgres_engine)

from sqlalchemy.orm import Session as ORMSession
from sqlalchemy import MetaData


def migrate(model):
    sqlite_db: ORMSession = SQLiteSession()
    pg_db: ORMSession = PostgresSession()

    pg_db.execute(text("SET session_replication_role = replica;"))

    try:
        # reflect target table on Postgres to detect columns that exist in the DB
        meta = MetaData()
        meta.reflect(bind=postgres_engine, only=[model.__tablename__])
        target_table = meta.tables.get(model.__tablename__)

        # find columns that exist in the Postgres table but not in the current model
        model_columns = {c.name for c in model.__table__.columns}
        extra_columns = [c for c in target_table.columns if c.name not in model_columns]

        # For extra columns that are NOT NULL and have no server default, drop NOT NULL
        for col in extra_columns:
            if not col.nullable and col.server_default is None:
                print(f"[INFO] Altering table {model.__tablename__} column {col.name} to DROP NOT NULL")
                # Use quoted identifiers to be safe for mixed-case names
                pg_db.execute(text(f'ALTER TABLE "{model.__tablename__}" ALTER COLUMN "{col.name}" DROP NOT NULL;'))

        rows = sqlite_db.query(model).all()

        for row in rows:
            data = {
                c.name: getattr(row, c.name)
                for c in model.__table__.columns
            }

            # ★ add ではなく merge
            pg_db.merge(model(**data))

        pg_db.commit()

    except IntegrityError as e:
        pg_db.rollback()   # ★ 絶対必要
        print(f"[ERROR] {model.__name__}: {e}")

    finally:
        pg_db.execute(text("SET session_replication_role = origin;"))
        pg_db.commit()
        sqlite_db.close()
        pg_db.close()


for model in [
    Member,
    Group,
    MembershipStatus,

    # 中間
    MemberGroup,
    WeeklyParticipation,
    MembershipStatusPeriod,

    # 子
    Attendance,
    AttendanceRate,

    # 独立
    Schedule,
    Session,
]:
    print(model)
    migrate(model)
