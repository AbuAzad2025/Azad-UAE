"""Coverage wave — remaining gaps across 15 service modules."""
from __future__ import annotations

import builtins
import importlib
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestTicketServiceGaps:
    @pytest.mark.parametrize(
        'method_name,args',
        [
            ('resolve_ticket', (1, MagicMock())),
            ('close_ticket', (1, MagicMock())),
            ('reopen_ticket', (1, MagicMock())),
            ('add_comment', (1, {'body': 'x'}, MagicMock(id=1))),
            ('get_ticket', (1, MagicMock())),
        ],
    )
    def test_missing_ticket_raises(self, app, mocker, method_name, args):
        mock_session = mocker.patch('services.ticket_service.db.session')
        mock_session.get.return_value = None
        from services.ticket_service import TicketService

        with app.app_context():
            with pytest.raises(ValueError, match='غير موجودة'):
                getattr(TicketService, method_name)(*args)


class TestTreasuryServiceGaps:
    def test_gateway_and_in_transit_box_kinds(self, mocker):
        boxes = [
            MagicMock(
                id=1, code='GW1', name_ar='بوابة', name_en=None, box_type='payment_gateway',
                current_balance=Decimal('10'), currency='AED', branch_id=None,
            ),
            MagicMock(
                id=2, code='CHQ', name_ar='شيك', name_en=None, box_type='cheque_under_collection',
                current_balance=Decimal('20'), currency='AED', branch_id=None,
            ),
        ]
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = boxes
        mocker.patch('models.CashBox.query', new_callable=mocker.PropertyMock, return_value=mock_q)

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_liquidity_position(1)
        kinds = {a['kind'] for a in result['accounts']}
        assert 'gateway' in kinds
        assert 'in_transit' in kinds

    def test_gl_fallback_with_branch_filter(self, mocker):
        cb_q = MagicMock()
        cb_q.filter_by.return_value = cb_q
        cb_q.filter.return_value = cb_q
        cb_q.order_by.return_value = cb_q
        cb_q.all.return_value = []
        mocker.patch('models.CashBox.query', new_callable=mocker.PropertyMock, return_value=cb_q)

        acc = MagicMock(
            id=1, code='1100', liquidity_kind='cash', name_ar='نقد', name_en=None,
            currency='AED', branch_id=3,
        )
        acc.get_balance.return_value = Decimal('100')
        gl_q = MagicMock()
        gl_q.filter.return_value = gl_q
        gl_q.order_by.return_value = gl_q
        gl_q.all.return_value = [acc]
        mocker.patch('models.GLAccount.query', new_callable=mocker.PropertyMock, return_value=gl_q)

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_liquidity_position(1, branch_id=3)
        assert result['accounts'][0]['source'] == 'gl_account'

    def test_cheque_maturity_branch_and_missing_due_date(self, mocker):
        today = date.today()
        cheque = MagicMock(
            id=1, cheque_type='incoming', amount_aed=Decimal('50'),
            due_date=None, cheque_number='C0', cheque_bank_number=None,
            bank_name='B', drawer_name='D', payee_name='P', status='pending',
            cheque_type_ar='وارد',
        )
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [cheque]
        mocker.patch('models.Cheque.query', new_callable=mocker.PropertyMock, return_value=mock_q)

        from services.treasury_service import TreasuryService

        result = TreasuryService.get_cheque_maturity(tenant_id=1, branch_id=2)
        assert result['incoming']['total_count'] == 1


class TestSentimentServiceGaps:
    def test_no_sentiment_words_neutral(self):
        from services.sentiment_service import SentimentAnalyzer

        result = SentimentAnalyzer.analyze('the quick brown fox jumps')
        assert result['sentiment'] == 'neutral'
        assert result['confidence'] == 0.0


