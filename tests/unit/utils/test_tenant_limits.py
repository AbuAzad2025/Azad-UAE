from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from utils.tenant_limits import (
    TenantLimitError,
    check_feature_enabled,
    check_limit,
    check_monthly_limit,
    check_users_limit,
    enforce_feature,
)


class _Col:
    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self


class TestTenantLimits:
    def test_tenant_limit_error_message(self):
        err = TenantLimitError('users', 5, 5)
        assert err.resource == 'users'
        assert err.limit == 5
        assert '5' in str(err)

    def test_check_limit_no_tenant_skips(self):
        with patch('utils.tenant_limits._active_tenant', return_value=None):
            check_limit('users', model=MagicMock())

    def test_check_limit_unlimited(self):
        tenant = MagicMock(id=1, max_users=0)
        with patch('utils.tenant_limits._active_tenant', return_value=tenant), \
             patch('extensions.db') as mock_db:
            check_limit('users', model=MagicMock())
            mock_db.session.query.assert_not_called()

    def test_check_limit_raises_at_cap(self):
        tenant = MagicMock(id=1, max_users=2)
        model = type('User', (), {'tenant_id': _Col()})
        with patch('utils.tenant_limits._active_tenant', return_value=tenant), \
             patch('utils.tenant_limits.db') as mock_db:
            mock_db.session.query.return_value.filter.return_value.count.return_value = 2
            with pytest.raises(TenantLimitError):
                check_limit('users', model=model)

    def test_check_limit_disabled_feature(self):
        tenant = MagicMock(id=1, max_users=0)
        model = type('User', (), {'tenant_id': _Col()})
        with patch('utils.tenant_limits._active_tenant', return_value=tenant):
            with pytest.raises(TenantLimitError):
                check_limit('users', model=model, error_if_disabled=True)

    def test_check_monthly_limit_raises(self):
        tenant = MagicMock(id=1, max_sales_per_month=1)
        model = type('Sale', (), {'tenant_id': _Col(), 'sale_date': _Col()})
        with patch('utils.tenant_limits._active_tenant', return_value=tenant), \
             patch('utils.tenant_limits._month_start', return_value=datetime(2025, 1, 1, tzinfo=timezone.utc)), \
             patch('utils.tenant_limits.db') as mock_db:
            mock_db.session.query.return_value.filter.return_value.count.return_value = 1
            with pytest.raises(TenantLimitError):
                check_monthly_limit('sales', model=model, date_field='sale_date')

    def test_check_feature_enabled_no_tenant(self):
        with patch('utils.tenant_limits._active_tenant', return_value=None):
            assert check_feature_enabled('enable_pos') is True

    def test_enforce_feature_disabled(self):
        tenant = MagicMock(enable_pos=False)
        with patch('utils.tenant_limits._active_tenant', return_value=tenant):
            with pytest.raises(TenantLimitError):
                enforce_feature('enable_pos', 'نقطة البيع')

    def test_check_users_limit_delegates(self):
        with patch('utils.tenant_limits.check_limit') as chk:
            check_users_limit()
            chk.assert_called_once()

    def test_active_tenant_exception_returns_none(self):
        with patch('utils.tenant_limits.get_active_tenant_id', side_effect=RuntimeError('fail')), \
             patch('utils.tenant_limits.current_user', MagicMock()):
            from utils.tenant_limits import _active_tenant
            assert _active_tenant() is None

    def test_check_limit_no_limit_attr(self):
        tenant = MagicMock(spec=['id'])
        tenant.id = 1
        with patch('utils.tenant_limits._active_tenant', return_value=tenant):
            check_limit('users', model=MagicMock())

    def test_check_monthly_no_limit(self):
        tenant = MagicMock(id=1, max_sales_per_month=None)
        with patch('utils.tenant_limits._active_tenant', return_value=tenant):
            check_monthly_limit('sales', model=MagicMock(), date_field='sale_date')

    def test_check_feature_enabled_for_tenant(self):
        tenant = MagicMock(enable_pos=True)
        with patch('utils.tenant_limits._active_tenant', return_value=tenant):
            assert check_feature_enabled('enable_pos') is True

    def test_enforce_feature_no_tenant_skips(self):
        with patch('utils.tenant_limits._active_tenant', return_value=None):
            enforce_feature('enable_pos', 'POS')

    def test_convenience_limits(self):
        from utils.tenant_limits import (
            check_branches_limit,
            check_customers_limit,
            check_invoices_monthly_limit,
            check_products_limit,
            check_sales_monthly_limit,
            check_suppliers_limit,
            check_warehouses_limit,
        )
        with patch('utils.tenant_limits.check_limit') as chk, \
             patch('utils.tenant_limits.check_monthly_limit') as mchk:
            check_branches_limit()
            check_warehouses_limit()
            check_products_limit()
            check_customers_limit()
            check_suppliers_limit()
            check_sales_monthly_limit()
            check_invoices_monthly_limit()
        assert chk.call_count == 5
        assert mchk.call_count == 2

    def test_active_tenant_returns_model(self):
        tenant = MagicMock(id=3)
        with patch('utils.tenant_limits.get_active_tenant_id', return_value=3), \
             patch('utils.tenant_limits.current_user', MagicMock()), \
             patch('utils.tenant_limits.db') as mock_db:
            mock_db.session.get.return_value = tenant
            from utils.tenant_limits import _active_tenant
            assert _active_tenant() is tenant

    def test_check_limit_with_extra_filter(self):
        tenant = MagicMock(id=1, max_users=10)
        model = type('User', (), {'tenant_id': _Col()})
        with patch('utils.tenant_limits._active_tenant', return_value=tenant), \
             patch('utils.tenant_limits.db') as mock_db:
            chain = mock_db.session.query.return_value.filter.return_value
            chain.count.return_value = 1
            check_limit('users', model=model, extra_filter=lambda q: q)
            chain.count.assert_called_once()

    def test_check_monthly_with_extra_filter(self):
        tenant = MagicMock(id=1, max_sales_per_month=100)
        model = type('Sale', (), {'tenant_id': _Col(), 'sale_date': _Col()})
        with patch('utils.tenant_limits._active_tenant', return_value=tenant), \
             patch('utils.tenant_limits._month_start', return_value=datetime(2025, 1, 1, tzinfo=timezone.utc)), \
             patch('utils.tenant_limits.db') as mock_db:
            chain = mock_db.session.query.return_value.filter.return_value
            chain.count.return_value = 0
            check_monthly_limit('sales', model=model, date_field='sale_date', extra_filter=lambda q: q)
            chain.count.assert_called_once()

    def test_month_start_helper(self):
        from utils.tenant_limits import _month_start

        start = _month_start()
        assert start.day == 1
        assert start.hour == 0

    def test_check_monthly_no_tenant_skips(self):
        with patch('utils.tenant_limits._active_tenant', return_value=None):
            check_monthly_limit('sales', model=MagicMock(), date_field='sale_date')

    def test_check_monthly_unlimited(self):
        tenant = MagicMock(id=1, max_sales_per_month=0)
        with patch('utils.tenant_limits._active_tenant', return_value=tenant):
            check_monthly_limit('sales', model=MagicMock(), date_field='sale_date')
