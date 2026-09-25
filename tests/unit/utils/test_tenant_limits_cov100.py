"""Additional coverage for utils/tenant_limits.py - targeting 100% coverage."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from utils.tenant_limits import (
    TenantLimitError,
    check_feature_enabled,
    check_limit,
    check_monthly_limit,
    enforce_feature,
)


class _Col:
    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self


class TestTenantLimitErrorCoverage:
    """Tests specifically for TenantLimitError uncovered lines."""

    def test_tenant_limit_error_whatsapp_link_generation(self, app):
        """Test lines 31-52: wa_upgrade_link generation with app config."""
        from utils.tenant_limits import TenantLimitError

        TenantLimitError.wa_upgrade_link = ""
        with app.test_request_context("/"):
            app.config["DEVELOPER_WHATSAPP"] = " 971500000000 "
            err = TenantLimitError("users", 5, 10)
            assert "wa.me/971500000000" in str(err)
            assert TenantLimitError.wa_upgrade_link == "https://wa.me/971500000000"

    def test_tenant_limit_error_link_exception_path(self, monkeypatch):
        """Test lines 46-47: exception during link generation."""
        import flask

        from utils.tenant_limits import TenantLimitError

        TenantLimitError.wa_upgrade_link = ""
        monkeypatch.setattr("utils.tenant_limits.db", MagicMock())
        monkeypatch.setattr(flask, "current_app", MagicMock(side_effect=RuntimeError("boom")))
        err = TenantLimitError("users", 1, 2)
        assert "users" in str(err)

    def test_tenant_limit_error_ar_message(self, app):
        """Test Arabic message in TenantLimitError."""
        with app.test_request_context("/"):
            err = TenantLimitError("users", 5, 10)
            assert "لقد تجاوزت الحد المسموح" in str(err)

    def test_tenant_limit_error_ar_message_ar_locale(self, app):
        """Test Arabic message in Arabic locale."""
        with app.test_request_context("/"):
            err = TenantLimitError("users", 5, 10)
            assert "لقد تجاوزت الحد المسموح" in str(err)


class TestActiveTenantCoverage:
    """Tests for _active_tenant uncovered lines."""

    def test_active_tenant_exception_returns_none(self, app):
        """Test lines 57-64: exception handling in _active_tenant."""
        with app.test_request_context("/"):
            with patch("utils.tenant_limits.get_active_tenant_id", side_effect=RuntimeError("boom")):
                from utils.tenant_limits import _active_tenant

                assert _active_tenant() is None

    def test_active_tenant_no_user(self, app):
        """Test _active_tenant when current_user is not authenticated."""
        from utils.tenant_limits import _active_tenant

        with patch("utils.tenant_limits.current_user", MagicMock(is_authenticated=False)):
            with app.test_request_context("/"):
                assert _active_tenant() is None

    def test_active_tenant_no_user_object(self, app):
        """Test _active_tenant when current_user returns None."""
        from utils.tenant_limits import _active_tenant

        with patch("utils.tenant_limits.current_user", None):
            with app.test_request_context("/"):
                assert _active_tenant() is None


class TestMonthStartCoverage:
    """Test _month_start function."""

    def test_month_start_returns_first_day(self):
        from utils.tenant_limits import _month_start

        start = _month_start()
        assert start.day == 1
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
        assert start.microsecond == 0
        assert start.tzinfo == UTC


class TestCheckLimitCoverage:
    """Tests for check_limit uncovered branches."""

    def test_check_limit_no_limit_attr(self, app):
        """Test line 93-95: limit_attr doesn't exist on tenant."""
        tenant = MagicMock(spec=["id"])
        tenant.id = 1
        # No max_users attribute
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_limit("users", model=MagicMock())
        # Should return early without error

    def test_check_limit_zero_unlimited(self, app):
        """Test line 100-101: limit_val <= 0 returns (unlimited)."""
        tenant = MagicMock(id=1, max_users=-1)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_limit("users", model=MagicMock())

    def test_check_limit_zero_with_error_if_disabled(self, app):
        """Test line 97-98: limit_val == 0 and error_if_disabled=True."""
        tenant = MagicMock(id=1, max_users=0)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            with pytest.raises(TenantLimitError):
                check_limit("users", model=MagicMock(), error_if_disabled=True)

    def test_check_limit_no_limit_attr_on_tenant(self, app):
        """Test line 93-95: limit_attr not found on tenant."""
        tenant = MagicMock(spec=["id"])
        tenant.id = 1
        # No max_users attribute
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_limit("users", model=MagicMock())

    def test_check_limit_with_extra_filter(self, app):
        """Test line 105-106: extra_filter branch."""
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 1

        with (
            patch("utils.tenant_limits._active_tenant", return_value=MagicMock(id=1, max_users=10)),
            patch("utils.tenant_limits.db") as mock_db,
        ):
            mock_db.session.query.return_value = q
            q.filter.return_value = q
            q.filter.return_value = q
            check_limit("users", model=MagicMock(), extra_filter=lambda q: q)

    def test_check_limit_exceeds_raises(self, app):
        """Test line 109-110: exceeding limit raises TenantLimitError."""
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 2

        with (
            patch("utils.tenant_limits._active_tenant", return_value=MagicMock(id=1, max_users=1)),
            patch("utils.tenant_limits.db") as mock_db,
        ):
            mock_db.session.query.return_value = q
            q.filter.return_value = q
            with pytest.raises(TenantLimitError):
                check_limit("users", model=type("User", (), {"tenant_id": _Col()}))