class TestShopCustomerAuthGaps:
    def test_register_short_name(self, sample_tenant):
        from services.shop_customer_auth_service import ShopCustomerAuthService

        with pytest.raises(ValueError, match='الاسم'):
            ShopCustomerAuthService.register(sample_tenant.id, 'A', 'a@b.co', '05012345678', 'pass12')

    def test_register_short_password(self, sample_tenant):
        from services.shop_customer_auth_service import ShopCustomerAuthService

        with pytest.raises(ValueError, match='كلمة المرور'):
            ShopCustomerAuthService.register(sample_tenant.id, 'Ali', 'a@b.co', '05012345678', '123')

    def test_register_updates_existing_customer_address(self, db_session, sample_tenant):
        from extensions import db
        from models import Customer
        from services.shop_customer_auth_service import ShopCustomerAuthService

        customer = Customer(
            tenant_id=sample_tenant.id,
            name='Old',
            customer_type='regular',
            phone='05033334444',
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()
        account = ShopCustomerAuthService.register(
            sample_tenant.id, 'New Name', 'newaddr@shop.test', '05033334444', 'pass1234', address='Street 1',
        )
        assert account.customer_id == customer.id
        assert customer.address == 'Street 1'

    @pytest.mark.parametrize('method_name,call_fn', [
        ('register', lambda svc, tid: svc.register(tid, 'Ali', 'c1@shop.test', '05044445555', 'pass1234')),
        ('authenticate', lambda svc, tid: svc.authenticate(tid, 'c2@shop.test', 'pass1234')),
        ('request_password_reset', lambda svc, tid: svc.request_password_reset(tid, 'c3@shop.test')),
        ('reset_password', lambda svc, tid: svc.reset_password(tid, 'tok', 'newpass1')),
    ])
    def test_commit_failure_rolls_back(self, db_session, sample_tenant, method_name, call_fn, mocker):
        from services.shop_customer_auth_service import ShopCustomerAuthService

        if method_name == 'authenticate':
            from tests.unit.services.test_shop_customer_auth_service import _account
            _account(db_session, sample_tenant.id, email='c2@shop.test', password='pass1234')
        elif method_name == 'request_password_reset':
            from tests.unit.services.test_shop_customer_auth_service import _account
            _account(db_session, sample_tenant.id, email='c3@shop.test')
        elif method_name == 'reset_password':
            from tests.unit.services.test_shop_customer_auth_service import _account
            acc = _account(db_session, sample_tenant.id, email='c4@shop.test')
            acc.password_reset_token = 'tok'
            acc.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            db_session.commit()

        mocker.patch('services.shop_customer_auth_service.db.session.flush', side_effect=RuntimeError('db'))
        with pytest.raises(RuntimeError, match='db'):
            call_fn(ShopCustomerAuthService, sample_tenant.id)
        ShopCustomerAuthService  # noqa: B018 — keep import used

    def test_reset_password_short_new_password(self, sample_tenant):
        from services.shop_customer_auth_service import ShopCustomerAuthService

        with pytest.raises(ValueError, match='كلمة المرور'):
            ShopCustomerAuthService.reset_password(sample_tenant.id, 'tok', '123')

    def test_reset_password_unknown_token(self, sample_tenant):
        from services.shop_customer_auth_service import ShopCustomerAuthService

        with pytest.raises(ValueError, match='رمز'):
            ShopCustomerAuthService.reset_password(sample_tenant.id, 'missing-token', 'newpass1')


class TestStoreOnlinePaymentGaps:
    def test_api_key_from_vault(self, app, mocker):
        vault = MagicMock(nowpayments_api_key='vault-key')
        mocker.patch('services.store_online_payment_service.PaymentVault.get_tenant_vault', return_value=vault)
        mocker.patch('services.store_online_payment_service.PaymentVault.get_platform_vault', return_value=None)

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            assert StoreOnlinePaymentService._api_key(1) == 'vault-key'

    def test_create_payment_missing_url(self, app, mocker):
        sale = MagicMock(id=1, amount_aed=10, total_amount=10, currency='AED', sale_number='S1', checkout_payment_method=None)
        store = MagicMock(tenant_id=2, title='Shop')
        resp = MagicMock(status_code=200, text='')
        resp.json.return_value = {'payment_id': 'p1'}
        mocker.patch('services.store_online_payment_service.requests.post', return_value=resp)
        mocker.patch('services.store_online_payment_service.StoreOnlinePaymentService._api_key', return_value='k')
        mocker.patch('services.store_online_payment_service.get_nowpayments_ipn_url', return_value='http://ipn')

        from services.store_online_payment_service import StoreOnlinePaymentService

        with app.app_context():
            with pytest.raises(ValueError, match='رابط الدفع'):
                StoreOnlinePaymentService.create_payment_for_sale(sale, store)


class TestStoreCheckoutGaps:
    def test_serial_product_rejected(self, app, mocker):
        product = MagicMock(id=1, name='Serial Item', has_serial_number=True, tenant_id=1, is_active=True)
        mocker.patch('services.store_checkout_service.Product.query').filter_by.return_value.first.return_value = product
        mocker.patch('services.store_checkout_service.StoreService.online_stock_map', return_value={1: Decimal('5')})

        from services.store_checkout_service import StoreCheckoutService

        with app.app_context():
            with pytest.raises(ValueError, match='الهاتف'):
                StoreCheckoutService.build_lines_from_cart(1, {1: 1}, online_warehouse_id=1)

    def test_stock_check_failure_message(self, app, mocker):
        product = MagicMock(id=1, name='Widget', has_serial_number=False, tenant_id=1, is_active=True)
        mocker.patch('services.store_checkout_service.Product.query').filter_by.return_value.first.return_value = product
        mocker.patch('services.store_checkout_service.StoreService.online_stock_map', return_value={1: Decimal('5')})
        mocker.patch('services.store_checkout_service.StockService.check_availability_in_warehouse', return_value=(False, 'blocked'))

        from services.store_checkout_service import StoreCheckoutService

        with app.app_context():
            with pytest.raises(ValueError, match='Widget'):
                StoreCheckoutService.build_lines_from_cart(1, {1: 1}, online_warehouse_id=1)


class TestStoreOrderGaps:
    def test_reverse_loyalty_without_account(self, mocker, online_sale):
        txn = MagicMock(points=10)
        mocker.patch('models.shop_loyalty.ShopLoyaltyTransaction.query').filter_by.return_value.first.return_value = txn
        mocker.patch('models.shop_customer_account.ShopCustomerAccount.query').filter_by.return_value.first.return_value = None
        online_sale.customer_id = 9

        from services.store_order_service import StoreOrderService

        StoreOrderService._reverse_loyalty_points(online_sale)


class TestSaleServiceGaps:
    def test_create_sale_needs_exchange_rate(self, app):
        from services.sale_service import SaleService

        customer = MagicMock(is_active=True, id=1, tenant_id=1, customer_type='regular')
        seller = MagicMock(is_active=True, id=2, tenant_id=1, branch_id=1)
        product = MagicMock(id=1, is_active=True, has_serial_number=False, partner_shares=[])
        lines = [{'product': product, 'quantity': 1, 'unit_price': 10}]
        with patch('services.sale_service.get_active_tenant_id', return_value=1), \
             patch('models.Warehouse') as mock_wh, \
             patch('services.sale_service.ExchangeRateService') as mock_ex, \
             patch('services.sale_service.normalize_tax_rate', return_value=Decimal('5')), \
             patch('utils.tax_settings.get_prices_include_vat', return_value=True):
            wh = MagicMock(id=1, branch_id=1)
            mock_wh.query.filter_by.return_value = mock_wh.query
            mock_wh.query.first.return_value = wh
            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate_mode': 'needs_input'}
            with app.app_context():
                with pytest.raises(ValueError, match='سعر الصرف'):
                    SaleService.create_sale(customer, seller, lines, currency='USD')

    def test_create_sale_invalid_exchange_rate(self, app):
        from services.sale_service import SaleService

        customer = MagicMock(is_active=True, id=1, tenant_id=1, customer_type='regular')
        seller = MagicMock(is_active=True, id=2, tenant_id=1, branch_id=1)
        product = MagicMock(id=1, is_active=True, has_serial_number=False, partner_shares=[])
        lines = [{'product': product, 'quantity': 1, 'unit_price': 10}]
        with patch('services.sale_service.get_active_tenant_id', return_value=1), \
             patch('models.Warehouse') as mock_wh, \
             patch('services.sale_service.ExchangeRateService') as mock_ex, \
             patch('services.sale_service.normalize_tax_rate', return_value=Decimal('5')), \
             patch('utils.tax_settings.get_prices_include_vat', return_value=True):
            wh = MagicMock(id=1, branch_id=1)
            mock_wh.query.filter_by.return_value = mock_wh.query
            mock_wh.query.first.return_value = wh
            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 0, 'rate_mode': 'auto'}
            with app.app_context():
                with pytest.raises(ValueError, match='سعر الصرف غير صالح'):
                    SaleService.create_sale(customer, seller, lines)

    def test_create_sale_no_warehouse(self, app):
        from services.sale_service import SaleService

        customer = MagicMock(is_active=True, id=1, tenant_id=1)
        seller = MagicMock(is_active=True, id=2, tenant_id=1, branch_id=1)
        product = MagicMock(id=1, is_active=True)
        lines = [{'product': product, 'quantity': 1, 'unit_price': 10}]
        with patch('services.sale_service.get_active_tenant_id', return_value=1), \
             patch('models.Warehouse') as mock_wh:
            mock_wh.query.filter_by.return_value = mock_wh.query
            mock_wh.query.first.return_value = None
            with app.app_context():
                with pytest.raises(ValueError, match='مستودع'):
                    SaleService.create_sale(customer, seller, lines)

    def test_add_payment_cheque_missing_bank(self, app):
        from services.sale_service import SaleService

        sale = MagicMock(branch_id=1, tenant_id=1)
        with app.app_context():
            with pytest.raises(ValueError, match='البنك'):
                SaleService.create_payment_for_sale(
                    sale, Decimal('10'), 'cheque', currency='AED',
                    cheque_number='123', cheque_date='2025-01-01', bank_name=None,
                )

    def test_add_payment_cheque_missing_date(self, app):
        from services.sale_service import SaleService

        sale = MagicMock(branch_id=1, tenant_id=1)
        with app.app_context():
            with pytest.raises(ValueError, match='تاريخ'):
                SaleService.create_payment_for_sale(
                    sale, Decimal('10'), 'cheque', currency='AED',
                    cheque_number='123', cheque_date=None, bank_name='Bank',
                )


