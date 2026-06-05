"""Drop orphaned AI tables

Revision ID: phase3_006
Revises: phase3_005
Create Date: 2026-06-05

Removes ai_interactions, ai_expertise, ai_memories tables which:
- No longer have corresponding model definitions
- Are not referenced by any application code
- Have been backed up to migrations/ai_tables_backup_2026-06-05.json
"""
from alembic import op
from sqlalchemy import inspect

revision = 'phase3_006'
down_revision = 'phase3_005'
branch_labels = None
depends_on = None


def _table_exists(name):
    return name in inspect(op.get_bind()).get_table_names()


def upgrade():
    if _table_exists('ai_memories'):
        op.drop_table('ai_memories')
    if _table_exists('ai_expertise'):
        op.drop_table('ai_expertise')
    if _table_exists('ai_interactions'):
        op.drop_table('ai_interactions')


def downgrade():
    # Tables can only be restored from the JSON backup manually.
    # This migration is intentionally one-way for schema cleanup.
    pass
