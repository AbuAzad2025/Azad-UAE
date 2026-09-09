"""payment_logs tenant_id nullable for platform-owned audit rows

The AZAD platform vault (tenant_id IS NULL) writes audit rows to
``payment_logs`` for vault unlock attempts. The legacy NOT NULL constraint
forced every log insert to set a tenant_id, which crashed with
NotNullViolation whenever the operator (a global owner with no active
tenant) tried to unlock a tenant-less vault. Tenant-scoped rows keep the
NOT NULL constraint behaviour via the application layer (see
``utils/tenant_orm.py``), which already returns ``sql_true()`` for the
platform-owner case.

Revision ID: 7f4c5e2a9011
Revises: b81e7a2c41d0
Create Date: 2026-09-08 21:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "7f4c5e2a9011"
down_revision = "b81e7a2c41d0"
branch_labels = None
depends_on = None


def _column_is_nullable(table: str, column: str) -> bool:
    from sqlalchemy import inspect

    bind = op.get_bind()
    insp = inspect(bind)
    for c in insp.get_columns(table):
        if c["name"] == column:
            return bool(c.get("nullable", True))
    return True


def upgrade():
    if not _column_is_nullable("payment_logs", "tenant_id"):
        with op.batch_alter_table("payment_logs", schema=None) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    if _column_is_nullable("payment_logs", "tenant_id"):
        with op.batch_alter_table("payment_logs", schema=None) as batch_op:
            batch_op.alter_column("tenant_id", existing_type=sa.Integer(), nullable=False)
