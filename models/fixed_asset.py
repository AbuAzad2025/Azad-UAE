"""
نموذج الأصول الثابتة والاستهلاك - Fixed Assets & Depreciation Model
"""

from datetime import datetime, timezone, date
from extensions import db
from decimal import Decimal, ROUND_HALF_UP


class FixedAsset(db.Model):
    """
    الأصول الثابتة
    """
    __tablename__ = 'fixed_assets'
    
    id = db.Column(db.Integer, primary_key=True)
    asset_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name_ar = db.Column(db.String(200), nullable=False)
    name_en = db.Column(db.String(200))
    description = db.Column(db.Text)
    
    # التصنيف
    category = db.Column(db.String(50), index=True)  # land, building, vehicle, equipment, furniture
    
    # الحسابات المحاسبية
    asset_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'), nullable=False)  # حساب الأصل
    depreciation_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'))  # مجمع الاستهلاك
    expense_account_id = db.Column(db.Integer, db.ForeignKey('gl_accounts.id'))  # مصروف الاستهلاك
    
    # التكلفة
    purchase_date = db.Column(db.Date, nullable=False, index=True)
    purchase_price = db.Column(db.Numeric(18, 3), nullable=False)
    salvage_value = db.Column(db.Numeric(18, 3), default=0)  # القيمة الإنقاذية (في نهاية العمر)
    
    # الاستهلاك
    depreciation_method = db.Column(db.String(30), default='straight_line')  # straight_line, declining_balance
    useful_life_years = db.Column(db.Integer, nullable=False)  # العمر الإنتاجي بالسنوات
    useful_life_months = db.Column(db.Integer)  # أو بالأشهر
    
    # القيم المحسوبة
    accumulated_depreciation = db.Column(db.Numeric(18, 3), default=0)  # مجمع الاستهلاك
    book_value = db.Column(db.Numeric(18, 3))  # القيمة الدفترية
    last_depreciation_date = db.Column(db.Date)  # آخر تاريخ استهلاك
    
    # الموقع
    location = db.Column(db.String(200))
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'))
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # New Branch ID
    
    # الحالة
    status = db.Column(db.String(20), default='active', index=True)
    # active: نشط
    # fully_depreciated: مستهلك بالكامل
    # disposed: تم التخلص منه
    # sold: تم بيعه
    
    disposal_date = db.Column(db.Date)
    disposal_price = db.Column(db.Numeric(18, 3))
    disposal_gain_loss = db.Column(db.Numeric(18, 3))  # ربح/خسارة البيع
    
    notes = db.Column(db.Text)
    
    # Meta
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    asset_account = db.relationship('GLAccount', foreign_keys=[asset_account_id])
    depreciation_account = db.relationship('GLAccount', foreign_keys=[depreciation_account_id])
    expense_account = db.relationship('GLAccount', foreign_keys=[expense_account_id])
    cost_center = db.relationship('CostCenter')
    branch = db.relationship('Branch', backref='assets', foreign_keys=[branch_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    depreciation_schedules = db.relationship('DepreciationSchedule', back_populates='asset', 
                                            cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<FixedAsset {self.asset_number} - {self.name_ar}>'
    
    @property
    def category_ar(self):
        """التصنيف بالعربي"""
        categories = {
            'land': 'أراضي',
            'building': 'مباني',
            'vehicle': 'سيارات',
            'equipment': 'معدات',
            'furniture': 'أثاث',
            'computer': 'أجهزة كمبيوتر'
        }
        return categories.get(self.category, self.category)
    
    @property
    def status_ar(self):
        """الحالة بالعربي"""
        statuses = {
            'active': 'نشط',
            'fully_depreciated': 'مستهلك بالكامل',
            'disposed': 'تم التخلص منه',
            'sold': 'تم بيعه'
        }
        return statuses.get(self.status, self.status)
    
    @property
    def depreciable_amount(self):
        """المبلغ القابل للاستهلاك"""
        return self.purchase_price - self.salvage_value
    
    @property
    def remaining_book_value(self):
        """القيمة الدفترية المتبقية"""
        return self.purchase_price - self.accumulated_depreciation
    
    def calculate_monthly_depreciation(self):
        """حساب الاستهلاك الشهري"""
        if self.category == 'land':
            return Decimal('0')  # الأراضي لا تستهلك
        
        if self.depreciation_method == 'straight_line':
            # القسط الثابت
            months = self.useful_life_years * 12
            monthly = (self.depreciable_amount / months).quantize(Decimal('0.01'), ROUND_HALF_UP)
            return monthly
        
        elif self.depreciation_method == 'declining_balance':
            # القسط المتناقص المضاعف (Double Declining Balance)
            rate = Decimal('2') / Decimal(str(self.useful_life_years))
            current_book_value = self.remaining_book_value
            
            # لا نستهلك أقل من القيمة الإنقاذية
            if current_book_value <= self.salvage_value:
                return Decimal('0')
            
            annual_depreciation = current_book_value * rate
            monthly = (annual_depreciation / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
            
            # التأكد من عدم تجاوز القيمة الإنقاذية
            if current_book_value - monthly < self.salvage_value:
                monthly = current_book_value - self.salvage_value
            
            return monthly
        
        return Decimal('0')
    
    def post_depreciation(self, period_date=None):
        """
        ترحيل الاستهلاك الشهري
        """
        if self.status != 'active':
            raise ValueError('الأصل غير نشط')
        
        if not period_date:
            period_date = date.today()
        
        # التحقق من عدم الاستهلاك المكرر
        existing = DepreciationSchedule.query.filter_by(
            asset_id=self.id,
            period_date=period_date
        ).first()
        
        if existing:
            raise ValueError('تم ترحيل الاستهلاك لهذا الشهر مسبقاً')
        
        # حساب الاستهلاك
        depreciation_amount = self.calculate_monthly_depreciation()
        
        if depreciation_amount == 0:
            return None
        
        # إنشاء قيد محاسبي
        from services.gl_service import GLService
        
        lines = [
            {
                'account': str(self.expense_account.code),
                'debit': depreciation_amount,
                'credit': 0,
                'description': f'استهلاك شهري - {self.name_ar}'
            },
            {
                'account': str(self.depreciation_account.code),
                'debit': 0,
                'credit': depreciation_amount,
                'description': f'مجمع استهلاك - {self.name_ar}'
            }
        ]
        
        entry = GLService.post_entry(
            lines=lines,
            description=f'قيد استهلاك شهري - {self.asset_number}',
            reference_type='depreciation',
            reference_id=self.id,
            branch_id=self.branch_id
        )
        
        # تحديث الأصل
        self.accumulated_depreciation += depreciation_amount
        self.book_value = self.remaining_book_value
        self.last_depreciation_date = period_date
        
        # إنشاء سجل في جدول الاستهلاك
        schedule = DepreciationSchedule(
            asset_id=self.id,
            period_date=period_date,
            depreciation_amount=depreciation_amount,
            accumulated_depreciation=self.accumulated_depreciation,
            book_value=self.book_value,
            journal_entry_id=entry.id
        )
        db.session.add(schedule)
        
        # التحقق من الاستهلاك الكامل
        if self.book_value <= self.salvage_value:
            self.status = 'fully_depreciated'
        
        db.session.commit()
        return schedule
    
    def dispose(self, disposal_date, disposal_price, notes=None):
        """
        التخلص من الأصل (بيع أو إتلاف)
        """
        if self.status in ['disposed', 'sold']:
            raise ValueError('تم التخلص من الأصل مسبقاً')
        
        self.status = 'sold' if disposal_price > 0 else 'disposed'
        self.disposal_date = disposal_date
        self.disposal_price = Decimal(str(disposal_price))
        
        # حساب ربح/خسارة البيع
        self.disposal_gain_loss = self.disposal_price - self.book_value
        
        if notes:
            self.notes = (self.notes or '') + f'\n{notes}'
        
        # إنشاء قيد محاسبي للتخلص
        from services.gl_service import GLService
        
        lines = []
        
        # إزالة الأصل من الدفاتر
        lines.append({
            'account': str(self.depreciation_account.code),
            'debit': self.accumulated_depreciation,
            'credit': 0,
            'description': f'إقفال مجمع استهلاك - {self.name_ar}'
        })
        
        if self.disposal_price > 0:
            # بيع
            lines.append({
                'account': '1120',  # البنك (أو الصندوق)
                'debit': self.disposal_price,
                'credit': 0,
                'description': f'ثمن بيع الأصل - {self.name_ar}'
            })
        
        # ربح أو خسارة
        if self.disposal_gain_loss > 0:
            # ربح بيع
            lines.append({
                'account': '4500',  # إيرادات أخرى
                'debit': 0,
                'credit': self.disposal_gain_loss,
                'description': f'ربح بيع أصل - {self.name_ar}'
            })
        elif self.disposal_gain_loss < 0:
            # خسارة بيع
            lines.append({
                'account': '6990',  # مصروفات متنوعة
                'debit': abs(self.disposal_gain_loss),
                'credit': 0,
                'description': f'خسارة بيع/إتلاف أصل - {self.name_ar}'
            })
        
        lines.append({
            'account': str(self.asset_account.code),
            'debit': 0,
            'credit': self.purchase_price,
            'description': f'إقفال حساب الأصل - {self.name_ar}'
        })
        
        disposal_type = 'بيع' if self.disposal_price > 0 else 'إتلاف'
        GLService.post_entry(
            lines=lines,
            description=f'قيد {disposal_type} أصل - {self.asset_number}',
            reference_type='asset_disposal',
            reference_id=self.id,
            branch_id=self.branch_id
        )
        
        db.session.commit()


class DepreciationSchedule(db.Model):
    """
    جدول الاستهلاك - سجل استهلاك شهري
    """
    __tablename__ = 'depreciation_schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id'), nullable=False, index=True)
    
    period_date = db.Column(db.Date, nullable=False, index=True)  # نهاية الشهر/الفترة
    depreciation_amount = db.Column(db.Numeric(18, 3), nullable=False)
    accumulated_depreciation = db.Column(db.Numeric(18, 3), nullable=False)
    book_value = db.Column(db.Numeric(18, 3), nullable=False)
    
    # الربط بالقيد المحاسبي
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('gl_journal_entries.id'))
    
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    asset = db.relationship('FixedAsset', back_populates='depreciation_schedules')
    journal_entry = db.relationship('GLJournalEntry')
    
    def __repr__(self):
        return f'<DepreciationSchedule {self.asset_id} - {self.period_date}>'

