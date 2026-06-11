"""
Multi-currency deep reconciliation tests.
End-to-end flow verification for foreign-currency GL entries,
exchange rate freezing, rounding consistency, and tenant isolation.
"""
import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bal(code, tenant_id, branch_id=None):
    from sqlalchemy import func
    from extensions import db
    from models import GLAccount, GLJournalLine, GLJournalEntry
    acc = GLAccount.query.filter_by(tenant_id=tenant_id, code=code).first()
    if not acc:
        return Decimal('0')
    q = db.session.query(func.coalesce(func.sum(GLJournalLine.amount_aed), 0)).join(
        GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id
    ).filter(
        GLJournalLine.account_id == acc.id,
        GLJournalEntry.is_posted == True,
    )
    if tenant_id is not None:
        q = q.filter(GLJournalEntry.tenant_id == tenant_id)
    if branch_id is not None:
        q = q.filter(GLJournalEntry.branch_id == branch_id)
    total = Decimal(str(q.scalar() or 0))
    if acc.type in ('asset', 'expense'):
        return total
    return -total


def _entries_for(ref_type, ref_id, tenant_id):
    from models import GLJournalEntry
    q = GLJournalEntry.query.filter_by(
        reference_type=ref_type, reference_id=ref_id, tenant_id=tenant_id, is_posted=True
    )
    return q.all()


# ---------------------------------------------------------------------------
# Environment fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def env(app, db_session):
    from extensions import db
    from services.gl_service import GLService
    from models import Tenant, Branch, User, Customer, Supplier, Product, Warehouse, ProductWarehouseCost

    tid = Tenant.query.order_by(Tenant.id).first()
    if not tid:
        tid = Tenant(name='RecTest', name_ar='RecTest', slug='rectest', email='r@t.com', phone_1='0500000000', country='AE', subscription_plan='basic')
        db.session.add(tid)
        db.session.flush()
    tenant_id = tid.id
    GLService.ensure_core_accounts(tenant_id=tenant_id)
    from services.gl_provisioning_service import GLProvisioningService
    GLProvisioningService.provision_tenant(tenant_id)

    branch = Branch.query.filter_by(tenant_id=tenant_id).first()
    if not branch:
        branch = Branch(tenant_id=tenant_id, name='Main', code='MAIN')
        db.session.add(branch)
        db.session.flush()

    from models import Role
    role = Role.query.filter_by(slug='owner').first()
    if not role:
        role = Role(name='Owner', slug='owner')
        db.session.add(role)
        db.session.flush()
    user = User.query.filter_by(tenant_id=tenant_id).first()
    if not user:
        user = User(tenant_id=tenant_id, username='rectestuser', email='u@t.com', full_name='Test', is_active=True, is_owner=True, branch_id=branch.id, role_id=role.id)
        user.set_password('p')
        db.session.add(user)
        db.session.flush()

    customer = Customer.query.filter_by(tenant_id=tenant_id).first()
    if not customer:
        customer = Customer(tenant_id=tenant_id, name='Test Customer', phone='0500000001')
        db.session.add(customer)
        db.session.flush()

    supplier = Supplier.query.filter_by(tenant_id=tenant_id).first()
    if not supplier:
        supplier = Supplier(tenant_id=tenant_id, name='Test Supplier', phone='0500000002')
        db.session.add(supplier)
        db.session.flush()

    product = Product.query.filter_by(tenant_id=tenant_id, name='Reconciliation Test Product').first()
    if not product:
        product = Product(tenant_id=tenant_id, name='Reconciliation Test Product', current_stock=0, cost_price=Decimal('600'), regular_price=Decimal('1000'), has_serial_number=False)
        db.session.add(product)
        db.session.flush()

    wh = Warehouse.query.filter_by(tenant_id=tenant_id).first()
    if not wh:
        wh = Warehouse(tenant_id=tenant_id, name='Test WH', code='TWH', branch_id=branch.id)
        db.session.add(wh)
        db.session.flush()

    pwc = ProductWarehouseCost.query.filter_by(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id).first()
    if not pwc:
        pwc = ProductWarehouseCost(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id, total_quantity=Decimal('0'), total_value=Decimal('0'), average_cost=Decimal('0'))
        db.session.add(pwc)
        db.session.flush()

    from services.stock_service import StockService
    StockService.add_stock(product.id, Decimal('100'), reference_type='adjustment', reference_id=1, warehouse_id=wh.id)
    db.session.commit()

    env = {
        'tenant_id': tenant_id,
        'branch_id': branch.id,
        'user': user,
        'customer': customer,
        'supplier': supplier,
        'product': product,
        'warehouse': wh,
        'pwc': pwc,
    }
    yield env


