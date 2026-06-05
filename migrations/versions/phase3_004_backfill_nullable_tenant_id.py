"""Backfill tenant_id NULLs and make columns NOT NULL

Revision ID: phase3_004
Revises: phase3_003
Create Date: 2026-06-05

Backfills missing tenant_id in legacy rows then aligns
tenant_id columns to model definitions (nullable=False).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = 'phase3_004'
down_revision = 'phase3_003'
branch_labels = None
depends_on = None


def _has_null_rows(table, col='tenant_id'):
    bind = op.get_bind()
    result = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"))
    return result.scalar() > 0


def _get_first_tenant_id():
    bind = op.get_bind()
    result = bind.execute(sa.text("SELECT id FROM tenants ORDER BY id LIMIT 1"))
    row = result.fetchone()
    return row[0] if row else None


def upgrade():
    first_tenant = _get_first_tenant_id()
    if first_tenant is None:
        # No tenants exist yet; nothing to backfill
        return

    # Backfill expense_categories
    if _has_null_rows('expense_categories'):
        op.execute(sa.text(
            f"UPDATE expense_categories SET tenant_id = {first_tenant} WHERE tenant_id IS NULL"
        ))

    # Backfill error_audit_logs
    if _has_null_rows('error_audit_logs'):
        op.execute(sa.text(
            f"UPDATE error_audit_logs SET tenant_id = {first_tenant} WHERE tenant_id IS NULL"
        ))

    # Backfill product_return_lines (if any)
    if _has_null_rows('product_return_lines'):
        op.execute(sa.text(
            f"UPDATE product_return_lines SET tenant_id = {first_tenant} WHERE tenant_id IS NULL"
        ))

    # Make columns NOT NULL where model says so
    # Only alter if the column is currently nullable
    with op.batch_alter_table('cost_centers', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=False)

    with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
        batch_op.alter_column('fingerprint', existing_type=sa.VARCHAR(length=64), nullable=False)
        batch_op.alter_column('first_seen_at', existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column('last_seen_at', existing_type=sa.DateTime(), nullable=False)

    with op.batch_alter_table('expense_categories', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=False)

    with op.batch_alter_table('fixed_assets', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=False)

    with op.batch_alter_table('product_return_lines', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=False)

    with op.batch_alter_table('product_returns', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=False)

    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=False)


def downgrade():
    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('product_returns', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('product_return_lines', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('fixed_assets', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('expense_categories', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table('error_audit_logs', schema=None) as batch_op:
        batch_op.alter_column('last_seen_at', existing_type=sa.DateTime(), nullable=True)
        batch_op.alter_column('first_seen_at', existing_type=sa.DateTime(), nullable=True)
        batch_op.alter_column('fingerprint', existing_type=sa.VARCHAR(length=64), nullable=True)

    with op.batch_alter_table('cost_centers', schema=None) as batch_op:
        batch_op.alter_column('tenant_id', existing_type=sa.INTEGER(), nullable=True)
