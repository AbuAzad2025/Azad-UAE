from decimal import Decimal
from datetime import datetime, timezone
from extensions import db
from models import GLAccount, GLJournalEntry, GLJournalLine, Currency
from utils.helpers import generate_number

_JE_SEQ = {}

# مرجع الحسابات: استخدم هذه الرموز للقيود لضمان الاتساق
# أصول: 1110 صندوق، 1120 بنك، 1130 ذمم مدينة، 1140 مخزون، 1150 شيكات تحت التحصيل، 1160 سلف موظفين
# خصوم: 2110 ذمم دائنة، 2115 ذمم تجار، 2120 شيكات مؤجلة، 2130 ضرائب، 2140 رواتب مستحقة
# إيرادات: 4100 مبيعات، 4200 خدمات، 4300 شحن، 4400 أرباح فرق عملة، 4500 أخرى
# مصروفات: 5100 تكلفة بضاعة، 5150 تعديلات مخزون، 5200 خصومات ممنوحة، 6100 رواتب، 6900 خسائر فرق عملة، 6990 متنوعة
GL_ACCOUNTS = {
    'cash': '1110',
    'bank': '1120',
    'bank_savings': '1121',
    'receivable': '1130',
    'inventory': '1140',
    'cheques_under_collection': '1150',
    'employee_advances': '1160',
    'payable': '2110',
    'merchants_payable': '2115',
    'deferred_cheques': '2120',
    'tax_payable': '2130',
    'salaries_payable': '2140',
    'sales_revenue': '4100',
    'service_revenue': '4200',
    'shipping_revenue': '4300',
    'fx_gain': '4400',
    'other_revenue': '4500',
    'cogs': '5100',
    'inventory_adjustments': '5150',
    'discounts_given': '5200',
    'salaries_expense': '6100',
    'rent': '6200',
    'utilities': '6300',
    'maintenance': '6400',
    'fx_loss': '6900',
    'bank_charges': '6950',
    'misc_expense': '6990',
}