class TestCheckMonthlyLimitCoverage:
    """Tests for check_monthly_limit uncovered branches."""

    def test_check_monthly_limit_no_tenant(self):
        """Test line 123-124: no tenant skips."""
        with patch("utils.tenant_limits._active_tenant", return_value=None):
            check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")

    def test_check_monthly_limit_no_limit_attr(self, app):
        """Test line 128-129: no limit attribute."""
        tenant = MagicMock(spec=["id"])
        tenant.id = 1
        # No max_sales_per_month attribute
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")

    def test_check_monthly_limit_zero_unlimited(self, app):
        """Test line 130-131: limit_val <= 0 returns unlimited."""
        tenant = MagicMock(id=1, max_sales_per_month=0)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")

    def test_check_monthly_limit_zero_with_error_if_disabled(self):
        """Test monthly limit with 0 and error_if_disabled (not currently implemented)."""
        tenant = MagicMock(id=1, max_sales_per_month=0)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            # Currently check_monthly_limit doesn't have error_if_disabled
            check_monthly_limit(
                "sales", model=type("Sale", (), {"tenant_id": _Col(), "sale_date": _Col()}), date_field="sale_date"
            )

    def test_check_monthly_limit_exceeds(self, app):
        """Test monthly limit exceeded raises error."""
        tenant = MagicMock(id=1, max_sales_per_month=1)
        with (
            patch("utils.tenant_limits._active_tenant", return_value=tenant),
            patch("utils.tenant_limits._month_start", return_value=datetime(2025, 1, 1, tzinfo=UTC)),
            patch("utils.tenant_limits.db") as mock_db,
        ):
            mock_db.session.query.return_value.filter.return_value.count.return_value = 1
            with pytest.raises(TenantLimitError):
                check_monthly_limit(
                    "sales", model=type("Sale", (), {"tenant_id": _Col(), "sale_date": _Col()}), date_field="sale_date"
                )


class TestCheckFeatureEnabledCoverage:
    """Tests for check_feature_enabled uncovered lines."""

    def test_check_feature_enabled_no_tenant(self):
        """Test line 150-151: no tenant returns True."""
        with patch("utils.tenant_limits._active_tenant", return_value=None):
            assert check_feature_enabled("enable_pos") is True

    def test_check_feature_enabled_feature_not_set(self, app):
        """Test when feature flag not set on tenant (defaults to True)."""
        tenant = MagicMock(spec=["id"])
        tenant.id = 1
        # No enable_pos attribute
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            assert check_feature_enabled("enable_pos") is True

    def test_check_feature_enabled_disabled(self, app):
        """Test feature disabled returns False."""
        tenant = MagicMock(id=1, enable_pos=False)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            assert check_feature_enabled("enable_pos") is False


