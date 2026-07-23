"""Promotion engine — bundle/BOGO/tiered/combo math, allocation, isolation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from extensions import db
from models.campaign import Campaign, SaleCampaign
from services.promotion_service import PromotionService


def _window(days_back=1, days_fwd=30):
    now = datetime.now(timezone.utc)
    return now - timedelta(days=days_back), now + timedelta(days=days_fwd)


def make_campaign(db_session, tenant_id, **kw):
    start, end = _window()
    campaign = Campaign(
        tenant_id=tenant_id,
        name=kw.pop("name", f"Promo {uuid.uuid4().hex[:6]}"),
        campaign_type=kw.pop("campaign_type", "bundle"),
        discount_value=kw.pop("discount_value", Decimal("0")),
        start_date=kw.pop("start_date", start),
        end_date=kw.pop("end_date", end),
        is_active=kw.pop("is_active", True),
        applies_to_pos=kw.pop("applies_to_pos", True),
        rule_config=kw.pop("rule_config", None),
        **kw,
    )
    db_session.add(campaign)
    db_session.flush()
    return campaign


@pytest.fixture
def other_tenant(db_session):
    from models import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Co {unique}",
        name_ar="شركة أخرى",
        slug=f"other-co-{unique}",
        email=f"other-{unique}@example.com",
        phone_1="0500000000",
        country="AE",
        subscription_plan="basic",
        default_currency="AED",
        base_currency="AED",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


@pytest.fixture
def other_branch(db_session, sample_tenant):
    from models import Branch

    unique = uuid.uuid4().hex[:4].upper()
    branch = Branch(
        tenant_id=sample_tenant.id,
        name=f"Second Branch {unique}",
        code=f"SB{unique}",
        is_active=True,
        is_main=False,
    )
    db_session.add(branch)
    db_session.flush()
    return branch


def cart(*items):
    """items: (product_id, quantity, unit_price) or (..., category_id)."""
    lines = []
    for item in items:
        pid, qty, price = item[0], item[1], item[2]
        lines.append(
            {
                "product_id": pid,
                "quantity": qty,
                "unit_price": price,
                "category_id": item[3] if len(item) > 3 else None,
            }
        )
    return lines


class TestBundleRules:
    def test_bundle_remainder_math(self, db_session, sample_tenant):
        """4 items with 'Buy 3 for 25' → 3 at bundle + 1 at unit price."""
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "25"},
        )
        result = PromotionService.evaluate_cart(cart((1, 4, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("5.000")
        assert result["subtotal_before"] == Decimal("40.000")
        assert result["subtotal_after"] == Decimal("35.000")
        assert result["lines"][0]["discount_amount"] == Decimal("5.000")
        assert len(result["applied_rules"]) == 1
        assert result["applied_rules"][0]["campaign_type"] == "bundle"

    def test_bundle_remainder_upsell_prompt(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "25"},
        )
        result = PromotionService.evaluate_cart(cart((1, 4, "10")), tenant_id=sample_tenant.id)
        prompts = result["upsell_prompts"]
        assert len(prompts) == 1
        assert prompts[0]["type"] == "bundle"
        assert prompts[0]["product_id"] == 1
        assert prompts[0]["needed_quantity"] == "2"

    def test_bundle_cross_product_groups_most_expensive(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "40"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "10"), (2, 1, "20"), (3, 1, "30")),
            tenant_id=sample_tenant.id,
        )
        # Most expensive pair (30 + 20 = 50) grouped → discount 10; the 10 unit remains.
        assert result["total_discount"] == Decimal("10.000")
        by_pid = {ln["product_id"]: ln for ln in result["lines"]}
        assert by_pid[3]["discount_amount"] == Decimal("6.000")
        assert by_pid[2]["discount_amount"] == Decimal("4.000")
        assert by_pid[1]["discount_amount"] == Decimal("0.000")

    def test_bundle_no_discount_when_price_not_better(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "30"},
        )
        result = PromotionService.evaluate_cart(cart((1, 3, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")
        assert result["applied_rules"] == []
        assert result["upsell_prompts"] == []

    def test_bundle_multiple_groups(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "25"},
        )
        result = PromotionService.evaluate_cart(cart((1, 7, "10")), tenant_id=sample_tenant.id)
        # Two full groups (6 units) → 2 × 5; 1 remainder at unit price.
        assert result["total_discount"] == Decimal("10.000")

    def test_bundle_proration_plug_sums_exactly(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "29"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "10"), (2, 1, "10"), (3, 1, "10")),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("1.000")
        allocated = sum(ln["discount_amount"] for ln in result["lines"])
        assert allocated == result["total_discount"]

    def test_bundle_scoped_to_applicable_products(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            applicable_products=[1],
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "10"), (2, 1, "10")),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("0.000")

    def test_bundle_scoped_to_applicable_categories(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            applicable_categories=[7],
        )
        result = PromotionService.evaluate_cart(
            cart((1, 2, "10", 7)),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("5.000")

    def test_bundle_discount_value_fallback(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            discount_value=Decimal("25"),
            rule_config={"bundle_size": 3},
        )
        result = PromotionService.evaluate_cart(cart((1, 3, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("5.000")


class TestBogoRules:
    def test_bogo_cheapest_free(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bogo",
            rule_config={"buy_quantity": 2, "get_quantity": 1, "get_discount_percent": "100"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "10"), (2, 1, "20"), (3, 1, "30")),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("10.000")
        by_pid = {ln["product_id"]: ln for ln in result["lines"]}
        assert by_pid[1]["discount_amount"] == Decimal("10.000")
        assert by_pid[2]["discount_amount"] == Decimal("0.000")

    def test_bogo_multiple_groups_cheapest_overall(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bogo",
            rule_config={"buy_quantity": 2, "get_quantity": 1, "get_discount_percent": "100"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "30"), (2, 1, "25"), (3, 1, "24"), (4, 1, "5"), (5, 1, "4"), (6, 1, "3")),
            tenant_id=sample_tenant.id,
        )
        # 2 groups → 2 cheapest overall (3 + 4) are free.
        assert result["total_discount"] == Decimal("7.000")

    def test_bogo_partial_group_no_discount(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bogo",
            rule_config={"buy_quantity": 2, "get_quantity": 1},
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")
        prompts = result["upsell_prompts"]
        assert len(prompts) == 1
        assert prompts[0]["type"] == "bogo"
        assert prompts[0]["needed_quantity"] == "1"

    def test_bogo_half_price_second_item(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bogo",
            rule_config={"buy_quantity": 1, "get_quantity": 1, "get_discount_percent": "50"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "10"), (2, 1, "20")),
            tenant_id=sample_tenant.id,
        )
        # Cheapest (10) at 50% → 5.
        assert result["total_discount"] == Decimal("5.000")


class TestTieredRules:
    def test_tiered_percent_over_amount_threshold(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="percentage",
            discount_value=Decimal("10"),
            min_order_amount=Decimal("100"),
        )
        result = PromotionService.evaluate_cart(cart((1, 3, "50")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("15.000")

    def test_tiered_below_threshold_no_discount_and_upsell(self, db_session, sample_tenant):
        campaign = make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="percentage",
            discount_value=Decimal("10"),
            min_order_amount=Decimal("100"),
        )
        result = PromotionService.evaluate_cart(cart((1, 1, "50")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")
        prompts = result["upsell_prompts"]
        assert len(prompts) == 1
        assert prompts[0]["campaign_id"] == campaign.id
        assert prompts[0]["needed_amount"] == "50.000"

    def test_tiered_fixed_amount_capped(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="fixed",
            discount_value=Decimal("80"),
            max_discount_amount=Decimal("50"),
        )
        result = PromotionService.evaluate_cart(cart((1, 3, "50")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("50.000")

    def test_tiered_quantity_threshold(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="percentage",
            discount_value=Decimal("10"),
            min_quantity=Decimal("5"),
        )
        result = PromotionService.evaluate_cart(cart((1, 4, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")
        assert result["upsell_prompts"][0]["needed_quantity"] == "1"

        result = PromotionService.evaluate_cart(cart((1, 5, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("5.000")

    def test_tiered_quantization(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="percentage",
            discount_value=Decimal("33.333"),
        )
        result = PromotionService.evaluate_cart(cart((1, 1, "100")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("33.333")


class TestComboRules:
    def test_combo_fixed_amount(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="combo",
            discount_value=Decimal("10"),
            rule_config={"required_products": [1, 2]},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "15"), (2, 1, "25")),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("10.000")
        assert result["applied_rules"][0]["campaign_type"] == "combo"

    def test_combo_percent_of_set(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="combo",
            discount_value=Decimal("50"),
            rule_config={"required_products": [1, 2], "discount_type": "percent"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 1, "10"), (2, 1, "20")),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("15.000")

    def test_combo_missing_product_no_discount_and_upsell(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="combo",
            discount_value=Decimal("10"),
            rule_config={"required_products": [1, 2]},
        )
        result = PromotionService.evaluate_cart(cart((1, 1, "15")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")
        prompts = result["upsell_prompts"]
        assert len(prompts) == 1
        assert prompts[0]["type"] == "combo"
        assert prompts[0]["product_id"] == 2

    def test_combo_multiple_sets(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="combo",
            discount_value=Decimal("10"),
            rule_config={"required_products": [1, 2]},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 2, "15"), (2, 2, "25")),
            tenant_id=sample_tenant.id,
        )
        assert result["total_discount"] == Decimal("20.000")


class TestBestCombination:
    def test_bigger_discount_rule_wins_no_double_count(self, db_session, sample_tenant):
        """Tiered 20% (8) beats bundle (5) on the same units → only tiered fires."""
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "25"},
        )
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="percentage",
            discount_value=Decimal("20"),
            min_order_amount=Decimal("30"),
        )
        result = PromotionService.evaluate_cart(cart((1, 4, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("8.000")
        assert len(result["applied_rules"]) == 1
        assert result["applied_rules"][0]["campaign_type"] == "percentage"

    def test_units_consumed_not_rediscounted(self, db_session, sample_tenant):
        """Bundle (5) consumes 3 units; tiered 5% then only sees the remaining 2."""
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "25"},
        )
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="percentage",
            discount_value=Decimal("5"),
        )
        result = PromotionService.evaluate_cart(cart((1, 5, "10")), tenant_id=sample_tenant.id)
        rules = {r["campaign_type"]: r["discount_amount"] for r in result["applied_rules"]}
        assert rules["bundle"] == Decimal("5.000")
        assert rules["percentage"] == Decimal("1.000")  # 5% of remaining 20, not full 50
        assert result["total_discount"] == Decimal("6.000")
        allocated = sum(ln["discount_amount"] for ln in result["lines"])
        assert allocated == result["total_discount"]


class TestValidityAndIsolation:
    def test_expired_campaign_not_applied(self, db_session, sample_tenant):
        now = datetime.now(timezone.utc)
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            start_date=now - timedelta(days=10),
            end_date=now - timedelta(days=1),
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")

    def test_future_campaign_not_applied(self, db_session, sample_tenant):
        now = datetime.now(timezone.utc)
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            start_date=now + timedelta(days=1),
            end_date=now + timedelta(days=10),
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")

    def test_inactive_campaign_not_applied(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            is_active=False,
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")

    def test_non_pos_campaign_not_applied(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            applies_to_pos=False,
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")

    def test_tenant_isolation(self, db_session, sample_tenant, other_tenant):
        make_campaign(
            db_session,
            other_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")

    def test_usage_limit_blocks_campaign(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            usage_limit=3,
            usage_count=3,
        )
        result = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")

    def test_branch_scoped_campaign(self, db_session, sample_tenant, sample_branch, other_branch):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
            branch_id=sample_branch.id,
        )
        hit = PromotionService.evaluate_cart(
            cart((1, 2, "10")), tenant_id=sample_tenant.id, branch_id=sample_branch.id
        )
        assert hit["total_discount"] == Decimal("5.000")

        miss = PromotionService.evaluate_cart(
            cart((1, 2, "10")), tenant_id=sample_tenant.id, branch_id=other_branch.id
        )
        assert miss["total_discount"] == Decimal("0.000")

        global_only = PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=sample_tenant.id)
        assert global_only["total_discount"] == Decimal("0.000")

    def test_global_campaign_applies_to_any_branch(self, db_session, sample_tenant, other_branch):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
        )
        result = PromotionService.evaluate_cart(
            cart((1, 2, "10")), tenant_id=sample_tenant.id, branch_id=other_branch.id
        )
        assert result["total_discount"] == Decimal("5.000")


class TestCartValidation:
    def test_empty_cart_raises(self, db_session, sample_tenant):
        with pytest.raises(ValueError):
            PromotionService.evaluate_cart([], tenant_id=sample_tenant.id)

    def test_invalid_quantity_raises(self, db_session, sample_tenant):
        with pytest.raises(ValueError):
            PromotionService.evaluate_cart(cart((1, 0, "10")), tenant_id=sample_tenant.id)

    def test_fractional_units_do_not_qualify(self, db_session, sample_tenant):
        make_campaign(
            db_session,
            sample_tenant.id,
            campaign_type="bundle",
            rule_config={"bundle_size": 3, "bundle_price": "25"},
        )
        result = PromotionService.evaluate_cart(cart((1, "2.5", "10")), tenant_id=sample_tenant.id)
        assert result["total_discount"] == Decimal("0.000")


class TestRecordAppliedPromotions:
    def _evaluate(self, db_session, tenant_id):
        make_campaign(
            db_session,
            tenant_id,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "15"},
        )
        return PromotionService.evaluate_cart(cart((1, 2, "10")), tenant_id=tenant_id)

    def test_records_sale_campaign_rows_and_usage(self, db_session, sample_tenant, sample_sale):
        evaluation = self._evaluate(db_session, sample_tenant.id)
        total = PromotionService.record_applied_promotions(sample_sale, evaluation)
        assert total == Decimal("5.000")
        assert sample_sale.promotion_discount_amount == Decimal("5.000")

        rows = (
            db_session.query(SaleCampaign)
            .filter_by(sale_id=sample_sale.id, tenant_id=sample_tenant.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].discount_amount == Decimal("5.000")

        campaign = db_session.get(Campaign, evaluation["applied_rules"][0]["campaign_id"])
        assert campaign.usage_count == 1

    def test_no_evaluation_records_zero(self, db_session, sample_sale):
        total = PromotionService.record_applied_promotions(sample_sale, None)
        assert total == Decimal("0")
        assert sample_sale.promotion_discount_amount == Decimal("0")

    def test_cross_tenant_campaign_row_skipped(self, db_session, sample_tenant, other_tenant, sample_sale):
        evaluation = self._evaluate(db_session, sample_tenant.id)
        # Forge an applied rule pointing at a campaign owned by another tenant.
        foreign = make_campaign(
            db_session,
            other_tenant.id,
            campaign_type="fixed",
            discount_value=Decimal("10"),
        )
        evaluation["applied_rules"].append(
            {
                "campaign_id": foreign.id,
                "name": foreign.name,
                "campaign_type": "fixed",
                "discount_amount": Decimal("10.000"),
            }
        )
        total = PromotionService.record_applied_promotions(sample_sale, evaluation)
        assert total == Decimal("5.000")
        rows = db_session.query(SaleCampaign).filter_by(sale_id=sample_sale.id).all()
        assert all(r.campaign_id != foreign.id for r in rows)
