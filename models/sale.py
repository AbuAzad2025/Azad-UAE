from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from extensions import db
from utils.currency_utils import context_aware_default_currency


class Sale(db.Model):
    __tablename__ = "sales"

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "sale_number", name="uq_sales_tenant_sale_number"),
        db.Index("idx_sale_customer_date", "customer_id", "sale_date"),
        db.Index("idx_sale_status_date", "status", "sale_date"),
        db.Index("idx_sale_payment_status", "payment_status", "customer_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_number = db.Column(db.String(50), nullable=False, index=True)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    sales_rep_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id"), nullable=True, index=True)  # New Branch ID

    sale_date = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    subtotal = db.Column(db.Numeric(15, 3), default=0)
    discount_amount = db.Column(db.Numeric(15, 3), default=0)
    shipping_cost = db.Column(db.Numeric(15, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    taxable_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False)

    amount = db.Column(db.Numeric(15, 3), nullable=False)
    paid_amount = db.Column(db.Numeric(15, 3), default=0)
    balance_due = db.Column(db.Numeric(15, 3), default=0)

    currency = db.Column(db.String(3), default=context_aware_default_currency, nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    paid_amount_aed = db.Column(db.Numeric(15, 3), default=0)

    # Pricing Method - هل الأسعار تشمل الضريبة؟
    prices_include_vat = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def amount_base(self):
        return self.amount_aed

    @amount_base.setter
    def amount_base(self, value):
        self.amount_aed = value

    @property
    def paid_amount_base(self):
        return self.paid_amount_aed

    @paid_amount_base.setter
    def paid_amount_base(self, value):
        self.paid_amount_aed = value

    @property
    def base_amount(self):
        return self.amount_aed

    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value

    @property
    def balance_due_base(self):
        return self.balance_due

    @property
    def balance_due_aed(self):
        """Alias: balance_due is always in AED/base currency."""
        return self.balance_due

    payment_status = db.Column(db.String(20), default="unpaid", index=True)
    status = db.Column(db.String(20), default="confirmed", index=True)
    source = db.Column(db.String(30), default="internal", nullable=False, index=True)
    checkout_payment_method = db.Column(db.String(50), nullable=True, index=True)
    checkout_gateway_ref = db.Column(db.String(120), nullable=True)
    coupon_code = db.Column(db.String(50), nullable=True)
    pos_session_id = db.Column(db.Integer, db.ForeignKey("pos_sessions.id"), nullable=True, index=True)
    order_type = db.Column(db.String(20), nullable=True, index=True)
    table_id = db.Column(db.Integer, db.ForeignKey("pos_tables.id"), nullable=True, index=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    notes = db.Column(db.Text)

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

    customer = db.relationship("Customer", back_populates="sales")
    seller = db.relationship("User", back_populates="sales", foreign_keys=[seller_id])
    sales_rep = db.relationship("User", foreign_keys=[sales_rep_id])
    warehouse = db.relationship("Warehouse", foreign_keys=[warehouse_id])
    branch = db.relationship("Branch", backref="sales", foreign_keys=[branch_id])
    lines = db.relationship("SaleLine", back_populates="sale", lazy="joined")
    payments = db.relationship("Payment", back_populates="sale", lazy="dynamic")
    tenant = db.relationship("Tenant", backref="sales", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<Sale {self.sale_number}>"

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
        shipping = Decimal(str(self.shipping_cost)) if self.shipping_cost else Decimal("0")
        tax_rate_decimal = Decimal(str(self.tax_rate)) if self.tax_rate else Decimal("0")
        exchange_rate_decimal = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal("1")

        # Calculate tax based on pricing method (inclusive vs exclusive VAT)
        if self.prices_include_vat:
            # الأسعار تشمل الضريبة: نفصل الضريبة من الإجمالي
            gross = self.subtotal - discount + shipping
            if tax_rate_decimal > 0:
                taxable_amount = (gross / (Decimal("1") + (tax_rate_decimal / Decimal("100")))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                self.tax_amount = (gross - taxable_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                taxable_amount = gross
                self.tax_amount = Decimal("0")
            self.total_amount = gross.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        else:
            # الأسعار لا تشمل الضريبة: نضيف الضريبة فوق الصافي
            taxable_amount = self.subtotal - discount + shipping
            self.tax_amount = (taxable_amount * (tax_rate_decimal / Decimal("100"))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            self.total_amount = (taxable_amount + self.tax_amount).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

        self.taxable_amount = taxable_amount

        # Ensure amount in invoice currency matches total_amount
        self.amount = self.total_amount

        # Resolve tenant base currency dynamically
        from utils.currency_utils import resolve_tenant_base_currency

        base_currency = resolve_tenant_base_currency(tenant_id=self.tenant_id)

        # Calculate amount in tenant base currency (dynamic)
        if self.currency == base_currency:
            self.amount_aed = self.total_amount
        else:
            self.amount_aed = (self.total_amount * exchange_rate_decimal).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )

        # Calculate paid amount in tenant base currency
        paid_foreign = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal("0")
        if self.currency == base_currency:
            self.paid_amount_aed = paid_foreign
        else:
            self.paid_amount_aed = (paid_foreign * exchange_rate_decimal).quantize(
                Decimal("0.001"), rounding=ROUND_HALF_UP
            )

        # Calculate balance and status using the centralized logic
        self.recalculate_payment_status()

    def recalculate_payment_status(self):
        """
        Recalculate payment status based on CONFIRMED payments, PENDING CHEQUES, and APPROVED returns
        المعالجة المحاسبية الذكية: خصم المرتجعات من المبلغ المستحق
        States: unpaid, partial, pending_cheque, paid, cancelled
        """
        # 1. Calculate Returns Total
        returns_total_aed = Decimal("0")
        if hasattr(self, "returns"):
            for ret in self.returns:
                if getattr(ret, "status", "approved") in ["approved", "completed"]:
                    returns_total_aed += Decimal(str(ret.amount_aed))

        # 2. Calculate Confirmed Payments
        total_confirmed_paid_aed = Decimal("0")
        total_pending_cheque_aed = Decimal("0")
        for p in self.payments:
            is_confirmed = getattr(p, "payment_confirmed", True)
            amount = Decimal(str(p.amount_aed))
            if is_confirmed:
                total_confirmed_paid_aed += amount
            elif p.payment_method == "cheque":
                total_pending_cheque_aed += amount

        # Update paid amounts (confirmed only) - Dynamic tenant base currency
        self.paid_amount_aed = total_confirmed_paid_aed
        try:
            from utils.currency_utils import resolve_tenant_base_currency

            base_currency = resolve_tenant_base_currency(tenant_id=self.tenant_id)
            ex = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal("1")
            if self.currency == base_currency:
                self.paid_amount = total_confirmed_paid_aed
            else:
                self.paid_amount = (total_confirmed_paid_aed / ex).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        except Exception:
            self.paid_amount = self.paid_amount or Decimal("0")

        # 3. Calculate Balance Due (Smart Calculation)
        # Balance = Total - Confirmed Paid - Returns
        # (Pending cheques do NOT reduce balance due until cleared)
        total_aed = Decimal(str(self.amount_aed))
        self.balance_due = (total_aed - total_confirmed_paid_aed - returns_total_aed).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

        # 4. Update Status with pending_cheque support
        if self.balance_due <= Decimal("0.01"):
            self.payment_status = "paid"
            if self.balance_due < 0:
                pass
            else:
                self.balance_due = Decimal("0")
        elif total_pending_cheque_aed > Decimal("0"):
            # Has pending cheques but not fully paid
            self.payment_status = "pending_cheque"
        elif total_confirmed_paid_aed > Decimal("0") or returns_total_aed > Decimal("0"):
            self.payment_status = "partial"
        else:
            self.payment_status = "unpaid"

    @property
    def pending_cheques_amount(self):
        """مبلغ الشيكات المعلقة (غير المؤكدة)"""
        try:
            total = Decimal("0")
            for p in self.payments:
                is_confirmed = getattr(p, "payment_confirmed", True)
                if not is_confirmed and p.payment_method == "cheque":
                    total += Decimal(str(p.amount_aed))
            return total
        except Exception:
            return Decimal("0")

    @property
    def confirmed_payments_amount(self):
        """المدفوع الفعلي المؤكد فقط"""
        try:
            total = Decimal("0")
            for p in self.payments:
                if getattr(p, "payment_confirmed", True):
                    total += Decimal(str(p.amount_aed))
            return total
        except Exception:
            return Decimal("0")

    def get_profit(self):
        """Calculate total profit with proper decimal precision"""
        if not self.lines:
            return Decimal("0")
        return sum((Decimal(str(line.get_profit())) for line in self.lines), Decimal("0"))

    def to_dict(self, include_lines=False, include_cost=False):
        data = {
            "id": self.id,
            "sale_number": self.sale_number,
            "customer": self.customer.name if self.customer else None,
            "seller": self.seller.username if self.seller else None,
            "sale_date": self.sale_date.isoformat(),
            "total_amount": float(self.total_amount),
            "paid_amount": float(self.paid_amount),
            "balance_due": float(self.balance_due),
            "currency": self.currency,
            "payment_status": self.payment_status,
            "status": self.status,
        }

        if include_lines:
            data["lines"] = [line.to_dict(include_cost=include_cost) for line in self.lines]

        if include_cost:
            data["profit"] = float(self.get_profit())

        return data


class SaleLine(db.Model):
    __tablename__ = "sale_lines"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)

    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_price = db.Column(db.Numeric(15, 3), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False)

    cost_price = db.Column(db.Numeric(15, 3), default=0)
    warranty_start_date = db.Column(db.DateTime, nullable=True)
    warranty_end_date = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.String(255))

    sale = db.relationship("Sale", back_populates="lines")
    product = db.relationship("Product", back_populates="sale_lines")
    tenant = db.relationship("Tenant", backref="sale_lines", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<SaleLine {self.product_id} x {self.quantity}>"

    def calculate_line_total(self):
        """Calculate line total with proper decimal precision and rounding"""
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        price = Decimal(str(self.unit_price)) if self.unit_price else Decimal("0")
        discount = Decimal(str(self.discount_percent)) if self.discount_percent else Decimal("0")

        discount_multiplier = (Decimal("100") - discount) / Decimal("100")
        self.line_total = (qty * price * discount_multiplier).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def get_profit(self):
        """Calculate line profit with proper decimal precision"""
        unit_price = Decimal(str(self.unit_price)) if self.unit_price else Decimal("0")
        cost_price = Decimal(str(self.cost_price)) if self.cost_price else Decimal("0")
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal("0")
        discount = Decimal(str(self.discount_percent)) if self.discount_percent else Decimal("0")

        discount_multiplier = (Decimal("100") - discount) / Decimal("100")
        profit = (unit_price - cost_price) * qty * discount_multiplier
        return profit.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def to_dict(self, include_cost=False):
        data = {
            "id": self.id,
            "product": self.product.name if self.product else None,
            "quantity": float(self.quantity),
            "unit_price": float(self.unit_price),
            "discount_percent": float(self.discount_percent),
            "line_total": float(self.line_total),
        }

        if include_cost:
            data["cost_price"] = float(self.cost_price)
            data["profit"] = float(self.get_profit())

        return data
