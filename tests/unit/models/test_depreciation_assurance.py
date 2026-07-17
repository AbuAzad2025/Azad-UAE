"""Depreciation service — monthly run, skip paths, GL posting delegation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestDepreciationFormulas:
    """FixedAsset.calculate_monthly_depreciation — straight-line vs declining balance."""

    @staticmethod
    def _asset(method="straight_line", **kwargs):
        from models.fixed_asset import FixedAsset

        asset = FixedAsset(
            tenant_id=1,
            asset_number="FA-001",
            name_ar="معدات",
            name_en="Equipment",
            category=kwargs.get("category", "equipment"),
            asset_account_id=1,
            depreciation_account_id=2,
            expense_account_id=3,
            purchase_date=date(2024, 1, 1),
            purchase_price=Decimal(kwargs.get("purchase_price", "12000")),
            salvage_value=Decimal(kwargs.get("salvage_value", "2000")),
            useful_life_years=kwargs.get("useful_life_years", 5),
            depreciation_method=method,
            accumulated_depreciation=Decimal(kwargs.get("accumulated", "0")),
            branch_id=1,
            status="active",
        )
        return asset

    def test_straight_line_monthly_amount(self):
        asset = self._asset()
        # (12000 - 2000) / (5 * 12) = 166.67
        assert asset.calculate_monthly_depreciation() == Decimal("166.67")

    def test_declining_balance_respects_salvage_floor(self):
        asset = self._asset(
            method="declining_balance",
            accumulated="10000",
            salvage_value="2000",
        )
        monthly = asset.calculate_monthly_depreciation()
        assert monthly >= Decimal("0")
        assert asset.remaining_book_value - monthly >= asset.salvage_value - Decimal(
            "0.01"
        )

    def test_land_category_zero_depreciation(self):
        asset = self._asset(category="land")
        assert asset.calculate_monthly_depreciation() == Decimal("0")


class TestDepreciationRunMonthly:
    """DepreciationService.run_monthly — tenant filter, posted/skipped/errors."""

    @staticmethod
    def _mock_assets_query(mocker, assets, _tenant_id=None):
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = assets
        mocker.patch("services.depreciation_service.FixedAsset.query", mock_q)
        return mock_q

    def test_posts_active_assets_for_tenant(self, app, mocker):
        asset = MagicMock(asset_number="FA-10")
        asset.post_depreciation.return_value = MagicMock(id=1)
        self._mock_assets_query(mocker, [asset])
        mocker.patch("services.depreciation_service.db.session")

        from services.depreciation_service import DepreciationService

        with app.app_context():
            result = DepreciationService.run_monthly(
                tenant_id=1, period_year=2026, period_month=3
            )

        assert result["posted"] == 1
        assert result["skipped"] == 0
        assert result["errors"] == []
        asset.post_depreciation.assert_called_once_with(period_date=date(2026, 3, 1))

    def test_skips_when_post_returns_none(self, app, mocker):
        asset = MagicMock(asset_number="FA-11")
        asset.post_depreciation.return_value = None
        self._mock_assets_query(mocker, [asset])
        mocker.patch("services.depreciation_service.db.session")

        from services.depreciation_service import DepreciationService

        with app.app_context():
            result = DepreciationService.run_monthly(period_year=2026, period_month=1)
        assert result["skipped"] == 1
        assert result["posted"] == 0

    def test_duplicate_period_counts_as_skipped(self, app, mocker):
        asset = MagicMock(asset_number="FA-12")
        asset.post_depreciation.side_effect = ValueError(
            "تم ترحيل الاستهلاك لهذا الشهر مسبقاً"
        )
        self._mock_assets_query(mocker, [asset])
        mocker.patch("services.depreciation_service.db.session")

        from services.depreciation_service import DepreciationService

        with app.app_context():
            result = DepreciationService.run_monthly(period_year=2026, period_month=6)
        assert result["skipped"] == 1

    def test_other_value_error_recorded(self, app, mocker):
        asset = MagicMock(asset_number="FA-13")
        asset.post_depreciation.side_effect = ValueError("inactive asset")
        self._mock_assets_query(mocker, [asset])
        mocker.patch("services.depreciation_service.db.session")

        from services.depreciation_service import DepreciationService

        with app.app_context():
            result = DepreciationService.run_monthly(period_year=2026, period_month=6)
        assert len(result["errors"]) == 1
        assert "FA-13" in result["errors"][0]

    def test_unexpected_exception_captured(self, app, mocker):
        asset = MagicMock(asset_number="FA-14")
        asset.post_depreciation.side_effect = RuntimeError("gl failure")
        self._mock_assets_query(mocker, [asset])
        mocker.patch("services.depreciation_service.db.session")

        from services.depreciation_service import DepreciationService

        with app.app_context():
            result = DepreciationService.run_monthly()
        assert "gl failure" in result["errors"][0]

    def test_commit_failure_rolls_back(self, app, mocker):
        asset = MagicMock(asset_number="FA-15")
        asset.post_depreciation.return_value = MagicMock(id=2)
        self._mock_assets_query(mocker, [asset])
        mock_session = mocker.patch("services.depreciation_service.db.session")
        mock_session.flush.side_effect = RuntimeError("commit failed")

        from services.depreciation_service import DepreciationService

        with app.app_context():
            with pytest.raises(RuntimeError, match="commit failed"):
                DepreciationService.run_monthly()
        mock_session.rollback.assert_called()

    def test_post_depreciation_posts_balanced_gl(self, app, mocker):
        """Border-date execution delegates balanced GL lines via gl_post_or_fail."""
        from models.fixed_asset import FixedAsset

        asset = FixedAsset(
            tenant_id=1,
            asset_number="FA-GL",
            name_ar="أصل",
            name_en="Asset",
            category="equipment",
            asset_account_id=1,
            depreciation_account_id=2,
            expense_account_id=3,
            purchase_date=date(2025, 1, 1),
            purchase_price=Decimal("6000"),
            salvage_value=Decimal("0"),
            useful_life_years=5,
            depreciation_method="straight_line",
            accumulated_depreciation=Decimal("0"),
            branch_id=1,
            status="active",
        )
        asset.id = 99
        asset.expense_account = MagicMock(code="6180")
        asset.depreciation_account = MagicMock(code="1190")

        mocker.patch(
            "models.fixed_asset.DepreciationSchedule.query"
        ).filter_by.return_value.first.return_value = None
        mocker.patch("models.fixed_asset.gl_ensure_core_accounts")
        mock_entry = MagicMock(id=501)
        mock_gl = mocker.patch(
            "models.fixed_asset.gl_post_or_fail", return_value=mock_entry
        )
        mocker.patch("models.fixed_asset.db.session")

        with app.app_context():
            schedule = asset.post_depreciation(period_date=date(2026, 1, 1))

        assert schedule is not None
        assert schedule.depreciation_amount == Decimal("100.00")
        mock_gl.assert_called_once()
        lines = mock_gl.call_args[1]["lines"]
        debit = sum(Decimal(str(l["debit"])) for l in lines)
        credit = sum(Decimal(str(l["credit"])) for l in lines)
        assert debit == credit


class TestFixedAssetModelCoverage:
    @staticmethod
    def _asset(**kwargs):
        from models.fixed_asset import FixedAsset

        return FixedAsset(
            tenant_id=1,
            asset_number=kwargs.get("asset_number", "FA-COV"),
            name_ar="أصل",
            name_en="Asset",
            category=kwargs.get("category", "equipment"),
            asset_account_id=1,
            depreciation_account_id=2,
            expense_account_id=3,
            purchase_date=date(2024, 1, 1),
            purchase_price=Decimal(kwargs.get("purchase_price", "12000")),
            salvage_value=Decimal(kwargs.get("salvage_value", "2000")),
            useful_life_years=kwargs.get("useful_life_years", 5),
            depreciation_method=kwargs.get(
                "depreciation_method", kwargs.get("method", "straight_line")
            ),
            accumulated_depreciation=Decimal(kwargs.get("accumulated", "0")),
            book_value=Decimal(kwargs.get("book_value", "10000")),
            branch_id=1,
            status=kwargs.get("status", "active"),
        )

    def test_repr_and_localized_labels(self):
        asset = self._asset()
        assert "FA-COV" in repr(asset)
        asset.category = "vehicle"
        assert asset.category_ar == "سيارات"
        asset.status = "fully_depreciated"
        assert asset.status_ar == "مستهلك بالكامل"

    def test_declining_balance_at_salvage_returns_zero(self):
        asset = self._asset(
            method="declining_balance",
            purchase_price="2200",
            accumulated="200",
            salvage_value="2000",
        )
        assert asset.remaining_book_value == Decimal("2000")
        assert asset.calculate_monthly_depreciation() == Decimal("0")

    def test_unknown_depreciation_method_returns_zero(self):
        asset = self._asset(depreciation_method="units_of_production")
        assert asset.calculate_monthly_depreciation() == Decimal("0")

    def test_post_depreciation_inactive_raises(self, app):
        asset = self._asset(status="disposed")
        with app.app_context():
            with pytest.raises(ValueError, match="غير نشط"):
                asset.post_depreciation()

    def test_post_depreciation_duplicate_period(self, app, mocker):
        asset = self._asset()
        asset.expense_account = MagicMock(code="6180")
        asset.depreciation_account = MagicMock(code="1190")
        mocker.patch(
            "models.fixed_asset.DepreciationSchedule.query"
        ).filter_by.return_value.first.return_value = MagicMock()
        with app.app_context():
            with pytest.raises(ValueError, match="مسبقاً"):
                asset.post_depreciation(period_date=date(2026, 3, 1))

    def test_post_depreciation_zero_amount_returns_none(self, app, mocker):
        asset = self._asset(category="land")
        mocker.patch(
            "models.fixed_asset.DepreciationSchedule.query"
        ).filter_by.return_value.first.return_value = None
        with app.app_context():
            assert asset.post_depreciation(period_date=date(2026, 3, 1)) is None

    def test_post_depreciation_default_period_date(self, app, mocker):
        asset = self._asset()
        asset.id = 1
        asset.expense_account = MagicMock(code="6180")
        asset.depreciation_account = MagicMock(code="1190")
        mocker.patch(
            "models.fixed_asset.DepreciationSchedule.query"
        ).filter_by.return_value.first.return_value = None
        mocker.patch("models.fixed_asset.gl_ensure_core_accounts")
        mocker.patch("models.fixed_asset.gl_post_or_fail", return_value=MagicMock(id=1))
        mocker.patch("models.fixed_asset.db.session")
        with app.app_context():
            schedule = asset.post_depreciation()
        assert schedule is not None
        assert asset.last_depreciation_date == date.today()

    def test_post_depreciation_marks_fully_depreciated(self, app, mocker):
        asset = self._asset(
            purchase_price="2200",
            salvage_value="2000",
            accumulated="199.99",
        )
        asset.id = 2
        asset.expense_account = MagicMock(code="6180")
        asset.depreciation_account = MagicMock(code="1190")
        mocker.patch(
            "models.fixed_asset.DepreciationSchedule.query"
        ).filter_by.return_value.first.return_value = None
        mocker.patch("models.fixed_asset.gl_ensure_core_accounts")
        mocker.patch("models.fixed_asset.gl_post_or_fail", return_value=MagicMock(id=2))
        mocker.patch("models.fixed_asset.db.session")
        with app.app_context():
            asset.post_depreciation(period_date=date(2026, 4, 1))
        assert asset.book_value <= asset.salvage_value
        assert asset.status == "fully_depreciated"

    def test_dispose_already_disposed_raises(self, app):
        asset = self._asset(status="sold")
        with app.app_context():
            with pytest.raises(ValueError, match="مسبقاً"):
                asset.dispose(date(2026, 1, 1), 0)

    def test_declining_balance_positive_monthly(self):
        asset = self._asset(
            method="declining_balance",
            purchase_price="12000",
            accumulated="0",
            salvage_value="2000",
        )
        monthly = asset.calculate_monthly_depreciation()
        assert monthly > Decimal("0")

    def test_declining_balance_caps_at_salvage_floor(self):
        asset = self._asset(
            method="declining_balance",
            purchase_price="2050",
            accumulated="0",
            salvage_value="2000",
            useful_life_years=5,
        )
        monthly = asset.calculate_monthly_depreciation()
        assert monthly == Decimal("50")

        asset = self._asset(
            method="declining_balance",
            purchase_price="12000",
            accumulated="0",
            salvage_value="2000",
        )
        monthly = asset.calculate_monthly_depreciation()
        assert monthly > Decimal("0")

    def test_dispose_with_loss(self, app, mocker):
        asset = self._asset(book_value="8000", accumulated="2000")
        asset.purchase_price = Decimal("10000")
        asset.asset_account = MagicMock(code="1500")
        asset.depreciation_account = MagicMock(code="1590")
        asset.id = 4
        mocker.patch(
            "models.fixed_asset.gl_get_default_liquidity_account", return_value="1110"
        )
        mocker.patch("models.fixed_asset.gl_post_entry")
        mocker.patch("models.fixed_asset.db.session")
        with app.app_context():
            asset.dispose(date(2026, 6, 1), 5000)
        assert asset.disposal_gain_loss < 0

        asset = self._asset(book_value="5000", accumulated="5000")
        asset.purchase_price = Decimal("10000")
        asset.asset_account = MagicMock(code="1500")
        asset.depreciation_account = MagicMock(code="1590")
        asset.id = 3
        mocker.patch(
            "models.fixed_asset.gl_get_default_liquidity_account", return_value="1110"
        )
        mocker.patch("models.fixed_asset.gl_post_entry")
        mock_session = mocker.patch("models.fixed_asset.db.session")
        with app.app_context():
            asset.dispose(date(2026, 5, 1), 7000, notes="sold unit")
        assert asset.status == "sold"
        assert asset.disposal_gain_loss == Decimal("2000")
        assert "sold unit" in asset.notes
        mock_session.flush.assert_called_once()

    def test_depreciation_schedule_repr(self):
        from models.fixed_asset import DepreciationSchedule

        sched = DepreciationSchedule(asset_id=9, period_date=date(2026, 1, 31))
        assert "9" in repr(sched)
