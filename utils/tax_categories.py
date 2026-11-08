"""Mixed-category VAT math — the single implementation of the split.

Used by the sale/purchase models (via their ``calculate_totals``) and by the
basket-preview routes, so the preview and the posted document always agree.
Zero/exempt categories take effect only when the tenant enabled tax
categories; otherwise every line posts as standard and the result is exactly
the pre-feature math.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from utils.tax_settings import effective_tax_category


def _q3(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def split_by_category(lines, *, tenant_id=None, tax_categories_enabled=None):
    """Sum line totals into (standard, zero, exempt)."""
    std_net = Decimal("0")
    zero_net = Decimal("0")
    exempt_net = Decimal("0")
    for line in lines:
        total = getattr(line, "line_total", None) if not isinstance(line, dict) else line.get("line_total")
        category = (
            line.get("tax_category") if isinstance(line, dict) else getattr(line, "tax_category", "standard")
        ) or "standard"
        amount = Decimal(str(total or 0))
        effective = effective_tax_category(category, tenant_id, enabled=tax_categories_enabled)
        if effective == "zero":
            zero_net += amount
        elif effective == "exempt":
            exempt_net += amount
        else:
            std_net += amount
    return std_net, zero_net, exempt_net


def compute_amounts(
    lines,
    *,
    tax_rate,
    discount_amount=Decimal("0"),
    promotion_discount=Decimal("0"),
    shipping_cost=Decimal("0"),
    prices_include_vat=False,
    tenant_id=None,
    tax_categories_enabled=None,
):
    """Return ``(taxable_amount, tax_amount, total_before_extras, after_discount)``.

    ``total_before_extras`` is the document total excluding landed cost — the
    purchase flow adds landed cost on top, the sale flow adds nothing.
    """
    rate = Decimal(str(tax_rate or 0))
    discount = Decimal(str(discount_amount or 0))
    promo = Decimal(str(promotion_discount or 0))
    shipping = Decimal(str(shipping_cost or 0))

    std_net = Decimal("0")
    zero_net = Decimal("0")
    exempt_net = Decimal("0")
    for line in lines:
        total = getattr(line, "line_total", None) if not isinstance(line, dict) else line.get("line_total")
        category = (
            line.get("tax_category") if isinstance(line, dict) else getattr(line, "tax_category", "standard")
        ) or "standard"
        amount = Decimal(str(total or 0))
        effective = effective_tax_category(category, tenant_id, enabled=tax_categories_enabled)
        if effective == "zero":
            zero_net += amount
        elif effective == "exempt":
            exempt_net += amount
        else:
            std_net += amount

    gross_lines = std_net + zero_net + exempt_net

    if gross_lines > 0:
        ratio = (gross_lines - discount - promo + shipping) / gross_lines
        std_base = std_net * ratio
        zero_base = zero_net * ratio
        exempt_base = exempt_net * ratio
    else:
        std_base, zero_base, exempt_base = Decimal("0"), Decimal("0"), Decimal("0")
    after_discount = std_base + zero_base + exempt_base
    taxable_base = _q3(std_base + zero_base)

    if prices_include_vat:
        if rate > 0:
            taxable_std = _q3(std_base / (Decimal("1") + rate / Decimal("100")))
            tax_amount = _q3(std_base - taxable_std)
            taxable_amount = _q3(taxable_std + zero_base)
        else:
            taxable_amount = taxable_base
            tax_amount = Decimal("0")
        total = _q3(after_discount)
    else:
        taxable_amount = taxable_base
        tax_amount = _q3(std_base * rate / Decimal("100"))
        total = _q3(after_discount + tax_amount)

    return taxable_amount, tax_amount, total, _q3(after_discount)
