"""Asset service — CRUD, depreciation, and disposal tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models import GLAccount
from services.asset_service import AssetService


def _get_asset_accounts(tenant_id):
    asset_acct = GLAccount.query.filter_by(tenant_id=tenant_id, code="1180").first()
    dep_acct = GLAccount.query.filter_by(tenant_id=tenant_id, code="6300").first()
    assert asset_acct is not None, "1180 Fixed Assets must be created by sample_gl_accounts"
    assert dep_acct is not None, "6300 Depreciation Expense must be created by sample_gl_accounts"
    return asset_acct.id, dep_acct.id


class TestAssetService:
    def test_create_asset(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        data = {
            "name_ar": "كمبيوتر",
            "category": "computer",
            "asset_account_id": str(acct_id),
            "depreciation_account_id": str(dep_id),
            "purchase_date": date(2026, 1, 1),
            "purchase_price": "10000",
            "salvage_value": "1000",
            "depreciation_method": "straight_line",
            "useful_life_years": "5",
        }
        asset = AssetService.create_asset(data, sample_user)
        assert asset.id is not None
        assert asset.status == "active"
        assert asset.asset_number.startswith("FA")
        assert asset.purchase_price == Decimal("10000")

    def test_update_asset(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        data = {
            "name_ar": "original name",
            "category": "equipment",
            "asset_account_id": str(acct_id),
            "depreciation_account_id": str(dep_id),
            "purchase_date": date(2026, 1, 1),
            "purchase_price": "5000",
            "useful_life_years": "3",
        }
        asset = AssetService.create_asset(data, sample_user)
        AssetService.update_asset(asset, {"name_ar": "جديد اسم", "location": "Office A"})
        assert asset.name_ar == "جديد اسم"
        assert asset.location == "Office A"

    def test_update_disposed_asset_raises(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        data = {
            "name_ar": "أصل قديم",
            "category": "vehicle",
            "asset_account_id": str(acct_id),
            "depreciation_account_id": str(dep_id),
            "purchase_date": date(2025, 1, 1),
            "purchase_price": "20000",
            "useful_life_years": "5",
        }
        asset = AssetService.create_asset(data, sample_user)
        asset.status = "disposed"
        db_session.flush()
        with pytest.raises(ValueError):
            AssetService.update_asset(asset, {"name_ar": "new"})

    def test_dispose_asset(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        data = {
            "name_ar": "أصل للتخلص",
            "category": "furniture",
            "asset_account_id": str(acct_id),
            "depreciation_account_id": str(dep_id),
            "purchase_date": date(2025, 6, 1),
            "purchase_price": "3000",
            "useful_life_years": "5",
        }
        asset = AssetService.create_asset(data, sample_user)
        asset.accumulated_depreciation = Decimal("1500")
        asset.book_value = Decimal("1500")
        db_session.flush()
        AssetService.dispose_asset(asset, date(2026, 8, 1), Decimal("500"), notes="Old desk")
        assert asset.status == "sold"
        assert asset.disposal_date == date(2026, 8, 1)

    def test_dispose_already_disposed_raises(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        data = {
            "name_ar": "أصل مسلّم",
            "category": "computer",
            "asset_account_id": str(acct_id),
            "depreciation_account_id": str(dep_id),
            "purchase_date": date(2025, 1, 1),
            "purchase_price": "8000",
            "useful_life_years": "3",
        }
        asset = AssetService.create_asset(data, sample_user)
        asset.status = "sold"
        db_session.flush()
        with pytest.raises(ValueError):
            AssetService.dispose_asset(asset, date(2026, 1, 1), Decimal("0"))

    def test_get_asset_summary(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        for i in range(3):
            data = {
                "name_ar": f"أصل {i}",
                "category": "equipment",
                "asset_account_id": str(acct_id),
                "depreciation_account_id": str(dep_id),
                "purchase_date": date(2026, 1, 1),
                "purchase_price": str(1000 * (i + 1)),
                "useful_life_years": "5",
            }
            AssetService.create_asset(data, sample_user)

        summary = AssetService.get_asset_summary(sample_user)
        assert summary["total"] >= 3
        assert summary["active"] >= 3

    def test_post_manual_depreciation_not_active_raises(
        self, db_session, sample_tenant, sample_gl_accounts, sample_user
    ):
        acct_id, dep_id = _get_asset_accounts(sample_tenant.id)
        data = {
            "name_ar": "أصل غير نشط",
            "category": "equipment",
            "asset_account_id": str(acct_id),
            "depreciation_account_id": str(dep_id),
            "purchase_date": date(2026, 1, 1),
            "purchase_price": "5000",
            "useful_life_years": "5",
        }
        asset = AssetService.create_asset(data, sample_user)
        asset.status = "disposed"
        db_session.flush()
        with pytest.raises(ValueError):
            AssetService.post_manual_depreciation(asset)
