"""add username to error_audit_logs

Revision ID: 24a7043cfc9c
Revises: c916e51c2e65
Create Date: 2026-08-25 12:34:58.881894

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '24a7043cfc9c'
down_revision = 'c916e51c2e65'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    bind = op.get_bind()
    insp = inspect(bind)
    try:
        cols = [c["name"] for c in insp.get_columns(table)]
        return column in cols
    except Exception:
        return False


def upgrade():
    if not _column_exists('error_audit_logs', 'username'):
        with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('username', sa.String(length=100), nullable=True))
            batch_op.create_index(batch_op.f('ix_error_audit_logs_username'), ['username'], unique=False)


def downgrade():
    if _column_exists('error_audit_logs', 'username'):
        with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
            batch_op.drop_index(batch_op.f('ix_error_audit_logs_username'))
            batch_op.drop_column('username')