class TestPaymentServiceGaps:
    def test_allocate_skips_invalid_sale(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name='Cust')
        customer.apply_receipt = MagicMock()
        receipt = MagicMock(
            id=13, receipt_number='RCV-SKIP', amount_aed=Decimal('50'), amount=Decimal('50'),
            payment_method='cash', payment_confirmed=True, branch_id=1, currency='AED', exchange_rate=Decimal('1'),
        )
        with app.app_context(), \
             patch('services.payment_service.db') as mock_db, \
             patch('services.payment_service.current_user', MagicMock(is_authenticated=True, id=1, tenant_id=1)), \
             patch('services.payment_service.generate_number', return_value='RCV-SKIP'), \
             patch.object(PaymentService, '_resolve_transaction_rate', return_value=Decimal('1')), \
             patch.object(PaymentService, '_resolve_branch_id', return_value=1), \
             patch('services.payment_service.GLService') as gl, \
             patch('services.payment_service.post_or_fail'), \
             patch('services.payment_service.Receipt', return_value=receipt):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else None
            gl.get_payment_debit_account.return_value = '1100'
            gl.get_payment_debit_concept.return_value = 'CASH'
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt({
                'customer_id': 1, 'amount': 50, 'currency': 'AED', 'payment_method': 'cash',
                'allocate_to_sales': {99: 50},
            })
            customer.apply_receipt.assert_called_once()


