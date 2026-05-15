"""add wallet_balance column to c_user table

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-05-13 10:00:00.000000

Adds a wallet_balance column to the c_user table to support:
  - Crediting refund amounts when a booking is cancelled
  - Debiting wallet balance when a user pays with 'WALLET' method
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a1b2'
down_revision = 'b2c3d4e5f6a1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('c_user', schema=None) as batch_op:
        try:
            batch_op.add_column(
                sa.Column(
                    'wallet_balance',
                    sa.Float(),
                    nullable=False,
                    server_default='0',
                )
            )
        except Exception:
            # Column may already exist on a re-run — skip safely
            pass


def downgrade():
    with op.batch_alter_table('c_user', schema=None) as batch_op:
        try:
            batch_op.drop_column('wallet_balance')
        except Exception:
            pass