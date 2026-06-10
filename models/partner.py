"""
Partner / Shareholder Model — نظام الشركاء والمساهمين

Supports 3 partnership scopes:
  • company   — شريك في الشركة (رأس مال + نسبة أرباح)
  • branch    — شريك في فرع محدد (استثمار + نسبة أرباح الفرع)
  • warehouse — شريك في مستودع (بضاعة + نسبة مبيعات)

Partner types:
  • investor         — شريك استثماري (صامت)
  • working_partner  — شريك عامل (يشتغل + نسبة)
  • silent_partner   — شريك صامت (فقط استثمار)
  • branch_partner   — شريك فرع (مستوى فرع)
  • warehouse_partner— شريك مستودع (مستوى مستودع)
"""
from datetime import datetime, timezone
from extensions import db


class Partner(db.Model):
    __tablename__ = 'partners'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'code', name='uq_partners_tenant_code'),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    # Identity
    name = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200))
    code = db.Column(db.String(50), nullable=True, index=True)

    # Partnership scope
    scope_type = db.Column(db.String(20), default='company', nullable=False)
    # 'company' | 'branch' | 'warehouse'

    scope_id = db.Column(db.Integer, nullable=True, index=True)
    # FK to branch.id or warehouse.id (NULL for company-level)

    partner_type = db.Column(db.String(30), default='investor', nullable=False)
    # 'investor' | 'working_partner' | 'silent_partner' |
    # 'branch_partner' | 'warehouse_partner'

    # Contact
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    id_number = db.Column(db.String(100))  # رقم الهوية/السجل التجاري

    # Financial terms
    investment_amount = db.Column(db.Numeric(15, 3), default=0)
    # رأس المال المستثمر

    share_percentage = db.Column(db.Numeric(5, 2), default=0)
    # نسبة الربح (0–100)

    fixed_monthly_amount = db.Column(db.Numeric(15, 3), default=0)
    # مبلغ ثابت شهري (للعاملين مثلاً)

    expense_share_percentage = db.Column(db.Numeric(5, 2), default=0)
    # نسبة تحمل المصاريف التشغيلية

    loss_share_percentage = db.Column(db.Numeric(5, 2), default=0)
    # نسبة تحمل الخسارة (قد تختلف عن نسبة الربح)

    min_profit_threshold = db.Column(db.Numeric(15, 3), default=0)
    # الحد الأدنى للربح قبل بدء التوزيع

    # Balance tracking
    current_balance = db.Column(db.Numeric(15, 3), default=0)
    # الرصيد الجاري (أرباح مستحقة - مسحوبات)

    total_profit_received = db.Column(db.Numeric(15, 3), default=0)
    total_loss_borne = db.Column(db.Numeric(15, 3), default=0)
    total_withdrawals = db.Column(db.Numeric(15, 3), default=0)
    total_additional_investment = db.Column(db.Numeric(15, 3), default=0)

    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    start_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    end_date = db.Column(db.Date, nullable=True)

    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    distributions = db.relationship('PartnerProfitDistribution',
                                     backref='partner',
                                     lazy='dynamic',
                                     cascade='all, delete-orphan')
    transactions = db.relationship('PartnerTransaction',
                                    backref='partner',
                                    lazy='dynamic',
                                    cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Partner {self.name} ({self.share_percentage}%)>'

    @property
    def scope_label(self):
        if self.scope_type == 'company':
            return 'مستوى الشركة'
        elif self.scope_type == 'branch':
            return f'فرع #{self.scope_id}'
        elif self.scope_type == 'warehouse':
            return f'مستودع #{self.scope_id}'
        return '—'

    @property
    def partner_type_label(self):
        labels = {
            'investor': 'شريك استثماري',
            'working_partner': 'شريك عامل',
            'silent_partner': 'شريك صامت',
            'branch_partner': 'شريك فرع',
            'warehouse_partner': 'شريك مستودع',
        }
        return labels.get(self.partner_type, self.partner_type)

    @property
    def net_investment(self):
        """الاستثمار الصافي = رأس المال + إضافي - مسحوبات"""
        inv = float(self.investment_amount or 0)
        add = float(self.total_additional_investment or 0)
        wd = float(self.total_withdrawals or 0)
        return inv + add - wd

    def get_balance_summary(self):
        return {
            'investment': float(self.investment_amount or 0),
            'current_balance': float(self.current_balance or 0),
            'total_profit': float(self.total_profit_received or 0),
            'total_loss': float(self.total_loss_borne or 0),
            'total_withdrawals': float(self.total_withdrawals or 0),
            'net_investment': self.net_investment,
        }
