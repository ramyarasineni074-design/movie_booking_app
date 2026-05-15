"""add seat_locks table for temporary seat locking

Revision ID: a1b2c3d4e5f6
Revises: 8e7b7f0ea28f
Create Date: 2026-05-02 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision     = 'a1b2c3d4e5f6'
down_revision = '8e7b7f0ea28f'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'seat_locks',
        sa.Column('lock_id',     sa.String(300), primary_key=True),
        sa.Column('show_id',     sa.String(300), sa.ForeignKey('shows.show_id'), nullable=False),
        sa.Column('seat_number', sa.String(200), nullable=False),
        sa.Column('user_id',     sa.String(300), nullable=False),
        sa.Column('locked_at',   sa.DateTime,    nullable=False),
        sa.Column('expires_at',  sa.DateTime,    nullable=False),
        sa.UniqueConstraint('show_id', 'seat_number', name='uq_show_seat_lock'),
    )
    op.create_index('idx_lock_show',   'seat_locks', ['show_id'])
    op.create_index('idx_lock_seat',   'seat_locks', ['seat_number'])
    op.create_index('idx_lock_user',   'seat_locks', ['user_id'])
    op.create_index('idx_lock_expiry', 'seat_locks', ['expires_at'])


def downgrade():
    op.drop_index('idx_lock_expiry', table_name='seat_locks')
    op.drop_index('idx_lock_user',   table_name='seat_locks')
    op.drop_index('idx_lock_seat',   table_name='seat_locks')
    op.drop_index('idx_lock_show',   table_name='seat_locks')
    op.drop_table('seat_locks')
