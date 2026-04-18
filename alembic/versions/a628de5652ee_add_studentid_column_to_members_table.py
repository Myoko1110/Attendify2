"""add studentid column to members table

Revision ID: a628de5652ee
Revises: f1d01bbe12e1
Create Date: 2026-03-26 22:09:28.071381

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'a628de5652ee'
down_revision = 'f1d01bbe12e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. studentidカラムを追加
    op.add_column('members', sa.Column('studentid', sa.Integer(), nullable=True))
    op.create_unique_constraint('uq_members_studentid', 'members', ['studentid'])

    # 2. 既存のemailから上8桁を抽出してstudentidに代入
    # emailがnullでない、かつ空でないものを対象とする
    # また、上8桁が数字であるもののみを対象とする
    connection = op.get_bind()
    # SQLでの処理（SQLiteとPostgreSQLの両方に対応を考慮）
    # substr(email, 1, 8) を使って最初の8文字を取得し、キャストする
    # emailの形式は通常 '20210001@example.com' のようなものを想定
    
    # SQLiteでは GLOB で正規表現に近いパターンマッチングが可能
    # PostgreSQLでは ~ で正規表現が可能
    if connection.dialect.name == "sqlite":
        condition = "email IS NOT NULL AND email GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*'"
    else:
        # PostgreSQL
        condition = "email IS NOT NULL AND email ~ '^[0-9]{8}'"

    connection.execute(
        sa.text(
            f"UPDATE members "
            f"SET studentid = CAST(SUBSTR(email, 1, 8) AS INTEGER) "
            f"WHERE {condition}"
        )
    )


def downgrade() -> None:
    op.drop_constraint('uq_members_studentid', 'members', type_='unique')
    op.drop_column('members', 'studentid')
