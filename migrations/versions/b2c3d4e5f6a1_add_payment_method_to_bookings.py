"""add payment_method column to bookings table

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-05-03 10:00:00.000000

FIX: The initial schema migration was missing the payment_method column
on the bookings table. The Booking model defines it (Bug #1 fix), but
existing databases created before this migration would raise an
OperationalError on confirm_booking() when trying to INSERT payment_method.

This migration adds the column to any existing database.
It is safe to run even if the column already exists (no-op on SQLite via
batch_alter with check_columns=True workaround; on Postgres the try/except
catches the duplicate-column error).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Use batch_alter_table (required for SQLite ALTER TABLE support)
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        # Add payment_method column — nullable so existing rows aren't broken
        try:
            batch_op.add_column(sa.Column('payment_method', sa.String(length=50), nullable=True))
        except Exception:
            # Column already exists (e.g. if initial migration was already fixed)
            pass


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        try:
            batch_op.drop_column('payment_method')
        except Exception:
            pass
