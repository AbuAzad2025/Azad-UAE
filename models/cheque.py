"""
نموذج الشيكات - Cheque Model
إدارة شاملة للشيكات الواردة والصادرة
"""

from datetime import datetime, timezone, timedelta
from extensions import db
from decimal import Decimal
from flask import current_app


class Cheque(db.Model):
    """
    نموذج الشيكات - وارد وصادر
    """
    __tablename__ = 'cheques'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    
    # معلومات الشيك الأساسية
    cheque_number = db.Column(db.String(50), nullable=False, unique=True, index=True)
    cheque_bank_number = db.Column(db.String(50), nullable=False)  # رقم الشيك من البنك
    
    # النوع: incoming (وارد) أو outgoing (صادر)
    cheque_type = db.Column(db.String(20), nullable=False, index=True)  # incoming, outgoing
    
    # البنك والمعلومات المصرفية
    bank_name = db.Column(db.String(200), nullable=False)
    bank_branch = db.Column(db.String(200))
    account_number = db.Column(db.String(100))
    
    # المبلغ والعملة
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(10), default='AED')
    exchange_rate = db.Column(db.Numeric(15, 6), default=Decimal('1.0'))  # سعر الصرف عند الإنشاء
    clearance_exchange_rate = db.Column(db.Numeric(15, 6))  # سعر الصرف عند الصرف الفعلي
    amount_aed = db.Column(db.Numeric(15, 2))  # المبلغ بالدرهم عند الإنشاء
    actual_amount_aed = db.Column(db.Numeric(15, 2))  # المبلغ الفعلي بالدرهم عند الصرف
    currency_gain_loss = db.Column(db.Numeric(15, 2), default=Decimal('0'))  # ربح/خسارة فرق العملة
    
    # التواريخ
    issue_date = db.Column(db.Date, nullable=False)  # تاريخ الإصدار
    due_date = db.Column(db.Date, nullable=False, index=True)  # تاريخ الاستحقاق
    deposit_date = db.Column(db.Date)  # تاريخ الإيداع في البنك
    clearance_date = db.Column(db.Date)  # تاريخ الصرف الفعلي (تأكيد البنك)
    cleared_date = db.Column(db.Date)  # تاريخ الصرف (alias for clearance_date)
    
    # الحالة
    status = db.Column(db.String(20), default='pending', index=True)
    # pending: معلق (استُلم الشيك)
    # deposited: مودع في البنك
    # cleared: تم الصرف (مؤكد من البنك)
    # bounced: مرتد (رُفض من البنك)
    # cancelled: ملغي
    # under_collection: تحت التحصيل
    
    # معلومات الطرف الآخر
    drawer_name = db.Column(db.String(200))  # اسم الساحب (للوارد)
    drawer_id_number = db.Column(db.String(50))  # رقم الهوية
    payee_name = db.Column(db.String(200))  # اسم المستفيد (للصادر)
    
    # الربط مع العمليات
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), index=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), index=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('receipts.id'), index=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), index=True)
    
    # ملاحظات وسبب الإرتداد
    notes = db.Column(db.Text)
    bounce_reason = db.Column(db.String(500))  # سبب الإرتداد
    
    # التحذيرات
    days_until_due = db.Column(db.Integer)  # أيام متبقية للاستحقاق
    is_overdue = db.Column(db.Boolean, default=False, index=True)  # متأخر
    alert_sent = db.Column(db.Boolean, default=False)  # تم إرسال تنبيه
    
    # الأرشفة
    is_active = db.Column(db.Boolean, default=True, index=True)
    archived_at = db.Column(db.DateTime)
    archive_reason = db.Column(db.String(500))
    
    # Meta
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Relationships
    customer = db.relationship('Customer', backref='cheques', foreign_keys=[customer_id])
    supplier = db.relationship('Supplier', backref='cheques', foreign_keys=[supplier_id])
    sale = db.relationship('Sale', backref='cheques', foreign_keys=[sale_id])
    receipt = db.relationship('Receipt', backref='cheques', foreign_keys=[receipt_id])
    expense = db.relationship('Expense', backref='cheques', foreign_keys=[expense_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])
    user = db.relationship('User', foreign_keys=[user_id])
    tenant = db.relationship('Tenant', backref='cheques', foreign_keys=[tenant_id])
    
    def __repr__(self):
        return f'<Cheque {self.cheque_number} - {self.cheque_type} - {self.status}>'
    
    @property
    def cheque_type_ar(self):
        """عرض نوع الشيك بالعربية للاستخدام في الرسائل والتقارير."""
        mapping = {
            'incoming': 'وارد',
            'outgoing': 'صادر',
        }
        return mapping.get(self.cheque_type, self.cheque_type or '')

    def update_status_based_on_date(self):
        """تحديث الحالة والتحذيرات حسب التاريخ"""
        if self.status in ['cleared', 'cancelled', 'bounced']:
            return
        
        today = datetime.now().date()
        
        # حساب الأيام المتبقية
        self.days_until_due = (self.due_date - today).days
        
        # التحقق من التأخير
        if today > self.due_date:
            self.is_overdue = True
        else:
            self.is_overdue = False
    
    def calculate_amount_aed(self):
        """حساب المبلغ بالدرهم"""
        if self.exchange_rate:
            self.amount_aed = self.amount * self.exchange_rate
        else:
            self.amount_aed = self.amount
    
    def receive_cheque(self):
        """تسجيل استلام الشيك الوارد - يُرجع القيد المحاسبي إن وُجد"""
        if self.cheque_type == 'incoming':
            from services.gl_service import GLService
            try:
                credit_account = GLService.get_customer_credit_account(self.customer) if self.customer_id else '1130'
                lines = [
                    {
                        'account': '1150',
                        'debit': self.amount_aed,
                        'credit': 0,
                        'description': f'استلام شيك رقم {self.cheque_bank_number}'
                    },
                    {
                        'account': credit_account,
                        'debit': 0,
                        'credit': self.amount_aed,
                        'description': f'استلام شيك من عميل - رقم {self.cheque_bank_number}'
                    }
                ]
                entry = GLService.post_entry(
                    lines=lines,
                    description=f'استلام شيك وارد رقم {self.cheque_bank_number}',
                    reference_type='cheque_receive',
                    reference_id=self.id,
                    branch_id=self.branch_id,
                )
                return entry
            except Exception as e:
                current_app.logger.error(f'Failed to create GL entry for cheque receipt {self.id}: {e}')
        return None
    
    def issue_cheque(self):
        """تسجيل إصدار الشيك الصادر"""
        if self.cheque_type == 'outgoing':
            from services.gl_service import GLService
            try:
                if self.supplier_id:
                    debit_account = '2110'
                elif self.customer_id:
                    debit_account = GLService.get_customer_credit_account(self.customer)
                else:
                    debit_account = '2110'
                lines = [
                    {
                        'account': debit_account,
                        'debit': self.amount_aed,
                        'credit': 0,
                        'description': f'إصدار شيك رقم {self.cheque_bank_number}'
                    },
                    {
                        'account': '2120',
                        'debit': 0,
                        'credit': self.amount_aed,
                        'description': f'إصدار شيك - رقم {self.cheque_bank_number}'
                    }
                ]
                
                entry = GLService.post_entry(
                    lines=lines,
                    description=f'إصدار شيك صادر رقم {self.cheque_bank_number}',
                    reference_type='cheque_issue',
                    reference_id=self.id,
                    branch_id=self.branch_id,
                )
                self.gl_journal_entry_id = entry.id
            except Exception as e:
                current_app.logger.error(f'Failed to create GL entry for cheque issue {self.id}: {e}')
    
    def deposit_cheque(self, deposit_date=None):
        """إيداع الشيك في البنك"""
        if self.status not in ['pending', 'under_collection']:
            raise ValueError(f'لا يمكن إيداع شيك بحالة: {self.status_ar}')
        
        self.status = 'deposited'
        self.deposit_date = deposit_date or datetime.now().date()
    
    def clear_cheque(self, clearance_date=None, clearance_exchange_rate=None):
        """تأكيد صرف الشيك من البنك - المحاسبة الحقيقية تبدأ هنا"""
        if self.status not in ['deposited', 'pending']:
            raise ValueError(f'لا يمكن تأكيد صرف شيك بحالة: {self.status_ar}')
        
        self.status = 'cleared'
        self.clearance_date = clearance_date or datetime.now().date()
        
        # حفظ سعر الصرف وقت الصرف إذا العملة مختلفة عن الدرهم
        if self.currency != 'AED' and clearance_exchange_rate:
            from services.currency_service import CurrencyService
            self.clearance_exchange_rate = Decimal(str(clearance_exchange_rate))
        elif self.currency != 'AED':
            # جلب السعر الحالي تلقائياً
            from services.currency_service import CurrencyService
            try:
                current_rate = CurrencyService.get_exchange_rate(self.currency, 'AED')
                self.clearance_exchange_rate = current_rate
            except:
                # إذا فشل جلب السعر، استخدم السعر الأصلي
                self.clearance_exchange_rate = self.exchange_rate
        else:
            # إذا العملة AED، السعر 1
            self.clearance_exchange_rate = Decimal('1.0')
        
        # حساب المبلغ الفعلي بالدرهم
        self.actual_amount_aed = self.amount * self.clearance_exchange_rate
        
        # حساب ربح/خسارة فرق العملة
        self.currency_gain_loss = self.actual_amount_aed - self.amount_aed
        
        # إنشاء قيد محاسبي تلقائي
        self._create_clearing_journal_entry()
        
        # تحديث الدفعة المرتبطة
        from models.payment import Payment, Receipt
        payment = Payment.query.filter_by(cheque_id=self.id).first()
        if payment:
            payment.confirm_payment()
        
        # تحديث السند المرتبط
        receipt = Receipt.query.filter_by(cheque_id=self.id).first()
        if receipt:
            receipt.confirm_receipt()
    
    def _create_clearing_journal_entry(self):
        """إنشاء القيد المحاسبي عند صرف الشيك"""
        from services.gl_service import GLService
        from extensions import db
        
        try:
            lines = []
            
            if self.cheque_type == 'incoming':
                # شيك وارد - نقل من "شيكات تحت التحصيل" إلى "البنك"
                lines.append({
                    'account': '1120',  # البنك
                    'debit': self.actual_amount_aed,
                    'credit': 0,
                    'description': f'صرف شيك وارد رقم {self.cheque_bank_number}'
                })
                lines.append({
                    'account': '1150',  # شيكات تحت التحصيل
                    'debit': 0,
                    'credit': self.amount_aed,
                    'description': f'صرف شيك رقم {self.cheque_bank_number}'
                })
                
                # إضافة ربح/خسارة فرق العملة إن وجد
                if self.currency_gain_loss and abs(self.currency_gain_loss) > Decimal('0.01'):
                    if self.currency_gain_loss > 0:
                        # ربح
                        lines.append({
                            'account': '4400',  # أرباح فرق العملة
                            'debit': 0,
                            'credit': abs(self.currency_gain_loss),
                            'description': f'ربح فرق عملة - شيك {self.cheque_bank_number}'
                        })
                    else:
                        # خسارة
                        lines.append({
                            'account': '6900',  # خسائر فرق العملة
                            'debit': abs(self.currency_gain_loss),
                            'credit': 0,
                            'description': f'خسارة فرق عملة - شيك {self.cheque_bank_number}'
                        })
            
            elif self.cheque_type == 'outgoing':
                # شيك صادر - نقل من "شيكات مؤجلة الدفع" إلى "البنك"
                lines.append({
                    'account': '2120',  # شيكات مؤجلة الدفع
                    'debit': self.amount_aed,
                    'credit': 0,
                    'description': f'صرف شيك صادر رقم {self.cheque_bank_number}'
                })
                lines.append({
                    'account': '1120',  # البنك
                    'debit': 0,
                    'credit': self.actual_amount_aed,
                    'description': f'صرف شيك رقم {self.cheque_bank_number}'
                })
                
                # إضافة ربح/خسارة فرق العملة إن وجد
                if self.currency_gain_loss and abs(self.currency_gain_loss) > Decimal('0.01'):
                    if self.currency_gain_loss > 0:
                        # خسارة (للشيك الصادر ربح فرق العملة يعتبر خسارة)
                        lines.append({
                            'account': '6900',  # خسائر فرق العملة
                            'debit': abs(self.currency_gain_loss),
                            'credit': 0,
                            'description': f'خسارة فرق عملة - شيك {self.cheque_bank_number}'
                        })
                    else:
                        # ربح
                        lines.append({
                            'account': '4400',  # أرباح فرق العملة
                            'debit': 0,
                            'credit': abs(self.currency_gain_loss),
                            'description': f'ربح فرق عملة - شيك {self.cheque_bank_number}'
                        })
            
            GLService.post_entry(
                lines=lines,
                description=f'صرف شيك {self.type_ar} رقم {self.cheque_bank_number}',
                reference_type='cheque_clear',
                reference_id=self.id,
                branch_id=self.branch_id,
            )
        
        except Exception as e:
            # لا نوقف العملية إذا فشل القيد المحاسبي
            current_app.logger.error(f'Failed to create GL entry for cheque {self.id}: {e}')
    
    def bounce_cheque(self, reason):
        """رفض الشيك من البنك - إرجاع الدين"""
        if self.status not in ['deposited', 'pending']:
            raise ValueError(f'لا يمكن رفض شيك بحالة: {self.status_ar}')
        
        self.status = 'bounced'
        self.bounce_reason = reason
        self.clearance_date = datetime.now().date()
        
        # إنشاء قيد محاسبي تلقائي للارتداد
        self._create_bounce_journal_entry()

        # إرجاع الدين على العميل عند ارتداد شيك وارد
        if self.cheque_type == 'incoming' and self.customer_id:
            try:
                self.customer.adjust_balance(self.amount_aed or Decimal('0'))
            except Exception:
                pass
        
        # إلغاء الدفعة المرتبطة
        from models.payment import Payment, Receipt
        payment = Payment.query.filter_by(cheque_id=self.id).first()
        if payment:
            payment.reject_payment(reason)
        
        # إلغاء السند المرتبط
        receipt = Receipt.query.filter_by(cheque_id=self.id).first()
        if receipt:
            receipt.reject_receipt(reason)
    
    def _create_bounce_journal_entry(self):
        """إنشاء القيد المحاسبي عند ارتداد الشيك"""
        from services.gl_service import GLService
        
        try:
            lines = []
            
            if self.cheque_type == 'incoming':
                ar_account = GLService.get_customer_credit_account(self.customer) if self.customer_id else '1130'
                lines.append({
                    'account': ar_account,
                    'debit': self.amount_aed,
                    'credit': 0,
                    'description': f'ارتداد شيك رقم {self.cheque_bank_number} - إرجاع الدين'
                })
                lines.append({
                    'account': '1150',  # شيكات تحت التحصيل
                    'debit': 0,
                    'credit': self.amount_aed,
                    'description': f'ارتداد شيك رقم {self.cheque_bank_number}'
                })
            
            elif self.cheque_type == 'outgoing':
                lines.append({
                    'account': '2120',  # شيكات مؤجلة الدفع
                    'debit': self.amount_aed,
                    'credit': 0,
                    'description': f'ارتداد شيك صادر رقم {self.cheque_bank_number}'
                })
                if self.supplier_id:
                    credit_account = '2110'
                elif self.customer_id:
                    credit_account = GLService.get_customer_credit_account(self.customer)
                else:
                    credit_account = '2110'
                lines.append({
                    'account': credit_account,
                    'debit': 0,
                    'credit': self.amount_aed,
                    'description': f'ارتداد شيك رقم {self.cheque_bank_number} - إرجاع الالتزام'
                })
            
            GLService.post_entry(
                lines=lines,
                description=f'ارتداد شيك {self.cheque_type_ar} رقم {self.cheque_bank_number}',
                reference_type='cheque_bounce',
                reference_id=self.id,
                branch_id=self.branch_id,
            )
        
        except Exception as e:
            current_app.logger.error(f'Failed to create GL entry for bounced cheque {self.id}: {e}')
    
    def cancel_cheque(self, reason=None):
        """إلغاء الشيك - عكس القيود المحاسبية"""
        if self.status == 'cancelled':
            return

        self.status = 'cancelled'
        if reason:
            self.notes = (self.notes or '') + f'\nسبب الإلغاء: {reason}'
        
        # عكس القيد المحاسبي للإلغاء
        self._create_cancel_journal_entry()

    def _create_cancel_journal_entry(self):
        """إنشاء قيد عكسي عند إلغاء الشيك"""
        from services.gl_service import GLService
        try:
            # إذا لم يكن للشيك قيد سابق (مثلاً جديد)، لا داعي للعكس
            # ولكن للضمان، نعكس بناءً على النوع والحالة السابقة
            # ملاحظة: الحالة تغيرت بالفعل إلى cancelled، لذا نعتمد على النوع
            
            lines = []
            if self.cheque_type == 'incoming':
                ar_account = GLService.get_customer_credit_account(self.customer) if self.customer_id else '1130'
                lines = [
                    {
                        'account': ar_account,
                        'debit': self.amount_aed,
                        'credit': 0,
                        'description': f'إلغاء شيك وارد رقم {self.cheque_bank_number}'
                    },
                    {
                        'account': '1150',
                        'debit': 0,
                        'credit': self.amount_aed,
                        'description': f'إلغاء شيك رقم {self.cheque_bank_number}'
                    }
                ]
            
            elif self.cheque_type == 'outgoing':
                if self.supplier_id:
                    credit_account = '2110'
                elif self.customer_id:
                    credit_account = GLService.get_customer_credit_account(self.customer)
                else:
                    credit_account = '2110'
                lines = [
                    {
                        'account': '2120',
                        'debit': self.amount_aed,
                        'credit': 0,
                        'description': f'إلغاء شيك صادر رقم {self.cheque_bank_number}'
                    },
                    {
                        'account': credit_account,
                        'debit': 0,
                        'credit': self.amount_aed,
                        'description': f'إلغاء شيك رقم {self.cheque_bank_number}'
                    }
                ]

            if lines:
                GLService.post_entry(
                    lines=lines,
                    description=f'إلغاء شيك {self.type_ar} رقم {self.cheque_bank_number}',
                    reference_type='cheque_cancel',
                    reference_id=self.id,
                    branch_id=self.branch_id,
                )
        except Exception as e:
            current_app.logger.error(f'Failed to create GL entry for cancelled cheque {self.id}: {e}')

    def archive(self, reason=None):
        """أرشفة الشيك - مع عكس القيد إذا كان نشطاً"""
        # إذا كان الشيك نشطاً (معلق/مودع/تحت التحصيل) يجب عكس تأثيره المالي قبل الأرشفة
        if self.is_active and self.status in ['pending', 'deposited', 'under_collection']:
             # نعتبر الأرشفة للشيك النشط بمثابة إلغاء محاسبي
             self._create_cancel_journal_entry()

        self.is_active = False
        self.archived_at = datetime.now(timezone.utc)
        if reason:
            self.archive_reason = reason
    
    def restore(self):
        """استعادة من الأرشيف"""
        self.is_active = True
        self.archived_at = None
        self.archive_reason = None
    
    @property
    def is_due_soon(self):
        """شيك قريب الاستحقاق (خلال 7 أيام)"""
        return self.days_until_due is not None and 0 <= self.days_until_due <= 7
    
    @property
    def status_ar(self):
        """الحالة بالعربي"""
        statuses = {
            'pending': 'معلق (استُلم)',
            'deposited': 'مودع في البنك',
            'cleared': 'مصروف',
            'bounced': 'مرتد',
            'cancelled': 'ملغي',
            'under_collection': 'تحت التحصيل'
        }
        return statuses.get(self.status, self.status)
    
    @property
    def is_confirmed(self):
        """هل الشيك مؤكد الصرف (يُحسب في الإيرادات الفعلية)"""
        return self.status == 'cleared'
    
    @property
    def is_pending(self):
        """هل الشيك معلّق (لا يُحسب في الإيرادات الفعلية)"""
        return self.status in ['pending', 'deposited', 'under_collection']
    
    @property
    def type_ar(self):
        """النوع بالعربي"""
        types = {
            'incoming': 'وارد',
            'outgoing': 'صادر'
        }
        return types.get(self.cheque_type, self.cheque_type)
    
    def to_dict(self):
        """تحويل إلى dict"""
        return {
            'id': self.id,
            'cheque_number': self.cheque_number,
            'cheque_bank_number': self.cheque_bank_number,
            'cheque_type': self.cheque_type,
            'type_ar': self.type_ar,
            'bank_name': self.bank_name,
            'amount': float(self.amount),
            'currency': self.currency,
            'exchange_rate': float(self.exchange_rate) if self.exchange_rate else 1.0,
            'clearance_exchange_rate': float(self.clearance_exchange_rate) if self.clearance_exchange_rate else None,
            'amount_aed': float(self.amount_aed) if self.amount_aed else 0,
            'actual_amount_aed': float(self.actual_amount_aed) if self.actual_amount_aed else None,
            'currency_gain_loss': float(self.currency_gain_loss) if self.currency_gain_loss else 0,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'due_date': self.due_date.isoformat() if self.due_date else None,
            'clearance_date': self.clearance_date.isoformat() if self.clearance_date else None,
            'status': self.status,
            'status_ar': self.status_ar,
            'days_until_due': self.days_until_due,
            'is_overdue': self.is_overdue,
            'is_due_soon': self.is_due_soon,
            'drawer_name': self.drawer_name,
            'payee_name': self.payee_name,
            'customer_id': self.customer_id,
            'supplier_id': self.supplier_id,
        }
    
    @staticmethod
    def get_incoming_cheques(customer_id=None, status=None):
        """الشيكات الواردة"""
        query = Cheque.query.filter_by(cheque_type='incoming', is_active=True)
        
        if customer_id:
            query = query.filter_by(customer_id=customer_id)
        
        if status:
            query = query.filter_by(status=status)
        
        return query.order_by(Cheque.due_date).all()
    
    @staticmethod
    def get_outgoing_cheques(supplier_id=None, status=None):
        """الشيكات الصادرة"""
        query = Cheque.query.filter_by(cheque_type='outgoing', is_active=True)
        
        if supplier_id:
            query = query.filter_by(supplier_id=supplier_id)
        
        if status:
            query = query.filter_by(status=status)
        
        return query.order_by(Cheque.due_date).all()
    
    @staticmethod
    def get_due_soon_cheques(branch_id=None):
        """الشيكات القريبة من الاستحقاق (7 أيام)"""
        Cheque.update_all_statuses(branch_id=branch_id)
        query = Cheque.query.filter(
            Cheque.is_active == True,
            Cheque.status == 'pending',
            Cheque.days_until_due <= 7,
            Cheque.days_until_due >= 0
        )
        if branch_id is not None:
            query = query.filter(Cheque.branch_id == branch_id)
        return query.order_by(Cheque.due_date).all()
    
    @staticmethod
    def get_overdue_cheques(branch_id=None):
        """الشيكات المتأخرة"""
        Cheque.update_all_statuses(branch_id=branch_id)
        query = Cheque.query.filter(
            Cheque.is_active == True,
            Cheque.status == 'pending',
            Cheque.is_overdue == True
        )
        if branch_id is not None:
            query = query.filter(Cheque.branch_id == branch_id)
        return query.order_by(Cheque.due_date).all()
    
    @staticmethod
    def update_all_statuses(branch_id=None):
        """تحديث حالة كل الشيكات"""
        query = Cheque.query.filter_by(status='pending', is_active=True)
        if branch_id is not None:
            query = query.filter(Cheque.branch_id == branch_id)
        pending_cheques = query.all()
        
        for cheque in pending_cheques:
            cheque.update_status_based_on_date()
        
        db.session.commit()
    
    @staticmethod
    def get_statistics(branch_id=None):
        """إحصائيات الشيكات"""
        base_query = Cheque.query.filter_by(is_active=True)
        if branch_id is not None:
            base_query = base_query.filter(Cheque.branch_id == branch_id)

        total_incoming = base_query.filter_by(cheque_type='incoming').count()
        total_outgoing = base_query.filter_by(cheque_type='outgoing').count()
        
        pending_incoming = base_query.filter_by(
            cheque_type='incoming', 
            status='pending', 
        ).count()
        
        pending_outgoing = base_query.filter_by(
            cheque_type='outgoing', 
            status='pending', 
        ).count()
        
        # المبالغ
        incoming_amount_query = db.session.query(
            db.func.sum(Cheque.amount_aed)
        ).filter_by(
            cheque_type='incoming',
            status='pending',
            is_active=True
        )
        if branch_id is not None:
            incoming_amount_query = incoming_amount_query.filter(Cheque.branch_id == branch_id)
        incoming_amount = incoming_amount_query.scalar() or Decimal('0')
        
        outgoing_amount_query = db.session.query(
            db.func.sum(Cheque.amount_aed)
        ).filter_by(
            cheque_type='outgoing',
            status='pending',
            is_active=True
        )
        if branch_id is not None:
            outgoing_amount_query = outgoing_amount_query.filter(Cheque.branch_id == branch_id)
        outgoing_amount = outgoing_amount_query.scalar() or Decimal('0')
        
        # المتأخرة
        overdue_query = Cheque.query.filter_by(
            status='pending',
            is_active=True,
            is_overdue=True
        )
        if branch_id is not None:
            overdue_query = overdue_query.filter(Cheque.branch_id == branch_id)
        overdue = overdue_query.count()
        
        # القريبة من الاستحقاق
        due_soon_query = Cheque.query.filter(
            Cheque.status == 'pending',
            Cheque.is_active == True,
            Cheque.days_until_due <= 7,
            Cheque.days_until_due >= 0
        )
        if branch_id is not None:
            due_soon_query = due_soon_query.filter(Cheque.branch_id == branch_id)
        due_soon = due_soon_query.count()
        
        return {
            'total_incoming': total_incoming,
            'total_outgoing': total_outgoing,
            'pending_incoming': pending_incoming,
            'pending_outgoing': pending_outgoing,
            'incoming_amount': float(incoming_amount),
            'outgoing_amount': float(outgoing_amount),
            'overdue': overdue,
            'due_soon': due_soon,
            'bounced': base_query.filter_by(status='bounced').count(),
        }

