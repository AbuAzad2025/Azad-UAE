from decimal import Decimal
from datetime import datetime, timezone
from extensions import db
from models import GLAccount, GLJournalEntry, GLJournalLine, Currency
from models._constants import GL_CONCEPT_REGISTRY, RESOLUTION_MODE_MAPPING, RESOLUTION_MODE_LIQUIDITY, RESOLUTION_MODE_RECORD, RESOLUTION_MODE_NON_POSTING
from services import gl_helpers
from services.gl_account_resolver import (
    GLMappingError,
    is_dynamic_gl_mapping_enabled,
    resolve_gl_account,
)
from services.gl_tree_builder import GLTreeBuilder
from utils.helpers import generate_number
from utils.currency_utils import get_system_default_currency, resolve_default_currency, resolve_tenant_base_currency

_JE_SEQ = {}

# مرجع الحسابات: استخدم هذه الرموز للقيود لضمان الاتساق
# أصول: 1110 صندوق، 1120 بنك، 1130 ذمم مدينة، 1140 مخزون، 1150 شيكات تحت التحصيل، 1170 سلف موظفين
# خصوم: 2110 ذمم دائنة، 2115 ذمم تجار، 2121 ضريبة مخرجات (VAT Output)، 2122 ضريبة مدخلات (VAT Input)، 2130 شيكات مؤجلة، 2140 رواتب مستحقة
# إيرادات: 4100 مبيعات، 4200 خدمات، 4300 شحن، 4400 أرباح فرق عملة، 4500 أخرى
# مصروفات: 5100 تكلفة بضاعة، 5150 تعديلات مخزون، 6130 خصومات ممنوحة، 6100 رواتب، 6600 خسائر فرق عملة، 6500 متنوعة
# 'cash' and 'bank' are retained as header account references for legacy callers.
# get_default_liquidity_account().
GL_ACCOUNTS = {
    'cash': '1110',
    'bank': '1120',
    'bank_savings': '1121',
    'receivable': '1130',
    'inventory': '1140',
    'cheques_under_collection': '1150',
    'employee_advances': '1170',  # Employee advances / prepayments
    'vat_input': '2122',          # VAT Input (recoverable tax on purchases)
    'payable': '2110',
    'merchants_payable': '2115',
    'deferred_cheques': '2130',   # Deferred Cheques Payable (outgoing cheques not yet cleared)
    'tax_payable': '2121',        # VAT Output (tax collected on sales)
    'salaries_payable': '2141',
    'end_of_service_liability': '2140',
    'sales_revenue': '4100',
    'service_revenue': '4200',
    'shipping_revenue': '4300',
    'fx_gain': '4400',
    'other_revenue': '4500',
    'cogs': '5100',
    'inventory_adjustments': '5150',
    'discounts_given': '6130',
    'salaries_expense': '6220',
    'commission_expense': '6150',
    'depreciation_expense': '6180',
    'accumulated_depreciation': '1190',  # Contra-asset: Accumulated Depreciation
    'rent': '6210',
    'utilities': '6230',
    'maintenance': '6240',
    'freight_in': '5301',
    'customs_duty': '5302',
    'insurance_in': '5303',
    'fx_loss': '6600',
    'bank_charges': '6260',
    'misc_expense': '6500',
    'partner_current_account': '2150',
    'azad_platform_payable': '2180',
    'azad_platform_fee_accrued': '2181',
    'azad_platform_fee_paid': '2182',
    'azad_subscription_expense': '6410',
    'azad_subscription_revenue': '4700',
    'end_of_service_provision': '6190',
    'leave_accrual_liability': '2160',
    'pos_cash_difference': '6500',
}

GL_ACCOUNT_CONCEPTS = {
    'cash': 'CASH',
    'bank': 'BANK',
    'receivable': 'AR',
    'inventory': 'INVENTORY_ASSET',
    'cheques_under_collection': 'CHEQUES_UNDER_COLLECTION',
    'employee_advances': 'EMPLOYEE_ADVANCES',
    'vat_input': 'VAT_INPUT',
    'payable': 'AP',
    'merchants_payable': 'MERCHANT_CURRENT_ACCOUNT',
    'deferred_cheques': 'DEFERRED_CHEQUES_PAYABLE',
    'salaries_payable': 'PAYROLL_PAYABLE',
    'end_of_service_liability': 'END_OF_SERVICE_LIABILITY',
    'tax_payable': 'VAT_OUTPUT',
    'sales_revenue': 'SALES_REVENUE',
    'shipping_revenue': 'SHIPPING_REVENUE',
    'service_revenue': 'DONATION_REVENUE',
    'cogs': 'COGS',
    'inventory_adjustments': 'INVENTORY_ADJUSTMENT_LOSS',
    'discounts_given': 'SALES_DISCOUNT',
    'salaries_expense': 'PAYROLL_EXPENSE',
    'commission_expense': 'COMMISSION_EXPENSE',
    'depreciation_expense': 'DEPRECIATION_EXPENSE',
    'accumulated_depreciation': 'ACCUMULATED_DEPRECIATION',
    'fx_gain': 'FX_GAIN',
    'fx_loss': 'FX_LOSS',
    'bank_charges': 'BANK_FEES',
    'misc_expense': 'MISC_EXPENSE',
    'partner_current_account': 'PARTNER_CURRENT_ACCOUNT',
    'azad_platform_payable': 'AZAD_PLATFORM_PAYABLE',
    'azad_platform_fee_accrued': 'AZAD_PLATFORM_FEE_ACCRUED',
    'azad_platform_fee_paid': 'AZAD_PLATFORM_FEE_PAID',
    'azad_subscription_expense': 'AZAD_SUBSCRIPTION_EXPENSE',
    'azad_subscription_revenue': 'AZAD_SUBSCRIPTION_REVENUE',
    'end_of_service_provision': 'END_OF_SERVICE_PROVISION',
    'leave_accrual_liability': 'LEAVE_ACCRUAL_LIABILITY',
    'pos_cash_difference': 'POS_CASH_DIFFERENCE',
}