class TestEnforceFeatureCoverage:
    """Tests for enforce_feature uncovered lines."""

    def test_enforce_feature_no_tenant(self):
        """Test line 260-261: no tenant returns early."""
        with patch("utils.tenant_limits._active_tenant", return_value=None):
            enforce_feature("enable_pos", "POS")  # Should not raise

    def test_enforce_feature_enabled(self, app):
        """Test feature enabled - no exception."""
        tenant = MagicMock(enable_pos=True)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            enforce_feature("enable_pos", "POS")

    def test_enforce_feature_disabled(self, app):
        """Test lines 262-264: feature disabled raises TenantLimitError."""
        tenant = MagicMock(enable_pos=False)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            with pytest.raises(TenantLimitError):
                enforce_feature("enable_pos", "نقطة البيع")


class TestCountModelCoverage:
    """Tests for _count_model and _monthly_count uncovered lines."""

    def test_count_model_without_extra_filter(self):
        from utils.tenant_limits import _count_model

        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 5

        sess = MagicMock()
        sess.query.return_value = q
        with patch("utils.tenant_limits.db", session=sess):
            assert _count_model(MagicMock(), 1) == 5

    def test_count_model_with_extra_filter(self):
        from utils.tenant_limits import _count_model

        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 3
        sess = MagicMock()
        sess.query.return_value = q
        extra = MagicMock(return_value=q)
        with patch("utils.tenant_limits.db", session=sess):
            assert _count_model(MagicMock(), 1, extra_filter=extra) == 3

    def test_monthly_count_without_extra_filter(self):
        from utils.tenant_limits import _monthly_count

        class _Comparable:
            def __eq__(self, other):
                return True

            def __ge__(self, other):
                return True

            def __hash__(self):
                return 1

        model = type("Model", (), {"tenant_id": 1, "sale_date": _Comparable()})
        mock_query = MagicMock()
        mock_query.filter.return_value = MagicMock(count=MagicMock(return_value=7))
        mock_db = MagicMock()
        mock_db.session.query.return_value = mock_query
        with patch("utils.tenant_limits.db", mock_db):
            assert _monthly_count(model, 1, "sale_date") == 7

    def test_monthly_count_with_extra_filter(self):
        from utils.tenant_limits import _monthly_count

        class _Comparable:
            def __eq__(self, other):
                return True

            def __ge__(self, other):
                return True

            def __hash__(self):
                return 1

        model = type("Model", (), {"tenant_id": 1, "sale_date": _Comparable()})
        mock_query = MagicMock()
        mock_query.filter.return_value = MagicMock(count=MagicMock(return_value=3))
        mock_db = MagicMock()
        mock_db.session.query.return_value = mock_query
        with patch("utils.tenant_limits.db", mock_db):
            assert _monthly_count(model, 1, "sale_date", lambda q: q) == 3


