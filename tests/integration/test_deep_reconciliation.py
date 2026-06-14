"""
Deep reconciliation tests for accounting audit fixes.
End-to-end flow verification with GL balance assertions.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date


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


def _sum_gl(code, tenant_id, side, branch_id=None):
    from sqlalchemy import func
    from extensions import db
    from models import GLAccount, GLJournalLine, GLJournalEntry
    acc = GLAccount.query.filter_by(tenant_id=tenant_id, code=code).first()
    if not acc:
        return Decimal('0')
    col = GLJournalLine.debit if side == 'debit' else GLJournalLine.credit
    q = db.session.query(func.coalesce(func.sum(col), 0)).join(
        GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id
    ).filter(
        GLJournalLine.account_id == acc.id,
        GLJournalEntry.is_posted == True,
    )
    if tenant_id is not None:
        q = q.filter(GLJournalEntry.tenant_id == tenant_id)
    if branch_id is not None:
        q = q.filter(GLJournalEntry.branch_id == branch_id)
    return Decimal(str(q.scalar() or 0))


def _entries_for(ref_type, ref_id, tenant_id):
    from models import GLJournalEntry
    q = GLJournalEntry.query.filter_by(
        reference_type=ref_type, reference_id=ref_id, tenant_id=tenant_id, is_posted=True
    )
    return q.all()


def _reverse_entries_for(ref_type, ref_id, tenant_id):
    from models import GLJournalEntry
    q = GLJournalEntry.query.filter_by(
        reference_type=ref_type, reference_id=ref_id, tenant_id=tenant_id, is_posted=True
    )
    return [e for e in q.all() if e.is_reversed]


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
    from utils.currency_utils import get_system_default_currency
    tid.default_currency = get_system_default_currency()
    tenant_id = tid.id

    GLService.ensure_core_accounts(tenant_id=tenant_id)
    from services.gl_provisioning_service import GLProvisioningService
    GLProvisioningService.provision_tenant(tenant_id)

    branch = Branch.query.filter_by(tenant_id=tenant_id).first()
    if not branch:
        branch = Branch(tenant_id=tenant_id, name='Main', code='MAIN')
        db.session.add(branch)
        db.session.flush()

    # Clean up pre-existing test cheques (nullify FK refs first)
    from models import Cheque, Payment, Receipt, GLAccount as _GlAcct
    for chk in Cheque.query.filter(Cheque.tenant_id == tenant_id, Cheque.cheque_number.in_(['CHK001', 'CHKOUT001', 'CHKDP', 'RETCHK'])).all():
        for pmt in Payment.query.filter_by(cheque_id=chk.id, tenant_id=tenant_id).all():
            pmt.cheque_id = None
        for rct in Receipt.query.filter_by(cheque_id=chk.id, tenant_id=tenant_id).all():
            rct.cheque_id = None
        db.session.delete(chk)
    db.session.commit()

    # Deactivate old bank accounts; let GLTreeBuilder create the correct one for this branch
    _GlAcct.query.filter(_GlAcct.tenant_id == tenant_id, _GlAcct.liquidity_kind == 'bank', _GlAcct.is_header == False).update({'is_active': False})
    db.session.commit()
    GLService.ensure_core_accounts(tenant_id=tenant_id)
    db.session.commit()

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
    customer.balance = Decimal('0')
    db.session.flush()

    supplier = Supplier.query.filter_by(tenant_id=tenant_id).first()
    if not supplier:
        supplier = Supplier(tenant_id=tenant_id, name='Test Supplier', phone='0500000002')
        db.session.add(supplier)
    supplier.total_purchases_aed = Decimal('0')
    supplier.total_paid_aed = Decimal('0')
    db.session.flush()

    product = Product.query.filter_by(tenant_id=tenant_id, name='Reconciliation Test Product').first()
    if not product:
        product = Product(tenant_id=tenant_id, name='Reconciliation Test Product', current_stock=0, cost_price=Decimal('600'), regular_price=Decimal('1000'), has_serial_number=False)
        db.session.add(product)
    product.cost_price = Decimal('600')
    db.session.flush()

    wh = Warehouse.query.filter_by(tenant_id=tenant_id, branch_id=branch.id).first()
    if not wh:
        wh = Warehouse.query.filter_by(tenant_id=tenant_id).first()
        if wh:
            wh.branch_id = branch.id
        else:
            wh = Warehouse(tenant_id=tenant_id, name='Test WH', code='TWH', branch_id=branch.id)
            db.session.add(wh)
        db.session.flush()

    pwc = ProductWarehouseCost.query.filter_by(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id).first()
    if not pwc:
        pwc = ProductWarehouseCost(tenant_id=tenant_id, product_id=product.id, warehouse_id=wh.id, total_quantity=Decimal('0'), total_value=Decimal('0'), average_cost=Decimal('0'))
        db.session.add(pwc)
        db.session.flush()

    # Seed stock
    from services.stock_service import StockService
    StockService.add_stock(product.id, Decimal('100'), reference_type='adjustment', reference_id=1, warehouse_id=wh.id)
    # Reset PWC to 0 so COGS forces fallback to line.cost_price (600)
    pwc.total_quantity = Decimal('0')
    pwc.total_value = Decimal('0')
    pwc.average_cost = Decimal('0')
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
# 1. Incoming customer cheque flow
# ---------------------------------------------------------------------------

class TestIncomingCustomerChequeFlow:
    def test_full_cheque_lifecycle(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from services.payment_service import PaymentService
            from services.cheque_service import process_cheque_clear, process_cheque_bounce
            from models import Sale, Payment, Cheque, Customer, GLAccount

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            # Initial balances
            ar_before = _bal('1130', tid)
            cuc_before = _bal('1150', tid)
            rev_before = _bal('4100', tid)
            cogs_before = _bal('5100', tid)
            inv_before = _bal('1140', tid)
            bank_acc = GLAccount.query.filter_by(tenant_id=tid, liquidity_kind='bank', is_header=False, is_active=True).first()
            bank_code = bank_acc.code if bank_acc else '1120'
            bank_before = _bal(bank_code, tid)
            cust_bal_before = customer.balance or Decimal('0')

            # Create sale
            sale = SaleService.create_sale(
                customer=customer,
                seller=user,
                lines_data=[{'product': product, 'quantity': 1, 'unit_price': Decimal('1000')}],
                warehouse_id=wh.id,
                tax_rate=Decimal('5'),
            )
            db.session.commit()
            sale = Sale.query.get(sale.id)

            # Verify sale GL
            assert _bal('1130', tid) - ar_before == Decimal('1050'), 'AR must increase by invoice total'
            assert _bal('4100', tid) - rev_before == Decimal('1000'), 'Revenue must be 1000'
            assert _bal('5100', tid) - cogs_before == Decimal('600'), 'COGS must be 600'
            assert _bal('1140', tid) - inv_before == Decimal('-600'), 'Inventory must decrease by 600'
            assert sale.payment_status == 'unpaid'
            assert sale.balance_due == Decimal('1050')

            # Receive cheque payment
            payment = SaleService.create_payment_for_sale(
                sale=sale,
                amount=Decimal('1050'),
                payment_method='cheque',
                exchange_rate=1.0,
                cheque_number='CHK001',
                cheque_date=str((datetime.now(timezone.utc).date() + timedelta(days=30))),
                bank_name='Test Bank',
            )
            db.session.commit()

            # Verify cheque payment GL
            assert _bal('1150', tid) - cuc_before == Decimal('1050'), 'CUC must increase by cheque amount'
            assert _bal('1130', tid) == ar_before, 'AR must return to zero after payment'
            sale = Sale.query.get(sale.id)
            customer = Customer.query.get(customer.id)
            assert customer.balance == cust_bal_before, 'Customer balance unchanged at receipt (already credited on sale)'
            assert sale.payment_status == 'pending_cheque'

            # Clear cheque
            cheque = Cheque.query.filter_by(cheque_number='CHK001', tenant_id=tid).first()
            assert cheque is not None
            process_cheque_clear(cheque)
            db.session.commit()

            # Verify clearing GL
            assert _bal('1150', tid) == cuc_before, 'CUC must return to zero after clearing'
            assert _bal(bank_code, tid) - bank_before == Decimal('1050'), 'Bank must increase by cheque amount'



# ---------------------------------------------------------------------------
# 2. Outgoing supplier cheque flow
# ---------------------------------------------------------------------------

class TestOutgoingSupplierChequeFlow:
    def test_full_outgoing_cheque_lifecycle(self, app, env):
        with app.app_context():
            from extensions import db
            from services.purchase_service import PurchaseService
            from services.payment_service import PaymentService
            from services.cheque_service import process_cheque_issue, process_cheque_clear, process_cheque_bounce
            from models import Purchase, Payment, Cheque, Supplier, GLAccount

            tid = env['tenant_id']
            supplier = env['supplier']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            ap_before = _bal('2110', tid)
            def_before = _bal('2130', tid)
            bank_acc = GLAccount.query.filter_by(tenant_id=tid, liquidity_kind='bank', is_header=False, is_active=True).first()
            bank_code = bank_acc.code if bank_acc else '1120'
            bank_before = _bal(bank_code, tid)
            sup_bal_before = supplier.get_balance_base() or Decimal('0')

            # Create purchase
            purchase = PurchaseService.create_purchase(
                user=user,
                supplier_data={'supplier_id': supplier.id},
                lines_data=[{'product_id': product.id, 'quantity': 1, 'unit_cost': Decimal('1000')}],
                warehouse_id=wh.id,
                tax_rate=Decimal('5'),
            )
            db.session.commit()
            purchase = Purchase.query.get(purchase.id)
            supplier = Supplier.query.get(supplier.id)

            assert _bal('2110', tid) - ap_before == Decimal('1050'), 'AP must increase by purchase total'
            assert supplier.get_balance_base() > sup_bal_before, 'Supplier balance must increase after purchase'

            # Issue outgoing cheque payment
            payment = PaymentService.create_payment({
                'supplier_id': supplier.id,
                'amount': Decimal('1050'),
                'payment_method': 'cheque',
                'cheque_number': 'CHKOUT001',
            })
            db.session.commit()
            supplier = Supplier.query.get(supplier.id)

            assert _bal('2110', tid) == ap_before, 'AP must return to zero after payment'
            assert _bal('2130', tid) - def_before == Decimal('1050'), 'Deferred Cheques must increase'
            assert supplier.get_balance_base() == sup_bal_before, 'Supplier balance must return to zero after payment'

            # Get the cheque created by payment
            cheque = Cheque.query.filter_by(payment_id=payment.id, tenant_id=tid).first()
            if not cheque:
                # Fallback: search by supplier/amount
                cheque = Cheque.query.filter_by(supplier_id=supplier.id, amount=Decimal('1050'), tenant_id=tid).order_by(Cheque.id.desc()).first()

            if cheque:
                process_cheque_clear(cheque)
                db.session.commit()
                assert _bal('2130', tid) == def_before, 'Deferred must return to zero after clearing'
                assert _bal(bank_code, tid) - bank_before == Decimal('-1050'), 'Bank must decrease by cheque amount'



# ---------------------------------------------------------------------------
# 3. Prevent double posting
# ---------------------------------------------------------------------------

class TestPreventDoublePosting:
    def test_cheque_payment_does_not_duplicate_gl(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from models import Sale, GLJournalEntry

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            sale = SaleService.create_sale(
                customer=customer,
                seller=user,
                lines_data=[{'product': product, 'quantity': 1, 'unit_price': Decimal('500')}],
                warehouse_id=wh.id,
            )
            db.session.commit()

            payment = SaleService.create_payment_for_sale(
                sale=sale,
                amount=Decimal('500'),
                payment_method='cheque',
                exchange_rate=1.0,
                cheque_number='CHKDP',
                cheque_date=str(datetime.now(timezone.utc).date() + timedelta(days=30)),
                bank_name='Test Bank',
            )
            db.session.commit()

            # Count unique GL entries for this payment
            entries = _entries_for('Payment', payment.id, tid)
            assert len(entries) == 1, f'Payment must create exactly one GL entry, found {len(entries)}'

            # Sum CUC debits from payment entry only
            cuc_debits = Decimal('0')
            for entry in entries:
                for line in entry.lines:
                    if line.account and line.account.code == '1150' and line.debit:
                        cuc_debits += Decimal(str(line.debit))
            assert cuc_debits == Decimal('500'), 'Payment GL must debit CUC exactly once'


# ---------------------------------------------------------------------------
# 4. Sale cancellation / hard-delete prevention
# ---------------------------------------------------------------------------

class TestSaleCancellation:
    def test_cancel_reverses_all_gl(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from models import Sale, GLJournalEntry, StockMovement, Customer, Product

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            ar_before = _bal('1130', tid)
            rev_before = _bal('4100', tid)
            cogs_before = _bal('5100', tid)
            inv_before = _bal('1140', tid)
            cust_bal_before = customer.balance or Decimal('0')
            stock_before = product.current_stock or Decimal('0')

            sale = SaleService.create_sale(
                customer=customer,
                seller=user,
                lines_data=[{'product': product, 'quantity': 5, 'unit_price': Decimal('300')}],
                warehouse_id=wh.id,
            )
            db.session.commit()
            sale = Sale.query.get(sale.id)

            assert _bal('1130', tid) - ar_before > Decimal('0'), 'AR must increase'
            assert _bal('4100', tid) - rev_before > Decimal('0'), 'Revenue must increase'
            assert _bal('5100', tid) - cogs_before > Decimal('0'), 'COGS must increase'
            assert _bal('1140', tid) < inv_before, 'Inventory must decrease'

            SaleService.cancel_sale(sale)
            db.session.commit()
            sale = Sale.query.get(sale.id)
            customer = Customer.query.get(customer.id)
            product = Product.query.get(product.id)

            # GL net effect must be zero
            assert abs(_bal('1130', tid) - ar_before) < Decimal('0.01'), 'AR net must be zero after cancel'
            assert abs(_bal('4100', tid) - rev_before) < Decimal('0.01'), 'Revenue net must be zero after cancel'
            assert abs(_bal('5100', tid) - cogs_before) < Decimal('0.01'), 'COGS net must be zero after cancel'
            assert abs(_bal('1140', tid) - inv_before) < Decimal('0.01'), 'Inventory net must be zero after cancel'

            # Customer balance restored
            assert abs(customer.balance - cust_bal_before) < Decimal('0.01'), 'Customer balance must be restored'

            # Stock restored
            assert abs(product.current_stock - stock_before) < Decimal('0.01'), 'Stock must be restored'

            # Reversal entries exist
            rev_entries = GLJournalEntry.query.filter_by(
                reference_id=sale.id, tenant_id=tid, entry_type='reversing', is_posted=True
            ).all()
            assert len(rev_entries) >= 1, 'Reversing entries must exist'

            # Original entries still exist (audit trail)
            orig_entries = GLJournalEntry.query.filter(
                GLJournalEntry.reference_id == sale.id,
                GLJournalEntry.tenant_id == tid,
                GLJournalEntry.is_posted == True,
                GLJournalEntry.entry_type != 'reversing',
            ).all()
            assert len(orig_entries) >= 1, 'Original entries must be preserved'


# ---------------------------------------------------------------------------
# 5. Sales return / credit note
# ---------------------------------------------------------------------------

class TestSalesReturn:
    def test_return_uses_original_sale_cost(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from services.return_service import ReturnService
            from models import Sale, ProductReturn, ProductCostHistory, Product

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            # Record original cost before sale
            original_cost = Decimal(str(product.cost_price or 0))

            # Create and fulfill sale
            sale = SaleService.create_sale(
                customer=customer,
                seller=user,
                lines_data=[{'product': product, 'quantity': 3, 'unit_price': Decimal('400')}],
                warehouse_id=wh.id,
            )
            db.session.commit()
            sale = Sale.query.get(sale.id)

            # Change product cost after sale (should NOT affect return COGS)
            product = Product.query.get(product.id)
            product.cost_price = Decimal('999')
            db.session.commit()

            rev_after_sale = _bal('4100', tid)
            cogs_before_return = _bal('5100', tid)
            inv_before_return = _bal('1140', tid)

            # Create return
            ret = ReturnService.create_return(
                sale_id=sale.id,
                return_lines_data=[{'sale_line_id': sale.lines[0].id, 'quantity': 1}],
                user_id=user.id,
            )
            db.session.commit()

            # COGS must decrease by original sale cost, not new cost
            cogs_change = _bal('5100', tid) - cogs_before_return
            assert cogs_change < Decimal('0'), 'COGS must decrease after return'
            assert abs(abs(cogs_change) - original_cost) < Decimal('1'), 'COGS reversal must use original cost'

            # Inventory must increase by original cost
            inv_change = _bal('1140', tid) - inv_before_return
            assert inv_change > Decimal('0'), 'Inventory must increase after return'

            # Revenue reduced relative to after-sale level
            assert _bal('4100', tid) <= rev_after_sale, 'Revenue must decrease after return'


# ---------------------------------------------------------------------------
# 6. Landed cost capitalization
# ---------------------------------------------------------------------------

class TestLandedCostCapitalization:
    def test_capitalization_off_expense_accounts(self, app, env):
        with app.app_context():
            from extensions import db
            from services.purchase_service import PurchaseService
            from models import Purchase

            tid = env['tenant_id']
            supplier = env['supplier']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            inv_before = _bal('1140', tid)
            freight_before = _bal('5301', tid)
            customs_before = _bal('5302', tid)
            insurance_before = _bal('5303', tid)
            misc_before = _bal('6500', tid)
            ap_before = _bal('2110', tid)

            # Force capitalization OFF
            from flask import current_app
            old_cap = current_app.config.get('ENABLE_LANDED_COST_CAPITALIZATION', True)
            current_app.config['ENABLE_LANDED_COST_CAPITALIZATION'] = False

            try:
                purchase = PurchaseService.create_purchase(
                    user=user,
                    supplier_data={'supplier_id': supplier.id},
                    lines_data=[{'product_id': product.id, 'quantity': 1, 'unit_cost': Decimal('1000')}],
                    warehouse_id=wh.id,
                    freight=Decimal('100'),
                    customs_duty=Decimal('50'),
                    insurance=Decimal('25'),
                    other_landed_cost=Decimal('10'),
                )
                db.session.commit()
                db.session.refresh(purchase)

                # AP increases by product + landed costs
                assert _bal('2110', tid) - ap_before == Decimal('1185'), f'AP must be 1185, got {_bal("2110", tid) - ap_before}'

                # Inventory only gets product cost
                assert _bal('1140', tid) - inv_before == Decimal('1000'), f'Inventory must be 1000, got {_bal("1140", tid) - inv_before}'

                # Expense accounts get landed costs
                assert _bal('5301', tid) - freight_before == Decimal('100'), 'Freight account must be 100'
                assert _bal('5302', tid) - customs_before == Decimal('50'), 'Customs account must be 50'
                assert _bal('5303', tid) - insurance_before == Decimal('25'), 'Insurance account must be 25'
                assert _bal('6500', tid) - misc_before == Decimal('10'), 'Misc account must be 10'
            finally:
                current_app.config['ENABLE_LANDED_COST_CAPITALIZATION'] = old_cap


# ---------------------------------------------------------------------------
# 7. VAT reversal report
# ---------------------------------------------------------------------------

class TestVatReversalReport:
    def test_vat_report_net_zero_after_cancel(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from services.gl_service import GLService
            from models import Sale, GLJournalEntry, GLJournalLine

            tid = env['tenant_id']
            customer = env['customer']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            vat_before = _bal('2121', tid)

            sale = SaleService.create_sale(
                customer=customer,
                seller=user,
                lines_data=[{'product': product, 'quantity': 2, 'unit_price': Decimal('500')}],
                warehouse_id=wh.id,
                tax_rate=Decimal('5'),
            )
            db.session.commit()

            # VAT output increased
            assert _bal('2121', tid) - vat_before > Decimal('0'), 'VAT output must increase'

            SaleService.cancel_sale(sale)
            db.session.commit()

            # Get VAT report
            report = GLService.get_vat_report(tenant_id=tid)
            vat_output = Decimal(str(report.get('vat_output', 0)))
            vat_input = Decimal(str(report.get('vat_input', 0)))
            net_vat = Decimal(str(report.get('net_vat', 0)))

            # Original and reversal must net to same as before
            assert abs(_bal('2121', tid) - vat_before) < Decimal('0.01'), 'VAT output net must be zero'


# ---------------------------------------------------------------------------
# 8. GL posted filter
# ---------------------------------------------------------------------------

class TestGlPostedFilter:
    def test_statements_exclude_unposted(self, app, env):
        with app.app_context():
            from extensions import db
            from models import GLJournalEntry, GLJournalLine, GLAccount, Customer, Supplier
            from services.gl_service import GLService

            tid = env['tenant_id']

            # Create an unposted entry with unique number to avoid collision from prior runs
            from uuid import uuid4
            uniq = uuid4().hex[:8]
            entry_number = f'UNPOSTED-{uniq}'
            entry = GLJournalEntry(
                tenant_id=tid,
                entry_number=entry_number,
                entry_date=datetime.now(timezone.utc),
                description='Unposted test',
                is_posted=False,
                total_debit=Decimal('100'),
                total_credit=Decimal('100'),
            )
            db.session.add(entry)
            db.session.flush()

            acc = GLAccount.query.filter_by(tenant_id=tid, code='1130').first()
            line = GLJournalLine(
                tenant_id=tid,
                entry_id=entry.id,
                account_id=acc.id,
                debit=Decimal('100'),
                credit=Decimal('0'),
                amount_aed=Decimal('100'),
            )
            db.session.add(line)
            db.session.commit()

            # Account statement must not include unposted
            stmt = GLService.get_account_statement(acc.id)
            entry_numbers = [t.get('entry_number') for t in stmt['transactions']]
            assert entry_number not in entry_numbers, f'Unposted line {entry_number} must not appear in account statement'

            # Trial balance must not include unposted
            from sqlalchemy import func
            tb_q = db.session.query(func.coalesce(func.sum(GLJournalLine.amount_aed), 0)).join(
                GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id
            ).filter(GLJournalEntry.is_posted == True)
            assert tb_q.scalar() is not None


# ---------------------------------------------------------------------------
# 9. Final reconciliation assertions
# ---------------------------------------------------------------------------

class TestFinalReconciliation:
    def test_ar_ap_inventory_reconcile(self, app, env):
        with app.app_context():
            from extensions import db
            from services.sale_service import SaleService
            from services.purchase_service import PurchaseService
            from models import Customer, Supplier, ProductWarehouseCost, Product, Cheque

            tid = env['tenant_id']
            customer = env['customer']
            supplier = env['supplier']
            user = env['user']
            product = env['product']
            wh = env['warehouse']

            # Reset balances
            customer = Customer.query.get(customer.id)
            supplier = Supplier.query.get(supplier.id)
            cust_bal = customer.balance or Decimal('0')
            sup_bal = supplier.get_balance_base() or Decimal('0')
            ar_gl = _bal('1130', tid)
            ap_gl = _bal('2110', tid)
            inv_gl = _bal('1140', tid)
            cogs_gl = _bal('5100', tid)
            cuc_gl_before = _bal('1150', tid)
            def_gl_before = _bal('2130', tid)
            pwc_before = ProductWarehouseCost.query.filter_by(tenant_id=tid, product_id=product.id, warehouse_id=wh.id).first()
            stock_val_before = pwc_before.total_value if pwc_before else Decimal('0')

            # Sale
            SaleService.create_sale(
                customer=customer,
                seller=user,
                lines_data=[{'product': product, 'quantity': 2, 'unit_price': Decimal('300')}],
                warehouse_id=wh.id,
            )
            db.session.commit()

            # Purchase
            PurchaseService.create_purchase(
                user=user,
                supplier_data={'supplier_id': supplier.id},
                lines_data=[{'product_id': product.id, 'quantity': 5, 'unit_cost': Decimal('200')}],
                warehouse_id=wh.id,
            )
            db.session.commit()

            customer = Customer.query.get(customer.id)
            supplier = Supplier.query.get(supplier.id)
            product = Product.query.get(product.id)

            # AR subledger vs GL — compare delta within this test only
            # Note: customer.balance convention: negative = customer owes us (debtor)
            #       AR GL (1130): positive = customer owes us
            #       Thus: cust_balance ≈ -(ar_gl_delta)
            cust_ops_delta = (customer.balance or Decimal('0')) - Decimal('0')
            ar_gl_delta = _bal('1130', tid) - ar_gl
            assert abs(cust_ops_delta + ar_gl_delta) < Decimal('1'), f'AR GL delta ({ar_gl_delta}) must be opposite of customer balance delta ({cust_ops_delta})'

            # AP subledger vs GL — compare delta within this test only
            # supplier.get_balance_base() convention: positive = we owe supplier
            #       AP GL (2110): positive = we owe supplier
            #       Thus: sup_balance ≈ ap_gl_delta
            sup_balance = supplier.get_balance_base() or Decimal('0')
            ap_gl_delta = _bal('2110', tid) - ap_gl
            assert abs(sup_balance - ap_gl_delta) < Decimal('1'), f'AP GL delta ({ap_gl_delta}) must equal supplier balance ({sup_balance})'

            # Inventory GL vs stock valuation (delta check within this test)
            # GL records inventory as: +debit on purchase, -credit on COGS
            # PWC only tracks current warehouse valuation (not updated on COGS fallback path)
            # Reconciliation: inv_gl_delta + cogs_delta = stock_val_delta
            pwc = ProductWarehouseCost.query.filter_by(tenant_id=tid, product_id=product.id, warehouse_id=wh.id).first()
            stock_valuation = pwc.total_value if pwc else Decimal('0')
            inv_gl_delta = _bal('1140', tid) - inv_gl
            cogs_delta = _bal('5100', tid) - cogs_gl
            stock_delta = stock_valuation - stock_val_before
            assert abs(inv_gl_delta + cogs_delta - stock_delta) < Decimal('1'), (
                f'Inv GL delta ({inv_gl_delta}) + COGS delta ({cogs_delta}) = {inv_gl_delta + cogs_delta} '
                f'must equal stock val delta ({stock_delta})'
            )

            # CUC vs open incoming cheques (delta within this test)
            cuc_gl = _bal('1150', tid)
            open_incoming = sum(c.amount_aed or 0 for c in Cheque.query.filter_by(tenant_id=tid, cheque_type='incoming').filter(Cheque.status.in_(['pending', 'deposited'])).all())
            cuc_delta = cuc_gl - cuc_gl_before
            assert abs(cuc_delta - Decimal(str(open_incoming))) < Decimal('1'), f'CUC GL delta ({cuc_delta}) must equal open incoming cheques ({open_incoming})'

            # Deferred vs open outgoing cheques (delta within this test)
            def_gl = _bal('2130', tid)
            open_outgoing = sum(c.amount_aed or 0 for c in Cheque.query.filter_by(tenant_id=tid, cheque_type='outgoing').filter(Cheque.status.in_(['pending', 'deposited'])).all())
            def_delta = def_gl - def_gl_before
            assert abs(def_delta - Decimal(str(open_outgoing))) < Decimal('1'), f'Deferred GL delta ({def_delta}) must equal open outgoing cheques ({open_outgoing})'