class GLService:

    @staticmethod
    def posting_line(account_key, *, debit=0, credit=0, description='', concept_code=None, account=None):
        legacy_code = account if account is not None else GL_ACCOUNTS[account_key]
        concept = concept_code if concept_code is not None else GL_ACCOUNT_CONCEPTS.get(account_key)
        line = {
            'account': legacy_code,
            'debit': debit,
            'credit': credit,
            'description': description,
        }
        if concept:
            line['concept_code'] = concept
        return line

    @staticmethod
    def get_payment_debit_concept(method):
        m = (method or '').strip().lower()
        if m == 'cash':
            return 'CASH'
        if m in ('bank_transfer', 'card', 'bank'):
            return 'BANK'
        if m == 'cheque':
            return 'CHEQUES_UNDER_COLLECTION'
        return 'CASH'

    @staticmethod
    def get_payment_credit_concept(payment_method):
        m = (payment_method or '').strip().lower()
        if m == 'cash':
            return 'CASH'
        if m in ('bank_transfer', 'card', 'bank'):
            return 'BANK'
        if m == 'cheque':
            return 'DEFERRED_CHEQUES_PAYABLE'
        return None

    @staticmethod
    def get_customer_credit_concept(customer):
        if customer and getattr(customer, 'customer_type', None) == 'partner':
            return 'PARTNER_CURRENT_ACCOUNT'
        if customer and getattr(customer, 'customer_type', None) == 'merchant':
            return 'MERCHANT_CURRENT_ACCOUNT'
        return 'AR'

    @staticmethod
    def _resolve_journal_line_account(line, tenant_id, branch_id=None, ensure_core=True, missing_ok=False):
        account_code = line.get('account_code') or line.get('account')
        raw_concept = line.get("concept_code")
        concept_code = str(raw_concept or "").strip().upper() or None

        # ---- Determine resolution mode ----
        resolution_mode = None
        if concept_code:
            meta = GL_CONCEPT_REGISTRY.get(concept_code, {})
            resolution_mode = meta.get('resolution_mode', RESOLUTION_MODE_MAPPING)

            # A non-empty unknown concept must raise GLMappingError immediately
            if raw_concept and concept_code not in GL_CONCEPT_REGISTRY:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code=raw_concept,
                    branch_id=branch_id,
                    issue=f"Unknown GL concept code: {raw_concept}",
                )

        # ---- Helper: validate an explicit account (tenant-owned, active, postable) ----
        def _validate_explicit(acct_code, branch_id=None):
            acct = gl_helpers.get_account(acct_code, tenant_id)
            if acct is None:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                    branch_id=branch_id,
                    issue=f"Explicit GL account {acct_code} does not exist for this tenant.",
                )
            if not acct.is_active:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                    branch_id=branch_id,
                    issue=f"Explicit GL account {acct_code} is inactive.",
                )
            if acct.is_header:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                    branch_id=branch_id,
                    issue=f"Explicit GL account {acct_code} is a header/group account.",
                )

            # Validate branch_id belongs to tenant_id when branch_id is supplied
            if branch_id is not None:
                from models import Branch
                branch = Branch.query.get(branch_id)
                if branch is None:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                        branch_id=branch_id,
                        issue=f"Branch {branch_id} does not exist.",
                    )
                if branch.tenant_id != tenant_id:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                        branch_id=branch_id,
                        issue=f"Branch {branch_id} belongs to a different tenant.",
                    )

                # For record mode: account.branch_id is None or equals branch_id
                # For liquidity mode: account.branch_id must equal branch_id exactly
                if resolution_mode == RESOLUTION_MODE_RECORD:
                    if getattr(acct, 'branch_id', None) is not None and getattr(acct, 'branch_id', None) != branch_id:
                        raise GLMappingError(
                            tenant_id=tenant_id,
                            concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                            branch_id=branch_id,
                            issue=f"Account {acct.code} branch_id {getattr(acct, 'branch_id', None)} does not match required branch_id {branch_id} for record mode.",
                        )
                elif resolution_mode == RESOLUTION_MODE_LIQUIDITY:
                    if getattr(acct, 'branch_id', None) != branch_id:
                        raise GLMappingError(
                            tenant_id=tenant_id,
                            concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                            branch_id=branch_id,
                            issue=f"Account {acct.code} branch_id {getattr(acct, 'branch_id', None)} does not match required branch_id {branch_id} for liquidity mode.",
                        )
            else:
                # Without branch_id: account.branch_id must be None exactly
                if getattr(acct, 'branch_id', None) is not None:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code or 'EXPLICIT_ACCOUNT',
                        branch_id=branch_id,
                        issue=f"Account {acct.code} has branch_id {getattr(acct, 'branch_id', None)} but branch_id is required to be None.",
                    )

            return acct

        # ---- Mode-specific resolution ----
        # Non-posting is absolute - must fail regardless of dynamic mapping setting
        if resolution_mode == RESOLUTION_MODE_NON_POSTING:
            raise GLMappingError(
                tenant_id=tenant_id,
                concept_code=concept_code,
                branch_id=branch_id,
                issue="Non-posting concept cannot be resolved in a journal entry.",
            )

        if is_dynamic_gl_mapping_enabled():
            if resolution_mode == RESOLUTION_MODE_LIQUIDITY:
                if not account_code:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code,
                        branch_id=branch_id,
                        issue="Liquidity-owned concept requires an explicit GL account code.",
                    )
                acct = _validate_explicit(account_code, branch_id)
                expected_kind = 'cash' if concept_code == 'CASH' else 'bank'
                if getattr(acct, 'liquidity_kind', None) != expected_kind:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code,
                        branch_id=branch_id,
                        issue=f"Account {account_code} liquidity_kind is '{getattr(acct, 'liquidity_kind', None)}', expected '{expected_kind}'.",
                    )
                return acct

            if resolution_mode == RESOLUTION_MODE_RECORD:
                if not line.get('explicit_account_allowed'):
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code,
                        branch_id=branch_id,
                        issue="Record-owned concept requires explicit_account_allowed=True.",
                    )
                if not account_code:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code=concept_code,
                        branch_id=branch_id,
                        issue="Record-owned concept requires an explicit GL account code.",
                    )
                return _validate_explicit(account_code, branch_id)

            # Mapping-owned (default) — resolve only through GLAccountMapping
            if concept_code:
                account = resolve_gl_account(
                    tenant_id=tenant_id,
                    concept_code=concept_code,
                    branch_id=branch_id,
                )
                if account is not None:
                    return account

            if account_code:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code=concept_code or 'UNMAPPED_ACCOUNT_CODE',
                    branch_id=branch_id,
                    issue=(
                        f"No approved GL concept was provided for legacy hardcoded "
                        f"account code {account_code}."
                    ),
                )

        # ---- Dynamic mapping disabled: try resolve (will return None) ----
        if concept_code:
            account = resolve_gl_account(
                tenant_id=tenant_id,
                concept_code=concept_code,
                branch_id=branch_id,
            )
            if account is not None:
                return account

        # ---- Legacy fallback (no concept, or dynamic mapping disabled) ----
        if not account_code:
            raise ValueError('GL account code is required when dynamic mapping is disabled.')

        account = gl_helpers.get_account(account_code, tenant_id)
        if account is None and ensure_core:
            GLService.ensure_core_accounts(tenant_id=tenant_id)
            account = gl_helpers.get_account(account_code, tenant_id)
        if account is None:
            if missing_ok:
                return None
            raise ValueError(f'GL account {account_code} not found')
        if getattr(account, 'is_header', False):
            raise ValueError(f'Cannot post to header GL account {account_code}')
        if not getattr(account, 'is_active', True):
            raise ValueError(f'GL account {account_code} is inactive')
        return account












    @staticmethod
    def create_journal_entry(date, description, lines, user_id=None, branch_id=None, reference_type=None, reference_id=None, tenant_id=None, currency=None, exchange_rate=None, entry_type='auto'):
        """Standardized GL Entry Creation"""

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id, user_id=user_id)
        gl_helpers.assert_period_open(date, tenant_id)
        entry_number = gl_helpers.next_entry_number(tenant_id, date)

        from utils.field_validators import validate_gl_line_sides, validate_reference_type_write
        from models import Branch

        # Validate tenant/branch isolation at journal-entry boundary
        if branch_id is not None:
            branch = Branch.query.get(branch_id)
            if branch is None:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code="JOURNAL_ENTRY_BRANCH",
                    branch_id=branch_id,
                    issue=f"Branch {branch_id} does not exist.",
                )
            if branch.tenant_id != tenant_id:
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code="JOURNAL_ENTRY_BRANCH",
                    branch_id=branch_id,
                    issue=(
                        f"Branch {branch_id} belongs to tenant "
                        f"{branch.tenant_id}, not tenant {tenant_id}."
                    ),
                )

        # Resolve currency from tenant if not provided
        if currency is None:
            try:
                from models.tenant import Tenant
                tenant = Tenant.query.get(tenant_id)
                currency = resolve_tenant_base_currency(tenant)
            except Exception:
                currency = resolve_tenant_base_currency(tenant_id=tenant_id)
        if exchange_rate is None:
            exchange_rate = Decimal('1')

        # Validate line branch_id belongs to same tenant if provided (for lines with explicit branch_id)
        for line in lines:
            line_branch_id = line.get('branch_id')
            if line_branch_id is not None:
                line_branch = Branch.query.get(line_branch_id)
                if line_branch is None:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code="JOURNAL_LINE_BRANCH",
                        branch_id=line_branch_id,
                        issue=f"Line branch {line_branch_id} does not exist.",
                    )
                if line_branch.tenant_id != tenant_id:
                    raise GLMappingError(
                        tenant_id=tenant_id,
                        concept_code="JOURNAL_LINE_BRANCH",
                        branch_id=line_branch_id,
                        issue=(
                            f"Line branch {line_branch_id} belongs to tenant "
                            f"{line_branch.tenant_id}, not tenant {tenant_id}."
                        ),
                    )

        entry = GLJournalEntry(
            tenant_id=tenant_id,
            entry_number=entry_number,
            entry_date=date,
            description=description,
            created_by=user_id,
            branch_id=branch_id,
            entry_type=entry_type,
            is_posted=True,
            currency=currency,
            exchange_rate=exchange_rate,
            reference_type=validate_reference_type_write(reference_type),
            reference_id=reference_id
        )
        db.session.add(entry)
        db.session.flush()

        total_debit = Decimal('0')
        total_credit = Decimal('0')

        for line in lines:
            account = GLService._resolve_journal_line_account(line, tenant_id, branch_id=branch_id)
            if getattr(account, 'is_header', False):
                raise ValueError(f"لا يمكن القيد على الحساب الرئيسي: {getattr(account, 'full_name', account.code)}")
            debit = Decimal(str(line.get('debit', 0)))
            credit = Decimal(str(line.get('credit', 0)))
            validate_gl_line_sides(debit, credit)

            original_debit = Decimal(str(line.get('original_debit', line.get('debit', 0))))
            original_credit = Decimal(str(line.get('original_credit', line.get('credit', 0))))
            gl_line = GLJournalLine(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account_id=account.id,
                debit=debit,
                credit=credit,
                description=line.get('description', description),
                amount=original_debit - original_credit,
                amount_aed=debit - credit,
                # الأبعاد المالية
                branch_id=line.get('branch_id') or branch_id,
                warehouse_id=line.get('warehouse_id'),
                cost_center_id=line.get('cost_center_id'),
                profit_center_id=line.get('profit_center_id'),
                partner_id=line.get('partner_id'),
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
    def ensure_core_accounts(tenant_id=None, cleanup_extra=False):
        """
        Create chart of accounts for the active or specified tenant.
        يستخدم GLTreeBuilder للبناء والتصحيح التلقائي.

        Args:
            tenant_id: معرف المستأجر (اختياري)
            cleanup_extra: إذا كان True، سيتم إيقاف الحسابات غير الأساسية
        """
        if tenant_id is None:
            tenant_id = gl_helpers.resolve_tenant_id()

        # استخدام GLTreeBuilder للبناء أو تصحيح الشجرة
        audit_report = GLTreeBuilder.build(tenant_id, cleanup_extra=cleanup_extra)

        # تسجيل التقرير (للإحتياط)
        if audit_report['created'] or audit_report['updated'] or audit_report['converted'] or audit_report['deactivated']:
            from flask import current_app
            current_app.logger.info(f"GLTreeBuilder: Tenant {tenant_id} report: {audit_report}")

        return audit_report

    @staticmethod
    def validate_account_tree(tenant_id=None):
        """التحقق من سلامة شجرة الحسابات"""
        if tenant_id is None:
            tenant_id = gl_helpers.resolve_tenant_id()

        return GLTreeBuilder.validate_tree(tenant_id)



    @staticmethod
    def post_entry(lines, description, reference_type=None, reference_id=None, date=None, currency=None, exchange_rate=1.0, branch_id=None, user_id=None, tenant_id=None, entry_type='auto'):
        """
        Wrapper for create_journal_entry: converts amounts to tenant base currency and creates balanced entry.
        """
        if not currency:
            currency = resolve_tenant_base_currency(tenant_id=tenant_id)
        rate = Decimal(str(exchange_rate)) if exchange_rate else Decimal('1')
        base_currency = resolve_tenant_base_currency(tenant_id=tenant_id)
        if currency and currency.upper() != base_currency.upper() and rate <= 0:
            rate = Decimal('1')
        adapted_lines = []
        for line in lines:
            orig_debit = Decimal(str(line.get('debit', 0) or 0))
            orig_credit = Decimal(str(line.get('credit', 0) or 0))
            debit = orig_debit * rate
            credit = orig_credit * rate
            adapted_lines.append({
                'account_code': line.get('account_code') or line.get('account'),
                'concept_code': line.get('concept_code'),
                'explicit_account_allowed': line.get('explicit_account_allowed', False),
                'debit': debit,
                'credit': credit,
                'original_debit': orig_debit,
                'original_credit': orig_credit,
                'description': line.get('description', description),
                'branch_id': line.get('branch_id') or branch_id,
                'warehouse_id': line.get('warehouse_id'),
                'cost_center_id': line.get('cost_center_id'),
                'profit_center_id': line.get('profit_center_id'),
                'partner_id': line.get('partner_id'),
            })
        entry_date = date or datetime.now(timezone.utc)
        entry = GLService.create_journal_entry(
            entry_date,
            description,
            adapted_lines,
            user_id=user_id,
            branch_id=branch_id,
            reference_type=reference_type,
            reference_id=reference_id,
            tenant_id=tenant_id,
            currency=currency,
            exchange_rate=rate,
            entry_type=entry_type,
        )
        return entry

    @staticmethod
    def get_vat_report(date_from=None, date_to=None, branch_id=None, tenant_id=None):
        """VAT summary: output (2121 credits) vs input (2122 debits). Includes posted entries only."""
        from sqlalchemy import func
        from utils.tax_settings import is_tax_enabled

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)
        if tenant_id is not None and not is_tax_enabled(tenant_id):
            return {
                'vat_output': 0.0,
                'vat_input': 0.0,
                'net_vat': 0.0,
                'tenant_id': tenant_id,
                'date_from': date_from,
                'date_to': date_to,
                'branch_id': branch_id,
                'tax_disabled': True,
            }
        output_acc = GLService._resolve_journal_line_account(
            GLService.posting_line('tax_payable'),
            tenant_id,
            branch_id=branch_id,
            ensure_core=False,
            missing_ok=True,
        )
        input_acc = GLService._resolve_journal_line_account(
            GLService.posting_line('vat_input'),
            tenant_id,
            branch_id=branch_id,
            ensure_core=False,
            missing_ok=True,
        )
        result = {
            'vat_output': 0.0,
            'vat_input': 0.0,
            'net_vat': 0.0,
            'tenant_id': tenant_id,
            'date_from': date_from,
            'date_to': date_to,
            'branch_id': branch_id,
        }
        if not output_acc and not input_acc:
            return result

        def _sum_side(account, side):
            if not account:
                return Decimal('0')
            q = db.session.query(func.coalesce(func.sum(getattr(GLJournalLine, side)), 0)).join(
                GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id
            ).filter(
                GLJournalLine.account_id == account.id,
                GLJournalEntry.is_posted == True
            )
            if tenant_id is not None:
                q = q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            if branch_id:
                q = q.filter(GLJournalEntry.branch_id == branch_id)
            if date_from:
                q = q.filter(func.date(GLJournalEntry.entry_date) >= date_from)
            if date_to:
                q = q.filter(func.date(GLJournalEntry.entry_date) <= date_to)
            return Decimal(str(q.scalar() or 0))

        vat_output = _sum_side(output_acc, 'credit') - _sum_side(output_acc, 'debit')
        vat_input = _sum_side(input_acc, 'debit') - _sum_side(input_acc, 'credit')
        result['vat_output'] = float(vat_output)
        result['vat_input'] = float(vat_input)
        result['net_vat'] = float(vat_output - vat_input)
        return result

    @staticmethod
    def reverse_entry(reference_type=None, reference_id=None, description=None, tenant_id=None):
        """عكس جميع القيود المرتبطة بمرجع (مثل فاتورة بيع/شراء/سند)."""
        from utils.gl_reference_types import ref_variants

        if not reference_type or reference_id is None:
            return
        variants = ref_variants(reference_type)
        query = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type.in_(variants),
            GLJournalEntry.reference_id == reference_id,
            GLJournalEntry.is_reversed == False,
        )
        if tenant_id is None:
            tenant_id = gl_helpers.resolve_tenant_id()
        if tenant_id is not None:
            query = query.filter_by(tenant_id=int(tenant_id))
        entries = query.order_by(GLJournalEntry.id.desc()).all()
        for entry in entries:
            entry.reverse_entry(description=description)
        return entries

    @staticmethod
    def get_default_liquidity_account(liquidity_kind, branch_id=None, tenant_id=None):
        kind = (liquidity_kind or '').strip().lower()
        if kind not in ('cash', 'bank'):
            raise ValueError(f'Unsupported liquidity account kind: {liquidity_kind}')

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)
        GLService.ensure_core_accounts(tenant_id=tenant_id)

        query = GLAccount.query.filter_by(
            tenant_id=int(tenant_id),
            liquidity_kind=kind,
            is_active=True,
            is_header=False,
        )
        if branch_id:
            account = (
                query
                .filter_by(branch_id=int(branch_id))
                .order_by(GLAccount.is_default_liquidity.desc(), GLAccount.id.asc())
                .first()
            )
            if account:
                return account.code
            raise ValueError(f'No default {kind} account configured for branch_id={branch_id}')

        accounts = query.order_by(GLAccount.is_default_liquidity.desc(), GLAccount.id.asc()).all()
        if len(accounts) == 1:
            return accounts[0].code
        if not accounts:
            raise ValueError(f'No default {kind} account configured for tenant_id={tenant_id}')
        raise ValueError(
            f'Multiple {kind} accounts exist for tenant_id={tenant_id}; branch_id is required to avoid ambiguous posting'
        )

    @staticmethod
    def get_payment_debit_account(method, branch_id=None, tenant_id=None):
        m = (method or '').strip()
        if m == 'cash':
            return GLService.get_default_liquidity_account('cash', branch_id=branch_id, tenant_id=tenant_id)
        if m in ('bank_transfer', 'card'):
            return GLService.get_default_liquidity_account('bank', branch_id=branch_id, tenant_id=tenant_id)
        if m == 'cheque':
            if tenant_id and is_dynamic_gl_mapping_enabled():
                account = resolve_gl_account(
                    tenant_id=tenant_id,
                    concept_code='CHEQUES_UNDER_COLLECTION',
                    branch_id=branch_id,
                )
                if account:
                    return account.code
                raise GLMappingError(
                    tenant_id=tenant_id,
                    concept_code='CHEQUES_UNDER_COLLECTION',
                    branch_id=branch_id,
                    issue="No GL account mapping found for cheque debit account."
                )
            return GL_ACCOUNTS.get('cheques_under_collection', '1150')
        return GLService.get_default_liquidity_account('cash', branch_id=branch_id, tenant_id=tenant_id)

    @staticmethod
    def get_customer_credit_account(customer, branch_id=None, tenant_id=None):
        if tenant_id and is_dynamic_gl_mapping_enabled():
            concept = GLService.get_customer_credit_concept(customer)
            if concept:
                account = resolve_gl_account(
                    tenant_id=tenant_id,
                    concept_code=concept,
                    branch_id=branch_id,
                )
                if account:
                    return account.code
            raise GLMappingError(
                tenant_id=tenant_id,
                concept_code=concept or 'AR',
                branch_id=branch_id,
                issue="No GL account mapping found for customer credit account."
            )
        code = '1130'
        if customer and getattr(customer, 'customer_type', None) == 'partner':
            code = '2150'
        elif customer and getattr(customer, 'customer_type', None) == 'merchant':
            code = '2115'
        return code

    @staticmethod
    def create_manual_entry(description, lines, entry_date=None, notes=None, created_by=None, currency=None, exchange_rate=1.0, branch_id=None):
        """إنشاء قيد يدوي — يستخدم post_entry بعد التحقق من الحسابات."""
        from flask_login import current_user

        entry_date = entry_date or datetime.now(timezone.utc)

        if not branch_id:
            if created_by:
                from models import User
                user = User.query.get(created_by)
                if user:
                    branch_id = user.branch_id
            elif hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                branch_id = current_user.branch_id

        user_id = created_by or (
            current_user.id if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated else None
        )
        tenant_id = gl_helpers.resolve_tenant_id(branch_id=branch_id, user_id=user_id)

        for line_data in lines:
            account_code = line_data.get('account_code') or line_data.get('account')
            account = gl_helpers.get_account(account_code, tenant_id)
            if not account:
                GLService.ensure_core_accounts(tenant_id=tenant_id)
                account = gl_helpers.get_account(account_code, tenant_id)
            if not account:
                raise ValueError(f'الحساب {account_code} غير موجود')
            if account.is_header:
                raise ValueError(f'الحساب {account.full_name} هو حساب رئيسي ولا يمكن إضافة قيود عليه')
            if not getattr(account, 'is_active', True):
                raise ValueError(f'الحساب {account.full_name} غير نشط ولا يمكن إضافة قيود عليه')

        entry = GLService.post_entry(
            lines,
            description=description,
            date=entry_date,
            currency=currency,
            exchange_rate=exchange_rate,
            branch_id=branch_id,
            user_id=user_id,
            tenant_id=tenant_id,
            entry_type='manual',
        )
        if notes:
            entry.notes = notes
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
        ).join(GLJournalEntry).filter(GLJournalEntry.is_posted == True)
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

        query = GLJournalLine.query.filter_by(account_id=account_id).join(GLJournalEntry).filter(GLJournalEntry.is_posted == True)

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
    def get_general_ledger(date_from=None, date_to=None, branch_id=None, tenant_id=None):
        """كشف حساب عام — running balance لكل حساب مع رصيد افتتاحي."""
        from sqlalchemy import func

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)

        accounts = GLAccount.query.filter_by(is_header=False)
        if tenant_id is not None:
            accounts = accounts.filter_by(tenant_id=int(tenant_id))
        accounts = accounts.order_by(GLAccount.code).all()

        result = []
        for account in accounts:
            lines_query = GLJournalLine.query.filter_by(account_id=account.id).join(
                GLJournalEntry
            ).filter(GLJournalEntry.is_posted == True)

            opening_query = GLJournalLine.query.filter_by(account_id=account.id).join(
                GLJournalEntry
            ).filter(GLJournalEntry.is_posted == True)

            if branch_id:
                lines_query = lines_query.filter(GLJournalEntry.branch_id == branch_id)
                opening_query = opening_query.filter(GLJournalEntry.branch_id == branch_id)
            if tenant_id is not None:
                lines_query = lines_query.filter(GLJournalEntry.tenant_id == int(tenant_id))
                opening_query = opening_query.filter(GLJournalEntry.tenant_id == int(tenant_id))
            if date_from:
                lines_query = lines_query.filter(func.date(GLJournalEntry.entry_date) >= date_from)
                opening_query = opening_query.filter(func.date(GLJournalEntry.entry_date) < date_from)
            if date_to:
                lines_query = lines_query.filter(func.date(GLJournalEntry.entry_date) <= date_to)

            opening_lines = opening_query.all()
            opening_debit = sum(l.debit for l in opening_lines)
            opening_credit = sum(l.credit for l in opening_lines)
            if account.type in ('asset', 'expense'):
                opening_balance = opening_debit - opening_credit
            else:
                opening_balance = opening_credit - opening_debit

            lines = lines_query.order_by(GLJournalEntry.entry_date, GLJournalEntry.id).all()
            running = opening_balance
            transactions = []
            for line in lines:
                d = line.debit
                c = line.credit
                if account.type in ('asset', 'expense'):
                    running += (d - c)
                else:
                    running += (c - d)
                transactions.append({
                    'date': line.entry.entry_date,
                    'entry_number': line.entry.entry_number,
                    'description': line.description or line.entry.description,
                    'reference': f'{line.entry.reference_type}#{line.entry.reference_id}' if line.entry.reference_type else '',
                    'debit': float(d),
                    'credit': float(c),
                    'balance': float(running),
                    'branch_id': line.entry.branch_id,
                })

            result.append({
                'account': account,
                'account_code': account.code,
                'account_name': account.full_name,
                'account_type': account.type_ar,
                'opening_balance': float(opening_balance),
                'transactions': transactions,
                'closing_balance': float(running) if transactions else float(opening_balance),
                'total_debit': sum(t['debit'] for t in transactions),
                'total_credit': sum(t['credit'] for t in transactions),
            })

        return result

    @staticmethod
    def get_partner_ledger(partner_id, date_from=None, date_to=None, branch_id=None, tenant_id=None):
        """كشف حساب شريك (عميل/مورد) من GL حسب partner_id."""
        from sqlalchemy import func

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)

        query = GLJournalLine.query.join(GLJournalEntry).filter(
            GLJournalLine.partner_id == partner_id,
            GLJournalEntry.is_posted == True,
        )
        if tenant_id is not None:
            query = query.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id:
            query = query.filter(GLJournalEntry.branch_id == branch_id)
        if date_from:
            query = query.filter(func.date(GLJournalEntry.entry_date) >= date_from)
        if date_to:
            query = query.filter(func.date(GLJournalEntry.entry_date) <= date_to)

        lines = query.order_by(GLJournalEntry.entry_date, GLJournalEntry.id).all()

        opening_query = GLJournalLine.query.join(GLJournalEntry).filter(
            GLJournalLine.partner_id == partner_id,
            GLJournalEntry.is_posted == True,
        )
        if tenant_id is not None:
            opening_query = opening_query.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id:
            opening_query = opening_query.filter(GLJournalEntry.branch_id == branch_id)
        if date_from:
            opening_query = opening_query.filter(func.date(GLJournalEntry.entry_date) < date_from)

        opening_lines = opening_query.all()
        opening_debit = sum(l.debit for l in opening_lines)
        opening_credit = sum(l.credit for l in opening_lines)
        opening_balance = opening_debit - opening_credit

        running = opening_balance
        transactions = []
        for line in lines:
            running += (line.debit - line.credit)
            transactions.append({
                'date': line.entry.entry_date,
                'entry_number': line.entry.entry_number,
                'account_code': line.account.code,
                'account_name': line.account.full_name,
                'description': line.description or line.entry.description,
                'reference': f'{line.entry.reference_type}#{line.entry.reference_id}' if line.entry.reference_type else '',
                'debit': float(line.debit),
                'credit': float(line.credit),
                'balance': float(running),
            })

        return {
            'partner_id': partner_id,
            'opening_balance': float(opening_balance),
            'transactions': transactions,
            'closing_balance': float(running),
            'total_debit': sum(t['debit'] for t in transactions),
            'total_credit': sum(t['credit'] for t in transactions),
        }

    @staticmethod
    def get_accounts_tree(tenant_id=None):
        """الحصول على شجرة الحسابات"""
        tenant_id = tenant_id or gl_helpers.resolve_tenant_id()
        root_query = GLAccount.query.filter_by(parent_id=None, is_active=True)
        if tenant_id is not None:
            root_query = root_query.filter_by(tenant_id=int(tenant_id))
        root_accounts = root_query.order_by(GLAccount.code).all()

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
    def get_trial_balance(date_from=None, date_to=None, branch_id=None, tenant_id=None):
        """ميزان المراجعة - يستخدم استعلاماً مجمعاً لتحسين الأداء."""
        from sqlalchemy import func
        from decimal import Decimal

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)

        # استعلام مجمع واحد لكل الحسابات
        agg_query = db.session.query(
            GLJournalLine.account_id,
            func.sum(GLJournalLine.debit).label('total_debit'),
            func.sum(GLJournalLine.credit).label('total_credit'),
        ).join(
            GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id
        ).filter(
            GLJournalEntry.is_posted == True
        )
        if tenant_id is not None:
            agg_query = agg_query.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id:
            agg_query = agg_query.filter(GLJournalEntry.branch_id == branch_id)
        if date_from:
            agg_query = agg_query.filter(func.date(GLJournalEntry.entry_date) >= date_from)
        if date_to:
            agg_query = agg_query.filter(func.date(GLJournalEntry.entry_date) <= date_to)
        agg_query = agg_query.group_by(GLJournalLine.account_id)

        account_totals = {}
        for row in agg_query.all():
            account_totals[row.account_id] = (
                Decimal(str(row.total_debit or 0)),
                Decimal(str(row.total_credit or 0))
            )

        accounts_query = GLAccount.query.filter_by(is_active=True)
        if tenant_id is not None:
            accounts_query = accounts_query.filter_by(tenant_id=int(tenant_id))
        accounts = accounts_query.order_by(GLAccount.code).all()

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

            debit_sum, credit_sum = account_totals.get(account.id, (Decimal('0'), Decimal('0')))

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
    def get_account_code_for_concept(concept_code, branch_id=None, tenant_id=None, fallback_key=None):
        """Resolve GL account code for a concept.
        Tries dynamic mapping first, then falls back to GL_ACCOUNTS dict.
        Raises GLMappingError if no mapping and no fallback available.
        """
        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)
        if tenant_id:
            try:
                account = resolve_gl_account(
                    tenant_id=int(tenant_id),
                    concept_code=concept_code,
                    branch_id=branch_id,
                )
                if account:
                    return account.code
            except GLMappingError:
                pass
        if fallback_key and fallback_key in GL_ACCOUNTS:
            return GL_ACCOUNTS[fallback_key]
        raise GLMappingError(
            tenant_id=tenant_id or 0,
            concept_code=concept_code,
            branch_id=branch_id,
            issue=f"No GL account mapping or fallback for concept {concept_code}.",
        )

    @staticmethod
    def get_payment_credit_account(payment_method, branch_id=None, tenant_id=None):
        """حساب الدائن عند الصرف (خروج نقدية)."""
        m = (payment_method or '').strip().lower()
        if m == 'cash':
            return GLService.get_default_liquidity_account('cash', branch_id=branch_id, tenant_id=tenant_id)
        if m in ('bank_transfer', 'card', 'bank'):
            return GLService.get_default_liquidity_account('bank', branch_id=branch_id, tenant_id=tenant_id)
        if m == 'cheque':
            return GLService.get_account_code_for_concept(
                'DEFERRED_CHEQUES_PAYABLE',
                branch_id=branch_id,
                tenant_id=tenant_id,
                fallback_key='deferred_cheques',
            )
        return GLService.get_default_liquidity_account('cash', branch_id=branch_id, tenant_id=tenant_id)

    @staticmethod
    def reconciliation_check(tenant_id=None, branch_id=None):
        """مقارنة أرصدة GL مع الأرصدة الدفترية — للكشف عن الانحرافات."""
        from sqlalchemy import func
        from decimal import Decimal

        tenant_id = tenant_id or gl_helpers.resolve_tenant_id(branch_id=branch_id)

        def _gl_balance(concept_code):
            acc = GLService._resolve_journal_line_account(
                {'concept_code': concept_code}, tenant_id, branch_id=branch_id,
                ensure_core=False, missing_ok=True,
            )
            if not acc:
                return Decimal('0')
            q = db.session.query(
                func.coalesce(func.sum(GLJournalLine.debit), 0) - func.coalesce(func.sum(GLJournalLine.credit), 0)
            ).join(GLJournalEntry).filter(
                GLJournalLine.account_id == acc.id,
                GLJournalEntry.is_posted == True,
            )
            if tenant_id is not None:
                q = q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            if branch_id:
                q = q.filter(GLJournalEntry.branch_id == branch_id)
            return Decimal(str(q.scalar() or 0))

        gl_ar = abs(_gl_balance('AR'))
        gl_ap = abs(_gl_balance('AP'))

        from models import Customer, Supplier
        customers = Customer.query.filter_by(is_active=True) if not tenant_id else Customer.query.filter_by(tenant_id=int(tenant_id), is_active=True)
        total_customer_balance = sum(Decimal(str(c.balance or 0)) for c in customers.all())
        suppliers = Supplier.query.filter_by(is_active=True) if not tenant_id else Supplier.query.filter_by(tenant_id=int(tenant_id), is_active=True)
        total_supplier_balance = sum(Decimal(str(s.get_balance_base())) for s in suppliers.all())

        return {
            'tenant_id': tenant_id,
            'ar_gl_balance': float(gl_ar),
            'ar_subledger_balance': float(total_customer_balance),
            'ar_difference': float(gl_ar - total_customer_balance),
            'ap_gl_balance': float(gl_ap),
            'ap_subledger_balance': float(total_supplier_balance),
            'ap_difference': float(gl_ap - total_supplier_balance),
        }