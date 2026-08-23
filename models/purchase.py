from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from extensions import db
from utils.currency_utils import context_aware_default_currency


class Purchase(db.Model):
    __tablename__ = "purchases"
    __table_args__ = (db.UniqueConstraint("tenant_id", "purchase_number", name="uq_purchases_tenant_purchase_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_number = db.Column(db.String(50), nullable=False, index=True)

    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True, index=True)
    branch_id = db.Column(
        db.Integer, db.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=True, index=True
    )  # New Branch ID

    # Procurement linkage — PO/GRN that this supplier invoice is matched against.
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    grn_id = db.Column(db.Integer, db.ForeignKey("goods_receipts.id", ondelete="SET NULL"), nullable=True, index=True)

    supplier_name = db.Column(db.String(200), nullable=False)
    supplier_phone = db.Column(db.String(20))
    supplier_email = db.Column(db.String(120))

    purchase_date = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    subtotal = db.Column(db.Numeric(15, 3), default=0)
    discount_amount = db.Column(db.Numeric(15, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    taxable_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False)

    amount = db.Column(db.Numeric(15, 3), nullable=False)
    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    base_currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    # Pricing Method - Ù‡Ù„ Ø£Ø³Ø¹Ø§Ø± Ø§Ù„Ù…Ø´ØªØ±ÙŠØ§Øª ØªØ´Ù…Ù„ Ø§Ù„Ø¶Ø±ÙŠØ¨Ø©ØŸ
    prices_include_vat = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def amount_base(self):
        return self.amount_aed

    @amount_base.setter
    def amount_base(self, value):
        self.amount_aed = value

    # Landed cost components (Phase 5)
    freight = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    insurance = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    customs_duty = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    other_landed_cost = db.Column(db.Numeric(15, 3), default=0, nullable=False)

    @property
    def total_landed_cost(self):
        return (
            Decimal(str(self.freight or 0))
            + Decimal(str(self.insurance or 0))
            + Decimal(str(self.customs_duty or 0))
            + Decimal(str(self.other_landed_cost or 0))
        )

    # Alias for unified currency handling â€” amount_aed stores the tenant's base currency
    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    @property
    def base_currency_display(self):
        """Alias for templates."""
        return self.base_currency

    status = db.Column(db.String(20), default="confirmed", index=True)

    notes = db.Column(db.Text)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
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

    user = db.relationship("User", foreign_keys=[user_id])
    supplier = db.relationship("Supplier", back_populates="purchases")
    branch = db.relationship("Branch", backref="purchases", foreign_keys=[branch_id])
    lines = db.relationship("PurchaseLine", back_populates="purchase", lazy="joined")
    tenant = db.relationship("Tenant", backref="purchases", foreign_keys=[tenant_id])
    purchase_order = db.relationship("PurchaseOrder", backref="invoices", foreign_keys=[po_id])
    goods_receipt = db.relationship("GoodsReceipt", backref="invoices", foreign_keys=[grn_id])

    @property
    def warehouse(self):
        if self.warehouse_id:
            from models import Warehouse

            return db.session.get(Warehouse, self.warehouse_id)
        return None

    def __repr__(self):
        return f"<Purchase {self.purchase_number}>"

    def get_paid_amount(self, as_of_date=None):
        """Ø­Ø³Ø§Ø¨ Ø§Ù„Ù…Ø¨Ù„Øº Ø§Ù„Ù…Ø¯ÙÙˆØ¹ Ø§Ù„Ù…Ø¤ÙƒØ¯ Ù„Ù‡Ø°Ù‡ Ø§Ù„ÙØ§ØªÙˆØ±Ø©."""
        from datetime import date
        from decimal import Decimal

        from sqlalchemy import func

        from models import Payment

        if as_of_date is None:
            as_of_date = date.today()

        # Ø£ÙˆÙ„ÙˆÙŠØ© 1: Ø§Ù„Ù…Ø¯ÙÙˆØ¹Ø§Øª Ø§Ù„Ù…Ø±ØªØ¨Ø·Ø© Ù…Ø¨Ø§Ø´Ø±Ø© Ø¨Ù‡Ø°Ù‡ Ø§Ù„ÙØ§ØªÙˆØ±Ø©
        query = db.session.query(func.sum(Payment.amount_aed)).filter(
            Payment.purchase_id == self.id,
            Payment.tenant_id == self.tenant_id,
            Payment.direction == "outgoing",
            Payment.payment_confirmed,
            func.date(Payment.payment_date) <= as_of_date,
        )
        if self.branch_id is not None:
            query = query.filter(Payment.branch_id == self.branch_id)
        direct_paid = query.scalar()

        if direct_paid:
            return Decimal(str(direct_paid))

        # Ø£ÙˆÙ„ÙˆÙŠØ© 2 (Ù„Ù„ØªÙˆØ§ÙÙ‚ Ù…Ø¹ Ø§Ù„Ø¥ØµØ¯Ø§Ø±Ø§Øª Ø§Ù„Ø³Ø§Ø¨Ù‚Ø©): ØªÙˆØ²ÙŠØ¹ FIFO Ø¹Ù„Ù‰ Ù…Ø³ØªÙˆÙ‰ Ø§Ù„Ù…ÙˆØ±Ø¯
        total_supplier_paid = db.session.query(func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == self.supplier_id,
            Payment.tenant_id == self.tenant_id,
            Payment.direction == "outgoing",
            Payment.payment_confirmed,
            Payment.purchase_id.is_(None),
            func.date(Payment.payment_date) <= as_of_date,
        )
        if self.branch_id is not None:
            total_supplier_paid = total_supplier_paid.filter(Payment.branch_id == self.branch_id)
        total_paid = total_supplier_paid.scalar()

        if not total_paid:
            return Decimal("0")

        # ØªÙˆØ²ÙŠØ¹ FIFO: Ø­Ø³Ø§Ø¨ Ø¥Ø¬Ù…Ø§Ù„ÙŠ ÙÙˆØ§ØªÙŠØ± Ø§Ù„Ù…ÙˆØ±Ø¯ ØºÙŠØ± Ø§Ù„Ù…Ø±ØªØ¨Ø·Ø© Ø¨Ù…Ø¯ÙÙˆØ¹Ø§Øª Ù…Ø¨Ø§Ø´Ø±Ø©
        from models import Purchase

        other_purchases = Purchase.query.filter(
            Purchase.supplier_id == self.supplier_id,
            Purchase.id != self.id,
            Purchase.tenant_id == self.tenant_id,
        )
        if self.branch_id is not None:
            other_purchases = other_purchases.filter(Purchase.branch_id == self.branch_id)

        other_total = sum(Decimal(str(p.amount_aed or 0)) for p in other_purchases.all())

        total_paid_decimal = Decimal(str(total_paid))
        my_amount = Decimal(str(self.amount_aed or 0))

        # ØªÙˆØ²ÙŠØ¹ Ø§Ù„Ù…Ø¯ÙÙˆØ¹Ø§Øª Ø¹Ù„Ù‰ Ø§Ù„ÙÙˆØ§ØªÙŠØ± Ø­Ø³Ø¨ FIFO
        if other_total >= total_paid_decimal:
            return Decimal("0")

        allocated_to_me = total_paid_decimal - other_total
        return min(allocated_to_me, my_amount)

    def calculate_totals(self):
        """
        Calculate all financial totals with proper decimal precision
        Ensures accurate financial calculations with rounding
        Supports both VAT-inclusive and VAT-exclusive pricing.
        """
        # Calculate subtotal from all lines - ensure Decimal type
        self.subtotal = sum((Decimal(str(line.line_total)) for line in self.lines), Decimal("0"))

        # Ensure all amounts are Decimal
        discount = Decimal(str(self.discount_amount)) if self.discount_amount else Decimal("0")
        tax_rate_decimal = Decimal(str(self.tax_rate)) if self.tax_rate else Decimal("0")
        exchange_rate_decimal = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal("1")

        # Calculate tax based on pricing method (inclusive vs exclusive VAT)
        if self.prices_include_vat:
            # Ø§Ù„Ø£Ø³Ø¹Ø§Ø± ØªØ´Ù…Ù„ Ø§Ù„Ø¶Ø±ÙŠØ¨Ø©: Ù†ÙØµÙ„ Ø§Ù„Ø¶Ø±ÙŠØ¨Ø© Ù…Ù† Ø§Ù„Ø¥Ø¬Ù…Ø§Ù„ÙŠ
            gross = self.subtotal - discount
            if tax_rate_decimal > 0:
                taxable_amount = (gross / (Decimal("1") + (tax_rate_decimal / Decimal("100")))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                self.tax_amount = (gross - taxable_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                taxable_amount = gross
                self.tax_amount = Decimal("0")
            self.total_amount = (gross + self.total_landed_cost).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        else:
            # Ø§Ù„Ø£Ø³Ø¹Ø§Ø± Ù„Ø§ ØªØ´Ù…Ù„ Ø§Ù„Ø¶Ø±ÙŠØ¨Ø©: Ù†Ø¶ÙŠÙ Ø§Ù„Ø¶Ø±ÙŠØ¨Ø© ÙÙˆÙ‚ Ø§Ù„ØµØ§ÙÙŠ
            taxable_amount = self.subtotal - discount
            self.tax_amount = (taxable_amount * (tax_rate_decimal / Decimal("100"))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            self.total_amount = (taxable_amount + self.tax_amount + self.total_landed_cost).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )

        self.taxable_amount = taxable_amount

        # Ensure amount in invoice currency matches total_amount
        self.amount = self.total_amount

        # Resolve tenant base currency and store it at transaction time
        from utils.currency_utils import resolve_tenant_base_currency

        base_currency = resolve_tenant_base_currency(tenant_id=self.tenant_id)
        self.base_currency = base_currency

        # Calculate amount in tenant base currency (using stored base_currency)
        if self.currency == base_currency:
            self.amount_aed = self.total_amount
        else:
            self.amount_aed = (self.total_amount * exchange_rate_decimal).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )

    def to_dict(self, include_lines=False):
        data = {
            "id": self.id,
            "purchase_number": self.purchase_number,
            "supplier_name": self.supplier_name,
            "supplier_phone": self.supplier_phone,
            "purchase_date": self.purchase_date.isoformat(),
            "total_amount": float(self.total_amount),
            "currency": self.currency,
            "status": self.status,
        }

        if include_lines:
            data["lines"] = [line.to_dict() for line in self.lines]

        return data


class PurchaseLine(db.Model):
    __tablename__ = "purchase_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_id = db.Column(
        db.Integer,
        db.ForeignKey("purchases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(15, 3), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False)
    landed_cost = db.Column(db.Numeric(15, 3), default=0, nullable=False)

    notes = db.Column(db.String(255))

    purchase = db.relationship("Purchase", back_populates="lines")
    product = db.relationship("Product", back_populates="purchase_lines")
    tenant = db.relationship("Tenant", backref="purchase_lines", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<PurchaseLine {self.product_id} x {self.quantity}>"

    def calculate_line_total(self):
        """Calculate line total with proper decimal precision and rounding"""
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        cost = Decimal(str(self.unit_cost)) if self.unit_cost else Decimal("0")
        discount = Decimal(str(self.discount_percent)) if self.discount_percent else Decimal("0")

        discount_multiplier = (Decimal("100") - discount) / Decimal("100")
        self.line_total = (qty * cost * discount_multiplier).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @property
    def landed_unit_cost(self):
        """Unit cost after distributing landed costs (freight, insurance, customs, etc.)"""
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        if qty == 0:
            return Decimal("0")
        base = Decimal(str(self.unit_cost)) if self.unit_cost else Decimal("0")
        landed = Decimal(str(self.landed_cost)) if self.landed_cost else Decimal("0")
        return (base + (landed / qty)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @property
    def inventory_unit_cost(self):
        """Unit cost for inventory valuation (VAT-exclusive if purchase uses prices_include_vat)."""
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        if qty == 0:
            return Decimal("0")
        base = Decimal(str(self.unit_cost)) if self.unit_cost else Decimal("0")
        discount = Decimal(str(self.discount_percent)) if self.discount_percent else Decimal("0")
        discount_multiplier = (Decimal("100") - discount) / Decimal("100")
        line_total_with_discount = base * qty * discount_multiplier

        purchase = self.purchase
        if purchase and getattr(purchase, "prices_include_vat", False):
            tax_rate = Decimal(str(purchase.tax_rate)) if purchase.tax_rate else Decimal("0")
            if tax_rate > 0:
                line_total_excl = (line_total_with_discount / (Decimal("1") + (tax_rate / Decimal("100")))).quantize(
                    Decimal("0.001"), rounding=ROUND_HALF_UP
                )
                return (line_total_excl / qty).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        return (line_total_with_discount / qty).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @property
    def landed_inventory_unit_cost(self):
        """Inventory unit cost after distributing landed costs (VAT-exclusive if applicable)."""
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        if qty == 0:
            return Decimal("0")
        base = self.inventory_unit_cost
        landed = Decimal(str(self.landed_cost)) if self.landed_cost else Decimal("0")
        return (base + (landed / qty)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def to_dict(self):
        return {
            "id": self.id,
            "product": self.product.name if self.product else None,
            "quantity": float(self.quantity),
            "unit_cost": float(self.unit_cost),
            "discount_percent": float(self.discount_percent),
            "line_total": float(self.line_total),
            "landed_cost": float(self.landed_cost) if self.landed_cost else 0,
            "landed_unit_cost": (float(self.landed_unit_cost) if self.landed_unit_cost else 0),
        }


class PurchaseRequisition(db.Model):
    __tablename__ = "purchase_requisitions"
    __table_args__ = (db.UniqueConstraint("tenant_id", "requisition_number", name="uq_pr_tenant_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requisition_number = db.Column(db.String(50), nullable=False, index=True)
    requester_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    requested_date = db.Column(db.Date, nullable=False, index=True)
    needed_by_date = db.Column(db.Date)
    priority = db.Column(db.String(20), default="normal")
    status = db.Column(db.String(20), default="draft", index=True)
    justification = db.Column(db.Text)
    notes = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime(timezone=True))
    rejected_reason = db.Column(db.String(500))
    po_id = db.Column(db.Integer, db.ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", backref="purchase_requisitions", foreign_keys=[tenant_id])
    requester = db.relationship("User", foreign_keys=[requester_id])
    department = db.relationship("Department", backref="requisitions")
    branch = db.relationship("Branch", backref="requisitions", foreign_keys=[branch_id])
    approver = db.relationship("User", foreign_keys=[approved_by])
    purchase = db.relationship("Purchase", backref="requisitions", foreign_keys=[po_id])
    lines = db.relationship(
        "PurchaseRequisitionLine", back_populates="requisition", lazy="joined", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<PurchaseRequisition {self.requisition_number}>"

    @property
    def status_ar(self):
        mapping = {
            "draft": "مسودة",
            "pending_approval": "بانتظار الموافقة",
            "approved": "تمت الموافقة",
            "rejected": "مرفوض",
            "converted_to_po": "تم التحويل لطلب شراء",
        }
        return mapping.get(self.status, self.status)

    @property
    def priority_ar(self):
        mapping = {"low": "منخفضة", "normal": "عادية", "high": "عالية", "urgent": "عاجلة"}
        return mapping.get(self.priority, self.priority)


class PurchaseRequisitionLine(db.Model):
    __tablename__ = "purchase_requisition_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requisition_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_cost_estimate = db.Column(db.Numeric(15, 3), default=0)
    notes = db.Column(db.String(255))

    requisition = db.relationship("PurchaseRequisition", back_populates="lines")
    product = db.relationship("Product")
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<PurchaseRequisitionLine {self.product_id} x {self.quantity}>"


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_orders"
    __table_args__ = (db.UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    po_number = db.Column(db.String(50), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    requisition_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_requisitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_date = db.Column(db.Date, nullable=False, index=True)
    expected_delivery_date = db.Column(db.Date)
    subtotal = db.Column(db.Numeric(15, 3), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), default=0)
    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    status = db.Column(db.String(20), default="draft", index=True)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    confirmed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    tenant = db.relationship("Tenant", backref="purchase_orders", foreign_keys=[tenant_id])
    supplier = db.relationship("Supplier", backref="purchase_orders")
    warehouse = db.relationship("Warehouse", backref="purchase_orders", foreign_keys=[warehouse_id])
    branch = db.relationship("Branch", backref="purchase_orders", foreign_keys=[branch_id])
    requisition = db.relationship("PurchaseRequisition", backref="converted_po", foreign_keys=[requisition_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    confirmer = db.relationship("User", foreign_keys=[confirmed_by])
    lines = db.relationship("PurchaseOrderLine", back_populates="order", lazy="joined", cascade="all, delete-orphan")
    goods_receipts = db.relationship("GoodsReceipt", back_populates="purchase_order")

    def __repr__(self):
        return f"<PurchaseOrder {self.po_number}>"

    def calculate_totals(self):
        self.subtotal = sum((Decimal(str(line.line_total)) for line in self.lines), Decimal("0"))
        self.total_amount = self.subtotal + self.tax_amount

    @property
    def total_received_quantity(self):
        total = Decimal("0")
        for line in self.lines:
            total += line.received_quantity or Decimal("0")
        return total

    @property
    def is_fully_received(self):
        return all((line.received_quantity or Decimal("0")) >= line.quantity for line in self.lines if line.quantity)

    @property
    def status_ar(self):
        mapping = {
            "draft": "مسودة",
            "submitted": "مُرسل",
            "confirmed": "مؤكد",
            "partially_received": "تم الاستلام جزئياً",
            "received": "تم الاستلام",
            "closed": "مغلق",
            "cancelled": "ملغى",
        }
        return mapping.get(self.status, self.status)


class PurchaseOrderLine(db.Model):
    __tablename__ = "purchase_order_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    po_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(15, 3), nullable=False)
    line_total = db.Column(db.Numeric(15, 3), nullable=False)
    received_quantity = db.Column(db.Numeric(15, 3), default=0)
    notes = db.Column(db.String(255))

    order = db.relationship("PurchaseOrder", back_populates="lines")
    product = db.relationship("Product")
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<PurchaseOrderLine {self.product_id} x {self.quantity}>"

    def calculate_line_total(self):
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        cost = Decimal(str(self.unit_cost)) if self.unit_cost else Decimal("0")
        self.line_total = (qty * cost).quantize(Decimal("0.001"))


class GoodsReceipt(db.Model):
    __tablename__ = "goods_receipts"
    __table_args__ = (db.UniqueConstraint("tenant_id", "grn_number", name="uq_grn_tenant_number"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grn_number = db.Column(db.String(50), nullable=False, index=True)
    po_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    warehouse_id = db.Column(
        db.Integer,
        db.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey("branches.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    received_date = db.Column(db.Date, nullable=False, index=True)
    received_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(20), default="draft", index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)

    tenant = db.relationship("Tenant", backref="goods_receipts", foreign_keys=[tenant_id])
    purchase_order = db.relationship("PurchaseOrder", back_populates="goods_receipts")
    supplier = db.relationship("Supplier")
    warehouse = db.relationship("Warehouse")
    branch = db.relationship("Branch", backref="goods_receipts", foreign_keys=[branch_id])
    receiver = db.relationship("User", foreign_keys=[received_by])
    lines = db.relationship("GoodsReceiptLine", back_populates="grn", lazy="joined", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<GoodsReceipt {self.grn_number}>"

    @property
    def status_ar(self):
        mapping = {"draft": "مسودة", "confirmed": "مؤكد", "cancelled": "ملغى"}
        return mapping.get(self.status, self.status)


class GoodsReceiptLine(db.Model):
    __tablename__ = "goods_receipt_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    grn_id = db.Column(
        db.Integer,
        db.ForeignKey("goods_receipts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    po_line_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order_lines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    ordered_quantity = db.Column(db.Numeric(15, 3), nullable=False)
    received_quantity = db.Column(db.Numeric(15, 3), nullable=False)
    condition = db.Column(db.String(20), default="acceptable")
    notes = db.Column(db.String(255))

    grn = db.relationship("GoodsReceipt", back_populates="lines")
    po_line = db.relationship("PurchaseOrderLine", backref="grn_lines")
    product = db.relationship("Product")
    tenant = db.relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<GoodsReceiptLine {self.product_id} received={self.received_quantity}>"
