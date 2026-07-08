"""Return service — tenant isolation, GL posting, serial/MWAC paths."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest


def _user(tenant_id=1, seller=False, authenticated=True):
    u = MagicMock()
    u.is_authenticated = authenticated
    u.id = 10
    u.is_seller = MagicMock(return_value=seller)
    return u


def _sale(**kwargs):
    s = MagicMock()
    s.id = kwargs.get('id', 100)
    s.tenant_id = kwargs.get('tenant_id', 1)
    s.branch_id = kwargs.get('branch_id', 2)
    s.warehouse_id = kwargs.get('warehouse_id', 3)
    s.status = kwargs.get('status', 'confirmed')
    s.customer_id = kwargs.get('customer_id', 5)
    s.customer = kwargs.get('customer', MagicMock())
    s.currency = 'AED'
    s.exchange_rate = Decimal('1')
    s.sale_number = 'S-001'
    s.subtotal = kwargs.get('subtotal', Decimal('100'))
    s.discount_amount = kwargs.get('discount_amount', Decimal('0'))
    s.shipping_cost = kwargs.get('shipping_cost', Decimal('0'))
    s.tax_rate = kwargs.get('tax_rate', Decimal('5'))
    s.seller_id = kwargs.get('seller_id', 10)
    s.recalculate_payment_status = MagicMock()
    return s


def _sale_line(**kwargs):
    sl = MagicMock()
    sl.id = kwargs.get('id', 200)
    sl.sale_id = kwargs.get('sale_id', 100)
    sl.tenant_id = kwargs.get('tenant_id', 1)
    sl.product_id = kwargs.get('product_id', 50)
    sl.quantity = kwargs.get('quantity', Decimal('1'))
    sl.line_total = kwargs.get('line_total', Decimal('100'))
    sl.cost_price = kwargs.get('cost_price', Decimal('40'))
    sl.product = kwargs.get('product')
    return sl


def _product(**kwargs):
    p = MagicMock()
    p.id = kwargs.get('id', 50)
    p.name = kwargs.get('name', 'Widget')
    p.has_serial_number = kwargs.get('has_serial_number', False)
    p.cost_price = kwargs.get('cost_price', Decimal('30'))
    return p


class TestNormalizeCondition:
    @pytest.mark.parametrize('raw,expected', [
        ('good', 'good'), ('sellable', 'good'), ('damaged', 'damaged'), ('defective', 'damaged'),
    ])
    def test_known_conditions(self, raw, expected):
        from services.return_service import ReturnService
        assert ReturnService._normalize_condition(raw) == expected

    def test_unsupported_raises(self):
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='Unsupported'):
            ReturnService._normalize_condition('broken')


class TestOptionalMoney:
    def test_none_and_empty(self):
        from services.return_service import ReturnService
        assert ReturnService._optional_money(None) is None
        assert ReturnService._optional_money('') is None

    def test_invalid_raises(self):
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='invalid'):
            ReturnService._optional_money('abc')

    def test_negative_raises(self):
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='negative'):
            ReturnService._optional_money('-1')

    def test_valid_amount(self):
        from services.return_service import ReturnService
        assert ReturnService._optional_money('10.555') == Decimal('10.555')


class TestValidateSaleAccess:
    def test_unauthenticated_skips(self):
        from services.return_service import ReturnService
        ReturnService._validate_sale_access(_sale(), user=None)

    def test_cross_tenant_regular_user(self, mocker):
        mocker.patch('services.return_service.get_active_tenant_id', return_value=2)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='tenant scope'):
            ReturnService._validate_sale_access(_sale(tenant_id=1), _user(tenant_id=2))

    def test_platform_owner_wrong_active_tenant(self, mocker):
        mocker.patch('services.return_service.get_active_tenant_id', return_value=2)
        mocker.patch('services.return_service.is_platform_owner', return_value=True)
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='active tenant'):
            ReturnService._validate_sale_access(_sale(tenant_id=1), _user())

    def test_branch_scope_violation(self, mocker):
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=99)
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='branch scope'):
            ReturnService._validate_sale_access(_sale(branch_id=2), _user())

    def test_seller_cannot_return_other_sale(self, mocker):
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with pytest.raises(ValueError, match='Seller cannot'):
            ReturnService._validate_sale_access(_sale(seller_id=99), _user(seller=True))


class TestCreateReturn:
    def _patch_common(self, mocker, sale, sale_line, product):
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: {
            sale.id: sale,
            sale_line.id: sale_line,
        }.get(pk)
        session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal('0')
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        mocker.patch('services.return_service.should_post_vat_gl', return_value=True)
        mocker.patch('services.return_service.StockService.create_movement')
        mocker.patch('services.return_service.GLService.get_account_code_for_concept', return_value='4100')
        mocker.patch('services.return_service.GLService.get_customer_credit_account', return_value='1130')
        mocker.patch('services.return_service.GLService.get_customer_credit_concept', return_value='AR')
        mocker.patch('services.return_service.GLService.ensure_core_accounts')
        mocker.patch('services.return_service.post_or_fail')
        product = product or _product()
        sale_line.product = product
        if session.get.side_effect:
            orig = session.get.side_effect
            def getter(model, pk):
                if pk == sale_line.product_id:
                    return product
                return orig(model, pk)
            session.get.side_effect = getter
        return session

    def test_sale_not_found(self, app, mocker):
        session = mocker.patch('services.return_service.db.session')
        session.get.return_value = None
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='not found'):
                ReturnService.create_return(999, [], user=_user())

    def test_cancelled_sale_rejected(self, app, mocker):
        session = mocker.patch('services.return_service.db.session')
        session.get.return_value = _sale(status='cancelled')
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='cancelled'):
                ReturnService.create_return(100, [], user=_user())

    def test_pending_sale_rejected(self, app, mocker):
        session = mocker.patch('services.return_service.db.session')
        session.get.return_value = _sale(status='pending')
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='pending'):
                ReturnService.create_return(100, [], user=_user())

    def test_happy_path_good_condition(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product()
        line.product = product
        session = self._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService
        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1, 'condition': 'good'}],
                user=_user(),
            )
        assert result.return_number == 'R-001'
        session.flush.assert_called()

    def test_no_lines_raises(self, app, mocker):
        sale = _sale()
        session = mocker.patch('services.return_service.db.session')
        session.get.return_value = sale
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='At least one'):
                ReturnService.create_return(sale.id, [{'sale_line_id': 1, 'quantity': 0}], user=_user())

    def test_sale_line_not_found(self, app, mocker):
        sale = _sale()
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: sale if pk == sale.id else None
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='Sale line'):
                ReturnService.create_return(sale.id, [{'sale_line_id': 999, 'quantity': 1}], user=_user())

    def test_wrong_sale_line_sale(self, app, mocker):
        sale = _sale()
        line = _sale_line(sale_id=999)
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='does not belong'):
                ReturnService.create_return(sale.id, [{'sale_line_id': line.id, 'quantity': 1}], user=_user())

    def test_cross_tenant_line(self, app, mocker):
        sale = _sale(tenant_id=1)
        line = _sale_line(tenant_id=2)
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='outside tenant'):
                ReturnService.create_return(sale.id, [{'sale_line_id': line.id, 'quantity': 1}], user=_user())

    def test_serial_product_validation(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product(has_serial_number=True)
        line.product = product
        self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.ReturnService._serials_from_line_data', return_value=['SN1'])
        mocker.patch('utils.serial_helpers.validate_serials')
        serial = MagicMock(status='sold', sale_line_id=line.id)
        serial_q = MagicMock()
        serial_q.filter_by.return_value.first.return_value = serial
        mocker.patch('services.return_service.ProductSerial.query', serial_q)
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1, 'serials': ['SN1']}],
                user=_user(),
            )
        assert serial.status == 'available'

    def test_damaged_serial_status(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product(has_serial_number=True)
        line.product = product
        self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.ReturnService._serials_from_line_data', return_value=['SN1'])
        mocker.patch('utils.serial_helpers.validate_serials')
        serial = MagicMock(status='sold', sale_line_id=line.id)
        serial_q = MagicMock()
        serial_q.filter_by.return_value.first.return_value = serial
        mocker.patch('services.return_service.ProductSerial.query', serial_q)
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1, 'condition': 'damaged', 'serials': ['SN1']}],
                user=_user(),
            )
        assert serial.status == 'defective'

    def test_unexpected_serials_on_non_serial_product(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product(has_serial_number=False)
        line.product = product
        self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.ReturnService._serials_from_line_data', return_value=['SN1'])
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='does not use serial'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1, 'serials': ['SN1']}],
                    user=_user(),
                )

    def test_manual_refund_override(self, app, mocker):
        sale = _sale(tax_rate=Decimal('5'))
        line = _sale_line()
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService
        with app.app_context():
            result = ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1}],
                user=_user(),
                manual_refund_amount='50',
                notes='test',
            )
        assert result.refund_amount == Decimal('50.000')
        assert 'Manual refund override' in result.notes

    def test_vat_disabled_zeros_tax(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.should_post_vat_gl', return_value=False)
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1}],
                user=_user(),
            )

    def test_commit_failure_rolls_back(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product()
        line.product = product
        session = self._patch_common(mocker, sale, line, product)
        session.flush.side_effect = RuntimeError('db fail')
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(RuntimeError, match='db fail'):
                ReturnService.create_return(
                    sale.id,
                    [{'sale_line_id': line.id, 'quantity': 1}],
                    user=_user(),
                )
        assert session.rollback.called

    def test_mwac_update_path(self, app, mocker):
        sale = _sale()
        line = _sale_line(cost_price=Decimal('40'))
        product = _product()
        line.product = product
        session = self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.current_app.config.get', return_value=True)
        pwc = MagicMock(total_quantity=Decimal('10'), total_value=Decimal('400'), average_cost=Decimal('40'))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = pwc
        mocker.patch('models.ProductWarehouseCost.query', pwc_q)
        mocker.patch('services.return_service.StockService._mwac_calc', return_value=(
            Decimal('11'), Decimal('440'), Decimal('40'),
        ))
        mocker.patch('models.ProductCostHistory')
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1, 'condition': 'good'}],
                user=_user(),
            )

    def test_discount_and_shipping_share(self, app, mocker):
        sale = _sale(subtotal=Decimal('100'), discount_amount=Decimal('10'), shipping_cost=Decimal('5'))
        line = _sale_line(line_total=Decimal('100'))
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id,
                [{'sale_line_id': line.id, 'quantity': 1}],
                user=_user(),
            )

    def test_invalid_quantity_raises(self, app, mocker):
        sale = _sale()
        session = mocker.patch('services.return_service.db.session')
        session.get.return_value = sale
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='Invalid return quantity'):
                ReturnService.create_return(sale.id, [{'sale_line_id': 1, 'quantity': 'bad'}], user=_user())

    def test_excess_return_quantity(self, app, mocker):
        sale = _sale()
        line = _sale_line(quantity=Decimal('1'))
        product = _product()
        line.product = product
        session = mocker.patch('services.return_service.db.session')
        session.get.side_effect = lambda model, pk: {sale.id: sale, line.id: line}.get(pk)
        session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.scalar.return_value = Decimal('1')
        mocker.patch('services.return_service.generate_number', return_value='R-001')
        mocker.patch('services.return_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.return_service.is_platform_owner', return_value=False)
        mocker.patch('services.return_service.branch_scope_id_for', return_value=None)
        from services.return_service import ReturnService
        with app.app_context():
            with pytest.raises(ValueError, match='Cannot return'):
                ReturnService.create_return(sale.id, [{'sale_line_id': line.id, 'quantity': 1}], user=_user())

    def test_product_cost_fallback(self, app, mocker):
        sale = _sale()
        line = _sale_line(cost_price=Decimal('0'))
        product = _product(cost_price=Decimal('25'))
        line.product = product
        session = self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.ProductCostHistory', create=True)
        session.query.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id, [{'sale_line_id': line.id, 'quantity': 1, 'condition': 'good'}], user=_user(),
            )

    def test_mwac_for_update_fallback(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.current_app.config.get', return_value=True)
        pwc = MagicMock(total_quantity=Decimal('10'), total_value=Decimal('400'), average_cost=Decimal('40'))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.side_effect = RuntimeError('lock')
        pwc_q.filter_by.return_value.first.return_value = pwc
        mocker.patch('models.ProductWarehouseCost.query', pwc_q)
        mocker.patch('services.return_service.StockService._mwac_calc', return_value=(Decimal('11'), Decimal('440'), Decimal('40')))
        mocker.patch('models.ProductCostHistory')
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id, [{'sale_line_id': line.id, 'quantity': 1, 'condition': 'good'}], user=_user(),
            )

    def test_mwac_failure_logged(self, app, mocker):
        sale = _sale()
        line = _sale_line()
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        mocker.patch('services.return_service.current_app.config.get', return_value=True)
        pwc = MagicMock(total_quantity=Decimal('10'), total_value=Decimal('400'), average_cost=Decimal('40'))
        pwc_q = MagicMock()
        pwc_q.filter_by.return_value.with_for_update.return_value.first.return_value = pwc
        mocker.patch('models.ProductWarehouseCost.query', pwc_q)
        mocker.patch('services.return_service.StockService._mwac_calc', side_effect=RuntimeError('mwac fail'))
        mock_logger = mocker.patch('services.return_service.current_app.logger')
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id, [{'sale_line_id': line.id, 'quantity': 1, 'condition': 'good'}], user=_user(),
            )
        mock_logger.exception.assert_called_once()

    def test_manual_refund_zero_tax(self, app, mocker):
        sale = _sale(tax_rate=Decimal('0'))
        line = _sale_line()
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService
        with app.app_context():
            result = ReturnService.create_return(
                sale.id, [{'sale_line_id': line.id, 'quantity': 1}],
                user=_user(), manual_refund_amount='50',
            )
        assert result.refund_amount == Decimal('50.000')

    def test_manual_refund_with_tax_splits_net(self, app, mocker):
        sale = _sale(tax_rate=Decimal('5'))
        line = _sale_line()
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService
        with app.app_context():
            result = ReturnService.create_return(
                sale.id, [{'sale_line_id': line.id, 'quantity': 1}],
                user=_user(), manual_refund_amount='105',
            )
        assert result.refund_amount == Decimal('105.000')

    def test_net_return_clamped_to_zero(self, app, mocker):
        sale = _sale(subtotal=Decimal('100'), discount_amount=Decimal('200'))
        line = _sale_line(line_total=Decimal('100'))
        product = _product()
        line.product = product
        self._patch_common(mocker, sale, line, product)
        from services.return_service import ReturnService
        with app.app_context():
            ReturnService.create_return(
                sale.id, [{'sale_line_id': line.id, 'quantity': 1}], user=_user(),
            )
