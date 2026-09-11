"""Coverage boost for services/promotion_service.py.

Targets fallback/except branches missed by the base suite (pure-unit paths:
_id_list, _normalize_cart, _eligible, _prorate, rule evaluators, upsell
prompts, record_applied_promotions). Real PromotionService methods run with
SimpleNamespace campaigns; DB is touched only via mocks.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from services.promotion_service import PromotionService


def _camp(**kw):
    base = {
        "id": 1,
        "name": "P",
        "campaign_type": "bundle",
        "discount_value": Decimal("0"),
        "rule_config": {},
        "applicable_products": None,
        "applicable_categories": None,
        "usage_limit": None,
        "usage_count": 0,
        "min_order_amount": Decimal("0"),
        "min_quantity": Decimal("0"),
        "max_discount_amount": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _lines_units(cart):
    return PromotionService._normalize_cart(cart)


class TestIdList:
    def test_non_list_returns_empty(self):
        assert PromotionService._id_list("1,2") == []
        assert PromotionService._id_list(None) == []

    def test_skips_non_numeric_values(self):
        assert PromotionService._id_list([1, "x", None, "3"]) == [1, 3]


class TestNormalizeCart:
    def test_non_dict_line_raises(self):
        try:
            PromotionService._normalize_cart(["nope"])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_bad_numeric_raises(self):
        try:
            PromotionService._normalize_cart([{"product_id": 1, "quantity": "abc", "unit_price": "5"}])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_empty_cart_raises(self):
        try:
            PromotionService._normalize_cart([])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


class TestEligible:
    def test_non_numeric_category_returns_false(self):
        camp = _camp(applicable_categories=[7])
        lines, units = _lines_units([{"product_id": 1, "quantity": 1, "unit_price": "10", "category_id": "zz"}])
        assert PromotionService._eligible(camp, product_id=1, category_id="zz") is False
        assert PromotionService._eligible_units(camp, lines, units) == []

    def test_none_category_with_required_categories_returns_false(self):
        camp = _camp(applicable_categories=[7])
        assert PromotionService._eligible(camp, product_id=1, category_id=None) is False


class TestProrate:
    def test_zero_total_or_discount_returns_empty(self):
        lines, units = _lines_units([{"product_id": 1, "quantity": 1, "unit_price": "0"}])
        assert PromotionService._prorate(Decimal("5"), units) == {}
        lines2, units2 = _lines_units([{"product_id": 1, "quantity": 1, "unit_price": "10"}])
        assert PromotionService._prorate(Decimal("0"), units2) == {}


class TestBundleGuards:
    def test_non_numeric_bundle_size_returns_none(self):
        camp = _camp(rule_config={"bundle_size": "xx", "bundle_price": "5"})
        lines, units = _lines_units([{"product_id": 1, "quantity": 3, "unit_price": "10"}])
        assert PromotionService._eval_bundle(camp, lines, units) is None

    def test_negative_bundle_price_returns_none(self):
        camp = _camp(rule_config={"bundle_size": 2, "bundle_price": "-1"})
        lines, units = _lines_units([{"product_id": 1, "quantity": 2, "unit_price": "10"}])
        assert PromotionService._eval_bundle(camp, lines, units) is None

    def test_discount_value_fallback_price(self):
        camp = _camp(rule_config={"bundle_size": 2}, discount_value=Decimal("15"))
        lines, units = _lines_units([{"product_id": 1, "quantity": 2, "unit_price": "10"}])
        app = PromotionService._eval_bundle(camp, lines, units)
        assert app is not None
        assert app["discount"] == Decimal("5.000")


class TestTieredGuards:
    def _tiered_lines(self):
        return _lines_units([{"product_id": 1, "quantity": 2, "unit_price": "50"}])

    def test_percent_over_100_returns_none(self):
        camp = _camp(campaign_type="tiered", discount_value=Decimal("150"), rule_config={"discount_type": "percent"})
        lines, units = self._tiered_lines()
        assert PromotionService._eval_tiered(camp, lines, units) is None

    def test_zero_percent_returns_none(self):
        camp = _camp(campaign_type="percentage", discount_value=Decimal("0"), rule_config={"discount_type": "percent"})
        lines, units = self._tiered_lines()
        assert PromotionService._eval_tiered(camp, lines, units) is None

    def test_fixed_zero_returns_none(self):
        camp = _camp(campaign_type="fixed", discount_value=Decimal("0"), rule_config={})
        lines, units = self._tiered_lines()
        assert PromotionService._eval_tiered(camp, lines, units) is None

    def test_cap_can_zero_out_discount(self):
        camp = _camp(
            campaign_type="fixed", discount_value=Decimal("10"), rule_config={}, max_discount_amount=Decimal("0.0001")
        )
        lines, units = self._tiered_lines()
        # cap 0.0001 quantizes to 0.000 -> discount <= 0 -> None
        assert PromotionService._eval_tiered(camp, lines, units) is None


class TestComboGuards:
    def _combo_lines(self):
        return _lines_units(
            [
                {"product_id": 1, "quantity": 1, "unit_price": "30"},
                {"product_id": 2, "quantity": 1, "unit_price": "20"},
            ]
        )

    def test_single_required_returns_none(self):
        camp = _camp(campaign_type="combo", discount_value=Decimal("5"), rule_config={"required_products": [1]})
        lines, units = self._combo_lines()
        assert PromotionService._eval_combo(camp, lines, units) is None

    def test_zero_discount_returns_none(self):
        camp = _camp(campaign_type="combo", discount_value=Decimal("0"), rule_config={"required_products": [1, 2]})
        lines, units = self._combo_lines()
        assert PromotionService._eval_combo(camp, lines, units) is None

    def test_percent_over_100_returns_none(self):
        camp = _camp(
            campaign_type="combo",
            discount_value=Decimal("120"),
            rule_config={"required_products": [1, 2], "discount_type": "percent"},
        )
        lines, units = self._combo_lines()
        assert PromotionService._eval_combo(camp, lines, units) is None

    def test_missing_product_returns_none(self):
        camp = _camp(campaign_type="combo", discount_value=Decimal("5"), rule_config={"required_products": [1, 99]})
        lines, units = self._combo_lines()
        assert PromotionService._eval_combo(camp, lines, units) is None

    def test_cap_applies_per_set(self):
        camp = _camp(
            campaign_type="combo",
            discount_value=Decimal("50"),
            rule_config={"required_products": [1, 2]},
            max_discount_amount=Decimal("5"),
        )
        lines, units = self._combo_lines()
        app = PromotionService._eval_combo(camp, lines, units)
        assert app is not None
        assert app["discount"] == Decimal("5.000")

    def test_cap_zero_breaks_sets(self):
        camp = _camp(
            campaign_type="combo",
            discount_value=Decimal("50"),
            rule_config={"required_products": [1, 2]},
            max_discount_amount=Decimal("0"),
        )
        lines, units = self._combo_lines()
        # cap Decimal("0") is falsy -> cap None; use tiny cap that quantizes to 0
        camp.max_discount_amount = Decimal("0.0001")
        assert PromotionService._eval_combo(camp, lines, units) is None


class TestBogoGuards:
    def _bogo_lines(self):
        return _lines_units([{"product_id": 1, "quantity": 4, "unit_price": "10"}])

    def test_non_numeric_quantities_return_none(self):
        camp = _camp(campaign_type="bogo", rule_config={"buy_quantity": "x", "get_quantity": 1})
        lines, units = self._bogo_lines()
        assert PromotionService._eval_bogo(camp, lines, units) is None

    def test_zero_percent_returns_none(self):
        camp = _camp(
            campaign_type="bogo", rule_config={"buy_quantity": 1, "get_quantity": 1, "get_discount_percent": "0"}
        )
        lines, units = self._bogo_lines()
        assert PromotionService._eval_bogo(camp, lines, units) is None

    def test_over_100_percent_returns_none(self):
        camp = _camp(
            campaign_type="bogo", rule_config={"buy_quantity": 1, "get_quantity": 1, "get_discount_percent": "150"}
        )
        lines, units = self._bogo_lines()
        assert PromotionService._eval_bogo(camp, lines, units) is None

    def test_zero_price_units_yield_no_discount(self):
        camp = _camp(
            campaign_type="bogo", rule_config={"buy_quantity": 1, "get_quantity": 1, "get_discount_percent": "100"}
        )
        lines, units = _lines_units([{"product_id": 1, "quantity": 2, "unit_price": "0"}])
        # unit_price 0 is allowed (>= 0); freebies share 0 -> discount 0 -> None
        assert PromotionService._eval_bogo(camp, lines, units) is None


class TestEvaluateRule:
    def test_unknown_type_returns_none(self):
        camp = _camp(campaign_type="mystery")
        lines, units = _lines_units([{"product_id": 1, "quantity": 1, "unit_price": "10"}])
        assert PromotionService._evaluate_rule(camp, lines, units) is None


class TestUpsellEdgeBranches:
    def _run_upsell(self, campaigns, cart):
        lines, units = _lines_units(cart)
        return PromotionService._build_upsell_prompts(campaigns, lines, units)

    def test_bundle_bad_size_no_prompt(self):
        camp = _camp(campaign_type="bundle", rule_config={"bundle_size": "xx"})
        assert self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}]) == []

    def test_bogo_bad_config_no_prompt(self):
        camp = _camp(campaign_type="bogo", rule_config={"buy_quantity": "x", "get_quantity": 1})
        assert self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}]) == []

    def test_bogo_exact_multiple_no_prompt(self):
        camp = _camp(campaign_type="bogo", rule_config={"buy_quantity": 1, "get_quantity": 1})
        # 2 units, group of 2 -> remainder 0 -> no prompt
        assert self._run_upsell([camp], [{"product_id": 1, "quantity": 2, "unit_price": "10"}]) == []

    def test_unknown_type_no_prompt(self):
        camp = _camp(campaign_type="mystery")
        assert self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}]) == []

    def test_combo_nothing_remaining_no_prompt(self):
        from services.promotion_service import PromotionService as PS

        camp = _camp(
            campaign_type="combo",
            discount_value=Decimal("5"),
            rule_config={"required_products": [1, 2]},
        )
        lines, units = PS._normalize_cart([{"product_id": 1, "quantity": 1, "unit_price": "10"}])
        for u in units:
            u.consumed = True
        assert PS._build_upsell_prompts([camp], lines, units) == []

    def test_tiered_amount_prompt(self):
        camp = _camp(campaign_type="tiered", min_order_amount=Decimal("100"), rule_config={})
        prompts = self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}])
        assert len(prompts) == 1
        assert prompts[0]["needed_amount"] == "90.000"

    def test_tiered_quantity_prompt(self):
        camp = _camp(campaign_type="tiered", min_quantity=Decimal("5"), rule_config={})
        prompts = self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}])
        assert len(prompts) == 1

    def test_combo_partial_missing_prompts(self):
        camp = _camp(campaign_type="combo", discount_value=Decimal("5"), rule_config={"required_products": [1, 2]})
        prompts = self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}])
        assert len(prompts) == 1
        assert prompts[0]["product_id"] == 2

    def test_combo_all_missing_no_prompt(self):
        camp = _camp(campaign_type="combo", discount_value=Decimal("5"), rule_config={"required_products": [8, 9]})
        assert self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}]) == []

    def test_combo_single_required_no_prompt(self):
        camp = _camp(campaign_type="combo", discount_value=Decimal("5"), rule_config={"required_products": [1]})
        assert self._run_upsell([camp], [{"product_id": 1, "quantity": 1, "unit_price": "10"}]) == []


class TestRecordApplied:
    def _sale(self, tenant_id=1):
        sale = SimpleNamespace(id=10, tenant_id=tenant_id, promotion_discount_amount=None)
        return sale

    def test_empty_evaluation_zeroes_discount(self):
        sale = self._sale()
        out = PromotionService.record_applied_promotions(sale, None)
        assert out == Decimal("0")
        assert sale.promotion_discount_amount == Decimal("0")

    def test_zero_amount_rule_skipped(self):
        sale = self._sale()
        with patch("services.promotion_service.db") as mock_db:
            out = PromotionService.record_applied_promotions(
                sale, {"applied_rules": [{"campaign_id": 1, "discount_amount": Decimal("0")}]}
            )
        assert out == Decimal("0")
        mock_db.session.add.assert_not_called()

    def test_missing_campaign_skipped(self):
        sale = self._sale()
        with patch("services.promotion_service.db") as mock_db:
            mock_db.session.get.return_value = None
            out = PromotionService.record_applied_promotions(
                sale, {"applied_rules": [{"campaign_id": 999, "discount_amount": Decimal("5")}]}
            )
        assert out == Decimal("0")

    def test_cross_tenant_campaign_skipped(self):
        sale = self._sale(tenant_id=1)
        foreign = SimpleNamespace(id=3, tenant_id=2, usage_limit=None, usage_count=0)
        with patch("services.promotion_service.db") as mock_db:
            mock_db.session.get.return_value = foreign
            out = PromotionService.record_applied_promotions(
                sale, {"applied_rules": [{"campaign_id": 3, "discount_amount": Decimal("5")}]}
            )
        assert out == Decimal("0")

    def test_exhausted_usage_skipped(self):
        sale = self._sale(tenant_id=1)
        spent = SimpleNamespace(id=4, tenant_id=1, usage_limit=2, usage_count=2)
        with patch("services.promotion_service.db") as mock_db:
            mock_db.session.get.return_value = spent
            out = PromotionService.record_applied_promotions(
                sale, {"applied_rules": [{"campaign_id": 4, "discount_amount": Decimal("5")}]}
            )
        assert out == Decimal("0")

    def test_records_rule_and_bumps_usage(self):
        sale = self._sale(tenant_id=1)
        live = SimpleNamespace(id=5, tenant_id=1, usage_limit=10, usage_count=3)
        with patch("services.promotion_service.db") as mock_db:
            mock_db.session.get.return_value = live
            out = PromotionService.record_applied_promotions(
                sale, {"applied_rules": [{"campaign_id": 5, "discount_amount": Decimal("7.5")}]}
            )
        assert out == Decimal("7.500")
        assert sale.promotion_discount_amount == Decimal("7.500")
        assert live.usage_count == 4
        mock_db.session.add.assert_called_once()


class TestEvaluateCartGuards:
    def test_closed_usage_campaigns_ignored(self):
        cart = [{"product_id": 1, "quantity": 2, "unit_price": "10"}]
        spent = _camp(
            id=50,
            campaign_type="bundle",
            rule_config={"bundle_size": 2, "bundle_price": "5"},
            usage_limit=1,
            usage_count=5,
        )
        with patch.object(PromotionService, "get_active_pos_campaigns", return_value=[spent]):
            out = PromotionService.evaluate_cart(cart, tenant_id=1)
        assert out["total_discount"] == Decimal("0.000")
        assert out["applied_rules"] == []

    def test_consumed_units_not_double_counted(self):
        cart = [{"product_id": 1, "quantity": 4, "unit_price": "10"}]
        first = _camp(id=1, campaign_type="bundle", rule_config={"bundle_size": 2, "bundle_price": "12"})
        second = _camp(id=2, campaign_type="bundle", rule_config={"bundle_size": 4, "bundle_price": "20"})
        with patch.object(PromotionService, "get_active_pos_campaigns", return_value=[first, second]):
            out = PromotionService.evaluate_cart(cart, tenant_id=1)
        # greedy order: second (20 discount) first consumes all 4 units; first then finds nothing
        assert out["total_discount"] == Decimal("20.000")
        assert [r["campaign_id"] for r in out["applied_rules"]] == [2]
