"""Unit tests for CashFlowService — operating, investing, financing, cash balance."""
from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

import pytest

from extensions import db
from models import (
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    Payment,
    Receipt,
    Expense,
    Branch,
)
from services.cash_flow_service import CashFlowService
from services.gl_tree_builder import GLTreeBuilder


PERIOD_START = date(2026, 6, 1)
PERIOD_END = date(2026, 6, 30)
BEFORE_PERIOD = date(2026, 5, 15)
IN_PERIOD = date(2026, 6, 15)


@pytest.fixture(autouse=True)
def _transaction_rollback(db_session):
    """Isolate each test via session rollback (pairs with conftest db_session)."""
    yield
    db_session.rollback()


@pytest.fixture
def cf_seed(
    db_session,
    sample_tenant,
    sample_branch,
    sample_customer,
    sample_supplier,
    sample_user,
    sample_expense_category,
    sample_gl_accounts,
):
    """Seed ledger + operational documents for cash-flow math verification."""
    tid = sample_tenant.id
    bid = sample_branch.id

    def _acct(code, **extra):
        row = GLAccount.query.filter_by(tenant_id=tid, code=code).first()
        if row:
            for k, v in extra.items():
                setattr(row, k, v)
            return row
        data = {
            'tenant_id': tid,
            'branch_id': bid,
            'code': code,
            'name': f'Account {code}',
            'type': 'asset',
            'is_active': True,
            'is_header': False,
        }
        data.update(extra)
        row = GLAccount(**data)
        db_session.add(row)
        db_session.flush()
        return row

    cash = _acct(
        GLTreeBuilder._branch_account_code('1110', bid),
        type='asset', liquidity_kind='cash',
    )
    bank = _acct(
        GLTreeBuilder._branch_account_code('1120', bid),
        type='asset', liquidity_kind='bank',
    )
    fixed_asset = _acct('1200', type='asset', sub_type='fixed_asset')
    salary = _acct('6100', type='expense')
    capital = _acct('3100', type='equity')
    owner_draw = _acct('3300', type='equity')
    loans = _acct('2210', type='liability')
    offset = _acct('3200', type='equity')

    def _entry(entry_date, entry_number, lines):
        entry = GLJournalEntry(
            tenant_id=tid,
            branch_id=bid,
            entry_number=entry_number,
            entry_date=datetime.combine(entry_date, datetime.min.time(), tzinfo=timezone.utc),
            description=f'CF test {entry_number}',
            is_posted=True,
            total_debit=sum(d for _, d, _c in lines),
            total_credit=sum(c for _, _d, c in lines),
        )
        db_session.add(entry)
        db_session.flush()
        for account, debit, credit in lines:
            db_session.add(GLJournalLine(
                tenant_id=tid,
                entry_id=entry.id,
                account_id=account.id,
                debit=Decimal(str(debit)),
                credit=Decimal(str(credit)),
            ))
        return entry

    uid = uuid.uuid4().hex[:6]

    # Cash beginning balances (before period)
    _entry(BEFORE_PERIOD, f'JE-CF-BEG-CASH-{uid}', [
        (cash, 3000, 0), (offset, 0, 3000),
    ])
    _entry(BEFORE_PERIOD, f'JE-CF-BEG-BANK-{uid}', [
        (bank, 2000, 0), (offset, 0, 2000),
    ])

    # Operating — salary GL debit
    _entry(IN_PERIOD, f'JE-CF-SAL-{uid}', [
        (salary, 100, 0), (offset, 0, 100),
    ])

    # Investing — fixed asset purchase (debit) and sale (credit)
    _entry(IN_PERIOD, f'JE-CF-FA-BUY-{uid}', [
        (fixed_asset, 5000, 0), (offset, 0, 5000),
    ])
    _entry(IN_PERIOD, f'JE-CF-FA-SELL-{uid}', [
        (fixed_asset, 0, 1500), (offset, 1500, 0),
    ])

    # Financing
    _entry(IN_PERIOD, f'JE-CF-CAP-{uid}', [
        (capital, 0, 10000), (offset, 10000, 0),
    ])
    _entry(IN_PERIOD, f'JE-CF-DRAW-{uid}', [
        (owner_draw, 2000, 0), (offset, 0, 2000),
    ])
    _entry(IN_PERIOD, f'JE-CF-LOAN-IN-{uid}', [
        (loans, 0, 5000), (offset, 5000, 0),
    ])
    _entry(IN_PERIOD, f'JE-CF-LOAN-OUT-{uid}', [
        (loans, 1000, 0), (offset, 0, 1000),
    ])

    in_period_dt = datetime.combine(IN_PERIOD, datetime.min.time(), tzinfo=timezone.utc)

    db_session.add(Receipt(
        tenant_id=tid,
        branch_id=bid,
        receipt_number=f'RC-CF-{uid}',
        customer_id=sample_customer.id,
        amount=Decimal('100.00'),
        currency='USD',
        exchange_rate=Decimal('3.675'),
        amount_aed=Decimal('1000.00'),
        payment_method='cash',
        payment_confirmed=True,
        receipt_date=in_period_dt,
        user_id=sample_user.id,
    ))

    db_session.add(Payment(
        tenant_id=tid,
        branch_id=bid,
        payment_number=f'PY-CF-{uid}',
        payment_type='supplier',
        direction='outgoing',
        supplier_id=sample_supplier.id,
        amount=Decimal('300.00'),
        amount_aed=Decimal('300.00'),
        payment_method='bank_transfer',
        payment_confirmed=True,
        payment_date=in_period_dt,
        user_id=sample_user.id,
    ))

    db_session.add(Expense(
        tenant_id=tid,
        branch_id=bid,
        expense_number=f'EX-CF-{uid}',
        category_id=sample_expense_category.id,
        description='CF test expense',
        amount=Decimal('200.00'),
        amount_aed=Decimal('200.00'),
        payment_method='cash',
        expense_date=in_period_dt,
        user_id=sample_user.id,
    ))

    # Noise — excluded from operating totals
    db_session.add(Receipt(
        tenant_id=tid,
        branch_id=bid,
        receipt_number=f'RC-CF-BAD-{uid}',
        customer_id=sample_customer.id,
        amount=Decimal('999.00'),
        amount_aed=Decimal('999.00'),
        payment_method='cheque',
        payment_confirmed=True,
        receipt_date=in_period_dt,
        user_id=sample_user.id,
    ))
    db_session.add(Receipt(
        tenant_id=tid,
        branch_id=bid,
        receipt_number=f'RC-CF-PEND-{uid}',
        customer_id=sample_customer.id,
        amount=Decimal('888.00'),
        amount_aed=Decimal('888.00'),
        payment_method='cash',
        payment_confirmed=False,
        receipt_date=in_period_dt,
        user_id=sample_user.id,
    ))

    db_session.commit()

    return {
        'tenant_id': tid,
        'branch_id': bid,
        'customer_id': sample_customer.id,
        'cash': cash,
        'bank': bank,
        'expected_operating_net': 400.0,      # 1000 - 300 - 200 - 100
        'expected_investing_net': -3500.0,    # 1500 - 5000
        'expected_financing_net': 12000.0,    # 10000 + 5000 - 2000 - 1000
        'expected_cash_beginning': 5000.0,    # 3000 + 2000
    }


