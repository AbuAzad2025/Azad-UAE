"""ai_init_001 — add ai_memories, ai_interactions, ai_expertise tables

Revision ID: ai_init_001
Revises: store_platform_lock_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = 'ai_init_001'
down_revision = 'store_platform_lock_001'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if 'ai_memories' not in tables:
        op.create_table(
            'ai_memories',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=True),
            sa.Column('category', sa.String(length=50), nullable=False, server_default='general'),
            sa.Column('key', sa.String(length=255), nullable=False),
            sa.Column('value', sa.Text(), nullable=False),
            sa.Column('confidence', sa.Numeric(3, 2), nullable=False, server_default=sa.text('0.80')),
            sa.Column('source', sa.String(length=100), nullable=True),
            sa.Column('access_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('last_accessed', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ai_memories_tenant_id', 'ai_memories', ['tenant_id'], unique=False)
        op.create_index('ix_ai_memories_category', 'ai_memories', ['category'], unique=False)
        op.create_index('ix_ai_memories_key', 'ai_memories', ['key'], unique=False)
        op.create_index('ix_ai_memories_active', 'ai_memories', ['is_active'], unique=False)

    if 'ai_interactions' not in tables:
        op.create_table(
            'ai_interactions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('session_id', sa.String(length=100), nullable=True),
            sa.Column('query', sa.Text(), nullable=False),
            sa.Column('response', sa.Text(), nullable=True),
            sa.Column('intent', sa.String(length=100), nullable=True),
            sa.Column('was_successful', sa.Boolean(), nullable=True),
            sa.Column('response_time_ms', sa.Integer(), nullable=True),
            sa.Column('is_training_sample', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ai_interactions_tenant_id', 'ai_interactions', ['tenant_id'], unique=False)
        op.create_index('ix_ai_interactions_user_id', 'ai_interactions', ['user_id'], unique=False)
        op.create_index('ix_ai_interactions_session', 'ai_interactions', ['session_id'], unique=False)
        op.create_index('ix_ai_interactions_created', 'ai_interactions', ['created_at'], unique=False)
        op.create_index('ix_ai_interactions_training', 'ai_interactions', ['is_training_sample'], unique=False)

    if 'ai_expertise' not in tables:
        op.create_table(
            'ai_expertise',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('tenant_id', sa.Integer(), nullable=True),
            sa.Column('domain', sa.String(length=100), nullable=False),
            sa.Column('topic', sa.String(length=200), nullable=False),
            sa.Column('knowledge', sa.Text(), nullable=False),
            sa.Column('priority', sa.Integer(), nullable=False, server_default=sa.text('5')),
            sa.Column('usage_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ai_expertise_tenant_id', 'ai_expertise', ['tenant_id'], unique=False)
        op.create_index('ix_ai_expertise_domain', 'ai_expertise', ['domain'], unique=False)
        op.create_index('ix_ai_expertise_active', 'ai_expertise', ['is_active'], unique=False)


def downgrade():
    op.drop_table('ai_expertise')
    op.drop_table('ai_interactions')
    op.drop_table('ai_memories')
