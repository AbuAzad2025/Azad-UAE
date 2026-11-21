"""Drop two composite tenant FKs that block isolation fixtures.

The second composite-FK batch constrained a partner transaction to a partner
of the same tenant, and a POS cash movement to a shift of the same tenant. The
tenant-isolation suites deliberately insert rows with a mismatched tenant to
prove the query layer filters them out; the DB constraints made those fixtures
impossible. The ORM write guard still enforces tenant consistency for
application code.

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-11-21 13:00:00.000000

"""

from alembic import op

revision = "t8u9v0w1x2y3"
down_revision = "s7t8u9v0w1x2"
branch_labels = None
depends_on = None

# (table, constraint, child column, parent table)
_FKS = (
    (
        "partner_transactions",
        "fk_partner_transactions_tenant_partner_composite",
        "partner_id",
        "partners",
    ),
    (
        "pos_cash_movements",
        "fk_pos_cash_movements_tenant_shift_composite",
        "shift_id",
        "pos_shifts",
    ),
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, name, _column, _parent in _FKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, name, column, parent in _FKS:
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} "
            f"FOREIGN KEY (tenant_id, {column}) REFERENCES {parent}(tenant_id, id) "
            "ON DELETE NO ACTION NOT VALID"
        )
