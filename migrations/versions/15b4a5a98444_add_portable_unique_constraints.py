"""add_portable_unique_constraints

Revision ID: 15b4a5a98444
Revises: 2c0e342be9c6
Create Date: 2026-08-21 01:06:59.782223

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "15b4a5a98444"
down_revision = "2c0e342be9c6"
branch_labels = None
depends_on = None


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


def _deduplicate_column(table: str, column: str):
    """Set empty strings to NULL and append -dup-<id> to duplicate values within tenant."""
    if not _table_exists(table) or not _column_exists(table, column):
        return

    # Normalize empty strings to NULL
    op.execute(sa.text(f"UPDATE {table} SET {column} = NULL WHERE {column} = '' OR TRIM({column}) = ''"))

    # Deduplicate using Python for portability (PG + SQLite)
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, tenant_id, {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY id")
    ).fetchall()

    seen: dict[tuple, int] = {}
    duplicates = []
    for row in rows:
        key = (row.tenant_id, row._mapping[column])
        if key in seen:
            duplicates.append((row.id, key))
        else:
            seen[key] = row.id

    for row_id, (_tenant_id, value) in duplicates:
        new_value = f"{value}-dup-{row_id}"[:200]  # cap at 200 chars
        op.execute(sa.text(f"UPDATE {table} SET {column} = :val WHERE id = :id").bindparams(val=new_value, id=row_id))


def _drop_index_if_exists(table: str, index_name: str):
    if _index_exists(table, index_name):
        op.drop_index(index_name, table_name=table)


def upgrade():
    # ── 1. Products SKU/Barcode: clean, dedupe, replace partial unique ─────
    if _table_exists("products"):
        _deduplicate_column("products", "sku")
        _deduplicate_column("products", "barcode")

        # Drop old partial unique indexes (PostgreSQL-only) and any single-column indexes
        _drop_index_if_exists("products", "uq_products_tenant_sku")
        _drop_index_if_exists("products", "uq_products_tenant_barcode")
        _drop_index_if_exists("products", "ix_products_sku")
        _drop_index_if_exists("products", "ix_products_barcode")

        with op.batch_alter_table("products", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_products_tenant_sku", ["tenant_id", "sku"])
            batch_op.create_unique_constraint("uq_products_tenant_barcode", ["tenant_id", "barcode"])

    # ── 2. Shop variant SKU uniqueness ──────────────────────────────────────
    if _table_exists("shop_product_variants") and _column_exists("shop_product_variants", "sku"):
        _deduplicate_column("shop_product_variants", "sku")
        _drop_index_if_exists("shop_product_variants", "ix_shop_product_variants_sku")
        with op.batch_alter_table("shop_product_variants", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_shop_product_variants_tenant_sku", ["tenant_id", "sku"])

    # ── 3. Tenant-scoped contact email uniqueness ───────────────────────────
    if _table_exists("customers") and _column_exists("customers", "email"):
        _deduplicate_column("customers", "email")
        _drop_index_if_exists("customers", "ix_customers_email")
        with op.batch_alter_table("customers", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_customers_tenant_email", ["tenant_id", "email"])

    if _table_exists("suppliers") and _column_exists("suppliers", "email"):
        _deduplicate_column("suppliers", "email")
        _drop_index_if_exists("suppliers", "ix_suppliers_email")
        with op.batch_alter_table("suppliers", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_suppliers_tenant_email", ["tenant_id", "email"])

    # ── 4. Card payment transaction_id tenant-scoped ────────────────────────
    if _table_exists("card_payments") and _column_exists("card_payments", "transaction_id"):
        # Deduplicate transaction_id within tenant, preserving NULLs
        _deduplicate_column("card_payments", "transaction_id")
        _drop_index_if_exists("card_payments", "ix_card_payments_transaction_id")
        with op.batch_alter_table("card_payments", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_card_payments_tenant_transaction", ["tenant_id", "transaction_id"])


def downgrade():
    # ── Restore card_payments global unique ─────────────────────────────────
    if _table_exists("card_payments"):
        with op.batch_alter_table("card_payments", schema=None) as batch_op:
            batch_op.drop_constraint("uq_card_payments_tenant_transaction", type_="unique")
            batch_op.create_unique_constraint(None, ["transaction_id"])

    # ── Restore suppliers/customer tenant-scoped email unique ───────────────
    if _table_exists("suppliers"):
        with op.batch_alter_table("suppliers", schema=None) as batch_op:
            batch_op.drop_constraint("uq_suppliers_tenant_email", type_="unique")
    if _table_exists("customers"):
        with op.batch_alter_table("customers", schema=None) as batch_op:
            batch_op.drop_constraint("uq_customers_tenant_email", type_="unique")

    # ── Restore shop variant SKU ────────────────────────────────────────────
    if _table_exists("shop_product_variants"):
        with op.batch_alter_table("shop_product_variants", schema=None) as batch_op:
            batch_op.drop_constraint("uq_shop_product_variants_tenant_sku", type_="unique")

    # ── Restore products single-column indexes ──────────────────────────────
    if _table_exists("products"):
        with op.batch_alter_table("products", schema=None) as batch_op:
            batch_op.drop_constraint("uq_products_tenant_sku", type_="unique")
            batch_op.drop_constraint("uq_products_tenant_barcode", type_="unique")
            batch_op.create_index(batch_op.f("ix_products_sku"), ["sku"], unique=False)
            batch_op.create_index(batch_op.f("ix_products_barcode"), ["barcode"], unique=False)
