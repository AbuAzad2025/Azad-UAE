import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock


def make_sync_logger_mock(name="logger"):
    """Synchronous logger MagicMock with __name__ for Python 3.14 introspection."""
    logger_mock = MagicMock(name=name)
    logger_mock.__name__ = name
    for method_name in ("debug", "info", "warning", "error", "exception", "critical"):
        method_mock = MagicMock(name=f"{name}.{method_name}")
        method_mock.__name__ = method_name
        setattr(logger_mock, method_name, method_mock)
    return logger_mock


class TestSaleServiceValidations:
    def test_create_sale_rejects_inactive_customer(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = False
        seller = MagicMock()
        seller.is_active = True
        with pytest.raises(ValueError, match='العميل غير صالح'):
            SaleService.create_sale(customer, seller, [])

    def test_create_sale_rejects_inactive_seller(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = False
        with pytest.raises(ValueError, match='البائع غير صالح'):
            SaleService.create_sale(customer, seller, [])

    def test_create_sale_rejects_empty_lines(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        with pytest.raises(ValueError, match='يجب إضافة منتج'):
            SaleService.create_sale(customer, seller, [])

    def test_create_sale_rejects_zero_quantity(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        product = MagicMock()
        product.name = 'Test'
        lines = [{'product': product, 'quantity': 0}]
        with patch('services.sale_service.StockService'):
            with patch('models.Warehouse'):
                with patch('services.sale_service.ensure_warehouse_access'):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with pytest.raises(ValueError, match='الكمية يجب أن تكون أكبر من صفر'):
                                            SaleService.create_sale(customer, seller, lines)

    def test_create_sale_rejects_zero_unit_price(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        customer.customer_type = 'regular'
        seller = MagicMock()
        seller.is_active = True
        product = MagicMock()
        product.name = 'Test'
        product.get_price_for_customer.return_value = Decimal('0')
        lines = [{'product': product, 'quantity': 1}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            with patch('models.Warehouse'):
                with patch('services.sale_service.ensure_warehouse_access'):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with pytest.raises(ValueError, match='السعر يجب أن يكون أكبر من صفر'):
                                            SaleService.create_sale(customer, seller, lines)

    def test_create_sale_rejects_negative_discount(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        with patch('models.Warehouse'):
            with pytest.raises(ValueError, match='الخصم لا يمكن أن تكون سالبة'):
                SaleService.create_sale(customer, seller, [{'product': MagicMock(), 'quantity': 1}], discount_amount=-10)

    def test_create_sale_rejects_negative_shipping(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        with patch('models.Warehouse'):
            with pytest.raises(ValueError, match='الشحن لا يمكن أن تكون سالبة'):
                SaleService.create_sale(customer, seller, [{'product': MagicMock(), 'quantity': 1}], shipping_cost=-10)

    def test_create_sale_rejects_invalid_discount_percent(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        product = MagicMock()
        product.name = 'Test'
        lines = [{'product': product, 'quantity': 1, 'unit_price': 100, 'discount_percent': 150}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            with patch('models.Warehouse'):
                with patch('services.sale_service.ensure_warehouse_access'):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with pytest.raises(ValueError, match='نسبة الخصم يجب أن تكون بين 0 و 100'):
                                            SaleService.create_sale(customer, seller, lines)


class TestSaleServiceCreate:
    def test_create_sale_success(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        customer.id = 1
        customer.customer_type = 'regular'
        customer.tenant_id = 1
        seller = MagicMock()
        seller.is_active = True
        seller.id = 2
        seller.tenant_id = 1
        seller.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test Product'
        product.cost_price = 50
        product.has_serial_number = False
        product.warranty_days = 0
        product.get_price_for_customer.return_value = Decimal('100')
        product.partner_shares = []
        lines = [{'product': product, 'quantity': 2, 'unit_price': 100}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            mock_stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'test')
            with patch('models.Warehouse') as mock_wh:
                wh = MagicMock()
                wh.id = 1
                wh.branch_id = 1
                mock_wh.query.filter_by.return_value = mock_wh.query
                mock_wh.query.first.return_value = wh
                with patch('services.sale_service.ensure_warehouse_access', return_value=wh):
                    with patch('services.sale_service.generate_number', return_value='S-2024-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with patch('services.sale_service.SaleService.fulfill_sale'):
                                            with patch('services.sale_service.SaleLine') as mock_line:
                                                line_instance = MagicMock()
                                                line_instance.line_total = Decimal('200')
                                                line_instance.quantity = 2
                                                line_instance.cost_price = Decimal('50')
                                                line_instance.id = 1
                                                line_instance.product_id = 1
                                                line_instance.calculate_line_total = MagicMock()
                                                mock_line.return_value = line_instance
                                                result = SaleService.create_sale(customer, seller, lines)
                                                assert result is not None

    def test_create_sale_with_discount(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        customer.id = 1
        customer.customer_type = 'regular'
        seller = MagicMock()
        seller.is_active = True
        seller.id = 2
        seller.tenant_id = 1
        seller.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test'
        product.cost_price = 50
        product.has_serial_number = False
        product.warranty_days = 0
        product.get_price_for_customer.return_value = Decimal('100')
        product.partner_shares = []
        lines = [{'product': product, 'quantity': 1, 'unit_price': 100, 'discount_percent': 10}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            mock_stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'test')
            with patch('models.Warehouse') as mock_wh:
                wh = MagicMock()
                wh.id = 1
                wh.branch_id = 1
                mock_wh.query.filter_by.return_value = mock_wh.query
                mock_wh.query.first.return_value = wh
                with patch('services.sale_service.ensure_warehouse_access', return_value=wh):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with patch('services.sale_service.SaleService.fulfill_sale'):
                                            with patch('services.sale_service.SaleLine') as mock_line:
                                                line_instance = MagicMock()
                                                line_instance.line_total = Decimal('90')
                                                line_instance.quantity = 1
                                                line_instance.cost_price = Decimal('50')
                                                line_instance.id = 1
                                                line_instance.product_id = 1
                                                line_instance.calculate_line_total = MagicMock()
                                                mock_line.return_value = line_instance
                                                result = SaleService.create_sale(customer, seller, lines, discount_amount=10)
                                                assert result is not None

    def test_create_sale_with_payment(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        customer.id = 1
        customer.customer_type = 'regular'
        seller = MagicMock()
        seller.is_active = True
        seller.id = 2
        seller.tenant_id = 1
        seller.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test'
        product.cost_price = 50
        product.has_serial_number = False
        product.warranty_days = 0
        product.get_price_for_customer.return_value = Decimal('100')
        product.partner_shares = []
        lines = [{'product': product, 'quantity': 1, 'unit_price': 100}]
        payment_data = {'amount': 100, 'currency': 'AED', 'exchange_rate': 1.0, 'method': 'cash'}
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            mock_stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'test')
            with patch('models.Warehouse') as mock_wh:
                wh = MagicMock()
                wh.id = 1
                wh.branch_id = 1
                mock_wh.query.filter_by.return_value = mock_wh.query
                mock_wh.query.first.return_value = wh
                with patch('services.sale_service.ensure_warehouse_access', return_value=wh):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with patch('services.sale_service.SaleService.fulfill_sale'):
                                            with patch('services.sale_service.SaleLine') as mock_line:
                                                line_instance = MagicMock()
                                                line_instance.line_total = Decimal('100')
                                                line_instance.quantity = 1
                                                line_instance.cost_price = Decimal('50')
                                                line_instance.id = 1
                                                line_instance.product_id = 1
                                                line_instance.calculate_line_total = MagicMock()
                                                mock_line.return_value = line_instance
                                                with patch('services.sale_service.Payment') as mock_pay:
                                                    result = SaleService.create_sale(customer, seller, lines, payment_data=payment_data)
                                                    assert result is not None

    def test_create_sale_serial_number_validation(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        customer.id = 1
        customer.customer_type = 'regular'
        seller = MagicMock()
        seller.is_active = True
        seller.id = 2
        seller.tenant_id = 1
        seller.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test'
        product.cost_price = 50
        product.has_serial_number = True
        product.warranty_days = 0
        product.get_price_for_customer.return_value = Decimal('100')
        product.partner_shares = []
        lines = [{'product': product, 'quantity': 1, 'unit_price': 100, 'serials': ['SN001']}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            mock_stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'test')
            with patch('models.Warehouse') as mock_wh:
                wh = MagicMock()
                wh.id = 1
                wh.branch_id = 1
                mock_wh.query.filter_by.return_value = mock_wh.query
                mock_wh.query.first.return_value = wh
                with patch('services.sale_service.ensure_warehouse_access', return_value=wh):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with patch('services.sale_service.SaleService.fulfill_sale'):
                                            with patch('services.sale_service.SaleLine') as mock_line:
                                                line_instance = MagicMock()
                                                line_instance.line_total = Decimal('100')
                                                line_instance.quantity = 1
                                                line_instance.cost_price = Decimal('50')
                                                line_instance.id = 1
                                                line_instance.product_id = 1
                                                line_instance.calculate_line_total = MagicMock()
                                                mock_line.return_value = line_instance
                                                with patch('models.ProductSerial') as mock_sn:
                                                    sn_obj = MagicMock()
                                                    sn_obj.status = 'available'
                                                    sn_obj.warehouse_id = 1
                                                    mock_sn.query.filter_by.return_value.first.return_value = sn_obj
                                                    with patch('services.sale_service.current_app') as mock_app:
                                                        mock_app.__name__ = "current_app"
                                                        mock_app.logger = make_sync_logger_mock("logger")
                                                        result = SaleService.create_sale(customer, seller, lines)
                                                        assert result is not None

    def test_create_sale_serial_number_mismatch_count(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        product = MagicMock()
        product.name = 'Test'
        product.has_serial_number = True
        lines = [{'product': product, 'quantity': 2, 'unit_price': 100, 'serials': ['SN001']}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            with patch('models.Warehouse'):
                with patch('services.sale_service.ensure_warehouse_access'):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with pytest.raises(ValueError, match='يتطلب'):
                                            SaleService.create_sale(customer, seller, lines)

    def test_create_sale_stock_unavailable(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        product = MagicMock()
        product.name = 'Test'
        lines = [{'product': product, 'quantity': 10, 'unit_price': 100}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (False, 'Stock not available')
            with patch('models.Warehouse'):
                with patch('services.sale_service.ensure_warehouse_access'):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with pytest.raises(ValueError, match='Stock not available'):
                                            SaleService.create_sale(customer, seller, lines)

    def test_create_sale_with_currency_conversion(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        customer.id = 1
        customer.customer_type = 'regular'
        seller = MagicMock()
        seller.is_active = True
        seller.id = 2
        seller.tenant_id = 1
        seller.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test'
        product.cost_price = 50
        product.has_serial_number = False
        product.warranty_days = 0
        product.get_price_for_customer.return_value = Decimal('100')
        product.partner_shares = []
        lines = [{'product': product, 'quantity': 1, 'unit_price': 100}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            mock_stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'test')
            with patch('models.Warehouse') as mock_wh:
                wh = MagicMock()
                wh.id = 1
                wh.branch_id = 1
                mock_wh.query.filter_by.return_value = mock_wh.query
                mock_wh.query.first.return_value = wh
                with patch('services.sale_service.ensure_warehouse_access', return_value=wh):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 3.67}
                            with patch('services.sale_service.db.session.add'):
                                with patch('services.sale_service.db.session.flush'):
                                    with patch('services.sale_service.db.session.commit'):
                                        with patch('services.sale_service.SaleService.fulfill_sale'):
                                            with patch('services.sale_service.SaleLine') as mock_line:
                                                line_instance = MagicMock()
                                                line_instance.line_total = Decimal('100')
                                                line_instance.quantity = 1
                                                line_instance.cost_price = Decimal('50')
                                                line_instance.id = 1
                                                line_instance.product_id = 1
                                                line_instance.calculate_line_total = MagicMock()
                                                mock_line.return_value = line_instance
                                                result = SaleService.create_sale(customer, seller, lines, currency='USD')
                                                assert result is not None


class TestSaleServiceOtherMethods:
    def test_has_inventory_posted_true(self, app):
        from services.sale_service import SaleService
        sale = MagicMock()
        sale.id = 1
        with patch('models.warehouse.StockMovement.query') as mock_q:
            mock_q.filter_by.return_value.first.return_value = MagicMock()
            assert SaleService.has_inventory_posted(sale) is True

    def test_has_inventory_posted_false(self, app):
        from services.sale_service import SaleService
        sale = MagicMock()
        sale.id = 1
        with patch('models.warehouse.StockMovement.query') as mock_q:
            mock_q.filter_by.return_value.first.return_value = None
            assert SaleService.has_inventory_posted(sale) is False

    def test_update_payment_status(self, app):
        from services.sale_service import SaleService
        sale = MagicMock()
        sale.total_amount = Decimal('100')
        sale.paid_amount = Decimal('100')
        sale.balance_due = Decimal('0')
        sale.payments = [MagicMock()]
        sale.payments[0].payment_confirmed = True
        sale.payments[0].amount_aed = Decimal('100')
        sale.returns = []
        def _mock_recalc():
            sale.payment_status = 'paid'
        sale.recalculate_payment_status = _mock_recalc
        with patch('services.sale_service.db.session') as mock_db:
            mock_db.add = MagicMock()
            mock_db.commit = MagicMock()
            SaleService.update_payment_status(sale)
            assert sale.payment_status == 'paid'
