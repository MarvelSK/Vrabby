"""
Billing: user accounts and credit transactions

Revision ID: 0002_billing_and_limits
Revises: 0001_initial
Create Date: 2025-10-21 17:20:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_billing_and_limits'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_accounts',
        sa.Column('owner_id', sa.String(length=128), primary_key=True),
        sa.Column('stripe_customer_id', sa.String(length=128), nullable=True),
        sa.Column('subscription_status', sa.String(length=32), nullable=True),
        sa.Column('plan', sa.String(length=64), nullable=True),
        sa.Column('credit_balance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_accounts_owner_id', 'user_accounts', ['owner_id'])
    op.create_index('ix_user_accounts_stripe_customer_id', 'user_accounts', ['stripe_customer_id'])

    op.create_table(
        'credit_transactions',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('owner_id', sa.String(length=128), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('tx_type', sa.String(length=16), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_credit_tx_owner_id', 'credit_transactions', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_credit_tx_owner_id', table_name='credit_transactions')
    op.drop_table('credit_transactions')

    op.drop_index('ix_user_accounts_stripe_customer_id', table_name='user_accounts')
    op.drop_index('ix_user_accounts_owner_id', table_name='user_accounts')
    op.drop_table('user_accounts')
