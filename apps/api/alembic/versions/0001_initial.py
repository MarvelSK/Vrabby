"""
Initial schema for Supabase/Postgres

Revision ID: 0001_initial
Revises: 
Create Date: 2025-10-21 16:17:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # projects
    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, default='idle'),
        sa.Column('preview_url', sa.String(length=255), nullable=True),
        sa.Column('preview_port', sa.Integer(), nullable=True),
        sa.Column('repo_path', sa.String(length=1024), nullable=True),
        sa.Column('initial_prompt', sa.Text(), nullable=True),
        sa.Column('template_type', sa.String(length=64), nullable=True),
        sa.Column('owner_id', sa.String(length=128), nullable=True),
        sa.Column('active_claude_session_id', sa.String(length=128), nullable=True),
        sa.Column('active_cursor_session_id', sa.String(length=128), nullable=True),
        sa.Column('preferred_cli', sa.String(length=32), nullable=False),
        sa.Column('selected_model', sa.String(length=64), nullable=True),
        sa.Column('fallback_enabled', sa.Boolean(), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_active_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_projects_status', 'projects', ['status'])
    op.create_index('ix_projects_owner_id', 'projects', ['owner_id'])
    op.create_index('ix_projects_created_at', 'projects', ['created_at'])

    # sessions
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('claude_session_id', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('cli_type', sa.String(length=32), nullable=False),
        sa.Column('transcript_path', sa.String(length=512), nullable=True),
        sa.Column('transcript_format', sa.String(length=32), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('total_messages', sa.Integer(), nullable=False),
        sa.Column('total_tools_used', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('total_cost_usd', sa.Numeric(10, 6), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_sessions_project_id', 'sessions', ['project_id'])
    op.create_index('ix_sessions_claude_session_id', 'sessions', ['claude_session_id'])

    # messages
    op.create_table(
        'messages',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('message_type', sa.String(length=32), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('parent_message_id', sa.String(length=64), sa.ForeignKey('messages.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('conversation_id', sa.String(length=64), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Numeric(10, 6), nullable=True),
        sa.Column('commit_sha', sa.String(length=64), nullable=True),
        sa.Column('cli_source', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_messages_project_id', 'messages', ['project_id'])
    op.create_index('ix_messages_session_id', 'messages', ['session_id'])
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_cli_source', 'messages', ['cli_source'])

    # commits
    op.create_table(
        'commits',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('commit_sha', sa.String(length=64), nullable=False),
        sa.Column('parent_sha', sa.String(length=64), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('author_type', sa.String(length=32), nullable=True),
        sa.Column('author_name', sa.String(length=128), nullable=True),
        sa.Column('author_email', sa.String(length=255), nullable=True),
        sa.Column('files_changed', sa.JSON(), nullable=True),
        sa.Column('stats', sa.JSON(), nullable=True),
        sa.Column('diff', sa.Text(), nullable=True),
        sa.Column('committed_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_commits_project_id', 'commits', ['project_id'])
    op.create_index('ix_commits_commit_sha', 'commits', ['commit_sha'], unique=True)
    op.create_index('ix_commits_committed_at', 'commits', ['committed_at'])

    # env_vars
    op.create_table(
        'env_vars',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key', sa.String(length=128), nullable=False),
        sa.Column('value_encrypted', sa.Text(), nullable=False),
        sa.Column('scope', sa.String(length=32), nullable=False),
        sa.Column('var_type', sa.String(length=32), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('project_id', 'key', 'scope', name='unique_project_var'),
    )
    op.create_index('ix_env_vars_project_id', 'env_vars', ['project_id'])

    # project_service_connections
    op.create_table(
        'project_service_connections',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('service_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_project_services', 'project_service_connections', ['project_id', 'provider'])
    op.create_index('idx_provider_status', 'project_service_connections', ['provider', 'status'])

    # tools_usage
    op.create_table(
        'tools_usage',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', sa.String(length=64), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tool_name', sa.String(length=64), nullable=False),
        sa.Column('tool_action', sa.String(length=32), nullable=True),
        sa.Column('input_data', sa.JSON(), nullable=True),
        sa.Column('output_data', sa.JSON(), nullable=True),
        sa.Column('files_affected', sa.JSON(), nullable=True),
        sa.Column('lines_added', sa.Integer(), nullable=True),
        sa.Column('lines_removed', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('is_error', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_tools_usage_session_id', 'tools_usage', ['session_id'])
    op.create_index('ix_tools_usage_project_id', 'tools_usage', ['project_id'])
    op.create_index('ix_tools_usage_tool_name', 'tools_usage', ['tool_name'])

    # service_tokens
    op.create_table(
        'service_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_service_tokens_provider', 'service_tokens', ['provider'])

    # user_requests
    op.create_table(
        'user_requests',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('project_id', sa.String(length=64), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_message_id', sa.String(length=64), sa.ForeignKey('messages.id', ondelete='CASCADE'),
                  nullable=False, unique=True),
        sa.Column('session_id', sa.String(length=64), sa.ForeignKey('sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('request_type', sa.String(length=16), nullable=False),
        sa.Column('is_completed', sa.Boolean(), nullable=False),
        sa.Column('is_successful', sa.Boolean(), nullable=True),
        sa.Column('result_metadata', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('cli_type_used', sa.String(length=32), nullable=True),
        sa.Column('model_used', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_user_requests_project_id', 'user_requests', ['project_id'])
    op.create_index('ix_user_requests_user_message_id', 'user_requests', ['user_message_id'])
    op.create_index('ix_user_requests_session_id', 'user_requests', ['session_id'])
    op.create_index('ix_user_requests_is_completed', 'user_requests', ['is_completed'])


def downgrade() -> None:
    op.drop_index('ix_user_requests_is_completed', table_name='user_requests')
    op.drop_index('ix_user_requests_session_id', table_name='user_requests')
    op.drop_index('ix_user_requests_user_message_id', table_name='user_requests')
    op.drop_index('ix_user_requests_project_id', table_name='user_requests')
    op.drop_table('user_requests')

    op.drop_index('ix_service_tokens_provider', table_name='service_tokens')
    op.drop_table('service_tokens')

    op.drop_index('ix_tools_usage_tool_name', table_name='tools_usage')
    op.drop_index('ix_tools_usage_project_id', table_name='tools_usage')
    op.drop_index('ix_tools_usage_session_id', table_name='tools_usage')
    op.drop_table('tools_usage')

    op.drop_index('idx_provider_status', table_name='project_service_connections')
    op.drop_index('idx_project_services', table_name='project_service_connections')
    op.drop_table('project_service_connections')

    op.drop_index('ix_env_vars_project_id', table_name='env_vars')
    op.drop_table('env_vars')

    op.drop_index('ix_commits_committed_at', table_name='commits')
    op.drop_index('ix_commits_commit_sha', table_name='commits')
    op.drop_index('ix_commits_project_id', table_name='commits')
    op.drop_table('commits')

    op.drop_index('ix_messages_cli_source', table_name='messages')
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_index('ix_messages_session_id', table_name='messages')
    op.drop_index('ix_messages_project_id', table_name='messages')
    op.drop_table('messages')

    op.drop_index('ix_sessions_claude_session_id', table_name='sessions')
    op.drop_index('ix_sessions_project_id', table_name='sessions')
    op.drop_table('sessions')

    op.drop_index('ix_projects_created_at', table_name='projects')
    op.drop_index('ix_projects_owner_id', table_name='projects')
    op.drop_index('ix_projects_status', table_name='projects')
    op.drop_table('projects')
