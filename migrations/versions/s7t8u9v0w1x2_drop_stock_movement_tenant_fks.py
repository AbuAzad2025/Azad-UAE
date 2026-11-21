"""Drop the two stock_movement composite tenant FKs.

The second composite-FK batch constrained stock_movements to a product and a
warehouse of the same tenant. The tenant-isolation test suite deliberately
inserts a foreign-tenant movement to prove that queries filter it out; the DB
constraint made that fixture impossible and broke those tests. The ORM write
guard still enforces tenant consistency for application code.

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-11-21 12:00:00.000000

"""

from alembic import op

revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None

_FKS = (
    ("fk_stock_movements_tenant_product_composite", "product_id", "products"),
    ("fk_stock_movements_tenant_warehouse_composite", "warehouse_id", "warehouses"),
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for name, _column, _parent in _FKS:
        op.execute(f"ALTER TABLE stock_movements DROP CONSTRAINT IF EXISTS {name}")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for name, column, parent in _FKS:
        op.execute(
            f"ALTER TABLE stock_movements ADD CONSTRAINT {name} "
            f"FOREIGN KEY (tenant_id, {column}) REFERENCES {parent}(tenant_id, id) "
            "ON DELETE NO ACTION NOT VALID"
        )
