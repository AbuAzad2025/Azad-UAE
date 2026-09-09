"""Coverage for FixedAsset.dispose branches (arcs 277->285, 296->307, 317->328)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock


def _asset(**kwargs):
    from models.fixed_asset import FixedAsset

    return FixedAsset(
        tenant_id=1,
        asset_number=kwargs.get("asset_number", "FA-COV-DISP"),
        name_ar="أصل",
        name_en="Asset",
        category="equipment",
        asset_account_id=1,
        depreciation_account_id=2,
        expense_account_id=3,
        purchase_date=date(2024, 1, 1),
        purchase_price=Decimal(kwargs.get("purchase_price", "10000")),
        salvage_value=Decimal(kwargs.get("salvage_value", "0")),
        useful_life_years=5,
        depreciation_method="straight_line",
        accumulated_depreciation=Decimal(kwargs.get("accumulated", "2000")),
        book_value=Decimal(kwargs.get("book_value", "8000")),
        branch_id=1,
        status="active",
    )


def _wire(asset, mocker):
    asset.asset_account = MagicMock(code="1500")
    asset.depreciation_account = MagicMock(code="1590")
    mocker.patch("models.fixed_asset.gl_get_default_liquidity_account", return_value="1110")
    mock_gl = mocker.patch("models.fixed_asset.gl_post_or_fail")
    mocker.patch("models.fixed_asset.db.session")
    return mock_gl


class TestDisposeScrapPath:
    def test_dispose_scrap_zero_price_skips_bank_line(self, app, mocker):
        """Arcs 277->285 and 296->307: disposal_price == 0 takes the scrap path."""
        asset = _asset(book_value="8000", accumulated="2000")
        asset.purchase_price = Decimal("10000")
        mock_gl = _wire(asset, mocker)
        with app.app_context():
            asset.dispose(date(2026, 6, 1), 0)
        assert asset.status == "disposed"
        assert asset.disposal_price == Decimal("0")
        assert asset.disposal_gain_loss == Decimal("-8000")
        lines = mock_gl.call_args[1]["lines"]
        assert not any(line.get("concept_code") == "BANK" for line in lines)
        assert any(line.get("concept_code") == "FIXED_ASSET_LOSS" for line in lines)

    def test_dispose_scrap_with_notes_appends(self, app, mocker):
        asset = _asset(book_value="8000", accumulated="2000")
        asset.purchase_price = Decimal("10000")
        _wire(asset, mocker)
        with app.app_context():
            asset.dispose(date(2026, 6, 2), 0, notes="scrapped unit")
        assert asset.status == "disposed"
        assert "scrapped unit" in asset.notes


class TestDisposeBreakEvenPath:
    def test_dispose_break_even_no_gain_no_loss_line(self, app, mocker):
        """Arc 317->328: gain_loss == 0 skips both gain and loss lines."""
        asset = _asset(book_value="8000", accumulated="2000")
        asset.purchase_price = Decimal("10000")
        mock_gl = _wire(asset, mocker)
        with app.app_context():
            asset.dispose(date(2026, 7, 1), Decimal("8000"))
        assert asset.status == "sold"
        assert asset.disposal_gain_loss == Decimal("0")
        lines = mock_gl.call_args[1]["lines"]
        assert any(line.get("concept_code") == "BANK" for line in lines)
        assert not any(line.get("concept_code") == "FIXED_ASSET_GAIN" for line in lines)
        assert not any(line.get("concept_code") == "FIXED_ASSET_LOSS" for line in lines)


class TestDisposeGainPath:
    def test_dispose_with_gain_posts_gain_line(self, app, mocker):
        """Gain side of 307/317: disposal_price above book value posts FIXED_ASSET_GAIN."""
        asset = _asset(book_value="5000", accumulated="5000")
        asset.purchase_price = Decimal("10000")
        mock_gl = _wire(asset, mocker)
        with app.app_context():
            asset.dispose(date(2026, 5, 1), 7000)
        assert asset.status == "sold"
        assert asset.disposal_gain_loss == Decimal("2000")
        lines = mock_gl.call_args[1]["lines"]
        assert any(line.get("concept_code") == "BANK" for line in lines)
        assert any(line.get("concept_code") == "FIXED_ASSET_GAIN" for line in lines)