class TestLoggingCoreGaps:
    def test_colorama_import_fallback(self):
        mod_name = 'services.logging_core'
        saved = sys.modules.pop(mod_name, None)
        real_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'colorama':
                raise ImportError('blocked')
            return real_import(name, globals, locals, fromlist, level)

        try:
            with patch.object(builtins, '__import__', side_effect=blocked_import):
                mod = importlib.import_module(mod_name)
            assert mod.Fore.BLUE == ''
        finally:
            if saved is not None:
                sys.modules[mod_name] = saved
            importlib.import_module(mod_name)

    def test_check_cpu_without_psutil(self, mocker):
        mocker.patch.dict('sys.modules', {'psutil': None})
        from services.logging_core import LoggingCore

        result = LoggingCore._check_cpu()
        assert result['healthy'] is True
        assert 'psutil' in result['error']


class TestInventoryReconciliationGaps:
    def test_date_bound_whitespace_only(self):
        from services.inventory_reconciliation_service import InventoryReconciliationService

        assert InventoryReconciliationService._date_bound('   ', end_of_day=False) is None

    def test_build_report_with_branch_filter(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value = pwc_q
        pwc_q.join.return_value = pwc_q
        pwc_q.filter.return_value = pwc_q
        pwc_q.all.return_value = []
        mocker.patch.object(
            __import__('models', fromlist=['ProductWarehouseCost']).ProductWarehouseCost,
            'query',
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        from services.inventory_reconciliation_service import InventoryReconciliationService

        report = InventoryReconciliationService.build_report(tenant_id=1, branch_id=3)
        assert report['rows'] == []
        pwc_q.join.assert_called_once()


class TestRealTimeListenersGaps:
    def test_send_notification_print_failure(self, mocker):
        mock_print = mocker.patch('builtins.print', side_effect=[RuntimeError('print fail'), None])
        from services.real_time_listeners import RealTimeAccountingListeners

        RealTimeAccountingListeners._send_notification('Title', 'hello', level='info')
        assert mock_print.call_count == 2
        assert 'خطأ' in str(mock_print.call_args_list[1])


class TestReturnServiceGaps:
    def test_tenant_mismatch_on_sale_line(self, app, mocker):
        from tests.unit.services.test_return_service_assurance import _sale, _sale_line, _user

        sale = _sale(id=1, tenant_id=1)
        line = _sale_line(sale_id=1, tenant_id=99)
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
        session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)

        from services.return_service import ReturnService

        with app.app_context():
            with pytest.raises(ValueError, match='outside tenant'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1}],
                    user=_user(),
                )

    def test_missing_product_on_line(self, app, mocker):
        from tests.unit.services.test_return_service_assurance import _sale, _sale_line, _user

        sale = _sale(id=1, tenant_id=1)
        line = _sale_line(sale_id=1, product_id=3, quantity=Decimal('1'))
        line.product = None
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: {
            sale.id: sale,
            line.id: line,
            line.product_id: None,
        }.get(pk)
        session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)

        from services.return_service import ReturnService

        with app.app_context():
            with pytest.raises(ValueError, match='not found'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1}],
                    user=_user(),
                )


