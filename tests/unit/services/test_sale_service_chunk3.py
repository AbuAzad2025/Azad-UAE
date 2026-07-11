from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


def _logger():
    lg = MagicMock()
    lg.__name__ = 'logger'
    for m in ('debug', 'info', 'warning', 'error', 'exception', 'critical'):
        setattr(lg, m, MagicMock(__name__=m))
    return lg


def _actors(**product_kw):
    customer = MagicMock(is_active=True, id=1, customer_type='regular', tenant_id=1)
    seller = MagicMock(is_active=True, id=2, tenant_id=1, branch_id=1)
    product = MagicMock(
        id=1,
        name='Widget',
        cost_price=Decimal('50'),
        has_serial_number=False,
        warranty_days=0,
        partner_shares=[],
    )
    product.get_price_for_customer.return_value = Decimal('100')
    product.__dict__.update(product_kw)
    return customer, seller, product


@contextmanager
def _create_ctx(customer, seller, product, line_extra=None, **create_kw):
    line = {'product': product, 'quantity': 1, 'unit_price': 100}
    if line_extra:
        line.update(line_extra)
    allow_serial = create_kw.pop('allow_serial_on_sale', False)
    wh = MagicMock(id=1, branch_id=1)
    line_inst = MagicMock(
        line_total=Decimal('100'),
        quantity=1,
        cost_price=Decimal('50'),
        id=1,
        product_id=product.id,
    )
    line_inst.calculate_line_total = MagicMock()
    patches = [
        patch('services.sale_service.StockService'),
        patch('models.Warehouse'),
        patch('services.sale_service.ensure_warehouse_access', return_value=wh),
        patch('services.sale_service.generate_number', return_value='S-CH3'),
        patch('services.sale_service.ExchangeRateService'),
        patch('services.sale_service.db.session'),
        patch('services.sale_service.SaleLine', return_value=line_inst),
        patch('services.sale_service.SaleService.fulfill_sale'),
        patch('services.sale_service.current_app'),
        patch('services.sale_service.get_active_tenant_id', return_value=1),
        patch('services.sale_service.normalize_tax_rate', return_value=Decimal('0')),
        patch('utils.tax_settings.get_prices_include_vat', return_value=False),
    ]
    started = [p.start() for p in patches]
    stock = started[0]
    wh_mod = started[1]
    ex = started[4]
    db_sess = started[5]
    capp = started[8]
    stock.check_availability_in_warehouse.return_value = (True, '')
    stock._resolve_cogs_unit_cost.return_value = (Decimal('40'), 'mwac')
    wh_mod.query.filter_by.return_value = wh_mod.query
    wh_mod.query.first.return_value = wh
    ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
    capp.config = {'ALLOW_SERIAL_CREATION_ON_SALE': allow_serial}
    for name in ('debug', 'info', 'warning', 'error', 'exception', 'critical'):
        setattr(capp.logger, name, MagicMock(__name__=name))
    try:
        from services.sale_service import SaleService
        yield SaleService, stock, db_sess, line_inst
        if not create_kw.get('defer_fulfillment') and 'expect_error' not in create_kw:
            kw = {k: v for k, v in create_kw.items() if k != 'expect_error'}
            kw.setdefault('currency', 'AED')
            SaleService.create_sale(customer, seller, [line], **kw)
    finally:
        for p in reversed(patches):
            p.stop()


