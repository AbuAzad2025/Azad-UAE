"""Cov4: campaign_service — filter/roi/commission/active/apply/coupon/list arcs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from services.campaign_service import CampaignService


def test_filter_json_overlap_branches():
    a = SimpleNamespace(applicable_products=None)
    b = SimpleNamespace(applicable_products="not-a-list")
    c = SimpleNamespace(applicable_products=[1, 2])
    d = SimpleNamespace(applicable_products=[9])
    out = CampaignService._filter_json_overlap([a, b, c, d], "applicable_products", [2, 3])
    assert out == [a, b, c]


def test_calculate_roi_and_safe_commission():
    assert CampaignService.calculate_roi(0, 100) == Decimal("0")
    assert CampaignService.calculate_roi(None, None) == Decimal("0")
    assert CampaignService.calculate_safe_commission(1000, 150) == Decimal("1000.00")
    assert CampaignService.calculate_safe_commission(1000, -5) == Decimal("0.00")
    assert CampaignService.safe_commission_rate(None) == Decimal("0")


def test_roi_metrics_no_usage(db_session, sample_tenant):
    camp = SimpleNamespace(id=3, discount_value=Decimal("10"), usage_count=0, name="C")
    m = CampaignService.get_campaign_roi_metrics(camp, total_revenue=Decimal("500"))
    assert m["total_cost"] == 0.0 and m["roi"] == 0.0


def test_get_active_campaigns_branches(db_session, sample_tenant):
    from models.campaign import Campaign

    now = datetime.now(UTC)
    camp = Campaign(
        tenant_id=sample_tenant.id,
        name="cov4",
        campaign_type="percentage",
        discount_value=Decimal("10"),
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        is_active=True,
        applicable_products=[7],
        applicable_categories=[9],
    )
    db_session.add(camp)
    db_session.flush()
    assert camp in CampaignService.get_active_campaigns(sample_tenant.id)
    assert camp in CampaignService.get_active_campaigns(sample_tenant.id, product_ids=[7])
    assert camp not in CampaignService.get_active_campaigns(sample_tenant.id, product_ids=[8])
    both = CampaignService.get_active_campaigns(sample_tenant.id, product_ids=[7], category_ids=[9])
    assert camp in both
    assert camp in CampaignService.get_active_campaigns(sample_tenant.id, category_ids=[9])
    assert camp not in CampaignService.get_active_campaigns(sample_tenant.id, category_ids=[10])


def test_apply_campaigns_skips_limits_and_caps(
    db_session, sample_tenant, sample_customer, sample_user, sample_warehouse
):
    from datetime import datetime as dt

    from models import Sale
    from models.campaign import Campaign

    now = dt.now(UTC)
    sale = Sale(
        tenant_id=sample_tenant.id,
        sale_number="CAMP-COV4",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        warehouse_id=sample_warehouse.id,
        sale_date=now,
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        amount=Decimal("1000"),
        amount_aed=Decimal("1000"),
        status="pending",
    )
    db_session.add(sale)
    db_session.flush()
    limited = Campaign(
        tenant_id=sample_tenant.id,
        name="lim",
        campaign_type="fixed",
        discount_value=Decimal("5"),
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        is_active=True,
        usage_limit=1,
        usage_count=5,
    )
    pct = Campaign(
        tenant_id=sample_tenant.id,
        name="pct",
        campaign_type="percentage",
        discount_value=Decimal("10"),
        max_discount_amount=Decimal("20"),
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        is_active=True,
    )
    bundle = Campaign(
        tenant_id=sample_tenant.id,
        name="bnd",
        campaign_type="bundle",
        discount_value=Decimal("7"),
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        is_active=True,
    )
    db_session.add_all([limited, pct, bundle])
    db_session.flush()
    total = CampaignService.apply_campaigns(sale, [limited, pct, bundle])
    assert total == Decimal("20") + Decimal("7")  # capped pct + bundle; limited skipped


def test_validate_coupon_and_list(db_session, sample_tenant):
    from datetime import datetime as dt

    from models.campaign import Campaign

    now = dt.now(UTC)
    camp = Campaign(
        tenant_id=sample_tenant.id,
        name="cpn",
        campaign_type="fixed",
        discount_value=Decimal("3"),
        coupon_code="COV4CODE",
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=1),
        is_active=True,
    )
    db_session.add(camp)
    db_session.flush()
    assert CampaignService.validate_coupon("COV4CODE", sample_tenant.id).id == camp.id
    assert CampaignService.validate_coupon("MISSING", sample_tenant.id) is None
    assert CampaignService.list_active_campaigns(None) == []
    assert camp in CampaignService.list_active_campaigns(sample_tenant.id)