class GLService:












    @staticmethod
    def create_journal_entry(date, description, lines, user_id=None, branch_id=None, reference_type=None, reference_id=None):
        """Standardized GL Entry Creation"""
        
        # Determine entry number
        y = date.strftime('%Y')
        latest = GLJournalEntry.query.filter(GLJournalEntry.entry_number.like(f'JE-{y}-%')).order_by(GLJournalEntry.entry_number.desc()).first()
        last_num = 0
        if latest:
            try:
                last_num = int(latest.entry_number.split('-')[-1])
            except:
                pass
        next_num = last_num + 1
        entry_number = f'JE-{y}-{next_num:04d}'
        
        entry = GLJournalEntry(
            entry_number=entry_number,
            entry_date=date,
            description=description,
            created_by=user_id,
            branch_id=branch_id,
            entry_type='auto',
            is_posted=True,
            reference_type=reference_type,
            reference_id=reference_id
        )
        db.session.add(entry)
        db.session.flush()
        
        total_debit = 0
        total_credit = 0
        
        for line in lines:
            account = GLAccount.query.filter_by(code=line['account_code']).first()
            if not account:
                if line['account_code'] == '1160':
                    account = GLAccount(code='1160', name='Employee Advances', name_ar='سلف الموظفين', type='asset', parent_id=None)
                    db.session.add(account)
                    db.session.flush()
                else:
                    raise ValueError(f"GL Account not found: {line['account_code']}")
            if getattr(account, 'is_header', False):
                raise ValueError(f"لا يمكن القيد على الحساب الرئيسي: {getattr(account, 'full_name', account.code)}")
            debit = Decimal(str(line.get('debit', 0)))
            credit = Decimal(str(line.get('credit', 0)))
            
            gl_line = GLJournalLine(
                entry_id=entry.id,
                account_id=account.id,
                debit=debit,
                credit=credit,
                description=line.get('description', description),
                amount_aed=debit - credit # Simplified
            )
            db.session.add(gl_line)
            total_debit += debit
            total_credit += credit
            
        entry.total_debit = total_debit
        entry.total_credit = total_credit

        if abs(total_debit - total_credit) > Decimal('0.001'):
            raise ValueError(f'القيد غير متوازن: مدين={total_debit} دائن={total_credit}')
            
        return entry

    @staticmethod
    def ensure_core_accounts():
        """Create enhanced GL accounts with hierarchical structure"""
        # (code, name_ar, name_en, type, parent_code, is_header, level)
        core = [
            # === الأصول Assets ===
            ('1000', 'الأصول', 'Assets', 'asset', None, True, 0),
            ('1100', 'الأصول المتداولة', 'Current Assets', 'asset', '1000', True, 1),
            ('1110', 'الصندوق', 'Cash', 'asset', '1100', False, 2),
            ('1120', 'البنك - حساب جاري', 'Bank - Current Account', 'asset', '1100', False, 2),
            ('1121', 'البنك - حساب توفير', 'Bank - Savings Account', 'asset', '1100', False, 2),
            ('1130', 'الذمم المدينة', 'Accounts Receivable', 'asset', '1100', False, 2),
            ('1140', 'المخزون', 'Inventory', 'asset', '1100', False, 2),
            ('1150', 'شيكات تحت التحصيل', 'Cheques Under Collection', 'asset', '1100', False, 2),
            ('1160', 'سلف الموظفين', 'Employee Advances', 'asset', '1100', False, 2),
            
            ('1200', 'الأصول الثابتة', 'Fixed Assets', 'asset', '1000', True, 1),
            ('1210', 'أراضي', 'Land', 'asset', '1200', False, 2),
            ('1220', 'مباني', 'Buildings', 'asset', '1200', False, 2),
            ('1230', 'سيارات', 'Vehicles', 'asset', '1200', False, 2),
            ('1240', 'معدات', 'Equipment', 'asset', '1200', False, 2),
            ('1250', 'أثاث', 'Furniture', 'asset', '1200', False, 2),
            
            # === الخصوم Liabilities ===
            ('2000', 'الخصوم', 'Liabilities', 'liability', None, True, 0),
            ('2100', 'الخصوم المتداولة', 'Current Liabilities', 'liability', '2000', True, 1),
            ('2110', 'الذمم الدائنة', 'Accounts Payable', 'liability', '2100', False, 2),
            ('2115', 'ذمم التجار', 'Merchants Payable', 'liability', '2100', False, 2),
            ('2120', 'شيكات مؤجلة الدفع', 'Deferred Cheques Payable', 'liability', '2100', False, 2),
            ('2130', 'ضرائب مستحقة', 'Taxes Payable', 'liability', '2100', False, 2),
            ('2140', 'رواتب مستحقة', 'Salaries Payable', 'liability', '2100', False, 2),
            
            ('2200', 'الخصوم طويلة الأجل', 'Long-term Liabilities', 'liability', '2000', True, 1),
            ('2210', 'قروض', 'Loans', 'liability', '2200', False, 2),
            
            # === حقوق الملكية Equity ===
            ('3000', 'حقوق الملكية', 'Equity', 'equity', None, True, 0),
            ('3100', 'رأس المال', 'Capital', 'equity', '3000', False, 1),
            ('3200', 'الأرباح المحتجزة', 'Retained Earnings', 'equity', '3000', False, 1),
            ('3300', 'جاري المالك', 'Owner Draw', 'equity', '3000', False, 1),
            ('3350', 'جاري الشركاء', 'Partners Current Account', 'equity', '3000', False, 1),
            ('3400', 'أرباح السنة الحالية', 'Current Year Profit', 'equity', '3000', False, 1),
            
            # === الإيرادات Revenues ===
            ('4000', 'الإيرادات', 'Revenues', 'revenue', None, True, 0),
            ('4100', 'إيرادات المبيعات', 'Sales Revenue', 'revenue', '4000', False, 1),
            ('4200', 'إيرادات الخدمات', 'Service Revenue', 'revenue', '4000', False, 1),
            ('4300', 'إيرادات الشحن', 'Shipping Revenue', 'revenue', '4000', False, 1),
            ('4400', 'أرباح فرق العملة', 'Foreign Exchange Gain', 'revenue', '4000', False, 1),
            ('4500', 'إيرادات أخرى', 'Other Revenue', 'revenue', '4000', False, 1),
            
            # === المصروفات Expenses ===
            ('5000', 'تكلفة المبيعات', 'Cost of Sales', 'expense', None, True, 0),
            ('5100', 'تكلفة البضاعة المباعة', 'Cost of Goods Sold', 'expense', '5000', False, 1),
            ('5150', 'تعديلات المخزون', 'Inventory Adjustments', 'expense', '5000', False, 1),
            ('5200', 'الخصومات الممنوحة', 'Discounts Given', 'expense', '5000', False, 1),
            ('5300', 'مصروفات الشحن', 'Shipping Expense', 'expense', '5000', False, 1),
            
            ('6000', 'المصروفات التشغيلية', 'Operating Expenses', 'expense', None, True, 0),
            ('6100', 'رواتب وأجور', 'Salaries & Wages', 'expense', '6000', False, 1),
            ('6200', 'إيجار', 'Rent', 'expense', '6000', False, 1),
            ('6300', 'كهرباء وماء', 'Utilities', 'expense', '6000', False, 1),
            ('6400', 'صيانة', 'Maintenance', 'expense', '6000', False, 1),
            ('6500', 'تسويق وإعلان', 'Marketing & Advertising', 'expense', '6000', False, 1),
            ('6600', 'مواصلات', 'Transportation', 'expense', '6000', False, 1),
            ('6700', 'اتصالات', 'Communications', 'expense', '6000', False, 1),
            ('6800', 'قرطاسية', 'Stationery', 'expense', '6000', False, 1),
            ('6900', 'خسائر فرق العملة', 'Foreign Exchange Loss', 'expense', '6000', False, 1),
            ('6950', 'مصروفات بنكية', 'Bank Charges', 'expense', '6000', False, 1),
            ('6990', 'مصروفات متنوعة', 'Miscellaneous Expenses', 'expense', '6000', False, 1),
        ]
        
        created_any = False
        created_cache = {}
        
        for code, name_ar, name_en, acc_type, parent_code, is_header, level in core:
            acc = GLAccount.query.filter_by(code=code).first()
            if acc:
                created_cache[code] = acc
                continue
            
            parent_id = None
            if parent_code:
                parent_acc = created_cache.get(parent_code) or GLAccount.query.filter_by(code=parent_code).first()
                if parent_acc:
                    parent_id = parent_acc.id
            
            acc = GLAccount(
                code=code,
                name=name_en,
                name_ar=name_ar,
                type=acc_type,
                parent_id=parent_id,
                is_header=is_header,
                level=level,
                currency='AED'
            )
            db.session.add(acc)
            db.session.flush()
            created_cache[code] = acc
            created_any = True
        
        if created_any:
            db.session.flush()
    

    
    @staticmethod
    def post_entry(lines, description, reference_type=None, reference_id=None, date=None, currency='AED', exchange_rate=1.0, branch_id=None):
        """
        Wrapper for create_journal_entry: converts amounts to AED and creates balanced entry.
        """
        rate = Decimal(str(exchange_rate)) if exchange_rate else Decimal('1')
        if currency and currency.upper() != 'AED' and rate <= 0:
            rate = Decimal('1')
        adapted_lines = []
        for line in lines:
            debit = Decimal(str(line.get('debit', 0) or 0)) * rate
            credit = Decimal(str(line.get('credit', 0) or 0)) * rate
            adapted_lines.append({
                'account_code': line.get('account'),
                'debit': debit,
                'credit': credit,
                'description': line.get('description', description)
            })
        entry_date = date or datetime.now(timezone.utc)
        entry = GLService.create_journal_entry(
            entry_date,
            description,
            adapted_lines,
            user_id=None,
            branch_id=branch_id,
            reference_type=reference_type,
            reference_id=reference_id
        )
        return entry
    
    @staticmethod
    def reverse_entry(reference_type=None, reference_id=None, description=None):
        """عكس جميع القيود المرتبطة بمرجع (مثل فاتورة بيع/شراء/سند)."""
        if not reference_type or reference_id is None:
            return
        entries = GLJournalEntry.query.filter_by(
            reference_type=reference_type,
            reference_id=reference_id,
            is_reversed=False
        ).order_by(GLJournalEntry.id.desc()).all()
        for entry in entries:
            entry.reverse_entry(description=description)
        if entries:
            db.session.commit()

    @staticmethod
    def get_payment_debit_account(method):
        m = (method or '').strip()
        if m == 'cash':
            return '1110'
        if m in ('bank_transfer', 'card'):
            return '1120'
        if m == 'cheque':
            return '1150'
        return '1110'

    @staticmethod
    def get_customer_credit_account(customer):
        code = '1130'
        if customer and getattr(customer, 'customer_type', None) == 'partner':
            code = '3350'
        elif customer and getattr(customer, 'customer_type', None) == 'merchant':
            code = '2115'
        return code
    
    @staticmethod
    def create_manual_entry(description, lines, entry_date=None, notes=None, created_by=None, currency='AED', exchange_rate=1.0, branch_id=None):
        """إنشاء قيد يدوي"""
        from flask_login import current_user
        
        def _unique_entry_number():
            y = datetime.now().strftime('%Y')
            from models import GLJournalEntry as _JE
            latest = db.session.query(_JE).filter(_JE.entry_number.like(f'JE-{y}-%')).order_by(_JE.entry_number.desc()).first()
            last_db = 0
            if latest:
                try:
                    last_db = int(latest.entry_number.split('-')[-1])
                except Exception:
                    last_db = 0
            last_mem = _JE_SEQ.get(y, last_db)
            next_num = max(last_db, last_mem) + 1
            _JE_SEQ[y] = next_num
            return f'JE-{y}-{next_num:04d}'
        entry_number = _unique_entry_number()
        
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        # التحقق من التوازن
        for line in lines:
            total_debit += Decimal(str(line.get('debit', 0) or 0))
            total_credit += Decimal(str(line.get('credit', 0) or 0))
        
        if total_debit != total_credit:
            raise ValueError(f'القيد غير متوازن: مدين={total_debit}, دائن={total_credit}')
        
        # إنشاء القيد
        
        # Get branch from user context if not provided
        if not branch_id:
            if created_by:
                from models import User
                user = User.query.get(created_by)
                if user: branch_id = user.branch_id
            elif hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                 branch_id = current_user.branch_id
            
        entry = GLJournalEntry(
            entry_number=entry_number,
            entry_date=entry_date or datetime.now(timezone.utc),
            description=description,
            entry_type='manual',
            branch_id=branch_id,
            currency=currency,
            exchange_rate=exchange_rate,
            total_debit=total_debit,
            total_credit=total_credit,
            notes=notes,
            created_by=created_by or (current_user.id if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else None),
            is_posted=True
        )
        db.session.add(entry)
        db.session.flush()
        
        # إنشاء السطور
        for line_data in lines:
            account_code = line_data.get('account_code') or line_data.get('account')
            account = GLAccount.query.filter_by(code=account_code).first()
            
            if not account:
                raise ValueError(f'الحساب {account_code} غير موجود')
            
            if account.is_header:
                raise ValueError(f'الحساب {account.full_name} هو حساب رئيسي ولا يمكن إضافة قيود عليه')
            
            debit = Decimal(str(line_data.get('debit', 0) or 0))
            credit = Decimal(str(line_data.get('credit', 0) or 0))
            
            line = GLJournalLine(
                entry_id=entry.id,
                account_id=account.id,
                description=line_data.get('description', ''),
                debit=debit,
                credit=credit,
                amount_aed=debit - credit
            )
            db.session.add(line)
        
        db.session.commit()
        return entry
    
    @staticmethod
    def get_account_balance_for_branch(account_id, branch_id=None):
        """رصيد حساب محدد مع عزل اختياري للفرع (عند اللزوم). branch_id=None = كل الفروع."""
        from sqlalchemy import func
        account = GLAccount.query.get(account_id)
        if not account:
            return None
        q = db.session.query(func.sum(GLJournalLine.amount_aed)).filter(
            GLJournalLine.account_id == account_id
        ).join(GLJournalEntry)
        if branch_id:
            q = q.filter(GLJournalEntry.branch_id == branch_id)
        total = q.scalar() or Decimal('0')
        if account.type in ('liability', 'equity', 'revenue'):
            total = -total
        return float(total)

    @staticmethod
    def get_account_statement(account_id, date_from=None, date_to=None, branch_id=None):
        """كشف حساب تفصيلي. عند تمرير branch_id يُعزل العرض لقيود الفرع فقط."""
        from sqlalchemy import func
        
        account = GLAccount.query.get_or_404(account_id)
        
        query = GLJournalLine.query.filter_by(account_id=account_id).join(GLJournalEntry)
        
        if branch_id:
            query = query.filter(GLJournalEntry.branch_id == branch_id)
            
        if date_from:
            query = query.filter(func.date(GLJournalEntry.entry_date) >= date_from)
        
        if date_to:
            query = query.filter(func.date(GLJournalEntry.entry_date) <= date_to)
        
        lines = query.order_by(GLJournalEntry.entry_date).all()
        
        # حساب الرصيد الافتتاحي
        opening_query = GLJournalLine.query.filter_by(account_id=account_id).join(GLJournalEntry)
        
        if branch_id:
            opening_query = opening_query.filter(GLJournalEntry.branch_id == branch_id)
            
        if date_from:
            opening_query = opening_query.filter(func.date(GLJournalEntry.entry_date) < date_from)
        
        # Calculate opening balance manually since we need to filter by date and branch
        opening_lines = opening_query.all()
        opening_debit = sum(line.debit for line in opening_lines)
        opening_credit = sum(line.credit for line in opening_lines)
        
        # حساب الرصيد بناءً على نوع الحساب
        if account.type in ['asset', 'expense']:
            opening_balance = opening_debit - opening_credit
        else:  # liability, equity, revenue
            opening_balance = opening_credit - opening_debit
        
        # إنشاء كشف الحساب
        running_balance = opening_balance
        transactions = []
        
        for line in lines:
            debit_val = line.debit
            credit_val = line.credit
            
            if account.type in ['asset', 'expense']:
                running_balance += (debit_val - credit_val)
            else:
                running_balance += (credit_val - debit_val)
            
            transactions.append({
                'date': line.entry.entry_date,
                'entry_number': line.entry.entry_number,
                'entry_type': line.entry.entry_type, # Fixed from entry_type_ar if not property
                'description': line.description or line.entry.description,
                'reference': f'{line.entry.reference_type} #{line.entry.reference_id}' if line.entry.reference_type else '',
                'debit': float(debit_val),
                'credit': float(credit_val),
                'balance': float(running_balance),
                'branch_id': line.entry.branch_id
            })
        
        return {
            'account': account,
            'opening_balance': float(opening_balance),
            'transactions': transactions,
            'closing_balance': float(running_balance),
            'total_debit': sum(t['debit'] for t in transactions),
            'total_credit': sum(t['credit'] for t in transactions)
        }
    
    @staticmethod
    def get_accounts_tree():
        """الحصول على شجرة الحسابات"""
        # الحصول على الحسابات الرئيسية (بدون parent)
        root_accounts = GLAccount.query.filter_by(parent_id=None, is_active=True).order_by(GLAccount.code).all()
        
        def build_tree(account):
            """بناء الشجرة بشكل متكرر"""
            return {
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'name_ar': account.name_ar,
                'full_name': account.full_name,
                'type': account.type,
                'type_ar': account.type_ar,
                'is_header': account.is_header,
                'level': account.level,
                'balance': float(account.get_balance()),
                'children': [build_tree(child) for child in account.children if child.is_active]
            }
        
        return [build_tree(acc) for acc in root_accounts]

    @staticmethod
    def get_trial_balance(date_from=None, date_to=None, branch_id=None):
        """ميزان المراجعة. عند تمرير branch_id يُعزل العرض لقيود الفرع فقط."""
        from sqlalchemy import func
        
        accounts = GLAccount.query.filter_by(is_active=True).order_by(GLAccount.code).all()
        result = []
        
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for account in accounts:
            if account.is_header:
                result.append({
                    'code': account.code,
                    'name': account.full_name,
                    'type': 'header',
                    'debit': 0,
                    'credit': 0,
                    'balance': 0,
                    'level': account.level
                })
                continue
                
            query = GLJournalLine.query.filter_by(account_id=account.id).join(GLJournalEntry)
            
            if branch_id:
                query = query.filter(GLJournalEntry.branch_id == branch_id)
                
            if date_from:
                query = query.filter(func.date(GLJournalEntry.entry_date) >= date_from)
            if date_to:
                query = query.filter(func.date(GLJournalEntry.entry_date) <= date_to)
                
            lines = query.all()
            
            debit_sum = sum(line.debit for line in lines)
            credit_sum = sum(line.credit for line in lines)
            
            if debit_sum == 0 and credit_sum == 0:
                continue
                
            balance = debit_sum - credit_sum
            
            total_debit += debit_sum
            total_credit += credit_sum
            
            result.append({
                'code': account.code,
                'name': account.full_name,
                'type': 'account',
                'debit': float(debit_sum),
                'credit': float(credit_sum),
                'balance': float(balance),
                'level': account.level
            })
            
        return {
            'lines': result,
            'total_debit': float(total_debit),
            'total_credit': float(total_credit)
        }

    @staticmethod
    def get_payment_credit_account(payment_method):
        """حساب الدائن عند الصرف (خروج نقدية)."""
        m = (payment_method or '').strip().lower()
        if m == 'cash':
            return '1110'
        if m in ('bank_transfer', 'card', 'bank'):
            return '1120'
        if m == 'cheque':
            return '2120'
        return '1110'


