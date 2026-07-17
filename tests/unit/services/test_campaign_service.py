from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from extensions import db
from models.campaign import Campaign, SaleCampaign
from services.campaign_service import CampaignService


@pytest.fixture
def active_campaign(db_session, sample_tenant):
    now = datetime.now(timezone.utc)
    campaign = Campaign(
        tenant_id=sample_tenant.id,
        name="Summer Sale",
        campaign_type="percentage",
        discount_value=Decimal("10"),
        max_discount_amount=Decimal("50"),
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=30),
        is_active=True,
        usage_count=0,
        coupon_code="SUMMER10",
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign


@pytest.fixture
def fixed_campaign(db_session, sample_tenant):
    now = datetime.now(timezone.utc)
    campaign = Campaign(
        tenant_id=sample_tenant.id,
        name="Fixed Off",
        campaign_type="fixed",
        discount_value=Decimal("25"),
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=30),
        is_active=True,
        usage_count=0,
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign


class TestCampaignROI:
    def test_calculate_roi_positive(self):
        assert CampaignService.calculate_roi(Decimal("100"), Decimal("150")) == Decimal(
            "50.00"
        )

    def test_calculate_roi_zero_cost(self):
        assert CampaignService.calculate_roi(Decimal("0"), Decimal("150")) == Decimal(
            "0"
        )

    def test_calculate_roi_negative(self):
        assert CampaignService.calculate_roi(Decimal("200"), Decimal("50")) == Decimal(
            "-75.00"
        )

    def test_get_campaign_roi_metrics(self, active_campaign):
        metrics = CampaignService.get_campaign_roi_metrics(
            active_campaign, total_revenue=Decimal("1000")
        )
        assert metrics["campaign_id"] == active_campaign.id
        assert metrics["total_cost"] == 0.0
        assert metrics["roi"] == 0.0

    def test_get_campaign_roi_metrics_with_usage(self, db_session, sample_tenant):
        campaign = Campaign(
            tenant_id=sample_tenant.id,
            name="Used",
            campaign_type="fixed",
            discount_value=Decimal("20"),
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=5),
            usage_count=5,
        )
        db_session.add(campaign)
        db_session.flush()
        metrics = CampaignService.get_campaign_roi_metrics(
            campaign, total_revenue=Decimal("500")
        )
        assert metrics["total_cost"] == 100.0
        assert metrics["roi"] == 400.0


class TestCampaignCommission:
    def test_safe_commission_rate_clamped(self):
        assert CampaignService.safe_commission_rate(Decimal("-5")) == Decimal("0")
        assert CampaignService.safe_commission_rate(Decimal("150")) == Decimal("100")

    def test_calculate_safe_commission(self):
        assert CampaignService.calculate_safe_commission(
            Decimal("1000"), Decimal("10")
        ) == Decimal("100.00")
        assert CampaignService.calculate_safe_commission(None, None) == Decimal("0.00")


class TestGetActiveCampaigns:
    def test_filters_by_tenant_and_dates(
        self, db_session, sample_tenant, active_campaign
    ):
        results = CampaignService.get_active_campaigns(sample_tenant.id)
        assert any(c.id == active_campaign.id for c in results)

    def test_product_filter_overlap(self, db_session, sample_tenant, active_campaign):
        active_campaign.applicable_products = [101, 102]
        db_session.flush()
        matched = CampaignService.get_active_campaigns(
            sample_tenant.id, product_ids=[102]
        )
        assert len(matched) == 1
        unmatched = CampaignService.get_active_campaigns(
            sample_tenant.id, product_ids=[999]
        )
        assert unmatched == []

    def test_category_filter_null_means_all(
        self, db_session, sample_tenant, active_campaign
    ):
        active_campaign.applicable_categories = None
        db_session.flush()
        results = CampaignService.get_active_campaigns(
            sample_tenant.id, category_ids=[1]
        )
        assert len(results) == 1

    def test_corrupt_scalar_json_treated_as_unrestricted(
        self, db_session, sample_tenant, active_campaign
    ):
        active_campaign.applicable_products = "invalid"
        db_session.flush()
        results = CampaignService.get_active_campaigns(
            sample_tenant.id, product_ids=[102]
        )
        assert len(results) == 1

    def test_product_and_category_filter(
        self, db_session, sample_tenant, active_campaign
    ):
        active_campaign.applicable_products = [101, 102]
        active_campaign.applicable_categories = [5, 6]
        db_session.flush()
        matched = CampaignService.get_active_campaigns(
            sample_tenant.id,
            product_ids=[102],
            category_ids=[5],
        )
        assert len(matched) == 1
        unmatched = CampaignService.get_active_campaigns(
            sample_tenant.id,
            product_ids=[102],
            category_ids=[99],
        )
        assert unmatched == []


class TestApplyCampaigns:
    def test_percentage_discount_capped(
        self, db_session, sample_tenant, active_campaign, sample_customer, sample_user
    ):
        from models import Sale

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"S-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            subtotal=Decimal("1000"),
            total_amount=Decimal("1000"),
            amount=Decimal("1000"),
            amount_aed=Decimal("1000"),
        )
        db_session.add(sale)
        db_session.flush()
        total = CampaignService.apply_campaigns(sale, [active_campaign])
        assert total == Decimal("50.000")
        assert active_campaign.usage_count == 1
        assert db.session.query(SaleCampaign).filter_by(sale_id=sale.id).count() == 1

    def test_skips_usage_limit_reached(
        self, db_session, sample_tenant, fixed_campaign, sample_customer, sample_user
    ):
        from models import Sale

        fixed_campaign.usage_limit = 1
        fixed_campaign.usage_count = 1
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"S-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            subtotal=Decimal("200"),
            total_amount=Decimal("200"),
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
        )
        db_session.add(sale)
        db_session.flush()
        total = CampaignService.apply_campaigns(sale, [fixed_campaign])
        assert total == Decimal("0")

    def test_fixed_discount_without_cap(
        self, db_session, sample_tenant, fixed_campaign, sample_customer, sample_user
    ):
        from models import Sale

        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"S-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            subtotal=Decimal("200"),
            total_amount=Decimal("200"),
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
        )
        db_session.add(sale)
        db_session.flush()
        total = CampaignService.apply_campaigns(sale, [fixed_campaign])
        assert total == Decimal("25.000")

    def test_bundle_campaign_type(
        self, db_session, sample_tenant, sample_customer, sample_user
    ):
        from models import Sale

        now = datetime.now(timezone.utc)
        bundle = Campaign(
            tenant_id=sample_tenant.id,
            name="Bundle",
            campaign_type="bundle",
            discount_value=Decimal("30"),
            start_date=now,
            end_date=now + timedelta(days=1),
        )
        db_session.add(bundle)
        db_session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number=f"S-{uuid.uuid4().hex[:6]}",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            subtotal=Decimal("300"),
            total_amount=Decimal("300"),
            amount=Decimal("300"),
            amount_aed=Decimal("300"),
        )
        db_session.add(sale)
        db_session.flush()
        total = CampaignService.apply_campaigns(sale, [bundle])
        assert total == Decimal("30")


class TestValidateCoupon:
    def test_valid_coupon(self, db_session, sample_tenant, active_campaign):
        found = CampaignService.validate_coupon("SUMMER10", sample_tenant.id)
        assert found is not None
        assert found.id == active_campaign.id

    def test_invalid_coupon(self, db_session, sample_tenant):
        assert CampaignService.validate_coupon("NOPE", sample_tenant.id) is None

    def test_tenant_isolation(self, db_session, active_campaign):
        assert CampaignService.validate_coupon("SUMMER10", 999999) is None
