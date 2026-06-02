"""store_platform_lock_001 — platform-owner force-OFF lock for tenant stores

Adds tenant_stores.platform_disabled so the platform owner can hard-disable a
tenant store regardless of the tenant's own is_enabled flag.

Revision ID: store_platform_lock_001
Revises: nasrallah_ps_local_001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = 'store_platform_lock_001'
down_revision = 'nasrallah_ps_local_001'
branch_labels = None
depends_on = None


def _has_column(insp, table, column):
    try:
        return column in {c['name'] for c in insp.get_columns(table)}
    except Exception:
        return False


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if 'tenant_stores' not in tables:
        return
    if _has_column(insp, 'tenant_stores', 'platform_disabled'):
        return
    with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'platform_disabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if 'tenant_stores' not in tables:
        return
    if not _has_column(insp, 'tenant_stores', 'platform_disabled'):
        return
    with op.batch_alter_table('tenant_stores', schema=None) as batch_op:
        batch_op.drop_column('platform_disabled')
