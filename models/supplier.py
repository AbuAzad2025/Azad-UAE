"""
🏪 Supplier Model - نموذج الموردين
نموذج منفصل لإدارة الموردين مع تتبع المشتريات والأرصدة
"""
from datetime import datetime, timezone
from extensions import db
from decimal import Decimal


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=False, index=True)
    
    # معلومات أساسية
    name = db.Column(db.String(200), nullable=False, index=True)
    name_ar = db.Column(db.String(200))  # الاسم بالعربية
    name_en = db.Column(db.String(200))  # الاسم بالإنجليزية
    company_name = db.Column(db.String(200))
    
    # معلومات الاتصال
    phone = db.Column(db.String(50))
    phone2 = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(200))
    
    # العنوان
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100), default='UAE')
    
    # معلومات ضريبية وقانونية
    tax_number = db.Column(db.String(50))
    commercial_registration = db.Column(db.String(50))
    
    # تصنيف المورد
    supplier_type = db.Column(db.String(50), default='parts')  # parts, equipment, services, materials
    rating = db.Column(db.Integer, default=3)  # 1-5 stars
    
    # الحد الائتماني والعملة
    credit_limit = db.Column(db.Numeric(15, 3), default=0)
    payment_terms_days = db.Column(db.Integer, default=30)  # شروط الدفع بالأيام
    preferred_currency = db.Column(db.String(3), default='AED')  # TODO: use Config.DEFAULT_CURRENCY
    
    # إحصائيات
    total_purchases_aed = db.Column(db.Numeric(15, 3), default=0)
    total_paid_aed = db.Column(db.Numeric(15, 3), default=0)
    last_purchase_date = db.Column(db.DateTime)
    
    # Aliases for unified currency handling
    @property
    def total_purchases_base(self):
        return self.total_purchases_aed
    
    @total_purchases_base.setter
    def total_purchases_base(self, value):
        self.total_purchases_aed = value
    
    @property
    def total_paid_base(self):
        return self.total_paid_aed
    
    @total_paid_base.setter
    def total_paid_base(self, value):
        self.total_paid_aed = value
    
    # معلومات إضافية
    notes = db.Column(db.Text)
    tags = db.Column(db.String(500))  # Comma-separated tags
    
    # الحالة
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    is_verified = db.Column(db.Boolean, default=False)  # مورد موثوق
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # العلاقات
    purchases = db.relationship('Purchase', back_populates='supplier', lazy='dynamic')
    tenant = db.relationship('Tenant', backref='suppliers', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<Supplier {self.name}>'
    
    def get_balance_aed(self):
        """حساب الرصيد المستحق للمورد (Legacy alias — use get_balance_base)"""
        return self.get_balance_base()
    
    def get_balance_base(self):
        """حساب الرصيد المستحق للمورد بالعملة الأساسية للتينانت"""
        total = self.total_purchases_aed or Decimal('0')
        paid = self.total_paid_aed or Decimal('0')
        return total - paid
    
    # دوال مساعدة لتحديث الإحصائيات/الرصيد بشكل تراكمي
    def apply_purchase(self, amount_aed: Decimal):
        """تحديث إجمالي المشتريات عند إنشاء فاتورة شراء."""
        self.total_purchases_aed = (self.total_purchases_aed or Decimal('0')) + Decimal(str(amount_aed or 0))
    
    def apply_payment(self, amount_aed: Decimal):
        """تحديث إجمالي المدفوع للمورد عند سند صرف."""
        self.total_paid_aed = (self.total_paid_aed or Decimal('0')) + Decimal(str(amount_aed or 0))
    
    def apply_purchase_base(self, amount: Decimal):
        """تحديث إجمالي المشتريات بالعملة الأساسية."""
        self.apply_purchase(amount)
    
    def apply_payment_base(self, amount: Decimal):
        """تحديث إجمالي المدفوع بالعملة الأساسية."""
        self.apply_payment(amount)
    
    def get_display_name(self, lang='ar'):
        """الحصول على الاسم حسب اللغة"""
        if lang == 'en' and self.name_en:
            return self.name_en
        return self.name
    
    def get_type_display(self):
        """عرض نوع المورد"""
        types = {
            'parts': 'قطع غيار',
            'equipment': 'معدات',
            'services': 'خدمات',
            'materials': 'مواد خام',
            'other': 'أخرى'
        }
        return types.get(self.supplier_type, self.supplier_type)
    
    def get_rating_stars(self):
        """عرض التقييم كنجوم"""
        stars = '⭐' * (self.rating or 0)
        return stars or '☆☆☆☆☆'
    
    def update_statistics(self):
        """تحديث إحصائيات المورد"""
        from models import Payment
        
        confirmed_purchases = self.purchases.filter_by(status='confirmed').all()
        
        self.total_purchases_aed = sum(
            p.amount_aed or Decimal('0') for p in confirmed_purchases
        )
        
        # Calculate total paid from Payment table
        total_paid = db.session.query(db.func.sum(Payment.amount_aed)).filter(
            Payment.supplier_id == self.id,
            Payment.direction == 'outgoing',
            Payment.payment_confirmed == True
        ).scalar()
        
        self.total_paid_aed = total_paid or Decimal('0')
        
        if confirmed_purchases:
            self.last_purchase_date = max(p.purchase_date for p in confirmed_purchases)
    
    def to_dict(self):
        """تحويل إلى قاموس للـ API"""
        return {
            'id': self.id,
            'name': self.name,
            'name_en': self.name_en,
            'company_name': self.company_name,
            'phone': self.phone,
            'email': self.email,
            'supplier_type': self.supplier_type,
            'type_display': self.get_type_display(),
            'rating': self.rating,
            'rating_stars': self.get_rating_stars(),
            'balance_aed': float(self.get_balance_aed()),
            'total_purchases_aed': float(self.total_purchases_aed or 0),
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'country': self.country,
            'city': self.city
        }

