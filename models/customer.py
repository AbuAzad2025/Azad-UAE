from datetime import datetime, timezone
from extensions import db


class Customer(db.Model):
    __tablename__ = 'customers'
    
    __table_args__ = (
        db.Index('idx_customer_active_type', 'is_active', 'customer_type'),
        db.Index('idx_customer_balance', 'balance'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    name_ar = db.Column(db.String(200))
    
    customer_type = db.Column(db.String(20), nullable=False, default='regular', index=True)
    
    customer_classification = db.Column(db.String(20), default='regular', index=True)
    
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    tax_number = db.Column(db.String(50))
    
    preferred_currency = db.Column(db.String(3), default='AED')  # TODO: use Config.DEFAULT_CURRENCY
    
    credit_limit = db.Column(db.Numeric(15, 3), default=0)
    total_purchases = db.Column(db.Numeric(15, 3), default=0)
    
    # Customer balance (receivables)
    balance = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    
    notes = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    sales = db.relationship('Sale', back_populates='customer', lazy='dynamic')
    receipts = db.relationship('Receipt', back_populates='customer', lazy='dynamic')
    tenant = db.relationship('Tenant', backref='customers', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<Customer {self.name}>'
    
    def get_balance_aed(self):
        # الرصيد التراكمي الرسمي بالدرهم
        from decimal import Decimal
        return Decimal(str(self.balance or 0))

    def get_balance_base(self):
        """Alias for get_balance_aed — returns balance in tenant base currency."""
        return self.get_balance_aed()

    # دوال مساعدة لتحديث الرصيد بشكل تراكمي وسريع
    def apply_sale(self, amount_aed):
        """تحديث رصيد العميل عند إنشاء فاتورة بيع (يزيد الذمم علينا)."""
        from decimal import Decimal
        self.balance = (self.balance or Decimal('0')) + Decimal(str(amount_aed or 0))

    def apply_receipt(self, amount_aed):
        """تحديث رصيد العميل عند سند قبض (يقلل الذمم علينا)."""
        from decimal import Decimal
        self.balance = (self.balance or Decimal('0')) - Decimal(str(amount_aed or 0))

    def apply_return(self, amount_aed):
        """تحديث رصيد العميل عند مرتجع مبيعات لصالحه (يقلل الذمم علينا)."""
        from decimal import Decimal
        self.balance = (self.balance or Decimal('0')) - Decimal(str(amount_aed or 0))

    def adjust_balance(self, delta_aed):
        """تعديل رصيد العميل بفرق موجب/سالب بشكل موحد."""
        from decimal import Decimal
        self.balance = (self.balance or Decimal('0')) + Decimal(str(delta_aed or 0))

    def set_balance(self, new_balance_aed):
        """تعيين رصيد العميل مباشرة (لعمليات التصحيح/الإدارة)."""
        from decimal import Decimal
        self.balance = Decimal(str(new_balance_aed or 0))
    
    def get_display_name(self, lang='ar'):
        if lang == 'ar' and self.name_ar:
            return self.name_ar
        return self.name
    
    def get_type_display(self, lang='ar'):
        types = {
            'regular': {'ar': 'عادي', 'en': 'Regular'},
            'merchant': {'ar': 'تاجر', 'en': 'Merchant'},
            'partner': {'ar': 'شريك', 'en': 'Partner'},
        }
        return types.get(self.customer_type, {}).get(lang, self.customer_type)
    
    def get_classification_display(self, lang='ar'):
        classifications = {
            'vip': {'ar': 'VIP - عميل مميز', 'en': 'VIP'},
            'premium': {'ar': 'ممتاز', 'en': 'Premium'},
            'regular': {'ar': 'عادي', 'en': 'Regular'},
            'inactive': {'ar': 'غير نشط', 'en': 'Inactive'},
        }
        return classifications.get(self.customer_classification, {}).get(lang, self.customer_classification)
    
    def update_classification(self):
        from decimal import Decimal
        total = self.total_purchases or Decimal('0')
        
        if total >= Decimal('100000'):
            self.customer_classification = 'vip'
        elif total >= Decimal('50000'):
            self.customer_classification = 'premium'
        else:
            self.customer_classification = 'regular'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'name_ar': self.name_ar,
            'customer_type': self.customer_type,
            'customer_classification': self.customer_classification,
            'phone': self.phone,
            'email': self.email,
            'balance': float(self.get_balance_aed()),
            'balance_aed': float(self.get_balance_aed()),
            'total_purchases': float(self.total_purchases or 0),
            'is_active': self.is_active,
        }

