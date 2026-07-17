from extensions import db


class PosFloor(db.Model):
    __tablename__ = "pos_floors"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    tables = db.relationship(
        "PosTable",
        back_populates="floor",
        lazy="dynamic",
        order_by="PosTable.sort_order",
    )


class PosTable(db.Model):
    __tablename__ = "pos_tables"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    floor_id = db.Column(
        db.Integer, db.ForeignKey("pos_floors.id"), nullable=False, index=True
    )
    label = db.Column(db.String(20), nullable=False)
    capacity = db.Column(db.Integer, default=4)
    pos_x = db.Column(db.Integer, default=0)
    pos_y = db.Column(db.Integer, default=0)
    shape = db.Column(db.String(20), default="rectangle")
    status = db.Column(db.String(20), default="free", nullable=False, index=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    floor = db.relationship("PosFloor", back_populates="tables")


class PosTableOrder(db.Model):
    __tablename__ = "pos_table_orders"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    table_id = db.Column(
        db.Integer, db.ForeignKey("pos_tables.id"), nullable=False, index=True
    )
    sale_id = db.Column(
        db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True
    )
    guest_count = db.Column(db.Integer, default=1)
    is_split = db.Column(db.Boolean, default=False)
    split_group = db.Column(db.String(20), nullable=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        nullable=False,
    )
