"""
Performance indexes for high-traffic queries

Revision ID: 0005_perf_indexes
Revises: 0004_content_tables
Create Date: 2025-10-23 00:35:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005_perf_indexes'
down_revision = '0004_content_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # messages: common filters for timelines
    op.create_index('ix_messages_project_created', 'messages', ['project_id', 'created_at'])
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'])

    # projects: frequent owner timeline queries
    op.create_index('ix_projects_owner_created', 'projects', ['owner_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_projects_owner_created', table_name='projects')
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_index('ix_messages_project_created', table_name='messages')
