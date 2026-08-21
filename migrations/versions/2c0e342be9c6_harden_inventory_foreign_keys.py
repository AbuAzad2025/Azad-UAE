"""harden_inventory_foreign_keys

Revision ID: 2c0e342be9c6
Revises: 86afead128ce
Create Date: 2026-08-21 01:06:05.940341

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2c0e342be9c6'
down_revision = '86afead128ce'
branch_labels = None
depends_on = None


FK_CHANGES = [
    {
        "table": "product_warehouse_stock",
        "column": "product_id",
        "ref_table": "products",
        "ref_column": "id",
        "new_name": "fk_product_warehouse_stock_product_id",
    },
    {
        "table": "product_warehouse_stock",
        "column": "warehouse_id",
        "ref_table": "warehouses",
        "ref_column": "id",
        "new_name": "fk_product_warehouse_stock_warehouse_id",
    },
    {
        "table": "sale_campaigns",
        "column": "sale_id",
        "ref_table": "sales",
        "ref_column": "id",
        "new_name": "fk_sale_campaigns_sale_id",
    },
]

MISSING_INDEXES = [
    ("document_verification", "ix_document_verification_tenant_id", ["tenant_id"]),
    ("fixed_assets", "ix_fixed_assets_depreciation_account_id", ["depreciation_account_id"]),
    ("fixed_assets", "ix_fixed_assets_expense_account_id", ["expense_account_id"]),
    ("gl_account_mappings", "ix_gl_account_mappings_gl_account_id", ["gl_account_id"]),
]


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return index_name in [idx["name"] for idx in insp.get_indexes(table)]


def _find_fk_name(table: str, column: str, ref_table: str, ref_column: str) -> str | None:
    """Return the database name of the FK matching the column mapping."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if (
            fk.get("constrained_columns") == [column]
            and fk.get("referred_table") == ref_table
            and fk.get("referred_columns") == [ref_column]
        ):
            return fk["name"]
    return None


def upgrade():
    # ── 1. Convert risky CASCADE FKs to RESTRICT ────────────────────────────
    for fk in FK_CHANGES:
        table = fk["table"]
        column = fk["column"]
        if not _table_exists(table) or not _column_exists(table, column):
            continue
        existing_name = _find_fk_name(table, column, fk["ref_table"], fk["ref_column"])
        if not existing_name:
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(existing_name, type_="foreignkey")
            batch_op.create_foreign_key(
                fk["new_name"],
                fk["ref_table"],
                [column],
                [fk["ref_column"]],
                ondelete="RESTRICT",
            )

    # ── 2. Add missing FK indexes ───────────────────────────────────────────
    for table, index_name, columns in MISSING_INDEXES:
        if not _table_exists(table):
            continue
        if not all(_column_exists(table, c) for c in columns):
            continue
        if _index_exists(table, index_name):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_index(batch_op.f(index_name), columns, unique=False)


def downgrade():
    # Drop added indexes
    for table, index_name, _ in MISSING_INDEXES:
        if not _table_exists(table):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(index_name))

    # Restore CASCADE FKs (drop named RESTRICT, recreate unnamed CASCADE)
    for fk in FK_CHANGES:
        table = fk["table"]
        column = fk["column"]
        if not _table_exists(table) or not _column_exists(table, column):
            continue
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(fk["new_name"], type_="foreignkey")
            batch_op.create_foreign_key(
                None,
                fk["ref_table"],
                [column],
                [fk["ref_column"]],
                ondelete="CASCADE",
            )
