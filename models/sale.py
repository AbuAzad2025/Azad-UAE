from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from extensions import db


class Sale(db.Model):
    __tablename__ = 'sales'

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'sale_number', name='uq_sales_tenant_sale_number'),
        db.Index('idx_sale_customer_date', 'customer_id', 'sale_date'),
        db.Index('idx_sale_status_date', 'status', 'sale_date'),
        db.Index('idx_sale_payment_status', 'payment_status', 'customer_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    sale_number = db.Column(db.String(50), nullable=False, index=True)
    
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # New Branch ID
    
    sale_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    
    subtotal = db.Column(db.Numeric(15, 3), default=0)
    discount_amount = db.Column(db.Numeric(15, 3), default=0)
    shipping_cost = db.Column(db.Numeric(15, 3), default=0)
    tax_rate = db.Column(db.Numeric(5, 2), default=0)
    tax_amount = db.Column(db.Numeric(15, 3), default=0)
    total_amount = db.Column(db.Numeric(15, 3), nullable=False)
    
    paid_amount = db.Column(db.Numeric(15, 3), default=0)
    balance_due = db.Column(db.Numeric(15, 3), default=0)
    
    currency = db.Column(db.String(3), default='AED', nullable=False)
    exchange_rate = db.Column(db.Numeric(15, 6), default=1)
    amount_aed = db.Column(db.Numeric(15, 3), nullable=False)
    paid_amount_aed = db.Column(db.Numeric(15, 3), default=0)
    
    # Aliases for unified currency handling — amount_aed stores the tenant's base currency
    @property
    def base_amount(self):
        return self.amount_aed
    
    @base_amount.setter
    def base_amount(self, value):
        self.amount_aed = value
    
    @property
    def base_paid_amount(self):
        return self.paid_amount_aed
    
    @base_paid_amount.setter
    def base_paid_amount(self, value):
        self.paid_amount_aed = value
    
    payment_status = db.Column(db.String(20), default='unpaid', index=True)
    status = db.Column(db.String(20), default='confirmed', index=True)
    source = db.Column(db.String(30), default='internal', nullable=False, index=True)
    checkout_payment_method = db.Column(db.String(50), nullable=True, index=True)
    checkout_gateway_ref = db.Column(db.String(120), nullable=True)
    coupon_code = db.Column(db.String(50), nullable=True)
    
    # Active status for consistency with other models
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    customer = db.relationship('Customer', back_populates='sales')
    seller = db.relationship('User', back_populates='sales', foreign_keys=[seller_id])
    warehouse = db.relationship('Warehouse', foreign_keys=[warehouse_id])
    branch = db.relationship('Branch', backref='sales', foreign_keys=[branch_id])
    lines = db.relationship('SaleLine', back_populates='sale', lazy='joined')
    payments = db.relationship('Payment', back_populates='sale', lazy='dynamic')
    tenant = db.relationship('Tenant', backref='sales', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<Sale {self.sale_number}>'
    
    def calculate_totals(self):
        """
        Calculate all financial totals with proper decimal precision
        Ensures accurate financial calculations with rounding
        """
        # Calculate subtotal from all lines - ensure Decimal type
        self.subtotal = sum((Decimal(str(line.line_total)) for line in self.lines), Decimal('0'))
        
        # Ensure all amounts are Decimal
        discount = Decimal(str(self.discount_amount)) if self.discount_amount else Decimal('0')
        shipping = Decimal(str(self.shipping_cost)) if self.shipping_cost else Decimal('0')
        tax_rate_decimal = Decimal(str(self.tax_rate)) if self.tax_rate else Decimal('0')
        exchange_rate_decimal = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal('1')
        
        # Calculate taxable amount
        taxable_amount = self.subtotal - discount + shipping
        
        # Calculate tax with proper rounding (2 decimal places)
        self.tax_amount = (taxable_amount * (tax_rate_decimal / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # Calculate total amount with proper rounding
        self.total_amount = (taxable_amount + self.tax_amount).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )
        
        # Calculate amount in AED (Base Currency)
        if self.currency == 'AED':
            self.amount_aed = self.total_amount
        else:
            self.amount_aed = (self.total_amount * exchange_rate_decimal).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
        
        # Calculate paid amount AED based on transaction currency
        paid_foreign = Decimal(str(self.paid_amount)) if self.paid_amount else Decimal('0')
        if self.currency == 'AED':
            self.paid_amount_aed = paid_foreign
        else:
            self.paid_amount_aed = (paid_foreign * exchange_rate_decimal).quantize(
                Decimal('0.001'), rounding=ROUND_HALF_UP
            )
        
        # Calculate balance and status using the centralized logic
        self.recalculate_payment_status()
    
    def recalculate_payment_status(self):
        """
        Recalculate payment status based on CONFIRMED payments and APPROVED returns
        المعالجة المحاسبية الذكية: خصم المرتجعات من المبلغ المستحق
        """
        # 1. Calculate Returns Total
        returns_total_aed = Decimal('0')
        # Check if returns relationship exists (it's a backref from ProductReturn)
        if hasattr(self, 'returns'):
            for ret in self.returns:
                # Only count approved/completed returns
                if getattr(ret, 'status', 'approved') in ['approved', 'completed']:
                    returns_total_aed += Decimal(str(ret.amount_aed))

        # 2. Calculate Confirmed Payments
        total_confirmed_paid_aed = Decimal('0')
        for p in self.payments:
            is_confirmed = getattr(p, 'payment_confirmed', True)
            if is_confirmed:
                total_confirmed_paid_aed += Decimal(str(p.amount_aed))
        
        # Update paid amounts (confirmed only)
        self.paid_amount_aed = total_confirmed_paid_aed
        try:
            ex = Decimal(str(self.exchange_rate)) if self.exchange_rate else Decimal('1')
            if self.currency == 'AED':
                self.paid_amount = total_confirmed_paid_aed
            else:
                self.paid_amount = (total_confirmed_paid_aed / ex).quantize(
                    Decimal('0.001'), rounding=ROUND_HALF_UP
                )
        except Exception:
            self.paid_amount = self.paid_amount or Decimal('0')
        
        # 3. Calculate Balance Due (Smart Calculation)
        # Balance = Total - Paid - Returns
        total_aed = Decimal(str(self.amount_aed))
        self.balance_due = (total_aed - total_confirmed_paid_aed - returns_total_aed).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )
        
        # 4. Update Status
        if self.balance_due <= Decimal('0.01'):
            self.payment_status = 'paid'
            # If negative balance (refund due), keep it negative to show overpayment
            if self.balance_due < 0:
                 pass 
            else:
                 self.balance_due = Decimal('0')
        elif total_confirmed_paid_aed > Decimal('0') or returns_total_aed > Decimal('0'):
            self.payment_status = 'partial'
        else:
            self.payment_status = 'unpaid'
    
    @property
    def pending_cheques_amount(self):
        """مبلغ الشيكات المعلقة (غير المؤكدة)"""
        try:
            total = Decimal('0')
            for p in self.payments:
                # التحقق من وجود payment_confirmed
                is_confirmed = getattr(p, 'payment_confirmed', True)
                if not is_confirmed and p.payment_method == 'cheque':
                    total += Decimal(str(p.amount_aed))
            return total
        except Exception:
            return Decimal('0')
    
    @property
    def confirmed_payments_amount(self):
        """المدفوع الفعلي المؤكد فقط"""
        return self.paid_amount if self.paid_amount else Decimal('0')
    
    def get_profit(self):
        """Calculate total profit with proper decimal precision"""
        if not self.lines:
            return Decimal('0')
        return sum((Decimal(str(line.get_profit())) for line in self.lines), Decimal('0'))
    
    def to_dict(self, include_lines=False, include_cost=False):
        data = {
            'id': self.id,
            'sale_number': self.sale_number,
            'customer': self.customer.name if self.customer else None,
            'seller': self.seller.username if self.seller else None,
            'sale_date': self.sale_date.isoformat(),
            'total_amount': float(self.total_amount),
            'paid_amount': float(self.paid_amount),
            'balance_due': float(self.balance_due),
            'currency': self.currency,
            'payment_status': self.payment_status,
            'status': self.status,
        }
        
        if include_lines:
            data['lines'] = [line.to_dict(include_cost=include_cost) for line in self.lines]
        
        if include_cost:
            data['profit'] = float(self.get_profit())
        
        return data


class SaleLine(db.Model):
    __tablename__ = 'sale_lines'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id', ondelete='RESTRICT'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    unit_price = db.Column(db.Numeric(15, 3), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), default=0)
    line_total = db.Column(db.Numeric(15, 3), nullable=False)
    
    cost_price = db.Column(db.Numeric(15, 3), default=0)
    
    notes = db.Column(db.String(255))
    
    sale = db.relationship('Sale', back_populates='lines')
    product = db.relationship('Product', back_populates='sale_lines')
    tenant = db.relationship('Tenant', backref='sale_lines', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<SaleLine {self.product_id} x {self.quantity}>'
    
    def calculate_line_total(self):
        """Calculate line total with proper decimal precision and rounding"""
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal('0')
        price = Decimal(str(self.unit_price)) if self.unit_price else Decimal('0')
        discount = Decimal(str(self.discount_percent)) if self.discount_percent else Decimal('0')
        
        discount_multiplier = (Decimal('100') - discount) / Decimal('100')
        self.line_total = (qty * price * discount_multiplier).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )
    
    def get_profit(self):
        """Calculate line profit with proper decimal precision"""
        unit_price = Decimal(str(self.unit_price)) if self.unit_price else Decimal('0')
        cost_price = Decimal(str(self.cost_price)) if self.cost_price else Decimal('0')
        qty = Decimal(str(self.quantity)) if self.quantity else Decimal('0')
        discount = Decimal(str(self.discount_percent)) if self.discount_percent else Decimal('0')
        
        discount_multiplier = (Decimal('100') - discount) / Decimal('100')
        profit = (unit_price - cost_price) * qty * discount_multiplier
        return profit.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    
    def to_dict(self, include_cost=False):
        data = {
            'id': self.id,
            'product': self.product.name if self.product else None,
            'quantity': float(self.quantity),
            'unit_price': float(self.unit_price),
            'discount_percent': float(self.discount_percent),
            'line_total': float(self.line_total),
        }
        
        if include_cost:
            data['cost_price'] = float(self.cost_price)
            data['profit'] = float(self.get_profit())
        
        return data

