from extensions import db
from models import GLAccount
from models.gl_account_registry import BASE_ACCOUNTS, INDUSTRY_EXTENSIONS
from sqlalchemy import or_
from utils.currency_utils import resolve_default_currency


def _template_to_tuple(tmpl):
    return (
        tmpl.code,
        tmpl.name_ar,
        tmpl.name,
        tmpl.type,
        tmpl.parent_code,
        tmpl.is_header,
        tmpl.level,
    )


def _get_core_account_tree():
    return [_template_to_tuple(t) for t in BASE_ACCOUNTS]


def _get_industry_tree(industry_code):
    if not industry_code:
        return []
    industry = industry_code.strip().lower()
    return [_template_to_tuple(t) for t in INDUSTRY_EXTENSIONS.get(industry, [])]


CORE_ACCOUNT_CODES = {t.code for t in BASE_ACCOUNTS}


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
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            
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
        
        existing_accounts = {}
        account_query = GLAccount.query.filter_by(tenant_id=tenant_id).all()
        for acc in account_query:
            existing_accounts[acc.code] = acc
        processed = {}
        core_tree = _get_core_account_tree()
        industry_tree = []
        try:
            from models.tenant import Tenant
            tenant = Tenant.query.get(tenant_id)
            if tenant and tenant.business_type:
                industry_tree = _get_industry_tree(tenant.business_type)
        except Exception:
            pass
        full_tree = core_tree + industry_tree
        for code, name_ar, name_en, acc_type, parent_code, is_header, level in full_tree:
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
        GLTreeBuilder._ensure_branch_liquidity_accounts(
            tenant_id=tenant_id,
            existing_accounts=existing_accounts,
            processed=processed,
            audit_report=audit_report,
        )
        if cleanup_extra:
            for code, acc in existing_accounts.items():
                if code not in CORE_ACCOUNT_CODES and acc.is_active and not getattr(acc, 'liquidity_kind', None):
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
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    raise

        
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
            
            # Preserve existing account currency; do not force AED
            
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
                currency=GLTreeBuilder._resolve_tenant_currency(tenant_id)
            )
            
            db.session.add(new_acc)
            db.session.flush()
            
            processed[code] = new_acc
            result['action'] = 'created'
            return result

    @staticmethod
    def _resolve_tenant_currency(tenant_id):
        """Resolve default currency for tenant, fallback to AED."""
        try:
            from models.tenant import Tenant
            tenant = Tenant.query.get(int(tenant_id))
            if tenant and tenant.default_currency:
                return tenant.default_currency
        except Exception:
            pass
        return 'AED'

    @staticmethod
    def _branch_account_code(prefix, branch_id):
        return f'{prefix}-B{int(branch_id)}'

    @staticmethod
    def _ensure_branch_liquidity_accounts(tenant_id, existing_accounts, processed, audit_report):
        from models import Branch

        branches = (
            Branch.query
            .filter_by(tenant_id=tenant_id, is_active=True)
            .order_by(Branch.is_main.desc(), Branch.id.asc())
            .all()
        )

        for branch in branches:
            GLTreeBuilder._ensure_liquidity_account(
                tenant_id=tenant_id,
                code=GLTreeBuilder._branch_account_code('1110', branch.id),
                name_ar=f'صندوق {branch.name}',
                name_en=f'Cashbox - {branch.name}',
                parent_code='1110',
                branch_id=branch.id,
                liquidity_kind='cash',
                existing_accounts=existing_accounts,
                processed=processed,
                audit_report=audit_report,
            )
            GLTreeBuilder._ensure_liquidity_account(
                tenant_id=tenant_id,
                code=GLTreeBuilder._branch_account_code('1120', branch.id),
                name_ar=f'بنك {branch.name}',
                name_en=f'Bank - {branch.name}',
                parent_code='1120',
                branch_id=branch.id,
                liquidity_kind='bank',
                existing_accounts=existing_accounts,
                processed=processed,
                audit_report=audit_report,
            )

    @staticmethod
    def _ensure_liquidity_account(
        tenant_id,
        code,
        name_ar,
        name_en,
        parent_code,
        branch_id,
        liquidity_kind,
        existing_accounts,
        processed,
        audit_report,
    ):
        result = {'code': code, 'name_ar': name_ar, 'action': 'none'}
        parent = processed.get(parent_code) or existing_accounts.get(parent_code)
        parent_id = parent.id if parent else None
        acc = existing_accounts.get(code)

        if acc:
            needs_update = False
            if not acc.is_active:
                acc.is_active = True
                needs_update = True
            if acc.name != name_en:
                acc.name = name_en
                needs_update = True
            if acc.name_ar != name_ar:
                acc.name_ar = name_ar
                needs_update = True
            if acc.type != 'asset':
                acc.type = 'asset'
                needs_update = True
            if acc.parent_id != parent_id:
                acc.parent_id = parent_id
                needs_update = True
            if acc.is_header:
                acc.is_header = False
                needs_update = True
            if acc.level != 3:
                acc.level = 3
                needs_update = True
            # Preserve existing account currency; do not force AED
            if getattr(acc, 'branch_id', None) != branch_id:
                acc.branch_id = branch_id
                needs_update = True
            if getattr(acc, 'liquidity_kind', None) != liquidity_kind:
                acc.liquidity_kind = liquidity_kind
                needs_update = True
            if not getattr(acc, 'is_default_liquidity', False):
                acc.is_default_liquidity = True
                needs_update = True

            processed[code] = acc
            if needs_update:
                result['action'] = 'updated'
                audit_report['updated'].append(result)
            return acc

        acc = GLAccount(
            tenant_id=tenant_id,
            code=code,
            name=name_en,
            name_ar=name_ar,
            type='asset',
            parent_id=parent_id,
            branch_id=branch_id,
            liquidity_kind=liquidity_kind,
            is_default_liquidity=True,
            is_header=False,
            level=3,
            is_active=True,
            currency=GLTreeBuilder._resolve_tenant_currency(tenant_id),
        )
        db.session.add(acc)
        db.session.flush()
        existing_accounts[code] = acc
        processed[code] = acc
        result['action'] = 'created'
        audit_report['created'].append(result)
        return acc
    
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
