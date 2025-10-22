"""
User profiles table to store additional user and system data

Revision ID: 0003_user_profiles
Revises: 0002_billing_and_limits
Create Date: 2025-10-22 22:50:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_user_profiles'
down_revision = '0002_billing_and_limits'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_profiles',
        sa.Column('owner_id', sa.String(length=128), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.String(length=1024), nullable=True),
        sa.Column('preferred_cli', sa.String(length=64), nullable=True),
        sa.Column('preferred_model', sa.String(length=128), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('last_active_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_user_profiles_owner_id', 'user_profiles', ['owner_id'])


def downgrade() -> None:
    op.drop_index('ix_user_profiles_owner_id', table_name='user_profiles')
    op.drop_table('user_profiles')