class TestGlServiceGaps:
    def test_resolve_missing_account_raises(self, sample_tenant, mocker):
        mocker.patch('services.gl_service.gl_helpers.get_account', return_value=None)
        mocker.patch('services.gl_service.GLService.ensure_core_accounts')
        from services.gl_service import GLService

        with pytest.raises(ValueError, match='not found'):
            GLService._resolve_journal_line_account(
                {'account': 'MISSING'},
                sample_tenant.id,
                ensure_core=True,
                missing_ok=False,
            )

    def test_post_entry_rejects_header_account(self, sample_tenant, mocker):
        header = MagicMock(is_header=True, code='H1', full_name='Header')
        mocker.patch('services.gl_service.GLService._resolve_journal_line_account', return_value=header)
        from services.gl_service import GLService

        with pytest.raises(ValueError, match='الحساب الرئيسي'):
            GLService.post_entry(
                [{'debit': 1, 'credit': 0, 'concept_code': 'CASH'}],
                description='x',
                tenant_id=sample_tenant.id,
            )

    def test_default_liquidity_multiple_without_branch(self, sample_tenant, mocker):
        a1 = MagicMock(code='C1')
        a2 = MagicMock(code='C2')
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [a1, a2]
        mocker.patch('services.gl_service.GLAccount.query', mock_q)
        from services.gl_service import GLService

        with pytest.raises(ValueError, match='Multiple'):
            GLService.get_default_liquidity_account('cash', tenant_id=sample_tenant.id)

    def test_manual_entry_inactive_account(self, sample_tenant, mocker):
        acct = MagicMock(is_header=False, is_active=False, full_name='Inactive', code='I1')
        mocker.patch('services.gl_service.gl_helpers.get_account', return_value=acct)
        mocker.patch('services.gl_service.gl_helpers.resolve_tenant_id', return_value=sample_tenant.id)
        from services.gl_service import GLService

        with pytest.raises(ValueError, match='غير نشط'):
            GLService.create_manual_entry(
                'x',
                [{'account_code': 'I1', 'debit': 1, 'credit': 0}],
            )

    def test_legacy_balance_unknown_concept(self, sample_tenant, mocker):
        mocker.patch('services.gl_account_resolver.is_dynamic_gl_mapping_enabled', return_value=False)
        from services.gl_service import GLService

        assert GLService._reconciliation_concept_balance(
            'UNKNOWN', tenant_id=sample_tenant.id,
        ) == Decimal('0')

    def test_manual_entry_header_account(self, sample_tenant, mocker):
        acct = MagicMock(is_header=True, is_active=True, full_name='Header', code='H1')
        mocker.patch('services.gl_service.gl_helpers.get_account', return_value=acct)
        mocker.patch('services.gl_service.gl_helpers.resolve_tenant_id', return_value=sample_tenant.id)
        from services.gl_service import GLService

        with pytest.raises(ValueError, match='حساب رئيسي'):
            GLService.create_manual_entry(
                'x',
                [{'account_code': 'H1', 'debit': 1, 'credit': 0}],
            )


