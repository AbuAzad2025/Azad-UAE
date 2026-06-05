"""
Treasury & Cash Position Service
Phase 8: Multi-branch bank, cashier, and post-dated cheque position tracking.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from extensions import db


class TreasuryService:
    """خدمة المركز المالي والخزينة"""

    LIQUIDITY_KINDS = {
        'cash': 'نقدية',
        'bank': 'بنك',
        'gateway': 'بوابة دفع',
        'card': 'بطاقة',
        'in_transit': 'تحت التحصيل',
    }

    CHEQUE_BUCKETS = [
        ('overdue', 'متأخر', lambda d: d < 0),
        ('0_7_days', '0-7 أيام', lambda d: 0 <= d <= 7),
        ('8_30_days', '8-30 يوم', lambda d: 8 <= d <= 30),
        ('31_plus_days', '31+ يوم', lambda d: d > 30),
    ]

    @staticmethod
    def get_liquidity_position(tenant_id, branch_id=None):
        """
        جلب مركز السيولة (نقدية + بنوك + بوابات + تحت التحصيل).
        Primary: CashBox rows. Fallback: GLAccount liquidity_kind.
        """
        from models import CashBox, GLAccount

        accounts = []
        total_balance = Decimal('0')

        # 1. Try CashBox first
        cashbox_q = CashBox.query.filter_by(tenant_id=tenant_id, is_active=True)
        if branch_id is not None:
            cashbox_q = cashbox_q.filter(CashBox.branch_id == branch_id)
        cashboxes = cashbox_q.order_by(CashBox.code).all()

        if cashboxes:
            for box in cashboxes:
                kind = box.box_type or 'cash'
                # Normalize box_type to liquidity_kind
                if kind in ('bank_account',):
                    kind = 'bank'
                elif kind in ('payment_gateway', 'digital_wallet'):
                    kind = 'gateway'
                elif kind in ('cheque_under_collection',):
                    kind = 'in_transit'

                balance = Decimal(str(box.current_balance or 0))
                accounts.append({
                    'id': box.id,
                    'code': box.code,
                    'name': box.name_ar or box.name_en or box.code,
                    'name_en': box.name_en,
                    'kind': kind,
                    'kind_label': TreasuryService.LIQUIDITY_KINDS.get(kind, kind),
                    'currency': box.currency or 'AED',
                    'balance': float(balance),
                    'balance_aed': float(balance),
                    'source': 'cash_box',
                    'branch_id': box.branch_id,
                })
                total_balance += balance
        else:
            # 2. Fallback: GLAccount liquidity_kind
            gl_q = GLAccount.query.filter(
                GLAccount.tenant_id == tenant_id,
                GLAccount.is_active == True,
                GLAccount.is_header == False,
                GLAccount.liquidity_kind.in_(list(TreasuryService.LIQUIDITY_KINDS.keys()))
            )
            if branch_id is not None:
                # GLAccount doesn't have branch_id; skip branch filter for fallback
                pass
            gl_accounts = gl_q.order_by(GLAccount.code).all()

            for acc in gl_accounts:
                kind = acc.liquidity_kind or 'cash'
                balance = Decimal(str(acc.get_balance() or 0))
                accounts.append({
                    'id': acc.id,
                    'code': acc.code,
                    'name': getattr(acc, 'name_ar', None) or getattr(acc, 'name', None) or acc.code,
                    'name_en': getattr(acc, 'name_en', None),
                    'kind': kind,
                    'kind_label': TreasuryService.LIQUIDITY_KINDS.get(kind, kind),
                    'currency': getattr(acc, 'currency', 'AED') or 'AED',
                    'balance': float(balance),
                    'balance_aed': float(balance),
                    'source': 'gl_account',
                    'branch_id': None,
                })
                total_balance += balance

        # Group by kind
        kind_summary = {}
        for a in accounts:
            k = a['kind']
            if k not in kind_summary:
                kind_summary[k] = {
                    'kind': k,
                    'label': TreasuryService.LIQUIDITY_KINDS.get(k, k),
                    'count': 0,
                    'total_balance': Decimal('0'),
                }
            kind_summary[k]['count'] += 1
            kind_summary[k]['total_balance'] += Decimal(str(a['balance']))

        return {
            'accounts': accounts,
            'kind_summary': {k: {
                'kind': v['kind'],
                'label': v['label'],
                'count': v['count'],
                'total_balance': float(v['total_balance']),
            } for k, v in kind_summary.items()},
            'total_balance': float(total_balance),
            'account_count': len(accounts),
        }

    @staticmethod
    def get_cheque_maturity(tenant_id, branch_id=None):
        """
        جلب الشيكات الواردة والصادرة حسب buckets الاستحقاق.
        """
        from models import Cheque

        query = Cheque.query.filter(
            Cheque.tenant_id == tenant_id,
            Cheque.is_active == True,
            Cheque.status.in_(['pending', 'deposited', 'under_collection'])
        )
        if branch_id is not None:
            query = query.filter(Cheque.branch_id == branch_id)

        cheques = query.order_by(Cheque.due_date.asc()).all()

        # Update days_until_due for accurate bucketing
        today = datetime.now(timezone.utc).date()
        for c in cheques:
            if c.due_date:
                c.days_until_due = (c.due_date - today).days

        incoming = [c for c in cheques if c.cheque_type == 'incoming']
        outgoing = [c for c in cheques if c.cheque_type == 'outgoing']

        def _bucket_cheques(cheque_list):
            buckets = {}
            for key, label, pred in TreasuryService.CHEQUE_BUCKETS:
                items = [c for c in cheque_list if pred(c.days_until_due or 0)]
                total = sum(Decimal(str(c.amount_aed or 0)) for c in items)
                buckets[key] = {
                    'label': label,
                    'count': len(items),
                    'total_amount': float(total),
                    'items': [
                        {
                            'id': c.id,
                            'cheque_number': c.cheque_number,
                            'cheque_bank_number': c.cheque_bank_number,
                            'bank_name': c.bank_name,
                            'drawer_name': c.drawer_name,
                            'payee_name': c.payee_name,
                            'amount_aed': float(c.amount_aed or 0),
                            'due_date': c.due_date.isoformat() if c.due_date else None,
                            'days_until_due': c.days_until_due,
                            'status': c.status,
                            'status_ar': c.cheque_type_ar,
                        }
                        for c in items
                    ],
                }
            total_all = sum(Decimal(str(c.amount_aed or 0)) for c in cheque_list)
            return {
                'buckets': buckets,
                'total_count': len(cheque_list),
                'total_amount': float(total_all),
            }

        return {
            'incoming': _bucket_cheques(incoming),
            'outgoing': _bucket_cheques(outgoing),
            'today': today.isoformat(),
        }

    @staticmethod
    def get_bank_reconciliation_status(tenant_id, branch_id=None, limit=5):
        """
        جلب آخر عمليات مطابقة البنك.
        """
        from models import BankReconciliation, GLAccount

        # BankReconciliation has no direct tenant_id; filter via GLAccount
        recs = (
            BankReconciliation.query
            .join(GLAccount, BankReconciliation.bank_account_id == GLAccount.id)
            .filter(GLAccount.tenant_id == tenant_id)
            .order_by(BankReconciliation.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                'id': r.id,
                'reconciliation_number': r.reconciliation_number,
                'bank_account_code': r.bank_account.code if r.bank_account else None,
                'bank_account_name': getattr(r.bank_account, 'name_ar', None) or getattr(r.bank_account, 'name', None),
                'period_start': r.period_start.isoformat() if r.period_start else None,
                'period_end': r.period_end.isoformat() if r.period_end else None,
                'closing_balance_per_books': float(r.closing_balance_per_books or 0),
                'closing_balance_per_bank': float(r.closing_balance_per_bank or 0),
                'difference': float(r.difference or 0),
                'status': r.status,
                'status_ar': r.status_ar,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in recs
        ]

    @staticmethod
    def build_dashboard(tenant_id, branch_id=None):
        """
        بناء تقرير المركز المالي الشامل.
        """
        liquidity = TreasuryService.get_liquidity_position(tenant_id, branch_id)
        cheques = TreasuryService.get_cheque_maturity(tenant_id, branch_id)
        reconciliations = TreasuryService.get_bank_reconciliation_status(tenant_id, branch_id)

        return {
            'liquidity': liquidity,
            'cheques': cheques,
            'reconciliations': reconciliations,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
