from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
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

    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True, index=True)  # New Branch ID

    supplier_name = db.Column(db.String(200), nullable=False)
    supplier_phone = db.Column(db.String(20))
    supplier_email = db.Column(db.String(120))

    purchase_date = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
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
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)

    # Pricing Method - هل أسعار المشتريات تشمل الضريبة؟
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

    # Alias for unified currency handling — amount_aed stores the tenant's base currency
    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    status = db.Column(db.String(20), default="confirmed", index=True)

    notes = db.Column(db.Text)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = db.relationship("User", foreign_keys=[user_id])
    supplier = db.relationship("Supplier", back_populates="purchases")
    branch = db.relationship("Branch", backref="purchases", foreign_keys=[branch_id])
    lines = db.relationship("PurchaseLine", back_populates="purchase", lazy="joined")
    tenant = db.relationship("Tenant", backref="purchases", foreign_keys=[tenant_id])

    @property
    def warehouse(self):
        if self.warehouse_id:
            from models import Warehouse

            return db.session.get(Warehouse, self.warehouse_id)
        return None

    def __repr__(self):
        return f"<Purchase {self.purchase_number}>"

    def get_paid_amount(self, as_of_date=None):
        """حساب المبلغ المدفوع المؤكد لهذه الفاتورة."""
        from models import Payment
        from sqlalchemy import func
        from decimal import Decimal
        from datetime import date

        if as_of_date is None:
            as_of_date = date.today()

        # أولوية 1: المدفوعات المرتبطة مباشرة بهذه الفاتورة
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

        # أولوية 2 (للتوافق مع الإصدارات السابقة): توزيع FIFO على مستوى المورد
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

        # توزيع FIFO: حساب إجمالي فواتير المورد غير المرتبطة بمدفوعات مباشرة
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

        # توزيع المدفوعات على الفواتير حسب FIFO
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
            # الأسعار تشمل الضريبة: نفصل الضريبة من الإجمالي
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
            # الأسعار لا تشمل الضريبة: نضيف الضريبة فوق الصافي
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

        # Calculate AED amount with proper rounding (includes landed cost)
        self.amount_aed = (self.total_amount * exchange_rate_decimal).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

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
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)

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
