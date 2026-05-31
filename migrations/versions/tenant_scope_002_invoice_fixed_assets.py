"""add tenant_id to invoice_settings and fixed_assets

Revision ID: tenant_scope_002
Revises: tenant_init_001
Create Date: 2026-05-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'tenant_scope_002'
down_revision = 'tenant_init_001'
branch_labels = None
depends_on = None


def _default_tenant_id(conn):
    row = conn.execute(
        sa.text("SELECT id FROM tenants WHERE is_active = TRUE ORDER BY id ASC LIMIT 1")
    ).fetchone()
    return int(row[0]) if row and row[0] else None


def _has_column(inspector, table, column):
    return column in {c.get("name") for c in inspector.get_columns(table)}


def upgrade():
    conn = op.get_bind()
    tenant_id = _default_tenant_id(conn)
    inspector = sa.inspect(conn)

    if not _has_column(inspector, "invoice_settings", "tenant_id"):
        with op.batch_alter_table("invoice_settings", schema=None) as batch_op:
            batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_invoice_settings_tenant_id"), ["tenant_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_invoice_settings_tenant_id",
                "tenants",
                ["tenant_id"],
                ["id"],
            )
        if tenant_id is not None:
            op.execute(
                sa.text(
                    "UPDATE invoice_settings SET tenant_id = :tenant_id WHERE tenant_id IS NULL"
                ).bindparams(tenant_id=tenant_id)
            )

    inspector = sa.inspect(conn)
    if not _has_column(inspector, "fixed_assets", "tenant_id"):
        with op.batch_alter_table("fixed_assets", schema=None) as batch_op:
            batch_op.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))
            batch_op.create_index(batch_op.f("ix_fixed_assets_tenant_id"), ["tenant_id"], unique=False)
            batch_op.create_foreign_key(
                "fk_fixed_assets_tenant_id",
                "tenants",
                ["tenant_id"],
                ["id"],
            )

    op.execute(
        sa.text(
            "UPDATE fixed_assets SET tenant_id = ("
            "SELECT tenant_id FROM branches WHERE branches.id = fixed_assets.branch_id"
            ") WHERE tenant_id IS NULL AND branch_id IS NOT NULL"
        )
    )
    if tenant_id is not None:
        op.execute(
            sa.text(
                "UPDATE fixed_assets SET tenant_id = :tenant_id WHERE tenant_id IS NULL"
            ).bindparams(tenant_id=tenant_id)
        )

    inspector = sa.inspect(conn)
    index_names = {idx.get("name") for idx in inspector.get_indexes("fixed_assets")}
    if "ix_fixed_assets_asset_number" in index_names:
        with op.batch_alter_table("fixed_assets", schema=None) as batch_op:
            batch_op.drop_index("ix_fixed_assets_asset_number")
            batch_op.create_index("ix_fixed_assets_asset_number", ["asset_number"], unique=False)

    uq_names = {u.get("name") for u in inspector.get_unique_constraints("fixed_assets")}
    if "uq_fixed_assets_tenant_asset_number" not in uq_names:
        with op.batch_alter_table("fixed_assets", schema=None) as batch_op:
            batch_op.create_unique_constraint(
                "uq_fixed_assets_tenant_asset_number",
                ["tenant_id", "asset_number"],
            )


def downgrade():
    with op.batch_alter_table("fixed_assets", schema=None) as batch_op:
        batch_op.drop_constraint("uq_fixed_assets_tenant_asset_number", type_="unique")
        batch_op.drop_constraint("fk_fixed_assets_tenant_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_fixed_assets_tenant_id"))
        batch_op.drop_column("tenant_id")

    with op.batch_alter_table("invoice_settings", schema=None) as batch_op:
        batch_op.drop_constraint("fk_invoice_settings_tenant_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_invoice_settings_tenant_id"))
        batch_op.drop_column("tenant_id")
