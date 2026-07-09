"""Warranty service — expiration boundaries, claims, serial lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestCreateClaim:
    """create_claim — warranty window from sale date + product days."""

    def test_sets_end_date_from_product_warranty_days(self, app, mocker):
        sale_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        product = MagicMock(id=7, warranty_days=365)
        sale = MagicMock(id=100, tenant_id=1, sale_date=sale_date)
        line = MagicMock(product=product, sale=sale)
        mock_session = mocker.patch('services.warranty_service.db.session')

        from services.warranty_service import WarrantyService

        with app.app_context():
            claim = WarrantyService.create_claim(line, 'repair', 'Screen defect')

        assert claim.product_id == 7
        assert claim.warranty_start_date == sale_date
        assert claim.warranty_end_date == sale_date + timedelta(days=365)
        mock_session.add.assert_called_once()

    def test_zero_warranty_days_same_day_expiry(self, app, mocker):
        sale_date = datetime(2025, 6, 1, tzinfo=timezone.utc)
        product = MagicMock(id=1, warranty_days=0)
        sale = MagicMock(id=2, tenant_id=1, sale_date=sale_date)
        line = MagicMock(product=product, sale=sale)
        mocker.patch('services.warranty_service.db.session')

        from services.warranty_service import WarrantyService

        with app.app_context():
            claim = WarrantyService.create_claim(line, 'return', 'DOA')
        assert claim.warranty_end_date == sale_date


class TestWarrantyQueries:
    """get_active_warranties / get_expiring_warranties — boundary filters."""

    def test_active_warranties_tenant_scoped(self, mocker):
        from models.warranty_claim import WarrantyClaim

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [MagicMock()]
        mocker.patch.object(
            WarrantyClaim, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )

        from services.warranty_service import WarrantyService

        rows = WarrantyService.get_active_warranties(tenant_id=5)
        assert len(rows) == 1
        mock_q.filter.assert_called_once()

    def test_expiring_within_window_excludes_resolved(self, mocker):
        from models.warranty_claim import WarrantyClaim

        expiring = MagicMock(status='open')
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = [expiring]
        mocker.patch.object(
            WarrantyClaim, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )

        from services.warranty_service import WarrantyService

        rows = WarrantyService.get_expiring_warranties(days=30)
        assert rows[0].status == 'open'
        assert mock_q.filter.call_count == 1

    def test_expiring_boundary_days_parameter(self, mocker):
        from models.warranty_claim import WarrantyClaim

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = []
        mocker.patch.object(
            WarrantyClaim, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )

        from services.warranty_service import WarrantyService

        WarrantyService.get_expiring_warranties(days=7)
        mock_q.filter.assert_called_once()
