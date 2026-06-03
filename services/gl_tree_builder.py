from extensions import db
from models import GLAccount
from sqlalchemy import or_

# === شجرة الحسابات الأساسية (58 حسابًا كاملاً) ===
# (code, name_ar, name_en, type, parent_code, is_header, level)
CORE_ACCOUNT_TREE = [
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
    ('1170', 'ضريبة مدخلات', 'VAT Input', 'asset', '1100', False, 2),
    ('1175', 'تسوية ضريبة', 'VAT Clearing', 'asset', '1100', False, 2),
    ('1200', 'الأصول الثابتة', 'Fixed Assets', 'asset', '1000', True, 1),
    ('1210', 'أراضي', 'Land', 'asset', '1200', False, 2),
    ('1220', 'مباني', 'Buildings', 'asset', '1200', False, 2),
    ('1230', 'سيارات', 'Vehicles', 'asset', '1200', False, 2),
    ('1240', 'معدات', 'Equipment', 'asset', '1200', False, 2),
    ('1250', 'أثاث', 'Furniture', 'asset', '1200', False, 2),
    ('1290', 'مجمع الاستهلاك', 'Accumulated Depreciation', 'asset', '1200', False, 2),
    
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
    ('6150', 'مصروف عمولات شركاء', 'Partner Commission Expense', 'expense', '6000', False, 1),
    ('6180', 'مصروف استهلاك', 'Depreciation Expense', 'expense', '6000', False, 1),
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

# مجموعة من الأكواد الأساسية للبحث السريع
CORE_ACCOUNT_CODES = {code for code, _, _, _, _, _, _ in CORE_ACCOUNT_TREE}


class GLTreeBuilder:
    """
    منشئ شجرة الحسابات المحاسبية مع:
    - Idempotency (تشغيل عدة مرات = نفس النتيجة)
    - Self-Healing (تصحيح الحسابات الخاطئة)
    - Audit Log (تقرير بكل التغييرات)
    - Cleanup (إيقاف الحسابات غير الأساسية أو المكررة)
    """

    @staticmethod
    def build(tenant_id, cleanup_extra=False, commit=True):
        """
        بناء أو تصحيح شجرة الحسابات للمستأجر معين.
        
        Args:
            tenant_id: معرف المستأجر
            cleanup_extra: إذا كان True، سيتم إيقاف الحسابات غير الموجودة في الشجرة الأساسية
            commit: إذا كان True، سيتم تنفيذ db.session.commit() تلقائيًا
            
        Returns:
            dict: تقرير بالتغييرات التي تمت
        """
        audit_report = {
            'tenant_id': tenant_id,
            'created': [],
            'updated': [],
            'converted': [],
            'deactivated': [],
            'errors': []
        }
        
        # خريطة للحسابات الموجودة بالفعل
        existing_accounts = {}
        account_query = GLAccount.query.filter_by(tenant_id=tenant_id).all()
        for acc in account_query:
            existing_accounts[acc.code] = acc
        
        # خريطة لتتبع الحسابات التي تم إنشاؤها/تحديثها
        processed = {}
        
        # معالجة الحسابات بالترتيب (الأولوية للأبواب)
        for code, name_ar, name_en, acc_type, parent_code, is_header, level in CORE_ACCOUNT_TREE:
            try:
                result = GLTreeBuilder._process_account(
                    tenant_id,
                    code, name_ar, name_en, acc_type, parent_code, is_header, level,
                    existing_accounts,
                    processed
                )
                
                if result['action'] == 'created':
                    audit_report['created'].append(result)
                elif result['action'] == 'updated':
                    audit_report['updated'].append(result)
                elif result['action'] == 'converted':
                    audit_report['converted'].append(result)
                
            except Exception as e:
                audit_report['errors'].append({
                    'code': code,
                    'error': str(e)
                })
        
        # تنظيف الحسابات الزائدة (إذا طلبنا ذلك)
        if cleanup_extra:
            for code, acc in existing_accounts.items():
                if code not in CORE_ACCOUNT_CODES and acc.is_active:
                    acc.is_active = False
                    audit_report['deactivated'].append({
                        'code': code,
                        'name_ar': acc.name_ar or acc.name
                    })
        
        # حفظ التغييرات
        has_changes = (
            audit_report['created'] or 
            audit_report['updated'] or 
            audit_report['converted'] or 
            audit_report['deactivated']
        )
        
        if has_changes:
            db.session.flush()
            if commit:
                db.session.commit()
        
        return audit_report
    
    @staticmethod
    def _process_account(tenant_id, code, name_ar, name_en, acc_type, parent_code, is_header, level, existing_accounts, processed):
        """معالجة حساب واحد"""
        result = {
            'code': code,
            'name_ar': name_ar,
            'action': 'none'
        }
        
        if code in existing_accounts:
            # الحساب موجود — تحقق هل يحتاج تصحيح؟
            acc = existing_accounts[code]
            needs_update = False
            conversion_needed = False
            
            # التأكد من أن الحساب نشط
            if not acc.is_active:
                acc.is_active = True
                needs_update = True
            
            # التحقق من خصائص الحساب
            if acc.name != name_en:
                acc.name = name_en
                needs_update = True
            
            if acc.name_ar != name_ar:
                acc.name_ar = name_ar
                needs_update = True
            
            if acc.type != acc_type:
                acc.type = acc_type
                needs_update = True
            
            if acc.is_header != is_header:
                # تحويل من حساب عادي إلى رئيسي أو العكس
                acc.is_header = is_header
                conversion_needed = True
                needs_update = True
            
            if acc.level != level:
                acc.level = level
                needs_update = True
            
            if acc.currency != 'AED':
                acc.currency = 'AED'
                needs_update = True
            
            # الحصول على معرف الأب الصحيح
            parent_id = None
            if parent_code:
                if parent_code in processed:
                    parent_id = processed[parent_code].id
                elif parent_code in existing_accounts:
                    parent_id = existing_accounts[parent_code].id
            
            if acc.parent_id != parent_id:
                acc.parent_id = parent_id
                needs_update = True
            
            if conversion_needed:
                result['action'] = 'converted'
            elif needs_update:
                result['action'] = 'updated'
            
            processed[code] = acc
            return result
        
        else:
            # الحساب غير موجود — أنشئه
            parent_id = None
            if parent_code:
                if parent_code in processed:
                    parent_id = processed[parent_code].id
                elif parent_code in existing_accounts:
                    parent_id = existing_accounts[parent_code].id
            
            new_acc = GLAccount(
                tenant_id=tenant_id,
                code=code,
                name=name_en,
                name_ar=name_ar,
                type=acc_type,
                parent_id=parent_id,
                is_header=is_header,
                level=level,
                is_active=True,
                currency='AED'
            )
            
            db.session.add(new_acc)
            db.session.flush()
            
            processed[code] = new_acc
            result['action'] = 'created'
            return result
    
    @staticmethod
    def validate_tree(tenant_id):
        """
        التحقق من سلامة شجرة الحسابات.
        
        Returns:
            dict: نتائج التحقق
        """
        validation = {
            'valid': True,
            'issues': [],
            'total_accounts': 0,
            'core_accounts_found': 0,
            'missing_core_accounts': [],
            'extra_accounts': []
        }
        
        # الحصول على جميع الحسابات للمستأجر
        accounts = GLAccount.query.filter_by(tenant_id=tenant_id).all()
        account_codes = {acc.code: acc for acc in accounts}
        validation['total_accounts'] = len(accounts)
        
        # التحقق من الحسابات الأساسية
        for code, name_ar, _, _, _, _, _ in CORE_ACCOUNT_TREE:
            if code not in account_codes:
                validation['missing_core_accounts'].append({
                    'code': code,
                    'name_ar': name_ar
                })
                validation['valid'] = False
            else:
                if not account_codes[code].is_active:
                    validation['issues'].append({
                        'code': code,
                        'issue': 'الحساب الأساسي غير نشط!'
                    })
                    validation['valid'] = False
        
        validation['core_accounts_found'] = len(CORE_ACCOUNT_CODES) - len(validation['missing_core_accounts'])
        
        # التحقق من الحسابات الزائدة
        for code, acc in account_codes.items():
            if code not in CORE_ACCOUNT_CODES:
                validation['extra_accounts'].append({
                    'code': code,
                    'name_ar': acc.name_ar or acc.name,
                    'is_active': acc.is_active
                })
        
        # التحقق من صحة الأب (أولوية الأبواب)
        for acc in accounts:
            if acc.parent_id:
                parent = db.session.get(GLAccount, acc.parent_id)
                if not parent or parent.tenant_id != tenant_id:
                    validation['issues'].append({
                        'code': acc.code,
                        'issue': f'الأب #{acc.parent_id} غير صالح'
                    })
                    validation['valid'] = False
            
            # التحقق من مستوى الحساب
            if acc.parent_id:
                parent = db.session.get(GLAccount, acc.parent_id)
                if parent and acc.level != parent.level + 1:
                    validation['issues'].append({
                        'code': acc.code,
                        'issue': f'المستوى ({acc.level}) لا يتطابق مع مستوى الأب'
                    })
                    validation['valid'] = False
        
        return validation