class TestGetTenantUsageSummaryCoverage:
    """Tests for get_tenant_usage_summary uncovered lines."""

    def test_summary_none_tenant(self):
        from utils.tenant_limits import get_tenant_usage_summary

        assert get_tenant_usage_summary(None) == []

    def test_summary_rows_and_unlimited(self, db_session, sample_tenant):
        from utils.tenant_limits import get_tenant_usage_summary

        sample_tenant.max_users = 10
        sample_tenant.max_products = -1  # unlimited
        db_session.commit()

        rows = {row["key"]: row for row in get_tenant_usage_summary(sample_tenant)}
        assert set(rows) == {
            "users",
            "branches",
            "warehouses",
            "products",
            "customers",
            "suppliers",
            "storage_mb",
            "sales_per_month",
        }
        assert rows["users"]["limit"] == 10
        assert rows["products"]["unlimited"] is True
        assert rows["products"]["limit"] is None
        assert rows["storage_mb"]["limit"] == 1024
        assert rows["storage_mb"]["unlimited"] is False

    def test_warn_at_80_percent(self, db_session, sample_tenant, sample_user):
        from utils.tenant_limits import get_tenant_usage_warnings

        sample_tenant.max_users = 1  # 100% usage
        sample_tenant.max_branches = None
        sample_tenant.max_warehouses = None
        sample_tenant.max_products = None
        sample_tenant.max_customers = None
        sample_tenant.max_suppliers = None
        sample_tenant.max_sales_per_month = None
        db_session.commit()

        warnings = get_tenant_usage_warnings(sample_tenant)
        keys = {row["key"] for row in warnings}
        assert "users" in keys
        users_row = next(row for row in warnings if row["key"] == "users")
        assert users_row["percent"] == 100
        assert users_row["warn"] is True

    def test_usage_summary_specific_counters(self, db_session, sample_tenant):
        """Test specific counter functions in get_tenant_usage_summary."""
        from utils.tenant_limits import get_tenant_usage_summary

        sample_tenant.max_users = 10
        sample_tenant.max_branches = 5
        sample_tenant.max_warehouses = 0  # disabled
        sample_tenant.max_products = 10
        db_session.commit()

        rows = get_tenant_usage_summary(sample_tenant)
        rows_dict = {row["key"]: row for row in rows}

        # Test unlimited/zero handling
        assert rows_dict["branches"]["limit"] == 5
        assert rows_dict["warehouses"]["unlimited"] is True  # limit 0 or None


class TestConvenienceHelpersCoverage:
    """Test convenience helper functions."""

    def test_check_users_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_limit") as chk:
            from utils.tenant_limits import check_users_limit

            check_users_limit()
            chk.assert_called_once()

    def test_check_branches_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_limit") as chk:
            from utils.tenant_limits import check_branches_limit

            check_branches_limit()
            chk.assert_called_once()

    def test_check_warehouses_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_limit") as chk:
            from utils.tenant_limits import check_warehouses_limit

            check_warehouses_limit()
            chk.assert_called_once()

    def test_check_products_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_limit") as chk:
            from utils.tenant_limits import check_products_limit

            check_products_limit()
            chk.assert_called_once()

    def test_check_customers_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_limit") as chk:
            from utils.tenant_limits import check_customers_limit

            check_customers_limit()
            chk.assert_called_once()

    def test_check_suppliers_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_limit") as chk:
            from utils.tenant_limits import check_suppliers_limit

            check_suppliers_limit()
            chk.assert_called_once()

    def test_check_sales_monthly_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_monthly_limit") as chk:
            from utils.tenant_limits import check_sales_monthly_limit

            check_sales_monthly_limit()
            chk.assert_called_once()

    def test_check_invoices_monthly_limit_delegates(self, app):
        with patch("utils.tenant_limits.check_monthly_limit") as chk:
            from utils.tenant_limits import check_invoices_monthly_limit

            check_invoices_monthly_limit()
            chk.assert_called_once()


class TestCheckLimitEdgeCases:
    def test_check_limit_limit_none(self, app):
        """Test when limit attribute doesn't exist on tenant."""
        tenant = MagicMock(spec=["id"])
        tenant.id = 1
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_limit("users", model=MagicMock())

    def test_check_limit_zero_disabled(self, app):
        tenant = MagicMock(id=1, max_users=0)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_limit("users", model=MagicMock())

    def test_check_limit_negative_unlimited(self, app):
        tenant = MagicMock(id=1, max_users=-1)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_limit("users", model=MagicMock())


class TestCheckMonthlyLimitEdgeCases:
    def test_check_monthly_limit_no_tenant(self):
        with patch("utils.tenant_limits._active_tenant", return_value=None):
            check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")

    def test_check_monthly_limit_no_limit_attr(self, app):
        tenant = MagicMock(spec=["id"])
        tenant.id = 1
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")

    def test_check_monthly_limit_zero_unlimited(self, app):
        tenant = MagicMock(id=1, max_sales_per_month=0)
        with patch("utils.tenant_limits._active_tenant", return_value=tenant):
            check_monthly_limit("sales", model=MagicMock(), date_field="sale_date")