class TestCashFlowOperating:
    def test_receipt_foreign_currency_uses_amount_aed_not_raw_amount(self, cf_seed):
        op = CashFlowService._get_operating_activities(
            PERIOD_START, PERIOD_END,
            tenant_id=cf_seed['tenant_id'],
            branch_id=cf_seed['branch_id'],
        )
        assert op['receipts_from_customers'] == 1000.0
        assert op['receipts_from_customers'] != 100.0
        assert op['receipts_from_customers'] != 367.5

    def test_operating_aggregates_amount_aed_and_gl_salaries(self, cf_seed):
        op = CashFlowService._get_operating_activities(
            PERIOD_START, PERIOD_END,
            tenant_id=cf_seed['tenant_id'],
            branch_id=cf_seed['branch_id'],
        )
        assert op['receipts_from_customers'] == 1000.0
        assert op['payments_to_suppliers'] == 300.0
        assert op['payments_for_expenses'] == 200.0
        assert op['payments_for_salaries'] == 100.0
        assert op['net_cash_from_operating'] == cf_seed['expected_operating_net']
        assert len(op['items']) == 4

    def test_operating_zero_when_no_salary_account(self, db_session, sample_tenant, sample_branch):
        tid = sample_tenant.id
        GLAccount.query.filter_by(tenant_id=tid, code='6100').delete()
        db_session.commit()

        op = CashFlowService._get_operating_activities(
            PERIOD_START, PERIOD_END, tenant_id=tid,
        )
        assert op['payments_for_salaries'] == 0.0
        assert op['net_cash_from_operating'] == 0.0


class TestCashFlowInvesting:
    def test_investing_fixed_asset_purchase_and_sale(self, cf_seed):
        inv = CashFlowService._get_investing_activities(
            PERIOD_START, PERIOD_END,
            tenant_id=cf_seed['tenant_id'],
            branch_id=cf_seed['branch_id'],
        )
        assert inv['purchase_of_fixed_assets'] == 5000.0
        assert inv['sale_of_fixed_assets'] == 1500.0
        assert inv['net_cash_from_investing'] == cf_seed['expected_investing_net']


