"""add target_type to attendance_rates unique constraint

Revision ID: g5f6g7h8i9j0
Revises: 6085dc70f5b0
Create Date: 2026-05-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g5f6g7h8i9j0'
down_revision = '6085dc70f5b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 既存の制約を削除
    op.drop_constraint('attendance_rates_target_id_month_actual_key', 'attendance_rates', type_='unique')

    # 新しい制約を追加（target_type 含む）
    op.create_unique_constraint('attendance_rates_target_type_target_id_month_actual_key',
                                'attendance_rates',
                                ['target_type', 'target_id', 'month', 'actual'])


def downgrade() -> None:
    # 新しい制約を削除
    op.drop_constraint('attendance_rates_target_type_target_id_month_actual_key', 'attendance_rates', type_='unique')

    # 古い制約に戻す
    op.create_unique_constraint('attendance_rates_target_id_month_actual_key',
                                'attendance_rates',
                                ['target_id', 'month', 'actual'])


