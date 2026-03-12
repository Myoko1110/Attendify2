from __future__ import annotations

import os
import traceback

from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"


def main() -> None:
    url = os.getenv("DATABASE_URL") or DEFAULT_DB_URL
    print("url=", url)
    eng = create_engine(url)
    try:
        with eng.begin() as c:
            exists = c.execute(text("select to_regclass('public.alembic_version')")).scalar_one()
            print("alembic_version table:", exists)
            if exists:
                v = c.execute(text("select version_num from alembic_version")).scalar_one_or_none()
                print("version_num:", v)
    except Exception:
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
