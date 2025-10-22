"""
Content tables for Blog, FAQ, and Pricing

Revision ID: 0004_content_tables
Revises: 0003_user_profiles
Create Date: 2025-10-22 23:20:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_content_tables'
down_revision = '0003_user_profiles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # blogs
    op.create_table(
        'blogs',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('published', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )
    op.create_index('ix_blogs_slug', 'blogs', ['slug'], unique=True)
    op.create_index('ix_blogs_created_at', 'blogs', ['created_at'])

    # faq_items
    op.create_table(
        'faq_items',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('published', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )
    op.create_index('ix_faq_items_order', 'faq_items', ['order'])

    # pricing_plans
    op.create_table(
        'pricing_plans',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('price_eur', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('credits', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('blurb', sa.Text(), nullable=True),
        sa.Column('stripe_price_id', sa.String(length=255), nullable=True),
        sa.Column('is_most_popular', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('sort', sa.Integer(), server_default='0', nullable=False),
        sa.Column('published', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )
    op.create_index('ix_pricing_plans_slug', 'pricing_plans', ['slug'], unique=True)
    op.create_index('ix_pricing_plans_sort', 'pricing_plans', ['sort'])

    # pricing_features
    op.create_table(
        'pricing_features',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('plan_id', sa.String(length=64), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tag', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['pricing_plans.id'], name='fk_pricing_features_plan'),
    )
    op.create_index('ix_pricing_features_plan_id', 'pricing_features', ['plan_id'])


def downgrade() -> None:
    op.drop_index('ix_pricing_features_plan_id', table_name='pricing_features')
    op.drop_table('pricing_features')

    op.drop_index('ix_pricing_plans_sort', table_name='pricing_plans')
    op.drop_index('ix_pricing_plans_slug', table_name='pricing_plans')
    op.drop_table('pricing_plans')

    op.drop_index('ix_faq_items_order', table_name='faq_items')
    op.drop_table('faq_items')

    op.drop_index('ix_blogs_created_at', table_name='blogs')
    op.drop_index('ix_blogs_slug', table_name='blogs')
    op.drop_table('blogs')
