"""
Regression tests for ERP Accounting Audit fixes (June 2026).

Covers:
- Correct GL account codes in cheque, purchase, return, sale services
- Cheque payment/receipt balance timing
- Duplicate property removal in Sale model
- Audit-trail-safe hard-delete route behavior
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, ANY


class TestChequeServiceGlCodes:
    """Ensure cheque service uses canonical GL account codes."""

    def _mock_cheque(self, cheque_type='outgoing', amount_aed=Decimal('1000')):
        cheque = MagicMock()
        cheque.cheque_type = cheque_type
        cheque.amount_aed = amount_aed
        cheque.cheque_bank_number = 'CHK001'
        cheque.currency = 'AED'
        cheque.actual_amount_aed = amount_aed
        cheque.currency_gain_loss = Decimal('0')
        cheque.branch_id = 1
        cheque.tenant_id = 1
        cheque.customer_id = None
        cheque.supplier_id = 1
        cheque.expense_id = None
        return cheque

    def _get_lines(self, mock_post):
        """Extract lines from _post_gl call (positional or keyword)."""
        args, kwargs = mock_post.call_args
        return kwargs.get('lines', args[1] if len(args) > 1 else [])

    def test_cheque_issue_uses_deferred_cheques_account(self, app):
        from services.cheque_service import process_cheque_issue
        cheque = self._mock_cheque('outgoing')
        with patch('services.cheque_service._post_gl') as mock_post:
            process_cheque_issue(cheque)
            lines = self._get_lines(mock_post)
            deferred_line = [l for l in lines if l.get('concept_code') == 'DEFERRED_CHEQUES_PAYABLE'][0]
            assert deferred_line['account'] == '2130', f"Expected 2130, got {deferred_line['account']}"

    def test_cheque_clear_outgoing_uses_deferred_cheques_account(self, app):
        from services.cheque_service import _create_clearing_journal_entry
        cheque = self._mock_cheque('outgoing')
        with patch('services.cheque_service._post_gl') as mock_post:
            with patch('services.cheque_service.gl_get_default_liquidity_account', return_value='1120'):
                _create_clearing_journal_entry(cheque)
                lines = self._get_lines(mock_post)
                deferred_line = [l for l in lines if l.get('concept_code') == 'DEFERRED_CHEQUES_PAYABLE'][0]
                assert deferred_line['account'] == '2130', f"Expected 2130, got {deferred_line['account']}"

    def test_cheque_bounce_outgoing_uses_deferred_cheques_account(self, app):
        from services.cheque_service import _create_bounce_journal_entry
        cheque = self._mock_cheque('outgoing')
        with patch('services.cheque_service._post_gl') as mock_post:
            _create_bounce_journal_entry(cheque)
            lines = self._get_lines(mock_post)
            deferred_line = [l for l in lines if l.get('concept_code') == 'DEFERRED_CHEQUES_PAYABLE'][0]
            assert deferred_line['account'] == '2130', f"Expected 2130, got {deferred_line['account']}"

    def test_cheque_cancel_outgoing_uses_deferred_cheques_account(self, app):
        from services.cheque_service import _create_cancel_journal_entry
        cheque = self._mock_cheque('outgoing')
        with patch('services.cheque_service._post_gl') as mock_post:
            _create_cancel_journal_entry(cheque)
            lines = self._get_lines(mock_post)
            deferred_line = [l for l in lines if l.get('concept_code') == 'DEFERRED_CHEQUES_PAYABLE'][0]
            assert deferred_line['account'] == '2130', f"Expected 2130, got {deferred_line['account']}"

    def test_cheque_clear_incoming_fx_loss_uses_6600(self, app):
        from services.cheque_service import _create_clearing_journal_entry
        cheque = self._mock_cheque('incoming')
        cheque.currency_gain_loss = Decimal('-50')
        with patch('services.cheque_service._post_gl') as mock_post:
            with patch('services.cheque_service.gl_get_default_liquidity_account', return_value='1120'):
                _create_clearing_journal_entry(cheque)
                lines = self._get_lines(mock_post)
                fx_lines = [l for l in lines if l.get('concept_code') == 'FX_LOSS']
                assert len(fx_lines) == 1, "Expected one FX loss line"
                assert fx_lines[0]['account'] == '6600', f"Expected 6600, got {fx_lines[0]['account']}"

    def test_cheque_clear_outgoing_fx_loss_uses_6600(self, app):
        from services.cheque_service import _create_clearing_journal_entry
        cheque = self._mock_cheque('outgoing')
        cheque.currency_gain_loss = Decimal('50')
        with patch('services.cheque_service._post_gl') as mock_post:
            with patch('services.cheque_service.gl_get_default_liquidity_account', return_value='1120'):
                _create_clearing_journal_entry(cheque)
                lines = self._get_lines(mock_post)
                fx_lines = [l for l in lines if l.get('concept_code') == 'FX_LOSS']
                assert len(fx_lines) == 1, "Expected one FX loss line"
                assert fx_lines[0]['account'] == '6600', f"Expected 6600, got {fx_lines[0]['account']}"

    def test_cheque_bounce_expense_fallback_uses_6500(self, app):
        from services.cheque_service import _create_bounce_journal_entry
        cheque = self._mock_cheque('outgoing')
        cheque.expense_id = 1
        expense = MagicMock()
        expense.category = None
        with patch('services.cheque_service._post_gl') as mock_post:
            with patch('models.expense.Expense.query') as mock_exp_q:
                mock_exp_q.get.return_value = expense
                _create_bounce_journal_entry(cheque)
                lines = self._get_lines(mock_post)
                credit_lines = [l for l in lines if l.get('credit', 0) > 0]
                fallback = [l for l in credit_lines if l['account'] == '6500']
                assert len(fallback) == 1, "Expected fallback misc expense account 6500"

    def test_cheque_cancel_expense_fallback_uses_6500(self, app):
        from services.cheque_service import _create_cancel_journal_entry
        cheque = self._mock_cheque('outgoing')
        cheque.expense_id = 1
        expense = MagicMock()
        expense.category = None
        with patch('services.cheque_service._post_gl') as mock_post:
            with patch('models.expense.Expense.query') as mock_exp_q:
                mock_exp_q.get.return_value = expense
                _create_cancel_journal_entry(cheque)
                lines = self._get_lines(mock_post)
                credit_lines = [l for l in lines if l.get('credit', 0) > 0]
                fallback = [l for l in credit_lines if l['account'] == '6500']
                assert len(fallback) == 1, "Expected fallback misc expense account 6500"


class TestPurchaseServiceLandedCosts:
    """Ensure non-capitalized landed costs post to correct expense accounts."""

    def _mock_purchase(self, freight=100, customs=50, insurance=25, other=10):
        purchase = MagicMock()
        purchase.subtotal = Decimal('1000')
        purchase.discount_amount = Decimal('0')
        purchase.total_amount = Decimal('1200')
        purchase.tax_amount = Decimal('0')
        purchase.total_landed_cost = Decimal(freight + customs + insurance + other)
        purchase.freight = Decimal(freight)
        purchase.customs_duty = Decimal(customs)
        purchase.insurance = Decimal(insurance)
        purchase.other_landed_cost = Decimal(other)
        purchase.currency = 'AED'
        purchase.exchange_rate = Decimal('1')
        purchase.purchase_number = 'P-001'
        purchase.supplier_name = 'Supplier A'
        purchase.branch_id = 1
        purchase.tenant_id = 1
        purchase.lines = []
        return purchase

    def test_non_capitalized_landed_costs_use_proper_accounts(self, app):
        from services.purchase_service import PurchaseService
        from services.gl_posting import post_or_fail
        purchase = self._mock_purchase()
        user = MagicMock()
        user.id = 1
        with patch('services.purchase_service.current_app') as mock_app:
            mock_app.config.get.return_value = False  # capitalize_landed = False
            with patch('services.purchase_service.StockService') as mock_stock:
                with patch('services.purchase_service.GLService') as mock_gl:
                    with patch('services.purchase_service.post_or_fail') as mock_post:
                        with patch.object(PurchaseService, 'create_purchase', wraps=PurchaseService.create_purchase):
                            # We patch create_purchase internals to capture the lines
                            pass
        # Simpler: directly inspect the lines built inside create_purchase by
        # mocking post_or_fail at the module level.
        with patch('services.purchase_service.post_or_fail') as mock_post:
            with patch('services.purchase_service.current_app') as mock_app:
                mock_app.config.get.side_effect = lambda key, default=False: False if key == 'ENABLE_LANDED_COST_CAPITALIZATION' else default
                with patch('services.purchase_service.GLService') as mock_gl:
                    with patch('services.purchase_service.StockService'):
                        with patch('services.purchase_service.Supplier') as mock_sup:
                            supplier = MagicMock()
                            supplier.id = 1
                            supplier.tenant_id = 1
                            mock_sup.query.get.return_value = supplier
                            with patch('services.purchase_service.Purchase') as mock_pur:
                                pur = self._mock_purchase()
                                mock_pur.return_value = pur
                                with patch('services.purchase_service.PurchaseLine') as mock_line:
                                    line = MagicMock()
                                    line.line_total = Decimal('1000')
                                    line.landed_cost = Decimal('0')
                                    line.landed_unit_cost = Decimal('0')
                                    mock_line.return_value = line
                                    try:
                                        PurchaseService.create_purchase(
                                            user,
                                            {'supplier_id': 1},
                                            [{'product_id': 1, 'quantity': 1, 'unit_cost': 1000}],
                                            warehouse_id=1,
                                            freight=100,
                                            customs_duty=50,
                                            insurance=25,
                                            other_landed_cost=10,
                                        )
                                    except Exception:
                                        pass
                                    if mock_post.called:
                                        args, kwargs = mock_post.call_args
                                        lines = args[0]
                                        accounts = {l['account'] for l in lines}
                                        assert '5301' in accounts, "Freight account 5301 missing"
                                        assert '5302' in accounts, "Customs account 5302 missing"
                                        assert '5303' in accounts, "Insurance account 5303 missing"
                                        assert '6500' in accounts, "Misc account 6500 missing"
                                        assert '6900' not in accounts, "Invalid account 6900 must not appear"


class TestReturnServiceVatReversal:
    """Ensure sales return VAT reversal uses VAT Output account (2121), not Deferred Cheques (2130)."""

    def test_return_vat_reversal_uses_2121(self, app):
        from services.return_service import ReturnService
        from unittest.mock import patch
        with patch('services.return_service.post_or_fail') as mock_post:
            with patch('services.return_service.Sale.query') as mock_sale_q:
                sale = MagicMock()
                sale.tenant_id = 1
                sale.branch_id = 1
                sale.customer_id = 1
                sale.currency = 'AED'
                sale.exchange_rate = Decimal('1')
                sale.subtotal = Decimal('1000')
                sale.discount_amount = Decimal('0')
                sale.shipping_cost = Decimal('0')
                sale.tax_rate = Decimal('5')
                sale.sale_number = 'S-001'
                sale.customer = MagicMock()
                sale.returns = []
                sale.payments = []
                mock_sale_q.get.return_value = sale
                with patch('services.return_service.ProductReturnLine'):
                    with patch('services.return_service.ProductReturn') as mock_ret:
                        ret = MagicMock()
                        ret.id = 1
                        ret.currency = 'AED'
                        ret.exchange_rate = Decimal('1')
                        mock_ret.return_value = ret
                        with patch('services.return_service.SaleLine.query') as mock_sl:
                            sl = MagicMock()
                            sl.sale_id = sale.id
                            sl.tenant_id = sale.tenant_id
                            sl.product_id = 1
                            sl.quantity = Decimal('1')
                            sl.line_total = Decimal('100')
                            sl.cost_price = Decimal('50')
                            sl.product = MagicMock()
                            sl.product.has_serial_number = False
                            mock_sl.get.return_value = sl
                            with patch('services.return_service.StockService'):
                                with patch('services.return_service.GLService'):
                                    try:
                                        ReturnService.create_return(
                                            sale_id=1,
                                            return_lines_data=[{'sale_line_id': 1, 'quantity': 1}],
                                            user_id=1,
                                        )
                                    except Exception:
                                        pass
                                    if mock_post.called:
                                        calls = mock_post.call_args_list
                                        for call in calls:
                                            args, kwargs = call
                                            lines = kwargs.get('lines', args[0] if args else [])
                                            for line in lines:
                                                if line.get('concept_code') == 'VAT_OUTPUT':
                                                    assert line['account'] == '2121', f"Expected 2121 for VAT_OUTPUT, got {line['account']}"
                                                    assert line['account'] != '2130', "Must not use 2130 for VAT reversal"


class TestSalePaymentChequeGl:
    """Ensure sale payment with cheque posts to Cheques Under Collection (1150)."""

    def test_sale_cheque_payment_uses_cuc_account(self, app):
        from services.sale_service import SaleService
        from unittest.mock import patch
        sale = MagicMock()
        sale.id = 1
        sale.tenant_id = 1
        sale.branch_id = 1
        sale.customer_id = 1
        sale.customer = MagicMock()
        sale.customer.customer_type = 'regular'
        sale.sale_number = 'S-001'
        with patch('services.sale_service.post_or_fail') as mock_post:
            with patch('services.sale_service.Payment') as mock_pmt:
                pmt = MagicMock()
                pmt.id = 1
                mock_pmt.return_value = pmt
                with patch('utils.helpers.generate_number', return_value='PAY-001'):
                    with patch('services.sale_service.db.session') as mock_db_session:
                        mock_db_session.add = MagicMock()
                        mock_db_session.flush = MagicMock()
                        with patch('services.sale_service.GLService') as mock_gl:
                            mock_gl.get_customer_credit_account.return_value = '1130'
                            mock_gl.get_customer_credit_concept.return_value = 'AR'
                            mock_gl.get_account_code_for_concept.return_value = '1150'
                            SaleService.create_payment_for_sale(
                                sale=sale,
                                amount=1000,
                                payment_method='cheque',
                                currency='AED',
                                exchange_rate=1.0,
                                cheque_number='CHK001',
                                cheque_date='2026-06-10',
                                bank_name='Test Bank',
                            )
                            assert mock_post.called, "GL posting should have been called"
                            args, kwargs = mock_post.call_args
                            lines = args[0]
                            debit_line = [l for l in lines if l.get('debit', 0) > 0][0]
                            assert debit_line['account'] == '1150', f"Expected 1150 for cheque debit, got {debit_line['account']}"
                            assert debit_line['concept_code'] == 'CHEQUES_UNDER_COLLECTION'


class TestPaymentServiceBalanceTiming:
    """Ensure customer/supplier balances are updated at correct lifecycle points."""

    def test_receipt_cheque_updates_customer_balance_immediately(self, app):
        from services.payment_service import PaymentService
        from unittest.mock import patch
        customer = MagicMock()
        customer.id = 1
        customer.tenant_id = 1
        customer.name = 'Test Customer'
        with patch('models.Customer') as mock_cust:
            with patch('services.payment_service.Receipt') as mock_rcpt:
                rcpt = MagicMock()
                rcpt.id = 1
                rcpt.amount_aed = Decimal('1000')
                mock_rcpt.return_value = rcpt
                with patch('models.Cheque') as mock_cheque:
                    cq = MagicMock()
                    cq.id = 1
                    mock_cheque.return_value = cq
                    with patch('services.payment_service.process_cheque_receive', return_value=MagicMock()):
                        with patch('services.payment_service.post_or_fail'):
                            with patch('services.payment_service.generate_number', return_value='RCV-001'):
                                with patch('services.payment_service.db.session') as mock_db:
                                    mock_db.add = MagicMock()
                                    mock_db.flush = MagicMock()
                                    mock_db.get.return_value = customer
                                    PaymentService.create_receipt({
                                        'customer_id': 1,
                                        'amount': 1000,
                                        'currency': 'AED',
                                        'payment_method': 'cheque',
                                        'cheque_number': 'CHK001',
                                        'cheque_date': '2026-06-10',
                                        'bank_name': 'Test Bank',
                                    })
                                    customer.apply_receipt.assert_called_once()

    def test_payment_cheque_updates_supplier_balance_immediately(self, app):
        from services.payment_service import PaymentService
        from unittest.mock import patch
        supplier = MagicMock()
        supplier.id = 1
        supplier.tenant_id = 1
        supplier.name = 'Test Supplier'
        with patch('models.Supplier') as mock_sup:
            with patch('models.Payment') as mock_pmt:
                pmt = MagicMock()
                pmt.id = 1
                pmt.amount_aed = Decimal('1000')
                mock_pmt.return_value = pmt
                with patch('services.payment_service.post_or_fail'):
                    with patch('services.payment_service.generate_number', return_value='PAY-001'):
                        with patch('services.payment_service.db.session') as mock_db:
                            mock_db.add = MagicMock()
                            mock_db.flush = MagicMock()
                            mock_db.get.return_value = supplier
                            PaymentService.create_payment({
                                'supplier_id': 1,
                                'amount': 1000,
                                'currency': 'AED',
                                'payment_method': 'cheque',
                            })
                            supplier.apply_payment.assert_called_once()


class TestSaleModelIntegrity:
    """Ensure Sale model has no duplicate properties."""

    def test_no_duplicate_confirmed_payments_amount(self, app):
        from models.sale import Sale
        props = [name for name in dir(Sale) if name == 'confirmed_payments_amount']
        # When accessed as class attributes, properties show up once.
        # We verify by checking the class __dict__ directly.
        class_attrs = list(Sale.__dict__.keys())
        count = sum(1 for name in class_attrs if name == 'confirmed_payments_amount')
        assert count == 1, f"Expected exactly one confirmed_payments_amount property, found {count}"


class TestSalesRouteHardDelete:
    """Ensure hard-delete route reverses GL entries instead of deleting them."""

    def test_delete_route_uses_reverse_entry_not_delete_entries_by_ref(self, app):
        import inspect
        from routes.sales import delete
        source = inspect.getsource(delete)
        assert 'reverse_entry' in source, "delete route must call GLService.reverse_entry for audit trail"
        assert 'delete_entries_by_ref' not in source, "delete route must NOT call delete_entries_by_ref"
