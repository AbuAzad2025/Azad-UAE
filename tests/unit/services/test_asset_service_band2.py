"""AssetService — list filters/tenant scoping, depreciation posting bands.

Complements test_asset_service.py: covers the filter matrix of
``list_assets``, the success and zero-depreciation branches of
``post_manual_depreciation``, and ``get_depreciation_schedule``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from models import GLAccount
from services.asset_service import AssetService


def _acct(tenant_id, code):
    account = GLAccount.query.filter_by(tenant_id=tenant_id, code=code).first()
    assert account is not None, f"core account {code} missing"
    return str(account.id)


def _asset_data(tenant_id, *, category="equipment", price="6000", life="5", branch_id=None):
    data = {
        "name_ar": "أصل اختبار",
        "name_en": "Test Asset",
        "category": category,
        "asset_account_id": _acct(tenant_id, "1180"),
        "depreciation_account_id": _acct(tenant_id, "1190"),
        "expense_account_id": _acct(tenant_id, "6300"),
        "purchase_date": date(2026, 1, 1),
        "purchase_price": price,
        "salvage_value": "100",
        "useful_life_years": life,
    }
    if branch_id is not None:
        data["branch_id"] = branch_id
    return data


class TestListAssetsFilters:
    def test_status_category_branch_filters_and_tenant_scope(
        self, db_session, sample_tenant, sample_gl_accounts, sample_user, sample_branch
    ):
        active = AssetService.create_asset(_asset_data(sample_tenant.id), sample_user)
        vehicle = AssetService.create_asset(
            _asset_data(sample_tenant.id, category="vehicle", branch_id=str(sample_branch.id)), sample_user
        )
        vehicle.status = "disposed"
        db_session.flush()

        all_assets = AssetService.list_assets(sample_user)
        ids = {a.id for a in all_assets}
        assert {active.id, vehicle.id} <= ids

        by_status = AssetService.list_assets(sample_user, {"status": "disposed"})
        assert vehicle.id in {a.id for a in by_status}
        assert active.id not in {a.id for a in by_status}

        by_category = AssetService.list_assets(sample_user, {"category": "vehicle"})
        assert all(a.category == "vehicle" for a in by_category)

        by_branch = AssetService.list_assets(sample_user, {"branch_id": str(sample_branch.id)})
        assert {a.id for a in by_branch} == {vehicle.id}

    def test_other_tenant_assets_excluded(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        """Tenant isolation: rows belonging to another tenant must never leak."""
        import uuid as _uuid

        from models import FixedAsset, Tenant

        suffix = _uuid.uuid4().hex[:8]
        other_tenant = Tenant(
            name=f"Other Assets Co {suffix}",
            name_ar="أخرى",
            slug=f"other-assets-{suffix}",
            email=f"other-assets-{suffix}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other_tenant)
        db_session.flush()

        foreign = FixedAsset(
            tenant_id=other_tenant.id,
            asset_number="FA-FOREIGN-1",
            name_ar="أصل آخر",
            category="equipment",
            asset_account_id=int(_acct(sample_tenant.id, "1180")),
            purchase_date=date(2026, 1, 1),
            purchase_price=Decimal("100"),
            useful_life_years=5,
            book_value=Decimal("100"),
            status="active",
        )
        db_session.add(foreign)
        db_session.flush()

        mine = AssetService.list_assets(sample_user)
        assert foreign.id not in {a.id for a in mine}
        assert all(a.tenant_id == sample_tenant.id for a in mine)


class TestPostManualDepreciation:
    def test_success_posts_schedule_and_updates_totals(
        self, db_session, sample_tenant, sample_gl_accounts, sample_user
    ):
        from models import DepreciationSchedule

        asset = AssetService.create_asset(_asset_data(sample_tenant.id, price="12000"), sample_user)
        period = date.today().replace(day=28)

        schedule = AssetService.post_manual_depreciation(asset, period_date=period)

        assert isinstance(schedule, DepreciationSchedule)
        assert schedule.asset_id == asset.id
        expected_monthly = (Decimal("11900") / 60).quantize(Decimal("0.01"))
        assert schedule.depreciation_amount == expected_monthly
        assert asset.accumulated_depreciation == expected_monthly

    def test_land_asset_zero_depreciation_raises_no_schedule_value_error(
        self, db_session, sample_tenant, sample_gl_accounts, sample_user
    ):
        asset = AssetService.create_asset(_asset_data(sample_tenant.id, category="land", price="50000"), sample_user)
        with pytest.raises(ValueError, match="استهلاك"):
            AssetService.post_manual_depreciation(asset)


class TestGetDepreciationSchedule:
    def test_returns_posted_schedules(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        asset = AssetService.create_asset(_asset_data(sample_tenant.id), sample_user)
        AssetService.post_manual_depreciation(asset, period_date=date.today().replace(day=28))

        schedules = AssetService.get_depreciation_schedule(asset.id, sample_user)
        assert len(schedules) == 1
        assert schedules[0].asset_id == asset.id

    def test_unknown_asset_raises(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        with pytest.raises(ValueError):
            AssetService.get_depreciation_schedule(999999999, sample_user)


class TestUpdateStatusGuard:
    def test_fully_depreciated_asset_remains_updatable(
        self, db_session, sample_tenant, sample_gl_accounts, sample_user
    ):
        asset = AssetService.create_asset(_asset_data(sample_tenant.id), sample_user)
        asset.status = "fully_depreciated"
        db_session.flush()

        updated = AssetService.update_asset(asset, {"notes": "checked"})
        assert updated.notes == "checked"

    def test_none_valued_fields_are_skipped(self, db_session, sample_tenant, sample_gl_accounts, sample_user):
        asset = AssetService.create_asset(_asset_data(sample_tenant.id), sample_user)
        original_name_en = asset.name_en
        AssetService.update_asset(asset, {"name_en": None})
        assert asset.name_en == original_name_en
