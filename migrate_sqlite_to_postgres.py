from sqlalchemy import create_engine, MetaData, event
from sqlalchemy.orm import sessionmaker, Session as ORMSession
from sqlalchemy.sql.expression import text
from sqlalchemy.exc import SQLAlchemyError
import datetime

SQLITE_URL = "sqlite:///./attendify.db"
POSTGRES_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"

# engines
sqlite_engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
postgres_engine = create_engine(POSTGRES_URL)

# Ensure client encoding on new DBAPI connections
@event.listens_for(postgres_engine, "connect")
def _set_client_encoding(dbapi_connection, connection_record):
    try:
        # psycopg2 connection has set_client_encoding
        dbapi_connection.set_client_encoding('UTF8')
    except Exception:
        # best-effort; ignore if not available
        pass

SQLiteSession = sessionmaker(bind=sqlite_engine)
PostgresSession = sessionmaker(bind=postgres_engine)

from app.database.models import *  # noqa: E402

Base.metadata.create_all(bind=postgres_engine)

def normalize_value(v):
    """bytes/bytearray を UTF-8 にデコードし、日付型はそのまま返す。"""
    if v is None:
        return None
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode('utf-8')
        except Exception:
            return v.decode('utf-8', errors='replace')
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v
    # other types (int, float, str, bool, etc.)
    return v

def migrate(model):
    sqlite_db: ORMSession = SQLiteSession()
    pg_db: ORMSession = PostgresSession()

    # set replication role to replica (best-effort)
    try:
        pg_db.execute(text("SET session_replication_role = replica;"))
        pg_db.commit()
    except Exception:
        try:
            pg_db.rollback()
        except Exception:
            pass

    try:
        meta = MetaData()
        meta.reflect(bind=postgres_engine, only=[model.__tablename__])
        target_table = meta.tables.get(model.__tablename__)

        model_columns = {c.name for c in model.__table__.columns}
        extra_columns = [c for c in target_table.columns if c.name not in model_columns]

        for col in extra_columns:
            if not col.nullable and col.server_default is None:
                print(f"[INFO] Altering table {model.__tablename__} column {col.name} to DROP NOT NULL")
                try:
                    pg_db.execute(text(f'ALTER TABLE "{model.__tablename__}" ALTER COLUMN "{col.name}" DROP NOT NULL;'))
                    pg_db.commit()
                except Exception:
                    try:
                        pg_db.rollback()
                    except Exception:
                        pass

        rows = sqlite_db.query(model).all()
        total = len(rows)
        moved = 0
        for idx, row in enumerate(rows, start=1):
            data = {}
            for c in model.__table__.columns:
                try:
                    data[c.name] = normalize_value(getattr(row, c.name))
                except Exception:
                    data[c.name] = None

            instance = model(**data)
            try:
                # merge/add per-row and commit to keep session clean on error
                pg_db.merge(instance)
                pg_db.commit()
                moved += 1
            except SQLAlchemyError as e:
                # rollback and continue with next row
                try:
                    pg_db.rollback()
                except Exception:
                    pass
                pk_info = {}
                try:
                    # attempt to get primary key value(s) from row
                    pk_info = {k.name: getattr(row, k.name) for k in model.__table__.primary_key}
                except Exception:
                    pass
                print(f"[ERROR] {model.__name__} row {idx}/{total} pk={pk_info}: {e}")
            except Exception as e:
                try:
                    pg_db.rollback()
                except Exception:
                    pass
                print(f"[ERROR] {model.__name__} unexpected error on row {idx}/{total}: {e}")

        print(f"[INFO] {model.__name__}: migrated {moved}/{total}")

    except Exception as e:
        try:
            pg_db.rollback()
        except Exception:
            pass
        print(f"[ERROR] {model.__name__} reflect/prepare failed: {e}")

    finally:
        # ensure transaction cleared then restore role
        try:
            pg_db.rollback()
        except Exception:
            pass

        try:
            pg_db.execute(text("SET session_replication_role = origin;"))
            pg_db.commit()
        except Exception:
            try:
                pg_db.rollback()
            except Exception:
                pass

        sqlite_db.close()
        pg_db.close()


if __name__ == "__main__":
    for model in [
        Member,
        Group,
        MembershipStatus,
        MemberGroup,
        WeeklyParticipation,
        MembershipStatusPeriod,
        Attendance,
        AttendanceRate,
        Schedule,
        Session,
    ]:
        migrate(model)