class TestStoreCheckoutRemainingGaps:
    def test_missing_product_in_cart(self, app, mocker):
        mocker.patch('services.store_checkout_service.Product.query').filter_by.return_value.first.return_value = None
        mocker.patch('services.store_checkout_service.StoreService.online_stock_map', return_value={1: Decimal('5')})
        from services.store_checkout_service import StoreCheckoutService

        with app.app_context():
            with pytest.raises(ValueError, match='غير متاح'):
                StoreCheckoutService.build_lines_from_cart(1, {1: 1}, online_warehouse_id=1)


class TestInventoryWarehouseFilter:
    def test_build_report_with_warehouse_filter(self, mocker):
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value = pwc_q
        pwc_q.all.return_value = []
        mocker.patch.object(
            __import__('models', fromlist=['ProductWarehouseCost']).ProductWarehouseCost,
            'query',
            new_callable=mocker.PropertyMock,
            return_value=pwc_q,
        )
        from services.inventory_reconciliation_service import InventoryReconciliationService

        report = InventoryReconciliationService.build_report(tenant_id=1, warehouse_id=7)
        assert report['rows'] == []
        pwc_q.filter_by.assert_any_call(warehouse_id=7)


class TestPaymentServiceRemainingGaps:
    def test_allocate_breaks_when_remaining_exhausted(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name='Cust')
        customer.apply_receipt = MagicMock()
        receipt = MagicMock(
            id=20, receipt_number='RCV-BRK', amount_aed=Decimal('30'), amount=Decimal('30'),
            payment_method='cash', payment_confirmed=True, branch_id=1, currency='AED', exchange_rate=Decimal('1'),
        )
        sale1 = MagicMock(id=2, customer_id=1, balance_due=Decimal('30'), branch_id=1, tenant_id=1, exchange_rate=Decimal('1'))
        sale2 = MagicMock(id=3, customer_id=1, balance_due=Decimal('50'), branch_id=1, tenant_id=1, exchange_rate=Decimal('1'))
        sale1.recalculate_payment_status = MagicMock()
        sale2.recalculate_payment_status = MagicMock()

        with app.app_context(), \
             patch('services.payment_service.db') as mock_db, \
             patch('services.payment_service.current_user', MagicMock(is_authenticated=True, id=1, tenant_id=1)), \
             patch('services.payment_service.generate_number', return_value='PAY-BRK'), \
             patch.object(PaymentService, '_resolve_transaction_rate', return_value=Decimal('1')), \
             patch.object(PaymentService, '_resolve_branch_id', return_value=1), \
             patch('services.payment_service.GLService') as gl, \
             patch('services.payment_service.post_or_fail'), \
             patch('services.payment_service.Receipt', return_value=receipt), \
             patch('services.payment_service.current_app') as capp:
            capp.logger = MagicMock()
            mock_db.session.get.side_effect = lambda model, pk: {1: customer, 2: sale1, 3: sale2}.get(pk)
            gl.get_payment_debit_account.return_value = '1100'
            gl.get_payment_debit_concept.return_value = 'CASH'
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt({
                'customer_id': 1, 'amount': 30, 'currency': 'AED', 'payment_method': 'cash',
                'allocate_to_sales': {2: 30, 3: 30},
            })
            assert mock_db.session.get.call_count >= 2

    def test_allocate_skips_zero_balance_sale(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1, name='Cust')
        customer.apply_receipt = MagicMock()
        receipt = MagicMock(
            id=21, receipt_number='RCV-ZB', amount_aed=Decimal('50'), amount=Decimal('50'),
            payment_method='cash', payment_confirmed=True, branch_id=1, currency='AED', exchange_rate=Decimal('1'),
        )
        sale = MagicMock(id=2, customer_id=1, balance_due=Decimal('0'), branch_id=1, tenant_id=1, exchange_rate=Decimal('1'))
        sale.recalculate_payment_status = MagicMock()

        with app.app_context(), \
             patch('services.payment_service.db') as mock_db, \
             patch('services.payment_service.current_user', MagicMock(is_authenticated=True, id=1, tenant_id=1)), \
             patch('services.payment_service.generate_number', return_value='RCV-ZB'), \
             patch.object(PaymentService, '_resolve_transaction_rate', return_value=Decimal('1')), \
             patch.object(PaymentService, '_resolve_branch_id', return_value=1), \
             patch('services.payment_service.GLService') as gl, \
             patch('services.payment_service.post_or_fail'), \
             patch('services.payment_service.Receipt', return_value=receipt):
            mock_db.session.get.side_effect = lambda model, pk: customer if pk == 1 else sale
            gl.get_payment_debit_account.return_value = '1100'
            gl.get_payment_debit_concept.return_value = 'CASH'
            gl.get_customer_credit_account.return_value = '1200'
            gl.get_customer_credit_concept.return_value = 'AR'
            gl.ensure_core_accounts.return_value = None
            PaymentService.create_receipt({
                'customer_id': 1, 'amount': 50, 'currency': 'AED', 'payment_method': 'cash',
                'allocate_to_sales': {2: 50},
            })
            customer.apply_receipt.assert_called_once()

    def test_get_customer_balance_scoped_resolves_tenant(self):
        from services.payment_service import PaymentService

        def _query_chain(scalar_val):
            chain = MagicMock()
            chain.filter.return_value = chain
            chain.scalar.return_value = scalar_val
            return chain

        with patch('services.payment_service.db') as mock_db, \
             patch('services.payment_service.get_active_tenant_id', return_value=9):
            mock_db.session.query.side_effect = [
                _query_chain(Decimal('0')),
                _query_chain(Decimal('0')),
                _query_chain(Decimal('0')),
            ]
            bal = PaymentService.get_customer_balance_scoped(5)
        assert bal == Decimal('0')

    def test_allocate_oldest_breaks_when_remaining_zero(self, app):
        from services.payment_service import PaymentService

        customer = MagicMock(id=1, tenant_id=1)
        customer.apply_receipt = MagicMock()
        receipt = MagicMock(
            amount_aed=Decimal('10'), receipt_number='RCV-OLD', currency='AED',
            exchange_rate=Decimal('1'), payment_method='cash', payment_confirmed=True, branch_id=1,
        )
        sale1 = MagicMock(id=2, balance_due=Decimal('10'), branch_id=1, tenant_id=1, exchange_rate=Decimal('1'))
        sale2 = MagicMock(id=3, balance_due=Decimal('50'), branch_id=1, tenant_id=1, exchange_rate=Decimal('1'))
        sale1.recalculate_payment_status = MagicMock()
        sale2.recalculate_payment_status = MagicMock()

        with app.app_context(), \
             patch.object(PaymentService, 'get_unpaid_sales', return_value=[sale1, sale2]), \
             patch('services.payment_service.generate_number', return_value='PAY-OLD'), \
             patch('services.payment_service.db') as mock_db, \
             patch('services.payment_service.current_user', MagicMock(is_authenticated=True, id=1)), \
             patch('services.payment_service.current_app') as capp:
            capp.logger = MagicMock()
            PaymentService.allocate_receipt_to_oldest_sales(receipt, customer)
            customer.apply_receipt.assert_called_once()


