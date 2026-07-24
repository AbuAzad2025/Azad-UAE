"""Smart Promotion & Dynamic Pricing Engine — Phase 1.

Evaluates tenant-scoped POS promotion rules (``Campaign`` rows with
``applies_to_pos=True``) against a cart of ``{product_id, quantity,
unit_price[, category_id]}`` lines and returns per-line discounts, the
rules that fired, and upsell prompts for the cashier UI.

Rule types (``Campaign.campaign_type``):

- ``bundle`` — "Buy N for X". ``rule_config``: ``bundle_size`` (N),
  ``bundle_price`` (X, falls back to ``discount_value``). Handles
  remainders: 4 items with N=3 → 3 at bundle price + 1 at unit price.
  Groups are formed from the most expensive eligible units first so the
  customer always gets the largest possible bundle discount.
- ``tiered`` / legacy ``percentage`` / ``fixed`` — cart threshold rules.
  Fires when the eligible value ≥ ``min_order_amount`` and the eligible
  unit count ≥ ``min_quantity`` (whichever thresholds are set).
  ``discount_value`` is a percent for ``percentage``/``tiered`` with
  ``rule_config.discount_type == "percent"``, otherwise a fixed amount.
  Capped by ``max_discount_amount``.
- ``combo`` — buy all of A+B(+...) together. Required products come from
  ``rule_config.required_products`` (falls back to
  ``applicable_products``). Discount per complete set is
  ``rule_config.discount_type`` ("percent" of set value or "amount"
  using ``discount_value``).
- ``bogo`` — buy N get M discounted. ``rule_config``: ``buy_quantity``,
  ``get_quantity``, ``get_discount_percent`` (default 100). The cheapest
  eligible items are the free/discounted ones.

Combination / allocation strategy (greedy, documented):

1. Every rule is scored on the full unconsumed cart to obtain its maximum
   potential discount.
2. Rules are then applied greedily in descending potential-discount order
   (ties broken by campaign id for determinism).
3. At apply time each rule is *re-evaluated against the remaining
   unconsumed units only*. Once a unit is consumed by a rule it can never
   be discounted — or used as a qualifier — by any later rule, so the same
   unit is never counted twice.

Greedy-by-discount is not a guaranteed global optimum for every
overlapping-rule combination, but it is deterministic, O(rules × units),
and in practice maximises the customer discount.

All money is strict ``Decimal`` quantized to 0.001 with ROUND_HALF_UP.
Only whole units participate in unit-based rules (bundle / combo / bogo);
fractional remainders keep their unit price and never qualify.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from extensions import db
from utils.tenanting import tenant_query

RULE_BUNDLE = "bundle"
RULE_TIERED = "tiered"
RULE_COMBO = "combo"
RULE_BOGO = "bogo"

_QUANTUM = Decimal("0.001")
_HUNDRED = Decimal("100")


class _Unit:
    """One indivisible cart unit used for rule allocation."""

    __slots__ = ("line_index", "product_id", "unit_price", "consumed")

    def __init__(self, line_index: int, product_id: int, unit_price: Decimal):
        self.line_index = line_index
        self.product_id = product_id
        self.unit_price = unit_price
        self.consumed = False


class PromotionService:
    QUANTUM = _QUANTUM

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _quantize(value) -> Decimal:
        return Decimal(str(value)).quantize(_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def _cfg(campaign) -> dict:
        cfg = getattr(campaign, "rule_config", None)
        return cfg if isinstance(cfg, dict) else {}

    @staticmethod
    def _id_list(raw) -> list[int]:
        if not isinstance(raw, list):
            return []
        out = []
        for value in raw:
            try:
                out.append(int(value))
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def _usage_open(campaign) -> bool:
        limit = getattr(campaign, "usage_limit", None)
        if not limit:
            return True
        return int(getattr(campaign, "usage_count", 0) or 0) < int(limit)

    @staticmethod
    def get_active_pos_campaigns(tenant_id, branch_id=None, now=None):
        """Active, in-window POS campaigns for the tenant (+ optional branch)."""
        from models.campaign import Campaign

        now = now or datetime.now(timezone.utc)
        query = tenant_query(Campaign).filter(
            Campaign.tenant_id == int(tenant_id),
            Campaign.is_active.is_(True),
            Campaign.applies_to_pos.is_(True),
            Campaign.start_date <= now,
            Campaign.end_date >= now,
        )
        if branch_id is not None:
            query = query.filter(
                db.or_(
                    Campaign.branch_id.is_(None),
                    Campaign.branch_id == int(branch_id),
                )
            )
        else:
            query = query.filter(Campaign.branch_id.is_(None))
        return query.order_by(Campaign.created_at.desc(), Campaign.id.desc()).all()

    # ── Cart normalization ─────────────────────────────────────────────

    @staticmethod
    def _normalize_cart(cart_lines):
        if not cart_lines:
            raise ValueError("بيانات السلة غير صالحة.")
        lines = []
        units = []
        for index, raw in enumerate(cart_lines):
            if not isinstance(raw, dict):
                raise ValueError("بيانات السلة غير صالحة.")
            try:
                product_id = int(raw.get("product_id") or 0)
                quantity = Decimal(str(raw.get("quantity") or "0"))
                unit_price = PromotionService._quantize(raw.get("unit_price") or "0")
            except (ArithmeticError, ValueError) as exc:
                raise ValueError("بيانات السلة غير صالحة.") from exc
            if product_id <= 0 or quantity <= 0 or unit_price < 0:
                raise ValueError("بيانات السلة غير صالحة.")
            line = {
                "index": index,
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": unit_price,
                "category_id": raw.get("category_id"),
                "promo_discount": Decimal("0"),
            }
            lines.append(line)
            for _ in range(int(quantity)):
                units.append(_Unit(index, product_id, unit_price))
        return lines, units

    @staticmethod
    def _eligible(campaign, *, product_id, category_id):
        products = PromotionService._id_list(getattr(campaign, "applicable_products", None))
        if products and product_id not in products:
            return False
        categories = PromotionService._id_list(getattr(campaign, "applicable_categories", None))
        if categories:
            try:
                if category_id is None or int(category_id) not in categories:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _eligible_units(campaign, lines, units):
        return [
            u
            for u in units
            if not u.consumed
            and PromotionService._eligible(
                campaign,
                product_id=u.product_id,
                category_id=lines[u.line_index]["category_id"],
            )
        ]

    # ── Rule evaluators ────────────────────────────────────────────────
    # Each evaluator inspects only *unconsumed* units and returns either
    # None (rule does not fire) or:
    #   {"campaign", "discount", "consumed": [units], "alloc": {unit: Decimal}}

    @staticmethod
    def _application(campaign, discount, consumed, alloc):
        return {
            "campaign": campaign,
            "discount": PromotionService._quantize(discount),
            "consumed": consumed,
            "alloc": alloc,
        }

    @staticmethod
    def _prorate(total_discount: Decimal, units_list: list) -> dict:
        """Spread a discount over units pro-rata by unit price.

        Independent per-unit rounding can drift a few fils; the residual is
        plugged onto the unit with the largest price so the allocation sums
        exactly to ``total_discount`` at 0.001 precision.
        """
        total_value = sum((u.unit_price for u in units_list), Decimal("0"))
        if total_value <= 0 or total_discount <= 0:
            return {}
        shares = []
        assigned = Decimal("0")
        for unit in units_list:
            share = PromotionService._quantize(total_discount * unit.unit_price / total_value)
            shares.append([unit, share])
            assigned += share
        diff = total_discount - assigned
        if diff:
            target = max(shares, key=lambda item: item[0].unit_price)
            target[1] += diff
        return {unit: share for unit, share in shares if share > 0}

    @staticmethod
    def _eval_bundle(campaign, lines, units):
        cfg = PromotionService._cfg(campaign)
        try:
            size = int(cfg.get("bundle_size") or 0)
        except (TypeError, ValueError):
            size = 0
        raw_price = cfg.get("bundle_price")
        bundle_price = (
            Decimal(str(raw_price))
            if raw_price is not None
            else Decimal(str(getattr(campaign, "discount_value", 0) or 0))
        )
        if size <= 1 or bundle_price < 0:
            return None
        eligible = PromotionService._eligible_units(campaign, lines, units)
        eligible.sort(key=lambda u: (-u.unit_price, u.line_index, u.product_id))
        groups = len(eligible) // size
        if groups <= 0:
            return None
        discount = Decimal("0")
        consumed = []
        alloc = {}
        for g in range(groups):
            group = eligible[g * size : (g + 1) * size]
            group_value = sum((u.unit_price for u in group), Decimal("0"))
            group_discount = PromotionService._quantize(group_value - bundle_price)
            if group_discount <= 0:
                break  # groups are price-descending; later ones cannot improve
            discount += group_discount
            consumed.extend(group)
            alloc.update(PromotionService._prorate(group_discount, group))
        if discount <= 0:
            return None
        return PromotionService._application(campaign, discount, consumed, alloc)

    @staticmethod
    def _eval_tiered(campaign, lines, units):
        cfg = PromotionService._cfg(campaign)
        min_amount = Decimal(str(getattr(campaign, "min_order_amount", 0) or 0))
        min_qty = Decimal(str(getattr(campaign, "min_quantity", 0) or 0))
        eligible = PromotionService._eligible_units(campaign, lines, units)
        value = sum((u.unit_price for u in eligible), Decimal("0"))
        if value < min_amount or Decimal(len(eligible)) < min_qty or value <= 0:
            return None
        campaign_type = getattr(campaign, "campaign_type", "")
        discount_type = cfg.get("discount_type")
        is_percent = campaign_type == "percentage" or discount_type == "percent"
        raw_value = Decimal(str(getattr(campaign, "discount_value", 0) or 0))
        if is_percent:
            if raw_value <= 0 or raw_value > _HUNDRED:
                return None
            discount = PromotionService._quantize(value * raw_value / _HUNDRED)
        else:
            if raw_value <= 0:
                return None
            discount = min(raw_value, value)
        cap = getattr(campaign, "max_discount_amount", None)
        if cap:
            discount = min(discount, Decimal(str(cap)))
        discount = PromotionService._quantize(discount)
        if discount <= 0:
            return None
        return PromotionService._application(
            campaign, discount, list(eligible), PromotionService._prorate(discount, eligible)
        )

    @staticmethod
    def _eval_combo(campaign, lines, units):
        cfg = PromotionService._cfg(campaign)
        required = PromotionService._id_list(cfg.get("required_products")) or PromotionService._id_list(
            getattr(campaign, "applicable_products", None)
        )
        if len(required) < 2:
            return None
        raw_value = Decimal(str(getattr(campaign, "discount_value", 0) or 0))
        if raw_value <= 0:
            return None
        is_percent = cfg.get("discount_type") == "percent"
        if is_percent and raw_value > _HUNDRED:
            return None
        cap = getattr(campaign, "max_discount_amount", None)
        cap = Decimal(str(cap)) if cap else None
        by_product = {}
        for u in units:
            if not u.consumed and u.product_id in required:
                by_product.setdefault(u.product_id, []).append(u)
        if any(pid not in by_product for pid in required):
            return None
        for bucket in by_product.values():
            bucket.sort(key=lambda u: (-u.unit_price, u.line_index))
        sets = min(len(by_product[pid]) for pid in required)
        discount = Decimal("0")
        consumed = []
        alloc = {}
        for s in range(sets):
            group = [by_product[pid][s] for pid in required]
            set_value = sum((u.unit_price for u in group), Decimal("0"))
            if is_percent:
                set_discount = PromotionService._quantize(set_value * raw_value / _HUNDRED)
            else:
                set_discount = min(raw_value, set_value)
            if cap is not None:
                set_discount = min(set_discount, cap - discount)
            set_discount = PromotionService._quantize(set_discount)
            if set_discount <= 0:
                break
            discount += set_discount
            consumed.extend(group)
            alloc.update(PromotionService._prorate(set_discount, group))
        if discount <= 0:
            return None
        return PromotionService._application(campaign, discount, consumed, alloc)

    @staticmethod
    def _eval_bogo(campaign, lines, units):
        cfg = PromotionService._cfg(campaign)
        try:
            buy_n = int(cfg.get("buy_quantity") or 0)
            get_m = int(cfg.get("get_quantity") or 0)
        except (TypeError, ValueError):
            return None
        pct = Decimal(str(cfg.get("get_discount_percent", _HUNDRED)))
        if buy_n <= 0 or get_m <= 0 or pct <= 0 or pct > _HUNDRED:
            return None
        eligible = PromotionService._eligible_units(campaign, lines, units)
        group_size = buy_n + get_m
        groups = len(eligible) // group_size
        if groups <= 0:
            return None
        eligible.sort(key=lambda u: (-u.unit_price, u.line_index, u.product_id))
        # Paid qualifiers are the most expensive units; the cheapest items
        # overall are the free/discounted ones.
        qualifiers = eligible[: groups * buy_n]
        freebies = eligible[len(eligible) - groups * get_m :]
        discount = Decimal("0")
        alloc = {}
        for unit in freebies:
            share = PromotionService._quantize(unit.unit_price * pct / _HUNDRED)
            if share > 0:
                discount += share
                alloc[unit] = share
        if discount <= 0:
            return None
        return PromotionService._application(campaign, discount, qualifiers + freebies, alloc)

    @staticmethod
    def _evaluate_rule(campaign, lines, units):
        campaign_type = getattr(campaign, "campaign_type", "")
        if campaign_type == RULE_BUNDLE:
            return PromotionService._eval_bundle(campaign, lines, units)
        if campaign_type in (RULE_TIERED, "percentage", "fixed"):
            return PromotionService._eval_tiered(campaign, lines, units)
        if campaign_type == RULE_COMBO:
            return PromotionService._eval_combo(campaign, lines, units)
        if campaign_type == RULE_BOGO:
            return PromotionService._eval_bogo(campaign, lines, units)
        return None

    # ── Main entry point ───────────────────────────────────────────────

    @staticmethod
    def evaluate_cart(cart_lines, tenant_id, branch_id=None, now=None):
        """Evaluate all active POS rules for the tenant against the cart.

        Returns a dict with per-line pricing, total promotional discount,
        the rules that fired, and upsell prompt metadata.
        """
        lines, units = PromotionService._normalize_cart(cart_lines)
        campaigns = [
            c
            for c in PromotionService.get_active_pos_campaigns(tenant_id, branch_id=branch_id, now=now)
            if PromotionService._usage_open(c)
        ]

        scored = []
        for campaign in campaigns:
            app = PromotionService._evaluate_rule(campaign, lines, units)
            if app and app["discount"] > 0:
                scored.append(app)
        scored.sort(key=lambda app: (-app["discount"], app["campaign"].id))

        applied = []
        for candidate in scored:
            campaign = candidate["campaign"]
            app = PromotionService._evaluate_rule(campaign, lines, units)
            if not app or app["discount"] <= 0:
                continue
            for unit in app["consumed"]:
                unit.consumed = True
            for unit, share in app["alloc"].items():
                lines[unit.line_index]["promo_discount"] += share
            applied.append(app)

        upsell = PromotionService._build_upsell_prompts(campaigns, lines, units)

        out_lines = []
        subtotal_before = Decimal("0")
        total_discount = Decimal("0")
        for line in lines:
            original_total = PromotionService._quantize(line["quantity"] * line["unit_price"])
            line_discount = PromotionService._quantize(line["promo_discount"])
            line_discount = min(line_discount, original_total)
            subtotal_before += original_total
            total_discount += line_discount
            out_lines.append(
                {
                    "product_id": line["product_id"],
                    "quantity": line["quantity"],
                    "unit_price": line["unit_price"],
                    "original_total": original_total,
                    "discount_amount": line_discount,
                    "adjusted_total": PromotionService._quantize(original_total - line_discount),
                }
            )

        return {
            "lines": out_lines,
            "subtotal_before": PromotionService._quantize(subtotal_before),
            "total_discount": PromotionService._quantize(total_discount),
            "subtotal_after": PromotionService._quantize(subtotal_before - total_discount),
            "applied_rules": [
                {
                    "campaign_id": app["campaign"].id,
                    "name": getattr(app["campaign"], "name", ""),
                    "campaign_type": getattr(app["campaign"], "campaign_type", ""),
                    "discount_amount": app["discount"],
                }
                for app in applied
            ],
            "upsell_prompts": upsell,
        }

    # ── Upsell prompts ─────────────────────────────────────────────────

    @staticmethod
    def _remaining_by_product(campaign, lines, units):
        remaining = {}
        for u in PromotionService._eligible_units(campaign, lines, units):
            remaining.setdefault(u.product_id, []).append(u)
        return remaining

    @staticmethod
    def _prompt(campaign, kind, message, product_id=None, needed_quantity=None, needed_amount=None):
        return {
            "type": kind,
            "campaign_id": campaign.id,
            "campaign_name": getattr(campaign, "name", ""),
            "product_id": product_id,
            "needed_quantity": str(needed_quantity) if needed_quantity is not None else None,
            "needed_amount": str(needed_amount) if needed_amount is not None else None,
            "message": message,
        }

    @staticmethod
    def _build_upsell_prompts(campaigns, lines, units):
        prompts = []
        for campaign in campaigns:
            campaign_type = getattr(campaign, "campaign_type", "")
            remaining = PromotionService._remaining_by_product(campaign, lines, units)
            total_remaining = sum(len(bucket) for bucket in remaining.values())

            if campaign_type == RULE_BUNDLE:
                cfg = PromotionService._cfg(campaign)
                try:
                    size = int(cfg.get("bundle_size") or 0)
                except (TypeError, ValueError):
                    size = 0
                if size > 1 and total_remaining > 0:
                    r = total_remaining % size
                    if r:
                        needed = size - r
                        product_id = next(iter(remaining)) if len(remaining) == 1 else None
                        prompts.append(
                            PromotionService._prompt(
                                campaign,
                                RULE_BUNDLE,
                                f"أضف {needed} قطعة إضافية للحصول على سعر العرض (اشترِ {size}).",
                                product_id=product_id,
                                needed_quantity=needed,
                            )
                        )

            elif campaign_type == RULE_BOGO:
                cfg = PromotionService._cfg(campaign)
                try:
                    buy_n = int(cfg.get("buy_quantity") or 0)
                    get_m = int(cfg.get("get_quantity") or 0)
                except (TypeError, ValueError):
                    buy_n, get_m = 0, 0
                group_size = buy_n + get_m
                if group_size > 0 and total_remaining > 0:
                    r = total_remaining % group_size
                    if r:
                        needed = group_size - r
                        product_id = next(iter(remaining)) if len(remaining) == 1 else None
                        prompts.append(
                            PromotionService._prompt(
                                campaign,
                                RULE_BOGO,
                                f"أضف {needed} قطعة إضافية واحصل على {get_m} بخصم (اشترِ {buy_n} واحصل على {get_m}).",
                                product_id=product_id,
                                needed_quantity=needed,
                            )
                        )

            elif campaign_type in (RULE_TIERED, "percentage", "fixed"):
                min_amount = Decimal(str(getattr(campaign, "min_order_amount", 0) or 0))
                min_qty = Decimal(str(getattr(campaign, "min_quantity", 0) or 0))
                value = sum(
                    (u.unit_price for bucket in remaining.values() for u in bucket),
                    Decimal("0"),
                )
                if min_amount > 0 and value < min_amount:
                    prompts.append(
                        PromotionService._prompt(
                            campaign,
                            RULE_TIERED,
                            f"أضف بقيمة {PromotionService._quantize(min_amount - value)} للحصول على الخصم.",
                            needed_amount=PromotionService._quantize(min_amount - value),
                        )
                    )
                elif min_qty > 0 and Decimal(total_remaining) < min_qty:
                    needed = (min_qty - Decimal(total_remaining)).normalize()
                    prompts.append(
                        PromotionService._prompt(
                            campaign,
                            RULE_TIERED,
                            f"أضف {needed} قطعة إضافية للحصول على الخصم.",
                            needed_quantity=needed,
                        )
                    )

            elif campaign_type == RULE_COMBO:
                cfg = PromotionService._cfg(campaign)
                required = PromotionService._id_list(cfg.get("required_products")) or PromotionService._id_list(
                    getattr(campaign, "applicable_products", None)
                )
                if len(required) >= 2 and remaining:
                    missing = [pid for pid in required if pid not in remaining]
                    if missing and len(missing) < len(required):
                        prompts.append(
                            PromotionService._prompt(
                                campaign,
                                RULE_COMBO,
                                "أضف المنتجات الناقصة لإكمال العرض المجمّع.",
                                product_id=missing[0],
                                needed_quantity=1,
                            )
                        )
        return prompts

    # ── Sale integration ───────────────────────────────────────────────

    @staticmethod
    def record_applied_promotions(sale, evaluation) -> Decimal:
        """Persist fired rules for a sale (SaleCampaign rows + usage counters).

        Services layer: flush only — the caller owns the transaction
        boundary. Returns the total promotional discount recorded on the
        sale's ``promotion_discount_amount``.
        """
        from models.campaign import Campaign, SaleCampaign

        total = Decimal("0")
        if not evaluation:
            sale.promotion_discount_amount = Decimal("0")
            return total

        tenant_id = getattr(sale, "tenant_id", None)
        for applied in evaluation.get("applied_rules", []):
            amount = PromotionService._quantize(applied.get("discount_amount") or "0")
            if amount <= 0:
                continue
            campaign = db.session.get(Campaign, int(applied.get("campaign_id") or 0))
            if campaign is None or int(campaign.tenant_id or 0) != int(tenant_id or 0):
                continue
            if not PromotionService._usage_open(campaign):
                continue
            db.session.add(
                SaleCampaign(
                    tenant_id=tenant_id,
                    campaign_id=campaign.id,
                    sale_id=sale.id,
                    discount_amount=amount,
                )
            )
            campaign.usage_count = int(campaign.usage_count or 0) + 1
            total += amount

        sale.promotion_discount_amount = PromotionService._quantize(total)
        return sale.promotion_discount_amount
