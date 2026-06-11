import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestPurchaseServiceValidations:
    def test_create_purchase_rejects_missing_warehouse(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        with pytest.raises(ValueError, match='يجب اختيار المستودع'):
            PurchaseService.create_purchase(user, {'supplier_name': 'Test'}, [])

    def test_create_purchase_rejects_missing_supplier_name(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        with patch('services.purchase_service.ensure_warehouse_access'):
            with pytest.raises(ValueError, match='يجب إدخال اسم المورد'):
                PurchaseService.create_purchase(user, {}, [], warehouse_id=1)

    def test_create_purchase_rejects_empty_lines(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.branch_id = 1
        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            wh = MagicMock()
            wh.id = 1
            wh.branch_id = 1
            wh.tenant_id = 1
            mock_wh.return_value = wh
            with pytest.raises(ValueError, match='يجب إضافة منتج'):
                PurchaseService.create_purchase(user, {'supplier_name': 'Test'}, [], warehouse_id=1)

    def test_create_purchase_rejects_zero_quantity(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.branch_id = 1
        product = MagicMock()
        product.name = 'Test'
        lines = [{'product_id': 1, 'quantity': 0, 'unit_cost': 10}]
        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            wh = MagicMock()
            wh.id = 1
            wh.branch_id = 1
            wh.tenant_id = 1
            mock_wh.return_value = wh
            with patch('services.purchase_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                with patch('services.purchase_service.validate_currency_code', return_value='AED'):
                    with patch('services.purchase_service.generate_number', return_value='P-001'):
                        with pytest.raises(ValueError, match='يجب إضافة منتج'):
                            PurchaseService.create_purchase(user, {'supplier_name': 'Test'}, lines, warehouse_id=1)


class TestPurchaseServiceCreate:
    def test_create_purchase_success(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test Product'
        product.has_serial_number = False
        product.warranty_days = 0
        lines = [{'product_id': 1, 'quantity': 5, 'unit_cost': 20}]
        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            wh = MagicMock()
            wh.id = 1
            wh.branch_id = 1
            wh.tenant_id = 1
            mock_wh.return_value = wh
            with patch('services.purchase_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                with patch('services.purchase_service.validate_currency_code', return_value='AED'):
                    with patch('services.purchase_service.generate_number', return_value='P-2024-001'):
                        with patch('services.purchase_service.db.session') as mock_db:
                            mock_db.add = MagicMock()
                            mock_db.flush = MagicMock()
                            mock_db.commit = MagicMock()
                            with patch('services.purchase_service.PurchaseLine') as mock_line:
                                line_instance = MagicMock()
                                line_instance.line_total = Decimal('100')
                                mock_line.return_value = line_instance
                                with patch('services.purchase_service.Product') as mock_product_class:
                                    mock_product_class.query.get.return_value = product
                                    with patch('services.purchase_service.post_or_fail', return_value=None):
                                        result = PurchaseService.create_purchase(
                                        user,
                                        {'supplier_name': 'Test Supplier'},
                                        lines,
                                        warehouse_id=1,
                                        currency='AED'
                                    )
                                    assert result is not None

    def test_create_purchase_with_serial_numbers(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test Product'
        product.has_serial_number = True
        product.warranty_days = 0
        lines = [{'product_id': 1, 'quantity': 2, 'unit_cost': 50, 'serials': ['SN001', 'SN002']}]
        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            wh = MagicMock()
            wh.id = 1
            wh.branch_id = 1
            wh.tenant_id = 1
            mock_wh.return_value = wh
            with patch('services.purchase_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                with patch('services.purchase_service.validate_currency_code', return_value='AED'):
                    with patch('services.purchase_service.generate_number', return_value='P-001'):
                        with patch('services.purchase_service.db.session') as mock_db:
                            mock_db.add = MagicMock()
                            mock_db.flush = MagicMock()
                            mock_db.commit = MagicMock()
                            with patch('services.purchase_service.PurchaseLine') as mock_line:
                                line_instance = MagicMock()
                                line_instance.line_total = Decimal('100')
                                mock_line.return_value = line_instance
                                with patch('services.purchase_service.Product') as mock_product_class:
                                    mock_product_class.query.get.return_value = product
                                    with patch('services.purchase_service.post_or_fail', return_value=None):
                                        with patch('models.ProductSerial') as mock_sn:
                                            mock_sn.query.filter_by.return_value.first.return_value = None
                                            result = PurchaseService.create_purchase(
                                                user,
                                                {'supplier_name': 'Test Supplier'},
                                                lines,
                                                warehouse_id=1,
                                                currency='AED'
                                            )
                                            assert result is not None

    def test_create_purchase_serial_count_mismatch(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test'
        product.has_serial_number = True
        product.warranty_days = 0
        lines = [{'product_id': 1, 'quantity': 2, 'unit_cost': 50, 'serials': ['SN001']}]
        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            wh = MagicMock()
            wh.id = 1
            wh.branch_id = 1
            wh.tenant_id = 1
            mock_wh.return_value = wh
            with patch('services.purchase_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 1.0}
                with patch('services.purchase_service.validate_currency_code', return_value='AED'):
                    with patch('services.purchase_service.generate_number', return_value='P-001'):
                        with patch('services.purchase_service.Product') as mock_product_class:
                            mock_product_class.query.get.return_value = product
                            with pytest.raises(ValueError, match='يتطلب'):
                                PurchaseService.create_purchase(
                                    user,
                                    {'supplier_name': 'Test'},
                                    lines,
                                    warehouse_id=1,
                                    currency='AED'
                                )

    def test_create_purchase_with_currency_conversion(self, app):
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1
        product = MagicMock()
        product.id = 1
        product.name = 'Test'
        product.has_serial_number = False
        product.warranty_days = 0
        lines = [{'product_id': 1, 'quantity': 1, 'unit_cost': 100}]
        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            wh = MagicMock()
            wh.id = 1
            wh.branch_id = 1
            wh.tenant_id = 1
            mock_wh.return_value = wh
            with patch('services.purchase_service.ExchangeRateService') as mock_ex:
                mock_ex.resolve_exchange_rate_for_transaction.return_value = {'rate': 3.67}
                with patch('services.purchase_service.validate_currency_code', return_value='USD'):
                    with patch('services.purchase_service.generate_number', return_value='P-001'):
                        with patch('services.purchase_service.db.session') as mock_db:
                            mock_db.add = MagicMock()
                            mock_db.flush = MagicMock()
                            mock_db.commit = MagicMock()
                            with patch('services.purchase_service.PurchaseLine') as mock_line:
                                line_instance = MagicMock()
                                line_instance.line_total = Decimal('100')
                                mock_line.return_value = line_instance
                                with patch('services.purchase_service.Product') as mock_product_class:
                                    mock_product_class.query.get.return_value = product
                                    with patch('services.purchase_service.post_or_fail', return_value=None):
                                        result = PurchaseService.create_purchase(
                                            user,
                                            {'supplier_name': 'Test'},
                                            lines,
                                            warehouse_id=1,
                                            currency='USD'
                                        )
                                        assert result is not None
