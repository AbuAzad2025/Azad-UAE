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
                                    patch('services.purchase_service.db.session.get', return_value=product).start()
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
                                    patch('services.purchase_service.db.session.get', return_value=product).start()
                                    with patch('services.purchase_service.post_or_fail', return_value=None):
                                        with patch('models.product_serial.ProductSerial') as mock_sn:
                                            mock_sn.query.filter_by.return_value.first.return_value = None
                                            mock_sn.query.filter.return_value.count.return_value = 0
                                            result = PurchaseService.create_purchase(
                                                user,
                                                {'supplier_name': 'Test Supplier'},
                                                lines,
                                                warehouse_id=1,
                                                currency='AED'
                                            )
        assert result is not None


class TestPurchaseServiceTenantIsolation:
    """Tests for tenant isolation in purchase creation."""

    def test_create_purchase_rejects_foreign_supplier(self, app):
        """Warehouse tenant A + supplier tenant B -> reject before persistence."""
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1

        # Warehouse belongs to tenant 1
        warehouse = MagicMock()
        warehouse.id = 1
        warehouse.branch_id = 1
        warehouse.tenant_id = 1

        # Supplier belongs to tenant 2 (foreign)
        foreign_supplier = MagicMock()
        foreign_supplier.id = 99
        foreign_supplier.name = 'Foreign Supplier'
        foreign_supplier.tenant_id = 2
        foreign_supplier.phone = '0500000000'
        foreign_supplier.email = 'foreign@example.com'

        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            mock_wh.return_value = warehouse
            with patch('services.purchase_service.Supplier') as mock_supplier_class:
                # Supplier.query.filter_by(id=99, tenant_id=1).first() returns None
                mock_supplier_class.query.filter_by.return_value.first.return_value = None

                with pytest.raises(ValueError, match='المورد المحدد غير موجود أو لا ينتمي لنفس الشركة'):
                    PurchaseService.create_purchase(
                        user,
                        {'supplier_id': 99},
                        [{'product_id': 1, 'quantity': 5, 'unit_cost': 20}],
                        warehouse_id=1,
                        currency='AED'
                    )

    def test_create_purchase_succeeds_same_tenant_supplier(self, app):
        """Warehouse tenant A + supplier tenant A -> success."""
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1

        warehouse = MagicMock()
        warehouse.id = 1
        warehouse.branch_id = 1
        warehouse.tenant_id = 1

        supplier = MagicMock()
        supplier.id = 2
        supplier.name = 'Same Tenant Supplier'
        supplier.tenant_id = 1
        supplier.phone = '0500000000'
        supplier.email = 'supplier@example.com'

        product = MagicMock()
        product.id = 1
        product.name = 'Test Product'
        product.has_serial_number = False
        product.warranty_days = 0

        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            mock_wh.return_value = warehouse
            with patch('services.purchase_service.Supplier') as mock_supplier_class:
                mock_supplier_class.query.filter_by.return_value.first.return_value = supplier
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
                                    line_instance.line_total = 100
                                    mock_line.return_value = line_instance
                                    with patch('services.purchase_service.Product') as mock_product_class:
                                        patch('services.purchase_service.db.session.get', return_value=product).start()
                                        with patch('services.purchase_service.post_or_fail', return_value=None):
                                            result = PurchaseService.create_purchase(
                                                user,
                                                {'supplier_id': 2},
                                                [{'product_id': 1, 'quantity': 5, 'unit_cost': 20}],
                                                warehouse_id=1,
                                                currency='AED'
                                            )
                                            assert result is not None

    def test_create_purchase_manual_supplier_name_unchanged(self, app):
        """No supplier_id, valid supplier_name, valid warehouse -> success (existing behavior)."""
        from services.purchase_service import PurchaseService
        user = MagicMock()
        user.id = 1
        user.tenant_id = 1
        user.branch_id = 1

        warehouse = MagicMock()
        warehouse.id = 1
        warehouse.branch_id = 1
        warehouse.tenant_id = 1

        product = MagicMock()
        product.id = 1
        product.name = 'Test Product'
        product.has_serial_number = False
        product.warranty_days = 0

        with patch('services.purchase_service.ensure_warehouse_access') as mock_wh:
            mock_wh.return_value = warehouse
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
                                line_instance.line_total = 100
                                mock_line.return_value = line_instance
                                with patch('services.purchase_service.Product') as mock_product_class:
                                    patch('services.purchase_service.db.session.get', return_value=product).start()
                                    with patch('services.purchase_service.post_or_fail', return_value=None):
                                        result = PurchaseService.create_purchase(
                                            user,
                                            {'supplier_name': 'Manual Supplier Name'},
                                            [{'product_id': 1, 'quantity': 5, 'unit_cost': 20}],
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
                        with patch('services.purchase_service.db.session') as mock_db:
                            mock_db.add = MagicMock()
                            mock_db.flush = MagicMock()
                            with patch('services.purchase_service.PurchaseLine') as mock_line:
                                line_instance = MagicMock()
                                line_instance.line_total = Decimal('100')
                                line_instance.id = 1
                                mock_line.return_value = line_instance
                                with patch('services.purchase_service.db.session.get', return_value=product):
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
                                    patch('services.purchase_service.db.session.get', return_value=product).start()
                                    with patch('services.purchase_service.post_or_fail', return_value=None):
                                        result = PurchaseService.create_purchase(
                                            user,
                                            {'supplier_name': 'Test'},
                                            lines,
                                            warehouse_id=1,
                                            currency='USD'
                                        )
                                        assert result is not None