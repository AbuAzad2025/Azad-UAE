import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestPurchaseCancelValidations:
    def test_cancel_already_cancelled(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'cancelled'
        with pytest.raises(ValueError, match='ملغاة بالفعل'):
            PurchaseService.cancel_purchase(purchase)

    def test_cancel_with_confirmed_payments(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'confirmed'
        purchase.id = 1
        purchase.purchase_number = 'P-001'
        purchase.supplier = MagicMock()
        purchase.amount_aed = Decimal('1000')
        with patch('services.purchase_service.db') as mock_db:
            mock_filter = MagicMock()
            mock_filter.scalar.return_value = Decimal('500')
            mock_db.session.query.return_value.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            with pytest.raises(ValueError, match='مدفوعات مؤكدة'):
                PurchaseService.cancel_purchase(purchase)

    def test_cancel_no_payments_reverses_supplier(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'confirmed'
        purchase.id = 1
        purchase.amount_aed = Decimal('1000')
        purchase.purchase_number = 'P-001'
        supplier = MagicMock()
        supplier.total_purchases_aed = Decimal('2000')
        purchase.supplier = supplier
        with patch('services.purchase_service.db') as mock_db:
            mock_filter = MagicMock()
            mock_filter.scalar.return_value = Decimal('0')
            mock_db.session.query.return_value.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            mock_db.session.commit = MagicMock()
            mock_db.session.rollback = MagicMock()
            with patch('models.warehouse.StockMovement') as mock_sm:
                mock_sm.query.filter_by.return_value.first.return_value = None
                with patch('services.purchase_service.StockService') as mock_ss:
                    with patch('services.purchase_service.GLService') as mock_gl:
                        with patch('services.purchase_service.LoggingCore'):
                            PurchaseService.cancel_purchase(purchase)
                            mock_ss.reverse_purchase.assert_not_called()
                            mock_gl.reverse_entry.assert_not_called()
                            assert supplier.total_purchases_aed == Decimal('1000')
                            assert purchase.status == 'cancelled'

    def test_cancel_with_stock_reverses_gl(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'confirmed'
        purchase.id = 1
        purchase.amount_aed = Decimal('500')
        purchase.purchase_number = 'P-002'
        supplier = MagicMock()
        supplier.total_purchases_aed = Decimal('500')
        purchase.supplier = supplier
        with patch('services.purchase_service.db') as mock_db:
            mock_filter = MagicMock()
            mock_filter.scalar.return_value = Decimal('0')
            mock_db.session.query.return_value.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            mock_db.session.commit = MagicMock()
            mock_db.session.rollback = MagicMock()
            with patch('models.warehouse.StockMovement') as mock_sm:
                mock_sm.query.filter_by.return_value.first.return_value = MagicMock()
                with patch('services.purchase_service.StockService') as mock_ss:
                    with patch('services.purchase_service.GLService') as mock_gl:
                        with patch('services.purchase_service.LoggingCore'):
                            PurchaseService.cancel_purchase(purchase)
                            mock_ss.reverse_purchase.assert_called_once_with(purchase)
                            mock_gl.reverse_entry.assert_called_once()
                            assert purchase.status == 'cancelled'

    def test_cancel_no_supplier_handles_gracefully(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'confirmed'
        purchase.id = 1
        purchase.amount_aed = Decimal('1000')
        purchase.purchase_number = 'P-003'
        purchase.supplier = None
        with patch('services.purchase_service.db') as mock_db:
            mock_filter = MagicMock()
            mock_filter.scalar.return_value = Decimal('0')
            mock_db.session.query.return_value.filter.return_value = mock_filter
            mock_filter.filter.return_value = mock_filter
            mock_db.session.commit = MagicMock()
            mock_db.session.rollback = MagicMock()
            with patch('models.warehouse.StockMovement') as mock_sm:
                mock_sm.query.filter_by.return_value.first.return_value = None
                with patch('services.purchase_service.StockService') as mock_ss:
                    with patch('services.purchase_service.GLService'):
                        with patch('services.purchase_service.LoggingCore'):
                            PurchaseService.cancel_purchase(purchase)
                            assert purchase.status == 'cancelled'