class TestCreateSaleSerialBranches:
    def test_serial_status_not_available(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors(has_serial_number=True)
        existing = MagicMock(status='sold', warehouse_id=1)
        with _create_ctx(customer, seller, product, {'serials': ['SN1']}, expect_error=True) as (svc, _, _, _):
            with patch('models.ProductSerial') as sn_mod:
                sn_mod.query.filter_by.return_value.first.return_value = existing
                with pytest.raises(ValueError, match='غير متاح للبيع'):
                    svc.create_sale(
                        customer, seller,
                        [{'product': product, 'quantity': 1, 'unit_price': 100, 'serials': ['SN1']}],
                        currency='AED',
                    )

    def test_serial_wrong_warehouse(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors(has_serial_number=True)
        existing = MagicMock(status='available', warehouse_id=99)
        with _create_ctx(customer, seller, product, {'serials': ['SN1']}, expect_error=True) as (svc, _, _, _):
            with patch('models.ProductSerial') as sn_mod:
                sn_mod.query.filter_by.return_value.first.return_value = existing
                with pytest.raises(ValueError, match='مستودع مختلف'):
                    svc.create_sale(
                        customer, seller,
                        [{'product': product, 'quantity': 1, 'unit_price': 100, 'serials': ['SN1']}],
                        currency='AED',
                    )

    def test_serial_missing_disallowed(self, app):
        customer, seller, product = _actors(has_serial_number=True)
        with _create_ctx(customer, seller, product, {'serials': ['SN-NEW']}, expect_error=True) as (svc, _, _, _):
            with patch('models.ProductSerial') as sn_mod:
                sn_mod.query.filter_by.return_value.first.return_value = None
                with pytest.raises(ValueError, match='غير موجود في النظام'):
                    svc.create_sale(
                        customer, seller,
                        [{'product': product, 'quantity': 1, 'unit_price': 100, 'serials': ['SN-NEW']}],
                        currency='AED',
                    )

    def test_serial_create_on_sale_allowed(self, app):
        customer, seller, product = _actors(has_serial_number=True, warranty_days=365)
        created = MagicMock(status='available', warehouse_id=1)
        with _create_ctx(
            customer, seller, product, {'serials': ['SN-NEW']}, allow_serial_on_sale=True, expect_error=True,
        ) as (svc, _, db_sess, _):
            with patch('models.ProductSerial') as sn_mod:
                sn_mod.query.filter_by.return_value.first.side_effect = [None, created]
                sn_mod.return_value = created
                svc.create_sale(
                    customer, seller,
                    [{'product': product, 'quantity': 1, 'unit_price': 100, 'serials': ['SN-NEW']}],
                    currency='AED',
                )
        sn_mod.assert_called_once()
        assert created.status == 'sold'
        assert created.sale_line_id is not None
        assert created.warranty_start_date is not None
        assert created.warranty_end_date is not None
        db_sess.flush.assert_called()


class TestCreateSaleCommissionAndOptions:
    def test_partner_commission_vat_inclusive(self, app):
        customer, seller, product = _actors(
            has_serial_number=False,
            partner_shares=[MagicMock(partner_customer_id=10, percentage=Decimal('10'))],
        )
        partner = MagicMock(customer_type='partner')
        with _create_ctx(customer, seller, product) as (svc, stock, db_sess, _):
            stock._resolve_cogs_unit_cost.return_value = (Decimal('30'), 'mwac')
            with patch('models.Customer') as cust_mod, \
                 patch('utils.tax_settings.get_prices_include_vat', return_value=True):
                cust_mod.query.filter_by.return_value.first.return_value = partner
                sale = svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    tax_rate=5,
                    currency='AED',
                )
        assert sale is not None
        assert db_sess.add.called

    def test_cogs_resolve_exception_uses_line_cost(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors()
        with _create_ctx(customer, seller, product) as (svc, stock, _, _):
            stock._resolve_cogs_unit_cost.side_effect = RuntimeError('no cost')
            sale = svc.create_sale(
                customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                currency='AED',
            )
        assert sale is not None

    def test_defer_fulfillment_commit_failure(self, app):
        customer, seller, product = _actors()
        with _create_ctx(customer, seller, product, defer_fulfillment=True) as (svc, _, db_sess, _):
            db_sess.flush.side_effect = RuntimeError('defer commit fail')
            with pytest.raises(RuntimeError, match='defer commit fail'):
                svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    defer_fulfillment=True,
                    currency='AED',
                )

    def test_create_sale_final_flush_failure(self, app):
        # Under the Single-Commit-Boundary pattern, create_sale flushes and the
        # route owns the commit; a failure during the final flush must propagate.
        customer, seller, product = _actors()
        with _create_ctx(customer, seller, product, expect_error=True) as (svc, _, db_sess, _):
            db_sess.flush.side_effect = RuntimeError('final flush fail')
            with pytest.raises(RuntimeError, match='final flush fail'):
                svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    currency='AED',
                )

    def test_partner_commission_skipped_paths(self, app):
        share_missing = MagicMock(partner_customer_id=None, percentage=Decimal('10'))
        share_zero_pct = MagicMock(partner_customer_id=10, percentage=Decimal('0'))
        share_bad_partner = MagicMock(partner_customer_id=11, percentage=Decimal('10'))
        customer, seller, product = _actors(
            partner_shares=[share_missing, share_zero_pct, share_bad_partner],
        )
        with _create_ctx(customer, seller, product) as (svc, stock, db_sess, _):
            stock._resolve_cogs_unit_cost.return_value = (Decimal('30'), 'mwac')
            with patch('models.Customer') as cust_mod:
                cust_mod.query.filter_by.return_value.first.return_value = None
                svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    currency='AED',
                )
        assert db_sess.add.called

    def test_currency_fallback_on_tenant_error(self, app):
        customer, seller, product = _actors()
        with _create_ctx(customer, seller, product, expect_error=True) as (svc, _, _, _):
            with patch('models.Tenant.get_current', side_effect=Exception('no tenant')), \
                 patch('services.sale_service.resolve_default_currency', side_effect=Exception('fallback')):
                svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                )

    def test_defer_fulfillment_commits_without_fulfill(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors()
        with _create_ctx(customer, seller, product, defer_fulfillment=True) as (svc, _, db_sess, _):
            with patch.object(SaleService, 'fulfill_sale') as fulfill:
                sale = svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    defer_fulfillment=True,
                    currency='AED',
                )
                fulfill.assert_not_called()
                db_sess.flush.assert_called()
        assert sale is not None

    def test_sale_status_and_checkout_method(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors()
        with _create_ctx(customer, seller, product) as (svc, _, _, _):
            sale = svc.create_sale(
                customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                sale_status='confirmed',
                checkout_payment_method='CARD',
                currency='AED',
            )
        assert sale.status == 'confirmed'

    def test_overpayment_note_on_create(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors()
        payment_data = {'amount': 200, 'currency': 'AED', 'exchange_rate': 1.0}
        with _create_ctx(customer, seller, product, payment_data=payment_data) as (svc, _, _, _):
            with patch.object(SaleService, 'fulfill_sale'):
                sale = MagicMock()
                sale.sale_number = 'S-CH3'
                sale.amount_aed = Decimal('100')
                sale.notes = ''
                sale.paid_amount = Decimal('0')
                sale.paid_amount_aed = Decimal('0')
                sale.prices_include_vat = False
                sale.tax_rate = Decimal('0')
                sale.calculate_totals = MagicMock()
                with patch('services.sale_service.Sale', return_value=sale):
                    svc.create_sale(
                        customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                        payment_data=payment_data,
                        currency='AED',
                    )
        assert 'دفع زائد' in (sale.notes or '')

    def test_explicit_warehouse_id(self, app):
        from services.sale_service import SaleService
        customer, seller, product = _actors()
        wh = MagicMock(id=5, branch_id=2)
        with patch('services.sale_service.StockService') as stock, \
             patch('services.sale_service.ensure_warehouse_access', return_value=wh) as ensure, \
             patch('services.sale_service.generate_number', return_value='S-WH'), \
             patch('services.sale_service.ExchangeRateService') as ex, \
             patch('services.sale_service.db.session'), \
             patch('services.sale_service.SaleLine') as sl, \
             patch('services.sale_service.SaleService.fulfill_sale'):
            stock.check_availability_in_warehouse.return_value = (True, '')
            stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'x')
            ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
            li = MagicMock(line_total=Decimal('100'), quantity=1, cost_price=Decimal('50'), id=1, product_id=1)
            li.calculate_line_total = MagicMock()
            sl.return_value = li
            SaleService.create_sale(
                customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                warehouse_id=5,
                currency='AED',
            )
            ensure.assert_called_once_with(5, user=seller)


class TestFulfillSaleGlBranches:
    def _fulfill(self, sale, **patches):
        from services.sale_service import SaleService
        defaults = {
            'has_inv': False,
            'cogs': Decimal('50'),
            'vat_gl': False,
        }
        defaults.update(patches)
        with patch.object(SaleService, 'has_inventory_posted', return_value=defaults['has_inv']), \
             patch('services.sale_service.StockService') as stock, \
             patch('services.sale_service.GLService') as gl, \
             patch('services.sale_service.post_or_fail') as post, \
             patch('services.sale_service.post_sale_commissions'), \
             patch('services.sale_service.should_post_vat_gl', return_value=defaults['vat_gl']):
            stock.check_availability_in_warehouse.return_value = (True, '')
            stock.calculate_sale_cogs_and_deduct.return_value = defaults['cogs']
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            gl.get_account_code_for_concept.return_value = '4000'
            SaleService.fulfill_sale(sale)
            return post

    def test_fulfill_shipping_and_discount_lines(self, app):
        sale = MagicMock(
            customer=MagicMock(apply_sale=MagicMock(), total_purchases=Decimal('0'), update_classification=MagicMock()),
            warehouse_id=1, tenant_id=1, branch_id=1, exchange_rate=Decimal('1'),
            prices_include_vat=False, tax_rate=Decimal('5'), tax_amount=Decimal('0'),
            subtotal=Decimal('100'), discount_amount=Decimal('10'), shipping_cost=Decimal('5'),
            taxable_amount=Decimal('95'), total_amount=Decimal('100'), amount_aed=Decimal('100'),
            sale_number='S-1', lines=[MagicMock(product_id=1, quantity=1)],
        )
        sale.calculate_totals = MagicMock()
        post = self._fulfill(sale)
        assert post.called

    def test_fulfill_vat_inclusive_zero_tax_rate(self, app):
        sale = MagicMock(
            customer=MagicMock(apply_sale=MagicMock(), total_purchases=Decimal('0'), update_classification=MagicMock()),
            warehouse_id=1, tenant_id=1, branch_id=1, exchange_rate=Decimal('1'),
            prices_include_vat=True, tax_rate=Decimal('0'), tax_amount=Decimal('0'),
            subtotal=Decimal('100'), discount_amount=Decimal('0'), shipping_cost=Decimal('0'),
            taxable_amount=Decimal('100'), total_amount=Decimal('100'), amount_aed=Decimal('100'),
            sale_number='S-2', lines=[MagicMock(product_id=1, quantity=1)],
        )
        sale.calculate_totals = MagicMock()
        post = self._fulfill(sale)
        assert post.called

    def test_fulfill_posts_vat_when_enabled(self, app):
        sale = MagicMock(
            customer=MagicMock(apply_sale=MagicMock(), total_purchases=Decimal('0'), update_classification=MagicMock()),
            warehouse_id=1, tenant_id=1, branch_id=1, exchange_rate=Decimal('1'),
            prices_include_vat=False, tax_rate=Decimal('5'), tax_amount=Decimal('5'),
            subtotal=Decimal('100'), discount_amount=Decimal('0'), shipping_cost=Decimal('0'),
            taxable_amount=Decimal('100'), total_amount=Decimal('105'), amount_aed=Decimal('105'),
            sale_number='S-3', lines=[MagicMock(product_id=1, quantity=1)],
        )
        sale.calculate_totals = MagicMock()
        post = self._fulfill(sale, vat_gl=True)
        assert post.called


class TestCreatePaymentFxAndGl:
    def test_payment_gl_failure_raises(self, app):
        from services.sale_service import SaleService
        sale = MagicMock(
            branch_id=1, tenant_id=1, customer_id=1, seller_id=1, sale_number='S-1',
            customer=MagicMock(), exchange_rate=Decimal('1'), currency='AED',
        )
        with patch('services.sale_service.generate_number', return_value='PAY-X'), \
             patch('services.sale_service.GLService') as gl, \
             patch('services.sale_service.post_or_fail', side_effect=RuntimeError('gl fail')), \
             patch('services.sale_service.db.session'), \
             patch('services.sale_service.current_app') as capp:
            gl.get_payment_debit_account.return_value = '1100'
            gl.get_payment_debit_concept.return_value = 'CASH'
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            capp.logger = _logger()
            with pytest.raises(RuntimeError, match='gl fail'):
                SaleService.create_payment_for_sale(sale, 100, 'cash', currency='AED', exchange_rate=1.0)

    def test_fx_loss_branch(self, app):
        from services.sale_service import SaleService
        sale = MagicMock(
            branch_id=1, tenant_id=1, customer_id=1, seller_id=1, sale_number='S-1',
            customer=MagicMock(apply_receipt=MagicMock()),
            exchange_rate=Decimal('3.8'), currency='USD',
        )
        sale.recalculate_payment_status = MagicMock()
        payment = MagicMock(payment_number='PAY-FX', id=9)
        with patch('services.sale_service.generate_number', return_value='PAY-FX'), \
             patch('services.sale_service.GLService') as gl, \
             patch('services.sale_service.post_or_fail') as post, \
             patch('services.sale_service.db.session') as db_sess, \
             patch('services.sale_service.Payment', return_value=payment):
            gl.get_payment_debit_account.return_value = '1100'
            gl.get_payment_debit_concept.return_value = 'CASH'
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            gl.get_account_code_for_concept.return_value = '4900'
            db_sess.flush = MagicMock()
            SaleService.create_payment_for_sale(sale, 100, 'cash', currency='USD', exchange_rate=3.5)
        assert post.call_count >= 2

    def test_fx_skip_on_second_post_error(self, app):
        from services.sale_service import SaleService
        sale = MagicMock(
            branch_id=1, tenant_id=1, customer_id=1, seller_id=1, sale_number='S-1',
            customer=MagicMock(apply_receipt=MagicMock()),
            exchange_rate=Decimal('3.8'), currency='USD',
        )
        sale.recalculate_payment_status = MagicMock()
        payment = MagicMock(payment_number='PAY-SKIP', id=10)
        with patch('services.sale_service.generate_number', return_value='PAY-SKIP'), \
             patch('services.sale_service.GLService') as gl, \
             patch('services.sale_service.post_or_fail', side_effect=[None, RuntimeError('fx')]) as post, \
             patch('services.sale_service.db.session') as db_sess, \
             patch('services.sale_service.Payment', return_value=payment), \
             patch('services.sale_service.current_app') as capp:
            gl.get_payment_debit_account.return_value = '1100'
            gl.get_payment_debit_concept.return_value = 'CASH'
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            gl.get_account_code_for_concept.return_value = '4900'
            db_sess.flush = MagicMock()
            capp.logger = _logger()
            result = SaleService.create_payment_for_sale(sale, 100, 'cash', currency='USD', exchange_rate=3.5)
        assert result is payment
        assert post.call_count >= 2


class TestCancelSale:
    def _sale(self):
        sale = MagicMock(
            id=1, sale_number='S-C', status='confirmed', tenant_id=1, branch_id=1,
            amount_aed=Decimal('100'),
        )
        sale.customer = MagicMock(total_purchases=Decimal('100'))
        sale.customer.adjust_balance = MagicMock()
        sale.customer.update_classification = MagicMock()
        sale.recalculate_payment_status = MagicMock()
        return sale

    def test_cancel_already_cancelled(self, app):
        from services.sale_service import SaleService
        sale = self._sale()
        sale.status = 'cancelled'
        with pytest.raises(ValueError, match='ملغاة بالفعل'):
            SaleService.cancel_sale(sale)

    def test_cancel_blocked_by_confirmed_payments(self, app):
        from services.sale_service import SaleService
        with patch('models.Payment') as pay_mod:
            pay_mod.query.filter_by.return_value.count.return_value = 1
            with pytest.raises(ValueError, match='دفعات مؤكدة'):
                SaleService.cancel_sale(self._sale())

    def test_cancel_pending_cheque_payment(self, app):
        from services.sale_service import SaleService
        sale = self._sale()
        pmt = MagicMock(cheque_id=7)
        cheque = MagicMock(status='pending')
        with patch('models.Payment') as pay_mod, \
             patch('services.sale_service.db') as db_mod, \
             patch.object(SaleService, 'has_inventory_posted', return_value=False), \
             patch('services.cheque_service.process_cheque_cancel') as cancel_chq, \
             patch('services.sale_service.db.session') as sess:
            pay_mod.query.filter_by.return_value.count.return_value = 0
            pay_mod.query.filter_by.return_value.all.return_value = [pmt]
            db_mod.session.get.return_value = cheque
            sess.commit = MagicMock()
            SaleService.cancel_sale(sale)
            cancel_chq.assert_called_once()
            pmt.reject_payment.assert_called_once()

    def test_cancel_with_inventory_and_gl(self, app):
        from services.sale_service import SaleService
        sale = self._sale()
        with patch('models.Payment') as pay_mod, \
             patch.object(SaleService, 'has_inventory_posted', return_value=True), \
             patch('services.sale_service.StockService') as stock, \
             patch('services.sale_service.GLService') as gl, \
             patch('services.sale_service.db.session') as sess:
            pay_mod.query.filter_by.return_value.count.return_value = 0
            pay_mod.query.filter_by.return_value.all.return_value = []
            sess.commit = MagicMock()
            SaleService.cancel_sale(sale)
            stock.reverse_sale.assert_called_once_with(sale)
            assert gl.reverse_entry.call_count == 2
            assert sale.status == 'cancelled'

    def test_cancel_gl_reversal_failure(self, app):
        from services.sale_service import SaleService
        sale = self._sale()
        with patch('models.Payment') as pay_mod, \
             patch.object(SaleService, 'has_inventory_posted', return_value=True), \
             patch('services.sale_service.StockService'), \
             patch('services.sale_service.GLService') as gl, \
             patch('services.sale_service.db.session') as sess, \
             patch('services.sale_service.current_app') as capp:
            pay_mod.query.filter_by.return_value.count.return_value = 0
            pay_mod.query.filter_by.return_value.all.return_value = []
            gl.reverse_entry.side_effect = RuntimeError('gl reverse')
            sess.rollback = MagicMock()
            capp.logger = _logger()
            with pytest.raises(ValueError, match='فشل عكس القيد'):
                SaleService.cancel_sale(sale)

    def test_cancel_commit_failure(self, app):
        from services.sale_service import SaleService
        sale = self._sale()
        with patch('models.Payment') as pay_mod, \
             patch.object(SaleService, 'has_inventory_posted', return_value=False), \
             patch('services.sale_service.db.session') as sess, \
             patch('services.sale_service.current_app') as capp:
            pay_mod.query.filter_by.return_value.count.return_value = 0
            pay_mod.query.filter_by.return_value.all.return_value = []
            sess.flush.side_effect = RuntimeError('commit fail')
            sess.rollback = MagicMock()
            capp.logger = _logger()
            with pytest.raises(RuntimeError, match='commit fail'):
                SaleService.cancel_sale(sale)


class TestUpdatePaymentStatus:
    def test_commit_failure_rolls_back(self, app):
        from services.sale_service import SaleService
        sale = MagicMock(sale_number='S-1')
        sale.recalculate_payment_status = MagicMock()
        with patch('services.sale_service.db.session') as sess, \
             patch('services.sale_service.current_app') as capp:
            sess.flush.side_effect = RuntimeError('db down')
            sess.rollback = MagicMock()
            capp.logger = _logger()
            with pytest.raises(RuntimeError, match='db down'):
                SaleService.update_payment_status(sale)
            sess.rollback.assert_called_once()