class TestCashFlowFinancing:
    def test_financing_capital_loans_and_draws(self, cf_seed):
        fin = CashFlowService._get_financing_activities(
            PERIOD_START, PERIOD_END,
            tenant_id=cf_seed['tenant_id'],
            branch_id=cf_seed['branch_id'],
        )
        assert fin['capital_contributions'] == 10000.0
        assert fin['owner_withdrawals'] == 2000.0
        assert fin['loans_received'] == 5000.0
        assert fin['loan_repayments'] == 1000.0
        assert fin['net_cash_from_financing'] == cf_seed['expected_financing_net']

    def test_financing_zero_without_equity_accounts(self, db_session, sample_tenant):
        tid = sample_tenant.id
        for code in ('3100', '3300', '2210'):
            GLAccount.query.filter_by(tenant_id=tid, code=code).delete()
        db_session.commit()

        fin = CashFlowService._get_financing_activities(
            PERIOD_START, PERIOD_END, tenant_id=tid,
        )
        assert fin['net_cash_from_financing'] == 0.0


class TestCashFlowBalance:
    def test_cash_balance_beginning_strictly_before_period(self, cf_seed):
        accounts = [cf_seed['cash'], cf_seed['bank']]
        beginning = CashFlowService._get_cash_balance(
            accounts, PERIOD_START, is_beginning=True,
            tenant_id=cf_seed['tenant_id'],
            branch_id=cf_seed['branch_id'],
        )
        assert float(beginning) == cf_seed['expected_cash_beginning']

    def test_cash_balance_ending_includes_in_period_movements(self, cf_seed, db_session):
        tid = cf_seed['tenant_id']
        bid = cf_seed['branch_id']
        uid = uuid.uuid4().hex[:6]
        offset = GLAccount.query.filter_by(tenant_id=tid, code='3200').first()
        entry = GLJournalEntry(
            tenant_id=tid,
            branch_id=bid,
            entry_number=f'JE-CF-END-{uid}',
            entry_date=datetime.combine(IN_PERIOD, datetime.min.time(), tzinfo=timezone.utc),
            description='In-period cash deposit',
            is_posted=True,
            total_debit=Decimal('500'),
            total_credit=Decimal('500'),
        )
        db_session.add(entry)
        db_session.flush()
        db_session.add(GLJournalLine(
            tenant_id=tid,
            entry_id=entry.id,
            account_id=cf_seed['cash'].id,
            debit=Decimal('500'),
            credit=Decimal('0'),
        ))
        db_session.add(GLJournalLine(
            tenant_id=tid,
            entry_id=entry.id,
            account_id=offset.id,
            debit=Decimal('0'),
            credit=Decimal('500'),
        ))
        db_session.commit()

        accounts = [cf_seed['cash'], cf_seed['bank']]
        ending = CashFlowService._get_cash_balance(
            accounts, PERIOD_END, is_beginning=False,
            tenant_id=tid, branch_id=bid,
        )
        assert float(ending) == 5500.0


class TestGenerateCashFlow:
    def test_generate_cash_flow_string_dates_and_reconciliation(self, cf_seed):
        report = CashFlowService.generate_cash_flow(
            '2026-06-01', '2026-06-30',
            branch_id=cf_seed['branch_id'],
            tenant_id=cf_seed['tenant_id'],
        )

        assert report['period_start'] == PERIOD_START
        assert report['period_end'] == PERIOD_END
        assert report['branch_id'] == cf_seed['branch_id']

        op_net = report['operating_activities']['net_cash_from_operating']
        inv_net = report['investing_activities']['net_cash_from_investing']
        fin_net = report['financing_activities']['net_cash_from_financing']
        expected_net = op_net + inv_net + fin_net

        assert report['net_change_in_cash'] == pytest.approx(expected_net)
        assert report['cash_beginning'] == cf_seed['expected_cash_beginning']
        assert report['cash_ending'] == pytest.approx(
            report['cash_beginning'] + report['net_change_in_cash']
        )

    def test_branch_isolation_excludes_other_branch(self, cf_seed, db_session, sample_tenant):
        other = Branch(
            tenant_id=sample_tenant.id,
            name='Other Branch',
            code=f'OTH{uuid.uuid4().hex[:4]}',
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()

        uid = uuid.uuid4().hex[:6]
        db_session.add(Receipt(
            tenant_id=sample_tenant.id,
            branch_id=other.id,
            receipt_number=f'RC-OTH-{uid}',
            customer_id=cf_seed['customer_id'],
            amount=Decimal('5000'),
            amount_aed=Decimal('5000'),
            payment_method='cash',
            payment_confirmed=True,
            receipt_date=datetime.combine(IN_PERIOD, datetime.min.time(), tzinfo=timezone.utc),
        ))
        db_session.commit()

        scoped = CashFlowService._get_operating_activities(
            PERIOD_START, PERIOD_END,
            tenant_id=cf_seed['tenant_id'],
            branch_id=cf_seed['branch_id'],
        )
        assert scoped['receipts_from_customers'] == 1000.0