class TestReturnServiceRemainingGaps:
    def test_serial_fractional_quantity_rejected(self, app, mocker):
        from tests.unit.services.test_return_service_assurance import (
            TestCreateReturn, _product, _sale, _sale_line, _user,
        )

        sale = _sale()
        line = _sale_line(quantity=Decimal('2'))
        product = _product(has_serial_number=True)
        helper = TestCreateReturn()
        helper._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService

        with app.app_context():
            with pytest.raises(ValueError, match='whole-number'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1.5}],
                    user=_user(),
                )

    def test_serial_not_linked_to_line(self, app, mocker):
        from tests.unit.services.test_return_service_assurance import (
            TestCreateReturn, _product, _sale, _sale_line, _user,
        )

        sale = _sale()
        line = _sale_line()
        product = _product(has_serial_number=True)
        helper = TestCreateReturn()
        helper._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.ReturnService._serials_from_line_data', return_value=['SN-MISS'])
        mocker.patch('utils.serial_helpers.validate_serials')
        serial_q = MagicMock()
        serial_q.filter_by.return_value.first.return_value = None
        mocker.patch('services.return_service.ProductSerial.query', serial_q)
        from services.return_service import ReturnService

        with app.app_context():
            with pytest.raises(ValueError, match='not linked'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1, 'serials': ['SN-MISS']}],
                    user=_user(),
                )

    def test_serial_not_sold_status(self, app, mocker):
        from tests.unit.services.test_return_service_assurance import (
            TestCreateReturn, _product, _sale, _sale_line, _user,
        )

        sale = _sale()
        line = _sale_line()
        product = _product(has_serial_number=True)
        helper = TestCreateReturn()
        helper._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.ReturnService._serials_from_line_data', return_value=['SN1'])
        mocker.patch('utils.serial_helpers.validate_serials')
        serial = MagicMock(status='available', sale_line_id=line.id)
        serial_q = MagicMock()
        serial_q.filter_by.return_value.first.return_value = serial
        mocker.patch('services.return_service.ProductSerial.query', serial_q)
        from services.return_service import ReturnService

        with app.app_context():
            with pytest.raises(ValueError, match='not sold'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1, 'serials': ['SN1']}],
                    user=_user(),
                )


