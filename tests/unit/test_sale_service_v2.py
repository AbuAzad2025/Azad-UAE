import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


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

    def test_create_sale_rejects_negative_discount(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        with patch('models.Warehouse.query'):
            with pytest.raises(ValueError, match='الخصم'):
                SaleService.create_sale(customer, seller, [{'product': MagicMock(), 'quantity': 1}], discount_amount=-10)

    def test_create_sale_rejects_negative_shipping(self, app):
        from services.sale_service import SaleService
        customer = MagicMock()
        customer.is_active = True
        seller = MagicMock()
        seller.is_active = True
        with patch('models.Warehouse.query'):
            with pytest.raises(ValueError, match='الشحن'):
                SaleService.create_sale(customer, seller, [{'product': MagicMock(), 'quantity': 1}], shipping_cost=-10)


class TestSaleServiceCreate:
    def _mock_warehouse(self):
        wh = MagicMock()
        wh.id = 1
        wh.branch_id = 1
        return wh

    def _setup_mocks(self):
        wh = self._mock_warehouse()
        return patch('models.Warehouse.query'), patch('services.sale_service.ensure_warehouse_access', return_value=wh), patch('services.sale_service.generate_number', return_value='S-001'), patch('services.sale_service.ExchangeRateService')

    def test_create_sale_success(self, app):
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
        lines = [{'product': product, 'quantity': 2, 'unit_price': 100}]
        with patch('services.sale_service.StockService') as mock_stock:
            mock_stock.check_availability_in_warehouse.return_value = (True, '')
            mock_stock._resolve_cogs_unit_cost.return_value = (Decimal('50'), 'test')
            with self._setup_mocks()[0] as mock_wh_query:
                wh = self._mock_warehouse()
                mock_wh_query.filter_by.return_value.filter_by.return_value.first.return_value = wh
                with self._setup_mocks()[1]:
                    with self._setup_mocks()[2]:
                        with self._setup_mocks()[3] as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session') as mock_db:
                                mock_db.add = MagicMock()
                                mock_db.flush = MagicMock()
                                mock_db.commit = MagicMock()
                                with patch('services.sale_service.SaleLine') as mock_line:
                                    line_instance = MagicMock()
                                    line_instance.line_total = Decimal('200')
                                    line_instance.quantity = 2
                                    line_instance.cost_price = Decimal('50')
                                    line_instance.id = 1
                                    line_instance.product_id = 1
                                    line_instance.calculate_line_total = MagicMock()
                                    mock_line.return_value = line_instance
                                    with patch('services.sale_service.validate_currency_code', return_value='AED'):
                                        with patch.object(SaleService, 'fulfill_sale', return_value=None):
                                            result = SaleService.create_sale(customer, seller, lines, currency='AED')
                                            assert result is not None

    def test_create_sale_with_serial_numbers(self, app):
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
            with patch('models.Warehouse.query') as mock_wh_query:
                wh = self._mock_warehouse()
                mock_wh_query.filter_by.return_value.filter_by.return_value.first.return_value = wh
                with patch('services.sale_service.ensure_warehouse_access', return_value=wh):
                    with patch('services.sale_service.generate_number', return_value='S-001'):
                        with patch('services.sale_service.ExchangeRateService') as mock_ex:
                            mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                            with patch('services.sale_service.db.session') as mock_db:
                                mock_db.add = MagicMock()
                                mock_db.flush = MagicMock()
                                mock_db.commit = MagicMock()
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
                                        sn_obj.warehouse_id = None
                                        mock_sn.query.filter_by.return_value.first.return_value = sn_obj
                                        with patch('services.sale_service.current_app'):
                                            with patch('services.sale_service.validate_currency_code', return_value='AED'):
                                                with patch.object(SaleService, 'fulfill_sale', return_value=None):
                                                    result = SaleService.create_sale(customer, seller, lines, currency='AED')
                                                    assert result is not None


class TestSaleServiceHelpers:
    def test_has_inventory_posted_true(self, app):
        from services.sale_service import SaleService
        sale = MagicMock()
        sale.id = 1
        with patch('models.warehouse.StockMovement') as mock_sm:
            mock_sm.query.filter_by.return_value.first.return_value = MagicMock()
            assert SaleService.has_inventory_posted(sale) is True

    def test_has_inventory_posted_false(self, app):
        from services.sale_service import SaleService
        sale = MagicMock()
        sale.id = 2
        with patch('models.warehouse.StockMovement') as mock_sm:
            mock_sm.query.filter_by.return_value.first.return_value = None
            assert SaleService.has_inventory_posted(sale) is False