# ---------------------------------------------------------------------------
# 1. Foreign-currency sale lifecycle
# ---------------------------------------------------------------------------

class TestForeignCurrencySaleLifecycle:
    def test_usd_sale_gl_and_customer_balance(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from models import Sale, Customer, GLJournalEntry
            from unittest.mock import patch

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            ar_before = _bal('1130', tid)
            rev_before = _bal('4100', tid)
            cust_bal_before = customer.balance or Decimal('0')

            with patch('services.sale_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 3.67}
                sale = SaleService.create_sale(
                    customer=customer,
                    seller=user,
                    lines_data=[{'product': product, 'quantity': 1, 'unit_price': Decimal('1000')}],
                    warehouse_id=wh.id,
                    currency='USD',
                    tax_rate=Decimal('0'),
                )
            db.session.commit()
            sale = Sale.query.get(sale.id)
            customer = Customer.query.get(customer.id)

            assert sale.currency == 'USD', 'Sale currency must be USD'
            assert sale.exchange_rate == Decimal('3.67'), 'Exchange rate must be 3.67'
            assert sale.amount == Decimal('1000'), 'Sale amount must be 1000 USD'
            expected_amount_aed = (Decimal('1000') * Decimal('3.67')).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            assert sale.amount_aed == expected_amount_aed, f'Sale amount AED must be {expected_amount_aed}'

            assert customer.balance == cust_bal_before + expected_amount_aed, 'Customer balance must increase by AED sale amount'

            entries = _entries_for('Sale', sale.id, tid)
            assert len(entries) >= 1, 'Sale must create at least one GL entry'
            entry = entries[0]
            assert entry.currency == 'USD', 'GL entry currency must be USD'
            assert entry.exchange_rate == Decimal('3.67'), 'GL entry exchange rate must be 3.67'
            assert entry.total_debit == entry.total_credit, 'GL entry must be balanced'

            ar_change = _bal('1130', tid) - ar_before
            rev_change = _bal('4100', tid) - rev_before
            assert ar_change == expected_amount_aed, f'AR must increase by {expected_amount_aed} AED'
            assert rev_change == expected_amount_aed, f'Revenue must increase by {expected_amount_aed} AED'

            for line in entry.lines:
                if line.account and line.account.code == '1130':
                    assert line.debit == expected_amount_aed, 'AR line debit must equal AED amount'
                    assert line.amount_aed == expected_amount_aed, 'AR line amount_aed must equal AED amount'
                    assert line.amount == Decimal('1000'), 'AR line original amount must be 1000 USD'
                elif line.account and line.account.code == '4100':
                    assert line.credit == expected_amount_aed, 'Revenue line credit must equal AED amount'
                    assert line.amount_aed == -expected_amount_aed, 'Revenue line amount_aed must be negative'
                    assert line.amount == -Decimal('1000'), 'Revenue line original amount must be -1000 USD'


# ---------------------------------------------------------------------------
# 2. Foreign-currency payment lifecycle
# ---------------------------------------------------------------------------

class TestForeignCurrencyPaymentLifecycle:
    def test_usd_payment_updates_customer_and_gl(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from models import Sale, Customer, GLJournalEntry
            from unittest.mock import patch

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            with patch('services.sale_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 3.67}
                sale = SaleService.create_sale(
                    customer=customer,
                    seller=user,
                    lines_data=[{'product': product, 'quantity': 1, 'unit_price': Decimal('1000')}],
                    warehouse_id=wh.id,
                    currency='USD',
                    tax_rate=Decimal('0'),
                )
            db.session.commit()
            sale = Sale.query.get(sale.id)
            customer = Customer.query.get(customer.id)
            cust_bal_after_sale = customer.balance or Decimal('0')

            ar_before = _bal('1130', tid)
            cuc_before = _bal('1150', tid)

            payment = SaleService.create_payment_for_sale(
                sale=sale,
                amount=Decimal('500'),
                payment_method='cheque',
                currency='USD',
                exchange_rate=3.67,
                cheque_number='CHK-USD-001',
                cheque_date=str(datetime.now(timezone.utc).date() + timedelta(days=30)),
                bank_name='Test Bank',
            )
            db.session.commit()
            customer = Customer.query.get(customer.id)

            expected_payment_aed = (Decimal('500') * Decimal('3.67')).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            assert customer.balance == cust_bal_after_sale - expected_payment_aed, 'Customer balance must decrease by payment AED'

            entries = _entries_for('Payment', payment.id, tid)
            assert len(entries) >= 1, 'Payment must create at least one GL entry'
            entry = entries[0]
            assert entry.currency == 'USD', 'Payment GL entry currency must be USD'
            assert entry.exchange_rate == Decimal('3.67'), 'Payment GL entry exchange rate must be 3.67'
            assert entry.total_debit == entry.total_credit, 'Payment GL entry must be balanced'

            ar_change = _bal('1130', tid) - ar_before
            cuc_change = _bal('1150', tid) - cuc_before
            assert ar_change == -expected_payment_aed, f'AR must decrease by {expected_payment_aed} AED'
            assert cuc_change == expected_payment_aed, f'CUC must increase by {expected_payment_aed} AED'

            for line in entry.lines:
                if line.account and line.account.code == '1150':
                    assert line.debit == expected_payment_aed, 'CUC line debit must equal AED amount'
                    assert line.amount_aed == expected_payment_aed, 'CUC line amount_aed must equal AED amount'
                    assert line.amount == Decimal('500'), 'CUC line original amount must be 500 USD'
                elif line.account and line.account.code == '1130':
                    assert line.credit == expected_payment_aed, 'AR line credit must equal AED amount'
                    assert line.amount_aed == -expected_payment_aed, 'AR line amount_aed must be negative'
                    assert line.amount == -Decimal('500'), 'AR line original amount must be -500 USD'


# ---------------------------------------------------------------------------
# 3. Foreign-currency reversal
# ---------------------------------------------------------------------------

class TestForeignCurrencyReversal:
    def test_usd_sale_reversal_preserves_currency_and_zeroes_balances(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from models import Sale, GLJournalEntry
            from unittest.mock import patch

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            ar_before = _bal('1130', tid)
            rev_before = _bal('4100', tid)

            with patch('services.sale_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 3.67}
                sale = SaleService.create_sale(
                    customer=customer,
                    seller=user,
                    lines_data=[{'product': product, 'quantity': 1, 'unit_price': Decimal('1000')}],
                    warehouse_id=wh.id,
                    currency='USD',
                    tax_rate=Decimal('0'),
                )
            db.session.commit()

            entries = _entries_for('Sale', sale.id, tid)
            assert len(entries) >= 1
            original_entry = entries[0]
            original_lines = {line.account.code: line for line in original_entry.lines if line.account}

            reversed_entry = original_entry.reverse_entry()
            db.session.commit()

            assert reversed_entry.currency == 'USD', 'Reversed entry currency must be USD'
            assert reversed_entry.exchange_rate == Decimal('3.67'), 'Reversed entry exchange rate must be 3.67'
            assert reversed_entry.is_posted is True, 'Reversed entry must be posted'

            for line in reversed_entry.lines:
                if line.account and line.account.code in original_lines:
                    orig = original_lines[line.account.code]
                    assert line.amount_aed == -orig.amount_aed, f'Reversed line amount_aed must negate original for {line.account.code}'
                    assert line.amount == -orig.amount, f'Reversed line amount must negate original for {line.account.code}'

            assert _bal('1130', tid) == ar_before, 'AR must return to pre-sale balance'
            assert _bal('4100', tid) == rev_before, 'Revenue must return to pre-sale balance'


# ---------------------------------------------------------------------------
# 4. Rounding consistency
# ---------------------------------------------------------------------------

class TestRoundingConsistency:
    def test_usd_sale_rounding_matches_gl(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from models import Sale, GLJournalEntry
            from unittest.mock import patch

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            rate = Decimal('3.6725')
            unit_price = Decimal('333.33')

            with patch('services.sale_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': float(rate)}
                sale = SaleService.create_sale(
                    customer=customer,
                    seller=user,
                    lines_data=[{'product': product, 'quantity': 1, 'unit_price': unit_price}],
                    warehouse_id=wh.id,
                    currency='USD',
                    tax_rate=Decimal('0'),
                )
            db.session.commit()
            sale = Sale.query.get(sale.id)

            expected_amount_aed = (unit_price * rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            assert sale.amount_aed == expected_amount_aed, 'Sale amount_aed must match rounded product of amount and rate'

            entries = _entries_for('Sale', sale.id, tid)
            assert len(entries) >= 1
            entry = entries[0]
            gl_total_aed = Decimal('0')
            for line in entry.lines:
                gl_total_aed += line.amount_aed
            assert gl_total_aed == Decimal('0'), 'GL entry lines must sum to zero (balanced)'

            gl_ar_aed = Decimal('0')
            for line in entry.lines:
                if line.account and line.account.code == '1130':
                    gl_ar_aed += line.amount_aed
            assert gl_ar_aed == expected_amount_aed, f'GL AR amount_aed {gl_ar_aed} must match sale amount_aed {expected_amount_aed}'


# ---------------------------------------------------------------------------
# 5. Multi-tenant isolation
# ---------------------------------------------------------------------------

class TestMultiTenantIsolation:
    def test_foreign_currency_balances_isolated_per_tenant(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from services.gl_service import GLService
            from services.gl_provisioning_service import GLProvisioningService
            from models import Tenant, Branch, User, Customer, Product, Warehouse, ProductWarehouseCost
            from unittest.mock import patch

            tid_a = env['tenant_id']
            user_a = env['user']
            product_a = env['product']
            wh_a = env['warehouse']
            customer_a = env['customer']

            ar_before_a = _bal('1130', tid_a)
            rev_before_a = _bal('4100', tid_a)

            with patch('services.sale_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 3.67}
                sale_a = SaleService.create_sale(
                    customer=customer_a,
                    seller=user_a,
                    lines_data=[{'product': product_a, 'quantity': 1, 'unit_price': Decimal('1000')}],
                    warehouse_id=wh_a.id,
                    currency='USD',
                    tax_rate=Decimal('0'),
                )
            db.session.commit()

            tid_b = Tenant(name='TenantB', name_ar='TenantB', slug='tenantb', email='b@t.com', phone_1='0500000003', country='AE', subscription_plan='basic')
            db.session.add(tid_b)
            db.session.flush()
            GLService.ensure_core_accounts(tenant_id=tid_b.id)
            GLProvisioningService.provision_tenant(tid_b.id)

            branch_b = Branch(tenant_id=tid_b.id, name='MainB', code='MAINB')
            db.session.add(branch_b)
            db.session.flush()

            user_b = User(tenant_id=tid_b.id, username='userb', email='u@b.com', full_name='User B', is_active=True, is_owner=True, branch_id=branch_b.id, role_id=user_a.role_id)
            user_b.set_password('p')
            db.session.add(user_b)
            db.session.flush()

            customer_b = Customer(tenant_id=tid_b.id, name='Customer B', phone='0500000004')
            db.session.add(customer_b)
            db.session.flush()

            product_b = Product(tenant_id=tid_b.id, name='Product B', current_stock=100, cost_price=Decimal('600'), regular_price=Decimal('1000'), has_serial_number=False)
            db.session.add(product_b)
            db.session.flush()

            wh_b = Warehouse(tenant_id=tid_b.id, name='WHB', code='WHB', branch_id=branch_b.id)
            db.session.add(wh_b)
            db.session.flush()

            from services.stock_service import StockService
            StockService.add_stock(product_b.id, Decimal('100'), reference_type='adjustment', reference_id=1, warehouse_id=wh_b.id)
            db.session.commit()

            with patch('services.sale_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 4.05}
                sale_b = SaleService.create_sale(
                    customer=customer_b,
                    seller=user_b,
                    lines_data=[{'product': product_b, 'quantity': 1, 'unit_price': Decimal('500')}],
                    warehouse_id=wh_b.id,
                    currency='EUR',
                    tax_rate=Decimal('0'),
                )
            db.session.commit()

            ar_a = _bal('1130', tid_a) - ar_before_a
            rev_a = _bal('4100', tid_a) - rev_before_a
            expected_a = (Decimal('1000') * Decimal('3.67')).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            assert ar_a == expected_a, f'Tenant A AR must be {expected_a}'
            assert rev_a == expected_a, f'Tenant A Revenue must be {expected_a}'

            ar_b = _bal('1130', tid_b.id)
            rev_b = _bal('4100', tid_b.id)
            expected_b = (Decimal('500') * Decimal('4.05')).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
            assert ar_b == expected_b, f'Tenant B AR must be {expected_b}'
            assert rev_b == expected_b, f'Tenant B Revenue must be {expected_b}'