class TestReturnServiceSoldQty:
    def test_sale_line_sold_qty_zero_raises_in_create(self, app, mocker):
        from tests.unit.services.test_return_service_assurance import (
            TestCreateReturn, _product, _sale, _sale_line, _user,
        )
        from services.return_service import ReturnService

        sale = _sale()
        line = _sale_line(quantity=Decimal('1'))
        product = _product(has_serial_number=False)
        helper = TestCreateReturn()
        helper._patch_common(mocker, sale, line, product)
        mocker.patch.object(ReturnService, '_sale_line_sold_qty', return_value=Decimal('0'))

        with app.app_context():
            with pytest.raises(ValueError, match='Invalid sale line quantity'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1}],
                    user=_user(),
                )


class TestSaleServiceRemainingGaps:
    def test_vat_inclusive_commission_revenue_path(self, app):
        from tests.unit.services.test_sale_service_chunk3 import _actors, _create_ctx

        customer, seller, product = _actors(
            partner_shares=[MagicMock(partner_customer_id=10, percentage=Decimal('10'))],
        )
        partner = MagicMock(customer_type='partner')
        with _create_ctx(customer, seller, product) as (svc, stock, db_sess, _):
            stock._resolve_cogs_unit_cost.return_value = (Decimal('30'), 'mwac')
            with patch('models.Customer') as cust_mod, \
                 patch('utils.tax_settings.get_prices_include_vat', return_value=True), \
                 patch('services.sale_service.normalize_tax_rate', return_value=Decimal('5')):
                cust_mod.query.filter_by.return_value.first.return_value = partner
                sale = svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    tax_rate=5,
                    currency='AED',
                )
        assert sale is not None
        assert db_sess.add.called

    def test_commission_base_aed_quantize_fallback(self):
        from services.sale_service import SaleService

        class BadRate:
            def __rmul__(self, other):
                raise RuntimeError('mul fail')

        result = SaleService._commission_base_aed(Decimal('10'), BadRate())
        assert result == Decimal('10')
        assert SaleService._commission_base_aed(Decimal('0'), Decimal('1')) == Decimal('0')

    def test_commission_skips_zero_amount(self, app):
        from tests.unit.services.test_sale_service_chunk3 import _actors, _create_ctx

        customer, seller, product = _actors(
            partner_shares=[MagicMock(partner_customer_id=10, percentage=Decimal('0.001'))],
        )
        partner = MagicMock(customer_type='partner')
        with _create_ctx(customer, seller, product) as (svc, stock, db_sess, _):
            stock._resolve_cogs_unit_cost.return_value = (Decimal('99.999'), 'mwac')
            with patch('models.Customer') as cust_mod:
                cust_mod.query.filter_by.return_value.first.return_value = partner
                svc.create_sale(
                    customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                    currency='AED',
                )
        assert db_sess.add.called

    def test_negative_payment_on_create_rejected(self, app):
        from tests.unit.services.test_sale_service_chunk3 import _actors, _create_ctx
        from services.sale_service import SaleService

        customer, seller, product = _actors()
        payment_data = {'amount': -5, 'currency': 'AED', 'exchange_rate': 1.0}
        with _create_ctx(customer, seller, product, payment_data=payment_data, expect_error=True) as (svc, _, _, _):
            with patch.object(SaleService, 'fulfill_sale'):
                with pytest.raises(ValueError, match='سالب'):
                    svc.create_sale(
                        customer, seller, [{'product': product, 'quantity': 1, 'unit_price': 100}],
                        payment_data=payment_data,
                        currency='AED',
                    )
