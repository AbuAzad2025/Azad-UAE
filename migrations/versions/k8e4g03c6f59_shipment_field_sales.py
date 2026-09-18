"""shipment field sales: pre-invoice van shipment with lines

Extends shipments for field-sales expedition (pre-invoice) as in UAE-Sale:
- shipment_number, from_warehouse, destination, totals, driver, lifecycle
- shipment_lines table
- sales.shipment_id FK
Keep legacy sale/purchase_return polymorphic columns nullable for backward compat.
"""

import sqlalchemy as sa
from alembic import op

revision = "k8e4g03c6f59"
down_revision = "f4a9c2e71b05"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    has_shipments = inspector.has_table("shipments")
    if not has_shipments:
        # Fresh DB (no shipments yet) — create full table as per current model
        op.create_table(
            "shipments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_type", sa.String(length=20), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "purchase_return_id",
                sa.Integer(),
                sa.ForeignKey("purchase_returns.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("shipment_number", sa.String(length=50), nullable=True, unique=True),
            sa.Column(
                "from_warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
            ),
            sa.Column(
                "destination_warehouse_id",
                sa.Integer(),
                sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("destination_name", sa.String(length=200), nullable=True),
            sa.Column("destination_type", sa.String(length=20), nullable=False, server_default="site"),
            sa.Column("total_value", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0.000"),
            sa.Column("total_quantity", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0.000"),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("carrier_name", sa.String(length=100), nullable=True),
            sa.Column("tracking_number", sa.String(length=100), nullable=True),
            sa.Column("tracking_url", sa.String(length=500), nullable=True),
            sa.Column("shipping_cost", sa.Numeric(precision=15, scale=3), nullable=True, server_default="0"),
            sa.Column("customs_duty", sa.Numeric(precision=15, scale=3), nullable=True, server_default="0"),
            sa.Column("insurance", sa.Numeric(precision=15, scale=3), nullable=True, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=True, server_default="pending"),
            sa.Column("estimated_delivery", sa.DateTime(timezone=True), nullable=True),
            sa.Column("actual_delivery", sa.DateTime(timezone=True), nullable=True),
            sa.Column("recipient_name", sa.String(length=200), nullable=True),
            sa.Column("recipient_phone", sa.String(length=50), nullable=True),
            sa.Column("recipient_address", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Index("ix_shipments_tenant_status", "tenant_id", "status"),
            sa.Index("ix_shipments_warehouse", "from_warehouse_id"),
            sa.Index("ix_shipments_destination", "destination_warehouse_id"),
            sa.Index("ix_shipment_source", "tenant_id", "source_type", "source_id"),
        )
    else:
        with op.batch_alter_table("shipments") as batch:
            batch.add_column(sa.Column("shipment_number", sa.String(length=50), nullable=True))
            batch.add_column(sa.Column("from_warehouse_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("destination_warehouse_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("destination_name", sa.String(length=200), nullable=True))
            batch.add_column(sa.Column("destination_type", sa.String(length=20), nullable=True, server_default="site"))
            batch.add_column(
                sa.Column("total_value", sa.Numeric(precision=15, scale=3), nullable=True, server_default="0.000")
            )
            batch.add_column(
                sa.Column("total_quantity", sa.Numeric(precision=15, scale=3), nullable=True, server_default="0.000")
            )
            batch.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("assigned_to_id", sa.Integer(), nullable=True))
            batch.add_column(sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True))
            batch.add_column(sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True))
            batch.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
            batch.add_column(sa.Column("notes", sa.Text(), nullable=True))
            batch.create_index("ix_shipments_tenant_status", ["tenant_id", "status"])
            batch.create_index("ix_shipments_warehouse", ["from_warehouse_id"])
            batch.create_index("ix_shipments_destination", ["destination_warehouse_id"])
            batch.create_foreign_key(
                "fk_shipments_from_warehouse", "warehouses", ["from_warehouse_id"], ["id"], ondelete="RESTRICT"
            )
            batch.create_foreign_key(
                "fk_shipments_dest_warehouse", "warehouses", ["destination_warehouse_id"], ["id"], ondelete="SET NULL"
            )
            batch.create_foreign_key("fk_shipments_created_by", "users", ["created_by_id"], ["id"], ondelete="SET NULL")
            batch.create_foreign_key(
                "fk_shipments_assigned_to", "users", ["assigned_to_id"], ["id"], ondelete="SET NULL"
            )
            batch.create_unique_constraint("uq_shipments_shipment_number", ["shipment_number"])

    # sales — add shipment_id (if not exists)
    sales_cols = [c["name"] for c in inspector.get_columns("sales")] if inspector.has_table("sales") else []
    if "shipment_id" not in sales_cols:
        with op.batch_alter_table("sales") as batch:
            batch.add_column(sa.Column("shipment_id", sa.Integer(), nullable=True))
            batch.create_index("ix_sales_shipment_id", ["shipment_id"])
            batch.create_foreign_key("fk_sales_shipment", "shipments", ["shipment_id"], ["id"], ondelete="SET NULL")

    # shipment_lines
    if not inspector.has_table("shipment_lines"):
        op.create_table(
            "shipment_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "shipment_id",
                sa.Integer(),
                sa.ForeignKey("shipments.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            sa.Column("quantity", sa.Numeric(precision=15, scale=3), nullable=False),
            sa.Column("quantity_invoiced", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0.000"),
            sa.Column("unit_cost", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0.000"),
            sa.Column("unit_price", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0.000"),
            sa.Column("line_total", sa.Numeric(precision=15, scale=3), nullable=False, server_default="0.000"),
            sa.Column("notes", sa.String(length=255), nullable=True),
            sa.Index("ix_shipment_lines_shipment", "shipment_id"),
            sa.Index("ix_shipment_lines_product", "product_id"),
            sa.CheckConstraint("quantity > 0", name="ck_shipmentline_qty_positive"),
            sa.CheckConstraint("unit_cost >= 0", name="ck_shipmentline_cost_non_negative"),
            sa.CheckConstraint("line_total >= 0", name="ck_shipmentline_total_non_negative"),
        )


def downgrade():
    op.drop_table("shipment_lines")
    with op.batch_alter_table("sales") as batch:
        batch.drop_constraint("fk_sales_shipment", type_="foreignkey")
        batch.drop_index("ix_sales_shipment_id")
        batch.drop_column("shipment_id")
    with op.batch_alter_table("shipments") as batch:
        batch.drop_constraint("uq_shipments_shipment_number", type_="unique")
        batch.drop_constraint("fk_shipments_assigned_to", type_="foreignkey")
        batch.drop_constraint("fk_shipments_created_by", type_="foreignkey")
        batch.drop_constraint("fk_shipments_dest_warehouse", type_="foreignkey")
        batch.drop_constraint("fk_shipments_from_warehouse", type_="foreignkey")
        batch.drop_index("ix_shipments_destination")
        batch.drop_index("ix_shipments_warehouse")
        batch.drop_index("ix_shipments_tenant_status")
        batch.drop_column("notes")
        batch.drop_column("closed_at")
        batch.drop_column("arrived_at")
        batch.drop_column("shipped_at")
        batch.drop_column("assigned_to_id")
        batch.drop_column("created_by_id")
        batch.drop_column("total_quantity")
        batch.drop_column("total_value")
        batch.drop_column("destination_type")
        batch.drop_column("destination_name")
        batch.drop_column("destination_warehouse_id")
        batch.drop_column("from_warehouse_id")
        batch.drop_column("shipment_number")
