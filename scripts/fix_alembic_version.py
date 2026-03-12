from __future__ import annotations

import os

from sqlalchemy import create_engine, text

DEFAULT_DB_URL = "postgresql+psycopg2://postgres:myon1110@localhost:5432/attendify"


def main() -> None:
    """Danger: reset alembic_version for dev DB.

    - Drops alembic_version row(s)
    - Sets revision to base (no revision)

    Use together with `alembic upgrade head`.
    """

    url = os.getenv("DATABASE_URL") or DEFAULT_DB_URL
    eng = create_engine(url)
    with eng.begin() as c:
        exists = c.execute(text("select to_regclass('public.alembic_version')")).scalar_one()
        if exists:
            c.execute(text("delete from alembic_version"))
        else:
            c.execute(text("create table alembic_version (version_num varchar(32) not null)"))


if __name__ == "__main__":
    main()
