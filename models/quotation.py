from datetime import UTC, datetime

from extensions import db
from utils.currency_utils import context_aware_default_currency


class Quotation(db.Model):
    __tablename__ = "quotations"
    __table_args__ = (db.UniqueConstraint("tenant_id", "quotation_number", name="uq_quotations_tenant_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quotation_number = db.Column(db.String(50), nullable=False, index=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True)

    quotation_date = db.Column(
        db.Date,
        default=lambda: datetime.now(UTC).date(),
        nullable=False,
        index=True,
    )
    expiry_date = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(20), default="draft", nullable=False, index=True)

    subtotal = db.Column(db.Numeric(15, 3), default=0)
    discount_amount = db.Column(db.Numeric(15, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    base_currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False, default=0)

    prices_include_vat = db.Column(db.Boolean, default=False, nullable=False)

    notes = db.Column(db.Text)
    terms = db.Column(db.Text)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    customer = db.relationship("Customer", foreign_keys=[customer_id])
    branch = db.relationship("Branch", foreign_keys=[branch_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    sale = db.relationship("Sale", foreign_keys=[sale_id], backref="source_quotations")
    lines = db.relationship("QuotationLine", back_populates="quotation", lazy="joined", cascade="all, delete-orphan")
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id], backref="quotations")

    def __repr__(self):
        return f"<Quotation {self.quotation_number}>"

    @property
    def is_expired(self):
        if self.expiry_date and self.status in ("draft", "sent"):
            return datetime.now(UTC).date() > self.expiry_date
        return False

    @property
    def status_ar(self):
        labels = {
            "draft": "مسودة",
            "sent": "مرسلة",
            "accepted": "مقبولة",
            "rejected": "مرفوضة",
            "converted_to_sale": "محولة لفاتورة",
            "expired": "منتهية",
        }
        return labels.get(self.status, self.status)


class QuotationLine(db.Model):
    __tablename__ = "quotation_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quotation_id = db.Column(
        db.Integer,
        db.ForeignKey("quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    description = db.Column(db.String(500))
    quantity = db.Column(db.Numeric(15, 3), nullable=False, default=1)
    unit_price = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False, default=0)
    sort_order = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC))

    quotation = db.relationship("Quotation", back_populates="lines")
    product = db.relationship("Product", foreign_keys=[product_id])

    def __repr__(self):
        return f"<QuotationLine product={self.product_id} qty={self.quantity}>"
