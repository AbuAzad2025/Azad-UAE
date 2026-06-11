import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestPurchaseReturnValidations:
    def test_return_cancelled_purchase(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'cancelled'
        user = MagicMock()
        with pytest.raises(ValueError, match='ملغاة'):
            PurchaseService.create_purchase_return(purchase, user, [])

    def test_return_empty_lines(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'confirmed'
        user = MagicMock()
        with patch('services.purchase_service.generate_number') as mock_gn:
            mock_gn.return_value = 'PR-001'
            with pytest.raises(ValueError, match='يجب إرجاع منتج'):
                PurchaseService.create_purchase_return(purchase, user, [])

    def test_return_success_no_tax(self, app):
        from services.purchase_service import PurchaseService
        purchase = MagicMock()
        purchase.status = 'confirmed'
        purchase.id = 1
        purchase.tenant_id = 1
        purchase.warehouse_id = 1
        purchase.branch_id = 1
        purchase.currency = 'AED'
        purchase.exchange_rate = Decimal('1')
        purchase.purchase_number = 'P-001'
        purchase.subtotal = Decimal('100')
        purchase.tax_amount = None
        purchase.supplier_id = 1
        purchase.supplier = MagicMock()
        purchase.supplier.total_purchases_aed = Decimal('1000')
        purchase.lines = []
        user = MagicMock()
        user.id = 1
        lines_data = [{'purchase_line_id': 1, 'product_id': 1, 'quantity': 2, 'unit_cost': 10}]
        with patch('services.purchase_service.generate_number') as mock_gn:
            mock_gn.return_value = 'PR-001'
            with patch('services.purchase_service.db') as mock_db:
                mock_db.session.add = MagicMock()
                mock_db.session.flush = MagicMock()
                mock_db.session.commit = MagicMock()
                mock_db.session.rollback = MagicMock()
                with patch('services.purchase_service.StockService') as mock_ss:
                    with patch('services.purchase_service.post_or_fail') as mock_post:
                        with patch('services.purchase_service.GLService') as mock_gl:
                            with patch('services.purchase_service.LoggingCore') as mock_log:
                                from models.purchase_return import PurchaseReturn
                                result = PurchaseService.create_purchase_return(purchase, user, lines_data)
                                assert result is not None
                                assert isinstance(result, PurchaseReturn)
                                assert mock_ss.remove_stock.called
                                assert mock_post.called
